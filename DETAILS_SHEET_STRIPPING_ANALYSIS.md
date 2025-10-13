# Details Sheet Stripping Implementation - Technical Analysis

## Objective

Strip the "Details" sheet from customer-facing Excel downloads while preserving it in S3 storage for internal auditing.

### Requirements
1. **Generate once**: Create full Excel with Details sheet
2. **Store full version**: Save to S3 with Details sheet intact (for internal use)
3. **Strip for customers**: Remove Details sheet before providing download links
4. **Preserve everything else**: All colors, comments, formulas, and data must remain

### Architecture
```
Generate Full Excel (with Details)
    ↓
Store in S3 (full version)
    ↓
Strip Details Sheet
    ↓
Provide to Customer (no Details)
```

---

## Current Implementation Path

### File: `src/lambdas/interface/reporting/interface_qc_excel_integration.py`

**Purpose**: Main integration point that creates both versions

**Key Function**: `create_qc_enhanced_excel_for_interface()` (lines 14-67)

**Expected Flow**:
```python
1. Call excel_report_qc_unified.create_enhanced_excel_with_validation()
   → Creates full Excel with Details sheet

2. Get bytes: full_excel_content = full_excel_buffer.getvalue()

3. Call strip_details_sheet_for_customer(full_excel_content)
   → Returns Excel without Details sheet

4. Return BytesIO with attributes:
   - buffer content: customer version (no Details)
   - .full_version: full version (with Details)
   - .customer_version: customer version (no Details)
```

### File: `src/lambdas/interface/handlers/background_handler.py`

**Purpose**: Orchestrates the validation workflow and uses dual versions

**Key Import** (line 1204):
```python
from ..reporting.interface_qc_excel_integration import create_qc_enhanced_excel_for_interface
```

**Usage Locations**:
- Line 2182: Preview validation
- Line 4224: Full validation

**Expected Usage**:
```python
excel_buffer = create_qc_enhanced_excel_for_interface(...)

# For S3 storage (with Details)
if hasattr(excel_buffer, 'full_version'):
    s3_content = excel_buffer.full_version

# For customer downloads (without Details)
if hasattr(excel_buffer, 'customer_version'):
    download_content = excel_buffer.customer_version
```

---

## Critical Issues Encountered

### Issue 1: Row Key Mismatch (CURRENT BLOCKER)

**Location**: `src/shared/excel_report_qc_unified.py`

**Error Log**:
```
[ROW_KEY_MATCH] HASH MISMATCH: 0 matching keys despite having 4 validation results!
[ROW_KEY_MATCH] Excel keys sample: ['69b53101270bad5741e19de4d850ab6fc94c9171beef38ff83623fa1b0b25cb2', ...]
[ROW_KEY_MATCH] Validation keys sample: ['message', 'success', 'metadata']
```

**Root Cause**:
The validation_results structure has changed. After extracting from `body`, we're now seeing:
- Validation keys: `['message', 'success', 'metadata']`
- These are STILL envelope/wrapper keys, not the actual row hash keys

**Expected Structure**:
```python
validation_results = {
    'row_hash_key_1': {
        'Company': {'value': '...', 'confidence': 'HIGH', ...},
        'Sector': {'value': '...', 'confidence': 'MEDIUM', ...}
    },
    'row_hash_key_2': {...}
}
```

**Actual Structure** (after body extraction):
```python
{
    'message': '...',
    'success': True,
    'metadata': {...},
    # Actual row data is nested somewhere else
}
```

**Fix Needed in** `interface_qc_excel_integration.py` lines 41-46:

Current code:
```python
if isinstance(validation_results, dict) and 'body' in validation_results:
    logger.info("[INTERFACE_QC] Extracting validation results from response body")
    actual_validation_results = validation_results.get('body', {})
```

**Need to find where actual row hash keys are**. Likely need:
```python
actual_validation_results = validation_results.get('body', {}).get('results', {})
# OR
actual_validation_results = validation_results.get('body', {}).get('validation_results', {})
```

### Issue 2: No Colors or Comments

**Symptom**: User reports Excel has no colors or comments

