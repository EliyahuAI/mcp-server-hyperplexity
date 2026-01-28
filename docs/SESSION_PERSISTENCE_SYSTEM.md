# Session Persistence System

## Overview

The Hyperplexity Table Validator implements a comprehensive session persistence system that automatically saves user progress and provides seamless restoration after page refreshes or navigation. This system ensures users don't lose their work when accidentally refreshing or navigating away from the application.

## Current Implementation

### Technology Stack
- **Storage**: HTML5 Session Storage (browser-native)
- **Scope**: Per-browser-tab session (clears when tab closes)
- **Capacity**: ~5-10MB typical browser limit
- **Persistence**: Survives page refreshes, back/forward navigation
- **Navigation Protection**: Warns users before losing unsaved work

### Architecture Components

#### 1. State Capture (`saveApplicationState()`)
```javascript
// Automatically triggered on:
- Form input changes (debounced 1 second)
- Page unload events
- User interactions
- Navigation events
```

**Data Saved:**
- **Card States**: Main workflow cards (card-1, card-2, etc.) with content and metadata
- **Form Data**: All input field values, checkboxes, selections (excluding file inputs)
- **Global State**: Session ID, environment config, user context
- **Processing State**: Workflow phase tracking, completion status
- **Preview Data**: Rich preview results for download functionality
- **UI State**: Scroll position, card completion status
- **Timestamps**: For automatic expiration (1 hour)

#### 2. Automatic State Restoration (`attemptStateRestore()`)
```javascript
// Triggered when:
- Page loads with existing session storage
- Meaningful progress exists (2+ cards)
- State is recent (within 1 hour)
- AUTOMATIC - no user confirmation required
```

**Restoration Process:**
1. **Validation**: Checks data integrity and age (<1 hour)
2. **Automatic Decision**: No modals - always restores if valid state exists
3. **Card Recreation**: Rebuilds cards with proper HTML structure
4. **Event Handler Reattachment**: Restores button functionality
5. **Form Data Population**: Repopulates all input fields
6. **State Synchronization**: Restores scroll position and global state

#### 3. Navigation Protection System
- **Navigation Warning**: Warns when leaving page with unsaved progress
- **Tab Visibility Detection**: Handles browser refresh vs navigation away
- **Automatic Restoration**: Silent restore on return - no user prompts
- **State Cleanup**: Automatically expires old sessions (1+ hour)

#### 4. Reset Functionality
- **Visual Reset Button**: Top-right corner, becomes prominent when state exists
- **Keyboard Shortcut**: Ctrl+Shift+R (Cmd+Shift+R on Mac)
- **Console Commands**: `resetPage()`, `hardReset()`, `clearState()`
- **Smart Clearing**: Prevents auto-save during reset process

### Data Structure

```javascript
{
  timestamp: 1234567890000,
  scrollPosition: 1250,
  globalState: {
    sessionId: "uuid-string",
    userEmail: "user@domain.com",
    environment: "dev",
    debounceTimers: undefined // Excluded from serialization
  },
  lastPreviewData: {
    enhanced_download_url: "...",
    cost_estimates: {...}
  },
  cards: [
    {
      id: "card-1",
      type: "email",
      title: "Email Validation",
      content: "<div>...</div>",
      isCompleted: true,
      isProcessing: false,
      formData: {
        email: "user@domain.com",
        code: "123456"
      }
    }
    // ... additional cards
  ],
  globalFormData: {
    // Global form inputs
  }
}
```

### Security Considerations

#### Current Security Measures
- **Session Storage Only**: Data clears when browser tab closes
- **No File Content**: File uploads excluded from persistence
- **Auto-Expiration**: Data expires after 1 hour
- **Input Validation**: Sanitizes content during save/restore

#### Security Limitations
- **Client-Side Storage**: Data visible in browser developer tools
- **No Encryption**: Data stored in plain JSON format
- **Local Access**: Anyone with device access can view saved data
- **Browser Vulnerabilities**: Subject to browser security issues

### Stale Session ID Handling (Updated January 2025)

A critical issue arises when `sessionId` is persisted across browser sessions but expires on the backend. This can cause CORS-like errors when the backend rejects requests for invalid sessions without proper CORS headers.

