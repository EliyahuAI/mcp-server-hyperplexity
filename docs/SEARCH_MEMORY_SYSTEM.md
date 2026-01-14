# Search Memory System

## Overview

The Search Memory System is a session-scoped memory layer for the Perplexity Search API that stores all search results and intelligently recalls them to avoid redundant searches, reduce costs, and improve response times.

The system also supports **direct URL content storage** for Table Maker extractions, enabling full table data to be stored and recalled during validation - ensuring extracted tables are available even when Perplexity search snippets are truncated.

## Architecture

### Storage Design

**In-Memory (Runtime):**
- Volatile RAM storage during lambda/process execution
- Fast access for recall operations
- Lazy loading from S3 on initialization

**S3 Persistence:**
- Location: `s3://.../results/{domain}/{email}/{session_id}/agent_memory.json`
- Backup: After each search (continuous)
- Restore: On lambda initialization
- Concurrency: Optimistic locking with retry (3 attempts, exponential backoff)

### Memory Structure

```json
{
  "session_id": "session_123",
  "queries": {
    "query_abc123": {
      "query_text": "What are Python 3.12 features?",
      "search_term": "Python 3.12 new features",
      "query_time": "2025-12-30T14:30:22Z",
      "parameters": {
        "max_results": 10,
        "max_tokens_per_page": 2048,
        "search_recency_filter": null,
        "include_domains": [],
        "exclude_domains": []
      },
      "results": [
        {
          "title": "...",
          "url": "...",
          "snippet": "...",
          "date": "2024-12-01"
        }
      ],
      "metadata": {
        "cost": 0.005,
        "num_results": 10,
        "strategy": "survey"
      }
    }
  },
  "indexes": {
    "by_time": ["query_001", "query_002", ...],
    "by_url": {"https://...": ["query_001"]}
  }
}
```

### URL Content Storage (Table Maker Integration)

In addition to search results, the memory can store **full URL content** directly:

```json
{
  "url_content_abc123": {
    "query_text": "[URL_CONTENT] https://census.gov/data/tables/...",
    "search_term": "[URL_CONTENT] https://census.gov/data/tables/...",
    "query_time": "2025-12-30T14:30:22Z",
    "parameters": {
      "source_type": "table_extraction",
      "content_length": 15000,
      "is_url_content": true
    },
    "results": [
      {
        "url": "https://census.gov/data/tables/...",
        "title": "US Population by State 1920-2020",
        "snippet": "| State | 2000 | 2010 | 2020 |\n|-------|------|------|------|\n| Wyoming | 493,782 | 563,626 | 576,851 |\n...",
        "_source_type": "table_extraction",
        "_is_full_content": true,
        "_extraction_metadata": {
          "rows_count": 50,
          "columns_found": ["State", "2000", "2010", "2020"]
        }
      }
    ],
    "metadata": {
      "cost": 0.0,
      "num_results": 1,
      "strategy": "table_extraction",
      "is_url_content": true
    }
  }
}
```

**Key Differences from Search Results:**
- `_is_full_content: true` - Marks this as complete content (not truncated)
- `_source_type` - Identifies the content type (table_extraction, background_research, etc.)
- `_extraction_metadata` - Contains table-specific metadata (rows, columns)
- Multiple snippets per URL supported (different source_types get different IDs)

## Recall Algorithm

The recall process uses a **3-stage hybrid approach** to find relevant memories:

### Stage 1: Keyword Pre-Filter (Free, <50ms)

- Matches keywords against **full text** (query + all snippets)
- Scores queries by: query overlap + keyword matches
- Filters to top 30 candidate queries
- **Cost: $0**

### Stage 2: Gemini Source Selection (~$0.0002)

- Gemini selects most relevant sources from filtered queries
- Provides initial confidence assessment
- Returns selected sources with initial confidence
- **Model: gemini-2.0-flash**

### Stage 3: Verification with Full Snippets (~$0.0003)

**Triggered when:** Initial confidence ≥ 0.75

**Process:**
1. Provides full snippet text to Gemini (up to 2000 chars per source)
2. Includes context: breadth (narrow/broad) and depth (shallow/deep)
3. Provides today's date for recency assessment

**Gemini Returns:**
- **Confidence**: Probability (0.0-1.0) that sources can provide complete, accurate answer
- **Ranked source indices**: Which sources to use, in priority order (skips irrelevant ones)
- **Recommended searches**: 1-3 specific search terms to fill identified gaps

**Example Output:**
```json
{
  "confidence": 0.85,
  "can_answer": true,
  "ranked_source_indices": [2, 0, 4],
  "recommended_searches": [],
  "reasoning": "Sources cover syntax and typing well, comprehensive for shallow/broad answer"
}
```

