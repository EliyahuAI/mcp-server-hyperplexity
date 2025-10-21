You are discovering candidate rows for a research table by analyzing web search results.

## Subdomain Focus
{{SUBDOMAIN}}

## Overall Search Strategy
{{SEARCH_STRATEGY}}

## Table Columns
The table uses these columns (ID columns are used to uniquely identify each row):
{{COLUMNS}}

## Web Search Results
{{WEB_SEARCH_RESULTS}}

## Your Task
Extract candidate entities from the web search results and evaluate each against the table criteria.

### Instructions:
1. **Extract Candidates**: Identify entities mentioned in the web search results that match the subdomain focus
2. **Score Each Candidate**: Assign a match score between 0.0 and 1.0 based on:
   - **Relevance to subdomain** (0.4 weight): How well does this entity fit the subdomain focus?
   - **Information availability** (0.3 weight): Can we find data for the research columns?
   - **Entity quality** (0.3 weight): Is this a significant/notable entity worth including?
3. **Provide Clear Rationale**: Explain why each candidate received its score
4. **Include Source URLs**: List the specific URLs where you found information about each candidate
5. **Quality Over Quantity**: Only include candidates with match scores >= 0.5

### Match Score Guidelines:
- **0.9-1.0**: Perfect match - highly relevant, complete information available, significant entity
- **0.7-0.89**: Strong match - clearly relevant, good information available, notable entity
- **0.5-0.69**: Moderate match - somewhat relevant, limited information, or less notable
- **Below 0.5**: Poor match - don't include in results

### ID Values Format:
For each candidate, populate ONLY the ID columns (columns where `is_identification: true`).
Use the exact column names as keys.

### Example Output Structure:
```json
{
  "subdomain": "AI Research Companies",
  "candidates": [
    {
      "id_values": {
        "Company Name": "Anthropic",
        "Website": "anthropic.com"
      },
      "match_score": 0.95,
      "match_rationale": "Leading AI safety research company with active hiring for ML engineers. Significant presence in search results with clear focus on AI research. Multiple sources confirm hiring activity and research focus.",
      "source_urls": ["https://anthropic.com/careers", "https://techcrunch.com/anthropic-hiring"]
    }
  ]
}
```

## Important Notes:
- Only extract entities that are explicitly mentioned or clearly referenced in the web search results
- Don't fabricate or infer entities not supported by the search results
- If web search results are empty or unhelpful, return an empty candidates array
- Ensure ID values are clean strings (no extra formatting, URLs, etc.)
- Source URLs should be specific to each candidate (not generic search URLs)