**Likely Cause**: Since row keys don't match (Issue 1), the code in `excel_report_qc_unified.py` cannot find validation data for any row:

**Location**: `src/shared/excel_report_qc_unified.py` (lines 302-368)

The logic is:
```python
for row_idx, (row_data, row_key) in enumerate(zip(rows_data, row_keys)):
    # Try to get validation results for this row
    row_validation_data = None
    if row_key in validation_results:  # ← NEVER MATCHES!
        row_validation_data = validation_results[row_key]

    # Apply colors based on confidence
    if row_validation_data:  # ← ALWAYS None, so no colors applied
        # Apply formatting...
```

Because row keys never match, `row_validation_data` is always None, so:
- No confidence-based colors applied
- No comments with reasoning added
- Details sheet is empty (0 entries)

---

## Previous Issues (RESOLVED)

### ✅ Issue: Wrong Import Path
**Location**: `background_handler.py` line 1204

**Was**: `from excel_report_qc_unified import create_qc_enhanced_excel_for_interface`
**Fixed to**: `from ..reporting.interface_qc_excel_integration import create_qc_enhanced_excel_for_interface`

### ✅ Issue: Missing config_s3_key Parameter
**Location**: `interface_qc_excel_integration.py` line 20

**Added**: `config_s3_key: Optional[str] = None`

### ✅ Issue: Wrong Function Name
**Location**: `interface_qc_excel_integration.py` line 39

**Was**: `from excel_report_qc_unified import create_qc_unified_excel_with_history`
**Fixed to**: `from excel_report_qc_unified import create_enhanced_excel_with_validation`

### ✅ Issue: Incorrect Relative Imports
**Location**: Multiple files

**Fixed**:
- `from ..handlers.interface_qc_handler` (relative import for handlers)
- `from .excel_report_new` (relative import for sibling module)

### ✅ Issue: File Not in Deployment Package
**Location**: `deployment/create_interface_package.py` line 194

**Was**: Trying to copy deleted file `qc_enhanced_excel_dual_generator.py`
**Fixed**: Removed from package list

---

## Validation Results Structure Investigation Needed

### What We Know:
1. Parser generates Excel with row keys like: `'69b53101270bad5741e19de4d850ab6fc94c9171beef38ff83623fa1b0b25cb2'`
2. These are generated in `excel_report_qc_unified.py` around lines 83-100
3. Validation results come back with keys like: `['message', 'success', 'metadata']`

### What We Need to Find:

**Location to check**: `src/lambdas/interface/handlers/background_handler.py`

Around lines 2182 and 4224 where `create_qc_enhanced_excel_for_interface` is called:

```python
excel_buffer = create_qc_enhanced_excel_for_interface(
    table_data, validation_results, config_data, session_id,
    validated_sheet_name=validated_sheet,
    config_s3_key=config_s3_key
)
```

**Need to trace back**: What is the actual structure of `validation_results` at this point?

**Possible locations**:
- Validator Lambda response structure
- Response transformation in background_handler before calling Excel generation
- Async completion message structure

### Suggested Debug Steps:

Add to `interface_qc_excel_integration.py` line 42:
```python
logger.info(f"[DEBUG] validation_results keys: {list(validation_results.keys())}")
if 'body' in validation_results:
    body = validation_results.get('body', {})
    logger.info(f"[DEBUG] body type: {type(body)}, keys: {list(body.keys()) if isinstance(body, dict) else 'not dict'}")
    if isinstance(body, dict):
        for key in ['results', 'validation_results', 'data', 'validated_rows']:
            if key in body:
                logger.info(f"[DEBUG] Found nested key '{key}' in body")
                sample = body[key]
                if isinstance(sample, dict):
                    logger.info(f"[DEBUG] {key} sample keys: {list(sample.keys())[:3]}")
```

---

## Files Modified

1. `src/lambdas/interface/handlers/background_handler.py`
   - Line 1204: Fixed import path

2. `src/lambdas/interface/reporting/interface_qc_excel_integration.py`
   - Line 20: Added `config_s3_key` parameter
   - Line 39: Fixed function import name
   - Lines 41-46: Added body extraction (incomplete - needs deeper nesting)
   - Lines 77-89: Fixed fallback with body extraction

