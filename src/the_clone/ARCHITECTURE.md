# The Clone - Complete Architecture Documentation

**Version:** 4.1
**Status:** Production Ready
**Date:** 2026-01-06

---

## System Overview

The Clone is an intelligent search and synthesis system that:
1. **Routes smartly** - Strategy-based (breadth/depth), answers directly or searches
2. **Batches efficiently** - 5-15 sources per extraction call for shallow strategies
3. **Handles semantically** - Structured verbal handles (`source_detail_limits`) for citations
4. **Matches perfectly** - 100% citation match rate with dual handle/ID paths
5. **Stops intelligently** - Early termination when reliable answer found
6. **Tracks costs precisely** - Provider-level cost aggregation

## Latest Updates (v4.1)

### Skip-to-Synthesis Path (New)
- When direct answer fails validation/repair, skip search entirely
- Extract URLs from query and fetch from memory or live (Jina)
- Go directly to synthesis with URL sources
- Faster fallback than full search when URLs are in query

### URL Detection and Live Fetch (New)
- `extract_urls_from_text()` detects URLs in user queries
- `recall_by_urls()` looks up URLs in search memory
- `fetch_url_content()` fetches missing URLs via Jina AI Reader
- URL sources get priority in source selection

### Section Symbol Standardization
- Location codes now use `S` (section symbol) consistently
- Removed backtick conversion in repair module
- Prevents markdown interpretation issues

---

## Updates (v4.0)

### Batch Extraction System
- **Shallow strategies** process 5-15 sources in single API call
- **Deep strategies** use individual extraction for thorough processing
- Reduces API overhead while maintaining quality

### Verbal Handle System
- All snippets have semantic handles: `source_detail_limits`
- Format: `pubmed_weight-loss_dec-2025`, `nih_insulin-sensitivity_tre-protocol`
- Citations use `[handle, S1.1.0.0-p0.95]` format
- Dual matching: by handle OR by snippet ID
- Auto-deduplication with _2, _3 suffixes

### Strategy Matrix
| Strategy | Breadth | Depth | Batch | Tokens/Page | Stop Condition |
|----------|---------|-------|-------|-------------|----------------|
| Targeted | narrow | shallow | 5 (batch) | 512 | Answer found (p≥0.85) |
| Focused Deep | narrow | deep | 10 (individual) | 2048 | All sources |
| Survey | broad | shallow | 15 (batch) | 512 | All sources |
| Comprehensive | broad | deep | 15 (individual) | 2048 | All sources |

### Model Updates
- **Initial Decision:** Gemini 2.0 Flash (all providers)
- **Triage/Extraction:** Gemini 2.0 Flash (fast, cost-effective)
- **Synthesis:** Provider-specific (tier-based: tier1-4)
- **Max tokens:** 64K for all synthesis models

---

## Complete Data Flow

```
┌─────────────────────────────────────────────┐
│  User Query                                  │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│  STEP 0: Initial Decision (Sonnet 4.5)      │
│  - Answer from knowledge? → Return answer   │
│  - Need search? → Determine:                │
│    * Context (low/medium/high)              │
│    * Model tier (fast/strong/deep)          │
│    * Initial search terms                   │
└──────────────────┬──────────────────────────┘
                   ↓
          ┌────────┼────────┐
          │        │        │
    Answer     Skip-to-    Need
    Directly   Synthesis   Search
          │        │        │
          ↓        ↓        ↓
       Return   URL Sources  Iteration Loop
               + Synthesis   (1-3 times)
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        │  STEP 1: Get Search Terms             │
        │    Iter 1: Use initial terms          │
        │    Iter 2+: Generate new based on gaps│
        └───────────────────┬───────────────────┘
                            ↓
        ┌───────────────────────────────────────┐
        │  STEP 2: Execute Searches (Perplexity)│
        │    - 1-5 searches based on context    │
        │    - 5-15 results per search          │
        └───────────────────┬───────────────────┘
                            ↓
        ┌───────────────────────────────────────┐
        │  STEP 3: Parallel Triage (Haiku)      │
        │    - All searches triaged concurrently│
        │    - Diversity-focused                │
        │    - Select 0-5 per search            │
        └───────────────────┬───────────────────┘
                            ↓
                    No sources? → Synthesize
                            ↓
        ┌───────────────────────────────────────┐
        │  STEP 4: Parallel Extraction (Haiku)  │
        │    - All sources extracted concurrently│
        │    - Essential quotes only            │
        │    - Off-topic detection              │
        │    - Context markers added            │
        └───────────────────┬───────────────────┘
                            ↓
        ┌───────────────────────────────────────┐
        │  STEP 5: Unified Eval+Synthesis       │
        │    (Tier determined by initial decision)│
        │                                       │
        │  Not last iteration:                  │
        │    - Can answer? Yes → Return answer  │
        │    - Can answer? No → Next iteration  │
        │                                       │
        │  Last iteration:                      │
        │    - Generate answer                  │
        └───────────────────┬───────────────────┘
                            ↓
        ┌───────────────────────────────────────┐
        │  Return: Answer + Citations + Costs   │
        └───────────────────────────────────────┘
```

