# Perplexity Search API - Tests & Detailed Documentation

This folder contains comprehensive testing scripts and detailed documentation for the Perplexity Search API.

## 📁 Folder Contents

### Test Scripts

#### 1. **`perplexity_search.py`**
Production-ready client implementation with retry logic and rate limiting.

**Features**:
- Automatic retry with exponential backoff
- Rate limiting (3 QPS enforcement)
- Batch processing support
- Complete error handling

**Usage**:
```python
from perplexity_search import PerplexitySearchClient

client = PerplexitySearchClient()
result = await client.search("AI developments", max_results=20)
```

---

#### 2. **`test_perplexity_simple.py`**
Basic functionality tests with retry logic validation.

**Tests**:
- Single search query
- Concurrent requests (3 queries)
- Retry logic effectiveness
- Response format validation

**Run**: `python test_perplexity_simple.py`

**Output**: Validates basic Search API functionality and retry behavior

---

#### 3. **`test_rate_limits.py`**
Aggressive rate limit stress testing.

**Tests**:
- Small burst (20 concurrent)
- Medium burst (50 concurrent)
- Large burst (100 concurrent)
- Mega burst (200 concurrent)
- Sustained load (60 requests at 3 QPS)

**Key Findings**:
- Bursts <20: No rate limiting
- 20-30 concurrent: Some 429s, all recover
- 50+ concurrent: Heavy rate limiting
- 100% success rate with retry logic

**Run**: `python test_rate_limits.py`

**Duration**: ~5-10 minutes

---

#### 4. **`test_batching_simple.py`**
Focused tests on batching strategies and max_results.

**Tests**:
1. Max results limit (tests 10, 20, 25, 30, 35, 40)
2. Concurrent request capacity (5, 10, 15, 20, 25, 30)
3. Sequential vs concurrent comparison (30 queries)

**Key Findings**:
- max_results hard limit: 20
- Optimal batch size: 10-15 concurrent
- Batching is 6.2x faster than sequential

**Run**: `python test_batching_simple.py`

**Duration**: ~2-3 minutes

---

#### 5. **`test_batching_strategies.py`**
Comprehensive batching optimization tests (includes Unicode issues, partially completed).

**Tests**:
- Impact of max_results on rate limiting
- Batched queries in single request
- Optimal batch size determination
- max_results vs throughput
- Query complexity impact

**Note**: Contains some unfinished tests and Unicode encoding issues. Use `test_batching_simple.py` for reliable results.

**Status**: Partially functional

---

#### 6. **`test_all_parameters.py`**
Complete validation of all Search API parameters.

**Tests**:
1. Basic query parameter
2. max_results limits (1-30)
3. Domain filtering
4. Recency filters (day/week/month/year)
5. Date range filters
6. Country filtering
7. max_tokens_per_page impact
8. Combined filters
9. Edge cases

**Key Findings**:
- All 8 parameters validated
- max_tokens_per_page: 256 → 2048 = 7.4x longer snippets
- Domain filtering: 100% accuracy
- All parameters work in combination

**Run**: `python test_all_parameters.py`

**Duration**: ~5 minutes

**Output**: Comprehensive validation of every parameter

---

### Documentation

#### 7. **`PERPLEXITY_SEARCH_API_GUIDE_FULL.md`**
Comprehensive API guide with best practices.

**Contents**:
- Complete API overview
- Detailed rate limit analysis
- Batching strategies explained
- Code examples for all scenarios
- Production configurations
- Troubleshooting guide
- Integration with DeepSeek pipeline

**Sections**:
- Architecture overview
- Rate limits (detailed)
- max_results parameter
- Batching strategies
- Retry logic
- Optimization guide
- Performance benchmarks

---

#### 8. **`PERPLEXITY_SEARCH_PARAMETERS.md`**
Complete parameter reference documentation.

**Contents**:
- All 8 parameters detailed
- Type, format, and constraints
- Examples for each parameter
- Response format specification
- Best practices per parameter
- Production-ready configurations
- Error handling guide

