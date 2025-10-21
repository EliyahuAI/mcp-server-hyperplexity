# Subdomain Analysis for Parallel Row Discovery

You are analyzing a search strategy to identify natural subdivisions (subdomains) that will enable parallel discovery of table rows.

## Search Strategy
{{SEARCH_STRATEGY}}

## Your Task

Analyze the search strategy above and identify **2-5 natural subdivisions** (subdomains) that:

1. **Cover the full scope** - Together, all subdomains should comprehensively cover the search space
2. **Are naturally distinct** - Each subdomain represents a meaningfully different category or segment
3. **Enable parallelization** - Subdomains should be independent enough to search in parallel without significant overlap
4. **Avoid over-splitting** - Don't create too many tiny subdomains; balance breadth with manageability

## Guidelines for Good Subdomain Splits

### Good Examples:
- **Geographic regions** (if relevant): "North American AI companies", "European AI companies", "Asian AI companies"
- **Industry sectors**: "Healthcare AI", "Financial AI", "Enterprise Software AI"
- **Company stages**: "AI Startups (Seed to Series B)", "Growth-stage AI companies", "Public AI companies"
- **Focus areas**: "AI Research Labs", "Applied AI Products", "AI Infrastructure"

### Bad Examples:
- **Too granular**: Splitting into 15 hyper-specific micro-categories that will each only yield 1-2 results
- **Overlapping heavily**: Categories that aren't distinct (e.g., "AI startups" and "small AI companies")
- **Single catch-all**: Just one subdomain that doesn't actually split anything
- **Arbitrary alphabetical**: "Companies A-F", "Companies G-M" (not natural or meaningful)

## Important Constraints

- **Target: 2-5 subdomains** - Fewer is often better. Only split if there's a natural, meaningful division.
- **If the search is narrow**: For very specific searches (e.g., "top 5 AI safety research labs"), you might only need 1-2 subdomains or even just 1.
- **If the search is broad**: For wide-ranging searches (e.g., "all types of AI companies"), you should identify 4-5 major categories.

## For Each Subdomain, Provide:

1. **Name**: Short, clear label (e.g., "Healthcare AI Companies")
2. **Focus**: 1-2 sentence explanation of what this subdomain targets and why it's distinct
3. **Search Queries**: 2-4 specific search queries optimized for finding entities in this subdomain

## Output Requirements

- Each subdomain must have focused, specific search queries (not just rephrasing the general strategy)
- Search queries should include relevant keywords, constraints, and qualifiers for that subdomain
- Explain your reasoning: Why did you choose these particular subdivisions?

## Example Output Structure

```json
{
  "subdomains": [
    {
      "name": "AI Research Companies",
      "focus": "Academic and research-focused AI organizations, including university spin-offs and dedicated research labs",
      "search_queries": [
        "AI research labs hiring machine learning scientists",
        "academic AI research companies with job openings",
        "university AI lab spin-offs recruiting"
      ]
    },
    {
      "name": "Healthcare AI",
      "focus": "AI companies specifically focused on healthcare, medical imaging, drug discovery, and clinical applications",
      "search_queries": [
        "healthcare AI companies hiring ML engineers",
        "medical AI startups with job postings",
        "clinical AI software companies recruiting"
      ]
    },
    {
      "name": "Enterprise AI Solutions",
      "focus": "B2B AI companies providing enterprise software, automation, and business intelligence tools",
      "search_queries": [
        "enterprise AI software companies hiring",
        "B2B AI automation companies with job openings",
        "business intelligence AI companies recruiting"
      ]
    }
  ],
  "reasoning": "Split into three major sectors that represent distinct application areas of AI. Healthcare AI has unique regulatory and domain requirements. Research companies focus on advancing the field vs. commercialization. Enterprise solutions target B2B customers with different needs than consumer or research applications. These three categories provide good coverage without over-fragmenting the search space."
}
```

Remember: The goal is to enable efficient parallel search while maintaining quality. Fewer, well-chosen subdomains are better than many overlapping or overly-specific ones.