**Total Recall Cost:** ~$0.0005 (all 3 stages)

## URL-Based Recall (with Keyword Validation)

When URLs are detected in the query (e.g., from Excel comments containing source references), the system uses **direct URL lookup** with keyword validation:

### `recall_by_urls(urls, required_keywords)`

```python
url_lookup_result = memory.recall_by_urls(
    urls=["https://census.gov/data/tables/..."],
    required_keywords=["Wyoming", "population"]  # Entity validation
)
```

**Returns:**
```json
{
  "found": [...],        // Sources that pass keyword validation
  "not_found": [...],    // URLs not in memory at all
  "needs_fetch": [...],  // URLs found but FAILED keyword validation
  "all_snippets": {...}  // All snippets per URL (for debugging)
}
```

### Keyword Validation Logic

When `required_keywords` is provided:
1. Each keyword group uses OR logic within (e.g., `"Wyoming|WY"`)
2. ALL keyword groups must match (AND logic between groups)
3. Searches both `snippet` and `title` (case-insensitive)

**Example:**
```python
required_keywords = ["Wyoming|WY", "population|census"]
# Matches if (Wyoming OR WY) AND (population OR census) found in snippet/title
```

### Multiple Snippets Per URL

The system returns **ALL snippets** for each URL:
- Search results (truncated by Perplexity)
- Table extractions (full content)
- Background research (authoritative sources)

**Priority Order:**
1. `_is_full_content=True` sources first (table extractions)
2. Longer snippets before shorter ones

### Handling Failed Keyword Validation

When stored snippets don't contain required entities:
1. URL goes to `needs_fetch` list
2. Clone fetches fresh content via Jina
3. Fresh content used for extraction

**Example Flow:**
```
Query: "Wyoming population 2020"
URL in prompt: census.gov/data/tables/...

1. recall_by_urls(["census.gov/..."], keywords=["Wyoming"])
2. Memory has truncated search snippet (Indiana, Texas... NOT Wyoming)
3. Keyword check fails → URL goes to needs_fetch
4. Jina fetches fresh census.gov content
5. Fresh content contains Wyoming → extraction succeeds
```

## Search Decision Logic

Based on Gemini's confidence assessment:

| Confidence | Action | Search Terms | Triage |
|------------|--------|--------------|--------|
| ≥ 0.85 | **SKIP** search | None | **SKIPPED** (Gemini pre-ranked) |
| 0.6-0.85 | **SUPPLEMENT** | Gemini's recommended (1-3) | **RUN** (rank memory + new sources) |
| < 0.6 | **FULL** search | Original terms | **RUN** (rank all sources) |

**Key Innovation:** When using memory-only (confidence ≥ 0.85):
- ✅ No search API call (saves $0.005)
- ✅ No triage call (saves ~$0.0002)
- ✅ Gemini pre-ranks sources in verification step
- ✅ Goes directly to extraction

## Integration into the_clone.py

### Modified Pipeline

```
Step 1: Initial Decision
  ↓ (generates: search_terms, keywords, breadth, depth)

Step 1.5: Memory Recall [NEW]
  ├─> Stage 1: Keyword filter
  ├─> Stage 2: Gemini selection
  └─> Stage 3: Verification (if confidence ≥ 0.75)
      - Provides full snippets
      - Considers breadth/depth
      - Returns: confidence, ranked sources, recommended searches
  ↓

Step 2: Search [MODIFIED]
  ├─> If confidence ≥ 0.85: SKIP
  ├─> If 0.6-0.85: Use recommended searches
  └─> If < 0.6: Full search
  ↓

Step 2.5: Deduplication [NEW]
  ↓ (Remove duplicate URLs between memory and search)

Step 3: Triage [OPTIMIZED]
  ├─> If memory-only: SKIP (already ranked by verification)
  └─> Else: Triage memory + search sources
  ↓

Step 4-5: Extraction & Synthesis [UNCHANGED]
```

## Usage

### Basic Usage (The Clone)

```python
from the_clone.the_clone import TheClone2Refined

clone = TheClone2Refined()

result = await clone.query(
    prompt="Your query",
    session_id="session_123",      # Required for memory
    email="user@example.com",      # Required for memory
    s3_manager=s3_manager,         # Required for memory
    use_memory=True                # Enable memory (default: True)
)

# Check memory stats
memory_stats = result['metadata']['memory_stats']
print(f"Search decision: {memory_stats['search_decision']}")
print(f"Confidence: {memory_stats['memory_confidence']}")
print(f"Recall cost: ${memory_stats['recall_cost']:.4f}")
```

