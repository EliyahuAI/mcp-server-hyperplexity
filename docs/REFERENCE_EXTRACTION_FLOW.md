# Reference Extraction Flow

**Date**: 2025-11-08
**Status**: Active Implementation

This document explains the complete end-to-end flow of reference extraction in the Reference Check system.

---

## Overview

The reference extraction system has a **two-phase approach**:

1. **Python Parser** (reference_parser.py) - Attempts automated extraction and quality checking
2. **AI Extractor** (Sonnet 4.5) - Falls back to manual extraction when Python fails

The goal: Extract numbered references `[1]`, `[2]`, `[3]` and map them to full citations, so claims can reference them by number only.

---

## Complete Flow Diagram

```
User submits text
  ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: Python Pre-Processing (execution.py:1059-1076)    │
└─────────────────────────────────────────────────────────────┘
  ↓
[1] parser.extract_reference_list(text)
    │
    ├─ Strategy 1: Sections (## References, ## Bibliography)
    ├─ Strategy 2: Headings (markdown headers)
    ├─ Strategy 3: Tail search (last 20-40%)
    ├─ Strategy 4: Inline blocks
    └─ Strategy 5: Citation-URL pairs
    │
    ↓ Returns: parsed_reference_map (Dict[str, str])
       Example: {"[1]": "Smith et al. (2024)...", "[2]": "https://..."}

[2] parser.detect_reference_format(text, parsed_reference_map)
    │
    ↓ Determines path type:
      • "inline_links" - [1](url) format (Perplexity/ChatGPT)
      • "needs_parsing" - Reference section found
      • "not_found" - No references detected
    │
    ↓ Returns: (path_type, confidence)

[3] parser.check_reference_quality(parsed_reference_map) ← NEW!
    │
    ↓ Quality checks:
      • Are refs >20 chars? (not fragments)
      • Start with uppercase? (not mid-sentence fragments)
      • Not just punctuation? (not ":853-861, 2015")
      • Have author/year/URL/journal? (real citations)
      • <50% fragments? (mostly good)
    │
    ↓ Returns: (is_good, failure_reason)

[4] parser.build_enriched_text(text, parsed_reference_map, path_type)
    │
    ↓ Appends reference notice to text based on path + quality:

    PATH A (inline_links):
      "--- REFERENCES DETECTED (5 found) ---"
      → AI uses refs as-is, no reference_list needed

    PATH B (needs_parsing) + GOOD QUALITY:
      "--- PARSED REFERENCES (12 found) ---"
      [1] Smith et al. (2024)...
      [2] Johnson (2023)...
      → AI trusts these, uses numbers, no reference_list

    PATH B (needs_parsing) + BAD QUALITY:
      "--- PARSED REFERENCES FAILED QUALITY CHECK (11 found) ---"
      Automated parsing was NOT successful...
      **AI SEGMENTATION REQUIRED**
      → AI must extract from References section, provide reference_list

    PATH C (not_found):
      "--- NOTICE: No reference list detected ---"
      → AI must extract references if citations exist

┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: AI Extraction (execution.py:1080-1151)            │
└─────────────────────────────────────────────────────────────┘
  ↓
[5] _extract_claims(enriched_text)
    │
    ↓ Sends to Sonnet 4.5 with claim_extraction.md prompt
    │ Prompt includes SOLEMN OATH section
    │
    ↓ AI reads notice at end of enriched_text

    If "REFERENCES DETECTED":
      → Uses refs as-is in text
      → No reference_list in output

    If "PARSED REFERENCES" (good):
      → Trusts provided numbered refs
      → Uses [1], [2] in claim reference fields
      → No reference_list in output

    If "PARSED REFERENCES FAILED QUALITY CHECK":
      → Extracts from References section
      → Numbers them [1], [2], [3]
      → Provides complete reference_list in output
      → Uses [1], [2] in claim reference fields

    If "NOTICE: No reference list detected":
      → Extracts references if citations exist
      → Provides complete reference_list
    │
    ↓ Returns: extraction_result with claims + optional reference_list

[6] Determine final_reference_map (execution.py:1129-1143)
    │
    ↓ Logic:
      if path_type == "inline_links":
          final_map = parsed_reference_map  (AI cannot override)
      elif ai_reference_list exists:
          final_map = ai_reference_list  (AI override for bad quality)
      else:
          final_map = parsed_reference_map  (Python extraction was good)

[7] parser.resolve_citations(claim['reference'], final_reference_map)
    │
    ↓ For each claim:
      Input:  claim['reference'] = "[1]" or "[1][2][3]"
              final_reference_map = {"[1]": "Smith, J. et al. (2019). Title..."}
      │
      ↓ _extract_short_citation(full_citation):
        • Extracts: "Smith, J. et al. (2019). Title..." → "Smith et al. (2019)"
        • Or URL: "https://example.com/path" → "example.com"
      │
      Output: "[1] Smith et al. (2019)" or "[1] example.com"
    │
    ↓ Updates claim['reference'] with short format

[8] Save to CSV (execution.py:714-727)
    │
    ↓ CSV row includes:
      • Claim ID
      • Statement
      • Context
      • Text Location
      • Reference ← "[1] Smith et al. (2019)" ✓
      • Claim Criticality
      • (RESEARCH columns empty...)
```

