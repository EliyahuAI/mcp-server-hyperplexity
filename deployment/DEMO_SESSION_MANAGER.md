# Demo Session Manager

A Python module for managing session lifecycle and S3 interactions for demo testing in the Hyperplexity Validator system.

## Features

- **Create Test Sessions**: Generate unique test session IDs
- **Check Session Status**: Monitor session state from S3
- **Verify Results**: Check if result files exist
- **Download Results**: Retrieve Excel outputs and results from S3
- **List Sessions**: View all demo sessions for a user
- **Cleanup**: Remove test data (with dry-run option)

## Installation

The module requires boto3:

```bash
pip install boto3
```

## Usage

### As a Python Module

```python
from demo_session_manager import DemoSessionManager

# Initialize with dev bucket
manager = DemoSessionManager()

# Or specify a different bucket
manager = DemoSessionManager(bucket_name="hyperplexity-storage-dev")
```

### Command-Line Interface

The module includes a full CLI interface:

```bash
# Show help
python demo_session_manager.py --help

# Create a new test session
python demo_session_manager.py create \
    --demo-name product_validation \
    --email test@example.com

# Check session status
python demo_session_manager.py status \
    --email test@example.com \
    --session-id session_demo_20251010_143022_abc12345

# Verify results exist
python demo_session_manager.py verify \
    --email test@example.com \
    --session-id session_demo_20251010_143022_abc12345

# Download results
python demo_session_manager.py download \
    --email test@example.com \
    --session-id session_demo_20251010_143022_abc12345 \
    --output ./results/

# List all demo sessions
python demo_session_manager.py list \
    --email test@example.com

# Clean up session (dry run first!)
python demo_session_manager.py cleanup \
    --email test@example.com \
    --session-id session_demo_20251010_143022_abc12345 \
    --dry-run

# Actually delete (use with caution!)
python demo_session_manager.py cleanup \
    --email test@example.com \
    --session-id session_demo_20251010_143022_abc12345
```

## API Reference

### DemoSessionManager

#### `__init__(bucket_name="hyperplexity-storage-dev", region="us-east-1")`

Initialize the demo session manager.

**Parameters:**
- `bucket_name` (str): S3 bucket name (default: hyperplexity-storage-dev)
- `region` (str): AWS region (default: us-east-1)

---

#### `create_test_session(demo_name, email)`

Generate unique test session ID for demo testing.

**Parameters:**
- `demo_name` (str): Name/identifier for the demo (e.g., "product_validation")
- `email` (str): Test user email address

**Returns:**
- `str`: Generated session ID (format: session_demo_YYYYMMDD_HHMMSS_XXXXXXXX)

**Example:**
```python
session_id = manager.create_test_session("product_validation", "test@example.com")
print(session_id)  # session_demo_20251010_143022_abc12345
```

---

#### `check_session_status(email, session_id)`

Check session state from S3 by reading session_info.json.

**Parameters:**
- `email` (str): User email address
- `session_id` (str): Session identifier

**Returns:**
- `dict`: Dictionary containing:
  - `exists` (bool): Whether the session exists
  - `session_info` (dict): Full session info data (if exists)
  - `current_version` (int): Latest config version
  - `has_preview` (bool): Whether preview results exist
  - `has_validation` (bool): Whether validation results exist
  - `preview_status` (str): Status of preview operation
  - `validation_status` (str): Status of validation operation
  - `error` (str): Error message (if any)

**Example:**
```python
status = manager.check_session_status("test@example.com", session_id)
if status['exists']:
    print(f"Current version: {status['current_version']}")
    print(f"Has validation: {status['has_validation']}")
```

---

#### `verify_results_exist(email, session_id, version=None)`

Check if results file exists in S3 for the specified session.

**Parameters:**
- `email` (str): User email address
- `session_id` (str): Session identifier
- `version` (int, optional): Config version to check (None = latest version)

**Returns:**
- `dict`: Dictionary containing:
  - `exists` (bool): Whether results exist
  - `validation_results` (str): Path to validation results (if exists)
  - `enhanced_excel` (str): Path to enhanced Excel file (if exists)
  - `preview_results` (str): Path to preview results (if exists)
  - `version` (int): Version number checked
  - `error` (str): Error message (if any)

**Example:**
```python
result = manager.verify_results_exist("test@example.com", session_id)
if result['exists']:
    print(f"Enhanced Excel: {result['enhanced_excel']}")
```

---

#### `download_results(email, session_id, output_path, version=None)`

Download result Excel file from S3 to local path.

**Parameters:**
- `email` (str): User email address
- `session_id` (str): Session identifier
- `output_path` (str): Local directory or file path to save results
- `version` (int, optional): Config version to download (None = latest version)

**Returns:**
- `bool`: True if download successful, False otherwise

**Example:**
```python
success = manager.download_results(
    "test@example.com",
    session_id,
    "./test_results/output.xlsx"
)
if success:
    print("Results downloaded successfully")
```

**Notes:**
- If `output_path` is a directory, the original filename is preserved
- Progress indicators show download status
- Also downloads `session_info.json` for reference

---

#### `list_all_demo_sessions(email)`

List all demo sessions for a given email.

**Parameters:**
- `email` (str): User email address

**Returns:**
- `list`: List of dictionaries, each containing:
  - `session_id` (str): Session identifier
  - `session_path` (str): S3 path to session
  - `last_modified` (str): Last modification timestamp
  - `file_count` (int): Number of files in session

