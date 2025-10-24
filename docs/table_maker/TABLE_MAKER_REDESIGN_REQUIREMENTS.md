# Table Maker System Redesign - Master Requirements

**Version:** 3.0 Requirements
**Date:** 2025-10-24
**Status:** In Development

---

## Overview

Redesign the table maker system to improve row discovery quality, reduce false rejections, add domain filtering, and enable iterative refinement through QC retriggers.

---

## Phase 1: Core Improvements (Items 1-5)

### 1. Subdomain Clarification

**Goal:** Emphasize subdomains are soft suggestions to avoid overlap, not strict boundaries.

**Changes:**
- **column_definition.md (lines 196-234):**
  - Add section: "Subdomains are focus areas to help parallel workers avoid overlap"
  - Clarify: "Not strict boundaries - rows can come from any subdomain"
  - Purpose: Organize search space, not filter results

- **row_discovery.md (lines 36-42):**
  - Add note: "This subdomain is a suggested focus. Include relevant entities outside this focus if found."

---

### 2. Row Requirements System (Hard vs Soft)

**Goal:** Add requirements system with at least 1 requirement (can be hard or soft), bias toward soft requirements.

**Key Points:**
- **Minimum:** At least 1 requirement (hard or soft)
- **Bias:** Prefer soft requirements over hard
- **Hard requirements:** Absolute dealbreakers (use sparingly)
- **Soft requirements:** Preferences that improve scores

**Schema Changes (column_definition_response.json):**
```json
{
  "search_strategy": {
    "description": "...",
    "requirements": [
      {
        "requirement": "string describing requirement",
        "type": "hard" | "soft",
        "rationale": "why this requirement matters"
      }
    ],
    "requirements_notes": "Overall guidance about what makes a good row",
    "default_included_domains": ["domain.com"],  // Optional
    "default_excluded_domains": ["youtube.com", "reddit.com"],  // Optional
    "subdomains": [...]
  }
}
```

**Validation:**
- Minimum 1 requirement in requirements array
- Can be all soft, all hard, or mixed
- Bias guidance: "Use hard requirements sparingly - only for absolute dealbreakers"

**Prompt Changes:**
- **column_definition.md (after line 238):**
  - New section: "Row Requirements (Minimum 1 Required)"
  - Explain hard vs soft distinction
  - Bias: "Prefer soft requirements. Only use hard requirements for absolute must-haves."
  - Example hard: "Must be a US-based company"
  - Example soft: "Prefers companies with >50 employees", "Prefers recent news (last 6 months)"

- **row_discovery.md (lines 40-44):**
  - Replace `{{SEARCH_REQUIREMENTS}}` with prominent section:
    ```
    ## REQUIREMENTS (Must be visible and clear)

    ### Hard Requirements (Absolute - entity MUST meet these):
    {{HARD_REQUIREMENTS}}

    ### Soft Requirements (Preferences - better scores if met):
    {{SOFT_REQUIREMENTS}}

    **Instructions:**
    - Hard requirements are dealbreakers - don't include entities that violate these
    - Soft requirements improve scoring but aren't required
    - Include entities that meet hard requirements even if soft requirements aren't met
    ```

- **qc_review.md (after line 17):**
  - Add prominent REQUIREMENTS section at top (before row data):
    ```
    ## REQUIREMENTS FOR THIS TABLE

    ### Hard Requirements (Must Meet):
    {{HARD_REQUIREMENTS}}

    ### Soft Requirements (Preferences):
    {{SOFT_REQUIREMENTS}}

    **QC Instructions:**
    - Reject: Clear violation of hard requirements
    - Demote: Doesn't meet soft requirements well (but keep if real and meets hard requirements)
    - Approve: Meets requirements well
    ```

---

### 3. QC Changes - Use Existing promote/demote/reject System

**Goal:** Use existing priority_adjustment field (promote/demote/none) instead of adding new status field.

