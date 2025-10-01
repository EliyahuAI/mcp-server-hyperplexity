# Async Validation System Review

## Architecture Overview

### Communication Flow
```
Interface Lambda → Validator Lambda (direct invoke) → Continuation Lambdas (direct invoke) → Interface Lambda (completion)
```

### Key Design Decisions
1. **Direct Lambda Invocation**: Replaced SQS queues with direct `lambda_client.invoke()` for lower latency
2. **S3-Based Payloads**: Large data (validation_data, config) stored in S3, metadata passed via Lambda invocation
3. **DynamoDB Coordination**: Atomic locking prevents multiple lambdas from processing same session
4. **Output-Based Progress**: Uses S3 results count (not counters) to track progress and prevent infinite loops
5. **Config Version-Based Paths**: Results stored in `v{N}_results/` directories based on config version

## Critical Bug Fixed

**Issue**: Event replacement loses invocation metadata
- When validator loaded S3 payload and replaced `event` with it (line 2655), critical fields from Lambda invocation were lost
- **Lost fields**: `results_path`, `config_version`, `email`, `run_key`, `session_id`, etc.

**Fix**: Preserve fields before replacement (lines 2653-2675)
```python
# Preserve critical fields from Lambda invocation event before replacing
preserved_fields = {
    'results_path': event.get('results_path'),
    'config_version': event.get('config_version'),
    'email': event.get('email'),
    ...
}
event = complete_payload  # Replace
# Restore preserved fields
for field, value in preserved_fields.items():
    if value is not None and field not in event:
        event[field] = value
```

## S3 Path Consistency

### Path Construction
All paths use: `results/{domain}/{email_prefix}/{session_id}/v{config_version}_results/`

### Path Usage
1. **Interface** (line 2963): Constructs initial `results_path`
2. **Continuation Payload** (line 2427): `{results_path}/continuation_payload_{count}_{timestamp}.json`
3. **Load Existing Results** (lines 3077-3083): `{results_path}/complete_validation_results.json`
4. **Save Before Continuation** (lines 3325-3331): `{results_path}/complete_validation_results.json`
5. **Final Results Save** (lines 4928-4934): `{results_path}/complete_validation_results.json`

### Fallback Logic
If `results_path` not in event, construct from `email` and `config_version`:
```python
domain, email_prefix = get_s3_path_components(event)
config_version = event.get('config_version', 1)
results_path = f"results/{domain}/{email_prefix}/{session_id}/v{config_version}_results"
```

## Payload Flow Through Continuation Chain

### First Async Invocation (Interface → Validator)
**Lambda Invocation Event**:
- results_path, config_version, email, complete_payload_s3_key

**S3 Payload** (async_payloads/{session_id}/{run_key}/complete_validation_payload.json):
- validation_data, config, email, config_version, results_path, async_delegation_request

### Continuation Invocations (Validator → Validator)
**Lambda Invocation Event**:
- results_path, config_version, email, complete_payload_s3_key, continuation_count

**S3 Payload** ({results_path}/continuation_payload_{count}.json):
- validation_data, config, email, config_version, results_path, async_delegation_request, continuation_metadata

## Sync/Async Bifurcation

### Decision Point (Interface)
```python
if estimated_minutes > MAX_SYNC_INVOCATION_TIME_MINUTES:
    should_delegate = True  # Use async
```

### Invocation Type
- **Sync**: `InvocationType='RequestResponse'` - waits for response
- **Async**: `InvocationType='Event'` - fire-and-forget

### Validator Detection
```python
is_async_request = event.get('async_delegation_request', False)
if is_async_request and complete_payload_s3_key:
    # Load from S3 and process with async logic
```

## Variable Scope Validation

### Properly Declared Nonlocal Variables
- `lock_acquired` (line 2886) - modified in acquire_coordination_lock()
- `validation_results` (line 3130) - modified in process_all_rows()

### Inner Functions with Proper Scope Access
- `get_s3_path_components(event_data)` - takes parameter, no scope issues
- `validate_message_age()` - reads outer scope, doesn't modify
- `acquire_coordination_lock()` - declares `nonlocal lock_acquired`
- `release_coordination_lock()` - reads outer scope only
- `trigger_self_continuation()` - reads outer scope only
- `trigger_interface_completion()` - reads outer scope only

## Error Handling

### Custom Exceptions
```python
class CoordinationConflictException(Exception):
    """Raised when another lambda is actively processing this session."""
    
class StaleMessageException(Exception):
    """Raised when processing a message older than the allowed age."""
```

### Exception Handlers
1. **Coordination Conflict** (line 5008): Returns 409 status
2. **Stale Message** (line 5014): Returns 410 status  
3. **Lock Release** (line 5032): Finally block ensures lock cleanup

## Safety Mechanisms

### 1. Progress Validation
```python
progress_made = current_completed_rows > last_completed_rows
if not progress_made:
    logger.error("[PROGRESS_CHECK] No progress made - preventing infinite continuation loop")
    trigger_interface_completion(results_s3_key)
```

### 2. Max Continuations Limit
```python
MAX_CONTINUATIONS = int(os.environ.get('MAX_CONTINUATIONS', '20'))
if continuation_count >= MAX_CONTINUATIONS:
    return {'statusCode': 429, 'body': json.dumps({'error': 'Maximum continuation limit reached'})}
```

### 3. Stale Lock Detection
```python
STALE_LOCK_THRESHOLD = 300  # 5 minutes
if age_seconds > STALE_LOCK_THRESHOLD:
    logger.info("Detected stale lock - taking over")
```

### 4. Message Age Validation
```python
MAX_MESSAGE_AGE = 300  # 5 minutes (disabled for direct invocation)
if message_age > MAX_MESSAGE_AGE:
    raise StaleMessageException(message_age, MAX_MESSAGE_AGE)
```

## Testing Configuration

### Forced Settings for Testing
```python
# Force batch size to 3 rows
batch_manager = DynamicBatchSizeManager(
    initial_batch_size=3, min_batch_size=3, max_batch_size=3
)

# Force continuation after first batch (14.8 min buffer)
SAFETY_BUFFER_MS = 888000  # 14.8 minutes
```

## Environment Configuration

### Removed
- SQS queue names (all environments)
- SQS event source mappings

### Added
- `VALIDATOR_LAMBDA_NAME` per environment
- `INTERFACE_LAMBDA_NAME` per environment

## Recommendations

1. ✅ **Event field preservation** - Critical fields now preserved during payload replacement
2. ✅ **S3 path consistency** - All operations use consistent path logic with config_version
3. ✅ **Payload completeness** - All payloads include email, config_version, results_path
4. ⚠️ **Testing needed** - Test with actual 100+ row dataset to verify continuation chain
5. ⚠️ **Monitoring** - Add CloudWatch metrics for continuation counts and progress tracking
6. ⚠️ **Cleanup** - Remove SQS queues from AWS after confirming direct invocation works

## Known Limitations

1. **SQS Legacy Code**: Message age validation checks for SentTimestamp which direct invocation doesn't have
2. **Testing Mode**: Batch size forced to 3 and safety buffer to 14.8 minutes for testing
3. **Hardcoded Values**: Some fallback defaults (e.g., 'unknown' domain) may need improvement
