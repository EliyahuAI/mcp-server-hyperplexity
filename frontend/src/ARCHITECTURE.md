# Hyperplexity Frontend Architecture

## Overview

The Hyperplexity frontend is a modular, single-page application built with vanilla JavaScript. The source code is split into separate CSS and JavaScript modules that are combined into a single HTML file during the build process.

## Directory Structure

```
frontend/
├── src/
│   ├── styles/              # CSS modules
│   │   ├── 00-reset.css           # CSS reset
│   │   ├── 01-variables.css       # CSS variables and theming
│   │   ├── 02-base.css            # Base styles
│   │   ├── 03-cards.css           # Card component styles
│   │   ├── 04-buttons.css         # Button styles
│   │   ├── 05-forms.css           # Form styles
│   │   ├── 06-messages.css        # Message/alert styles
│   │   ├── 07-ticker.css          # Ticker/progress styles
│   │   └── 08-utilities.css       # Utility classes
│   │
│   ├── js/                  # JavaScript modules
│   │   ├── 00-config.js           # Configuration & global state
│   │   ├── 01-utils.js            # Utility functions
│   │   ├── 02-websocket.js        # WebSocket communication
│   │   ├── 03-ticker.js           # Progress ticker
│   │   ├── 04-cards.js            # Card system
│   │   ├── 05-chat.js             # Chat interface
│   │   ├── 06-upload.js           # File upload & demos
│   │   ├── 07-email.js            # Email validation
│   │   ├── 08-config-generation.js # Config generation
│   │   ├── 09-table-maker.js      # Table maker feature
│   │   ├── 10-upload-interview.js # Upload interview
│   │   ├── 11-preview.js          # Preview validation
│   │   ├── 12-validation.js       # Full validation
│   │   ├── 13-results.js          # Results display
│   │   ├── 14-balance.js          # Credit balance
│   │   ├── 15-reference-check.js  # Reference checking
│   │   ├── 16-sidebar.js          # Sidebar navigation
│   │   └── 99-init.js             # Initialization
│   │
│   ├── template.html        # HTML template with placeholders
│   └── ARCHITECTURE.md      # This file
│
├── build.py                 # Build script
├── Hyperplexity_frontend.html  # Built output (do not edit)
└── README.md               # Build instructions
```

## Module System

### Load Order

Modules are loaded in numerical order (00, 01, 02, etc.). This ensures dependencies are available when needed.

**CSS Load Order:**
1. Reset → Variables → Base → Components → Utilities

**JavaScript Load Order:**
1. Config/State → Utils → Core Systems → Features → Initialization

### Naming Convention

- **00-09**: Foundation (config, utils, core systems)
- **10-19**: Features (specific functionality)
- **90-99**: Initialization and bootstrapping

## CSS Architecture

### 00-reset.css
**Purpose**: Normalize browser default styles
- Resets margins, paddings, box-sizing
- Sets consistent font rendering
- Removes default button/input styles

### 01-variables.css
**Purpose**: CSS custom properties (design tokens)
- Color palette (primary, secondary, success, error, etc.)
- Typography scale (font sizes, weights, line heights)
- Spacing scale (margins, paddings)
- Breakpoints for responsive design
- Z-index layers

**Key Variables:**
```css
--color-primary: #4a90e2;
--color-success: #4caf50;
--color-error: #f44336;
--font-size-base: 16px;
--spacing-unit: 8px;
```

### 02-base.css
**Purpose**: Base HTML element styles
- Typography defaults
- Link styles
- Global layout (body, html)
- Scrollbar customization

### 03-cards.css
**Purpose**: Card component system
- `.card` - Main card container
- `.card-header` - Title and icon area
- `.card-content` - Main content area
- `.card-footer` - Action buttons area
- `.final-state` - Success/error states

### 04-buttons.css
**Purpose**: Button styles and variants
- `.std-button` - Base button class
- `.primary`, `.secondary`, `.tertiary` - Color variants
- `.selected`, `.disabled` - State modifiers
- Icon buttons and button groups

