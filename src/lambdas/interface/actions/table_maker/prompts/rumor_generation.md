# Rumor Generation: Candidate Entity Discovery

You are tasked with generating a list of plausible candidate entities that **might exist** based on the search strategy below. Your goal is to produce creative, diverse candidates that could potentially be real, along with a confidence score for each.

## Search Strategy

{{SEARCH_STRATEGY}}

## Task

Generate **{{TARGET_COUNT}}** candidate entities that might match this search strategy. For each candidate, provide:

1. **ID Column Values** - The identifying information for each entity (specified below)
2. **Realness Score** - Your confidence (0-1) that this entity actually exists

### ID Columns to Populate

{{ID_COLUMNS}}

### Realness Score Guidelines

- **0.0-0.3**: Low confidence - entity might be fictional or very uncertain
- **0.4-0.6**: Medium confidence - plausible but unverified
- **0.7-0.9**: High confidence - likely exists based on patterns/knowledge
- **0.9-1.0**: Very high confidence - almost certainly real

## Output Format

Provide your results as a **markdown table** with the following structure:

```markdown
| [ID Column 1] | [ID Column 2] | ... | Realness Score |
|---------------|---------------|-----|----------------|
| value1        | value2        | ... | 0.85           |
| value3        | value4        | ... | 0.72           |
```

## Important Guidelines

1. **Prioritize diversity** - Include entities from different subcategories, sizes, regions, etc.
2. **Be creative** - Think beyond the most obvious/popular entities
3. **Consider edge cases** - Include emerging, niche, or lesser-known entities that might exist
4. **Honest scoring** - If you're uncertain an entity exists, give it a lower realness score
5. **No explanations** - Just provide the markdown table (no rationale or commentary)
6. **Exact format** - Use the exact column names provided above in the table header

{{EXAMPLES_SECTION}}

## Generate Your Candidates

Provide {{TARGET_COUNT}} diverse candidate entities in the markdown table format specified above.
