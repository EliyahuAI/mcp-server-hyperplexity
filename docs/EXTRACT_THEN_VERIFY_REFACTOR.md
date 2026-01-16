# Extract-Then-Verify Refactor Plan

**Status:** COMPLETED

**Goal:** Eliminate double-reading of memory sources by extracting quotes BEFORE assessing confidence.

**Solution:** Simple - triage already has `existing_snippets` parameter. Pass `memory_snippets` to it.

---

## Architecture

### Before (Verify-Then-Extract)
```
Memory Recall:
  1. Keyword filter (free)
  2. Gemini selection (titles) → $0.0002
  3. Verification (2000 chars) → $0.0003, confidence=0.90
  ↓
Search Decision: Skip (confidence=0.90)
  ↓
Triage: Memory + search sources mixed together
  ↓
Extraction: Read memory sources AGAIN → $0.0011, 0 snippets!
  ↓
Synthesis: "I have 0 snippets but conf was 0.90..."
```

**Problem:** False positives (high confidence, 0 snippets) + double extraction

### After (Extract-Then-Verify) ✅
```
Memory Recall:
  1. Keyword filter (free)
  2. Gemini selection (titles) → $0.0002
  ↓
Extract from Memory:
  3. Extract quotes → memory_snippets
  ↓
Snippet-Based Confidence:
  4. Heuristic based on actual snippets → confidence
  ↓
Search Decision: Based on snippet confidence
  ↓
Search Execution (if needed)
  ↓
Triage SEARCH ONLY:
  - existing_snippets=memory_snippets (knows what we have)
  - Deprioritizes redundant search results
  ↓
Extract from Search Sources
  ↓
all_snippets = memory_snippets + search_snippets
  ↓
Synthesis
```

**Benefit:** No double extraction, accurate confidence, simple triage integration

---

## Implementation Summary

### Key Changes (all in the_clone.py)

1. **Memory extraction before confidence** (lines 652-697)
   ```python
   # Extract from memory sources first
   memory_snippets = await extract_from_sources_batch(memory_sources, prefix="SM")
   ```

2. **Snippet-based confidence** (lines 699-732)
   ```python
   confidence = await assess_snippet_confidence(memory_snippets, search_terms, ...)
   ```

3. **URL deduplication** (lines 952-963)
   ```python
   # Remove search results that memory already covers
   memory_urls = {s.get('_source_url') for s in memory_snippets}
   result['results'] = [r for r in results if r.get('url') not in memory_urls]
   ```

4. **Pass memory to triage** (line 986)
   ```python
   existing_snippets=memory_snippets  # Triage sees what memory covers
   ```

5. **Start with memory snippets** (line 1039)
   ```python
   all_snippets = list(memory_snippets)  # Search snippets added by extraction loop
   ```

### Files Modified
- `the_clone.py` - Main flow refactor
- `snippet_confidence.py` - Confidence assessment utility (already existed)
- `search_memory.py` - Added `skip_verification` parameter (already existed)

---

## Testing Checklist

- [ ] Memory with relevant sources → snippets extracted → high confidence → skip search
- [ ] Memory with irrelevant sources → 0 snippets → low confidence → trigger search
- [ ] Memory + search → snippets merged correctly (no duplicates)
- [ ] No memory → regular flow works
- [ ] Memory-only path → no double extraction