3. `src/shared/qc_enhanced_excel_report.py`
   - Lines 339-381: Added `strip_details_sheet_for_customer()` function

4. `deployment/create_interface_package.py`
   - Line 194: Removed deleted file from package list

---

## Solution Required

### Immediate Fix Needed:

**File**: `src/lambdas/interface/reporting/interface_qc_excel_integration.py`

**Line 41-46**: Need correct path to row hash data

Current attempt:
```python
if isinstance(validation_results, dict) and 'body' in validation_results:
    actual_validation_results = validation_results.get('body', {})
```

Likely should be (need to verify):
```python
if isinstance(validation_results, dict) and 'body' in validation_results:
    body = validation_results.get('body', {})
    # Try common nested locations
    actual_validation_results = (
        body.get('results', {}) or
        body.get('validation_results', {}) or
        body.get('data', {}) or
        body
    )
    logger.info(f"[DEBUG] Extracted validation keys: {list(actual_validation_results.keys())[:5]}")
```

### Verification After Fix:

1. Deploy updated package
2. Check logs for row key match success
3. Verify Excel has colors/comments
4. Verify Details sheet has entries
5. Verify customer download lacks Details sheet
6. Verify S3 storage has Details sheet

---

## Working Files Reference

### Strip Function (WORKING)
**File**: `src/shared/qc_enhanced_excel_report.py` lines 339-381

```python
def strip_details_sheet_for_customer(excel_content: bytes) -> bytes:
    try:
        import openpyxl
        from io import BytesIO

        wb = openpyxl.load_workbook(BytesIO(excel_content))

        if 'Details' not in wb.sheetnames:
            logger.warning("[STRIP_DETAILS] No Details sheet found")
            return excel_content

        del wb['Details']
        logger.info(f"[STRIP_DETAILS] Removed Details sheet. Remaining: {wb.sheetnames}")

        output_buffer = BytesIO()
        wb.save(output_buffer)
        output_buffer.seek(0)
        result = output_buffer.read()

        logger.info(f"[STRIP_DETAILS] Success. Original: {len(excel_content)}, New: {len(result)}")
        return result

    except Exception as e:
        logger.error(f"[STRIP_DETAILS] Error: {e}")
        return excel_content
```

### Dual Version Handling (WORKING)
**File**: `src/lambdas/interface/handlers/background_handler.py` lines 2219-2250

```python
# Use FULL version (with Details) for S3 storage
if enhanced_excel_buffer and hasattr(enhanced_excel_buffer, 'full_version'):
    s3_excel_content = enhanced_excel_buffer.full_version
    logger.info("[PREVIEW_S3] Using full version (with Details sheet)")
else:
    s3_excel_content = enhanced_excel_content
    logger.warning("[PREVIEW_S3] No full_version attribute")

# Store FULL version in S3
enhanced_result = storage_manager.store_enhanced_files(...)

# Use CUSTOMER version (without Details) for download
if enhanced_excel_buffer and hasattr(enhanced_excel_buffer, 'customer_version'):
    download_excel_content = enhanced_excel_buffer.customer_version
    logger.info("[PREVIEW_DOWNLOAD] Using customer version (no Details)")
else:
    download_excel_content = enhanced_excel_content
    logger.warning("[PREVIEW_DOWNLOAD] No customer_version attribute")
```

---

## Success Criteria

When implementation is complete, logs should show:

```
[INTERFACE_QC] Extracting validation results from response body
[INTERFACE_QC] Full Excel generated: XX,XXX bytes (with Details sheet)
[STRIP_DETAILS] Removed Details sheet. Remaining sheets: ['Updated Values', 'Original Values', 'Reasons']
[INTERFACE_QC] Customer Excel created: XX,XXX bytes (no Details sheet)
[PREVIEW_S3] Using full version (with Details sheet) for S3 storage
[PREVIEW_DOWNLOAD] Using customer version (no Details sheet) for download
Created 3-sheet Excel with XX total detail entries (new + historical)
```

And customer download should NOT contain Details sheet while S3 storage DOES.
