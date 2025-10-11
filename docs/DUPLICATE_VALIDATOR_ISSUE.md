# Duplicate Validator Invocation Issue

## Problem Description

When using **direct Lambda invocation** (`lambda_client.invoke()`) with `InvocationType='RequestResponse'` for SYNC full validations, we observed multiple validator Lambda containers being triggered for a single validation request. This manifested as:

- **AI call counter restarting**: Frontend would show "AI Call 45/50" then suddenly "AI Call 1/50" again
- **Multiple validators running in parallel**: 2-4 validator instances processing the same session
- **Timing pattern**: New validators appeared approximately 60-120 seconds apart
- **Completion behavior**: First validator would complete (50/50) BEFORE second validator started

## Key Observations

1. **Not from retry logic**: Interface Lambda's `max_retries=2` was initially suspected, but setting it to `0` didn't resolve the issue
2. **Not from frontend**: Frontend guard flags confirmed only one button click per validation
3. **Not from SQS redelivery**: Only ONE SQS message was sent to `standard-queue-dev` per validation
4. **Not from continuation logic**: Validators showed `type=SYNC, mode=INITIAL` (not continuations)
5. **Started after parallel processing changes**: Issue appeared after implementing true parallel row processing (25 threads)

## What We Tried

### 1. Disabled Interface Retry Logic ✗
**File**: `src/lambdas/interface/core/validator_invoker.py`
**Change**: Set `max_retries=0` (line 159)
**Result**: Duplicates persisted

### 2. Added Frontend Guard Flag ✗
**File**: `frontend/perplexity_validator_interface2.html`
**Added**: `globalState.processingInProgress` flag
**Result**: Frontend only clicked once, but validators still duplicated

### 3. Disabled Validator SQS Event Source ✗
**Action**: Disabled `perplexity-validator-async-queue-dev` event source mapping
**Result**: Duplicates persisted

### 4. Added SQS Message Deduplication ✗
**Files**:
- `src/lambdas/interface/core/sqs_service.py` - Added deduplication_id
- `src/lambdas/interface/handlers/background_handler.py` - DynamoDB duplicate check
**Result**: Duplicates persisted

### 5. Enhanced Logging for Investigation
**Files**: Multiple
**Added**: Instance IDs, SQS MessageIds, timing tracking
**Result**: Confirmed only one SQS message, but multiple validator invocations

## Root Cause (Unresolved)

The exact trigger for duplicate validator invocations remains **unidentified**. Evidence points to:

- **Direct lambda_client.invoke() behavior**: Something in AWS Lambda's internal handling of synchronous invocations
- **Possible timeout/failure retry**: AWS may be internally retrying the invocation despite successful completion
- **EventBridge or CloudWatch Events**: Potential unknown trigger watching validator metrics
- **Lambda concurrency behavior**: Cold starts or container reuse patterns

**Critical observation**: The validators complete successfully (50/50) before duplicates start, ruling out:
- Continuation logic (would exit early)
- Timeout failures (completes normally)
- Response errors (no errors in logs)

## Workaround (Current Solution) ✓

**Instead of using direct `lambda_client.invoke()`**, we now use the **`invoke_validator_lambda()` function** for both preview AND full validation.

### Implementation

**File**: `src/lambdas/interface/handlers/background_handler.py`
**Lines**: 3410-3474

**Before** (problematic):
```python
# Direct invoke - NO retry protection
response = lambda_client.invoke(
    FunctionName=validator_lambda_name,
    InvocationType='RequestResponse',
    Payload=json.dumps(sync_payload, default=str)
)
```

**After** (workaround):
```python
# Use invoke_validator_lambda with retry protection (max_retries=0)
invoke_result = invoke_validator_lambda(
    excel_s3_key=actual_excel_s3_key,
    config_s3_key=actual_config_s3_key,
    max_rows=max_rows,
    batch_size=batch_size,
    S3_CACHE_BUCKET=S3_UNIFIED_BUCKET,
    VALIDATOR_LAMBDA_NAME=VALIDATOR_LAMBDA_NAME,
    preview_first_row=False,  # Full validation
    preview_max_rows=None,
    sequential_call=None,
    session_id=session_id,
    update_callback=None,
    special_request=None,
    validation_history=validation_history
)

# Convert to expected format
validation_results = {
    'statusCode': 200,
    'body': {
        'data': {
            'rows': invoke_result.get('validation_results', {})
        },
        'metadata': invoke_result.get('metadata', {})
    },
    'status': invoke_result.get('status', 'completed'),
    'total_rows': invoke_result.get('total_rows', 0),
    'metadata': invoke_result.get('metadata', {}),
    'total_processed_rows': len(invoke_result.get('validation_results', {})),
    'qc_results': invoke_result.get('qc_results', {}),
    'qc_metrics': invoke_result.get('qc_metrics', {})
}
```

### Why This Works

The `invoke_validator_lambda()` function:
1. **Has explicit retry control**: `max_retries=0` parameter enforced
2. **Consistent behavior**: Same code path for preview and full validation
3. **Better error handling**: Structured exception handling
4. **Proper logging**: `[RETRY_TRACKER]` logs for debugging

## Remaining Risks

⚠️ **This is a workaround, not a root cause fix.**

**Potential future issues**:

1. **AWS behavior changes**: If AWS Lambda internals change, issue could resurface
2. **Different invocation paths**: Other direct `lambda_client.invoke()` calls may have same issue
3. **Performance implications**: Using the function wrapper adds minimal overhead but changes the execution path
4. **Debugging complexity**: Harder to trace if issues occur since we're using indirect invocation

**Locations to watch**:
- Line 3310: ASYNC delegation (direct invoke with `InvocationType='Event'`)
- Line 6040: Config Lambda invoke (different Lambda, may be unaffected)

## Monitoring Recommendations

1. **Watch for counter resets**: Monitor frontend AI call counter behavior
2. **Check validator concurrency**: CloudWatch metric `ConcurrentExecutions` for validator Lambda
3. **Monitor SQS queues**: Ensure no unexpected message buildup in `standard-queue-dev`
4. **Review [RETRY_TRACKER] logs**: Confirm only one invocation per validation request

## Testing Protocol

Before deploying changes to invocation logic:

1. Run validation with 10 rows (small dataset)
2. Monitor frontend counter for resets
3. Check CloudWatch for multiple validator START events (same session)
4. Verify SQS message count matches validator invocations
5. Review timing: second validator should NOT appear ~60s after first

## References

- **Troubleshooting Doc**: `/DUPLICATE_VALIDATOR_TROUBLESHOOTING.md`
- **Main Issue**: Interface Lambda's direct invoke triggers unknown duplicate mechanism
- **Date Implemented**: 2025-10-11
- **Status**: **WORKAROUND ACTIVE** - Root cause unresolved

## Future Investigation

If issue resurfaces or for deeper investigation:

1. **AWS Support case**: Request analysis of Lambda invocation logs at AWS level
2. **X-Ray tracing**: Enable AWS X-Ray to trace full request lifecycle
3. **CloudTrail analysis**: Check for any `InvokeFunction` API calls from unknown sources
4. **Event source mappings**: Audit all Lambda triggers across the account
5. **Lambda layers**: Verify no layer is adding retry logic
6. **VPC configuration**: Check if VPC networking is causing timeout-retry patterns

---

**Last Updated**: 2025-10-11
**Author**: Claude Code (Anthropic)
**Severity**: High (impacts user experience)
**Workaround Status**: Active and stable
