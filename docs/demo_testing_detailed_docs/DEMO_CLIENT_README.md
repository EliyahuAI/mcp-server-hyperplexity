# Demo API Client

Python HTTP client for interacting with the Hyperplexity Validator dev environment interface lambda API.

## Overview

The `demo_api_client.py` module provides a simple Python interface for:
- Loading demo datasets into user sessions
- Triggering preview validations
- Running full validations
- Polling validation status
- Retrieving results

## Installation

No installation required. The module uses only standard Python libraries:
- `requests` (for HTTP)
- `json`, `time`, `datetime` (standard library)

Make sure you have `requests` installed:
```bash
pip install requests
```

## Quick Start

### 1. List Available Demos

```python
from deployment.demo_api_client import DemoAPIClient

client = DemoAPIClient(email="your@email.com")
demos = client.list_demos()

for demo in demos['demos']:
    print(f"{demo['name']}: {demo['display_name']}")
```

### 2. Run Demo Workflow (Preview Only)

```python
from deployment.demo_api_client import quick_demo_test

# Run preview only
result = quick_demo_test('competitive_intelligence', preview_only=True)
```

### 3. Run Complete Demo Workflow

```python
from deployment.demo_api_client import DemoAPIClient

# Initialize client
client = DemoAPIClient(email="eliyahu@eliyahu.ai")

# Step 1: Load demo
session_id, demo_info = client.call_demo_api("competitive_intelligence")

# Step 2: Run preview
preview_result = client.trigger_preview(session_id, wait_for_completion=True)
print(f"Estimated cost: ${preview_result['preview_data']['estimated_total_cost']:.2f}")

# Step 3: Run full validation
validation_result = client.trigger_full_validation(session_id, wait_for_completion=True)
print(f"Results: {validation_result['download_url']}")
```

## API Reference

### DemoAPIClient Class

#### Initialization

```python
client = DemoAPIClient(
    email="your@email.com",  # Optional, defaults to "eliyahu@eliyahu.ai"
    api_base=None             # Optional, defaults to dev environment
)
```

#### Methods

##### `list_demos() -> Dict`
List all available demos.

**Returns:**
```python
{
    'success': True,
    'demos': [
        {
            'name': 'competitive_intelligence',
            'display_name': 'Competitive Intelligence',
            'description': '...',
            'data_file': {...},
            'config_file': {...}
        },
        ...
    ]
}
```

##### `call_demo_api(demo_name: str, email: str = None) -> Tuple[str, Dict]`
Load a demo into a new session.

**Parameters:**
- `demo_name`: Name of the demo to load
- `email`: User email (optional)

**Returns:**
- Tuple of `(session_id, demo_info)`

**Example:**
```python
session_id, demo_info = client.call_demo_api("competitive_intelligence")
```

##### `trigger_preview(session_id: str, email: str = None, preview_max_rows: int = 3, wait_for_completion: bool = True) -> Dict`
Trigger preview validation.

**Parameters:**
- `session_id`: Session ID from `call_demo_api`
- `email`: User email (optional)
- `preview_max_rows`: Number of rows to preview (default: 3)
- `wait_for_completion`: Whether to poll until complete (default: True)

**Returns:**
```python
{
    'success': True,
    'session_id': 'session_demo_..._preview_...',
    'preview_data': {
        'estimated_total_cost': 12.34,
        'estimated_total_time_seconds': 120,
        'total_rows': 100,
        'markdown_table': '...',
        ...
    },
    'full_status': {...}
}
```

##### `trigger_full_validation(session_id: str, email: str = None, max_rows: int = None, batch_size: int = None, wait_for_completion: bool = True) -> Dict`
Trigger full validation.

**Parameters:**
- `session_id`: Session ID from `call_demo_api`
- `email`: User email (optional)
- `max_rows`: Maximum rows to process (None = all)
- `batch_size`: Batch size (None = auto)
- `wait_for_completion`: Whether to poll until complete (default: True)

**Returns:**
```python
{
    'success': True,
    'session_id': 'session_demo_...',
    'download_url': 'https://s3.amazonaws.com/...',
    'total_rows': 100,
    'processed_rows': 100,
    'total_cost': 12.34,
    'full_status': {...}
}
```

