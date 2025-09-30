# Row Keys System Documentation

## Overview

The Perplexity Validator uses a **hash-based row key system** to uniquely identify and track rows across all components of the validation pipeline. This document explains how row keys work, where they're generated, and how they ensure consistency between validation results, QC data, history tracking, and Excel output.

## What are Row Keys?

Row keys are **SHA-256 hash strings** that uniquely identify each row in a dataset based on the row's primary key columns. They look like:
```
f406842c0aa1e13ede3082f4a3feda87adec2f1a32a77a8ee0ef842c3c464697
```

### Why Hash-Based Keys?
- **Consistent**: Same data always produces the same hash
- **Encoding-agnostic**: Avoids Unicode normalization issues
- **Collision-resistant**: SHA-256 ensures unique identification
- **Cross-component compatibility**: Works across validation, QC, history, and Excel systems

## Row Key Generation

### Core Function: `generate_row_key()`
**Location**: `src/shared/row_key_utils.py`

```python
def generate_row_key(row: Dict[str, Any], primary_keys: List[str]) -> str:
    """Generate a unique row key based on primary key columns using hashing."""
```

**Process**:
1. Extract values from primary key columns (ID fields)
2. Normalize values (NULL, EMPTY, strip whitespace)
3. Create JSON structure with keys and values
4. Generate SHA-256 hash of JSON string
5. Return 64-character hex string

**Example**:
```python
row_data = {"Company": "Apple Inc", "Year": "2023", "Revenue": "394.3B"}
primary_keys = ["Company", "Year"]  # ID fields from config
row_key = generate_row_key(row_data, primary_keys)
# Result: "a1b2c3d4e5f6789..." (64-char hash)
```

## Primary Keys (ID Fields)

Primary keys are columns marked with `importance: "ID"` in the configuration:

```json
{
  "validation_targets": [
    {"name": "Company", "importance": "ID"},
    {"name": "Year", "importance": "ID"},
    {"name": "Revenue", "importance": "VALIDATED"}
  ]
}
```

The system automatically extracts ID fields to use as primary keys for hash generation.

## Row Key Flow Through the System

### 1. Initial Generation (Interface Lambda)
**Location**: `src/lambdas/interface/handlers/background_handler.py:2678-2687`

```python
from row_key_utils import generate_row_key
for row_data in excel_rows:
    row_key = generate_row_key(row_data, id_fields)
    row_data['_row_key'] = row_key  # Add to payload
```

**Purpose**: Generate hash keys for all rows and embed them in the validation payload.

### 2. Validation Processing (Validation Lambda)
**Location**: `src/lambdas/validation/lambda_function.py:3132-3141`

```python
if '_row_key' in row:
    row_key = row['_row_key']  # Use pre-computed hash
else:
    row_key = generate_row_key(row_data, validator.primary_key)  # Fallback
```

**Purpose**: Use pre-computed hash keys for consistent row identification during validation.

### 3. QC Results Storage (Validation Lambda)
**Location**: `src/lambdas/validation/lambda_function.py:3335`

```python
all_qc_results[row_key] = qc_results_by_field  # Store QC with hash key
```

**Purpose**: Store QC results using the same hash keys as validation results.

### 4. Key Format Conversion (Validation Lambda)
**Location**: `src/lambdas/validation/lambda_function.py:4481-4503`

```python
# Convert validation_results from numeric indices to hash-based keys
hash_based_validation_results = {}
for row_idx in range(len(rows)):
    if row_idx in validation_results:
        row_key = row['_row_key']  # Get pre-computed hash
        hash_based_validation_results[row_key] = validation_results[row_idx]
```

**Purpose**: Convert numeric-indexed validation results to hash-keyed format for consistency with QC.

### 5. Excel Generation (Excel Function)
**Location**: `src/shared/excel_report_qc_unified.py:360-375`

```python
# Extract row keys from validation results instead of regenerating
available_keys = list(validation_results.keys())  # Hash keys
for row_idx, row_data in enumerate(rows_data):
    row_key = available_keys[row_idx]  # Use validation hash key
```

**Purpose**: Use the same hash keys from validation results for Excel row identification.

### 6. QC Data Lookup (Excel Function)
**Location**: `src/shared/excel_report_qc_unified.py:221-233`

```python
def get_qc_data_for_row(excel_row_key, row_position):
    if excel_row_key in qc_results:  # Direct hash key lookup
        return qc_results[excel_row_key]
```

**Purpose**: Look up QC data using matching hash keys between Excel and QC results.

## History System Integration

### History Loading
**Location**: `src/lambdas/interface/utils/history_loader.py:119-124`

```python
# Use the row key as-is (no conversion needed for hash-based keys)
sanitized_row_key = row_key
validation_history[sanitized_row_key] = {}
```

**Purpose**: Load validation history from Excel Details sheet using hash-based row keys.

### History Matching
**Location**: `src/lambdas/interface/handlers/background_handler.py:2712-2713`

```python
for row in processed_rows:
    payload_key = row.get('_row_key', '')  # Hash key
    if payload_key and payload_key in validation_history:  # Match with history
```

**Purpose**: Match current rows with historical data using consistent hash keys.

### History Usage
**Location**: `src/lambdas/validation/lambda_function.py:3145-3146`

```python
if row_key in event['validation_history']:
    validation_history = event['validation_history'][row_key]  # Hash lookup
```

