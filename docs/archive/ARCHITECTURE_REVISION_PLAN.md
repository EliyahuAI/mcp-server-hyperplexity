# Architecture Revision Plan - Synthesized

**Date:** October 20, 2025
**Branch:** `feature/independent-row-discovery`
**Status:** Revising before testing

---

## Executive Summary

Before running any tests, we need to fix critical architectural issues identified:

### Issues from IMPLEMENTATION_STATUS_AND_NEXT_STEPS.md
1. Frontend not updated for new flow
2. Models hardcoded (sonar-pro not configurable)
3. Subdomain analysis requires separate AI call
4. Documentation scattered
5. No row overshooting
6. Subdomain prompts don't prioritize multi-row queries
7. No local testing done yet

### New Requirements from Architectural Review
1. **Scoring integrated into search** (not separate)
2. **Subdomains defined in column definition** (not separate call)
3. **Scoring rubric** with three dimensions
4. **WebSocket queue** for parallel message management
5. **Sequential testing first** before parallel

---

## Revised Architecture

### AI Call Reduction
**BEFORE (Initial Implementation):**
- Column Definition (claude) → 1 call
- Subdomain Analysis (claude) → 1 call
- Row Discovery per subdomain:
  - Web Search (sonar-pro) → 1 call
  - Candidate Scoring (claude) → 1 call
  - × 3 subdomains = 6 calls
- **TOTAL: 8 calls**

**AFTER (Revised):**
- Column Definition with Subdomains (claude) → 1 call
- Row Discovery per subdomain (sonar-pro with integrated scoring) → 1 call
  - × 3 subdomains = 3 calls
- **TOTAL: 4 calls**

**SAVINGS:** 4 fewer calls, ~$0.05 per table, ~20 seconds faster

---

## Implementation Tasks

### Phase 1: Core Architecture Revisions (Sequential Testing)

#### Task 1: Update Column Definition Schema
**File:** `table_maker/schemas/column_definition_response.json`
**Changes:**
- Add `subdomains` array to `search_strategy` object
- Each subdomain has: name, focus, search_queries, target_rows
- Validate 2-5 subdomains required

#### Task 2: Update Column Definition Prompt
**File:** `table_maker/prompts/column_definition.md`
**Changes:**
- Add subdomain specification section
- Add multi-row query prioritization guidelines
- Add scoring rubric reference
- Add target_rows distribution logic

#### Task 3: Update Row Discovery Stream (Integrated Scoring)
**File:** `table_maker/src/row_discovery_stream.py`
**Changes:**
- Remove separate scoring call
- Single sonar-pro call with scoring rubric in prompt
- Make web_search_model configurable (default: sonar-pro)
- Return score_breakdown (relevancy, reliability, recency)

#### Task 4: Update Row Discovery Orchestrator
**File:** `table_maker/src/row_discovery.py`
**Changes:**
- Remove SubdomainAnalyzer import and call
- Read subdomains from search_strategy (from column definition)
- Add discovery_multiplier support (find 30, keep 20)
- Support sequential mode (max_parallel_streams=1)

#### Task 5: Update Configuration
**Files:**
- `table_maker/table_maker_config.json`
- `src/lambdas/interface/actions/table_maker/table_maker_config.json`

**Changes:**
```json
{
  "column_definition": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "use_web_search": true,
    "web_searches": 3,
    "include_subdomains": true,  // NEW
    "subdomain_count_min": 2,    // NEW
    "subdomain_count_max": 5     // NEW
  },
  "row_discovery": {
    "web_search_model": "sonar-pro",        // NEW: configurable
    "scoring_model": "sonar-pro",           // NEW: same model
    "integrated_scoring": true,             // NEW: score during search
    "target_row_count": 20,
    "discovery_multiplier": 1.5,            // NEW: find 30, keep 20
    "min_match_score": 0.6,
    "max_parallel_streams": 1,              // START: sequential for testing
    "web_searches_per_stream": 3
  }
}
```

#### Task 6: Remove Subdomain Analyzer
**Files to update:**
- `table_maker/src/row_discovery.py` - Remove import, remove call
- Mark `subdomain_analyzer.py` as DEPRECATED (may be useful later)

#### Task 7: Update Tests
**Files:**
- `table_maker/tests/test_row_discovery_stream.py` - Update for integrated scoring
- `table_maker/tests/test_row_discovery.py` - Remove subdomain analyzer tests
- `table_maker/tests/test_column_definition_handler.py` - Add subdomain output tests

---

### Phase 2: WebSocket Queue (Parallel Support)

#### Task 8: Create WebSocket Queue
**File:** `src/lambdas/interface/actions/table_maker/websocket_queue.py`
**Features:**
- Priority-based message sending (critical, high, normal)
- Message aggregation for progress updates
- Thread-safe asyncio.Queue
- Configurable buffer times

#### Task 9: Update Execution Orchestrator
**File:** `src/lambdas/interface/actions/table_maker/execution.py`
**Changes:**
- Initialize WebSocket queue
- Pass queue to all parallel operations
- Ensure sequential message delivery

#### Task 10: Update Row Discovery Handler
**File:** `src/lambdas/interface/actions/table_maker/row_discovery_handler.py`
**Changes:**
- Accept WebSocket queue parameter
- Send messages via queue (not directly)
- Use priority levels appropriately

---

### Phase 3: Local Testing Setup

