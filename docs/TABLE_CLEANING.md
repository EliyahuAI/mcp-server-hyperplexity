# Table Cleaning Documentation

## Overview

The table cleaning system provides intelligent detection and filtering of Excel and CSV data tables, handling common issues like metadata rows, empty rows/columns, summary statistics, and multiple tables in the same sheet. The system preserves Excel formulas when rows are removed and uses smart heuristics to identify actual data vs non-data content.

## Key Features

### 1. Table Boundary Detection
- **ID column detection**: Automatically identifies header rows containing ID columns (Company_ID, Product_ID, etc.)
- **ID columns as definitive headers**: When ID columns are found, that row is definitively treated as the header row
- **Automatic header detection**: Identifies actual table headers vs metadata rows
- **Metadata pattern rejection**: Rejects rows with patterns like "Department:", "Quarter:", "Generated", etc.
- **Data vs summary separation**: Detects summary rows (TOTAL, AVERAGE, etc.) using keyword and vertical range formula detection
- **Multiple table support**: Can identify and extract multiple tables from a single worksheet
- **Smart metadata filtering**: Removes report headers, timestamps, and other non-data rows
- **Empty column removal**: Automatically removes columns without headers after header row is found
- **Priority sheet selection**: Defaults to "Updated Values" sheet if available

### 2. Cleaning Log System
- **Comprehensive operation tracking**: Logs all cleaning operations with enough detail for restoration
- **File versioning**: Saves both original and cleaned versions of files
- **Primary file in results folder**: Cleaned version saved as primary file in base results folder
- **Restoration capability**: Generates restoration scripts to recover original structure
- **Summary reporting**: Provides human-readable reports of all cleaning operations

### 3. Row Filtering

#### Sparse Row Detection (Header Detection Phase Only)
The system uses sparse row filtering ONLY during header detection to skip metadata:
- **During header search**: Rows with <80% filled cells may be skipped as potential headers
- **After headers found**: ALL data rows are kept, including sparse ones
- **Empty rows**: Always removed (completely empty rows with no data)
- **Summary row detection**: Uses both keywords (TOTAL, AVERAGE, etc.) and vertical range formula patterns

#### Important Changes (Latest Updates)
- **Sparse row filtering is ONLY applied during header detection**
- **Once headers are found, sparse data rows are PRESERVED**
- **This ensures partial data records are not lost**
- **Summary rows are detected more accurately using vertical range formulas (e.g., =SUM(A7:A11))**
- **Rows with ID values (like '001', '002') are not mistaken for summary rows**
- **Empty leading columns are now properly handled** - data is correctly aligned with headers even when empty columns exist before data
- **Column alignment tracking** - header column indices are tracked to ensure proper data extraction when columns without headers are removed

#### Special Cases
- **ID columns are definitive**: If a row contains ID columns (Product_ID, Company_ID, etc.), it's treated as the header row
- **Summary rows**: Detected by keywords (TOTAL, AVERAGE) and formula patterns
- **Metadata rows**: Identified by keywords like "Generated", "Report", "Confidential" - only filtered during header detection

### 4. Column Handling

#### Empty Column Detection and Removal
The system handles empty columns intelligently:
- **Header-based filtering**: Columns without headers are automatically removed
- **Empty column detection**: Columns with no data are identified
- **Automatic removal**: Empty leading columns (before data columns) are removed
- **Column index tracking**: The system tracks which columns have headers (`header_column_indices`) to maintain proper data alignment
- **Formula-aware**: Column removal preserves formula references using openpyxl's built-in methods
- **Data alignment**: When extracting data rows, the system uses header column indices to correctly map data from original columns to headers

#### Column Normalization
- Unicode characters converted to ASCII equivalents (em-dash → hyphen)
- Special spaces normalized to regular spaces
- Columns without headers are removed rather than given generic names

### 5. Formula Preservation

#### Row Deletion
When rows are deleted from Excel files:
- Uses openpyxl's `delete_rows()` method which automatically adjusts formula references
- Formulas like `=SUM(A2:A10)` become `=SUM(A2:A8)` if 2 rows are deleted
- All cell references in formulas are automatically updated

