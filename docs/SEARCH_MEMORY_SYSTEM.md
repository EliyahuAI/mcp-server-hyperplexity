# Search Memory System

## Overview

The Search Memory System is a session-scoped memory layer for the Perplexity Search API that stores all search results and intelligently recalls them to avoid redundant searches, reduce costs, and improve response times.

The system also supports **direct URL content storage** for Table Maker extractions, enabling full table data to be stored and recalled during validation - ensuring extracted tables are available even when Perplexity search snippets are truncated.

## Architecture

### Storage Design

**In-Process Cache (Parallel Agent Access):**
- Module-level singleton (`_MEMORY_CACHE`) shared across all async agents
- Zero latency: All agents read/write to same RAM
- Thread-safe: Mutex-protected access
- Automatic backup check: Loads from S3 if needed
- Single S3 write at batch end (not per-search)

**In-Memory (Runtime):**
- Volatile RAM storage during lambda/process execution
- Fast access for recall operations
- Lazy loading from S3 on initialization or on-demand

**S3 Persistence:**
- Location: `s3://.../results/{domain}/{email}/{session_id}/agent_memory.json`
- Backup: ~~After each search (continuous)~~ **At batch end only** (via `MemoryCache.flush()`)
- Restore: On lambda initialization or when `MemoryCache.get()` is called
- Concurrency: ~~Optimistic locking with retry~~ **No concurrency issues - single write per batch**

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

The recall process uses a **2-stage approach** with optional verification:

### Stage 1: Keyword Pre-Filter (Free, <50ms)

- Matches keywords against **full text** (query + all snippets)
- Scores queries by: query overlap + keyword matches
- Filters to top 30 candidate queries
- **Cost: $0**

### Stage 2: Gemini Source Selection (~$0.0002)

- Gemini selects most relevant sources from filtered queries
- Returns selected sources (confidence determined later by extraction)
- **Model: gemini-2.0-flash**

### Stage 3: Verification (SKIPPED in Extract-Then-Verify mode)

**Note:** The clone now uses `skip_verification=True` by default. Confidence is determined by actual extracted snippets, not preview-based verification. See "Extract-Then-Verify Architecture" below.

**Total Recall Cost:** ~$0.0002 (selection only, verification skipped)

---

## Extract-Then-Verify Architecture

**The Problem:** Preview-based verification could return high confidence (0.90) but extraction would find 0 snippets (false positive).

**The Solution:** Extract from memory sources FIRST, then assess confidence based on actual extracted quotes.

### Flow

```
Memory Recall (skip_verification=True)
    ↓
memory_sources = selected sources (no confidence yet)
    ↓
Extract from memory sources → memory_snippets (with p-scores)
    ↓
assess_snippet_confidence(memory_snippets, search_terms)
    ↓
confidence = based on actual snippet count & quality
    ↓
Search Decision (using real confidence)
    ↓
Search (if low confidence)
    ↓
Dedupe search results by URL (remove URLs in memory_snippets)
    ↓
Triage search results (existing_snippets=memory_snippets)
    ↓
Extract from search sources
    ↓
all_snippets = memory_snippets + search_snippets
    ↓
Synthesis
```

### Confidence Assessment (snippet_confidence.py)

Heuristic based on actual extracted snippets:

| Snippets | Avg p-score | Confidence |
|----------|-------------|------------|
| 0        | N/A         | 0.0        |
| 1-2      | < 0.7       | 0.3-0.5    |
| 3+       | ≥ 0.85      | 0.85+      |

**Per-term confidence:** Each search term gets its own confidence based on snippets that match that term.

### Benefits

1. **No false positives** - 0 snippets = 0 confidence (impossible to claim high confidence with no data)
2. **Accurate cost** - Extraction cost tracked separately from recall
3. **Simple triage** - Pass `existing_snippets=memory_snippets` so triage knows what we have

## URLs in Query Input

The system automatically detects and handles URLs mentioned in the user's query.

### URL Extraction from Prompt

```python
from the_clone.search_memory import extract_urls_from_text

# Automatically extracts URLs from query
query_urls = extract_urls_from_text(prompt)
# ["https://census.gov/data/tables/...", "https://bls.gov/..."]
```

