# Hyperplexity Test Suite

Comprehensive testing for Hyperplexity's security, authentication, and viewer functionality.

---

## Test Types

### 1. **Playwright E2E Tests** (Browser Automation)

**Location:** `tests/*.spec.js`

**Tests:**
- `frontend.spec.js` - Basic UI component tests
- `user-flow.spec.js` - Complete user journey (email → demo)
- `comprehensive-flow.spec.js` - All major paths
- `security-flow.spec.js` - **NEW** - JWT auth, token revocation, security violations
- `message-persistence.spec.js` - WebSocket message handling
- `e2e-all-paths.spec.js` - Exhaustive path coverage

### 2. **Python API Tests** (Backend Integration)

**Location:** `tests/test_*.py`

**Tests:**
- `test_viewer_session.py` - **NEW** - Viewer with JWT authentication
- `src/test_email_validation.py` - Email validation flow

### 3. **Manual Tests**

**Location:** `docs/TESTING_SUMMARY.md`

---

## Quick Start

### Run Playwright Tests

```bash
# Install dependencies (first time only)
npm install

# Install browsers (first time only)
npx playwright install

# Run all tests
npx playwright test

# Run specific test file
npx playwright test security-flow.spec.js

# Run in UI mode (interactive)
npx playwright test --ui

# Run with browser visible (headed mode)
npx playwright test --headed
```

### Run Python API Tests

```bash
# Test viewer session with real API
python3 tests/test_viewer_session.py

# Test with specific email/session
python3 tests/test_viewer_session.py \
  --email eliyahu@eliyahu.ai \
  --session session_20260202_144646_02c0f05c

# Test against different environment
python3 tests/test_viewer_session.py \
  --api-base https://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod
```

---

## Security Tests (NEW)

### What's Tested:

**Authentication:**
- ✅ JWT token issuance after email validation
- ✅ Token storage in sessionStorage
- ✅ Token transmission in X-Session-Token header
- ✅ Token expiration (30 days)
- ✅ Backward compatibility with email parameter

**Authorization:**
- ✅ Session ownership verification
- ✅ Email validation requirement
- ✅ Rate limiting enforcement

**Security Violations:**
- ✅ Ownership violation detection
- ✅ Path traversal prevention
- ✅ Invalid session ID format blocking
- ✅ Automatic token revocation on violations

**Token Revocation:**
- ✅ Token revoked on ownership violation
- ✅ Token revoked on path traversal attempt
- ✅ Token revoked on excessive rate limiting
- ✅ Session cleared on frontend after revocation
- ✅ Logout all devices functionality

---

## Test Session Details

**Valid Test Session:**
- Email: `eliyahu@eliyahu.ai`
- Session: `session_20260202_144646_02c0f05c`
- URL: https://eliyahu.ai/viewer?session=session_20260202_144646_02c0f05c

**This session can be used for testing:**
- Viewer mode functionality
- JWT authentication
- Session ownership verification
- Download URL generation

---

## Running Tests Locally

### Option 1: Local File Testing (Playwright)

```bash
# Start from project root
cd /path/to/perplexityValidator

# Build frontend
python3 frontend/build.py

# Run Playwright tests
npx playwright test

# Tests will load frontend/Hyperplexity_FullScript_Temp-dev.html
```

