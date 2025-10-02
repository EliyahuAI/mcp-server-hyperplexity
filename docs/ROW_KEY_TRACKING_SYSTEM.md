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

A row key is a **SHA-256 hash** generated from a row's primary key field values.

```python
# From row_key_utils.py
def generate_row_key(row_data: dict, primary_key_fields: list) -> str:
    """
    Generate deterministic hash from primary key field values.

    Example:
        row_data = {"supplier_id": "ABC123", "name": "Acme Corp", "city": "NYC"}
        primary_key_fields = ["supplier_id", "name"]

        Returns: "a7f8d9e2..." (SHA-256 hash of "ABC123||Acme Corp")
    """
```

### When Are Row Keys Generated?

**Interface Lambda (background_handler.py:2750-2757):**
```python
for row_data in excel_rows:
    row_key = generate_row_key(row_data, id_fields)
    row_data['_row_key'] = row_key  # Added to each row
    processed_rows.append(row_data)
```

**Timing:** Before sending to validator (both sync and async)

**Result:** All rows arrive at validator with pre-computed `_row_key`

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

**Key Insight:** History lookup uses same hash as current validation → perfect matching

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

**Step 1: Initialize Pending Queue (lambda_function.py:3129-3153)**
```python
for row in rows:
    # Extract or generate row_key
    if '_row_key' in row_data:
        row_key = row_data['_row_key']  # Use pre-computed from interface
    else:
        row_key = generate_row_key(row_data, validator.primary_key)

    # Store mapping
    row_key_to_row_data[row_key] = row

    # Add to pending if not already validated
    if row_key not in validation_results:
        pending_row_keys.append(row_key)
        row_key_retry_count[row_key] = 0
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

### Matching Rows to Results

**Excel Report (excel_report_new.py:294-302):**
```python
# Iterate Excel rows in ORIGINAL ORDER
for row_idx, (row_data, row_key) in enumerate(zip(rows_data, row_keys)):
    # Generate same hash from row data
    row_key = generate_row_key(row_data, id_fields)

    # Lookup validation results by hash (order-independent)
    if row_key in validation_results:
        row_validation_data = validation_results[row_key]
    elif str(row_idx) in validation_results:  # Fallback for old format
        row_validation_data = validation_results[str(row_idx)]
```

### Key Points

1. **Excel rows iterate in original order** (from uploaded file)
2. **Validation results stored in hash-keyed dict** (processing order)
3. **Matching happens via hash lookup** → order doesn't matter
4. **Failed rows reordered during processing** → still appear in original position in Excel

### Example Flow

```
Excel Upload:
  Row 1: supplier_id=ABC, name=Acme    → hash: a7f8d9e2...
  Row 2: supplier_id=DEF, name=Beta    → hash: b3e1c7a4...
  Row 3: supplier_id=GHI, name=Gamma   → hash: c9d2f8b1...

Validation Processing Order (with retry):
  Batch 1: [a7f8d9e2, b3e1c7a4, c9d2f8b1] → b3e1c7a4 fails
  Batch 2: [a7f8d9e2, c9d2f8b1, b3e1c7a4] → all succeed

Validation Results:
  {
    "a7f8d9e2...": {...validation_data...},
    "b3e1c7a4...": {...validation_data...},
    "c9d2f8b1...": {...validation_data...}
  }

Excel Output (original order preserved):
  Row 1: ABC, Acme    → looks up a7f8d9e2... → validation data
  Row 2: DEF, Beta    → looks up b3e1c7a4... → validation data
  Row 3: GHI, Gamma   → looks up c9d2f8b1... → validation data
```

---

## 7. Benefits of Hash-Based System

### Reliability
- ✅ Failed rows can be retried without affecting other rows
- ✅ Rows can be processed in any order
- ✅ Continuation chains work seamlessly

### Consistency
- ✅ Validation results match QC data (same row_key)
- ✅ History matches current validation (same row_key)
- ✅ Excel output matches validation (hash lookup)

### Flexibility
- ✅ Can reorder rows for retry optimization
- ✅ Can process rows in parallel (future enhancement)
- ✅ Can merge results from multiple Lambdas

### Debugging
- ✅ Can identify specific failed rows by primary key values
- ✅ Can track retry attempts per row
- ✅ Can see which batch processed which row

---

## 8. Edge Cases Handled

### Duplicate Rows
**Problem:** Two rows with identical primary keys
**Solution:** Same hash → only processed once, result shared

### Missing Primary Keys
**Problem:** Row has no primary key fields
**Solution:** Hash first 3 fields as fallback

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
| Interface adds _row_key | `background_handler.py` | 2750-2757 |
| History loading | `utils/history_loader.py` | `load_validation_history_from_excel()` |
| Validator initialization | `lambda_function.py` | 3129-3153 |
| Batch processing | `lambda_function.py` | 3165-3242 |
| Retry logic | `lambda_function.py` | 3417-3442 |
| QC storage | `lambda_function.py` | 3724-3726 |
| Excel matching | `excel_report_new.py` | 294-302 |

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

The hash-based row tracking system provides:
1. **Deterministic row identification** via primary key hashing
2. **Order-independent result matching** across validation, QC, history, and Excel
3. **Robust retry logic** with failed row reordering
4. **Continuation chain support** with pending state persistence
5. **Clear error reporting** with primary key identifiers

This architecture enables reliable, scalable validation processing with automatic retry and continuation support.
