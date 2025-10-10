# Bug Investigation: Excel Comment Row Offset Issue

## Problem Statement

Excel comments in the **Original Values sheet** are displaying validated values from the wrong rows, while all other data (citations, confidences, cell values) appear correct.

### Observed Symptoms

**First Run (Timestamp: 2025-10-10T14:25:26)**
- Row 0 (NeurIPS 2025): Comment shows `2026-04-23` (ICLR's date - Row 1's value)
- Row 1 (ICLR 2026): Comment shows `2026-07-06` (ICML's date - Row 2's value)
- Row 2 (ICML 2026): Comment shows `2025-12-02` (NeurIPS's date - Row 0's value)

**Pattern**: Circular rotation/shift by +1 row

**Second Run (Timestamp: 2025-10-10T14:28:33)**
- Row 0 (NeurIPS 2025): Comment shows `2025-12-02` ✓ CORRECT

**Pattern**: Bug is intermittent

### Critical Observations

1. **Citations are ALWAYS correct** in the comments - proving the `field_data` dictionary lookup is working correctly
2. **Details sheet shows CORRECT values** for all rows
3. **Updated Values sheet comments** were reported as correct in previous runs
4. **Only the Original Values sheet comments** show wrong validated values
5. **The rest of the comment is OK** - only the "Updated Value" line is wrong

### Expected vs Actual Data

**Details Sheet (CORRECT)**:
```
Series                                          | Original Value | Updated Value | QC Value
Neural Information Processing Systems (2025)    | 2025-11-30    | 2025-11-30   | 2025-12-02
International Conference on Learning Reps (2026)| 2026-04-23    | 2026-04-23   | 2026-04-23
International Conference on Machine Learn (2026)| 2026-07-06    | 2026-07-06   | 2026-07-06
```

**Original Values Sheet Comments (WRONG - First Run)**:
```
Row 0 (NeurIPS):  Updated Value: 2026-04-23  <- Should be 2025-12-02 (or 2025-11-30)
Row 1 (ICLR):     Updated Value: 2026-07-06  <- Should be 2026-04-23
Row 2 (ICML):     Updated Value: 2025-12-02  <- Should be 2026-07-06
```

## Code Investigation

### Relevant Code Sections

**Original Values Sheet Comment Generation** (`excel_report_qc_unified.py` lines 922-1070):
```python
# Line 923: Outer row loop
for row_idx, (row_data, row_key) in enumerate(zip(rows_data, row_keys)):
    # Line 926: Get validation data for this row
    if row_key and row_key in validation_results:
        row_validation_data = validation_results[row_key]

    # Line 934: Inner column loop
    for col_idx, col_name in enumerate(headers):
        # Line 943: Reset validated_value for each column
        validated_value = None

        # Line 947-950: Extract field data
        if col_name in row_validation_data:
            field_data = row_validation_data[col_name]
            original_confidence = field_data.get('original_confidence')
            validated_value = field_data.get('value', '')  # <- BUG SOURCE

        # Line 988-993: Build comment using validated_value
        if validated_value != original_value:
            comment_parts.append(f'Updated Value: {validated_value}')
```

**Debug Logging Output**:
```
[ORIG_SHEET_DEBUG] Row 0 (Conference: NeurIPS 2025): Using validation data for key 50ad1eff...
[ORIG_SHEET_DEBUG] Row 0 Start Date: validated_value='2026-04-23', original_value='2025-12-02'
[COMMENT_BUILD_DEBUG] Row 0 Start Date: About to build comment with validated_value='2026-04-23'
[COMMENT_WRITE_DEBUG] Row 0 Start Date: Writing comment at Excel row 1: Updated Value: 2026-04-23...
```

### The Paradox

**How can this be possible?**
- `row_validation_data = validation_results[row_key]` ✓ Correct lookup (proven by correct Conference name in logs)
- `field_data = row_validation_data[col_name]` ✓ Correct lookup (proven by correct citations)
- `validated_value = field_data.get('value', '')` ❌ Returns WRONG value
- `citations = field_data.get('citations', [])` ✓ Returns CORRECT citations

**This should be impossible in Python** - two `.get()` calls on the same dictionary should return data from the same source!

## Hypotheses Investigated

### Hypothesis 1: Variable Carryover Between Columns
**Theory**: `validated_value` persists from a previous column iteration

**Evidence Against**:
- Line 943 resets `validated_value = None` for each column
- Bug shows rotation pattern across ROWS, not columns
- All rows have the "Start Date" column, so no carryover should occur

**Status**: ❌ Rejected

