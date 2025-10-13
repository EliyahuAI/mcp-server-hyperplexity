# Table Maker Tests

This directory contains unit and integration tests for the table generation system.

## Test Types

### Unit Tests
- Fast tests that don't make external API calls
- Use mocks/fixtures for external dependencies
- Run frequently during development

### Integration Tests
- End-to-end tests using REAL API calls
- Test full workflows with actual Claude API
- Require `ANTHROPIC_API_KEY` environment variable
- Slower and may incur API costs

## Setup

### Prerequisites

1. Install test dependencies:
```bash
cd table_maker
pip install -r requirements.txt
```

2. Set up Anthropic API key:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## Running Tests

### Run All Unit Tests (No API Calls)
```bash
pytest -m "not integration"
```

### Run All Integration Tests (Real API Calls)
```bash
pytest -m integration -v
```

### Run Specific Test File
```bash
pytest tests/test_integration.py -v
```

### Run Specific Test Function
```bash
pytest tests/test_integration.py::test_full_conversation_flow -v
```

### Run with Detailed Output
```bash
pytest -v -s
```

### Run with Coverage Report
```bash
pytest --cov=src --cov-report=html --cov-report=term-missing
```

## Integration Test Scenarios

The integration tests in `test_integration.py` cover the following scenarios:

### 1. Full Conversation Flow
- Start conversation with research description
- Perform 2-3 refinement turns
- Finalize table structure
- Verify completeness and validity

**Test Function:** `test_full_conversation_flow`

### 2. Row Expansion
- Create initial table with sample rows
- Expand rows based on specific criteria
- Verify generated rows match schema
- Test row merging with deduplication

**Test Function:** `test_row_expansion`

### 3. CSV Generation
- Generate CSV from finalized table
- Verify CSV structure and content
- Test appending rows to existing CSV
- Validate CSV structure matches schema

**Test Function:** `test_csv_generation`

### 4. Config Generation
- Create research table with importance levels
- Generate AI validation config
- Verify config structure and search groups
- Export config to JSON file

**Test Function:** `test_config_generation`

### 5. Save and Load Conversation
- Create and save conversation to file
- Load conversation in new handler
- Verify state preservation
- Continue conversation after loading

**Test Function:** `test_save_load_conversation`

### 6. Error Handling
- Test uninitialized conversation operations
- Test invalid CSV operations
- Test schema validation failures
- Verify proper error messages

**Test Function:** `test_error_handling`

### 7. Iterative Row Expansion
- Generate large datasets in batches
- Test batch processing functionality
- Verify all rows have correct structure

**Test Function:** `test_iterative_row_expansion`

## Test Output

Integration tests create temporary files during execution:
- Conversation JSON files
- Generated CSV files
- AI validation configs

All files are created in temporary directories and cleaned up after tests complete.

## CI/CD Integration

### Skip Integration Tests in CI
```bash
pytest -m "not integration"
```

### Run Integration Tests in CI (with API key)
```bash
export ANTHROPIC_API_KEY="${SECRET_ANTHROPIC_API_KEY}"
pytest -m integration --tb=short
```

## Troubleshooting

### "ANTHROPIC_API_KEY not set"
- Ensure the environment variable is set before running integration tests
- Check that the key is valid and has sufficient credits

### Import Errors
- Verify you're running tests from the `table_maker` directory
- Ensure all dependencies are installed: `pip install -r requirements.txt`

### Test Timeouts
- Integration tests may take 1-2 minutes per test due to API calls
- Increase pytest timeout if needed: `pytest --timeout=300`

### API Rate Limits
- If you hit rate limits, add delays between tests or reduce concurrent tests
- Consider using `pytest-xdist` with limited workers: `pytest -n 2`

## Writing New Tests

### Unit Test Template
```python
import pytest

def test_something():
    # Arrange
    # ... setup test data

    # Act
    # ... call function under test

    # Assert
    # ... verify results
    pass
```

### Integration Test Template
```python
import pytest

@pytest.mark.integration
@pytest.mark.asyncio
async def test_something_with_api(conversation_handler):
    # Test that uses real API calls
    result = await conversation_handler.start_conversation(...)
    assert result['success']
    # ... more assertions
```

## Test Markers

Use markers to categorize tests:

```python
@pytest.mark.integration  # Real API calls
@pytest.mark.unit         # No external calls
@pytest.mark.slow         # Takes >10 seconds
```

Run specific markers:
```bash
pytest -m integration
pytest -m "unit and not slow"
```

## Best Practices

1. **Use Fixtures**: Define reusable test components in `conftest.py`
2. **Clean Up**: Use `temp_output_dir` fixture for temporary files
3. **Clear Tests**: Each test should be independent and self-contained
4. **Good Names**: Test names should clearly describe what they test
5. **Assertions**: Use descriptive assertion messages
6. **Logging**: Integration tests include detailed logging for debugging

## Performance Notes

- Unit tests should complete in <5 seconds
- Integration tests may take 1-2 minutes each
- Total integration suite runtime: ~10-15 minutes
- Consider running integration tests only before commits/merges
