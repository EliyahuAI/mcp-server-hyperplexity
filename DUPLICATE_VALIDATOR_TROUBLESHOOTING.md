# Duplicate Validator Lambda Invocation Troubleshooting

## Problem Statement
Multiple validator Lambda invocations are being triggered for a single validation request, causing:
- AI call counter to restart (1/X, 2/X... then 1/X again)
- Multiple validators running in parallel (3-4 invocations)
- Timing pattern: ~60-120 seconds between invocations
- AWS rate limit issues (TooManyRequestsException)

## Evidence from Logs

### Validator Invocations Pattern
```
09:50:15 | Validator invoked: type=SYNC, mode=INITIAL, rows=3    (preview)
09:51:43 | Validator invoked: type=SYNC, mode=INITIAL, rows=10   (+88s, full validation)
09:52:44 | Validator invoked: type=SYNC, mode=INITIAL, rows=10   (+61s, duplicate)
09:53:44 | Validator invoked: type=SYNC, mode=INITIAL, rows=10   (+60s, duplicate)
```

### AI Counter Restarting
```
First validator:  AI Counter: 1/12, 2/12... 12/12 (completes)
Second validator: AI Counter: 1/40, 2/40... (RESTARTS from 1)
Third validator:  AI Counter: 1/40, 2/40... (RESTARTS from 1 again)
```

## Architecture Understanding

### Normal Flow
1. Frontend → Interface Lambda (HTTP/API Gateway)
2. Interface → SQS Queue (preview-queue or standard-queue)
3. SQS → Interface Lambda (background handler via event source mapping)
4. Interface → Validator Lambda (direct invoke)

### Queue Configuration
- **preview-queue-dev**: For preview validations (3 rows)
- **standard-queue-dev**: For full validations
  - VisibilityTimeout: 960s (16 minutes)
  - BatchSize: 5
  - No RedrivePolicy (DLQ)

### Lambda Configuration
- **Interface Lambda**: Timeout 900s (15 min), Memory 512MB
- **Validator Lambda**: Timeout 870s (14.5 min), Memory 512MB

## What We've Tried

### 1. Disabled Interface Retry Logic ✅
**File**: `src/lambdas/interface/core/validator_invoker.py`
**Change**: Set `max_retries=0` (line 159)
**Result**: Still seeing duplicates - retries weren't from this code path

### 2. Added Frontend Guard Flag ✅
**File**: `frontend/perplexity_validator_interface2.html`
**Added**: `globalState.processingInProgress` flag to prevent duplicate button clicks
**Result**: Frontend only clicks once, but validators still duplicate

### 3. Disabled Validator SQS Event Source ✅
**Action**: Disabled `perplexity-validator-async-queue-dev` event source mapping
**Command**: `lambda_client.update_event_source_mapping(UUID='bc66c073...', Enabled=False)`
**Result**: Still seeing duplicates - validators weren't being triggered by this queue

### 4. Added Logging to SYNC Validation Path ✅
**File**: `src/lambdas/interface/handlers/background_handler.py` (lines 3350-3364)
**Added**: Logging for SYNC validator invocation timing
**Result**: Discovered 136-second gap in interface logs during validator execution

### 5. Added SQS Deduplication ✅
**Files**:
- `src/lambdas/interface/core/sqs_service.py` - Added deduplication_id to messages
- `src/lambdas/interface/handlers/background_handler.py` - Added DynamoDB check for duplicates
**Result**: Still retriggering - deduplication not preventing the issue

## Key Discoveries

### 1. Different Code Paths
- **Preview**: Uses `invoke_validator_lambda()` function (has retry logic control)
- **Full Validation**: Uses direct `lambda_client.invoke()` in SYNC path (no retry logic)

### 2. Smart Delegation System
- Decides between ASYNC (>10 min) and SYNC (≤10 min) processing
- Small tests (3-10 rows) use SYNC path
- SYNC path bypasses the `invoke_validator_lambda()` function entirely

