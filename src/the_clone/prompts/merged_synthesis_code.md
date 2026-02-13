# Synthesis with Code-Based Citations

Synthesize answer to query using labeled sources. Cite with codes, probability, and classification.

**Query:** {query} | **Today:** {current_date}

## Synthesis Instructions

{synthesis_guidance}

**CRITICAL - YOU MUST USE THE SNIPPETS PROVIDED BELOW:**
- Your ONLY job is to synthesize the answer FROM the snippets below
- DO NOT create your own citations or reference sources not in the snippets
- EVERY factual claim MUST cite a snippet code from the labeled sources
- If you cannot find a snippet that supports a claim, DO NOT make that claim

**Response Length Management:**
- **Standard format:** Use full verbose citations: `{{§S1:1.1, 0.95, c:H/P}} [Anthropic official]`
- **If approaching max words:** Use minimal format to save space: `[S1.1.1]` (no § symbol, no p/c scores)
- The minimal format still tracks which snippet was used, just more compact
- Example: "Autoinflation improved outcomes [S1.2.3] [S1.2.5] [S2.1.1]"

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

## Important: Relevance vs Support

**Snippets grouped under a search term are RELEVANT to it, not necessarily SUPPORTING.**

Check for **`/N`** flags in reason field - these snippets contradict or don't support the search.

**Handling `/N` flagged snippets:**
1. Don't blend with supporting quotes - acknowledge contradiction
2. Use contrastive language: "However", "Instead", "Actually", "not"
3. Prioritize if more authoritative (higher p, better classification)

**Example:** Search "Does Ratio own VMT02?"
- S1: "Ratio develops pipelines" (p: 0.85, PRIMARY) - neutral
- S2: "Perspective owns VMT02" (p: 0.95, PRIMARY/N) - relevant but contradicts

**❌ Bad:** "Ratio's VMT02 {{§S1:1.1, 0.85, c:H/P}} is owned by Perspective {{§S2:1.2, 0.95, c:H/P}}"
**✅ Good:** "VMT02 is owned by Perspective {{§S2:1.2, 0.95, c:H/P}}, not Ratio."

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

1. **USE THE SNIPPETS** - Synthesize ONLY from the labeled sources below
2. Cite every factual claim with snippet codes
3. Use only codes that exist in sources (check "Available codes" for each source)
4. Choose citation format based on response length:
   - **Standard:** `{{§S1:1.1, 0.95, c:H/P}} [verbose context]`
   - **Compact (if approaching max words):** `[S1.1.1]` or `[S1.1.1-1.3]` for ranges
5. **Prefer H (high authority) sources** for critical claims

**Checklist:**
- ✓ **Every claim cites a snippet** (no unsourced claims)
- ✓ Codes match those in labeled sources (don't invent)
- ✓ For verbose format: include p, c, and context
- ✓ For compact format: just [S#.#.#] to save space
- ✓ Source prefix included (S1, S2, etc.)
- ✓ Critical claims preferentially cite H sources
- ✓ NO fabricated information - if no snippet supports it, omit it
