# Row-Key Based Tracking System

## Overview

The validator uses a **hash-based row tracking system** that replaces sequential integer indices with deterministic row key hashes. This enables:
- Reliable retry logic for failed rows
- Consistent matching between validation results, QC data, and history
- Order-independent result assembly
- Continuation chain support

---

## 1. Row Key Generation

### What is a Row Key?

A row key is a **SHA-256 hash** used to uniquely identify each row. The system uses a **hybrid hashing approach**:

- **ID-field hashing** (primary keys only) - Used for rows with unique IDs
- **Full-row hashing** (all fields) - Used for rows with duplicate IDs

```python
# From row_key_utils.py
def generate_row_key(row_data: dict, primary_key_fields: list) -> str:
    """
    Generate deterministic hash from specified fields.

    Args:
        row_data: Row dictionary
        primary_key_fields: List of ID field names, or None for full-row hash

    Returns: SHA-256 hash (64-character hex string)
    """
```

### Hybrid Hashing Strategy

**Why Hybrid?**
- **ID-field hashing** enables history matching (validated values don't affect the hash)
- **Full-row hashing** distinguishes rows with duplicate IDs
- **Best of both worlds**: History works for most rows, duplicates are still handled correctly

### When Are Row Keys Generated?

**Interface Lambda (background_handler.py:2828-2858):**
```python
# Two-pass hybrid hashing approach
id_hash_counts = {}

# Pass 1: Detect duplicate IDs
for row_idx, row_data in enumerate(excel_rows):
    id_hash = generate_row_key(row_data, primary_keys=id_fields)
    if id_hash not in id_hash_counts:
        id_hash_counts[id_hash] = []
    id_hash_counts[id_hash].append(row_idx)

# Pass 2: Assign final row keys
for row_idx, row_data in enumerate(excel_rows):
    id_hash = generate_row_key(row_data, primary_keys=id_fields)

    if len(id_hash_counts[id_hash]) > 1:
        # Duplicate ID → use full-row hash
        row_key = generate_row_key(row_data, primary_keys=None)
    else:
        # Unique ID → use ID-field hash (enables history matching)
        row_key = id_hash

    row_data['_row_key'] = row_key
    processed_rows.append(row_data)
```

**Timing:** Before sending to validator (both sync and async)

**Result:** All rows arrive at validator with pre-computed `_row_key`

### Example: Hybrid Hashing in Action

```
Input (278 rows):
  Row 1: ID=ABC, Name=Acme, City=NYC
  Row 2: ID=ABC, Name=Acme, City=NYC    (exact duplicate)
  Row 3: ID=ABC, Name=Acme, City=LA     (same ID, different data)
  Row 4: ID=DEF, Name=Beta, City=SF

Pass 1 - Detect duplicates:
  hash(ID=ABC): [0, 1, 2]  # 3 rows with same ID
  hash(ID=DEF): [3]         # 1 row with unique ID

Pass 2 - Assign row keys:
  Row 1: Duplicate ID → full-row hash → a7f8d9e2...
  Row 2: Duplicate ID → full-row hash → a7f8d9e2... (SAME as Row 1!)
  Row 3: Duplicate ID → full-row hash → b3e1c7a4... (different from Row 1)
  Row 4: Unique ID    → ID-field hash → c9d2f8b1...

Processed rows:
  {ID: ABC, ..., _row_key: a7f8d9e2...}  # Row 1
  {ID: ABC, ..., _row_key: a7f8d9e2...}  # Row 2 (same hash!)
  {ID: ABC, ..., _row_key: b3e1c7a4...}  # Row 3 (different data)
  {ID: DEF, ..., _row_key: c9d2f8b1...}  # Row 4 (history matching works!)
```

---

## 2. History Mapping from Details Sheet

### Purpose
Match current validation attempt with previous validation results stored in Excel "Details" sheet.

### Flow

**Step 1: Interface Loads History (background_handler.py:2761-2801)**
```python
# Load validation history from Excel Details sheet
from interface_lambda.utils.history_loader import load_validation_history_from_excel
original_validation_history = load_validation_history_from_excel(excel_file)

# Returns: {row_key_hash: {...previous_validation_data...}}
```

**Step 2: Match Current Rows to History**
```python
for row in processed_rows:
    payload_key = row.get('_row_key')
    if payload_key in validation_history:
        matched_count += 1
```

**Step 3: Send to Validator**
```python
payload = {
    "validation_data": {"rows": processed_rows},  # With _row_key
    "validation_history": validation_history      # Keyed by row_key
}
```

**Key Insights:**
- History matching works for rows with **unique IDs** (ID-field hash is stable across validations)
- Rows with **duplicate IDs** use full-row hashing (history matching disabled - we can't tell which historical entry corresponds to which duplicate)

---

## 3. Validation Row Tracking

### Data Structures

**Validator Lambda (lambda_function.py:3109-3127):**
```python
# Primary tracking structures
row_key_to_row_data = {}      # row_key → original row dict
pending_row_keys = []          # Ordered list of incomplete row_keys
row_key_retry_count = {}       # row_key → retry attempts
row_key_to_batch_mapping = {}  # row_key → batch_number (for metrics)

# Abandoned row tracking
abandoned_rows_details = []    # Failed rows with identifiers
```

### Processing Flow

**Step 1: Initialize Pending Queue with Deduplication (lambda_function.py:3176-3200)**
```python
duplicate_count = 0

for row in rows:
    # Extract pre-computed row_key from interface lambda
    if '_row_key' in row_data:
        row_key = row_data['_row_key']  # Hybrid hash from interface
    else:
        # Fallback: generate ID-field hash
        row_key = generate_row_key(row_data, validator.primary_key)

    # DEDUPLICATION: Detect duplicate row_keys (true duplicates)
    if row_key in row_key_to_row_data:
        duplicate_count += 1
        # Skip - this exact row_key already exists
        continue

    # Store mapping for unique row_keys only
    row_key_to_row_data[row_key] = row

    # Add to pending if not already validated
    if row_key not in validation_results:
        pending_row_keys.append(row_key)
        row_key_retry_count[row_key] = 0
```

**Deduplication Example:**
```
Input: 278 rows with pre-computed _row_key
  Row 1: _row_key = a7f8d9e2...
  Row 2: _row_key = a7f8d9e2... (duplicate! same as Row 1)
  Row 3: _row_key = b3e1c7a4...
  ...

After deduplication:
  row_key_to_row_data = {
    a7f8d9e2...: <Row 1 data>,  # Row 2 skipped (duplicate)
    b3e1c7a4...: <Row 3 data>,
    ...
  }

Validator processes: 239 unique row_keys (not 278 rows)
```

**Step 2: Process Batches from Pending Queue (lambda_function.py:3165-3168)**
```python
while pending_row_keys:
    # Select from front of list (failed rows moved to end)
    batch_row_keys = pending_row_keys[:current_batch_size]
    batch = [row_key_to_row_data[rk] for rk in batch_row_keys]
```

**Step 3: Store Results (lambda_function.py:3234-3242)**
```python
for row_key, result, _, batch_num in batch_results:
    validation_results[row_key] = result  # Dict keyed by row_key (not index)
    row_key_to_batch_mapping[row_key] = batch_index
    pending_row_keys.remove(row_key)  # Remove from pending
```

**Step 4: Handle Failures (lambda_function.py:3417-3442)**
```python
for failed_row_key in failed_row_keys:
    row_key_retry_count[failed_row_key] += 1

    if row_key_retry_count[failed_row_key] >= MAX_ROW_RETRIES:
        # Abandon row
        pending_row_keys.remove(failed_row_key)
        abandoned_rows_details.append({...})
    else:
        # Move to end for retry later
        pending_row_keys.remove(failed_row_key)
        pending_row_keys.append(failed_row_key)  # Retry at end
```

**Step 5: Continuation Support (lambda_function.py:3328-3330)**
```python
continuation_event['pending_row_keys'] = list(pending_row_keys)
continuation_event['row_key_retry_count'] = row_key_retry_count.copy()
# Next Lambda loads these and continues processing
```

---

## 4. QC Tracking

### QC Results Storage

**Validator Lambda (lambda_function.py:3724-3726):**
```python
# Store QC results using hash key (for Excel compatibility)
all_qc_results[row_key] = qc_results_by_field
logger.debug(f"Stored QC results for row with hash_key {row_key}: {len(qc_results_by_field)} fields")
```

**Structure:**
```python
all_qc_results = {
    "a7f8d9e2...": {  # row_key hash
        "supplier_name": {
            "original_value": "Acme Corp",
            "validated_value": "ACME Corporation",
            "confidence_level": "HIGH",
            "qc_status": "MODIFIED",
            ...
        }
    }
}
```

### QC Matching in Response

**Response Structure (lambda_function.py:4700-4750):**
```python
response = {
    "body": {
        "data": {
            "rows": validation_results,  # {row_key: {...validation...}}
            "qc_results": all_qc_results,  # {row_key: {...qc_data...}}
            "qc_metrics": qc_metrics_summary
        }
    }
}
```

**Key Insight:** Both `validation_results` and `qc_results` use **same row_key** → perfect alignment

---

## 5. Interface Assembly

### Receiving Validation Results

**Interface Lambda (background_handler.py:897-918):**
```python
# Load results from S3 (async) or Lambda response (sync)
async_validation_results = json.loads(s3_content)

# Structure:
{
    'validation_results': {row_key: {...}},  # Hash-keyed validation
    'qc_results': {row_key: {...}},          # Hash-keyed QC data
    'qc_metrics': {...}
}
```

### Wrapping for Common Processing

**Interface Lambda (background_handler.py:897-909):**
```python
validation_results = {
    'body': {
        'data': {
            'rows': async_validation_results['validation_results'],
            'qc_results': async_validation_results.get('qc_results', {}),
            'qc_metrics': async_validation_results.get('qc_metrics', {})
        }
    },
    # Preserve original structure for other uses
    'validation_results': async_validation_results['validation_results'],
    'qc_results': async_validation_results.get('qc_results', {}),
    'qc_metrics': async_validation_results.get('qc_metrics', {})
}
```

---

## 6. Final Excel Creation

### Extracting Row Keys from Rows

**Excel Report (excel_report_qc_unified.py:350-380):**
```python
# CRITICAL: Extract row keys from rows_data (pre-computed by interface lambda)
# Do NOT regenerate - this would break the matching!
row_keys = []

if rows_data and isinstance(rows_data[0], dict) and '_row_key' in rows_data[0]:
    # Extract pre-computed row keys from each row
    for row_idx, row_data in enumerate(rows_data):
        row_key = row_data.get('_row_key')
        row_keys.append(row_key)
    logger.info(f"Extracted {len(row_keys)} pre-computed row keys from rows_data")
else:
    # Fallback: extract from validation_results keys (positional matching)
    logger.warning("No _row_key in rows_data, using fallback")
```

### Matching All Rows to Results

**Excel Report (excel_report_qc_unified.py:520-530):**
```python
# Iterate ALL Excel rows in ORIGINAL ORDER (all 278 rows)
for row_idx, (row_data, row_key) in enumerate(zip(rows_data, row_keys)):
    # Lookup validation results by row_key
    row_validation_data = None
    if row_key in validation_results:
        row_validation_data = validation_results[row_key]

    # Write row to Excel (all rows, not just validated ones)
    # Rows with matching row_keys share the same validation result
```

### Key Points

1. **All 278 rows appear in Excel** (original order preserved)
2. **Row keys extracted from rows_data** (not regenerated!)
3. **Validation results keyed by row_key** (239 unique hashes)
4. **Multiple rows can share same row_key** (true duplicates)
5. **Rows without results shown as unvalidated** (partial validation)

### Example Flow with Duplicates

```
Excel Input (278 rows):
  Row 1: ID=ABC, Name=Acme, City=NYC    → _row_key: a7f8d9e2... (full-row hash)
  Row 2: ID=ABC, Name=Acme, City=NYC    → _row_key: a7f8d9e2... (SAME! duplicate)
  Row 3: ID=ABC, Name=Acme, City=LA     → _row_key: b3e1c7a4... (full-row hash)
  Row 4: ID=DEF, Name=Beta, City=SF     → _row_key: c9d2f8b1... (ID-field hash)
  ... (274 more rows)

Validator Processes (after deduplication):
  239 unique row_keys (not 278 rows!)

Validation Results:
  {
    "a7f8d9e2...": {validated data},  # Processed once (covers Row 1 AND Row 2)
    "b3e1c7a4...": {validated data},
    "c9d2f8b1...": {validated data},
    ...
  }

Excel Output (all 278 rows displayed):
  Row 1: _row_key=a7f8d9e2... → validation_results[a7f8d9e2...] ✓
  Row 2: _row_key=a7f8d9e2... → validation_results[a7f8d9e2...] ✓ (SAME result!)
  Row 3: _row_key=b3e1c7a4... → validation_results[b3e1c7a4...] ✓
  Row 4: _row_key=c9d2f8b1... → validation_results[c9d2f8b1...] ✓
  ... (all 278 rows shown)
```

---

## 7. Benefits of Hybrid Hash-Based System

### Reliability
- ✅ Failed rows can be retried without affecting other rows
- ✅ Rows can be processed in any order
- ✅ Continuation chains work seamlessly
- ✅ Automatic deduplication (true duplicates processed once)

### Consistency
- ✅ Validation results match QC data (same row_key)
- ✅ History matching works for unique ID rows (ID-field hash)
- ✅ Excel output matches validation (hash lookup)
- ✅ All 278 rows appear in Excel (duplicates share results)

### Flexibility
- ✅ Can reorder rows for retry optimization
- ✅ Can process rows in parallel (future enhancement)
- ✅ Can merge results from multiple Lambdas
- ✅ Handles both unique rows and duplicates intelligently

### Debugging
- ✅ Can identify specific failed rows by primary key values
- ✅ Can track retry attempts per row
- ✅ Can see which batch processed which row
- ✅ Clear logging of duplicate ID detection

---

## 8. Edge Cases Handled

### Duplicate IDs (Same ID, Different Data)
**Problem:** Multiple rows with same ID but different data
**Solution:**
- All rows with duplicate IDs use **full-row hashing**
- Different data → different hashes → processed separately
- History matching disabled for these rows (can't tell which is which)

### True Duplicates (Exact Same Row)
**Problem:** Two identical rows (same ID AND same data)
**Solution:**
- Both get same full-row hash
- Validator deduplicates → processed once
- Both rows in Excel show same validation result

### Unique ID Rows
**Problem:** Need history matching for rows with unique IDs
**Solution:**
- Use **ID-field hashing** (validated values don't affect hash)
- History matching works perfectly across validation runs

### Missing Primary Keys
**Problem:** No ID fields configured
**Solution:**
- All rows use full-row hashing (primary_keys=None)
- History matching disabled

### Continuation with Partial Results
**Problem:** Lambda times out mid-processing
**Solution:** Saves pending_row_keys to S3, next Lambda continues

### Failed Rows After MAX_RETRIES
**Problem:** Row fails 3 times
**Solution:**
- Marked in `abandoned_rows_details`
- Validation status = 'FAILED'
- Error message lists row identifiers
- Customer NOT charged (billing protection)

### Order Changes During Processing
**Problem:** Failed rows moved to end of queue
**Solution:** Excel output still uses original order (hash lookup is order-independent)

---

## 9. Code Locations

| Component | File | Lines |
|-----------|------|-------|
| Row key generation | `row_key_utils.py` | `generate_row_key()` |
| **Hybrid hash generation** | `background_handler.py` | **2828-2869** |
| Table data update with _row_key | `background_handler.py` | 2871-2874 |
| History loading | `utils/history_loader.py` | `load_validation_history_from_excel()` |
| Validator initialization + dedup | `lambda_function.py` | 3176-3203 |
| Batch processing | `lambda_function.py` | 3205-3290 |
| Retry logic | `lambda_function.py` | 3450-3475 |
| QC storage | `lambda_function.py` | 3724-3726 |
| **Excel row key extraction** | `excel_report_qc_unified.py` | **350-380** |
| **Excel row iteration (all 278)** | `excel_report_qc_unified.py` | **520, 730, 910** |

---

## 10. Migration Notes

**Old System (Integer Indices):**
```python
validation_results = {
    0: {...},  # First row
    1: {...},  # Second row
    2: {...}   # Third row
}
```

**New System (Hash Keys):**
```python
validation_results = {
    "a7f8d9e2...": {...},  # Row with supplier_id=ABC
    "b3e1c7a4...": {...},  # Row with supplier_id=DEF
    "c9d2f8b1...": {...}   # Row with supplier_id=GHI
}
```

**Backward Compatibility:**
Excel report tries hash lookup first, falls back to integer index if not found.

---

## Summary

The **hybrid hash-based row tracking system** provides:

1. **Intelligent row identification**
   - ID-field hashing for unique rows (enables history matching)
   - Full-row hashing for duplicate IDs (distinguishes different data)
   - Automatic detection and handling of both cases

2. **Complete Excel output**
   - All 278 input rows appear in Excel (original order preserved)
   - Validator processes only 239 unique hashes (automatic deduplication)
   - True duplicates share validation results

3. **History matching for most rows**
   - Rows with unique IDs: History works perfectly (ID-field hash is stable)
   - Rows with duplicate IDs: History disabled (can't disambiguate which is which)

4. **Order-independent processing**
   - Validation results keyed by row_key (not position)
   - QC data matches validation via same row_key
   - Excel lookup via pre-computed row_key (not regenerated)

5. **Robust retry and continuation**
   - Failed rows reordered without affecting Excel output
   - Continuation chains preserve pending_row_keys
   - Clear error reporting with primary key identifiers

This architecture enables reliable, scalable validation processing with intelligent duplicate handling, history matching, and automatic deduplication.
