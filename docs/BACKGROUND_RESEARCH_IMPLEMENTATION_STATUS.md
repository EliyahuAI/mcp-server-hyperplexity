# Background Research Phase - Implementation Status

**Date:** October 31, 2025
**Feature:** Split background research from column definition into separate phase

---

## ✅ Completed

### 1. Configuration
- **table_maker_config.json**
  - Added `background_research` section (Step 0, always runs)
  - Clarified Perplexity (`search_context_size`) vs Anthropic (`max_web_searches`) parameters
  - Documented that research is ALWAYS cached on restructure (mandatory, not optional)
  - Updated `column_definition` to use claude-sonnet-4-5 without web search
  - Updated execution steps: 4 user-visible, Step 0 internal

### 2. Schemas
- **background_research_response.json** - Created
  - Enforces minimum 2 starting tables with 5+ sample entities each
  - Validates all required fields (sources, patterns, domain context)
- **column_definition_response.json** - Updated
  - Added optional `sample_rows` array for QC review
  - Rows include id_values, source, match_score, model_used

### 3. Prompts
- **background_research.md** - Created (new prompt)
  - Comprehensive examples for AI companies and NIH researchers
  - Emphasizes extracting ACTUAL sample entities (not just URLs)
  - Quality checklist and common mistakes section
- **column_definition.md** - Completely rewritten
  - Reduced from 1115 lines to 427 lines (62% reduction)
  - Proper conditional restructuring ({{RESTRUCTURING_SECTION}} injected by handler)
  - Background research input section ({{BACKGROUND_RESEARCH}})
  - Sample rows output documentation
  - Follows PROMPT_STRUCTURING.md guidelines
  - Shows original failed structure in restructure mode

### 4. Handlers
- **background_research_handler.py** - Created
  - `conduct_research()` - Runs research phase with configurable model
  - `format_research_for_column_definition()` - Formats output for injection
  - Proper Perplexity vs Anthropic parameter handling
- **column_definition_handler.py** - Updated
  - Accepts `background_research_result` parameter (required)
  - Conditionally builds restructuring section (not hardcoded in prompt)
  - Shows original failed structure in restructure mode
  - Formats research for injection via `_format_research_for_prompt()`
  - Handles `sample_rows` output from schema
  - Removed web search logic (handled by research phase)

### 5. Documentation
- **TABLE_MAKER_WORKFLOW_ANALYSIS.md** - Workflow comparison
- **COLUMN_DEFINITION_PROMPT_REFACTOR_PLAN.md** - Refactor specifications
- **CONVERSATION_CONTEXT_DATA_FLOW.md** - Data flow documentation
- **BACKGROUND_RESEARCH_IMPLEMENTATION_STATUS.md** - This file

---

## 🔄 Remaining Work

### 1. execution.py - Wire Two-Phase Flow

**Add Step 0:**
```python
async def execute_full_table_generation(...):
    # Load conversation_state
    conversation_state = _load_from_s3(..., 'conversation_state.json')

    # Check for cached research (restructure mode)
    cached_research = conversation_state.get('cached_background_research')

    if cached_research:
        logger.info("[STEP 0] Using cached background research (restructure mode)")
        background_research_result = cached_research
    else:
        logger.info("[STEP 0] Running background research...")

        # Send progress update (0% -> 25%)
        send_execution_progress(
            session_id, conversation_id,
            current_step=0, total_steps=4,
            status='Researching domain and finding authoritative sources...',
            progress_percent=5
        )

        # Initialize research handler
        background_research_handler = BackgroundResearchHandler(
            ai_client, prompt_loader, schema_validator
        )

        # Run research
        config_research = config.get('background_research', {})
        background_research_result = await background_research_handler.conduct_research(
            conversation_context=conversation_state,
            context_research_items=conversation_state.get('context_web_research', []),
            model=config_research.get('model', 'sonar-pro'),
            max_tokens=config_research.get('max_tokens', 8000),
            search_context_size=config_research.get('search_context_size', 'high'),
            max_web_searches=config_research.get('max_web_searches', 5)
        )

        # Validate success
        if not background_research_result.get('success'):
            logger.error("[STEP 0] Background research failed")
            return {'success': False, 'error': 'Background research failed'}

        # Save to S3
        _save_to_s3(
            storage_manager, email, session_id, conversation_id,
            'background_research_result.json', background_research_result
        )

        # Track API call
        _add_api_call_to_runs(
            session_id, run_key, background_research_result,
            call_type='background_research'
        )

        # Send completion update
        send_execution_progress(
            session_id, conversation_id,
            current_step=0, total_steps=4,
            status='Background research complete',
            progress_percent=25,
            research_sources_count=len(background_research_result.get('authoritative_sources', [])),
            starting_tables_count=len(background_research_result.get('starting_tables', []))
        )

    # Step 1: Column Definition (now receives research)
    logger.info("[STEP 1] Defining columns using background research...")

    column_result = await column_handler.define_columns(
        conversation_context=conversation_state,
        background_research_result=background_research_result,  # NEW
        model=config_column.get('model', 'claude-sonnet-4-5'),
        max_tokens=config_column.get('max_tokens', 8000)
    )

    # Handle sample_rows from column definition
    sample_rows = column_result.get('sample_rows', [])
    if sample_rows:
        logger.info(f"[STEP 1] Column definition provided {len(sample_rows)} sample rows")
        # Will be merged with discovery rows later

    # ... continue with Steps 2-4
```