#### Column Deletion
When columns are deleted from Excel files:
- Uses openpyxl's `delete_cols()` method which automatically adjusts formula references
- Formulas referencing columns to the right of deleted columns are adjusted
- Example: If column B is deleted, `=SUM(C2:C10)` becomes `=SUM(B2:B10)`
- Cross-references between tables are preserved

## Implementation Details

### Core Components

#### 1. ExcelTableDetector (`excel_table_detector.py`)
Advanced detection class with methods:
- `detect_table_boundaries()`: Find all tables in a worksheet, returns `header_column_indices` for proper data alignment
- `filter_data_rows()`: Smart row filtering with metadata detection (expects first row to be headers)
- `preserve_formulas_on_row_deletion()`: Safely delete rows while maintaining formulas
- `preserve_formulas_on_column_deletion()`: Safely delete columns while maintaining formulas
- `detect_empty_columns()`: Identify columns with no data
- `_is_summary_row()`: Improved detection using ID values and vertical range formulas to avoid false positives

#### 2. SharedTableParser (`shared_table_parser.py`)
Main parsing interface:
- Integrates with ExcelTableDetector when available
- Falls back to basic detection if advanced detector not present
- Handles both CSV and Excel files
- Manages row key generation with deduplication
- Prefers focused/cleaned versions from results folder
- Integrates with cleaning logger
- Uses `header_column_indices` from detector to correctly align data with headers when empty columns are present

#### 3. TableCleaningLogger (`table_cleaning_logger.py`)
Comprehensive logging system:
- `start_file_cleaning()`: Initialize cleaning log for a file
- `log_header_detection()`: Log how headers were detected
- `log_row_removal()`: Track removed rows with content
- `log_column_removal()`: Track removed columns
- `finalize_cleaning()`: Generate summary statistics
- `save_log()`: Save JSON log file
- `save_original_and_cleaned()`: Save both file versions
- `get_restoration_script()`: Generate Python restoration code

### Usage Examples

#### Basic Table Parsing with Cleaning Log
```python
from shared_table_parser import S3TableParser

# Parser with cleaning log enabled (default)
parser = S3TableParser(enable_cleaning_log=True, output_dir='results')

result = parser.parse_s3_table(
    bucket='my-bucket',
    key='data/report.xlsx',
    id_fields=['Company_ID'],  # For row key generation
    use_focused=True,  # Prefer cleaned version if exists
    save_cleaned=True  # Save cleaned version
)

# Result includes cleaned data with:
# - Metadata rows removed
# - Empty rows/columns trimmed
# - Summary rows optionally excluded
# - Row keys generated for deduplication
# - Cleaning log saved to results folder
# - Both original and cleaned files saved
```

#### Advanced Table Detection
```python
from excel_table_detector import ExcelTableDetector
from openpyxl import load_workbook

detector = ExcelTableDetector()
workbook = load_workbook('report.xlsx')
worksheet = workbook.active

# Find all tables
tables = detector.detect_table_boundaries(worksheet)
for table in tables:
    print(f"Found {table['table_type']} table at rows {table['start_row']}-{table['end_row']}")
    if table['has_summary']:
        print(f"  Summary starts at row {table['summary_start_row']}")

# Filter data rows
data_rows = list(worksheet.iter_rows(values_only=True))
filtered_rows, metadata = detector.filter_data_rows(
    data_rows,
    headers=['Col1', 'Col2', 'Col3'],
    preserve_summary=False
)
print(f"Removed {metadata['removed_empty']} empty rows")
print(f"Removed {metadata['removed_sparse']} sparse rows")
```

#### Handling Empty Columns
```python
# Detect empty columns in data
empty_cols = detector.detect_empty_columns(worksheet, start_row=1, end_row=100)
print(f"Found {len(empty_cols)} empty columns: {empty_cols}")

# Remove empty columns during parsing
result = parser.parse_s3_table(
    bucket='my-bucket',
    key='data/report.xlsx',
    remove_empty_columns=True  # Optional parameter
)
```

## Configuration Options

