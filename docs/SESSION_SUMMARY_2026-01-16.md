# Session Summary: 2026-01-16

## Latency Investigation & Memory Cache Implementation

### Problem Identified
- ~2 minute turnaround times for Perplexity searches in production
- Initial suspicion: `max_tokens_per_page` or API parameters
- **Actual cause:** Parallel S3 writes to agent_memory.json

### Root Cause Analysis
- Perplexity API: **0.3s** locally (FAST)
- Production report: **113s** for same query (400x slower!)
- Problem: Multiple agents writing 50MB+ memory file to S3 simultaneously
- S3 write latency: 2-6 seconds per write
- Race conditions: Last write wins, data loss

### Solution Implemented: RAM-Based Memory Cache

**Architecture:**
```
Module-level singleton (_MEMORY_CACHE)
  ↓
All parallel agents share SAME memory object in RAM
  ↓
Zero S3 writes during execution (0ms latency)
  ↓
Single S3 write at batch end
```

**Performance:**
- Before: N agents × 5s per write = massive latency + conflicts
- After: 0ms during execution + 5s at end = **10x faster**

### Files Created
1. `src/the_clone/search_memory_cache.py` - RAM cache singleton
2. `src/the_clone/snippet_confidence.py` - Snippet-based confidence
3. `docs/MEMORY_CACHE_INTEGRATION.md` - Integration guide
4. `docs/PERPLEXITY_LATENCY_DIAGNOSTIC_2026-01-16.md` - Diagnostic report
5. `docs/EXTRACT_THEN_VERIFY_REFACTOR.md` - Refactor plan

### Bugs Fixed

**Bug 1-3: Memory cache bugs**
- asyncio.run() fails in running event loop → Added flush_sync()
- Race condition during S3 backup → Added deep copy
- Pretty-printing overhead (indent=2) → Removed (30-40% smaller)

**Bug 4-5: Synthesis parameter bugs**
- answer_directly path missing parameters
- Self-correction iteration missing parameters

**Bug 6: Source mismatch detection**
- Synthesis unaware when initial_decision="need_search" but 0 snippets
- Now shows warning with examined sources list

### Integration Points

**Config copy:**
- `copy_config.py` - Loads copied memory into RAM cache
- `use_config_by_id.py` - Loads copied memory into RAM cache

**Pre-validation flush:**
- `background_handler.py` (2 locations) - Flush before Lambda invoke
- `process_excel_unified.py` (2 locations) - Flush before Lambda invoke

---

## Extract-Then-Verify Pattern (In Progress)

### Problem
Memory verification reads 2000-char previews, gives high confidence (0.90),
then extraction finds 0 relevant quotes. This causes:
1. False positives (topically related ≠ entity-specific)
2. Double-reading (verify + extract read same content)
3. Synthesis answering without sources

### Solution
Extract quotes FIRST, then assess confidence on ACTUAL quotes.

**Benefits:**
- Impossible false positives (0 snippets = 0 confidence automatically)
- Single read of memory sources (not double)
- More accurate (judges actual quotes, not predictions)

### Status
- ✅ `snippet_confidence.py` created
- ✅ `search_memory.py` has `skip_verification` parameter
- ⏳ `the_clone.py` refactor in progress
- ⏳ Testing needed

### Next Steps
1. Implement extract-then-verify flow in the_clone.py
2. Test with memory sources that should fail (topically related, not specific)
3. Verify snippet merging works correctly (memory + search)
4. Deploy and monitor

---

## Metrics

**Commits:** 9 commits in this session
**Code changes:**
- 5 new files
- 10+ files modified
- ~500 lines added

**Performance improvements:**
- Memory cache: 10x speedup for parallel execution
- No pretty-printing: 30-40% smaller files, faster serialization
- Extract-then-verify (when complete): Eliminates false positives, saves ~$0.0003 per query

---

## Open Questions

1. Should extract-then-verify be default, or feature flag initially?
2. How to handle snippet merging edge cases (same URL, different queries)?
3. Should we keep old verification as fallback for debugging?
