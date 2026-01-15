# Debug: Overnight Browser Session Rejection

## Symptom
User leaves browser window open overnight, returns, and gets rejected from lambdas. May need to re-validate email.

## Root Cause
The error handler in `frontend/src/js/06-upload.js:783-790` is overly aggressive:

```javascript
if (errorMsg.toLowerCase().includes('session') &&
    (errorMsg.toLowerCase().includes('expired') ||
     errorMsg.toLowerCase().includes('invalid'))) {
    localStorage.removeItem('sessionId');
    localStorage.removeItem('validatedEmail');  // ← PROBLEM: clears email too!
    // ...
}
```

When ANY error contains "session" + ("expired" OR "invalid"), it clears BOTH sessionId AND validatedEmail.

## TTLs to Know
| Component | TTL | Location |
|-----------|-----|----------|
| sessionStorage state | 1 hour | `99-init.js:462` |
| WebSocket connection (DynamoDB) | 2 hours | `dynamodb_schemas.py:3663` |
| Presigned S3 URLs | 5 minutes | `presigned_upload.py:172` |
| Email validation | Forever (TTL removed on success) | `dynamodb_schemas.py:1595` |
| AWS API Gateway WebSocket idle | 10 min (but we ping every 45s) | AWS default |

## Debug Steps

### 1. Check Browser Console
Look for the error message that triggered the rejection. Search for:
- "session expired"
- "session invalid"
- Any 403 errors

### 2. Check localStorage State
```javascript
// In browser console:
localStorage.getItem('validatedEmail')  // Should have email if validated
localStorage.getItem('sessionId')       // May be stale/null after overnight
```

### 3. Check What Error Triggered It
Add temporary logging to `06-upload.js` around line 780:
```javascript
console.log('[DEBUG] Error received:', errorMsg);
console.log('[DEBUG] Would clear email?',
    errorMsg.toLowerCase().includes('session') &&
    (errorMsg.toLowerCase().includes('expired') ||
     errorMsg.toLowerCase().includes('invalid')));
```

### 4. Check Backend Logs
Look in CloudWatch for the specific lambda invocation that returned the error.

## Potential Fixes

### Option A: Don't clear validatedEmail on session errors
The email validation is separate from session state. Change the handler to only clear sessionId:

```javascript
if (errorMsg.toLowerCase().includes('session') &&
    (errorMsg.toLowerCase().includes('expired') ||
     errorMsg.toLowerCase().includes('invalid'))) {
    localStorage.removeItem('sessionId');
    // DON'T clear validatedEmail - email validation is independent
    globalState.sessionId = null;
    throw new Error('Session expired - please refresh the page');
}
```

### Option B: More specific error matching
Only clear email for actual email validation errors, not generic session errors.

### Option C: Re-check email validation before clearing
```javascript
// Before clearing validatedEmail, verify it's actually invalid
const email = localStorage.getItem('validatedEmail');
if (email) {
    const stillValid = await checkEmailValidation(email);
    if (stillValid) {
        // Don't clear it - just the session is stale
        localStorage.removeItem('sessionId');
        globalState.sessionId = null;
    }
}
```

## Files Involved
- `frontend/src/js/06-upload.js` - Error handler (lines 780-792)
- `frontend/src/js/02-storage.js` - localStorage helpers
- `frontend/src/js/99-init.js` - Session state restoration
- `frontend/src/js/03-websocket.js` - WebSocket reconnection logic
- `src/shared/dynamodb_schemas.py` - Backend TTLs

## Related Commits
- `d211293d` - feat: Add deferred email validation option
- `27503e1b` - Fix WebSocket fallback polling for inactive tab validation completion
