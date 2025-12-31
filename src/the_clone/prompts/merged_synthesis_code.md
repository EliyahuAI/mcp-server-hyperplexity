# Synthesis with Code-Based Citations

Synthesize answer to query using labeled sources. Cite with codes, probability, and classification.

**Query:** {query} | **Today:** {current_date}

## Synthesis Instructions

{synthesis_guidance}

---

## Labeled Sources

Below you'll see sources with text labeled with codes. Each sentence ends with a code like `` §S1:1.1 ``.

**How codes work:**
- `` §S1:1.1 `` = Source 1, Section 1, Sentence 1
- `` §S2:3.5 `` = Source 2, Section 3, Sentence 5
- `` §S1:1.0 `` = Section heading (sentence 0)
- `` §S1:1.5-1.7 `` = Range from sentence 1.5 to 1.7

**To cite a fact:** Find the sentence in the labeled text below, copy its code exactly.

**Available codes:** Each source shows "Available codes: `` §S1:1.0-1.25 `` (26 codes)" - this tells you what codes exist. Only use codes that are listed.

{formatted_sources}

**Context annotations (advanced):**
- Heading context: `` [§S1:2.0] §S1:2.1 `` (adds heading from 2.0 as context for 2.1)
- Attribution: `` [§S2:1.w1-4] §S2:3.5 `` (pulls words 1-4 from sentence 1 as attribution)
- Clarification: `` §S1:1.1 [of Gemini] `` (adds clarifying text)

**CRITICAL:** Only use codes that exist in sources above. Don't invent codes.

---

## Source-Level Quality (Each source assessed once)

**p (probability)** - Source-level score: 0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95
- Judge tests all atomic claims from source, p = expected pass-rate

**c (classification)** - Authority + all applicable quality codes:

**Authority (required - pick one):**
- **H**: High authority + topic expertise
- **M**: Medium authority or unclear
- **L**: Low authority

**Quality (include ALL that apply):**
- **P**: PRIMARY (official/primary doc)
- **D**: DOCUMENTED (methods/peer-reviewed)
- **A**: ATTRIBUTED (named experts)
- **O**: OK (no red flags)
- **C**: CONTRADICTED (false)
- **U**: UNSOURCED (no evidence)
- **PR**: PROMOTIONAL (biased)
- **S**: STALE (outdated)
- **SL**: SLOP (AI SEO)
- **IR**: INDIRECT (tangential)

**Format:** c:H/P (high + primary), c:M/A/O (medium + attributed + ok), c:H/P/D (high + primary + documented)

**CRITICAL:** Prefer H sources for critical claims!

---

## Citation Format

**Format:** `{{§S#:code, p, c}}`

**Fields:**
1. **code**: `` §S1:1.1 `` (with optional context)
2. **p**: Source probability (0.05-0.95)
3. **c**: Classification with c: prefix (c:H/P, c:M/O, c:H/P/D, etc.)

**Examples:**
```
"Released Nov 2024 {{§S1:1.1, 0.95, c:H/P}} [Anthropic official - high authority + primary]"

"NIH study found {{§S2:1.5, 0.90, c:H/P/D/A}} [high authority + primary + documented + attributed] 40% improvement"

"Tech blog reports {{§S3:3.1, 0.65, c:M/O}} [medium authority + ok, unverified]"

"Reddit claims {{§S4:1.1, 0.30, c:L/U}} [low authority + unsourced]"
```

**With context annotations:**
```
"Under API Pricing {{[§S1:2.0] §S1:2.5, 0.85, c:H/P}} [heading from code §S1:2.0], rate is $0.002"

"Dr. Smith stated {{[§S2:1.1.w1-5] §S2:3.2, 0.90, c:H/A}} [attribution from code §S2:1.1.w1-5] results improved"

"The model {{§S1:1.5 [of GPT-4], 0.75, c:M/O}} [clarification added] processes images"
```

---

## Output Format

{output_format_guidance}

**Example:**
```json
{
  "answer": {
    "opus_4": {
      "release": "Nov 2024 {{§S1:1.1, 0.95, c:H/P}} [Anthropic official]",
      "architecture": "Transformer {{§S1:1.2-1.3, 0.85, c:H/P/D}} [documented] + MoE {{§S1:1.4, 0.85, c:H/P/D}}",
      "performance": {
        "mmlu": "92.3% {{§S2:2.1, 0.95, c:H/P}}",
        "humaneval": "89.5% {{§S2:2.2, 0.95, c:H/P}}"
      }
    },
    "gpt_4.5": {
      "release": "Dec 2024 {{§S3:3.1, 0.65, c:M/O}}",
      "architecture": "Undisclosed {{§S3:3.2, 0.30, c:L/U}}"
    }
  }{assessment_field}
}
```

---

## Your Task

1. Synthesize structured answer with logical organization
2. Cite every factual claim: `{{§S#:code, p, c:classification}}`
3. Use only codes that exist in sources
4. Add verbose context after citations in square brackets
5. **Prefer H (high authority) sources** for critical claims

**Checklist:**
- ✓ Every claim has citation with code, p, and c
- ✓ p is exact source-level value (0.05-0.95)
- ✓ **c has c: prefix** (c:H/P, c:M/A/O, c:H/P/D)
- ✓ c includes authority (H/M/L) + ALL applicable quality codes
- ✓ Codes exist in sources (don't invent)
- ✓ Source prefix included (`` §S1: ``, `` §S2: ``, etc.)
- ✓ Verbose context added after citations
- ✓ Critical claims preferentially cite H sources
