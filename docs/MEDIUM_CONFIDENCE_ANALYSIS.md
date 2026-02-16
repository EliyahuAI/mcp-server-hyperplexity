# MEDIUM Confidence Entries - Analysis Report

**Analysis Date:** February 13, 2026
**Dataset:** theranostic_CI_metadata_take6.json
**Total MEDIUM Confidence Entries:** 439
**Sample Validated:** 5 entries

---

## Executive Summary

MEDIUM confidence entries in the dataset exhibit **significantly lower accuracy** than HIGH confidence entries:

- **HIGH Confidence Mean:** 92.29/100
- **MEDIUM Confidence Mean:** 60/100
- **Difference:** -32.29 points

### Key Findings

✅ **Some MEDIUM ratings are too conservative** - 40% of tested entries (2/5) scored 90-95 and should be HIGH

❌ **"None identified" claims are unreliable** - 67% (2/3) were incorrect with information actually available

⚠️ **MEDIUM confidence indicates research uncertainty** - Often used when information wasn't found, not when absence was confirmed

---

## Validated Entries

### 1. Xofigo - Regulation (Score: 90/100)

**Claim:** "Priority Review designation"
**Stated Confidence:** MEDIUM
**Actual Status:** ✅ ACCURATE - FDA granted Priority Review Feb 2013

**Finding:**
- Priority Review definitively confirmed by FDA documents
- Approved May 15, 2013 (3+ months ahead of schedule)
- No Orphan Drug or Fast Track designations (correctly not mentioned)

**Recommendation:** **Upgrade to HIGH confidence**

**Issue:** The claim is accurate and well-documented. MEDIUM confidence is too conservative for a definitively confirmed regulatory designation.

---

### 2. AKY-2519 - Inactive Organization (Score: 95/100)

**Claim:** "None identified"
**Stated Confidence:** MEDIUM
**Actual Status:** ✅ ACCURATE - No previous organizations involved

**Finding:**
- Aktis Oncology founded in 2020 by MPM BioImpact
- AKY-2519 developed internally using proprietary platform
- No licensing, acquisition, or technology transfer from other orgs
- Definitively confirmed as internal program

**Recommendation:** **Upgrade to HIGH confidence**

**Issue:** This is an accurate negative finding confirmed through exhaustive research. When absence is definitively confirmed, use HIGH confidence.

---

### 3. PNT2002 - Active Organization (Score: 75/100)

**Claim:** "Eli Lilly and Company (via acquisition of POINT Biopharma)"
**Stated Confidence:** MEDIUM
**Actual Status:** ⚠️ PARTIALLY ACCURATE - Lilly owns it but development discontinued

**Finding:**
- ✅ Eli Lilly acquired POINT Biopharma Dec 27, 2023 for $1.4B
- ✅ Lilly owns the PNT2002 asset
- ❌ **NOT actively developed** - Lantheus abandoned FDA pursuit May 2025
- ❌ Not in Lilly's official pipeline as of Feb 2026
- SPLASH trial showed unfavorable OS trend (HR 1.11)

**Recommendation:** **MEDIUM confidence justified, but claim needs correction**

**Correction Needed:**
```
Current: "Eli Lilly and Company (via acquisition of POINT Biopharma)"
Should be: "Eli Lilly and Company (via acquisition; development discontinued May 2025)"
Or: Active Organization → "None (discontinued)"
```

**Issue:** The "Active Organization" field should not list Lilly if the program is discontinued. This is a data accuracy issue, not just confidence.

---

### 4. RAD201 - Core Patent (Score: 40/100)

**Claim:** "No key patent numbers or specific patent information for RAD201 identified..."
**Stated Confidence:** MEDIUM
**Actual Status:** ❌ INACCURATE - Patent information exists and was missed

**Finding:**
- **Patent information WAS available:**
  - PCT/EP2015/067424
  - WO/2016/016329 (Feb 4, 2016)
  - PCT/CN2018/091953 (June 20, 2018)
  - US20200306392A1 (Anti-HER2 nanobody)
- Patents acquired from NanoMab Technology Ltd for US$500,000
- Information available in patent databases and scientific literature

**Recommendation:** **Correct the data - add patent numbers**

**Correction Needed:**
```
Current: "None identified"
Should be: "PCT/EP2015/067424, WO/2016/016329 (Anti-HER2 nanobody patents acquired from NanoMab Technology)"
Confidence: HIGH
```

**Issue:** This is a research failure, not a legitimate "none found" case. The information was publicly available but missed during validation.

---

### 5. Pylarify - Regulation (Score: 0/100) ⚠️ CRITICAL ERROR

**Claim:** "No regulatory designations (e.g., Fast Track, Orphan Drug) identified"
**Stated Confidence:** MEDIUM
**Actual Status:** ❌ COMPLETELY WRONG - Priority Review was granted

**Finding:**
- **Priority Review was definitively granted in 2020**
- FDA approved Pylarify May 26, 2021
- Priority Review shortened review from 10 months to 6 months
- Multiple press releases and FDA documents confirm this
- Information widely available and well-documented

**Recommendation:** **IMMEDIATE CORRECTION REQUIRED**

**Correction Needed:**
```
Current: "No regulatory designations (e.g., Fast Track, Orphan Drug) identified"
Should be: "Priority Review (granted 2020)"
Confidence: HIGH
```

**Issue:** This is a major data error. The claim states "no regulatory designations" when Priority Review was granted and is well-documented in FDA databases, press releases, and industry news.

**Root Cause:** The explanation states "authoritative sources describe it as a diagnostic agent but do not mention special regulatory designations" - this indicates incomplete research. The validator did not check FDA approval timelines or regulatory databases.

---

## Pattern Analysis

