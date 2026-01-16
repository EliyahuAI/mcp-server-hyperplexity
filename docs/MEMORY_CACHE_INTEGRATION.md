# Memory Cache Integration Guide

**Problem Solved:** Parallel agents writing to S3 simultaneously causes race conditions, data loss, and massive latency (~2-5 seconds per write × N agents).

**Solution:** In-process RAM cache with single S3 write at batch end.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│             Lambda Invocation (single process)          │
│                                                         │
│   ┌─────────────────────────────────────────────────┐  │
│   │      _MEMORY_CACHE (module-level dict)          │  │
│   │                                                  │  │
│   │   session_123: SearchMemory                     │  │
│   │     ├─ queries: {...}                           │  │
│   │     └─ indexes: {...}                           │  │
│   │                                                  │  │
│   └──────────▲──────────▲──────────▲────────────────┘  │
│              │          │          │                    │
│         ┌────┴───┐ ┌────┴───┐ ┌────┴───┐               │
│         │Agent 1 │ │Agent 2 │ │Agent 3 │               │
│         │(async) │ │(async) │ │(async) │               │
│         │        │ │        │ │        │               │
│         │ read() │ │ read() │ │ read() │  ← 0ms        │
│         │store() │ │store() │ │store() │  ← 0ms        │
│         └────────┘ └────────┘ └────────┘               │
│                                                         │
│   All agents share SAME memory object in RAM           │
│   Zero S3 calls during execution                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
                  MemoryCache.flush()
                  ONE S3 write (1-5s)
```

**Speed Improvement:**
- Before: N agents × 5s per S3 write = 5N seconds
- After: 0ms during execution + 1 write at end = ~5 seconds total

**Cost:** Same ($0 - same number of S3 operations)

---

## Integration Points

### 1. The Clone Integration

Replace direct `SearchMemory` usage with `MemoryCache`:

```python
# the_clone.py

from the_clone.search_memory_cache import MemoryCache

class TheClone:
    async def query(self, prompt, session_id, email, s3_manager, use_memory=True, ...):

        # Get shared memory from cache (loads from S3 if not cached)
        if use_memory and session_id and email and s3_manager:
            memory = MemoryCache.get(session_id, email, s3_manager, self.ai_client)
        else:
            memory = None

        # ... memory recall step ...

        # Store search results (RAM only, no S3)
        if memory:
            for term, results in search_results.items():
                MemoryCache.store_search(
                    session_id=session_id,
                    search_term=term,
                    results=results,
                    parameters=search_params,
                    strategy=strategy_name
                )

        # DON'T flush here - let batch controller do it

        return result
```

**Key Changes:**
- Use `MemoryCache.get()` instead of `SearchMemory.restore()`
- Use `MemoryCache.store_search()` instead of `memory.store_search()`
- Remove all `await memory.backup()` calls
- Let batch controller call `MemoryCache.flush()` at end

---

### 2. Table Maker Integration

Store extracted tables to RAM cache:

```python
# table_maker/execution.py

from the_clone.search_memory_cache import MemoryCache

async def execute_table_extraction(session_id, email, s3_manager, ...):

    # Get shared memory (loads if needed)
    memory = MemoryCache.get(session_id, email, s3_manager)

    # Extract table
    table_markdown = extract_table_from_url(url)

    # Store to RAM cache (no S3 write)
    MemoryCache.store_url_content(
        session_id=session_id,
        url=url,
        content=table_markdown,
        title=f"Table from {url}",
        source_type="table_extraction",
        metadata={
            "rows_count": row_count,
            "columns_found": columns
        }
    )

    # DON'T flush here - let batch controller do it
```

---

### 3. Config Copy Integration

When copying config, load copied memory into RAM cache:

```python
# copy_config.py or use_config_by_id.py

from the_clone.search_memory_cache import MemoryCache

