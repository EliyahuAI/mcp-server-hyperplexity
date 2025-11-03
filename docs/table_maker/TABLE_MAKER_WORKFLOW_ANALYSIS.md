# Table Maker Workflow Analysis - Backend & Frontend

**Version:** 2.5 (With Background Research Phase)
**Date:** October 31, 2025

---

## Current Workflow (Before Background Research)

### Normal Execution Flow

```
Interview → Column Definition → Row Discovery → QC Review → Complete
   (0)           (Step 1)          (Step 2)       (Step 3)    (Step 4)
```

**Steps:**
1. **Interview** (conversation.py): User discusses table requirements
2. **Column Definition** (execution.py → column_definition_handler.py):
   - Uses sonar-pro with web search to find authoritative lists
   - Defines columns, search strategy, subdomains
3. **Row Discovery** (row_discovery.py): Find entities across subdomains
4. **QC Review** (qc_reviewer.py): Review discovered rows

---

## New Workflow (With Background Research)

### Normal Execution Flow

```
Interview → Background Research → Column Definition → Row Discovery → QC Review → Complete
   (0)           (Step 1)              (Step 2)          (Step 3)      (Step 4)    (Step 5)
```

**Steps:**
1. **Interview** (conversation.py): User discusses table requirements
2. **Background Research** (NEW - execution.py → background_research_handler.py):
   - Uses sonar-pro (or claude-sonnet-4-5) with web search
   - Finds authoritative sources and starting tables
   - Extracts ACTUAL sample entities (not just URLs)
   - Output stored in S3 and passed to column definition
3. **Column Definition** (execution.py → column_definition_handler.py):
   - NOW uses claude-sonnet-4-5 WITHOUT web search
   - Receives formatted research output as input
   - Uses starting tables to design subdomains
   - Defines columns based on sample entities
4. **Row Discovery** (row_discovery.py): Find entities across subdomains
5. **QC Review** (qc_reviewer.py): Review discovered rows

---

## Retrigger Scenarios

### Scenario 1: QC Requests Additional Discovery (Retrigger)

**Current Flow:**
```
QC Review (0 rows insufficient)
    ↓
QC returns: retrigger_discovery = true
    ↓
execution.py: Modifies column_definition_result
    ↓
- Adds new subdomains suggested by QC
- Updates requirements if needed
- Updates domain filtering if needed
    ↓
Row Discovery runs AGAIN with new subdomains
    ↓
Merge new rows with existing rows
    ↓
QC Review runs AGAIN (with retrigger_allowed=false)
```

**Key Points:**
- ✅ Does NOT re-run column definition from scratch
- ✅ Only modifies the existing column_definition_result
- ✅ QC suggests NEW subdomains to explore
- ✅ Does NOT repeat background research (CORRECT BEHAVIOR)

