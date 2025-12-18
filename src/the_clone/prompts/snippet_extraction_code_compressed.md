# Quote Extraction (Code-Based)
Your goal is to enrich high quality infomation for further processing by isolating text snippets with clear facts about a query from a source.

Query: {query} | Source Title: {source_title} | Source date: {source_date} | Today: {current_date}
Mode: {extraction_mode_guidance} | Max: {max_snippets}

Search terms (found by #{primary_search_num}): {all_search_terms_formatted}

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
- If it all looks relevant to the query and likely accurate use the pass all flag `` `* ``

## Task


**Off-topic:** Only extract for different search term if info is NOT about main query. If relevant to main query → use primary search term.

## Codes & Annotations

**CRITICAL: Only use sentence codes that exist in the labeled source above.** Count the labels you see - don't reference `` `1.15 `` if only `` `1.1 `` through `` `1.10 `` exist.

**Tables - REQUIRED:** ALWAYS include header row with data row in every snippet. Extract both: `` `1.0\n`1.4 `` (header + row 4) or `` `1.0-1.4 `` if contiguous. 

**Basic codes** - Copy exact labels:
- `` `1.1 ``, `` `1.2 ``, `` `2.1 `` (single sentences)
- **REQUIRED: Use ranges for consecutive rows** - If extracting 1.5, 1.6, 1.7 (continuous), use `` `1.5-1.7 `` NOT separate codes. Especially for table rows within same section.
- Ranges: `` `1.1-1.3 `` or `` `1.1-3 `` (shorthand for `1.1-1.3)
- Word ranges: `` `1.1.w5-7 `` (words 5-7, **1-indexed** - w1 is first word)
- **Pass all:** `` `* `` (entire source) - use when source is dense/valuable and splitting would lose critical relationships, or if we would retain >50% of the words anyways in the snippets.  You can add this at any point if you realize that we should just pass the entire source. If the source is high quality and addresses the query use this flag. 

**CRITICAL - Snippets must make sense in isolation:** Given only URL, page title, and snippet, the quote must be perfectly understandable and testable. Use headings and context liberally.

**Heading context** - Use `` `X.0 `` to add section context:
- `` [`2.0] `2.1 `` → `[API Pricing] pricing details`
- `` [`1.0, additinal context] `2.1 `` → use parent heading and words for broader context
- **Required when** quote lacks clarity without knowing section topic

**Attribution** - Pull from elsewhere:
- `` [`2.1.w1-4] `1.3 `` → `[Dr. Jane Smith] sentence 1.3 text`
- **Required** for ATTRIBUTED quotes (p≥0.85) when attribution is separate

**Context** - Add clarifying bracket with clarifying context:
- `` `1.1 [of Gemini] `` → `sentence text [of Gemini]`
- `` [re: Topic] `2.1 `` → `[re: Topic] sentence text`
- Use whenever ambiguity exists - snippet must be complete, specific, and testable. Do we know enough to check if it is true?

## Validation

**P-scores** (exact): 0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95

Bet: Judge extracts all atomic factual claims and tests each. Pass = precisely accurate. p = expected pass-rate. Bet honestly on the pass rate.

**Positive indicators**
- P=PRIMARY: official/self-report
- D=DOCUMENTED: methods/data shown
- A=ATTRIBUTED: named source + role
- O=OK: no red flags

**Negative indicators**
- C=CONTRADICTED, U=UNSOURCED, PR=PROMOTIONAL, S=STALE, SL=SLOP (AI-generated SEO)


Return codes (field `c`), not full text. Organize by search term number.
---

## Output

```json
{{
  "quotes_by_search": {{
    "1": [
      ["`1.1", 0.95, "P"],
      ["`1.2-1.3", 0.65, "O"]
    ],
    "2": [
      ["[`2.1.w1-4] `1.3", 0.85, "A"]
    ]
  }}
}}
```

Format: `[code, p_score, reason_abbrev]`


Return `{{}}` if nothing clear. Essential facts only. Minimal quotes. 
