# Independent Row Discovery - Requirements Document

**Status:** Draft for Approval
**Branch:** `feature/independent-row-discovery`
**Date:** October 20, 2025

---

## Executive Summary

Transform table generation from an iterative refinement process into a **two-phase approval workflow**:
1. **Conversation Phase** - Quick back-and-forth to get user approval on table concept
2. **Execution Phase** - One-shot pipeline that delivers a complete, validated table

**Key Change:** No refinement after execution starts. All changes happen during conversation.

---

## Problem Statement

### Current Issues
1. **Quality Drop-Off:** Preview shows 3 good rows, then additional rows are poor quality
2. **Confusing Workflow:** Preview → Refine → Generate Again → Validate (what's the difference?)
3. **Repeated Tables:** User sees table multiple times with inconsistent quality
4. **False Expectations:** Preview sold as "sample of quality" but final table doesn't match
5. **Row Generation Coupled:** Table generator does BOTH column design AND row discovery

### Core Problem
The LLM trying to generate rows inline with column definitions produces poor quality because:
- It's doing two different tasks simultaneously (structure + content)
- It doesn't have systematic web search for each row
- The "additional_rows" are an afterthought, not a primary focus

---

## Proposed Solution

### Two-Phase Workflow

#### Phase 1: Conversation & Approval (Fast, Interactive)
**Duration:** 1-3 turns, ~10-30 seconds per turn
**Purpose:** Get agreement on WHAT to build

**User sees:**
```
AI: "I understand you want to research [CONCEPT].
     I'll create a table with:
     - ID columns: Company Name, Website
     - Research questions: Is hiring for AI?, Team size, Recent funding
     - ~20 companies in [DOMAIN]

     Does this match your needs?"
```

**User responds:**
- ✅ "Yes, go ahead" → Proceed to Phase 2
- 🔄 "Change X to Y" → Continue conversation
- ❌ "No, I want something different" → Continue conversation

**Technical:**
- Existing `interview.py` with minor schema changes
- Output: `trigger_execution` boolean (not `trigger_preview`)
- No heavy computation, no web search yet

---

#### Phase 2: Execution (Slow, Automatic, No Interaction)
**Duration:** 3-4 minutes
**Purpose:** Build the complete, validated table

**User sees progress:**
```
"Great! Give me 3-4 minutes to:
 1. Define precise columns and search strategy
 2. Discover 20 matching entities
 3. Populate all data
 4. Validate everything

[Progress bar with current step]"
```

**Pipeline Steps (All automatic, some parallel):**

```
START: User approved table concept
  ↓
Step 1: Column Definition (~30s)
  - Define precise column specs
  - Create search strategy for row discovery
  - Generate validation config (parallel)
  ↓
Step 2: Row Discovery (~90s) [PARALLEL STREAMS]
  ├─ Stream 1: AI Research Companies
  ├─ Stream 2: Healthcare AI Companies
  ├─ Stream 3: Enterprise AI Companies
  └─ ...
  ↓
  Consolidation: Deduplicate + Score + Sort → Top 20
  ↓
Step 3: Table Population (~90s)
  - Batch 1: Rows 1-10 (parallel)
  - Batch 2: Rows 11-20 (parallel)
  ↓
Step 4: Validation (~10s)
  - Apply validation config
  - Mark confidence scores
  ↓
END: Show complete, validated table
```

**User sees:**
- Complete table with 20 rows
- All columns populated
- Validation status for each cell
- Download button
- NO REFINEMENT OPTION

**If user wants changes:**
- Start a NEW conversation
- No "refine this table" loop

---

## Architectural Components

### 1. Interview Handler (Existing, Minor Changes)
**File:** `interview.py`
**Changes:**
- Schema: `trigger_execution` instead of `trigger_preview`
- Prompt: Emphasize "sketch approval" not "final design"
- Output: Simple concept description for user approval

### 2. Column Definition (New)
**File:** `column_definition.py`
**Purpose:** Define precise column specifications and search strategy
**Input:** Approved conversation context
**Output:**
```json
{
  "columns": [
    {
      "name": "Company Name",
      "description": "Official company name",
      "format": "String",
      "is_identification": true,
      "importance": "ID"
    },
    {
      "name": "Is Hiring for AI?",
      "description": "Whether company has active AI/ML job postings",
      "format": "Boolean",
      "importance": "CRITICAL",
      "validation_strategy": "Check careers page for 'AI', 'ML', 'Machine Learning' keywords"
    }
  ],
  "search_strategy": {
    "description": "Find companies in AI/ML space with active hiring",
    "subdomain_hints": ["AI Research", "Healthcare AI", "Enterprise AI"],
    "search_queries": [
      "AI companies hiring machine learning engineers",
      "artificial intelligence startups with job openings"
    ]
  },
  "table_name": "AI Companies Hiring Status"
}
```

### 3. Subdomain Analyzer (New)
**File:** `subdomain_analyzer.py`
**Purpose:** Automatically split search into parallel streams
**Input:** `search_strategy` from column definition
**Output:**
```json
{
  "subdomains": [
    {
      "name": "AI Research Companies",
      "focus": "Academic/research-focused AI companies",
      "search_queries": ["AI research labs hiring", "machine learning research companies"]
    },
    {
      "name": "Healthcare AI",
      "focus": "AI companies in healthcare/biotech",
      "search_queries": ["healthcare AI companies", "medical ML startups"]
    }
  ]
}
```

### 4. Row Discovery Stream (New)
**File:** `row_discovery_stream.py`
**Purpose:** Find and score candidate rows in ONE subdomain
**Input:**
- Subdomain definition
- Column specifications
- Search strategy
- Web search limit (e.g., 3 searches)

**Process:**
1. Execute web searches for subdomain
2. Extract candidate entities from search results
3. LLM evaluates each candidate against criteria
4. Score each candidate (0-1 match score)
5. Return scored candidates with rationale

**Output:**
```json
{
  "subdomain": "AI Research Companies",
  "candidates": [
    {
      "id_values": {
        "Company Name": "Anthropic",
        "Website": "anthropic.com"
      },
      "match_score": 0.95,
      "match_rationale": "Leading AI safety research company with active hiring for ML engineers",
      "source_urls": ["https://anthropic.com/careers", "https://..."]
    }
  ]
}
```

### 5. Row Consolidator (New)
**File:** `row_consolidator.py`
**Purpose:** Deduplicate and prioritize rows from all streams
**Input:** Results from all parallel streams
**Process:**
1. Fuzzy matching on ID columns (e.g., "Anthropic" = "Anthropic Inc." = "Anthropic PBC")
2. Merge duplicates (keep highest score, combine source URLs)
3. Filter by `min_match_score` threshold (config: 0.6)
4. Sort by match_score descending
5. Take top N (config: `target_row_count: 20`)

**Output:**
```json
{
  "final_rows": [
    {
      "id_values": {...},
      "match_score": 0.95,
      "merged_from": ["Stream 1 candidate", "Stream 3 candidate"],
      "source_urls": [...]
    }
  ],
  "deduplication_stats": {
    "total_candidates": 45,
    "duplicates_removed": 12,
    "below_threshold": 3,
    "final_count": 20
  }
}
```

### 6. Row Discovery Orchestrator (New)
**File:** `row_discovery.py`
**Purpose:** Coordinate parallel row discovery
**Process:**
1. Analyze search_strategy → identify subdomains (via subdomain_analyzer)
2. Launch parallel streams (asyncio.gather, max 5 concurrent)
3. Collect all results
4. Consolidate (via row_consolidator)
5. Return prioritized row list

### 7. Table Population (Modified)
**File:** `finalize.py`
**Changes:**
- **Remove:** Row ID generation logic
- **Accept:** `final_row_ids` as input (from row discovery)
- **Focus:** Populate data only, no discovery
- **Process:** Batch processing with progress updates

### 8. Execution Orchestrator (New)
**File:** `execution.py`
**Purpose:** Run the complete Phase 2 pipeline
**Process:**
```python
async def execute_full_table_generation(conversation_id, approved_context):
    # Step 1: Column Definition
    columns_result = await define_columns(approved_context)

    # Step 2: Parallel execution
    row_discovery_task = asyncio.create_task(
        discover_rows(columns_result['search_strategy'], columns_result['columns'])
    )
    config_generation_task = asyncio.create_task(
        generate_config(columns_result['columns'], approved_context)
    )

    rows_result, config_result = await asyncio.gather(
        row_discovery_task,
        config_generation_task
    )

    # Step 3: Table Population
    table_result = await populate_table(
        columns=columns_result['columns'],
        row_ids=rows_result['final_rows'],
        config=config_result
    )

    # Step 4: Validation
    validated_table = await validate_table(table_result, config_result)

    return validated_table
```

---

## Configuration

### Updated `table_maker_config.json`

```json
{
  "interview": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "use_web_search": false,
    "max_turns": 5,
    "emphasis": "sketch_approval"
  },
  "column_definition": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "use_web_search": true,
    "web_searches": 3
  },
  "row_discovery": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "target_row_count": 20,
    "min_match_score": 0.6,
    "max_parallel_streams": 5,
    "web_searches_per_stream": 3,
    "automatic_subdomain_splitting": true,
    "subdomain_analysis_model": "claude-sonnet-4-5"
  },
  "table_population": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 16000,
    "batch_size": 10,
    "parallel_batches": 2
  },
  "config_generation": {
    "model": "claude-sonnet-4-5",
    "parallel_with_row_discovery": true
  },
  "validation": {
    "model": "claude-sonnet-4-5",
    "confidence_threshold": 0.7
  }
}
```

---

## User Experience Flow

### Example Session

```
User: "I want to find AI companies that are hiring"

AI: "I'll create a table to track AI companies and their hiring status.

**Table Structure:**
- **ID Columns:** Company Name, Website
- **Research Questions:**
  - Is hiring for AI/ML roles?
  - Number of AI job postings
  - Recent funding (last 12 months)
  - Company focus area

I'll find approximately 20 AI companies across research, healthcare,
and enterprise sectors.

Does this match your needs?"

User: "Yes, but also add team size"

AI: "Updated! I've added 'Team Size' as a research column.

**Table Structure:**
- **ID Columns:** Company Name, Website
- **Research Questions:**
  - Is hiring for AI/ML roles?
  - Number of AI job postings
  - Team size
  - Recent funding
  - Company focus area

Ready to proceed?"

User: "Yes, go ahead"

AI: "Perfect! Give me 3-4 minutes to:
1. Define precise columns and search strategy
2. Discover 20 matching AI companies
3. Populate all data
4. Validate everything

[Progress: 1/4 - Defining columns and search strategy...]"

[90 seconds pass]

AI: "[Progress: 2/4 - Discovering companies (found 12 so far)...]"

[120 seconds pass]

AI: "[Progress: 3/4 - Populating data for 20 companies...]"

[60 seconds pass]

AI: "[Progress: 4/4 - Validating data...]"

AI: "✓ Complete! Here's your validated table with 20 AI companies.

**Summary:**
- 20 companies found across 3 sectors
- All 5 research questions answered
- 92% data validation confidence
- Download CSV below

[Table display with 20 rows × 7 columns]
[Download Button]"
```

---

## Technical Specifications

### New Schemas

#### `schemas/column_definition_response.json`
```json
{
  "type": "object",
  "required": ["columns", "search_strategy", "table_name"],
  "properties": {
    "columns": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "description", "format", "importance", "is_identification"],
        "properties": {
          "name": {"type": "string"},
          "description": {"type": "string"},
          "format": {"type": "string"},
          "importance": {"type": "string", "enum": ["ID", "CRITICAL"]},
          "is_identification": {"type": "boolean"},
          "validation_strategy": {"type": "string"}
        }
      }
    },
    "search_strategy": {
      "type": "object",
      "required": ["description", "subdomain_hints", "search_queries"],
      "properties": {
        "description": {"type": "string"},
        "subdomain_hints": {"type": "array", "items": {"type": "string"}},
        "search_queries": {"type": "array", "items": {"type": "string"}}
      }
    },
    "table_name": {"type": "string"},
    "tablewide_research": {"type": "string"}
  }
}
```

#### `schemas/row_discovery_response.json`
```json
{
  "type": "object",
  "required": ["subdomain", "candidates"],
  "properties": {
    "subdomain": {"type": "string"},
    "candidates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id_values", "match_score", "match_rationale"],
        "properties": {
          "id_values": {"type": "object"},
          "match_score": {"type": "number", "minimum": 0, "maximum": 1},
          "match_rationale": {"type": "string"},
          "source_urls": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  }
}
```

### New Prompts

#### `prompts/column_definition.md`
- Focus on precise column specifications
- Include validation strategy for each research column
- Emphasize search strategy for findability
- No sample data generation (that's row discovery's job)

#### `prompts/row_discovery.md`
- Markdown template with variables: `{{SUBDOMAIN}}`, `{{SEARCH_STRATEGY}}`, `{{COLUMNS}}`
- Instructions for match scoring (0-1 scale)
- Web search integration guidance
- Emphasis on quality over quantity

#### `prompts/subdomain_analysis.md`
- Analyze search strategy
- Identify 2-5 natural subdivisions
- Generate focused search queries per subdomain
- Balance parallelization (don't over-split)

---

## WebSocket Updates

### Phase 1: Conversation
```json
{
  "type": "table_conversation_update",
  "conversation_id": "...",
  "status": "Interview turn 2 complete",
  "trigger_execution": false,
  "follow_up_question": "Does this match your needs?",
  "table_sketch": "..."
}
```

### Phase 2: Execution Start
```json
{
  "type": "table_execution_update",
  "conversation_id": "...",
  "status": "Starting execution",
  "estimated_duration_seconds": 240,
  "steps": [
    "Define columns and search strategy",
    "Discover matching entities",
    "Populate all data",
    "Validate results"
  ]
}
```

### Phase 2: Progress Updates
```json
{
  "type": "table_execution_update",
  "conversation_id": "...",
  "status": "Discovering entities",
  "current_step": 2,
  "total_steps": 4,
  "progress_percent": 45,
  "detail": "Found 12 candidates across 3 sectors"
}
```

### Phase 2: Completion
```json
{
  "type": "table_execution_complete",
  "conversation_id": "...",
  "status": "Complete",
  "table_data": {
    "columns": [...],
    "rows": [...],  // All 20 rows fully populated
    "validation_summary": {
      "total_cells": 100,
      "validated": 92,
      "confidence_avg": 0.87
    }
  },
  "download_url": "..."
}
```

---

## Testing Strategy

### 1. Local Testing (Pre-Lambda)
**Location:** `table_maker/` standalone directory
**Purpose:** Test row discovery logic without AWS complexity

**Test Cases:**
1. Single subdomain row discovery
2. Multi-subdomain parallel discovery
3. Deduplication (same entity, different names)
4. Match score filtering
5. Search strategy parsing

**Tools:**
- pytest fixtures for mock web search results
- Snapshot testing for LLM outputs
- Performance benchmarks (target: <2 minutes for 20 rows)

### 2. Integration Testing
**Purpose:** Test full pipeline end-to-end

**Scenarios:**
1. Simple request (clear domain, 1-2 subdomains)
2. Complex request (ambiguous, 4-5 subdomains)
3. No matches found (should gracefully handle)
4. Duplicate entities across streams
5. Low match scores (below threshold)

### 3. Subagent-Driven Implementation
**Approach:** Use Claude Code Task agents for each component

**Breakdown:**
1. Agent 1: Build subdomain_analyzer.py + tests
2. Agent 2: Build row_discovery_stream.py + tests
3. Agent 3: Build row_consolidator.py + tests
4. Agent 4: Build row_discovery.py (orchestrator) + tests
5. Agent 5: Build column_definition.py + tests
6. Agent 6: Build execution.py (main pipeline) + tests
7. Agent 7: Update conversation.py, interview schema
8. Agent 8: Update finalize.py (remove row generation)
9. Agent 9: Integration testing
10. Agent 10: Update documentation

---

## Metrics & Monitoring

### New Metrics to Track
```json
{
  "row_discovery_metrics": {
    "subdomains_analyzed": 3,
    "parallel_streams": 3,
    "total_candidates_found": 45,
    "duplicates_removed": 12,
    "below_threshold": 3,
    "final_row_count": 20,
    "avg_match_score": 0.82,
    "discovery_time_seconds": 87,
    "web_searches_executed": 9
  },
  "pipeline_metrics": {
    "column_definition_time": 28,
    "row_discovery_time": 87,
    "config_generation_time": 82,
    "table_population_time": 64,
    "validation_time": 8,
    "total_execution_time": 187
  }
}
```

---

## Migration Plan

### Phase A: Build & Test Locally
1. Create new branch: `feature/independent-row-discovery`
2. Implement all new components in `table_maker/` standalone
3. Local testing with pytest
4. Benchmark performance (target: 20 rows in <2 min)

### Phase B: Lambda Integration
5. Copy components to `src/lambdas/interface/actions/table_maker/`
6. Update conversation.py, interview.py
7. Update finalize.py
8. Add new schemas, prompts

### Phase C: Testing & Validation
9. Deploy to dev environment
10. E2E testing with real searches
11. Performance validation
12. User acceptance testing

### Phase D: Documentation
13. Update TABLE_MAKER_IMPLEMENTATION_COMPLETE.md
14. Create migration guide for existing conversations
15. Update frontend documentation

---

## Success Criteria

### Functional
- [ ] Row discovery finds 20 high-quality matches
- [ ] Match scores accurately reflect fit
- [ ] Deduplication removes >90% of duplicates
- [ ] Parallel streams complete in <2 minutes
- [ ] Config generation completes in parallel
- [ ] Table population succeeds with discovered rows
- [ ] Validation runs and flags low-confidence cells

### Performance
- [ ] Total execution time: 3-4 minutes for 20 rows
- [ ] Row discovery: <2 minutes
- [ ] Web searches: <5 per subdomain
- [ ] Parallel streams: 2-5 concurrent

### Quality
- [ ] Average match score: >0.75
- [ ] No quality drop (all rows same quality)
- [ ] No repeated/duplicate entities in final list
- [ ] Source URLs provided for transparency

### User Experience
- [ ] Clear "sketch approval" in conversation
- [ ] No refinement loop confusion
- [ ] Progress updates every 15-30 seconds
- [ ] Final table is complete and validated
- [ ] User understands: "This is the table, not a preview"

---

## Open Questions for Approval

1. **Row count:** Is 20 rows the right default? Should it be configurable per request?
2. **Match score threshold:** Is 0.6 too low/high for minimum quality?
3. **Subdomain limit:** Max 5 parallel streams - is this the right balance?
4. **Conversation turns:** Should we hard-limit to 3 turns before forcing decision?
5. **Failed execution:** If row discovery finds <10 matches, should we fail or continue?
6. **Cost implications:** More web searches = higher cost. Acceptable for quality?

---

## Estimated Impact

### Development
- **New code:** ~2,000 lines
- **Modified code:** ~500 lines
- **New files:** 10
- **Modified files:** 5
- **Development time:** 12-16 hours (with subagents)

### Performance
- **Before:** Preview (3 rows) in ~30s, Full table (20 rows) in ~90s = 120s total
- **After:** Full execution (20 rows, validated) in ~210s = 210s total
- **Trade-off:** +90s but eliminates refinement loop, better quality

### Quality
- **Before:** Preview quality 8/10, Final quality 5/10 (drop-off)
- **After:** Consistent quality 8/10 (no drop-off)

### User Experience
- **Before:** Confusing (preview vs final, refinement, repeated tables)
- **After:** Clear (approve sketch, wait, get complete table)

---

**Ready for approval?** Please review and confirm:
1. Two-phase workflow (conversation → execution, no refinement)
2. Independent row discovery with parallel streams
3. Match scoring and deduplication approach
4. Testing strategy (local first, then Lambda)
5. Subagent-driven implementation