### Direct Memory Usage

```python
from the_clone.search_memory import SearchMemory

# Initialize/restore memory
memory = await SearchMemory.restore(
    session_id="session_123",
    email="user@example.com",
    s3_manager=s3_manager,
    ai_client=ai_client
)

# Store a search
await memory.store_search(
    query="What is AI safety?",
    search_term="AI safety research",
    results=search_result,  # Perplexity API response
    parameters={'max_results': 10, 'max_tokens_per_page': 2048},
    strategy="survey"
)

# Recall memories
recall_result = await memory.recall(
    query="What are AI alignment techniques?",
    keywords={'positive': ['alignment', 'safety'], 'negative': []},
    max_results=10,
    confidence_threshold=0.6,
    breadth="broad",
    depth="shallow"
)

# Check results
print(f"Confidence: {recall_result['confidence']}")
print(f"Recommended searches: {recall_result['recommended_searches']}")
print(f"Memories found: {len(recall_result['memories'])}")
```

## Lambda Integration

### Challenge

The memory system requires:
- `session_id`: Unique session identifier
- `email`: User email for session path
- `s3_manager`: UnifiedS3Manager instance

These may not be readily available in all lambda contexts (validation, table_maker, etc.).

### Integration Patterns

**Pattern 1: Pass Through Lambda Event**
```python
# In lambda handler
session_id = event.get('session_id')
email = event.get('email')
s3_manager = UnifiedS3Manager()

clone = TheClone2Refined()
result = await clone.query(
    prompt=query,
    session_id=session_id,
    email=email,
    s3_manager=s3_manager,
    use_memory=True
)
```

**Pattern 2: Extract from Session Context**
```python
# If you have session_info
session_info = await s3_manager.load_session_info(email, session_id)

# Memory is automatically tied to this session
memory = await SearchMemory.restore(session_id, email, s3_manager)
```

**Pattern 3: Disable Memory (Fallback)**
```python
# If session context not available
result = await clone.query(
    prompt=query,
    use_memory=False  # Disable memory
)
```

### Validation Lambda Considerations

**Current State:**
- Validation lambda may not have session context readily available
- Would need to pass session_id and email through the validation request
- S3Manager already available in validation lambdas

**Recommendation:**
- Start with memory **disabled** in validation lambda
- Enable once session context is properly threaded through
- Memory is most valuable in interactive contexts (the_clone queries) where users ask follow-up questions

**Table Maker Integration:**
- Table Maker already has session_id and email
- Easy integration - pass to the_clone.query() if using clone for research
- **Table Maker now stores extracted tables to agent_memory automatically**

## Table Maker Memory Integration

Table Maker automatically stores extracted content to agent_memory during execution:

### What Gets Stored

**Step 0b (Table Extraction) - ONLY full table content:**
- Full markdown tables extracted from URLs
- Source type: `table_extraction`
- Includes all source URLs (primary and alternates)

**NOT stored:**
- Background research descriptions (brief summaries, not actual URL content)
- Storing brief descriptions would pollute memory with snippets that pass keyword validation but don't contain actual data

### Storage Flow

```
Table Maker Pipeline:
  ↓
Step 0: Background Research
  └─> Finds authoritative sources (NOT stored to memory - just descriptions)
  ↓
Step 0b: Table Extraction
  └─> store_url_content(source_url, markdown_table, "table_extraction")
  └─> store_url_content(alt_urls..., markdown_table, "table_extraction_alt")
  ↓
Excel Generated (with source URLs in cell comments)
  ↓
Validation runs later...
  └─> recall_by_urls(urls_from_comments, required_keywords)
  └─> Finds full table content in memory (if extracted)
  └─> If not in memory OR fails keywords → Jina fetches fresh
  └─> Extraction pulls specific data (e.g., Wyoming row)
```

### API: `store_url_content()`

```python
from the_clone.search_memory import SearchMemory

memory = SearchMemory(ai_client=ai_client)

await memory.store_url_content(
    url="https://census.gov/data/tables/...",
    content="| State | 2000 | 2010 | 2020 |\n|Wyoming|493,782|...",
    title="US Population by State",
    source_type="table_extraction",
    metadata={
        "rows_count": 50,
        "columns_found": ["State", "2000", "2010", "2020"],
        "session_id": "session_123"
    }
)
```

**Parameters:**
- `url`: Source URL (used for lookup)
- `content`: Full content (markdown table, text, etc.)
- `title`: Display title
- `source_type`: Content type identifier (allows multiple snippets per URL)
- `metadata`: Optional extraction metadata

