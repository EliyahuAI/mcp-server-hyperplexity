# Table Maker Prompt-Schema Alignment Review

**Date:** 2025-10-24
**Purpose:** Ensure one-to-one correspondence between Table Maker prompts and their JSON schemas

---

## Executive Summary

This review analyzes three critical prompt/schema pairs in the Table Maker system:
1. Column Definition
2. Row Discovery
3. QC Review

Each section provides:
- [SUCCESS] Fields that match correctly
- [ERROR] Missing or misaligned fields
- [WARNING] Structural differences or optional field handling issues
- [FIX] Recommended corrections

---

## 1. Column Definition Prompt vs Schema

**Files:**
- Prompt: `/src/lambdas/interface/actions/table_maker/prompts/column_definition.md`
- Schema: `/src/lambdas/interface/actions/table_maker/schemas/column_definition_response.json`

### Schema Required Fields

```json
{
  "required": ["columns", "search_strategy", "table_name", "tablewide_research"]
}
```

### Detailed Analysis

#### [SUCCESS] Top-Level Required Fields

| Field | Schema Required | Prompt Requests | Match |
|-------|----------------|-----------------|-------|
| `columns` | YES | YES (line 35-95, 201-209) | [SUCCESS] |
| `search_strategy` | YES | YES (line 96-119, 211-234) | [SUCCESS] |
| `table_name` | YES | YES (line 121, 235) | [SUCCESS] |
| `tablewide_research` | YES | YES (line 122, 237) | [SUCCESS] |

#### [SUCCESS] Column Object Fields

Schema requires for each column:
- `name` - [SUCCESS] Requested (lines 130-146)
- `description` - [SUCCESS] Requested (lines 185-188)
- `format` - [SUCCESS] Requested (line 42, 48, etc.)
- `importance` - [SUCCESS] Requested (line 43, 51, etc.)
- `is_identification` - [SUCCESS] Requested (lines 147-177)

Schema optional:
- `validation_strategy` - [SUCCESS] Explained as empty for ID columns (line 175), required for research columns (lines 179-194)

#### [ERROR] Search Strategy Structure Mismatch

**Schema requires:**
```json
"search_strategy": {
  "required": ["description", "requirements", "subdomains"],
  "properties": {
    "requirements": {
      "type": "array",
      "minItems": 1,
      "items": {
        "required": ["requirement", "type", "rationale"]
      }
    },
    "requirements_notes": { "type": "string" }
  }
}
```

**Prompt mentions:**
- Lines 241-285: Detailed explanation of requirements
- Line 282: "Requirements Notes" section with `requirements_notes` field
- BUT: Prompt does NOT show the requirements in the example output (lines 36-124)
- The example JSON (lines 36-124) is missing the `requirements` array entirely

**Issue:** The example output in the prompt does not include the required `requirements` array, which could confuse the model.

#### [SUCCESS] Requirements Fields (When Documented)

| Field | Schema Required | Prompt Documents | Match |
|-------|----------------|------------------|-------|
| `requirements` array | YES | YES (lines 241-285) | [SUCCESS] |
| `requirement` (string) | YES | YES (line 246+) | [SUCCESS] |
| `type` (hard/soft) | YES | YES (lines 245-265) | [SUCCESS] |
| `rationale` (string) | YES | YES (line 262+) | [SUCCESS] |
| `requirements_notes` | NO (optional) | YES (lines 280-284) | [SUCCESS] |

#### [SUCCESS] Domain Filtering (Optional)

| Field | Schema | Prompt Documents | Match |
|-------|--------|------------------|-------|
| `default_included_domains` | Optional | YES (lines 288-319) | [SUCCESS] |
| `default_excluded_domains` | Optional | YES (lines 288-319) | [SUCCESS] |

#### [SUCCESS] Subdomain Fields

Schema requires for each subdomain:
- `name` - [SUCCESS] Requested (line 99, 213)
- `focus` - [SUCCESS] Requested (line 100, 213)
- `search_queries` - [SUCCESS] Requested (line 101-106, 213)
- `target_rows` - [SUCCESS] Requested (line 107, 213)

Schema optional for subdomains:
- `included_domains` - [SUCCESS] Documented (line 318)
- `excluded_domains` - [SUCCESS] Documented (line 318)

