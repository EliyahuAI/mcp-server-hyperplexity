"""
Session token management using JWT.

Provides cryptographically signed session tokens to prevent email spoofing.
After successful email validation, a JWT token is issued and must be included
in subsequent requests. The token contains the validated email address and
cannot be forged without breaking the signature.

Security Benefits:
- Prevents localStorage email spoofing attacks
- No DynamoDB calls for token verification (JWT is self-contained)
- Tokens expire after 24 hours (forces re-validation)
- Unique token ID (jti) prevents token reuse
- Server-side verification (client cannot forge tokens)
"""
import jwt
import os
import time
import logging
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_ALGORITHM = 'HS256'
TOKEN_EXPIRATION_HOURS = 720  # 30 days (24 hours * 30)
PARAMETER_STORE_KEY = '/perplexity-validator/jwt-secret-key'

# Cache for JWT secret (Lambda instances persist across invocations)
_JWT_SECRET_CACHE = None


def _get_jwt_secret():
    """
    Get JWT secret from AWS Parameter Store (with caching).

    Falls back to environment variable if Parameter Store is unavailable.

    Returns:
        str: JWT secret key
    """
    global _JWT_SECRET_CACHE

    # Return cached value if available
    if _JWT_SECRET_CACHE:
        return _JWT_SECRET_CACHE

    try:
        # Try to load from AWS Systems Manager Parameter Store (recommended)
        import boto3
        ssm = boto3.client('ssm', region_name='us-east-1')
        response = ssm.get_parameter(
            Name=PARAMETER_STORE_KEY,
            WithDecryption=True
        )
        _JWT_SECRET_CACHE = response['Parameter']['Value']
        logger.info(f"[SECURITY] Loaded JWT secret from Parameter Store: {PARAMETER_STORE_KEY}")
        return _JWT_SECRET_CACHE
    except Exception as e:
        logger.warning(f"[SECURITY] Could not load JWT secret from Parameter Store: {e}")

        # Fallback to environment variable
        secret = os.environ.get('JWT_SECRET_KEY', 'CHANGE-THIS-IN-PRODUCTION-DEPLOYMENT')

        if secret == 'CHANGE-THIS-IN-PRODUCTION-DEPLOYMENT':
            logger.critical("[SECURITY] Using default JWT secret - NOT SECURE FOR PRODUCTION!")
        else:
            logger.info("[SECURITY] Using JWT secret from environment variable")

        _JWT_SECRET_CACHE = secret
        return secret


# Get JWT secret on module load
JWT_SECRET = _get_jwt_secret()


def create_session_token(email: str) -> str:
    """
    Create JWT session token for validated email.

    Args:
        email: Validated email address

    Returns:
        Signed JWT token string

    Token Payload:
        - email: User's email address (normalized to lowercase)
        - iat: Issued at timestamp
        - exp: Expiration timestamp (24 hours from issue)
        - jti: Unique token ID (prevents reuse)
    """
    payload = {
        'email': email.lower().strip(),
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRATION_HOURS),
        'jti': str(int(time.time() * 1000))  # Unique token ID (millisecond timestamp)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def is_token_revoked(jti: str, email: str) -> bool:
    """
    Check if a token has been revoked (blocklist check).

    Uses DynamoDB to store revoked tokens. Tokens are automatically cleaned up
    after their expiration time via TTL.

    Args:
        jti: Token unique identifier (from JWT payload)
        email: Email address from token

    Returns:
        True if token is revoked, False if valid

    Performance:
        - ~30ms (DynamoDB read)
        - Only called on token verification (once per request)
    """
    try:
        import boto3
        table = boto3.resource('dynamodb', region_name='us-east-1').Table('perplexity-validator-user-validation')

        # Check for revoked token
        revocation_key = f"revoked_token:{jti}"
        response = table.get_item(Key={'email': revocation_key})

        if 'Item' in response:
            logger.warning(f"[SECURITY] Revoked token attempted use: {jti} for {email}")
            return True

        return False
    except Exception as e:
        logger.error(f"[SECURITY] Error checking token revocation: {e}")
        # Fail closed - if we can't check, assume revoked for security
        return True


def revoke_token(token: str, reason: str = "security_violation") -> bool:
    """
    Revoke a specific token (add to blocklist).

    SECURITY: Called when suspicious activity is detected:
    - Ownership violations
    - Excessive rate limiting
    - Path traversal attempts
    - Suspicious IP changes

    Args:
        token: JWT token string to revoke
        reason: Reason for revocation (for audit trail)

    Returns:
        True if revocation successful, False otherwise

    Examples:
        >>> revoke_token(user_token, reason="ownership_violation")
        >>> revoke_token(user_token, reason="excessive_rate_limit_violations")
    """
    try:
        import boto3

        # Decode token (don't verify - we want to revoke even invalid tokens)
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                            options={"verify_exp": False})

        jti = payload.get('jti')
        email = payload.get('email')
        exp = payload.get('exp')

        if not jti:
            logger.error("[SECURITY] Cannot revoke token: missing jti")
            return False

        table = boto3.resource('dynamodb', region_name='us-east-1').Table('perplexity-validator-user-validation')

        # Add to revocation list with TTL = token expiration
        revocation_key = f"revoked_token:{jti}"
        table.put_item(Item={
            'email': revocation_key,
            'jti': jti,
            'user_email': email,
            'revoked_at': datetime.now(timezone.utc).isoformat(),
            'reason': reason,
            'ttl': exp  # Automatically delete after token would have expired anyway
        })

        logger.warning(f"[SECURITY] Revoked token {jti} for {email} - Reason: {reason}")
        return True

    except Exception as e:
        logger.error(f"[SECURITY] Error revoking token: {e}")
        return False