**Prevention Mechanisms:**
1. **Hard Refresh Cleanup**: On page reload (`IS_PAGE_RELOAD`), both sessionStorage state AND localStorage `sessionId` are cleared
2. **Age-Based Clearing**: During state restoration, sessionIds older than 30 minutes are cleared to prevent stale session errors
3. **Table Maker State Reset**: `tableMakerState` is reset when creating new cards to prevent stale `conversationId` from persisting
4. **WebSocket Validation**: Before using a restored sessionId for Table Maker, the system checks if there's an active WebSocket connection; if not, a fresh session is requested

**Files Modified:**
- `99-init.js`: Added localStorage sessionId cleanup on reload and age-based sessionId validation during restore
- `09-table-maker.js`: Added `resetTableMakerState()` function and cleanup of orphaned handlers

#### Sensitive Data Handling
- **Excluded**: File contents, passwords, sensitive API keys
- **Included**: Form inputs, session IDs, non-sensitive configuration
- **Risk Level**: Medium - contains email addresses and workflow progress

## User Experience

### Success Scenarios
1. **Accidental Refresh**: User continues exactly where they left off
2. **Navigation Away**: Back button restores complete session
3. **Browser Recovery**: Session survives browser crashes
4. **Multi-Step Process**: Complex validations preserved across steps

### Automatic Restoration Experience
- **Silent Operation**: No modals or user confirmations required
- **Seamless Return**: Users continue exactly where they left off
- **Navigation Warnings**: Prevents accidental data loss when leaving
- **Smart Cleanup**: Automatically removes stale sessions

### Reset Options
- **Subtle Button**: Small, semi-transparent in corner
- **Prominent When Needed**: Pulses when state exists
- **Multiple Methods**: Visual, keyboard, console commands

## WebSocket Message Persistence System (Implemented January 2025)

The application now includes a **server-side WebSocket message persistence system** that complements the client-side UI state persistence. This system ensures that WebSocket messages (progress updates, completion notifications) are never lost, even if the browser disconnects or the user refreshes during validation.

### Two Complementary Systems

| System | Storage | Purpose | Triggered By |
|--------|---------|---------|--------------|
| **UI State Persistence** | sessionStorage (client) | Restore cards, forms, scroll position | beforeunload, input changes |
| **WebSocket Message Persistence** | DynamoDB (server) | Replay missed WebSocket messages | Validator stall warning, page refresh |

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BACKEND                                      │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │
│  │ Validation      │───▶│ WebSocket       │───▶│ DynamoDB        │  │
│  │ Lambda          │    │ Client          │    │ Message Log     │  │
│  │                 │    │ (sends + logs)  │    │ (3-day TTL)     │  │
│  └─────────────────┘    └────────┬────────┘    └────────┬────────┘  │
│                                  │                       │           │
│                                  │              ┌────────▼────────┐  │
│                                  │              │ Message Replay  │  │
│                                  │              │ API             │  │
│                                  │              └────────┬────────┘  │
└──────────────────────────────────┼───────────────────────┼───────────┘
                                   │ WebSocket             │ HTTP
                                   ▼                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                     │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │
│  │ Message Queue   │◀───│ WebSocket       │    │ Restorable      │  │
│  │ (dedup, order)  │    │ Handler         │    │ State           │  │
│  │                 │    │                 │    │ (sessionStorage)│  │
│  └────────┬────────┘    └─────────────────┘    └────────┬────────┘  │
│           │                                              │           │
│           ▼                                              ▼           │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                     Gap Detection & Recovery                     ││
│  │  - Detects missing sequence numbers                              ││
│  │  - Fetches missed messages from API                              ││
│  │  - Replays messages through normal handlers                      ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### Backend Components

#### 1. DynamoDB Message Log Table

**Table**: `hyperplexity-message-log`

```python
# Schema (src/shared/dynamodb_schemas.py)
{
    'session_id': str,      # Partition key
    'seq_card': str,        # Sort key: "{sequence}#{card_id}"
    'card_id': str,         # Card identifier (e.g., 'preview', 'validation')
    'sequence': int,        # Monotonically increasing per session
    'message_data': dict,   # Full WebSocket message payload
    'timestamp': int,       # Unix timestamp (ms)
    'ttl': int              # Auto-delete after 3 days
}
```

