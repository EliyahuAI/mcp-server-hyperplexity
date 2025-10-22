# QC Layer and Enhancements - Implementation Plan

**Date:** October 21, 2025
**Status:** Plan Document
**Scope:** LOCAL table_maker/ only

---

## Overview

Four major enhancements to the row discovery system:

1. **Enhanced Data Collection** - Track all API calls with descriptive context
2. **QC Layer** - Quality control step to filter/prioritize discovered rows
3. **Flexible Row Count** - Remove fixed cutoffs, let QC determine final count
4. **Debug Sonar 0 Results** - Investigate and fix why sonar returns empty results

---

## 1. Enhanced Data Collection

### Goal
Capture enhanced_data from EVERY API call with descriptive messages about what the call was for.

### Structure
```python
{
  "api_calls": [
    {
      "call_description": "Creating Columns",
      "model": "claude-haiku-4-5",
      "enhanced_data": {...},  # From ai_api_client response
      "timestamp": "2025-10-21T13:45:00Z",
      "duration_seconds": 12.3
    },
    {
      "call_description": "Finding Rows - Subdomain 1 (AI Research) - Round 1 (sonar-low)",
      "model": "sonar",
      "context": "low",
      "enhanced_data": {...},
      "timestamp": "2025-10-21T13:45:15Z",
      "duration_seconds": 18.7
    },
    {
      "call_description": "Finding Rows - Subdomain 1 (AI Research) - Round 2 (sonar-high)",
      "model": "sonar",
      "context": "high",
      "enhanced_data": {...},
      "timestamp": "2025-10-21T13:45:34Z",
      "duration_seconds": 24.2
    },
    {
      "call_description": "QC Review - Filtering and Prioritizing Rows",
      "model": "claude-sonnet-4-5",
      "enhanced_data": {...},
      "timestamp": "2025-10-21T13:47:15Z",
      "duration_seconds": 8.5
    }
  ],
  "total_cost": 0.0847,
  "total_api_calls": 4,
  "cost_breakdown": {
    "column_definition": 0.0023,
    "row_discovery": 0.0654,
    "qc_review": 0.0170
  }
}
```

### Implementation
- Add `api_calls` list to test results
- Each component returns enhanced_data in result
- Test script collects and displays all calls

---

## 2. QC Layer

### Purpose
Review all discovered rows and:
- **Reject:** Rows that don't match requirements or are redundant
- **Reprioritize:** Rerank rows based on overall quality
- **Flexible scoring:** More nuanced than discovery rubric

### QC Schema (`schemas/qc_review_response.json`)
```json
{
  "type": "object",
  "required": ["reviewed_rows", "rejected_rows", "qc_summary"],
  "properties": {
    "reviewed_rows": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id_values", "row_score", "qc_score", "qc_rationale", "keep"],
        "properties": {
          "id_values": {"type": "object"},
          "row_score": {"type": "number"},
          "qc_score": {"type": "number", "minimum": 0, "maximum": 1},
          "qc_rationale": {"type": "string"},
          "keep": {"type": "boolean"},
          "priority_adjustment": {"type": "string", "enum": ["promote", "demote", "none"]}
        }
      }
    },
    "rejected_rows": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id_values", "rejection_reason"],
        "properties": {
          "id_values": {"type": "object"},
          "rejection_reason": {"type": "string"}
        }
      }
    },
    "qc_summary": {
      "type": "object",
      "properties": {
        "total_reviewed": {"type": "integer"},
        "kept": {"type": "integer"},
        "rejected": {"type": "integer"},
        "promoted": {"type": "integer"},
        "demoted": {"type": "integer"},
        "reasoning": {"type": "string"}
      }
    }
  }
}
```

### QC Prompt (`prompts/qc_review.md`)
```markdown
You are reviewing discovered rows for a research table to ensure quality and relevance.

## Table Context
{{TABLE_NAME}}
{{USER_REQUIREMENTS}}
{{COLUMN_DEFINITIONS}}

## Rows to Review
{{DISCOVERED_ROWS}}

Each row has:
- ID columns (identifying the entity)
- row_score: Discovery score from search (0-1)
- Source models/contexts

## Your Task

Review each row and:

1. **Decide if it should be kept:**
   - Keep if it genuinely matches user requirements
   - Reject if:
     - Doesn't match requirements (wrong type of entity)
     - Redundant with another row (same entity, different name)
     - Low quality sources or unreliable data
     - Off-topic or irrelevant

2. **Assign QC Score (0-1):**
   - More flexible than discovery rubric
   - Consider:
     - Overall relevance to user's goals
     - Uniqueness (not duplicate)
     - Actionability (can we actually validate this row?)
     - Strategic value (good example for the table)

3. **Priority Adjustment:**
   - promote: Particularly good fit, should rank higher
   - demote: Marginal fit, rank lower
   - none: Keep current ranking

## QC Score Guidelines

- **0.9-1.0:** Exceptional fit - perfect match, unique, highly actionable
- **0.7-0.89:** Strong fit - good match, valuable addition
- **0.5-0.69:** Adequate fit - meets requirements but not ideal
- **0.3-0.49:** Marginal fit - barely meets requirements, consider rejecting
- **0.0-0.29:** Poor fit - reject

## Output Format

For each row:
- id_values: (copy from input)
- row_score: (copy from input)
- qc_score: Your assessment (0-1)
- qc_rationale: 1 sentence explaining your decision
- keep: true/false
- priority_adjustment: promote/demote/none

Summary:
- Total reviewed
- Kept/rejected counts
- Promoted/demoted counts
- Overall reasoning
```

