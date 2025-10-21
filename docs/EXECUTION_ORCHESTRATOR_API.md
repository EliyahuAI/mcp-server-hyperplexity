# Execution Orchestrator - API Reference

## Main Functions

### `execute_full_table_generation()`

**Main pipeline orchestrator - executes all 4 steps in sequence.**

```python
async def execute_full_table_generation(
    email: str,
    session_id: str,
    conversation_id: str,
    run_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute complete table generation pipeline (Phase 2).

    Pipeline:
    1. Column Definition (~30s)
    2. PARALLEL:
       - Row Discovery (~90s)
       - Config Generation (~90s)
    3. Table Population (~90s)
    4. Validation (~10s)

    Args:
        email: User email address
        session_id: Session identifier (e.g., "session_20251020_123456")
        conversation_id: Conversation identifier (e.g., "table_conv_abc123")
        run_key: Optional run tracking key for metrics

    Returns:
        {
            'success': bool,              # True if all steps succeeded
            'conversation_id': str,       # Echo of conversation_id
            'table_data': Dict,           # Complete validated table
            'validation_summary': Dict,   # Validation results
            'error': Optional[str],       # Error message if failed
            'failed_at_step': Optional[int]  # Which step failed (0-4)
        }
    """
```

**Example Call:**
```python
from .execution import execute_full_table_generation

result = await execute_full_table_generation(
    email="user@example.com",
    session_id="session_20251020_123456",
    conversation_id="table_conv_abc123",
    run_key="run_xyz789"
)

if result['success']:
    print(f"Table generated: {len(result['table_data']['rows'])} rows")
else:
    print(f"Failed at step {result['failed_at_step']}: {result['error']}")
```

---

### `send_execution_progress()`

**Send WebSocket progress updates throughout pipeline.**

```python
def send_execution_progress(
    session_id: str,
    conversation_id: str,
    current_step: int,        # 0-4
    total_steps: int,         # Always 4
    status: str,              # Human-readable status message
    progress_percent: int,    # 0-100
    **kwargs                  # Additional fields for message
) -> None:
    """
    Send execution progress update via WebSocket.

    Args:
        session_id: Session identifier
        conversation_id: Conversation identifier
        current_step: Current step number (1-4)
        total_steps: Total number of steps (4)
        status: Human-readable status message
        progress_percent: Progress percentage (0-100)
        **kwargs: Additional fields to include in message
            - rows_discovered: int
            - match_score_avg: float
            - error: str
            - etc.

    Returns:
        None (sends WebSocket message)
    """
```

**Example Call:**
```python
send_execution_progress(
    session_id="session_123",
    conversation_id="table_conv_abc",
    current_step=2,
    total_steps=4,
    status="Discovering rows across 3 subdomains...",
    progress_percent=35,
    rows_found_so_far=12
)
```

---

### `handle_execute_full_table()`

**HTTP handler for API Gateway or SQS invocation.**

```python
async def handle_execute_full_table(
    event: Dict[str, Any],
    context: Any
) -> Dict[str, Any]:
    """
    HTTP handler for full table execution.

    This handler is called when trigger_execution=true from conversation.py
    or directly via API Gateway.

    Input event body:
    {
        'email': 'user@example.com',
        'session_id': 'session_xxx',
        'conversation_id': 'table_conv_xxx',
        'run_key': 'optional_run_key'
    }

    Returns:
        HTTP response (200 or 500) with execution results
    """
```

**Example Event:**
```json
{
  "body": "{\"email\": \"user@example.com\", \"session_id\": \"session_123\", \"conversation_id\": \"table_conv_abc\"}"
}
```

---

## Helper Functions

### `_load_conversation_state()`

**Load conversation state from S3.**

```python
def _load_conversation_state(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str
) -> Optional[Dict[str, Any]]:
    """
    Load conversation state from S3.

    S3 Key: {session_path}table_maker/conversation_{conversation_id}.json

    Returns:
        Conversation state dictionary or None if not found
    """
```

---

### `_save_conversation_state()`

**Save conversation state to S3.**

```python
def _save_conversation_state(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str,
    conversation_state: Dict[str, Any]
) -> bool:
    """
    Save conversation state to S3.

    S3 Key: {session_path}table_maker/conversation_{conversation_id}.json

    Returns:
        True if successful, False otherwise
    """
```

---

## Placeholder Functions (To Be Implemented)

### `_generate_config_placeholder()`

**Generate validation config (placeholder).**