### 05-forms.css
**Purpose**: Form controls and inputs
- Text inputs, textareas
- File inputs and drop zones
- Select dropdowns
- Form validation states
- Drag-and-drop areas

### 06-messages.css
**Purpose**: Alert and notification styles
- `.message` - Base message class
- `.message-success`, `.message-error`, `.message-info` - Variants
- Inline messages and toasts

### 07-ticker.css
**Purpose**: Progress ticker and status bar
- `.ticker-container` - Main ticker wrapper
- `.ticker-message` - Rotating status messages
- Progress bar animations
- Confidence score indicators

### 08-utilities.css
**Purpose**: Utility classes
- Display utilities (`.hidden`, `.flex`, `.block`)
- Text alignment (`.text-center`, `.text-left`)
- Spacing utilities (`.mt-1`, `.mb-2`, `.p-3`)
- Color utilities (`.text-primary`, `.bg-success`)

## JavaScript Architecture

### Module Dependencies

```
00-config.js (no dependencies)
    ↓
01-utils.js (uses config)
    ↓
02-websocket.js (uses config, utils)
    ↓
03-ticker.js (uses config, utils)
    ↓
04-cards.js (uses config, utils, ticker)
    ↓
05-chat.js (uses config, utils, cards)
    ↓
06-upload.js (uses config, cards, chat)
07-email.js (uses config, cards, chat)
08-config-generation.js (uses config, cards, chat, websocket)
... (features use foundation modules)
    ↓
99-init.js (uses all modules)
```

### Foundation Modules (00-09)

#### 00-config.js
**Purpose**: Configuration and global state management

**Key Exports:**
- `API_BASE` - Backend API endpoint
- `WEBSOCKET_API_URL` - WebSocket endpoint
- `globalState` - Application state object
- `referenceCheckState` - Reference check state
- `ENV_CONFIG` - Environment configuration

**Global State Structure:**
```javascript
globalState = {
    email: '',
    sessionId: null,
    websockets: new Map(),
    cardCounter: 0,
    excelFileUploaded: false,
    configStored: false,
    workflowPhase: 'initial',
    // ... more state properties
}
```

**Functions:**
- `detectEnvironment()` - Auto-detect dev/test/prod
- `setEnvironment(env)` - Manually set environment
- `ensureProcessingState()` - Initialize processing state
- `checkForTestingOverrides()` - Check URL params for testing

#### 01-utils.js
**Purpose**: Utility functions used across the app

**Key Functions:**
- `generateCardId()` - Generate unique card IDs
- `debounce(func, delay)` - Debounce function calls
- `formatTimestamp(date)` - Format dates
- `escapeHtml(text)` - Sanitize HTML
- `calculateConfidenceColor(score)` - Map score to color
- `truncateText(text, maxLength)` - Truncate long text

#### 02-websocket.js
**Purpose**: WebSocket connection management

**Key Functions:**
- `createWebSocket(cardId, action, payload)` - Establish connection
- `handleWebSocketMessage(event, cardId)` - Handle incoming messages
- `closeWebSocket(cardId)` - Close connection
- `getWebSocketStatus(cardId)` - Check connection status

**Message Types Handled:**
- `progress` - Progress updates
- `result` - Final results
- `error` - Error messages
- `thinking` - Processing status

#### 03-ticker.js
**Purpose**: Progress ticker and status updates

**Key Functions:**
- `addTickerMessage(message, priority)` - Add message to queue
- `updateTicker()` - Update ticker display
- `startTicker(cardId)` - Start ticker for card
- `stopTicker(cardId)` - Stop ticker
- `setTickerMessage(message)` - Set immediate message

#### 04-cards.js
**Purpose**: Card system - main UI component

**Key Functions:**
- `createCard(options)` - Create new card
- `showMessage(containerId, message, type)` - Show message in card
- `showFinalCardState(cardId, message, state)` - Show completion state
- `updateCardProgress(cardId, progress)` - Update progress bar
- `showThinkingInCard(cardId, message)` - Show thinking indicator
- `completeThinkingInCard(cardId, message)` - Complete thinking state
- `markButtonSelected(button, newText)` - Highlight selected button
- `markButtonUnselected(button, originalText)` - Reset button state

