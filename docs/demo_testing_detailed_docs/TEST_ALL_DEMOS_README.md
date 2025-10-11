# Demo Test Orchestrator - Complete Testing Suite

This document describes the end-to-end testing system for validating all demo configurations in the Hyperplexity Validator.

## Overview

The test orchestrator provides automated testing of all demos stored in the `demos/` directory. It performs complete validation workflows including:

1. Demo discovery and validation
2. Loading demos from S3 via the demo management API
3. Running preview validation (first 5 rows)
4. Running full validation (all rows)
5. Downloading and verifying result files
6. Generating comprehensive test reports

## Architecture

The system consists of four main components:

### 1. `test_all_demos.py` - Main Orchestrator

The primary entry point that coordinates the entire testing workflow. It:
- Discovers demos in the local `demos/` directory
- Validates demo folder structure
- Executes preview and full validation for each demo
- Generates comprehensive reports in multiple formats

### 2. `demo_api_client.py` - API Client

Handles all HTTP interactions with the dev environment API Gateway. Provides methods for:
- **`call_demo_api(demo_name, email)`** - Load a demo from S3
- **`trigger_preview(session_id, ...)`** - Start preview validation
- **`trigger_full_validation(session_id, ...)`** - Start full validation
- **`check_status(session_id, is_preview)`** - Poll validation status
- **`list_demos()`** - List all available demos on server

### 3. `demo_session_manager.py` - Session Management

Manages S3 session state and file operations:
- Track session lifecycle
- Verify results exist in S3
- Download results from S3
- Clean up test data

### 4. `demo_test_reporter.py` - Report Generation

Generates comprehensive test reports in three formats:
- **Text** - Human-readable console output
- **JSON** - Machine-readable structured data
- **HTML** - Rich formatted web report

## Prerequisites

### Python Dependencies

```bash
pip install requests openpyxl boto3
```

### AWS Configuration

Ensure AWS credentials are configured for S3 access:

```bash
aws configure
# OR set environment variables:
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
```

### Demo Folder Structure

Each demo folder should contain:

```
demos/
├── 01. Investment Research/
│   ├── InvestmentResearch.xlsx          # Data file
│   ├── InvestmentResearch_config.json   # Configuration
│   ├── description.md                   # Demo description
│   └── Investment_Research_Hyperplexity_Output.xlsx  # (generated)
├── 02. Competitive Intelligence/
│   ├── Competitive_Intelligence.xlsx
│   ├── Competitive_Intelligence_config.json
│   ├── description.md
│   └── Competitive_Intelligence_Hyperplexity_Output.xlsx
...
```

## Usage

### Basic Usage

Run all demos in dev environment:

```bash
cd deployment
python test_all_demos.py
```

### Advanced Options

```bash
# Specify custom demos directory
python test_all_demos.py --demos-dir ../demos

# Use different email
python test_all_demos.py --email test@example.com

# Continue testing even if errors occur
python test_all_demos.py --no-stop-on-error

# Custom output directory
python test_all_demos.py --output-dir ./my_test_results

# Skip preview (only run full validation)
python test_all_demos.py --skip-preview

# Skip validation (only run preview)
python test_all_demos.py --skip-validation
```

### Command Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--demos-dir` | `./demos` | Path to demos directory |
| `--email` | `eliyahu@eliyahu.ai` | Test email address |
| `--environment` | `dev` | Environment (dev, test, staging, prod) |
| `--output-dir` | `./test_results` | Output directory for results |
| `--stop-on-error` | `True` | Stop on first error |
| `--no-stop-on-error` | - | Continue even if errors occur |
| `--skip-preview` | `False` | Skip preview step |
| `--skip-validation` | `False` | Skip validation step |

## Test Workflow

For each demo, the orchestrator performs:

### Step 1: Demo Loading

```python
# Load demo from S3 using demo management API
session_id, demo_info = api_client.call_demo_api(demo_name, email)
```

This creates a new session with demo files copied to user storage.

### Step 2: Preview Validation (Optional)

```python
# Trigger preview on first 5 rows
preview_result = api_client.trigger_preview(
    session_id=session_id,
    preview_max_rows=5,
    wait_for_completion=True
)
```

Preview validation:
- Validates first 5 rows
- Returns cost and time estimates
- Timeout: 5 minutes
- Poll interval: 5 seconds

