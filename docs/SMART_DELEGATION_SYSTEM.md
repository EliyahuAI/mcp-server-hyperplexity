# Smart Delegation System Specification

## Overview

The Smart Delegation System automatically routes validation jobs between synchronous and asynchronous processing based on estimated completion time. It prevents lambda timeouts while maintaining precise cost tracking and seamless user experience.

## Architecture Flow

```
Interface Lambda → SQS → Background Handler → Decision Point:
                                                    ↓
                               Estimated Time <= MAX_SYNC_TIME?
                                  ↙️                    ↘️
                          YES: Process Sync           NO: Delegate Async
                          (Current Path)                    ↓
                               ↓                    Save Context to DynamoDB
                          Complete Job               Create Input Files (S3)
                                                    Trigger Async Validator (SQS)
                                                    Background Handler: EXIT
                                                           ↓
                                                  Async Validator (Self-Managing):
                                                  ├─ Monitor Execution Time
                                                  ├─ Process in Time-Aware Chunks
                                                  ├─ Save Progress to DynamoDB
                                                  ├─ Self-Trigger for Continuation
                                                  ├─ Save Complete Results to S3
                                                  └─ Trigger Background Handler (Completion)
                                                           ↓
                                                  Background Handler (Async Completion):
                                                  ├─ Load Context from DynamoDB
                                                  ├─ Load Results from S3
                                                  ├─ Reconstruct Variables
                                                  ├─ Aggregate Complete Data
                                                  └─ Complete Job (WebSocket, Email, etc.)
```

## Core Components

### 1. Background Handler Delegation Logic

**Decision Criteria:**
- Use existing `estimated_total_time_seconds` from preview results
- Compare against configurable `MAX_SYNC_INVOCATION_TIME` (default: 5 minutes)
- Route to sync (current) or async (new) processing

**Context Preservation:**
- Save complete request context to DynamoDB runs table
- Store all variables needed for job completion
- Create S3 input files for async validator

### 2. DynamoDB State Tracking Schema

**New Fields for Runs Table:**
```python
{
    # Delegation State
    'processing_mode': 'SYNC' | 'ASYNC_DELEGATED' | 'ASYNC_PROCESSING' | 'ASYNC_COMPLETING',
    'delegation_timestamp': '2025-09-29T12:34:56Z',
    'estimated_processing_minutes': 18.5,
    'sync_timeout_limit_minutes': 5.0,

    # Async Context (JSON)
    'async_context': {
        'request_context': {...},
        'preview_estimates': {...},
        'processing_state': {...},
        's3_input_files': {...}
    },

    # Progress Tracking
    'async_progress': {
        'chunks_completed': 2,
        'chunks_total': 4,
        'rows_processed': 500,
        'current_cost': 45.50,
        'last_update': '2025-09-29T12:45:00Z'
    },

    # Completion Data
    'async_results_s3_key': 'results/session_xyz/final_results.json',
    'async_completion_timestamp': '2025-09-29T13:15:30Z'
}
```

### 3. Async Validator (Self-Managing)

**Time Monitoring:**
```python
SAFETY_BUFFER_MS = 180000  # 3 minutes safety buffer

def should_continue_processing(context):
    remaining_ms = context.get_remaining_time_in_millis()
    return remaining_ms > SAFETY_BUFFER_MS

def process_with_time_monitoring(session_id, context):
    while has_more_work() and should_continue_processing(context):
        process_chunk()
        update_progress_in_dynamodb(session_id)

    if has_more_work():
        # Time running low - trigger continuation
        save_state_to_s3(session_id)
        trigger_self_continuation(session_id)
        return "CONTINUED"
    else:
        # Work complete - notify interface
        trigger_interface_completion(session_id)
        return "COMPLETED"
```

**Progress Updates:**
- Update DynamoDB runs table after each chunk
- Track chunks completed, costs accumulated, time elapsed
- Enable real-time progress monitoring via WebSocket

### 4. Interface Async Completion Handler

**Context Restoration:**
```python
def handle_async_completion(session_id):
    # Load complete context from DynamoDB
    run_record = get_run_record(session_id)
    async_context = run_record['async_context']

    # Load final results from S3
    results_key = run_record['async_results_s3_key']
    validation_results = load_from_s3(results_key)

    # Reconstruct status_update_data as if sync processing
    status_data = merge_context_and_results(async_context, validation_results)

    # Complete job with original WebSocket connection
    complete_validation_job(status_data, async_context['websocket_connection_id'])
```

## Configuration

### Environment Variables

