# Search Memory - Lambda Integration Guide

## Overview

This guide shows how to integrate the Search Memory system into AWS Lambda functions.

## Prerequisites

**No new packages required!** The memory system uses only:
- Standard Python libraries (asyncio, json, hashlib, etc.)
- Existing project modules (ai_api_client, UnifiedS3Manager)

## Session Context Requirements

The memory system needs:
```python
session_id: str   # Unique session identifier
email: str        # User email (for S3 path)
s3_manager        # UnifiedS3Manager instance
```

## Integration Pattern: Pass Through Event

### Step 1: Frontend Sends Session Context

**Example Event Payload:**
```json
{
  "action": "query_clone",
  "query": "What are Python 3.12 features?",
  "session_id": "session_20251230_143022_abc123",
  "email": "user@example.com",
  "config": {
    "provider": "deepseek",
    "breadth": "broad"
  }
}
```

### Step 2: Lambda Handler Extracts Context

**Example Lambda Handler:**
```python
# lambda_function.py

import asyncio
from the_clone.the_clone import TheClone2Refined
from lambdas.interface.core.unified_s3_manager import UnifiedS3Manager

async def handle_clone_query(event: dict) -> dict:
    """
    Handle clone query with optional memory support.

    Args:
        event: Lambda event with query, session_id, email

    Returns:
        Clone result with metadata
    """
    # Extract parameters
    query = event.get('query')
    session_id = event.get('session_id')  # Optional
    email = event.get('email')            # Optional

    # Validate required fields
    if not query:
        raise ValueError("Missing required field: query")

    # Initialize managers
    s3_manager = UnifiedS3Manager()
    clone = TheClone2Refined()

    # Determine if memory is available
    has_session_context = bool(session_id and email)

    # Run query with optional memory
    result = await clone.query(
        prompt=query,
        session_id=session_id if has_session_context else None,
        email=email if has_session_context else None,
        s3_manager=s3_manager if has_session_context else None,
        use_memory=has_session_context,  # Auto-enable if context available
        provider=event.get('provider', 'deepseek'),
        breadth=event.get('breadth'),
        depth=event.get('depth')
    )

    # Log memory usage
    if has_session_context:
        memory_stats = result['metadata'].get('memory_stats', {})
        logger.info(
            f"[MEMORY] Session {session_id}: "
            f"decision={memory_stats.get('search_decision')}, "
            f"confidence={memory_stats.get('memory_confidence', 0):.2f}"
        )

    return result

def lambda_handler(event, context):
    """AWS Lambda handler."""
    try:
        result = asyncio.run(handle_clone_query(event))
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
    except Exception as e:
        logger.error(f"Error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

## Current Lambda Status

### Validation Lambda
**Current:** Does NOT use the_clone (uses direct API calls)
**Memory Support:** Not applicable yet
**Action:** No changes needed now

### Interface Lambda (Actions)
**Current:** May use the_clone in some actions
**Memory Support:** Add session_id/email to event payload
**Action:** Update event schema to include session context

### Table Maker Lambda
**Current:** Has session context available
**Memory Support:** ✅ Ready to use
**Action:** Pass session_id/email to clone.query() if used

## Example: Table Maker Integration

```python
# In table_maker/execution.py or conversation.py

async def research_with_clone(query: str, session_id: str, email: str) -> dict:
    """Use the_clone for research with memory support."""

    from the_clone.the_clone import TheClone2Refined
    from lambdas.interface.core.unified_s3_manager import UnifiedS3Manager

    s3_manager = UnifiedS3Manager()
    clone = TheClone2Refined()

    # The_clone with memory enabled
    result = await clone.query(
        prompt=query,
        session_id=session_id,    # Already available in Table Maker!
        email=email,              # Already available in Table Maker!
        s3_manager=s3_manager,
        use_memory=True           # Enable memory for multi-turn research
    )

    return result
