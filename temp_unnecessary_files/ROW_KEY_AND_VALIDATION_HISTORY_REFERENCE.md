# Row Key and Validation History Reference Guide

## Overview

This document serves as the definitive reference for understanding how row keys and validation history work in the Perplexity Validator system. The system uses row keys to uniquely identify records and maintain validation history across multiple runs.

## 1. Row Key Generation

### 1.1 Primary Key Inference

Row keys are generated from **primary key columns** which are **automatically inferred** from the schema configuration:

- Fields with `importance: "ID"` are considered primary keys
- The system uses `SimplifiedSchemaValidator` to determine primary keys
- **NO manual specification of primary keys is required**

Example configuration:
```json
{
  "validation_targets": [
    {
      "column": "Product Name",
      "importance": "ID",  // This makes it a primary key
      "format": "String"
    },
    {
      "column": "Developer", 
      "importance": "ID",  // This makes it a primary key
      "format": "String"
    },
    {
      "column": "Target",
      "importance": "ID",  // This makes it a primary key  
      "format": "String"
    },
    {
      "column": "Indication",
      "importance": "CRITICAL",  // NOT a primary key
      "format": "String"
    }
  ]
}
```

### 1.2 Row Key Format

Row keys are generated using the `generate_row_key()` function from `row_key_utils.py`:

```python
# Format: value1||value2||value3
# Example: "225Ac-PSMA-617||Novartis||PSMA"
```

Key characteristics:
- Values are joined with double pipe separator (`||`)
- Unicode characters are sanitized to ASCII equivalents
- Empty values become "EMPTY"
- Only acceptable ASCII characters are retained

### 1.3 Character Sanitization

The system sanitizes all row key components to prevent Unicode-related mismatches:

- `‑` (non-breaking hyphen U+2011) → `-` (regular hyphen)
- `α` (Greek alpha) → `a` (removed in sanitization)
- Non-breaking spaces → regular spaces
- All other non-ASCII characters are removed

## 2. Validation History Storage

### 2.1 Details Sheet Structure

Validation history is stored in the "Details" worksheet with these columns:

1. **Row Key** - The unique identifier for the row
2. **Identifier** - Human-readable identifier from primary keys
3. **Column** - The field name being validated
4. **Original Value** - Value from the source data
5. **Validated Value** - The validated/corrected value
6. **Confidence** - Confidence level (HIGH/MEDIUM/LOW)
7. **Quote** - Supporting quote from sources
8. **Sources** - List of source URLs
9. **Explanation** - Explanation of the validation
10. **Update Required** - Whether update is needed
11. **Substantially Different** - If value differs significantly
12. **Consistent with Model** - Model consistency check
13. **Timestamp** - When validation occurred
14. **New** - Status: "New" or "Historical"

### 2.2 Dynamic ID Columns

To enable consistent row key regeneration, the Details sheet includes dynamic ID columns:

- Format: `ID:FieldName` (e.g., `ID:Product Name`, `ID:Developer`)
- These columns store the actual ID field values
- Allows reconstruction of row keys even if the main data changes

### 2.3 New vs Historical Entries

The "New" column tracks validation status:
- **"New"** - Current validation results
- **"Historical"** - Previous validation results

When processing:
1. New validations are written first, marked as "New"
2. Existing "New" entries are changed to "Historical"
3. Historical entries are preserved below new ones

## 3. Validation History Loading

### 3.1 Loading Process

The `load_validation_history_from_excel()` function:

1. First tries to load from "History" sheet (legacy)
2. Falls back to "Details" sheet
3. Returns empty dictionary if no history exists

### 3.2 Data Structure

Validation history is structured as:
```python
{
    "row_key1": {
        "Field1": [
            {
                "timestamp": "2024-01-15T14:30:22",
                "value": "Phase 1",
                "confidence_level": "HIGH",
                "quote": "The study is in Phase 1...",
                "sources": ["https://example.com"]
            }
        ],
        "Field2": [...]
    },
    "row_key2": {...}
}
```

## 4. Validation History Flow

### 4.1 Excel Upload → Interface Lambda

