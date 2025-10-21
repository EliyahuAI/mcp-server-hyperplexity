# Row Discovery Task

## What You're Doing

Find and score entities that match the criteria for this table subdomain.

## Subdomain

**Name:** {{SUBDOMAIN_NAME}}
**Focus:** {{SUBDOMAIN_FOCUS}}

## Requirements

{{SEARCH_REQUIREMENTS}}

## Search Queries

Use these queries to find entities:
{{SEARCH_QUERIES}}

## Target

Find **{{TARGET_ROWS}} entities** that best match the requirements.

---

## Output Format

For each entity found, populate:

### ID Columns (Use EXACT names)
{{ID_COLUMNS}}

**Example:**
```json
{
  "id_values": {
    "Company Name": "Anthropic",
    "Website": "https://anthropic.com"
  }
}
```

### Scoring (Three Dimensions)

Score each entity on three dimensions (0-1.0 scale):

**1. Relevancy (0-1.0):** How well does it match the requirements?
- 1.0 = Perfect match
- 0.7 = Strong match, minor gaps
- 0.4 = Moderate match
- 0.0 = Weak match

**2. Source Reliability (0-1.0):** How reliable are your sources?
- 1.0 = Primary (company site, Crunchbase, official)
- 0.7 = Secondary (TechCrunch, LinkedIn, major news)
- 0.4 = Tertiary (blogs, forums)
- 0.0 = Unreliable

**3. Recency (0-1.0):** How recent is the information?
- 1.0 = <3 months old
- 0.7 = 3-6 months old
- 0.4 = 6-12 months old
- 0.0 = >12 months or unknown

### Required Output

For each entity, provide:
```json
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
  "match_rationale": "One sentence explaining why this entity matches (or doesn't match perfectly)",
  "source_urls": ["https://source1.com", "https://source2.com"]
}
```

**Notes:**
- Use EXACT field names from ID columns list
- Provide all three dimension scores
- Include specific source URLs
- Keep rationale concise (1 sentence)
- Return top {{TARGET_ROWS}} entities

---

## Return Format

```json
{
  "subdomain": "{{SUBDOMAIN_NAME}}",
  "candidates": [
    {
      "id_values": {...},
      "score_breakdown": {...},
      "match_rationale": "...",
      "source_urls": [...]
    }
  ]
}
```

Return candidates array with your findings. If no matches found, return empty array.
