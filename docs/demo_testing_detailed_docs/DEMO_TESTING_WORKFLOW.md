# Demo Testing Workflow

Quick reference guide for using the Demo Session Manager in testing workflows.

## Quick Start

### 1. Create a Test Session

```bash
python demo_session_manager.py create \
    --demo-name my_test \
    --email test@example.com
```

**Output:**
```
[SUCCESS] Generated test session ID: session_demo_20251010_143022_abc12345
```

**Save this session ID** - you'll need it for all subsequent operations.

---

### 2. Run Your Test

Use the generated session ID in your validation workflow:

```bash
# Example: Upload file and trigger validation through API
curl -X POST https://api.example.com/validate \
  -F "file=@test_data.xlsx" \
  -F "session_id=session_demo_20251010_143022_abc12345" \
  -F "email=test@example.com"
```

---

### 3. Check Session Status

Monitor the session progress:

```bash
python demo_session_manager.py status \
    --email test@example.com \
    --session-id session_demo_20251010_143022_abc12345
```

**Output:**
```
[SUCCESS] Session found
[INFO] Current version: 1
[INFO] Preview results: True (status: completed)
[INFO] Validation results: True (status: completed)
```

---

### 4. Verify Results Exist

Before downloading, verify the results are ready:

```bash
python demo_session_manager.py verify \
    --email test@example.com \
    --session-id session_demo_20251010_143022_abc12345
```

**Output:**
```
[SUCCESS] Results found for version 1
[INFO] Validation results: results/.../v1_results/validation_results.json
[INFO] Enhanced Excel: results/.../v1_results/enhanced_validation.xlsx
```

---

### 5. Download Results

Download the output files:

```bash
python demo_session_manager.py download \
    --email test@example.com \
    --session-id session_demo_20251010_143022_abc12345 \
    --output ./test_results/
```

**Output:**
```
[INFO] Downloading from S3...
[INFO] File size: 1,234,567 bytes (1.18 MB)
[INFO] Progress: 100.0% (1.18/1.18 MB)
[SUCCESS] Results downloaded successfully to: ./test_results/enhanced_validation.xlsx
[INFO] Session info downloaded to: ./test_results/session_demo_20251010_143022_abc12345_session_info.json
```

---

### 6. Clean Up (Optional)

Remove test data after you're done:

```bash
# First, dry run to see what would be deleted
python demo_session_manager.py cleanup \
    --email test@example.com \
    --session-id session_demo_20251010_143022_abc12345 \
    --dry-run

# If happy with the list, actually delete
python demo_session_manager.py cleanup \
    --email test@example.com \
    --session-id session_demo_20251010_143022_abc12345
```

---

## Python Integration

### Basic Usage

```python
from demo_session_manager import DemoSessionManager

# Initialize
manager = DemoSessionManager()

# Create session
session_id = manager.create_test_session("my_test", "test@example.com")

# ... run your test ...

# Check status
status = manager.check_session_status("test@example.com", session_id)
print(f"Validation complete: {status['has_validation']}")

# Download results
if status['has_validation']:
    manager.download_results(
        "test@example.com",
        session_id,
        "./test_results/"
    )
```

### With Error Handling

```python
from demo_session_manager import DemoSessionManager

def test_workflow():
    manager = DemoSessionManager()

    # Create session
    session_id = manager.create_test_session("test_workflow", "test@example.com")
    print(f"Created session: {session_id}")

    try:
        # ... trigger validation ...

        # Wait for completion (poll status)
        import time
        max_wait = 300  # 5 minutes
        start_time = time.time()

        while time.time() - start_time < max_wait:
            status = manager.check_session_status("test@example.com", session_id)

            if status['exists'] and status['has_validation']:
                if status['validation_status'] == 'completed':
                    print("Validation completed successfully!")
                    break
                elif status['validation_status'] == 'failed':
                    print("Validation failed!")
                    return False

            time.sleep(10)  # Check every 10 seconds

        # Verify and download
        result = manager.verify_results_exist("test@example.com", session_id)

        if result['exists']:
            success = manager.download_results(
                "test@example.com",
                session_id,
                "./test_results/"
            )
            return success

        return False

    finally:
        # Cleanup (optional)
        manager.cleanup_session("test@example.com", session_id, dry_run=False)

if __name__ == '__main__':
    success = test_workflow()
    print(f"Test {'passed' if success else 'failed'}")
```