---

## Configuration System

### Model Tiers (Abstract)

Configuration uses abstract tier names, not model names:

```json
{
  "model_tiers": {
    "fast": "claude-haiku-4-5",
    "strong": "claude-sonnet-4-5",
    "deep_thinking": "claude-opus-4-6"
  }
}
```

**Benefits:**
- Easy to swap models (change config, not code)
- Clear intent (fast vs strong vs deep)
- Tier selection is semantic, not technical

### Context Levels (Data-Driven)

```json
{
  "contexts": {
    "low": {
      "max_iterations": 1,
      "search_terms_range": [1, 2],
      "max_results_per_search": 5,
      "sources_per_search_range": [1, 2]
    },
    "medium": {...},
    "high": {...}
  }
}
```

**Everything is configuration-driven:**
- Prompts built from config
- Schemas generated from config
- No hardcoded values

---

## Quote Extraction with Off-Topic Detection

### Schema
```json
{
  "quotes_by_search": {
    "1": ["quote for search term 1", ...],
    "2": ["off-topic quote for term 2", ...],
    "3": []
  }
}
```

### Snippet ID Format
```
S{iteration}.{search}.{source}.{quote}-{reliability}

Example: S1.2.3.0-H
```

### Off-Topic Context Markers

Off-topic quotes automatically get context:
```
Original: "Model achieves 92% accuracy"
With marker: "[re: GPT-4.5 performance] Model achieves 92% accuracy"
```

**Why?** Makes it clear what the quote is about when it comes from a source about a different topic.

---

## Synthesis Input Format

Quotes are grouped BY SEARCH TERM for better synthesis:

```
=== Search Term 1: "Claude Opus 4 architecture" ===
[S1.1.0-H] Introducing Claude 4
  - [S1.1.0.0-H] "Uses hybrid architecture with two modes"
  - [S1.1.0.1-H] "Supports 200K context window"

=== Search Term 2: "GPT-4.5 performance" ===
[S1.2.0-M] GPT-4.5 Analysis
  - [S1.2.0.0-M] "Achieves 92% on benchmarks"
[S1.1.0-H] Introducing Claude 4 (off-topic)
  - [S1.1.0.2-H] "[re: GPT-4.5] Comparison shows GPT-4.5 at 12.8T params"

=== Search Term 3: "DeepSeek V3 MoE" ===
...
```

**Benefits:**
- Synthesis sees all info about one aspect together
- Easier to organize comparison answers
- Off-topic quotes clearly marked

---

## Cost Tracking

### Aggregation
Costs extracted from `enhanced_data` in every API response:

```python
response = await api_call(...)
enhanced = response.get('enhanced_data', {})
costs = enhanced.get('costs', {}).get('actual', {})
total_cost = costs.get('total_cost', 0.0)
```

### Breakdown
```
Component          Example Cost   % of Total
──────────────────────────────────────────────
Initial Decision   $0.0078        7.3%
Triage (5 calls)   $0.0106        9.9%
Extraction (15)    $0.0360        33.7%
Synthesis (1)      $0.0374        35.0%
Search (3 calls)   $0.0150        14.1%
──────────────────────────────────────────────
TOTAL              $0.1067        100%
```

---

## Performance Characteristics

### By Query Complexity

| Complexity | Time | Cost | Iterations | Context | Tier |
|------------|------|------|------------|---------|------|
| **Simple** | 6-10s | $0.01-0.02 | 0 | N/A | Direct answer |
| **Moderate** | 30-60s | $0.08-0.15 | 1-2 | medium | strong |
| **Complex** | 60-150s | $0.15-0.25 | 1-3 | high | strong/deep |

### Comparison to Baselines

| System | Time | Cost | Citations | Notes |
|--------|------|------|-----------|-------|
| **Sonar (low)** | 15s | $0.001 | 10-15 | Fast but basic |
| **Sonar Pro (high)** | 40s | $0.05 | 20-25 | Better quality |
| **Clone V1** | 400s | $0.05 | 11 | Slow, fewer citations |
| **The Clone** | 40-125s | $0.10-0.21 | 7-92 | **Fast + comprehensive** |

---

## Implementation Details

### Parallel Processing

**Triage (Step 3):**
```python
# All search terms triaged concurrently
tasks = [triage(search_1), triage(search_2), ..., triage(search_5)]
results = await asyncio.gather(*tasks)
# 5 searches triaged in ~7s (not 5 × 7s = 35s)
```

**Extraction (Step 4):**
```python
# All selected sources extracted concurrently
tasks = [extract(source_1), extract(source_2), ..., extract(source_15)]
results = await asyncio.gather(*tasks)
# 15 sources in ~8s (not 15 × 8s = 120s)
```

### Schema Validation