```python
async def _generate_config_placeholder(
    email: str,
    session_id: str,
    conversation_id: str,
    conversation_state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate configuration using config_bridge.

    This is a placeholder that will use config_bridge.py to generate
    a validation config from the conversation context.

    TODO: Implement actual config generation using:
      - config_bridge.build_table_analysis_from_conversation()
      - handle_generate_config_unified()

    Returns:
        {
            'success': bool,
            'config': Dict,
            'error': Optional[str]
        }
    """
```

---

### `_populate_table_with_rows()`

**Populate table with discovered rows (placeholder).**

```python
async def _populate_table_with_rows(
    email: str,
    session_id: str,
    conversation_id: str,
    final_rows: list,              # Discovered rows from Step 2a
    conversation_state: Dict[str, Any],
    run_key: Optional[str]
) -> Dict[str, Any]:
    """
    Populate table with discovered rows.

    This function will eventually call a modified version of finalize.py
    that accepts final_row_ids as input instead of generating them internally.

    TODO: Modify finalize.py to:
      - Accept final_row_ids parameter
      - Remove internal row generation logic
      - Focus on data population only (row expansion)

    Returns:
        {
            'success': bool,
            'table_data': Dict,
            'error': Optional[str]
        }
    """
```

---

### `_validate_complete_table()`

**Validate complete table (placeholder).**

```python
async def _validate_complete_table(
    email: str,
    session_id: str,
    conversation_id: str,
    table_data: Dict[str, Any],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate complete table.

    This is a placeholder for table validation. In the full implementation,
    this would call the validation lambda to validate the complete table.

    TODO: Implement actual validation:
      - Apply validation config to table_data
      - Call validation lambda or handler
      - Return detailed validation summary

    Returns:
        {
            'success': bool,
            'validation_summary': Dict,
            'error': Optional[str]
        }
    """
```

---

## Progress Tracking

### Progress Percentages by Step

| Step | Start | End | Duration | Key Actions |
|------|-------|-----|----------|-------------|
| 0 (Init) | 0% | 5% | ~5s | Load conversation, validate parameters |
| 1 (Column Def) | 5% | 25% | ~30s | Define columns, search strategy |
| 2a (Row Discovery) | 25% | 50% | ~90s | Parallel subdomain streams, deduplication |
| 2b (Config Gen) | 25% | 50% | ~90s | Generate validation config (parallel) |
| 3 (Table Pop) | 50% | 75% | ~90s | Populate data columns, expansion |
| 4 (Validation) | 75% | 100% | ~10s | Validate table, confidence scores |

**Total: ~3-4 minutes**

---

## WebSocket Message Schema

### Progress Update

```typescript
{
  type: 'table_execution_update',
  conversation_id: string,
  current_step: number,        // 0-4
  total_steps: number,         // Always 4
  status: string,              // Human-readable status
  progress_percent: number,    // 0-100

  // Optional fields
  rows_discovered?: number,
  match_score_avg?: number,
  error?: string
}
```

### Error Message

```typescript
{
  type: 'table_execution_update',
  conversation_id: string,
  current_step: number,
  total_steps: number,
  status: string,              // e.g., "Failed at step 2: ..."
  progress_percent: number,
  error: string                // Detailed error message
}
```

### Completion Message

```typescript
{
  type: 'table_execution_update',
  conversation_id: string,
  current_step: 4,
  total_steps: 4,
  status: 'Execution complete! Table is ready.',
  progress_percent: 100
}
```

---

## Integration with Other Components

### Called By

- **conversation.py**: When `trigger_execution=true`
  ```python
  if interview_result.get('trigger_execution'):
      execution_result = await execute_full_table_generation(
          email=email,
          session_id=session_id,
          conversation_id=conversation_id,
          run_key=run_key
      )
  ```

### Calls

1. **column_definition.py** (Step 1)
   ```python
   column_result = await handle_column_definition(event, None)
   ```

2. **row_discovery_handler.py** (Step 2a)
   ```python
   row_result = await handle_row_discovery(event, None)
   ```

3. **config_bridge.py** (Step 2b)
   ```python
   config_result = await _generate_config_placeholder(...)
   ```

4. **finalize.py** (Step 3) - Modified
   ```python
   table_result = await _populate_table_with_rows(...)
   ```

5. **validation.py** (Step 4) - To be implemented
   ```python
   validation_result = await _validate_complete_table(...)
   ```

---

## Error Codes and Recovery

### Error Response Structure

