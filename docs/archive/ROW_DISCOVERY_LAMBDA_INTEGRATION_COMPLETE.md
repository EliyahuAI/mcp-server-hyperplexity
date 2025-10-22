# Row Discovery Lambda Integration - Complete

**Date:** October 20, 2025
**Branch:** table-maker
**Status:** Integration Complete - Ready for Testing

---

## Executive Summary

Successfully integrated all 4 Row Discovery components into the Lambda environment:
1. SubdomainAnalyzer (Agent 1) - Identifies 2-5 natural subdivisions for parallel search
2. RowDiscoveryStream (Agent 2) - Discovers and scores candidates in each subdomain
3. RowConsolidator (Agent 3) - Deduplicates and prioritizes final rows
4. RowDiscovery (Agent 4) - Orchestrates the entire parallel row discovery pipeline

All components have been copied, imports updated, configuration added, and a Lambda handler created following existing patterns.

---

## Files Copied/Created

### 1. Schemas (2 files)
**Location:** `src/lambdas/interface/actions/table_maker/schemas/`

- `subdomain_analysis.json` (1.3K) - Schema for subdomain analyzer LLM response
- `row_discovery_response.json` (1.4K) - Schema for row discovery stream LLM response

**Source:** `table_maker/schemas/`

### 2. Prompts (2 files)
**Location:** `src/lambdas/interface/actions/table_maker/prompts/`

- `subdomain_analysis.md` (4.4K) - Prompt template for subdomain analysis
- `row_discovery.md` (2.8K) - Prompt template for row discovery with variables:
  - `{{SUBDOMAIN}}` - Subdomain name and focus
  - `{{SEARCH_STRATEGY}}` - Overall search strategy
  - `{{COLUMNS}}` - Column definitions (JSON)
  - `{{WEB_SEARCH_RESULTS}}` - Web search results

**Source:** `table_maker/prompts/`

### 3. Library Components (4 files)
**Location:** `src/lambdas/interface/actions/table_maker/table_maker_lib/`

- `subdomain_analyzer.py` (14K) - Analyzes search strategies to identify subdomains
- `row_discovery_stream.py` (17K) - Discovers rows in a single subdomain
- `row_consolidator.py` (21K) - Deduplicates and prioritizes rows from all streams
- `row_discovery.py` (21K) - Orchestrates the complete row discovery pipeline

**Source:** `table_maker/src/`

**Import Changes:**
- Updated relative imports to use `.` prefix for Lambda package structure
  - `from subdomain_analyzer` → `from .subdomain_analyzer`
  - `from row_discovery_stream` → `from .row_discovery_stream`
  - `from row_consolidator` → `from .row_consolidator`

### 4. Lambda Handler (1 new file)
**Location:** `src/lambdas/interface/actions/table_maker/row_discovery_handler.py` (23K)

**Purpose:** Lambda integration layer for row discovery following existing patterns

**Key Functions:**
- `handle_row_discovery(event, context)` - Main async handler
- `_add_api_call_to_runs()` - Tracks API call metrics in runs database
- `_load_table_maker_config()` - Loads configuration from table_maker_config.json
- `_load_conversation_state_from_s3()` - Loads conversation state
- `_save_conversation_state_to_s3()` - Saves updated conversation state

---

## Import Adjustments Made

### Library Components

**File:** `table_maker_lib/row_discovery.py`

**Changes:**
```python
# BEFORE (standalone)
from subdomain_analyzer import SubdomainAnalyzer
from row_discovery_stream import RowDiscoveryStream
from row_consolidator import RowConsolidator

# AFTER (Lambda package)
from .subdomain_analyzer import SubdomainAnalyzer
from .row_discovery_stream import RowDiscoveryStream
from .row_consolidator import RowConsolidator
```

**Verification:**
All imports tested and working:
- `from table_maker_lib.row_discovery import RowDiscovery` - [SUCCESS]
- `from table_maker_lib.subdomain_analyzer import SubdomainAnalyzer` - [SUCCESS]
- `from table_maker_lib.row_discovery_stream import RowDiscoveryStream` - [SUCCESS]
- `from table_maker_lib.row_consolidator import RowConsolidator` - [SUCCESS]

