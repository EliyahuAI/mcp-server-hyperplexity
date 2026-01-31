# Batch Quote Extraction (Code-Based)

Extract quotable snippets with codes for synthesis. **Synthesis will NOT see original sources** - only these snippets.

**Today:** {current_date} | **Mode:** {extraction_mode_guidance} | **Max:** {max_snippets}/source/search

**Search terms:**
{all_search_terms_formatted}

**RULES:**
- **Merge contiguous:** Adjacent sentences = ONE snippet (use ranges), even if addressing different aspects
- **No duplication:** Once a passage is extracted, trust it's available to synthesis - do NOT extract again for other terms
- **Self-contained:** Each snippet MUST make a complete point in isolation - no sentence fragments
- **Skip redundant:** If a point was already made by a snippet of same/higher quality, do NOT extract again

{mode_rules}

---

## Labeled Sources

Sentences labeled `` §SX:Y.Z ``, headings labeled `` §SX:Y.0 `` (X=source, Y=section, Z=sentence). Copy exact labels.

{formatted_sources}

---

## Task Structure

For each source:
1. **Assess source-level quality** → c (authority/quality) + p (probability)
2. **Extract snippets** → code + detail_limitation
3. **Assign source handle** → 1-word identifier (freddie, nih, pubmed, etc.)

---

## Source-Level Assessment (CRITICAL)

Evaluate ENTIRE source before extracting snippets:

**c (classification)** - Authority + all applicable quality codes:
- **Authority (who):** ALWAYS include one
  - **H**: High authority + topic expertise
  - **M**: Medium authority or unclear
  - **L**: Low authority or lacks topic expertise

- **Quality (what):** Include ALL that apply
  - **P**: PRIMARY (official/primary doc)
  - **D**: DOCUMENTED (methods/peer-reviewed)
  - **A**: ATTRIBUTED (named experts throughout)
  - **O**: OK (no red flags, nothing special)
  - **C**: CONTRADICTED (false/inconsistent)
  - **U**: UNSOURCED (no evidence)
  - **PR**: PROMOTIONAL (biased)
  - **S**: STALE (outdated)
  - **SL**: SLOP (AI SEO)
  - **IR**: INDIRECT (tangentially related)

**Format:** c:H/P (high authority + primary), c:M/A/O (medium + attributed + ok), c:L/U/S (low + unsourced + stale)
**Can combine multiple quality codes** - include ALL that apply to the source

**p (probability)** - Exact values: p05, p15, p30, p50, p65, p85, p95

Judge extracts all atomic claims from source and tests each. Pass = precisely accurate. p = expected pass-rate.

**source_handle** - 1-word identifier: freddie, nih, pubmed, nrel, bankrate, healthline, etc.

---

## Snippet Extraction Rules

**Gate - Extract only if:**
- Concrete, verifiable facts (not vague summaries/speculation)
- Doesn't need full article to verify
- Skip AI-generated SEO slop (mark source c:LA/SL if encountered)

**Pass-all flag:** `` §SX:* `` → Use entire source if dense/interconnected or would extract >50%

**Snippet Requirements:**
- **Self-contained:** Each snippet MUST make a complete point in isolation
- **Context in brackets:** Max 5 words, shorthand preferred (e.g., [re: IF] not [regarding intermittent fasting])
- **Ellipsis for gaps:** Use ... to join non-adjacent sentences into one coherent snippet
- **Must be testable:** Given only URL, title, and snippet, a judge can verify all claims
- **No redundancy:** Skip if same point already made by another snippet of same/higher quality

**Code Syntax:**
- Single: `` §S1:1.1 ``
- **Range (REQUIRED for consecutive):** `` §S1:1.5-1.7 ``
- **Ellipsis join (non-adjacent):** `` §S1:1.2 ... §S1:1.5 `` → resolves to "text1 ... text5"
- Word range: `` §S2:1.1.w5-7 `` (1-indexed)
- Heading context: `` [§S1:2.0] §S1:2.1 ``
- Attribution: `` [§S1:2.1.w1-4] §S1:1.3 `` (REQUIRED for c:A sources)
- Clarification: `` §S1:1.1 [re: Gemini] `` (max 5 words, shorthand)

