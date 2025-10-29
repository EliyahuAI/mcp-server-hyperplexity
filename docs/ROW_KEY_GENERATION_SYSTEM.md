# Row Key Generation and Caching System

## Overview

Row keys are SHA-256 hashes that uniquely identify rows across the entire validation pipeline. They serve as the primary mechanism for matching validation results back to their source rows in Excel/CSV files.

**CRITICAL RULE**: Row keys MUST be generated exactly ONCE per table parsing operation and NEVER regenerated. All subsequent operations must use the pre-computed row keys embedded in the parsed data.

## Why Row Keys Matter

Row keys solve a critical problem: how to reliably match validation results back to their source rows when:
- Row order may change during processing
- Multiple rows may have similar or identical ID field values
- Different parts of the system may extract ID fields differently from configuration

Without consistent row key generation, validation results and QC data cannot be matched back to the correct Excel rows, leading to complete failure of the validation system.

## Row Key Generation Strategy

### Primary Strategy: ID Field-Based Keys

When `id_fields` are provided, row keys are generated using only those fields:

```python
row_key = generate_row_key(row_data, primary_keys=id_fields)
```

This creates a hash from the concatenated values of ID fields:
```python
# Example: id_fields = ['Researcher', 'Institution']
# Row: {'Researcher': 'Philip S. Low', 'Institution': 'Purdue University', ...}
# Key generated from: "Philip S. Low|Purdue University"
```

### Deduplication Strategy: Full Row Hash

If multiple rows produce the same ID-based hash (duplicate ID fields), the system falls back to a full row hash:

```python
# Detect duplicates in first pass
id_hash_counts = {}
for row in rows:
    id_hash = generate_row_key(row, primary_keys=id_fields)
    id_hash_counts[id_hash] += 1

# Second pass: use full hash for duplicates
for row in rows:
    id_hash = generate_row_key(row, primary_keys=id_fields)
    if id_hash_counts[id_hash] > 1:
        # Duplicate - use full row hash
        row_key = generate_row_key(row, primary_keys=None)
    else:
        # Unique - use ID hash
        row_key = id_hash

    row['_row_key'] = row_key
```

This ensures:
1. Rows with unique ID fields get stable, ID-based keys
2. Rows with duplicate ID fields get unique, full-content-based keys
3. Every row has exactly one unique identifier

## The Caching System

### Problem Being Solved