#### 2. WebSocket Client Enhancement

**File**: `src/shared/websocket_client.py`

```python
def send_to_session(self, session_id: str, message: Dict, card_id: str = None):
    # Get next sequence number for this session
    seq = self._get_next_sequence(session_id)

    # Add metadata to message
    message_with_meta = {
        **message,
        '_seq': seq,
        '_card_id': card_id,
        '_timestamp': int(time.time() * 1000)
    }

    # Persist to DynamoDB (if card_id provided)
    if card_id:
        self._persist_message(session_id, card_id, seq, message_with_meta)

    # Send via WebSocket
    self._send_websocket(session_id, message_with_meta)
```

#### 3. Message Replay API

**File**: `src/lambdas/interface/actions/message_replay.py`

| Action | Parameters | Returns |
|--------|------------|---------|
| `getMessagesForCard` | `session_id`, `card_id` | All messages for a card |
| `getMessagesSince` | `session_id`, `since_seq` | Messages after sequence number |

### Frontend Components

#### 1. Message Queue Module

**File**: `frontend/src/js/03b-message-queue.js`

```javascript
// Global state for message tracking
window.messageQueueState = {
    lastReceivedSeq: {},      // card_id -> last sequence number
    seenSeqs: {},             // card_id -> Set of seen sequences
    pendingMessages: {},      // card_id -> messages awaiting ordering
    isFetching: {}            // card_id -> boolean (prevent duplicate fetches)
};

// Process incoming WebSocket message
function processIncomingMessage(data) {
    const seq = parseInt(data._seq, 10);
    const cardId = data._card_id;

    // Legacy message (no sequence) - always process
    if (seq === undefined || isNaN(seq) || !cardId) {
        return { shouldProcess: true, isOutOfOrder: false };
    }

    // Deduplication - skip if already seen
    if (seenSeqs[cardId]?.has(seq)) {
        return { shouldProcess: false, isOutOfOrder: false };
    }

    // Gap detection
    const lastSeq = lastReceivedSeq[cardId] || 0;
    const expectedSeq = lastSeq + 1;

    if (seq > expectedSeq) {
        const gap = seq - expectedSeq;
        console.log(`[MESSAGE_QUEUE] Gap detected: expected ${expectedSeq}, got ${seq}`);

        if (gap > 5) {
            // Large gap - reset tracking to avoid getting stuck
            lastReceivedSeq[cardId] = seq;
        } else {
            // Small gap - fetch missed messages
            fetchMissedMessages(cardId, lastSeq);
        }
    }

    // Track and process
    seenSeqs[cardId].add(seq);
    lastReceivedSeq[cardId] = Math.max(lastReceivedSeq[cardId] || 0, seq);

    return { shouldProcess: true, isOutOfOrder: seq !== expectedSeq };
}
```

#### 2. Warning-Based State Recovery

**File**: `frontend/src/js/99-init.js`

When the validator appears stalled (no updates for 3 minutes), the system saves restorable state:

```javascript
// Triggered when validator stall warning is shown
function saveRestorableState(cardId, phase) {
    const restorableState = {
        sessionId: globalState.sessionId,
        cardId: cardId,
        phase: phase,
        workflowPhase: globalState.workflowPhase,
        email: globalState.email,
        lastSeqs: messageQueueState.lastReceivedSeq,  // Last received sequences
        timestamp: Date.now(),
        warningTriggered: true
    };

    sessionStorage.setItem('hyperplexity_restorable_state', JSON.stringify(restorableState));
}
```

On page load, if restorable state exists:

```javascript
// In DOMContentLoaded handler
const savedRestoreState = sessionStorage.getItem('hyperplexity_restorable_state');
if (savedRestoreState) {
    const restoreState = JSON.parse(savedRestoreState);

    if (restoreState.warningTriggered && age <= 30 * 60 * 1000) {
        // Restore global state
        globalState.sessionId = restoreState.sessionId;
        globalState.email = restoreState.email;

        // Reconnect WebSocket
        connectToSession(restoreState.sessionId);

        // Fetch and replay missed messages
        const minSeq = Math.min(...Object.values(restoreState.lastSeqs));
        const result = await getAllMessagesSince(restoreState.sessionId, minSeq);

        for (const msg of result.messages) {
            dispatchReplayedMessage(msg.message_data);
        }
    }
}
```