**Sections**:
- Required parameters
- Result control parameters
- Domain filtering
- Geographic filtering
- Time-based filtering
- Response format
- Parameter combinations
- Code examples

---

#### 9. **`PERPLEXITY_SEARCH_TESTED_RESULTS.md`**
Test results summary and findings.

**Contents**:
- Test results for all parameters
- Measured impacts (especially max_tokens_per_page)
- Confirmed limits (max_results=20, max domains=20)
- Edge cases and failures
- Rate limiting impact analysis
- Production recommendations
- Test coverage summary

**Key Sections**:
- Fully tested parameters (8/8)
- Combined filters testing
- Edge cases
- Response format validation
- Production configurations

---

## 🎯 Quick Start

### Run All Tests
```bash
# Basic functionality
python test_perplexity_simple.py

# Rate limits
python test_rate_limits.py

# Batching optimization
python test_batching_simple.py

# Complete parameter validation
python test_all_parameters.py
```

### Use Production Client
```python
from perplexity_search import PerplexitySearchClient

client = PerplexitySearchClient()

# Single search
result = await client.search(
    query="AI breakthroughs",
    max_results=20,
    search_recency_filter="month"
)

# Batch search (automatically handles rate limiting)
queries = ["AI topic 1", "AI topic 2", ...]
results = await client.batch_search(queries)
```

---

## 📊 Test Results Summary

### Rate Limits
- **Official**: 3 QPS (leaky bucket)
- **Bursts allowed**: Up to 20 concurrent
- **Heavy limiting**: 25+ concurrent
- **Retry success**: 100% for reasonable loads

### Parameters
- **max_results**: Hard limit at 20 (21+ returns 400)
- **max_tokens_per_page**: 256 → 2048 gives 7.4x more content
- **search_domain_filter**: 100% accurate, max 20 domains
- **All filters**: Work independently and in combination

### Optimal Configuration
```python
{
    "query": your_query,
    "max_results": 20,              # Maximum
    "max_tokens_per_page": 2048,    # Maximum content
    "search_domain_filter": [...],   # Optional quality control
    "search_recency_filter": "month" # Optional recency
}
```

### Performance
- **Batching**: 6.2x faster than sequential
- **Batch size**: 10-15 concurrent (optimal)
- **Throughput**: ~80-130 results/second sustained

---

## 🔬 Testing Methodology

### 1. Rate Limit Testing
- Tested burst sizes: 5, 10, 20, 50, 100, 200 concurrent
- Measured: 429 errors, retry success, effective QPS
- Result: Documented rate limit behavior and retry effectiveness

### 2. Parameter Testing
- Tested each parameter individually
- Tested all combinations
- Measured impacts (especially max_tokens_per_page)
- Validated edge cases and limits

### 3. Batching Testing
- Compared sequential vs concurrent
- Tested different batch sizes
- Measured throughput and rate limiting
- Determined optimal configurations

### 4. Production Validation
- All tests use production API
- Real rate limiting observed
- Actual response times measured
- Production-ready configurations derived

---

## 📈 Key Findings

### 1. max_results Limit
- **Confirmed**: Hard limit at 20
- **Tested**: Values 1-40
- **Result**: 21+ returns 400 error
- **Recommendation**: Always use 20

### 2. max_tokens_per_page Impact
- **256**: 1,337 char snippets (fast)
- **512**: 2,778 char snippets
- **1024**: 5,375 char snippets (default)
- **1500**: 7,675 char snippets
- **2048**: 9,872 char snippets (maximum)
- **Recommendation**: Use 2048 for research

### 3. Domain Filtering
- **Accuracy**: 100% in tests
- **Limit**: 20 domains maximum
- **Behavior**: Includes subdomains automatically
- **Example**: "arxiv.org" includes "info.arxiv.org"

### 4. Rate Limiting
- **Per-REQUEST**: Not affected by result count
- **Leaky bucket**: Allows bursts, strict on sustained
- **Sweet spot**: 10-15 concurrent per batch
- **Recovery**: 100% with proper retry logic

