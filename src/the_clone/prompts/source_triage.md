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

{relevance_scores}

Ranking Criteria (Priority Order):
1) Relevance Score: Consider the algorithmic relevance score based on search rank + keyword matches
   - Higher scores indicate better rank AND presence of desired technical/topical keywords
   - Negative keyword matches (if any) are a strong signal of irrelevant/low-quality content
2) Relevance: EXCLUDE sources that are off-topic or don't address the query
3) Authority: Assess source authority for the query topic
   - AU (Authoritative): High general authority + known topic expertise → prioritize
   - UK (Unknown): Unclear/medium authority → neutral
   - LA (Low Authority): Low general authority or lacks topic expertise → deprioritize
4) Quality Codes: Sources will be coded during extraction. Seek sources likely to yield:
   - GOOD codes: P (Primary/official), D (Documented), A (Attributed), O (OK/reliable)
   - AVOID sources likely to yield: C (Contradicted), U (Unsourced), PR (Promotional), S (Stale), SL (SEO slop)
5) Novelty: Prioritize sources likely to add NEW information not in existing snippets
6) Independence: Prefer diverse origins, avoid echo chambers
7) Recency: For time-sensitive queries ("latest", "current"), prefer recent sources

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
