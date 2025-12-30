# Memory Recall – Select Relevant Sources from Past Searches

**Current Query:** {query}

**Past Queries ({num_queries} candidates):**

{formatted_queries}

---

## Task

Select up to {max_select} most relevant sources that would help answer the current query.

Return as JSON with structure:
```json
{
  "selected_sources": [
    {"query_index": 0, "source_index": 2},
    {"query_index": 1, "source_index": 0},
    ...
  ],
  "reasoning": "Brief explanation of why these sources were selected"
}
```

---

## Selection Criteria

1. **Query Similarity** - Does the past query address the same topic/intent as the current query?
2. **Source Relevance** - Does the source contain useful, substantive information for answering the current query?
3. **Recency** - For time-sensitive topics, prefer newer sources (check query_date and source date)
4. **Diversity** - Avoid redundant sources that cover the same information
5. **Authority** - Prefer authoritative sources when available

---

## Notes

- Each source is identified by (query_index, source_index) pair
- You can select multiple sources from the same query if they're all relevant
- It's okay to select fewer than {max_select} sources if only a few are truly relevant
- Consider both the original query context AND the source content itself
