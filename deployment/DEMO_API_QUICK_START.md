# Demo API Client - Quick Start Guide

## Files Created

1. **`demo_api_client.py`** - Main API client module (20KB)
2. **`test_demo_client.py`** - Test/example script (4.8KB)
3. **`DEMO_CLIENT_README.md`** - Complete documentation (8.7KB)
4. **`DEMO_API_QUICK_START.md`** - This file

## 30-Second Quick Start

### Python API Usage

```python
from deployment.demo_api_client import quick_demo_test

# Run a demo with preview only
result = quick_demo_test('competitive_intelligence', preview_only=True)
```

### Command Line Usage

```bash
# From project root
cd /mnt/c/Users/ellio/OneDrive\ -\ Eliyahu.AI/Desktop/src/perplexityValidator

# List available demos
python.exe deployment/test_demo_client.py list

# Run demo preview
python.exe deployment/test_demo_client.py demo competitive_intelligence

# Run complete workflow (preview + validation)
python.exe deployment/test_demo_client.py demo competitive_intelligence --full
```

## 5-Minute Walkthrough

### Step 1: Initialize Client

```python
from deployment.demo_api_client import DemoAPIClient

# Use default email (eliyahu@eliyahu.ai) and dev environment
client = DemoAPIClient()

# Or specify custom email
client = DemoAPIClient(email="your@email.com")
```

### Step 2: List Available Demos

```python
demos = client.list_demos()

for demo in demos['demos']:
    print(f"{demo['name']}: {demo['display_name']}")
```

### Step 3: Load a Demo

```python
session_id, demo_info = client.call_demo_api("competitive_intelligence")
print(f"Session ID: {session_id}")
```

### Step 4: Run Preview

```python
preview = client.trigger_preview(session_id, wait_for_completion=True)
print(f"Estimated cost: ${preview['preview_data']['estimated_total_cost']:.2f}")
```

### Step 5: Run Full Validation (Optional)

```python
result = client.trigger_full_validation(session_id, wait_for_completion=True)
print(f"Download: {result['download_url']}")
```

## Key Functions

### 1. `call_demo_api(demo_name, email)`
Loads demo and creates session

**Returns:** `(session_id, demo_info)`

### 2. `trigger_preview(session_id, email)`
Runs preview validation (first 3 rows by default)

**Returns:** Preview results with cost estimates

### 3. `trigger_full_validation(session_id, email)`
Runs complete validation

**Returns:** Results with download URL

### 4. `check_status(session_id)`
Polls validation status

**Returns:** Status information

### 5. `get_results_info(session_id)`
Gets results metadata for completed validation

**Returns:** Download URL and metadata

## Configuration

All functions use sensible defaults:

- **Environment:** Dev (`https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev`)
- **Email:** `eliyahu@eliyahu.ai`
- **Preview rows:** 3
- **Preview timeout:** 5 minutes
- **Validation timeout:** 30 minutes
- **Retry attempts:** 3
- **Poll interval:** 5 seconds

## Error Handling

All functions raise exceptions with clear error messages:

```python
try:
    session_id, demo_info = client.call_demo_api("invalid_demo")
except Exception as e:
    print(f"Error: {e}")
    # Output: Demo selection failed: Demo invalid_demo not found or invalid
```

## Complete Example

```python
from deployment.demo_api_client import DemoAPIClient

# Initialize
client = DemoAPIClient(email="eliyahu@eliyahu.ai")

# Load demo
session_id, demo_info = client.call_demo_api("competitive_intelligence")
print(f"Loaded: {demo_info['display_name']}")

# Preview (waits for completion)
preview = client.trigger_preview(session_id)
print(f"Preview cost: ${preview['preview_data']['estimated_total_cost']:.2f}")
print(f"Total rows: {preview['preview_data']['total_rows']}")

# Full validation (waits for completion)
result = client.trigger_full_validation(session_id)
print(f"Completed! Download: {result['download_url']}")
print(f"Actual cost: ${result['total_cost']:.2f}")
```

## Testing

Run the test script to verify everything works:

```bash
# Test listing demos
python.exe deployment/test_demo_client.py list

# Test demo workflow (preview only)
python.exe deployment/test_demo_client.py demo competitive_intelligence
```

## Environment Details

### Dev Environment
- **API Base:** `https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev`
- **Test Email:** `eliyahu@eliyahu.ai`

### Demo Management Flow
1. **selectDemo** action copies demo files to session folder
2. Creates new session ID: `session_demo_YYYYMMDD_HHMMSS_UUID`
3. Preview creates separate session: `{session_id}_preview_HHMMSS`
4. Full validation uses original session ID

## API Endpoints

- `POST /validate` with `action=selectDemo` - Load demo
- `POST /validate` with `action=listDemos` - List demos
- `POST /validate` with query params - Trigger validation
- `GET /status/{session_id}?preview=true/false` - Check status

## Common Use Cases

### 1. Quick Test
```python
from deployment.demo_api_client import quick_demo_test
result = quick_demo_test('competitive_intelligence', preview_only=True)
```

### 2. Async Workflow (Don't Wait)
```python
# Start validation without waiting
preview = client.trigger_preview(session_id, wait_for_completion=False)

# Later, check status manually
status = client.check_status(preview['session_id'], is_preview=True)
if status['status'] == 'COMPLETED':
    print("Done!")
```

### 3. Custom Parameters
```python
# Full validation with custom settings
result = client.trigger_full_validation(
    session_id,
    max_rows=50,          # Process only first 50 rows
    batch_size=10,        # Use batch size of 10
    wait_for_completion=True
)
```

## Troubleshooting

### Module not found
Make sure you're in the project root:
```bash
cd /mnt/c/Users/ellio/OneDrive\ -\ Eliyahu.AI/Desktop/src/perplexityValidator
```

### Connection timeout
The dev environment may be slow. Increase timeouts:
```python
client.VALIDATION_TIMEOUT = 60 * 60  # 1 hour
```

### Demo not found
List available demos first:
```python
demos = client.list_demos()
```

## Next Steps

1. Read `DEMO_CLIENT_README.md` for complete API documentation
2. Check `test_demo_client.py` for more examples
3. Customize timeout/retry settings as needed
4. Use in your own scripts/tests

## Support

For issues or questions:
1. Check the error message (they're descriptive)
2. Verify dev environment is accessible
3. Check demo name spelling with `list_demos()`
4. Review `DEMO_CLIENT_README.md` for detailed docs
