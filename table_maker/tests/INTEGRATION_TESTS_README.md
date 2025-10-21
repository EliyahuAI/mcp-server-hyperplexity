# Integration Tests for Independent Row Discovery System

## Overview

This directory contains comprehensive integration tests for the Independent Row Discovery system. The tests validate the complete pipeline from conversation approval to validated table generation.

## Test Files

### 1. `test_integration_row_discovery.py`
**Local Pipeline Integration Tests**

Tests the complete local pipeline WITHOUT Lambda integration:
- Column definition from conversation context
- Row discovery with parallel streams
- Deduplication and consolidation
- Full end-to-end flow

**Test Scenarios:**
- Simple request (1-2 subdomains)
- Complex request (4-5 subdomains)
- No matches found
- Low match scores (below threshold)
- Duplicate entities across streams
- Full end-to-end pipeline

**Run:**
```bash
# Run all local integration tests
pytest table_maker/tests/test_integration_row_discovery.py -v -m integration

# Run specific test
pytest table_maker/tests/test_integration_row_discovery.py::test_simple_request_full_pipeline -v

# Skip integration tests (run only unit tests)
pytest table_maker/tests/test_integration_row_discovery.py -v -m "not integration"
```

---

### 2. `test_table_maker_independent_rows.py`
**Lambda Integration Tests**

Tests the Lambda-integrated version with full AWS infrastructure:
- Conversation → Interview → trigger_execution
- Execution orchestrator coordination
- S3 state persistence
- WebSocket message flow
- Runs database tracking
- Complete table generation

**Test Scenarios:**
- Conversation to execution trigger
- Full execution orchestrator pipeline (4 steps)
- S3 state persistence
- WebSocket message flow (mocked)
- Execution failure at each step

**Requirements:**
- AWS credentials configured
- Anthropic API key in environment
- Access to dev DynamoDB tables
- Access to dev S3 bucket

**Run:**
```bash
# Run all Lambda integration tests
pytest tests/test_table_maker_independent_rows.py -v -m integration

# Run specific test
pytest tests/test_table_maker_independent_rows.py::test_execution_orchestrator_full_pipeline -v

# Skip in CI/CD
pytest -m "not integration"
```

---

### 3. `test_performance_benchmarks.py`
**Performance Benchmarks**

Measures and verifies performance targets:
- Column definition: <30s
- Row discovery (single stream): <60s
- Row discovery (parallel 3-5 streams): <120s
- Full pipeline: <240s (4 minutes)

**Benchmarks:**
- Column definition performance (simple, medium, complex)
- Single stream row discovery
- Parallel streams row discovery (3-5 streams)
- Full pipeline performance
- Scalability test (5, 10, 15, 20 rows)

**Run:**
```bash
# Run all performance benchmarks
pytest table_maker/tests/test_performance_benchmarks.py -v -m integration -s

# Generate performance report
pytest table_maker/tests/test_performance_benchmarks.py -v -m integration --tb=short > performance_report.txt

# Run specific benchmark
pytest table_maker/tests/test_performance_benchmarks.py::test_full_pipeline_performance -v
```

---

## Test Coverage

### Component Coverage

| Component | Unit Tests | Integration Tests | Performance Tests |
|-----------|-----------|-------------------|-------------------|
| Column Definition Handler | [X] | [X] | [X] |
| Subdomain Analyzer | [X] | [X] | - |
| Row Discovery Stream | [X] | [X] | [X] |
| Row Consolidator | [X] | [X] | - |
| Row Discovery Orchestrator | [X] | [X] | [X] |
| Execution Orchestrator | - | [X] | [X] |
| S3 State Management | - | [X] | - |
| WebSocket Communication | - | [X] | - |
| Runs Database Tracking | - | [X] | - |

### Scenario Coverage

- [X] Simple search (1-2 subdomains)
- [X] Complex search (4-5 subdomains)
- [X] No matches found
- [X] All matches below threshold
- [X] Duplicate handling across streams
- [X] Parallel stream execution
- [X] Single stream execution
- [X] Conversation approval flow
- [X] Execution orchestration (4 steps)
- [X] S3 state transitions
- [X] Error handling at each step
- [X] Performance benchmarking

---

## Setup Instructions

### Prerequisites

1. **Python Environment**
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Environment Variables**
   ```bash
   # Required for all integration tests
   export ANTHROPIC_API_KEY="your-api-key-here"

   # Required for Lambda integration tests only
   export AWS_ACCESS_KEY_ID="your-access-key"
   export AWS_SECRET_ACCESS_KEY="your-secret-key"
   export AWS_DEFAULT_REGION="us-east-1"
   ```