#### Task 11: Create Local E2E Test Script
**File:** `table_maker/test_local_e2e_sequential.py`
**Features:**
- Uses environment variables for API keys
- Tests: Conversation → Column Definition → Row Discovery → Results
- Sequential mode only (max_parallel_streams=1)
- Detailed output showing columns, rows, scores
- Performance timing

#### Task 12: Create AI Client Environment Setup
**File:** `table_maker/.env.example`
```bash
ANTHROPIC_API_KEY=sk-ant-...
PERPLEXITY_API_KEY=pplx-...  # If needed
```

#### Task 13: Verify AI Client Uses Environment Variables
**File:** Check `ai_api_client.py` or equivalent
- Ensure it reads from environment variables
- Works with local testing

---

### Phase 4: Documentation Consolidation

#### Task 14: Create Single Concise Guide
**File:** `docs/TABLE_MAKER_GUIDE.md` (NEW)
**Contents:**
- Quick start (5 minutes to understanding)
- Architecture overview (two-phase workflow)
- Configuration reference
- Common tasks
- Troubleshooting

#### Task 15: Organize Detailed Docs
**Create:** `docs/table_maker/` folder structure
- Move detailed component docs
- Move API references
- Move implementation details

#### Task 16: Archive Old Docs
**Create:** `docs/archive/` folder
- Move preview/refinement docs
- Move old architecture docs
- Keep for reference only

---

## Implementation Order

### Batch 1: Architecture Revisions (45-60 min)
Tasks 1-7 can be done together:
- Schema updates
- Prompt updates
- Code updates (integrated scoring)
- Config updates
- Remove subdomain analyzer dependency
- Update tests

### Batch 2: Local Testing (15-20 min)
Tasks 11-13:
- Create test script
- Set up environment
- Verify AI client setup

### Batch 3: Test & Validate (Run by User - 10-15 min)
- Set API keys in environment
- Run sequential test
- Review results
- Validate scoring quality

### Batch 4: WebSocket Queue (30-45 min) - AFTER Testing Validates Architecture
Tasks 8-10:
- Create queue
- Update execution orchestrator
- Update row discovery handler

### Batch 5: Documentation (30-45 min) - AFTER Everything Works
Tasks 14-16:
- Create concise guide
- Reorganize detailed docs
- Archive old versions

---

## Testing Strategy

### Test 1: Sequential Mode (First)
```bash
export ANTHROPIC_API_KEY="your-key"
cd table_maker
python3 test_local_e2e_sequential.py
```

**Config:**
```json
{"row_discovery": {"max_parallel_streams": 1}}
```

**Validates:**
- Integrated scoring works
- Subdomains from column definition work
- Row overshooting works (30 → 20)
- Match scores are reasonable
- Deduplication works
- NO concurrency issues to debug

### Test 2: Parallel Mode (After Sequential Works)
```bash
python3 test_local_e2e_parallel.py
```

**Config:**
```json
{"row_discovery": {"max_parallel_streams": 3}}
```

**Validates:**
- WebSocket queue handles concurrent messages
- Parallel streams complete correctly
- Performance improvement vs sequential

---

## Success Criteria

### Before Moving to AWS:
- [ ] Sequential test runs successfully
- [ ] Match scores are reasonable (avg >0.75)
- [ ] Deduplication works (fuzzy matching verified)
- [ ] Row overshooting produces better final set
- [ ] Scoring rubric produces consistent results
- [ ] Performance: <120s for 20 rows (sequential)

### After WebSocket Queue Added:
- [ ] Parallel test runs successfully
- [ ] Messages delivered in order
- [ ] No race conditions
- [ ] Performance: <90s for 20 rows (parallel)

---

## Current Status Dashboard

| Component | Status | Next Action |
|-----------|--------|-------------|
| Column Definition | Built but needs subdomain addition | Task 1-2 |
| Row Discovery Stream | Built but needs integrated scoring | Task 3 |
| Row Discovery Orchestrator | Built but uses subdomain analyzer | Task 4 |
| Row Consolidator | ✅ Complete | None |
| Configuration | Needs updates | Task 5 |
| Subdomain Analyzer | DEPRECATE | Task 6 |
| Tests | Need updating | Task 7 |
| WebSocket Queue | NOT BUILT | Task 8-10 |
| Local Test Script | NOT BUILT | Task 11-13 |
| Documentation | SCATTERED | Task 14-16 |
| Frontend | NOT UPDATED | Separate task |

---

## Revised Timeline

**Today (Architecture + Sequential Testing):**
- [ ] Implement Tasks 1-7 (architecture revisions) - 45-60 min
- [ ] Implement Tasks 11-13 (local test setup) - 15-20 min
- [ ] Run sequential test with your keys - 10-15 min
- [ ] Validate and iterate if needed - 15-30 min
- **TOTAL: ~2-2.5 hours**

**Tomorrow (Parallelization + WebSocket):**
- [ ] Implement Tasks 8-10 (WebSocket queue) - 30-45 min
- [ ] Run parallel test - 10-15 min
- [ ] Validate performance - 15-30 min
- **TOTAL: ~1-1.5 hours**

**Later (Documentation + Frontend):**
- [ ] Implement Tasks 14-16 (doc consolidation) - 30-45 min
- [ ] Update frontend for new flow - 60-90 min
- [ ] Deploy to AWS - 30 min
- [ ] Integration testing in AWS - 30-60 min
- **TOTAL: ~2.5-4 hours**

---

**GRAND TOTAL: ~6-8 hours to production-ready system**

---

**Ready to proceed with Batch 1 (Architecture Revisions)?**
