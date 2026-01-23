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

**Note: We already have {{PRE_ROW_COUNT}} rows from extracted tables. These are PRE-APPROVED - do NOT include them in your `rows` output (they will be automatically added).**

{{PREPOPULATED_ROWS_MARKDOWN}}

**Sources:**
{{PREPOPULATED_CITATIONS}}

---

## Discovered Rows (from Row Discovery) - REVIEW THESE

**{{ROW_COUNT}} NEW rows discovered via web search:**

{{DISCOVERED_ROWS}}

**IMPORTANT: Your `rows` output should contain ONLY the discovered rows you approve, NOT the pre-existing rows above.**

---

## Decision Guide

**IMPORTANT: Pre-existing rows ({{PRE_ROW_COUNT}}) are automatically included. Your decision is about the {{ROW_COUNT}} DISCOVERED rows.**

### Action: "pass"
**When:** All discovered rows look good, OR discovery found 0 rows but pre-existing rows are sufficient
**Output:** `rows` (approved discovered rows, best-first), `overall_score`
**Note:** If discovery found 0 rows and pre-existing rows meet requirements, use "pass" with empty `rows: []`

### Action: "filter"
**When:** Need to remove some discovered rows (duplicates, fake entries, requirement violations)
**Output:** `rows` (approved discovered rows), `removed` (with 1-sentence reasons), `overall_score`

### Action: "retrigger_discovery"
**When:** Need MORE ENTITIES beyond pre-existing rows
**NOT for:** Filling empty columns (validator handles that downstream)
**Output:** `rows` (current discovered rows), `discovery_guidance`, `new_subdomains`, `overall_score`
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
