# Table Cleaning Documentation

## Overview

The table cleaning system provides intelligent detection and filtering of Excel and CSV data tables, handling common issues like metadata rows, empty rows/columns, summary statistics, and multiple tables in the same sheet. The system preserves Excel formulas when rows are removed and uses smart heuristics to identify actual data vs non-data content.

## Key Features

### 1. Table Boundary Detection
- **Automatic header detection**: Identifies actual table headers vs metadata rows
- **Data vs summary separation**: Detects summary rows (TOTAL, AVERAGE, etc.) and can exclude them from data processing
- **Multiple table support**: Can identify and extract multiple tables from a single worksheet
- **Smart metadata filtering**: Removes report headers, timestamps, and other non-data rows

### 2. Row Filtering

#### Sparse Row Detection
The system uses an 80% threshold for determining valid data rows:
- **Complete rows** (>80% filled): Always kept as data
- **Sparse rows** (30-80% filled): Analyzed for data patterns
- **Very sparse rows** (<30% filled): Usually removed as metadata
- **Empty rows**: Always removed

#### Special Cases
- **Early rows** (first 3 rows after headers): More lenient filtering to preserve sub-headers
- **Summary rows**: Detected by keywords (TOTAL, AVERAGE) and formula patterns
- **Metadata rows**: Identified by keywords like "Generated", "Report", "Confidential"

### 3. Column Handling

#### Empty Column Detection
The system can identify and handle empty columns:
- Columns with no data are detected
- Trailing empty columns are automatically trimmed
- Interior empty columns can be preserved or removed based on configuration

#### Column Normalization
- Unicode characters converted to ASCII equivalents (em-dash → hyphen)
- Special spaces normalized to regular spaces
- Consistent naming for unnamed columns (Column_1, Column_2, etc.)

### 4. Formula Preservation

When rows are deleted from Excel files:
- Uses openpyxl's `delete_rows()` method which automatically adjusts formula references
- Formulas like `=SUM(A2:A10)` become `=SUM(A2:A8)` if 2 rows are deleted
- External references are detected and preserved
- Cell references in formulas are automatically updated

## Implementation Details

### Core Components

#### 1. ExcelTableDetector (`excel_table_detector.py`)
Advanced detection class with methods:
- `detect_table_boundaries()`: Find all tables in a worksheet
- `filter_data_rows()`: Smart row filtering with metadata detection
- `preserve_formulas_on_row_deletion()`: Safely delete rows while maintaining formulas
- `detect_empty_columns()`: Identify columns with no data

#### 2. SharedTableParser (`shared_table_parser.py`)
Main parsing interface:
- Integrates with ExcelTableDetector when available
- Falls back to basic detection if advanced detector not present
- Handles both CSV and Excel files
- Manages row key generation with deduplication

### Usage Examples

#### Basic Table Parsing
```python
from shared_table_parser import S3TableParser

parser = S3TableParser()
result = parser.parse_s3_table(
    bucket='my-bucket',
    key='data/report.xlsx',
    id_fields=['Company_ID']  # For row key generation
)

# Result includes cleaned data with:
# - Metadata rows removed
# - Empty rows/columns trimmed
# - Summary rows optionally excluded
# - Row keys generated for deduplication
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
- **Sparse row threshold**: 80% (rows with less than 80% filled cells are examined closely)
- **Very sparse threshold**: 30% (rows with less than 30% filled are usually removed)
- **Header detection minimum**: 2 non-empty cells required for valid headers
- **Summary detection threshold**: 30% of cells must be aggregate formulas

### Patterns
The system uses regex patterns to identify:
- **Data patterns**: Dates, IDs, URLs, email addresses
- **Summary formulas**: SUM, AVERAGE, COUNT, MIN, MAX, MEDIAN, SUBTOTAL
- **Metadata keywords**: "generated", "report", "confidential", "page"

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
- Check for metadata rows above headers
- Ensure headers have at least 2 non-empty cells
- Verify headers don't match metadata patterns

#### 2. Data Rows Filtered Out
**Problem**: Valid data rows are being removed
**Solution**:
- Adjust sparse row thresholds if needed
- Check if rows match metadata patterns
- Verify fill percentage calculations

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