### How URLs in Query Are Processed

```
User Query: "What is Wyoming's population? See https://census.gov/data/..."
    ↓
extract_urls_from_text(prompt) → ["https://census.gov/..."]
    ↓
recall_by_urls(urls, required_keywords=["Wyoming"])
    ↓
├─> URL found in memory + passes keywords → url_sources
├─> URL found but fails keywords → needs_fetch (Jina fetches live)
└─> URL not in memory → not_found (Jina fetches live)
    ↓
url_sources passed to memory.recall() as priority sources
    ↓
Gemini selection sees URL sources at TOP (query_index=-1)
    ↓
URL sources ALWAYS included in final memory_sources
```

### Priority Handling

URLs mentioned in the query receive special treatment:

1. **Lookup in memory first** - Avoids redundant fetches
2. **Keyword validation** - Ensures stored content has required entities
3. **Jina fallback** - Fetches fresh if memory doesn't have valid content
4. **Always included** - URL sources bypass ranking (user explicitly mentioned them)

### Skip-to-Synthesis Mode

When certain conditions are met, the clone can skip directly to synthesis using URL content:

```python
# In the_clone.py, skip-to-synthesis checks:
if (initial_decision['action'] == 'answer_directly'
    and query_urls
    and memory):
    # Look up URLs in memory
    url_lookup_result = memory.recall_by_urls(
        urls=query_urls,
        required_keywords=skip_required_keywords
    )
    # If URLs found with valid content → skip search entirely
```

---

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

### Modified Pipeline (Extract-Then-Verify)

```
Step 1: Initial Decision
  ↓ (generates: search_terms, keywords, breadth, depth)

Step 1.5: Memory Recall + Extraction [EXTRACT-THEN-VERIFY]
  ├─> Stage 1: Keyword filter
  ├─> Stage 2: Gemini selection (skip_verification=True)
  ├─> Extract from memory_sources → memory_snippets
  └─> assess_snippet_confidence(memory_snippets) → confidence
  ↓

Step 2: Search [MODIFIED]
  ├─> If confidence ≥ 0.85: SKIP
  ├─> If 0.6-0.85: Supplement (low-confidence terms only)
  └─> If < 0.6: Full search
  ↓

Step 2.5: URL Deduplication [SIMPLIFIED]
  ↓ (Remove search results whose URLs are already in memory_snippets)

Step 3: Triage [SIMPLIFIED]
  ├─> If memory-only: SKIP (memory_snippets already extracted)
  └─> Else: Triage search results with existing_snippets=memory_snippets
  ↓

Step 4: Extraction [MEMORY-AWARE]
  ├─> all_snippets starts with memory_snippets
  └─> Extract from search sources only (memory already done)
  ↓

Step 5: Synthesis
  └─> Uses all_snippets (memory + search combined)
```

### Key Changes from Previous Architecture

1. **Memory extraction happens BEFORE confidence assessment** - No more false positives
2. **Triage receives `existing_snippets=memory_snippets`** - Knows what we already have
3. **Memory sources NOT added to search_results** - Clean separation
4. **Deduplication by URL against memory_snippets** - Simple and effective

## Usage

### MemoryCache (Recommended for Parallel Execution)

**Use MemoryCache for parallel agents** to avoid S3 write conflicts and improve performance:

```python
from the_clone.search_memory_cache import MemoryCache

# Get shared memory (loads from S3 if not cached)
memory = MemoryCache.get(session_id, email, s3_manager, ai_client)

# Use memory for recall (same API as SearchMemory)
recall_result = await memory.recall(query, keywords, ...)

# Store search results (RAM only, no S3 write)
MemoryCache.store_search(
    session_id=session_id,
    search_term="AI safety research",
    results=search_result,
    parameters={'max_results': 10},
    strategy="survey"
)

# Store URL content (for table extractions)
MemoryCache.store_url_content(
    session_id=session_id,
    url="https://example.com/table",
    content=table_markdown,
    source_type="table_extraction"
)

# At batch end: flush to S3 (REQUIRED!)
await MemoryCache.flush(session_id)
# Or flush all dirty sessions:
await MemoryCache.flush_all()
```

