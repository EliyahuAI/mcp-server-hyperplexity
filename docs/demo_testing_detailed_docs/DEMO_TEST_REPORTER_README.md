# Demo Test Reporter Module

A comprehensive Python module for generating test execution reports for demo validation testing.

## Overview

The `demo_test_reporter.py` module provides a complete solution for tracking, analyzing, and reporting on demo validation test results. It supports multiple output formats (text, JSON, HTML) and tracks detailed metrics including timing, costs, success rates, and error details.

## Features

- **Multiple Output Formats**: Generate reports in text, JSON, and HTML formats
- **Comprehensive Metrics Tracking**:
  - Demo name and path
  - Preview time and results
  - Full validation time and results
  - Download success/failure status
  - Error details and timestamps
  - Cost estimates (preview and full validation)
  - Session IDs and configuration versions
- **Summary Statistics**:
  - Total/passed/failed/skipped counts
  - Success rates
  - Average times and costs
  - Total execution time
- **Error Tracking**: Detailed error logging with timestamps and context
- **Easy Integration**: Simple API for integration into test automation workflows

## Installation

No external dependencies required! The module uses only Python standard library.

Simply ensure the file is in your Python path:

```bash
cp demo_test_reporter.py /path/to/your/project/
```

## Quick Start

```python
from demo_test_reporter import create_report, add_demo_result, save_report, print_report

# 1. Initialize report
report = create_report(
    email="test@example.com",
    environment="dev",
    test_description="Automated demo validation"
)

# 2. Add test results
add_demo_result(report, "Investment Research", {
    "status": "passed",
    "preview_time": 45.2,
    "full_validation_time": 180.5,
    "download_success": True,
    "preview_cost": 0.15,
    "full_cost": 0.82
})

# 3. Print or save report
print_report(report)
save_report(report, output_dir="./test_results", format="html")
```

## API Reference

### `create_report(email, environment, test_description=None)`

Initialize a new test report.

**Parameters:**
- `email` (str): Test email address used for validation
- `environment` (str): Environment name (dev, staging, prod)
- `test_description` (str, optional): Description of the test run

**Returns:** Report dictionary with initialized structure

**Example:**
```python
report = create_report(
    email="eliyahu@eliyahu.ai",
    environment="dev",
    test_description="End-to-end validation of all demos"
)
```

---

### `add_demo_result(report, demo_name, result_data)`

Add a test result for a demo to the report.

**Parameters:**
- `report` (dict): Report dictionary created by `create_report()`
- `demo_name` (str): Name/title of the demo
- `result_data` (dict): Dictionary containing test results

**Result Data Fields:**
- `status` (str, required): "passed", "failed", or "skipped"
- `demo_path` (str, optional): S3 path or identifier
- `session_id` (str, optional): Session ID for the test
- `config_version` (int, optional): Configuration version used (default: 1)
- `preview_time` (float, optional): Time in seconds for preview
- `preview_results` (dict, optional): Preview validation results
- `preview_cost` (float, optional): Estimated cost for preview
- `full_validation_time` (float, optional): Time in seconds for full validation
- `full_validation_results` (dict, optional): Full validation results
- `full_cost` (float, optional): Actual cost for full validation
- `download_success` (bool, optional): Whether download succeeded
- `download_path` (str, optional): Path to downloaded file
- `error` (str, optional): Error message if failed
- `error_details` (str, optional): Detailed error information

**Example:**
```python
add_demo_result(report, "Investment Research", {
    "status": "passed",
    "demo_path": "demos/investment_research/",
    "session_id": "session_demo_20251010_123456_abc123",
    "preview_time": 42.5,
    "preview_results": {
        "rows_processed": 5,
        "validations_passed": 5
    },
    "preview_cost": 0.14,
    "full_validation_time": 175.2,
    "full_validation_results": {
        "rows_processed": 48,
        "validations_passed": 48
    },
    "full_cost": 0.78,
    "download_success": True,
    "download_path": "/tmp/results.xlsx"
})
```

