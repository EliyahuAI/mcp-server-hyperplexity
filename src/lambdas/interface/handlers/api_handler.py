"""
Handles HTTP requests from the external API Gateway (api.hyperplexity.ai/v1).

Authenticates via API key (Bearer token), enforces rate limits, routes RESTful
paths to existing action handlers, and wraps all responses in the standard
API envelope: {success, data, error, meta}.

Supports both REST API v1 (httpMethod/path) and HTTP API v2 (version:2.0/rawPath)
event formats, so the same Lambda can serve both gateways.
"""
import base64
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def handle(event, context):
    """Route external API Gateway events to action handlers."""

    http_method, path, headers, body, query_params = _normalize_event(event)
    logger.info(f"[API_HANDLER] {http_method} {path}")

    request_id = f"req_{uuid.uuid4().hex[:12]}"
    timestamp = datetime.now(timezone.utc).isoformat()
    meta = {"request_id": request_id, "timestamp": timestamp, "api_version": "v1"}

    # CORS preflight
    if http_method == "OPTIONS":
        return _success_response(200, {}, meta)

    # --- Authentication ---
    raw_key = _extract_bearer_token(headers)
    if not raw_key:
        return _error_response(
            401, "missing_api_key",
            "Authorization header with Bearer token is required.", meta
        )

    from interface_lambda.utils.api_key_manager import authenticate_api_key, hash_api_key
    key_info = authenticate_api_key(raw_key)
    if not key_info:
        return _error_response(
            401, "invalid_api_key",
            "API key is invalid, revoked, or expired.", meta
        )

    email = key_info["email"]

    # --- Rate Limiting ---
    try:
        key_hash = hash_api_key(raw_key)
        from interface_lambda.utils.rate_limiter_api import check_rate_limit
        allowed, remaining, reset_at = check_rate_limit(
            key_hash, key_info["rate_limit_rpm"], key_info["rate_limit_rpd"]
        )
    except Exception as e:
        logger.warning(f"[API_HANDLER] Rate limiter error (fail open): {e}")
        allowed, remaining, reset_at = True, key_info["rate_limit_rpm"], timestamp

    rate_limit_headers = {
        "X-RateLimit-Limit": str(key_info["rate_limit_rpm"]),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": reset_at,
    }

    if not allowed:
        return _error_response(
            429, "rate_limit_exceeded",
            f"Too many requests. Rate limit: {key_info['rate_limit_rpm']}/min.",
            meta,
            extra_headers={**rate_limit_headers, "Retry-After": "60"},
        )

    # --- Routing ---
    try:
        result = _route(http_method, path, headers, body, query_params, email, meta)
    except Exception as e:
        logger.error(f"[API_HANDLER] Unhandled error: {e}", exc_info=True)
        result = _error_response(500, "server_error", "An internal error occurred.", meta)

    # Attach rate-limit headers to every response
    result.setdefault("headers", {}).update(rate_limit_headers)
    return result


# ---------------------------------------------------------------------------
# Event normalisation
# ---------------------------------------------------------------------------

def _normalize_event(event):
    """Return (method, path, headers, body_dict, query_params) from any event format."""
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    if event.get("version") == "2.0":          # HTTP API v2
        http_method = (
            event.get("requestContext", {}).get("http", {}).get("method", "GET").upper()
        )
        path = event.get("rawPath", "/")
    else:                                        # REST API v1
        http_method = (event.get("httpMethod") or "GET").upper()
        path = event.get("path", "/")

    body_raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body_raw = base64.b64decode(body_raw).decode("utf-8")
    try:
        body = json.loads(body_raw) if body_raw else {}
    except (json.JSONDecodeError, TypeError):
        body = {}

    query_params = event.get("queryStringParameters") or {}
    return http_method, path, headers, body, query_params


