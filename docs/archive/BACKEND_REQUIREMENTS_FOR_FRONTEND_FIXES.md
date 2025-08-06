# Backend Requirements for Frontend Fixes

## Overview
The frontend has been updated but several backend issues need to be addressed to ensure proper functionality. This document outlines the requirements for versioning, preview emails, sequential log handling, and WebSocket-only responses.

## 1. Config Versioning System

### Current Problem
The interface is not maintaining proper configuration versioning as intended. Currently seeing:
- `config_v1_upload.json` 
- `config_v1_ai_generated.json`

### Expected Behavior
Should see continuous versioning:
- `config_v1_upload.json` (initial user upload)
- `config_v2_refined.json` (first refinement)
- `config_v3_refined.json` (second refinement)
- etc.

### Implementation Required in Backend

#### Files to Modify:
1. `src/interface_lambda/core/unified_storage.py` (if exists) or `src/interface_lambda/core/s3_manager.py`
2. `src/interface_lambda/actions/generate_config.py` 
3. `src/interface_lambda/actions/generate_config_unified.py`

#### Key Changes Needed:

**1. Version Tracking Logic:**
```python
def get_next_config_version(email: str, session_id: str) -> int:
    \"\"\"Get the next version number for config files\"\"\"
    try:
        # List all config files in session folder
        session_path = get_session_path(email, session_id)
        existing_configs = list_session_files(session_path, prefix=\"config_v\")
        
        # Extract version numbers and get max
        versions = []
        for config_file in existing_configs:
            match = re.search(r'config_v(\\d+)_', config_file)
            if match:
                versions.append(int(match.group(1)))
        
        return max(versions, default=0) + 1
    except Exception as e:
        logger.warning(f\"Could not determine next version: {e}\")
        return 1
```

**2. Config Storage with Proper Versioning:**
```python
def store_config_with_versioning(email: str, session_id: str, config_data: dict, 
                                source: str = 'refined') -> dict:
    \"\"\"Store config with automatic version increment\"\"\"
    next_version = get_next_config_version(email, session_id)
    
    # Store with incremented version
    result = store_config_file(
        email=email,
        session_id=session_id, 
        config_data=config_data,
        version=next_version,
        source=source
    )
    
    # Update session info with new version
    update_session_info(email, session_id, current_config_version=next_version)
    
    return result
```

**3. Session Info Updates:**
Ensure `session_info.json` tracks:
```json
{
    \"session_id\": \"abc123\",
    \"current_config_version\": 3,
    \"total_configs\": 3,
    \"config_history\": [
        {\"version\": 1, \"source\": \"upload\", \"created_at\": \"2024-01-01T10:00:00Z\"},
        {\"version\": 2, \"source\": \"refined\", \"created_at\": \"2024-01-01T10:05:00Z\"},
        {\"version\": 3, \"source\": \"refined\", \"created_at\": \"2024-01-01T10:10:00Z\"}
    ]
}
```

## 2. WebSocket-Only Response System

### Current Problem
Duplicate responses occur because both synchronous HTTP responses AND WebSocket messages are being processed for refinements. The frontend expects only WebSocket responses for consistent handling.

### Solution Required

#### In HTTP Response Handlers:
For `/validate?async=true` endpoints handling `modifyConfig` actions:

**Before (causing duplicates):**
```python
# Don't return both sync response AND send WebSocket message
return {
    'success': True,
    'ai_summary': refined_summary,  # This causes sync processing
    'session_id': session_id
}
```

**After (WebSocket-only):**
```python
# Only return async processing indicator
if session_id and websocket_connected:
    # Send via WebSocket only
    send_websocket_message(session_id, {
        'type': 'config_generation_complete',
        'ai_summary': refined_summary,
        'download_url': download_url,
        'clarifying_questions': questions,
        'session_id': session_id
    })
    
    return {
        'success': True,
        'status': 'processing',
        'session_id': session_id
        # NO ai_summary field to prevent sync processing
    }
```

#### Files to Modify:
1. `src/interface_lambda/actions/generate_config_unified.py`
2. `src/interface_lambda/actions/process_excel_unified.py` 
3. Any endpoint handling `modifyConfig` action

## 3. Clarifying Questions Storage & Retrieval