```python
{
    'success': False,
    'conversation_id': str,
    'error': str,                # Human-readable error message
    'failed_at_step': int,       # 0, 1, 2, 3, or 4
    'table_data': None,
    'validation_summary': None
}
```

### Recovery Strategies by Step

| Failed Step | Saved State | Recovery Action |
|-------------|-------------|-----------------|
| 0 (Init) | None | Retry from beginning |
| 1 (Column Def) | Conversation context | Retry column definition |
| 2 (Discovery) | Column definition | Retry row discovery |
| 3 (Population) | Rows discovered | Retry table population |
| 4 (Validation) | Complete table | Mark unvalidated, continue |

### Partial Results Access

Even when execution fails, partial results are saved to S3:

```python
# Load conversation state to access partial results
conversation_state = _load_conversation_state(
    storage_manager, email, session_id, conversation_id
)

# Check what's available
if 'column_definition' in conversation_state:
    columns = conversation_state['column_definition']['columns']

if 'row_discovery' in conversation_state:
    discovered_rows = conversation_state['row_discovery']['final_rows']

if 'table_data' in conversation_state:
    table = conversation_state['table_data']
```

---

## Testing Examples

### Unit Test for Step 1

```python
async def test_step_1_column_definition():
    """Test column definition step independently."""

    # Setup
    email = "test@example.com"
    session_id = "test_session"
    conversation_id = "test_conv"

    # Mock conversation state
    conversation_state = {
        'interview_context': {...},
        'messages': [...]
    }

    # Execute step 1
    column_result = await handle_column_definition(
        {'body': json.dumps({
            'email': email,
            'session_id': session_id,
            'conversation_id': conversation_id
        })},
        None
    )

    # Assert
    assert column_result['statusCode'] == 200
    body = json.loads(column_result['body'])
    assert body['success'] == True
    assert 'columns' in body
    assert 'search_strategy' in body
```

### Integration Test for Full Pipeline

```python
async def test_full_pipeline_execution():
    """Test complete pipeline end-to-end."""

    # Setup
    email = "test@example.com"
    session_id = "test_session"
    conversation_id = "test_conv"

    # Execute full pipeline
    result = await execute_full_table_generation(
        email=email,
        session_id=session_id,
        conversation_id=conversation_id
    )

    # Assert
    assert result['success'] == True
    assert result['conversation_id'] == conversation_id
    assert 'table_data' in result
    assert 'validation_summary' in result
    assert result['failed_at_step'] is None
```

---

## Monitoring and Metrics

### CloudWatch Logs

All log messages prefixed with `[EXECUTION]`:

```
[EXECUTION] Starting full table generation pipeline for table_conv_abc123
[EXECUTION] Step 1/4: Starting column definition
[EXECUTION] Step 1/4 complete: 7 columns defined
[EXECUTION] Step 2/4: Starting parallel row discovery and config generation
[EXECUTION] Step 2/4 complete: 20 rows discovered, config generated: True
[EXECUTION] Step 3/4: Starting table population
[EXECUTION] Table populated with 20 rows (7 columns)
[EXECUTION] Step 4/4: Starting validation
[EXECUTION] Step 4/4 complete: Validation finished
[EXECUTION] Full table generation pipeline complete for table_conv_abc123
```

### Runs Database Tracking

The execution orchestrator updates the runs database at each step:

- **status**: IN_PROGRESS → COMPLETED (or FAILED)
- **percent_complete**: 0 → 25 → 50 → 75 → 100
- **verbose_status**: Step-by-step progress messages
- **run_type**: "Table Generation (Execution)"
- **error_message**: Set if execution fails

Query example:
```python
from dynamodb_schemas import get_run_status

run_data = get_run_status(session_id, run_key)
print(f"Status: {run_data['status']}")
print(f"Progress: {run_data['percent_complete']}%")
print(f"Current step: {run_data['verbose_status']}")
```

---

## Quick Reference

**Main entry point:**
```python
result = await execute_full_table_generation(email, session_id, conversation_id, run_key)
```

**Check result:**
```python
if result['success']:
    table = result['table_data']
    validation = result['validation_summary']
else:
    error = result['error']
    failed_step = result['failed_at_step']
```

**Send progress:**
```python
send_execution_progress(session_id, conversation_id, step, total_steps, status, percent)
```

**Load state:**
```python
state = _load_conversation_state(storage_manager, email, session_id, conversation_id)
```

**Save state:**
```python
success = _save_conversation_state(storage_manager, email, session_id, conversation_id, state)
```