**Limitations:**
- API calls will fail (CORS from file://)
- JWT authentication requires backend
- Use mocked API responses (already configured in security-flow.spec.js)

### Option 2: Local Server Testing (Recommended)

```bash
# Terminal 1: Start local server
./start-local.sh

# Terminal 2: Run tests against local server
npx playwright test --headed

# Or run Python API tests (against production)
python3 tests/test_viewer_session.py
```

### Option 3: Production Testing

```bash
# Test against production API
python3 tests/test_viewer_session.py \
  --email eliyahu@eliyahu.ai \
  --session session_20260202_144646_02c0f05c
```

---

## Test Scenarios

### Scenario 1: First-Time User (Email Not Validated)

**Expected Flow:**
1. Enter email → Validation code sent
2. Enter 6-digit code → JWT token issued
3. Token stored in sessionStorage
4. Signed-in badge appears
5. Can access viewer with token

**Playwright Test:**
```bash
npx playwright test user-flow.spec.js
```

**Manual Test:**
1. Open http://localhost:8000/Hyperplexity_FullScript_Temp-dev.html
2. Enter email
3. Check email for code
4. Enter code
5. Verify signed-in badge appears

### Scenario 2: Returning User (Email Already Validated)

**Expected Flow:**
1. Enter email → Token issued immediately (no code)
2. Token stored in sessionStorage
3. Signed-in badge appears
4. Can access viewer with token

**Python Test:**
```bash
# Should return token immediately
python3 tests/test_viewer_session.py --email eliyahu@eliyahu.ai
```

### Scenario 3: Viewer Mode

**Expected Flow:**
1. Navigate to viewer URL with session parameter
2. If not authenticated → Email validation card shown
3. After authentication → Viewer loads with session data
4. Can download Excel and JSON

**Test:**
```bash
# Open in browser
./start-local.sh
# Navigate to: http://localhost:8000/Hyperplexity_FullScript_Temp-dev.html?mode=viewer&session=session_20260202_144646_02c0f05c
```

### Scenario 4: Demo Mode (No Auth Required)

**Expected Flow:**
1. Navigate to demo URL
2. Demo loads immediately (no email prompt)
3. No signed-in badge shown
4. Can explore demo table

**Test:**
```bash
# Playwright
npx playwright test security-flow.spec.js -g "Demo Mode"

# Manual
./start-local.sh
# Navigate to: http://localhost:8000/Hyperplexity_FullScript_Temp-dev.html?demo=TheranosticCI
```

### Scenario 5: Security Violations

**Expected Flow:**
1. Attempt ownership violation → Token revoked
2. Attempt path traversal → Token revoked
3. Exceed rate limit → Token revoked
4. Frontend clears session and shows alert

**Test:**
```bash
# Python test (includes security violation tests)
python3 tests/test_viewer_session.py
# Warning: Will revoke your token!
```

---

## Test Data

### Demo Tables (Public - No Auth)

Available in `demos/interactive_tables/`:
- `TheranosticCI` - Radiopharmaceutical competitive intelligence
- `RatioCI` - Ratio therapeutics analysis
- `HyperplexityVs` - Hyperplexity vs Competition
- `EarPatentsForTroels` - Ear patent analysis

**Access:**
```
?demo=TheranosticCI
?demo=RatioCI
?demo=HyperplexityVs
?demo=EarPatentsForTroels
```

### Test Session (Requires Auth)

- **Email:** eliyahu@eliyahu.ai
- **Session:** session_20260202_144646_02c0f05c
- **URL:** https://eliyahu.ai/viewer?session=session_20260202_144646_02c0f05c

---

## Continuous Integration

### GitHub Actions (To Be Configured)

```yaml
name: Playwright Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
      - name: Install dependencies
        run: npm ci
      - name: Install Playwright browsers
        run: npx playwright install --with-deps
      - name: Run tests
        run: npx playwright test
      - uses: actions/upload-artifact@v3
        if: always()
        with:
          name: playwright-report
          path: playwright-report/
```

---

## Debugging

### View Test Report

```bash
# After running tests
npx playwright show-report
```

### Run in Debug Mode

```bash
# Opens Playwright Inspector
npx playwright test --debug

# Run specific test in debug mode
npx playwright test security-flow.spec.js --debug
```

### Generate New Tests

```bash
# Record a test interactively
npx playwright codegen http://localhost:8000/Hyperplexity_FullScript_Temp-dev.html
```

---

## Common Issues

### Issue: "Browser not found"

**Fix:**
```bash
npx playwright install
```

### Issue: "file:// protocol CORS errors"

**Expected** - Use mocked API responses in tests or run against localhost server.

### Issue: "Token not stored in sessionStorage"

**Debug:**
```javascript
// In test
const token = await page.evaluate(() => sessionStorage.getItem('sessionToken'));
console.log('Token:', token);
```

### Issue: "Email validation code needed"

**Solutions:**
1. Use pre-validated test email
2. Mock API to return validated=true
3. Manually validate email once, then tokens last 30 days

---

## Test Coverage

### Current Coverage

- ✅ Email validation UI
- ✅ JWT token storage
- ✅ Signed-in badge display
- ✅ Demo mode (no auth)
- ✅ Viewer mode (with auth)
- ✅ Token revocation handling
- ✅ Security violation detection
- ⚠️ Rate limiting (partial - needs backend)
- ⚠️ IP-based validation (partial - needs backend)
- ❌ File upload flow (not yet tested)
- ❌ WebSocket real-time updates (mocked only)

### To Be Added

- [ ] Full validation flow (upload → config → validate)
- [ ] WebSocket connection and message handling
- [ ] Payment integration testing
- [ ] Mobile responsive testing
- [ ] Cross-browser compatibility tests
- [ ] Performance/load testing

---

## Contributing Tests

### Writing New Tests

1. **Create test file:** `tests/feature-name.spec.js`
2. **Follow pattern:**
   ```javascript
   import { test, expect } from '@playwright/test';

   test.describe('Feature Name', () => {
     test('should do something', async ({ page }) => {
       // Test code
       await page.goto(frontendUrl);
       // ... assertions
     });
   });
   ```

3. **Run test:**
   ```bash
   npx playwright test feature-name.spec.js
   ```

### Best Practices

- ✅ Use descriptive test names
- ✅ Add console.log for debugging
- ✅ Set appropriate timeouts
- ✅ Mock API calls when possible
- ✅ Test both success and failure paths
- ✅ Clean up (clear storage) between tests
- ✅ Use data-testid attributes in HTML for selectors

---

## Resources

- **Playwright Docs:** https://playwright.dev/
- **Testing Guide:** docs/PLAYWRIGHT_TESTING_GUIDE.md
- **Security Docs:** docs/SECURITY.md

---

**Last Updated:** 2026-02-02
**Maintainer:** Security & QA Team
