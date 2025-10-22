# Migration Guide: Independent Row Discovery

**Version:** 1.0
**Date:** October 20, 2025
**Target Audience:** Developers working with the Table Maker codebase

---

## Overview

This guide helps developers migrate from the old **preview/refinement model** to the new **Independent Row Discovery** system with a four-step execution pipeline.

---

## Table of Contents

1. [What Changed](#what-changed)
2. [Breaking Changes](#breaking-changes)
3. [Code Changes Required](#code-changes-required)
4. [Configuration Updates](#configuration-updates)
5. [API Changes](#api-changes)
6. [WebSocket Message Changes](#websocket-message-changes)
7. [Database Schema Changes](#database-schema-changes)
8. [Backward Compatibility](#backward-compatibility)
9. [Migration Steps](#migration-steps)
10. [Testing Your Migration](#testing-your-migration)

---

## What Changed

### High-Level Summary

**Before (Preview/Refinement Model):**
```
Interview → Preview (3 rows) → User Refinement → Final Generation (20 rows)
```

**After (Execution Pipeline Model):**
```
Interview → User Approval → Execution (4 steps: Column → Row Discovery → Population → Validation)
```

### Key Architectural Changes

| Aspect | Old System | New System |
|--------|------------|------------|
| **User Flow** | Interview → Preview → Refine → Generate | Interview → Approve → Execute |
| **Row Generation** | LLM generates rows inline with columns | Independent row discovery via web search |
| **Phases** | 2 (Interview, Preview/Refinement) | 2 (Interview, Execution with 4 steps) |
| **Refinement** | Multiple refinement loops | No refinement (one-shot execution) |
| **WebSocket Messages** | `table_conversation_update` only | `table_conversation_update` + `table_execution_update` |
| **Trigger Field** | `trigger_preview` | `trigger_execution` |
| **Row Discovery** | None (LLM guesses) | Parallel streams with deduplication |
| **Quality** | Drops after preview | Consistent across all rows |

---

## Breaking Changes

### 1. Interview Response Schema

**Old Schema:**
```json
{
  "trigger_preview": boolean,
  "follow_up_question": string,
  "context_web_research": array,
  "processing_steps": array,
  "table_name": string
}
```

**New Schema:**
```json
{
  "trigger_execution": boolean,  // CHANGED: was trigger_preview
  "follow_up_question": string,
  "context_web_research": array,
  "processing_steps": array,
  "table_name": string
}
```

**Migration:** Update all code checking for `trigger_preview` to check `trigger_execution` instead.

### 2. Preview Endpoint Removed

**Old Endpoint:** `POST /api/table_maker/preview`

**Status:** Removed (no longer needed)

**Migration:** Use the execution pipeline instead. There is no "preview" phase anymore - execution produces the complete table.

### 3. Refinement Endpoint Removed

**Old Endpoint:** `POST /api/table_maker/refine`

**Status:** Removed (no refinement in new model)

**Migration:** Remove all calls to refinement endpoint. If user wants changes, they must start a new table.

### 4. WebSocket Message Types

**Old:** Only `table_conversation_update` used throughout

**New:**
- Phase 1 (Interview): `table_conversation_update`
- Phase 2 (Execution): `table_execution_update`

**Migration:** Update frontend to handle both message types.

### 5. Conversation State Structure

**Old conversation_state.json:**
```json
{
  "conversation_id": "...",
  "status": "preview_generated",
  "preview_data": {...},
  "table_data": {...}
}
```

**New conversation_state.json:**
```json
{
  "conversation_id": "...",
  "status": "execution_complete",
  "column_definition": {...},      // NEW
  "row_discovery": {...},         // NEW
  "table_data": {...},
  "validation": {...}              // NEW
}
```

**Migration:** Update code reading conversation state to handle new structure.

---

## Code Changes Required

### 1. Frontend Changes

#### Check for `trigger_execution` instead of `trigger_preview`

**Before:**
```javascript
if (response.trigger_preview) {
    startPreviewGeneration();
}
```

**After:**
```javascript
if (response.trigger_execution) {
    startExecutionPipeline();
}
```

#### Handle New WebSocket Message Type

**Before:**
```javascript
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'table_conversation_update') {
        handleConversationUpdate(data);
    }
};
```

**After:**
```javascript
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'table_conversation_update') {
        handleConversationUpdate(data);
    } else if (data.type === 'table_execution_update') {
        handleExecutionUpdate(data);  // NEW
    }
};
```

#### Display Execution Progress (4 Steps)

**New Code:**
```javascript
function handleExecutionUpdate(data) {
    const { current_step, total_steps, status, progress_percent } = data;

    // Update progress bar
    updateProgressBar(progress_percent);

    // Update step indicator
    updateStepIndicator(current_step, total_steps);

    // Update status message
    updateStatusMessage(status);

    // Handle completion
    if (progress_percent === 100 && data.table_data) {
        displayCompleteTable(data.table_data);
    }

    // Handle errors
    if (data.error) {
        displayError(data.error, data.failed_at_step);
    }
}
```

#### Remove Refinement UI

**Before:**
```javascript
// Refinement button and flow
<button onClick={refineTable}>Refine Table</button>
```

**After:**
```javascript
// No refinement - show "Start New Table" instead
<button onClick={startNewTable}>Start New Table</button>
```

### 2. Backend Changes

#### Import New Modules

**New Imports:**
```python
from .execution import execute_full_table_generation
from .column_definition import handle_column_definition
from .row_discovery_handler import handle_row_discovery
from .table_maker_lib.subdomain_analyzer import analyze_subdomains
from .table_maker_lib.row_discovery_stream import discover_candidates_for_subdomain
from .table_maker_lib.row_consolidator import consolidate_and_rank
from .table_maker_lib.row_discovery import discover_rows
```

#### Update Conversation Handler

**Before:**
```python
if interview_result.get('trigger_preview'):
    # Generate preview
    preview_result = await generate_preview(conversation_id)
    return preview_result
```

**After:**
```python
if interview_result.get('trigger_execution'):
    # Start execution pipeline
    execution_result = await execute_full_table_generation(
        email=email,
        session_id=session_id,
        conversation_id=conversation_id,
        run_key=run_key
    )
    return execution_result
```

#### Update Metrics Tracking

**Before:**
```python
table_maker_breakdown = {
    "interview_calls": 1,
    "preview_calls": 1,
    "expansion_calls": 0
}
```

**After:**
```python
table_maker_breakdown = {
    "interview_calls": 2,
    "column_definition_calls": 1,
    "row_discovery_calls": 3,  // One per subdomain
    "config_generation_calls": 1,
    "table_population_calls": 2,
    "validation_calls": 1
}
```

---

## Configuration Updates

### table_maker_config.json

**New Sections Added:**

```json
{
  // NEW: Column definition configuration
  "column_definition": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "use_web_search": true,
    "web_searches": 3
  },

  // NEW: Row discovery configuration
  "row_discovery": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "target_row_count": 20,
    "min_match_score": 0.6,
    "max_parallel_streams": 5,
    "web_searches_per_stream": 3,
    "automatic_subdomain_splitting": true
  },

  // MODIFIED: Table population (was row_expansion)
  "table_population": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 16000,
    "batch_size": 10,
    "parallel_batches": 2,
    "use_web_search": true
  },

  // NEW: Execution pipeline settings
  "execution": {
    "total_steps": 4,
    "estimated_duration_seconds": 240,
    "enable_parallel_step2": true
  },

  // NEW: Feature flags
  "features": {
    "enable_independent_row_discovery": true,
    "enable_parallel_step2": true
  }
}
```

**Removed Sections:**
```json
// REMOVED: preview_generation config
"preview_generation": {
  "sample_row_count": 3,
  ...
}

// REMOVED: refinement config
"refinement": {
  ...
}
```

---

## API Changes

### New Endpoints

#### 1. Execute Full Table
```
POST /api/table_maker/execute
```

**Request:**
```json
{
  "email": "user@example.com",
  "session_id": "session_123",
  "conversation_id": "table_conv_456",
  "run_key": "run_789"
}
```

**Response:**
```json
{
  "success": true,
  "conversation_id": "table_conv_456",
  "table_data": {...},
  "validation_summary": {...}
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Row discovery timeout",
  "failed_at_step": 2
}
```

#### 2. Column Definition
```
POST /api/table_maker/column_definition
```

**Request:**
```json
{
  "email": "user@example.com",
  "session_id": "session_123",
  "conversation_id": "table_conv_456"
}
```

**Response:**
```json
{
  "success": true,
  "columns": [...],
  "search_strategy": {...},
  "table_name": "..."
}
```

#### 3. Row Discovery
```
POST /api/table_maker/row_discovery
```

**Request:**
```json
{
  "email": "user@example.com",
  "session_id": "session_123",
  "conversation_id": "table_conv_456"
}
```

**Response:**
```json
{
  "success": true,
  "final_rows": [...],
  "row_discovery_metrics": {...}
}
```

### Removed Endpoints

- `POST /api/table_maker/preview` - REMOVED
- `POST /api/table_maker/refine` - REMOVED
- `POST /api/table_maker/regenerate` - REMOVED

### Modified Endpoints

#### Conversation Endpoint
```
POST /api/table_maker/conversation
```

**Changed Response:**
```json
{
  "success": true,
  "trigger_execution": true,  // Was trigger_preview
  "follow_up_question": "...",
  ...
}
```

---

## WebSocket Message Changes

### Phase 1: Interview (Unchanged)

**Message Type:** `table_conversation_update`

**Example:**
```json
{
  "type": "table_conversation_update",
  "conversation_id": "table_conv_123",
  "status": "Interview complete",
  "trigger_execution": true,  // Changed from trigger_preview
  "follow_up_question": "...",
  "table_name": "..."
}
```

### Phase 2: Execution (NEW)

**Message Type:** `table_execution_update`

**Progress Update Example:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_123",
  "current_step": 2,
  "total_steps": 4,
  "status": "Step 2/4: Discovering rows...",
  "progress_percent": 30,
  "detail": "Found 12 candidates so far"
}
```

**Completion Example:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_123",
  "current_step": 4,
  "total_steps": 4,
  "status": "Execution complete! Table is ready.",
  "progress_percent": 100,
  "table_data": {...},
  "validation_summary": {...}
}
```

**Error Example:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_123",
  "current_step": 2,
  "total_steps": 4,
  "status": "Failed at step 2: Row discovery timeout",
  "progress_percent": 50,
  "error": "Row discovery timeout after 120s",
  "failed_at_step": 2
}
```

---

## Database Schema Changes

### Runs Database (DynamoDB)

**New Fields Added:**

```python
# Conversation state fields
"column_definition": dict  # Column specs and search strategy
"row_discovery": dict      # Row discovery results and metrics
"validation": dict         # Validation results

# Metrics fields
"row_discovery_metrics": {
    "subdomains_analyzed": int,
    "parallel_streams": int,
    "total_candidates_found": int,
    "duplicates_removed": int,
    "below_threshold": int,
    "final_row_count": int,
    "avg_match_score": float,
    "discovery_time_seconds": float,
    "web_searches_executed": int
}

# Call metrics breakdown
"table_maker_breakdown": {
    "interview_calls": int,
    "column_definition_calls": int,
    "row_discovery_calls": int,  # NEW
    "config_generation_calls": int,
    "table_population_calls": int,
    "validation_calls": int
}
```

**Removed Fields:**
```python
# No longer used
"preview_data": dict  # REMOVED
"preview_generated": boolean  # REMOVED
"refinement_count": int  # REMOVED
```

---

## Backward Compatibility

### What's NOT Backward Compatible

1. **Conversation State Files** - Old conversation states cannot be resumed in new system
2. **API Endpoints** - Preview and refinement endpoints removed
3. **WebSocket Messages** - Execution messages use new format
4. **Configuration** - Old config files missing required sections

### Handling Existing Conversations

**Option 1: Force New Tables**

```python
def handle_old_conversation(conversation_id):
    conversation_state = load_conversation_state(conversation_id)

    if 'preview_data' in conversation_state:
        # Old conversation - cannot migrate
        return {
            'success': False,
            'error': 'This conversation was created with the old system. Please start a new table.',
            'migration_required': True
        }
```

**Option 2: Migration Path (if needed)**

```python
def migrate_conversation_state(old_state):
    """
    Migrate old conversation state to new format.
    Note: Cannot resume execution, but can preserve interview context.
    """
    new_state = {
        'conversation_id': old_state['conversation_id'],
        'interview_history': old_state.get('conversation_history', []),
        'status': 'interview',  # Reset to interview
        'migration_note': 'Migrated from old system'
    }

    # Cannot migrate preview_data or refinement state
    # User must approve new execution

    return new_state
```

---

## Migration Steps

### Step 1: Update Configuration

1. Backup existing `table_maker_config.json`
2. Add new sections: `column_definition`, `row_discovery`, `execution`
3. Remove old sections: `preview_generation`, `refinement`
4. Update `table_population` (was `row_expansion`)
5. Add feature flags

```bash
# Backup
cp table_maker_config.json table_maker_config.json.backup

# Update (use new template)
cp docs/examples/table_maker_config.json table_maker_config.json
```

### Step 2: Update Backend Code

1. Update imports to include new modules
2. Change `trigger_preview` checks to `trigger_execution`
3. Replace preview generation with execution pipeline
4. Remove refinement handlers
5. Update metrics tracking
6. Update WebSocket message sending

```bash
# Search for old patterns
grep -r "trigger_preview" src/lambdas/interface/actions/table_maker/
grep -r "preview_data" src/lambdas/interface/actions/table_maker/
grep -r "refinement" src/lambdas/interface/actions/table_maker/

# Replace with new patterns
# (Manual updates required based on search results)
```

### Step 3: Update Frontend Code

1. Update WebSocket message handlers
2. Change `trigger_preview` to `trigger_execution`
3. Add execution progress display (4 steps)
4. Remove refinement UI
5. Update error handling for execution failures

```javascript
// Example update
const oldCode = `
if (data.trigger_preview) {
    showPreview(data.preview_data);
}
`;

const newCode = `
if (data.trigger_execution) {
    startExecutionPipeline();
}
`;
```

### Step 4: Update Database Access

1. Update code reading conversation state
2. Add handlers for new fields: `column_definition`, `row_discovery`, `validation`
3. Update metrics aggregation to include row discovery metrics
4. Remove references to old fields: `preview_data`, `refinement_count`

### Step 5: Deploy New Code

```bash
# Deploy to dev environment first
cd deployment
./deploy_all.sh --environment dev --force-rebuild

# Test thoroughly
# - Interview flow
# - Execution pipeline (all 4 steps)
# - Error handling
# - Metrics tracking

# Deploy to production
./deploy_all.sh --environment prod --force-rebuild
```

### Step 6: Handle Existing Conversations

**Option A: Clear all old conversations**

```bash
# WARNING: This deletes all in-progress conversations
aws s3 rm s3://hyperplexity-storage/ --recursive --include "*/table_maker/conversation_*.json"
```

**Option B: Mark old conversations as invalid**

```python
# Add to conversation.py
def is_old_conversation(conversation_state):
    return 'preview_data' in conversation_state or 'refinement_count' in conversation_state

if is_old_conversation(conversation_state):
    return {
        'success': False,
        'error': 'This conversation uses the old system. Please start a new table.',
        'migration_required': True
    }
```

---

## Testing Your Migration

### Test Checklist

#### Phase 1: Interview
- [ ] Interview starts correctly
- [ ] Interview turns tracked properly
- [ ] `trigger_execution` set correctly (not `trigger_preview`)
- [ ] Table proposal shows in markdown format
- [ ] WebSocket message type is `table_conversation_update`

#### Phase 2: Execution
- [ ] Execution starts when user approves
- [ ] Step 1 (Column Definition) completes in ~30s
- [ ] Step 2 (Row Discovery + Config) runs in parallel (~90s)
- [ ] Row discovery finds candidates across multiple subdomains
- [ ] Deduplication removes duplicates correctly
- [ ] Step 3 (Table Population) fills all data columns
- [ ] Step 4 (Validation) assigns confidence scores
- [ ] WebSocket message type is `table_execution_update`
- [ ] Progress updates sent regularly (every 15-30s)
- [ ] Total execution time: 3-5 minutes

#### Row Discovery
- [ ] Subdomain analysis splits into 2-5 subdomains
- [ ] Parallel streams execute concurrently (check logs)
- [ ] Web searches executed (3 per stream)
- [ ] Candidates scored with match_score 0-1
- [ ] Fuzzy matching identifies duplicates
- [ ] Final rows sorted by match_score
- [ ] Row count matches target_row_count config

#### Metrics
- [ ] `call_metrics_list` includes all pipeline calls
- [ ] `enhanced_metrics_aggregated` shows totals
- [ ] `table_maker_breakdown` shows correct counts
- [ ] `row_discovery_metrics` populated
- [ ] Costs aggregate correctly

#### Error Handling
- [ ] Error at Step 1 caught and reported
- [ ] Error at Step 2 caught and reported
- [ ] Error at Step 3 caught and reported
- [ ] Error at Step 4 (non-fatal) handled
- [ ] `failed_at_step` field present in error messages
- [ ] Runs database marked as FAILED
- [ ] WebSocket sends error message

#### UI
- [ ] Execution progress bar shows 4 steps
- [ ] Step indicator updates correctly
- [ ] Status messages clear and informative
- [ ] Complete table displays correctly
- [ ] No refinement button shown
- [ ] "Start New Table" button works

---

## Common Migration Issues

### Issue 1: `trigger_preview` Not Found

**Symptom:** Code looks for `trigger_preview` in response

**Fix:**
```python
# Before
if response.get('trigger_preview'):
    ...

# After
if response.get('trigger_execution'):
    ...
```

### Issue 2: WebSocket Message Type Not Recognized

**Symptom:** Frontend doesn't handle execution messages

**Fix:**
```javascript
// Add handler for new message type
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'table_execution_update') {
        handleExecutionUpdate(data);
    }
};
```

### Issue 3: Old Conversation State Causes Errors

**Symptom:** Loading old conversation fails

**Fix:**
```python
# Detect and reject old conversations
if 'preview_data' in conversation_state:
    return error_response('Please start a new table')
```

### Issue 4: Missing Configuration Sections

**Symptom:** KeyError when accessing config

**Fix:**
```python
# Add defaults for new sections
config = load_config()
config.setdefault('row_discovery', {
    'target_row_count': 20,
    'min_match_score': 0.6,
    ...
})
```

### Issue 5: Metrics Not Aggregating Correctly

**Symptom:** Missing row_discovery metrics

**Fix:**
```python
# Ensure row discovery metrics are saved
conversation_state['row_discovery_metrics'] = {
    'subdomains_analyzed': len(subdomains),
    'total_candidates_found': total_candidates,
    ...
}
save_conversation_state(conversation_state)
```

---

## Rollback Plan

If migration fails, you can rollback to the old system:

### Step 1: Restore Old Code

```bash
git checkout <previous-commit>
```

### Step 2: Restore Old Configuration

```bash
cp table_maker_config.json.backup table_maker_config.json
```

### Step 3: Redeploy

```bash
cd deployment
./deploy_all.sh --environment prod --force-rebuild
```

### Step 4: Notify Users

```
System Notice: We've temporarily reverted to the previous table generation system due to technical issues. We apologize for any inconvenience.
```

---

## Support

### Getting Help

- **Documentation:** See `docs/INDEPENDENT_ROW_DISCOVERY_GUIDE.md`
- **API Reference:** See `docs/API_REFERENCE_ROW_DISCOVERY.md`
- **Implementation Details:** See `TABLE_MAKER_IMPLEMENTATION_COMPLETE.md`

### Reporting Issues

When reporting migration issues, include:

1. Error message and stack trace
2. Conversation ID (if applicable)
3. Step where failure occurred
4. CloudWatch logs excerpt
5. Request/response payloads

---

**Last Updated:** October 20, 2025
**Version:** 1.0
**Migration Support:** Active