---

### `generate_summary(report)`

Generate summary statistics from the report.

**Parameters:**
- `report` (dict): Report dictionary

**Returns:** Dictionary containing summary statistics including:
- Total/passed/failed/skipped counts
- Success rate percentage
- Total and average times
- Total and average costs
- Test duration

**Example:**
```python
summary = generate_summary(report)
print(f"Success Rate: {summary['success_rate']:.1f}%")
print(f"Average Cost: ${summary['avg_cost_per_demo']:.3f}")
```

---

### `save_report(report, output_dir, format='text', filename=None)`

Save report to file.

**Parameters:**
- `report` (dict): Report dictionary
- `output_dir` (str): Directory to save report to
- `format` (str): Output format - "text", "json", or "html" (default: "text")
- `filename` (str, optional): Custom filename (auto-generated if not provided)

**Returns:** Path to saved report file (str)

**Raises:** `ValueError` if format is not supported

**Example:**
```python
# Save in multiple formats
text_path = save_report(report, "./test_results", format="text")
json_path = save_report(report, "./test_results", format="json")
html_path = save_report(report, "./test_results", format="html")

# Custom filename
custom_path = save_report(
    report,
    "./reports",
    format="html",
    filename="my_custom_report.html"
)
```

---

### `print_report(report)`

Print report to console in text format.

**Parameters:**
- `report` (dict): Report dictionary

**Example:**
```python
print_report(report)
```

## Output Formats

### Text Format

ASCII-formatted report suitable for console output and log files.

```
======================================================================
                         DEMO TESTING REPORT
======================================================================

Generated:    2025-10-10 10:30:00
Environment:  dev
Test Email:   eliyahu@eliyahu.ai

SUMMARY:
- Total Demos: 10
- Passed: 8 (80.0%)
- Failed: 2
- Total Time: 45.5 minutes

DETAILS:
[1/10] Investment Research - [PASS] (4.2 min)
[2/10] Competitive Intelligence - [PASS] (3.8 min)
...

ERRORS:
Demo: Program Applications
Error: Timeout during full validation
Details: ...
```

### JSON Format

Machine-readable format for programmatic processing and integration.

```json
{
  "metadata": {
    "generated_at": "2025-10-10T10:30:00",
    "test_email": "test@example.com",
    "environment": "dev"
  },
  "demos": [...],
  "summary": {
    "total": 10,
    "passed": 8,
    "failed": 2,
    "total_time": 2730.5,
    "total_cost": 8.45
  },
  "errors": [...]
}
```

### HTML Format

Visually formatted report with styling, suitable for viewing in browsers and sharing with stakeholders.

Features:
- Responsive grid layout
- Color-coded status badges
- Sortable data tables
- Professional styling
- Error highlighting

## Integration Examples

### Basic Integration

```python
from demo_test_reporter import create_report, add_demo_result, save_report

def run_demo_tests():
    # Initialize
    report = create_report(email="test@example.com", environment="ci")

    # Run tests
    for demo_name in get_demo_list():
        result = test_demo(demo_name)
        add_demo_result(report, demo_name, result)

    # Save reports
    save_report(report, "./test_results", format="json")
    save_report(report, "./test_results", format="html")

    return report
```

### CI/CD Integration

```python
import sys
from demo_test_reporter import create_report, add_demo_result, save_report

def ci_test_runner():
    report = create_report(
        email="ci@example.com",
        environment="ci",
        test_description="Automated CI pipeline demo validation"
    )

    failed_demos = []

    for demo in demos:
        try:
            result = validate_demo(demo)
            add_demo_result(report, demo, result)

            if result['status'] == 'failed':
                failed_demos.append(demo)
        except Exception as e:
            add_demo_result(report, demo, {
                'status': 'failed',
                'error': str(e)
            })
            failed_demos.append(demo)

    # Save reports
    save_report(report, "./ci_reports", format="json")
    save_report(report, "./ci_reports", format="html")

    # Exit with error if any tests failed
    if failed_demos:
        print(f"[ERROR] {len(failed_demos)} demos failed")
        sys.exit(1)
    else:
        print(f"[SUCCESS] All demos passed")
        sys.exit(0)
```

