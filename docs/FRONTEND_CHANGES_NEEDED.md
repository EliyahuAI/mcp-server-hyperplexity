# Frontend Changes Required for Upload Interview

## Summary
The frontend needs 4 key additions to handle the upload interview flow:

1. Detect `action='start_interview'` in upload response
2. Add WebSocket message handlers for interview updates
3. Create interview UI functions
4. Send interview messages via API

---

## 1. Detect Upload Interview Trigger

**Location:** After line 7556 in `uploadExcelFile` function (around line 7560)

**Insert after storing matching_configs:**

```javascript
// Check if we should start upload interview
if (confirmData.action === 'start_interview' && confirmData.conversation_id) {
    console.log('[UPLOAD_INTERVIEW] Starting interview for', confirmData.conversation_id);

    // Store conversation info
    globalState.uploadInterviewConversationId = confirmData.conversation_id;
    globalState.tableAnalysis = confirmData.table_analysis;

    // Show interview UI instead of going to config
    setTimeout(() => {
        createUploadInterviewCard(cardId, confirmData);
    }, 500);

    return; // Don't proceed to normal config flow
}
```

---

## 2. Add WebSocket Message Handlers

**Location:** In `routeMessage` function after line 5942 (after reference_check handlers)

**Insert:**

```javascript
// Handle Upload Interview updates
if (data.type === 'upload_interview_update') {
    handleUploadInterviewUpdate(data);
    return;
}

if (data.type === 'config_generation_start') {
    handleConfigGenerationStart(data);
    return;
}

if (data.type === 'upload_interview_error') {
    handleUploadInterviewError(data);
    return;
}
```

---

## 3. Create Interview Handler Functions

**Location:** Add these functions near other handler functions (around line 13000+)

```javascript
// ========== UPLOAD INTERVIEW HANDLERS ==========

function handleUploadInterviewUpdate(data) {
    console.log('[UPLOAD_INTERVIEW] Received update:', data);

    const conversationId = data.conversation_id;
    if (!conversationId) return;

    // Find the interview card
    const cardId = globalState.uploadInterviewCardId;
    if (!cardId) return;

    const conversationContainer = document.getElementById(`${cardId}-interview`);
    const inputArea = document.getElementById(`${cardId}-input-area`);
    const buttonRow = document.getElementById(`${cardId}-button-row`);

    if (!conversationContainer) return;

    // Add AI message to conversation
    addChatMessage(conversationContainer.id, 'assistant', data.ai_message);

    if (data.mode === 1) {
        // Mode 1: AI is asking questions
        inputArea.style.display = 'block';
        buttonRow.innerHTML = '';

        const sendButton = createInterviewButton('Send Response', 'primary', () => {
            const userMessage = document.getElementById(`${cardId}-interview-input`).value;
            if (userMessage.trim()) {
                addChatMessage(conversationContainer.id, 'user', userMessage);
                sendInterviewMessage(conversationId, userMessage);
                document.getElementById(`${cardId}-interview-input`).value = '';
            }
        });
        buttonRow.appendChild(sendButton);

    } else if (data.mode === 2) {
        // Mode 2: AI showing understanding, requesting confirmation

        // Store confirmation response for later use
        window[`${cardId}_confirmation`] = data.confirmation_response;

        inputArea.style.display = 'block';
        buttonRow.innerHTML = '';

        // Primary button: Confirm and generate config
        const confirmButton = createInterviewButton('Looks Good - Generate Config', 'primary', async () => {
            const confirmation = window[`${cardId}_confirmation`];
            if (confirmation) {
                // Show confirmation message immediately
                addChatMessage(conversationContainer.id, 'assistant', confirmation.ai_message);

                // Hide input area
                inputArea.style.display = 'none';

                // Send empty message to trigger config generation
                await sendInterviewMessage(conversationId, '');
            }
        });
        buttonRow.appendChild(confirmButton);

        // Secondary button: Add more context
        const contextButton = createInterviewButton('Add More Context', 'secondary', () => {
            document.getElementById(`${cardId}-interview-input`).focus();
        });
        buttonRow.appendChild(contextButton);

    } else if (data.mode === 3) {
        // Mode 3: Config generation starting
        inputArea.style.display = 'none';
        addChatMessage(conversationContainer.id, 'assistant', data.ai_message);
    }
}

function handleConfigGenerationStart(data) {
    console.log('[UPLOAD_INTERVIEW] Config generation starting');

    const cardId = globalState.uploadInterviewCardId;
    if (!cardId) return;

    const conversationContainer = document.getElementById(`${cardId}-interview`);
    if (conversationContainer) {
        addChatMessage(conversationContainer.id, 'system', data.message || 'Generating validation configuration...');
    }

    // Show progress indicator
    showThinkingInCard(cardId, 'Generating configuration and validating first rows...');
}

function handleUploadInterviewError(data) {
    console.error('[UPLOAD_INTERVIEW] Error:', data.error);

    const cardId = globalState.uploadInterviewCardId;
    if (!cardId) return;

    const conversationContainer = document.getElementById(`${cardId}-interview`);
    if (conversationContainer) {
        addChatMessage(conversationContainer.id, 'error', `[ERROR] ${data.error}`);
    }
}

function createUploadInterviewCard(previousCardId, uploadData) {
    // Hide or complete previous card
    if (previousCardId) {
        showFinalCardState(previousCardId, 'Starting upload interview...', 'success');
    }

    const cardId = generateCardId();
    globalState.uploadInterviewCardId = cardId;

    const content = `
        <div id="${cardId}-interview" class="interview-conversation"></div>
        <div id="${cardId}-input-area" class="interview-input-container" style="display: none;">
            <textarea id="${cardId}-interview-input" class="interview-input"
                placeholder="Type your response..." rows="3"></textarea>
            <div id="${cardId}-button-row" class="button-row"></div>
        </div>
    `;

    const card = createCard({
        id: cardId,
        title: 'Table Upload Configuration',
        content: content,
        thinking: true
    });

    globalState.cardsContainer.appendChild(card);

    // Add initial message
    const conversationContainer = document.getElementById(`${cardId}-interview`);
    addChatMessage(conversationContainer.id, 'assistant', 'Analyzing your table...');

    // Start the interview
    sendInterviewMessage(uploadData.conversation_id, '');
}

async function sendInterviewMessage(conversationId, userMessage) {
    const sessionId = conversationId.replace('upload_interview_', '');

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                action: 'continueUploadInterview',
                session_id: sessionId,
                conversation_id: conversationId,
                user_message: userMessage,
                email: globalState.email
            })
        });

        const data = await response.json();

        if (!data.success) {
            console.error('[UPLOAD_INTERVIEW] Failed to send message:', data.error);
            alert(`Failed to send message: ${data.error}`);
        }
    } catch (error) {
        console.error('[UPLOAD_INTERVIEW] Error sending message:', error);
        alert(`Error: ${error.message}`);
    }
}

function addChatMessage(containerId, role, message) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}-message`;

    // Simple markdown parsing
    const html = message
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');

    messageDiv.innerHTML = html;

    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
}

