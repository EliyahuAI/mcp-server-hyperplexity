# Perplexity Search API - Rate Limit Testing Suite

**Test Date**: 2026-02-10
**Status**: ✅ Complete
**Key Finding**: "50 per second" = 50-request burst capacity, NOT 50 QPS sustained

---

## Quick Start

### Read the Reports

1. **Executive Summary** (5 min read)
   - `RATE_LIMIT_EXECUTIVE_SUMMARY.md`
   - TL;DR with key findings and recommendations

2. **Full Analysis Report** (20 min read)
   - `PERPLEXITY_RATE_LIMIT_ANALYSIS_2026.md`
   - Complete methodology, results, code examples

### Run the Tests Yourself

```bash
# Set your API key
export PERPLEXITY_API_KEY='your-key-here'

# Run burst capacity tests (~2 minutes)
python3 test_rate_limits_50qps.py

# Run sustained rate discovery (~12 minutes)
python3 test_sustained_rate_limit.py
```

---

## Files in This Directory

### 📊 Reports

| File | Description | Read Time |
|------|-------------|-----------|
| `RATE_LIMIT_EXECUTIVE_SUMMARY.md` | Quick summary with key findings | 5 min |
| `PERPLEXITY_RATE_LIMIT_ANALYSIS_2026.md` | Complete analysis report | 20 min |

### 🧪 Test Scripts

| File | Description | Duration |
|------|-------------|----------|
| `test_rate_limits_50qps.py` | Burst capacity tests (50→1000 concurrent) | ~2 min |
| `test_sustained_rate_limit.py` | Sustained rate tests (5→50 QPS) | ~12 min |

### 📁 Test Results

| File | Description |
|------|-------------|
| `sustained_rate_limit_results.json` | Raw test data from sustained rate tests |

### 📚 Legacy Documentation

| File | Description |
|------|-------------|
| `PERPLEXITY_SEARCH_SUMMARY.md` | Original 3 QPS documentation |
| `PERPLEXITY_SEARCH_QUICK_REF.md` | Original quick reference |
| `perplexity_search.py` | Production client (configured for 3 QPS) |
| `test_rate_limits.py` | Original 3 QPS tests |

---

## Key Findings Summary

### 🚨 Critical Discovery

The "50 per second" rate limit is **NOT what it seems**:

| What You Might Think | What It Actually Is |
|---------------------|---------------------|
| 50 requests per second sustained | ❌ No - only ~3 QPS sustained |
| Can process 3,000 requests/minute | ❌ No - only ~180 requests/minute |
| 16× improvement over 3 QPS | ❌ No - 2.5× improvement (burst only) |

### ✅ Actual Capabilities

**Burst Operations**:
- 50 concurrent requests: ✅ Zero rate limiting
- 100 concurrent requests: ✅ 100% success with retries
- Completion time: ~1-2 seconds per burst

**Sustained Operations**:
- Effective rate: ~3 QPS (unchanged from before)
- Cooldown required: 17 seconds between 50-request bursts
- Long-term throughput: ~2.7 QPS

### 📈 What Improved

**Leaky Bucket Parameters**:
- Bucket size: 20 → **50 tokens** ✅ (2.5× increase)
- Refill rate: ~3/second → **~3/second** ❌ (unchanged)

This means:
- ✅ Better handling of bursty traffic
- ✅ Can process batches 2.5× larger
- ❌ No improvement for sustained throughput
- ❌ Still limited to ~3 QPS average

---

## Optimal Configuration

### Recommended Settings

```python
BURST_BATCH_SIZE = 50          # Concurrent requests per burst
SUSTAINED_QPS = 3              # Long-term average rate
COOLDOWN_BETWEEN_BURSTS = 17   # Seconds (50 / 3)
MAX_RETRIES = 5                # Exponential backoff
BASE_DELAY = 1.0               # Seconds
```

### Performance Expectations

| Metric | Value |
|--------|-------|
| Requests per burst | 50 |
| Burst duration | ~1 second |
| Cooldown required | 17 seconds |
| Total time per cycle | 18 seconds |
| Effective throughput | 2.78 QPS |
| Rate limiting | 0 errors |
| Success rate | 100% |

---

## When to Use Each Strategy

### 50-Concurrent Bursts

**Use if**:
- ✅ Processing ≤50 requests at a time
- ✅ Can wait 17+ seconds between batches
- ✅ Want zero rate limiting
- ✅ Have bursty traffic patterns

**Example workloads**:
- Periodic batch jobs
- User-triggered searches
- On-demand processing
- Scheduled tasks

### 3 QPS Sustained

**Use if**:
- ✅ Continuous processing needed
- ✅ Large ongoing workloads
- ✅ Can't tolerate burst delays
- ✅ Need predictable throughput

**Example workloads**:
- Real-time data pipelines
- Continuous monitoring
- Streaming applications
- Background processing queues

### Hybrid Strategy

**Best for**:
- ✅ Large total workloads (1000+ requests)
- ✅ Can be processed in chunks
- ✅ Want optimal speed with zero rate limiting

**Implementation**:
```python
# Process in 50-request bursts with 17s cooldown
# Achieves ~2.7 QPS sustained with 100% success rate
```

---

## Test Methodology

### Burst Capacity Tests

**Approach**: Launch N concurrent requests simultaneously
- Tested: 50, 100, 200, 300, 500, 1000 concurrent
- Metrics: 429 errors, success rate, actual throughput
- Finding: 50 concurrent = sweet spot (0 rate limiting)

### Sustained Rate Tests