def _extract_bearer_token(headers):
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def _route(http_method, path, headers, body, query_params, email, meta):
    # Strip /v1 prefix so matching is simpler
    clean = path[3:] if path.startswith("/v1") else path

    # POST /uploads/presigned
    if http_method == "POST" and clean == "/uploads/presigned":
        return _handle_presigned_upload(body, email, meta)

    # POST /jobs
    if http_method == "POST" and clean == "/jobs":
        return _handle_create_job(body, email, meta)

    # GET /jobs/{job_id}   (must not end in /validate or /results)
    if (
        http_method == "GET"
        and clean.startswith("/jobs/")
        and not clean.endswith(("/validate", "/results"))
    ):
        job_id = clean[6:]
        if job_id and "/" not in job_id:
            return _handle_get_job_status(job_id, email, query_params, meta)

    # POST /jobs/{job_id}/validate
    if http_method == "POST" and clean.endswith("/validate"):
        parts = clean.split("/")  # ['', 'jobs', '{job_id}', 'validate']
        if len(parts) == 4 and parts[1] == "jobs":
            return _handle_approve_validation(parts[2], body, email, meta)

    # GET /jobs/{job_id}/results
    if http_method == "GET" and clean.endswith("/results"):
        parts = clean.split("/")  # ['', 'jobs', '{job_id}', 'results']
        if len(parts) == 4 and parts[1] == "jobs":
            return _handle_get_results(parts[2], email, meta)

    # GET /account/balance
    if http_method == "GET" and clean == "/account/balance":
        return _handle_account_balance(email, meta)

    # GET /account/usage
    if http_method == "GET" and clean == "/account/usage":
        return _handle_account_usage(email, query_params, meta)

    return _error_response(
        404, "not_found",
        f"Endpoint not found: {http_method} /v1{clean}", meta
    )


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _handle_presigned_upload(body, email, meta):
    from interface_lambda.actions import presigned_upload
    request_data = {**body, "email": email, "_verified_email": email}
    resp = presigned_upload.request_presigned_url(request_data, None)
    return _wrap_handler_response(resp, meta)


def _handle_create_job(body, email, meta):
    """POST /v1/jobs — save config/s3_key to S3 then queue preview."""
    session_id = body.get("session_id")
    if not session_id:
        return _error_response(400, "missing_fields", "session_id is required.", meta)

    base_session_id = session_id
    if not base_session_id.startswith("session_"):
        base_session_id = f"session_{base_session_id}"

    try:
        preview_rows = max(1, min(int(body.get("preview_rows", 3)), 10))
    except (ValueError, TypeError):
        return _error_response(400, "invalid_input", "preview_rows must be an integer between 1 and 10.", meta)

    # Persist the uploaded file's s3_key into session_info if provided
    s3_key = body.get("s3_key")
    if s3_key:
        try:
            from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
            mgr = UnifiedS3Manager()
            sess_info = mgr.load_session_info(email, base_session_id)
            if not sess_info.get("table_path"):
                sess_info["table_path"] = s3_key
                mgr.save_session_info(email, base_session_id, sess_info)
                logger.info(f"[API_HANDLER] Saved table_path={s3_key} for {base_session_id}")
        except Exception as e:
            logger.warning(f"[API_HANDLER] Could not save s3_key to session_info: {e}")

    # Persist the inline config to S3 if provided
    config = body.get("config")
    if config:
        try:
            from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
            mgr = UnifiedS3Manager()
            config_key = f"{mgr.get_session_path(email, base_session_id)}config.json"
            mgr.s3_client.put_object(
                Bucket=mgr.bucket_name,
                Key=config_key,
                Body=json.dumps(config, indent=2).encode("utf-8"),
                ContentType="application/json",
            )
            logger.info(f"[API_HANDLER] Saved config to S3: {config_key}")
        except Exception as e:
            logger.warning(f"[API_HANDLER] Could not save config to S3: {e}")

    request_data = {
        "_verified_email": email,
        "_api_email": email,
        "session_id": base_session_id,
        "preview_max_rows": preview_rows,
    }

    from interface_lambda.actions import start_preview
    resp = start_preview.handle_start_preview(request_data, None)
    parsed = _parse_handler_response(resp)

    if parsed["status_code"] >= 400:
        b = parsed["body"]
        return _error_response(
            parsed["status_code"],
            b.get("error", "request_failed"),
            b.get("message") or b.get("error", "Failed to create job"),
            meta,
        )

    job_id = parsed["body"].get("session_id", base_session_id)
    return _success_response(202, {
        "job_id": job_id,
        "status": "queued",
        "run_type": "preview",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "urls": {
            "status": f"/v1/jobs/{job_id}",
            "results": f"/v1/jobs/{job_id}/results",
        },
        "polling": {
            "recommended_interval_seconds": 10,
            "max_wait_seconds": 1800,
        },
    }, meta)


