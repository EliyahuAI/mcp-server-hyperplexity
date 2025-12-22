# Batch Quote Extraction (Code-Based)

## Purpose
Detect and enrich reliable information into quotable snippets with sufficient context for synthesis.

**CRITICAL:** Synthesis will NOT have access to original sources - only these snippets. Each snippet must be:
1. **Self-contained** - Understandable without the original source
2. **Enriched with context** - Include necessary background in [brackets]
3. **Directly quotable** - Ready for citation in final answer

**When enrichment not possible:** If source is dense/interconnected where splitting loses meaning, use pass-all flag `` `SX:* `` (X=source num).

---

Search Focus: Multiple sources | Today: {current_date}
Mode: {extraction_mode_guidance} | Max: {max_snippets} per source

Search terms: {all_search_terms_formatted}

---

## Labeled Sources

Sentences end with `` `SX:Y.Z `` labels where X=source number. Headings end with `` `SX:Y.0 ``. Copy these exact labels in your codes.

{formatted_sources}

---

## Gate

Extract only if quote has concrete, verifiable facts. Skip:
- Vague summaries, speculation, opinion (unless query asks for it)
- Statements needing full article to verify
- **AI-generated SEO slop** (generic filler, keyword stuffing, low-info content) → tag with p=0.05, reason=SL (SLOP)
- If entire source looks relevant to query and likely accurate use pass all flag `` `SX:* `` (X=source num)

## Task

Extract quotes from each source using **source-prefixed codes**.

**Off-topic:** Only extract for different search term if info is NOT about main query. If relevant to main query → use primary search term.

## Codes & Annotations

**CRITICAL: Only use sentence codes that exist in the labeled sources above.** Don't reference `` `S1:1.15 `` if only `` `S1:1.1 `` through `` `S1:1.10 `` exist.

**Tables - CRITICAL GROUPING RULE:**
- **ONE snippet per table** (or per meaningful table section if very large)
- ALWAYS include header row: `` `S1:H5.0-5.7 `` = header + rows 1-7 as SINGLE snippet
- NEVER split rows from same table into separate snippets
- Use ranges to group: `` `S1:H5.0-5.3 `` (header + rows 1-3) NOT separate `` `S1:H5.0 ``, `` `S1:H5.1 ``, etc.

