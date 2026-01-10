# Table Upload Conversation Flow Design

## Overview

Create a conversational interview flow for table uploads that mirrors the table_maker pattern. When a user uploads a table, instead of immediately generating a config with default prompts, we engage in a quick interview to gather context - then trigger config generation with that context.

## Current Flow (Problem)
```
Upload Excel → Config Generation (default prompt) → Preview
                     ↑
            No user context gathered
            Uses hardcoded "Generate optimal config" instruction
```

## New Flow (Solution)
```
Upload Excel → Store file → Interview (1-2 turns) → Config Generation (with context) → Preview
                                ↑
                    AI asks smart questions based on table analysis
                    User provides context or confirms defaults
```

---

## Design: 3-Mode Interview System

**Model:** `gemini-2.0-flash` (fast, free tier available, no web search needed)

**Default Behavior:** Skip to Mode 2 for most tables. Only use Mode 1 when genuinely ambiguous.

### Mode 1: Ask Clarifying Questions (Rare)
Only when AI is genuinely confused about the table.

**Triggers:**
- Column names are cryptic abbreviations with no clear meaning
- Multiple conflicting interpretations possible
- Cannot determine what defines a row

**Output:**
```json
{
  "mode": 1,
  "ai_message": "I see columns like 'XYZ_CD' and 'ABC_01' - could you help me understand what this table tracks?",
  "questions": ["What does each row represent?", "Which columns are most important to validate?"],
  "trigger_config_generation": false
}
```

### Mode 2: Show Understanding & Confirm (Default)
The normal path - AI infers purpose and asks for confirmation.

**Triggers:**
- Table structure is reasonably clear (most tables)
- Purpose can be inferred from column names
- ID columns can be identified

**Output:**
```json
{
  "mode": 2,
  "ai_message": "I understand this is a VC investor tracking table. I'll validate: company details, investment focus, and contact information. Ready to generate your configuration?",
  "inferred_context": {
    "table_purpose": "Track venture capital investors",
    "id_columns": ["Organization Name"],
    "research_columns": ["Investment Focus", "Portfolio Companies", "Contact"]
  },
  "trigger_config_generation": false,
  "confirmation_response": {
    "ai_message": "Analyzing table structure and divining column meanings...",
    "config_instructions": "Validate VC investor table focusing on..."
  }
}
```

**Note:** `confirmation_response` is pre-generated so when user confirms, we can immediately show the message and trigger config generation without another AI call.

### Mode 3: Generate Config (User Approved)
When user confirms or provides additional context.

**Triggers:**
- User says "yes", "go ahead", "looks good"
- User provides additional context and approves

**Output:**
```json
{
  "mode": 3,
  "ai_message": "In the next 3-4 minutes, I will formalize the verification plan and validate the first 3 rows for preview.\n\nAnalyzing your investor tracking table and preparing validation strategy...",
  "config_instructions": "Validate VC investor table focusing on...",
  "trigger_config_generation": true
}
```

**Message Format:** Table-specific with timing notice:
```
In the next 3-4 minutes, I will formalize the verification plan and validate the first 3 rows for preview.

Analyzing your investor tracking table and preparing validation strategy...
```

**Message Examples by Table Type:**
- "...Analyzing your investor tracking table and preparing validation strategy..."
- "...Examining your conference schedule and identifying research targets..."
- "...Reviewing your company database and configuring validation approach..."

**UX Flow on Confirmation:**
1. Display timing notice + table-specific message
2. Brief pause (1-2 seconds) for user to read
3. Transition to config generation progress → preview validation
4. Show preview results using existing `showTablePreviewInCard()` (lines 12420-12562)

**Preview Display Reference:**
The existing preview display code in `showTablePreviewInCard()` renders:
- Transposed markdown table (first 3 rows validated)
- Blue info box for ID columns
- Purple info box for research columns
- Orange info box for additional rows discovered
- Action buttons for next steps

---

## Implementation Plan

### Phase 1: Backend - Upload Interview Action (Isolated New Action)

#### 1.1 Create Upload Interview Action
**Location:** `src/lambdas/interface/actions/upload_interview/` (own isolated action)

