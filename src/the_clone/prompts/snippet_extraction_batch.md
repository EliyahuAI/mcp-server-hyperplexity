# Batch Quote Extraction (Code-Based)

Extract quotable snippets with codes for synthesis. **Synthesis will NOT see original sources** - only these snippets.

**Today:** {current_date} | **Mode:** {extraction_mode_guidance} | **Max:** {max_snippets}/source

**Search terms:**
{all_search_terms_formatted}

---

## Labeled Sources

Sentences labeled `` `SX:Y.Z ``, headings labeled `` `SX:Y.0 `` (X=source, Y=section, Z=sentence). Copy exact labels.

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

**Pass-all flag:** `` `SX:* `` → Use entire source if dense/interconnected or would extract >50%

**Snippet Requirements:**
- **Self-contained:** [SHORT CONTEXT] + DIRECT FACT (never paraphrase)
- **Context in brackets:** Max 10 words, clean summary
- **Must be testable:** Given only URL, title, and snippet, a judge can verify all claims

**Code Syntax:**
- Single: `` `S1:1.1 ``
- **Range (REQUIRED for consecutive sentences):** `` `S1:1.5-1.7 ``
- Word range: `` `S2:1.1.w5-7 `` (1-indexed)
- Heading context: `` [`S1:2.0] `S1:2.1 ``
- Attribution: `` [`S1:2.1.w1-4] `S1:1.3 `` (REQUIRED for c:A sources)
- Clarification: `` `S1:1.1 [of Gemini] ``

**Consecutive Lines (CRITICAL):**
- **Consecutive lines within same heading section = ONE snippet**
- Use ranges to group: `` `S1:2.1-2.4 `` for lines that flow together under one heading
- Don't split related content that belongs together conceptually

**Tables (CRITICAL):**
- ONE snippet per table: `` `S1:5.0-5.7 `` (header row 0 + data rows 1-7)
- NEVER separate rows

**CRITICAL:** Only use codes that exist in sources.

---

## Snippet Handle Components

For each snippet, provide: `detail_limitation` (NO source prefix here)

**Format:** `detail_limitation`
- **detail** (1-2 words hyphenated): mortgage-rate, weight-loss, efficiency-table
- **limitation** (1-2 words hyphenated): dec-2025, solar-2024, us-only, post-2020

**Examples:**
- `mortgage-rate_dec-2025`
- `weight-loss_if-protocol`
- `efficiency-table_solar-2024`

Max 25 chars. Must be unique within source (append _2, _3 if needed).

**Full handle assembled later:** `{{source_handle}}_{{detail}}_{{limitation}}`
- freddie_mortgage-rate_dec-2025
- nih_weight-loss_if-protocol

---

## Output Format

```json
{{
  "quotes_by_source": {{
    "S1": {{
      "source_handle": "freddie",
      "c": "H/P",
      "p": "p95",
      "quotes_by_search": {{
        "1": [
          ["mortgage-rate_dec-2025", "`S1:1.1"],
          ["refinance-rate_30yr-fixed", "`S1:2.1"]
        ],
        "2": []
      }}
    }},
    "S2": {{
      "source_handle": "nih",
      "c": "H/D/A",
      "p": "p85",
      "quotes_by_search": {{
        "1": [
          ["weight-loss_if-vs-cer", "[`S2:1.0] `S2:1.5"],
          ["insulin-sensitivity_tre-protocol", "`S2:2.1-2.3"]
        ]
      }}
    }},
    "S3": {{
      "source_handle": "techblog",
      "c": "M/O",
      "p": "p65",
      "quotes_by_search": {{
        "1": [["ai-trends_2025", "`S3:1.1"]]
      }}
    }}
  }}
}}
```

**For each source:**
- **source_handle**: 1-word identifier
- **c**: Authority + all applicable quality codes (H/P, M/A/O, L/U/S, etc.)
- **p**: Source-level probability (p05, p15, p30, p50, p65, p85, p95)
- **quotes_by_search**: Organized by search term number
  - Each quote: `[detail_limitation, code]` ← **HANDLE FIRST, then code**

Return empty `{{}}` if nothing clear.
