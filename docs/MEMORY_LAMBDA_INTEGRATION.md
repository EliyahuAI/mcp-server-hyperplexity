# Search Memory - Lambda Integration Guide

## Overview

This guide shows how to integrate the Search Memory system into AWS Lambda functions.

## Prerequisites

**No new packages required!** The memory system uses only:
- Standard Python libraries (asyncio, json, hashlib, etc.)
- Existing project modules (ai_api_client, UnifiedS3Manager)

## Lambda Architecture

**Correct Flow:**
```
Frontend
  ↓ (sends session_id, email)
Interface Lambda (has session_id, email)
  ↓ (invokes with payload)
Validation Lambda (receives payload)
  ↓ (uses the_clone for queries - if applicable)
```

**Key Point:** Interface Lambda invokes Validation Lambda (not frontend directly).

## Current Payload Status

**In Interface Lambda → Validation Lambda payload:**
- ✅ `session_id` - Already included (background_handler.py:3280)
- ❌ `email` - Currently NOT included (needs to be added)

**Location:** `src/lambdas/interface/handlers/background_handler.py:3270-3281`

## Quick Fix: Add Email to Validation Payload

### Current Payload (background_handler.py)
```python
complete_validation_payload = {
    "test_mode": False,
    "config": config_data,
    "validation_data": {...},
    "validation_history": validation_history,
    "session_id": session_id  # ✅ Already here
}
```

### Updated Payload (Add Email)
```python
complete_validation_payload = {
    "test_mode": False,
    "config": config_data,
    "validation_data": {...},
    "validation_history": validation_history,
    "session_id": session_id,  # ✅ Already here
    "email": email             # ✅ ADD THIS
}
```

**Note:** The `email` variable is already available in the Interface Lambda context (extracted from frontend request).

## Using Memory in Validation Lambda

Once `email` is added to the payload, the validation lambda can use memory:

```python
# In validation lambda_function.py

def lambda_handler(event, context):
    """Validation lambda handler with memory support."""

    # Extract session context (already in payload!)
    session_id = event.get('session_id')
    email = event.get('email')  # Will be available after payload update

    # If using the_clone for any validation queries
    if needs_clone_query:
        from the_clone.the_clone import TheClone2Refined
        from lambdas.interface.core.unified_s3_manager import UnifiedS3Manager

        s3_manager = UnifiedS3Manager()
        clone = TheClone2Refined()

        result = await clone.query(
            prompt=validation_query,
            session_id=session_id,  # From payload
            email=email,            # From payload (after update)
            s3_manager=s3_manager,
            use_memory=True
        )
```

## Integration Status by Lambda

### Validation Lambda
**Status:** Has `session_id`, needs `email` added to payload
**Action:** Add `email` to validation payload in background_handler.py
**Priority:** Only needed if validation lambda will use the_clone

### Table Maker Lambda
**Status:** Already has full session context
**Action:** Pass `session_id` and `email` when calling clone.query()
**Priority:** High (Table Maker uses the_clone for research)

### Interface Lambda Actions
**Status:** Has full session context
**Action:** Pass session context when using the_clone
**Priority:** Medium (some actions may use the_clone)

## Example: Table Maker Integration (Ready Now)

```python
# In table_maker/row_discovery_stream.py or conversation.py

async def research_topic(query: str, session_id: str, email: str):
    """Research using the_clone with memory."""

    from the_clone.the_clone import TheClone2Refined
    from lambdas.interface.core.unified_s3_manager import UnifiedS3Manager

    # Session context already available in Table Maker!
    s3_manager = UnifiedS3Manager()
    clone = TheClone2Refined()

    result = await clone.query(
        prompt=query,
        session_id=session_id,    # Already available
        email=email,              # Already available
        s3_manager=s3_manager,    # Create instance
        use_memory=True           # Enable memory
    )

    # Memory stats available in result
    memory_stats = result['metadata']['memory_stats']
    logger.info(f"Memory decision: {memory_stats['search_decision']}")

    return result
```

## Memory System Benefits by Context

### Interactive Sessions (High Value)
- Table Maker conversations
- Multi-turn research queries
- Follow-up questions

**Expected savings:** 40-60% cost reduction on follow-up queries

### Batch Processing (Lower Value)
- Validation of many independent rows
- One-time bulk operations

**Expected savings:** Minimal (each row is independent)

## Deployment Checklist

### Phase 1: Table Maker (Immediate)
- [x] No new packages needed
- [ ] Pass session_id and email to clone.query() in Table Maker
- [ ] Test memory recall in multi-turn conversations

### Phase 2: Validation Lambda (Future)
- [ ] Add `email` to validation payload (background_handler.py:3280)
- [ ] Extract email in validation lambda handler
- [ ] Pass to clone.query() if the_clone is used

### Phase 3: Other Interface Actions (As Needed)
- [ ] Identify which actions use the_clone
- [ ] Pass session_id and email to clone.query()
- [ ] Test and monitor memory hit rates

## Summary

**Current State:**
- ✅ `session_id` already in validation payloads
- ❌ `email` needs to be added (1-line change)
- ✅ No deployment package changes needed

**Integration Priority:**
1. **High:** Table Maker (already has email, just pass to clone.query())
2. **Medium:** Interface actions that use the_clone
3. **Low:** Validation lambda (doesn't currently use the_clone)

**Next Steps:**
1. Add `email` to validation payload in background_handler.py:3280
2. Use memory in Table Maker when calling the_clone
3. Monitor memory hit rates and cost savings