3. **AWS Setup (Lambda tests only)**
   - Configure AWS CLI: `aws configure`
   - Ensure access to dev DynamoDB tables
   - Ensure access to dev S3 bucket
   - (Optional) WebSocket infrastructure for real-time updates

### Running Tests

**Quick Start:**
```bash
# Run all unit tests (no API calls, fast)
pytest table_maker/tests/ -v -m "not integration"

# Run all integration tests (requires API key)
pytest table_maker/tests/ -v -m integration

# Run only local integration tests (no AWS required)
pytest table_maker/tests/test_integration_row_discovery.py -v -m integration

# Run only Lambda integration tests (requires AWS)
pytest tests/test_table_maker_independent_rows.py -v -m integration

# Run performance benchmarks
pytest table_maker/tests/test_performance_benchmarks.py -v -m integration
```

**Common Options:**
```bash
# Verbose output with test details
pytest -v -s

# Stop on first failure
pytest -x

# Run specific test
pytest table_maker/tests/test_integration_row_discovery.py::test_simple_request_full_pipeline -v

# Show print statements
pytest -s

# Generate coverage report
pytest --cov=table_maker --cov-report=html
```

---

## Performance Benchmarks

### Target Metrics

| Component | Target | Acceptable | Unacceptable |
|-----------|--------|------------|--------------|
| Column Definition | <30s | <45s | >60s |
| Row Discovery (1 stream) | <60s | <90s | >120s |
| Row Discovery (3-5 streams) | <120s | <180s | >240s |
| Full Pipeline | <240s | <300s | >360s |
| Per-row Discovery | <6s | <10s | >15s |

### Actual Performance (Example Results)

```
Column Definition Performance:
  [PASS] Simple (2-3 columns): 18.3s (target: 25.0s)
  [PASS] Medium (5-7 columns): 24.7s (target: 30.0s)
  [PASS] Complex (8+ columns): 31.2s (target: 35.0s)

Single Stream Discovery:
  [PASS] 5 rows, 1 stream: 47.8s (target: 60.0s)

Parallel Streams Discovery:
  [PASS] 3 streams, 15 rows: 82.4s (target: 100.0s)
  [PASS] 5 streams, 20 rows: 98.6s (target: 120.0s)

Full Pipeline:
  [PASS] Simple pipeline (5 rows): 72.1s (target: 90.0s)
  [PASS] Standard pipeline (15 rows): 156.3s (target: 180.0s)
  [PASS] Complex pipeline (20 rows): 203.7s (target: 240.0s)

Scalability:
  5 rows: 45.2s (9.0s per row)
  10 rows: 73.8s (7.4s per row)
  15 rows: 98.1s (6.5s per row)
  20 rows: 118.4s (5.9s per row)
  Scaling factor: 0.66x [EXCELLENT] Sub-linear scaling
```

**Note:** Actual results vary based on:
- API response times
- Search complexity
- Number of subdomains identified
- Web search results quality

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on:
  pull_request:
    branches: [ main, develop ]
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest -v -m "not integration"

  local-integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest table_maker/tests/test_integration_row_discovery.py -v -m integration
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

  lambda-integration-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule'  # Only on scheduled runs
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/test_table_maker_independent_rows.py -v -m integration
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: us-east-1

  performance-benchmarks:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule'  # Only on scheduled runs
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest table_maker/tests/test_performance_benchmarks.py -v -m integration
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - uses: actions/upload-artifact@v3
        with:
          name: performance-report
          path: performance_report.json
```

### Best Practices

1. **Unit Tests:** Run on every commit/PR
   - Fast (<5 minutes)
   - No external dependencies
   - High coverage

2. **Local Integration Tests:** Run on PR and daily
   - Moderate speed (~10-20 minutes)
   - Requires API key only
   - Tests real API behavior

3. **Lambda Integration Tests:** Run daily or weekly
   - Slower (~30-60 minutes)
   - Requires AWS infrastructure
   - Tests full system integration

4. **Performance Benchmarks:** Run weekly or on-demand
   - Very slow (~60-120 minutes)
   - Requires API key
   - Generates performance reports
   - Track performance trends over time

---

## Troubleshooting

### Common Issues

**1. API Key Not Found**
```
ERROR: ANTHROPIC_API_KEY not set in environment
```
**Solution:** Set the environment variable:
```bash
export ANTHROPIC_API_KEY="your-key-here"
```

**2. AWS Credentials Not Configured**
```
ERROR: AWS credentials not configured
```
**Solution:** Configure AWS CLI or set environment variables:
```bash
aws configure
# OR
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
```

**3. S3 Bucket Access Denied**
```
ERROR: Access denied to S3 bucket
```
**Solution:** Ensure your AWS credentials have S3 access and the bucket exists.

**4. Tests Timing Out**
```
ERROR: Test exceeded maximum timeout
```
**Solution:** Some integration tests can take a while. Increase pytest timeout:
```bash
pytest --timeout=600  # 10 minutes
```

**5. Performance Tests Failing**
```
FAIL: Pipeline too slow: 245.3s > 240s target
```
**Solution:** Performance can vary. Targets are guidelines. Investigate if consistently failing:
- Check API response times
- Check network latency
- Review search complexity
- Consider infrastructure upgrades

### Debugging Tips

**1. Enable Detailed Logging**
```bash
pytest -v -s --log-cli-level=DEBUG
```

**2. Run Single Test in Isolation**
```bash
pytest table_maker/tests/test_integration_row_discovery.py::test_simple_request_full_pipeline -v -s
```

**3. Skip Slow Tests**
```bash
pytest -v -m "integration and not slow"
```

**4. Generate HTML Coverage Report**
```bash
pytest --cov=table_maker --cov-report=html
open htmlcov/index.html
```

**5. Profile Performance**
```bash
pytest --profile
```

---

## Test Output Examples

### Successful Test Run
```
[============] TEST: Simple Request Full Pipeline (1-2 Subdomains) [============]

