# Conversation Context Data Flow - Normal vs Restructure

**Purpose:** Document what gets stored in conversation_context vs passed separately for original and restructuring executions.

---

## Data Sources

### 1. conversation_state (Persistent S3 Storage)

**Location:** `s3://bucket/tables/{email}/{session_id}/table_maker/{conversation_id}/conversation_state.json`

**Managed By:** conversation.py

**Contains:**
```python
{
    # Interview metadata
    'conversation_id': str,
    'session_id': str,
    'created_at': str,  # ISO timestamp
    'last_updated': str,  # ISO timestamp
    'status': str,  # 'in_progress', 'execution_ready', 'completed', 'failed'
    'turn_count': int,

    # Interview content
    'messages': List[Dict],  # Full conversation history (role, content, timestamp)
    'interview_context': Dict,  # interview_handler.get_interview_context()
    'context_web_research': List[str],  # Items user wants researched
    'trigger_execution': bool,

    # Restructuring guidance (ONLY present on restructure)
    'restructuring_guidance': {
        'is_restructure': True,
        'column_changes': str,
        'requirement_changes': str,
        'search_broadening': str,
        'previous_attempt_failed': True,
        'failure_reason': str
    },

    # Cached research (ONLY present on restructure with caching enabled)
    'cached_background_research': Dict  # Full background_research_result
}
```

### 2. Execution Results (S3 Storage - Per Phase)

**Location:** `s3://bucket/tables/{email}/{session_id}/table_maker/{conversation_id}/`

**Files:**
- `background_research_result.json` - Step 0 output
- `column_definition_result.json` - Step 1 output
- `discovery_result.json` - Step 2 output
- `qc_result.json` - Step 3 output

**These are NOT in conversation_state** - they're separate files loaded as needed.

---

## Normal Execution Flow

### Interview Phase (conversation.py)

**Builds conversation_state:**
```python
conversation_state = {
    'conversation_id': 'conv_abc123',
    'session_id': 'sess_xyz',
    'created_at': '2025-10-31T10:00:00Z',
    'status': 'in_progress',
    'turn_count': 3,
    'messages': [
        {'role': 'user', 'content': 'I want to track AI companies hiring', 'timestamp': '...'},
        {'role': 'assistant', 'content': 'What information would you like...', 'timestamp': '...'},
        # ... more turns
    ],
    'interview_context': {
        'user_goal': 'Track AI companies hiring',
        'column_outline': ['Company Name', 'Is Hiring', 'Website'],
        # ... other interview context
    },
    'context_web_research': [],  # Empty or items to research
    'trigger_execution': True  # User approved, ready to execute
}
```

**Saved to:** S3 conversation_state.json

### Execution Phase (execution.py)

**Loads conversation_state from S3, then:**

```python
# Step 0: Background Research
background_research_result = await background_research_handler.conduct_research(
    conversation_context=conversation_state,  # Pass full state
    context_research_items=conversation_state.get('context_web_research', [])
)

# Save to S3 separately (NOT in conversation_state)
_save_to_s3(storage_manager, email, session_id, conversation_id,
            'background_research_result.json', background_research_result)

# Step 1: Column Definition
column_result = await column_handler.define_columns(
    conversation_context=conversation_state,  # Pass full state
    background_research_result=background_research_result  # Pass separately!
)

# Save to S3 separately
_save_to_s3(storage_manager, email, session_id, conversation_id,
            'column_definition_result.json', column_result)

# ... Steps 2-4 continue
```

**Key Point:** Background research result is passed TO column_definition_handler as a parameter, NOT embedded in conversation_context.

---

## Restructure Execution Flow

### QC Decides to Restructure (execution.py)

**When 0 rows found:**
```python
if approved_rows == 0:
    recovery_decision = qc_result.get('recovery_decision', {})
    if recovery_decision.get('decision') == 'restructure':
        # Build result to trigger restructure
        result['restructure_needed'] = True
        result['restructuring_guidance'] = recovery_decision.get('restructuring_guidance', {})
        result['user_facing_message'] = recovery_decision.get('user_facing_message', '')
        result['conversation_state'] = conversation_state  # Pass full state back
        return result  # Return to conversation.py
```

### Conversation.py Handles Restructure