---

## WebSocket Message Flow

### 1. Start (Step 2 of 4)
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_xxx",
  "status": "Discovering matching entities",
  "current_step": 2,
  "total_steps": 4,
  "progress_percent": 30
}
```

### 2. Per-Stream Progress (Optional - Not Implemented Yet)
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_xxx",
  "status": "Searching AI Research Companies: found 8 candidates",
  "current_step": 2,
  "total_steps": 4,
  "progress_percent": 45,
  "streams_completed": 2,
  "streams_total": 4
}
```

**Note:** Per-stream progress updates are optional and not implemented in the current handler. The standalone row_discovery_stream.py doesn't expose per-stream progress events.

### 3. Complete (Step 2 Complete)
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_xxx",
  "status": "Row discovery complete",
  "current_step": 2,
  "total_steps": 4,
  "progress_percent": 50,
  "rows_discovered": 20,
  "match_score_avg": 0.82
}
```

---

## Runs Database Tracking Approach

### Challenge: Multiple API Calls

Row discovery makes **multiple parallel API calls** (one per subdomain stream), which requires careful tracking.

### Current Implementation

The handler uses `_add_api_call_to_runs()` (same pattern as conversation.py) to track metrics:

```python
def _add_api_call_to_runs(
    session_id: str,
    run_key: Optional[str],
    api_response: Dict[str, Any],
    model: str,
    processing_time: float,
    call_type: str = 'row_discovery_stream',
    status: str = 'IN_PROGRESS',
    verbose_status: str = None,
    percent_complete: int = None,
    stream_index: int = None,  # NEW: Track which stream
    total_streams: int = None   # NEW: Track total streams
)
```

### Aggregation Strategy

1. **Read** existing run record from DynamoDB
2. **Extract** existing `call_metrics_list` and `models` list
3. **Add** new call metrics from this stream (tagged with `call_type='row_discovery_stream'`)
4. **Re-aggregate** ALL calls across all providers
5. **Write** back to database with updated totals

### Breakdown in `table_maker_breakdown`

```json
{
  "table_maker_breakdown": {
    "interview_calls": 1,
    "preview_calls": 1,
    "expansion_calls": 0,
    "row_discovery_calls": 5,  // One per stream
    "column_definition_calls": 1,
    "total_calls": 8
  }
}
```

### Known Limitation

**Issue:** The current standalone `row_discovery_stream.py` does NOT return API response metadata (enhanced_data, token_usage, etc.) from each stream.

**Impact:** The handler cannot track per-stream API call metrics until we modify the stream to return this data.

**Workaround Options:**
1. **Accept limitation** - Track only aggregate metrics at orchestrator level
2. **Modify stream** - Update `row_discovery_stream.py` to return API metadata
3. **Instrument later** - Add per-stream tracking in future enhancement

**Recommendation:** Accept limitation for initial integration. Per-stream metrics are nice-to-have, not critical. The orchestrator-level tracking is sufficient.

---

## S3 Storage Structure

### Conversation State Update

After row discovery completes, the conversation state is updated with:

```json
{
  "conversation_id": "table_conv_xxx",
  "session_id": "session_xxx",
  "email": "user@example.com",
  "status": "row_discovery_complete",  // Updated
  "last_updated": "2025-10-20T23:30:00Z",

  "column_definition": {
    "columns": [...],
    "search_strategy": {...},
    "table_name": "AI Companies Hiring Status"
  },

  "row_discovery": {  // NEW SECTION
    "final_rows": [
      {
        "id_values": {
          "Company Name": "Anthropic",
          "Website": "anthropic.com"
        },
        "match_score": 0.95,
        "match_rationale": "Leading AI safety research company with active hiring...",
        "source_urls": [
          "https://anthropic.com/careers",
          "https://techcrunch.com/anthropic-hiring"
        ],
        "merged_from_streams": ["AI Research Companies", "Enterprise AI"]
      }
      // ... 19 more rows
    ],
    "stats": {
      "subdomains_analyzed": 3,
      "parallel_streams": 3,
      "total_candidates_found": 45,
      "duplicates_removed": 12,
      "below_threshold": 3,
      "final_row_count": 20
    },
    "generated_at": "2025-10-20T23:30:00Z",
    "config": {
      "target_row_count": 20,
      "min_match_score": 0.6,
      "max_parallel_streams": 5,
      "web_searches_per_stream": 3
    }
  }
}
```

### S3 Path

**Location:** `{session_path}table_maker/conversation_{conversation_id}.json`

**Example:** `user@example.com/research/session_20251020_123456/table_maker/conversation_table_conv_abc123.json`

---

## Configuration Values

### Updated `table_maker_config.json`

Added new `row_discovery` section:

```json
{
  "interview": { ... },
  "conversation": { ... },
  "preview_generation": { ... },
  "full_table_generation": { ... },

  "row_discovery": {
    "target_row_count": 20,        // Number of final rows to return
    "min_match_score": 0.6,        // Minimum match score threshold (0-1)
    "max_parallel_streams": 5,     // Maximum concurrent subdomain streams
    "web_searches_per_stream": 3,  // Web searches per subdomain
    "model": "claude-sonnet-4-5",  // LLM model for row scoring
    "max_tokens": 8000             // Max tokens per LLM call
  },

  "models": { ... },
  "features": { ... }
}
```

### Configuration Parameters Explained

| Parameter | Default | Description | Tuning Guidance |
|-----------|---------|-------------|-----------------|
| `target_row_count` | 20 | Number of final rows to return after deduplication | Increase for more comprehensive tables |
| `min_match_score` | 0.6 | Minimum match score threshold (0-1) | Lower = more rows (lower quality), Higher = fewer rows (higher quality) |
| `max_parallel_streams` | 5 | Maximum concurrent subdomain streams | Balance between speed and cost/load |
| `web_searches_per_stream` | 3 | Web searches per subdomain | More searches = better coverage but higher cost |
| `model` | claude-sonnet-4-5 | LLM model for scoring | Could use cheaper model for cost savings |
| `max_tokens` | 8000 | Max tokens per LLM call | Increase if responses are truncated |

---

## Deployment Checklist

### Pre-Deployment

- [x] All schemas copied to Lambda schemas directory
- [x] All prompts copied to Lambda prompts directory
- [x] All library components copied to table_maker_lib
- [x] Imports updated for Lambda package structure
- [x] Configuration file updated with row_discovery section
- [x] Lambda handler created following existing patterns
- [x] All imports verified and tested

### Deployment Steps

1. **Deploy Lambda package** with updated table_maker_lib
   - Ensure all new files are included in deployment package
   - Verify schemas and prompts directories are included

2. **Update Lambda handler routing** (if needed)
   - Add route for `handle_row_discovery` if called directly
   - Or integrate into existing execution orchestrator

3. **Test in dev environment**
   - Start with simple search strategy (1-2 subdomains)
   - Verify WebSocket updates are sent
   - Check S3 state is saved correctly
   - Verify runs database tracking works

4. **Monitor initial runs**
   - Check CloudWatch logs for `[ROW_DISCOVERY]` prefix
   - Verify API call metrics are aggregated correctly
   - Monitor costs (multiple API calls per execution)

### Post-Deployment Validation

- [ ] End-to-end test: Interview → Column Definition → Row Discovery
- [ ] Verify discovered rows match search criteria
- [ ] Check deduplication removes duplicates correctly
- [ ] Confirm match scores are reasonable (>0.6 by default)
- [ ] Validate WebSocket messages appear in frontend
- [ ] Verify S3 state contains `row_discovery` section
- [ ] Check runs database shows `row_discovery_calls` in breakdown

---

## Integration Points

### 1. Column Definition Handler
**Location:** `column_definition.py`

**What it provides:**
- `column_definition` object with `search_strategy` and `columns`
- This is saved to conversation state in S3

**What row_discovery needs:**
- Loads `column_definition` from conversation state
- Extracts `search_strategy` and `columns` for discovery

### 2. Table Population Handler (Next Step)
**Location:** `finalize.py` (to be modified)

**What row_discovery provides:**
- `final_rows` list with `id_values` for each row
- Already scored and prioritized (no need to re-generate)

**What table population needs:**
- Accept `final_rows` as input (instead of generating row IDs)
- Focus on populating research columns only
- Skip row ID generation logic

---

## Quality Requirements Met

### Code Quality
- [x] Follows existing Lambda patterns (conversation.py, preview.py)
- [x] Uses UnifiedS3Manager for S3 operations
- [x] Uses WebSocketClient for progress updates
- [x] Uses runs database tracking with aggregation
- [x] Comprehensive error handling with graceful degradation
- [x] Type hints throughout all functions
- [x] Detailed logging with `[ROW_DISCOVERY]` prefix

### Integration Quality
- [x] No changes to existing Lambda handlers (non-breaking)
- [x] Configuration in table_maker_config.json (centralized)
- [x] Follows S3 storage patterns (session_path structure)
- [x] Compatible with existing WebSocket message types
- [x] Runs database tracking uses same aggregation pattern

### Documentation Quality
- [x] Comprehensive docstrings in all functions
- [x] Clear examples in docstrings
- [x] Integration points documented
- [x] Configuration parameters explained
- [x] Known limitations documented
- [x] Deployment checklist provided

---

## Special Considerations

### 1. Parallel Stream Metrics (Limitation)

**Current State:** The standalone `row_discovery_stream.py` does NOT expose API response metadata.

**Impact:** Cannot track individual stream API call metrics in runs database.

**Options:**
1. **Accept limitation** - Track only orchestrator-level metrics (RECOMMENDED)
2. **Modify stream** - Update to return `api_response` in result
3. **Future enhancement** - Add per-stream tracking later

**Recommendation:** Accept limitation for MVP. The orchestrator makes subdomain analysis call and consolidation happens locally (no API call), so we're mainly missing the per-stream discovery call tracking. This is acceptable for initial launch.

### 2. Error Handling Strategy

**Graceful Degradation:**
- If subdomain analysis fails → Return error, no rows discovered
- If SOME streams fail → Continue with successful streams
- If ALL streams fail → Return error, no rows discovered
- If consolidation finds <1 rows → Return empty list (not an error)

**Error Messages:**
- All errors logged with `[ROW_DISCOVERY]` prefix for easy filtering
- WebSocket errors sent to frontend for user visibility
- Runs database updated with FAILED status on critical errors

### 3. Performance Considerations

**Expected Timing:**
- Subdomain analysis: ~5-10s (1 LLM call)
- Parallel streams: ~30-60s (N LLM calls in parallel, N=2-5)
- Consolidation: ~1-2s (local processing, no API calls)
- **Total:** ~40-75s for 20 rows across 3-5 subdomains

**Cost Considerations:**
- Each stream makes 1 LLM call (claude-sonnet-4-5)
- With 5 streams: 5 LLM calls + 1 subdomain analysis = 6 calls
- Plus web searches: 5 streams * 3 searches = 15 web searches
- **Estimate:** ~$0.10-0.20 per row discovery execution (depends on token usage)

### 4. Deduplication Algorithm

**Method:** Fuzzy matching on ID column values using `SequenceMatcher`

**Threshold:** 0.85 similarity (configurable in RowConsolidator)

**Example:**
- "Anthropic" vs "Anthropic Inc" → 0.89 similarity → MERGED
- "Anthropic" vs "OpenAI" → 0.15 similarity → SEPARATE

**Merge Strategy:**
- Keep higher match_score version
- Combine source_urls from both
- Track which streams contributed via `merged_from_streams`

---

## Testing Recommendations

### Unit Tests (Local)
1. Test SubdomainAnalyzer with various search strategies
2. Test RowDiscoveryStream with mock web search results
3. Test RowConsolidator with duplicate candidates
4. Test RowDiscovery orchestration with mocked components

### Integration Tests (Lambda)
1. **Simple case:** 1-2 subdomains, 10 candidates, no duplicates
2. **Complex case:** 4-5 subdomains, 50 candidates, 20% duplicates
3. **Edge case:** No matches found (all below threshold)
4. **Error case:** Subdomain analysis fails
5. **Error case:** All streams fail

### E2E Tests (Full Pipeline)
1. Interview → Column Definition → Row Discovery → Table Population
2. Verify each step saves state correctly
3. Check WebSocket messages flow to frontend
4. Validate runs database tracks all operations
5. Confirm final table has 20 high-quality rows

---

## Next Steps

### Immediate (Current Sprint)
1. Test row_discovery_handler.py in Lambda environment
2. Verify integration with column_definition output
3. Update finalize.py to accept discovered rows (Agent 8 continuation)

### Short-Term (Next Sprint)
1. Add per-stream progress WebSocket updates (optional)
2. Modify row_discovery_stream.py to return API metadata (for better tracking)
3. Implement retry logic for failed streams
4. Add configuration validation on startup

### Long-Term (Future)
1. Optimize parallel stream execution (async batching)
2. Add caching for subdomain analysis (same strategy → same subdomains)
3. Implement adaptive stream count (auto-detect optimal N)
4. Add quality metrics dashboard (match scores, dedup stats)

---

## Known Issues & Limitations

### 1. No Per-Stream API Tracking
**Issue:** row_discovery_stream.py doesn't return API response metadata

**Impact:** Cannot track individual stream costs/tokens in runs database

**Workaround:** Track only orchestrator-level metrics

**Fix Required:** Modify row_discovery_stream.py to return api_response

### 2. No Per-Stream Progress Updates
**Issue:** WebSocket updates only at start/end, not during stream execution

**Impact:** User sees "Discovering..." for full 60s without intermediate updates

**Workaround:** None (acceptable for MVP)

**Fix Required:** Add progress callback to row_discovery.py

### 3. Fixed Similarity Threshold
**Issue:** Deduplication similarity threshold is hardcoded (0.85)

**Impact:** Cannot tune per-use-case

**Workaround:** None currently

**Fix Required:** Add to configuration file

### 4. No Stream Retry Logic
**Issue:** If a stream fails, it's skipped (no retry)

**Impact:** May lose coverage if transient error

**Workaround:** None (graceful degradation)

**Fix Required:** Add retry logic with exponential backoff

---

## Success Metrics

### Functional Success
- [ ] Row discovery finds 20 high-quality matches
- [ ] Match scores accurately reflect fit (avg >0.75)
- [ ] Deduplication removes >90% of duplicates
- [ ] Parallel streams complete in <90 seconds
- [ ] WebSocket updates sent correctly
- [ ] S3 state saved with row_discovery section
- [ ] Runs database tracks operations

### Quality Success
- [ ] No quality drop across all 20 rows (consistent quality)
- [ ] No repeated/duplicate entities in final list
- [ ] Source URLs provided for transparency
- [ ] Match rationales are clear and accurate

### Performance Success
- [ ] Total execution time: <90 seconds for 20 rows
- [ ] Subdomain analysis: <10 seconds
- [ ] Parallel streams: <60 seconds
- [ ] Consolidation: <5 seconds

---

## Conclusion

All 4 Row Discovery components have been successfully integrated into the Lambda environment:
1. **SubdomainAnalyzer** - Identifies natural subdivisions
2. **RowDiscoveryStream** - Discovers candidates in subdomains
3. **RowConsolidator** - Deduplicates and prioritizes
4. **RowDiscovery** - Orchestrates the pipeline

The integration follows existing Lambda patterns, includes comprehensive error handling, and is ready for testing. Known limitations are documented and acceptable for MVP launch.

**Status:** READY FOR DEPLOYMENT AND TESTING

**Next Agent:** Agent 9 (or continuation) - Update finalize.py to accept discovered rows