**Behavior:**
- Generates unique ID based on URL + source_type
- Deduplicates by content length (keeps richer data)
- Sets `_is_full_content=True` flag
- Updates `by_url` index for recall

## Deduplication Rules

### 1. Same Query Deduplication (Storage)
- **Rule**: Only dedupe within same query
- **Key**: Hash of `query_text + search_term`
- **Behavior**:
  - Lower max_tokens → Skipped (preserve richer data)
  - Higher max_tokens → Updated (upgrade to richer data)

### 2. Memory vs Search Deduplication (Recall)
- **Rule**: Dedupe by URL before triage
- **Behavior**:
  - Same URL, different dates → Keep both (content may have changed)
  - Same URL, same/no date → Prefer search (fresher query context)

## Performance Characteristics

### Cold Start
- Load memory from S3: **50-100ms** for 100 queries (~50KB JSON)
- Memory footprint: **~500KB** for 100 queries with 8K snippets

### Recall Performance
- Stage 1 (keyword): **<50ms**
- Stage 2 (selection): **200-300ms**
- Stage 3 (verification): **300-400ms**
- **Total: ~500-750ms** (acceptable for lambda)

### Cost Analysis

**Per Query Savings:**
- Recall cost: **$0.0005**
- Search saved: **$0.0050** (if skipped)
- Triage saved: **$0.0002** (if skipped)
- **Net savings: ~$0.0047** (9.4x cheaper than search)

**Breakeven:**
- Memory pays for itself after **1 successful recall**
- Typical cost reduction: **40-60%** on follow-up queries

## Metadata Tracking

The system adds detailed memory statistics to query metadata:

```json
{
  "memory_stats": {
    "memory_enabled": true,
    "sources_recalled": 5,
    "sources_from_memory_after_dedup": 3,
    "sources_from_search": 0,
    "memory_confidence": 0.85,
    "search_decision": "skip",
    "search_decision_reasoning": "High confidence (0.85) - Gemini assessed sources as complete",
    "recall_cost": 0.0005,
    "memory_sources_cited": 3
  }
}
```

## Debug Logging

When `debug_dir` is specified, memory operations are fully logged in `FULL_LOG.md`:

```markdown
<details>
<summary><b>[SUCCESS] Step: Memory Recall</b></summary>

#### Memory Statistics
- Total Queries in Memory: 15
- Total Sources: 42
- Unique URLs: 38

#### Recall Results
- Queries After Keyword Filter: 8
- Sources Selected: 5
- Confidence: 0.85
- Recall Cost: $0.0005
- Verification: Ran with full snippets (2-stage recall)
- Recommended Searches: []

#### Search Decision
- Action: SKIP
- Reasoning: High confidence (0.85) - Gemini assessed sources as complete
</details>
```

## Key Features

### ✅ Implemented
- Session-scoped memory with S3 persistence
- 3-stage hybrid recall (keyword + 2x Gemini)
- Context-aware verification (breadth/depth)
- Intelligent source selection (skip irrelevant sources)
- Targeted supplemental searches (Gemini recommends gaps)
- Triage skipping for memory-only queries
- Full debug logging and cost tracking
- Deduplication (same query + memory vs search)
- Proper nouns in keywords
- Sparse negative keywords (only when needed)
- **Direct URL content storage** (`store_url_content()`)
- **URL-based recall with keyword validation** (`recall_by_urls(required_keywords)`)
- **Multiple snippets per URL** (search results + table extractions)
- **Table Maker integration** (auto-stores extracted tables)
- **Full content prioritization** (`_is_full_content` sources ranked first)

### 📊 Performance Metrics
- Recall time: ~500-750ms
- Recall cost: ~$0.0005
- Search skip rate: ~40-60% on follow-up queries
- Cost reduction: ~9.4x when search is skipped

## Files

### New Files
- `src/the_clone/search_memory.py` - Core memory class
- `src/the_clone/prompts/memory_recall.md` - Source selection prompt template
- `src/the_clone/tests/test_memory.py` - Unit tests
- `src/the_clone/test_memory_integration.py` - Integration test
- `docs/SEARCH_MEMORY_SYSTEM.md` - This documentation

### Modified Files
- `src/the_clone/the_clone.py` - Full integration (Step 1.5, search decision, triage skip, URL keyword validation)
- `src/the_clone/search_memory.py` - Added `store_url_content()`, enhanced `recall_by_urls()` with keyword validation
- `src/the_clone/prompts/initial_decision.md` - Proper nouns, sparse negative keywords
- `src/the_clone/initial_decision_schemas.py` - Negative keywords optional
- `src/lambdas/interface/actions/table_maker/execution.py` - Stores extracted tables to agent_memory