**Injects guidance into conversation_state:**
```python
if execution_result.get('restructure_needed'):
    restructuring_guidance = execution_result.get('restructuring_guidance', {})
    conversation_state = execution_result.get('conversation_state', {})

    # Option 1: Load cached background research from S3
    background_research_result = _load_from_s3(
        storage_manager, email, session_id, conversation_id,
        'background_research_result.json'
    )

    if background_research_result:
        # Cache in conversation_state for reuse
        conversation_state['cached_background_research'] = background_research_result
        logger.info("[RESTRUCTURE] Cached background research for reuse")

    # Inject restructuring guidance into conversation_state
    conversation_state['restructuring_guidance'] = {
        'is_restructure': True,
        'column_changes': restructuring_guidance.get('column_changes', ''),
        'requirement_changes': restructuring_guidance.get('requirement_changes', ''),
        'search_broadening': restructuring_guidance.get('search_broadening', ''),
        'previous_attempt_failed': True,
        'failure_reason': 'Zero rows found with previous structure'
    }

    # Save updated conversation_state to S3
    _save_to_s3(storage_manager, email, session_id, conversation_id,
                'conversation_state.json', conversation_state)

    # Trigger new execution
    await execute_full_table_generation(
        session_id, conversation_id, email, run_key
    )
```

### Second Execution (Restructure)

**Loads conversation_state (now with guidance):**
```python
# Load from S3
conversation_state = _load_from_s3(..., 'conversation_state.json')

# Check for cached research
cached_research = conversation_state.get('cached_background_research')

if cached_research:
    logger.info("[RESTRUCTURE] Using cached background research (skip Step 0)")
    background_research_result = cached_research
else:
    logger.info("[RESTRUCTURE] No cached research, running Step 0 again")
    background_research_result = await background_research_handler.conduct_research(...)

# Step 1: Column Definition (with restructuring guidance)
restructuring_guidance = conversation_state.get('restructuring_guidance', {})
is_restructure = restructuring_guidance.get('is_restructure', False)

column_result = await column_handler.define_columns(
    conversation_context=conversation_state,  # Contains restructuring_guidance!
    background_research_result=background_research_result  # Cached or fresh
)

# Handler extracts:
# - conversation_state['restructuring_guidance'] → builds RESTRUCTURING_SECTION
# - background_research_result → formats as BACKGROUND_RESEARCH
```

---

## Summary: What Goes Where

### conversation_state (S3 conversation_state.json)

**Always Present:**
- Metadata (conversation_id, session_id, timestamps, status)
- Interview history (messages, interview_context)
- Research items (context_web_research)
- Execution trigger flag

**Only on Restructure:**
- `restructuring_guidance` - QC's instructions for redesign
- `cached_background_research` - Reused research result (optional, saves time/cost)

### Separate S3 Files (Not in conversation_state)

- `background_research_result.json` - Step 0 output (always separate)
- `column_definition_result.json` - Step 1 output (always separate)
- `discovery_result.json` - Step 2 output (always separate)
- `qc_result.json` - Step 3 output (always separate)

### Handler Parameters (Passed Separately)

**column_definition_handler.define_columns():**
```python
def define_columns(
    conversation_context: Dict,  # Full conversation_state from S3
    background_research_result: Dict  # Loaded separately or from cache
)
```

**Why separate?**
- Background research result can be large (5-10KB)
- Not needed in conversation_state during interview
- Can be cached in conversation_state ONLY on restructure (optional optimization)
- Keeps conversation_state focused on interview/dialogue data

---

## Comparison

### Original Execution

```
conversation_state:
  - messages (interview)
  - interview_context
  - context_web_research
  - trigger_execution = True

Parameters to execution.py:
  - conversation_state (from S3)

execution.py runs:
  - Step 0: background_research (saves to S3 separately)
  - Step 1: column_definition (loads conversation_state + background_research separately)
  - Step 2-4: discovery, QC (load their own separate S3 files)
```

### Restructure Execution

```
conversation_state (UPDATED):
  - messages (same interview)
  - interview_context (same)
  - context_web_research (same)
  - restructuring_guidance: {is_restructure, column_changes, ...} ← NEW
  - cached_background_research: {...} ← NEW (optional)

Parameters to execution.py:
  - conversation_state (updated with guidance + cached research)

execution.py runs:
  - Step 0: Skip (use cached) OR run fresh if cache disabled
  - Step 1: column_definition (loads conversation_state with guidance + background_research from cache or fresh)
  - Step 2-4: discovery, QC (new attempt)
```

---

## Key Insights

1. **conversation_state = Interview + Metadata + Restructure Guidance**
   - Think of it as "what the user said and what we learned from failures"
   - Lightweight, conversation-focused

2. **Execution Results = Separate S3 Files**
   - Think of it as "outputs from each phase"
   - Can be large (discovery_result.json can be 50KB+)
   - Loaded on-demand by handlers

3. **cached_background_research = Performance Optimization**
   - Only added to conversation_state on restructure
   - Avoids re-running expensive research phase
   - Can be skipped (will just re-run research)

4. **Handler Parameters = Clear Dependencies**
   - Handlers receive conversation_context + phase-specific data
   - Makes dependencies explicit
   - Easier to test and reason about