**Consecutive Lines (CRITICAL):**
- **Contiguous sentences = ONE snippet** - even if they address different search terms or aspects
- Use ranges: `` §S1:2.1-2.4 `` - NEVER create separate snippets for adjacent lines
- Assign combined snippet to the MOST relevant search term

**Tables (CRITICAL):**
- ONE snippet per table: `` §S1:5.0-5.7 `` (header row 0 + data rows 1-7)
- NEVER separate rows

**CRITICAL - Code Accuracy Rules:**
- **ONLY use codes that appear in the labeled source text** - copy them EXACTLY
- Each source shows "Valid codes for SX:" at the bottom - codes MUST fall within those ranges
- **WRONG formats (NEVER output these):**
  - `` §S2:47.84 `` ← Decimal sentence numbers don't exist
  - `` §S2:189 `` ← Single integers without section.sentence format
  - `` §S7:1.1 `` when extracting from S2 ← Wrong source prefix
  - `` §S1:1.15-1.18 `` ← Range beyond actual sentence count
- **If you can't find the exact code in the source, OMIT the quote entirely**
- When in doubt, look at the "Valid codes" line for each source

---

## Snippet Handle Components

For each snippet, provide: `detail_limitation` (NO source prefix here)

**CRITICAL: EVERY CITATION MUST HAVE A UNIQUE TEXT HANDLE**
- Handles are the PRIMARY identifier for citations in synthesis
- If two snippets have the same handle, synthesis cannot distinguish them
- **ALWAYS ensure uniqueness** - append _2, _3, _4, etc. if a handle already exists

**Format:** `detail_limit` (max 2 words total, shorthand preferred)
- **detail**: 1 word, abbreviated (mtg-rate, wt-loss, eff-tbl)
- **limit**: 1 word, abbreviated (dec25, us, 2024)

**Examples:**
- `mtg-rate_dec25` (mortgage rate, December 2025)
- `wt-loss_if` (weight loss, intermittent fasting)
- `eff-tbl_solar` (efficiency table, solar)
- `wt-loss_if_2` ← Second snippet on same topic
- `wt-loss_if_3` ← Third snippet

Max 15 chars. **MUST be unique** (append _2, _3 if needed). Use common abbreviations.

**Full handle assembled later:** `{{source_handle}}_{{detail}}_{{limitation}}`
- freddie_mortgage-rate_dec-2025
- nih_weight-loss_if-protocol
- nih_weight-loss_if-protocol_2

---

## Output Format

```json
{{
  "source_metadata": {{
    "S1": {{"handle": "freddie", "c": "H/P", "p": "p95"}},
    "S2": {{"handle": "nih", "c": "H/D/A", "p": "p85"}},
    "S3": {{"handle": "techblog", "c": "M/O", "p": "p65"}}
  }},
  "quotes_by_search": {{
    "1": [
      ["mortgage-rate_dec-2025", "§S1:1.1"],
      ["refinance-rate_30yr-fixed", "§S1:2.1"],
      ["weight-loss_if-vs-cer", "[§S2:1.0] §S2:1.5"],
      ["insulin-sensitivity_tre-protocol", "§S2:2.1-2.3"],
      ["ai-trends_2025", "§S3:1.1"]
    ],
    "2": []
  }}
}}
```

**source_metadata** - One entry per source:
- **handle**: 1-word identifier (nih, webmd, freddie)
- **c**: Authority + quality codes (H/P, M/A/O, L/U/S)
- **p**: Probability (p05, p15, p30, p50, p65, p85, p95)

**quotes_by_search** - Organized by search term number:
- Each quote: `[detail_limitation, code]` ← **HANDLE FIRST, then code**
- Source is identified by code prefix (§S1:1.1 → S1)
- **Max {max_snippets} per source per search term**
- **ORDERING: List quotes sequentially by source (all S1, then all S2, then S3...), and within each source by code order (1.1, 1.2, 2.1...)**

Return empty `{{}}` if nothing clear.

**⚠️ RESPONSE LENGTH LIMIT: Keep your total response under {word_limit} words.**
