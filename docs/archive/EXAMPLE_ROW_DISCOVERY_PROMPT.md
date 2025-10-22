# Example Row Discovery Prompt

This is what actually gets sent to sonar-pro for finding AI companies.

---

## Example Prompt (Real)

```
You are finding and scoring entities for: AI Research Companies

FOCUS: Academic and research-focused AI organizations, research labs, university spin-offs

REQUIREMENTS: Find AI companies actively hiring for AI/ML positions across research, healthcare, and enterprise domains.

TARGET: Find 10 best-matching entities

SEARCH QUERIES (prioritize multi-row results):
- top AI research labs hiring 2024
- AI research companies list
- academic AI institutes with job openings

CRITICAL: Use EXACT field names for ID columns in your response:
- Company Name
- Website

For example, if columns are "Company Name" and "Website", use those EXACT names:
  {"id_values": {"Company Name": "Anthropic", "Website": "https://anthropic.com"}}

Do NOT rename to "entity_name", "Entity Name", "company", etc.
Use the EXACT field names listed above.

SCORING RUBRIC (0-1.0 scale):
Final Score = (Relevancy × 0.4) + (Source Reliability × 0.3) + (Recency × 0.3)

**Relevancy (0-1.0):** How well does the entity match requirements?
  1.0 = Perfect match to all requirements
  0.7 = Matches most requirements, minor gaps
  0.4 = Matches core requirements only
  0.0 = Weak or no match

**Source Reliability (0-1.0):** How reliable are your sources?
  1.0 = Primary sources (company site, Crunchbase, official docs)
  0.7 = Secondary sources (TechCrunch, LinkedIn, WSJ, Bloomberg)
  0.4 = Tertiary sources (blogs, aggregators, forums)
  0.0 = Unreliable or unverified

**Recency (0-1.0):** How recent is the information?
  1.0 = <3 months old
  0.7 = 3-6 months old
  0.4 = 6-12 months old
  0.0 = >12 months or undated

For each entity:
1. Populate ID columns using EXACT field names from list above
2. Calculate individual dimension scores (relevancy, reliability, recency)
3. Calculate final weighted score: (relevancy × 0.4) + (reliability × 0.3) + (recency × 0.3)
4. Provide 1-sentence rationale explaining score
5. Include source URLs

Return top 10 candidates sorted by final score (highest first).
```

---

## What sonar-pro Should Return

```json
{
  "subdomain": "AI Research Companies",
  "candidates": [
    {
      "id_values": {
        "Company Name": "Anthropic",
        "Website": "https://www.anthropic.com"
      },
      "match_score": 0.95,
      "score_breakdown": {
        "relevancy": 0.95,
        "reliability": 1.0,
        "recency": 0.9
      },
      "match_rationale": "Leading AI safety research company with active hiring for ML engineers and researchers",
      "source_urls": [
        "https://www.anthropic.com/careers",
        "https://www.crunchbase.com/organization/anthropic"
      ]
    },
    {
      "id_values": {
        "Company Name": "OpenAI",
        "Website": "https://www.openai.com"
      },
      "match_score": 0.92,
      "score_breakdown": {
        "relevancy": 0.93,
        "reliability": 1.0,
        "recency": 0.85
      },
      "match_rationale": "Premier AI research organization with extensive hiring across multiple AI research teams",
      "source_urls": [
        "https://openai.com/careers",
        "https://www.linkedin.com/company/openai/jobs"
      ]
    }
  ]
}
```

---

## Issues We've Seen

### Problem 1: Returns 0 Candidates
Sometimes sonar returns:
```json
{
  "subdomain": "AI Research Companies",
  "candidates": []
}
```

**Possible causes:**
- Search queries too specific/narrow
- Response format not parsed correctly
- API issue/timeout

### Problem 2: Wrong Field Names (Less Common Now)
Sometimes returns:
```json
{
  "id_values": {
    "Entity Name": "Anthropic",  // Should be "Company Name"
    "Website URL": "..."          // Should be "Website"
  }
}
```

**Fix:** "CRITICAL: Use EXACT field names" instruction helps

### Problem 3: Incorrect Score Calculation
Sometimes returns:
```json
{
  "match_score": 1.0,
  "score_breakdown": {
    "relevancy": 1.0,
    "reliability": 0.7,
    "recency": 0.7
  }
}
```
Correct score should be: (1.0 × 0.4) + (0.7 × 0.3) + (0.7 × 0.3) = **0.82**, not 1.0

**Fix:** Row consolidator recalculates scores automatically

---

**This is the actual prompt structure being used.**
