# Integration Tests - Quick Start Guide

## Setup (One Time)

```bash
# 1. Set API key
export ANTHROPIC_API_KEY="your-anthropic-api-key-here"

# 2. (Optional) For Lambda tests - set AWS credentials
export AWS_ACCESS_KEY_ID="your-aws-key"
export AWS_SECRET_ACCESS_KEY="your-aws-secret"
export AWS_DEFAULT_REGION="us-east-1"
```

---

## Running Tests

### Local Integration Tests (Recommended to Start)

```bash
# Run all local integration tests
pytest table_maker/tests/test_integration_row_discovery.py -v -m integration

# Run specific test
pytest table_maker/tests/test_integration_row_discovery.py::test_simple_request_full_pipeline -v

# Show detailed output
pytest table_maker/tests/test_integration_row_discovery.py -v -s -m integration
```

**Time:** ~10-15 minutes
**Requirements:** ANTHROPIC_API_KEY only

---

### Performance Benchmarks

```bash
# Run all benchmarks
pytest table_maker/tests/test_performance_benchmarks.py -v -m integration -s

# Run specific benchmark
pytest table_maker/tests/test_performance_benchmarks.py::test_full_pipeline_performance -v -s

# Generate report to file
pytest table_maker/tests/test_performance_benchmarks.py -v -m integration -s > perf_report.txt
```

**Time:** ~60-90 minutes
**Requirements:** ANTHROPIC_API_KEY only

---

### Lambda Integration Tests

```bash
# Run all Lambda tests (requires AWS)
pytest tests/test_table_maker_independent_rows.py -v -m integration

# Run specific test
pytest tests/test_table_maker_independent_rows.py::test_execution_orchestrator_full_pipeline -v

# Skip slow tests
pytest tests/test_table_maker_independent_rows.py -v -m "integration and not slow"
```

**Time:** ~30-60 minutes
**Requirements:** ANTHROPIC_API_KEY + AWS credentials

---

## Common Commands

```bash
# Skip all integration tests (unit tests only)
pytest -v -m "not integration"

# Run with detailed logging
pytest -v -s --log-cli-level=INFO

# Stop on first failure
pytest -x -v

# Run tests in parallel (faster)
pytest -n auto -v

# Generate HTML coverage report
pytest --cov=table_maker --cov-report=html
open htmlcov/index.html
```

---

## Test Categories

| Test File | Purpose | Time | Requirements |
|-----------|---------|------|--------------|
| test_integration_row_discovery.py | Local pipeline | 10-15 min | API key |
| test_performance_benchmarks.py | Performance | 60-90 min | API key |
| test_table_maker_independent_rows.py | Lambda integration | 30-60 min | API key + AWS |

---

## Expected Results

### Success
```
[============] TEST: Simple Request Full Pipeline [============]
[STEP 1] Column Definition
[SUCCESS] Columns defined: 4 columns
[TIMING] Step 1 took 18.3s (target: <30s)
...
[RESULT] Simple request test PASSED
[========================================================]

collected 6 items

test_integration_row_discovery.py::test_simple_request_full_pipeline PASSED
test_integration_row_discovery.py::test_complex_request_parallel_streams PASSED
...
==================== 6 passed in 892.45s ====================
```

### Failure
```
FAILED test_integration_row_discovery.py::test_simple_request_full_pipeline
AssertionError: Column definition failed: timeout
```

---

## Troubleshooting

**API Key Error:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**AWS Credentials Error:**
```bash
aws configure
# OR
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
```

**Test Timeout:**
```bash
pytest --timeout=600  # 10 minutes
```

**Import Errors:**
```bash
pip install -r requirements.txt
```

---

## Next Steps

1. Start with local integration tests
2. Review test output
3. Run performance benchmarks (optional)
4. Run Lambda tests if needed (optional)
5. Read full documentation: `INTEGRATION_TESTS_README.md`

---

**Need Help?** See `INTEGRATION_TESTS_README.md` for complete documentation.
