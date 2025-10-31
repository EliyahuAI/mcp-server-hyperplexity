# Table Maker Version 2.5 - Complete Changes Summary

**Release Date:** October 31, 2025
**Major Features:** Background Research Phase + Enhanced Discoverability

---

## Overview

Version 2.5 introduces a fundamental architectural improvement: separating background research from column definition into a dedicated phase. This improves success rates by ensuring table design is based on what's actually discoverable via web search.

---

## Major Changes

### 1. Background Research Phase (NEW - Step 0)

**What:** Dedicated research step that runs BEFORE column definition

**Purpose:** Find authoritative sources and starting tables to guide table design

**Implementation:**
- New handler: `background_research_handler.py`
- New prompt: `prompts/background_research.md`
- New schema: `schemas/background_research_response.json`
- Runs with sonar-pro (configurable)
- Output: Authoritative sources, starting tables with sample entities, discovery patterns

**Benefits:**
- Column definition knows what's findable before designing table
- Higher success rate (design based on reality)
- Sample entities guide ID column structure
- Faster column definition (no web search needed)

### 2. Research Caching on Restructure

**What:** Background research is ALWAYS reused on restructure (mandatory, not optional)

**Why:** Domain research doesn't change when table structure changes

**Saves:** 30-60s and $0.02-0.05 per restructure

**Implementation:**
- conversation.py loads research from S3 on restructure
- Caches in `conversation_state['cached_background_research']`
- execution.py checks for cache before running Step 0
- If cached: Skip research, use cached data

### 3. Sample Rows from Column Definition

**What:** Column definition extracts 5-15 sample rows from starting tables

**Purpose:** Gives QC immediate candidates without waiting for discovery

**Flow:**
1. Background research finds starting tables with sample entities
2. Column definition extracts 5-15 entities as sample_rows
3. Discovery phase finds more rows via web search
4. Merge sample_rows + discovered_rows (discovery preferred for duplicates)
5. QC reviews merged set

**Benefits:**
- QC gets candidates even if discovery struggles
- Baseline rows from curated lists (Forbes, NIH, etc.)
- Discovery can improve upon samples with better scoring

### 4. Enhanced Discoverability Guidance

**New Concepts in Prompts:**

**Design for Row Discovery:**
- Table structure determines if rows can be found
- Offload filtering to research columns
- Make row identification EASY, validation handles specifics

**Support Columns Strategy:**
- Break complex validations into discoverable steps
- Example: Institution Email Pattern → Email (85% vs 30% success)
- Example: Has AI Team → Has AI Ethics Program (70% vs 40% success)

**Implementation:**
- New sections in column_definition.md
- Comprehensive examples with success rate improvements
- Clear guidance on when to use support columns

### 5. Original Structure on Restructure

**What:** Shows the failed table structure when restructuring

**Why:** Helps AI understand what was too complex

**Includes:**
- Original ID columns
- Original research columns
- Original hard/soft requirements
- Failure reason

**Implementation:**
- conversation.py loads original column_definition_result on restructure
- Stores in `restructuring_guidance['original_columns']` and `['original_requirements']`
- column_definition_handler formats and displays in restructuring section

### 6. Proper Conditional Sections

**Problem:** Restructuring section was hardcoded in prompt (always visible)

**Solution:** Inject restructuring section as variable

**Implementation:**
- Prompt uses `{{RESTRUCTURING_SECTION}}` placeholder
- Handler builds section conditionally:
  - Normal mode: Empty string
  - Restructure mode: Full section with guidance + original structure
- Uses simple string replacement (not Mustache conditionals)

### 7. Streamlined Prompts

**Column Definition:**
- Reduced from 1115 to 427 lines (62% reduction)
- Follows PROMPT_STRUCTURING.md guidelines
- Removed redundancy
- Clearer structure (Prompt Map → Core Task → Sections → Final Reminder)

### 8. Parameter Cleanup

**Problem:** Confusion between Perplexity and Anthropic web search parameters