**Card Options:**
```javascript
{
    id: 'card-1',
    icon: '📊',
    title: 'Card Title',
    subtitle: 'Description',
    content: '<div>HTML content</div>',
    buttons: [
        {
            text: 'Button Text',
            icon: '✓',
            variant: 'primary',
            callback: async function() { }
        }
    ]
}
```

#### 05-chat.js
**Purpose**: Chat-style interface for conversations

**Key Functions:**
- `createChatCard(options)` - Create chat interface card
- `addChatMessage(cardId, message, type)` - Add message to chat
- `showChatThinking(cardId)` - Show typing indicator
- `hideChatThinking(cardId)` - Hide typing indicator
- `setChatInputEnabled(cardId, enabled)` - Enable/disable input

**Message Types:**
- `user` - User messages
- `assistant` - AI responses
- `system` - System notifications
- `error` - Error messages

### Feature Modules (06-16)

#### 06-upload.js
**Purpose**: File upload, demo selection, S3 integration

**Key Functions:**
- `createUploadOrDemoCard()` - Initial choice card
- `createUploadCard()` - File upload interface
- `proceedWithDemo(cardId)` - Start demo flow
- `proceedWithUpload(cardId)` - Start upload flow
- `createSelectDemoCard()` - Demo selection UI
- `loadAvailableDemos(cardId)` - Fetch demo list
- `selectDemo(cardId, demoName)` - Load selected demo
- `setupFileUpload(cardId)` - Setup drag-drop
- `validateExcelFile(file)` - Validate Excel file
- `uploadExcelFile(cardId, file)` - Upload to S3
- `handleConfigUpload(event, cardId)` - Upload config file

**S3 Upload Flow:**
1. Request presigned URL from backend
2. Upload file directly to S3
3. Confirm upload completion
4. Backend processes file metadata

#### 07-email.js
**Purpose**: Email validation and verification

**Key Functions:**
- `createEmailCard()` - Email input card
- `validateEmail(email)` - Basic email validation
- `sendVerificationCode(email)` - Send verification email
- `verifyCode(email, code)` - Verify entered code
- `handleEmailSubmit(cardId)` - Process email submission

**Flow:**
1. User enters email
2. Backend sends verification code
3. User enters code
4. Session established

#### 08-config-generation.js
**Purpose**: AI-powered configuration generation

**Key Functions:**
- `createConfigurationCard()` - Config generation UI
- `generateConfigWithAI(cardId)` - Start AI generation
- `handleConfigWebSocket(event, cardId)` - WebSocket message handling
- `displayGeneratedConfig(cardId, config)` - Show generated config
- `editConfig(cardId, config)` - Manual config editing
- `validateAndProceed(cardId, config)` - Validate config

**WebSocket Message Types:**
- `thinking` - AI thinking/processing
- `column_analysis` - Column interpretation
- `config_draft` - Initial config
- `config_complete` - Final config
- `error` - Generation errors

#### 09-table-maker.js
**Purpose**: Interactive table creation from prompts

**Key Functions:**
- `createTableMakerCard()` - Table maker interface
- `submitTablePrompt(cardId, prompt)` - Send user prompt
- `handleTableMakerMessage(cardId, message)` - Process AI responses
- `displayColumnPreview(cardId, columns)` - Show columns
- `confirmTableGeneration(cardId)` - Finalize table

**Flow:**
1. User describes desired table
2. AI suggests columns and validation
3. User reviews and confirms
4. Table configuration created

#### 10-upload-interview.js
**Purpose**: Guided interview for uploaded tables

**Key Functions:**
- `createUploadInterviewCard(cardId, data)` - Interview UI
- `handleInterviewMessage(cardId, message)` - Process responses
- `submitInterviewAnswer(cardId, answer)` - Send user input
- `completeInterview(cardId, config)` - Finish interview

**Use Case**: When uploading ambiguous tables, guide user through clarifying questions.

