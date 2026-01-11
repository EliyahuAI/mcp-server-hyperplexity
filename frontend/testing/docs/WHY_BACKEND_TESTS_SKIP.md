# Why Backend Tests Are Currently Skipped

## The Problem

When we try to run backend tests, they **timeout** and hang. Here's why:

### Current Test Setup
```javascript
const frontendUrl = `file:///path/to/Hyperplexity_frontend-dev.html`;
```

Tests load the HTML from the local filesystem using `file://` protocol.

### What Happens During Email Validation

1. User enters email: `eliyahu@eliyahu.ai`
2. Clicks "Validate Email" button
3. Frontend makes API call:
   ```javascript
   fetch('https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev/validate', {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({
       action: 'validateEmail',
       email: 'eliyahu@eliyahu.ai'
     })
   });
   ```

### The CORS Problem

**Backend rejects the request because:**
- Origin: `file://` (not allowed by CORS)
- Backend CORS policy expects: `https://eliyahu.ai` or similar

**Result:**
- API call fails silently
- Frontend waits forever for response
- Test times out ⏱️

---

## Why `test:quick` Works

```bash
npm run test:quick
# Runs: SKIP_BACKEND_TESTS=true playwright test
```

This sets an environment variable that tells tests to skip:
- Email validation API calls
- Demo selection
- File uploads
- Table generation
- Reference checking

So tests only verify UI components, not backend integration.

---

## Solutions to Enable Backend Testing

### Solution 1: Test Against Deployed Site ✅ (Recommended)

Instead of testing local file, test your deployed site:

**Update test file:**
```javascript
// In e2e-all-paths.spec.js
const frontendUrl = process.env.TEST_URL ||
  'https://eliyahu.ai/hyperplexity-dev';
```

**Run tests:**
```bash
npm run test:e2e
```

**Pros:**
- Real end-to-end testing
- CORS works properly
- Tests actual production environment
- Backend integration works

**Cons:**
- Requires deployment to test changes
- Slower (network latency)

---

### Solution 2: Local HTTP Server ✅

Serve the HTML via HTTP instead of file://

**Setup:**
```bash
# Install HTTP server
npm install --save-dev http-server

# Add to package.json scripts:
"serve": "http-server frontend -p 3000 --cors",
"test:local": "TEST_URL=http://localhost:3000/Hyperplexity_frontend-dev.html npm run test:e2e"
```

**Run:**
```bash
# Terminal 1: Start server
npm run serve

# Terminal 2: Run tests
npm run test:local
```

**Pros:**
- Test local changes immediately
- HTTP protocol (not file://)
- Backend integration works if CORS allows localhost

**Cons:**
- Extra setup
- Backend might still block localhost origin
- Need to run server separately

---

### Solution 3: Update Backend CORS ✅

Add `file://` or `localhost` to backend CORS allowed origins.

**Backend change needed:**
```python
# In your API Gateway/Lambda CORS config
allowed_origins = [
    'https://eliyahu.ai',
    'https://www.eliyahu.ai',
    'http://localhost:3000',  # For local testing
    # DON'T add file:// - it's a security risk
]
```

**Pros:**
- Can test locally via HTTP server
- No changes to test code

**Cons:**
- Backend deployment needed
- Still can't use file:// (security risk)

---

### Solution 4: Mock Backend for Tests ⚠️

Mock API responses in tests.

**Example:**
```javascript
// Mock email validation
await page.route('**/validate', route => {
  if (route.request().postDataJSON().action === 'validateEmail') {
    route.fulfill({
      status: 200,
      body: JSON.stringify({
        success: true,
        session_id: 'test-session-123'
      })
    });
  }
});
```

**Pros:**
- Tests work from file://
- No backend needed
- Fast

**Cons:**
- Not real end-to-end testing
- Misses backend bugs
- Complex to maintain

---

## Recommended Approach

### For Development
**Use Solution 2: Local HTTP Server**

```bash
# Install once
npm install --save-dev http-server

# Add to package.json:
{
  "scripts": {
    "serve": "http-server frontend -p 3000 --cors",
    "test:local": "TEST_URL=http://localhost:3000/Hyperplexity_frontend-dev.html playwright test e2e-all-paths.spec.js"
  }
}

# Run tests with backend:
npm run serve  # Keep this running
npm run test:local
```

### For CI/CD
**Use Solution 1: Test Deployed Site**

```bash
# In CI/CD pipeline after deployment:
TEST_URL=https://eliyahu.ai/hyperplexity-dev npm run test:e2e
```

---

## Implementing Solution 1 (Test Deployed Site)

Let me show you how to set this up:

**1. Update test file to accept URL:**
```javascript
// tests/e2e-all-paths.spec.js
const frontendPath = resolve(__dirname, '../frontend/Hyperplexity_frontend-dev.html');
const frontendUrl = process.env.TEST_URL || `file://${frontendPath}`;
```

**2. Run against deployed site:**
```bash
TEST_URL=https://eliyahu.ai/hyperplexity-dev npm run test:e2e
```

**3. All backend tests now work:**
- ✅ Email validation
- ✅ Demo selection
- ✅ File upload
- ✅ Table generation
- ✅ Reference checking
- ✅ WebSocket communication

---

## Current Test Strategy

### Quick Tests (No Backend)
```bash
npm run test:quick
```
- 14 UI tests pass
- 6 backend tests skipped
- Fast: ~20 seconds
- Tests: Components, state, environment

### Full Tests (With Backend)
```bash
# Option A: Against deployed site
TEST_URL=https://eliyahu.ai/hyperplexity-dev npm run test:e2e

# Option B: Against local server
npm run serve  # Terminal 1
npm run test:local  # Terminal 2
```
- 20 tests total
- Full backend integration
- Slow: ~10-15 minutes
- Tests: Everything including API/WebSocket

---

## Why This Matters

**Without backend testing, we miss:**
- ❌ Email validation bugs
- ❌ API integration issues
- ❌ WebSocket connection problems
- ❌ Session management bugs
- ❌ Demo selection failures
- ❌ File upload errors

**With backend testing, we catch:**
- ✅ Full user workflow bugs
- ✅ API contract changes
- ✅ CORS issues
- ✅ Authentication problems
- ✅ Real-world integration issues

---

## Next Steps

Want me to:

**A) Set up local HTTP server for backend testing?**
- I'll add the server config
- Update test scripts
- You can test with backend locally

**B) Update tests to work with deployed site?**
- I'll make tests URL-configurable
- You can run against https://eliyahu.ai/hyperplexity-dev
- True end-to-end testing

**C) Both?**
- Local server for development
- Deployed site for CI/CD
- Best of both worlds

Which would you prefer?