### Hypothesis 2: Hash Key Mismatch
**Theory**: `row_key` lookup is finding wrong row's validation data

**Evidence Against**:
- Logs show `Row 0 (Conference: NeurIPS 2025)` - conference name is correct
- Citations are correct (they come from the same `field_data` dictionary)
- If hash was wrong, ALL fields would be wrong, not just `value`

**Status**: ❌ Rejected

### Hypothesis 3: Fallback Positional Lookup
**Theory**: Fallback to positional index causes wrong row matching

**Evidence Against**:
- Fallback code was already removed in commit `c85030f5`
- Logs show direct hash key match: `Using validation data for key 50ad1eff...`
- No fallback being triggered

**Status**: ❌ Rejected (already fixed)

### Hypothesis 4: Dictionary Order Mismatch
**Theory**: `validation_results` dict order doesn't match `rows_data` order

**Evidence Against**:
- We use hash-based lookup, not positional iteration
- `row_key in validation_results` lookup is explicit
- Order shouldn't matter for hash-based dict lookups

**Status**: ❌ Rejected

### Hypothesis 5: QC Merge Modified validation_results In-Place
**Theory**: The `validation_results` dict has been modified by QC merge, where the `value` field was replaced with QC values but other fields (citations) were not

**Evidence For**:
- Details sheet shows different logic using separate `pre_qc_value` field
- Details sheet is CORRECT, Original Values is WRONG
- Bug is intermittent (could be timing/processing order related)
- QC merge happens BEFORE Excel generation
- The 'value' field being wrong while 'citations' are correct suggests selective field modification

**Evidence Against**:
- Why would the circular rotation pattern occur?
- Why would QC merge create wrong row associations?

**Status**: ⚠️ **Most Likely** - needs verification

### Hypothesis 6: xlsxwriter Comment Writing Bug
**Theory**: The `write_comment()` function is somehow writing to wrong cell

**Evidence Against**:
- Comment is written to `row_idx + 1, col_idx` which should be correct
- Citations in the comment are correct
- Cell values are correct
- Only the `validated_value` text in the comment is wrong

**Status**: ❌ Rejected

## Attempted Fixes

### Fix 1: Remove Fallback Positional Lookup
**Commit**: `c85030f5`

**Changes**:
- Removed fallback to `str(row_idx)` and `row_idx` in validation data lookup
- Rationale: Fallback was causing random row mismatches

**Result**: Bug persisted

### Fix 2: Add QC Confidence Enforcement
**Commit**: `c85030f5`

**Changes**:
- Added rule: when QC value equals original OR update_importance is 0/1, enforce equal confidences
- Fixed safety check to use actual row data

**Result**: Fixed separate confidence bug, but row offset bug persisted

### Fix 3: Add Debug Logging
**Commit**: `abaab740`

**Changes**:
- Added logging at validated_value extraction point (line 954)
- Added logging before comment building (line 976)
- Added logging before comment writing (line 1064)

**Result**: Revealed that `validated_value` is wrong immediately upon extraction from `field_data.get('value')`

### Fix 4: Use pre_qc_value in Original Values Sheet
**Commit**: `a809fe24`

**Changes**:
```python
# BUGFIX: Use pre-QC value if available (QC merge may have modified 'value' field)
if field_data.get('qc_applied') and 'pre_qc_value' in field_data:
    validated_value = str(field_data.get('pre_qc_value', ''))
else:
    validated_value = field_data.get('value', '')
```

**Rationale**:
- Matches Details sheet logic (lines 264-266)
- Ensures comments show actual multiplex validated value before QC modifications
- If validation_results has been modified by QC merge, use the preserved pre-QC value

**Result**: 🔬 **TESTING REQUIRED**

## Questions Requiring Investigation

### Critical Questions

1. **Where is validation_results created and how is it modified?**
   - Is it created by the validation lambda?
   - Does the interface lambda modify it?
   - Does QC merge happen in-place or create a new dict?

2. **Why do Citations remain correct while Value is wrong?**
   - Are citations and value set at different times?
   - Are they from different source dictionaries?
   - Is there selective field modification happening?

3. **Why is the bug intermittent?**
   - First run: wrong values with circular rotation
   - Second run: correct values
   - What changed between runs?
   - Is it related to processing order, caching, or timing?

4. **Why does the circular rotation pattern occur?**
   - Row 0 gets Row 1's value
   - Row 1 gets Row 2's value
   - Row 2 gets Row 0's value
   - This suggests systematic misalignment, not random errors