#### 11-preview.js
**Purpose**: Preview validation (sample rows)

**Key Functions:**
- `createPreviewCard()` - Preview interface
- `startPreview(cardId)` - Begin preview validation
- `handlePreviewWebSocket(event, cardId)` - Process updates
- `displayPreviewResults(cardId, results)` - Show results
- `proceedToFullValidation(cardId)` - Continue to full

**Flow:**
1. Validate first 10-25 rows
2. Show results and cost estimate
3. User decides whether to proceed

#### 12-validation.js
**Purpose**: Full table validation

**Key Functions:**
- `createValidationCard()` - Validation interface
- `startValidation(cardId)` - Begin full validation
- `handleValidationWebSocket(event, cardId)` - Process updates
- `displayValidationProgress(cardId, progress)` - Show progress
- `handleValidationComplete(cardId, results)` - Show completion

**Progress Updates:**
- Row count and ETA
- Validation status per row
- Confidence scores
- Error detection

#### 13-results.js
**Purpose**: Display validation results

**Key Functions:**
- `createResultsCard(results)` - Results display
- `displayResultsTable(results)` - Format results table
- `exportResults(format)` - Export to Excel/CSV/JSON
- `showValidationSummary(results)` - Show statistics
- `downloadResultsFile(sessionId)` - Download results

**Result Metrics:**
- Total rows validated
- Confidence scores
- Validation status
- Error breakdown
- Processing time and cost

#### 14-balance.js
**Purpose**: Credit balance management

**Key Functions:**
- `checkBalance()` - Query current balance
- `displayBalance(balance)` - Show balance in UI
- `handleInsufficientBalance()` - Show purchase prompt
- `addCredits(quantity)` - Add credits to cart
- `refreshBalanceDisplay()` - Update balance UI

**Integration**: Works with Squarespace product component for credit purchases.

#### 15-reference-check.js
**Purpose**: Reference/citation validation

**Key Functions:**
- `createReferenceCheckCard()` - Reference check UI
- `submitTextForChecking(cardId, text)` - Submit text
- `uploadReferencePDF(cardId, file)` - Upload reference PDF
- `processReferenceCheck(cardId)` - Validate references
- `displayReferenceResults(cardId, results)` - Show results

**Features:**
- Extract claims from text
- Validate against provided PDF
- Show confidence scores
- Highlight unsupported claims

#### 16-sidebar.js
**Purpose**: Sidebar navigation (if implemented)

**Key Functions:**
- `createSidebar()` - Create sidebar
- `updateSidebarState(phase)` - Update based on workflow
- `toggleSidebar()` - Show/hide sidebar
- `navigateToPhase(phase)` - Jump to workflow phase

### Initialization (99-init.js)

#### 99-init.js
**Purpose**: Application initialization and bootstrapping

**Key Responsibilities:**
1. Wait for DOM to be ready
2. Check for mobile devices
3. Initialize global state from localStorage
4. Create initial email card
5. Set up event listeners
6. Check for testing overrides

**Initialization Sequence:**
```javascript
DOMContentLoaded →
    Check mobile →
    Restore session →
    Detect environment →
    Create email card →
    Start application
```

## Build System

### build.py

**Purpose**: Combine modular sources into single HTML file

**Process:**
1. Load `template.html`
2. Read all CSS files in order (00-08)
3. Read all JS files in order (00-99)
4. Wrap JS in IIFE (Immediately Invoked Function Expression)
5. Replace `{{CSS}}` and `{{JS}}` placeholders
6. Write to `Hyperplexity_frontend.html`

**Usage:**
```bash
# Build once
python build.py

# Watch mode (rebuild on changes)
python build.py --watch
```

**Build Time**: ~20ms per build

### IIFE Wrapper

JavaScript is wrapped in an IIFE to prevent global scope pollution:

```javascript
(function() {
    // All modules loaded here
    // Functions explicitly added to window are global
})();
```

**Global Exports:**
Only functions that need to be called from `onclick=""` handlers are exported:
```javascript
window.proceedWithDemo = proceedWithDemo;
window.selectDemo = selectDemo;
window.validateEmail = validateEmail;
```