**Solution:** Clear documentation and separation

**Parameters:**
- `search_context_size` (low/medium/high) - FOR PERPLEXITY ONLY
- `max_web_searches` (number) - FOR ANTHROPIC ONLY

**Implementation:**
- Documented in config with clear notes
- Handlers log which parameter is being used
- Both passed to AI client (uses correct one internally)

---

## File Changes

### New Files Created

1. `src/lambdas/interface/actions/table_maker/table_maker_lib/background_research_handler.py`
2. `src/lambdas/interface/actions/table_maker/prompts/background_research.md`
3. `src/lambdas/interface/actions/table_maker/schemas/background_research_response.json`
4. `src/lambdas/interface/actions/table_maker/prompts/column_definition_BACKUP_20251031.md` (backup)
5. `docs/TABLE_MAKER_WORKFLOW_ANALYSIS.md`
6. `docs/COLUMN_DEFINITION_PROMPT_REFACTOR_PLAN.md`
7. `docs/CONVERSATION_CONTEXT_DATA_FLOW.md`
8. `docs/BACKGROUND_RESEARCH_IMPLEMENTATION_STATUS.md`
9. `docs/VERSION_2.5_CHANGES_SUMMARY.md` (this file)

### Modified Files

1. **Config:**
   - `table_maker_config.json` - Added background_research section, updated column_definition, execution steps

2. **Schemas:**
   - `schemas/column_definition_response.json` - Added sample_rows array

3. **Prompts:**
   - `prompts/column_definition.md` - Complete rewrite (1115→427 lines)

4. **Handlers:**
   - `table_maker_lib/column_definition_handler.py` - Accept research, conditional restructuring, format research
   - `execution.py` - Added Step 0, row merging, updated docstring, imports
   - `conversation.py` - Cache research + original structure on restructure

5. **Documentation:**
   - `docs/TABLE_MAKER_GUIDE.md` - Version 2.5, new workflow, updated principles
   - `docs/FRONTEND_WEBSOCKET_MESSAGES_TABLE_MAKER.md` - Version 2.5, Step 0 messages

---

## Configuration Changes

### background_research (NEW)
```json
{
  "model": "sonar-pro",
  "max_tokens": 8000,
  "search_context_size": "high",  // FOR PERPLEXITY
  "max_web_searches": 5,          // FOR ANTHROPIC
  "min_starting_tables": 2,
  "min_sample_entities_per_table": 5
}
```

### column_definition (UPDATED)
```json
{
  "model": "claude-sonnet-4-5",  // Changed from sonar-pro
  "max_tokens": 8000
  // Removed: use_web_search, web_searches, etc. (now in background_research)
}
```

### execution (UPDATED)
```json
{
  "total_steps": 4,  // User-visible (unchanged)
  "internal_step_0_name": "background_research",
  "_restructure_caching": "Research ALWAYS reused on restructure"
}
```

---

## Data Flow Changes

### Normal Execution

```
1. Interview → conversation_state saved to S3
2. Load conversation_state
3. Step 0: Background Research
   - Run research with sonar-pro
   - Save background_research_result.json to S3
4. Step 1: Column Definition
   - Load background_research_result from S3
   - Pass to column_handler.define_columns()
   - Extract sample_rows from starting tables
   - Save column_definition_result.json to S3
5. Step 2: Row Discovery
   - Merge sample_rows + discovered_rows
6. Step 3: QC Review (on merged rows)
```

### Restructure Execution

```
1. QC decides: RECOVERABLE (restructure)
2. conversation.py:
   - Load background_research_result.json from S3
   - Load column_definition_result.json from S3 (for original structure)
   - Cache research in conversation_state['cached_background_research']
   - Add original_columns and original_requirements to restructuring_guidance
   - Save updated conversation_state to S3
3. Trigger new execution
4. Load conversation_state (now has cached_background_research)
5. Step 0: SKIP (use cache)
   - Log: "Using cached background research (restructure mode)"
6. Step 1: Column Definition
   - Receives cached background_research_result
   - Builds restructuring section showing original failed structure
   - Creates new simpler table structure
7. Step 2-3: Continue as normal
```

