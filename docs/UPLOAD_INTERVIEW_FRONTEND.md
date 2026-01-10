# Upload Interview Frontend Implementation Guide

## Overview

This guide shows how to integrate the upload interview flow into the frontend. The upload interview engages users in a quick conversation after they upload a table to clarify validation requirements before generating a config.

## Flow Summary

```
User uploads Excel → Backend returns table_analysis + action='start_interview'
                  → Frontend starts interview conversation
                  → AI analyzes table and shows understanding (Mode 2)
                  → User confirms (button press or text)
                  → Config generation starts automatically
                  → Preview shows validated rows
```

## Backend Response Structure

When a user uploads an Excel file, the backend returns:

```javascript
{
  "success": true,
  "session_id": "session_20260109_123456_abc123",
  "excel_s3_key": "results/...",
  "table_analysis": {
    "columns": ["Column A", "Column B", "Column C"],
    "row_count": 150,
    "sample_rows": [
      {"Column A": "Value1", "Column B": "Value2"},
      // ... up to 3 sample rows
    ]
  },
  "conversation_id": "upload_interview_session_20260109_123456_abc123",
  "action": "start_interview",  // Signal to start interview
  "matching_configs": {...}
}
```

## WebSocket Message Types

### 1. `upload_interview_update`

Sent when the AI responds during the interview.

```javascript
{
  "type": "upload_interview_update",
  "conversation_id": "upload_interview_...",
  "mode": 2,  // 1=Ask Questions, 2=Show Understanding, 3=Start Generation
  "ai_message": "I understand this is a **VC investor tracking table**...",
  "inferred_context": {
    "table_purpose": "Track venture capital investors...",
    "id_columns": ["Organization Name"],
    "research_columns": ["Investment Focus", "Portfolio Companies"],
    "skipped_columns": ["Internal Notes"],
    "assumptions": ["Website URLs should be accessible..."]
  },
  "trigger_config_generation": false,
  "confirmation_response": {  // Only present in mode 2
    "ai_message": "Analyzing table structure...",
    "config_instructions": "..."
  }
}
```

### 2. `config_generation_start`

Sent when config generation begins after approval.

```javascript
{
  "type": "config_generation_start",
  "conversation_id": "upload_interview_...",
  "message": "Generating validation configuration..."
}
```

### 3. `upload_interview_error`

Sent if an error occurs.

```javascript
{
  "type": "upload_interview_error",
  "conversation_id": "upload_interview_...",
  "error": "Error message"
}
```

## Frontend Implementation

### 1. Detect Upload Interview Trigger

```javascript
async function handleUploadSuccess(response) {
    const cardId = `card-${response.session_id}`;

    // Check if we should start interview
    if (response.action === 'start_interview' && response.conversation_id) {
        await startUploadInterview(cardId, response);
    } else {
        // Old flow: show matching configs or other UI
        showMatchingConfigs(cardId, response.matching_configs);
    }
}
```

### 2. Start Upload Interview

```javascript
async function startUploadInterview(cardId, uploadResponse) {
    const sessionId = uploadResponse.session_id;
    const conversationId = uploadResponse.conversation_id;

    // Register WebSocket handler for this conversation
    registerCardHandler(cardId, [
        'upload_interview_update',
        'config_generation_start',
        'upload_interview_error'
    ], (message) => handleInterviewMessage(cardId, message));

    // Show interview UI in card
    showInterviewUI(cardId, conversationId);

    // Send initial request (empty message triggers AI analysis)
    await sendInterviewMessage(sessionId, conversationId, '');
}
```

### 3. Show Interview UI

```javascript
function showInterviewUI(cardId, conversationId) {
    const card = document.getElementById(cardId);

    // Clear existing content
    const contentArea = card.querySelector('.card-content');
    contentArea.innerHTML = '';

    // Add title
    const title = document.createElement('h3');
    title.textContent = 'Table Upload Configuration';
    contentArea.appendChild(title);

    // Add conversation container
    const conversationContainer = document.createElement('div');
    conversationContainer.id = `${cardId}-interview`;
    conversationContainer.className = 'interview-conversation';
    contentArea.appendChild(conversationContainer);

    // Add input area (hidden initially)
    const inputArea = createInterviewInput(cardId, conversationId);
    inputArea.id = `${cardId}-input-area`;
    inputArea.style.display = 'none';
    contentArea.appendChild(inputArea);

    // Add loading message
    addChatMessage(`${cardId}-interview`, 'assistant', 'Analyzing your table...');
}
```

