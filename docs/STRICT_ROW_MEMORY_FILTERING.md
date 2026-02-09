# Strict Row-Level Memory Filtering Implementation
## Two-Tier Memory System: General + Row-Specific

**Date:** 2026-02-09
**Implementation:** Strict binary filtering in `search_memory.py`
**Motivation:** Eliminate multi-product company contamination (Bayer, Aktis cases)

---

## Overview

### Problem Identified

From Take 3 and Take 4 contamination analysis:
- **Bayer / 225Ac-PSMA-Trillium:** 56% contamination from different Bayer product (225Ac-Pelgifatamab)
- **Aktis Oncology / AKY-2519:** 100% contamination from different Aktis product (AKY-1189)

**Root Cause:** Previous implementation used **scoring** to prefer same-row memories but still allowed cross-row memories with penalty (-5 score). This meant:
- Memory about Bayer Product A could still be retrieved for Bayer Product B
- Just ranked lower, but still included in results
- Multi-product companies suffered from cross-product contamination

### Solution: Strict Binary Filtering

Implement **two-tier memory system**:
1. **Tier 1: Row-Specific Memories** - Only memories with exact matching row_key
2. **Tier 2: General Memories** - Memories with no row_context (general knowledge)

**Block everything else** - no partial matches, no cross-row memories.

---

## Implementation Details

### Code Changes

**File:** `src/the_clone/search_memory.py`

**Location:** `_filter_queries_by_keywords()` function (lines ~975-990)

### Before: Scoring Approach

```python
# OLD: Row context used for SCORING only
row_context_score = self._calculate_row_context_score(query_data, row_identifiers)

# Scoring formula included row_context_score
relevance_score = (
    query_overlap × 10.0 +
    req_matches × 3.0 +
    pos_matches × 1.0 +
    recency_score × 0.5 +
    row_context_score -           # +10, +5, 0, or -5
    neg_matches × 5.0
)

# PROBLEM: Memories with -5 penalty could still rank high enough to be selected
# Example: Strong keyword match + recency could overcome -5 penalty
```

### After: Strict Filtering

```python
# NEW: Row context used for BINARY FILTERING (before scoring)
stored_context = query_data.get('row_context')
if stored_context and row_identifiers:
    # This memory HAS row context AND we have current row context
    # Only allow if row keys match exactly
    stored_row_key = stored_context.get('row_key')
    current_row_key = row_identifiers.get('row_key')

    if stored_row_key and current_row_key:
        if stored_row_key != current_row_key:
            # Different row - SKIP this memory entirely
            logger.debug(
                f"[MEMORY] Skipping query '{query_data['search_term']}' - "
                f"different row context (stored: {stored_context.get('row_id_display')}, "
                f"current: {row_identifiers.get('row_id_display')})"
            )
            continue  # HARD FILTER - query not even considered for scoring
# If no stored_context: General memory - always allowed
# If no row_identifiers: Backward compatibility - allow everything

# Then scoring happens only on filtered queries (same-row + general)
```

---

## Two-Tier Memory Logic