**Purpose**: Use hash keys to retrieve relevant history for each row during validation.

## Key Consistency Requirements

### 1. Same Primary Keys
All components must use the **same ID fields** from the configuration:
- Interface lambda extracts ID fields from config
- Validation lambda uses `validator.primary_key` (same ID fields)
- History loader reads keys from Details sheet (generated with same ID fields)

### 2. Same Generation Method
All components use the **same `generate_row_key()` function**:
- Same normalization logic
- Same JSON structure
- Same hashing algorithm

### 3. Pre-computed Keys
The system prefers **pre-computed keys** over regeneration:
- Interface lambda generates keys once
- Validation lambda uses `_row_key` from payload
- Excel function extracts keys from validation results
- Avoids regeneration inconsistencies

## Data Structures

### Validation Results
```python
{
  "f406842c0aa1e13ede3082f4a3feda87...": {  # Hash-based row key
    "Company": {"value": "Apple Inc", "confidence": "HIGH"},
    "Revenue": {"value": "394.3B", "confidence": "MEDIUM"}
  }
}
```

### QC Results
```python
{
  "f406842c0aa1e13ede3082f4a3feda87...": {  # Same hash key
    "Revenue": {
      "qc_applied": true,
      "qc_entry": "394.33B",
      "qc_confidence": "HIGH"
    }
  }
}
```

### Validation History
```python
{
  "f406842c0aa1e13ede3082f4a3feda87...": {  # Same hash key
    "Revenue": [
      {
        "timestamp": "2023-01-01T00:00:00Z",
        "value": "394.3B",
        "confidence_level": "MEDIUM"
      }
    ]
  }
}
```

## Excel Details Sheet Format

The Details sheet stores row keys for history loading:

| Row Key | Column | Validated Value | Confidence | ... |
|---------|--------|----------------|------------|-----|
| f406842c... | Revenue | 394.3B | MEDIUM | ... |
| a1b2c3d4... | Revenue | 287.5B | HIGH | ... |

## Benefits of Hash-Based System

### 1. Consistency
- Same row always gets same key across all components
- No dependency on row order or position
- Reliable cross-component data matching

### 2. Reliability
- Collision-resistant SHA-256 hashing
- Works with any Unicode data
- Stable across different environments

### 3. Traceability
- History tracking works reliably
- QC data matches validation results precisely
- Excel output correctly maps all data types

### 4. Scalability
- No performance impact from key generation
- Works with datasets of any size
- Efficient hash-based lookups

## Debugging Row Key Issues

### Common Issues
1. **Key Mismatch**: Different components using different primary keys
2. **Missing Keys**: Validation results using numeric indices instead of hashes
3. **Generation Inconsistency**: Different normalization or hashing logic

### Debugging Logs
```python
# Key generation
logger.info(f"[ROW_KEY_EXTRACT] Found {len(available_keys)} pre-computed row keys")
logger.info(f"[ROW_KEY_EXTRACT] Sample keys: {[k[:8] + '...' for k in available_keys[:3]]}")

# Key matching
logger.info(f"[KEY_MATCH_DEBUG] QC keys sample: {[k[:8] + '...' for k in qc_keys[:3]]}")
logger.info(f"[KEY_MATCH_DEBUG] Excel keys sample: {[k[:8] + '...' for k in excel_keys[:3]]}")
logger.info(f"[KEY_MATCH_DEBUG] Found {len(matching_keys)} exact key matches")

# Key conversion
logger.info(f"[KEY_CONVERSION] Converted {len(validation_results)} validation results from numeric to hash-based keys")
```

### Verification Steps
1. Check that all components use same ID fields from config
2. Verify `_row_key` is present in validation payload
3. Confirm QC and validation results use same key format
4. Ensure Excel function extracts rather than regenerates keys

## Migration from Legacy System

### Old System (Deprecated)
- Used concatenated strings: `"Apple Inc||2023"`
- Subject to encoding and normalization issues
- Inconsistent across different platforms

### New System (Current)
- Uses SHA-256 hashes: `"f406842c0aa1e13ede3082f4a3feda87..."`
- Encoding-agnostic and collision-resistant
- Consistent across all components

### Backward Compatibility
The system handles legacy Excel files through the history loader, which can read both formats but always converts to hash-based keys internally.

## Best Practices

### 1. Always Use Pre-computed Keys
```python
# Good: Use existing key
if '_row_key' in row:
    row_key = row['_row_key']

# Avoid: Regenerating keys unnecessarily
row_key = generate_row_key(row_data, primary_keys)
```

### 2. Validate Key Consistency
```python
# Check for key matches between systems
matching_keys = set(validation_keys) & set(qc_keys)
if len(matching_keys) != len(validation_keys):
    logger.error("Key mismatch detected!")
```

### 3. Use Consistent Primary Keys
Ensure all components use the same ID fields from the configuration rather than hardcoded or assumed primary keys.

### 4. Log Key Operations
Include key debugging logs to help diagnose data flow issues:
```python
logger.info(f"Generated row key {row_key[:8]}... for row {row_idx}")
logger.debug(f"Using primary keys: {primary_keys}")
```

---

*This documentation reflects the current implementation as of the hash-based row key system migration. All components now use consistent SHA-256-based row identification for reliable data tracking and cross-component integration.*