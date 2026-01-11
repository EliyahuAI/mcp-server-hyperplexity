# Hyperplexity Testing

Comprehensive end-to-end testing for the Hyperplexity frontend using Playwright.

## Quick Start

```bash
# Install dependencies (if not already done)
npm install

# Run all tests (UI only, skips backend tests)
npm run test:quick

# Run full E2E tests (including backend integration)
npm run test:e2e

# Run tests in headed mode (watch browser)
npm run test:e2e:headed

# Run specific path tests
npm run test:demo       # Path 1: Demo Table Selection
npm run test:upload     # Path 2: Upload Your Own Table
npm run test:tablemaker # Path 3: Table Maker
npm run test:refcheck   # Path 4: Reference Check
```

## Test Coverage

### Path 1: Demo Table Selection (4 tests)
- ✅ Load demo selection card
- ✅ List available demos
- ✅ Select and load demo (backend)
- ✅ Run preview validation (backend)

### Path 2: Upload Your Own Table (3 tests)
- ✅ Show upload button
- ✅ Trigger file picker
- ✅ Upload file and show config card (backend)

### Path 3: Table Maker (3 tests)
- ✅ Show Table Maker button
- ✅ Load Table Maker card
- ✅ Submit table prompt (backend)

### Path 4: Reference Check (3 tests)
- ✅ Show Reference Check button
- ✅ Load Reference Check card
- ✅ Submit text for reference check (backend)

### Cross-Cutting Tests (7 tests)
- ✅ Persist email in localStorage
- ✅ Create session ID on workflow start (backend)
- ✅ Handle invalid email gracefully
- ✅ No JavaScript errors on any path
- ✅ Detect dev environment from filename
- ✅ Use dev API endpoint
- ✅ Show environment indicator

## Test Results

**Current Status:** 20/20 tests passing (100%)

- **20 passing** - All UI and backend integration tests
- **0 skipped** - All tests enabled
- **0 failing** - Complete test coverage

## Test Configuration

### Environment Variables

- `TEST_EMAIL` - Email to use for testing (default: eliyahu@eliyahu.ai)
- `TEST_URL` - URL to test against (default: local file)
- `SKIP_BACKEND_TESTS` - Set to 'true' to skip backend tests

### Test Timeouts

- SHORT: 5s - Basic UI operations
- MEDIUM: 30s - API calls and animations
- LONG: 120s - WebSocket operations
- XLARGE: 300s - Full validation runs

## Testing Against Deployed Site

To test against the deployed production/staging site:

```bash
TEST_URL=https://eliyahu.ai/hyperplexity-dev npm run test:e2e
```

## Test Data

Test files are located in `/test-data/`:
- `sample-table.xlsx` - Sample Excel file for upload testing

## Documentation

Detailed testing documentation is available in `/frontend/testing/docs/`:

- `ALL_TESTS_WORKING.md` - Summary of all tests and fixes
- `WHY_BACKEND_TESTS_SKIP.md` - Explanation of backend testing strategy
- `TESTING_READY.md` - Initial test setup documentation
- `TESTS_BUTTON_ISSUE.md` - Button visibility issues and solutions
- `TEST_EMAIL_FIX.md` - Email configuration changes

## Key Issues Fixed

1. **Demo buttons not loading** - API timing issue (1-2s delay)
2. **Wrong button selection** - Selector matched hidden buttons instead of visible ones
3. **globalState not accessible** - Exposed to window for test validation
4. **WebSocket wait logic** - Changed from Map.size to sessionId check
5. **Animation timing** - Added appropriate waits for CSS animations
6. **Button selector specificity** - Used more specific selectors to avoid conflicts

## Continuous Integration

Add to your CI/CD pipeline:

```yaml
- name: Run Tests
  run: |
    npm install
    npm run test:e2e
```

For deployments, test against the deployed site:

```yaml
- name: Test Deployed Site
  run: TEST_URL=${{ env.DEPLOY_URL }} npm run test:e2e
```
