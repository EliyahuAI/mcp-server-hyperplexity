# Quick Start Guide - Perplexity Validator

## Overview

The Perplexity Validator is a system that validates data in Excel tables using the Perplexity AI API. It supports both synchronous and asynchronous processing through a unified API Gateway interface.

⚠️ **Email Validation Required**: All users must validate their email address before processing Excel files.

## Architecture

The system uses a simplified architecture:
- **API Gateway** → **Interface Lambda** → **Validator Lambda**
- Synchronous requests are processed immediately
- Asynchronous requests are queued via SQS for background processing
- All results are tracked in DynamoDB and stored in S3

## Quick Test

Use the new test script for comprehensive testing:

```bash
# Run all tests (sync preview, async preview, full validation)
python test_validation.py

# Test only async preview with custom name
python test_validation.py --mode async_preview --name "my_test"

# Use custom files
python test_validation.py --excel "path/to/file.xlsx" --config "path/to/config.json"

# Specify output directory and rows
python test_validation.py --output-dir "my_tests" --max-rows 20 --preview-rows 5
```

## API Endpoints

**Base URL**: `https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod`

### Email Validation Endpoints (Required First)
- **POST** `/validate` with JSON body:
  - `{"action": "requestEmailValidation", "email": "user@company.com"}` - Request validation code
  - `{"action": "validateEmailCode", "email": "user@company.com", "code": "123456"}` - Validate email
  - `{"action": "getUserStats", "email": "user@company.com"}` - Get user statistics

### Main Validation Endpoint
- **POST** `/validate`
- Query parameters:
  - `preview_first_row=true` - Preview mode
  - `async=true` - Asynchronous processing
  - `max_rows=N` - Limit rows to process
  - `batch_size=N` - Rows per batch

### Status Check Endpoint
- **GET** `/status/{sessionId}`
- Query parameters:
  - `preview=true` - Check preview status

## Configuration File Format

Create a JSON configuration file that specifies which columns to validate:

```json
{
  "validation_targets": [
    {
      "column": "Product Name",
      "description": "Official name of the product",
      "importance": "ID",
      "format": "String",
      "notes": "Use official nomenclature"
    },
    {
      "column": "Development Stage",
      "description": "Current stage of development",
      "importance": "CRITICAL",
      "format": "String",
      "examples": ["Phase 1", "Phase 2", "Phase 3", "Approved"]
    }
  ]
}
```

**Importance Levels**:
- `ID`: Primary key fields (used to uniquely identify rows)
- `CRITICAL`: Must be validated
- `HIGH`: Important but not critical
- `MEDIUM`/`LOW`: Lower priority fields

## Output

The validator produces:

### 1. Enhanced Excel File (in ZIP)
- **Results Sheet**: Original data with color-coded validation results
  - 🟢 Green (HIGH confidence)
  - 🟡 Yellow (MEDIUM confidence)
  - 🔴 Red (LOW confidence)
- **Details Sheet**: Detailed validation results with quotes and sources

### 2. DynamoDB Tracking
- Session status and progress
- Cost and token metrics
- Processing times
- Email delivery status

### 3. Test Output (when using test_validation.py)
- Timestamped directories: `YYYYMMDD_HHMMSS_[name]`
- Complete API responses
- DynamoDB records
- Preview tables
- Summary reports

## Validation Modes

### 1. Synchronous Preview
- Immediate response with results
- Best for testing with 1-3 rows
- Times out after 29 seconds

### 2. Asynchronous Preview
- Returns session ID for polling
- Better for larger previews
- Results stored in S3

### 3. Full Validation
- Always asynchronous
- Sends results via email
- Handles large datasets

## Requirements

- Python 3.8+
- AWS credentials configured (for direct AWS access)
- Required packages: `requests`, `boto3`

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd perplexityValidator

# Install dependencies
pip install requests boto3
```

## Examples

### Example 1: Test Everything

```bash
# Run comprehensive test with default Congress Master List
python test_validation.py --name "congress_test"
```

### Example 2: Quick Preview

```bash
# Test sync preview with 3 rows
python test_validation.py --mode sync_preview --preview-rows 3
```

### Example 3: Custom Files

```bash
# Validate your own data
python test_validation.py \
  --excel "data/my_file.xlsx" \
  --config "data/my_config.json" \
  --mode full_validation \
  --max-rows 50
```

### Example 4: Direct API Usage

```python
import requests

base_url = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod"
email = "user@example.com"

# Step 1: Validate email
# Request validation code
response = requests.post(f"{base_url}/validate", json={
    "action": "requestEmailValidation",
    "email": email
})
print("Validation code sent:", response.json())

# Enter code from email
code = input("Enter 6-digit code from email: ")
response = requests.post(f"{base_url}/validate", json={
    "action": "validateEmailCode",
    "email": email, 
    "code": code
})
print("Validation result:", response.json())

# Step 2: Process Excel file
files = {
    'excel_file': open('data.xlsx', 'rb'),
    'config_file': open('config.json', 'rb')
}
data = {'email': email}

response = requests.post(
    f'{base_url}/validate?preview_first_row=true',
    files=files,
    data=data
)
print("Processing result:", response.json())
```

## Deployment (For Administrators)

### Deploy Core Validator Lambda

```bash
cd deployment
python create_package.py --deploy --force-rebuild
```

### Deploy Interface Lambda with API Gateway

```bash
python create_interface_package.py --deploy --force-rebuild
```

This creates:
- Interface Lambda function with SQS event source mappings
- API Gateway with `/validate` and `/status` endpoints
- DynamoDB tracking integration

### Test Deployment

```bash
# Test with included event
python create_package.py --test-only --test-event ratio_competitive_intelligence_test.json

# Or use the test script
cd ..
python test_validation.py --mode sync_preview
```

## Troubleshooting

1. **Network Issues**: The test script includes connectivity checks
2. **504 Gateway Timeout**: Use async mode or reduce row count
3. **Missing Results**: Check DynamoDB for session status
4. **Preview Not Found**: May be 1-second timestamp difference (fixed in latest version)

## Support

For issues:
- Check test output in `test_results/` directories
- Review CloudWatch logs for Lambda functions
- Verify network connectivity with built-in checks
- Ensure config file columns match Excel headers