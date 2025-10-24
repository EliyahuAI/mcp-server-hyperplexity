# Full Column Population During Discovery - Design Document

**Date:** 2025-10-24
**Status:** Design Phase

---

## Overview

Redesign row discovery to opportunistically populate ALL columns (not just ID columns) when information is available during search.

---

## Current Paradigm (v3.0)

**Discovery Phase:**
- Populates: ID columns only (Company Name, Website)
- Returns: `id_values: {Company Name: "X", Website: "Y"}`

**Validation Phase:**
- Populates: Research columns (Industry Sector, Employee Count, Has Job Posting)
- Requires: Separate validation pass for each row

**Problem:** Information often available during discovery (e.g., "biotech company with 300 employees") is ignored and requires re-fetching later.

---

## New Paradigm (v3.1)

**Discovery Phase:**
- Attempts: ALL columns (ID + research)
- Populates: Whatever information is found in search results
- Returns: `column_values: {Company Name: "X", Website: "Y", Industry: "Biotech", Employee Count: "300"}`
- Leaves blank: Columns not found during discovery

**Validation Phase:**
- Populates: Only empty columns (those not filled during discovery)
- Validates: Information that was filled (check accuracy)
- Much faster: Only validates/fills gaps instead of everything

---

## Benefits

1. **Efficiency:** Capture data once instead of fetching twice
2. **Cost:** Fewer API calls needed for validation
3. **Speed:** Faster table generation
4. **Quality:** Discovery search results often contain rich data
5. **Flexibility:** Validation only fills gaps

---

## Design Changes

### 1. Schema (row_discovery_response.json)

**Current:**
```json
{
  "candidates": [
    {
      "id_values": {"Company Name": "X", "Website": "Y"},
      "score_breakdown": {...},
      "match_rationale": "..."
    }
  ]
}
```

**New:**
```json
{
  "candidates": [
    {
      "id_values": {"Company Name": "X", "Website": "Y"},
      "research_values": {
        "Industry Sector": "Biotech",
        "Employee Count": "300",
        "Has Job Posting": ""  // Empty if not found
      },
      "populated_columns": ["Company Name", "Website", "Industry Sector", "Employee Count"],
      "missing_columns": ["Has Job Posting", "Has GenAI Program"],
      "score_breakdown": {...},
      "match_rationale": "..."
    }
  ]
}
```

**Key changes:**
- Add `research_values` object (like id_values but for research columns)
- Add `populated_columns` array (which columns have data)
- Add `missing_columns` array (which columns still need validation)

---

### 2. Prompt (row_discovery.md)

**Add section after "ID Fields to Populate":**

```markdown
## Research Columns to Populate (If Information Available)

**NEW: Opportunistic Population**

If you find information about these research columns during your search, POPULATE THEM. If not found, leave them empty.

{{RESEARCH_COLUMNS}}

**Instructions:**
- Try to populate as many columns as possible from search results
- If information is readily available (in search snippets, company pages, etc.), include it
- If information requires deep research or isn't found, leave blank (empty string)
- Don't fabricate - only include what you actually found

**Example:**
Search result: "Ginkgo Bioworks, a Boston-based synthetic biology company with 400 employees, posted a Head of AI position..."

Populated:
- Company Name: "Ginkgo Bioworks" (ID)
- Website: "https://ginkgobioworks.com" (ID)
- Industry Sector: "Synthetic biology / Biotech" (Research - FOUND)
- Employee Count: "400" (Research - FOUND)
- Has Job Posting: "Yes - Head of AI" (Research - FOUND)
- Has GenAI Program: "" (Research - NOT FOUND, left empty)
```

---

### 3. Code Changes

**row_discovery_stream.py:**
- Pass ALL column definitions (not just ID columns) to the prompt
- Accept research_values in addition to id_values from AI response
- Track populated vs missing columns

**qc_reviewer.py:**
- Review full row data (ID + populated research columns)
- Assess quality of populated research values
- Flag rows with missing critical columns

**execution.py:**
- Include populated research values in CSV generation
- Mark which columns still need validation

---

## CSV Output

**Current (v3.0):**
```csv
Company Name,Website,Industry Sector,Employee Count,Has Job Posting
Anthropic,https://anthropic.com,,,
OpenAI,https://openai.com,,,
```
(All research columns empty)

**New (v3.1):**
```csv
Company Name,Website,Industry Sector,Employee Count,Has Job Posting
Anthropic,https://anthropic.com,AI Safety,500-1000,Yes - Multiple
OpenAI,https://openai.com,AI Research,300-500,
Ginkgo,https://ginkgo.com,Synthetic Biology,400,Yes - Head of AI
```
(Research columns populated when found during discovery)

**Validation Phase:**
- Validates populated values (are they accurate?)
- Fills in missing values (empty cells)
- Much faster than validating everything

---

## Implementation Plan

### Phase 1: Schema and Prompt
1. Update row_discovery_response.json schema
2. Update row_discovery.md prompt
3. Update column_definition_handler.py to pass research columns to prompt

### Phase 2: Code Changes
4. Update row_discovery_stream.py to extract research_values
5. Update row_consolidator.py to handle full rows
6. Update qc_reviewer.py to review populated values

### Phase 3: CSV Generation
7. Update CSV generation to include populated research values
8. Mark which columns need validation

### Phase 4: Validation Integration
9. Update validation phase to skip populated columns (optional)
10. Update validation to verify populated values (optional)

---

## Backwards Compatibility

**Option 1: Gradual rollout**
- Keep id_values required, make research_values optional
- If research_values missing, behave like v3.0 (empty research columns)

**Option 2: Clean break**
- Require research_values in schema
- All discovered rows must attempt research column population

**Recommendation:** Option 1 for safety

---

## Expected Impact

**Cost reduction:**
- Discovery: Slightly more expensive (populating more fields)
- Validation: MUCH cheaper (only filling gaps)
- Net: 30-50% cost reduction overall

**Speed improvement:**
- Discovery: Same or slightly slower
- Validation: Much faster
- Net: 20-40% faster overall

**Quality improvement:**
- More complete data capture
- Fewer validation errors (data from source search)
- Better user experience

---

## Questions to Resolve

1. Should research_values be required or optional in schema?
2. Should QC reject rows with too many missing columns?
3. Should CSV mark which columns were populated vs validated?
4. Should validation skip populated columns or re-verify them?

**Recommendation:**
1. Optional (backward compatible)
2. No - let validation handle that
3. Yes - add metadata column or separate tracking
4. Quick re-verification better than skipping

---

**Next Steps:** Approve design, then implement Phase 1-3
