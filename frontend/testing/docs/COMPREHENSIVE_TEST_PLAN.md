# Comprehensive End-to-End Test Plan
## Hyperplexity Frontend - All User Paths

This document outlines comprehensive end-to-end tests for all 4 Get Started paths in the Hyperplexity application. These tests interact with the real backend API and WebSocket connections.

---

## Test Environment Setup

### Prerequisites
- Backend API running at dev endpoint: `https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev`
- WebSocket endpoint: `wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod`
- Frontend built as: `Hyperplexity_frontend-dev.html`
- Valid test email addresses
- Demo files available in backend
- Sufficient credits for testing

### Test Configuration
```javascript
// Test timeouts (WebSocket operations take time)
const SHORT_TIMEOUT = 5000;      // Basic UI operations
const MEDIUM_TIMEOUT = 30000;    // API calls
const LONG_TIMEOUT = 120000;     // Full validation runs
const XLARGE_TIMEOUT = 300000;   // Complex operations

// Test data
const TEST_EMAIL = 'test@example.com';
const TEST_FILES = {
  validExcel: 'test-data/sample-table.xlsx',
  validCSV: 'test-data/sample-table.csv',
  invalidFile: 'test-data/invalid.txt',
  largeFile: 'test-data/large-table.xlsx'
};
```

---

## Path 1: Demo Table Selection Flow

### User Journey
1. Enter email → Validate
2. Click "🎯 Explore a Demo Table"
3. Select a demo from the list
4. Preview table validation
5. Optionally run full validation
6. View results

### Test Cases

#### Test 1.1: Load Demo Selection Card
**Steps:**
1. Navigate to page
2. Enter valid email
3. Click validate button
4. Click "Explore a Demo Table"

**Expected:**
- Demo selection card appears
- List of demos loads from API
- Each demo shows: name, description
- Demo buttons are clickable

**Assertions:**
```javascript
- Card title contains "Select Demo"
- At least 1 demo button visible
- Each button has demo name and description
- No JavaScript errors
```

#### Test 1.2: Select and Load Demo
**Steps:**
1. Complete Test 1.1
2. Click first demo button
3. Wait for demo to load

**Expected:**
- Button shows loading state
- API call to `selectDemo` succeeds
- Session ID created/updated
- globalState updated with demo data
- Success message appears
- Auto-proceeds to preview card

**Assertions:**
```javascript
- globalState.sessionId is set
- globalState.excelFileUploaded === true
- globalState.configStored === true
- Preview card appears within 5 seconds
```

**Timeout:** MEDIUM_TIMEOUT (30s)

#### Test 1.3: Preview Demo Validation
**Steps:**
1. Complete Test 1.2
2. Wait for preview card
3. Observe WebSocket ticker updates

**Expected:**
- Preview card appears
- Preview validation starts automatically
- WebSocket connection established
- Ticker shows progress messages
- Preview completes with confidence score
- Results display with preview badge

**Assertions:**
```javascript
- WebSocket connected successfully
- Ticker messages received (>0)
- Confidence score displayed (0-100)
- Preview results table visible
- [PREVIEW] badges on cells
```

**Timeout:** LONG_TIMEOUT (120s)

#### Test 1.4: Full Validation from Demo
**Steps:**
1. Complete Test 1.3
2. Click "Run Full Validation" button
3. Wait for full validation to complete

**Expected:**
- Full validation starts
- WebSocket sends progress updates
- Ticker shows validation progress
- Full validation completes
- Results show full citations
- Cost deducted from balance

**Assertions:**
```javascript
- Full validation results appear
- Citations visible (not preview placeholders)
- Validation summary shows total cells
- No [PREVIEW] badges
```

**Timeout:** LONG_TIMEOUT (120s)

---

## Path 2: Upload Your Own Table Flow

### User Journey
1. Enter email → Validate
2. Click "📁 Upload Your Own Table"
3. Select Excel/CSV file
4. Upload file to S3
5. Generate or upload config
6. Preview validation
7. Full validation
8. View results

### Test Cases

#### Test 2.1: File Upload Dialog
**Steps:**
1. Navigate to page
2. Enter valid email
3. Click validate
4. Click "Upload Your Own Table"

**Expected:**
- File picker opens
- Accepts .xlsx, .xls, .csv files