## State Management

### Global State

All application state is stored in `globalState` object:

```javascript
globalState = {
    // User identity
    email: '',
    sessionId: null,

    // Workflow tracking
    workflowPhase: 'initial', // initial, upload, config, preview, validating, completed
    excelFileUploaded: false,
    configStored: false,

    // Active connections
    websockets: new Map(),

    // UI state
    cardCounter: 0,
    activeCardId: null,

    // Progress tracking
    cardProgress: {},
    currentConfidenceScore: null,

    // Feature flags
    isReferenceCheck: false,
    hasInsufficientBalance: false
}
```

### Local Storage

Persistent data stored in browser:
- `sessionId` - User session ID
- `validatedEmail` - Verified email address
- `hyperplexity_environment` - Selected environment (dev/test/prod)

### Session Management

1. **New User**: No sessionId → Create new session on email validation
2. **Returning User**: sessionId exists → Restore session
3. **Session Expiry**: Backend validates sessionId, clears if expired

## Workflow Phases

### Phase 1: Email Validation
- Module: `07-email.js`
- Card: Email verification
- Outcome: `globalState.email` and `globalState.sessionId` set

### Phase 2: Get Started
- Module: `06-upload.js`
- Card: Choice card (demo, upload, table maker, reference check)
- Outcome: User selects workflow path

### Phase 3a: Demo Selection (Demo Path)
- Module: `06-upload.js`
- Card: Demo selection
- Outcome: Pre-configured table and config loaded

### Phase 3b: File Upload (Upload Path)
- Module: `06-upload.js`
- Card: File upload
- Outcome: Excel file uploaded to S3, `globalState.excelFileUploaded = true`

### Phase 3c: Table Maker (Prompt Path)
- Module: `09-table-maker.js`
- Card: Table maker interview
- Outcome: Table structure defined via AI conversation

### Phase 4: Configuration
- Module: `08-config-generation.js`
- Card: Config generation/selection
- Outcome: Validation configuration established, `globalState.configStored = true`

### Phase 5: Preview
- Module: `11-preview.js`
- Card: Preview validation
- Outcome: Sample results shown, cost estimated

### Phase 6: Full Validation
- Module: `12-validation.js`
- Card: Full validation progress
- Outcome: All rows validated

### Phase 7: Results
- Module: `13-results.js`
- Card: Results display
- Outcome: Download results, view summary

## API Integration

### Backend Endpoints

**Main API**: `API_BASE/validate` (POST)
- All non-upload actions use this endpoint
- `action` parameter determines behavior

**Upload API**: `API_BASE/upload` (POST)
- Used for file uploads via FormData

**WebSocket API**: `WEBSOCKET_API_URL`
- Real-time updates during long operations

### Common Actions

```javascript
// Request format
{
    action: 'actionName',
    email: globalState.email,
    session_id: globalState.sessionId,
    // ... action-specific params
}

// Response format
{
    success: true/false,
    error: 'error message',  // if success=false
    // ... response data
}
```

**Action Types:**
- `validateEmail` - Send verification code
- `verifyCode` - Verify email code
- `listDemos` - Get available demos
- `selectDemo` - Load demo table
- `requestPresignedUrl` - Get S3 upload URL
- `confirmUploadComplete` - Confirm S3 upload
- `validateConfig` - Validate configuration
- `startPreview` - Begin preview validation
- `startFullValidation` - Begin full validation
- `getResults` - Fetch validation results
- `checkBalance` - Get credit balance

## WebSocket Protocol

### Connection

```javascript
const ws = new WebSocket(
    `${WEBSOCKET_API_URL}?sessionId=${sessionId}&action=${action}`
);
```

### Message Format

```javascript
// Client → Server
{
    action: 'start_validation',
    session_id: '...',
    config: { }
}

// Server → Client
{
    type: 'progress',
    data: {
        row: 42,
        total: 100,
        confidence: 85,
        message: 'Validating row 42...'
    }
}
```