**With New Background Research Phase:**
- ✅ Should still NOT re-run background research
- ✅ Should NOT re-run column definition
- ✅ Only add new subdomains and re-run discovery
- ✅ Background research output remains valid (it's about the domain, not the specific subdomains)

---

### Scenario 2: QC Decides to Restructure (0 Rows Autonomous Recovery)

**Current Flow:**
```
QC Review (0 approved rows)
    ↓
QC analyzes: Is this recoverable?
    ↓
    ├─ RECOVERABLE (restructure)
    │      ↓
    │  QC returns:
    │  - restructuring_guidance (column_changes, requirement_changes, search_broadening)
    │  - user_facing_message
    │      ↓
    │  execution.py returns: restructure_needed = true
    │      ↓
    │  conversation.py:
    │  - Saves restructuring_guidance to conversation_state
    │  - Triggers NEW execution from beginning
    │      ↓
    │  Column Definition runs AGAIN with guidance
    │  - Prompt receives {{RESTRUCTURING_GUIDANCE}} section
    │  - AI applies guidance to simplify/broaden table
    │      ↓
    │  Row Discovery runs with new structure
    │      ↓
    │  QC Review runs with new rows
    │
    └─ UNRECOVERABLE (give_up)
           ↓
       Show apology + "Get Started" card
```

**Key Points:**
- ✅ DOES re-run column definition from scratch (necessary - table structure changed)
- ✅ Injects restructuring_guidance into conversation_state
- ✅ Column definition prompt has {{#RESTRUCTURING_GUIDANCE}} section
- ❌ **PROBLEM:** With background research, should it re-run research?

**With New Background Research Phase - TWO OPTIONS:**

**Option A: Skip Background Research on Restructure** ✅ RECOMMENDED
```
QC decides: RECOVERABLE (restructure)
    ↓
conversation.py: Saves restructuring_guidance
    ↓
execution.py: Starts new execution
    ↓
Check: Is background_research_result already in conversation_state?
    ↓
YES → Skip background research, use cached result
    ↓
Column Definition with:
- Cached background research output
- Restructuring guidance
    ↓
Row Discovery with new structure
    ↓
QC Review
```

**Why Skip Research:**
- Background research found the authoritative sources and starting tables
- The DOMAIN hasn't changed (still AI companies, still NIH researchers, etc.)
- Only the TABLE STRUCTURE needs to change (simpler ID columns, relaxed requirements)
- Re-running research would waste time and cost (30-60s, $0.02-0.05)
- Starting tables are still valid examples

**Option B: Re-run Background Research** ❌ NOT RECOMMENDED
```
QC decides: RECOVERABLE (restructure)
    ↓
conversation.py: Saves restructuring_guidance
    ↓
execution.py: Starts new execution from Step 0
    ↓
Background Research runs AGAIN
    ↓
Column Definition with fresh research + guidance
```

**Why NOT Re-run:**
- Wastes time (adds 30-60s)
- Wastes cost (adds $0.02-0.05)
- Research findings unlikely to change
- Starting tables are still valid
- Only makes sense if restructuring guidance says "search a different domain entirely"

---

## Recommendation: Implement Option A

### Changes Needed:

1. **conversation.py** - When restructuring:
   ```python
   # Check if background_research_result exists in S3
   background_research_result = _load_from_s3_if_exists(
       storage_manager, email, session_id, conversation_id,
       'background_research_result.json'
   )

   if background_research_result:
       # Cache it in conversation_state for reuse
       conversation_state['cached_background_research'] = background_research_result
       logger.info("[RESTRUCTURE] Cached background research for reuse (skip re-run)")
   ```

2. **execution.py** - Execute_full_table_generation():
   ```python
   # Step 0: Background Research (if enabled and not cached)
   background_research_enabled = config['background_research'].get('enabled', True)
   cached_research = conversation_state.get('cached_background_research')

   if background_research_enabled and not cached_research:
       logger.info("[STEP 0] Running background research...")
       background_research_result = await background_research_handler.conduct_research(...)
       # Save to S3 and conversation_state
   elif cached_research:
       logger.info("[STEP 0] Using cached background research (restructure mode)")
       background_research_result = cached_research
   else:
       logger.info("[STEP 0] Background research disabled, skipping...")
       background_research_result = None
   ```

3. **Frontend** - Handle restructure WebSocket message:
   ```javascript
   // When receiving 'table_execution_restructure'
   case 'table_execution_restructure':
       // Clear displayed columns/rows from previous attempt
       clearColumnsAndRows();

       // Show restructure notice (not error)
       showProgressMessage(data.user_facing_message);

       // Reset progress to Step 0 (or Step 1 if research cached)
       updateProgressBar(0);

       // Wait for new execution messages
       // Will receive either:
       // - table_execution_update (step=1, background_research if not cached)
       // - table_execution_update (step=2, column_definition if research cached)
       break;
   ```

---

## Frontend WebSocket Message Sequence

### Normal Execution (With Background Research)

```
1. table_execution_update (step=1, status="Conducting background research...")
   - progress_percent: 10
   - Frontend: Show "Researching domain..."

2. table_execution_update (step=1 complete, research_summary, starting_tables)
   - progress_percent: 20
   - Frontend: Show "Background research complete"
   - Optional: Show research summary in collapsible section

3. table_execution_update (step=2, status="Defining columns...")
   - progress_percent: 25
   - Frontend: Show "Designing table structure..."

4. table_execution_update (step=2 complete, columns, table_name)
   - progress_percent: 40
   - Frontend: Show column boxes (ID/Research)

5. table_execution_update (step=3, status="Discovering rows in subdomain X...")
   - progress_percent: 45-75 (incremental)
   - Frontend: Show subdomain progress

6. table_execution_update (step=3 complete, discovered_rows)
   - progress_percent: 80
   - Frontend: Show discovered rows box

7. table_execution_update (step=4, status="QC reviewing rows...")
   - progress_percent: 85
   - Frontend: Show "Quality control in progress..."

8. table_execution_update (step=4 complete, approved_rows)
   - progress_percent: 100
   - Frontend: Update discovered rows box with approved count

9. table_execution_complete (table ready)
   - Frontend: Show CSV download + validation preview
```

### Restructure Execution (Background Research Cached)

```
1. table_execution_restructure
   - clear_previous_state: true
   - user_facing_message: "Restructuring with simpler columns..."
   - Frontend: Clear columns/rows, show restructure notice

2. table_execution_update (step=1, status="Using cached research, defining columns...")
   - progress_percent: 10
   - Frontend: Show "Restructuring table structure..."
   - NOTE: Skips background research step!

3. table_execution_update (step=1 complete, columns, table_name)
   - progress_percent: 40
   - Frontend: Show NEW column boxes

4. [Continue with steps 5-9 as normal]
```

---

## Step Numbering with Background Research

### Option 1: Always 5 Steps (Show Background Research)
```
Step 0: Interview (not counted in execution)
Step 1: Background Research (NEW)
Step 2: Column Definition
Step 3: Row Discovery
Step 4: QC Review
Total: 5 steps shown to user
```

**Pros:**
- User sees what's happening
- Transparent about research phase
- Progress bar more granular

**Cons:**
- Adds complexity to frontend
- Restructure shows different steps (skips 1)

### Option 2: Keep 4 Steps (Hide Background Research) ✅ RECOMMENDED
```
Step 0: Background Research (internal, not shown)
Step 1: Column Definition
Step 2: Row Discovery
Step 3: QC Review
Total: 4 steps shown to user (consistent with current)
```

**Pros:**
- Frontend unchanged (still 4 steps)
- Consistent numbering in restructure
- Simpler UX
- Background research is internal detail

**Cons:**
- User doesn't see research phase explicitly
- Progress jumps from 0% → 25% during research

**Recommendation:** Use Option 2 - Keep 4 visible steps, run background research as Step 0 internally.

---

## Configuration for Restructure Behavior

Add to `table_maker_config.json`:

```json
{
  "background_research": {
    "enabled": true,
    "cache_for_restructure": true,
    "_note_cache": "When true, restructure will reuse cached research instead of re-running (saves time/cost)"
  }
}
```

---

## Summary of Required Changes

### Backend:

1. **execution.py:**
   - Add Step 0: Background Research (before column definition)
   - Check for cached_background_research in conversation_state
   - Skip research if cached (restructure mode)
   - Pass research output to column definition handler

2. **conversation.py:**
   - When restructuring, load background_research_result from S3
   - Cache it in conversation_state for reuse
   - Log that research is being reused

3. **column_definition_handler.py:**
   - Accept background_research_result parameter
   - Format and inject into prompt as {{BACKGROUND_RESEARCH}}
   - Update prompt to use this instead of doing web search

4. **S3 Storage:**
   - Save background_research_result.json after research phase
   - Load it on restructure for caching

### Frontend:

1. **WebSocket Handlers:**
   - Update step numbering (keep 4 visible steps)
   - Handle background research progress (Step 0, internal)
   - Show research phase status in progress bar (0% → 25%)
   - On restructure, show "Using previous research, restructuring table..."

2. **Progress Bar:**
   - Step 1 starts at 25% (after research completes)
   - Research runs from 0% → 25% (internal)
   - On restructure with cached research, starts at 10%

---

## Testing Scenarios

1. **Normal Flow with Research:**
   - Run complete flow from interview to completion
   - Verify background research runs first
   - Verify research output used by column definition
   - Verify 5 total steps (0=research, 1-4=existing)

2. **Restructure with Cached Research:**
   - Force 0 rows to trigger restructure
   - Verify research is NOT re-run
   - Verify cached research is loaded from S3
   - Verify column definition receives cached research
   - Verify restructuring guidance is applied

3. **Retrigger (No Restructure):**
   - Force QC retrigger (insufficient rows)
   - Verify background research is NOT touched
   - Verify column definition is NOT re-run
   - Verify only new subdomains added and discovery re-run

4. **Legacy Mode (Research Disabled):**
   - Set background_research.enabled = false
   - Verify system falls back to old behavior
   - Verify column definition does web search itself

---

## Cost & Time Impact

### Before (Current):
- Column Definition with web search: 30-60s, $0.01-0.03
- Total execution time: 2-3 minutes

### After (With Background Research):
- Background Research: 30-60s, $0.02-0.05
- Column Definition (no web search): 10-20s, $0.005-0.01
- Total execution time: 2.5-3.5 minutes (+30-60s)

### On Restructure:
- WITHOUT caching: +60s, +$0.05 (research runs again)
- WITH caching: +0s, +$0.00 (research reused) ✅ RECOMMENDED

**Net savings on restructure: 60s and $0.05**