---

## Four Paths Explained

### Path A: Inline Links (Already Good)
**Detection**: `[1](https://url)` or `[1] https://url` patterns (≥3 occurrences)
**Python Parser**: Extracts inline URLs
**Quality Check**: Not needed (inline URLs are always good)
**Notice Appended**: `--- REFERENCES DETECTED ---`
**AI Behavior**: Uses refs as-is from text, no `reference_list` needed
**Final Format**: URLs or short citations already in text

**Example**:
```
Text: "Brain rot is real [1](https://example.com)"
Notice: "--- REFERENCES DETECTED (1 found) ---"
AI output: "reference": "[1](https://example.com)"
Final: "[1] example.com"
```

---

### Path B1: Parsed References (Good Quality)
**Detection**: Reference section found with ≥3 complete citations
**Python Parser**: Extracts numbered reference list successfully
**Quality Check**: PASSED (refs are complete, have author/year/URL)
**Notice Appended**: `--- PARSED REFERENCES (12 found) ---`
**AI Behavior**: Trusts provided numbers, uses `[1]`, `[2]` in claims, no `reference_list`
**Final Format**: `[1] FirstAuthor et al. (Year)`

**Example**:
```
Text: "Brain rot is real (Firth et al., 2019)"
Parsed refs: {"[1]": "Firth, J. et al. (2019). The online brain..."}
Quality: PASSED
Notice: "--- PARSED REFERENCES (1 found) ---
         [1] Firth, J. et al. (2019). The online brain..."
AI output: "reference": "[1]"  (converts (Firth et al., 2019) → [1])
Final: "[1] Firth et al. (2019)"
```

---

### Path B2: Parsed References (Bad Quality) ← NEW!
**Detection**: Reference section found but quality check FAILED
**Python Parser**: Attempted extraction but got fragments/garbage
**Quality Check**: FAILED (>50% fragments, too short, no author/year/URL)
**Notice Appended**: `--- PARSED REFERENCES FAILED QUALITY CHECK ---`
**AI Behavior**: MUST extract from References section, provide `reference_list`
**Final Format**: `[1] FirstAuthor et al. (Year)`

