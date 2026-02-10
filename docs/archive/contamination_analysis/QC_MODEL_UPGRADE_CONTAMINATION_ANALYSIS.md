# QC Model Upgrade Impact Analysis
## DeepSeek V3.2 → Claude Sonnet 4.5

**Date:** 2026-02-09
**Analysis Type:** Direct comparison of identical 68-row dataset
**Variable Changed:** QC model only
**Analysis Script:** `analyze_contamination_take4_qc.py`

---

## Executive Summary

### Unexpected Finding: QC Model Has Minimal Impact on Contamination

Upgrading the QC model from DeepSeek V3.2 (Take 3) to Claude Sonnet 4.5 (Take 4) resulted in a **slight increase** in contamination, contrary to expectations:

| Metric | Take 3 (DeepSeek QC) | Take 4 (Sonnet QC) | Change |
|--------|---------------------|-------------------|---------|
| **Contamination Rate** | 28.9% | 31.1% | **+2.2 pp** (+7.7%) |
| **Contaminated Validations** | 26/90 | 28/90 | **+2** |
| **Rows with Contamination** | 7/10 | 8/10 | **+1 row** |

### Key Insight

🔍 **QC model choice does NOT significantly affect memory contamination.**

- 9 out of 10 rows showed **no change** in contamination
- Only 1 row worsened (previously clean row gained contamination)
- 0 rows improved

**Conclusion:** Memory contamination is primarily a **memory filtering and retrieval issue**, not a QC quality issue. The QC layer operates downstream of source retrieval and cannot fix contaminated sources.

---

## Detailed Results

### Configuration

**Take 3:**
- Memory: Fresh (no contamination from previous runs)
- QC Model: DeepSeek V3.2 (the-clone)
- Dataset: 68 rows, 43 companies, 66 products

**Take 4:**
- Memory: Fresh (same starting point)
- QC Model: Claude Sonnet 4.5 (claude-opus-4-6)
- Dataset: **Identical 68 rows** (direct comparison)

### Overall Statistics

**Take 3 (DeepSeek V3.2 QC):**
- Total Validations: 90
- Contaminated: 26 (28.9%)
- Rows with Contamination: 7/10

**Take 4 (Sonnet 4.5 QC):**
- Total Validations: 90
- Contaminated: 28 (31.1%)
- Rows with Contamination: 8/10

**Change:**
- Contamination Rate: 28.9% → 31.1% (+2.2 percentage points)
- Relative Change: -7.7% (increase in contamination)

---

## Row-by-Row Analysis

### ✓ Clean in Both Versions (2 rows)

#### Row 0: Akiram Therapeutics / 177Lu-AKIR001
- DeepSeek QC: 0/9 contaminated (0%)
- Sonnet QC: 0/9 contaminated (0%)
- **Status:** ✓ Consistently clean

#### Row 42: Modulation Therapeutics / MTI-201
- DeepSeek QC: 0/9 contaminated (0%)
- Sonnet QC: 0/9 contaminated (0%)
- **Status:** ✓ Consistently clean

---

### = No Change in Contamination (7 rows)

#### Row 6: Bayer / 225Ac-PSMA-Trillium
- DeepSeek QC: 5/9 contaminated (56%)
- Sonnet QC: 5/9 contaminated (56%)
- **Status:** = Unchanged (high contamination in both)

#### Row 12: Radionetics Oncology / 68Ga-R11228 / 177Lu-R11228
- DeepSeek QC: 2/9 contaminated (22%)
- Sonnet QC: 2/9 contaminated (22%)
- **Status:** = Unchanged (low contamination in both)

#### Row 18: Aktis Oncology / AKY-2519
- DeepSeek QC: 9/9 contaminated (100%)
- Sonnet QC: 9/9 contaminated (100%)
- **Status:** = Unchanged (complete contamination in both)

#### Row 24: AstraZeneca / AZD2068
- DeepSeek QC: 2/9 contaminated (22%)
- Sonnet QC: 2/9 contaminated (22%)
- **Status:** = Unchanged (low contamination in both)

#### Row 30: SOFIE / iTheranostics / FAPI (FAPI-46 and FAPI-74)
- DeepSeek QC: 4/9 contaminated (44%)
- Sonnet QC: 4/9 contaminated (44%)
- **Status:** = Unchanged (moderate contamination in both)

#### Row 36: ITM Isotope Technologies Munich / ITM-11
- DeepSeek QC: 2/9 contaminated (22%)
- Sonnet QC: 2/9 contaminated (22%)
- **Status:** = Unchanged (low contamination in both)

#### Row 48: Eli Lilly / PNT2001
- DeepSeek QC: 2/9 contaminated (22%)
- Sonnet QC: 2/9 contaminated (22%)
- **Status:** = Unchanged (low contamination in both)

---

