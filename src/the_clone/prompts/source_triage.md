# Source Triage – Rank ALL Sources by Yield Potential

Query: {query}
Search Term: "{search_term}"

Objective:
Rank RELEVANT sources from best to worst. Exclude off-topic sources entirely.

Existing Snippets Already Collected:
{formatted_existing_snippets}
Existing snippet count: {existing_snippet_count}

Sources from This Search ({source_count} results):
{formatted_sources}

Ranking Criteria (Priority Order):
1) Relevance: EXCLUDE sources that are off-topic or don't address the query
2) Novelty: Prioritize sources likely to add NEW information not in existing snippets
3) Auditability: Prefer primary/official sources, reports, data over opinion/commentary
4) Independence: Prefer diverse origins, avoid echo chambers
5) Recency: For time-sensitive queries ("latest", "current"), prefer recent sources

Output:
Rank ONLY RELEVANT sources from best to worst. Exclude off-topic sources.

Example - If 10 sources but only [0,2,5,7,8] are relevant:
{{
  "ranked_indices": [5, 0, 8, 2, 7]
}}
(Source 5 is best, sources 1,3,4,6,9 excluded as off-topic)

If ALL sources are relevant:
{{
  "ranked_indices": [5, 0, 8, 2, 7, 1, 9, 3, 4, 6]
}}

If NO sources are relevant:
{{
  "ranked_indices": []
}}

Return ranked list of RELEVANT sources only.