**Key Points:**
- Keep existing binary keep=true/false
- Use priority_adjustment to indicate quality tier:
  - **keep=true, priority=promote:** Excellent fit
  - **keep=true, priority=none:** Good fit
  - **keep=true, priority=demote:** Marginal but acceptable (meets hard requirements)
  - **keep=false, priority=none:** Rejected
- Only explain when changing from discovery score (use qc_rationale field)

**Prompt Changes:**
- **qc_review.md (lines 68-82):**
  - Clarify three tiers using existing fields:
    - Approve (keep=true, priority=promote/none): Meets requirements well
    - Demote (keep=true, priority=demote): Marginal fit but real, meets hard requirements
    - Reject (keep=false): Only for hard requirement violations, clear duplicates, fake entries
  - Add: "Only provide qc_rationale when your qc_score differs significantly from row_score"

**Code Changes:**
- **qc_reviewer.py (lines 180-220):**
  - Sort approved rows: priority=promote first (by qc_score), then priority=none, then priority=demote
  - Track demoted_count in qc_summary
  - Ensure minimum 4 rows (see item 5)

---

### 4. Perplexity Domain Filtering

**Goal:** Support domain filtering for Perplexity (using search_domain_filter) and Anthropic (in prompt text).

**Key Points:**
- Default exclusions: ["youtube.com", "reddit.com"] unless specifically needed
- Inclusion list: Optional, for authoritative sources
- Can be overridden per subdomain
- Use '-' prefix for exclusions in Perplexity API
- For Anthropic: Add to prompt text

**Testing Required First:**
- Test Perplexity API with search_domain_filter parameter locally
- Verify '-' prefix works for exclusions
- Verify format and behavior

**Schema Changes (column_definition_response.json):**
- See requirements section in item 2 above
- Add to each subdomain (optional overrides):
  ```json
  {
    "name": "...",
    "focus": "...",
    "search_queries": [...],
    "target_rows": 10,
    "included_domains": ["optional.com"],  // Override default
    "excluded_domains": ["optional.com"]   // Override default
  }
  ```

**Prompt Changes:**
- **column_definition.md (after requirements section):**
  - New section: "Domain Filtering (Optional)"
  - Explain purpose: Focus on reliable sources, avoid noise
  - Default exclusions: ["youtube.com", "reddit.com"] unless user specifically wants video/social sources
  - Good inclusions: Authoritative sources (e.g., crunchbase.com for companies, nyt.com for news)
  - Warning: "Don't over-constrain - leave empty if unsure. We can adjust based on search results."

**API Client Changes (ai_api_client.py):**
- Add parameters to call methods:
  - `include_domains: Optional[List[str]] = None`
  - `exclude_domains: Optional[List[str]] = None`
- For Perplexity:
  - Format as search_domain_filter: ["domain.com", "-excluded.com"]
  - Test locally first!
- For Anthropic:
  - Add to system prompt or user prompt:
    ```
    Domain filtering preferences:
    - Focus on these domains: {include_domains}
    - Avoid these domains: {exclude_domains}
    ```

**Row Discovery Stream Changes (row_discovery_stream.py):**
- Extract domain lists from subdomain config, fallback to search_strategy defaults
- Pass to AI client
- Collect domain_filtering_recommendations from each round

---

### 5. QC Minimum 4 Results + Insufficient Results Handling

**Goal:** Guarantee at least 4 results, handle scenario where insufficient rows generated.

**Key Points:**
- Minimum: 4 rows (configurable)
- If below minimum after QC: Promote best rejected rows to demoted status
- If still below minimum (e.g., only 2 discovered): QC provides overall statement and recommendations for rerun
- Frontend: Show results with restart button if below threshold

**Config Changes (table_maker_config.json):**
```json
{
  "qc_review": {
    "min_row_count": 4,
    "min_row_count_for_frontend": 4
  }
}
```

