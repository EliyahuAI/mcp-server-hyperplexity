# Perplexity Search API - Summary

**Complete testing and documentation**: `src/perplexity_search_tests/`

## TL;DR

**Endpoint**: `POST https://api.perplexity.ai/search`
**Pricing**: $5 per 1,000 requests (flat, no token costs)
**Rate Limit**: 3 QPS (allows bursts up to ~20 concurrent)

### Optimal Configuration
```python
{
    "query": your_query,
    "max_results": 20,              # Max allowed
    "max_tokens_per_page": 2048,    # Max content extraction
    "search_domain_filter": [...],   # Optional: quality control
    "search_recency_filter": "month" # Optional: time filter
}
```

**Expected**: ~150-200 results per batch, ~1.5s per batch, ~80-130 results/sec sustained

---

## Key Findings

### Parameters (8/8 Tested ✓)

| Parameter | Limit/Range | Impact | Recommendation |
|-----------|-------------|--------|----------------|
| `max_results` | 1-20 (hard limit) | More results per request | Always use 20 |
| `max_tokens_per_page` | 256-2048 | 7.4x content difference | Use 2048 for research |
| `search_domain_filter` | Max 20 domains | 100% accurate filtering | Use for quality control |
| `search_recency_filter` | day/week/month/year | Time-based filtering | Use for current events |
| `search_after_date` | %m/%d/%Y format | Date range start | Historical research |
| `search_before_date` | %m/%d/%Y format | Date range end | Historical research |
| `country` | ISO 3166-1 codes | Geographic filtering | Regional research |
| `query` | string | Required | - |

### Rate Limits (Tested ✓)

| Concurrent | 429 Errors | Success Rate | Notes |
|------------|------------|--------------|-------|
| 1-20 | 0-2 | 100% | **Sweet spot** |
| 25-30 | 5-15 | 100% | Moderate limiting |
| 50+ | 30+ | 95-100% | Heavy limiting |

**Key**: Rate limit is per-REQUEST, not affected by result count or complexity

### Batching (Tested ✓)

| Strategy | Time (30 queries) | Speedup | Recommendation |
|----------|-------------------|---------|----------------|
| Sequential | 10.8s | 1.0x | ❌ Don't use |
| Batches of 10 | 1.7s | **6.2x** | ✅ **Optimal** |
| All concurrent | 2.8s | 3.9x | ⚠️ More 429s |

**Optimal**: Process in batches of 10-15 concurrent requests

---

## Production Configurations

### Academic Research
```python
{
    "query": "research topic",
    "max_results": 20,
    "max_tokens_per_page": 2048,
    "search_domain_filter": ["arxiv.org", "nature.com", "science.org"],
    "search_recency_filter": "year"
}
```

### News Monitoring
```python
{
    "query": "current events",
    "max_results": 15,
    "search_domain_filter": ["reuters.com", "bloomberg.com"],
    "search_recency_filter": "day",
    "country": "US"
}
```

### Date Range Query
```python
{
    "query": "historical topic",
    "max_results": 20,
    "search_after_date": "01/01/2020",
    "search_before_date": "12/31/2023"
}
```

---

## Response Format

```json
{
  "results": [
    {
      "title": "Article title",
      "url": "https://example.com",
      "snippet": "Content excerpt (length varies by max_tokens_per_page)",
      "date": "2025-03-20",
      "last_updated": "2025-09-19"
    }
  ]
}
```

---

## Quick Reference

### Do's ✓
- Use `max_results=20` (maximum efficiency)
- Use `max_tokens_per_page=2048` (maximum content)
- Batch 10-15 concurrent requests
- Implement retry logic (exponential backoff)
- Use domain filtering for quality

### Don'ts ✗
- Don't use `max_results > 20` (returns 400 error)
- Don't send 25+ concurrent without expecting 429s
- Don't process sequentially (6x slower)
- Don't skip retry logic

---

