# Session Persistence System

## Overview

The Hyperplexity Table Validator implements a comprehensive session persistence system that automatically saves user progress and allows restoration after page refreshes or navigation. This system ensures users don't lose their work when accidentally refreshing or navigating away from the application.

## Current Implementation

### Technology Stack
- **Storage**: HTML5 Session Storage (browser-native)
- **Scope**: Per-browser-tab session (clears when tab closes)
- **Capacity**: ~5-10MB typical browser limit
- **Persistence**: Survives page refreshes, back/forward navigation

### Architecture Components

#### 1. State Capture (`saveApplicationState()`)
```javascript
// Automatically triggered on:
- Form input changes (debounced 1 second)
- Page unload events
- User interactions
```

**Data Saved:**
- **Card States**: Main workflow cards (card-1, card-2, etc.) with content and metadata
- **Form Data**: All input field values, checkboxes, selections (excluding file inputs)
- **Global State**: Session ID, environment config, user context
- **Preview Data**: Rich preview results for download functionality
- **UI State**: Scroll position, card completion status
- **Timestamps**: For automatic expiration (1 hour)

#### 2. State Restoration (`restoreApplicationState()`)
```javascript
// Triggered when:
- Page loads with existing session storage
- Only for meaningful progress (3+ cards)
- User chooses "Restore Session" from modal
```

**Restoration Process:**
1. **Validation**: Checks data integrity and age (<1 hour)
2. **Card Recreation**: Rebuilds cards with proper HTML structure
3. **Event Handler Reattachment**: Restores button functionality
4. **Form Data Population**: Repopulates all input fields
5. **State Synchronization**: Restores scroll position and global state

#### 3. Smart Restoration Logic
- **Early Stage (1-2 cards)**: Auto-clears state, starts fresh
- **Meaningful Progress (3+ cards)**: Shows restoration modal
- **Modal Choice**: User decides between restore or fresh start

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

### Smart Modal System
```
🔄 Previous Session Found
We found a previous validation session with your progress saved.

[📂 Restore Session] [🆕 Start Fresh]

Choose "Restore Session" to continue where you left off,
or "Start Fresh" for a new validation.
```

### Reset Options
- **Subtle Button**: Small, semi-transparent in corner
- **Prominent When Needed**: Pulses when state exists
- **Multiple Methods**: Visual, keyboard, console commands

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

## Technical Implementation

### Key Functions
- `saveApplicationState()`: Core save logic with debouncing
- `restoreApplicationState()`: Complete restoration with validation
- `reinitializeCardButtons()`: Event handler reattachment
- `recreateProcessTableButton()`: Special handling for complex buttons
- `showRestoreSessionModal()`: User choice interface
- `attemptStateRestore()`: Smart restore decision logic

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

The current session persistence system provides robust protection against data loss while maintaining good user experience. The client-side approach offers immediate functionality with reasonable security for the current use case. Future database integration will enable enhanced collaboration and cross-device access while addressing security limitations.