### 4. Create Input Area with Confirmation Button

```javascript
function createInterviewInput(cardId, conversationId) {
    const container = document.createElement('div');
    container.className = 'interview-input-container';

    // Textarea for user input
    const textarea = document.createElement('textarea');
    textarea.id = `${cardId}-interview-input`;
    textarea.className = 'interview-input';
    textarea.placeholder = 'Type your response or click button below...';
    textarea.rows = 3;
    container.appendChild(textarea);

    // Button row
    const buttonRow = document.createElement('div');
    buttonRow.className = 'button-row';
    buttonRow.id = `${cardId}-button-row`;
    container.appendChild(buttonRow);

    return container;
}
```

### 5. Handle Interview Messages

```javascript
function handleInterviewMessage(cardId, message) {
    const conversationContainer = document.getElementById(`${cardId}-interview`);
    const inputArea = document.getElementById(`${cardId}-input-area`);
    const buttonRow = document.getElementById(`${cardId}-button-row`);

    if (message.type === 'upload_interview_update') {
        // Add AI message to conversation
        addChatMessage(conversationContainer.id, 'assistant', message.ai_message);

        if (message.mode === 1) {
            // Mode 1: AI is asking questions
            // Show input area for user to respond
            inputArea.style.display = 'block';
            buttonRow.innerHTML = '';

            const sendButton = createButton('Send Response', () => {
                const userMessage = document.getElementById(`${cardId}-interview-input`).value;
                if (userMessage.trim()) {
                    addChatMessage(conversationContainer.id, 'user', userMessage);
                    sendInterviewMessage(message.conversation_id, userMessage);
                    document.getElementById(`${cardId}-interview-input`).value = '';
                }
            });
            buttonRow.appendChild(sendButton);

        } else if (message.mode === 2) {
            // Mode 2: AI showing understanding, requesting confirmation
            // Store confirmation response for later use
            window[`${cardId}_confirmation`] = message.confirmation_response;

            // Show confirmation button prominently
            inputArea.style.display = 'block';
            buttonRow.innerHTML = '';

            // Primary button: Confirm and generate config
            const confirmButton = createButton('Looks Good - Generate Config', async () => {
                // Use pre-generated confirmation response
                const confirmation = window[`${cardId}_confirmation`];
                if (confirmation) {
                    // Show confirmation message immediately
                    addChatMessage(conversationContainer.id, 'assistant', confirmation.ai_message);

                    // Hide input area
                    inputArea.style.display = 'none';

                    // Send empty message to trigger config generation with pre-generated response
                    await sendInterviewMessage(message.conversation_id, '');
                }
            }, 'primary');
            buttonRow.appendChild(confirmButton);

            // Secondary button: Add more context
            const contextButton = createButton('Add More Context', () => {
                // Just enable the textarea for user to type
                document.getElementById(`${cardId}-interview-input`).focus();
            }, 'secondary');
            buttonRow.appendChild(contextButton);

            // Send button (for when user types context)
            const sendButton = createButton('Send & Generate', async () => {
                const userMessage = document.getElementById(`${cardId}-interview-input`).value;
                if (userMessage.trim()) {
                    addChatMessage(conversationContainer.id, 'user', userMessage);
                    await sendInterviewMessage(message.conversation_id, userMessage);
                    document.getElementById(`${cardId}-interview-input`).value = '';
                    inputArea.style.display = 'none';
                }
            });
            sendButton.style.display = 'none';
            sendButton.id = `${cardId}-send-btn`;
            buttonRow.appendChild(sendButton);

            // Show send button when user types
            document.getElementById(`${cardId}-interview-input`).addEventListener('input', (e) => {
                document.getElementById(`${cardId}-send-btn`).style.display =
                    e.target.value.trim() ? 'inline-block' : 'none';
            });

        } else if (message.mode === 3) {
            // Mode 3: Config generation starting
            // Hide input area and show progress
            inputArea.style.display = 'none';
            addChatMessage(conversationContainer.id, 'assistant', message.ai_message);
        }

    } else if (message.type === 'config_generation_start') {
        // Config generation has started
        addChatMessage(conversationContainer.id, 'system', message.message);

    } else if (message.type === 'upload_interview_error') {
        // Show error
        addChatMessage(conversationContainer.id, 'error', `[ERROR] ${message.error}`);
        inputArea.style.display = 'block';
    }
}
```

