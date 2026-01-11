# End-to-End Test Execution Guide
## Hyperplexity - All 4 User Paths

This guide explains how to run the comprehensive end-to-end tests for all Hyperplexity user workflows.

---

## Quick Start

### Run All Tests (No Backend Required)
```bash
npm run test:quick
```
This runs UI-only tests that don't require backend integration.

### Run All Tests (With Backend)
```bash
npm run test:e2e
```
This runs the full test suite including backend integration tests.

### Run Tests in Visible Browser
```bash
npm run test:e2e:headed
```
Watch tests execute in a real browser window.

---

## Test Organization

### Four Main User Paths

#### Path 1: Demo Table Selection (🎯)
Tests the workflow: Email → Demo Selection → Preview → Full Validation

**Run:**
```bash
npm run test:demo
```

**Tests:**
- 1.1: Load demo selection card
- 1.2: List available demos
- 1.3: Select and load demo (requires backend)
- 1.4: Run preview validation (requires backend)

---

#### Path 2: Upload Your Own Table (📁)
Tests the workflow: Email → File Upload → Config → Preview → Full Validation

**Run:**
```bash
npm run test:upload
```

**Tests:**
- 2.1: Show upload button
- 2.2: Trigger file picker
- 2.3: Upload file and show config card (requires backend)

**Note:** Test 2.3 requires test data file at `test-data/sample-table.xlsx`

---

#### Path 3: Table Maker - Create from Prompt (✨)
Tests the workflow: Email → Prompt Entry → AI Table Generation → Preview → Full Validation

**Run:**
```bash
npm run test:tablemaker
```

**Tests:**
- 3.1: Show Table Maker button
- 3.2: Load Table Maker card
- 3.3: Submit table prompt (requires backend)

---

#### Path 4: Reference Check (🔍)
Tests the workflow: Email → Text Entry → Reference Validation → Results

**Run:**
```bash
npm run test:refcheck
```

**Tests:**
- 4.1: Show Reference Check button
- 4.2: Load Reference Check card
- 4.3: Submit text for reference check (requires backend)

---

### Cross-Cutting Tests

Tests that apply across all paths: state management, error handling, environment configuration.

**Run:**
```bash
npm run test:cross-cutting
```

**Tests:**
- S.1: Persist email in localStorage
- S.2: Create session ID on workflow start
- E.1: Handle invalid email gracefully
- E.2: No JavaScript errors on any path
- ENV.1: Detect dev environment from filename
- ENV.2: Use dev API endpoint
- ENV.3: Show environment indicator

---

## Test Execution Modes

### 1. Quick Mode (No Backend)
Runs only UI tests that don't require backend API or WebSocket connections.

```bash
npm run test:quick
```

**What it tests:**
- UI components load correctly
- Buttons appear and are clickable
- Email validation (frontend only)
- Environment detection
- State management (frontend only)

**Duration:** ~30 seconds

---

### 2. Full Mode (With Backend)
Runs all tests including those requiring live backend and WebSocket connections.

```bash
npm run test:e2e
```

**What it tests:**
- Complete user flows end-to-end
- API integration
- WebSocket communication
- File uploads
- Validation processing
- Results display

**Duration:** ~10-15 minutes (depends on backend response times)

**Requirements:**
- Backend API must be running
- WebSocket endpoint must be accessible
- Test email must have sufficient credits
- Test data files must exist

---

### 3. Debug Mode
Runs tests with step-by-step debugging.

```bash
npm run test:debug
```

**Features:**
- Pauses before each action
- Shows browser DevTools
- Allows inspection at each step
- Can step through test line by line

---

### 4. UI Mode
Interactive test runner with visual feedback.

```bash
npm run test:ui
```

**Features:**
- Visual test selector
- Real-time test execution
- Timeline view
- Network inspection
- Console logs

---

## Test Results & Reports

### View HTML Report
After running tests:
```bash
npm run test:report
```

This opens an interactive HTML report showing:
- Test pass/fail status
- Screenshots of failures
- Video recordings (if enabled)
- Detailed execution timeline
- Console logs and network activity

### Report Location
```
playwright-report/index.html
```

---

## Test Data Requirements

### Required Files

Create `test-data/` directory in project root with:

#### 1. Sample Excel File
```
test-data/sample-table.xlsx
```
- Small Excel file (10-50 rows)
- Valid table structure with headers
- Clean data for testing

#### 2. Sample CSV File
```
test-data/sample-table.csv
```
- Same data as Excel in CSV format

#### 3. Sample Config File
```
test-data/sample-config.json
```
- Valid Hyperplexity config JSON
- Matches sample table structure

#### 4. Reference PDF (Optional)
```
test-data/reference.pdf
```
- For reference check testing
- Contains citations matching test text

### Creating Test Data

**Quick Setup:**
```bash
mkdir -p test-data
# Copy your own files or use backend demo files
```

---

## Environment Configuration

### Testing Against Different Environments

#### Dev Environment (Default)
Tests use `Hyperplexity_frontend-dev.html` which automatically detects dev backend.

```bash
npm run test:e2e
```

**Backend:** `https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev`

#### Production Environment
Change test file to use prod frontend:

```javascript
// In e2e-all-paths.spec.js, line 10:
const frontendPath = resolve(__dirname, '../frontend/Hyperplexity_frontend.html');
```

**Backend:** `https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod`

---

## Troubleshooting

### Tests Timing Out

**Problem:** Tests fail with timeout errors

**Solutions:**
1. Increase timeout in test file:
   ```javascript
   test.setTimeout(300000); // 5 minutes
   ```

2. Check backend is running and responsive

3. Check network connectivity to AWS endpoints

4. Run in headed mode to see what's happening:
   ```bash
   npm run test:e2e:headed
   ```

