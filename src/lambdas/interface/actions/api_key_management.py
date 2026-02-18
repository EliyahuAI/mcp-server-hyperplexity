"""
API Key Management Actions

Handles CRUD operations for API keys via the web UI (JWT-authenticated).
These actions are called by http_handler.py with _verified_email injected.

Supported actions:
  - createApiKey
  - listApiKeys
  - revokeApiKey
  - updateApiKey
  - getApiKeyUsage
"""
import logging

from interface_lambda.utils.helpers import create_response
from interface_lambda.utils import api_key_manager

logger = logging.getLogger(__name__)

# Maximum keys per user
MAX_KEYS_PER_USER = 10


def handle(request_data: dict, context) -> dict:
    """Main dispatcher — routes to sub-handler based on action field."""
    action = request_data.get("action", "")
    email = request_data.get("_verified_email", "")

    if not email:
        return create_response(401, {"success": False, "error": "Authentication required"})

    try:
        if action == "createApiKey":
            return _create_api_key(email, request_data)
        elif action == "listApiKeys":
            return _list_api_keys(email)
        elif action == "revokeApiKey":
            return _revoke_api_key(email, request_data)
        elif action == "updateApiKey":
            return _update_api_key(email, request_data)
        elif action == "getApiKeyUsage":
            return _get_api_key_usage(email, request_data)
        else:
            return create_response(400, {"success": False, "error": f"Unknown API key action: {action}"})
    except Exception as e:
        logger.error(f"API key management error (action={action}, email={email}): {e}", exc_info=True)
        return create_response(500, {"success": False, "error": "Internal server error"})


def _create_api_key(email: str, request_data: dict) -> dict:
    """Create a new API key for the user."""
    key_name = request_data.get("key_name", "").strip()
    if not key_name:
        return create_response(400, {"success": False, "error": "key_name is required"})
    if len(key_name) > 100:
        return create_response(400, {"success": False, "error": "key_name must be 100 characters or fewer"})

    tier = request_data.get("tier", "live")
    if tier not in ("live", "test"):
        return create_response(400, {"success": False, "error": "tier must be 'live' or 'test'"})

    # Validate scopes
    allowed_scopes = {"validate", "account:read", "config:read"}
    requested_scopes = request_data.get("scopes", ["validate", "account:read"])
    if not isinstance(requested_scopes, list):
        return create_response(400, {"success": False, "error": "scopes must be a list"})
    invalid_scopes = set(requested_scopes) - allowed_scopes
    if invalid_scopes:
        return create_response(400, {"success": False, "error": f"Invalid scopes: {invalid_scopes}"})

    # Enforce per-user key limit
    existing_keys = api_key_manager.list_api_keys(email)
    active_keys = [k for k in existing_keys if k.get("is_active")]
    if len(active_keys) >= MAX_KEYS_PER_USER:
        return create_response(400, {
            "success": False,
            "error": f"Maximum of {MAX_KEYS_PER_USER} active API keys allowed. Please revoke unused keys."
        })

    ip_whitelist = request_data.get("ip_whitelist", [])
    if not isinstance(ip_whitelist, list):
        ip_whitelist = []

    expires_at = request_data.get("expires_at")  # Optional ISO 8601 string

    result = api_key_manager.create_api_key_record(
        email=email,
        key_name=key_name,
        tier=tier,
        scopes=requested_scopes,
        ip_whitelist=ip_whitelist,
        expires_at=expires_at,
    )

    return create_response(201, {
        "success": True,
        "message": "API key created. Store the raw key now — it will not be shown again.",
        "api_key": result["raw_key"],      # Shown ONCE
        "key_prefix": result["key_prefix"],
        "key_name": result["key_name"],
        "tier": result["tier"],
        "scopes": result["scopes"],
        "created_at": result["created_at"],
    })


def _list_api_keys(email: str) -> dict:
    """List all API keys for the user (no raw keys)."""
    keys = api_key_manager.list_api_keys(email)
    return create_response(200, {
        "success": True,
        "api_keys": keys,
        "total": len(keys),
        "active_count": sum(1 for k in keys if k.get("is_active")),
    })


def _revoke_api_key(email: str, request_data: dict) -> dict:
    """Revoke an API key by prefix."""
    key_prefix = request_data.get("key_prefix", "").strip()
    if not key_prefix:
        return create_response(400, {"success": False, "error": "key_prefix is required"})

    reason = request_data.get("reason", "User requested revocation").strip()

    revoked = api_key_manager.revoke_api_key(email, key_prefix, reason)
    if not revoked:
        return create_response(404, {
            "success": False,
            "error": "API key not found or does not belong to your account"
        })

    return create_response(200, {
        "success": True,
        "message": f"API key {key_prefix} has been revoked.",
        "key_prefix": key_prefix,
    })


def _update_api_key(email: str, request_data: dict) -> dict:
    """Update mutable fields of an API key."""
    key_prefix = request_data.get("key_prefix", "").strip()
    if not key_prefix:
        return create_response(400, {"success": False, "error": "key_prefix is required"})

    # Verify the key exists, is owned by this user, and is still active
    existing_keys = api_key_manager.list_api_keys(email)
    target = next((k for k in existing_keys if k["key_prefix"] == key_prefix), None)
    if not target:
        return create_response(404, {"success": False, "error": "API key not found or does not belong to your account"})
    if not target.get("is_active"):
        return create_response(400, {"success": False, "error": "Cannot modify a revoked API key"})

    updates = {}
    if "key_name" in request_data:
        name = request_data["key_name"].strip()
        if not name or len(name) > 100:
            return create_response(400, {"success": False, "error": "key_name must be 1-100 characters"})
        updates["key_name"] = name
    if "scopes" in request_data:
        allowed_scopes = {"validate", "account:read", "config:read"}
        requested_scopes = request_data["scopes"]
        if not isinstance(requested_scopes, list):
            return create_response(400, {"success": False, "error": "scopes must be a list"})
        invalid_scopes = set(requested_scopes) - allowed_scopes
        if invalid_scopes:
            return create_response(400, {"success": False, "error": f"Invalid scopes: {sorted(invalid_scopes)}"})
        updates["scopes"] = requested_scopes
    if "ip_whitelist" in request_data:
        updates["ip_whitelist"] = request_data["ip_whitelist"]
    if "expires_at" in request_data:
        updates["expires_at"] = request_data["expires_at"]

    if not updates:
        return create_response(400, {"success": False, "error": "No updatable fields provided"})

    updated = api_key_manager.update_api_key(email, key_prefix, updates)
    if updated is None:
        return create_response(404, {
            "success": False,
            "error": "API key not found or does not belong to your account"
        })

    return create_response(200, {"success": True, "api_key": updated})


def _get_api_key_usage(email: str, request_data: dict) -> dict:
    """Get usage statistics for a specific API key."""
    key_prefix = request_data.get("key_prefix", "").strip()
    if not key_prefix:
        return create_response(400, {"success": False, "error": "key_prefix is required"})

    usage = api_key_manager.get_api_key_usage(email, key_prefix)
    if not usage:
        return create_response(404, {
            "success": False,
            "error": "API key not found or does not belong to your account"
        })

    return create_response(200, {"success": True, "api_key": usage})