**Performance:**
- Read/write during execution: **0ms** (RAM only)
- Flush at batch end: **2-5s** (single S3 write)
- Speedup vs per-search writes: **10x faster**

### Basic Usage (The Clone)

```python
from the_clone.the_clone import TheClone2Refined
from the_clone.search_memory_cache import MemoryCache

clone = TheClone2Refined()

result = await clone.query(
    prompt="Your query",
    session_id="session_123",      # Required for memory
    email="user@example.com",      # Required for memory
    s3_manager=s3_manager,         # Required for memory
    use_memory=True                # Enable memory (default: True)
)

# After batch: flush memory
await MemoryCache.flush(session_id)

# Check memory stats
memory_stats = result['metadata']['memory_stats']
print(f"Search decision: {memory_stats['search_decision']}")
print(f"Confidence: {memory_stats['memory_confidence']}")
print(f"Recall cost: ${memory_stats['recall_cost']:.4f}")
```

### Direct Memory Usage (Legacy)

**Note:** For parallel execution, use MemoryCache instead to avoid S3 conflicts.

```python
from the_clone.search_memory import SearchMemory

# Initialize/restore memory
memory = await SearchMemory.restore(
    session_id="session_123",
    email="user@example.com",
    s3_manager=s3_manager,
    ai_client=ai_client
)

# Store a search (writes to S3 immediately - slow for parallel!)
await memory.store_search(
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

### 2. Memory vs Search Deduplication (Extract-Then-Verify)
- **Rule**: Remove search results whose URLs are already in `memory_snippets`
- **When**: After search execution, before triage
- **Logic**:
  ```python
  memory_urls = {s.get('_source_url') for s in memory_snippets}
  result['results'] = [r for r in results if r.get('url') not in memory_urls]
  ```
- **Note**: Same URL with different search term could yield different Perplexity snippets. Current implementation prefers memory (already extracted). Future enhancement could compare snippet content.

### 3. Triage Awareness
- **Rule**: Triage receives `existing_snippets=memory_snippets`
- **Benefit**: Triage can deprioritize search results that cover same ground as memory
- **Logic**: Built into triage prompt - "these snippets already exist, rank new sources by unique value"

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
- Recall Cost: $0.0002

#### Memory Extraction Results
- Sources Processed: 5
- Snippets Extracted: 8
- Extraction Time: 1.2s
- Extraction Cost: $0.0008
- Provider: gemini
- Avg Quality: 0.82
- High Quality (p>=0.85): 5

#### Snippet-Based Confidence
- Overall Confidence: 0.85
- Assessment Method: Snippet-based (extract-then-verify)
- Snippets Assessed: 8
- Term 1: "Python 3.12 features": conf=0.90, snippets=5
- Term 2: "type hints": conf=0.80, snippets=3
- Recommended Searches: None (all terms covered)

#### Search Decision
- Action: SKIP
- Reasoning: High confidence (0.85) - Snippet-based assessment
</details>
```

## Memory Copying (Config Match)

When a matching configuration is copied to a new session, `agent_memory.json` is also copied if it exists:

### What Gets Copied
- All stored queries and their results
- URL indexes for fast lookup
- A system caution note about data freshness

### Caution Note Added
```json
{
  "type": "system_caution",
  "message": "Memory copied from session X on 2025-01-15. Contains data from both original and current session. For dynamic content, check query_time for freshness.",
  "copied_from_session": "session_20250110_...",
  "copied_on": "2025-01-15"
}
```

### Session Info Tracking
The memory copy is recorded in `session_info.json`:
```json
{
  "agent_memory_copied": {
    "copied_from_session": "session_20250110_...",
    "copied_at": "2025-01-15T10:30:00Z",
    "queries_copied": 15,
    "caution_note_added": true
  }
}
```

### Data Freshness Handling
- Each memory stores `query_time` (when it was captured)
- Verification prompts show **relative time** (e.g., "2 days ago", "1 week ago")
- Dynamic content warning in verification prompts alerts LLM to check freshness
- Recency scoring gives priority to fresher memories in recall

## Key Features

