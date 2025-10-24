# Row Discovery Task

## Your Job

You are charged with **finding new row entries** for a research table that we are going to build.

These rows are characterized by their **ID fields** (identification columns). Your task is to:

1. **Use web search** to find unique entries that match the specified requirements within the specified subdomain. 
2. **Populate ID fields** with actual values from your search results
3. **Score each entry** for relevance, source reliability, and recency
4. **Provide reasoning** for why the entry is a good fit

### Search Tips
1. Exclude youtube and other video results - web results only.
2. Use sources that are likely to yield many results at once. Sites that aggregate the information you are looking for (e.g. indeed for jobs, nyt for news, etc) are great. 
3. When you come up short, iterate until you find something. Use provided search recommendations to get what we need. 
4. Do not fabricate anything. Only use real entities.  
 
---

## Context About This Table (not specifically your task - you are just identifying candidate rows)

**User's Original Request:**
{{USER_CONTEXT}}

**Table Purpose:**
{{TABLE_PURPOSE}}

**Background Research Context:**
{{TABLEWIDE_RESEARCH}}

---

## Your Specific Assignment

**Subdomain:** {{SUBDOMAIN_NAME}}

**Focus Area:** {{SUBDOMAIN_FOCUS}}

**Requirements:** {{SEARCH_REQUIREMENTS}}

**Target:** Find **{{TARGET_ROWS}} unique entries**

---

## Recommended Searches

Make sure to try these search queries to find entries:
{{SEARCH_QUERIES}}

---

## ID Fields to Populate

For each entry you find, populate these ID fields with ACTUAL values from your search:

{{ID_COLUMNS}}

**Example of populated ID fields:**
```json
{
  "Company Name": "Anthropic",
  "Website": "https://anthropic.com"
}
```

**Another example:**
```json
{
  "Company Name": "PathAI",
  "Website": "https://www.pathai.com"
}
```

---

## Scoring Each Entry

Score each entry on three dimensions (0-1.0 scale):

### 1. Relevancy (0-1.0)
How well does this entry match the requirements?
- 1.0 = Perfect match
- 0.7 = Strong match, minor gaps
- 0.4 = Moderate match
- 0.0 = Weak match

### 2. Source Reliability (0-1.0)
How reliable are your information sources?
- 1.0 = Primary sources (official website, Crunchbase, official docs)
- 0.7 = Secondary sources (TechCrunch, LinkedIn, major news outlets)
- 0.4 = Tertiary sources (blogs, forums, aggregators)
- 0.0 = Unreliable or unverified

### 3. Recency (0-1.0)
How recent is the information?
- 1.0 = Less than 3 months old
- 0.7 = 3-6 months old
- 0.4 = 6-12 months old
- 0.0 = More than 12 months or date unknown

---

## Output Format

Return JSON in this exact format:

```json
{
  "subdomain": "{{SUBDOMAIN_NAME}}",
  "candidates": [
    {
      "id_values": {
        "Company Name": "Anthropic",
        "Website": "https://anthropic.com"
      },
      "score_breakdown": {
        "relevancy": 0.95,
        "reliability": 1.0,
        "recency": 0.9
      },
      "match_rationale": "Leading AI safety research company with active hiring for ML engineers",
      "source_urls": [
        "https://anthropic.com/careers",
        "https://www.crunchbase.com/organization/anthropic"
      ]
    }
  ]
}
```

**Requirements:**
- Use EXACT field names from ID fields list above
- Each entry must be UNIQUE (different from other entries)
- Always include all three dimension scores
- Keep rationale to 1-2 sentences
- Include specific source URLs

---

## Important Notes

- **Find real entries:** Don't make up placeholder names or generic examples
- **Use exact field names:** Copy field names exactly as shown in ID fields list
- **Return candidates array:** Even if empty, always return {"candidates": []}
- **No minimum quality:** Include entries that are real even if scores are moderate (we'll filter later) 

{{PREVIOUS_SEARCH_IMPROVEMENTS}}

## If No Matches Found

This is a bad outcome - lower quality results are greatly preferred - as long as they are real. If you cannot provide results of any quality at all, you must explain why. If your searches return 0 candidates, you MUST provide a "no_matches_reason" field explaining why:

```json
{
  "subdomain": "Healthcare AI Companies",
  "no_matches_reason": "Search queries returned general information about healthcare but no specific company matches. Queries may need to be more specific or use different search terms.",
  "search_improvements": [
    "Try more specific queries like 'healthcare AI startups radiology' instead of general 'healthcare AI'",
    "Search for company directories or funding databases rather than news articles"
  ],
  "candidates": []
}
```

**Possible reasons to report:**
- "Search queries too broad/narrow, no specific entity results"
- "Web search returned no relevant results for this subdomain"
- "Queries found general information but no identifiable entities"
- "Technical/niche subdomain with limited public information"

## Search Improvements (Optional)

If you experienced difficulties finding good candidates or had to try multiple search approaches, provide suggestions in the `search_improvements` array. This helps improve results for subsequent subdomains.

**Include search_improvements if:**
- Initial search queries didn't work well and you had to reformulate
- You found better query patterns that could help other subdomains
- Certain search terms or approaches proved more effective than others
- You discovered missing context that would help narrow results

**Examples:**
```json
{
  "subdomain": "News Stories",
  "search_improvements": [
    "Headlines work better than searching for 'story descriptions'",
    "Adding date ranges to queries improves result relevance",
    "Primary news sources are more reliable than aggregators"
  ],
  "candidates": [...]
}
```


This helps us improve search strategies for future subdomains.
Return your findings as valid JSON.