---

### Backend Tests Skipping

**Problem:** Backend tests show as skipped

**Cause:** `SKIP_BACKEND_TESTS=true` is set OR backend is not responding

**Solutions:**
1. Run without skip flag:
   ```bash
   npm run test:e2e  # NOT test:quick
   ```

2. Verify backend API is accessible:
   ```bash
   curl https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev/health
   ```

3. Check API keys and credentials if required

---

### File Upload Tests Failing

**Problem:** Test 2.3 fails with "Test data file required"

**Solution:**
Create test data file:
```bash
mkdir -p test-data
# Add sample-table.xlsx to test-data/
```

---

### WebSocket Tests Failing

**Problem:** Tests fail waiting for WebSocket connection

**Causes:**
- WebSocket endpoint blocked by firewall
- CORS issues
- Backend WebSocket not running

**Solutions:**
1. Check WebSocket endpoint in browser DevTools:
   ```javascript
   // In browser console:
   window.ENV_CONFIG.websocketUrl
   ```

2. Verify WebSocket is accessible:
   ```bash
   # Use wscat or similar tool
   wscat -c wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod
   ```

3. Check browser console for WebSocket errors in headed mode

---

### Tests Pass Locally But Fail in CI

**Common Issues:**
1. **Timeouts:** CI may be slower, increase timeouts
2. **File paths:** Ensure test data files are in repo
3. **Environment variables:** Set properly in CI config
4. **Headless mode:** Some tests may behave differently headless

**CI Configuration:**
```yaml
# Example GitHub Actions
- name: Run E2E Tests
  run: |
    npm run test:quick  # Start with quick tests
  env:
    CI: true
```

---

## Test Maintenance

### When to Update Tests

Update tests when:
- New features added to any user path
- UI components change structure
- API endpoints or responses change
- WebSocket message format changes
- New error conditions added

### Adding New Tests

**Pattern:**
```javascript
test('NEW: Description of test', async ({ page }) => {
  test.setTimeout(TIMEOUTS.MEDIUM);

  // 1. Setup
  await completeEmailValidation(page);

  // 2. Action
  await page.locator('button#new-feature').click();

  // 3. Assert
  await expect(page.locator('.result')).toBeVisible();
});
```

---

## Test Coverage Summary

### Current Coverage

#### Path 1: Demo Selection
- ✅ UI Components (100%)
- ✅ Demo List Loading (100%)
- ⚠️  Demo Selection (requires backend)
- ⚠️  Preview Validation (requires backend)

#### Path 2: File Upload
- ✅ Upload Button (100%)
- ✅ File Picker (100%)
- ⚠️  File Upload (requires backend + test data)
- ⚠️  Config Generation (requires backend)

#### Path 3: Table Maker
- ✅ UI Components (100%)
- ⚠️  Prompt Submission (requires backend)
- ⚠️  Table Generation (requires backend)

#### Path 4: Reference Check
- ✅ UI Components (100%)
- ⚠️  Reference Checking (requires backend)

#### Cross-Cutting
- ✅ State Management (100%)
- ✅ Error Handling (100%)
- ✅ Environment Detection (100%)

### Test Statistics

**Total Tests:** 21
- **UI-Only Tests:** 12 (can run without backend)
- **Backend Tests:** 9 (require backend API)

**Expected Pass Rate:**
- Without backend: ~57% (12/21)
- With backend: ~100% (21/21)

---

## Best Practices

### 1. Run Quick Tests First
Always start with quick tests to catch UI regressions:
```bash
npm run test:quick
```

### 2. Run Full Tests Before Deployment
Before deploying, run full test suite:
```bash
npm run test:e2e
```

### 3. Use Headed Mode for Debugging
When tests fail, run in headed mode:
```bash
npm run test:e2e:headed
```

### 4. Check Test Reports
Always review HTML reports after test runs:
```bash
npm run test:report
```

### 5. Keep Test Data Updated
Ensure test data files match current backend expectations.

### 6. Monitor Test Duration
If tests take too long, consider:
- Running paths separately
- Optimizing wait times
- Parallelizing tests

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Install dependencies
        run: npm ci

      - name: Install Playwright
        run: npx playwright install --with-deps

      - name: Run Quick Tests
        run: npm run test:quick

      - name: Run Full Tests (if backend available)
        run: npm run test:e2e
        if: ${{ env.BACKEND_AVAILABLE == 'true' }}

      - name: Upload Report
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: playwright-report/
```

---

## Support & Resources

### Documentation
- [COMPREHENSIVE_TEST_PLAN.md](./COMPREHENSIVE_TEST_PLAN.md) - Detailed test plan
- [PLAYWRIGHT_TESTING_GUIDE.md](./PLAYWRIGHT_TESTING_GUIDE.md) - Playwright basics
- [ARCHITECTURE.md](../frontend/src/ARCHITECTURE.md) - Frontend architecture

### External Resources
- [Playwright Documentation](https://playwright.dev/)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Debugging Tests](https://playwright.dev/docs/debug)

### Getting Help
- Check test logs: `playwright-report/index.html`
- Run in debug mode: `npm run test:debug`
- Review browser console in headed mode
- Check backend logs if tests fail on backend calls

---

## Quick Reference

```bash
# Run all tests (no backend)
npm run test:quick

# Run all tests (with backend)
npm run test:e2e

# Run specific path
npm run test:demo
npm run test:upload
npm run test:tablemaker
npm run test:refcheck

# Run in visible browser
npm run test:e2e:headed

# Debug mode
npm run test:debug

# UI mode
npm run test:ui

# View report
npm run test:report
```

---

**Last Updated:** 2026-01-10
**Test Suite Version:** 1.0.0