### QC Handler (`src/qc_reviewer.py`)
```python
class QCReviewer:
    async def review_rows(
        self,
        discovered_rows: List[Dict],
        columns: List[Dict],
        user_requirements: str,
        table_name: str,
        model: str = "claude-sonnet-4-5"
    ) -> Dict:
        """
        Review and filter discovered rows using QC criteria.

        Returns:
          {
            "approved_rows": [...],  # Rows with keep=true, sorted by qc_score
            "rejected_rows": [...],  # Rows with keep=false
            "qc_summary": {...},
            "enhanced_data": {...}
          }
        """
```

---

## 3. Flexible Row Count

### Current (Fixed)
```python
target_row_count = 20
# Always return exactly 20 rows (or less if not enough found)
final_rows = sorted_candidates[:target_row_count]
```

### New (Flexible)
```python
min_row_count = 5   # Don't return less than this
max_row_count = 50  # Don't return more than this
qc_threshold = 0.7  # Only return rows with qc_score >= 0.7

# Let QC decide
approved = [r for r in qc_result['reviewed_rows'] if r['keep'] and r['qc_score'] >= qc_threshold]

# Sort by qc_score
approved_sorted = sorted(approved, key=lambda x: x['qc_score'], reverse=True)

# Return all approved within limits
final_count = len(approved_sorted)
if final_count < min_row_count:
    # Warning: insufficient quality rows
elif final_count > max_row_count:
    # Trim to max
    final_rows = approved_sorted[:max_row_count]
else:
    # Return all approved
    final_rows = approved_sorted
```

### Configuration
```json
{
  "qc_review": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "min_row_count": 5,
    "max_row_count": 50,
    "qc_score_threshold": 0.7,
    "enable_qc": true
  }
}
```

---

## 4. Debug Sonar 0 Results

### Investigation Steps

1. **Check actual Perplexity API response**
   - Log raw response when 0 candidates returned
   - Check if search actually executed
   - Verify response_format is working

2. **Strengthen prompts**
   - Add more explicit instructions
   - Add concrete examples of expected output
   - Emphasize must return candidates array

3. **Add fallback handling**
   ```python
   if len(candidates) == 0:
       logger.warning("Perplexity returned 0 candidates")
       logger.warning(f"Prompt: {prompt[:500]}")
       logger.warning(f"Response: {json.dumps(response, indent=2)[:1000]}")
       # Try again with different prompt formulation?
   ```

4. **Verify search_queries quality**
   - Are queries too specific?
   - Are they searchable?
   - Do they yield results on Google?

### Prompt Reinforcement for Row Discovery

Add to `prompts/row_discovery.md`:
```markdown
## CRITICAL OUTPUT REQUIREMENTS

You MUST return a JSON object with a "candidates" array.

ALWAYS return candidates, even if only partial matches.
- If you find 10 great matches, return all 10
- If you find 3 weak matches, return those 3
- If you find 1 marginal match, return that 1
- NEVER return an empty candidates array unless truly no matches exist

Example valid outputs:
✓ {"candidates": [{"id_values": {...}, "match_score": 0.95, ...}]}
✓ {"candidates": [{"id_values": {...}, "match_score": 0.65, ...}]}
✓ {"candidates": []}  // ONLY if absolutely no matches

❌ NEVER: Return anything other than this structure
❌ NEVER: Omit the candidates array
❌ NEVER: Return error messages instead of JSON
```

---

## Implementation Order

### Phase 1: Enhanced Data Collection (30 min)
1. Update column_definition_handler to return enhanced_data
2. Update row_discovery_stream to return enhanced_data per round
3. Update test to collect and display all enhanced_data
4. Add cost aggregation across all calls

### Phase 2: Debug Sonar (30 min)
1. Add detailed logging when 0 candidates returned
2. Strengthen row_discovery.md prompt
3. Test with various queries
4. Document findings

### Phase 3: QC Layer (60 min)
1. Create qc_review_response.json schema
2. Create qc_review.md prompt
3. Create qc_reviewer.py component
4. Add tests for QC layer

### Phase 4: Integration (30 min)
1. Add QC step after row consolidation
2. Remove fixed row cutoff
3. Use QC-determined flexible count
4. Update configuration
5. Update tests

**Total Estimated Time: 2.5-3 hours**

---

## Expected Flow After Implementation

```
1. Column Definition (claude-haiku-4-5)
   → Enhanced data: "Creating Columns"
   → Cost: $0.002

2. Row Discovery - Subdomain 1
   Round 1: sonar (low) → 6 candidates
     → Enhanced data: "Finding Rows - Subdomain 1 (AI Research) - Round 1"
     → Cost: $0.006
   Early stop (50% reached)

3. Row Discovery - Subdomain 2
   Round 1: sonar (low) → 8 candidates
     → Enhanced data: "Finding Rows - Subdomain 2 (Healthcare) - Round 1"
     → Cost: $0.008
   Early stop (50% reached)

4. Consolidation
   → 14 candidates total
   → 2 duplicates removed
   → 12 unique candidates

5. QC Review (claude-sonnet-4-5)
   → Input: 12 candidates
   → Enhanced data: "QC Review - Filtering and Prioritizing Rows"
   → Output: 10 approved (qc_score >= 0.7), 2 rejected
   → Cost: $0.017

Final: 10 rows (not fixed, QC-determined)
Total Cost: $0.033
```

---

**Should I proceed with Phase 1 (Enhanced Data Collection)?**