### ✅ Implemented
- Session-scoped memory with S3 persistence
- **RAM-based cache for parallel agents** (`MemoryCache` - zero latency, no S3 conflicts)
- **Automatic backup check** (loads from S3 if not in cache)
- **Single S3 write per batch** (no per-search writes)
- **Extract-then-verify architecture** (no false positives)
- **Snippet-based confidence** (assessed from actual extracted quotes)
- 2-stage recall (keyword + Gemini selection, verification skipped)
- Intelligent source selection (skip irrelevant sources)
- Targeted supplemental searches (low-confidence terms only)
- Triage skipping for memory-only queries
- **Triage awareness** (`existing_snippets=memory_snippets`)
- Full debug logging and cost tracking
- Deduplication (URL-based against memory_snippets)
- Proper nouns in keywords
- Sparse negative keywords (only when needed)
- **Direct URL content storage** (`store_url_content()`)
- **URL extraction from prompt** (`extract_urls_from_text()`)
- **URL-based recall with keyword validation** (`recall_by_urls(required_keywords)`)
- **Multiple snippets per URL** (search results + table extractions)
- **Table Maker integration** (auto-stores extracted tables)
- **Full content prioritization** (`_is_full_content` sources ranked first)
- **Memory copying on config match** (copies agent_memory.json with caution note)
- **Recency priority scoring** (fresher memories get priority in recall)
- **Relative time display** (verification shows "2 days ago" not timestamps)
- **Jina-fetched URL storage** (live-fetched URLs stored to memory for future recall)

### 📊 Performance Metrics
- Recall time: ~500-750ms
- Recall cost: ~$0.0005
- Search skip rate: ~40-60% on follow-up queries
- Cost reduction: ~9.4x when search is skipped

## Files

### New Files
- `src/the_clone/search_memory.py` - Core memory class + `extract_urls_from_text()`
- `src/the_clone/search_memory_cache.py` - **RAM-based cache for parallel agents**
- `src/the_clone/snippet_confidence.py` - **Snippet-based confidence assessment** (extract-then-verify)
- `src/the_clone/prompts/memory_recall.md` - Source selection prompt template
- `src/the_clone/tests/test_memory.py` - Unit tests
- `src/the_clone/test_memory_integration.py` - Integration test
- `docs/SEARCH_MEMORY_SYSTEM.md` - This documentation
- `docs/MEMORY_CACHE_INTEGRATION.md` - RAM cache integration guide
- `docs/EXTRACT_THEN_VERIFY_REFACTOR.md` - Extract-then-verify architecture notes

### Modified Files
- `src/the_clone/search_memory.py` - Added `skip_verification` parameter, URL extraction
- `src/the_clone/the_clone.py` - Extract-then-verify flow, triage with `existing_snippets`, URL deduplication
- `src/the_clone/prompts/initial_decision.md` - Proper nouns, sparse negative keywords
- `src/the_clone/initial_decision_schemas.py` - Negative keywords optional
- `src/lambdas/interface/actions/table_maker/execution.py` - Stores extracted tables to agent_memory
- `src/lambdas/interface/actions/copy_config.py` - Copies agent_memory.json when copying config

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

### Known Issue: URL Memory Storage Gap

**Issue documented in:** `docs/MEMORY_URL_STORAGE_ISSUE.md`

**Summary:** URLs cited in validation output may not appear in `agent_memory.json`, causing subsequent runs to re-fetch via Jina.

**Fix applied:** Jina-fetched URLs are now stored to memory in `fetch_url_content()` (lines 1987-2002 in `search_memory.py`).

**Open question:** Why would Jina be called in the first validation run at all? This remains unexplained. See the issue doc for details.

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

### URLs Not Being Recalled

**Symptom:** URL Memory Lookup shows URLs as "Not in Memory" even though they were used in a previous validation.

**Debug steps:**
1. Check `[CLONE_MEMORY_DEBUG]` logs for how many URLs were stored
2. Check `[MEMORY_CACHE]` flush logs for query/URL counts
3. Compare citation URLs with URLs in search results

**See:** `docs/MEMORY_URL_STORAGE_ISSUE.md` for detailed analysis of this issue.

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