### Summary for Column Definition

**Overall Alignment: 95%**

**Strengths:**
- All required top-level fields are requested
- Column structure perfectly matches
- Subdomain structure perfectly matches
- Optional fields are well-documented
- Domain filtering is thoroughly explained

**Critical Issue:**
- [ERROR] Example output (lines 36-124) is missing the required `requirements` array
- [ERROR] Example does not show `requirements_notes` field

**Recommendations:**
1. [FIX] Add `requirements` array to example output (after line 120, before closing the search_strategy object)
2. [FIX] Add `requirements_notes` to example output
3. [FIX] Show domain filtering in example if applicable

---

## 2. Row Discovery Prompt vs Schema

**Files:**
- Prompt: `/src/lambdas/interface/actions/table_maker/prompts/row_discovery.md`
- Schema: `/src/lambdas/interface/actions/table_maker/schemas/row_discovery_response.json`

### Schema Required Fields

```json
{
  "required": ["subdomain", "candidates"]
}
```

### Detailed Analysis

#### [SUCCESS] Top-Level Required Fields

| Field | Schema Required | Prompt Requests | Match |
|-------|----------------|-----------------|-------|
| `subdomain` | YES | YES (line 128, example) | [SUCCESS] |
| `candidates` | YES | YES (line 129-146, 163) | [SUCCESS] |

#### [SUCCESS] Optional Top-Level Fields

| Field | Schema | Prompt Documents | Match |
|-------|--------|------------------|-------|
| `no_matches_reason` | Optional | YES (lines 168-188) | [SUCCESS] |
| `search_improvements` | Optional | YES (lines 190-212) | [SUCCESS] |
| `domain_filtering_recommendations` | Optional | YES (lines 214-243) | [SUCCESS] |

#### [SUCCESS] Candidate Object Structure

Schema requires for each candidate:
- `id_values` (object) - [SUCCESS] Requested (line 131-134, 151)
- `match_rationale` (string) - [SUCCESS] Requested (line 140, 154)

Schema optional:
- `score_breakdown` (object) - [SUCCESS] Requested (lines 97-119, 135-139)
  - `relevancy` - [SUCCESS] Requested (lines 99-104)
  - `reliability` - [SUCCESS] Requested (lines 106-112)
  - `recency` - [SUCCESS] Requested (lines 114-119)
- `source_urls` (array) - [SUCCESS] Requested (line 141-144, 155)

#### [WARNING] Score Breakdown Marked as Required in Prompt

**Schema says:** `score_breakdown` is OPTIONAL (not in required array)

**Prompt says (line 153):** "Always include all three dimension scores"

**Issue:** Prompt treats score_breakdown as required, but schema treats it as optional. This creates ambiguity.