### 6. Send Interview Message

```javascript
async function sendInterviewMessage(conversationId, userMessage) {
    const sessionId = conversationId.replace('upload_interview_', '');

    try {
        const response = await fetch(`${API_BASE}/upload/interview/continue`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: sessionId,
                conversation_id: conversationId,
                user_message: userMessage,
                email: userEmail  // Get from global state
            })
        });

        const data = await response.json();

        if (!data.success) {
            console.error('[INTERVIEW] Failed to send message:', data.error);
            alert(`Failed to send message: ${data.error}`);
        }
    } catch (error) {
        console.error('[INTERVIEW] Error sending message:', error);
        alert(`Error: ${error.message}`);
    }
}
```

### 7. Helper Functions

```javascript
function addChatMessage(containerId, role, message) {
    const container = document.getElementById(containerId);
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}-message`;

    // Parse markdown if needed
    messageDiv.innerHTML = parseMarkdown(message);

    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
}

function createButton(text, onClick, variant = 'default') {
    const button = document.createElement('button');
    button.textContent = text;
    button.className = `btn btn-${variant}`;
    button.onclick = onClick;
    return button;
}

function parseMarkdown(text) {
    // Simple markdown parser (or use a library like marked.js)
    return text
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}
```

## CSS Styles

```css
.interview-conversation {
    max-height: 400px;
    overflow-y: auto;
    margin-bottom: 20px;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
}

.chat-message {
    margin-bottom: 15px;
    padding: 10px;
    border-radius: 4px;
}

.assistant-message {
    background-color: #f0f0f0;
    margin-right: 20%;
}

.user-message {
    background-color: #e3f2fd;
    margin-left: 20%;
    text-align: right;
}

.system-message {
    background-color: #fff3cd;
    text-align: center;
    font-style: italic;
}

.error-message {
    background-color: #f8d7da;
    color: #721c24;
}

.interview-input-container {
    margin-top: 15px;
}

.interview-input {
    width: 100%;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-family: inherit;
    resize: vertical;
}

.button-row {
    margin-top: 10px;
    display: flex;
    gap: 10px;
    justify-content: flex-end;
}

.btn {
    padding: 8px 16px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
}

.btn-primary {
    background-color: #007bff;
    color: white;
}

.btn-primary:hover {
    background-color: #0056b3;
}

.btn-secondary {
    background-color: #6c757d;
    color: white;
}

.btn-secondary:hover {
    background-color: #545b62;
}

.btn-default {
    background-color: #f8f9fa;
    border: 1px solid #ddd;
}

.btn-default:hover {
    background-color: #e2e6ea;
}
```

## Key Implementation Notes

1. **Confirmation Button Behavior**: When user clicks "Looks Good - Generate Config" or presses it with blank input, use the pre-generated `confirmation_response` from the Mode 2 message. This avoids a redundant AI call.

2. **WebSocket Integration**: The interview uses WebSocket messages for real-time updates. Make sure your WebSocket handler routes `upload_interview_*` messages to the interview handler.

3. **Session ID**: The conversation_id follows the pattern `upload_interview_{session_id}`, so you can extract the session_id by removing the prefix.

4. **Mode 2 Details**: The AI message in Mode 2 should display important details:
   - **ID Columns**: Which columns uniquely identify rows
   - **Research Columns**: Which columns require validation
   - **Skipped Columns**: Which columns won't be validated
   - **Assumptions**: Key assumptions about the data

5. **Config Generation Flow**: After user confirms (Mode 3), the backend automatically:
   - Triggers config generation with the interview context
   - Generates a validation config
   - Validates the first 3 rows
   - Returns preview results via existing preview flow

## Testing

Test these scenarios:

1. **Clear Table**: Upload a table with clear column names → AI should go directly to Mode 2
2. **Ambiguous Table**: Upload a table with cryptic column names → AI should ask questions (Mode 1)
3. **User Confirmation**: Click "Looks Good" button → Should immediately show config generation message
4. **Additional Context**: Type extra context before confirming → Should include in config instructions
5. **Error Handling**: Test with invalid data → Should show error message
