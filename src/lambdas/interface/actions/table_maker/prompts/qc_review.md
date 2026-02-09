# QC Review - Quality Control for Discovered Rows

## Your Task

Review ALL rows (both pre-existing and discovered) and choose ONE action:
1. **pass** - Approve all rows as-is
2. **filter** - Remove some rows (provide reasons)
3. **retrigger_discovery** - Need MORE ENTITIES (not to fill columns - validator does that)
4. **restructure** - 0 rows approved, table needs redesign

---

## Table Context

**User Request:** {{USER_CONTEXT}}

**Table Name:** {{TABLE_NAME}}

**Requirements:**

**Hard (must meet):**
{{HARD_REQUIREMENTS}}

**Soft (preferences):**
{{SOFT_REQUIREMENTS}}

---

## Pre-existing Rows (from Column Definition)

**{{PRE_ROW_COUNT}} rows from extracted tables/sources (row_ids prefixed with P-).**

**You CAN remove pre-existing rows.** Flag any that are duplicates, irrelevant, don't meet requirements, or have missing/placeholder ID values. Use `remove_prepopulated_row_ids` to list their P-prefixed row_ids.

{{PREPOPULATED_ROWS_MARKDOWN}}

**Sources:**
{{PREPOPULATED_CITATIONS}}

---

## Discovered Rows (from Row Discovery) - REVIEW THESE

**{{ROW_COUNT}} NEW rows discovered via web search:**

{{DISCOVERED_ROWS}}

---

## STRICT DEDUPLICATION - Require Evident Uniqueness

**Every row must be EVIDENTLY UNIQUE.** If two rows MIGHT be the same entity, remove the less complete one. The burden of proof is on uniqueness, not on duplication.

**Remove duplicates aggressively across BOTH pre-existing and discovered rows:**

- **Same entity, different names:** "EarPopper" vs "EarPopper(R)" vs "Ear Popper" = SAME (keep ONE)
- **Same entity, different verbosity:** "Anthropic" vs "Anthropic AI Safety Company" = SAME
- **Same product, different context:** If SAME product/entity appears in both pre-existing and discovered rows, keep the MORE COMPLETE version (more columns filled, better sources) regardless of which set it came from
- **Trademark/symbol variations:** (R), (TM), (C) symbols don't make entries unique
- **Abbreviations:** "AERA" vs "Acclarent AERA" vs "ACCLARENT AERA(TM)" = SAME
- **Subsidiaries vs parents:** If both parent and subsidiary are listed and they represent the same core entity, keep ONE
- **Slight spelling differences:** "Grey" vs "Gray", "Center" vs "Centre" = likely SAME

**When in doubt, REMOVE.** It is better to have fewer high-quality unique rows than many near-duplicates.

---

## MISSING ID COLUMNS - Reject Incomplete Rows

**Every row MUST have ALL ID columns populated with real values.**

- Remove rows where ANY ID column is empty, "Unknown", "N/A", "TBD", "-", or any other placeholder
- ID columns: {{ID_COLUMNS}}
- If a row has a placeholder in any ID column, it is NOT a valid row - remove it

---

## Decision Guide

**IMPORTANT:**
- Use `keep_row_ids_in_order` to specify which DISCOVERED rows to keep AND their order
- Use `remove_prepopulated_row_ids` to flag pre-existing rows for removal
- If `keep_row_ids_in_order` is null, ALL discovered rows are kept in original order
- If `remove_prepopulated_row_ids` is null, ALL pre-existing rows are kept

### Action: "pass"
**When:** All rows (both pre-existing and discovered) look good - no duplicates, no missing IDs, no quality issues
**Output:** `keep_row_ids_in_order: null`, `remove_prepopulated_row_ids: null`, `overall_score`

### Action: "filter"
**When:** Need to remove some rows (from either set) OR reorder discovered rows
**Output:** `keep_row_ids_in_order` (discovered rows to KEEP in order), `remove_prepopulated_row_ids` (pre-existing rows to remove), `overall_score`, optionally `removal_reasons`

### Action: "retrigger_discovery"
**When:** Need MORE ENTITIES beyond pre-existing rows
**NOT for:** Filling empty columns (validator handles that downstream)
**Output:** `discovery_guidance`, `new_subdomains`, `overall_score`
**Important:** Focus on finding MORE entities, NOT populating columns

**USE YOUR KNOWLEDGE:** If you know of specific entities that SHOULD be in this table but are missing, LIST THEM in `discovery_guidance`. The next discovery round will use your guidance to find them.

**Example discovery_guidance:**
- Good: "Have 5 total but need 20. Missing known entries: Medtronic, Boston Scientific, Abbott Laboratories, Stryker, Zimmer Biomet. Also search for smaller companies in orthopedics and cardiovascular devices."
- Good: "Only 3 Fortune 500 tech companies found. Missing: Apple, Microsoft, Google, Amazon, Meta, NVIDIA, Salesforce, Oracle, Intel, IBM. Search for complete Fortune 500 technology sector."
- Bad: "Need to populate tax rate columns" <- NO, validator does this

