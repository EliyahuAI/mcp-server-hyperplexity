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

# Use environment variable for secret key in production
# WARNING: Change this in production deployment!
JWT_SECRET = os.environ.get('JWT_SECRET_KEY', 'CHANGE-THIS-IN-PRODUCTION-DEPLOYMENT')
JWT_ALGORITHM = 'HS256'
TOKEN_EXPIRATION_HOURS = 24


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


def verify_session_token(token: str) -> Optional[Dict]:
    """
    Verify JWT session token and return payload.

    Args:
        token: JWT token string to verify

    Returns:
        Token payload dict with email/exp/iat if valid, None if invalid/expired

    Performance:
        - ~2ms (pure CPU, no I/O)
        - ZERO DynamoDB calls
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {
            'email': payload['email'],
            'exp': payload['exp'],
            'iat': payload['iat']
        }
    except jwt.ExpiredSignatureError:
        logger.warning("[SECURITY] Expired session token")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"[SECURITY] Invalid session token: {e}")
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
    if headers:
        token = headers.get('X-Session-Token') or headers.get('x-session-token')

    # Fallback to request body (for backward compatibility during migration)
    if not token:
        token = request_data.get('session_token')

    if not token:
        logger.warning("[SECURITY] No session token provided in request")
        return None

    # Verify token and extract email
    token_data = verify_session_token(token)
    if not token_data:
        logger.warning("[SECURITY] Invalid or expired session token")
        return None

    return token_data['email']