**Message Types:**
- `thinking` - AI processing
- `progress` - Operation progress
- `result` - Final result
- `error` - Error occurred

## Adding New Features

### Step 1: Create New Module

```bash
# Create new JS module
touch frontend/src/js/17-my-feature.js
```

```javascript
/* ========================================
 * 17-my-feature.js - My Feature Description
 *
 * Purpose: What this module does
 *
 * Dependencies: 00-config.js, 04-cards.js
 * ======================================== */

function createMyFeatureCard() {
    const cardId = generateCardId();

    const card = createCard({
        id: cardId,
        icon: '🎉',
        title: 'My Feature',
        subtitle: 'Feature description',
        content: '<div>Feature content</div>',
        buttons: [
            {
                text: 'Action',
                variant: 'primary',
                callback: async function() {
                    await handleMyFeatureAction(cardId);
                }
            }
        ]
    });

    return card;
}

async function handleMyFeatureAction(cardId) {
    try {
        showThinkingInCard(cardId, 'Processing...');

        // Your logic here

        completeThinkingInCard(cardId, 'Complete!');
    } catch (error) {
        showMessage(`${cardId}-messages`, error.message, 'error');
    }
}

// Export to global scope if needed
window.createMyFeatureCard = createMyFeatureCard;
```

### Step 2: Add CSS (if needed)

```bash
touch frontend/src/styles/09-my-feature.css
```

```css
/* My Feature Styles */
.my-feature-container {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-unit);
}

.my-feature-item {
    padding: calc(var(--spacing-unit) * 2);
    background: var(--color-background-light);
    border-radius: 8px;
}
```

### Step 3: Rebuild

```bash
python build.py
```

### Step 4: Test

```bash
npx playwright test
```

### Step 5: Write Tests

```javascript
// tests/my-feature.spec.js
import { test, expect } from '@playwright/test';

test.describe('My Feature', () => {
    test('should create feature card', async ({ page }) => {
        await page.goto(frontendUrl);

        // Trigger your feature
        await page.evaluate(() => {
            window.createMyFeatureCard();
        });

        // Assert card appears
        const card = page.locator('.card').last();
        await expect(card.locator('.card-title')).toHaveText('My Feature');
    });
});
```

## Debugging

### Browser DevTools

1. Open `Hyperplexity_frontend.html` in browser
2. Open DevTools (F12)
3. Check Console for errors
4. Use Network tab for API calls
5. Use Application tab for localStorage

### Common Debug Patterns

```javascript
// Log state changes
console.log('[MY_FEATURE] Current state:', globalState);

// Log API requests
console.log('[API] Request:', { action: 'myAction', data });

// Log WebSocket messages
console.log('[WS] Message received:', message);

// Add error boundaries
try {
    await riskyOperation();
} catch (error) {
    console.error('[MY_FEATURE] Error:', error);
    showMessage(cardId, `Error: ${error.message}`, 'error');
}
```

### Build Watch Mode

```bash
python build.py --watch
```

Auto-rebuilds on file changes, so you can immediately refresh browser to see updates.

## Performance Considerations

### Module Loading

- All modules loaded on page load (~570KB)
- IIFE wrapper prevents scope pollution
- No lazy loading currently implemented

### Future Optimization Ideas

1. **Code Splitting**: Load feature modules on demand
2. **Minification**: Minify CSS/JS in production builds
3. **Lazy Loading**: Load features when first used
4. **Tree Shaking**: Remove unused code
5. **Caching**: Add service worker for offline support

## Testing Strategy

### Unit Tests
- Test individual functions in isolation
- Mock dependencies
- Fast feedback loop

### Integration Tests
- Test module interactions
- Test API integration
- Test WebSocket communication

### End-to-End Tests
- Test complete user flows
- Use Playwright for browser automation
- Test across multiple browsers

**See**: `docs/PLAYWRIGHT_TESTING_GUIDE.md` for detailed testing documentation.

## Common Patterns

### Creating a New Card

```javascript
const cardId = generateCardId();
const card = createCard({
    id: cardId,
    icon: '📝',
    title: 'Card Title',
    subtitle: 'Description',
    content: '<div>Content</div>'
});
```

