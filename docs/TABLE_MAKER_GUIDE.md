# Table Maker - Independent Row Discovery System

**Version:** 2.0 (Independent Row Discovery)
**Last Updated:** October 22, 2025
**Status:** Production Ready (Lambda Integrated)

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Components](#components)
4. [Configuration](#configuration)
5. [Local Testing](#local-testing)
6. [Lambda Integration](#lambda-integration)
7. [Frontend Integration](#frontend-integration)
8. [Troubleshooting](#troubleshooting)
9. [Next Steps](#next-steps)

---

## Quick Start

### What It Does

The Table Maker system generates research tables by discovering entities through web search and validating them through progressive model escalation and quality control.

**Example:** "Track AI companies that are hiring"

**Output:**
- 8-25 validated rows (company names, websites, etc.)
- Validation configuration for data quality checks
- CSV template ready for population

### 30-Second Overview

```
User Request → Interview → Column Definition → Row Discovery → QC Review → CSV + Config
                                    ↓
                          (Progressive Escalation: sonar → sonar-pro)
```

### Running a Test

```bash
cd table_maker
export ANTHROPIC_API_KEY="your-key"
python test_local_e2e_sequential.py
```

**Expected:**
- Duration: 1-3 minutes
- Cost: $0.05-0.15
- Output: 8-15 validated companies in `output/local_tests/`

---

## Architecture Overview

### The 4-Step Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Column Definition (~10-40s)                             │
│  • Define columns (ID vs data columns)                          │
│  • Create search strategy with subdomains                       │
│  • Model: claude-haiku-4-5 or sonar-pro (if web research)      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Row Discovery + Config Generation (PARALLEL)            │
│                                                                  │
│  Row Discovery (60-120s):              Config Generation (20-40s)│
│   • Process subdomains in parallel      • Build validation rules │
│   • Progressive escalation:             • Based on columns       │
│     - Level 1: sonar (low cost)        • Runs in background     │
│     - Level 2: sonar-pro (if needed)                            │
│   • Tag candidates with metadata                                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Consolidation (built into row_discovery)                │
│  • Deduplicate entities (fuzzy matching)                        │
│  • Calculate match scores                                       │
│  • Filter by threshold (default: 0.6)                           │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: QC Review (~8-15s)                                      │
│  • Review each candidate (claude-sonnet-4-5)                    │
│  • Assign qc_score, keep/reject, priority                       │
│  • Filter: keep=true AND qc_score >= 0.5                        │
│  • Flexible row count (no artificial limits)                    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Mutual Completion: Wait for Config + Generate CSV               │
│  • Wait for config generation to finish                         │
│  • Generate CSV with ID columns filled, other columns empty     │
│  • Ready for validation workflow                                │
└─────────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Progressive Escalation:** Start cheap (sonar), escalate if needed (sonar-pro)
2. **Quality Over Quantity:** QC layer ensures relevance
3. **No Row Limits:** Keep all quality rows (not arbitrarily capped at 20)
4. **Parallel Execution:** Config generation doesn't block QC
5. **Cost Tracking:** Every API call tracked with enhanced_data

---

## Components

### 1. Column Definition Handler
**File:** `table_maker/src/column_definition_handler.py`

**Purpose:** Define table structure and search strategy

**Key Features:**
- Generates columns (ID vs data columns)
- Creates subdomains for parallel discovery
- Uses web search for unknowns (via `context_web_research`)
- Model: claude-haiku-4-5 (or sonar-pro if web search needed)

**Output:**
```json
{
  "columns": [...],
  "search_strategy": {
    "subdomains": [
      {
        "name": "AI Research Companies",
        "search_queries": ["top AI research labs 2024", ...],
        "target_rows": 10
      }
    ]
  }
}
```

### 2. Row Discovery Orchestrator
**File:** `table_maker/src/row_discovery.py`

**Purpose:** Coordinate subdomain discovery with progressive escalation

**Key Features:**
- Processes subdomains (sequential or parallel)
- Implements escalation strategy from config
- Consolidates results (deduplication, scoring)
- Tracks which model/round found each candidate

**Output:**
```json
{
  "final_rows": [...],  // Consolidated, deduplicated candidates
  "stream_results": [...],  // Per-subdomain details
  "stats": {
    "total_candidates_found": 25,
    "duplicates_removed": 5,
    "below_threshold": 1
  }
}
```

### 3. Row Discovery Stream
**File:** `table_maker/src/row_discovery_stream.py`

**Purpose:** Execute progressive escalation for a single subdomain

**Key Features:**
- Level-by-level escalation (sonar → sonar-pro)
- Early stopping (if >= 75% of target found)
- Tags each candidate with model_used, round, context
- Uses web searches from subdomain.search_queries

**Escalation Logic:**
```python
Level 1: sonar-high (cheap, fast)
  → If found >= 75% of target: STOP
  → Else: Continue to Level 2

Level 2: sonar-pro-high (better quality, more expensive)
  → Always completes (final level)
```

### 4. Row Consolidator
**File:** `table_maker/src/row_consolidator.py`

**Purpose:** Deduplicate and score candidates

**Key Features:**
- Fuzzy matching on ID columns ("Anthropic" = "Anthropic Inc")
- Recalculates match scores (don't trust LLM math)
- Prefers candidates from better models
- Merges source URLs from duplicates

### 5. QC Reviewer
**File:** `table_maker/src/qc_reviewer.py`

**Purpose:** Final quality control and prioritization

**Key Features:**
- Uses claude-sonnet-4-5 (no web search)
- Reviews all consolidated candidates
- Assigns qc_score (0-1), more flexible than discovery rubric
- Can promote/demote based on strategic value
- No max_rows cutoff - keeps all quality rows

**Decision Criteria:**
- Does it match user requirements?
- Is it unique (not redundant)?
- Is it actionable (can we validate it)?
- Strategic value (good example)?

---

## Configuration

**File:** `table_maker/table_maker_config.json`

### Column Definition
```json
{
  "column_definition": {
    "model": "claude-haiku-4-5",
    "max_tokens": 12000
  }
}
```

### Row Discovery
```json
{
  "row_discovery": {
    "escalation_strategy": [
      {
        "model": "sonar",
        "search_context_size": "high",
        "min_candidates_percentage": 75  // Early stop threshold
      },
      {
        "model": "sonar-pro",
        "search_context_size": "high",
        "min_candidates_percentage": null  // Final level, always runs
      }
    ],
    "max_tokens": 16000,
    "min_match_score": 0.6  // Filter threshold after consolidation
  }
}
```

### QC Review
```json
{
  "qc_review": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 16000,
    "min_qc_score": 0.5  // Final quality threshold
  }
}
```

### Key Settings to Tune

**`min_candidates_percentage` (75):**
- Higher → More early stops (cheaper, faster, fewer rows)
- Lower → More escalations (more expensive, more rows)

**`min_match_score` (0.6):**
- Higher → Fewer candidates pass to QC (stricter)
- Lower → More candidates pass to QC (more lenient)

**`min_qc_score` (0.5):**
- Higher → Fewer final rows (stricter quality)
- Lower → More final rows (more lenient quality)

---

## Local Testing

### Prerequisites

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Optional:
export PERPLEXITY_API_KEY="pplx-..."
```

### Run Sequential Test

```bash
cd table_maker
python test_local_e2e_sequential.py
```

**What it does:**
1. Defines columns for "AI companies that are hiring"
2. Discovers rows across 3 subdomains (sequential)
3. Consolidates and deduplicates
4. QC review with Sonnet
5. Saves results to `output/local_tests/`

**Expected output:**
```
[INFO] Step 1/4: Defining columns and search strategy...
[SUCCESS] Defined 5 columns in 12.3s ($0.015)
[INFO] Step 2/4: Discovering rows (SEQUENTIAL mode)...
[INFO]   Subdomain: AI Research Companies
[INFO]     Level 1 (sonar-high): 8 candidates → Stop (80% of target)
[INFO]   Subdomain: Healthcare AI
[INFO]     Level 1 (sonar-high): 4 candidates → Continue (40%)
[INFO]     Level 2 (sonar-pro-high): 7 candidates → Stop
[SUCCESS] Discovered 25 candidates, consolidated to 19
[INFO] Step 4/4: Quality control review...
[SUCCESS] QC approved 15 rows
[SUCCESS] Total cost: $0.087, Total time: 142.5s
```

### Run Parallel Test

```bash
python test_local_e2e_parallel.py
```

**Difference:** Processes all 3 subdomains concurrently (faster)

### View Prompts

```bash
python view_prompts.py
```

Shows the exact prompts sent to each model.

---

## Lambda Integration

**Location:** `src/lambdas/interface/actions/table_maker/`

### Entry Point

**File:** `conversation.py` → `_trigger_execution()`

Called when interview completes and user approves the table.

### Execution Orchestrator

**File:** `execution.py` → `execute_full_table_generation()`

**Key differences from local:**
- Uses `UnifiedS3Manager` for state persistence
- Sends WebSocket updates for real-time feedback
- Tracks metrics in DynamoDB runs table
- Runs config generation in parallel with row discovery
- Generates CSV template at the end

**Integration pattern:**
```python
# Initialize LOCAL components (no modifications)
from .table_maker_lib.column_definition_handler import ColumnDefinitionHandler
from .table_maker_lib.row_discovery import RowDiscovery
from .table_maker_lib.qc_reviewer import QCReviewer

# Use them exactly as in local tests
column_result = await column_handler.define_columns(...)
discovery_result = await row_discovery.discover_rows(...)
qc_result = await qc_reviewer.review_rows(...)

# Add Lambda wrappers
_add_api_call_to_runs(session_id, run_key, column_result, 'Column Definition')
_save_to_s3(storage_manager, email, session_id, conversation_id, 'column_result.json', column_result)
```

### WebSocket Messages

**Progress updates:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "...",
  "current_step": 2,
  "total_steps": 4,
  "status": "Step 2/4: Discovering rows...",
  "progress_percent": 25
}
```

**Completion:**
```json
{
  "type": "table_execution_complete",
  "conversation_id": "...",
  "status": "Independent Row Discovery complete",
  "table_name": "AI Companies Hiring Status",
  "row_count": 15,
  "approved_rows": [...]
}
```

### Config Generation Integration

**Runs in parallel with row discovery:**
```python
# Start config generation in background
config_task = asyncio.create_task(
    _generate_validation_config(...)
)

# Run row discovery (blocks until complete)
discovery_result = await row_discovery.discover_rows(...)

# QC starts immediately (config still running)
qc_result = await qc_reviewer.review_rows(...)

# Wait for config to finish
config_result = await config_task

# Generate CSV with ID columns filled
```

**Benefits:**
- No added time (runs during row discovery)
- Validation config ready when rows are approved
- CSV template immediately available

---

## Frontend Integration

**Location:** `frontend/perplexity_validator_interface2.html`

### WebSocket Event Handlers

Listen for `table_execution_update` and `table_execution_complete` events.

**Progress display:**
```javascript
{
  current_step: 2,
  total_steps: 4,
  status: "Step 2/4: Discovering rows...",
  progress_percent: 25
}
```

**Completion:**
```javascript
{
  type: 'table_execution_complete',
  table_name: 'AI Companies Hiring Status',
  row_count: 15,
  approved_rows: [...],
  csv_s3_key: 'path/to/template.csv',
  config_s3_key: 'path/to/config.json'
}
```

### CSV Download

User can download the CSV template with:
- ID columns filled (Company Name, Website, etc.)
- Other columns empty (ready for manual population or validation)

---

## Troubleshooting

### Common Issues

**1. No rows discovered**

**Symptoms:** `final_rows` is empty after row discovery

**Causes:**
- Search queries too specific
- min_match_score threshold too high
- No web search results for queries

**Solutions:**
- Check `search_strategy.subdomains[].search_queries`
- Lower `min_match_score` from 0.6 to 0.5
- Add `context_web_research` items for unknowns

**2. Too many duplicates**

**Symptoms:** Many similar entities after consolidation

**Causes:**
- Fuzzy matching not catching variations
- Different subdomains finding same entities

**Solutions:**
- Review `row_consolidator.py` matching logic
- Check ID column definitions (should be unique identifiers)
- Increase `min_match_score` to filter marginal matches

**3. QC rejects too many rows**

**Symptoms:** Large gap between `final_rows` and `approved_rows`

**Causes:**
- min_qc_score too high
- User requirements unclear
- Discovery finding off-topic entities

**Solutions:**
- Lower `min_qc_score` from 0.5 to 0.4
- Improve column definitions with better descriptions
- Add more context to `table_purpose` and `tablewide_research`

**4. Progressive escalation not working**

**Symptoms:** Always escalates to sonar-pro, even when finding enough

**Causes:**
- `min_candidates_percentage` set too low
- Not finding enough candidates in Level 1

**Solutions:**
- Check `escalation_strategy[0].min_candidates_percentage` (should be 75)
- Review search queries (may be too narrow)
- Check logs for "Early stop" vs "Continue" messages

### Debug Logging

**Local:**
```bash
# View all API calls with costs
python view_prompts.py

# Check consolidation logic
grep "Deduplication" output/local_tests/latest.log

# See escalation decisions
grep "Early stop\|Continue" output/local_tests/latest.log
```

**Lambda:**
```bash
# CloudWatch logs
aws logs tail /aws/lambda/interface-lambda --follow

# Search for specific conversation
aws logs filter-pattern "{$.conversation_id = 'abc123'}"
```

### Cost Optimization

**Current costs (typical run):**
- Column Definition: $0.002-0.035 (depends on web search)
- Row Discovery: $0.01-0.06 (progressive escalation)
- QC Review: $0.015-0.035
- Config Generation: $0.01-0.03
- **Total: $0.05-0.20**

**To reduce costs:**
1. Increase `min_candidates_percentage` → More early stops
2. Reduce `target_rows` per subdomain → Less discovery needed
3. Use `max_parallel_streams=1` → Sequential (slower but cheaper)
4. Decrease number of subdomains → Fewer API calls

**To improve quality (may increase cost):**
1. Decrease `min_candidates_percentage` → More escalations
2. Increase `target_rows` → More comprehensive discovery
3. Add more subdomains → Better coverage
4. Use `search_context_size: "very_high"` → More context

---

## Next Steps

### Immediate (Already Implemented)

- ✅ Local system working end-to-end
- ✅ Lambda integration complete
- ✅ Config generation in parallel
- ✅ CSV template generation
- ✅ Cost tracking and metrics

### Near-Term Enhancements

**1. Global Counter with Exclusion**

Track discovered entities across subdomains to avoid duplicates:
```json
{
  "global_discovered": ["Anthropic", "OpenAI", ...],
  "subdomain_exclusions": {
    "Healthcare AI": ["Anthropic"]  // Don't rediscover
  }
}
```

**2. Level-by-Level Escalation**

More granular escalation across ALL subdomains:
```
Round 1: All subdomains try sonar-low
  → Aggregate results
  → If total < target: Continue to Round 2

Round 2: All subdomains try sonar-high
  → Aggregate results
  → If total < target: Continue to Round 3

Round 3: All subdomains try sonar-pro-high
  → Final round
```

**3. Enhanced QC Feedback**

QC layer provides feedback to improve future discoveries:
```json
{
  "feedback": {
    "too_broad": ["Enterprise AI subdomain finding non-AI companies"],
    "missing_types": ["No healthcare AI startups found"],
    "suggestions": ["Add subdomain for medical imaging AI"]
  }
}
```

### Long-Term

**1. Iterative Refinement**

User can refine table after initial generation:
- Add/remove columns
- Re-run discovery with new criteria
- Merge with existing rows

**2. Row Expansion**

Automatically fill data columns using web search:
- "Is Hiring?" → Check careers page
- "Team Size" → LinkedIn company page
- "Recent Funding" → Crunchbase

**3. Multi-Table Workflows**

Generate related tables in sequence:
- Table 1: AI companies
- Table 2: Key people at those companies
- Table 3: Recent products from those companies

---

## Additional Resources

### Detailed Documentation

- **Architecture:** `docs/table_maker/architecture/overview.md`
- **Components:** `docs/table_maker/components/*.md`
- **Configuration:** `docs/table_maker/configuration/config_reference.md`
- **Deployment:** `docs/table_maker/deployment/lambda_integration.md`

### Source Code

- **Local:** `table_maker/src/`
- **Lambda:** `src/lambdas/interface/actions/table_maker/`
- **Tests:** `table_maker/test_local_e2e_*.py`

### Key Files

- **Config:** `table_maker/table_maker_config.json`
- **Prompts:** `table_maker/prompts/*.md`
- **Schemas:** `table_maker/schemas/*.json`

---

**Questions?** See `docs/table_maker/` for detailed documentation or check the troubleshooting section above.