async def handle_config_match_copy(
    source_session_id: str,
    target_session_id: str,
    email: str,
    s3_manager,
    ai_client=None
):
    """Copy config and load memory into RAM cache."""

    # 1. Copy the agent_memory.json file in S3
    source_key = f"{s3_manager.get_session_path(email, source_session_id)}agent_memory.json"
    target_key = f"{s3_manager.get_session_path(email, target_session_id)}agent_memory.json"

    try:
        s3_manager.s3_client.copy_object(
            Bucket=s3_manager.bucket_name,
            CopySource={'Bucket': s3_manager.bucket_name, 'Key': source_key},
            Key=target_key
        )
        logger.info(f"[CONFIG_COPY] Copied agent_memory.json: {source_session_id} -> {target_session_id}")

        # 2. CRITICAL: Load copied memory into RAM cache immediately
        memory = MemoryCache.load_from_copy(
            target_session_id=target_session_id,
            source_session_id=source_session_id,
            email=email,
            s3_manager=s3_manager,
            ai_client=ai_client
        )

        query_count = len(memory._memory.get('queries', {}))
        logger.info(f"[CONFIG_COPY] Loaded {query_count} queries into RAM cache")

    except Exception as e:
        logger.warning(f"[CONFIG_COPY] Failed to copy/load memory: {e}")
        # Continue without memory
```

**Why This Matters:**
- Without this, agents would load old memory from S3 (before copy)
- With this, agents immediately see the copied memory

---

### 4. Batch Controller Integration

Add flush at end of batch:

```python
# Lambda handler or batch controller

from the_clone.search_memory_cache import MemoryCache

async def process_batch(rows, session_id, email, s3_manager, ...):
    """Process multiple rows in parallel."""

    try:
        # Process all rows in parallel (each may use memory)
        tasks = [
            process_single_row(row, session_id, email, s3_manager, ...)
            for row in rows
        ]
        results = await asyncio.gather(*tasks)

    finally:
        # CRITICAL: Flush memory at batch end
        if session_id:
            try:
                await MemoryCache.flush(session_id)
                logger.info(f"[BATCH] Flushed memory for session {session_id}")
            except Exception as e:
                logger.error(f"[BATCH] Failed to flush memory: {e}")
                # Don't fail the batch over flush failure

    return results
```

**Or flush all sessions:**
```python
finally:
    # Flush ALL sessions that were modified
    await MemoryCache.flush_all()
```

---

## Backup Check Pattern

The cache automatically loads from S3 if memory is needed but not cached:

```python
# Agent needs memory
memory = MemoryCache.get(session_id, email, s3_manager, ai_client)

# MemoryCache.get() will:
# 1. Check if session_id in cache
# 2. If NOT: Load from S3 synchronously (backup check)
# 3. If S3 file missing: Initialize empty memory
# 4. Return memory instance (now cached for other agents)
```

**This handles:**
- Config copy where memory was copied but not loaded
- Mid-batch agents joining late and needing memory
- Lambda warm starts where cache was cleared

---

## Error Handling

### Store Before Get

```python
# BAD - will raise ValueError
MemoryCache.store_search(session_id, ...)  # Session not in cache!

# GOOD
memory = MemoryCache.get(session_id, email, s3_manager)  # Load first
MemoryCache.store_search(session_id, ...)  # Now works
```

### Flush Failure

Flush failures should NOT fail the batch:

```python
try:
    await MemoryCache.flush(session_id)
except Exception as e:
    logger.error(f"Memory flush failed, but batch succeeded: {e}")
    # Continue - memory will be stale but batch results are saved