**Example**:
```
Text: "Brain rot is real (Firth et al., 2019)"
     ...
     REFERENCES
     Firth, J. et al. (2019). The online brain: how the internet...

Parsed refs (BAD): {"[1]": "prompted with categorized", "[2]": ":853-861, 2015"}
Quality: FAILED (fragments detected: 2/2 refs are fragments)
Notice: "--- PARSED REFERENCES FAILED QUALITY CHECK (2 found) ---
         Automated parsing was NOT successful...
         **AI SEGMENTATION REQUIRED**"
AI output: reference_list: [{"ref_id": "[1]", "full_citation": "Firth, J. et al. (2019)..."}]
          "reference": "[1]"
Final: "[1] Firth et al. (2019)"
```

---

### Path C: No References Found
**Detection**: No reference section detected
**Python Parser**: Returns empty dict
**Quality Check**: Not applicable (empty is fine)
**Notice Appended**: `--- NOTICE: No reference list detected ---`
**AI Behavior**: Extract refs if citations exist, otherwise unreferenced claims
**Final Format**: `[1] FirstAuthor et al. (Year)` or null

**Example**:
```
Text: "Brain rot is real [1]"
      (no reference section found)
Parsed refs: {}
Notice: "--- NOTICE: No reference list detected ---"
AI output: Must provide reference_list if [1] citations exist
Final: Depends on AI extraction
```

---

## Key Components

### 1. Python Parser (reference_parser.py)

**Methods**:
- `extract_reference_list()` - 5 extraction strategies
- `detect_reference_format()` - Determines path type
- `check_reference_quality()` - NEW! Validates parsed refs aren't fragments
- `build_enriched_text()` - Appends appropriate notice based on path + quality
- `resolve_citations()` - Converts `[1]` + full citation → `[1] Author (Year)`
- `_extract_short_citation()` - Extracts short form from full citation

**Quality Check Criteria**:
```python
For each reference, check:
- Length ≥20 chars (not fragment)
- Starts with uppercase (not mid-sentence)
- Not just punctuation (not ":853-861, 2015")
- Has author OR year OR URL OR journal name

If >50% fail these checks → Quality FAILED
```

### 2. AI Extractor (claim_extraction.md prompt)

**SOLEMN OATH** (by electricity and transistors!):
1. Check for reference section at end of input
2. If NO section shown → refs already good
3. If "PARSED REFERENCES" → trust them, use numbers
4. If "FAILED QUALITY CHECK" → extract yourself, provide reference_list
5. If "No reference list detected" → extract if citations exist
6. NEVER use `(Author, Year)` in claim reference fields
7. ALWAYS convert to numbered format `[1]`, `[2]`
8. System auto-converts `[1]` → `[1] Author (Year)` later

**Output Structure** (reference_list FIRST):
```json
{
  "table_name": "...",
  "reference_list": [...],  ← First!
  "claims": [
    {
      "reference": "[1]"  ← Just the number
    }
  ]
}
```

### 3. Resolution Logic (execution.py:1129-1151)

**Determine final_reference_map**:
```python
if path_type == "inline_links":
    final_map = parsed_reference_map  # AI cannot override
elif ai_reference_list:
    final_map = ai_reference_list  # AI override (quality failed)
else:
    final_map = parsed_reference_map  # Python succeeded
```

**Resolve citations**:
```python
for claim in claims:
    if claim['reference'] and final_reference_map:
        # Input: "[1]" or "[1][2][3]"
        # Output: "[1] Smith et al. (2019)" or "[1] Smith et al. (2019), [2] Johnson (2024)"
        claim['reference'] = parser.resolve_citations(claim['reference'], final_reference_map)
```

---

## Example Scenarios

### Scenario 1: Perplexity Output (Path A)
```
Input: "AI is powerful [1](https://openai.com)"
↓
Python: Detects inline links, path="inline_links"
Notice: "--- REFERENCES DETECTED (1 found) ---"
AI: Uses "[1](https://openai.com)" directly
Resolution: "[1](https://openai.com)" → "[1] openai.com"
CSV: "[1] openai.com"
```