### Current Problem
Questions from initial generation/refinement are not being saved and retrieved for subsequent refinements.

### Implementation Required

#### Question Storage:
```python
def save_clarifying_questions(email: str, session_id: str, questions: str, 
                             config_version: int) -> None:
    \"\"\"Save clarifying questions for future reference\"\"\"
    questions_key = f\"{get_session_path(email, session_id)}clarifying_questions_v{config_version}.txt\"
    
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=questions_key,
        Body=questions.encode('utf-8'),
        ContentType='text/plain'
    )
    
    # Also store in session_info for quick access
    update_session_info(email, session_id, latest_questions=questions)
```

#### Question Retrieval:
```python
def get_latest_clarifying_questions(email: str, session_id: str) -> str:
    \"\"\"Get the most recent clarifying questions for refinement\"\"\"
    try:
        # First try session_info
        session_info = get_session_info(email, session_id)
        if session_info and session_info.get('latest_questions'):
            return session_info['latest_questions']
        
        # Fallback: find most recent questions file
        session_path = get_session_path(email, session_id)
        question_files = list_session_files(session_path, prefix=\"clarifying_questions_v\")
        
        if question_files:
            # Get latest version
            latest_file = max(question_files, key=lambda x: int(re.search(r'v(\\d+)', x).group(1)))
            response = s3_client.get_object(Bucket=S3_BUCKET, Key=f\"{session_path}{latest_file}\")
            return response['Body'].read().decode('utf-8')
            
    except Exception as e:
        logger.warning(f\"Could not retrieve clarifying questions: {e}\")
        
    return None
```

#### Integration in Config Generation:
```python
# In generate_config_unified.py or similar
if action == 'modifyConfig':
    # Include saved questions in AI prompt context
    saved_questions = get_latest_clarifying_questions(email, session_id)
    if saved_questions:
        ai_prompt += f\"\\n\\nPrevious clarifying questions for context:\\n{saved_questions}\"
    
    # After AI processing, save new questions if provided
    if ai_response.get('clarifying_questions'):
        save_clarifying_questions(email, session_id, 
                                 ai_response['clarifying_questions'], 
                                 current_config_version)
```

## 4. Automatic Preview Email System

### Current Problem
Preview emails are not being sent automatically after preview processing completes.

### Implementation Required

#### Files to Modify:
1. `src/interface_lambda/handlers/background_handler.py`
2. `src/email_sender.py` or equivalent email service

#### Preview Email Logic:
```python
# In background_handler.py after preview processing completes

async def handle_preview_completion(session_id: str, email: str, preview_results: dict):
    \"\"\"Handle preview completion including email sending\"\"\"
    try:
        # Store preview results (already implemented)
        storage_result = storage_manager.store_results(
            email, session_id, config_version, preview_results, 'preview'
        )
        
        # Generate enhanced Excel file with preview results
        enhanced_excel = create_enhanced_excel(preview_results)
        
        # Store enhanced files
        file_result = storage_manager.store_enhanced_files(
            email, session_id, config_version, 
            enhanced_excel_content=enhanced_excel,
            summary_text=preview_results.get('summary', '')
        )
        
        # Send preview email automatically
        if file_result['success'] and file_result.get('enhanced_excel_url'):
            await send_preview_email(
                email=email,
                session_id=session_id,
                preview_url=file_result['enhanced_excel_url'],
                summary=preview_results.get('summary', ''),
                table_name=preview_results.get('table_name', 'Unknown')
            )
            logger.info(f\"Preview email sent to {email} for session {session_id}\")
        
        # Send WebSocket completion message
        send_websocket_message(session_id, {
            'type': 'preview_complete',
            'status': 'COMPLETED',
            'preview_results': preview_results,
            'email_sent': True
        })
        
    except Exception as e:
        logger.error(f\"Preview completion handling failed: {e}\")
        send_websocket_message(session_id, {
            'type': 'preview_failed', 
            'error': str(e)
        })
```