### 2. conversation.py - Cache Research on Restructure

**When restructure triggered:**
```python
if execution_result.get('restructure_needed'):
    # Load background research from S3 for caching
    background_research_result = _load_from_s3(
        storage_manager, email, session_id, conversation_id,
        'background_research_result.json'
    )

    if not background_research_result:
        logger.error("[RESTRUCTURE] Cannot restructure - background research not found in S3")
        # Fall back to give up
        return

    # Load original column definition for reference
    column_definition_result = _load_from_s3(
        storage_manager, email, session_id, conversation_id,
        'column_definition_result.json'
    )

    original_columns = column_definition_result.get('columns', [])
    original_requirements = column_definition_result.get('search_strategy', {}).get('requirements', [])

    # Cache research and original structure in conversation_state
    conversation_state['cached_background_research'] = background_research_result
    conversation_state['restructuring_guidance'] = {
        'is_restructure': True,
        'column_changes': restructuring_guidance.get('column_changes', ''),
        'requirement_changes': restructuring_guidance.get('requirement_changes', ''),
        'search_broadening': restructuring_guidance.get('search_broadening', ''),
        'failure_reason': 'Zero rows found with previous structure',
        'original_columns': original_columns,  # NEW - for showing what failed
        'original_requirements': original_requirements  # NEW
    }

    # Save updated conversation_state
    _save_to_s3(storage_manager, ..., 'conversation_state.json', conversation_state)

    # Trigger new execution (will use cached research)
    await execute_full_table_generation(...)
```

### 3. Merge sample_rows with discovery_rows

**In execution.py after discovery completes:**
```python
# Step 2: Row Discovery
discovery_result = await row_discovery.discover_rows(...)

# Get sample rows from column definition
sample_rows = column_result.get('sample_rows', [])
discovered_rows = discovery_result.get('final_rows', [])

if sample_rows:
    logger.info(f"[MERGE] Merging {len(sample_rows)} sample rows with {len(discovered_rows)} discovered rows")

    # Merge rows - discovery takes precedence for duplicates
    merged_rows = _merge_rows_with_preference(
        sample_rows,
        discovered_rows,
        prefer_model='discovery'  # Discovery rows have better model scoring
    )

    logger.info(f"[MERGE] Final merged count: {len(merged_rows)} rows")
else:
    merged_rows = discovered_rows

# Step 3: QC Review (on merged rows)
qc_result = await qc_reviewer.review_rows(
    rows=merged_rows,  # Combined sample + discovered
    ...
)
```

### 4. WebSocket Messages

**Add research phase progress:**
```python
# When starting research
send_execution_progress(
    current_step=0,
    total_steps=4,
    status='Researching domain and finding authoritative sources...',
    progress_percent=5
)

# When research completes
send_execution_progress(
    current_step=0,
    total_steps=4,
    status='Background research complete',
    progress_percent=25,
    research_sources_count=len(sources),
    starting_tables_count=len(tables)
)

# On restructure with cached research
send_execution_progress(
    current_step=0,
    total_steps=4,
    status='Using cached research, restructuring table...',
    progress_percent=10
)
```

---

## Testing Checklist

- [ ] Normal flow: Interview → Research → Column Def → Discovery → QC
- [ ] Research produces valid starting tables with 5+ entities
- [ ] Column definition receives formatted research
- [ ] Sample rows extracted from starting tables
- [ ] Sample rows merged with discovered rows
- [ ] Restructure: Research cached in conversation_state
- [ ] Restructure: Original structure shown in prompt
- [ ] Restructure: Cached research reused (not re-run)
- [ ] WebSocket messages show research progress

---

## Key Design Decisions

1. **Research Always Runs (Not Optional)**
   - Simplifies code, better results
   - Column definition depends on research output

2. **Research Always Cached on Restructure**
   - Mandatory optimization, not configurable
   - Saves 30-60s and $0.02-0.05 per restructure
   - Domain research doesn't change when table structure changes

3. **Original Structure Shown on Restructure**
   - AI sees what failed (columns, requirements)
   - Makes it easier to understand what to fix
   - Provides concrete reference for "too complex" guidance

4. **Sample Rows from Column Definition**
   - Gives QC immediate candidates
   - Merged with discovery rows (discovery preferred)
   - Provides baseline even if discovery struggles

---

## Next Implementation Steps

1. Wire execution.py (Step 0 + caching logic)
2. Update conversation.py (cache research + original structure)
3. Implement row merging logic
4. Add WebSocket messages
5. Test end-to-end
