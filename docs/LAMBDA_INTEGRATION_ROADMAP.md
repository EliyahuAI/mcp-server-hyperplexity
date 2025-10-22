# Lambda Integration Roadmap - Independent Row Discovery

**Date:** October 21, 2025
**Goal:** Integrate tested local components into Lambda environment
**Constraint:** No code outside `src/` can be used in Lambda

---

## Current State Analysis

### What EXISTS in Lambda (src/lambdas/interface/actions/table_maker/)

**Keep (Good patterns):**
- `conversation.py` - S3 storage, WebSocket, runs DB integration, async wrappers
- `interview.py` - Interview handler (updated for trigger_execution)
- `config_bridge.py` - Config generation integration
- Pattern: `_add_api_call_to_runs()` for metrics tracking
- Pattern: UnifiedS3Manager for state persistence
- Pattern: WebSocket updates for real-time feedback

**Remove/Replace (Outdated):**
- `preview.py` - Old preview/refinement flow (OBSOLETE)
- `finalize.py` - Needs major updates for discovered rows
- `table_maker_lib/conversation_handler.py` - Old table generation (REPLACE)
- Anything related to preview/refinement workflow

---

## Integration Strategy

### Phase 1: Copy Local Components to Lambda (Direct Use)

**What to Copy:**

**1. Core Handlers** (`table_maker/src/` → `src/lambdas/interface/actions/table_maker/table_maker_lib/`)
```
✓ column_definition_handler.py
✓ row_discovery_stream.py
✓ row_discovery.py
✓ row_consolidator.py
✓ qc_reviewer.py
✓ prompt_loader.py (if updated)
✓ schema_validator.py (if updated)
```

**2. Schemas** (`table_maker/schemas/` → `src/lambdas/interface/actions/table_maker/schemas/`)
```
✓ column_definition_response.json
✓ row_discovery_response.json
✓ qc_review_response.json
(Keep existing interview_response.json)
```

**3. Prompts** (`table_maker/prompts/` → `src/lambdas/interface/actions/table_maker/prompts/`)
```
✓ column_definition.md
✓ row_discovery.md
✓ qc_review.md
(Keep existing interview.md)
```

**4. Config** (`table_maker/table_maker_config.json` → `src/lambdas/interface/actions/table_maker/table_maker_config.json`)
```
✓ Replace entire config with local version
```

---

### Phase 2: Create Lambda Wrappers (Thin Integration Layer)

**DO NOT modify the local components.** Just wrap them with Lambda infrastructure.

**New File:** `src/lambdas/interface/actions/table_maker/execution.py`

```python
"""
Independent Row Discovery Execution Handler.

Coordinates the 4-step pipeline with Lambda infrastructure:
1. Column Definition
2. Row Discovery
3. Consolidation
4. QC Review
"""

import logging
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response
from dynamodb_schemas import update_run_status
from websocket_client import WebSocketClient

# Import LOCAL components (no modifications)
from .table_maker_lib.column_definition_handler import ColumnDefinitionHandler
from .table_maker_lib.row_discovery import RowDiscovery
from .table_maker_lib.qc_reviewer import QCReviewer
from .table_maker_lib.prompt_loader import PromptLoader
from .table_maker_lib.schema_validator import SchemaValidator
from ai_api_client import AIAPIClient

async def execute_independent_row_discovery(
    email: str,
    session_id: str,
    conversation_id: str,
    conversation_state: Dict,
    run_key: str
):
    """
    Execute complete 4-step pipeline.

    Uses LOCAL components directly - no changes needed.
    Only adds Lambda infrastructure (S3, WebSocket, runs DB).
    """

    # Initialize components (same as local test)
    ai_client = AIAPIClient()
    prompt_loader = PromptLoader()
    schema_validator = SchemaValidator()

    column_handler = ColumnDefinitionHandler(ai_client, prompt_loader, schema_validator)
    row_discovery = RowDiscovery(ai_client, prompt_loader, schema_validator)
    qc_reviewer = QCReviewer(ai_client, prompt_loader, schema_validator)

    # Step 1: Column Definition
    websocket_update(session_id, "Step 1/4: Defining columns...")

    column_result = await column_handler.define_columns(
        conversation_context=conversation_state,
        context_web_research=conversation_state.get('context_web_research', []),
        model="claude-haiku-4-5"
    )

    _add_api_call_to_runs(session_id, run_key, column_result, 'column_definition')
    _save_to_s3(conversation_id, 'column_definition', column_result)

    # Step 2: Row Discovery
    websocket_update(session_id, "Step 2/4: Discovering rows...")

    discovery_result = await row_discovery.discover_rows(
        search_strategy=column_result['search_strategy'],
        columns=column_result['columns'],
        escalation_strategy=load_config()['row_discovery']['escalation_strategy']
    )

    # Track each round's API call
    for stream in discovery_result['stream_results']:
        for round_data in stream.get('all_rounds', []):
            _add_api_call_to_runs(session_id, run_key, round_data, 'row_discovery_round')

    _save_to_s3(conversation_id, 'discovery_results', discovery_result)

    # Step 3: Consolidation (no API calls, just processing)
    final_rows = discovery_result['final_rows']

    # Step 4: QC Review
    websocket_update(session_id, "Step 4/4: Quality control review...")

    qc_result = await qc_reviewer.review_rows(
        discovered_rows=final_rows,
        columns=column_result['columns'],
        user_context=conversation_state.get('user_request', ''),
        table_name=column_result['table_name'],
        table_purpose=column_result['search_strategy'].get('table_purpose', ''),
        tablewide_research=column_result.get('tablewide_research', '')
    )

    _add_api_call_to_runs(session_id, run_key, qc_result, 'qc_review')
    _save_to_s3(conversation_id, 'qc_results', qc_result)

    approved_rows = qc_result['approved_rows']

    # Save final table
    _create_table_csv(approved_rows, column_result['columns'])

    websocket_update(session_id, f"Complete! {len(approved_rows)} rows approved")

    return {
        'success': True,
        'table_name': column_result['table_name'],
        'row_count': len(approved_rows),
        'download_url': '...'
    }
```