[STEP 1] Column Definition
[SUCCESS] Columns defined: 4 columns
[TIMING] Step 1 took 18.3s (target: <30s)

[STEP 2] Row Discovery with Subdomain Analysis
[SUCCESS] Row discovery complete
  Subdomains: 2
  Parallel streams: 2
  Candidates found: 12
  Duplicates removed: 2
  Final rows: 8
[TIMING] Step 2 took 54.2s (target: <60s for single stream)

[STEP 3] Verifying Row Quality
  Row 1: Anthropic (score: 0.95)
  Row 2: OpenAI (score: 0.92)
  Row 3: DeepMind (score: 0.89)

[TIMING] Total pipeline time: 72.5s (target: <90s for simple request)

[RESULT] Simple request test PASSED
[============================================================================]
```

### Failed Test Run
```
[============] TEST: Execution Orchestrator Full Pipeline [==================]

[EXECUTE] Running full execution pipeline

[VERIFY] Checking execution result
AssertionError: Execution failed: Column definition timeout at step 1

[RESULT] Execution orchestrator test FAILED
[============================================================================]

FAILED tests/test_table_maker_independent_rows.py::test_execution_orchestrator_full_pipeline
```

---

## Contributing

### Adding New Tests

1. **Choose the right file:**
   - Local pipeline tests → `test_integration_row_discovery.py`
   - Lambda tests → `test_table_maker_independent_rows.py`
   - Performance tests → `test_performance_benchmarks.py`

2. **Follow naming conventions:**
   ```python
   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_descriptive_name(fixtures):
       """Clear docstring explaining what this tests."""
   ```

3. **Add appropriate markers:**
   - `@pytest.mark.integration` - Requires API calls
   - `@pytest.mark.slow` - Takes >5 minutes
   - `@pytest.mark.asyncio` - Async test

4. **Include logging:**
   ```python
   logger.info("\n" + "=" * 80)
   logger.info("TEST: Descriptive Name")
   logger.info("=" * 80)
   ```

5. **Update this README** with new test descriptions

### Test Quality Guidelines

- **Clear purpose:** Each test should have a clear, single purpose
- **Isolation:** Tests should not depend on each other
- **Cleanup:** Use fixtures for cleanup
- **Assertions:** Use descriptive assertion messages
- **Logging:** Log key steps and results
- **Performance:** Track timing for benchmarks
- **Documentation:** Document test scenarios

---

## Contact & Support

For questions or issues:
- Review existing test code for examples
- Check troubleshooting section above
- Review logs with `-v -s` flags
- Contact the development team

---

## Appendix: Test Architecture

### Test Pyramid

```
               /\
              /  \  Lambda Integration Tests (5 tests)
             /____\
            /      \  Local Integration Tests (6 tests)
           /________\
          /          \  Unit Tests (50+ tests)
         /__Performance_\  Performance Benchmarks (5 benchmarks)
```

### Test Dependencies

```
Unit Tests (No dependencies)
    ↓
Local Integration Tests (API key only)
    ↓
Performance Benchmarks (API key only)
    ↓
Lambda Integration Tests (API key + AWS)
```

### Test Data Flow

```
1. Conversation Context (fixture)
   ↓
2. Column Definition Handler
   ↓
3. Subdomain Analyzer
   ↓
4. Row Discovery Streams (parallel)
   ↓
5. Row Consolidator
   ↓
6. Final Rows (verified)
```

---

**Last Updated:** 2025-10-20
**Version:** 1.0
**Status:** Complete
