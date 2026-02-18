"""
API Key Manager - Handles generation, hashing, storage, and authentication of API keys.

Key format: hpx_{tier}_{40_random_chars}
Example:    hpx_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8
Storage:    Only HMAC-SHA256 hash stored in DynamoDB (raw key never stored)
"""
import hmac
import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# DynamoDB table names
API_KEYS_TABLE = "perplexity-validator-api-keys"
API_KEY_USAGE_TABLE = "perplexity-validator-api-key-usage"

# Key format constants
KEY_PREFIX_MAP = {
    "live": "hpx_live_",
    "test": "hpx_test_",
    "int":  "hpx_int_",
}
KEY_RANDOM_LENGTH = 40  # chars from token_urlsafe(30) = 40 url-safe base64 chars

# How many characters of the key to store as the display prefix (e.g. "hpx_live_a1b2c3d4")
DISPLAY_PREFIX_LENGTH = 18

# Cached HMAC secret (loaded once per Lambda container)
_hmac_secret: Optional[str] = None


def load_hmac_secret() -> str:
    """Load the HMAC secret from SSM (cached after first load)."""
    global _hmac_secret
    if _hmac_secret:
        return _hmac_secret

    # Try env var first (local dev / override)
    env_val = os.environ.get("API_KEY_HMAC_SECRET")
    if env_val:
        _hmac_secret = env_val
        return _hmac_secret

    # Load from SSM
    param_name = os.environ.get(
        "API_KEY_HMAC_SECRET_PARAM",
        "/perplexity-validator/api-key-hmac-secret"
    )
    try:
        ssm = boto3.client("ssm")
        response = ssm.get_parameter(Name=param_name, WithDecryption=True)
        _hmac_secret = response["Parameter"]["Value"]
        return _hmac_secret
    except ClientError as e:
        logger.error(f"Failed to load API key HMAC secret from SSM ({param_name}): {e}")
        raise RuntimeError("API key HMAC secret unavailable") from e


def generate_api_key(tier: str = "live") -> str:
    """
    Generate a new raw API key.

    Args:
        tier: 'live', 'test', or 'int'

    Returns:
        Raw key string (e.g. 'hpx_live_a1b2c3d4...'). Never stored — caller must hash it.
    """
    if tier not in KEY_PREFIX_MAP:
        raise ValueError(f"Invalid tier '{tier}'. Must be one of: {list(KEY_PREFIX_MAP.keys())}")
    prefix = KEY_PREFIX_MAP[tier]
    random_part = secrets.token_urlsafe(30)  # 30 bytes → 40 url-safe chars
    return f"{prefix}{random_part}"


def hash_api_key(raw_key: str) -> str:
    """
    HMAC-SHA256 hash of a raw API key. Used as the DynamoDB primary key.

    Args:
        raw_key: The full raw API key string.

    Returns:
        Hex-encoded HMAC-SHA256 digest.
    """
    secret = load_hmac_secret()
    return hmac.new(
        secret.encode("utf-8"),
        raw_key.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def get_key_prefix(raw_key: str) -> str:
    """
    Extract the display prefix from a raw key (safe to store and show to users).

    Example: 'hpx_live_a1b2c3d4e5f6...' -> 'hpx_live_a1b2c3d4'
    """
    return raw_key[:DISPLAY_PREFIX_LENGTH]


def _get_dynamodb():
    """Return a DynamoDB resource (boto3 resource for table operations)."""
    return boto3.resource("dynamodb")


def create_api_key_record(
    email: str,
    key_name: str,
    tier: str = "live",
    scopes: Optional[list] = None,
    ip_whitelist: Optional[list] = None,
    expires_at: Optional[str] = None,
) -> dict:
    """
    Generate a new API key and store the hashed record in DynamoDB.

    Args:
        email: Owner's email address.
        key_name: Human-readable label for the key.
        tier: 'live', 'test', or 'int'.
        scopes: List of permission scopes (default: ['validate', 'account:read']).
        ip_whitelist: Optional list of allowed IP addresses.
        expires_at: Optional ISO 8601 expiration datetime string.

    Returns:
        dict with 'raw_key' (shown once only), 'key_prefix', and 'created_at'.
    """
    if scopes is None:
        scopes = ["validate", "account:read"]

    raw_key = generate_api_key(tier)
    key_hash = hash_api_key(raw_key)
    key_prefix = get_key_prefix(raw_key)
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "api_key_hash": key_hash,
        "key_prefix": key_prefix,
        "email": email,
        "key_name": key_name,
        "tier": tier,
        "scopes": scopes,
        "rate_limit_rpm": 300 if tier == "int" else 60,
        "rate_limit_rpd": 0 if tier == "int" else 1000,  # 0 = unlimited
        "created_at": now,
        "last_used_at": None,
        "expires_at": expires_at,
        "is_active": True,
        "revoked_at": None,
        "revoked_reason": None,
        "ip_whitelist": ip_whitelist or [],
        "cors_origins": ["*"],
        "metadata": {
            "created_via": "web_ui",
        },
    }

    ddb = _get_dynamodb()
    table = ddb.Table(API_KEYS_TABLE)
    table.put_item(Item=item)

    logger.info(f"API key created: prefix={key_prefix} email={email} tier={tier}")

    return {
        "raw_key": raw_key,       # Return ONCE - never persisted
        "key_prefix": key_prefix,
        "key_name": key_name,
        "tier": tier,
        "scopes": scopes,
        "created_at": now,
    }