### Action: "restructure"
**When:** ONLY if table structure is fundamentally flawed AND pre-existing rows don't help
**Output:** `restructuring_guidance` (column_changes, requirement_changes, search_broadening), `user_message`
**WARNING:** Do NOT restructure just because discovery found 0 rows if pre-existing rows are valid!

---

## Output Format

**Use `keep_row_ids_in_order` for discovered rows and `remove_prepopulated_row_ids` for pre-existing rows.**

**All fields must be present. Use null for fields not applicable to your action.**

```json
{
  "action": "pass",
  "keep_row_ids_in_order": null,
  "remove_prepopulated_row_ids": null,
  "removal_reasons": null,
  "overall_score": 0.85,
  "discovery_guidance": null,
  "new_subdomains": null,
  "restructuring_guidance": null,
  "user_message": null
}
```

### How `keep_row_ids_in_order` Works (Discovered Rows)

This field handles BOTH filtering AND ordering of discovered rows:

**To keep all discovered rows in original order (pass action):**
```json
"keep_row_ids_in_order": null
```

**To filter AND order (filter action):**
```json
"keep_row_ids_in_order": ["1-Anthropic", "2-OpenAI", "4-Google", "6-Meta"]
```
This keeps only these 4 discovered rows, in this exact order. Rows 3 and 5 are removed.

### How `remove_prepopulated_row_ids` Works (Pre-existing Rows)

**To keep all pre-existing rows:**
```json
"remove_prepopulated_row_ids": null
```

**To remove some pre-existing rows:**
```json
"remove_prepopulated_row_ids": ["P3-FakeCompany", "P7-DuplicateEntity"]
```

### When to Specify Ordering

**Preserve natural order when data has:**
- **Rankings**: Forbes 500, Top 10 lists - keep rank order
- **Alphabetical**: Company names, person names - sort A-Z
- **Chronological**: Events, releases - sort by date
- **Categorical**: Group similar entities together

**Use null when:**
- Discovery order is already correct
- No particular ordering makes sense

### Example: Filter Action (removing from both sets)
```json
{
  "action": "filter",
  "keep_row_ids_in_order": ["1-Anthropic", "2-OpenAI", "4-Google"],
  "remove_prepopulated_row_ids": ["P5-OldCompany"],
  "removal_reasons": {"3-FakeCompany": "Not a real company", "5-Duplicate": "Duplicate of row 2", "P5-OldCompany": "Duplicate of discovered row 4-Google"},
  "overall_score": 0.85,
  "discovery_guidance": null,
  "new_subdomains": null,
  "restructuring_guidance": null,
  "user_message": null
}
```

### Example: Retrigger Discovery Action
```json
{
  "action": "retrigger_discovery",
  "keep_row_ids_in_order": null,
  "remove_prepopulated_row_ids": null,
  "removal_reasons": null,
  "overall_score": 0.6,
  "discovery_guidance": "Have 3 pre-existing + 2 discovered = 5 total. Need 15 more. Missing known entities: Salesforce, Oracle, SAP, ServiceNow, Workday, Atlassian, Datadog, Snowflake. Also search for mid-cap enterprise SaaS companies.",
  "new_subdomains": [
    {
      "name": "Enterprise Software Companies",
      "focus": "Large B2B software companies - specifically Salesforce, Oracle, SAP, ServiceNow, Workday, Atlassian",
      "search_queries": ["enterprise software companies list 2024", "B2B software unicorns", "Salesforce Oracle SAP ServiceNow enterprise"],
      "target_rows": 10
    }
  ],
  "restructuring_guidance": null,
  "user_message": null
}
```

### Example: Restructure Action
```json
{
  "action": "restructure",
  "keep_row_ids_in_order": null,
  "remove_prepopulated_row_ids": null,
  "removal_reasons": null,
  "overall_score": null,
  "discovery_guidance": null,
  "new_subdomains": null,
  "restructuring_guidance": {
    "column_changes": "Simplify ID columns to just 'Company Name'",
    "requirement_changes": "Remove revenue requirement, make it a research column instead",
    "search_broadening": "Search for companies in any industry, not just tech"
  },
  "user_message": "The table requirements are too specific. Restructuring with simpler columns and broader criteria."
}
```

### Field Requirements by Action:

| Action | keep_row_ids_in_order | remove_prepopulated_row_ids | removal_reasons | overall_score | discovery_guidance | new_subdomains | restructuring_guidance | user_message |
|--------|----------------------|---------------------------|-----------------|---------------|-------------------|----------------|----------------------|--------------|
| pass | null (keep all) | null (keep all) | null | number | null | null | null | null |
| filter | array OR null | array OR null | optional object | number | null | null | null | null |
| retrigger_discovery | null | null | null | number | string | array | null | null |
| restructure | null | null | null | null | null | null | object | string |

**Keep it concise - avoid verbose explanations.**
