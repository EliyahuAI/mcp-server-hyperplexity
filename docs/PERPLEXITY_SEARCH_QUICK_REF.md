# Perplexity Search API - Quick Reference

## TL;DR - Optimal Configuration

```python
MAX_RESULTS = 20       # Maximum safe value (hard limit at 20)
BATCH_SIZE = 10        # Concurrent requests per batch
MAX_RETRIES = 5        # Retry attempts for 429 errors
BASE_DELAY = 1.0       # Exponential backoff starting delay
```

**Expected Performance**:
- ~150-200 results per batch
- ~1.5-2.0 seconds per batch
- ~80-130 results/second sustained
- $0.005 per request ($5 per 1,000)

---

## Rate Limit Cheat Sheet

| Concurrent Requests | 429 Errors | Success with Retries | QPS | Recommendation |
|---------------------|------------|----------------------|-----|----------------|
| 1-20 | 0-2 | 100% | 15-30 | ✓ **Safe** |
| 25-30 | 5-15 | 100% | 8-10 | ⚠ Moderate |
| 50+ | 30+ | 95-100% | 5-15 | ⚠ Heavy limiting |

**Sweet Spot**: 10-15 concurrent requests per batch

---

## max_results Limits

```
max_results = 1-20:  ✓ Works (recommended: 10-20)
max_results = 25+:   ✗ Returns 400 error (hard limit)
```

**Key Finding**: Rate limit is per-REQUEST, not per-RESULT
→ Always use `max_results=20` to maximize data return

---

## Quick Comparison

### Strategy Performance (30 queries)

| Strategy | Time | Speedup | 429s | Use When |
|----------|------|---------|------|----------|
| Sequential | 10.8s | 1.0x | 0 | Never |
| Batches of 10 | 1.7s | **6.2x** | 0 | **Production ✓** |
| All concurrent | 2.8s | 3.9x | 9 | Quick tasks |

---

## Minimal Working Example

```python
import aiohttp
import asyncio

async def search(query, max_results=20, retries=5):
    url = "https://api.perplexity.ai/search"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {"query": query, "max_results": max_results}

    for attempt in range(retries + 1):
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as r:
                if r.status == 200:
                    return await r.json()
                elif r.status == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
    raise Exception("Retries exhausted")

# Usage
results = await search("AI developments 2024")
```

---

## Production Template

```python
async def batch_search(queries, batch_size=10):
    all_results = []
    for i in range(0, len(queries), batch_size):
        batch = queries[i:i+batch_size]
        tasks = [search(q, max_results=20) for q in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_results.extend([r for r in results if not isinstance(r, Exception)])
    return all_results
```

---

## Cost Calculator

| Queries | Cost | Results (max_results=20) | Cost per Result |
|---------|------|--------------------------|-----------------|
| 10 | $0.05 | ~200 | $0.00025 |
| 100 | $0.50 | ~2,000 | $0.00025 |
| 1,000 | $5.00 | ~20,000 | $0.00025 |
| 10,000 | $50.00 | ~200,000 | $0.00025 |

**Compare to Sonar API**: $5 + $1-15/M tokens = **much more expensive**

---

## Retry Logic Essentials

**Exponential Backoff Schedule**:
```
Attempt 1: Immediate
Attempt 2: 1s delay
Attempt 3: 2s delay
Attempt 4: 4s delay
Attempt 5: 8s delay
Attempt 6: 16s delay
```

**Success Rate** (from testing):
- 50 concurrent: 100% success with retries
- 100 concurrent: 100% success with retries
- 200 concurrent: 95% success with retries

---

## Common Pitfalls

❌ **Don't**:
```python
# DON'T: max_results too high
search(query, max_results=50)  # 400 error

# DON'T: No retry logic
search(query)  # Will fail on 429s

# DON'T: Sequential processing
for q in queries:
    await search(q)  # 6x slower
```

✓ **Do**:
```python
# DO: Use max_results=20
search(query, max_results=20)

# DO: Implement retries
search(query, max_retries=5)

# DO: Batch processing
asyncio.gather(*[search(q) for q in batch])
```

---

## Response Format

```json
{
  "results": [
    {
      "title": "Article Title",
      "url": "https://example.com",
      "snippet": "Relevant text...",
      "date": "2025-03-20",
      "last_updated": "2025-09-19"
    }
  ]
}
```

---

## Recency Filters

```python
# Filter by timeframe
search(query, recency_filter="day")    # Last 24 hours
search(query, recency_filter="week")   # Last 7 days
search(query, recency_filter="month")  # Last 30 days
search(query, recency_filter=None)     # All time
```

---

## Files Reference

- **Full Guide**: `docs/PERPLEXITY_SEARCH_API_GUIDE.md`
- **Production Client**: `perplexity_search.py`
- **Test Scripts**:
  - `test_rate_limits.py` - Rate limit stress tests
  - `test_batching_simple.py` - Batching optimization tests
  - `test_perplexity_simple.py` - Basic functionality tests

---

## When to Use Search API vs Sonar

### Use Search API When:
- You want raw search results
- You'll process results with your own LLM (e.g., DeepSeek)
- Cost is a concern
- You need control over citations

### Use Sonar API When:
- You want synthesized answers
- You need immediate LLM responses
- You're okay with higher costs ($5 + $1-15/M tokens)

**Typical Use Case**: Search API → DeepSeek on Bedrock for cost-effective research with reasoning

---

## Known Issues

### `KeyError(<loop_id>)` — searches silently fail under concurrency

**Symptom**: `[SEARCH_MANAGER] Search N failed: 139892102495248` (a large integer that looks
like a memory address). All searches in a batch fail with the same number.

**What it is**: `str(KeyError(id(loop)))` prints just the integer — no "KeyError:" prefix.
The value is `id(asyncio.get_running_loop())`, i.e. the memory address of the event loop object.
aiohttp's internal connector manages connections in a dict keyed by `id(loop)`, and when a
`ClientSession` is created and destroyed rapidly (a new session per request, 15 concurrent),
a race in that internal dict raises `KeyError(loop_id)`.

**Root cause**: `perplexity_search.py` creates a fresh `aiohttp.ClientSession` for every
single search request inside `batch_search`. aiohttp recommends one long-lived session per
application/batch; creating 15 sessions simultaneously against the same event loop triggers
the internal connector race.

**Current status**: Non-fatal — `asyncio.gather(return_exceptions=True)` catches the
exceptions and returns them as result items; `search_manager` logs them and continues.
Searches that fail this way return no results for those queries (the clone proceeds with
whatever it has).

**Proper fix**: Refactor `PerplexitySearchClient` to hold a single `aiohttp.ClientSession`
created lazily on first use (keyed to the current event loop), reused across all requests in
`batch_search`, and closed only at explicit teardown. The per-loop semaphore logic in
`_get_semaphore()` already does the right thing; the session should follow the same pattern.

**Related files**: `src/the_clone/perplexity_search.py` lines 152–270 (`search` method),
`src/the_clone/search_manager.py` lines 287–328 (`execute_searches`).

---

Last updated: 2026-02-23