### Thresholds
These can be adjusted in the code:
- **Sparse row threshold during header detection**: 80% (rows with less than 80% filled cells may be skipped as potential headers)
- **Very sparse threshold during header detection**: 30% (rows with less than 30% filled are likely metadata)
- **Data row filtering**: NO FILTERING - all non-empty data rows are kept after headers are found
- **Header detection minimum**: 2 non-empty cells required OR presence of ID columns
- **Summary detection threshold**: 30% of cells must be aggregate formulas

### Patterns
The system uses regex patterns and keywords to identify:
- **ID column patterns**: '_ID', 'PRODUCT_ID', 'COMPANY_ID', 'CUSTOMER_ID', etc.
- **Data patterns**: Dates, IDs, URLs, email addresses
- **Summary formulas**: SUM, AVERAGE, COUNT, MIN, MAX, MEDIAN, SUBTOTAL
- **Metadata keywords**: "generated", "report", "confidential", "page" (only checked during header detection)

## CSV-Specific Features

### Comment Line Filtering
CSV files with metadata comments are handled:
```csv
# Generated: 2024-01-15
# Report Type: Sales Analysis
Company,Revenue,Growth
ABC Corp,1000000,15%
```
Lines starting with `#` are automatically filtered out.

### Delimiter Detection
The system automatically detects delimiters:
1. Tries common delimiters: `,`, `;`, `\t`, `|`, `:`, ` `
2. Scores each based on consistency across lines
3. Falls back to manual parsing if needed

### Encoding Support
Multiple encodings are tried in order:
- UTF-8 (with and without BOM)
- Latin-1, CP1252, ISO-8859-1
- UTF-16 variants
- DOS/OEM encodings
- ASCII as last resort

## Table Maker Integration

When tables are generated by the table maker workflow:
1. Two CSV files are created:
   - Human-readable with `#` comment metadata
   - Clean version for validation (no comments)
2. Parser automatically selects the clean version
3. ID fields are extracted from `generation_metadata.identification_columns`
4. Row keys use hybrid deduplication (ID-based for unique, full-row for duplicates)

## Best Practices

### 1. ID Field Usage
Always provide ID fields when available:
- Enables better row key generation
- Improves deduplication accuracy
- Maintains consistency across validation runs

### 2. Formula Preservation
When modifying Excel files with formulas:
- Use the advanced detector's `preserve_formulas_on_row_deletion()` method
- Avoid manual row deletion which breaks references
- Test formula adjustments after modifications

### 3. Multiple Tables
For sheets with multiple tables:
- Process each table separately using detected boundaries
- Check `table_type` to distinguish data vs summary tables
- Consider the relationship between tables

### 4. Performance
For large files:
- Use `max_rows` parameter to limit processing
- Consider streaming approaches for very large datasets
- Cache parsed results when doing multiple operations

## Troubleshooting

### Common Issues

#### 1. Headers Not Detected
**Problem**: Table headers are being skipped or misidentified
**Solution**:
- Ensure ID columns are present in the header row for automatic detection
- Check for metadata rows above headers that might be mistaken as headers
- Ensure headers have at least 2 non-empty cells or contain ID columns
- Verify headers don't match metadata patterns like "Report", "Generated", etc.

#### 2. Data Rows Filtered Out
**Problem**: Valid data rows are being removed
**Solution**:
- This should not happen with the updated logic - sparse data rows are preserved
- Only completely empty rows are removed after headers are found
- If data is still being filtered, check if the header detection is correct
- Verify that the advanced table detector is being used when available

#### 3. Formula References Broken
**Problem**: Excel formulas show #REF! errors after processing
**Solution**:
- Use `preserve_formulas_on_row_deletion()` method
- Don't use read-only mode when modifying formulas
- Verify worksheet is saved after modifications

#### 4. Empty Columns Not Removed
**Problem**: Trailing or interior empty columns remain
**Solution**:
- Enable `remove_empty_columns` option
- Check column detection range
- Verify no hidden data in "empty" columns

## Future Enhancements

Planned improvements include:
- Machine learning-based table detection
- Support for merged cells and complex headers
- Automatic pivot table recognition
- Cross-sheet formula preservation
- Streaming support for very large files
- Configuration file support for custom thresholds