# Quote Extraction (Code-Based)

Query: {query} | Source: {source_title} | Source date: {source_date} | Today: {current_date}
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

## Task

Return codes (field `c`), not full text. Organize by search term number.

**Off-topic:** Only extract for different search term if info is NOT about main query. If relevant to main query → use primary search term.

## Codes & Annotations

**CRITICAL: Only use sentence codes that exist in the labeled source above.** Count the labels you see - don't reference `` `1.15 `` if only `` `1.1 `` through `` `1.10 `` exist.

**Tables:** Extract header row + data row. Use multiple codes or range: `` `1.1 `1.4 `` or `` `1.1-1.4 ``. Include newline if not contiguous.

**Basic codes** - Copy exact labels:
- `` `1.1 ``, `` `1.2 ``, `` `2.1 ``
- Ranges: `` `1.1-1.3 `` (only if all sentences exist)

**Heading context** - Use `` `X.0 `` (heading) only if necessary for clarity:
- `` [`2.0] `2.1 `` → `[API Pricing] pricing details`
- Can use parent heading: `` [`1.0] `2.1 `` if broader context is clearer
- Only add if quote needs context - skip if self-evident

**Attribution** - Pull from elsewhere:
- `` [`2.1.w1-4] `1.3 `` → `[Dr. Jane Smith] sentence 1.3 text`
- Required for ATTRIBUTED quotes (p≥0.85) when attribution is separate

**Context** - Add literal brackets:
- `` `1.1 [of Gemini] `` → `sentence text [of Gemini]`
- `` [re: Topic] `2.1 `` → `[re: Topic] sentence text`

## Validation

**P-scores** (exact): 0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95

Bet: Judge extracts K=2 atomic factual claims. Pass = all precisely accurate. p = expected pass-rate.

**High (p≥0.85)** if one gate met:
- PRIMARY: official/self-report
- DOCUMENTED: methods/data shown
- ATTRIBUTED: named source + role

**Low (p≤0.15):**
- CONTRADICTED, UNSOURCED, PROMOTIONAL, STALE, SLOP (AI-generated SEO)

Else: OK

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
Reasons: P=PRIMARY, D=DOCUMENTED, A=ATTRIBUTED, O=OK, C=CONTRADICTED, U=UNSOURCED, N=ANONYMOUS, PR=PROMOTIONAL, S=STALE, SL=SLOP

Return `{{}}` if nothing clear. Essential facts only. Minimal quotes. Bet honestly.