```
src/lambdas/interface/actions/
├── config_generation/             # EXISTING - unchanged
├── table_maker/                   # EXISTING - unchanged
├── upload_interview/              # NEW ISOLATED ACTION
│   ├── __init__.py               # Handler exports + route function
│   ├── interview.py              # UploadInterviewHandler class
│   ├── prompts/
│   │   └── upload_interview.md   # Interview prompt template
│   └── schemas/
│       └── upload_interview_response.json
├── process_excel_unified.py       # EXISTING - modify to return table_analysis
└── ...
```

**Key class: `UploadInterviewHandler`**
- Similar to `TableInterviewHandler`
- Takes table_analysis as input (column names, sample data, row count)
- Uses fast model (haiku or deepseek) - NO web search needed
- Returns structured response with mode, message, and context

#### 1.2 Interview Prompt Design
**File:** `prompts/upload_interview.md`

```markdown
You are analyzing an uploaded table to prepare for validation configuration.

## Table Analysis
{{TABLE_ANALYSIS}}

## Your Task
Analyze this table and determine if you need clarification before generating a validation config.

Choose ONE mode:

### MODE 1: Ask Questions
If the table has ambiguous columns or unclear purpose, ask 1-3 focused questions.

### MODE 2: Confirm Understanding
If the table is clear, summarize your understanding and ask for confirmation.
Include: inferred purpose, ID columns, research columns.

### MODE 3: Ready to Generate
If user has confirmed or provided context, generate the config instructions.

## Current Conversation
{{CONVERSATION_HISTORY}}

## User's Latest Message
{{USER_MESSAGE}}
```

#### 1.3 Add SQS Message Type
**File:** `src/lambdas/interface/core/sqs_service.py`

Add: `send_upload_interview_request()`
- request_type: 'upload_interview'
- Includes: session_id, email, conversation_id, user_message, table_analysis

#### 1.4 Background Handler Route
**File:** `deployment/.../handlers/background_handler.py`

Add handler for `request_type == 'upload_interview'`:
- Load conversation state from S3
- Run UploadInterviewHandler
- Save updated state to S3
- Send WebSocket update with response
- If `trigger_config_generation=true`, chain to config generation

### Phase 2: Backend - Integration Points

#### 2.1 Modify Upload Response
**File:** `src/lambdas/interface/actions/process_excel_unified.py`

After storing Excel file, return:
```python
{
    'success': True,
    'session_id': session_id,
    'table_analysis': {
        'columns': [...],
        'row_count': N,
        'sample_rows': first_3_rows,  # For frontend display
        'detected_patterns': {...}
    },
    'conversation_id': new_conversation_id,
    'action': 'start_interview'  # Signal to frontend
}
```

#### 2.2 Modify Config Generation
**File:** `src/lambdas/interface/actions/config_generation/__init__.py`

Accept `interview_context` in payload:
```python
interview_context = payload.get('interview_context', {})
# Include in prompt building:
# - User's stated purpose
# - Confirmed ID columns
# - Special requirements
```

### Phase 3: Frontend Changes

#### 3.1 New WebSocket Message Types
```javascript
// Register handlers for:
'upload_interview_update'     // Interview response
'upload_interview_complete'   // Ready for config gen
```

#### 3.2 Modified Upload Flow
**File:** `frontend/perplexity_validator_interface2.html`

```javascript
// After successful upload:
async function handleUploadSuccess(response) {
    // 1. Display sample rows (optional future feature)
    if (response.sample_rows) {
        showTablePreview(cardId, response.sample_rows);
    }

    // 2. Start interview conversation
    await startUploadInterview(cardId, response.session_id, response.conversation_id);
}

async function startUploadInterview(cardId, sessionId, conversationId) {
    // Register WebSocket handler
    registerCardHandler(cardId, ['upload_interview_update'], handleInterviewMessage);

    // Send initial request (empty message triggers AI analysis)
    await fetch(`${API_BASE}/upload/interview/start`, {
        method: 'POST',
        body: JSON.stringify({
            session_id: sessionId,
            conversation_id: conversationId,
            user_message: ''  // Empty = AI analyzes table first
        })
    });
}
```

#### 3.3 Interview UI
Reuse existing chat patterns:
- `addChatMessage()` for AI/user messages
- `createButtonRow()` for quick actions
- Input textarea for user responses