**Key Points:**
- Uses LOCAL components unchanged
- Only adds Lambda wrappers (WebSocket, S3, runs DB)
- Same logic as local test, just with AWS services

---

### Phase 3: Update conversation.py

**Minimal changes to existing file:**

**Find:** `_trigger_execution()` function (around line 617)

**Replace body with:**
```python
async def _trigger_execution(...):
    from .execution import execute_independent_row_discovery

    logger.info(f"[TABLE_MAKER] Triggering independent row discovery for {conversation_id}")

    # Send starting message
    websocket_client.send_to_session(session_id, {
        'type': 'table_execution_update',
        'conversation_id': conversation_id,
        'status': 'Starting 4-step pipeline...',
        'steps': ['Column Definition', 'Row Discovery', 'Consolidation', 'QC Review']
    })

    # Execute pipeline
    result = await execute_independent_row_discovery(
        email, session_id, conversation_id,
        conversation_state, run_key
    )

    # Send completion
    websocket_client.send_to_session(session_id, {
        'type': 'table_execution_complete',
        'conversation_id': conversation_id,
        'table_data': result
    })
```

**That's it!** Minimal changes to conversation.py.

---

### Phase 4: Cleanup

**Files to DELETE:**
```
src/lambdas/interface/actions/table_maker/preview.py (OBSOLETE)
src/lambdas/interface/actions/table_maker/table_maker_lib/conversation_handler.py (REPLACE with local)
src/lambdas/interface/actions/table_maker/table_maker_lib/table_generator.py (REPLACE with local)
src/lambdas/interface/actions/table_maker/table_maker_lib/row_expander.py (OBSOLETE)
```

**Files to KEEP:**
```
conversation.py (update _trigger_execution only)
interview.py (already updated)
config_bridge.py (still needed for validation config)
context_research.py (might be useful)
```

---

## Step-by-Step Integration Plan

### Week 1: Copy and Wrap

**Day 1:**
1. Copy all 5 core handlers to table_maker_lib/
2. Copy all 3 schemas
3. Copy all 3 prompts
4. Copy config file
5. Test imports work

**Day 2:**
1. Create execution.py (thin wrapper)
2. Update conversation.py (_trigger_execution only)
3. Test in dev environment
4. Verify WebSocket messages work

**Day 3:**
1. Test with real conversation flow
2. Verify S3 storage
3. Verify runs database tracking
4. Fix any integration issues

### Week 2: Cleanup and Frontend

**Day 1:**
1. Delete obsolete files (preview.py, etc.)
2. Update imports
3. Test still works

**Day 2:**
1. Consolidate documentation
2. Update deployment scripts
3. Deploy to dev

**Day 3:**
1. Frontend updates for new WebSocket messages
2. End-to-end testing
3. Production deployment

---

## What NOT to Change

**DON'T modify the local components** (column_definition_handler.py, row_discovery.py, etc.)

They work perfectly. Just:
- Copy them to Lambda
- Wrap with Lambda infrastructure
- Use them as-is

**The local components are the SOURCE OF TRUTH.**

---

## Integration Checklist

### Pre-Integration
- [ ] All local tests passing
- [ ] Cost tracking accurate
- [ ] QC working correctly
- [ ] Documentation complete

### Integration
- [ ] Copy 5 handlers to table_maker_lib/
- [ ] Copy 3 schemas
- [ ] Copy 3 prompts
- [ ] Copy config
- [ ] Create execution.py wrapper
- [ ] Update conversation.py (minimal)
- [ ] Test in dev

### Cleanup
- [ ] Delete preview.py
- [ ] Delete old conversation_handler.py
- [ ] Delete row_expander.py
- [ ] Update imports
- [ ] Consolidate docs

### Frontend
- [ ] Update for new WebSocket messages
- [ ] Remove refinement UI
- [ ] Test end-to-end

---

**Estimated Time:** 2-3 days for full integration + cleanup + frontend

**Risk:** Low - local components are tested and working, just need Lambda wrappers