### Message Flow During Validation

```
1. User starts validation
   └─▶ Backend sends: { type: "progress", progress: 10, _seq: 1, _card_id: "validation" }
       └─▶ Logged to DynamoDB
       └─▶ Sent via WebSocket
       └─▶ Frontend processes, tracks seq=1

2. Network hiccup - messages 15-17 lost
   └─▶ Frontend receives seq=18
   └─▶ Gap detected (expected 15, got 18)
   └─▶ Fetch messages since seq=14
   └─▶ Replay messages 15, 16, 17
   └─▶ Continue with seq=18

3. User refreshes during validation stall
   └─▶ saveRestorableState() saved lastSeqs
   └─▶ Page reloads
   └─▶ Detects warningTriggered state
   └─▶ Reconnects WebSocket
   └─▶ Fetches all messages since lastSeqs
   └─▶ Replays to rebuild UI state
```

### Key Differences from UI State Persistence

| Aspect | UI State Persistence | WebSocket Message Persistence |
|--------|---------------------|------------------------------|
| **Storage** | Client (sessionStorage) | Server (DynamoDB) |
| **Data** | UI cards, forms, scroll | WebSocket messages |
| **TTL** | 1 hour | 3 days |
| **Trigger** | Always (beforeunload) | Only during active validation |
| **Recovery** | Back/forward navigation | Validator stall + refresh |
| **Complexity** | High (button recreation) | Low (replay existing messages) |

### When Each System Is Used

1. **Normal back/forward navigation**: UI State Persistence restores cards
2. **Refresh during validation**: WebSocket Message Persistence fetches missed messages
3. **Validator stall + refresh**: Both systems work together:
   - UI State Persistence may restore card structure
   - WebSocket Message Persistence fetches/replays progress updates

### Related Files

| File | Purpose |
|------|---------|
| `src/shared/dynamodb_schemas.py` | DynamoDB table schema and persistence functions |
| `src/shared/websocket_client.py` | Sequence numbering and message logging |
| `src/lambdas/interface/actions/message_replay.py` | API for fetching missed messages |
| `frontend/src/js/03b-message-queue.js` | Client-side deduplication and gap detection |
| `frontend/src/js/99-init.js` | `saveRestorableState()`, `getRestorableState()` |
| `tests/message-persistence.spec.js` | Playwright tests for the system |

### Console Logging

```javascript
// Gap detection
[MESSAGE_QUEUE] Gap detected for card=validation: expected seq=100, got seq=102, gap=2
[MESSAGE_QUEUE] Fetching missed messages for card=validation since seq=99

// Large gap handling
[MESSAGE_QUEUE] Gap too large (8), resetting sequence tracking

// Deduplication
[MESSAGE_QUEUE] Already fetching, skipping duplicate request

// State recovery
[INIT] Found warning-triggered state, will attempt restore
[INIT] Fetched 15 missed messages for restore
```

## Future Enhancements

### Database-Based Persistence

#### Proposed Architecture
```javascript
// Server-side session storage
POST /api/sessions/save
{
  sessionId: "uuid",
  userId: "user-id",
  workflowState: {...},
  expiresAt: "2024-12-31T23:59:59Z"
}

GET /api/sessions/restore/{sessionId}
// Returns complete session state

GET /api/sessions/share/{shareCode}
// Public restoration via share code
```

#### Benefits
- **Cross-Device Access**: Sessions available on any device
- **Secure Storage**: Server-side encryption and access control
- **Collaborative Features**: Share progress via links
- **Audit Trail**: Track session history and usage
- **Data Backup**: Protected against client-side data loss

#### Share Code System
```javascript
// Generate shareable restoration links
const shareCode = generateShareCode(sessionId);
const shareUrl = `https://validator.eliyahu.ai/restore/${shareCode}`;