## Future Enhancements

### Potential Improvements
1. **Cross-session memory**: User-level memory across all sessions
2. **Memory pruning**: Auto-cleanup old queries (>90 days)
3. **Semantic search**: Embeddings for better query matching
4. **Memory analytics**: Track hit rate, cost savings, confidence trends
5. **Lambda context helper**: Auto-detect session_id/email from event

### Known Limitations
- Requires session_id and email (not available in all contexts)
- Memory scope limited to single session
- Verification runs on snippet previews (2000 chars), not full content
- Self-assessment "B" triggers improvement searches (bypasses memory savings)

## Troubleshooting

### Memory Not Working

**Check:**
1. `use_memory=True` parameter passed
2. `session_id` and `email` provided
3. `s3_manager` instance available
4. S3 bucket accessible (check permissions)

**Logs to check:**
```
[CLONE] Memory not available (missing session_id, email, or s3_manager)
```

### Low Confidence

**Possible causes:**
1. First query in session (no memory yet)
2. Query topic very different from past queries
3. Breadth/depth requirements higher than memory sources support
4. Sources are outdated (recency matters for this query)

**Solution:**
- Memory improves over time as more queries are stored
- Confidence will increase with more diverse stored queries

### High Costs Despite Memory

**Likely cause:**
- Self-assessment "B" triggers improvement iteration
- Clone searches for additional sources to improve answer quality
- Memory saved initial search, but improvement searches still executed

**This is normal** - memory provides starting point, clone augments if needed

## Example: Lambda Integration

```python
# Example: Validation Lambda with Memory Support

async def lambda_handler(event, context):
    """Validation lambda with optional memory support."""

    # Extract parameters
    query = event.get('query')
    session_id = event.get('session_id')  # Must be passed from frontend
    email = event.get('email')            # Must be passed from frontend

    # Initialize managers
    s3_manager = UnifiedS3Manager()
    clone = TheClone2Refined()

    # Check if memory context available
    use_memory = bool(session_id and email)

    if use_memory:
        logger.info(f"Memory enabled for session {session_id}")
    else:
        logger.info("Memory disabled (no session context)")

    # Run query with optional memory
    result = await clone.query(
        prompt=query,
        session_id=session_id if use_memory else None,
        email=email if use_memory else None,
        s3_manager=s3_manager if use_memory else None,
        use_memory=use_memory
    )

    return result
```

## Cost Comparison

| Scenario | Without Memory | With Memory | Savings |
|----------|----------------|-------------|---------|
| **First query** | $0.0080 | $0.0080 | $0 (no memory yet) |
| **Follow-up (high confidence)** | $0.0080 | $0.0033 | **$0.0047 (59%)** |
| **Follow-up (supplement)** | $0.0080 | $0.0055 | **$0.0025 (31%)** |
| **Follow-up (full search)** | $0.0080 | $0.0085 | **-$0.0005 (-6%)** |

**Note:** Costs shown are for initial pipeline only. Self-assessment improvements may add additional costs regardless of memory usage.

## Success Criteria

The memory system is working correctly when:

1. ✅ **Storage**: Searches automatically stored in memory
2. ✅ **Recall**: Follow-up queries find relevant memories
3. ✅ **Confidence**: Gemini assessments are reasonable (0.6-0.9 range)
4. ✅ **Skip rate**: 30-50% of follow-up queries skip initial search
5. ✅ **Triage skip**: Memory-only queries skip triage
6. ✅ **Cost tracking**: Recall costs properly tracked by provider
7. ✅ **Debug logs**: Memory steps visible in FULL_LOG.md

## Monitoring

### Key Metrics to Track

- **Memory hit rate**: % of queries that skip/supplement search
- **Average confidence**: Mean confidence across recalls
- **Cost savings**: Total saved from skipped searches
- **Recall latency**: p50, p95, p99 recall times
- **Verification rate**: % of recalls that run verification

### Log Examples

**Successful Skip:**
```
[MEMORY] Keyword filter: 10 → 5 candidate queries
[MEMORY] Gemini selected 3 sources, confidence=0.85
[MEMORY] High confidence (0.85), running verification...
[MEMORY] Verification: confidence=0.90, ranked_sources=3, recommended_searches=0
[CLONE] Search decision: skip - High confidence (0.90)
[CLONE] Step 3: Skipping triage (memory sources already ranked)
```

**Supplement Decision:**
```
[MEMORY] Verification: confidence=0.72, recommended_searches=2
[CLONE] Search decision: supplement - Using Gemini's recommended searches
[SEARCH] Executing 2 searches: ['Python 3.12 performance', 'PEP 709 benchmarks']
```