### Pytest Integration

```python
import pytest
from demo_session_manager import DemoSessionManager

@pytest.fixture
def session_manager():
    """Provide a session manager instance"""
    return DemoSessionManager()

@pytest.fixture
def test_session(session_manager):
    """Create a test session and clean up after"""
    session_id = session_manager.create_test_session("pytest_test", "test@example.com")
    yield session_id
    # Cleanup after test
    session_manager.cleanup_session("test@example.com", session_id, dry_run=False)

def test_validation_workflow(session_manager, test_session):
    """Test the validation workflow"""

    # ... trigger validation using test_session ...

    # Check results
    result = session_manager.verify_results_exist("test@example.com", test_session)
    assert result['exists'], "Results should exist after validation"

    # Download
    success = session_manager.download_results(
        "test@example.com",
        test_session,
        f"./test_output/{test_session}/"
    )
    assert success, "Download should succeed"
```

---

## Common Workflows

### Testing Different Configurations

```bash
# Test 1: Basic validation
SESSION1=$(python demo_session_manager.py create --demo-name basic_test --email test@example.com | grep "session_demo" | awk '{print $NF}')
# ... run test with SESSION1 ...

# Test 2: Advanced validation
SESSION2=$(python demo_session_manager.py create --demo-name advanced_test --email test@example.com | grep "session_demo" | awk '{print $NF}')
# ... run test with SESSION2 ...

# Download both results
python demo_session_manager.py download --email test@example.com --session-id $SESSION1 --output ./results/basic/
python demo_session_manager.py download --email test@example.com --session-id $SESSION2 --output ./results/advanced/
```

### Batch Testing

```bash
#!/bin/bash
# batch_test.sh

EMAIL="test@example.com"
TESTS=("test1" "test2" "test3")

for test_name in "${TESTS[@]}"; do
    echo "Running test: $test_name"

    # Create session
    SESSION_ID=$(python demo_session_manager.py create \
        --demo-name "$test_name" \
        --email "$EMAIL" | grep "session_demo" | awk '{print $NF}')

    echo "Session ID: $SESSION_ID"

    # ... trigger validation ...

    # Wait and download
    sleep 30  # Wait for completion
    python demo_session_manager.py download \
        --email "$EMAIL" \
        --session-id "$SESSION_ID" \
        --output "./results/$test_name/"
done
```

### Continuous Monitoring

```python
import time
from demo_session_manager import DemoSessionManager

def monitor_session(email, session_id, timeout=300, check_interval=10):
    """Monitor session until completion or timeout"""
    manager = DemoSessionManager()
    start_time = time.time()

    while time.time() - start_time < timeout:
        status = manager.check_session_status(email, session_id)

        if not status['exists']:
            print("Session not found yet...")
            time.sleep(check_interval)
            continue

        print(f"Version: {status['current_version']}")
        print(f"Preview: {status['has_preview']} ({status.get('preview_status', 'N/A')})")
        print(f"Validation: {status['has_validation']} ({status.get('validation_status', 'N/A')})")

        if status['has_validation'] and status['validation_status'] in ['completed', 'failed']:
            print(f"\nValidation {status['validation_status']}!")
            return status['validation_status'] == 'completed'

        time.sleep(check_interval)

    print("Timeout waiting for results")
    return False

# Usage
session_id = "session_demo_20251010_143022_abc12345"
success = monitor_session("test@example.com", session_id)
```

---

## Troubleshooting

### Session Not Found

If `check_session_status` returns `exists: False`:

1. Check the session ID is correct (copy-paste to avoid typos)
2. Verify the email matches the session owner
3. Ensure the validation workflow actually created the session in S3
4. Check you're using the correct bucket (`--bucket` flag)

### Results Not Available

If results don't exist after validation completes:

1. Check session status first: `python demo_session_manager.py status ...`
2. Look at the validation_status: it should be "completed"
3. Check CloudWatch logs for the validation lambda
4. Verify the session_info.json has the results paths

### Download Fails

Common causes and solutions:

| Error | Solution |
|-------|----------|
| Permission denied | Check AWS credentials have S3 read access |
| File not found | Run `verify` command first to check paths |
| Disk full | Free up space or use different output path |
| Network timeout | Increase timeout or retry download |

