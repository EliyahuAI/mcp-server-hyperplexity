# Session Info Tracking System

## Overview

The `session_info.json` file is the **central tracking document** for each validation session. It provides a complete audit trail of all configurations, previews, validations, and their outcomes within a session. This file is critical for:

- **Session continuity**: Understanding what has been done in a session
- **Version management**: Tracking multiple config versions and their results
- **UX analysis**: Storing frontend payloads to analyze user experience
- **Debugging**: Complete history of operations and their outcomes
- **Billing reconciliation**: Links to run records and cost data

## File Location

```
S3: hyperplexity-storage/results/{domain}/{email_prefix}/{session_id}/session_info.json
```

**Example:**
```
hyperplexity-storage/results/gmail.com/john_doe/session_20250102_143022_abc123/session_info.json
```

## Structure

### Top-Level Fields

```json
{
  "session_id": "session_20250102_143022_abc123",
  "created": "2025-01-02T14:30:22.123Z",
  "email": "john.doe@gmail.com",
  "table_name": "customer_data.xlsx",
  "table_path": "results/gmail.com/john_doe/session_20250102_143022_abc123/customer_data_input.xlsx",
  "current_version": 2,
  "last_updated": "2025-01-02T14:45:30.456Z",
  "versions": { /* version-based tracking */ }
}
```

### Version-Based Organization

Each configuration version gets its own entry under `versions`. This supports multiple iterations:

```json
{
  "versions": {
    "1": {
      "config": { /* config metadata */ },
      "preview": { /* preview results */ },
      "validation": { /* validation results */ }
    },
    "2": {
      "config": { /* refined config metadata */ },
      "preview": { /* preview results */ },
      "validation": { /* validation results */ }
    }
  }
}
```

## Config Tracking

Each version contains a `config` object with metadata about the configuration:

```json
{
  "config": {
    "config_id": "session_20250102_143022_abc123_config_v1_ai_generated",
    "config_path": "results/gmail.com/john_doe/session_20250102_143022_abc123/config_v1_ai_generated.json",
    "source": "ai_generated",
    "created_at": "2025-01-02T14:30:25.789Z",
    "description": "Initial AI-generated configuration for customer validation",
    "run_key": "20250102_143022_abc123#CONFIG#20250102T143025",
    "source_session": null,  // populated when copying from another session
    "source_config_path": null  // populated when copying from another config
  }
}
```

### Config Sources

- `ai_generated`: Created by AI from user instructions
- `uploaded`: User uploaded a JSON config file
- `used_by_id`: Retrieved using a config ID from a previous session
- `copied`: Copied from another session/config
- `refined`: AI-refined version of previous config

## Preview Tracking

Each version can have a `preview` object tracking the preview operation:

### Successful Preview

```json
{
  "preview": {
    "run_key": "20250102_143022_abc123#PREVIEW#20250102T143030",
    "status": "completed",
    "completed_at": "2025-01-02T14:30:45.123Z",
    "results_path": "results/gmail.com/john_doe/session_20250102_143022_abc123/v1_results/preview_results.json",
    "frontend_payload": {
      "type": "preview_complete",
      "status": "completed",
      "cost_estimated": 2.45,
      "cost_quoted": 1.85,
      "time_estimated_minutes": 3.5,
      "rows_processed": 5,
      "config_version": 1
    }
  }
}
```

### Failed Preview

```json
{
  "preview": {
    "run_key": "20250102_143022_abc123#PREVIEW#20250102T143030",
    "status": "failed",
    "completed_at": "2025-01-02T14:30:35.123Z",
    "frontend_payload": {
      "type": "preview_failed",
      "progress": 100,
      "status": "❌ Failed to retrieve files for preview",
      "session_id": "session_20250102_143022_abc123",
      "error": "Files not found"
    }
  }
}
```

## Validation Tracking

Each version can have a `validation` object tracking the full validation operation:

### Successful Validation