**Assertions:**
```javascript
- File input element created
- Accept attribute includes .xlsx,.xls,.csv
```

**Timeout:** SHORT_TIMEOUT (5s)

#### Test 2.2: Upload Valid Excel File
**Steps:**
1. Complete Test 2.1
2. Select valid Excel file
3. Wait for upload

**Expected:**
- File uploads to S3 via presigned URL
- Progress message shows upload status
- Session ID created
- Upload confirmed with backend
- Success message appears
- Auto-proceeds to config card

**Assertions:**
```javascript
- globalState.excelFileUploaded === true
- globalState.sessionId is set
- globalState.excelS3Key exists
- Config card appears
```

**Timeout:** MEDIUM_TIMEOUT (30s)

#### Test 2.3: Generate Config with AI
**Steps:**
1. Complete Test 2.2
2. Wait for config card
3. Click "Generate Config with AI"
4. Wait for WebSocket config generation

**Expected:**
- Config generation starts
- WebSocket sends config updates
- Ticker shows generation progress
- Config completes and validates
- Auto-proceeds to preview

**Assertions:**
```javascript
- WebSocket messages received
- Config generated successfully
- globalState.configStored === true
- Preview card appears
```

**Timeout:** LONG_TIMEOUT (120s)

#### Test 2.4: Upload Existing Config
**Steps:**
1. Complete Test 2.2
2. Click "Upload Config File"
3. Select valid JSON config
4. Wait for validation

**Expected:**
- Config file uploads
- Backend validates config
- Success message appears
- Auto-proceeds to preview

**Assertions:**
```javascript
- Config validated successfully
- globalState.configStored === true
- Preview card appears
```

**Timeout:** MEDIUM_TIMEOUT (30s)

#### Test 2.5: Preview Uploaded Table
**Steps:**
1. Complete Test 2.3 or 2.4
2. Wait for preview card
3. Observe preview validation

**Expected:**
- Preview validation runs
- WebSocket progress updates
- Results appear with preview badges

**Assertions:**
```javascript
- Preview results visible
- Confidence score displayed
- [PREVIEW] badges present
```

**Timeout:** LONG_TIMEOUT (120s)

#### Test 2.6: Full Validation Uploaded Table
**Steps:**
1. Complete Test 2.5
2. Click "Run Full Validation"
3. Wait for completion

**Expected:**
- Full validation runs
- Full citations appear
- Cost deducted

**Assertions:**
```javascript
- Full results visible
- No [PREVIEW] badges
- Citations complete
```

**Timeout:** LONG_TIMEOUT (120s)

---

## Path 3: Table Maker (Create from Prompt) Flow

### User Journey
1. Enter email → Validate
2. Click "✨ Create Table from Prompt"
3. Enter prompt describing desired table
4. AI generates table structure
5. Preview validation
6. Full validation
7. View results

### Test Cases

#### Test 3.1: Table Maker Card Appears
**Steps:**
1. Navigate to page
2. Enter valid email
3. Click validate
4. Click "Create Table from Prompt"

**Expected:**
- Table Maker card appears
- Prompt textarea visible
- Submit button visible

**Assertions:**
```javascript
- Card title contains "Table Maker"
- Textarea for prompt exists
- Submit button enabled
```

**Timeout:** SHORT_TIMEOUT (5s)

#### Test 3.2: Submit Table Prompt
**Steps:**
1. Complete Test 3.1
2. Enter table prompt (e.g., "Create a table of top 10 tech companies with revenue and employees")
3. Click submit
4. Wait for table generation

**Expected:**
- Prompt submitted to backend
- WebSocket connection established
- Ticker shows generation progress
- Table structure generated
- Auto-proceeds to config/preview

**Assertions:**
```javascript
- WebSocket messages received
- Table generation completes
- Session ID created
- Next card appears
```

**Timeout:** LONG_TIMEOUT (120s)

#### Test 3.3: Preview Generated Table
**Steps:**
1. Complete Test 3.2
2. Wait for preview validation

**Expected:**
- Preview validation runs on generated table
- Results appear with data
- Confidence scores shown

**Assertions:**
```javascript
- Preview results visible
- Table data populated
- Confidence scores present
```

**Timeout:** LONG_TIMEOUT (120s)

