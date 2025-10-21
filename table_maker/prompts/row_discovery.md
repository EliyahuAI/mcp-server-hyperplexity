# Row Discovery Task

## Your Job

You are charged with **finding new row entries** for a research table that we are going to build.

These rows are characterized by their **ID fields** (identification columns). Your task is to:

1. **Use web search** to find unique entries that match the specified requirements within the specified subdomain
2. **Populate ID fields** with actual values from your search results
3. **Score each entry** for relevance, source reliability, and recency
4. **Provide reasoning** for why the entry is a good fit

---

## Context About This Table

**User's Original Request:**
{{USER_CONTEXT}}

**Table Purpose:**
{{TABLE_PURPOSE}}

---

## Your Specific Assignment

**Subdomain:** {{SUBDOMAIN_NAME}}

**Focus Area:** {{SUBDOMAIN_FOCUS}}

**Requirements:** {{SEARCH_REQUIREMENTS}}

**Target:** Find **{{TARGET_ROWS}} unique entries**

---

## Recommended Searches

Use these search queries to find entries:
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
- Populate with ACTUAL values from your web search results
- Each entry must be UNIQUE (different from other entries)
- Always include all three dimension scores
- Keep rationale to 1-2 sentences
- Include specific source URLs

---

## Important Notes

- **Find real entries:** Don't make up placeholder names or generic examples
- **Use exact field names:** Copy field names exactly as shown in ID fields list
- **Return candidates array:** Even if empty, always return {"candidates": []}
- **No minimum quality:** Include entries even if scores are moderate (we'll filter later)

Return your findings as valid JSON.
