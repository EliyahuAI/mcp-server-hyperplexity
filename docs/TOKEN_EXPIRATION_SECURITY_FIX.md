# Token Expiration Security Fix

**Issue Identified:** 2026-02-02
**Severity:** HIGH
**Status:** Proposed Solutions

---

## Problem Statement

The current token expiration mechanism provides **false security**:

1. JWT tokens expire after 24 hours ✓
2. But token renewal only requires entering an email address ✗
3. Email validation never expires ✗

**Attack Vector:**
```
Attacker learns victim's email → Enters email on site → Gets valid token immediately
```

The 24-hour token expiration adds **friction without security**.

---

## Root Cause

**Design Inconsistency:**
- Email validation proves ownership **once** (via 6-digit code)
- Token renewal **doesn't re-verify ownership** (just checks email is validated)
- Anyone who knows a validated email can get a token

---

## Proposed Solutions

### Solution 1: Long-Lived Tokens (Simplest)

**Change:** Increase token expiration to match security model

```python
# src/lambdas/interface/utils/session_manager.py
TOKEN_EXPIRATION_HOURS = 720  # 30 days (from 24 hours)
```

**Pros:**
- ✅ No code changes needed (config only)
- ✅ Better UX (stay logged in)
- ✅ Honest security model

**Cons:**
- ⚠️ Longer window if token compromised

**Recommendation:** Use for low-risk applications

---

### Solution 2: Periodic Re-Validation (Most Secure)

**Change:** Email validation expires after 90 days

```python
# src/shared/dynamodb_schemas.py - validate_email_code()

# After successful validation
validation_expiry = datetime.now(timezone.utc) + timedelta(days=90)
validation_ttl = int(validation_expiry.timestamp())

table.update_item(
    Key={'email': email},
    UpdateExpression="SET validated = :val, validated_at = :timestamp, ttl = :ttl",
    ExpressionAttributeValues={
        ':val': True,
        ':timestamp': validated_at,
        ':ttl': validation_ttl  # Expires in 90 days
    }
)
```

**Pros:**
- ✅ Actual security (periodic ownership proof)
- ✅ Detects compromised emails

**Cons:**
- ⚠️ Users re-enter codes quarterly

**Recommendation:** Use for high-security applications

---

### Solution 3: Session Management (Recommended)

**Change:** Add session layer between email validation and token issuance

**Architecture:**
```
Email Validation (90 days)
    ↓
Session (30 days) ← Created after code entry
    ↓
JWT Token (24 hours) ← Renewed automatically within session
```

**New DynamoDB Table:**
```python
# sessions table
{
    'session_id': 'abc123...',       # PK
    'email': 'user@example.com',     # GSI
    'created_at': '2026-02-02T...',
    'expires_at': '2026-03-04T...',  # 30 days
    'last_ip': '203.0.113.42',
    'ttl': 1738540800
}
```

**Implementation:**
```python
# New file: src/lambdas/interface/utils/session_store.py

import boto3
import secrets
from datetime import datetime, timezone, timedelta

sessions_table = boto3.resource('dynamodb').Table('perplexity-validator-sessions')

def create_session(email: str, ip_address: str) -> str:
    """Create session after successful code validation."""
    session_id = secrets.token_hex(32)
    session_expiry = datetime.now(timezone.utc) + timedelta(days=30)

    sessions_table.put_item(Item={
        'session_id': session_id,
        'email': email,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'expires_at': session_expiry.isoformat(),
        'last_ip': ip_address,
        'ttl': int(session_expiry.timestamp())
    })

    return session_id

def has_active_session(email: str) -> bool:
    """Check if user has an active session."""
    response = sessions_table.query(
        IndexName='email-index',
        KeyConditionExpression='email = :email',
        ExpressionAttributeValues={':email': email}
    )

    now = datetime.now(timezone.utc)
    for session in response.get('Items', []):
        expires_at = datetime.fromisoformat(session['expires_at'])
        if expires_at > now:
            return True

    return False

def invalidate_all_sessions(email: str):
    """Logout all devices for a user."""
    response = sessions_table.query(
        IndexName='email-index',
        KeyConditionExpression='email = :email',
        ExpressionAttributeValues={':email': email}
    )

    for session in response.get('Items', []):
        sessions_table.delete_item(Key={'session_id': session['session_id']})
```

**Updated Flow:**
```python
# email_validation.py

def handle_validate_code(email, code, ip_address):
    # Validate code
    result = validate_email_code(email, code, ip_address)

    if result['success'] and result['validated']:
        # Create session (30 days)
        session_id = create_session(email, ip_address)

        # Issue JWT token (24 hours)
        token = create_session_token(email)

        return {
            'success': True,
            'validated': True,
            'session_token': token,
            'session_id': session_id  # Store in frontend
        }

def handle_check_or_send_validation(email, ip_address):
    # Check if email is validated
    if is_email_validated(email):
        # Check if active session exists
        if has_active_session(email):
            # Session valid - issue new token
            token = create_session_token(email)
            return {
                'success': True,
                'validated': True,
                'session_token': token
            }
        else:
            # Session expired - require code again
            return create_email_validation_request(email)
    else:
        # Email not validated - send code
        return create_email_validation_request(email)
```

**Pros:**
- ✅ Best security/UX balance
- ✅ Token renewal without codes (within 30 days)
- ✅ Periodic re-validation (every 30 days)
- ✅ Can implement "logout all devices"
- ✅ Can track active users

**Cons:**
- ⚠️ Requires new DynamoDB table
- ⚠️ More complex implementation

