# Demo Test Reporter - Quick Reference

## 5-Minute Start Guide

### Basic Usage

```python
from demo_test_reporter import create_report, add_demo_result, save_report, print_report

# 1. Create report
report = create_report(email="test@example.com", environment="dev")

# 2. Add results
add_demo_result(report, "Demo Name", {
    "status": "passed",           # Required: "passed", "failed", or "skipped"
    "preview_time": 45.0,          # Optional: seconds
    "full_validation_time": 180.0, # Optional: seconds
    "preview_cost": 0.15,          # Optional: dollars
    "full_cost": 0.82,             # Optional: dollars
    "download_success": True       # Optional: boolean
})

# 3. Output
print_report(report)
save_report(report, "./reports", format="html")
```

### Key Functions

| Function | Purpose | Returns |
|----------|---------|---------|
| `create_report(email, environment, description=None)` | Initialize new report | Report dict |
| `add_demo_result(report, demo_name, result_data)` | Add test result | None (modifies report) |
| `generate_summary(report)` | Calculate statistics | Summary dict |
| `save_report(report, output_dir, format='text', filename=None)` | Save to file | File path (str) |
| `print_report(report)` | Print to console | None |

### Result Data Fields

**Required:**
- `status`: "passed", "failed", or "skipped"

**Optional:**
- `demo_path`: S3 path or identifier
- `session_id`: Session ID for tracking
- `config_version`: Config version number
- `preview_time`: Preview duration (seconds)
- `preview_results`: Preview result dict
- `preview_cost`: Preview cost (dollars)
- `full_validation_time`: Validation duration (seconds)
- `full_validation_results`: Validation result dict
- `full_cost`: Validation cost (dollars)
- `download_success`: Download status (boolean)
- `download_path`: Path to downloaded file
- `error`: Error message string
- `error_details`: Detailed error information

### Output Formats

```python
# Text (console-friendly)
save_report(report, "./reports", format="text")

# JSON (machine-readable)
save_report(report, "./reports", format="json")

# HTML (browser-viewable)
save_report(report, "./reports", format="html")
```

### Complete Example

```python
from demo_test_reporter import create_report, add_demo_result, save_report

# Initialize
report = create_report(
    email="eliyahu@eliyahu.ai",
    environment="dev",
    test_description="Nightly demo validation"
)

# Success case
add_demo_result(report, "Investment Research", {
    "status": "passed",
    "demo_path": "demos/investment_research/",
    "session_id": "session_demo_20251010_100001",
    "preview_time": 42.5,
    "preview_cost": 0.14,
    "full_validation_time": 175.2,
    "full_cost": 0.78,
    "download_success": True
})

# Failure case
add_demo_result(report, "Program Applications", {
    "status": "failed",
    "demo_path": "demos/program_applications/",
    "preview_time": 55.3,
    "preview_cost": 0.19,
    "error": "Lambda timeout",
    "error_details": "Exceeded 300s timeout"
})

# Skipped case
add_demo_result(report, "Missing Demo", {
    "status": "skipped",
    "error": "Configuration file not found"
})

# Save reports
save_report(report, "./test_results", format="text")
save_report(report, "./test_results", format="json")
save_report(report, "./test_results", format="html")
```

### Summary Statistics

```python
summary = generate_summary(report)

# Available metrics:
summary['total']                   # Total demos tested
summary['passed']                  # Number passed
summary['failed']                  # Number failed
summary['skipped']                 # Number skipped
summary['success_rate']            # Percentage (0-100)
summary['total_time']              # Total seconds
summary['total_cost']              # Total dollars
summary['avg_time_per_demo']       # Average seconds
summary['avg_cost_per_demo']       # Average dollars
summary['test_duration_seconds']   # Wall clock time
```

### Error Tracking

Errors are automatically extracted and compiled:

```python
for error in report['errors']:
    print(f"Demo: {error['demo_name']}")
    print(f"Error: {error['error']}")
    print(f"Details: {error['error_details']}")
    print(f"Time: {error['timestamp']}")
```

### File Locations

```
deployment/
├── demo_test_reporter.py              # Main module (23KB)
├── demo_test_reporter_example.py      # Examples (7KB)
├── DEMO_TEST_REPORTER_README.md       # Full docs (14KB)
├── DEMO_TEST_REPORTER_QUICK_REFERENCE.md  # This file
└── test_results/
    ├── demo_test_report_dev_20251010_123456.txt
    ├── demo_test_report_dev_20251010_123456.json
    └── demo_test_report_dev_20251010_123456.html
```

### Common Patterns

**Testing Loop:**
```python
report = create_report(email="test@test.com", environment="ci")

for demo in demo_list:
    try:
        result = test_demo(demo)
        add_demo_result(report, demo, result)
    except Exception as e:
        add_demo_result(report, demo, {
            "status": "failed",
            "error": str(e)
        })

save_report(report, "./reports", format="html")
```

**CI/CD Integration:**
```python
import sys

report = create_report(email="ci@example.com", environment="ci")

# Run tests...
# Add results...

# Exit with status code
if report['summary']['failed'] > 0:
    sys.exit(1)  # Fail CI build
else:
    sys.exit(0)  # Pass CI build
```

### Tips

1. Initialize report at start of test suite
2. Add results immediately after each test
3. Save in multiple formats (JSON + HTML)
4. Include timing/cost data when available
5. Provide detailed error messages
6. Use consistent demo names
7. Archive reports with timestamps

### Getting Help

- Full documentation: `DEMO_TEST_REPORTER_README.md`
- Example code: `demo_test_reporter_example.py`
- Test module: `python demo_test_reporter.py`
- Test examples: `python demo_test_reporter_example.py`