#### Test 3.4: Full Validation Generated Table
**Steps:**
1. Complete Test 3.3
2. Click "Run Full Validation"
3. Wait for completion

**Expected:**
- Full validation completes
- Complete results with citations

**Assertions:**
```javascript
- Full validation results
- Citations complete
- Cost deducted
```

**Timeout:** LONG_TIMEOUT (120s)

---

## Path 4: Reference Check Flow

### User Journey
1. Enter email → Validate
2. Click "🔍 Check Text References"
3. Enter text to check
4. Optionally upload reference PDF
5. AI checks references
6. View results with accuracy scores

### Test Cases

#### Test 4.1: Reference Check Card Appears
**Steps:**
1. Navigate to page
2. Enter valid email
3. Click validate
4. Click "Check Text References"

**Expected:**
- Reference Check card appears
- Text input area visible
- Optional PDF upload visible
- Submit button visible

**Assertions:**
```javascript
- Card title contains "Reference Check"
- Textarea for text exists
- PDF upload option exists
- Submit button enabled
```

**Timeout:** SHORT_TIMEOUT (5s)

#### Test 4.2: Submit Text for Reference Check (No PDF)
**Steps:**
1. Complete Test 4.1
2. Enter text with references (e.g., "According to Smith (2020), climate change is accelerating.")
3. Click submit without PDF
4. Wait for check to complete

**Expected:**
- Text submitted to backend
- WebSocket connection established
- Reference check runs
- Results appear with accuracy scores

**Assertions:**
```javascript
- WebSocket messages received
- Reference check completes
- Results show reference accuracy
- Session ID created
```

**Timeout:** LONG_TIMEOUT (120s)

#### Test 4.3: Submit Text with Reference PDF
**Steps:**
1. Complete Test 4.1
2. Enter text with references
3. Upload reference PDF
4. Click submit
5. Wait for check to complete

**Expected:**
- PDF uploads to S3
- Text and PDF submitted together
- Reference check runs against PDF
- Results show which references match PDF

**Assertions:**
```javascript
- PDF uploaded successfully
- Reference check completes
- Results indicate PDF matches
```

**Timeout:** LONG_TIMEOUT (120s)

---

## Cross-Cutting Test Cases

### State Management Tests

#### Test S.1: Session Persistence
**Steps:**
1. Complete any flow to get session ID
2. Refresh page
3. Verify state restored

**Expected:**
- Email persists
- Session ID persists
- Can continue workflow

**Assertions:**
```javascript
- localStorage.sessionId === globalState.sessionId
- Email pre-filled after refresh
```

#### Test S.2: Multiple Workflow Sessions
**Steps:**
1. Complete demo flow
2. Click "Start New Session"
3. Complete upload flow
4. Verify separate sessions

**Expected:**
- Each workflow gets new session ID
- Old results still accessible
- No state pollution

**Assertions:**
```javascript
- Session IDs are different
- Each session independent
```

### Error Handling Tests

#### Test E.1: Insufficient Balance
**Steps:**
1. Use test account with 0 credits
2. Try to run full validation

**Expected:**
- Error message appears
- Link to purchase credits
- Validation blocked

**Assertions:**
```javascript
- Error message visible
- Purchase button appears
- Validation does not run
```

#### Test E.2: WebSocket Connection Failure
**Steps:**
1. Start validation
2. Simulate WebSocket disconnect

**Expected:**
- Retry connection automatically
- User notified if persistent failure
- Graceful degradation

**Assertions:**
```javascript
- Reconnection attempted
- Error message if fails
- UI remains functional
```

#### Test E.3: Invalid File Upload
**Steps:**
1. Try to upload non-Excel file
2. Try to upload oversized file

**Expected:**
- Validation error before upload
- Clear error message
- File rejected

**Assertions:**
```javascript
- Error message visible
- File not uploaded
- Can retry with valid file
```

### Performance Tests

#### Test P.1: Large Table Upload
**Steps:**
1. Upload large table (10,000+ rows)
2. Run validation

**Expected:**
- Upload completes without timeout
- Validation processes successfully
- Progress updates regular

**Assertions:**
```javascript
- File uploads < 60s
- Validation completes
- No performance degradation
```

**Timeout:** XLARGE_TIMEOUT (300s)