def authenticate_api_key(raw_key: str) -> Optional[dict]:
    """
    Authenticate a raw API key.

    Args:
        raw_key: The raw key value from the Authorization header.

    Returns:
        dict with {email, scopes, tier, key_prefix, rate_limit_rpm, rate_limit_rpd}
        or None if the key is invalid/revoked/expired.
    """
    if not raw_key or not raw_key.startswith("hpx_"):
        return None

    try:
        key_hash = hash_api_key(raw_key)
    except RuntimeError:
        return None

    ddb = _get_dynamodb()
    table = ddb.Table(API_KEYS_TABLE)

    try:
        response = table.get_item(Key={"api_key_hash": key_hash})
    except ClientError as e:
        logger.error(f"DynamoDB error during API key auth: {e}")
        return None

    item = response.get("Item")
    if not item:
        logger.warning(f"API key not found: prefix={raw_key[:DISPLAY_PREFIX_LENGTH]}")
        return None

    if not item.get("is_active", False):
        logger.warning(f"API key is revoked: prefix={item.get('key_prefix')}")
        return None

    # Check expiry
    expires_at = item.get("expires_at")
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            if datetime.now(timezone.utc) > exp_dt:
                logger.warning(f"API key expired: prefix={item.get('key_prefix')}")
                return None
        except ValueError:
            pass

    # Update last_used_at asynchronously (best-effort, don't block auth)
    try:
        table.update_item(
            Key={"api_key_hash": key_hash},
            UpdateExpression="SET last_used_at = :ts",
            ExpressionAttributeValues={":ts": datetime.now(timezone.utc).isoformat()},
        )
    except ClientError:
        pass  # Non-blocking

    return {
        "email": item["email"],
        "scopes": item.get("scopes", []),
        "tier": item.get("tier", "live"),
        "key_prefix": item.get("key_prefix"),
        "rate_limit_rpm": item.get("rate_limit_rpm", 60),
        "rate_limit_rpd": item.get("rate_limit_rpd", 1000),
        "ip_whitelist": item.get("ip_whitelist", []),
    }


def list_api_keys(email: str) -> list:
    """
    List all API keys for a user (no raw keys returned).

    Args:
        email: The user's email address.

    Returns:
        List of key records (prefix, name, tier, scopes, status, dates).
    """
    ddb = _get_dynamodb()
    table = ddb.Table(API_KEYS_TABLE)

    try:
        response = table.query(
            IndexName="email-index",
            KeyConditionExpression=Key("email").eq(email),
        )
    except ClientError as e:
        logger.error(f"Failed to list API keys for {email}: {e}")
        return []

    keys = []
    for item in response.get("Items", []):
        keys.append({
            "key_prefix": item.get("key_prefix"),
            "key_name": item.get("key_name"),
            "tier": item.get("tier"),
            "scopes": item.get("scopes", []),
            "is_active": item.get("is_active", False),
            "created_at": item.get("created_at"),
            "last_used_at": item.get("last_used_at"),
            "expires_at": item.get("expires_at"),
            "revoked_at": item.get("revoked_at"),
            "revoked_reason": item.get("revoked_reason"),
            "ip_whitelist": item.get("ip_whitelist", []),
        })

    # Sort by created_at descending
    keys.sort(key=lambda k: k.get("created_at") or "", reverse=True)
    return keys