```

## Frontend Changes Needed

### Current Event Structure (Example)
```json
{
  "action": "start_validation",
  "config_id": "config_123",
  "mode": "preview"
}
```

### Updated Event Structure (With Session Context)
```json
{
  "action": "start_validation",
  "config_id": "config_123",
  "mode": "preview",
  "session_id": "session_20251230_143022_abc123",  // NEW
  "email": "user@example.com"                     // NEW
}
```

**Note:** Frontend can extract these from:
- Current session state (if tracked client-side)
- API response from session creation
- User authentication context

## Graceful Degradation

The system gracefully handles missing session context:

```python
# If session_id or email missing
result = await clone.query(
    prompt=query,
    session_id=None,      # Memory won't work
    email=None,           # Memory won't work
    s3_manager=None,      # Memory won't work
    use_memory=True       # Will be ignored (no context)
)

# Logs will show:
# [CLONE] Memory not available (missing session_id, email, or s3_manager)
# [CLONE] Continuing with full search...
```

**Result:** Query still works, just without memory optimization.

## Testing Lambda Integration Locally

```python
# test_lambda_with_memory.py

import asyncio
from lambdas.interface.actions.some_action import lambda_handler

async def test():
    event = {
        'action': 'clone_query',
        'query': 'What are Python 3.12 features?',
        'session_id': 'test_session_001',
        'email': 'test@example.com',
        'provider': 'deepseek'
    }

    result = lambda_handler(event, None)

    # Check memory usage
    memory_stats = result['metadata']['memory_stats']
    print(f"Memory enabled: {memory_stats['memory_enabled']}")
    print(f"Search decision: {memory_stats.get('search_decision', 'N/A')}")

if __name__ == '__main__':
    asyncio.run(test())
```

## Deployment Checklist

When integrating memory into a lambda:

- [x] **No new packages** required in deployment
- [ ] **Event schema** updated to include session_id and email
- [ ] **Frontend** sends session context with requests
- [ ] **Lambda handler** extracts session_id and email from event
- [ ] **Error handling** for missing session context (graceful degradation)
- [ ] **Logging** to track memory usage and cost savings
- [ ] **Testing** with and without session context

## Performance Impact on Lambda

**Cold Start:**
- Memory adds: **~100ms** (loading from S3)
- Total cold start: Same as before + 100ms

**Warm Execution:**
- Memory recall: **~500-750ms** (3-stage process)
- Search saved: **~1-2s** (Perplexity API latency)
- **Net improvement: ~500ms-1s faster** on memory hits

**Memory Footprint:**
- Memory class: **~500KB** for 100 queries
- Lambda limit: 10GB (plenty of room)

## Cost Tracking in Lambda

The memory system automatically tracks costs in metadata:

```python
result = await clone.query(...)

# Extract for DynamoDB logging
metadata = result['metadata']
costs_by_provider = metadata['cost_by_provider']

# Memory recall cost tracked under 'gemini'
recall_cost = costs_by_provider.get('gemini', {}).get('cost', 0)

# Search cost (if not skipped)
search_cost = costs_by_provider.get('perplexity', {}).get('cost', 0)

# Log to DynamoDB runs table
await save_run_metrics({
    'session_id': session_id,
    'recall_cost': recall_cost,
    'search_cost': search_cost,
    'search_skipped': metadata['memory_stats']['search_decision'] == 'skip'
})
```

## Monitoring Recommendations

Track these metrics in DynamoDB or CloudWatch:

1. **Memory hit rate**: % of queries that skip/supplement search
2. **Cost savings**: Total $ saved from skipped searches
3. **Average confidence**: Mean confidence across recalls
4. **Verification rate**: % of recalls that run verification
5. **Session memory size**: Average queries stored per session

## Summary

**For immediate use:**
- ✅ No deployment changes needed (no new packages)
- ✅ Memory works out of the box if session context provided
- ✅ Graceful fallback if session context missing

**For production integration:**
- Update frontend to send session_id and email in events
- Extract session context in lambda handlers
- Pass to clone.query() to enable memory
- Monitor memory hit rate and cost savings