#### Test P.2: Multiple Concurrent Users
**Steps:**
1. Simulate 5 users on same page
2. Each runs different workflow

**Expected:**
- Each session isolated
- No interference
- All complete successfully

**Assertions:**
```javascript
- 5 separate sessions
- All workflows complete
- No crosstalk
```

---

## Test Execution Plan

### Test Order (Recommended)
1. **Phase 1: Smoke Tests** - Quick validation all paths load
   - Test 1.1, 2.1, 3.1, 4.1 (5 min)

2. **Phase 2: Demo Path** - Simplest full flow
   - Tests 1.1 - 1.4 (10 min)

3. **Phase 3: Upload Path** - Most common workflow
   - Tests 2.1 - 2.6 (15 min)

4. **Phase 4: Table Maker** - AI generation
   - Tests 3.1 - 3.4 (15 min)

5. **Phase 5: Reference Check** - Separate workflow
   - Tests 4.1 - 4.3 (10 min)

6. **Phase 6: Cross-Cutting** - State, errors, performance
   - Tests S.1 - P.2 (20 min)

**Total Estimated Time:** ~75 minutes for full suite

### Running Tests

#### Run All Paths
```bash
npm run test:e2e
```

#### Run Individual Paths
```bash
npm run test:demo         # Path 1
npm run test:upload       # Path 2
npm run test:tablemaker   # Path 3
npm run test:refcheck     # Path 4
```

#### Run with Dev Backend
```bash
npm run test:e2e:dev      # Uses dev environment
```

#### Debug Mode (Headed Browser)
```bash
npx playwright test --headed --debug
```

---

## Test Data Requirements

### Demo Selection
- Minimum 3 demo tables available in backend
- Each demo must have valid config

### File Upload
- `test-data/sample-table.xlsx` - Small valid Excel (10 rows)
- `test-data/sample-table.csv` - Small valid CSV (10 rows)
- `test-data/large-table.xlsx` - Large Excel (1000+ rows)
- `test-data/sample-config.json` - Valid config JSON
- `test-data/invalid.txt` - Invalid file type

### Table Maker
- Test prompts prepared for consistency

### Reference Check
- Sample text with 3-5 references
- `test-data/reference.pdf` - PDF with matching references

---

## Success Criteria

### All Paths Must:
- ✅ Complete without errors
- ✅ Display progress via WebSocket ticker
- ✅ Create/update session correctly
- ✅ Show appropriate results
- ✅ Handle errors gracefully
- ✅ Deduct credits appropriately
- ✅ Allow user to continue workflow

### Performance Targets:
- Email validation: < 5s
- Demo load: < 10s
- File upload: < 30s
- Config generation: < 120s
- Preview validation: < 120s
- Full validation: < 120s

### Reliability Targets:
- 99% success rate on valid inputs
- All errors handled with clear messages
- No JavaScript console errors
- WebSocket reconnection works

---

## Test Maintenance

### When to Update Tests:
- New features added to any path
- API endpoints change
- WebSocket message format changes
- UI flow changes
- New error conditions added

### Test Review Schedule:
- After each sprint/release
- Before major deployments
- After backend API changes

---

## Appendix: WebSocket Testing Patterns

### Pattern 1: Wait for Specific Message
```javascript
// Wait for completion message
await page.waitForFunction(() => {
  return window.globalState.currentValidationState === 'completed';
}, { timeout: 120000 });
```

### Pattern 2: Collect Ticker Messages
```javascript
// Monitor ticker progress
const messages = [];
await page.exposeFunction('captureTickerMessage', (msg) => {
  messages.push(msg);
});

// Inject listener
await page.evaluate(() => {
  const originalUpdate = window.updateTicker;
  window.updateTicker = function(msg) {
    window.captureTickerMessage(msg);
    return originalUpdate.apply(this, arguments);
  };
});

// Wait for messages
await page.waitForTimeout(5000);
expect(messages.length).toBeGreaterThan(0);
```

### Pattern 3: Wait for WebSocket Connection
```javascript
// Wait for WebSocket to connect
await page.waitForFunction(() => {
  return window.globalState.websockets.size > 0;
}, { timeout: 30000 });
```

---

## Next Steps

1. Implement test files for each path
2. Create test data files
3. Set up CI/CD integration
4. Document test failures
5. Create test reporting dashboard