5. **Why is Details sheet correct but Original Values wrong?**
   - Details sheet uses: `field_data.get('pre_qc_value')` or `field_data.get('value')`
   - Original Values uses: `field_data.get('value')`
   - What's the difference in their data sources?

### Technical Questions

1. **Is validation_results modified by reference?**
   ```python
   # In qc_integration.py line 112
   merged_results = self.qc_module.merge_multiplex_and_qc_results(
       multiplex_results=all_multiplex_results,
       qc_results=qc_results,
       original_row_data=row
   )
   ```
   - Does this modify `all_multiplex_results` in-place?
   - Or does it return a new dictionary?

2. **What is the structure of validation_results?**
   ```python
   validation_results = {
       'row_hash_key': {
           'column_name': {
               'value': ???,  # Is this original or QC-modified?
               'citations': [...],
               'qc_applied': True/False,
               'pre_qc_value': ???,  # Is this always present?
               ...
           }
       }
   }
   ```

3. **How does Excel generation receive validation_results?**
   - From interface lambda?
   - Already merged with QC?
   - Separate from QC results?

## Recommended Next Steps

### Immediate Actions

1. **Test Fix 4** - Run validation and check if Original Values comments now show correct values

2. **Add More Granular Logging**:
   ```python
   # Log the entire field_data dict structure
   logger.info(f"[DEBUG] Row {row_idx} {col_name} field_data keys: {field_data.keys()}")
   logger.info(f"[DEBUG] Row {row_idx} {col_name} value: {field_data.get('value')}")
   logger.info(f"[DEBUG] Row {row_idx} {col_name} pre_qc_value: {field_data.get('pre_qc_value')}")
   logger.info(f"[DEBUG] Row {row_idx} {col_name} qc_applied: {field_data.get('qc_applied')}")
   ```

3. **Verify validation_results Structure**:
   - Add logging in interface lambda before passing to Excel generation
   - Log the entire validation_results structure for all 3 rows
   - Compare 'value' field across all rows

### Deep Investigation

1. **Trace QC Merge Process**:
   - Review `qc_module.py` merge_multiplex_and_qc_results()
   - Check if it modifies dictionaries in-place
   - Verify it preserves `pre_qc_value` correctly

2. **Compare Updated Values vs Original Values Code Paths**:
   - Why does Updated Values work correctly?
   - What's different in how they access `validated_value`?
   - Is there a timing difference?

3. **Instrument the Full Pipeline**:
   - Add logging in validation lambda output
   - Add logging in QC merge
   - Add logging in interface lambda before Excel
   - Track the 'value' field through entire pipeline

### Validation Tests

1. **Test with QC Disabled**:
   - Does bug still occur when QC is disabled?
   - This would prove/disprove QC merge hypothesis

2. **Test with Different Row Counts**:
   - Does rotation pattern change with 4+ rows?
   - Or is it always +1 circular shift?

3. **Test with Different Columns**:
   - Does bug affect other columns besides "Start Date"?
   - Or is it column-specific?

## Current Status

**Bug Status**: 🔴 **ACTIVE** - Partial fix applied, needs testing

**Confidence in Fix**: ⚠️ **LOW-MEDIUM** - Fix addresses hypothesis 5 but root cause not fully understood

**Risk**: ⚠️ **MEDIUM** - If hypothesis 5 is wrong, we're masking a deeper data integrity issue

**Next Action**: **TEST** fix with full validation run and verify Original Values sheet comments

## Files Involved

### Primary Files
- `/src/shared/excel_report_qc_unified.py` - Excel generation with bug
- `/src/shared/qc_module.py` - QC merge logic
- `/src/shared/qc_integration.py` - QC integration layer

### Supporting Files
- `/src/lambdas/interface/lambda_function.py` - Calls Excel generation
- `/src/prompts.yml` - QC prompt instructions

## Related Issues

- **QC Confidence Enforcement Bug** - Fixed in commit `c85030f5`
- **Fallback Positional Lookup Bug** - Fixed in commit `c85030f5`

## Conclusion

This bug is particularly insidious because:

1. **The paradox is real**: Same dictionary returning different correctness for different fields
2. **The pattern is systematic**: Circular +1 rotation, not random
3. **The bug is intermittent**: Sometimes works, sometimes doesn't
4. **The scope is narrow**: Only Original Values comments, only the validated_value

The most likely explanation is that the `validation_results` dictionary has been modified by the QC merge process, with the 'value' field being selectively replaced while 'citations' remain untouched. However, this doesn't fully explain the circular rotation pattern or the intermittent nature.

**This bug requires deeper investigation into the QC merge process and validation_results data flow before we can be confident in any fix.**