1. User uploads Excel file with existing Details sheet
2. Interface Lambda loads validation history using `load_validation_history_from_excel()`
3. Primary keys are inferred using `SimplifiedSchemaValidator`
4. Row keys are generated for current data
5. Validation history is included in payload to Core Lambda

### 4.2 Interface Lambda → Core Lambda

Payload structure:
```json
{
    "config": {...},
    "validation_data": {
        "rows": [
            {
                "_row_key": "225Ac-PSMA-617||Novartis||PSMA",
                "Product Name": "225Ac-PSMA-617",
                "Developer": "Novartis",
                ...
            }
        ]
    },
    "validation_history": {
        "225Ac-PSMA-617||Novartis||PSMA": {
            "Development Stage": [...],
            "Indication": [...]
        }
    }
}
```

### 4.3 Core Lambda → Prompt Generation

1. Core Lambda receives validation history in event
2. `SimplifiedSchemaValidator.generate_multiplex_prompt()` includes history
3. History appears in prompts as:
   ```
   Previous validation entries:
   - [2024-01-15] Phase 1 (HIGH confidence)
     Quote: "The study is in Phase 1..."
     Sources: https://example.com
   ```

### 4.4 Results → Excel Output

1. New validation results are written to Details sheet as "New"
2. Previous "New" entries become "Historical"
3. All historical entries are preserved
4. ID columns are populated for future row key regeneration

## 5. Common Issues and Solutions

### Issue 1: Row Key Mismatches
**Problem**: Historical row keys don't match current row keys
**Cause**: Unicode characters or different primary key configurations
**Solution**: Sanitization in `row_key_utils.py` ensures consistency

### Issue 2: Missing Primary Keys
**Problem**: "No primary keys provided for row key generation"
**Cause**: Schema validator not properly inferring ID fields
**Solution**: Ensure fields have `importance: "ID"` in config

### Issue 3: History Not in Prompts
**Problem**: Validation history loaded but not appearing in prompts
**Possible Causes**:
1. Row keys don't match between current data and history
2. Cache hit (identical prompts skip history inclusion)
3. Primary keys not properly inferred

**Debug Steps**:
1. Check CloudWatch logs for "Validation history received" messages
2. Verify row key generation matches between runs
3. Ensure validation history is in the Lambda payload

### Issue 4: Details Sheet Corruption
**Problem**: Details sheet structure doesn't match expected format
**Solution**: The system handles various formats:
- Missing columns are ignored
- Extra columns are preserved
- ID columns are dynamically added as needed

## 6. Best Practices

1. **Always use ID importance** for fields that uniquely identify records
2. **Don't manually specify primary keys** - let the system infer them
3. **Preserve the Details sheet** when sharing files - it contains the history
4. **Monitor CloudWatch logs** for validation history debug messages
5. **Use consistent column names** across runs to maintain history

## 7. Testing Validation History

To test if validation history is working:

1. Run validation on a file
2. Check Details sheet has entries marked "New"
3. Run validation again on the same file
4. Verify:
   - Previous "New" entries are now "Historical"
   - New entries are added above historical ones
   - CloudWatch logs show "Validation history included in prompt"
   - Prompts contain "Previous validation entries" sections

## 8. Architecture Summary

```
Excel File with Details Sheet
    ↓
Interface Lambda
    - Loads validation history from Details
    - Infers primary keys from ID fields
    - Generates row keys
    - Passes history in payload
    ↓
Core Lambda  
    - Receives validation history
    - Groups fields for validation
    - Generates prompts with history
    ↓
Perplexity API
    - Receives prompts with historical context
    - Returns new validation results
    ↓
Results with Updated Details Sheet
    - New results marked as "New"
    - Previous results marked as "Historical"
    - ID columns for row key regeneration
```

## Key Files

- `row_key_utils.py` - Centralized row key generation
- `lambda_test_json_clean.py` - Contains `load_validation_history_from_excel()`
- `schema_validator_simplified.py` - Infers primary keys, generates prompts with history
- `interface_lambda_function.py` - Loads and passes validation history

## Remember

**The system is designed to work automatically** - if validation history isn't appearing in prompts, it's usually due to row key mismatches or missing ID field designations in the configuration. The debug logging added to both Lambdas will help trace where the history is getting lost. 