// Restoration flow
https://validator.eliyahu.ai/restore/ABC123
→ Loads saved session state
→ Shows preview of saved progress
→ User clicks "Continue Session"
```

#### Database Schema
```sql
CREATE TABLE session_states (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  session_data JSONB NOT NULL,
  share_code VARCHAR(10) UNIQUE,
  created_at TIMESTAMP DEFAULT NOW(),
  expires_at TIMESTAMP NOT NULL,
  access_count INTEGER DEFAULT 0,
  last_accessed_at TIMESTAMP
);
```

#### Migration Strategy
1. **Phase 1**: Add server-side storage alongside client-side
2. **Phase 2**: Preference for server storage with client fallback
3. **Phase 3**: Optional migration of existing client sessions
4. **Phase 4**: Full server-side with legacy client support

### Enhanced Features
- **Session Analytics**: Track user journey and drop-off points
- **Progress Insights**: Visualize completion rates by step
- **Recovery Tools**: Admin tools for session debugging
- **Performance Monitoring**: Track save/restore performance

## Restoration Challenges and Code Complexity

### The Dual-State Problem

One of the biggest challenges in the session persistence system is handling the fact that any given application state can be reached through **two different paths**:

1. **Original Path**: User progresses through the workflow naturally
2. **Restored Path**: State is recreated from saved session data

This dual-state nature creates significant code complexity because:

#### Event Handler Restoration
```javascript
// Original: Button created with natural event attachment
<button onclick="processTable()">Process Table</button>

// Restored: Must manually reattach events after DOM recreation
const button = cardElement.querySelector('button');
button.addEventListener('click', processTable);
```

#### Form Data Synchronization
```javascript
// Original: Form data flows naturally through user interaction
globalState.email = inputElement.value;

// Restored: Must manually populate AND sync state
inputElement.value = savedState.formData.email;
globalState.email = savedState.formData.email;
```

#### Button State Recreation
The most complex challenge is recreating dynamic button states:

```javascript
// Original workflow progression:
// [Upload File] → [File Uploaded ✓] → [Process Table] → [Processing...] → [Download Results]

// Restored state must determine:
// - Which button should be shown?
// - What state should it be in?
// - What functionality should be attached?
// - How to handle credit insufficiency?
// - Should auto-processing be triggered?
```

### Code Complexity Manifestations

#### 1. Conditional Logic Explosion
```javascript
if (isRestoring) {
    // Handle restored state
    if (cardData.formData.hasProcessed) {
        createDownloadButton();
    } else if (needsCredits()) {
        createAddCreditsButton();
    } else {
        createProcessButton();
    }
} else {
    // Handle original workflow
    // Completely different logic path
}
```

#### 2. Event Handler Duplication
Every interactive element requires two initialization paths:
- Original creation during workflow
- Restoration recreation with proper event binding

#### 3. State Validation Complexity
```javascript
// Must validate that restored state makes sense
if (cardData.type === 'preview' && !globalState.sessionId) {
    // Inconsistent state - how did we get preview without session?
    console.warn('Invalid restored state detected');
    clearState();
    return;
}
```

#### 4. Credit System Integration
The credit purchasing system adds another layer of complexity:
```javascript
// Original: User hits insufficient credits → shows Add Credits button
// Restored: Must detect credit state AND user intent for auto-processing
if (isRestoring && savedState.userIntendedToProcess && hasCredits()) {
    // Auto-trigger processing that was interrupted
    setTimeout(() => processTable(), 1000);
}
```

### Technical Debt and Maintenance Issues

#### Button Recreation Mess
The most problematic area is button state management:

```javascript
function reinitializeCardButtons(cardElement, cardData) {
    // 200+ lines of conditional logic to determine:
    // - What buttons existed originally?
    // - What state should they be in now?
    // - How to handle edge cases?
    // - Credit insufficiency scenarios
    // - Auto-processing triggers
}
```

#### Global State Synchronization
```javascript
// Must keep multiple state representations in sync:
- sessionStorage (persistent)
- globalState (runtime)
- DOM elements (visual)
- Processing state tracking
- Credit system state
```

#### Error Handling Complexity
Every restoration operation can fail in multiple ways:
- Corrupt session data
- Missing DOM elements
- Invalid state transitions
- Credit system inconsistencies
- WebSocket connection issues

### Design Patterns for Managing Complexity

#### 1. State Machine Pattern
```javascript
const workflowStates = {
    initial: { validTransitions: ['email'] },
    email: { validTransitions: ['upload', 'demo'] },
    upload: { validTransitions: ['config'] },
    config: { validTransitions: ['preview'] },
    preview: { validTransitions: ['validation', 'credits'] },
    validation: { validTransitions: ['results'] },
    results: { validTransitions: [] }
};
```

#### 2. Restoration Factory Pattern
```javascript
class CardRestorer {
    static restore(cardData, isOriginal = false) {
        const restorer = CardRestorerFactory.create(cardData.type);
        return restorer.restore(cardData, isOriginal);
    }
}
```

#### 3. Event Handler Registry
```javascript
const eventHandlers = new Map();
// Centralized event handler management for both original and restored states
```

### Future Improvements

#### Simplification Strategies
1. **Unified State Representation**: Single source of truth for all state
2. **Declarative Button States**: Define button configurations rather than imperative recreation
3. **State Validation Framework**: Comprehensive validation rules
4. **Restoration Testing**: Automated tests for all restoration scenarios

#### Architectural Changes
```javascript
// Instead of dual-path logic:
if (isRestoring) { /* complex restoration logic */ }
else { /* different original logic */ }