#### Email Template Enhancement:
```python
async def send_preview_email(email: str, session_id: str, preview_url: str, 
                           summary: str, table_name: str):
    \"\"\"Send preview results email with enhanced Excel attachment\"\"\"
    subject = f\"📊 Preview Results Ready - {table_name}\"
    
    body = f\"\"\"
    Your table preview has been completed successfully!
    
    📈 **Summary:** {summary}
    
    📧 **Enhanced Excel File:** Your preview results are available as an enhanced Excel file with validation highlights and comments.
    
    🔗 **Download Link:** {preview_url}
    
    Next steps:
    - Review the enhanced Excel file
    - Use the interface to refine your configuration if needed
    - Run full validation when ready
    
    Session ID: {session_id}
    \"\"\"
    
    # Send email using existing email service
    email_service.send_email(
        to_email=email,
        subject=subject,
        body=body,
        attachments=[{
            'url': preview_url,
            'filename': f'preview_results_{session_id}.xlsx'
        }]
    )
```

## 5. Sequential Log Handling & Conversation Continuity

### Current Problem
The interface lambda is not maintaining proper conversation history and sequential logging for the chat-like refinement process.

### Implementation Required

#### Conversation History Storage:
```python
def store_conversation_message(email: str, session_id: str, message_type: str, 
                              content: str, config_version: int = None):
    \"\"\"Store conversation messages for continuity\"\"\"
    conversation_key = f\"{get_session_path(email, session_id)}conversation_history.json\"
    
    # Load existing conversation
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=conversation_key)
        conversation = json.loads(response['Body'].read().decode('utf-8'))
    except:
        conversation = {'messages': [], 'created': datetime.now().isoformat()}
    
    # Add new message
    message = {
        'timestamp': datetime.now().isoformat(),
        'type': message_type,  # 'user', 'ai', 'system'
        'content': content,
        'config_version': config_version,
        'message_id': str(uuid.uuid4())
    }
    
    conversation['messages'].append(message)
    conversation['last_updated'] = datetime.now().isoformat()
    
    # Store updated conversation
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=conversation_key,
        Body=json.dumps(conversation, indent=2).encode('utf-8'),
        ContentType='application/json'
    )
```

#### Integration in Config Processing:
```python
# In generate_config_unified.py
if action == 'modifyConfig':
    # Store user refinement request
    store_conversation_message(
        email, session_id, 'user', 
        instructions, current_config_version
    )
    
    # Get conversation history for AI context
    conversation_history = get_conversation_history(email, session_id)
    
    # Include history in AI prompt
    ai_prompt = build_refinement_prompt(
        current_config=current_config,
        user_instructions=instructions,
        conversation_history=conversation_history
    )
    
    # After AI processing
    ai_response = call_ai_service(ai_prompt)
    
    # Store AI response
    store_conversation_message(
        email, session_id, 'ai',
        ai_response['summary'], current_config_version + 1
    )
    
    # Store clarifying questions if provided
    if ai_response.get('clarifying_questions'):
        store_conversation_message(
            email, session_id, 'system',
            f\"Clarifying questions: {ai_response['clarifying_questions']}\",
            current_config_version + 1
        )
```

## 6. Testing & Validation

### Frontend Testing Scenarios:
1. **Config Versioning Test:**
   - Upload Excel → Generate Config → Refine → Refine Again
   - Verify: v1_upload.json, v2_refined.json, v3_refined.json

2. **Duplicate Response Test:**
   - Generate config → Refine once → Refine again
   - Verify: Only one response per refinement request

3. **Questions Persistence Test:**
   - Generate config (with questions) → Accept → Refine
   - Verify: Questions appear in refinement interface

4. **Preview Email Test:**
   - Upload Excel → Generate Config → Accept → Preview
   - Verify: Email received with enhanced Excel attachment

### Backend Logging:
Add comprehensive logging to track:
```python
logger.info(f\"Config versioning: {email}/{session_id} - storing v{version}_{source}.json\")
logger.info(f\"Conversation stored: {message_type} message for session {session_id}\")
logger.info(f\"WebSocket message sent: {message_type} to session {session_id}\")
logger.info(f\"Preview email queued for {email}, session {session_id}\")
```

## Priority Implementation Order:
1. **WebSocket-only responses** (fixes duplicate responses immediately)
2. **Config versioning** (ensures proper file tracking)
3. **Questions storage/retrieval** (improves refinement UX)
4. **Preview email automation** (completes preview workflow)
5. **Conversation continuity** (enhances overall experience)

This document provides the complete context needed to implement the backend changes that will support the frontend improvements.