---

## API Cost & Time Impact

### Before v2.5:
- Column Definition: 30-60s, $0.01-0.03 (with web search)
- Total: 2-3 minutes, $0.05-0.15

### After v2.5 (Normal):
- Background Research: 30-60s, $0.02-0.05
- Column Definition: 10-20s, $0.005-0.01 (no web search)
- Total: 2.5-3.5 minutes, $0.07-0.25
- **Net change: +30-60s, +$0.02-0.10**

### After v2.5 (Restructure):
- Background Research: 0s, $0.00 (cached)
- Column Definition: 10-20s, $0.005-0.01
- **Restructure saves: 30-60s, $0.02-0.05** (vs v2.4)

---

## WebSocket Message Changes

### New Fields

**Step 0 Progress:**
```json
{
  "current_step": 0,
  "status": "Researching domain...",
  "progress_percent": 5,
  "research_sources_count": 3,
  "starting_tables_count": 2
}
```

**Step 1 Starts at 30% (was 5%):**
```json
{
  "current_step": 1,
  "progress_percent": 30,  // Changed from 5%
  "status": "Defining columns using background research"
}
```

---

## Breaking Changes

### For Frontend:
- **None** - Total steps still 4, Step 0 is internal
- Progress percentages shifted slightly (Step 1 now 30% instead of 5%)
- New optional fields: `research_sources_count`, `starting_tables_count`

### For Backend:
- **column_definition_handler.define_columns()** - Now requires `background_research_result` parameter
  - Old: `define_columns(conversation_context, context_web_research, model, max_tokens)`
  - New: `define_columns(conversation_context, background_research_result, model, max_tokens)`
- Config: Removed `column_definition.use_web_search` and related params

---

## Migration Guide

### If You Have Custom Code Calling Column Definition:

**Before:**
```python
result = await column_handler.define_columns(
    conversation_context=state,
    context_web_research=items,
    model='sonar-pro',
    max_tokens=8000
)
```

**After:**
```python
# First run background research
research_result = await background_research_handler.conduct_research(
    conversation_context=state,
    context_research_items=items,
    model='sonar-pro',
    max_tokens=8000,
    search_context_size='high'
)

# Then run column definition with research
result = await column_handler.define_columns(
    conversation_context=state,
    background_research_result=research_result,
    model='claude-sonnet-4-5',
    max_tokens=8000
)
```

---

## Testing Recommendations

1. **Normal Flow:** Run complete pipeline, verify research → column def works
2. **Restructure:** Trigger 0 rows, verify research cached and reused
3. **Sample Rows:** Verify column def extracts samples from starting tables
4. **Merging:** Verify sample + discovered rows merged correctly
5. **Original Structure:** Verify failed structure shown on restructure
6. **Cost:** Verify research cost tracked, cached research saves cost

---

## Related Documentation

- `docs/TABLE_MAKER_GUIDE.md` - Updated with v2.5 workflow
- `docs/FRONTEND_WEBSOCKET_MESSAGES_TABLE_MAKER.md` - Updated with Step 0 messages
- `docs/TABLE_MAKER_WORKFLOW_ANALYSIS.md` - Detailed workflow comparison
- `docs/CONVERSATION_CONTEXT_DATA_FLOW.md` - Data flow explanation
- `docs/BACKGROUND_RESEARCH_IMPLEMENTATION_STATUS.md` - Implementation details
- `docs/COLUMN_DEFINITION_PROMPT_REFACTOR_PLAN.md` - Prompt refactor details

---

## Next Steps After Deployment

1. Monitor background research phase success rates
2. Track sample_rows usage (how many from samples vs discovery)
3. Verify research caching working on restructures
4. Collect feedback on discoverability improvements
5. Consider adding research phase to local test scripts