### Step 3: Full Validation

```python
# Trigger full validation on all rows
validation_result = api_client.trigger_full_validation(
    session_id=session_id,
    wait_for_completion=True
)
```

Full validation:
- Processes all rows
- Returns actual costs and results
- Timeout: 30 minutes
- Poll interval: 5 seconds

### Step 4: Download and Verify

```python
# Download result file
download_url = validation_result['download_url']
response = requests.get(download_url)

# Verify file integrity
wb = openpyxl.load_workbook(output_path)
```

Downloads the Excel result file and verifies:
- File can be opened
- Contains expected sheets
- Has data in first sheet

## Output and Reports

### Directory Structure

```
test_results/
├── test_all_demos_20251010_143022.log           # Detailed log file
├── demo_test_report_dev_20251010_143022.txt     # Text report
├── demo_test_report_dev_20251010_143022.json    # JSON report
└── demo_test_report_dev_20251010_143022.html    # HTML report
```

### Text Report Example

```
======================================================================
                        DEMO TESTING REPORT
======================================================================

Generated:    2025-10-10T14:30:22
Environment:  dev
Test Email:   eliyahu@eliyahu.ai
Description:  Automated end-to-end testing of all demos in ./demos

----------------------------------------------------------------------
SUMMARY
----------------------------------------------------------------------
Total Demos:     10
Passed:          8 (80.0%)
Failed:          2
Skipped:         0

Total Time:      45.2min
  Preview Time:  8.5min
  Validation:    36.7min
Average Time:    4.5min

Total Cost:      $12.45
  Preview Cost:  $1.20
  Validation:    $11.25
Average Cost:    $1.24

----------------------------------------------------------------------
DEMO DETAILS
----------------------------------------------------------------------
[1/10] Investment Research - [PASS]
  Time:     4.2min (Preview: 0.8min, Validation: 3.4min)
  Cost:     $1.15 (Preview: $0.10, Validation: $1.05)
  Download: Success
  Session:  session_demo_20251010_143045_abc123

[2/10] Competitive Intelligence - [PASS]
  Time:     3.9min (Preview: 0.7min, Validation: 3.2min)
  Cost:     $1.08 (Preview: $0.09, Validation: $0.99)
  Download: Success
  Session:  session_demo_20251010_143512_def456

...
```

### JSON Report Structure

```json
{
  "metadata": {
    "generated_at": "2025-10-10T14:30:22",
    "test_email": "eliyahu@eliyahu.ai",
    "environment": "dev",
    "description": "Automated end-to-end testing of all demos",
    "start_time": "2025-10-10T14:10:00"
  },
  "demos": [
    {
      "demo_name": "Investment Research",
      "status": "passed",
      "session_id": "session_demo_20251010_143045_abc123",
      "preview": {
        "time_seconds": 48.2,
        "cost": 0.10,
        "results": {...}
      },
      "full_validation": {
        "time_seconds": 204.5,
        "cost": 1.05,
        "results": {...}
      },
      "download": {
        "success": true,
        "file_path": "/path/to/output.xlsx"
      }
    }
  ],
  "summary": {
    "total": 10,
    "passed": 8,
    "failed": 2,
    "total_time": 2712.0,
    "total_cost": 12.45,
    "success_rate": 80.0
  },
  "errors": [...]
}
```

### HTML Report

Opens in browser with:
- Summary cards with metrics
- Detailed results table
- Error highlighting
- Responsive design

## Error Handling

### Demo Loading Errors

If a demo fails to load from S3:

```
[ERROR] Demo test failed: Demo selection failed: Demo not found in S3
```

**Solution**: Ensure demo has been uploaded to S3 using `upload_demos.py`

### Validation Timeout

If validation exceeds timeout:

```
[ERROR] Validation error: Polling timeout after 1800s. Last status: PROCESSING
```

**Solutions**:
- Increase timeout in code
- Check for backend issues
- Reduce demo size

### Download Failures

If download URL is invalid:

```
[ERROR] Download/verification error: No download URL in validation result
```

**Solutions**:
- Check validation completed successfully
- Verify S3 permissions
- Check download URL expiration

## Troubleshooting

### Common Issues

#### 1. ModuleNotFoundError