**Basic codes** - Copy exact labels with source prefix:
- `` `S1:1.1 ``, `` `S2:2.1 `` (single sentences - use for non-table content)
- **REQUIRED: Use ranges for consecutive content** - `` `S1:1.5-1.7 `` NOT separate codes
- Ranges: `` `S1:1.1-1.3 `` or `` `S1:1.1-3 `` (shorthand)
- Word ranges: `` `S2:1.1.w5-7 `` (words 5-7, **1-indexed** - w1 is first word)
- **Pass all:** `` `S1:* `` (entire source 1) - use when source is dense/valuable and splitting would lose critical relationships, or if we would retain >50% of words in snippets. If source is high quality and addresses query use this flag.

**CRITICAL - Snippets must make sense in isolation:**
Synthesis has NO access to original sources. Given only URL, page title, and this snippet, it must be perfectly understandable and testable.

**Structure: [SHORT CONTEXT] + DIRECT FACT**
- Context in brackets: MAX 10 words, replace messy/long context with clean summary
- Fact: ALWAYS direct extract from source, never paraphrase
- Goal: Create self-contained snippets ready for synthesis WITHOUT needing the original source

**Heading context** - Use `` `SX:Y.0 `` to add section context:
- `` [`S1:2.0] `S1:2.1 `` → `[API Pricing] pricing details`
- `` [`S2:1.0, Q3 2024] `S2:2.1 `` → use parent heading + brief context (≤10 words)
- **Required when** quote lacks clarity without knowing section topic

**Attribution** - Pull from elsewhere:
- `` [`S1:2.1.w1-4] `S1:1.3 `` → `[Dr. Jane Smith] sentence 1.3 text`
- **REQUIRED** for ATTRIBUTED quotes (p≥0.85, reason=A) when attribution is separate
- **CRITICAL:** The attribution (name + role) MUST appear in the final snippet text in brackets
- Keep attributions concise (≤10 words in brackets)
- Example: Don't just mark as "A" - actually include `[Dr. Smith, MIT researcher]` in the snippet

**Context clarification** - Add SHORT clarifying brackets:
- `` `S1:1.1 [of Gemini] `` → `sentence text [of Gemini]`
- `` [re: GPU performance] `S2:2.1 `` → `[re: GPU performance] sentence text`
- Context must be ≤10 words - replace long/messy with clean summary
- Use whenever ambiguity exists - snippet must be complete, specific, and testable

## Validation

**Source Authority** - Assess BEFORE betting:
- **AU** (Authoritative): High general authority + known expertise on query topic
- **UK** (Unknown): Unclear authority or medium general authority
- **LA** (Low Authority): Low general authority or lacks topic expertise

**P-scores** (exact): 0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95

Bet: Judge extracts all atomic factual claims and tests each. Pass = precisely accurate. p = expected pass-rate. Consider source authority (AU/UK/LA) when betting - higher authority → higher confidence in same claim.

**Positive indicators**
- P=PRIMARY: official self-report / primary-document style
- D=DOCUMENTED: methods/data shown/peer reviewed
- A=ATTRIBUTED: believable named source + role (MUST pull attribution into snippet text using brackets)
- O=OK: no red flags, aligns with your knowledge

**CRITICAL for ATTRIBUTED (A):** The actual attribution MUST be in the snippet text!
- ❌ WRONG: Just marking reason=A without including attribution
- ✅ CORRECT: `["[`S1:2.1.w1-4] `S1:1.3", 0.85, "A"]` → Final text includes "[Dr. Jane Smith, MIT] fact text"

**Negative indicators**
- C=CONTRADICTED: You know otherwise / internally inconsistent
- U=UNSOURCED: Just statements
- PR=PROMOTIONAL: Clear bias
- S=STALE: Out of date dynamic information
- SL=SLOP: AI-generated SEO

Return codes (not full text). Organize by source ID, then by search term.

---

## Output

```json
{{
  "quotes_by_source": {{
    "S1": {{
      "1": [
        ["`S1:1.1", 0.95, "P", "mortgage_rate_dec2025"],
        ["`S1:H5.0-5.3", 0.85, "D", "efficiency_table"],
        ["[`S1:2.0] `S1:2.5", 0.65, "O", "solar_residential_only"]
      ],
      "2": []
    }},
    "S2": {{
      "1": [
        ["[`S2:3.1.w1-4] `S2:3.5", 0.85, "A", "wind_capacity_2024"]
      ],
      "2": []
    }}
  }}
}}
```

Format: `[source_prefixed_code, p_score, reason_abbrev, verbal_handle]`

**Verbal Handle Requirements:**

**Format:** `source_detail_limits`
- Sections separated by underscore `_`
- Within sections use hyphens `-`

**Parts:**
- **source** (1 word): Source attribution (pubmed, nih, harvard, freddie, bankrate, healthline, etc.)
- **detail** (1-2 words, hyphenated): Specific reason WHY this snippet chosen (weight-loss, insulin-sensitivity, mortgage-rate, metabolic-switch, etc.)
- **limits** (1-2 words, hyphenated): Qualifications/scope (dec-2025, fasting-only, 8wk-study, post-2020, adf-protocol, etc.)

**Examples:**
- `freddie_mortgage-rate_dec-2025` - Freddie Mac rate, Dec 2025 specific
- `pubmed_weight-loss_if-vs-cer` - PubMed weight loss, IF vs CER comparison
- `nih_insulin-sensitivity_tre-protocol` - NIH insulin sensitivity, TRE protocol
- `harvard_metabolic-switch_12hr-fast` - Harvard metabolic switch, 12-hour fasting

**CRITICAL:**
- **MUST be unique** - if duplicate, append _2, _3
- All three parts required
- Max 30 chars total

**Code Examples:**
- `` `S1:1.1 `` = single sentence from source 1 (non-table content)
- `` `S1:H5.0-5.3 `` = table header + rows 1-3 as ONE snippet (all rows from same table grouped)
- `` [`S1:2.0] `S1:2.5 `` = section heading as context + fact
- `` [`S2:3.1.w1-4] `S2:3.5 `` = attribution from elsewhere + fact

**Table Extraction Examples:**
- ❌ WRONG: Separate snippets for rows: `` `S1:H5.0 ``, `` `S1:H5.1 ``, `` `S1:H5.2 ``
- ✅ CORRECT: Single snippet for table: `` `S1:H5.0-5.7 `` (header + all relevant rows)

Return empty objects `{{}}` if nothing clear. Essential facts only. Minimal quotes.
