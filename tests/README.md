# Testing the Perplexity Validator

This directory contains tests for the AWS Perplexity Validator Lambda function.

## Types of Tests

The test suite includes:

1. **Unit Tests** - Mock AWS services and the Perplexity API to test the code logic
2. **Integration Tests** - Use real AWS services and Perplexity API calls to test end-to-end functionality

## Setup for Testing

### Prerequisites

- Python 3.8 or higher
- Required packages installed (see requirements.txt in the root directory)
- For integration tests:
  - AWS credentials with S3 access configured
  - Perplexity API key
  - An S3 bucket for testing

### Environment Setup

For integration tests, create a `.env` file in the project root with:

```
PERPLEXITY_API_KEY=your_api_key_here
TEST_BUCKET_NAME=your-test-bucket
```

## Running Tests

### Run All Unit Tests

```bash
pytest
```

### Run Integration Tests

```bash
# Run all integration tests
pytest -m integration

# Run a specific integration test
pytest tests/test_lambda_integration.py::test_lambda_handler_integration
```

### Run a Single Test File

```bash
pytest tests/test_lambda.py
```

### Run Integration Tests Directly (without pytest)

```bash
python -m tests.test_lambda_integration
```

## What the Tests Verify

### Unit Tests

- Validation logic
- Caching behavior
- Error handling
- JSON serialization

### Integration Tests

- End-to-end validation with real Perplexity API
- S3 caching functionality
- Next check date calculation
- Error handling with real services

## Test Output

Successful tests will show:

```
====================================== test session starts =======================================
...
collected 7 items                                                                                 

tests/test_lambda.py::test_lambda_handler_success PASSED                                    [ 14%]
tests/test_lambda.py::test_lambda_handler_cache_hit PASSED                                  [ 28%]
tests/test_lambda.py::test_lambda_handler_cache_expired PASSED                              [ 42%]
tests/test_lambda.py::test_lambda_handler_error PASSED                                      [ 57%]
tests/test_lambda_integration.py::test_lambda_handler_integration PASSED                    [ 71%]
tests/test_lambda_integration.py::test_lambda_handler_caching_integration PASSED            [ 85%]
tests/test_lambda_integration.py::test_next_check_date_integration PASSED                   [100%]

====================================== 7 passed in 10.23s ====================================== 