**Memory Debug Logging (for MEMORY_URL_STORAGE_ISSUE):**
```
[CLONE_MEMORY_DEBUG] Stored 3 searches with 15 URLs to memory (RAM cache)
[MEMORY_CACHE] Flushing 72 queries, 156 unique URLs to S3 for session session_123
[CLONE_MEMORY_DEBUG] Citations: 5 total, 2 from memory, 2 from search, 1 from Jina
[CLONE_MEMORY_DEBUG] Jina-fetched URLs: ['https://example.com/...']
```

## Citation-Aware Memory System

The memory system includes **citation-aware storage and recall** that avoids redundant extraction by returning pre-extracted citations when they match the required keywords.

### How It Works

**After Extraction**: When snippets are extracted from sources, they are stored as citations with `hit_keywords` (the required keywords that were found in the citation).

**During Recall**: Before extracting from a source, the system checks if there are already stored citations that match the current query's required keywords. If found, the cached citations are returned directly without re-extraction.

### Citation Storage Structure

```json
{
  "sources": {
    "source_abc123": {
      "url": "https://census.gov/population-by-state",
      "title": "US Population by State",
      "content": "Full table...",
      "source_type": "search",
      "search_term": "US state population 2020",
      "citations": [
        {
          "quote": "Wyoming: 576,851",
          "p_score": 0.92,
          "context": "Census 2020 table",
          "hit_keywords": ["Wyoming", "population", "2020"],
          "extracted_at": "2026-01-20T10:30:00Z"
        },
        {
          "quote": "Montana: 1,084,225",
          "p_score": 0.89,
          "context": "Census 2020 table",
          "hit_keywords": ["Montana", "population", "2020"],
          "extracted_at": "2026-01-20T11:00:00Z"
        }
      ]
    }
  }
}
```

### Citation-Aware Recall Flow

```python
# Check for cached citations before extraction
result = MemoryCache.recall_citations(
    session_id=session_id,
    url=source_url,
    required_keywords=['Wyoming', 'population']
)

if result['found'] and not result['needs_extraction']:
    # Use cached citations directly (no extraction needed)
    for citation in result['citations']:
        snippet = convert_citation_to_snippet(citation)
        memory_snippets.append(snippet)
else:
    # Need extraction - run extraction then store
    snippets = await extractor.extract(source)
    MemoryCache.store_citations(
        session_id=session_id,
        url=source_url,
        citations=snippets_to_citations(snippets, required_keywords)
    )
```

### Citation Accumulation

Citations accumulate over time for the same source. Different validation runs with different entities add new citations:

1. **First validation** (Wyoming population): Extracts and stores citation with `hit_keywords: ["Wyoming", "population"]`
2. **Second validation** (Montana population): Same source, extracts and stores citation with `hit_keywords: ["Montana", "population"]`
3. **Third validation** (Wyoming population again): **Recalls cached citation** - no extraction needed

### MemoryCache Citation Methods

```python
# Store citations after extraction
MemoryCache.store_citations(
    session_id=session_id,
    url="https://census.gov/pop",
    content="Full table content...",
    title="Census Data",
    search_term="state population 2020",
    citations=[{
        'quote': 'Wyoming: 576,851',
        'p_score': 0.92,
        'context': 'Census table',
        'hit_keywords': ['Wyoming', 'population'],
        'extracted_at': '2026-01-20T10:30:00Z'
    }],
    source_type="search"
)

# Recall cached citations
result = MemoryCache.recall_citations(
    session_id=session_id,
    url="https://census.gov/pop",
    required_keywords=['Wyoming', 'population']
)

# Get citation statistics
stats = MemoryCache.get_citation_stats(session_id)
print(f"Total citations: {stats['total_citations']}")
```

### Debug Logging

```
[CLONE] Citation recall HIT: 3 citations match keywords ['Wyoming', 'population']
[CLONE] Citation recall MISS: sources found but no citations match keywords ['California']
[CLONE] Memory processing: 5 snippets (2 from cache, 3 extracted) (1.2s, $0.0012)
[CLONE] Stored 4 citations from 2 sources (type: search_extraction)
```

### Related Documentation

- `docs/CITATION_AWARE_MEMORY_PLAN.md` - Implementation plan and design details