def revoke_api_key(email: str, key_prefix: str, reason: str = "") -> bool:
    """
    Revoke an API key by prefix. Only the owning email can revoke.

    Args:
        email: Owner email (for ownership verification).
        key_prefix: The display prefix of the key to revoke.
        reason: Optional reason string.

    Returns:
        True if revoked, False if key not found or not owned by email.
    """
    ddb = _get_dynamodb()
    table = ddb.Table(API_KEYS_TABLE)

    # Find the key by email + prefix via GSI
    try:
        response = table.query(
            IndexName="email-index",
            KeyConditionExpression=Key("email").eq(email),
            FilterExpression=Attr("key_prefix").eq(key_prefix),
        )
    except ClientError as e:
        logger.error(f"Failed to find key for revocation: {e}")
        return False

    items = response.get("Items", [])
    if not items:
        logger.warning(f"Key not found for revocation: email={email} prefix={key_prefix}")
        return False

    key_hash = items[0]["api_key_hash"]
    now = datetime.now(timezone.utc).isoformat()

    try:
        table.update_item(
            Key={"api_key_hash": key_hash},
            UpdateExpression="SET is_active = :false, revoked_at = :ts, revoked_reason = :reason",
            ExpressionAttributeValues={
                ":false": False,
                ":ts": now,
                ":reason": reason or "User requested revocation",
            },
        )
    except ClientError as e:
        logger.error(f"Failed to revoke key {key_prefix}: {e}")
        return False

    logger.info(f"API key revoked: prefix={key_prefix} email={email}")
    return True


def update_api_key(email: str, key_prefix: str, updates: dict) -> Optional[dict]:
    """
    Update mutable fields of an API key (name, scopes, ip_whitelist, expires_at).

    Args:
        email: Owner email.
        key_prefix: Display prefix of the key to update.
        updates: Dict of fields to update (allowed: key_name, scopes, ip_whitelist, expires_at).

    Returns:
        Updated key record (without raw key) or None if not found.
    """
    allowed_fields = {"key_name", "scopes", "ip_whitelist", "expires_at"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return None

    ddb = _get_dynamodb()
    table = ddb.Table(API_KEYS_TABLE)

    # Find by email + prefix
    try:
        response = table.query(
            IndexName="email-index",
            KeyConditionExpression=Key("email").eq(email),
            FilterExpression=Attr("key_prefix").eq(key_prefix),
        )
    except ClientError as e:
        logger.error(f"Failed to find key for update: {e}")
        return None

    items = response.get("Items", [])
    if not items:
        return None

    key_hash = items[0]["api_key_hash"]

    # Build update expression
    set_parts = []
    expr_values = {}
    for field, value in filtered.items():
        set_parts.append(f"{field} = :{field}")
        expr_values[f":{field}"] = value

    try:
        table.update_item(
            Key={"api_key_hash": key_hash},
            UpdateExpression="SET " + ", ".join(set_parts),
            ExpressionAttributeValues=expr_values,
        )
    except ClientError as e:
        logger.error(f"Failed to update key {key_prefix}: {e}")
        return None

    # Return updated record
    keys = list_api_keys(email)
    return next((k for k in keys if k["key_prefix"] == key_prefix), None)


def get_api_key_usage(email: str, key_prefix: str) -> dict:
    """
    Get usage statistics for a specific API key.

    Args:
        email: Owner email (for access verification).
        key_prefix: Display prefix of the key.

    Returns:
        Usage statistics dict.
    """
    # Verify ownership first
    keys = list_api_keys(email)
    target_key = next((k for k in keys if k["key_prefix"] == key_prefix), None)
    if not target_key:
        return {}

    # Find the hash for this prefix by querying the main table
    ddb = _get_dynamodb()
    main_table = ddb.Table(API_KEYS_TABLE)
    try:
        response = main_table.query(
            IndexName="email-index",
            KeyConditionExpression=Key("email").eq(email),
            FilterExpression=Attr("key_prefix").eq(key_prefix),
        )
    except ClientError:
        return target_key

    items = response.get("Items", [])
    if not items:
        return target_key

    key_hash = items[0]["api_key_hash"]

    # Query usage table
    usage_table = ddb.Table(API_KEY_USAGE_TABLE)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current_minute = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")

    usage_stats = {
        "requests_this_minute": 0,
        "requests_today": 0,
        "requests_this_month": 0,
    }

    try:
        # Today's usage
        resp = usage_table.get_item(Key={"api_key_hash": key_hash, "window": f"day:{today}"})
        if resp.get("Item"):
            usage_stats["requests_today"] = resp["Item"].get("request_count", 0)

        # This minute
        resp = usage_table.get_item(Key={"api_key_hash": key_hash, "window": f"minute:{current_minute}"})
        if resp.get("Item"):
            usage_stats["requests_this_minute"] = resp["Item"].get("request_count", 0)

    except ClientError as e:
        logger.warning(f"Failed to get usage stats: {e}")

    return {**target_key, "usage": usage_stats}