def _handle_get_job_status(job_id, email, query_params, meta):
    """GET /v1/jobs/{job_id}"""
    request_data = {
        "session_id": job_id,
        "preview_mode": False,
        "email": email,
        "_api_email": email,
    }
    from interface_lambda.actions import status_check
    resp = status_check.handle_post_status(request_data, None)
    parsed = _parse_handler_response(resp)
    body_data = parsed["body"]

    _STATUS_MAP = {
        "COMPLETED": "completed",
        "PROCESSING": "processing",
        "QUEUED": "queued",
        "FAILED": "failed",
        "ERROR": "failed",
        "PREVIEW_COMPLETE": "preview_complete",
    }
    internal = (body_data.get("status") or "PROCESSING").upper()
    api_status = _STATUS_MAP.get(internal, internal.lower())

    data = {
        "job_id": job_id,
        "status": api_status,
        "progress_percent": body_data.get("progress_percent", 0),
        "current_step": body_data.get("message") or body_data.get("current_step"),
        "submitted_at": body_data.get("created_at") or body_data.get("submitted_at"),
    }

    extra = {"Retry-After": "10"} if api_status == "processing" else None
    return _success_response(200, data, meta, extra_headers=extra)


def _handle_approve_validation(job_id, body, email, meta):
    """POST /v1/jobs/{job_id}/validate"""
    request_data = {
        "_api_email": email,
        "_verified_email": email,
        "job_id": job_id,
        "approved_cost_usd": body.get("approved_cost_usd"),
        "webhook_url": body.get("webhook_url"),
        "webhook_secret": body.get("webhook_secret"),
    }
    from interface_lambda.actions import start_preview
    resp = start_preview.handle_approve_validation(request_data, None)
    return _wrap_handler_response(resp, meta, success_status=202)


def _handle_get_results(job_id, email, meta):
    """GET /v1/jobs/{job_id}/results"""
    request_data = {
        "_api_email": email,
        "_verified_email": email,
        "job_id": job_id,
    }
    from interface_lambda.actions import status_check
    resp = status_check.handle_get_results(request_data, None)
    return _wrap_handler_response(resp, meta)


def _handle_account_balance(email, meta):
    """GET /v1/account/balance"""
    request_data = {"email": email, "_verified_email": email}
    from interface_lambda.actions import account_balance
    resp = account_balance.handle(request_data, None)
    return _wrap_handler_response(resp, meta)


def _handle_account_usage(email, query_params, meta):
    """GET /v1/account/usage"""
    try:
        limit = int(query_params.get("limit", 100))
        offset = int(query_params.get("offset", 0))
    except (ValueError, TypeError):
        return _error_response(400, "invalid_input", "limit and offset must be integers.", meta)

    request_data = {
        "email": email,
        "_verified_email": email,
        "start_date": query_params.get("start_date"),
        "end_date": query_params.get("end_date"),
        "limit": limit,
        "offset": offset,
    }
    from interface_lambda.actions import user_stats
    resp = user_stats.handle(request_data, None)
    return _wrap_handler_response(resp, meta)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _parse_handler_response(resp):
    """Unpack a create_response() dict into {status_code, body}."""
    status_code = resp.get("statusCode", 200)
    body_raw = resp.get("body", "{}")
    try:
        body = json.loads(body_raw) if isinstance(body_raw, str) else body_raw
    except (json.JSONDecodeError, TypeError):
        body = {}
    return {"status_code": status_code, "body": body}


def _wrap_handler_response(resp, meta, success_status=200):
    """
    Wrap an existing create_response() result into the API envelope.
    Uses the inner handler's HTTP status code on error, or success_status on success.
    """
    parsed = _parse_handler_response(resp)
    status_code = parsed["status_code"]
    body_data = parsed["body"]

    if body_data.get("success") is False or status_code >= 400:
        error_code = body_data.get("error", "request_failed")
        error_msg = (
            body_data.get("message")
            or body_data.get("details")
            or body_data.get("error")
            or "Request failed"
        )
        details = body_data.get("details") if isinstance(body_data.get("details"), dict) else None
        return _error_response(status_code, error_code, error_msg, meta, details=details)

    return _success_response(success_status, body_data, meta)


def _success_response(status_code, data, meta, extra_headers=None):
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
    }
    if extra_headers:
        headers.update(extra_headers)
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps({"success": True, "data": data, "error": None, "meta": meta}),
    }


def _error_response(status_code, code, message, meta, details=None, extra_headers=None):
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
    }
    if extra_headers:
        headers.update(extra_headers)
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps({"success": False, "data": None, "error": error, "meta": meta}),
    }