### Scenario 2: Academic Paper, Good Parsing (Path B1)
```
Input: "Brain rot is real (Firth et al., 2019)"
       REFERENCES
       Firth, J. et al. (2019). The online brain...

Python: Extracts {"[1]": "Firth, J. et al. (2019). The online brain..."}
Quality: PASSED (has author, year, complete)
Notice: "--- PARSED REFERENCES (1 found) ---
         [1] Firth, J. et al. (2019). The online brain..."
AI: Converts (Firth et al., 2019) → [1]
    Uses provided ref, outputs "reference": "[1]"
    No reference_list in output
Resolution: "[1]" + {"[1]": "Firth, J. et al..."} → "[1] Firth et al. (2019)"
CSV: "[1] Firth et al. (2019)"
```

### Scenario 3: Academic Paper, Bad Parsing (Path B2) ← NEW!
```
Input: "Brain rot is real (Firth et al., 2019)"
       REFERENCES
       Firth, J. et al. (2019). The online brain...

Python: Extracts {"[1]": "prompted with categorized", "[2]": ":853-861"}
Quality: FAILED (2/2 are fragments, no author/year/URL)
Notice: "--- PARSED REFERENCES FAILED QUALITY CHECK (2 found) ---
         Automated parsing was NOT successful.
         **AI SEGMENTATION REQUIRED**"
AI: Sees failure notice
    Extracts from References section
    Outputs: reference_list: [{"ref_id": "[1]", "full_citation": "Firth, J. et al. (2019)..."}]
            "reference": "[1]"
Resolution: "[1]" + {"[1]": "Firth, J. et al..."} → "[1] Firth et al. (2019)"
CSV: "[1] Firth et al. (2019)"
```

### Scenario 4: No References Found (Path C)
```
Input: "Brain rot is real [1]"
       (no reference section)

Python: Extracts {}
Notice: "--- NOTICE: No reference list detected ---
         If numbered citations exist, provide reference_list"
AI: Sees [1] in text but no refs
    Searches for References section
    Extracts and numbers references
    Provides reference_list
Resolution: Uses AI-provided reference_list
CSV: "[1] FirstAuthor (Year)" or "[1]" if not found
```

---

## Quality Check Details

### What Makes References "Good"?

Each reference must have **at least one** of:
- ✅ Author pattern (starts with uppercase name)
- ✅ Year (4-digit number)
- ✅ URL (http/https/doi/arxiv)
- ✅ Journal marker (journal, conference, proceedings, preprint)

AND must NOT be:
- ❌ Too short (<20 chars)
- ❌ Lowercase start (fragment)
- ❌ Just punctuation (":853-861, 2015")

### Failure Threshold

If **>50% of refs are fragments**, quality check FAILS.

**Example PASS** (2/3 good = 67%):
```
[1] Smith, J. et al. (2019). Title...  ✓
[2] https://example.com               ✓
[3] :853-861                          ✗ (fragment)
Result: PASS (67% good)
```

**Example FAIL** (1/3 good = 33%):
```
[1] prompted with categorized  ✗ (fragment)
[2] :853-861, 2015             ✗ (fragment)
[3] Smith et al. (2019)...     ✓
Result: FAIL (33% good, need 50%+)
```

---

## Short Citation Conversion

After resolution, `_extract_short_citation()` converts full citations to short format:

**Academic Citations**:
```
"Smith, J. et al. (2023). Title..." → "Smith et al. (2023)"
"Johnson, A. (2024). Title..."      → "Johnson (2024)"
"A1, B2, C3 (2023). Title..."       → "A1 et al. (2023)"
```

**URLs**:
```
"https://www.example.com/path" → "example.com"
"https://arxiv.org/abs/1234"   → "arxiv.org"
```

**Fallback**:
```
"Some long citation without clear pattern..." → "Some long citation withou..."  (30 chars max)
```

---

## File Locations