**QC Reviewer Changes (qc_reviewer.py):**
- After filtering by min_qc_score:
  1. Count approved + demoted rows
  2. If < min_row_count (4):
     - Sort rejected rows by qc_score descending
     - Promote top rejected rows to keep=true, priority=demote
     - Log: "Promoted {n} rejected rows to meet minimum of 4"
     - Add to qc_summary: "minimum_guarantee_applied": true
  3. If still < min_row_count_for_frontend (discovered < 4):
     - Set flag in result: "insufficient_rows": true
     - Require QC to provide: "insufficient_rows_statement" and "insufficient_rows_recommendations"

**Schema Changes (qc_review_response.json):**
```json
{
  "reviewed_rows": [...],
  "qc_summary": {
    "total_reviewed": int,
    "kept": int,
    "rejected": int,
    "promoted": int,
    "demoted": int,
    "reasoning": "string",
    "minimum_guarantee_applied": boolean,  // Added
    "insufficient_rows": boolean  // Added
  },
  "insufficient_rows_statement": "string (optional)",  // Overall assessment if < 4 rows
  "insufficient_rows_recommendations": [  // Optional array
    {
      "issue": "Search queries too specific",
      "recommendation": "Broaden queries to include related terms"
    }
  ]
}
```

**Prompt Changes (qc_review.md after line 145):**
- Add section: "Insufficient Results (if applicable)"
- If total discovered < 4:
  - Provide insufficient_rows_statement: "Overall assessment of why we got so few results"
  - Provide insufficient_rows_recommendations: Array of issues and recommendations for rerun

---

## Phase 2: QC Retrigger (Item 6)

### 6. QC Can Retrigger Discovery with De-Novo Subdomains

**Goal:** Allow QC to request new discovery round with completely new subdomains.

**Key Points:**
- QC sees: Original subdomains, which subdomains produced which results, all search improvements, all domain filtering recommendations
- QC can specify: Completely new subdomains (not modifications of existing)
- Max retriggers: 1 (prevent loops)
- On retrigger: Merge new results with existing (deduplicate)

**Schema Changes (qc_review_response.json):**
```json
{
  "reviewed_rows": [...],
  "qc_summary": {...},
  "retrigger_discovery": {  // Optional
    "should_retrigger": boolean,
    "reason": "Why retrigger is needed",
    "new_subdomains": [  // Complete subdomain definitions
      {
        "name": "New Subdomain Name",
        "focus": "What to search for",
        "search_queries": ["query 1", "query 2"],
        "target_rows": 10,
        "included_domains": ["optional"],
        "excluded_domains": ["optional"]
      }
    ],
    "updated_requirements": [  // Optional - can relax/tighten requirements
      {
        "requirement": "...",
        "type": "hard" | "soft",
        "rationale": "Why this change"
      }
    ],
    "updated_default_domains": {  // Optional
      "included_domains": ["add or replace"],
      "excluded_domains": ["add or replace"]
    }
  }
}
```

**Prompt Changes (qc_review.md after line 145):**
- New section: "Request Additional Discovery (Optional)"
- Show QC:
  - Original subdomains with results count per subdomain
  - Aggregated search_improvements from all rounds/subdomains
  - Aggregated domain_filtering_recommendations
  - Current requirements (hard/soft)
  - Current domain filters
- Instructions:
  - "If results are insufficient and you believe different searches could help, request a retrigger"
  - "Specify completely NEW subdomains (not modifications) - redesign the search strategy"
  - "You can also adjust requirements or domain filters"
  - "This will run ONE additional discovery cycle, then merge with existing results"

**Execution Changes (execution.py):**
- After QC review, check for retrigger_discovery.should_retrigger
- If true and retry_count < max_retriggers (1):
  - Log: "QC requested retrigger: {reason}"
  - Update column_definition_result:
    - Replace subdomains with new_subdomains
    - Update requirements if provided
    - Update domain filters if provided
  - Add existing approved/demoted row IDs to exclusion list
  - Re-run row discovery with updated parameters
  - Re-run QC (with retrigger_allowed=false to prevent loops)
  - Merge results (deduplicate across old + new)

---

## Phase 3: Validator Lambda Approach (Item 7)

### 7. Validator Lambda Quality Check with 2x1 Weighting

**Goal:** Use validator lambda as alternative/additional QC method.

