# Entity Discovery: Candidate Generation

You are tasked with recalling entities that match the search strategy below. Your goal is to draw on your training knowledge to surface real, specific entities — including lesser-known ones that would impress a domain expert.

## Search Strategy

{{SEARCH_STRATEGY}}

### Requirement Types

- **[HARD]** — Inclusion gate. Only include entities you believe satisfy this requirement. If you are unsure whether an entity meets a HARD requirement, leave it out.
- **[SOFT]** — Prioritization signal. Prefer entities that satisfy this, but do not exclude ones that don't.

## Task

Generate **{{TARGET_COUNT}}** entities that match this search strategy. For each entity, provide:

1. **ID Column Values** - The identifying information for each entity (specified below)
2. **Confidence Score** - Your confidence (0-1) that this entity is real and matches the criteria

### ID Columns to Populate

{{ID_COLUMNS}}

### Confidence Score Guidelines

The bar is not public verifiability — it is whether **you genuinely know this entity exists**. A good row is one where you can recall specific details about it beyond just the name (e.g. who founded it, when it launched, what it does). A domain expert with deep insider knowledge should look at your list and recognize the entries as real.

- **0.9-1.0**: You recall specific details — this entity is real and matches
- **0.7-0.9**: You are fairly sure it exists and matches, though details are hazy
- **0.5-0.7**: Plausible — you believe it exists but are genuinely uncertain
- **below 0.5**: Do not include — you are guessing

## Output Format

Provide your results as a **markdown table** with the following structure:

```markdown
| [ID Column 1] | [ID Column 2] | ... | Confidence Score |
|---------------|---------------|-----|------------------|
| value1        | value2        | ... | 0.85             |
| value3        | value4        | ... | 0.72             |
```

## Important Guidelines

1. **Draw on real knowledge** - Only include entities you genuinely recall, not plausible-sounding inventions
2. **Prioritize diversity** - Include entities from different subcategories, sizes, regions, etc.
3. **Go beyond the obvious** - Surface niche, emerging, or lesser-known entities a non-expert might miss
4. **Honest scoring** - If you can recall specific details, score high. If only the name feels familiar, score low or omit.
5. **No explanations** - Just provide the markdown table (no rationale or commentary)
6. **Exact format** - Use the exact column names provided above in the table header

{{EXAMPLES_SECTION}}

{{EXISTING_ROWS_SECTION}}

## Generate Your Candidates

Provide {{TARGET_COUNT}} diverse entities in the markdown table format specified above.