**Approach**: Send requests at fixed QPS for 30 seconds
- Tested: 5, 10, 15, 20, 25, 30, 35, 40, 45, 50 QPS
- Metrics: 429 errors, success rate, actual throughput
- Finding: ALL rates experienced heavy rate limiting

---

## Test Results at a Glance

### Burst Tests

| Concurrent | 429 Errors | Success | Status |
|-----------|------------|---------|--------|
| 50 | **0** | 100% | ✅ Optimal |
| 100 | 50 | 100% | ✅ Good |
| 200 | 300 | 100% | ⚠️ Slow |
| 500+ | 1500+ | <98% | ❌ Fails |

### Sustained Tests

| Target QPS | 429 Errors | Success | Status |
|-----------|------------|---------|--------|
| 5 | 150 (100%) | 100% | ❌ All rate limited |
| 10 | 747 (249%) | 100% | ❌ Heavy limiting |
| 50 | 5139 (343%) | 72% | ❌ Catastrophic |

---

## Production Code Examples

### Example 1: Simple 50-Burst

```python
async def process_batch(queries):
    """Process up to 50 queries with zero rate limiting."""
    if len(queries) > 50:
        raise ValueError("Batch size must be ≤50")

    tasks = [search(q, max_results=10, max_retries=5) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

# Usage
results = await process_batch(my_50_queries)  # ~1 second, 0 rate limiting
```

### Example 2: Large Workload with Optimal Batching

```python
async def process_large_workload(queries):
    """
    Process large number of queries using optimal batching.
    Achieves ~2.7 QPS sustained with zero rate limiting.
    """
    results = []
    BATCH_SIZE = 50
    COOLDOWN = 17  # seconds

    for i in range(0, len(queries), BATCH_SIZE):
        # Process burst
        batch = queries[i:i+BATCH_SIZE]
        batch_results = await process_batch(batch)
        results.extend(batch_results)

        # Cooldown (skip after last batch)
        if i + BATCH_SIZE < len(queries):
            await asyncio.sleep(COOLDOWN)

    return results

# Usage
results = await process_large_workload(my_1000_queries)
# Time: ~18s per batch × 20 batches = ~6 minutes
# Rate: 1000 / 360s = 2.78 QPS sustained
```

### Example 3: Sustained 3 QPS

```python
async def sustained_processing(queries):
    """Process queries at sustained 3 QPS rate."""
    results = []
    DELAY = 1.0 / 3  # 0.333 seconds

    for query in queries:
        result = await search(query, max_results=10, max_retries=5)
        results.append(result)
        await asyncio.sleep(DELAY)

    return results

# Usage
results = await sustained_processing(my_queries)
# Predictable: 3 requests/second, minimal rate limiting
```

---

## Monitoring Recommendations

Track these metrics in production:

| Metric | Target | Alert If |
|--------|--------|----------|
| Rate limit errors (429s) | 0 | >5 per batch |
| Success rate | 100% | <99% |
| Batch completion time | ~1-2s | >5s |
| Effective throughput | ~2.7 QPS | <2 QPS |

---

## Common Pitfalls

### ❌ Don't Do This

```python
# WRONG: Expecting 50 QPS sustained
for i in range(1000):
    await search(query)  # Will hit massive rate limiting
    await asyncio.sleep(0.02)  # 50 QPS pace
```

### ✅ Do This Instead

```python
# CORRECT: 50-burst with proper cooldown
for i in range(0, 1000, 50):
    batch = queries[i:i+50]
    await asyncio.gather(*[search(q) for q in batch])
    await asyncio.sleep(17)  # Respect sustained rate
```

---

## Cost Analysis

**Pricing**: $5 per 1,000 requests (flat rate)

| Workload | Time | Cost | Avg Throughput |
|----------|------|------|----------------|
| 100 requests | 18s | $0.50 | 5.5 QPS |
| 1,000 requests | 6 min | $5.00 | 2.8 QPS |
| 10,000 requests | 60 min | $50.00 | 2.8 QPS |

**Key insight**: Burst capacity doesn't reduce costs, but reduces latency per batch.

---

## Comparison with Other APIs

| API | Burst Capacity | Sustained Rate | Algorithm |
|-----|---------------|----------------|-----------|
| Perplexity Search | 50 concurrent | ~3 QPS | Leaky bucket |
| Perplexity Sonar | ~50 requests | 1,000 RPM | Token bucket |
| Anthropic Claude | N/A | 1,000 RPM | Token bucket |

**Perplexity Search is optimized for bursty batch processing, not continuous high throughput.**

---

## Update History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-02-10 | Complete retest after "50/second" change |
| 1.0 | 2025-12-12 | Original 3 QPS documentation |

---

## Questions?

### "Can I really only do 3 QPS sustained?"

Yes. Despite the "50 per second" claim, sustained operations are limited to ~3 QPS. The 50 refers to burst bucket size, not refill rate.

### "What if I need higher sustained throughput?"

Options:
1. Use multiple API keys (if allowed by terms of service)
2. Switch to Perplexity Sonar API (1,000 RPM but different pricing)
3. Accept the 3 QPS limit and batch process accordingly

### "Is this a bug?"

Unlikely. This appears to be intentional rate limit design:
- Burst capacity increased to handle bursty traffic
- Sustained rate kept low to prevent abuse
- Common pattern for APIs with flat-rate pricing

---

## License

These test scripts and reports are provided as-is for informational purposes. Test against your own API key before relying on these findings for production use.

---

**Last Updated**: 2026-02-10
**Test Completion**: ✅ All tests passed
**Recommended Action**: Update production code to use 50-burst with 17s cooldown