---

## Best Practices

1. **Always save session IDs**: Store them for later reference
2. **Use descriptive demo names**: Makes it easier to identify tests
3. **Check status before downloading**: Avoid unnecessary API calls
4. **Clean up after testing**: Remove test data to avoid clutter
5. **Use dry-run for cleanup**: Always verify what will be deleted
6. **Monitor timeout**: Don't wait indefinitely for results
7. **Handle errors gracefully**: Check return values and error messages

---

## Environment-Specific Usage

### Development Environment

```bash
# Use dev bucket (default)
python demo_session_manager.py create \
    --demo-name dev_test \
    --email dev@example.com
```

### Production Environment

```bash
# Use production bucket
python demo_session_manager.py create \
    --bucket hyperplexity-storage \
    --demo-name prod_test \
    --email prod@example.com
```

### Testing Environment

```bash
# Use test bucket
python demo_session_manager.py create \
    --bucket hyperplexity-storage-test \
    --demo-name test_scenario \
    --email test@example.com
```

---

## Session ID Format

Demo sessions use the format:
```
session_demo_YYYYMMDD_HHMMSS_XXXXXXXX
```

Where:
- `YYYYMMDD`: Date (e.g., 20251010)
- `HHMMSS`: Time (e.g., 143022)
- `XXXXXXXX`: Unique 8-character hash

Example: `session_demo_20251010_143022_abc12345`

This format:
- Clearly identifies demo/test sessions
- Includes timestamp for easy sorting
- Has unique suffix to prevent collisions

---

## Advanced Features

### Downloading Specific Versions

```python
# Download results from version 2 specifically
manager.download_results(
    "test@example.com",
    session_id,
    "./results/v2/",
    version=2
)
```

### Listing All Test Sessions

```bash
# See all demo sessions for a user
python demo_session_manager.py list --email test@example.com
```

Output:
```
[SUCCESS] Found 3 demo sessions
  - session_demo_20251010_143022_abc12345 (15 files)
  - session_demo_20251010_150000_def67890 (12 files)
  - session_demo_20251011_090000_ghi24680 (18 files)
```

### Programmatic Session Management

```python
# Get all sessions and download latest
manager = DemoSessionManager()
sessions = manager.list_all_demo_sessions("test@example.com")

# Find most recent session
latest_session = max(sessions, key=lambda s: s['last_modified'])
print(f"Latest session: {latest_session['session_id']}")

# Download its results
manager.download_results(
    "test@example.com",
    latest_session['session_id'],
    "./latest_results/"
)
```

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Validation Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.9'

    - name: Install dependencies
      run: |
        pip install boto3

    - name: Create test session
      id: session
      run: |
        SESSION_ID=$(python deployment/demo_session_manager.py create \
          --demo-name github_actions_test \
          --email ci@example.com | grep "session_demo" | awk '{print $NF}')
        echo "::set-output name=session_id::$SESSION_ID"

    - name: Run validation test
      env:
        SESSION_ID: ${{ steps.session.outputs.session_id }}
      run: |
        # Your validation test here
        python tests/run_validation.py --session-id $SESSION_ID

    - name: Download results
      env:
        SESSION_ID: ${{ steps.session.outputs.session_id }}
      run: |
        python deployment/demo_session_manager.py download \
          --email ci@example.com \
          --session-id $SESSION_ID \
          --output ./test_results/

    - name: Upload artifacts
      uses: actions/upload-artifact@v2
      with:
        name: test-results
        path: ./test_results/

    - name: Cleanup
      if: always()
      env:
        SESSION_ID: ${{ steps.session.outputs.session_id }}
      run: |
        python deployment/demo_session_manager.py cleanup \
          --email ci@example.com \
          --session-id $SESSION_ID
```

---

## Summary

The Demo Session Manager provides a complete toolkit for managing test sessions:

1. **Create** unique test sessions with `create`
2. **Monitor** progress with `status`
3. **Verify** results with `verify`
4. **Download** outputs with `download`
5. **List** all sessions with `list`
6. **Clean up** test data with `cleanup`

All operations are designed to work seamlessly with the Hyperplexity Validator S3 structure and provide clear feedback about operations and errors.

For more details, see `DEMO_SESSION_MANAGER.md`.