### 3. Interface Lambda Gaps
- 136-second gap in logs during SYNC validator call
- No timeout errors visible
- No error logs during the gap

### 4. SQS Behavior
- NOT visibility timeout (that's 16 minutes, seeing ~1 minute retries)
- `FunctionResponseTypes: []` means immediate retry on Lambda error
- But no errors found in logs

## Remaining Questions

1. **Why are there multiple interface Lambda invocations?**
   - At 11:00:23, 11:02:26-28, 11:04:03
   - But only one shows processing for our session

2. **Is SQS delivering multiple messages initially?**
   - Could the frontend be sending multiple requests?
   - Is there a race condition in message sending?

3. **Why the 60-second retry pattern?**
   - Not matching any configured timeout
   - Not matching SQS visibility timeout

4. **Are validators being triggered directly?**
   - Not through interface Lambda?
   - Some other service invoking them?

## Next Investigation Steps

### 1. Track SQS Message Flow
```python
# Add comprehensive SQS message tracking
- Log when message is sent to queue (with MessageId)
- Log when message is received from queue (with MessageId, ReceiptHandle)
- Log when message processing starts/ends
- Log if/when message is deleted from queue
```

### 2. Check for Lambda Concurrent Executions
```python
# Check if interface Lambda is running multiple times concurrently
- Add instance ID to all logs: str(uuid.uuid4())[:8]
- Log at start: "Instance {id} starting processing for session {session_id}"
- Track if same session processed by multiple instances
```

### 3. Verify SQS Message Deletion
```python
# Explicitly check if SQS messages are being deleted
- Log before delete_message call
- Log after successful deletion
- Check if Lambda is returning success but message not deleted
```

### 4. Check CloudWatch Metrics
```bash
# Check Lambda concurrent executions metric
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ConcurrentExecutions \
  --dimensions Name=FunctionName,Value=perplexity-validator-interface-dev \
  --start-time 2025-10-11T15:00:00Z \
  --end-time 2025-10-11T15:10:00Z \
  --period 60 \
  --statistics Maximum

# Check SQS message metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/SQS \
  --metric-name ApproximateNumberOfMessagesVisible \
  --dimensions Name=QueueName,Value=perplexity-validator-standard-queue-dev
```

### 5. Add Request Tracing
```python
# Add X-Ray tracing or custom correlation ID
- Generate trace_id at entry point
- Pass through all function calls
- Log with every operation
- Track the full request lifecycle
```

### 6. Check for External Triggers
```python
# Verify no other services are invoking validators
- Check CloudTrail for InvokeFunction calls
- Check if any other Lambda has permissions to invoke validator
- Check if API Gateway is triggering multiple times
```

### 7. Implement Circuit Breaker
```python
# Add temporary circuit breaker to prevent duplicates
- Store "processing_started" timestamp in DynamoDB
- If another request comes within 5 minutes for same session, reject
- Log all rejections to identify source
```

### 8. Monitor Lambda Cold Starts
```python
# Check if cold starts are causing issues
- Log if Lambda is cold start: "COLD_START" if '/tmp' is empty
- Check if cold starts correlate with duplicates
```

## Hypothesis Priority

1. **SQS message not being deleted** after successful processing
   - Lambda returns success but message stays in queue
   - Queue redelivers after some internal retry timer

2. **Multiple SQS messages sent initially**
   - Race condition in frontend or interface
   - Multiple API Gateway invocations

3. **Lambda partial failure**
   - Processing succeeds but response fails
   - SQS interprets as failure and retries

4. **CloudWatch Events or other trigger**
   - Another service triggering validators directly
   - Scheduled retry mechanism we're not aware of

## Immediate Action Plan

1. **Deploy enhanced logging** to track full message lifecycle
2. **Monitor CloudWatch metrics** during next test
3. **Add correlation IDs** to track request flow
4. **Check CloudTrail** for all Lambda invocations
5. **Test with longer running validation** to see if pattern changes