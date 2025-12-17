# Source Triage - Diversity-Focused Selection

**Query:** {query}

**Search Term:** "{search_term}"

**Your Task:** Select UP TO {max_sources} sources from the {source_count} results below that will **ADD NEW, INDEPENDENT information** beyond what we already have.

---

## Existing Snippets Already Collected

{formatted_existing_snippets}

**Count:** {existing_snippet_count} snippets

---

## Sources from This Search ({source_count} results)

{formatted_sources}

---

## Selection Criteria

Evaluate each source based on:

1. **Recency:**
   - **Prioritize recent sources** (newer dates are strongly preferred)
   - Recent information is more accurate and relevant
   - Date shown in source metadata

2. **Quality:**
   - Position in search results (lower index = more relevant)
   - Source authority and reliability
   - Content preview quality

3. **Novelty:**
   - Does this add NEW information not in existing snippets?
   - Avoid sources that duplicate what we already have

4. **Diversity:**
   - Select sources that cover INDEPENDENT aspects
   - Don't select 3 sources that all say the same thing
   - Prefer sources that each add a unique piece of information

5. **Value:**
   - Will extracting from this source meaningfully improve our answer?
   - Skip sources with marginal/redundant value

---

## Output Rules

**Select 0-3 source indices:**
- **3 sources:** If you find 3 high-quality sources each adding unique information
- **1-2 sources:** If only some sources add value
- **0 sources (empty array):** If NOTHING in these results adds new information

**Important:**
- Return indices only (e.g., [0, 2, 5])
- You are NOT required to select {max_sources} sources
- Empty array is a valid response if nothing is worth extracting
- Prioritize quality and diversity over quantity

---

## Examples

**Good Selection (Diverse):**
```json
{{
  "selected_indices": [0, 3, 7],
  "reasoning": "Source 0 covers architecture, 3 covers performance, 7 covers pricing - all independent"
}}
```

**Good Selection (Partial):**
```json
{{
  "selected_indices": [1],
  "reasoning": "Only source 1 adds new benchmark data, others duplicate existing info"
}}
```

**Good Selection (Empty):**
```json
{{
  "selected_indices": [],
  "reasoning": "All sources cover information already in existing snippets"
}}
```

**Bad Selection (Not Diverse):**
```json
{{
  "selected_indices": [0, 1, 2],
  "reasoning": "All three say the same thing about architecture"
}}
```

---

**Return selected_indices array with 0-3 source indices that maximize information gain.**