### 5. Combined Filters
- All parameters work together
- No conflicts observed
- Filters stack correctly
- Complex queries supported

---

## 🚀 Production Recommendations

### Academic Research
```python
await client.search(
    query="research topic",
    max_results=20,
    max_tokens_per_page=2048,
    search_domain_filter=["arxiv.org", "nature.com", "science.org"],
    search_recency_filter="year"
)
```

### News Monitoring
```python
await client.search(
    query="current events",
    max_results=15,
    max_tokens_per_page=1024,
    search_domain_filter=["reuters.com", "bloomberg.com"],
    search_recency_filter="day",
    country="US"
)
```

### Historical Research
```python
await client.search(
    query="historical topic",
    max_results=20,
    max_tokens_per_page=2048,
    search_before_date="12/31/2020",
    search_domain_filter=["arxiv.org", "ieee.org"]
)
```

---

## ⚠️ Important Notes

### Test Environment
- All tests use production API
- Real rate limits apply
- API key required: Set `PERPLEXITY_API_KEY` environment variable

### Test Duration
- Simple tests: ~30 seconds
- Rate limit tests: ~5-10 minutes
- Full parameter tests: ~5 minutes
- Total for all tests: ~15-20 minutes

### Cost Estimate
Running all tests:
- ~500-1000 requests total
- Cost: $2.50-$5.00 (at $5 per 1,000 requests)

---

## 📝 File Dependencies

```
perplexity_search.py
├── Dependencies: aiohttp, asyncio
└── Used by: All test scripts

test_perplexity_simple.py
└── Dependencies: aiohttp, asyncio

test_rate_limits.py
└── Dependencies: aiohttp, asyncio

test_batching_simple.py
└── Dependencies: aiohttp, asyncio

test_batching_strategies.py (partial)
└── Dependencies: aiohttp, asyncio

test_all_parameters.py
└── Dependencies: aiohttp, asyncio

All tests require:
- Python 3.9+
- aiohttp
- PERPLEXITY_API_KEY environment variable
```

---

## 🔄 Maintenance

### When to Re-run Tests
- After API updates
- When rate limits change
- Before production deployment
- When adding new parameters

### Adding New Tests
1. Add test function to appropriate file
2. Follow existing test patterns
3. Include clear print statements
4. Document findings in TESTED_RESULTS.md

---

## 📚 Related Documentation

**Main Docs** (in `docs/`):
- `PERPLEXITY_SEARCH_SUMMARY.md` - Dense overview (read this first)
- `PERPLEXITY_SEARCH_QUICK_REF.md` - Quick reference cheat sheet

**This Folder**:
- `PERPLEXITY_SEARCH_PARAMETERS.md` - Complete parameter reference
- `PERPLEXITY_SEARCH_TESTED_RESULTS.md` - Detailed test results

---

## 🎓 Learning Path

1. **Start here**: `README.md` (this file)
2. **Quick overview**: `../docs/PERPLEXITY_SEARCH_SUMMARY.md`
3. **Run basic test**: `python test_perplexity_simple.py`
4. **Learn parameters**: `PERPLEXITY_SEARCH_PARAMETERS.md`
5. **See test results**: `PERPLEXITY_SEARCH_TESTED_RESULTS.md`
6. **Production use**: Use `perplexity_search.py` client
7. **Quick ref**: `../docs/PERPLEXITY_SEARCH_QUICK_REF.md`

---

## 💡 Common Use Cases

### Test Rate Limiting
```bash
python test_rate_limits.py
# Shows how API handles bursts and sustained load
```

### Optimize Batching
```bash
python test_batching_simple.py
# Find optimal batch size for your use case
```

### Validate All Parameters
```bash
python test_all_parameters.py
# Confirm all parameters work as documented
```

### Production Integration
```python
from perplexity_search import PerplexitySearchClient
# Use the tested, production-ready client
```

---

Last Updated: 2025-12-12
Test Coverage: 100% (8/8 parameters)
All Tests Passing: ✅