### MEDIUM Confidence Usage Patterns

MEDIUM confidence is typically assigned to:

1. **Negative findings** ("None identified") - 60% of sample
2. **Uncertain organizational status** - 20% of sample
3. **Incomplete information** - 20% of sample

### Problem Categories

**Category 1: Underconfident Accurate Claims (40%)**
- Claims that are accurate and well-supported
- Should be HIGH confidence
- Examples: Xofigo Priority Review, AKY-2519 inactive org

**Category 2: Research Failures (40%)**
- Information was available but missed
- "None identified" when data exists
- Examples: RAD201 patents, Pylarify Priority Review

**Category 3: Legitimately Uncertain (20%)**
- Claim is partially accurate or status unclear
- MEDIUM confidence appropriate
- Example: PNT2002 ownership vs active development

---

## Recommendations

### Immediate Actions

1. **Correct Pylarify Entry** (Critical)
   - Change "None identified" to "Priority Review (granted 2020)"
   - Upgrade confidence to HIGH
   - This is a major data quality issue

2. **Correct RAD201 Entry** (High Priority)
   - Add patent numbers: PCT/EP2015/067424, WO/2016/016329
   - Upgrade confidence to HIGH
   - Research was incomplete

3. **Update PNT2002 Entry** (High Priority)
   - Mark development as discontinued
   - Remove from "Active Organization" or note "(discontinued May 2025)"
   - MEDIUM confidence appropriate given complex ownership status

### Process Improvements

4. **Revise "None Identified" Research Protocol**

   **Current problem:** Validators use "None identified" when information isn't found, not when absence is confirmed.

   **New protocol:**
   ```
   Before claiming "None identified":
   1. Check minimum 3 authoritative sources
   2. For FDA-approved drugs: Always check FDA databases
   3. For patents: Search Google Patents, USPTO, EPO
   4. For regulatory designations: Check FDA approval press releases
   5. Document search strategy in validation notes

   Confidence levels for negative findings:
   - HIGH: Definitively confirmed absence (exhaustive search, logical impossibility)
   - MEDIUM: Uncertain - limited search or conflicting information
   - LOW: Very uncertain - minimal search or likely incomplete
   ```

5. **Upgrade Conservative MEDIUM Ratings**

   When to use HIGH vs MEDIUM:

   **HIGH Confidence:**
   - 3+ authoritative sources agree
   - No contradictions found
   - Recent information (<6 months for R&D status)
   - **OR definitively confirmed negative finding**

   **MEDIUM Confidence:**
   - 2 authoritative sources
   - Minor contradictions or gaps
   - Some uncertainty in interpretation
   - **OR unconfirmed negative finding**

6. **Implement Validation Checklists by Column Type**

   **Regulation Column:**
   ```
   Required searches:
   [ ] FDA approval press release
   [ ] Company press release (approval date)
   [ ] FDA Drugs@FDA database
   [ ] Check for: Priority Review, Fast Track, Breakthrough, Orphan Drug
   [ ] Verify PDUFA date and actual approval date
   ```

   **Core Patent Column:**
   ```
   Required searches:
   [ ] Google Patents (patent.google.com)
   [ ] USPTO database
   [ ] EPO Espacenet
   [ ] Company acquisition/licensing press releases
   [ ] Scientific publications (patents often cited)
   ```

### Quality Metrics

**MEDIUM Confidence Quality Target:**
- Current mean accuracy: 60/100
- Target mean accuracy: 80/100
- Expected outcome: Fewer MEDIUM ratings overall, higher accuracy when used

**Expected Impact:**
- Reduce MEDIUM confidence entries from 439 to ~200 (upgrade accurate ones to HIGH)
- Correct inaccurate "none identified" claims with actual data
- Reserve MEDIUM for genuinely uncertain claims

---

## Statistical Summary

```
MEDIUM CONFIDENCE VALIDATION RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Entries Tested:                 5
Mean Accuracy:                  60/100
Median Accuracy:                75/100
Range:                          0-95

ACCURACY DISTRIBUTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Excellent (90-100):             2 (40%) ✅ Should be HIGH
Good (80-89):                   0 (0%)
Acceptable (70-79):             1 (20%) ⚠️ Needs correction
Poor (40-69):                   1 (20%) ❌ Major error
Fail (0-39):                    1 (20%) ❌ Critical error

CONFIDENCE APPROPRIATENESS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Should be HIGH:                 2 (40%)
MEDIUM appropriate:             1 (20%)
Needs correction:               2 (40%)

COMPARISON TO HIGH CONFIDENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HIGH confidence mean:           92.29/100
MEDIUM confidence mean:         60.00/100
Difference:                     -32.29 points

Error rate (< 70):
HIGH confidence:                0%
MEDIUM confidence:              40%
```

---

## Conclusions

1. **MEDIUM confidence is overused** - 40% of tested entries should be HIGH

2. **"None identified" claims need strict validation** - 67% error rate indicates poor research quality

3. **MEDIUM confidence = Lower accuracy** - 32-point gap vs HIGH confidence

4. **Critical data errors exist** - Pylarify missing Priority Review is a major quality issue

5. **Research protocols need improvement** - Systematic gaps in checking FDA databases and patent records

**Overall Assessment:** MEDIUM confidence entries require significant quality improvement. Immediate corrections needed for Pylarify and RAD201 entries.

---

**Analysis Performed By:** Claude Code QC Team
**Next Steps:**
1. Correct 2 critical errors (Pylarify, RAD201)
2. Re-evaluate all 439 MEDIUM confidence entries using updated protocols
3. Implement validation checklists
4. Target 80/100 mean accuracy for MEDIUM confidence entries

**Report Version:** 1.0
**Last Updated:** February 13, 2026