function createInterviewButton(text, variant, onClick) {
    const button = document.createElement('button');
    button.textContent = text;
    button.className = `btn btn-${variant}`;
    button.onclick = onClick;
    return button;
}
```

---

## 4. Add CSS Styles

**Location:** In the `<style>` section (add near end of styles, before closing `</style>`)

```css
/* Upload Interview Styles */
.interview-conversation {
    max-height: 400px;
    overflow-y: auto;
    margin-bottom: 20px;
    padding: 15px;
    border: 1px solid #ddd;
    border-radius: 8px;
    background-color: #fafafa;
}

.chat-message {
    margin-bottom: 15px;
    padding: 12px;
    border-radius: 8px;
    max-width: 85%;
}

.assistant-message {
    background-color: #f0f0f0;
    margin-right: 15%;
    border-left: 3px solid #007bff;
}

.user-message {
    background-color: #e3f2fd;
    margin-left: 15%;
    text-align: right;
    border-right: 3px solid #2196F3;
}

.system-message {
    background-color: #fff3cd;
    text-align: center;
    font-style: italic;
    margin-left: auto;
    margin-right: auto;
    max-width: 70%;
}

.error-message {
    background-color: #f8d7da;
    color: #721c24;
    border-left: 3px solid #dc3545;
    margin-left: auto;
    margin-right: auto;
    max-width: 70%;
}

.interview-input-container {
    margin-top: 15px;
}

.interview-input {
    width: 100%;
    padding: 12px;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-family: inherit;
    font-size: 14px;
    resize: vertical;
    min-height: 60px;
}

.interview-input:focus {
    outline: none;
    border-color: #007bff;
    box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.1);
}

.button-row {
    margin-top: 10px;
    display: flex;
    gap: 10px;
    justify-content: flex-end;
}

.btn-primary {
    background-color: #007bff;
    color: white;
    padding: 10px 20px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
}

.btn-primary:hover {
    background-color: #0056b3;
}

.btn-secondary {
    background-color: #6c757d;
    color: white;
    padding: 10px 20px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
}

.btn-secondary:hover {
    background-color: #545b62;
}
```

---

## 5. Update HTTP Handler Routing (Backend)

**Location:** `deployment/.../handlers/http_handler.py`

Find where actions are routed and add:

```python
elif action in ['startUploadInterview', 'continueUploadInterview']:
    from interface_lambda.actions.upload_interview import route_upload_interview_action
    result = route_upload_interview_action(action, request_data, context)
```

---

## Testing Checklist

- [ ] Upload clear table → AI shows Mode 2 with ID columns, skipped columns, assumptions
- [ ] Click "Looks Good" button → Immediately shows "Analyzing table structure..." message
- [ ] Upload ambiguous table → AI asks questions (Mode 1)
- [ ] Type additional context → Can send and generate
- [ ] Config generation completes → Shows preview as normal
- [ ] WebSocket reconnects → Interview state persists
- [ ] Error handling → Shows error message in conversation

---

## Key Implementation Notes

1. **Confirmation Button**: Uses pre-generated `confirmation_response` from Mode 2 to avoid redundant AI call
2. **WebSocket Messages**: Must be routed through existing `routeMessage` function
3. **Card Management**: Uses existing card creation and state management patterns
4. **API Calls**: Follow existing fetch pattern with `action` parameter
5. **CSS**: Matches existing card styling with interview-specific additions