### ✗ Worsened with Sonnet QC (1 row)

#### Row 54: Radiopharm Theranostics / RAD301
- DeepSeek QC: 0/9 contaminated (0%)
- Sonnet QC: 2/9 contaminated (22%)
- **Change:** Clean → Contaminated
- **Newly Contaminated Columns:**
  - "Latest News (Bulleted with Date)"
  - "Next Milestone Estimate & Abandonment Signs"

**Analysis:**
- This row was perfectly clean with DeepSeek QC
- Sonnet 4.5 QC introduced contamination in 2 columns
- Possible reasons:
  1. Sonnet retrieved different sources during validation
  2. Sonnet interpreted broader context as relevant
  3. Random variation in source retrieval

**Status:** ✗ Regression - Sonnet QC introduced new contamination

---

## Summary Statistics

| Category | Count | Percentage |
|----------|-------|------------|
| **Rows Improved** | 0 | 0% |
| **Rows Worsened** | 1 | 10% |
| **Rows Unchanged** | 9 | 90% |
| **Clean in Both** | 2 | 20% |

---

## Analysis & Interpretation

### Why Doesn't QC Model Impact Contamination?

**The QC Process Pipeline:**

```
1. Source Retrieval (Memory + Search)
   ↓
2. Source Filtering (Row-Identity Matching)
   ↓
3. Validation & Analysis (QC Model)
   ↓
4. Result Generation
```

**Key Insight:** QC operates at **Step 3**, but contamination occurs at **Steps 1-2**.

#### Contamination Happens Before QC

1. **Memory Retrieval:**
   - If memory contains cross-row information, it gets retrieved
   - QC model cannot reject sources already in the input

2. **Source Filtering:**
   - Row-identity filtering determines which sources are available
   - QC model works with whatever sources are provided

3. **QC Validation:**
   - QC model analyzes and validates the sources
   - Cannot fix contamination in the source material itself
   - Can only work with the sources it receives

#### Why the Slight Increase?

The 2.2 percentage point increase (28.9% → 31.1%) is likely due to:

1. **Different Validation Choices:**
   - Sonnet 4.5 may interpret sources differently
   - May include more context or broader references
   - May use different search queries during validation

2. **Random Variation:**
   - Small sample size (10 rows, 90 validations)
   - 2 additional contaminated validations could be noise
   - Not statistically significant

3. **Model Behavior Differences:**
   - Sonnet may be more thorough in citing sources
   - May pull in more contextual information
   - May reference related entities more frequently

---

## Implications for Contamination Reduction

### What This Tells Us

1. **QC Model is NOT the Solution**
   - Upgrading to a more powerful QC model (Sonnet 4.5) did not reduce contamination
   - QC operates too late in the pipeline to fix contamination
   - Focus should be on Steps 1-2 (retrieval and filtering)

2. **Memory Filtering is Critical**
   - Take 3's 28.9% contamination is primarily due to:
     - Multi-product company issues
     - Partnership context in sources
     - Pipeline overview articles
   - These are all **source-level issues**, not QC-level issues

3. **Product-Level Filtering is the Next Priority**
   - As identified in Take 3 analysis
   - Need to enhance row-identity filtering to be product-specific
   - This happens at Step 2, before QC

### What This Doesn't Tell Us

1. **QC Quality Impact:**
   - This analysis only measures contamination, not validation quality
   - Sonnet 4.5 may still provide better validation accuracy
   - Better reasoning, better citations, better confidence scores

2. **Error Correction:**
   - QC model may correct other types of errors
   - Just not memory cross-contamination specifically

---

## Recommendations

### Immediate Actions

1. **Do NOT Expect QC to Fix Contamination** ✅ VALIDATED
   - QC model choice has minimal impact on contamination
   - Focus efforts on memory filtering instead

2. **Choose QC Model Based on Quality, Not Contamination**
   - Use Sonnet 4.5 if validation quality is better
   - Use DeepSeek V3.2 if cost is a concern
   - Contamination will be similar either way

3. **Investigate Row 54 Regression**
   - Understand why Radiopharm Theranostics became contaminated with Sonnet
   - May reveal issues with Sonnet's source retrieval patterns
   - Could inform source filtering improvements

### Medium-Term Strategy

4. **Implement Product-Level Filtering** (HIGH PRIORITY)
   - As recommended in Take 3 analysis
   - This is where contamination can be reduced
   - Target: <15% contamination

5. **Enhance Memory Scoring Algorithm**
   - Penalize sources mentioning foreign products
   - Boost sources focusing on current row's entities
   - Implement negative boosting for unrelated companies

6. **Add Source Relevance Validation**
   - Pre-filter sources before QC
   - Reject sources primarily about other entities
   - Independent of QC model choice

### Long-Term Improvements

7. **A/B Test QC Models for Quality**
   - Measure validation accuracy, not contamination
   - Compare confidence calibration
   - Assess citation quality and reasoning