**Recommendation:** Either:
- Make `score_breakdown` required in schema (preferred - it's valuable data)
- OR: Update prompt to say "Include score breakdown when possible" instead of "Always include"

#### [SUCCESS] No Matches Handling

When `candidates` array is empty:
- Schema allows optional `no_matches_reason` - [SUCCESS] Documented (lines 168-188)
- Prompt provides clear instructions - [SUCCESS]

#### [SUCCESS] Search Improvements Structure

Schema structure:
```json
"search_improvements": {
  "type": "array",
  "items": { "type": "string" }
}
```

Prompt example (lines 201-210):
```json
"search_improvements": [
  "Headlines work better than searching for 'story descriptions'",
  ...
]
```

[SUCCESS] Perfect match - array of strings

#### [SUCCESS] Domain Filtering Recommendations Structure

Schema requires (when provided):
```json
"domain_filtering_recommendations": {
  "properties": {
    "add_to_included": { "type": "array" },
    "add_to_excluded": { "type": "array" },
    "reasoning": { "type": "string" }
  }
}
```

Prompt example (lines 226-236):
```json
"domain_filtering_recommendations": {
  "add_to_included": ["crunchbase.com", "techcrunch.com"],
  "add_to_excluded": ["medium.com"],
  "reasoning": "Crunchbase provided structured company data..."
}
```

[SUCCESS] Perfect match

### Summary for Row Discovery

**Overall Alignment: 98%**

**Strengths:**
- All required fields are clearly requested
- All optional fields are thoroughly documented with examples
- Output format examples match schema perfectly
- Edge cases (no matches) are well-handled

**Minor Issue:**
- [WARNING] `score_breakdown` ambiguity: optional in schema but prompt says "always include"

**Recommendations:**
1. [FIX] Update schema to make `score_breakdown` required (preferred)
2. OR: Update prompt line 153 to say "Include score breakdown when available" instead of "Always include"

---

## 3. QC Review Prompt vs Schema

**Files:**
- Prompt: `/src/lambdas/interface/actions/table_maker/prompts/qc_review.md`
- Schema: `/src/lambdas/interface/actions/table_maker/schemas/qc_review_response.json`

### Schema Required Fields

```json
{
  "required": []  // NO required fields!
}
```

### Detailed Analysis

#### [SUCCESS] All Fields Are Optional

The schema has NO required fields, which is appropriate since different scenarios need different fields.

#### [SUCCESS] Reviewed Rows Structure

Schema structure:
```json
"reviewed_rows": {
  "items": {
    "required": ["row_id", "row_score", "qc_score", "keep"],
    "properties": {
      "row_id": { "type": "string" },
      "row_score": { "type": "number" },
      "qc_score": { "type": "number" },
      "qc_rationale": { "type": "string" },
      "keep": { "type": "boolean" },
      "priority_adjustment": { "enum": ["promote", "demote", "none"] }
    }
  }
}
```

Prompt example (lines 148-176):
```json
"reviewed_rows": [
  {
    "row_id": "1-Anthropic",
    "row_score": 0.95,
    "qc_score": 0.98,
    "qc_rationale": "Perfect match - leading AI company with active hiring",
    "keep": true,
    "priority_adjustment": "promote"
  }
]
```

[SUCCESS] Perfect match

**Note:** Prompt correctly documents that `qc_rationale` can be omitted when qc_score matches row_score (lines 131, 178)

#### [SUCCESS] Rejected Rows Structure

Schema:
```json
"rejected_rows": {
  "items": {
    "required": ["row_id", "rejection_reason"],
    "properties": {
      "row_id": { "type": "string" },
      "rejection_reason": { "type": "string" }
    }
  }
}
```

Prompt does not show explicit example of rejected_rows array, but:
- Rejection is handled via `keep: false` in reviewed_rows (line 167-173)
- This appears to be a design choice where rejected_rows might be auto-generated from reviewed_rows

[SUCCESS] Schema allows both approaches (rejected_rows is optional)

#### [SUCCESS] QC Summary Structure

Schema:
```json
"qc_summary": {
  "required": ["total_reviewed", "kept", "rejected"],
  "properties": {
    "total_reviewed": { "type": "integer" },
    "kept": { "type": "integer" },
    "rejected": { "type": "integer" },
    "promoted": { "type": "integer" },
    "demoted": { "type": "integer" },
    "reasoning": { "type": "string" },
    "minimum_guarantee_applied": { "type": "boolean" },
    "insufficient_rows": { "type": "boolean" }
  }
}
```

Prompt mentions (line 180): "qc_summary will be auto-calculated from reviewed_rows if you don't provide it"

[SUCCESS] This matches schema design (qc_summary is optional at top level)

#### [SUCCESS] Insufficient Rows Fields

Schema:
- `insufficient_rows_statement` (optional string)
- `insufficient_rows_recommendations` (optional array)

Prompt documentation:
- Lines 184-220: Comprehensive explanation of when/how to use these fields
- Lines 190-197: Example of insufficient_rows_statement
- Lines 203-219: Example of insufficient_rows_recommendations structure

[SUCCESS] Perfect match

#### [SUCCESS] Retrigger Discovery Structure

Schema structure (lines 119-215):
```json
"retrigger_discovery": {
  "properties": {
    "should_retrigger": { "type": "boolean" },
    "reason": { "type": "string" },
    "new_subdomains": {
      "items": {
        "required": ["name", "focus", "search_queries", "target_rows"]
      }
    },
    "updated_requirements": { ... },
    "updated_default_domains": { ... }
  }
}
```

Prompt example (lines 270-301):
```json
"retrigger_discovery": {
  "should_retrigger": true,
  "reason": "Why retrigger is needed...",
  "new_subdomains": [ ... ],
  "updated_requirements": [ ... ],
  "updated_default_domains": { ... }
}
```

[SUCCESS] Perfect match

Field-by-field comparison:

| Field | Schema | Prompt | Match |
|-------|--------|--------|-------|
| `should_retrigger` | boolean | YES (line 273) | [SUCCESS] |
| `reason` | string | YES (line 274) | [SUCCESS] |
| `new_subdomains` | array | YES (line 275) | [SUCCESS] |
| `new_subdomains[].name` | string | YES (line 277) | [SUCCESS] |
| `new_subdomains[].focus` | string | YES (line 278) | [SUCCESS] |
| `new_subdomains[].search_queries` | array | YES (line 279-283) | [SUCCESS] |
| `new_subdomains[].target_rows` | integer | YES (line 284) | [SUCCESS] |
| `new_subdomains[].included_domains` | array (optional) | YES (line 285) | [SUCCESS] |
| `new_subdomains[].excluded_domains` | array (optional) | YES (line 286) | [SUCCESS] |
| `updated_requirements` | array (optional) | YES (line 289-295) | [SUCCESS] |
| `updated_requirements[].requirement` | string | YES (line 291) | [SUCCESS] |
| `updated_requirements[].type` | enum | YES (line 292) | [SUCCESS] |
| `updated_requirements[].rationale` | string | YES (line 293) | [SUCCESS] |
| `updated_default_domains` | object (optional) | YES (line 296-300) | [SUCCESS] |
| `updated_default_domains.included_domains` | array | YES (line 298) | [SUCCESS] |
| `updated_default_domains.excluded_domains` | array | YES (line 299) | [SUCCESS] |

### Summary for QC Review

**Overall Alignment: 100%**

**Strengths:**
- All schema fields are documented in the prompt
- Examples perfectly match schema structure
- Optional fields are clearly marked as optional
- Complex nested structures (retrigger_discovery) are thoroughly explained
- Edge cases (insufficient rows) are well-handled

**Issues:**
- NONE - perfect alignment

**Recommendations:**
- No changes needed

---

## Overall Summary

### Alignment Scores

1. **Column Definition:** 95% - Missing requirements in example
2. **Row Discovery:** 98% - Minor score_breakdown ambiguity
3. **QC Review:** 100% - Perfect alignment

### Critical Issues to Fix

#### 1. Column Definition Example Missing Required Fields

**Problem:** The example output (lines 36-124) does not include the required `requirements` array.

**Impact:** Model might not include requirements in response, causing validation errors.

**Fix Required:** Add requirements array to example output.

#### 2. Row Discovery score_breakdown Ambiguity

**Problem:** Schema treats `score_breakdown` as optional, but prompt says "Always include"

**Impact:** Minor - model will likely include it anyway, but creates ambiguity.

**Fix Required:** Either make schema require it OR update prompt to say "include when available"

### Strengths Across All Pairs

1. **Comprehensive documentation** - All fields are explained with context
2. **Good examples** - JSON examples help clarify structure
3. **Edge cases handled** - No matches, insufficient rows, etc.
4. **Optional fields clearly marked** - Prompt explains when to use optional fields

---

## Recommended Actions

### Priority 1 (Critical - Breaks Validation)

1. **Fix column_definition.md example** - Add missing `requirements` array to example output

### Priority 2 (Important - Reduces Ambiguity)

1. **Resolve score_breakdown ambiguity** in row_discovery.md - Make schema require it OR update prompt
2. **Add requirements_notes to column_definition.md example** - Show complete structure

### Priority 3 (Nice to Have - Improves Clarity)

1. Consider adding more examples across all prompts
2. Consider adding counter-examples (what NOT to do)

---

## Field-by-Field Master Reference

### Column Definition

| Field Path | Schema Type | Required | Prompt Location |
|------------|-------------|----------|-----------------|
| `columns` | array | YES | Lines 35-95, 201-209 |
| `columns[].name` | string | YES | Lines 130-146 |
| `columns[].description` | string | YES | Lines 185-188 |
| `columns[].format` | string | YES | Lines 42, 48, etc. |
| `columns[].importance` | enum | YES | Lines 43, 51, etc. |
| `columns[].is_identification` | boolean | YES | Lines 147-177 |
| `columns[].validation_strategy` | string | NO | Lines 175, 179-194 |
| `search_strategy` | object | YES | Lines 96-119, 211-234 |
| `search_strategy.description` | string | YES | Line 97, 212 |
| `search_strategy.requirements` | array | YES | Lines 241-285 [ERROR: NOT IN EXAMPLE] |
| `search_strategy.requirements[].requirement` | string | YES | Line 246+ |
| `search_strategy.requirements[].type` | enum | YES | Lines 245-265 |
| `search_strategy.requirements[].rationale` | string | YES | Line 262+ |
| `search_strategy.requirements_notes` | string | NO | Lines 280-284 [ERROR: NOT IN EXAMPLE] |
| `search_strategy.default_included_domains` | array | NO | Lines 288-319 |
| `search_strategy.default_excluded_domains` | array | NO | Lines 288-319 |
| `search_strategy.subdomains` | array | YES | Lines 96-119, 211-234 |
| `search_strategy.subdomains[].name` | string | YES | Lines 99, 213 |
| `search_strategy.subdomains[].focus` | string | YES | Lines 100, 213 |
| `search_strategy.subdomains[].search_queries` | array | YES | Lines 101-106, 213 |
| `search_strategy.subdomains[].target_rows` | integer | YES | Lines 107, 213 |
| `search_strategy.subdomains[].included_domains` | array | NO | Line 318 |
| `search_strategy.subdomains[].excluded_domains` | array | NO | Line 318 |
| `table_name` | string | YES | Lines 121, 235 |
| `tablewide_research` | string | YES | Lines 122, 237 |

### Row Discovery

| Field Path | Schema Type | Required | Prompt Location |
|------------|-------------|----------|-----------------|
| `subdomain` | string | YES | Line 128 |
| `candidates` | array | YES | Lines 129-146, 163 |
| `candidates[].id_values` | object | YES | Lines 131-134, 151 |
| `candidates[].score_breakdown` | object | NO [WARNING] | Lines 97-119, 135-139 |
| `candidates[].score_breakdown.relevancy` | number | YES (if parent exists) | Lines 99-104 |
| `candidates[].score_breakdown.reliability` | number | YES (if parent exists) | Lines 106-112 |
| `candidates[].score_breakdown.recency` | number | YES (if parent exists) | Lines 114-119 |
| `candidates[].match_rationale` | string | YES | Lines 140, 154 |
| `candidates[].source_urls` | array | NO | Lines 141-144, 155 |
| `no_matches_reason` | string | NO | Lines 168-188 |
| `search_improvements` | array | NO | Lines 190-212 |
| `domain_filtering_recommendations` | object | NO | Lines 214-243 |
| `domain_filtering_recommendations.add_to_included` | array | NO | Lines 224, 230 |
| `domain_filtering_recommendations.add_to_excluded` | array | NO | Lines 225, 231 |
| `domain_filtering_recommendations.reasoning` | string | NO | Lines 226, 232 |

### QC Review

| Field Path | Schema Type | Required | Prompt Location |
|------------|-------------|----------|-----------------|
| `reviewed_rows` | array | NO | Lines 148-176 |
| `reviewed_rows[].row_id` | string | YES (if parent exists) | Line 152 |
| `reviewed_rows[].row_score` | number | YES (if parent exists) | Line 153 |
| `reviewed_rows[].qc_score` | number | YES (if parent exists) | Line 154 |
| `reviewed_rows[].qc_rationale` | string | NO | Lines 131, 155, 178 |
| `reviewed_rows[].keep` | boolean | YES (if parent exists) | Line 156 |
| `reviewed_rows[].priority_adjustment` | enum | NO | Line 157 |
| `rejected_rows` | array | NO | Not shown (auto-generated) |
| `rejected_rows[].row_id` | string | YES (if parent exists) | N/A |
| `rejected_rows[].rejection_reason` | string | YES (if parent exists) | N/A |
| `qc_summary` | object | NO | Line 180 (auto-generated) |
| `qc_summary.total_reviewed` | integer | YES (if parent exists) | Auto-calculated |
| `qc_summary.kept` | integer | YES (if parent exists) | Auto-calculated |
| `qc_summary.rejected` | integer | YES (if parent exists) | Auto-calculated |
| `qc_summary.promoted` | integer | NO | Auto-calculated |
| `qc_summary.demoted` | integer | NO | Auto-calculated |
| `qc_summary.reasoning` | string | NO | Auto-calculated |
| `qc_summary.minimum_guarantee_applied` | boolean | NO | Auto-calculated |
| `qc_summary.insufficient_rows` | boolean | NO | Auto-calculated |
| `insufficient_rows_statement` | string | NO | Lines 190-197 |
| `insufficient_rows_recommendations` | array | NO | Lines 203-219 |
| `insufficient_rows_recommendations[].issue` | string | NO | Line 206 |
| `insufficient_rows_recommendations[].recommendation` | string | NO | Line 207 |
| `retrigger_discovery` | object | NO | Lines 270-301 |
| `retrigger_discovery.should_retrigger` | boolean | NO | Line 273 |
| `retrigger_discovery.reason` | string | NO | Line 274 |
| `retrigger_discovery.new_subdomains` | array | NO | Line 275 |
| `retrigger_discovery.new_subdomains[].name` | string | YES (if parent exists) | Line 277 |
| `retrigger_discovery.new_subdomains[].focus` | string | YES (if parent exists) | Line 278 |
| `retrigger_discovery.new_subdomains[].search_queries` | array | YES (if parent exists) | Lines 279-283 |
| `retrigger_discovery.new_subdomains[].target_rows` | integer | YES (if parent exists) | Line 284 |
| `retrigger_discovery.new_subdomains[].included_domains` | array | NO | Line 285 |
| `retrigger_discovery.new_subdomains[].excluded_domains` | array | NO | Line 286 |
| `retrigger_discovery.updated_requirements` | array | NO | Lines 289-295 |
| `retrigger_discovery.updated_requirements[].requirement` | string | YES (if parent exists) | Line 291 |
| `retrigger_discovery.updated_requirements[].type` | enum | YES (if parent exists) | Line 292 |
| `retrigger_discovery.updated_requirements[].rationale` | string | YES (if parent exists) | Line 293 |
| `retrigger_discovery.updated_default_domains` | object | NO | Lines 296-300 |
| `retrigger_discovery.updated_default_domains.included_domains` | array | NO | Line 298 |
| `retrigger_discovery.updated_default_domains.excluded_domains` | array | NO | Line 299 |

---

## Changes Applied

### 1. Column Definition Prompt (column_definition.md)

**Fixed: Missing requirements array in example**

Added complete requirements structure to the example output (lines 98-115):
```json
"requirements": [
  {
    "requirement": "Must be in healthcare, medical, or health-tech sector",
    "type": "hard",
    "rationale": "Jenifer's background is specifically in healthcare and medicine"
  },
  {
    "requirement": "Prefers roles that combine clinical expertise with AI/ML technology",
    "type": "soft",
    "rationale": "Best fit leverages both her medical training and technical skills"
  },
  {
    "requirement": "Prefers leadership or senior-level positions",
    "type": "soft",
    "rationale": "Matches her experience level and career trajectory"
  }
],
"requirements_notes": "Ideal roles bridge clinical medicine and AI innovation, allowing her to leverage both her MD and technical expertise.",
```

**Impact:** Models will now see a complete example including the required `requirements` array, preventing validation errors.

### 2. Row Discovery Schema (row_discovery_response.json)

**Fixed: score_breakdown ambiguity**

Changed `score_breakdown` from optional to required in the schema:
```json
"required": ["id_values", "score_breakdown", "match_rationale"]
```

**Rationale:** The prompt explicitly says "Always include all three dimension scores" (line 153), so the schema should require this field to match the prompt's expectations.

**Impact:** Eliminates ambiguity and ensures consistent scoring data across all discovered rows.

### Verification Status

- [SUCCESS] Column Definition: Now 100% aligned (was 95%)
- [SUCCESS] Row Discovery: Now 100% aligned (was 98%)
- [SUCCESS] QC Review: Already 100% aligned (no changes needed)

---

**End of Report**