All internal API calls use JSON schemas:
- Initial decision: `get_initial_decision_schema()`
- Triage: `get_source_triage_schema()`
- Extraction: `get_snippet_extraction_schema()`
- Synthesis: `get_unified_evaluation_synthesis_schema()` or `get_synthesis_only_schema()`

**Ensures:**
- Structured, predictable outputs
- Type safety
- Easy debugging

---

## Optimization Techniques

### 1. Smart Routing (Step 0)
- Answers ~20% of queries directly (no search)
- Saves ~$0.10 and 60-120s per direct answer

### 1b. Skip-to-Synthesis Path
When direct answer fails validation/repair, skip search and go straight to synthesis:
- Extract URLs from query using `extract_urls_from_text()`
- Look up URLs in memory via `SearchMemory.recall_by_urls()`
- Fetch missing URLs live via Jina AI Reader
- Convert URL sources to snippets and synthesize
- Faster than full search when URLs are available in query

**Decision Flow:**
```
answer_directly + valid answer     → Return answer
answer_directly + repairable       → Repair, return answer
answer_directly + unrepairable     → Skip-to-synthesis (with URL sources)
need_search                        → Full search path
```

### 2. Parallel Triage (Step 3)
- Concurrent evaluation of all searches
- 5-7x faster than sequential

### 3. Streamlined Extraction (Step 4)
- Extract only essential quotes (not full analysis)
- 3-4x faster per source (0.5s vs 1.5s)
- Smaller synthesis input

### 4. Off-Topic Detection
- Capture cross-search information
- 36% bonus quotes without extra API calls
- More comprehensive answers

### 5. Unified Eval+Synthesis (Step 5)
- One call instead of two
- If can answer, provides answer immediately
- Saves one Sonnet API call when sufficient

### 6. Early Stopping
- Stop when sufficient (don't use all iterations)
- ~50% of queries stop after iteration 1

---

## URL Extraction and Memory Recall

### URL Detection
The system automatically detects URLs in user queries using `extract_urls_from_text()`:
- Matches `http://` and `https://` URLs
- Extracts domain and path
- Used for memory lookup and live fetching

### URL-Based Memory Recall
When URLs are found in the query (via `SearchMemory`):

1. **Memory Lookup** (`recall_by_urls()`):
   - Checks if URL sources exist in search memory
   - Returns `{found: [...], not_found: [...]}`

2. **Live Fetch** (`fetch_url_content()`):
   - URLs not in memory are fetched via Jina AI Reader
   - Jina converts web pages to clean markdown
   - Fetched content is converted to source format

3. **Priority Handling**:
   - URL sources get high priority in Gemini source selection
   - Always included in verification and synthesis
   - Bypass keyword filtering for direct relevance

### Implementation
```python
# In the_clone.py
from the_clone.search_memory import SearchMemory, extract_urls_from_text

query_urls = extract_urls_from_text(prompt)
if query_urls:
    url_lookup = memory.recall_by_urls(query_urls)
    url_sources = url_lookup['found']

    # Fetch missing URLs live
    if url_lookup['not_found']:
        fetched = await memory.fetch_url_content(url_lookup['not_found'])
        url_sources.extend(fetched)
```

---

## Error Handling

- API failures: Continue with available data
- Empty extractions: Skip sources, continue
- Triage returns 0: Proceed to synthesis with existing
- Schema validation: Soft schemas with fallback parsing

---

## Experimental Approaches (Not in Production)

### Merged Synthesis (Code-Based Citations)

**Status**: Experimental - Fully functional but not integrated
**Documentation**: See `MERGED_SYNTHESIS_EXPERIMENTAL.md`

An alternative approach that combines extraction and synthesis into a single LLM call:

```
┌─────────────────────────────────────────────┐
│  All sources → Label with codes (`S1:1.1)   │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│  Single LLM Call:                            │
│  - Synthesize from all labeled sources       │
│  - Cite using codes {`S1:1.1, 0.95, P}       │
│  - Include p-scores inline                   │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│  Post-processing:                            │
│  - Resolve codes to text                     │
│  - Create citations [1][2]                   │
└─────────────────────────────────────────────┘

Total: 1 LLM call (vs N+1 traditional)
```

**Validated Performance**:
- ✅ 85.7% LLM call reduction (7 → 1)
- ✅ 15-20% token reduction
- ✅ 99-100% code resolution rate
- ⚠️ ~10% higher cost (output token heavy)
- ⚠️ 50-90% slower (single large call)

**Use cases**: Rate-limited scenarios, cost-per-call billing, batch processing

**Current decision**: Stick with traditional approach for production (speed + proven stability)

---

## Future Enhancements

Potential optimizations:
- [ ] Caching frequent queries
- [ ] Batch similar queries
- [ ] Adaptive source limits based on quote density
- [ ] Multi-language support
- [ ] Custom synthesis schemas per query type

---

**The Clone is a production-ready intelligent search system!** 🚀
