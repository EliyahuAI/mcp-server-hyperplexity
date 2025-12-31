# Essential Quote Extraction with Precision Betting

**Main Query:** {query}

**Source:** {source_title}
**URL:** {source_url}
**Date:** {source_date}

**Extraction Mode:** {extraction_mode_guidance}
**Max Snippets:** Extract up to {max_snippets} quotes maximum from this source.

---

## All Search Terms

This source was found by **Search {primary_search_num}**, but it may contain information for OTHER search terms:

{all_search_terms_formatted}

---

## Labeled Source

The source text below has been labeled with backtick suffixes (`X.Y) at the end of each sentence:
- Headings end with `X.0 (e.g., §1.0, §2.0)
- Sentences end with `X.Y (e.g., §1.1, §1.2, §2.1)
- All original text, markdown, and formatting is preserved

{source_full_text}

---

## Pre-Extraction Gate (Internal)

Before extracting any quote, ask:

> **"Could a judge, using only the query, URL, date, and this snippet, reasonably decide whether all factual claims in it are precisely accurate?"**

If **NO**, do **not** extract the quote.

In particular, **do not extract**:

* high-level summaries without concrete facts
* speculative or hedged statements without attribution
* opinion or analysis without checkable claims (unless query directly requests opinions)
* statements that require reading the full article to verify

If no snippet passes this gate, return an empty result.

---

## Your Task

Extract **essential quotes** from this source, organized by which search term they address.

### Off-Topic Detection

**IMPORTANT:** Only extract quotes for a DIFFERENT search term if the information is genuinely NOT about the main query topic.

* **Main Query:** {query}
* **If a quote IS relevant to the main query**, extract it for the PRIMARY search term (Search {primary_search_num})
* **Only use other search terms** if the quote is about a DIFFERENT topic that does not directly answer the main query

**Example:**

* Main Query: *"What are the key features of Gemini 2.0 Flash?"*
* Search 1: *"Gemini 2.0 Flash features"*
* Search 2: *"GPT-4 features"*

A quote like *"Gemini 2.0 Flash has a 1M token context window"* → Search 1
A quote like *"GPT-4 supports 128K context"* → Search 2

If a quote partially overlaps the main query but does **not** add new factual information, treat it as relevant but **do not extract it**.

---

## Extraction Rules

1. **Essential quotes only**
   Must contain **concrete, checkable factual claims** that help answer the query.

2. **Return empty if no clear quotes**
   Do not force extraction.

3. **Exact quotes only**
   Word-for-word from the source.

4. **Brackets for orientation**
   Use brackets only to clarify context:
   `[of DeepSeek V3]`, `[in 2024]`

5. **Use "…" for omissions**
   Skip non-essential text.

6. **Keep it minimal**
   1–5 quotes maximum total.

7. **Avoid false off-topic marking**
   Do not mark quotes as off-topic if they directly address the main query.

---

## When to Return Empty

Return:

```json
{{"quotes_by_search": {{}}}}
```

if:

* the source does not directly address the query
* information is vague, speculative, or opinion-only
* content duplicates what is already known
* no snippet passes the Pre-Extraction Gate

---

## Quality Assessment (Precision Betting System)

**For EACH extracted quote, place a bet using only:**
**query, URL, date, snippet**

### Bet Definition

An all knowing judgee will extract up to **K = 2 query-relevant atomic factual claims** from the snippet.

The snippet **PASSes** iff **all extracted claims** are **precisely accurate as stated**
(entity, date, quantity, scope).
Any material error or overstatement = FAIL.

You must output:

> **p = expected pass-rate over many similar (query, URL, date, snippet) items**

---

### Hard Rules

* If **internal contradiction**, **promotional tone**, **anonymous sourcing**, or **stale vs query intent**
  → `p = 0.05–0.10`
  → reason ∈ `{{CONTRADICTED, PROMOTIONAL, ANONYMOUS, STALE}}`

* `p ≥ 0.85` **only if one gate is met**:

  * **PRIMARY**: official self-report / primary-document style
  * **DOCUMENTED**: methods, data, denominators, or record excerpts
  * **ATTRIBUTED**: named accountable source + role + specifics
    → Include attribution IN the quote text itself (e.g., "[Dr. Jane Smith, Chief Scientist, stated that] ...", or with the explicit reference in brackets at the end)

* Choose **p from exactly**:

  ```
  {{0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95}}
  ```

  No other values.

### Reason Keywords

* If `p ≥ 0.85` → `PRIMARY`, `DOCUMENTED`, or `ATTRIBUTED`
* If `p ≤ 0.15` → `CONTRADICTED`, `UNSOURCED`, `ANONYMOUS`, `PROMOTIONAL`, or §STALE`
* Else → `OK`

> **Do not extract a quote unless you are willing to place a non-trivial bet on its precise accuracy.**

---

## Output Format

**Return codes (field `c`) matching the backtick labels in the source above.**

Copy exact labels: `` §1.1 ``, `` §1.2 ``, `` §2.1 ``, etc.
Ranges: `` §1.1-1.3 `` or `` §1.1-3 ``
Attribution: `` [§2.w1-4] §1.1 ``
Context: `` §1.1 [of X] ``

**Must include section.sentence (`` §1.1 `` NOT `` §1 ``). Only use labels that exist.**

```json
{{
  "quotes_by_search": {{
    "1": [
      {{"c": "§1.1", "p": 0.95, "r": "PRIMARY"}},
      {{"c": "§1.2-1.3", "p": 0.65, "r": "OK"}}
    ],
    "2": [
      {{"c": "[§2.1.w1-4] §1.3", "p": 0.85, "r": "ATTRIBUTED"}}
    ]
  }}
}}
```

**Note:** Field names are `c` (code), `p` (probability), `r` (reason) for compactness.

Or, if nothing essential:

```json
{{
  "quotes_by_search": {{}}
}}
```

---

**Extract minimal, auditable quotes only.
Precision over coverage. Bet honestly.**
