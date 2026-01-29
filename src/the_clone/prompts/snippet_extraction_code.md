# Extract quotes using codes

Query: {query}
Source: {source_title} ({source_url})
Date: {source_date}
Mode: {extraction_mode_guidance} | Max: {max_snippets} quotes

Search terms (found by #{primary_search_num}):
{all_search_terms_formatted}

---

## Labeled Source

{source_full_text}

---

## Task

Return **codes with backtick prefix** (not full text) for essential quotes.

**Quality gate:** Only extract if quote contains concrete, verifiable factual claims. Skip:
- Vague summaries, speculation, opinion (unless query directly requests this)
- Statements requiring full article to verify
- Info that duplicates what's already known

**Code format:** Use backtick `` ` `` before codes
- `` §1 `` = sentence 1
- `` §1-3 `` = sentences 1-3
- `` §1.w5-7 `` = words 5-7 of sentence 1
- `` [§2.w1-3] §1 `` = pull words 1-3 from s2 as attribution for s1 → `[Dr. Smith] sentence 1`
- `` §1 [of Gemini] `` = add literal context → `sentence 1 [of Gemini]`
- `` [re: Topic] §2 `` = off-topic marker → `[re: Topic] sentence 2`

**Examples:**
```
[1] Results were significant.
[2] Dr. Jane Smith led the study.
```
- Code `` §2 `` → "Dr. Jane Smith led the study."
- Code `` [§2.w1-4] §1 `` → "[Dr. Jane Smith] Results were significant."
- Code `` §1 [from study] `` → "Results were significant [from study]"

---

## Validation

**P-scores** (must use exactly): 0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95

**High (p≥0.85)** - one gate met:
- PRIMARY: official/self-report
- DOCUMENTED: methods/data shown
- ATTRIBUTED: named source + role (must pull attribution via code if separate sentence)

**Low (p≤0.15)**:
- CONTRADICTED, UNSOURCED, PROMOTIONAL, STALE

**Mid**: OK

---

## Output

```json
{{
  "quotes_by_search": {{
    "1": [
      {{"c": "§1", "p": 0.95, "r": "PRIMARY"}},
      {{"c": "[§2.w1-3] §3", "p": 0.85, "r": "ATTRIBUTED"}},
      {{"c": "§4 [of Gemini]", "p": 0.65, "r": "OK"}}
    ]
  }}
}}
```

Return `{{}}` if nothing clear. Extract only concrete, checkable facts.

**⚠️ RESPONSE LENGTH LIMIT: Keep your total response under {word_limit} words.**
