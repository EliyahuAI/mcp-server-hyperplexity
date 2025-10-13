# Testing Guide - Table Maker

Quick reference for running tests in the table generation system.

## Quick Start

```bash
# Set API key
export ANTHROPIC_API_KEY="your-api-key-here"

# Run integration tests (recommended method)
./run_integration_tests.sh

# Or using pytest directly
pytest -m integration tests/test_integration.py -v
```

## Test Commands Cheat Sheet

### Run Specific Test Scenarios

```bash
# Test 1: Full conversation flow
pytest -m integration tests/test_integration.py::test_full_conversation_flow -v -s

# Test 2: Row expansion
pytest -m integration tests/test_integration.py::test_row_expansion -v -s

# Test 3: CSV generation
pytest -m integration tests/test_integration.py::test_csv_generation -v -s

# Test 4: Config generation
pytest -m integration tests/test_integration.py::test_config_generation -v -s

# Test 5: Save/load conversation
pytest -m integration tests/test_integration.py::test_save_load_conversation -v -s

# Test 6: Error handling
pytest -m integration tests/test_integration.py::test_error_handling -v -s

# Test 7: Iterative row expansion
pytest -m integration tests/test_integration.py::test_iterative_row_expansion -v -s
```

### Test Organization

```bash
# All integration tests
pytest -m integration -v

# All unit tests (no API calls)
pytest -m "not integration" -v

# Specific test file
pytest tests/test_integration.py -v

# With detailed output
pytest tests/test_integration.py -v -s

# Stop on first failure
pytest tests/test_integration.py -x

# Run last failed tests
pytest --lf

# Run tests matching pattern
pytest -k "conversation" -v
```

## What Each Test Does

### Test 1: Full Conversation Flow
**Purpose:** Validate complete multi-turn conversation workflow

**Steps:**
1. Start conversation with research description
2. First refinement: Add new columns
3. Second refinement: Set importance levels
4. Finalize table structure
5. Save conversation to file

**API Calls:** 3 (one per conversation turn)

**Duration:** ~2-3 minutes

### Test 2: Row Expansion
**Purpose:** Test AI-powered row generation

**Steps:**
1. Create simple table (3 rows)
2. Expand with specific criteria (5 new rows)
3. Verify row structure
4. Merge and deduplicate rows

**API Calls:** 2 (initial + expansion)

**Duration:** ~1-2 minutes

### Test 3: CSV Generation
**Purpose:** Validate CSV file operations

**Steps:**
1. Create table structure
2. Generate CSV with metadata
3. Read and verify CSV
4. Append new rows
5. Validate CSV structure

**API Calls:** 1 (table creation)

**Duration:** ~1 minute

### Test 4: Config Generation
**Purpose:** Generate AI validation configs from tables

**Steps:**
1. Create research table with importance levels
2. Generate validation config
3. Verify config structure (search groups, validation targets)
4. Export to JSON file

**API Calls:** 1 (table creation)

**Duration:** ~1 minute

### Test 5: Save and Load Conversation
**Purpose:** Test conversation persistence

**Steps:**
1. Create conversation
2. Save to JSON file
3. Load into new handler
4. Verify state preservation
5. Continue conversation after load

**API Calls:** 2 (initial + continue after load)

**Duration:** ~1-2 minutes

### Test 6: Error Handling
**Purpose:** Validate error handling in various scenarios

**Steps:**
1. Test uninitialized conversation operations
2. Test invalid CSV operations
3. Test schema validation failures

**API Calls:** 0 (error scenarios only)

**Duration:** <1 minute

### Test 7: Iterative Row Expansion
**Purpose:** Test batch row generation for large datasets

**Steps:**
1. Create simple table
2. Expand rows iteratively (3 batches of 5 rows)
3. Verify all batches succeed

**API Calls:** 4 (1 initial + 3 batches)

**Duration:** ~3-4 minutes

## Expected Results

### Success Indicators

All tests should show:
- ✓ Green PASSED status
- ✓ [SUCCESS] markers in logs
- ✓ No error messages
- ✓ Proper cleanup of temp files

### Sample Output

```
tests/test_integration.py::test_full_conversation_flow PASSED
tests/test_integration.py::test_row_expansion PASSED
tests/test_integration.py::test_csv_generation PASSED
tests/test_integration.py::test_config_generation PASSED
tests/test_integration.py::test_save_load_conversation PASSED
tests/test_integration.py::test_error_handling PASSED
tests/test_integration.py::test_iterative_row_expansion PASSED

========================================
All tests PASSED
========================================
```

## Troubleshooting

### "ANTHROPIC_API_KEY not set"
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Import errors
```bash
# Ensure you're in table_maker directory
cd table_maker

# Install dependencies
pip install -r requirements.txt
```

### API rate limits
```bash
# Run tests sequentially with delays
pytest -m integration --dist=no -v
```

### Tests timeout
```bash
# Increase timeout (default is 120s per test)
pytest -m integration --timeout=300
```

## Cost Estimates

### API Usage per Test Run

| Test | API Calls | Est. Tokens | Est. Cost |
|------|-----------|-------------|-----------|
| Test 1 | 3 | ~15,000 | $0.15 |
| Test 2 | 2 | ~10,000 | $0.10 |
| Test 3 | 1 | ~5,000 | $0.05 |
| Test 4 | 1 | ~5,000 | $0.05 |
| Test 5 | 2 | ~10,000 | $0.10 |
| Test 6 | 0 | 0 | $0.00 |
| Test 7 | 4 | ~20,000 | $0.20 |
| **Total** | **13** | **~65,000** | **~$0.65** |

*Estimates based on Claude Sonnet 4.5 pricing. Actual costs may vary.*

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          cd table_maker
          pip install -r requirements.txt

      - name: Run integration tests
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          cd table_maker
          pytest -m integration tests/test_integration.py -v
```

## Best Practices

1. **Run before commits**: Ensure all integration tests pass before pushing
2. **Check logs**: Review detailed logs for any warnings
3. **Monitor costs**: Track API usage to avoid unexpected charges
4. **Use test isolation**: Each test is independent and can run alone
5. **Clean environment**: Tests clean up temporary files automatically

## Development Workflow

```bash
# 1. Make code changes
vim src/conversation_handler.py

# 2. Run related test
pytest tests/test_integration.py::test_full_conversation_flow -v -s

# 3. Fix issues and rerun
pytest --lf -v

# 4. Run all integration tests before commit
./run_integration_tests.sh

# 5. Commit if all pass
git add .
git commit -m "Update conversation handler"
```

## Getting Help

- See `tests/README.md` for detailed test documentation
- Check test logs for detailed error messages
- Review test source code in `tests/test_integration.py`
- File issues for reproducible test failures