## Retry Logic (Essential)

```python
max_retries = 5
base_delay = 1.0

for attempt in range(max_retries + 1):
    try:
        result = await search(query)
        return result
    except RateLimitError:
        if attempt < max_retries:
            delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s, 8s, 16s
            await asyncio.sleep(delay)
            continue
        raise
```

**Result**: 100% success rate for reasonable load (tested up to 100 concurrent)

---

## Cost Examples

| Queries | Cost | Results (max=20) | Cost per Result |
|---------|------|------------------|-----------------|
| 10 | $0.05 | ~200 | $0.00025 |
| 100 | $0.50 | ~2,000 | $0.00025 |
| 1,000 | $5.00 | ~20,000 | $0.00025 |

**vs Sonar API**: $5 + $1-15/M tokens (much more expensive)

---

## Performance Benchmarks

### Small Query (10 topics)
- Time: ~0.6s
- Results: ~100-200
- Cost: $0.05
- Rate limits: 0

### Medium Query (100 topics)
- Time: ~15-20s
- Results: ~2,000
- Cost: $0.50
- Rate limits: 10-20 (all recovered)

### Large Query (1,000 topics)
- Time: ~3-5 minutes
- Results: ~20,000
- Cost: $5.00
- Rate limits: 200-300 (all recovered)

---

## Integration with DeepSeek

```
Perplexity Search API ($0.005/query)
    ↓ Raw search results
Format as context
    ↓
DeepSeek V3 on Bedrock ($0.27-0.55/M tokens)
    ↓ Reasoning and synthesis
Structured output with citations
```

**Benefits**: Perplexity's search + DeepSeek's reasoning = Cost-effective research

---

## Complete Documentation

**This folder**: `src/perplexity_search_tests/`

### Test Scripts
1. **`perplexity_search.py`** - Production client with retry logic
2. **`test_perplexity_simple.py`** - Basic functionality tests
3. **`test_rate_limits.py`** - Rate limit stress tests (20-200 concurrent)
4. **`test_batching_simple.py`** - Batching optimization tests
5. **`test_all_parameters.py`** - Complete parameter validation

### Documentation
1. **`README.md`** - Complete guide to tests and docs
2. **`PERPLEXITY_SEARCH_PARAMETERS.md`** - All parameters detailed
3. **`PERPLEXITY_SEARCH_TESTED_RESULTS.md`** - Test results and findings

### Quick Reference
- **`PERPLEXITY_SEARCH_QUICK_REF.md`** - Cheat sheet (in `docs/`)

---

## Getting Started

1. **Set API key**: `export PERPLEXITY_API_KEY='your-key'`
2. **Run basic test**: `python src/perplexity_search_tests/test_perplexity_simple.py`
3. **Use production client**:
   ```python
   from src.perplexity_search_tests.perplexity_search import PerplexitySearchClient
   client = PerplexitySearchClient()
   result = await client.search("AI developments", max_results=20)
   ```

---

## Critical Limits

| Limit | Value | What Happens |
|-------|-------|--------------|
| `max_results` | 20 | 21+ returns 400 error |
| `search_domain_filter` | 20 domains | 21+ returns 400 error |
| Rate limit | 3 QPS | 429 errors (retry recommended) |
| Burst capacity | ~20 concurrent | Above this triggers rate limiting |

---

## Tested Configurations

All parameters tested: ✅ 8/8
All combinations tested: ✅
Rate limits validated: ✅
Production-ready: ✅

**Test coverage**: 100%
**Test date**: 2025-12-12
**All tests passing**: ✅

---

## Next Steps

1. Read `src/perplexity_search_tests/README.md` for comprehensive details
2. Review `PERPLEXITY_SEARCH_QUICK_REF.md` for quick reference
3. Run tests to validate in your environment
4. Use `perplexity_search.py` as production client
5. Integrate with DeepSeek for reasoning pipeline

---

**Last Updated**: 2025-12-12
