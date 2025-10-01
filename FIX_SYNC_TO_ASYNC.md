# Sync-to-Async Transition Issue

## Problem
A **sync validation** (not delegated from interface) is trying to trigger an async continuation, but it doesn't have `complete_payload_s3_key` because it was never stored in S3.

## Log Evidence
```
[CONTINUATION] Reusing original payload: None
[DIRECT_INVOKE] Triggered continuation #1 for session session_demo_20251001_160301_b3e369c4, status: 202
[WARNING] [ASYNC_PAYLOAD] Async delegation request missing complete_payload_s3_key
```

## Root Cause
The continuation logic assumes async mode where payload is already in S3. But sync validations don't have this.

## Solutions

### Option 1: Save Payload Before First Continuation (RECOMMENDED)
When a sync validation needs to continue, save the payload to S3 first:
```python
if not original_payload_s3_key:
    # This is sync mode transitioning to async
    # Save current state to S3
    payload_s3_key = f"{results_path}/initial_payload_{timestamp}.json"
    payload = {
        'validation_data': event.get('validation_data'),
        'config': event.get('config'),
        'session_id': session_id,
        ...
    }
    s3_client.put_object(Bucket=s3_bucket, Key=payload_s3_key, Body=json.dumps(payload))
    original_payload_s3_key = payload_s3_key
```

### Option 2: Disable Continuation for Sync Mode
Only allow continuations for truly async-delegated validations:
```python
if not event.get('complete_payload_s3_key'):
    logger.warning("Sync validation cannot trigger continuation - aborting")
    return False
```

### Option 3: Pass Inline Data (Not Recommended)
Pass validation_data directly in continuation event - but this hits Lambda 256KB payload limit.

## Recommendation
**Use Option 1**: Save payload to S3 on first continuation from sync mode. This allows seamless sync→async transition.