```json
{
  "validation": {
    "run_key": "20250102_143022_abc123#VALIDATION#20250102T143100",
    "status": "completed",
    "completed_at": "2025-01-02T14:35:22.456Z",
    "results_path": "results/gmail.com/john_doe/session_20250102_143022_abc123/v1_results/validation_results.json",
    "enhanced_excel_path": "results/gmail.com/john_doe/session_20250102_143022_abc123/v1_results/enhanced_validation.xlsx",
    "frontend_payload": {
      "status": "COMPLETED",
      "processed_rows": 150,
      "total_rows": 150,
      "verbose_status": "Validation complete. Results should be in your inbox shortly.",
      "percent_complete": 100,
      "enhanced_download_url": "https://hyperplexity-storage.s3.amazonaws.com/downloads/uuid-123/enhanced.xlsx"
    }
  }
}
```

### Failed Validation

```json
{
  "validation": {
    "run_key": "20250102_143022_abc123#VALIDATION#20250102T143100",
    "status": "failed",
    "completed_at": "2025-01-02T14:33:15.789Z",
    "frontend_payload": {
      "type": "validation_failed",
      "session_id": "session_20250102_143022_abc123",
      "progress": 100,
      "status": "❌ Validation failed: Incomplete results",
      "error": "Validation incomplete: Missing validation results, Processed 45/150 rows"
    }
  }
}
```

## Frontend Payload Tracking

The `frontend_payload` field captures **exactly what was sent to the user** via WebSocket or email. This is critical for:

1. **UX Analysis**: Understanding what users saw when things failed
2. **Debugging**: Reproducing user-reported issues
3. **Consistency**: Ensuring session_info.json reflects actual user experience

### Why Track Frontend Payloads?

Before this tracking was added, there was a disconnect between:
- What was sent to the user (WebSocket messages, emails)
- What was recorded in session_info.json

Now, both success and failure messages are preserved, ensuring complete audit trails.

## Key Update Functions

### `update_session_results()`

**Location**: `src/lambdas/interface/core/unified_s3_manager.py:1295`

**Purpose**: Update session_info.json with operation results (preview or validation)

**Parameters**:
```python
def update_session_results(
    self,
    email: str,
    session_id: str,
    operation_type: str,  # "preview" or "validation"
    config_id: str,
    version: int,
    run_key: str,
    results_path: str = None,  # S3 path to results JSON
    enhanced_excel_path: str = None,  # S3 path to enhanced Excel
    status: str = "completed",  # "completed" or "failed"
    completed_at: str = None,
    frontend_payload: Dict = None  # What was sent to user
) -> bool
```

**Usage Examples**:

```python
# Successful preview
storage_manager.update_session_results(
    email=email,
    session_id=session_id,
    operation_type="preview",
    config_id="session_20250102_143022_abc123_config_v1_ai_generated",
    version=1,
    run_key="20250102_143022_abc123#PREVIEW#20250102T143030",
    results_path="results/.../v1_results/preview_results.json",
    status="completed",
    frontend_payload={
        "type": "preview_complete",
        "cost_estimated": 2.45,
        "rows_processed": 5
    }
)

# Failed validation
storage_manager.update_session_results(
    email=email,
    session_id=session_id,
    operation_type="validation",
    config_id="session_20250102_143022_abc123_config_v1_ai_generated",
    version=1,
    run_key="20250102_143022_abc123#VALIDATION#20250102T143100",
    status="failed",
    frontend_payload={
        "type": "validation_failed",
        "error": "Validation incomplete: Missing results"
    }
)
```

### `update_session_config()`

**Location**: `src/lambdas/interface/core/unified_s3_manager.py:1228`

**Purpose**: Create/update config entry in session_info.json

**Parameters**:
```python
def update_session_config(
    self,
    email: str,
    session_id: str,
    config_data: Dict,
    config_key: str,  # S3 path to config
    config_id: str,
    version: int,
    source: str,  # "ai_generated", "uploaded", etc.
    description: str = None,
    source_session: str = None,  # If copied from another session
    excel_s3_key: str = None,
    source_config_path: str = None,
    run_key: str = None
) -> bool
```

## Failure Tracking Locations

All failure scenarios now properly update session_info.json:

### 1. Preview Failure - Files Not Found
**Location**: `background_handler.py:1236`
```python
# When Excel/config files can't be retrieved
storage_manager.update_session_results(
    operation_type="preview",
    status="failed",
    frontend_payload={
        'type': 'preview_failed',
        'error': 'Files not found'
    }
)
```

### 2. Preview Processing Failure
**Location**: `background_handler.py:1334`
```python
# When validation lambda fails during preview
storage_manager.update_session_results(
    operation_type="preview",
    status="failed",
    frontend_payload={
        'type': 'preview_failed',
        'error': error_type.lower().replace(' ', '_'),
        'message': 'Preview encountered an issue...'
    }
)
```

### 3. Preview Failure - No Results
**Location**: `background_handler.py:2542`
```python
# When validation returns empty results
storage_manager.update_session_results(
    operation_type="preview",
    status="failed",
    frontend_payload={
        'type': 'preview_failed',
        'error': 'No validation results returned'
    }
)
```

### 4. Validation Failure - Incomplete Results
**Location**: `background_handler.py:4753`
```python
# When validation completes but is missing data
storage_manager.update_session_results(
    operation_type="validation",
    status="failed",
    frontend_payload={
        'type': 'validation_failed',
        'error': f"Validation incomplete: {'; '.join(completeness_issues)}"
    }
)
```

### 5. Validation Failure - No Results
**Location**: `background_handler.py:4867` (preview), `background_handler.py:4897` (validation)
```python
# When validation returns no results
storage_manager.update_session_results(
    operation_type="validation",  # or "preview"
    status="failed",
    frontend_payload={
        'type': 'validation_failed',
        'error': 'No validation results returned'
    }
)
```

## Session Lifecycle

### 1. Session Creation
```json
{
  "session_id": "session_20250102_143022_abc123",
  "created": "2025-01-02T14:30:22.123Z",
  "email": "john.doe@gmail.com",
  "table_name": "table_abc123",
  "current_version": 0,
  "last_updated": "2025-01-02T14:30:22.123Z",
  "versions": {}
}
```

### 2. Config Upload/Generation (Version 1)
```json
{
  "current_version": 1,
  "versions": {
    "1": {
      "config": {
        "config_id": "session_20250102_143022_abc123_config_v1_ai_generated",
        "config_path": "results/.../config_v1_ai_generated.json",
        "source": "ai_generated",
        "created_at": "2025-01-02T14:30:25.789Z"
      }
    }
  }
}
```

### 3. Preview Execution
```json
{
  "versions": {
    "1": {
      "config": { /* ... */ },
      "preview": {
        "run_key": "20250102_143022_abc123#PREVIEW#20250102T143030",
        "status": "completed",
        "results_path": "results/.../v1_results/preview_results.json",
        "frontend_payload": { /* ... */ }
      }
    }
  }
}
```

### 4. Full Validation Execution
```json
{
  "versions": {
    "1": {
      "config": { /* ... */ },
      "preview": { /* ... */ },
      "validation": {
        "run_key": "20250102_143022_abc123#VALIDATION#20250102T143100",
        "status": "completed",
        "results_path": "results/.../v1_results/validation_results.json",
        "enhanced_excel_path": "results/.../v1_results/enhanced_validation.xlsx",
        "frontend_payload": { /* ... */ }
      }
    }
  }
}
```

### 5. Config Refinement (Version 2)
```json
{
  "current_version": 2,
  "versions": {
    "1": { /* ... */ },
    "2": {
      "config": {
        "config_id": "session_20250102_143022_abc123_config_v2_refined",
        "config_path": "results/.../config_v2_refined.json",
        "source": "refined",
        "created_at": "2025-01-02T14:40:00.000Z"
      }
    }
  }
}
```

## Integration with Other Systems

### DynamoDB Runs Table
- **`run_key`**: Links session_info.json entries to DynamoDB run records
- Each preview/validation has a unique run_key for detailed metrics
- Format: `{session_id}#{operation_type}#{timestamp}`

