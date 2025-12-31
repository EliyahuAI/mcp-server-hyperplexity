# Quote Extraction (Code-Based)

## Purpose
Detect and enrich reliable information into quotable snippets with sufficient context for synthesis.

**CRITICAL:** Synthesis will NOT have access to original sources - only these snippets. Each snippet must be:
1. **Self-contained** - Understandable without the original source
2. **Enriched with context** - Include necessary background in [brackets]
3. **Directly quotable** - Ready for citation in final answer

**When enrichment not possible:** If source is dense/interconnected where splitting loses meaning, use pass-all flag `` §* ``.

---

Search Focus: {primary_search_term} | Source: {source_title} | Date: {source_date} | Today: {current_date}
Mode: {extraction_mode_guidance} | Max: {max_snippets}

All search terms (found by #{primary_search_num}): {all_search_terms_formatted}

---

## Labeled Source

Sentences end with `` `X.Y `` labels. Headings end with `` `X.0 ``. Copy these exact labels in your codes.

{source_full_text}

---

## Gate

Extract only if quote has concrete, verifiable facts. Skip:
- Vague summaries, speculation, opinion (unless query asks for it)
- Statements needing full article to verify
- **AI-generated SEO slop** (generic filler, keyword stuffing, low-info content) → tag with p=0.05, reason=SL (SLOP)
- If it all looks relevant to the query and likely accurate use the pass all flag `` §* ``

## Task


**Off-topic:** Only extract for different search term if info is NOT about main query. If relevant to main query → use primary search term.

## Codes & Annotations

**CRITICAL: Only use sentence codes that exist in the labeled source above.** Count the labels you see - don't reference `` §1.15 `` if only `` §1.1 `` through `` §1.10 `` exist.

**Tables - CRITICAL GROUPING RULE:**
- **ONE snippet per table** (or per meaningful table section if very large)
- ALWAYS include header row: `` §H5.0-5.7 `` = header + rows 1-7 as SINGLE snippet
- NEVER split rows from same table into separate snippets
- Use ranges to group: `` §H5.0-5.3 `` (header + rows 1-3) NOT separate `` §H5.0 ``, `` §H5.1 ``, etc.

**Basic codes** - Copy exact labels:
- `` §1.1 ``, `` §1.2 ``, `` §2.1 `` (single sentences - use for non-table content)
- **REQUIRED: Use ranges for consecutive content** - `` §1.5-1.7 `` NOT separate codes
- Ranges: `` §1.1-1.3 `` or `` §1.1-3 `` (shorthand for §1.1-1.3)
- Word ranges: `` §1.1.w5-7 `` (words 5-7, **1-indexed** - w1 is first word)
- **Pass all:** `` §* `` (entire source) - use when source is dense/valuable and splitting would lose critical relationships, or if we would retain >50% of the words anyways in the snippets.  You can add this at any point if you realize that we should just pass the entire source. If the source is high quality and addresses the query use this flag. 

**CRITICAL - Snippets must make sense in isolation:**
Synthesis has NO access to original sources. Given only URL, page title, and this snippet, it must be perfectly understandable and testable.

**Structure: [SHORT CONTEXT] + DIRECT FACT**
- Context in brackets: MAX 10 words, replace messy/long context with clean summary
- Fact: ALWAYS direct extract from source, never paraphrase
- Goal: Create self-contained snippets ready for synthesis WITHOUT needing the original source

**Heading context** - Use `` `X.0 `` to add section context:
- `` [§2.0] §2.1 `` → `[API Pricing] pricing details`
- `` [§1.0, Q3 2024] §2.1 `` → use parent heading + brief context (≤10 words)
- **Required when** quote lacks clarity without knowing section topic

**Attribution** - Pull from elsewhere:
- `` [§2.1.w1-4] §1.3 `` → `[Dr. Jane Smith] sentence 1.3 text`
- **REQUIRED** for ATTRIBUTED quotes (p≥0.85, reason=A) when attribution is separate
- **CRITICAL:** The attribution (name + role) MUST appear in the final snippet text in brackets
- Keep attributions concise (≤10 words in brackets)
- Example: Don't just mark as "A" - actually include `[Dr. Smith, MIT researcher]` in the snippet

**Context clarification** - Add SHORT clarifying brackets:
- `` §1.1 [of Gemini] `` → `sentence text [of Gemini]`
- `` [re: GPU performance] §2.1 `` → `[re: GPU performance] sentence text`
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
- ✅ CORRECT: `["[Dr. Jane Smith, MIT] §1.3", 0.85, "A"]` → Final text includes "[Dr. Jane Smith, MIT] fact text"

**Negative indicators**
- C=CONTRADICTED: You know otherwise / internally incosistent
- U=UNSOURCED: Just statements
- PR=PROMOTIONAL: Clear bias
- S=STALE: Out of date dynamic information
- SL=SLOP: AI-generated SEO (be wary of perfect markdown on a random page)

Return codes (field `c`), not full text. Organize by search term number.
---

## Output

```json
{{
  "quotes_by_search": {{
    "1": [
      ["§1.1", 0.95, "P", "mortgage_rate_dec2025"],
      ["§H5.0-5.3", 0.85, "D", "efficiency_table"],
      ["[§2.0] §2.5", 0.65, "O", "solar_residential_only"]
    ],
    "2": [
      ["[§3.1.w1-4] §3.5", 0.85, "A", "wind_capacity_2024"]
    ]
  }}
}}
```

Format: `[code, p_score, reason_abbrev, verbal_handle]`

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
- `` §1.1 `` = single sentence (non-table content)
- `` §H5.0-5.3 `` = table header + rows 1-3 as ONE snippet (all rows from same table grouped)
- `` [§2.0] §2.5 `` = section heading as context + fact
- `` [§3.1.w1-4] §3.5 `` = attribution from elsewhere + fact

**Table Extraction Examples:**
- ❌ WRONG: Separate snippets for rows: `` §H5.0 ``, `` §H5.1 ``, `` §H5.2 ``
- ✅ CORRECT: Single snippet for table: `` §H5.0-5.7 `` (header + all relevant rows)

Return `{{}}` if nothing clear. Essential facts only. Minimal quotes. 
