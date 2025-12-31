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

**Note: We already have these {{PRE_ROW_COUNT}} rows identified from extracted tables.**

{{PREPOPULATED_ROWS_MARKDOWN}}

**Sources:**
{{PREPOPULATED_CITATIONS}}

---

## Discovered Rows (from Row Discovery)

**{{ROW_COUNT}} rows discovered:**

{{DISCOVERED_ROWS}}

---

## Decision Guide

### Action: "pass"
**When:** All discovered rows look good, no removals needed
**Output:** `rows` (all rows ordered best-first), `overall_score`

### Action: "filter"
**When:** Need to remove duplicates, fake entries, or hard requirement violations
**Output:** `rows` (approved), `removed` (with 1-sentence reasons), `overall_score`

### Action: "retrigger_discovery"
**When:** Need MORE ENTITIES (more rows to identify)
**NOT for:** Filling empty columns (validator handles that downstream)
**Output:** `rows` (current), `discovery_guidance`, `new_subdomains`, `overall_score`
**Important:** Focus on finding MORE entities, NOT populating columns

**Example discovery_guidance:**
- Good: "Have 15 billionaires identified. Need 5 more to reach 20 total entities."
- Bad: "Need to populate tax rate columns" ← NO, validator does this

### Action: "restructure"
**When:** 0 rows approved, table structure is fundamentally flawed
**Output:** `restructuring_guidance` (column_changes, requirement_changes, search_broadening), `user_message`

---

## Output Format

Choose ONE action and populate ONLY the required fields for that action. No verbose per-row rationales unless removing rows.

```json
{
  "action": "pass|filter|retrigger_discovery|restructure",
  "rows": [...],  // If pass/filter/retrigger
  "overall_score": 0.85,  // If pass/filter/retrigger
  "removed": [...],  // If filter (with reasons)
  "discovery_guidance": "...",  // If retrigger (what entities to find)
  "new_subdomains": [...],  // If retrigger (where to search)
  "restructuring_guidance": {...},  // If restructure
  "user_message": "..."  // If restructure
}
```

**Keep it concise - avoid verbose explanations.**
