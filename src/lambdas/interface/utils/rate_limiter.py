"""
Simple rate limiter using DynamoDB.

Prevents abuse and brute force attacks by limiting the number of requests
from a specific identifier (email, IP, etc.) within a time window.

Uses DynamoDB atomic counters with TTL for automatic cleanup.
"""
import boto3
import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple

logger = logging.getLogger(__name__)
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')


def check_rate_limit(
    identifier: str,
    action: str,
    max_requests: int = 10,
    window_minutes: int = 1
) -> Tuple[bool, int]:
    """
    Check if identifier has exceeded rate limit for action.

    Uses DynamoDB atomic increment to safely track requests across
    multiple Lambda instances.

    Args:
        identifier: Unique identifier (email, IP, session_id, etc.)
        action: Action being rate-limited (e.g., 'getViewerData', 'validateCode')
        max_requests: Maximum requests allowed in window (default: 10)
        window_minutes: Time window in minutes (default: 1)

    Returns:
        Tuple of (is_allowed: bool, remaining_requests: int)
        - is_allowed: True if request should be allowed, False if rate limit exceeded
        - remaining_requests: Number of requests remaining in current window

    Performance:
        - Single DynamoDB write (atomic increment)
        - ~5-10ms latency
        - Automatic cleanup via TTL

    Cost:
        - $0.25 per million writes
        - Expected: <$0.01/month for typical usage

    Examples:
        >>> is_allowed, remaining = check_rate_limit('user@example.com', 'getViewerData', max_requests=10)
        >>> if not is_allowed:
        >>>     return error_response(429, 'Too many requests')
    """
    try:
        # Use email validation table with TTL for automatic cleanup
        # (This table already has TTL configured, so we reuse it for rate limiting)
        table = dynamodb.Table('perplexity-validator-user-validation')

        now = datetime.now(timezone.utc)
        rate_limit_key = f"rate_limit:{action}:{identifier}"
        ttl = int((now + timedelta(minutes=window_minutes)).timestamp())

        # Atomic increment with conditional expression
        response = table.update_item(
            Key={'email': rate_limit_key},
            UpdateExpression='ADD request_count :inc SET #ttl = :ttl, updated_at = :now',
            ExpressionAttributeNames={
                '#ttl': 'ttl'
            },
            ExpressionAttributeValues={
                ':inc': 1,
                ':ttl': ttl,
                ':now': now.isoformat()
            },
            ReturnValues='ALL_NEW'
        )

        count = int(response['Attributes'].get('request_count', 0))
        remaining = max(0, max_requests - count)
        is_allowed = count <= max_requests

        if not is_allowed:
            logger.warning(f"[RATE_LIMIT] Exceeded for {action}:{identifier} - {count}/{max_requests}")
        else:
            logger.debug(f"[RATE_LIMIT] {action}:{identifier} - {count}/{max_requests} (remaining: {remaining})")

        return is_allowed, remaining

    except Exception as e:
        # Fail open on errors (allow request to proceed)
        logger.error(f"[RATE_LIMIT] Error checking rate limit: {e}")
        return True, max_requests


def check_ip_rate_limit(
    ip_address: str,
    action: str,
    max_requests: int = 10,
    window_minutes: int = 60
) -> Tuple[bool, int]:
    """
    Check IP-based rate limit (useful for preventing distributed attacks).

    Similar to check_rate_limit but with longer default window (60 minutes)
    since IP addresses are less specific than user identifiers.

    Args:
        ip_address: IP address to rate limit
        action: Action being rate-limited
        max_requests: Maximum requests allowed in window (default: 10)
        window_minutes: Time window in minutes (default: 60)

    Returns:
        Tuple of (is_allowed: bool, remaining_requests: int)

    Example:
        >>> ip = context.get('identity', {}).get('sourceIp')
        >>> is_allowed, remaining = check_ip_rate_limit(ip, 'validateCode', max_requests=10)
    """
    return check_rate_limit(
        identifier=f"ip:{ip_address}",
        action=action,
        max_requests=max_requests,
        window_minutes=window_minutes
    )


def get_rate_limit_info(identifier: str, action: str) -> dict:
    """
    Get current rate limit status for identifier without incrementing count.

    Useful for debugging or displaying rate limit info to users.

    Args:
        identifier: Unique identifier (email, IP, etc.)
        action: Action being rate-limited

    Returns:
        Dict with keys:
        - count: Current request count
        - ttl: TTL timestamp
        - expires_at: ISO format expiration time
    """
    try:
        table = dynamodb.Table('perplexity-validator-user-validation')
        rate_limit_key = f"rate_limit:{action}:{identifier}"

        response = table.get_item(Key={'email': rate_limit_key})

        if 'Item' not in response:
            return {
                'count': 0,
                'ttl': None,
                'expires_at': None
            }

        item = response['Item']
        count = int(item.get('request_count', 0))
        ttl = item.get('ttl')
        expires_at = datetime.fromtimestamp(ttl, tz=timezone.utc).isoformat() if ttl else None

        return {
            'count': count,
            'ttl': ttl,
            'expires_at': expires_at
        }

    except Exception as e:
        logger.error(f"[RATE_LIMIT] Error getting rate limit info: {e}")
        return {
            'count': 0,
            'ttl': None,
            'expires_at': None
        }
