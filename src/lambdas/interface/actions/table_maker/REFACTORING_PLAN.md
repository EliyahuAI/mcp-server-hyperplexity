# Table Maker Interview Refactoring Plan

## Overview
Refactoring table maker to use a two-phase approach:
1. **Phase 1: Interview** - Quick context gathering with fast Haiku model
2. **Phase 2: Preview Generation** - Full table generation with progress updates

## Completed ✅

1. **Interview Schema** (`schemas/interview_response.json`)
   - `trigger_preview`: Boolean to indicate readiness
   - `follow_up_question`: Contains table proposal or follow-up question
   - `context_web_research`: Research questions for COLUMN definitions (not rows)
   - `processing_steps`: 3-5 word action phrases
   - `table_name`: Descriptive title case name

2. **Interview Prompt** (`prompts/interview.md`)
   - Markdown formatting guidance (bold, bullets, no long paragraphs)
   - A/B style questions with clear options
   - Table size proposals (rows and columns)
   - Explicit table proposal: "Here is what I understand so far..."
   - Clear examples showing markdown-formatted responses

3. **Interview Handler** (`interview.py`)
   - `TableInterviewHandler` class
   - Uses fast Haiku model (`claude-haiku-4-5`)
   - No web search access
   - Manages interview conversation history

4. **Configuration** (`table_maker_config.json`)
   - Added interview section with model, max_tokens, use_web_search=false

## Remaining Work 🚧

### 1. Update `handle_table_conversation_start` in conversation.py

**Current**: Uses `TableConversationHandler` with old schema
**Target**: Use `TableInterviewHandler` with interview schema

Changes needed:
```python
# Replace lines 560-596
# OLD: Initialize TableConversationHandler
conversation_handler = TableConversationHandler(...)
conversation_result = await conversation_handler.start_conversation(...)

# NEW: Initialize TableInterviewHandler
interview_handler = TableInterviewHandler(
    prompts_dir=prompts_dir,
    schemas_dir=schemas_dir
)
interview_config = config.get('interview', {})
model = interview_config.get('model', 'claude-haiku-4-5')
max_tokens = interview_config.get('max_tokens', 4000)

interview_result = await interview_handler.start_interview(
    user_message=user_message,
    model=model,
    max_tokens=max_tokens
)

# Update result structure (lines 619-627)
result['success'] = True
result['trigger_preview'] = interview_result.get('trigger_preview', False)
result['follow_up_question'] = interview_result.get('follow_up_question', '')
result['context_web_research'] = interview_result.get('context_web_research', [])
result['processing_steps'] = interview_result.get('processing_steps', [])
result['table_name'] = interview_result.get('table_name', '')
result['turn_count'] = 1

# Update conversation_state structure (lines 629-643)
conversation_state = {
    'conversation_id': conversation_id,
    'session_id': session_id,
    'email': email,
    'created_at': datetime.utcnow().isoformat() + 'Z',
    'last_updated': datetime.utcnow().isoformat() + 'Z',
    'status': 'preview_ready' if result['trigger_preview'] else 'in_progress',
    'turn_count': 1,
    'run_key': run_key,
    'config': config,
    'messages': interview_handler.get_interview_history(),
    'interview_context': interview_handler.get_interview_context(),
    'trigger_preview': result['trigger_preview']
}

# Update WebSocket message (lines 663-674)
websocket_client.send_to_session(session_id, {
    'type': 'table_conversation_update',
    'conversation_id': conversation_id,
    'progress': 100,
    'status': 'Interview turn 1 complete',
    'trigger_preview': result['trigger_preview'],
    'follow_up_question': result['follow_up_question'],
    'context_web_research': result['context_web_research'],
    'processing_steps': result['processing_steps'],
    'table_name': result['table_name'],
    'turn_count': result['turn_count']
})

# If trigger_preview is true, automatically start preview generation
if result['trigger_preview']:
    await _trigger_preview_generation(
        email=email,
        session_id=session_id,
        conversation_id=conversation_id,
        conversation_state=conversation_state,
        run_key=run_key
    )
```

### 2. Update `handle_table_conversation_continue` in conversation.py

**Current**: Uses `TableConversationHandler` with old schema
**Target**: Use `TableInterviewHandler` with interview schema

Changes needed:
```python
# Replace lines 388-432
# OLD: Initialize and restore TableConversationHandler
conversation_handler = TableConversationHandler(...)
conversation_handler.conversation_id = ...
conversation_handler.conversation_log = ...

# NEW: Initialize and restore TableInterviewHandler
interview_handler = TableInterviewHandler(
    prompts_dir=prompts_dir,
    schemas_dir=schemas_dir
)
interview_handler.messages = conversation_state['messages']
interview_handler.interview_context = conversation_state.get('interview_context', {})

interview_config = config.get('interview', {})
model = interview_config.get('model', 'claude-haiku-4-5')
max_tokens = interview_config.get('max_tokens', 4000)

interview_result = await interview_handler.continue_interview(
    user_message=user_message,
    model=model,
    max_tokens=max_tokens
)

# Update result structure and conversation state similar to start handler
# If trigger_preview is true, call _trigger_preview_generation
```