Before caching, row keys were being regenerated multiple times:
1. Once during initial table parsing
2. Again when creating Excel reports (if _row_key wasn't preserved)
3. Potentially again in validation if _row_key wasn't passed through

Each regeneration risked using different `id_fields`, producing different hashes and breaking the row matching.

### Solution: Parsed Table Caching

The caching system (implemented in `src/shared/shared_table_parser.py`) ensures row keys are generated exactly once:

```python
def parse_s3_table(self, bucket, key, id_fields=None, ...):
    # 1. Check for cached parsed JSON first
    parsed_cache_key = self._get_parsed_cache_key(key)  # e.g., "uploads/table_parsed.json"
    cached_result = self._try_load_parsed_cache(bucket, parsed_cache_key, id_fields)

    if cached_result:
        # Cache hit - use pre-computed row keys
        return cached_result

    # 2. Cache miss - parse the file and generate row keys
    result = self._parse_csv_or_excel(...)

    # 3. Save parsed result to cache
    self._save_parsed_cache(bucket, parsed_cache_key, result, id_fields)

    return result
```

### Cache Validation

The cache loading function performs multiple validations:

1. **Last Modified Check**: Ensures cache is newer than source file
   ```python
   cache_modified = cache_metadata['LastModified']
   original_modified = original_metadata['LastModified']

   if cache_modified < original_modified:
       # Source file was updated - invalidate cache
       return None
   ```

2. **ID Fields Match**: Ensures the requested `id_fields` match what was used to generate the cache
   ```python
   cached_id_fields = cached_data['metadata']['id_fields']
   if id_fields != cached_id_fields:
       # Different ID fields requested - invalidate cache
       return None
   ```

3. **Structure Validation**: Ensures required fields are present
   ```python
   if 'metadata' not in cached_data or 'data' not in cached_data:
       return None

   if id_fields and '_row_key' not in cached_data['data'][0]:
       return None
   ```

### Cache File Format

Cached files are stored as `{original_filename}_parsed.json`:
- `uploads/research_data.xlsx` → `uploads/research_data_parsed.json`
- `config/validation_table.csv` → `config/validation_table_parsed.json`

Structure:
```json
{
  "metadata": {
    "filename": "research_data.xlsx",
    "id_fields": ["Researcher", "Institution"],
    "used_focused_version": false,
    ...
  },
  "column_names": ["Researcher", "Institution", "Citation Count", ...],
  "data": [
    {
      "_row_key": "f0190109292987df20dc386cadfdaf86a2e90ab1918bc5744a5496eac0d82bcb",
      "Researcher": "Philip S. Low",
      "Institution": "Purdue University",
      ...
    },
    ...
  ],
  "total_rows": 3,
  "total_columns": 5
}
```

## Flow Through the System

### 1. Initial Table Upload and Parsing

```
User uploads table.xlsx
  ↓
background_handler.py receives request
  ↓
Calls shared_table_parser.parse_s3_table(bucket, key, id_fields=['Researcher', 'Institution'])
  ↓
Parser checks cache: uploads/table_parsed.json
  ↓
Cache MISS - parse table.xlsx
  ↓
Generate row keys with id_fields
  ↓
Save result to uploads/table_parsed.json
  ↓
Return parsed data with _row_key fields
```

### 2. Validation Lambda

```
Validation lambda receives:
{
  "rows": [
    {"_row_key": "f019...", "Researcher": "Philip S. Low", ...},
    {"_row_key": "d1ff...", "Researcher": "Sarah Bohndiek", ...}
  ],
  "validation_targets": [...]
}
  ↓
For each row:
  - Extract pre-computed _row_key
  - Validate fields
  - Store results using row_key as dict key
  ↓
Return validation_results:
{
  "f019...": {"field1": {...}, "field2": {...}},
  "d1ff...": {"field1": {...}, "field2": {...}}
}
```

### 3. QC Lambda

```
QC lambda receives:
{
  "validation_results": {
    "f019...": {...},
    "d1ff...": {...}
  },
  ...
}
  ↓
For each row_key in validation_results:
  - Perform QC review
  - Store QC decisions using same row_key
  ↓
Return qc_results:
{
  "f019...": {"field1": {...}, "field2": {...}},
  "d1ff...": {"field1": {...}, "field2": {...}}
}
```

### 4. Excel Report Generation

```
excel_report_qc_unified.py creates final Excel
  ↓
Loads parsed data from cache OR re-parses with SAME id_fields
  ↓
Cache HIT - uses pre-computed row keys
  ↓
Extracts row keys from rows_data:
  excel_row_keys = [row['_row_key'] for row in rows_data]
  ↓
Matches against validation_results and qc_results using same keys:
{
  "f019...": <Excel Row 1>,  # Matches validation_results["f019..."]
  "d1ff...": <Excel Row 2>   # Matches validation_results["d1ff..."]
}
  ↓
Writes Excel with QC values applied
```

## Critical Code Locations

### Row Key Generation (ONE TIME)
- **File**: `src/shared/shared_table_parser.py`
- **Methods**:
  - `_parse_csv_content()` lines 430-466 (CSV parsing)
  - `_parse_excel_content()` lines 701-847 (Excel parsing)
- **What it does**: Generates row keys and embeds them as `_row_key` field

### Cache Management
- **File**: `src/shared/shared_table_parser.py`
- **Methods**:
  - `_get_parsed_cache_key()` - Generate cache filename
  - `_try_load_parsed_cache()` - Load and validate cache
  - `_save_parsed_cache()` - Save parsed data to cache

### Validation Results Storage
- **File**: `src/lambdas/validation/lambda_function.py`
- **Line**: 3370 - `validation_results[row_key] = result`
- **What it does**: Uses row_key as dict key for storing validation results

### QC Results Storage
- **File**: `src/shared/qc_module.py`
- **What it does**: Uses row_key as dict key for storing QC results

### Excel Report Row Matching
- **File**: `src/shared/excel_report_qc_unified.py`
- **Lines**: 543-552 - Extract pre-computed row keys from rows_data
- **What it does**: Uses `_row_key` fields to match Excel rows to validation results

## Common Issues and Solutions

### Issue 1: Row Key Mismatch

**Symptoms**:
```
[ERROR] [ROW_KEY_MATCH] HASH MISMATCH: 0 matching keys despite having 3 validation results!
[ERROR] Excel keys sample: ['97456842...', '70b024...', '33ae9b...']
[ERROR] Validation keys sample: ['f0190109...', 'd1ff16...', 'be2db1...']
```

**Root Cause**: Row keys were regenerated with different `id_fields`

**Solution**:
1. Ensure all calls to `parse_s3_table()` use the SAME `id_fields`
2. Use the caching system to prevent regeneration
3. Always preserve `_row_key` fields through the pipeline

### Issue 2: Cache Invalidation

**Symptoms**: Cache is ignored despite existing

**Common Causes**:
1. Source file was modified after cache was created (expected behavior)
2. Different `id_fields` requested than what's in the cache
3. Cache file is corrupted or missing required fields

**Solution**: Let the cache system automatically handle invalidation and re-parse

### Issue 3: Missing _row_key Fields

**Symptoms**: Validation or Excel generation fails to find row keys

**Root Cause**: `_row_key` fields were stripped during data transformation

**Solution**:
- Always preserve `_row_key` when transforming data structures
- Check that `_row_key` exists before accessing it
- Use fallback generation only as a last resort (with warning log)

## Best Practices

### DO:
✅ Always pass `id_fields` to `parse_s3_table()`
✅ Use the caching system by default
✅ Preserve `_row_key` fields through all transformations
✅ Use row_key as the dict key for results storage
✅ Extract pre-computed row keys rather than regenerating
✅ Log when cache hits/misses occur
✅ Validate row key matching before processing results

### DON'T:
❌ NEVER regenerate row keys after initial parsing
❌ NEVER call `generate_row_key()` in Excel report generation
❌ NEVER strip `_row_key` fields from parsed data
❌ NEVER assume row order is preserved
❌ NEVER use array indices to match rows
❌ NEVER bypass the cache without good reason

## Testing Row Key Consistency

To verify row keys are consistent:

```python
# 1. Parse table and get row keys
parser = S3TableParser()
parsed_data = parser.parse_s3_table(bucket, key, id_fields=['ID_Field1', 'ID_Field2'])
original_keys = [row['_row_key'] for row in parsed_data['data']]

# 2. Load from cache
cached_data = parser.parse_s3_table(bucket, key, id_fields=['ID_Field1', 'ID_Field2'])
cached_keys = [row['_row_key'] for row in cached_data['data']]

# 3. Verify they match
assert original_keys == cached_keys, "Row keys changed between parse and cache load!"
```

## Future Considerations

### Handling ID Field Changes

When `id_fields` configuration changes:
1. Cache will be invalidated automatically (ID fields mismatch)
2. New row keys will be generated with new ID fields
3. Previous validation results become invalid (can't be matched)
4. User should be warned that re-validation is required

### Distributed Validation

For distributed validation (multiple rows processed in parallel):
1. All validators must use the SAME pre-computed row keys
2. Row keys must be passed in the validation request
3. Results are aggregated using row keys as merge keys

### Row Key Versioning

Consider adding version metadata to support future changes:
```json
{
  "metadata": {
    "row_key_version": "1.0",
    "row_key_algorithm": "sha256-id-fields-with-full-hash-fallback"
  }
}
```

## Summary

The row key system is the backbone of result matching in the validation pipeline. The caching system ensures:

1. **Consistency**: Row keys generated exactly once per table
2. **Performance**: Cached parsed tables avoid re-parsing
3. **Reliability**: Validation results always match their source rows
4. **Debugging**: Clear logging of cache hits/misses and key generation

By following the "generate once, use everywhere" principle, the system eliminates an entire class of bugs related to row matching and data contamination.
