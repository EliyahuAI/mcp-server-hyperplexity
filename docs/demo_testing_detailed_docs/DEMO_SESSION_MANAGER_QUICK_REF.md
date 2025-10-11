# Demo Session Manager - Quick Reference

## Installation

```bash
pip install boto3
```

## CLI Commands (One-Liners)

```bash
# Create session
python demo_session_manager.py create --demo-name TEST_NAME --email EMAIL

# Check status
python demo_session_manager.py status --email EMAIL --session-id SESSION_ID

# Verify results
python demo_session_manager.py verify --email EMAIL --session-id SESSION_ID

# Download results
python demo_session_manager.py download --email EMAIL --session-id SESSION_ID --output PATH

# List sessions
python demo_session_manager.py list --email EMAIL

# Cleanup (dry-run)
python demo_session_manager.py cleanup --email EMAIL --session-id SESSION_ID --dry-run

# Cleanup (actual)
python demo_session_manager.py cleanup --email EMAIL --session-id SESSION_ID
```

## Python API (Quick)

```python
from demo_session_manager import DemoSessionManager

manager = DemoSessionManager()

# Create
session_id = manager.create_test_session("test", "user@example.com")

# Status
status = manager.check_session_status("user@example.com", session_id)

# Verify
result = manager.verify_results_exist("user@example.com", session_id)

# Download
manager.download_results("user@example.com", session_id, "./output/")

# List
sessions = manager.list_all_demo_sessions("user@example.com")

# Cleanup
manager.cleanup_session("user@example.com", session_id, dry_run=False)
```

## Common Workflows

### Basic Test
```bash
# 1. Create
SESSION_ID=$(python demo_session_manager.py create --demo-name test --email test@example.com | grep session_demo | awk '{print $NF}')

# 2. ... run your test with $SESSION_ID ...

# 3. Download
python demo_session_manager.py download --email test@example.com --session-id $SESSION_ID --output ./results/

# 4. Cleanup
python demo_session_manager.py cleanup --email test@example.com --session-id $SESSION_ID
```

### Python Monitoring
```python
import time

def wait_for_results(manager, email, session_id, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        status = manager.check_session_status(email, session_id)
        if status['has_validation'] and status['validation_status'] == 'completed':
            return True
        time.sleep(10)
    return False
```

## Response Formats

### Status Response
```python
{
    'exists': True,
    'current_version': 1,
    'has_preview': True,
    'has_validation': True,
    'preview_status': 'completed',
    'validation_status': 'completed',
    'session_info': {...}
}
```

### Verify Response
```python
{
    'exists': True,
    'version': 1,
    'validation_results': 's3/path/to/validation_results.json',
    'enhanced_excel': 's3/path/to/enhanced_validation.xlsx',
    'preview_results': 's3/path/to/preview_results.json'
}
```

## Session ID Format

```
session_demo_YYYYMMDD_HHMMSS_XXXXXXXX

Example: session_demo_20251010_143022_abc12345
```

## S3 Path Structure

```
results/{domain}/{email_prefix}/{session_id}/
├── session_info.json
├── file_input.xlsx
├── config_v1_ai_generated.json
└── v1_results/
    ├── validation_results.json
    ├── preview_results.json
    └── enhanced_validation.xlsx
```

## Environment Selection

```bash
# Dev (default)
python demo_session_manager.py create --email test@example.com --demo-name test

# Test
python demo_session_manager.py create --bucket hyperplexity-storage-test --email test@example.com --demo-name test

# Prod
python demo_session_manager.py create --bucket hyperplexity-storage --email test@example.com --demo-name test
```

## Error Checking

```python
# Always check exists/success flags
status = manager.check_session_status(email, session_id)
if not status['exists']:
    print(f"Error: {status.get('error')}")

result = manager.verify_results_exist(email, session_id)
if not result['exists']:
    print(f"Error: {result.get('error')}")
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Session not found | Check session ID, verify email matches |
| Results not found | Check session status first |
| Download fails | Verify results exist, check permissions |
| Permission denied | Check AWS credentials, S3 bucket access |

## Documentation

- **Full API:** `DEMO_SESSION_MANAGER.md`
- **Workflows:** `DEMO_TESTING_WORKFLOW.md`
- **Summary:** `DEMO_SESSION_MANAGER_SUMMARY.md`
- **Examples:** `demo_session_manager_example.py`

## Quick Test

```bash
# Create and verify module works
python demo_session_manager.py create --demo-name quick_test --email test@example.com

# Should output:
# [SUCCESS] Generated test session ID: session_demo_YYYYMMDD_HHMMSS_XXXXXXXX
```