**Key Points:**
- Config template: Basic structure, dynamically populated
- One search group with columns for existence + requirements
- Hard requirements weighted 2x soft requirements in scoring
- Boolean for existence, -2 to +2 scale for requirements
- Requirements written as statements where +2 = perfectly meets requirement

**Config Template Structure:**
```json
{
  "table_name": "{table_name}",
  "search_groups": [
    {
      "name": "Row Quality Check",
      "model": "sonar",
      "search_context_size": "low",
      "columns": [
        {
          "name": "Entity Exists",
          "type": "boolean",
          "instruction": "Does this entity actually exist? Verify sources are legitimate and entity is real."
        },
        // For each hard requirement:
        {
          "name": "Hard Req: {requirement}",
          "type": "scale",
          "scale_definition": "-2 (strongly disagree) to +2 (strongly agree)",
          "instruction": "Statement: {requirement as positive statement}. Rate how well this entity meets this requirement."
        },
        // For each soft requirement:
        {
          "name": "Soft Req: {requirement}",
          "type": "scale",
          "scale_definition": "-2 (strongly disagree) to +2 (strongly agree)",
          "instruction": "Statement: {requirement as positive statement}. Rate how well this entity meets this requirement."
        }
      ]
    }
  ]
}
```

**Scoring Formula:**
```python
# Reject if:
# - Entity Exists = False
# - Any hard requirement < 0

# Otherwise calculate qc_score:
hard_scores = [score for score in hard_req_scores]  # -2 to +2
soft_scores = [score for score in soft_req_scores]  # -2 to +2

# Normalize to 0-1: (score + 2) / 4
hard_normalized = [(s + 2) / 4 for s in hard_scores]
soft_normalized = [(s + 2) / 4 for s in soft_scores]

# Weight 2x1 (hard:soft)
total_weight = len(hard_scores) * 2 + len(soft_scores) * 1
weighted_sum = sum(h * 2 for h in hard_normalized) + sum(s * 1 for s in soft_normalized)

qc_score = weighted_sum / total_weight

# Status:
# - Reject: Entity Exists = False OR any hard < 0
# - Demote: All hard >= 0 but avg hard < 0.5 OR qc_score < 0.5
# - Approve: qc_score >= 0.5
```

**Config Changes (table_maker_config.json):**
```json
{
  "qc_review": {
    "qc_strategy": "traditional",  // "traditional" | "validator" | "both"
    "validator_qc_model": "sonar",
    "validator_qc_context": "low"
  }
}
```

**New File: table_maker_lib/validator_qc.py**
- Class: ValidatorQC
- Method: async review_rows_with_validator(discovered_rows, requirements, ...)
- Generate config from template
- Call validator lambda
- Parse results with 2x1 weighting
- Return same structure as traditional QC

**QC Reviewer Changes (qc_reviewer.py):**
- Accept qc_strategy parameter
- Conditional logic:
  - "traditional": Use existing LLM-based QC
  - "validator": Use ValidatorQC class
  - "both": Run both, merge results (intersection = approve, union = demote)

---

## Additional Requirements

### Domain Filtering Recommendations (Item 4 detail)

**Goal:** Aggregate domain recommendations across threads and pass to QC.

**Schema Changes (row_discovery_response.json):**
```json
{
  "subdomain": "...",
  "candidates": [...],
  "search_improvements": [...],
  "domain_filtering_recommendations": {  // New field
    "add_to_included": ["domain.com"],
    "add_to_excluded": ["other.com"],
    "reasoning": "Why these domain changes would help"
  }
}
```

**Aggregation (row_discovery.py):**
- Collect domain_filtering_recommendations from each subdomain result
- Aggregate across all subdomains
- Pass to QC review (in prompt)
- Save in discovery_result.json

**Pass to QC (qc_review.md):**
- Add section showing aggregated domain recommendations
- QC can use these when deciding on retrigger

---

## Testing Requirements

