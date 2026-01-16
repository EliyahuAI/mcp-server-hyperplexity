# Perplexity Search Latency Diagnostic

**Date:** 2026-01-15
**Issue:** ~2 minute turnaround times for Perplexity searches in The Clone
**Status:** Root cause narrowed down - NOT the Perplexity API itself

---

## Problem Statement

Production reports showed search execution taking **113.51 seconds** for a single query:

```
Search Execution started: 19:21:34
Search Results Summary:   19:23:27
Duration: 113.51s (for 1 query, 10 results)
```

Initial suspicion was that `max_tokens_per_page` or `max_results` parameters were causing slowness.

---

## Diagnostic Tests Created

Two test scripts were created in `src/the_clone/tests/`:

### 1. `test_latency_diagnostic_standalone.py`
General diagnostic testing:
- max_tokens_per_page impact (None, 512, 1024, 2048)
- max_results impact (5, 10, 20, 30)
- Concurrency impact (1, 5, 10, 15, 25 parallel)
- Combined worst-case scenario

### 2. `test_production_query_latency.py`
Production-specific diagnostic:
- Exact production query replication
- Medical/oncology query testing
- Sequential vs parallel comparison
- Rate limiting pattern detection

---

## Test Results (Local Environment)

### Exact Production Query Test
```
Query: "nivolumab chemotherapy NSCLC perioperative"
Settings: max_results=10, max_tokens_per_page=2048

Run 1: 0.31s | 10 results | 31,169 bytes
Run 2: 0.27s | 10 results | 34,455 bytes
Run 3: 0.26s | 10 results | 34,455 bytes

Average: 0.28s
```

### Sequential Medical Queries (5 queries)
```
Query 1: 0.28s | 34,455 bytes
Query 2: 0.31s | 77,393 bytes
Query 3: 0.32s | 58,505 bytes
Query 4: 0.31s | 62,489 bytes
Query 5: 0.40s | 79,822 bytes

Total sequential time: 1.62s
Average: 0.32s per query
```

### Parallel Medical Queries (5 queries)
```
Total batch time: 0.34s
Effective throughput: 14.88 req/s
```

### Rate Limiting Pattern (10 rapid requests)
```
First half avg:  0.31s
Second half avg: 0.30s
Result: No throttling pattern detected
```

### max_tokens_per_page Impact
```
512:  0.26s | 19,556 snippet chars
1024: 0.38s | 29,234 snippet chars
2048: 0.27s | 31,632 snippet chars
4096: 0.31s | 37,780 snippet chars

Result: Minimal impact on latency
```

---

## Key Finding

| Environment | Latency | Notes |
|-------------|---------|-------|
| **Local** | 0.28s | Same query, same settings |
| **Production (Lambda)** | 113.51s | 400x slower |

**The Perplexity API is NOT the bottleneck.** The API responds in under 1 second consistently.

---

## Root Cause Analysis

The 113s delay in production is NOT caused by:
- ❌ `max_tokens_per_page` settings
- ❌ `max_results` parameter
- ❌ Query complexity (medical/oncology queries)
- ❌ Perplexity API rate limiting (from single requests)

Likely causes (to investigate):

| Possible Cause | Description |
|----------------|-------------|
| **Concurrent row validation** | If multiple table rows are validated simultaneously, they share the 15-slot semaphore. 16+ searches would cause queuing. |
| **Different API key/account** | Production might use a different key with lower rate limits |
| **Lambda network latency** | Lambda → Perplexity routing from certain AWS regions |
| **429 retry accumulation** | If rate limited, exponential backoff adds: 1s + 2s + 4s + 8s + 16s = 31s per retry cycle |
| **Semaphore starvation** | If global semaphore is shared across Lambda invocations in warm containers |

---

## Production Report Breakdown

From the analyzed report, the full pipeline timing was:

| Step | Time | % of Total |
|------|------|------------|
| Initial Decision | 17.86s | 7% |
| Memory Recall | 10.98s | 4% |
| **Search** | **113.51s** | **45%** |
| Triage | 39.64s | 16% |
| Extraction | 37.36s | 15% |
| Synthesis | 33.58s | 13% |
| **Total** | **254.6s** | 100% |

The Search step alone accounts for 45% of total time.

---

## Root Cause Identified

**The actual bottleneck: Parallel S3 writes to agent_memory.json**

After implementation, the real problem was discovered:
- Multiple parallel agents writing `agent_memory.json` to S3 after each search
- File size: 50+ MB (with pretty-printing)
- S3 write latency: 2-6 seconds per write
- Race conditions: Last write wins, data loss
- Total overhead: N agents × 5s per write = massive latency

**Solution Implemented:** RAM-based memory cache (see `search_memory_cache.py`)

---

## Recommended Next Steps

1. **Check Lambda CloudWatch logs** for:
   - `[PERPLEXITY_HIGH_429]` warnings
   - `[PERPLEXITY] Rate limit 429` retry messages
   - `[PERPLEXITY_SLOW]` slow search alerts
   - `[MEMORY] Backed up to S3` frequency (should be rare)

2. **Check concurrent usage**:
   - How many table rows are validated simultaneously?
   - Are multiple Lambda invocations sharing rate limits?

3. **Migrate to RAM cache** (see `docs/MEMORY_CACHE_INTEGRATION.md`):
   - Replace `SearchMemory.restore()` with `MemoryCache.get()`
   - Replace `memory.store_search()` with `MemoryCache.store_search()`
   - Add `MemoryCache.flush()` at batch end
   - Expect 10x speedup for parallel execution

4. **Test from Lambda environment**:
   - Deploy a test function to replicate production conditions
   - Compare Lambda vs local network latency to Perplexity

---

## Code Locations

- Search client: `src/the_clone/perplexity_search.py`
- Search manager: `src/the_clone/search_manager.py`
- Memory cache: `src/the_clone/search_memory_cache.py` (NEW - RAM-based cache)
- Search memory: `src/the_clone/search_memory.py` (modified with no-backup methods)
- Semaphore limit: `_SEMAPHORE_LIMIT = 15` (line 27 of perplexity_search.py)
- Diagnostic tests: `src/the_clone/tests/test_*_latency*.py`
- Integration guide: `docs/MEMORY_CACHE_INTEGRATION.md`

---

## Configuration Reference

Current strategy settings (`strategy_config.json`):

| Strategy | max_tokens_per_page | max_results |
|----------|---------------------|-------------|
| targeted | 512 | default |
| focused_deep | 2048 | default |
| survey | 512 | default |
| comprehensive | 2048 | default |
| findall_breadth | 512 | 20 |
| extraction | 8192 | 10 |

---

## Conclusion

The Perplexity Search API is fast (~0.3s per query locally). The ~2 minute latency in production is caused by environmental factors (Lambda, concurrent usage, or rate limiting from aggregate load) rather than API parameters.

Further investigation should focus on Lambda logs and concurrent validation patterns.