### Showing Progress

```javascript
showThinkingInCard(cardId, 'Processing...');
// ... do work ...
completeThinkingInCard(cardId, 'Done!');
```

### WebSocket Communication

```javascript
const ws = createWebSocket(cardId, 'myAction', {
    param1: 'value1'
});

// Handle messages in separate function
function handleMyWebSocket(event, cardId) {
    const message = JSON.parse(event.data);

    if (message.type === 'progress') {
        updateProgress(cardId, message.data);
    } else if (message.type === 'result') {
        displayResults(cardId, message.data);
    }
}
```

### API Calls

```javascript
const response = await fetch(`${API_BASE}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        action: 'myAction',
        email: globalState.email,
        session_id: globalState.sessionId,
        // ... params
    })
});

const data = await response.json();

if (!data.success) {
    throw new Error(data.error || 'Request failed');
}

// Use data.result
```

## Environment Configuration

### Environments

- **dev**: Development (wqamcddvub...amazonaws.com/dev)
- **test**: Testing (a0tk95o95g...amazonaws.com/prod)
- **staging**: Staging (same as test)
- **prod**: Production (a0tk95o95g...amazonaws.com/prod)

### Detection Methods

1. URL parameter: `?env=dev`
2. Page name: `/page-name-dev`
3. localStorage: `hyperplexity_environment`
4. Default: `prod`

### Manual Override

```javascript
// In browser console
window.hyperplexityEnv.set('dev');
window.hyperplexityEnv.current(); // 'dev'
```

## Security Considerations

### XSS Prevention

- Always use `escapeHtml()` for user input
- Never use `innerHTML` with unvalidated data
- Sanitize all text before rendering

### CORS

- API endpoints configured for specific origins
- WebSocket requires valid session ID
- File uploads use presigned URLs (time-limited)

### Session Management

- Session IDs stored in localStorage
- Backend validates session on each request
- Sessions expire after inactivity

## Browser Support

### Minimum Requirements

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

### Features Used

- ES6+ JavaScript (arrow functions, async/await, classes)
- CSS Custom Properties (variables)
- Fetch API
- WebSocket API
- LocalStorage API
- File API (drag and drop)

### Polyfills

None currently required for target browsers.

## Contributing

### Before Making Changes

1. Read this architecture doc
2. Understand module dependencies
3. Check existing patterns
4. Write tests first (TDD)

### Code Style

- Use 4-space indentation
- Add descriptive comments
- Use meaningful variable names
- Follow existing patterns
- Add JSDoc for complex functions

### Pull Request Checklist

- [ ] Code follows existing patterns
- [ ] Tests added/updated
- [ ] Build succeeds (`python build.py`)
- [ ] Tests pass (`npx playwright test`)
- [ ] No console errors
- [ ] Documentation updated

## Troubleshooting

### Problem: Card not appearing

**Check:**
1. Card ID is unique (`generateCardId()`)
2. `createCard()` returns element
3. Element appended to `#cardContainer`
4. No JavaScript errors in console

### Problem: Function not found

**Check:**
1. Function exported to window
2. Module loaded before use
3. Module number ensures correct order
4. Function name spelled correctly

### Problem: State not persisting

**Check:**
1. Using `globalState` object
2. Not overwriting globalState
3. localStorage for persistent data
4. Session ID included in API calls

### Problem: Build not updating

**Check:**
1. Saved all files
2. Build script completed
3. Refreshed browser (hard refresh: Ctrl+Shift+R)
4. Watch mode running (`python build.py --watch`)

## Resources

- **Playwright Docs**: `docs/PLAYWRIGHT_TESTING_GUIDE.md`
- **Build Instructions**: `frontend/README.md`
- **API Documentation**: (backend docs)
- **Design System**: `frontend/src/styles/01-variables.css`

---

**Last Updated**: 2026-01-10
**Frontend Version**: Modular v2.0
**Lines of Code**: ~15,418 (built), ~15,000 (source)
**Modules**: 26 (9 CSS + 17 JS)