### Phase 1 Testing:
1. **Domain Filtering API Test (FIRST):**
   - Test Perplexity API with search_domain_filter locally
   - Verify format: ["domain.com", "-excluded.com"]
   - Verify behavior matches expectations
   - Document results before implementing

2. **Requirements System:**
   - Test with 0 hard, multiple soft requirements
   - Test with 1 hard, 0 soft requirements
   - Test with mixed hard/soft requirements
   - Verify minimum 1 requirement enforced

3. **QC Demote vs Reject:**
   - Test that marginal rows are demoted (keep=true, priority=demote)
   - Test that only clear violations are rejected (keep=false)
   - Verify sorting: promote > none > demote

4. **Minimum 4 Rows:**
   - Test with 10 discovered, 2 approved → should promote 2 rejected to demoted
   - Test with 2 discovered total → should trigger insufficient_rows handling

5. **Domain Filtering in Discovery:**
   - Test that domain filters are passed to API
   - Test subdomain overrides of defaults
   - Verify domain recommendations are collected

### Phase 2 Testing:
6. **QC Retrigger:**
   - Test retrigger request with new subdomains
   - Verify merge with existing results (no duplicates)
   - Verify max_retriggers=1 prevents infinite loops

### Phase 3 Testing:
7. **Validator QC:**
   - Test validator config generation
   - Verify 2x1 weighting formula
   - Test strategy switching (traditional/validator/both)

---

## File Locations

### Schemas:
- `src/lambdas/interface/actions/table_maker/schemas/column_definition_response.json`
- `src/lambdas/interface/actions/table_maker/schemas/row_discovery_response.json`
- `src/lambdas/interface/actions/table_maker/schemas/qc_review_response.json`

### Prompts:
- `src/lambdas/interface/actions/table_maker/prompts/column_definition.md`
- `src/lambdas/interface/actions/table_maker/prompts/row_discovery.md`
- `src/lambdas/interface/actions/table_maker/prompts/qc_review.md`

### Python Code:
- `src/shared/ai_api_client.py` - Add domain filtering support
- `src/lambdas/interface/actions/table_maker/table_maker_lib/column_definition_handler.py`
- `src/lambdas/interface/actions/table_maker/table_maker_lib/row_discovery_stream.py`
- `src/lambdas/interface/actions/table_maker/table_maker_lib/row_discovery.py` - Aggregation
- `src/lambdas/interface/actions/table_maker/table_maker_lib/qc_reviewer.py`
- `src/lambdas/interface/actions/table_maker/execution.py` - Retrigger logic
- `src/lambdas/interface/actions/table_maker/table_maker_lib/validator_qc.py` - NEW FILE

### Config:
- `src/lambdas/interface/actions/table_maker/table_maker_config.json`
- `src/lambdas/interface/actions/table_maker/validator_qc_config_template.json` - NEW FILE

---

## Success Criteria

1. **Subdomain flexibility:** Rows can come from any subdomain without strict boundaries
2. **Requirements clarity:** At least 1 requirement (hard or soft), clear distinction in prompts
3. **Reduced rejections:** Marginal rows demoted instead of rejected
4. **Domain filtering works:** Perplexity uses search_domain_filter, Anthropic uses prompt text
5. **Minimum guarantee:** Always get at least 4 rows (or clear insufficient results message)
6. **Retrigger capability:** QC can request rerun with new subdomains
7. **Validator option:** Can switch between traditional/validator/both QC strategies
8. **Proper weighting:** Validator QC uses 2x1 hard/soft weighting

---

## Implementation Order

1. **Test Perplexity domain filtering API** (blocking for rest)
2. **Update schemas** (column_definition, row_discovery, qc_review)
3. **Update prompts** (column_definition, row_discovery, qc_review)
4. **Update ai_api_client.py** with domain filtering
5. **Update row_discovery_stream.py** with domain filtering and recommendations
6. **Update qc_reviewer.py** with minimum 4 rows guarantee
7. **Update execution.py** with retrigger support
8. **Create validator_qc.py** with 2x1 weighting
9. **Update config files**
10. **Test end-to-end**