```python
# Sync/Async Decision Point
MAX_SYNC_INVOCATION_TIME_MINUTES = int(os.environ.get('MAX_SYNC_INVOCATION_TIME', '5'))

# Validator Time Management
VALIDATOR_SAFETY_BUFFER_MINUTES = int(os.environ.get('VALIDATOR_SAFETY_BUFFER', '3'))

# SQS Queue Names
ASYNC_VALIDATOR_QUEUE = os.environ.get('ASYNC_VALIDATOR_QUEUE', 'perplexity-validator-async-queue')
INTERFACE_COMPLETION_QUEUE = os.environ.get('INTERFACE_COMPLETION_QUEUE', 'perplexity-validator-completion-queue')
```

### Debugging Support

- **Small Test Tables**: Set `MAX_SYNC_INVOCATION_TIME=1` to force async processing
- **Progress Monitoring**: Real-time updates via DynamoDB and WebSocket
- **State Inspection**: Complete context preserved in runs table
- **Recovery**: Resume from any failure point using saved state

## Single Handler Architecture

The Smart Delegation System uses a **single background handler** that handles all three scenarios:

### 1. **Synchronous Processing**
```python
# Short estimated time
background_handler.handle(event, context)
→ Direct validation call
→ Common final processing
```

### 2. **Async Delegation**
```python
# Long estimated time
background_handler.handle(event, context)
→ Save context to DynamoDB
→ Trigger async validator via SQS
→ Return early (don't block)
```

### 3. **Async Completion**
```python
# Completion message from validator
background_handler.handle({
    'async_completion': True,
    'session_id': session_id,
    'results_s3_key': s3_key
}, context)
→ Load context from DynamoDB
→ Load results from S3
→ Reconstruct variables
→ Common final processing
```

### Key Benefits:
- **No code bifurcation**: Single final processing path
- **Consistent behavior**: Same completion logic for sync and async
- **Simple debugging**: One entry point for all scenarios
- **No separate lambdas**: Eliminates async completion handler

## SQS Message Schemas

### Async Validator Trigger Message
```json
{
    "message_type": "ASYNC_VALIDATION_REQUEST",
    "session_id": "session_xyz",
    "s3_input_key": "async_input/session_xyz/input_data.json",
    "s3_config_key": "async_input/session_xyz/config.json",
    "continuation_context": {
        "is_continuation": false,
        "start_position": 0,
        "chunks_completed": 0
    }
}
```

### Interface Completion Message
```json
{
    "async_completion": true,
    "message_type": "ASYNC_VALIDATION_COMPLETE",
    "session_id": "session_xyz",
    "run_key": "AsyncValidation_1727615730",
    "results_s3_key": "sessions/session_xyz/complete_validation_results.json",
    "completion_timestamp": "2025-09-29T13:15:30Z",
    "total_duration_seconds": 450.2,
    "background_processing": true
}
```

## State Transitions

1. **SYNC**: Standard synchronous processing (current system)
2. **ASYNC_DELEGATED**: Background handler saved context, triggered async validator
3. **ASYNC_PROCESSING**: Async validator actively processing, updating progress
4. **ASYNC_COMPLETING**: Interface handling completion, aggregating final results
5. **COMPLETED**: Job finished successfully

## Error Handling & Recovery

### Validator Timeout/Failure
- **Detection**: No progress updates within expected timeframe
- **Recovery**: Re-trigger async validator with saved state
- **Fallback**: Manual admin intervention via DynamoDB state inspection

### Interface Completion Failure
- **Detection**: Completion message processed but job not finalized
- **Recovery**: Re-trigger completion handler with same message
- **Fallback**: Manual job completion using saved async_context

### Cost Accuracy Guarantee
- **Chunk-Level Tracking**: Each completed chunk saves exact costs to DynamoDB
- **No Lost Data**: Even on failure, all completed work costs are preserved
- **Aggregation**: Final cost = sum of all chunk costs in progress tracking

## Benefits

✅ **No More 413 Errors**: Results stored in S3, not lambda response
✅ **Perfect Time Management**: Validator monitors its own execution limits
✅ **Zero Cost Loss**: Chunk-level cost tracking with DynamoDB persistence
✅ **Seamless UX**: Users see consistent progress regardless of sync/async mode
✅ **Debugging Friendly**: Configurable timeouts for testing with small tables
✅ **Failure Resilient**: Complete state recovery from DynamoDB
✅ **Backward Compatible**: Small jobs continue working synchronously

## Implementation Phases

### Phase 1: Core Infrastructure
1. DynamoDB schema extensions
2. S3 input/output handling
3. Basic delegation logic in background handler

### Phase 2: Async Validator
1. Time monitoring and self-triggering
2. Progress tracking integration
3. Chunk-based processing

### Phase 3: Interface Integration
1. Async completion handler
2. WebSocket progress updates from DynamoDB
3. Context restoration and job finalization

### Phase 4: Testing & Optimization
1. End-to-end testing with various job sizes
2. Performance optimization
3. Error handling refinement

This system transforms the timeout problem into intelligent job management, ensuring reliable processing for any dataset size while maintaining all existing functionality and cost accuracy.