**Python Parser**:
- `src/lambdas/interface/actions/reference_check/reference_check_lib/reference_parser.py`
  - Lines 98-145: extract_reference_list()
  - Lines 147-207: check_reference_quality() ← NEW!
  - Lines 46-96: detect_reference_format()
  - Lines 857-978: build_enriched_text()
  - Lines 713-823: resolve_citations()
  - Lines 657-711: _extract_short_citation()

**AI Prompt**:
- `src/lambdas/interface/actions/reference_check/prompts/claim_extraction.md`
  - Lines 169-221: REFERENCE LIST HANDLING
  - Lines 225-264: SOLEMN OATH (by electricity and transistors!)
  - Lines 276-312: OUTPUT FORMAT (reference_list FIRST)

**Execution Flow**:
- `src/lambdas/interface/actions/reference_check/execution.py`
  - Lines 1059-1076: Python pre-processing
  - Lines 1080-1085: AI extraction call
  - Lines 1129-1151: Final resolution

---

## Key Design Decisions

### Why Quality Check?
Before the quality check, Python might extract garbage like:
```
[1] prompted with categorized
[2] :853-861, 2015
[6] :e2218523120, 2023
```

The AI would see "PARSED REFERENCES" and trust them, leading to broken citations.

**Solution**: Quality check detects fragments and triggers AI extraction demand.

### Why "by the power of electricity and transistors"?
Creates psychological commitment in the AI to follow the rules:
- Trust good references
- Don't rebuild unnecessarily
- Use only numbers `[1]`, not `(Author, Year)`
- Convert author-year to numbered format

### Why reference_list FIRST in output?
Forces AI to think about references before extracting claims, ensuring proper mapping.

### Why short citation format?
Instead of:
```
Reference: [1] https://publichealth.jhu.edu/2025/the-evidence-on-tylenol-and-autism
```

We get:
```
Reference: [1] publichealth.jhu.edu
```

Cleaner, easier to read, still verifiable.

---

## Testing Edge Cases

### Edge Case 1: Mixed Inline and Numbered
```
Text: "Claim 1 [1](https://url.com). Claim 2 (Smith, 2023)."
Path: inline_links (Perplexity pattern detected)
Behavior: AI uses both formats as-is
```

### Edge Case 2: Author-Year with Good Reference Section
```
Text: "(Smith, 2023)" + References section at end
Python: Extracts refs, numbers them [1], [2]...
Quality: PASSED
AI: Converts (Smith, 2023) → [1], trusts parsed refs
```

### Edge Case 3: Author-Year with Bad Parsing
```
Text: "(Smith, 2023)" + References section at end
Python: Extracts fragments (quality FAIL)
Notice: "FAILED QUALITY CHECK - AI SEGMENTATION REQUIRED"
AI: Extracts from References section, provides reference_list
```

### Edge Case 4: Numbered Citations, No Reference Section
```
Text: "Brain rot is real [1][2][3]" (no refs at end)
Python: No refs found, detects numbered citations
Notice: "No reference list detected"
AI: Must find/infer references or mark as inaccessible
```

---

## Success Criteria

A successful extraction produces:

1. ✅ **Numbered references** in claims: `[1]`, `[2]`, `[1][2][3]`
2. ✅ **Short citation format** after resolution: `[1] Smith et al. (2019)`
3. ✅ **No author-year format** in claims: NOT `(Smith, 2023)`
4. ✅ **Complete reference_list** when needed (quality failed or not found)
5. ✅ **Trusted parsed refs** when quality passes (no unnecessary rebuilding)

---

## Current Status

- ✅ Python parser with 5 extraction strategies
- ✅ Quality check method to detect fragments
- ✅ Dynamic notice based on quality check results
- ✅ AI oath to follow reference handling rules
- ✅ Short citation extraction from full citations
- ✅ Reference_list reordered to come first in output
- ✅ Backup mapping for refs without numbers

**Next**: Deploy and test with real academic papers to validate quality check accuracy.