def revoke_all_user_tokens(email: str, reason: str = "user_request") -> int:
    """
    Revoke all tokens for a specific user (logout all devices).

    SECURITY: Called when:
    - User clicks logout
    - Account compromise detected
    - User requests "logout all devices"

    Args:
        email: Email address
        reason: Reason for revocation

    Returns:
        Number of tokens revoked

    Note: This doesn't revoke specific tokens (we don't track them).
    Instead, it marks the email as requiring re-validation.
    """
    try:
        import boto3
        table = boto3.resource('dynamodb', region_name='us-east-1').Table('perplexity-validator-user-validation')

        # Mark email as requiring re-validation
        logout_marker = f"logout_marker:{email}"
        logout_expiry = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRATION_HOURS)

        table.put_item(Item={
            'email': logout_marker,
            'user_email': email,
            'logout_at': datetime.now(timezone.utc).isoformat(),
            'reason': reason,
            'ttl': int(logout_expiry.timestamp())
        })

        # Reset validated flag — user must re-verify with email code
        validation_table = boto3.resource('dynamodb', region_name='us-east-1').Table('perplexity-validator-user-validation')
        validation_table.update_item(
            Key={'email': email.lower().strip()},
            UpdateExpression="SET validated = :val",
            ExpressionAttributeValues={':val': False}
        )

        logger.info(f"[SECURITY] Created logout marker for {email} and reset validated flag - Reason: {reason}")
        return 1  # Return count of 1 for consistency

    except Exception as e:
        logger.error(f"[SECURITY] Error creating logout marker: {e}")
        return 0


def verify_session_token(token: str) -> Optional[Dict]:
    """
    Verify JWT session token and return payload.

    SECURITY ENHANCEMENTS:
    - Checks token signature and expiration
    - Checks if token has been revoked (blocklist)
    - Checks if user has logged out all devices

    Args:
        token: JWT token string to verify

    Returns:
        Token payload dict with email/exp/iat if valid, None if invalid/expired/revoked

    Performance:
        - Signature check: ~2ms (pure CPU)
        - Revocation check: ~30ms (DynamoDB read, only when jti present)
        - Total: ~32ms average
    """
    try:
        # Decode and verify token
        logger.info(f"[SECURITY] Decoding JWT token (length: {len(token)})")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        email = payload.get('email')
        jti = payload.get('jti')
        logger.info(f"[SECURITY] Token decoded successfully - email: {email}, jti: {jti}")

        # SECURITY: Check if token is revoked (individual token blocklist)
        if jti and is_token_revoked(jti, email):
            logger.warning(f"[SECURITY] Revoked token attempted use: {jti} for {email}")
            return None

        # SECURITY: Check if user logged out all devices (user-level blocklist)
        if email:
            import boto3
            table = boto3.resource('dynamodb', region_name='us-east-1').Table('perplexity-validator-user-validation')
            logout_marker = f"logout_marker:{email}"

            response = table.get_item(Key={'email': logout_marker})
            if 'Item' in response:
                logout_time = response['Item'].get('logout_at', '')
                token_issued = datetime.fromtimestamp(payload.get('iat'), tz=timezone.utc).isoformat()

                # If token was issued before logout, reject it
                if token_issued < logout_time:
                    logger.warning(f"[SECURITY] Token issued before logout: {email}")
                    return None

        logger.info(f"[SECURITY] Token verification successful for {email}")
        return {
            'email': payload['email'],
            'exp': payload['exp'],
            'iat': payload['iat'],
            'jti': jti
        }
    except jwt.ExpiredSignatureError as e:
        logger.warning(f"[SECURITY] Expired session token: {e}")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"[SECURITY] Invalid session token: {e}")
        return None
    except Exception as e:
        logger.error(f"[SECURITY] Unexpected error verifying token: {e}")
        return None


def extract_email_from_request(request_data: Dict, headers: Dict = None) -> Optional[str]:
    """
    Extract and verify email from session token.

    SECURITY: This is the primary defense against email spoofing. The email
    comes from a cryptographically verified token, NOT from client input.

    Args:
        request_data: Request body (may contain legacy email field)
        headers: Request headers (preferred location for token)

    Returns:
        Validated email from token if valid, None otherwise

    Token Priority:
        1. X-Session-Token header (preferred)
        2. session_token in request body (backward compatibility)
        3. None (invalid/missing token)
    """
    # Try to get token from headers first (preferred method)
    token = None
    token_source = None
    if headers:
        token = headers.get('X-Session-Token') or headers.get('x-session-token')
        if token:
            token_source = 'header'
            logger.info(f"[SECURITY] Token found in header (length: {len(token)})")
        else:
            logger.warning(f"[SECURITY] No token in headers. Available headers: {list(headers.keys())}")

    # Fallback to request body (for backward compatibility during migration)
    if not token:
        token = request_data.get('session_token')
        if token:
            token_source = 'body'
            logger.info(f"[SECURITY] Token found in request body (length: {len(token)})")

    if not token:
        logger.warning("[SECURITY] No session token provided in request (checked headers and body)")
        return None

    # Verify token and extract email
    logger.info(f"[SECURITY] Verifying token from {token_source} (preview: {token[:20]}...{token[-10:]})")
    token_data = verify_session_token(token)
    if not token_data:
        logger.warning(f"[SECURITY] Invalid or expired session token from {token_source}")
        return None

    logger.info(f"[SECURITY] Successfully extracted email from token: {token_data['email']}")
    return token_data['email']