**Example:**
```python
sessions = manager.list_all_demo_sessions("test@example.com")
for session in sessions:
    print(f"Session: {session['session_id']}")
    print(f"  Files: {session['file_count']}")
```

---

#### `cleanup_session(email, session_id, dry_run=True)`

Clean up test data from S3 (optional - use with caution!).

**Parameters:**
- `email` (str): User email address
- `session_id` (str): Session identifier
- `dry_run` (bool): If True, only list files without deleting (default: True)

**Returns:**
- `dict`: Dictionary containing cleanup summary:
  - `files_found` (int): Number of files found
  - `files_deleted` (int): Number of files deleted (0 if dry_run)
  - `deleted_keys` (list): List of deleted S3 keys (empty if dry_run)
  - `error` (str): Error message (if any)

**Example:**
```python
# First, do a dry run to see what would be deleted
result = manager.cleanup_session("test@example.com", session_id, dry_run=True)
print(f"Would delete {result['files_found']} files")

# If you're sure, actually delete
result = manager.cleanup_session("test@example.com", session_id, dry_run=False)
print(f"Deleted {result['files_deleted']} files")
```

**Warning:** This permanently deletes data from S3. Always run with `dry_run=True` first!

---

## S3 Path Structure

The module follows the standard Hyperplexity S3 path structure:

```
results/{domain}/{email_prefix}/{session_id}/
├── session_info.json              # Session tracking file
├── {filename}_input.xlsx          # Original input file
├── config_v1_ai_generated.json    # Config version 1
├── config_v2_refined.json         # Config version 2
├── v1_results/                    # Version 1 results
│   ├── preview_results.json
│   ├── validation_results.json
│   └── enhanced_validation.xlsx   # Output file
└── v2_results/                    # Version 2 results
    ├── preview_results.json
    ├── validation_results.json
    └── enhanced_validation.xlsx
```

### Session ID Format

Demo sessions use the format: `session_demo_YYYYMMDD_HHMMSS_XXXXXXXX`

Example: `session_demo_20251010_143022_abc12345`

### Results Files

The module looks for output files in the versioned results folders (`v{N}_results/`):
- `enhanced_validation.xlsx` - Primary output file
- `*_output.xlsx` or `*_Output.xlsx` - Alternative naming patterns
- `validation_results.json` - Validation results data
- `preview_results.json` - Preview results data

## Environment Variables

The module uses standard AWS credentials from:
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- AWS credentials file (`~/.aws/credentials`)
- IAM role (if running on EC2)

## Examples

See `demo_session_manager_example.py` for comprehensive usage examples:

```bash
python demo_session_manager_example.py
```

## Error Handling

All functions include comprehensive error handling and return informative error messages:

```python
status = manager.check_session_status("test@example.com", "invalid_id")
if not status['exists']:
    print(f"Error: {status.get('error', 'Unknown error')}")
```

## Progress Indicators

Download operations show progress with size information:

```
[INFO] Downloading from S3...
[INFO] File size: 1,234,567 bytes (1.18 MB)
[INFO] Progress: 45.2% (0.53/1.18 MB)
```

## AWS Permissions Required

The following S3 permissions are needed:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::hyperplexity-storage-dev/*",
        "arn:aws:s3:::hyperplexity-storage-dev"
      ]
    }
  ]
}
```

## Best Practices

1. **Always use dry_run first**: Before cleaning up sessions, run with `dry_run=True` to see what will be deleted

2. **Check status before operations**: Verify a session exists before trying to download results

3. **Handle errors gracefully**: All functions return error information in the response dictionary

4. **Use descriptive demo names**: Make it easy to identify test sessions later

5. **Clean up test data**: Remove test sessions when done to avoid clutter

## Troubleshooting

### "Session not found"
- Verify the session ID is correct
- Check that the email matches the session owner
- Ensure you're using the correct bucket

### "Results not found"
- The session may not have completed validation yet
- Check session status first with `check_session_status()`
- Verify the session has a `has_validation: true` status

### "Permission denied"
- Ensure your AWS credentials have the required S3 permissions
- Check that you're using the correct bucket name
- Verify the IAM role/user has access to the bucket

### "Download fails"
- Check available disk space
- Ensure output directory exists or can be created
- Verify S3 object actually exists with `verify_results_exist()`

## Integration with Testing

The module is designed to integrate with automated testing workflows:

```python
# In your test suite
def test_validation_workflow():
    manager = DemoSessionManager()

    # Create test session
    session_id = manager.create_test_session("test_workflow", "test@example.com")

    # ... trigger validation through your API ...

    # Wait for completion and verify results
    result = manager.verify_results_exist("test@example.com", session_id)
    assert result['exists'], "Results should exist after validation"

    # Download and validate output
    manager.download_results("test@example.com", session_id, "./test_output/")

    # Cleanup
    manager.cleanup_session("test@example.com", session_id, dry_run=False)
```

## Future Enhancements

Potential improvements for future versions:

- [ ] Async operations for faster bulk downloads
- [ ] Support for downloading specific versions
- [ ] Batch operations for multiple sessions
- [ ] Result comparison utilities
- [ ] Integration with test frameworks (pytest, unittest)
- [ ] Webhook/callback support for session events
- [ ] Session metadata export (CSV, JSON)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the example script for usage patterns
3. Consult the infrastructure documentation in `docs/INFRASTRUCTURE_GUIDE.md`

## License

This module is part of the Hyperplexity Validator system.
