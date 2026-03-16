# Entity Discovery: Candidate Generation

You are tasked with recalling entities that match the search strategy below. Your goal is to draw on your training knowledge to surface real, specific entities — including lesser-known ones that would impress a domain expert.

## Search Strategy

{{SEARCH_STRATEGY}}

### Requirement Types

- **[HARD]** — Must be met for inclusion. Your confidence score should reflect both existence *and* whether this entity meets the hard requirements. An entity that exists but clearly fails a HARD requirement should not be included.
- **[SOFT]** — Prioritization only. Prefer entities that satisfy this, but do not exclude ones that don't.

## Task

Generate **{{TARGET_COUNT}}** entities that match this search strategy. For each entity, provide:

1. **ID Column Values** - The identifying information for each entity (specified below)
2. **Confidence Score** - Your confidence (0-1) that this entity is real and matches the criteria

### ID Columns to Populate

{{ID_COLUMNS}}

### Confidence Score Guidelines

The confidence score is the probability (0–1) that **a domain expert with perfect knowledge** would confirm this entity exists *and* meets the HARD requirements. Think of it as: if that expert reviewed your list, what fraction of the time would they say "yes, this is a valid entry"?

Only include entities where you can recall specific details beyond the name. If you are purely guessing, leave it out.

## Output Format

Provide your results as a **markdown table** with this exact structure:

```markdown
{{OUTPUT_FORMAT_EXAMPLE}}
```

## Important Guidelines

1. **Draw on real knowledge** - Only include entities you genuinely recall, not plausible-sounding inventions
2. **Prioritize diversity** - Include entities from different subcategories, sizes, regions, etc.
3. **Go beyond the obvious** - Surface niche, emerging, or lesser-known entities a non-expert might miss
4. **Honest scoring** - Score = probability an expert with perfect knowledge confirms this entry. Recall specific details to justify a high score.
5. **No explanations** - Just provide the markdown table (no rationale or commentary)
6. **Exact format** - Use the exact column names provided above in the table header

{{EXAMPLES_SECTION}}

{{EXISTING_ROWS_SECTION}}

## Generate Your Candidates

Provide {{TARGET_COUNT}} diverse entities in the markdown table format specified above.
