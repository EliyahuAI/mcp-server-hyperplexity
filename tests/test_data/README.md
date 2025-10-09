# Test Data for History Handling Tests

This directory contains mock data structures for testing the history handling system.

## Files

### mock_validation_results.py

Contains mock data structures that match the actual output from the validation system:

- `get_mock_validation_results()` - Validation results from schema validator
- `get_mock_qc_results()` - QC results that adjust validation results
- `get_mock_config_data()` - Configuration data structure
- `get_mock_excel_data()` - Parsed Excel data from shared_table_parser
- `get_mock_session_info()` - Session info with validation runs
- `get_mock_cell_comments()` - Cell comments as they appear in Excel

## Usage

```python
from tests.test_data.mock_validation_results import (
    get_mock_validation_results,
    get_mock_qc_results
)

# Use in tests
validation_results = get_mock_validation_results()
qc_results = get_mock_qc_results()
```

## Data Structure Overview

### Validation Results Structure
```python
{
    'row_hash': {
        'ColumnName': {
            'value': 'validated value',
            'confidence_level': 'HIGH|MEDIUM|LOW',
            'original_confidence': 'HIGH|MEDIUM|LOW',
            'reasoning': 'explanation',
            'sources': ['url1', 'url2'],
            'citations': [{'title': '...', 'url': '...', 'cited_text': '...'}]
        }
    }
}
```

### QC Results Structure
```python
{
    'row_hash': {
        'ColumnName': {
            'qc_applied': True,
            'qc_entry': 'corrected value',
            'qc_confidence': 'HIGH|MEDIUM|LOW',
            'qc_original_confidence': 'reassessed original confidence',
            'qc_reasoning': 'why QC made changes',
            'qc_citations': 'citation text',
            'update_importance': '1-5'
        }
    }
}
```

### Cell Comment Format
```
Original Value: ABC Corp (MEDIUM Confidence)

Key Citation: Company website dated 2024-01-15 (https://example.com/about)

Sources:
[1] Company Website (https://example.com/about): "ABC Corp was founded in..."
[2] SEC Filing (https://sec.gov/filing): "ABC Corp (formerly ABC Corporation)..."
```

## Testing Scenarios

The mock data supports testing:

1. **New File (No History)** - Fresh data with no prior validation
2. **Preview Then Full** - Preview validation followed by full validation
3. **Re-validation** - File with existing validation history
4. **QC Integration** - QC corrections applied to validation results
5. **Confidence Tracking** - Changes in confidence levels over time