### S3 File Structure
```
results/{domain}/{email_prefix}/{session_id}/
├── session_info.json                              # This tracking file
├── customer_data_input.xlsx                       # Original Excel
├── config_v1_ai_generated.json                    # Config version 1
├── config_v2_refined.json                         # Config version 2
├── v1_results/                                    # Version 1 results folder
│   ├── preview_results.json
│   ├── validation_results.json
│   └── enhanced_validation.xlsx
└── v2_results/                                    # Version 2 results folder
    ├── preview_results.json
    ├── validation_results.json
    └── enhanced_validation.xlsx
```

### WebSocket Messages
- Frontend payloads in session_info.json match WebSocket messages sent to user
- Enables debugging: "What did the user see when this failed?"

### Email Notifications
- Completion emails reference data from session_info.json
- Failure emails trigger session_info.json updates

## Best Practices

### 1. Always Update on Completion AND Failure
```python
# ✅ CORRECT: Update session_info.json on both success and failure
if validation_successful:
    storage_manager.update_session_results(
        status="completed",
        frontend_payload=success_payload
    )
else:
    storage_manager.update_session_results(
        status="failed",
        frontend_payload=error_payload
    )
```

### 2. Preserve Frontend Payloads
```python
# ✅ CORRECT: Save the exact payload sent to user
error_payload = {
    'type': 'preview_failed',
    'status': '❌ Failed to retrieve files',
    'error': 'Files not found'
}
_send_websocket_message(session_id, error_payload)

storage_manager.update_session_results(
    frontend_payload=error_payload  # Same payload
)
```

### 3. Get Correct Config Version
```python
# ✅ CORRECT: Extract version from config metadata
config_version = config_data.get('storage_metadata', {}).get('version', 1)
config_id = config_data.get('storage_metadata', {}).get('config_id')

storage_manager.update_session_results(
    config_id=config_id,
    version=config_version
)
```

### 4. Handle Missing Config Gracefully
```python
# ✅ CORRECT: Fallback when config is unavailable
config_version = 1
config_id = None

if config_data:
    config_version = config_data.get('storage_metadata', {}).get('version', 1)
    config_id = config_data.get('storage_metadata', {}).get('config_id')

storage_manager.update_session_results(
    config_id=config_id or f"{session_id}_config_v{config_version}",
    version=config_version
)
```

## Common Issues & Solutions

### Issue: Failures not recorded in session_info.json
**Solution**: Ensure `update_session_results()` is called in all failure paths with `status="failed"`

### Issue: Wrong config version in session_info.json
**Solution**: Extract version from `config_data.get('storage_metadata', {}).get('version')`, not from filename parsing

### Issue: Frontend payload missing
**Solution**: Capture the exact payload sent to user and pass it to `update_session_results(frontend_payload=...)`

### Issue: run_key missing in session_info.json
**Solution**: Pass `run_key` to both `update_session_config()` and `update_session_results()`

## Validation & Debugging

### Check if session is properly tracked:
```python
session_info = storage_manager.load_session_info(email, session_id)

# Check current version
current_version = session_info.get('current_version')

# Check if version has config
version_data = session_info.get('versions', {}).get(str(current_version))
has_config = 'config' in version_data

# Check if preview completed
preview_status = version_data.get('preview', {}).get('status')

# Check if validation completed
validation_status = version_data.get('validation', {}).get('status')
```

### Common Validation Checks:
1. **Version consistency**: `current_version` matches highest version number in `versions`
2. **Config exists**: Each version has a `config` object before preview/validation
3. **File paths valid**: All S3 paths (`config_path`, `results_path`, etc.) exist
4. **Status accuracy**: `status` field matches actual operation outcome
5. **Frontend payload**: Payload exists and matches what user received

## Summary

The `session_info.json` file is the **single source of truth** for session history. It:

1. **Tracks all versions**: Multiple configs and their iterations
2. **Records all operations**: Preview and validation for each version
3. **Preserves outcomes**: Both success and failure with exact user-facing messages
4. **Links to other systems**: DynamoDB runs, S3 files, WebSocket messages
5. **Enables debugging**: Complete audit trail of what happened and what user saw

By ensuring all code paths (success AND failure) update session_info.json with correct version information and frontend payloads, we maintain data integrity and enable powerful debugging and analysis capabilities.
