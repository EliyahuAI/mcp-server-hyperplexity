"""
Per-key sliding window rate limiter for the external API.

Uses DynamoDB atomic ADD operations on the perplexity-validator-api-key-usage table.
Tracks two windows: per-minute (RPM) and per-day (RPD).
Returns (allowed, remaining, reset_at) so the caller can set X-RateLimit-* headers.

Rate limit of 0 for RPD means unlimited (used for internal 'int' tier keys).
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

API_KEY_USAGE_TABLE = "perplexity-validator-api-key-usage"

# Module-level cache: reuse the same resource across warm Lambda invocations
_dynamodb_resource = None


def _get_table():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb")
    return _dynamodb_resource.Table(API_KEY_USAGE_TABLE)


def check_rate_limit(api_key_hash: str, rpm: int, rpd: int) -> Tuple[bool, int, str]:
    """
    Atomically increment request counters and check if the key is within limits.

    Args:
        api_key_hash: HMAC hash of the raw API key (DynamoDB PK).
        rpm:          Requests-per-minute limit.
        rpd:          Requests-per-day limit. 0 means unlimited.

    Returns:
        (allowed, remaining_rpm, reset_at)
        - allowed:       True if the request is within rate limits.
        - remaining_rpm: How many more requests are allowed in the current minute.
        - reset_at:      ISO-8601 timestamp when the current minute window resets.
    """
    now = datetime.now(timezone.utc)
    minute_window = now.strftime("%Y-%m-%dT%H:%M")
    day_window = now.strftime("%Y-%m-%d")

    # Window reset times
    next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    reset_at = next_minute.isoformat()

    # TTL values: minute window expires in 2 min, day window in 2 days
    minute_ttl = int((now + timedelta(minutes=2)).timestamp())
    day_ttl = int((now + timedelta(days=2)).timestamp())

    table = _get_table()

    minute_count = _increment_window(table, api_key_hash, f"minute:{minute_window}", minute_ttl)
    day_count = _increment_window(table, api_key_hash, f"day:{day_window}", day_ttl)

    # Check per-minute limit
    if minute_count > rpm:
        remaining = max(0, rpm - minute_count + 1)
        logger.warning(
            f"Rate limit (RPM) exceeded: hash={api_key_hash[:8]}... "
            f"count={minute_count} limit={rpm}"
        )
        return False, remaining, reset_at

    # Check per-day limit (0 = unlimited)
    if rpd > 0 and day_count > rpd:
        logger.warning(
            f"Rate limit (RPD) exceeded: hash={api_key_hash[:8]}... "
            f"count={day_count} limit={rpd}"
        )
        # Day resets at midnight UTC
        next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return False, 0, next_day.isoformat()

    remaining_rpm = max(0, rpm - minute_count)
    return True, remaining_rpm, reset_at


def _increment_window(table, api_key_hash: str, window: str, ttl: int) -> int:
    """
    Atomically increment the request_count for a given window.

    Returns the new request_count after incrementing.
    """
    try:
        response = table.update_item(
            Key={"api_key_hash": api_key_hash, "window": window},
            UpdateExpression="ADD request_count :one SET #ttl = if_not_exists(#ttl, :ttl)",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={":one": 1, ":ttl": ttl},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"].get("request_count", 1))
    except ClientError as e:
        logger.error(f"DynamoDB error incrementing rate limit window {window}: {e}")
        # Fail open: don't block the request if DynamoDB is unavailable
        return 0