##### `check_status(session_id: str, is_preview: bool = False) -> Dict`
Check validation status.

**Parameters:**
- `session_id`: Session ID to check
- `is_preview`: Whether this is a preview session

**Returns:**
```python
{
    'status': 'COMPLETED',  # or 'PROCESSING', 'FAILED', 'ERROR'
    'percent_complete': 100,
    'total_rows': 100,
    'processed_rows': 100,
    'download_url': '...',  # For completed validations
    ...
}
```

##### `get_results_info(session_id: str) -> Dict`
Get results metadata for a completed validation.

**Parameters:**
- `session_id`: Session ID

**Returns:**
```python
{
    'session_id': 'session_demo_...',
    'download_url': 'https://s3.amazonaws.com/...',
    'total_rows': 100,
    'processed_rows': 100,
    'total_cost': 12.34,
    'status_data': {...}
}
```

## Command Line Usage

### Using demo_api_client.py directly

```bash
# Run demo with preview only
python.exe deployment/demo_api_client.py competitive_intelligence --preview-only

# Run complete demo workflow
python.exe deployment/demo_api_client.py competitive_intelligence

# List available demos
python.exe -c "from deployment.demo_api_client import DemoAPIClient; client = DemoAPIClient(); print(client.list_demos())"
```

### Using test_demo_client.py

```bash
# List all demos
python.exe deployment/test_demo_client.py list

# Run demo (preview only)
python.exe deployment/test_demo_client.py demo competitive_intelligence

# Run complete demo workflow
python.exe deployment/test_demo_client.py demo competitive_intelligence --full

# Check status
python.exe deployment/test_demo_client.py status session_demo_20251010_123456_abcd1234
```

## Configuration

### Environment
The client defaults to the dev environment:
- API Base: `https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev`

### Timeouts
- Preview: 5 minutes
- Full Validation: 30 minutes

### Retry Settings
- Max Retries: 3
- Retry Delay: 2 seconds

### Polling
- Poll Interval: 5 seconds

These can be modified by changing the class constants in `DemoAPIClient`.

## Error Handling

The client includes comprehensive error handling:

1. **Automatic Retries**: Network errors are retried up to 3 times
2. **Timeout Protection**: All requests have configurable timeouts
3. **Status Validation**: Responses are validated before returning
4. **Clear Error Messages**: Detailed error messages for debugging

Example error handling:

```python
try:
    session_id, demo_info = client.call_demo_api("invalid_demo")
except Exception as e:
    print(f"Error: {e}")
    # Output: Demo selection failed: Demo invalid_demo not found or invalid
```

## Demo Management Flow

The typical workflow is:

1. **selectDemo** action:
   - Copies demo files to user session folder
   - Creates new session ID (format: `session_demo_YYYYMMDD_HHMMSS_UUID`)
   - Returns session_id and demo metadata

2. **Preview Validation**:
   - Sends multipart request with dummy file
   - Sets `preview_first_row=true` and `preview_max_rows=3`
   - Returns preview session ID (format: `{session_id}_preview_HHMMSS`)
   - Polls status until COMPLETED

3. **Full Validation**:
   - Sends multipart request with dummy file
   - Uses original session ID
   - Polls status until COMPLETED
   - Returns download URL for results

## API Endpoints Used

- `POST /validate` - Main endpoint for all actions:
  - `action=selectDemo` - Load demo
  - `action=listDemos` - List available demos
  - With query params for preview/validation

- `GET /status/{session_id}` - Check validation status
  - Query param: `preview=true/false`

## Troubleshooting

### Import Errors
Make sure you're in the project root:
```bash
cd /mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator
python.exe -c "from deployment.demo_api_client import DemoAPIClient"
```

### Connection Errors
Check that the dev environment is accessible:
```bash
curl https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev/health
```

### Timeout Issues
Increase timeouts if needed:
```python
client = DemoAPIClient()
client.VALIDATION_TIMEOUT = 60 * 60  # 1 hour
```

## Examples

See `test_demo_client.py` for complete working examples.

## Notes

- The client uses `requests.Session` for connection pooling
- All responses are returned as dictionaries
- Status polling uses exponential backoff (via fixed intervals)
- The demo workflow automatically creates new session IDs
- Preview sessions get unique IDs to avoid conflicts