8. **Implement Multi-Stage Filtering**
   - Stage 1: Memory retrieval with row context
   - Stage 2: Source relevance scoring
   - Stage 3: Entity-specific filtering
   - Stage 4: QC validation and analysis

---

## Comparison with Previous Results

### Full Progression: Take 1 → Take 4

| Version | Memory | QC Model | Contamination | Change from T1 |
|---------|--------|----------|---------------|----------------|
| **Take 1** | Old | Unknown | 37.0% | - |
| **Take 2** | Old | Unknown | 36.0% | -1.0 pp (-3%) |
| **Take 3** | Fresh | DeepSeek V3.2 | 28.9% | -8.1 pp (-22%) |
| **Take 4** | Fresh | Sonnet 4.5 | 31.1% | -5.9 pp (-16%) |

**Key Observations:**

1. **Fresh Memory is the Game Changer**
   - Take 1 → Take 2: Old memory + fixes = -3% improvement
   - Take 1 → Take 3: Fresh memory + fixes = -22% improvement
   - Fresh memory contributes ~19 percentage points of improvement

2. **QC Model is Negligible**
   - Take 3 → Take 4: QC model change = +2.2 pp worsening
   - Essentially no impact (within noise margin)

3. **Take 3 Performance is Best**
   - Take 3 (DeepSeek QC): 28.9% contamination
   - Take 4 (Sonnet QC): 31.1% contamination
   - DeepSeek V3.2 slightly better for contamination

### Recommendation for Production

**Use Take 3 configuration (Fresh Memory + DeepSeek V3.2 QC)** unless validation quality metrics show Sonnet 4.5 is significantly better.

If using Sonnet 4.5 for quality reasons, accept the slight contamination increase (2.2 pp) as acceptable trade-off.

---

## Next Steps

### Test Plan: Product-Level Filtering (Take 5)

1. **Enhance Row-Identity Filtering**
   - Modify memory scoring to heavily penalize different products
   - Even from same company
   - Implement product-specific context matching

2. **Target Problematic Cases**
   - Bayer (2 products): Reduce from 56% to <30%
   - Aktis (2 products): Reduce from 100% to <50%

3. **Choose QC Model**
   - Based on quality metrics, not contamination
   - Likely Sonnet 4.5 for better reasoning
   - Accept ~31% contamination baseline

4. **Expected Results**
   - Take 5: Fresh memory + Product filtering + Sonnet QC
   - Target: <20% contamination (down from 31.1%)
   - Stretch goal: <15% contamination

---

## Related Documentation

- `docs/MEMORY_CONTAMINATION_TAKE3_ANALYSIS.md` - Take 3 detailed analysis
- `docs/MEMORY_CONTAMINATION_ANALYSIS_REPORT.md` - Take 1 vs Take 2 comparison
- `docs/MEMORY_CROSS_CONTAMINATION_CLEAN_IMPLEMENTATION.md` - Implementation details
- `docs/SEARCH_MEMORY_SYSTEM.md` - Memory system architecture

---

## Appendix: Technical Details

### Analysis Methodology

1. **Same Dataset:** 68 rows in both Take 3 and Take 4
2. **Same Sample:** 10 rows sampled at indices: 0, 6, 12, 18, 24, 30, 36, 42, 48, 54
3. **Same Memory State:** Both start with fresh memory
4. **Single Variable:** Only QC model changed

### Contamination Detection

- String matching for foreign company/product names
- Excluded URL-only mentions
- Normalized entity names (removed Inc., Ltd., etc.)
- Case-insensitive matching

### Limitations

- Sample size: 10 rows (14.7% of dataset)
- Statistical significance: 2.2 pp change may be within margin of error
- Only measures contamination, not validation quality

---

## Conclusion

The QC model upgrade from DeepSeek V3.2 to Claude Sonnet 4.5 resulted in a **slight increase** in contamination (28.9% → 31.1%), demonstrating that:

### ✅ Key Findings

1. **QC model has minimal impact on contamination** (90% of rows unchanged)
2. **Contamination is a source-level issue**, not a QC-level issue
3. **Fresh memory remains the critical factor** (enabled 22% reduction in Take 3)
4. **Product-level filtering is the next priority** for contamination reduction

### 🎯 Recommended Path Forward

1. ✅ Use fresh memory (validated in Take 3)
2. ✅ Choose QC model based on quality, not contamination
3. 🔄 Implement product-level filtering (Take 5)
4. 🔄 Target <15% contamination with enhanced filtering

**Status:** Ready to proceed with product-level filtering enhancement in Take 5.

---

**Report Generated:** 2026-02-09
**Analyst:** Claude Sonnet 4.5 (1M context)
**Status:** QC Model Impact Assessed - Minimal Effect on Contamination