```
ModuleNotFoundError: No module named 'demo_api_client'
```

**Solution**: Run from `deployment/` directory:

```bash
cd deployment
python test_all_demos.py
```

#### 2. AWS Credentials Error

```
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```

**Solution**: Configure AWS credentials:

```bash
aws configure
```

#### 3. Demo Not Found on Server

```
[ERROR] Demo selection failed: Demo 'investment_research' not found
```

**Solution**: Check demo name normalization. Names are converted to lowercase with underscores:
- "01. Investment Research" → "01._investment_research"
- Try: "investment_research" or check available demos via `list_demos()`

#### 4. Permission Denied on Windows

```
PermissionError: [Errno 13] Permission denied: './test_results/...'
```

**Solution**: Run as administrator or change output directory to user-writable location

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Demo Tests

on:
  push:
    branches: [main, dev]
  schedule:
    - cron: '0 0 * * *'  # Daily at midnight

jobs:
  test-demos:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install requests openpyxl boto3

      - name: Configure AWS
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        run: |
          aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID
          aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY
          aws configure set default.region us-east-1

      - name: Run demo tests
        run: |
          cd deployment
          python test_all_demos.py --no-stop-on-error

      - name: Upload test reports
        uses: actions/upload-artifact@v2
        with:
          name: test-reports
          path: test_results/

      - name: Publish HTML report
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./test_results
```

## Performance Considerations

### Timeouts

- **Preview**: 5 minutes (300s)
- **Full Validation**: 30 minutes (1800s)

### Polling Intervals

- **Preview**: 5 seconds
- **Full Validation**: 5 seconds

### Parallelization

Currently, demos are tested sequentially. Future enhancement could add:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(test_demo, demo) for demo in demos]
```

**Note**: Be cautious with parallelization to avoid:
- API rate limits
- Resource exhaustion
- Cost overruns

## API Reference

### DemoAPIClient Methods

#### `call_demo_api(demo_name, email)`

Load a demo from S3 storage.

**Parameters:**
- `demo_name` (str): Demo name/identifier
- `email` (str): User email address

**Returns:**
- `session_id` (str): Session ID for subsequent operations
- `demo_info` (dict): Demo metadata

#### `trigger_preview(session_id, email, preview_max_rows, wait_for_completion)`

Trigger preview validation.

**Parameters:**
- `session_id` (str): Session ID from demo loading
- `email` (str): User email
- `preview_max_rows` (int): Rows to preview (default: 3)
- `wait_for_completion` (bool): Poll until complete (default: True)

**Returns:**
- `preview_data` (dict): Preview results including cost estimates

#### `trigger_full_validation(session_id, email, max_rows, wait_for_completion)`

Trigger full validation.

**Parameters:**
- `session_id` (str): Session ID
- `email` (str): User email
- `max_rows` (int, optional): Max rows to process
- `wait_for_completion` (bool): Poll until complete (default: True)

**Returns:**
- `validation_result` (dict): Full results including download URL

## Future Enhancements

### Planned Features

1. **Parallel Execution** - Run multiple demos concurrently
2. **Selective Testing** - Test only specific demos by name/tag
3. **Regression Detection** - Compare results with baseline
4. **Performance Metrics** - Track timing trends over time
5. **Cost Tracking** - Budget alerts and cost optimization
6. **Slack/Email Notifications** - Alert on test failures
7. **Result Comparison** - Diff output files between runs

### Configuration File

Future support for `test_config.yaml`:

```yaml
test_orchestrator:
  environment: dev
  email: eliyahu@eliyahu.ai
  stop_on_error: true
  parallel_workers: 3

  timeouts:
    preview: 300
    validation: 1800

  filters:
    include_tags: [regression, smoke]
    exclude_demos: [large_dataset_demo]

  notifications:
    slack_webhook: https://hooks.slack.com/...
    email_on_failure: team@example.com

  baselines:
    enabled: true
    baseline_dir: ./baselines
    fail_on_regression: true
```

## Support

For issues or questions:

1. Check CloudWatch logs for Lambda errors
2. Review S3 bucket for session data
3. Examine DynamoDB tables for session state
4. Contact: eliyahu@eliyahu.ai

## License

Internal use only - Hyperplexity Validator Testing Suite