// Move to unified state machine:
const currentState = determineWorkflowState();
const buttonConfig = getButtonConfigForState(currentState);
renderButton(buttonConfig);
```

## Technical Implementation

### Key Functions
- `saveApplicationState()`: Core save logic with debouncing
- `restoreApplicationState()`: Complete restoration with validation
- `reinitializeCardButtons()`: Event handler reattachment (most complex function)
- `recreateProcessTableButton()`: Special handling for complex processing buttons
- `attemptStateRestore()`: Automatic restore decision logic (no modals)

### Error Handling
- **Graceful Degradation**: Continues without persistence if storage fails
- **Data Validation**: Checks integrity before restoration
- **Fallback Behavior**: Creates fresh session if restoration fails
- **User Feedback**: Clear messages about restoration status

### Performance Considerations
- **Debounced Saving**: Prevents excessive storage writes
- **Selective Restoration**: Only restores meaningful progress
- **Memory Management**: Clears expired data automatically
- **Efficient Serialization**: Excludes non-serializable objects

## Monitoring and Maintenance

### Current Logging
```javascript
console.log('[SUCCESS] Application state restored from previous session');
console.log('[INFO] Restored 4 valid cards out of 4 saved cards');
console.warn('[WARN] Could not save application state:', error);
```

### Metrics to Track
- Session save frequency and success rate
- Restoration success rate and user choices
- Average session duration and complexity
- Error rates and failure patterns

### Maintenance Tasks
- Monitor storage usage patterns
- Clean expired session data
- Update security measures as needed
- Performance optimization based on usage

## Conclusion

The current session persistence system provides robust protection against data loss with automatic, seamless restoration. The elimination of restore modals creates a smoother user experience, but the underlying dual-state complexity remains a significant architectural challenge.

### Key Strengths
- **Zero-Friction Experience**: No user prompts or confirmations required
- **Navigation Protection**: Warns before data loss but restores silently
- **Robust State Management**: Handles complex workflow states and credit system integration
- **Time-Based Cleanup**: Automatically expires stale sessions

### Technical Challenges
- **Dual-State Complexity**: Every feature must work in both original and restored contexts
- **Button Recreation Logic**: Complex conditional logic to recreate proper button states
- **Event Handler Management**: Manual reattachment of all interactive functionality
- **State Synchronization**: Multiple state representations must remain consistent

### Future Architectural Goals
The system would benefit from a complete architectural redesign using:
1. **Unified State Machine**: Single workflow state representation
2. **Declarative UI**: Button configurations rather than imperative recreation
3. **Component-Based Architecture**: Self-contained restoration logic
4. **Comprehensive Testing**: Automated validation of all restoration scenarios

While the current system effectively prevents data loss and provides excellent user experience, the underlying code complexity suggests a need for architectural simplification in future iterations.