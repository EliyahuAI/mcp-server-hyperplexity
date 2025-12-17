# Essential Quote Extraction with Off-Topic Detection

**Main Query:** {query}

**Source:** {source_title}
**URL:** {source_url}
**Reliability:** {source_reliability}

---

## All Search Terms

This source was found by **Search {primary_search_num}**, but it may contain information for OTHER search terms:

{all_search_terms_formatted}

---

## Source Text

{source_full_text}

---

## Your Task

Extract **essential quotes** from this source, organized by which search term they address.

### Off-Topic Detection

**IMPORTANT:** Only extract quotes for a DIFFERENT search term if the information is genuinely NOT about the main query topic.

- **Main Query:** {query}
- **If a quote IS relevant to the main query**, extract it for the PRIMARY search term (Search {primary_search_num})
- **Only use other search terms** if the quote is about a DIFFERENT topic that doesn't directly answer the main query

**Example:**
- Main Query: "What are the key features of Gemini 2.0 Flash?"
- Search 1: "Gemini 2.0 Flash features"
- Search 2: "GPT-4 features"

A quote like "Gemini 2.0 Flash has 1M token context" should go to Search 1 (directly relevant to main query)
A quote like "GPT-4 has 128K context" should go to Search 2 (different model, off-topic)

### Extraction Rules

1. **Essential quotes only** - Must directly help answer the query
2. **Return empty if no clear quotes** - Don't force extraction
3. **Exact quotes** - Word-for-word from source
4. **Brackets for orientation** - [of DeepSeek V3], [in 2024] to add context
5. **Use "..." for omissions** - Skip non-essential text
6. **Keep it minimal** - 1-5 quotes maximum (not 10+)
7. **Avoid false off-topic marks** - Don't mark quotes as off-topic if they're relevant to main query

### When to Return Empty

Return `quotes: []` (empty array) if:
- Source doesn't directly address the query
- Information is vague or speculative
- Content duplicates what's already known
- No clear, quotable facts

### Output Format

```json
{{
  "quotes_by_search": {{
    "1": ["Quote for search term 1", "Another quote for term 1"],
    "2": ["Off-topic quote for search term 2"],
    "3": []
  }}
}}
```

Or if nothing essential:

```json
{{
  "quotes_by_search": {{}}
}}
```

---

## Examples

**Good (Primary + Off-topic):**
```json
{{
  "quotes_by_search": {{
    "1": [
      "Claude Opus 4 uses hybrid architecture with two modes",
      "Supports 200K context window"
    ],
    "2": [
      "GPT-4.5 has 12.8T parameters"
    ]
  }}
}}
```

**Good (Primary only):**
```json
{{
  "quotes_by_search": {{
    "3": [
      "DeepSeek V3 uses MoE architecture with 671B parameters",
      "Achieves 85.2% on MMLU"
    ]
  }}
}}
```

**Good (Nothing Essential):**
```json
{{
  "quotes_by_search": {{}}
}}
```

**Bad (Too much):**
```json
{{
  "quotes": [
    "DeepSeek is an AI model",
    "It was developed by researchers",
    "The model performs various tasks",
    "Some users like it",
    "It has capabilities",
    ... (10 more vague quotes)
  ],
  "has_quotes": true
}}
```

---

**Extract minimal essential quotes or return empty. Quality over quantity.**