### Automated Testing Loop

```python
from demo_test_reporter import create_report, add_demo_result, print_report
import time

def automated_test_suite():
    report = create_report(
        email="automation@example.com",
        environment="dev"
    )

    demos = [
        "investment_research",
        "competitive_intelligence",
        "program_applications"
    ]

    for demo_name in demos:
        print(f"Testing {demo_name}...")
        start_time = time.time()

        try:
            # Run preview
            preview_result = run_preview(demo_name)
            preview_time = time.time() - start_time

            # Run full validation
            validation_start = time.time()
            validation_result = run_full_validation(demo_name)
            validation_time = time.time() - validation_start

            # Add successful result
            add_demo_result(report, demo_name, {
                "status": "passed",
                "preview_time": preview_time,
                "preview_cost": preview_result['cost'],
                "full_validation_time": validation_time,
                "full_cost": validation_result['cost'],
                "download_success": True
            })

        except Exception as e:
            add_demo_result(report, demo_name, {
                "status": "failed",
                "error": str(e),
                "error_details": traceback.format_exc()
            })

    # Display results
    print_report(report)
    return report
```

## Error Handling

The module includes comprehensive error tracking:

```python
# Failed test with error details
add_demo_result(report, "Problem Demo", {
    "status": "failed",
    "error": "Lambda timeout during validation",
    "error_details": "Function exceeded 300s timeout during batch 3 of 5",
    "preview_time": 45.0,
    "preview_cost": 0.15,
    "full_validation_time": 0.0,
    "full_cost": 0.0
})

# Skipped test
add_demo_result(report, "Skipped Demo", {
    "status": "skipped",
    "error": "Missing configuration file"
})
```

## Best Practices

1. **Initialize Report Early**: Create the report at the start of your test suite
2. **Add Results Immediately**: Call `add_demo_result()` as soon as each test completes
3. **Save Multiple Formats**: Generate both JSON (for automation) and HTML (for humans)
4. **Include Context**: Use descriptive error messages and test descriptions
5. **Track All Metrics**: Include timing and cost data even for failed tests when available
6. **Use Consistent Naming**: Keep demo names consistent across test runs
7. **Archive Reports**: Save reports with timestamps for historical tracking

## File Structure

```
deployment/
├── demo_test_reporter.py              # Main module
├── demo_test_reporter_example.py      # Usage examples
├── DEMO_TEST_REPORTER_README.md       # This documentation
└── test_results/                      # Generated reports
    ├── demo_test_report_dev_20251010_123456.txt
    ├── demo_test_report_dev_20251010_123456.json
    └── demo_test_report_dev_20251010_123456.html
```

## Running Examples

Test the module with the included example:

```bash
cd deployment
python demo_test_reporter.py          # Run built-in test
python demo_test_reporter_example.py  # Run comprehensive example
```

## Troubleshooting

**Issue: Reports not saving**
- Check that the output directory exists or can be created
- Verify write permissions on the output directory

**Issue: HTML report not displaying correctly**
- Ensure the file is opened in a modern browser
- Check for JavaScript blockers or security restrictions

**Issue: Cost/timing metrics showing as 0**
- Verify that you're passing the metrics in the `result_data` dictionary
- Check that the values are floats, not strings

## Contributing

To extend the module:

1. **Add New Metrics**: Extend the `result_data` dictionary structure in `add_demo_result()`
2. **Custom Formats**: Create new format functions like `_generate_custom_report()`
3. **Additional Analysis**: Extend `generate_summary()` with new calculations

## License

This module is part of the Hyperplexity Validator project.

## Support

For questions or issues, contact the development team or refer to the main project documentation.