```

---

## Performance Characteristics

### Before (per-search S3 writes)

| Operation | Latency | Parallel (10 agents) |
|-----------|---------|---------------------|
| Store search | ~3-5s | 3-5s × 10 = 30-50s |
| **Total** | **30-50s** | **Race conditions!** |

### After (RAM cache)

| Operation | Latency | Parallel (10 agents) |
|-----------|---------|---------------------|
| Store search | ~0ms | 0ms (all share RAM) |
| Flush at end | ~3-5s | 3-5s (one write) |
| **Total** | **3-5s** | **No conflicts!** |

**Speedup: 10x faster**

---

## Migration Checklist

- [ ] Update `the_clone.py` to use `MemoryCache.get()` instead of `SearchMemory.restore()`
- [ ] Replace `memory.store_search()` with `MemoryCache.store_search()`
- [ ] Remove all `await memory.backup()` calls from The Clone
- [ ] Update Table Maker to use `MemoryCache.store_url_content()`
- [ ] Add `MemoryCache.load_from_copy()` to config copy flow
- [ ] Add `MemoryCache.flush()` or `flush_all()` to batch controller
- [ ] Test parallel execution (10+ rows simultaneously)
- [ ] Verify memory is shared across agents (check logs)
- [ ] Verify single S3 write at batch end (check CloudWatch metrics)

---

## Debugging

### Check Cache Status

```python
from the_clone.search_memory_cache import MemoryCache

# Check if session is cached
is_cached = MemoryCache.is_cached(session_id)

# Check if session has pending writes
is_dirty = MemoryCache.is_dirty(session_id)

# Get detailed stats
stats = MemoryCache.get_stats(session_id)
print(stats)
# {'cached': True, 'dirty': True, 'queries': 15, 'unique_urls': 42}
```

### List All Sessions

```python
# See all cached sessions
cached = MemoryCache.get_all_cached_sessions()
print(f"Cached sessions: {cached}")

# See all dirty sessions
dirty = MemoryCache.get_all_dirty_sessions()
print(f"Dirty sessions: {dirty}")
```

### Clear Cache (Testing)

```python
# Clear specific session
MemoryCache.clear(session_id)

# Clear all sessions
MemoryCache.clear()
```

---

## Lambda Lifecycle

```
Lambda Cold Start
    ↓
┌─────────────────────────────────────┐
│ _MEMORY_CACHE = {}                  │ ← Empty
│ _DIRTY_SESSIONS = set()             │
└─────────────────────────────────────┘
    ↓
First Request (Batch 1)
    ├─ MemoryCache.get(session_A)     → Load from S3, cache
    ├─ Agent 1, 2, 3 process rows     → Store to RAM
    └─ MemoryCache.flush(session_A)   → Write to S3, mark clean
    ↓
┌─────────────────────────────────────┐
│ _MEMORY_CACHE = {session_A: ...}    │ ← Cached
│ _DIRTY_SESSIONS = {}                │ ← Clean
└─────────────────────────────────────┘
    ↓
Second Request (Batch 2) [Warm Start]
    ├─ MemoryCache.get(session_A)     → Use cache (no S3 read!)
    ├─ Agent 1, 2, 3 process rows     → Store to RAM
    └─ MemoryCache.flush(session_A)   → Write to S3
    ↓
Lambda Shutdown (cache cleared automatically)
```

**Warm start benefit:** Second+ requests skip S3 read entirely!

---

## Success Criteria

After implementation, verify:

1. ✅ **Parallel execution works** - 10+ agents run simultaneously without conflicts
2. ✅ **Zero S3 writes during execution** - CloudWatch shows no `PutObject` during batch
3. ✅ **Single S3 write at end** - CloudWatch shows one `PutObject` after batch completes
4. ✅ **Memory is shared** - Logs show `[MEMORY_CACHE] Session X already in cache`
5. ✅ **Config copy loads memory** - After copy, agents see copied queries immediately
6. ✅ **Latency improvement** - Batch time reduced by 20-40 seconds
7. ✅ **No data loss** - All searches/tables stored correctly in final memory file

---

## Rollback Plan

If issues occur, revert to direct SearchMemory usage:

1. Use `SearchMemory.restore()` instead of `MemoryCache.get()`
2. Use `await memory.store_search()` instead of `MemoryCache.store_search()`
3. Keep `await memory.backup()` calls (old behavior)
4. Remove `MemoryCache.flush()` calls

The old pattern still works - MemoryCache is additive, not replacing core functionality.
