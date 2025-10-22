# Quality Control Review

## Understanding the Table

**What We're Building:**
We are creating a research table to track specific entities (companies, papers, people, etc.) based on the user's research needs.

**User's Original Request:**
{{USER_CONTEXT}}

**Table Name:** {{TABLE_NAME}}

**Table Purpose:** {{TABLE_PURPOSE}}

**Background Research Context:**
{{TABLEWIDE_RESEARCH}}

---

## Understanding the Rows

Each row in this table represents **one specific entity**. Rows are defined by their **ID fields** (identification columns).

### ID Fields (What Identifies Each Row)

{{ID_COLUMNS}}

**What this means:**
- Each row is a UNIQUE entity (e.g., one company, one paper, one person)
- The ID fields contain the IDENTIFIERS for that entity
- Example: For company "Anthropic", ID fields would be: Company Name="Anthropic", Website="https://anthropic.com"

### All Column Definitions (For Context)

{{COLUMN_DEFINITIONS}}

---

## Rows to Review ({{ROW_COUNT}} discovered)

{{DISCOVERED_ROWS}}

Each discovered row has:
- **id_values** - The actual identifiers for this entity (populated ID fields)
- **row_score** - Discovery score from search (0-1)
- **model_used** - Which model found it (sonar, sonar-pro)
- **context_used** - Search context level (low, high)
- **match_rationale** - Why it was selected during discovery
- **source_urls** - Where the information was found

---

## Your Job

Review each discovered row to decide if it should be included in the final table.

You will:
1. **Decide which rows to keep** (genuinely match user's needs)
2. **Reject rows that** don't match, are duplicates, or are low quality
3. **Assign QC scores** (0-1) with more nuance than discovery scoring
4. **Adjust priorities** (promote exceptional fits, demote marginal ones)

---

## Your Task

For each row:

### 1. Decide: Keep or Reject?

**Keep if:**
- ✓ Genuinely matches user requirements
- ✓ Unique entity (not duplicate)
- ✓ Actionable (we can validate this row)
- ✓ Good fit for table purpose

**Reject if:**
- ✗ Doesn't match requirements (wrong type of entity)
- ✗ Redundant (same as another row, just different name)
- ✗ Low quality sources or unreliable
- ✗ Off-topic or irrelevant

### 2. Assign QC Score (0-1.0)

More flexible than discovery rubric. Consider:
- **Overall relevance** to user's goals
- **Uniqueness** (not duplicate)
- **Actionability** (can we validate this?)
- **Strategic value** (good example for table)

**QC Score Guidelines:**
- **0.9-1.0:** Exceptional - perfect match, must include
- **0.7-0.89:** Strong - good fit, definitely include
- **0.5-0.69:** Adequate - meets requirements, include unless limited space
- **0.3-0.49:** Marginal - barely meets requirements, reject unless needed
- **0.0-0.29:** Poor - reject

### 3. Priority Adjustment

- **promote:** Particularly good fit, rank higher than discovery score suggests
- **demote:** Marginal fit, rank lower
- **none:** Keep current ranking

---

## Output Format

Return JSON:

```json
{
  "reviewed_rows": [
    {
      "id_values": {"Company Name": "Anthropic"},
      "row_score": 0.95,
      "qc_score": 0.98,
      "qc_rationale": "Perfect match - leading AI company with active hiring",
      "keep": true,
      "priority_adjustment": "promote"
    },
    {
      "id_values": {"Company Name": "Generic Corp"},
      "row_score": 0.65,
      "qc_score": 0.2,
      "qc_rationale": "Not an AI company, off-topic",
      "keep": false,
      "priority_adjustment": "none"
    }
  ],
  "rejected_rows": [
    {
      "id_values": {"Company Name": "Generic Corp"},
      "rejection_reason": "Not an AI company"
    }
  ],
  "qc_summary": {
    "total_reviewed": 12,
    "kept": 10,
    "rejected": 2,
    "promoted": 3,
    "demoted": 1,
    "reasoning": "Rejected 2 off-topic entries, promoted 3 exceptional fits"
  }
}
```

Review all rows and return your assessment.