### 3. Create `_trigger_preview_generation` Helper Function

Add new function to conversation.py:
```python
async def _trigger_preview_generation(
    email: str,
    session_id: str,
    conversation_id: str,
    conversation_state: Dict[str, Any],
    run_key: Optional[str]
) -> None:
    """
    Automatically trigger preview generation when interview is complete.

    This function:
    1. Sends WebSocket progress updates simulating ~60s generation
    2. Calls preview generator with conversation context
    3. Updates run status
    """
    logger.info(f"[TABLE_MAKER] Triggering automatic preview generation for {conversation_id}")

    # Import preview handler
    from .preview import handle_table_preview_generate

    # Send progress updates (simulate ~60s task)
    processing_steps = conversation_state.get('interview_context', {}).get('processing_steps', [])

    # Simulate progress over 60 seconds with processing steps
    step_duration = 60.0 / len(processing_steps) if processing_steps else 20.0

    for idx, step in enumerate(processing_steps):
        progress = 10 + (idx * (80 / len(processing_steps)))
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_generation_progress',
                    'conversation_id': conversation_id,
                    'progress': progress,
                    'status': step,
                    'step': idx + 1,
                    'total_steps': len(processing_steps)
                })
            except Exception as e:
                logger.warning(f"Failed to send progress update: {e}")

        await asyncio.sleep(step_duration)

    # Send "Generating Preview" message
    if websocket_client and session_id:
        try:
            websocket_client.send_to_session(session_id, {
                'type': 'table_generation_progress',
                'conversation_id': conversation_id,
                'progress': 90,
                'status': 'Generating Preview...'
            })
        except Exception as e:
            logger.warning(f"Failed to send progress update: {e}")

    # Call preview generator
    preview_request = {
        'email': email,
        'session_id': session_id,
        'conversation_id': conversation_id
    }

    try:
        preview_result = await handle_table_preview_generate(preview_request, None)
        logger.info(f"[TABLE_MAKER] Preview generation complete: {preview_result}")
    except Exception as e:
        logger.error(f"[TABLE_MAKER] Preview generation failed: {e}")
        if run_key:
            update_run_status(
                session_id=session_id,
                run_key=run_key,
                status='FAILED',
                run_type="Table Generation",
                verbose_status=f"Preview generation failed: {str(e)}",
                error_message=str(e)
            )
```

### 4. Update Preview Generator to Use Interview Context

In `preview.py`, modify to use `context_web_research` from interview:

```python
# Load conversation state
conversation_state = _load_conversation_state_from_s3(...)

# Extract interview context
interview_context = conversation_state.get('interview_context', {})
context_web_research = interview_context.get('context_web_research', [])
table_name = interview_context.get('table_name', '')

# Use context_web_research to inform column descriptions
# These are research questions about column definitions, not rows
# Example: "What metrics define GenAI job postings?"
# Should inform the "GenAI Job Posting" column description
```

### 5. Handle Refine Flow

When user clicks "refine table" button:
- Frontend sends `continueTableConversation` with user's refinement request
- Backend continues interview conversation
- Full conversation history preserved in S3
- When `trigger_preview: true` again, regenerate preview

## Testing Plan

1. **Test interview flow**:
   - Start conversation with clear request → should trigger preview
   - Start with unclear request → should ask follow-up with A/B options
   - Continue conversation → should eventually trigger preview

2. **Test progress updates**:
   - Verify WebSocket messages sent during ~60s simulation
   - Verify processing_steps are displayed
   - Verify "Generating Preview" appears

3. **Test preview generation**:
   - Verify context_web_research used in column descriptions
   - Verify table_name used for file naming
   - Verify preview card shows with refine/generate options

4. **Test refine flow**:
   - Click refine → continues interview
   - Full conversation history preserved
   - New preview generated when trigger_preview: true

## Key Design Decisions

1. **Fast Haiku model for interview** - Cheaper and faster for context gathering
2. **Markdown formatting** - Better UX for follow-up questions and proposals
3. **A/B style questions** - Clearer options than open-ended
4. **Automatic preview trigger** - No separate API call needed
5. **Progress simulation** - Better UX than waiting silently
6. **context_web_research for columns** - Research questions inform column descriptions, not row data
7. **Conversation history preserved** - Full context available for refine flow
