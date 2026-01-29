# QC Review - Quality Control for Discovered Rows

## Your Task

Review discovered rows and choose ONE action:
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

**Note: We already have {{PRE_ROW_COUNT}} rows from extracted tables. These are PRE-APPROVED - do NOT include them in your output (they will be automatically added).**

{{PREPOPULATED_ROWS_MARKDOWN}}

**Sources:**
{{PREPOPULATED_CITATIONS}}

---

## Discovered Rows (from Row Discovery) - REVIEW THESE

**{{ROW_COUNT}} NEW rows discovered via web search:**

{{DISCOVERED_ROWS}}

**IMPORTANT: Your output should reference ONLY the discovered rows above, NOT the pre-existing rows.**

---

## Decision Guide

**IMPORTANT:**
- Pre-existing rows ({{PRE_ROW_COUNT}}) are automatically included
- **ALL discovered rows are KEPT BY DEFAULT** - only specify rows to REMOVE
- Your decision is about the {{ROW_COUNT}} DISCOVERED rows

### Action: "pass"
**When:** All discovered rows look good, OR discovery found 0 rows but pre-existing rows are sufficient
**Output:** `overall_score` only (no need to list rows - all are kept by default)

### Action: "filter"
**When:** Need to remove some discovered rows (duplicates, fake entries, requirement violations)
**Output:** `remove_row_ids` (rows to remove with 1-sentence reasons), `overall_score`
**Note:** Only list rows to REMOVE. All other rows are kept automatically.

### Action: "retrigger_discovery"
**When:** Need MORE ENTITIES beyond pre-existing rows
**NOT for:** Filling empty columns (validator handles that downstream)
**Output:** `discovery_guidance`, `new_subdomains`, `overall_score`
**Important:** Focus on finding MORE entities, NOT populating columns

**Example discovery_guidance:**
- Good: "Have 3 pre-existing + 2 discovered = 5 total. Need 15 more to reach 20."
- Bad: "Need to populate tax rate columns" ← NO, validator does this

### Action: "restructure"
**When:** ONLY if table structure is fundamentally flawed AND pre-existing rows don't help
**Output:** `restructuring_guidance` (column_changes, requirement_changes, search_broadening), `user_message`
**WARNING:** Do NOT restructure just because discovery found 0 rows if pre-existing rows are valid!

---

## Output Format

**IMPORTANT: All discovered rows are KEPT BY DEFAULT.** Only specify rows to REMOVE.

Do NOT rewrite the markdown table. Just specify which rows to remove (if any).

**All fields must be present. Use null for fields not applicable to your action.**

```json
{
  "action": "pass",
  "remove_row_ids": null,
  "overall_score": 0.85,
  "discovery_guidance": null,
  "new_subdomains": null,
  "restructuring_guidance": null,
  "user_message": null
}
```

### Example: Filter Action (remove specific rows)
```json
{
  "action": "filter",
  "remove_row_ids": [
    {"row_id": "3-FakeCompany", "reason": "Not a real Fortune 500 company"},
    {"row_id": "5-Duplicate", "reason": "Duplicate of row 2"}
  ],
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
  "remove_row_ids": null,
  "overall_score": 0.6,
  "discovery_guidance": "Have 3 pre-existing + 2 discovered = 5 total. Need 15 more tech companies.",
  "new_subdomains": [
    {
      "name": "Enterprise Software Companies",
      "focus": "Large B2B software companies with $1B+ revenue",
      "search_queries": ["enterprise software companies list 2024", "B2B software unicorns"],
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
  "remove_row_ids": null,
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

| Action | remove_row_ids | overall_score | discovery_guidance | new_subdomains | restructuring_guidance | user_message |
|--------|----------------|---------------|-------------------|----------------|----------------------|--------------|
| pass | null | ✅ number | null | null | null | null |
| filter | ✅ array (rows to remove) | ✅ number | null | null | null | null |
| retrigger_discovery | null | ✅ number | ✅ string | ✅ array | null | null |
| restructure | null | null | null | null | ✅ object | ✅ string |

**Keep it concise - avoid verbose explanations.**