**Quick Action Buttons (Mode 2):**
```javascript
createButtonRow(`${cardId}-buttons`, [
    {
        text: 'Looks Good - Generate Config',
        icon: '[OK]',
        variant: 'primary',
        callback: () => confirmAndGenerate(cardId)
    },
    {
        text: 'I have more context',
        icon: '[+]',
        variant: 'secondary',
        callback: () => showInputForContext(cardId)
    }
]);
```

### Phase 4: Conversation State

#### 4.1 S3 State Structure
**Path:** `tables/{email}/{session_id}/upload_interview/{conversation_id}/state.json`

```json
{
    "conversation_id": "conv_xxx",
    "session_id": "session_xxx",
    "email": "user@example.com",
    "created_at": "2026-01-09T...",
    "status": "in_progress|ready_for_config|config_generated",
    "turn_count": 1,
    "messages": [
        {"role": "user", "content": "", "timestamp": "..."},
        {"role": "assistant", "content": "{...}", "timestamp": "..."}
    ],
    "table_analysis": {...},
    "interview_context": {
        "inferred_purpose": "...",
        "confirmed_id_columns": [...],
        "user_requirements": "..."
    },
    "config_instructions": "Final instructions for config gen"
}
```

---

## Files to Create/Modify

### New Files (isolated upload_interview action)
| File | Purpose |
|------|---------|
| `src/lambdas/interface/actions/upload_interview/__init__.py` | Handler exports, route_upload_interview_action() |
| `src/lambdas/interface/actions/upload_interview/interview.py` | UploadInterviewHandler class |
| `src/lambdas/interface/actions/upload_interview/prompts/upload_interview.md` | Interview prompt template |
| `src/lambdas/interface/actions/upload_interview/schemas/upload_interview_response.json` | JSON schema for AI response |

### Modified Files
| File | Change |
|------|--------|
| `src/lambdas/interface/core/sqs_service.py` | Add `send_upload_interview_request()` |
| `src/lambdas/interface/actions/process_excel_unified.py` | Return table_analysis with sample rows |
| `src/lambdas/interface/actions/config_generation/__init__.py` | Accept interview_context in payload |
| `deployment/deployment/interface_package/interface_lambda/handlers/background_handler.py` | Route upload_interview requests |
| `frontend/perplexity_validator_interface2.html` | Interview UI flow |

### Key Reference Files (for understanding patterns)
| File | Reference For |
|------|---------------|
| `src/lambdas/interface/actions/table_maker/interview.py` | Interview handler pattern (lines 79-200) |
| `src/lambdas/interface/actions/table_maker/conversation.py` | State management, WebSocket updates (lines 525-612) |
| `src/lambdas/interface/actions/table_maker/prompts/interview.md` | 3-mode prompt structure |
| `src/lambdas/interface/actions/table_maker/schemas/interview_response.json` | Response schema pattern |
| `frontend/perplexity_validator_interface2.html` lines 12420-12562 | `showTablePreviewInCard()` - Preview display |
| `frontend/perplexity_validator_interface2.html` lines 9362-9480 | `addChatMessage()` - Chat message display |
| `frontend/perplexity_validator_interface2.html` lines 3504-3603 | `createButtonRow()` - Action buttons |
| `frontend/perplexity_validator_interface2.html` lines 4102-4287 | WebSocket connection handling |
| `src/lambdas/interface/core/sqs_service.py` lines 95-110 | `send_table_conversation_request()` pattern |

---

## Verification Plan

1. **Unit Test Interview Handler**
   - Test Mode 1: Ambiguous table triggers questions
   - Test Mode 2: Clear table shows confirmation
   - Test Mode 3: User approval triggers config gen

2. **Integration Test**
   - Upload Excel file
   - Verify interview starts automatically
   - Respond to questions
   - Verify config generation receives context

3. **End-to-End Test**
   - Full flow: Upload → Interview → Config → Preview
   - Verify WebSocket messages at each step
   - Check conversation state persistence in S3

---

## Future Enhancement: First 3 Rows Display

After Phase 4 is complete, add:
1. Backend returns `sample_rows` in upload response
2. Frontend displays transposed table preview
3. Shows while waiting for interview response