### Memory Retrieval Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Memory Store (All Queries)                                  │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────┐│
│  │ Row-Specific     │  │ Row-Specific     │  │ General    ││
│  │ (Bayer Product A)│  │ (Bayer Product B)│  │ (No Context││
│  │ row_key: abc123  │  │ row_key: def456  │  │ row_key: - ││
│  └──────────────────┘  └──────────────────┘  └────────────┘│
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────────┐
                    │ Strict Filter for │
                    │ Bayer Product A   │
                    │ (row_key: abc123) │
                    └───────────────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
        ┌──────────────┐        ┌──────────────┐
        │ ALLOW:       │        │ ALLOW:       │
        │ Product A    │        │ General      │
        │ (exact match)│        │ (no context) │
        └──────────────┘        └──────────────┘
                │                       │
                └───────────┬───────────┘
                            ▼
                    ┌──────────────┐
                    │ BLOCK:       │
                    │ Product B    │
                    │ (different   │
                    │  row_key)    │
                    └──────────────┘
```

### Decision Matrix

| Stored Memory Has Context? | Current Query Has Context? | row_key Match? | Decision |
|----------------------------|---------------------------|----------------|----------|
| **No** | Any | N/A | ✅ **ALLOW** (General memory) |
| **Yes** | **No** | N/A | ✅ **ALLOW** (Backward compatibility) |
| **Yes** | **Yes** | **Exact match** | ✅ **ALLOW** (Same row) |
| **Yes** | **Yes** | **Different** | ❌ **BLOCK** (Cross-row contamination) |

---

## Expected Impact

### Target Contamination Cases

Based on Take 3/Take 4 analysis:

#### Case 1: Bayer Multi-Product (Currently 56% contaminated)

**Before:**
```
Row: Bayer / 225Ac-PSMA-Trillium
Memory Retrieved:
  ✓ Bayer / 225Ac-PSMA-Trillium (row_key match) - score +10
  ✓ General pharma knowledge (no context) - score 0
  ⚠ Bayer / 225Ac-Pelgifatamab (different row_key) - score -5
     ^ Still retrieved despite penalty!

Result: 5/9 columns contaminated (56%)
```

**After:**
```
Row: Bayer / 225Ac-PSMA-Trillium
Memory Retrieved:
  ✓ Bayer / 225Ac-PSMA-Trillium (row_key match) - score +10
  ✓ General pharma knowledge (no context) - score 0
  ✗ Bayer / 225Ac-Pelgifatamab (FILTERED OUT - different row_key)
     ^ Never reaches scoring!

Expected: 0-2/9 columns contaminated (<22%)
```

#### Case 2: Aktis Oncology Multi-Product (Currently 100% contaminated)

**Before:**
```
Row: Aktis / AKY-2519
Memory Retrieved:
  ✓ Aktis / AKY-2519 (row_key match) - score +10
  ✓ General oncology knowledge (no context) - score 0
  ⚠ Aktis / AKY-1189 (different row_key) - score -5
  ⚠ Bristol Myers Squibb partnership info - score -5
     ^ Both still retrieved!

Result: 9/9 columns contaminated (100%)
```

**After:**
```
Row: Aktis / AKY-2519
Memory Retrieved:
  ✓ Aktis / AKY-2519 (row_key match) - score +10
  ✓ General oncology knowledge (no context) - score 0
  ✗ Aktis / AKY-1189 (FILTERED OUT - different row_key)
  ✗ Bristol Myers Squibb partnership (FILTERED OUT - different row_key)
     ^ Never reach scoring!

Expected: 2-4/9 columns contaminated (<50%)
```

**Note:** Partnership mentions (Bristol Myers Squibb) may still appear in general memories or same-row memories if legitimately relevant to AKY-2519.

### Overall Impact Prediction

| Metric | Take 4 (Before) | Take 5 (After) | Expected Improvement |
|--------|----------------|----------------|---------------------|
| Overall Contamination | 31.1% | **15-20%** | **-35% to -50%** |
| Multi-Product Rows | 56-100% | **<30%** | **-60% to -70%** |
| Clean Rows | 2/10 (20%) | **5-6/10 (50-60%)** | **+30-40 pp** |

**Conservative Estimate:** 31.1% → 20% (35% reduction)
**Optimistic Estimate:** 31.1% → 15% (52% reduction)

---

## Technical Considerations

### 1. Performance Impact

**Before:** All memories scored, then sorted
**After:** Many memories filtered out before scoring

**Performance:** ✅ **Slight improvement**
- Fewer queries to score
- Filtering is simple string comparison (row_key)
- No AI calls involved

### 2. Memory Efficiency

**RAM:** No impact - filtering in-memory
**S3:** No impact - same storage structure

### 3. Backward Compatibility

✅ **Fully backward compatible**

```python
# Case 1: Old memory (no row_context stored)
stored_context = query_data.get('row_context')  # None
if stored_context and row_identifiers:  # False - skipped
    # Filter not applied
# Result: Old memories treated as general memories - always allowed

# Case 2: New code, old validation (no row_identifiers passed)
if stored_context and row_identifiers:  # False - row_identifiers is None
    # Filter not applied
# Result: All memories allowed (backward compatible)

# Case 3: New memory, new validation (both present)
if stored_context and row_identifiers:  # True
    # Strict filter applied
# Result: Only same-row + general memories allowed
```

### 4. Edge Cases

#### Edge Case 1: Partial row_key Match
```python
stored_row_key = "abc123def"
current_row_key = "abc123"

if stored_row_key != current_row_key:  # True - different
    continue  # BLOCKED
```
**Decision:** Require **exact match** only. No substring matching.

#### Edge Case 2: Missing row_key But Has id_values
```python
stored_context = {'id_values': ['Bayer', '225Ac-PSMA-Trillium']}  # No row_key
current_row_key = 'abc123'

if stored_row_key and current_row_key:  # False - stored_row_key is None
    # Filter not applied
```
**Decision:** If row_key missing, treat as general memory (allowed).

#### Edge Case 3: Empty row_key
```python
stored_row_key = ""
current_row_key = "abc123"

if stored_row_key and current_row_key:  # False - empty string is falsy
    # Filter not applied
```
**Decision:** Empty row_key treated as missing (general memory).

---

## Migration & Deployment

### Phase 1: Code Deploy (Immediate)

1. ✅ **Deploy updated search_memory.py**
   - Strict filtering active for new validations
   - Backward compatible with old memory

2. ✅ **Monitor logging**
   ```
   grep "[MEMORY] Skipping query" logs/lambda.log
   ```
   - Check how many memories are being filtered
   - Verify cross-row memories are blocked

### Phase 2: Memory Refresh (Recommended)

**Option A: Natural Refresh**
- Let memory naturally update over time
- New validations create new memories with proper row_context
- Old memories phase out (if not used)

**Option B: Forced Refresh**
- Clear agent_memory.json for test sessions
- Run fresh validation to rebuild memory
- Ensures all memories have proper row_context

**Recommendation:** Option B for critical testing, Option A for production

### Phase 3: Validation (Testing)

1. **Re-run theranostic dataset** (Take 5)
   - Same 68 rows as Take 3/Take 4
   - Fresh memory (to ensure all memories have row_context)
   - Use Sonnet 4.5 QC (or DeepSeek based on quality preference)

2. **Run contamination analysis**
   ```bash
   python3 analyze_contamination_take5.py
   ```

3. **Compare results**
   - Take 4: 31.1% contamination (Sonnet QC, scoring approach)
   - Take 5: Expected 15-20% (Sonnet QC, strict filtering)
   - Target: <20% contamination

### Phase 4: Production Rollout

If Take 5 shows <20% contamination:
1. ✅ **Deploy to production**
2. ✅ **Monitor contamination metrics**
3. ✅ **Iterate if needed** (e.g., context-aware partnership detection)

---

## Monitoring & Debugging

### Debug Logging

The implementation includes detailed debug logging:

```python
logger.debug(
    f"[MEMORY] Skipping query '{query_data['search_term']}' - "
    f"different row context (stored: {stored_context.get('row_id_display', 'unknown')}, "
    f"current: {row_identifiers.get('row_id_display', 'unknown')})"
)
```

**Example Output:**
```
[MEMORY] Skipping query 'Bayer radiopharmaceutical pipeline' -
  different row context (stored: Bayer | 225Ac-Pelgifatamab, current: Bayer | 225Ac-PSMA-Trillium)
```

### Metrics to Track

1. **Filter Rate:**
   - Count of `"Skipping query"` log entries
   - % of memories filtered per validation
   - Expected: 10-30% of memories filtered for multi-product companies

2. **Contamination Rate:**
   - Same metrics as previous analysis
   - Target: <20% overall, <30% for multi-product rows

3. **Memory Reuse:**
   - Are same-row memories being reused effectively?
   - Are general memories providing value?

4. **Validation Quality:**
   - Has strict filtering reduced information quality?
   - Are validations still comprehensive?

---

## Comparison with Previous Approaches

### Approach 1: No Row Context (Take 1, Take 2)
- **Contamination:** 36-37%
- **Method:** No filtering
- **Problem:** Maximum cross-row contamination

### Approach 2: Row Context Scoring (Take 3, Take 4)
- **Contamination:** 29-31%
- **Method:** Penalty for different rows (-5 score)
- **Problem:** Cross-row memories still retrieved, just ranked lower

### Approach 3: Strict Binary Filtering (Take 5 - This Implementation)
- **Contamination:** Expected 15-20%
- **Method:** Block different rows entirely
- **Benefit:** Eliminates cross-row contamination at source

---

## Future Enhancements

### 1. Context-Aware Partnership Detection

**Problem:** Bristol Myers Squibb mentioned in Aktis memories may be legitimate partnership context.

**Solution:** Relationship graph
```python
COMPANY_RELATIONSHIPS = {
    'Aktis Oncology': {
        'partners': ['Bristol Myers Squibb'],
        'subsidiaries': [],
        'acquirer': 'Eli Lilly'
    }
}

# Allow cross-row memories if relationship exists
if is_related(stored_company, current_company):
    # Allow even if different row_key
    pass
```

### 2. Product Family Trees

**Problem:** Clinical trial variants (Phase I vs Phase II) may need shared context.

**Solution:** Product family linking
```python
PRODUCT_FAMILIES = {
    'AKY-2519': {
        'family': 'AKY',
        'related': ['AKY-1189', 'AKY-xxxx']
    }
}
```

### 3. Configurable Strictness

**Allow runtime configuration:**
```python
MEMORY_FILTER_MODE = os.environ.get('MEMORY_FILTER_MODE', 'strict')
# Options: 'strict', 'moderate', 'permissive'
```

---

## Related Documentation

- `docs/MEMORY_CONTAMINATION_TAKE3_ANALYSIS.md` - Take 3 analysis (DeepSeek QC, scoring approach)
- `docs/QC_MODEL_UPGRADE_CONTAMINATION_ANALYSIS.md` - Take 4 QC model comparison
- `docs/MEMORY_CROSS_CONTAMINATION_CLEAN_IMPLEMENTATION.md` - Original row context implementation
- `docs/SEARCH_MEMORY_SYSTEM.md` - Memory system architecture

---

## Conclusion

The strict two-tier memory filtering approach represents a **fundamental shift** from:
- **Scoring-based soft filtering** (rank cross-row memories lower)

To:
- **Binary hard filtering** (block cross-row memories entirely)

This should address the multi-product company contamination identified in Take 3 and Take 4, particularly the Bayer (56%) and Aktis (100%) cases.

**Next Steps:**
1. ✅ Code deployed and syntax-checked
2. 🔄 Run Take 5 validation with fresh memory
3. 🔄 Analyze contamination results
4. 🔄 Compare with Take 4 (31.1% baseline)
5. 🎯 Target: <20% contamination

**Status:** Ready for Take 5 testing

---

**Implementation Date:** 2026-02-09
**Implemented By:** Claude Sonnet 4.5 (1M context)
**File Modified:** `src/the_clone/search_memory.py` (lines ~975-997, ~1066)
**Status:** ✅ Deployed, awaiting validation testing
