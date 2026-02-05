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
- Use `keep_row_ids_in_order` to specify which rows to keep AND their order
- If `keep_row_ids_in_order` is null, ALL rows are kept in original order
- Your decision is about the {{ROW_COUNT}} DISCOVERED rows

### Action: "pass"
**When:** All discovered rows look good, OR discovery found 0 rows but pre-existing rows are sufficient
**Output:** `keep_row_ids_in_order: null` (keeps all in original order), `overall_score`

### Action: "filter"
**When:** Need to remove some rows OR reorder rows
**Output:** `keep_row_ids_in_order` (list rows to KEEP in order), `overall_score`, optionally `removal_reasons`

**🔍 DUPLICATE DETECTION - Check carefully for:**
- **Same entity, different names:** "EarPopper" vs "EarPopper®" vs "Ear Popper" (keep ONE)
- **Same entity, different verbosity:** "Anthropic" vs "Anthropic AI Safety Company" (same entity)
- **Same product, different manufacturers/distributors:** If it's the SAME product sold by multiple companies, keep ONE authoritative entry
- **Trademark variations:** ®, ™ symbols don't make entries unique
- **Abbreviations:** "AERA" vs "Acclarent AERA" vs "ACCLARENT AERA™" (same product)

**When you find duplicates:** Keep the row with the MOST COMPLETE information (more columns filled, better sources).

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

**Use `keep_row_ids_in_order` to specify which rows to keep AND their order.**

- If provided: only these rows are kept, in this exact order
- If null: all rows kept in original discovery order

**All fields must be present. Use null for fields not applicable to your action.**

```json
{
  "action": "pass",
  "keep_row_ids_in_order": null,
  "removal_reasons": null,
  "overall_score": 0.85,
  "discovery_guidance": null,
  "new_subdomains": null,
  "restructuring_guidance": null,
  "user_message": null
}
```

### How `keep_row_ids_in_order` Works

This single field handles BOTH filtering AND ordering:

**To keep all rows in original order (pass action):**
```json
"keep_row_ids_in_order": null
```

**To filter AND order (filter action):**
```json
"keep_row_ids_in_order": ["1-Anthropic", "2-OpenAI", "4-Google", "6-Meta"]
```
This keeps only these 4 rows, in this exact order. Rows 3 and 5 are removed.

**To reorder without filtering:**
List ALL row_ids in the desired order.

### When to Specify Ordering

**Preserve natural order when data has:**
- **Rankings**: Forbes 500, Top 10 lists - keep rank order
- **Alphabetical**: Company names, person names - sort A-Z
- **Chronological**: Events, releases - sort by date
- **Categorical**: Group similar entities together

**Use null when:**
- Discovery order is already correct
- No particular ordering makes sense

### Example: Filter Action
```json
{
  "action": "filter",
  "keep_row_ids_in_order": ["1-Anthropic", "2-OpenAI", "4-Google", "6-Meta"],
  "removal_reasons": {"3-FakeCompany": "Not a real company", "5-Duplicate": "Duplicate of row 2"},
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
  "removal_reasons": null,
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
  "keep_row_ids_in_order": null,
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

| Action | keep_row_ids_in_order | removal_reasons | overall_score | discovery_guidance | new_subdomains | restructuring_guidance | user_message |
|--------|----------------------|-----------------|---------------|-------------------|----------------|----------------------|--------------|
| pass | null (keep all) | null | ✅ number | null | null | null | null |
| filter | ✅ array (rows to keep, in order) | optional object | ✅ number | null | null | null | null |
| retrigger_discovery | null | null | ✅ number | ✅ string | ✅ array | null | null |
| restructure | null | null | null | null | null | ✅ object | ✅ string |

**Keep it concise - avoid verbose explanations.**
