# Entity Discovery: Candidate Generation

You are tasked with recalling entities that match the search strategy below. Your goal is to draw on your training knowledge to surface real, specific entities — including lesser-known ones that would impress a domain expert.

## Search Strategy

{{SEARCH_STRATEGY}}

### Requirement Types

- **[HARD]** — Must be met for inclusion. Entities that clearly fail a HARD requirement should be marked R (Reject).
- **[SOFT]** — Prioritization only. Prefer entities that satisfy this, but do not exclude ones that don't.

## Task

Generate **{{TARGET_COUNT}}** entities that match this search strategy. For each entity, provide:

1. **ID Column Values** - The identifying information for each entity (specified below)
2. **Disposition** - Your pre-screening verdict: K, R, or V (see guidelines below)
3. **[HARD] columns** - One column per HARD requirement (if any), with values T, F, or ?

### ID Columns to Populate

{{ID_COLUMNS}}

### Disposition Guidelines

- **K** (Keep) — You are highly confident this entity is real AND all HARD requirements are met → will be included directly without validation
- **R** (Reject) — This entity probably doesn't exist OR clearly fails a HARD requirement → will be discarded
- **V** (Validate) — You are uncertain about existence or any HARD requirement → will be sent to web validation

**Default to V when unsure. Only use K or R when very confident.**

- Use K only when you can recall specific identifying details (headquarters, founding year, key metrics, etc.)
- Use R only when confident the entity is fictional, non-existent, or obviously fails a hard requirement
- K and R rows save validation cost; incorrect K/R decisions waste rows or include bad data

### [HARD] Column Guidelines (if hard requirements exist)

For each HARD requirement column named `[HARD] {requirement text}`:
- **T** = True — entity clearly meets this requirement (based on your training knowledge)
- **F** = False — entity clearly fails this requirement
- **?** = Uncertain — you're not sure whether this requirement is met

If you mark T or F, that should align with your Disposition:
- All T → strong case for K (if also confident entity exists)
- Any F → strong case for R

## Output Format

Provide your results as a **markdown table** with this exact structure:

```markdown
{{OUTPUT_FORMAT_EXAMPLE}}
```

## Important Guidelines

1. **Draw on real knowledge** - Only include entities you genuinely recall, not plausible-sounding inventions
2. **Prioritize diversity** - Include entities from different subcategories, sizes, regions, etc.
3. **Go beyond the obvious** - Surface niche, emerging, or lesser-known entities a non-expert might miss
4. **Honest disposition** - Default to V; K/R only when very confident
5. **No explanations** - Just provide the markdown table (no rationale or commentary)
6. **Exact format** - Use the exact column names provided above in the table header

{{EXAMPLES_SECTION}}

{{EXISTING_ROWS_SECTION}}

## Generate Your Candidates

Provide {{TARGET_COUNT}} diverse entities in the markdown table format specified above.
