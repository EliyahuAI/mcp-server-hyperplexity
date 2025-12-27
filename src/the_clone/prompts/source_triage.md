# Source Triage – Rank Sources by Yield Potential

Query: {query}
Search Term: "{search_term}"

Rank RELEVANT sources from best to worst. Exclude off-topic sources entirely.

{keyword_info}

Existing Snippets: {existing_snippet_count} collected
{formatted_existing_snippets}

---

## Sources ({source_count} results)

{formatted_sources}

---

## Ranking Criteria

1) **Relevance Score** - Higher score = better search rank + more keyword matches
   - Negative keyword match is a strong signal of irrelevant/low-quality content
2) **Authority** - Prioritize official docs, academic sources, established institutions
3) **Novelty** - Prefer sources adding NEW information not in existing snippets
4) **Recency** - For volatile/time-sensitive info ("latest", "current", recent events), prefer recent sources

---

## Output

Return ranked indices of RELEVANT sources only: `[best, second_best, ...]`

Example: `[5, 0, 8, 2]` means source 5 is best, others excluded as off-topic.
