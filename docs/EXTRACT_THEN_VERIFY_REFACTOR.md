# Extract-Then-Verify Refactor Plan

**Goal:** Eliminate double-reading of memory sources by extracting quotes BEFORE assessing confidence.

**Current Problem:** Memory verification reads 2000 chars, then extraction reads the SAME content again.

---

## Architecture Change

### Before (Verify-Then-Extract)
```
Memory Recall:
  1. Keyword filter (free)
  2. Gemini selection (titles) → $0.0002
  3. Verification (2000 chars) → $0.0003, confidence=0.90
  ↓
Search Decision: Skip (confidence=0.90)
  ↓
Triage: Skip (memory-only)
  ↓
Extraction: Read 2000 chars AGAIN → $0.0011, 0 snippets!
  ↓
Synthesis: "I have 0 snippets but conf was 0.90..."
```

**Total Gemini calls on memory: 3** (selection + verification + extraction)
**Problem:** False positives (high confidence, 0 snippets)

### After (Extract-Then-Verify)
```
Memory Recall:
  1. Keyword filter (free)
  2. Gemini selection (titles) → $0.0002
  ↓
Extract from Memory:
  3. Read sources, extract quotes → $0.0011, 0 snippets!
  ↓
Snippet-Based Confidence:
  4. Heuristic: 0 snippets → conf=0.0 (fast)
  OR
  4. Gemini (borderline): Assess actual quotes → $0.0002
  ↓
Search Decision: Search (confidence=0.0)
  ↓
Search Execution → 10 results
  ↓
Triage (search results only, memory already done)
  ↓
Extract from Search Sources → snippets
  ↓
Merge: memory_snippets + search_snippets
  ↓
Synthesis: Has actual snippets
```

**Total Gemini calls on memory: 2-3** (selection + extraction + optional assessment)
**Benefit:** Impossible to have false positives (0 snippets = 0 confidence)

---

## Implementation Plan

### Phase 1: Add skip_verification to memory.recall()
- [x] Add parameter `skip_verification: bool = False`
- [x] When True: Skip verification step, return confidence=None
- [x] Update return dict to handle None confidence

### Phase 2: Create snippet_confidence.py
- [x] Heuristic assessment (count + p-scores)
- [x] Optional Gemini refinement (borderline cases)
- [x] Returns confidence_vector per search term

### Phase 3: Refactor the_clone.py memory recall section
```python
# Call recall without verification
recall_result = await memory.recall(..., skip_verification=True)
memory_sources = recall_result['memories']  # No confidence yet

# Extract from memory sources (if any)
memory_snippets = []
if memory_sources:
    # Mark sources as memory-origin
    for src in memory_sources:
        src['_from_memory'] = True
        src['_already_extracted'] = True  # Flag to skip in main loop

    # Extract
    memory_snippets = await extract_from_sources(memory_sources, prefix="SM")

    # Assess confidence based on ACTUAL snippets
    confidence_result = await assess_snippet_confidence(
        snippets=memory_snippets,
        search_terms=search_terms,
        breadth=breadth,
        depth=depth
    )

    confidence = confidence_result['overall_confidence']
    recommended_searches = confidence_result['recommended_searches']
```

### Phase 4: Update search decision logic
- Use snippet-based confidence instead of preview-based
- Terms with <0.85 confidence go to search

### Phase 5: Update triage
- Skip sources with `_already_extracted=True`
- Or triage search sources only, memory already ranked

### Phase 6: Update extraction loop
- Skip sources with `_already_extracted=True`
- Or separate memory/search extraction entirely

### Phase 7: Merge snippets
```python
all_snippets = memory_snippets + search_snippets
# Dedupe by URL at snippet level (not source level)
```

### Phase 8: Update synthesis
- Pass merged snippets
- Update source mismatch warning to account for memory snippets

---

## Risk Mitigation

1. **Add feature flag:** `use_extract_then_verify=True` (default off initially)
2. **Preserve old code path:** Keep verify-then-extract working
3. **Extensive logging:** Log every step of new flow
4. **Backwards compatibility:** Ensure old tests still pass

---

## Testing Checklist

- [ ] Memory with relevant sources → snippets extracted → high confidence → skip search
- [ ] Memory with irrelevant sources → 0 snippets → low confidence → trigger search
- [ ] Memory + search → snippets merged correctly
- [ ] No memory → regular flow works
- [ ] Memory-only path → no double extraction

---

## Files to Modify

1. `search_memory.py` - Add skip_verification parameter ✓
2. `snippet_confidence.py` - Confidence assessment utility ✓
3. `the_clone.py` - Main refactor (extract memory early, assess, merge)
4. `unified_synthesizer.py` - Handle memory snippets in source mismatch warning

---

## Rollback Plan

If issues arise:
```python
# In the_clone.py
USE_EXTRACT_THEN_VERIFY = False  # Set to False to revert

if USE_EXTRACT_THEN_VERIFY:
    # New flow
else:
    # Old flow (current code)
```