**Cost:**
- DynamoDB sessions table: ~$0.01/month
- Extra read per token renewal: ~$0.001/month
- **Total:** ~$0.01/month

**Recommendation:** **Use this for production** - best overall solution

---

### Solution 4: IP Address Binding

**Change:** Require re-validation if IP address changes

```python
# dynamodb_schemas.py - check_or_send_validation()

def check_or_send_validation(email: str, ip_address: str = None) -> Dict[str, Any]:
    if is_email_validated(email):
        validation_record = get_validation_record(email)

        # Check IP address change
        if ip_address and 'last_ip' in validation_record:
            if validation_record['last_ip'] != ip_address:
                logger.warning(f"IP change for {email}: {validation_record['last_ip']} → {ip_address}")
                # Force re-validation
                return create_email_validation_request(email)

        # Update last IP
        if ip_address:
            update_last_ip(email, ip_address)

        # Issue token
        return {
            'success': True,
            'validated': True,
            'session_token': create_session_token(email)
        }
```

**Pros:**
- ✅ Detects account takeover
- ✅ Simple implementation

**Cons:**
- ⚠️ VPN users affected
- ⚠️ Mobile users with dynamic IPs

**Recommendation:** Use as **additional** security layer, not primary

---

## Recommended Implementation Plan

**Phase 1: Immediate (This Week)**
- [ ] Implement Solution 3 (Session Management)
- [ ] Create sessions DynamoDB table
- [ ] Update email_validation.py logic
- [ ] Update frontend to store session_id
- [ ] Test session expiration flow

**Phase 2: Enhanced Security (Next Week)**
- [ ] Add Solution 2 (Email validation expires in 90 days)
- [ ] Update validation record TTL logic
- [ ] Test quarterly re-validation

**Phase 3: Defense in Depth (Following Week)**
- [ ] Add Solution 4 (IP binding) as optional feature
- [ ] Make IP check configurable
- [ ] Add user setting: "Require re-validation on IP change"

---

## Configuration Settings

```python
# Recommended production settings
SESSION_EXPIRATION_DAYS = 30          # Sessions expire monthly
JWT_TOKEN_EXPIRATION_HOURS = 24       # Tokens expire daily
EMAIL_VALIDATION_EXPIRATION_DAYS = 90 # Re-validate quarterly
IP_BINDING_ENABLED = False            # Optional (causes UX friction)
```

**User Experience:**
- **Daily:** Token expires, auto-renewed (seamless)
- **Monthly:** Session expires, need to enter code
- **Quarterly:** Email validation expires, need to enter code

---

## Migration Strategy

### Step 1: Deploy Session System (Backward Compatible)

```python
# email_validation.py - add session support without breaking existing flow

def handle_validate_code(email, code, ip_address):
    result = validate_email_code(email, code, ip_address)

    if result['success'] and result['validated']:
        # New: Create session
        try:
            session_id = create_session(email, ip_address)
        except:
            session_id = None  # Fallback if table doesn't exist

        # Existing: Issue token
        token = create_session_token(email)

        return {
            'success': True,
            'validated': True,
            'session_token': token,
            'session_id': session_id  # New field, optional
        }
```

### Step 2: Enable Session Checking (Gradual Rollout)

```python
# Use feature flag for gradual rollout
USE_SESSION_MANAGEMENT = os.environ.get('USE_SESSION_MANAGEMENT', 'false').lower() == 'true'

def handle_check_or_send_validation(email, ip_address):
    if is_email_validated(email):
        if USE_SESSION_MANAGEMENT:
            # New path: check session
            if has_active_session(email):
                return issue_new_token(email)
            else:
                return create_email_validation_request(email)
        else:
            # Old path: always issue token (current behavior)
            return {
                'success': True,
                'validated': True,
                'session_token': create_session_token(email)
            }
```

### Step 3: Monitor & Enable

1. Deploy with `USE_SESSION_MANAGEMENT=false`
2. Monitor session creation for 1 week
3. Enable for 10% of users
4. Monitor for issues
5. Gradually increase to 100%

---

## Testing Checklist

**Session Management:**
- [ ] Code validation creates session
- [ ] Token renewal works within session period
- [ ] Token renewal fails after session expiry
- [ ] Multiple sessions per user work correctly
- [ ] Session cleanup (TTL) works

**Email Validation Expiration:**
- [ ] Validation expires after configured period
- [ ] Expired validation requires new code
- [ ] TTL properly set in DynamoDB

**IP Binding (if enabled):**
- [ ] IP change triggers re-validation
- [ ] Same IP allows token renewal
- [ ] VPN users can still use system

**Backward Compatibility:**
- [ ] Existing validated emails still work
- [ ] Existing tokens still valid until expiration
- [ ] No data loss during migration

---

## Security Review

**Before Fix:**
- Token expiration: Useless (anyone can renew with email)
- Email validation: Never expires
- **Attack success rate:** 100% if attacker knows email

**After Fix (Solution 3):**
- Token expiration: Short-lived (24h), auto-renewed within session
- Session expiration: Monthly (requires code)
- Email validation: Quarterly expiration
- **Attack success rate:** <1% (requires code every 30 days)

---

## References

- Original security audit: `SECURITY_FIXES_IMPLEMENTED.md`
- Session management pattern: AWS Cognito architecture
- Industry standard: OAuth 2.0 refresh tokens

---

**Document Status:** PROPOSED
**Next Action:** Review with security team, choose solution
**Implementation Priority:** HIGH (security issue)
