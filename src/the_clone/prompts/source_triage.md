# Source Triage – Yield-Oriented, Diversity-Preserving Selection

Query: {query}
Search Term: "{search_term}"

Objective:
Select UP TO {max_sources} sources from the {source_count} results below that are most likely to yield NEW, PRECISELY-AUDITABLE factual snippets that improve the final answer. This is triage, not fact-checking.

Existing Snippets Already Collected:
{formatted_existing_snippets}
Existing snippet count: {existing_snippet_count}

Sources from This Search ({source_count} results):
{formatted_sources}

Selection Guidance (Internal):
Choose sources that are likely to contain short, checkable factual claims not already covered by existing snippets. Prefer sources that naturally produce auditable facts rather than opinion or high-level summaries.

Selection Heuristics (Priority Order):
1) Novelty: Select only sources likely to add new information (different aspects, new numbers/dates/entities, primary or document-like material). Skip sources that likely repeat existing snippets.
2) Independence & Diversity: Prefer independent origins or perspectives. Avoid multiple sources that appear to echo the same underlying material.
3) Auditability Yield: Up-rank primary/official sources, reports, filings, announcements, datasets, or pages with concrete numbers and clear attribution. Down-rank opinion, commentary, listicles, explainers, promotional or persuasive content.
4) Recency (Conditional): If the query is time-sensitive ("latest", "current", "new", "today"), prefer recent sources. Otherwise, do not penalize older authoritative material.
5) Search Position: Use rank as a weak hint only; do not override novelty or independence.

When to Select NOTHING:
Return an empty array if all sources repeat existing snippets, are high-level summaries without extractable facts, are promotional/opinion-only, or are otherwise low-yield.

Output Rules:
Select 0–{max_sources} indices. You are not required to select {max_sources}. Fewer high-yield sources are better than many weak ones.

Output Format (indices only):
{{
  "selected_indices": [0, 3, 7]
}}

Or, if nothing is worth extracting:
{{
  "selected_indices": []
}}
