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


def _json_default(obj):
    """Fallback JSON encoder — handles DynamoDB Decimal and datetime objects."""
    import decimal
    from datetime import datetime
    if isinstance(obj, decimal.Decimal):
        # Preserve integers as int, everything else as float
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def handle(event, context):
    """Route external API Gateway events to action handlers."""

    http_method, path, headers, body, query_params = _normalize_event(event)

    request_id = f"req_{uuid.uuid4().hex[:12]}"
    timestamp = datetime.now(timezone.utc).isoformat()
    meta = {"request_id": request_id, "timestamp": timestamp, "api_version": "v1"}

    _start_time = datetime.now(timezone.utc)

    # CORS preflight
    if http_method == "OPTIONS":
        return _success_response(200, {}, meta)

    # --- Authentication ---
    raw_key = _extract_bearer_token(headers)
    if not raw_key:
        logger.warning(json.dumps({
            "event": "api_auth_failed",
            "reason": "missing_key",
            "request_id": request_id,
        }))
        return _error_response(
            401, "missing_api_key",
            "Authorization header with Bearer token is required.", meta
        )

    from interface_lambda.utils.api_key_manager import authenticate_api_key, hash_api_key
    key_info = authenticate_api_key(raw_key)
    if not key_info:
        api_key_prefix = raw_key[:8] if raw_key else "unknown"
        logger.warning(json.dumps({
            "event": "api_auth_failed",
            "reason": "invalid_key",
            "api_key_prefix": api_key_prefix,
            "request_id": request_id,
        }))
        return _error_response(
            401, "invalid_api_key",
            "API key is invalid, revoked, or expired.", meta
        )

    email = key_info["email"]
    api_key_prefix = raw_key[:8]

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
        _duration_ms = int((datetime.now(timezone.utc) - _start_time).total_seconds() * 1000)
        logger.info(json.dumps({
            "event": "api_request",
            "method": http_method,
            "path": path,
            "api_key_prefix": api_key_prefix,
            "request_id": request_id,
            "status_code": 429,
            "duration_ms": _duration_ms,
        }))
        return _error_response(
            429, "rate_limit_exceeded",
            f"Too many requests. Rate limit: {key_info['rate_limit_rpm']}/min.",
            meta,
            extra_headers={**rate_limit_headers, "Retry-After": "60"},
        )

    # --- Routing ---
    result = None
    try:
        result = _route(http_method, path, headers, body, query_params, email, meta)
    except Exception as e:
        logger.error(f"[API_HANDLER] Unhandled error: {e}", exc_info=True)
        result = _error_response(500, "server_error", "An internal error occurred.", meta)
    finally:
        _duration_ms = int((datetime.now(timezone.utc) - _start_time).total_seconds() * 1000)
        _status_code = (result or {}).get("statusCode", 500)
        logger.info(json.dumps({
            "event": "api_request",
            "method": http_method,
            "path": path,
            "api_key_prefix": api_key_prefix,
            "request_id": request_id,
            "status_code": _status_code,
            "duration_ms": _duration_ms,
        }))
        if _status_code >= 400:
            _body = {}
            try:
                _body = json.loads((result or {}).get("body", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass
            _error_code = (_body.get("error") or {}).get("code", "unknown")
            logger.error(json.dumps({
                "event": "api_error",
                "method": http_method,
                "path": path,
                "request_id": request_id,
                "status_code": _status_code,
                "error_code": _error_code,
            }))

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

    # POST /uploads/confirm
    if http_method == "POST" and clean == "/uploads/confirm":
        return _handle_confirm_upload(body, email, meta)

    # POST /jobs/reference-check  (before generic /jobs route)
    if http_method == "POST" and clean == "/jobs/reference-check":
        return _handle_reference_check(body, email, meta)

    # POST /jobs
    if http_method == "POST" and clean == "/jobs":
        return _handle_create_job(body, email, meta)

    # GET /jobs/{job_id}/reference-results
    if http_method == "GET" and clean.endswith("/reference-results"):
        parts = clean.split("/")  # ['', 'jobs', '{job_id}', 'reference-results']
        if len(parts) == 4 and parts[1] == "jobs":
            return _handle_get_reference_results(parts[2], email, meta)

    # GET /jobs/{job_id}/messages  — replay persisted WebSocket progress messages
    if http_method == "GET" and clean.endswith("/messages"):
        parts = clean.split("/")  # ['', 'jobs', '{job_id}', 'messages']
        if len(parts) == 4 and parts[1] == "jobs":
            return _handle_get_job_messages(parts[2], email, query_params, meta)

    # GET /jobs/{job_id}   (must not end in /validate, /results, /reference-results, /messages)
    if (
        http_method == "GET"
        and clean.startswith("/jobs/")
        and not clean.endswith(("/validate", "/results", "/reference-results", "/messages"))
    ):
        job_id = clean[6:]
        if job_id and "/" not in job_id:
            return _handle_get_job_status(job_id, email, query_params, meta)

    # POST /jobs/update-table  (before /jobs/{job_id}/validate to avoid mis-routing)
    if http_method == "POST" and clean == "/jobs/update-table":
        return _handle_update_table(body, email, meta)

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

    # --- Conversation routes ---
    # POST /conversations/table-maker
    if http_method == "POST" and clean == "/conversations/table-maker":
        return _handle_start_table_maker(body, email, meta)

    # POST /conversations/upload-interview
    if http_method == "POST" and clean == "/conversations/upload-interview":
        return _handle_start_upload_interview(body, email, meta)

    if clean.startswith("/conversations/"):
        conv_segment = clean[len("/conversations/"):]  # e.g. "{conv_id}" or "{conv_id}/message"
        conv_parts = conv_segment.split("/", 1)
        conv_id = conv_parts[0]
        sub = conv_parts[1] if len(conv_parts) > 1 else ""

        if conv_id and http_method == "GET" and not sub:
            return _handle_get_conversation(conv_id, email, query_params, meta)

        if conv_id and http_method == "POST" and sub == "message":
            return _handle_conversation_message(conv_id, body, email, meta)

        if conv_id and http_method == "POST" and sub == "select":
            return _handle_conversation_select(conv_id, body, email, meta)

        if conv_id and http_method == "POST" and sub == "refine-config":
            return _handle_refine_config(conv_id, body, email, meta)

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


def _handle_confirm_upload(body, email, meta):
    """
    POST /v1/uploads/confirm

    Mirrors what the web UI does after an Excel upload:
      1. Verify the file landed in S3
      2. Run _find_matching_configs() on the raw Excel bytes
      3. Save session_info (table_name, input_file, table_path) so subsequent
         calls (upload-interview, POST /v1/jobs) have everything they need
      4. Save table_analysis so upload-interview doesn't have to re-parse
      5. Return structured matches + a next_steps block that spells out every
         available option with the exact API call(s) needed

    Required body fields: s3_key, session_id
    Optional: upload_id, filename
    """
    s3_key = body.get("s3_key")
    session_id = body.get("session_id")
    upload_id = body.get("upload_id", "")
    filename = body.get("filename", "")

    if not s3_key or not session_id:
        return _error_response(400, "missing_fields", "s3_key and session_id are required.", meta)

    if not session_id.startswith("session_"):
        session_id = f"session_{session_id}"

    try:
        from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
        from interface_lambda.utils.helpers import clean_table_name

        mgr = UnifiedS3Manager()

        # 1. Verify the file actually landed in S3
        try:
            head = mgr.s3_client.head_object(Bucket=mgr.bucket_name, Key=s3_key)
            file_size = head["ContentLength"]
        except Exception:
            return _error_response(
                404, "file_not_found",
                "File not found in S3. Ensure the PUT upload completed before calling confirm.", meta
            )

        # 2. Infer filename from s3_key if caller didn't send it
        #    S3 key format: results/{domain}/{user}/{session_id}/{upload_id}_{filename}
        if not filename:
            raw = s3_key.split("/")[-1]
            # Strip "upload_{hex}_" prefix
            parts = raw.split("_", 2)
            filename = parts[2] if (len(parts) == 3 and parts[0] == "upload") else raw

        display_name = clean_table_name(filename, for_display=True)
        filename_base = clean_table_name(filename, for_display=False)

        # 3. Save session_info — everything downstream depends on this
        try:
            sess_info = mgr.load_session_info(email, session_id)
            sess_info["original_filename"] = filename
            sess_info["clean_table_name"] = display_name
            sess_info["table_name_base"] = filename_base
            sess_info["table_path"] = s3_key
            sess_info["input_file"] = {
                "s3_key": s3_key,
                "upload_id": upload_id,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            mgr.save_session_info(email, session_id, sess_info)
            logger.info(f"[CONFIRM_UPLOAD] Saved session_info for {session_id}")
        except Exception as e:
            logger.warning(f"[CONFIRM_UPLOAD] Could not save session_info: {e}")

        # 4. Download bytes and run the match finder (same path as confirm_upload_complete)
        matching_data = {"success": False, "matches": [], "perfect_match": False}
        table_columns = []
        match_error = None
        try:
            # find_matching_configs reads the Excel from S3 internally via session_info.table_path
            # (saved above), so we don't need to download the bytes here.
            from interface_lambda.actions.find_matching_config import find_matching_configs
            result = find_matching_configs(email, session_id)
            if result:
                matching_data = result
            table_columns = matching_data.get("table_columns") or []

            # Save table_analysis so upload-interview doesn't have to re-parse
            if table_columns:
                try:
                    sess_info = mgr.load_session_info(email, session_id)
                    sess_info["table_analysis"] = {
                        "columns": table_columns,
                        "row_count": None,
                        "sample_rows": [],
                    }
                    mgr.save_session_info(email, session_id, sess_info)
                except Exception as e:
                    logger.warning(f"[CONFIRM_UPLOAD] Could not save table_analysis: {e}")

        except Exception as e:
            logger.warning(f"[CONFIRM_UPLOAD] Match-finding error (non-fatal): {e}")
            match_error = str(e)

        # 5. Shape the matches list for the API response
        raw_matches = matching_data.get("matches") or []
        perfect_match = bool(matching_data.get("perfect_match"))
        auto_select = matching_data.get("auto_select_config")

        matches = []
        for m in raw_matches:
            if not m.get("config_id"):
                continue
            matches.append({
                "config_id": m["config_id"],
                "name": m.get("description") or m["config_id"],
                "match_score": round(float(m.get("match_score") or 0), 3),
                "matched_columns": m.get("matching_columns"),
                "total_columns": m.get("column_count"),
                "created_at": m.get("created_date") or m.get("last_modified"),
            })

        match_count = len(matches)
        top_config_id = (auto_select or {}).get("config_id") or (matches[0]["config_id"] if matches else None)

        # 6. Build next_steps — spell out every option with ready-to-execute calls
        options = []

        if match_count > 0:
            options.append({
                "action": "use_match",
                "label": "Use a matching config",
                "description": (
                    f"{'Perfect match found. ' if perfect_match else ''}"
                    f"{match_count} existing config{'s' if match_count > 1 else ''} "
                    f"matched this table structure. Pick one from the matches list above."
                ),
                "method": "POST",
                "url": "/v1/jobs",
                "body": {
                    "session_id": session_id,
                    "config_id": top_config_id,
                    "preview_rows": 3,
                },
                "note": "Replace config_id with any config_id from the matches[] list.",
            })

        options.append({
            "action": "use_code",
            "label": "Use a config ID you already have",
            "description": (
                "If you know the config_id from a previous run or from GET /v1/account/usage, "
                "submit it directly without needing to match."
            ),
            "method": "POST",
            "url": "/v1/jobs",
            "body": {
                "session_id": session_id,
                "config_id": "<your_config_id>",
                "preview_rows": 3,
            },
        })

        options.append({
            "action": "upload_config",
            "label": "Upload your own config file",
            "description": (
                "Upload a JSON config file you already have. "
                "The file goes straight to your session — no extra storage step needed."
            ),
            "steps": [
                {
                    "step": 1,
                    "label": "Get a presigned URL for your config file",
                    "method": "POST",
                    "url": "/v1/uploads/presigned",
                    "body": {
                        "file_type": "config",
                        "filename": "my_config.json",
                        "file_size": "<byte_length_of_your_file>",
                        "session_id": session_id,
                    },
                    "note": "Response includes config_s3_key — use it in step 3.",
                },
                {
                    "step": 2,
                    "label": "PUT your file to the presigned URL",
                    "method": "PUT",
                    "url": "<presigned_url from step 1>",
                    "headers": {"Content-Type": "application/json"},
                    "body": "<raw file bytes>",
                },
                {
                    "step": 3,
                    "label": "Submit the job referencing the uploaded config",
                    "method": "POST",
                    "url": "/v1/jobs",
                    "body": {
                        "session_id": session_id,
                        "config_s3_key": "<config_s3_key from step 1 response>",
                        "preview_rows": 3,
                    },
                },
            ],
        })

        options.append({
            "action": "create_ai",
            "label": "Generate a new config with AI",
            "description": (
                "Start a short interview and let the AI build a validation config "
                "tailored to this table. The interview usually takes 1–3 turns before "
                "config generation begins (~2–4 min total)."
            ),
            "steps": [
                {
                    "step": 1,
                    "label": "Start the upload interview",
                    "method": "POST",
                    "url": "/v1/conversations/upload-interview",
                    "body": {"session_id": session_id},
                    "note": "Returns conversation_id. The AI will ask clarifying questions.",
                },
                {
                    "step": 2,
                    "label": "Poll conversation state until trigger_execution is true",
                    "method": "GET",
                    "url": f"/v1/conversations/{{conv_id}}?session_id={session_id}",
                    "note": (
                        "Each response includes last_ai_message. If the AI asks a question, "
                        "reply via POST /v1/conversations/{conv_id}/message. "
                        "When trigger_execution == true, config generation has started — "
                        "proceed to step 3."
                    ),
                },
                {
                    "step": 3,
                    "label": "Submit a preview job (use next_step.body from step 2 response)",
                    "method": "POST",
                    "url": "/v1/jobs",
                    "body": {
                        "session_id": session_id,
                        "preview_rows": 3,
                    },
                },
            ],
        })

        # Determine recommended action
        if perfect_match or match_count > 0:
            recommended = "use_match"
        else:
            recommended = "create_ai"

        next_steps = {
            "recommended": recommended,
            "options": options,
        }

        response_data = {
            "session_id": session_id,
            "table_name": display_name,
            "file_size_bytes": file_size,
            "match_count": match_count,
            "perfect_match": perfect_match,
            "matches": matches,
            "next_steps": next_steps,
        }
        if match_error:
            response_data["match_warning"] = f"Config matching encountered an error and was skipped: {match_error}"

        return _success_response(200, response_data, meta)

    except Exception as e:
        logger.error(f"[CONFIRM_UPLOAD] Unexpected error: {e}", exc_info=True)
        return _error_response(500, "server_error", f"Upload confirmation failed: {e}", meta)


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

    # Resolve config in priority order: config_id → config_s3_key → inline config
    config_id = body.get("config_id")
    config_s3_key = body.get("config_s3_key")
    config = body.get("config")

    if config_id:
        # Copy saved config by ID into the session path
        try:
            from interface_lambda.actions.use_config_by_id import handle_use_config_by_id
            result = handle_use_config_by_id(
                {"email": email, "_verified_email": email, "session_id": base_session_id, "config_id": config_id},
                None,
            )
            # handle_use_config_by_id returns a create_response() envelope
            parsed = _parse_handler_response(result)
            if parsed["status_code"] >= 400 or parsed["body"].get("success") is False:
                msg = (parsed["body"].get("message")
                       or parsed["body"].get("error")
                       or f"Configuration '{config_id}' not found.")
                return _error_response(404, "config_not_found", msg, meta)
            logger.info(f"[API_HANDLER] Applied config_id={config_id} for {base_session_id}")
        except Exception as e:
            logger.warning(f"[API_HANDLER] Could not apply config_id: {e}")
            return _error_response(404, "config_not_found",
                                   f"Configuration '{config_id}' not found.", meta)
    elif config_s3_key:
        # Copy already-uploaded config file to the canonical session config path
        try:
            from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
            mgr = UnifiedS3Manager()
            target_key = f"{mgr.get_session_path(email, base_session_id)}config.json"
            mgr.s3_client.copy_object(
                Bucket=mgr.bucket_name,
                CopySource={"Bucket": mgr.bucket_name, "Key": config_s3_key},
                Key=target_key,
            )
            logger.info(f"[API_HANDLER] Copied config_s3_key={config_s3_key} → {target_key}")
        except Exception as e:
            logger.warning(f"[API_HANDLER] Could not copy config_s3_key: {e}")
    elif config:
        # Save inline config using store_config_file so storage_metadata.config_id
        # is set — this lets background_handler record a real config_id in DynamoDB
        # that can later be looked up via GET /v1/jobs/{id}/results and reused.
        try:
            from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
            mgr = UnifiedS3Manager()
            store_result = mgr.store_config_file(
                email=email,
                session_id=base_session_id,
                config_data=config,
                version=1,
                source="api_inline",
            )
            if not store_result.get("success"):
                logger.warning(f"[API_HANDLER] store_config_file failed: {store_result.get('error')}, falling back to raw put")
                config_key = f"{mgr.get_session_path(email, base_session_id)}config.json"
                mgr.s3_client.put_object(
                    Bucket=mgr.bucket_name,
                    Key=config_key,
                    Body=json.dumps(config, indent=2).encode("utf-8"),
                    ContentType="application/json",
                )
            else:
                logger.info(f"[API_HANDLER] Saved inline config via store_config_file: {store_result.get('s3_key')}")
        except Exception as e:
            logger.warning(f"[API_HANDLER] Could not save config to S3: {e}")
    else:
        # No config supplied via request — check if the session already has one.
        # This is the normal path after a table-maker or upload-interview flow,
        # where the background handler writes a config to the session before
        # setting trigger_execution=True.
        try:
            from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
            from interface_lambda.actions.generate_config_unified import find_latest_config_in_session
            _mgr = UnifiedS3Manager()
            _existing = find_latest_config_in_session(
                _mgr.s3_client, _mgr.bucket_name,
                _mgr.get_session_path(email, base_session_id)
            )
        except Exception as _e:
            logger.warning(f"[API_HANDLER] Could not check for existing session config: {_e}")
            _existing = None

        if not _existing:
            return _error_response(
                400, "missing_config",
                "One of config, config_id, or config_s3_key is required.", meta
            )
        logger.info(f"[API_HANDLER] Using existing session config for {base_session_id}")

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
    """GET /v1/jobs/{job_id}

    Reads DynamoDB directly to avoid Decimal serialisation issues that occur
    when passing a raw DynamoDB item through create_response / json.dumps.
    """
    _STATUS_MAP = {
        "COMPLETED": "completed",
        "COMPLETE": "completed",      # reference check stores lowercase "complete"
        "PROCESSING": "processing",
        "IN_PROGRESS": "processing",
        "PENDING": "queued",
        "QUEUED": "queued",
        "FAILED": "failed",
        "ERROR": "failed",
    }

    try:
        from dynamodb_schemas import find_run_key_by_type, find_existing_run_key, get_run_status

        # Prefer the Validation run if one exists; fall back to any run (Preview)
        run_key = find_run_key_by_type(job_id, "Validation") or find_existing_run_key(job_id)

        if not run_key:
            logger.info(f"[JOB_STATUS] No run record found for job_id={job_id}")
            return _success_response(200, {
                "job_id": job_id, "status": "queued",
                "progress_percent": 0, "current_step": "Job is queued.",
            }, meta, extra_headers={"Retry-After": "10"})

        record = get_run_status(job_id, run_key)
        if not record:
            return _success_response(200, {
                "job_id": job_id, "status": "queued",
                "progress_percent": 0, "current_step": "Job is processing.",
            }, meta, extra_headers={"Retry-After": "10"})

        # Safely extract fields — DynamoDB returns Decimal for numbers
        db_status = str(record.get("status") or "PROCESSING").upper()
        pct = int(record.get("percent_complete") or 0)
        step = str(record.get("verbose_status") or record.get("message") or "")
        _t = record.get("start_time") or record.get("created_at")
        submitted_at = str(_t) if _t is not None else None

        logger.info(f"[JOB_STATUS] job_id={job_id} run_key={run_key!r} db_status={db_status} pct={pct}")

        # A completed Preview run means "awaiting approval", not "completed"
        is_preview_run = run_key.lower().startswith("preview#")
        if db_status == "COMPLETED" and is_preview_run:
            api_status = "preview_complete"
        else:
            api_status = _STATUS_MAP.get(db_status, db_status.lower())

    except Exception as e:
        logger.error(f"[JOB_STATUS] Error reading status for {job_id}: {e}", exc_info=True)
        return _error_response(500, "server_error", "Failed to retrieve job status.", meta)

    data = {
        "job_id": job_id,
        "status": api_status,
        "progress_percent": pct,
        "current_step": step or None,
        "submitted_at": submitted_at,
    }

    # Surface preview results when the preview run is complete
    if api_status == "preview_complete" and record:
        config_id = record.get("configuration_id")
        if config_id:
            data["config_id"] = config_id
        pr_key = record.get("preview_results_s3_key")
        if pr_key:
            from interface_lambda.core.s3_manager import generate_presigned_url, S3_RESULTS_BUCKET
            pr_dir = pr_key.rsplit("/", 1)[0]
            data["preview_results"] = {
                "download_url": generate_presigned_url(S3_RESULTS_BUCKET, pr_key),
                "file_format": "xlsx" if pr_key.endswith(".xlsx") else "unknown",
                "metadata_url": generate_presigned_url(S3_RESULTS_BUCKET, f"{pr_dir}/table_metadata.json"),
            }
        pd = record.get("preview_data") or {}
        ce = pd.get("cost_estimate") or {}
        data["cost_estimate"] = {
            "estimated_total_cost_usd": ce.get("total_cost"),
            "estimated_rows": pd.get("total_rows"),
        }
        data["next_steps"] = {
            "approve_url": f"/v1/jobs/{job_id}/validate",
            "requires_approval": True,
        }

    extra = {"Retry-After": "10"} if api_status in ("processing", "queued") else None
    return _success_response(200, data, meta, extra_headers=extra)


def _handle_update_table(body, email, meta):
    """POST /v1/jobs/update-table

    Creates a new preview job whose input is the enhanced/validated Excel from a
    completed source job.  The source job's config is automatically copied so
    the same validation logic is applied to the updated data.

    Request body:
        source_job_id  (str, required)  — completed job to take output from
        source_version (int, optional)  — which result version to use (default: latest)
    """
    source_job_id = body.get("source_job_id")
    if not source_job_id:
        return _error_response(400, "missing_fields", "source_job_id is required.", meta)

    source_version = body.get("source_version")

    # Build the new session (copy enhanced output + config) using existing backend
    request_data = {"email": email, "source_session_id": source_job_id}
    if source_version is not None:
        request_data["source_version"] = source_version

    from interface_lambda.actions.create_update_session import handle_create_update_session
    resp = handle_create_update_session(request_data, None)
    parsed = _parse_handler_response(resp)

    if parsed["status_code"] >= 400 or parsed["body"].get("success") is False:
        b = parsed["body"]
        error_msg = b.get("error") or "Failed to create update session."
        # Map backend errors to appropriate HTTP codes
        if "not found" in error_msg.lower() or parsed["status_code"] == 404:
            return _error_response(404, "source_not_found", error_msg, meta)
        return _error_response(parsed["status_code"], "update_table_failed", error_msg, meta)

    new_session_id = parsed["body"].get("new_session_id")
    is_preview_data = bool(parsed["body"].get("used_preview_data", False))

    if not new_session_id:
        return _error_response(500, "server_error", "Failed to generate new session ID.", meta)

    # Queue the preview on the new session
    preview_request = {
        "_verified_email": email,
        "_api_email": email,
        "session_id": new_session_id,
        "preview_max_rows": 3,
    }
    from interface_lambda.actions import start_preview
    preview_resp = start_preview.handle_start_preview(preview_request, None)
    preview_parsed = _parse_handler_response(preview_resp)

    if preview_parsed["status_code"] >= 400:
        b = preview_parsed["body"]
        return _error_response(
            preview_parsed["status_code"],
            b.get("error", "request_failed"),
            b.get("message") or "Failed to queue preview for new session.",
            meta,
        )

    response_data = {
        "job_id": new_session_id,
        "source_job_id": source_job_id,
        "status": "queued",
        "run_type": "preview",
        "note": "Enhanced output from source job used as new input. Config automatically copied.",
        "urls": {
            "status": f"/v1/jobs/{new_session_id}",
            "results": f"/v1/jobs/{new_session_id}/results",
        },
    }
    if is_preview_data:
        response_data["used_preview_data"] = True
        response_data["warning"] = (
            "Source job only had preview data available — full validation output was not found. "
            "Run a full validation on the source job first for complete results."
        )

    return _success_response(202, response_data, meta)


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
    parsed = _parse_handler_response(resp)
    if parsed["status_code"] >= 400 or parsed["body"].get("success") is False:
        return _wrap_handler_response(resp, meta)
    account_info = parsed["body"].get("account_info", {})
    _internal_fields = {"raw_cost", "multiplier_applied"}
    transactions = [
        {k: v for k, v in tx.items() if k not in _internal_fields}
        for tx in account_info.get("recent_transactions", [])
    ]
    return _success_response(200, {
        "email": account_info.get("email", email),
        "balance_usd": account_info.get("current_balance", 0),
        "domain": account_info.get("email_domain", ""),
        "recent_transactions": transactions,
    }, meta)


def _handle_account_usage(email, query_params, meta):
    """GET /v1/account/usage"""
    try:
        limit  = min(int(query_params.get("limit",  50)), 200)
        offset = int(query_params.get("offset", 0))
    except (ValueError, TypeError):
        return _error_response(400, "invalid_input", "limit and offset must be integers.", meta)

    start_date = query_params.get("start_date", "")
    end_date   = query_params.get("end_date", "")

    try:
        from dynamodb_schemas import get_user_transactions
        # Fetch enough rows to support the requested offset+limit in one call.
        raw = get_user_transactions(email, limit=limit + offset)
    except Exception as e:
        logger.error(f"[API_HANDLER] get_user_transactions failed: {e}", exc_info=True)
        return _error_response(500, "server_error", "Failed to retrieve usage data.", meta)

    _internal_fields = {"raw_cost", "multiplier_applied"}
    filtered = []
    for tx in raw:
        ts = tx.get("timestamp", "")
        if start_date and ts < start_date:
            continue
        if end_date and ts > end_date + "T23:59:59":
            continue
        filtered.append({k: v for k, v in tx.items() if k not in _internal_fields})

    page = filtered[offset: offset + limit]
    total_debited = round(
        sum(abs(tx.get("amount", 0)) for tx in page if (tx.get("amount") or 0) < 0),
        6,
    )
    return _success_response(200, {
        "transactions": page,
        "total_cost_usd": total_debited,
        "count": len(page),
        "limit": limit,
        "offset": offset,
    }, meta)


def _handle_reference_check(body, email, meta):
    """POST /v1/jobs/reference-check"""
    import asyncio

    text = (body.get("text") or "").strip()
    upload_s3_key = body.get("s3_key")
    session_id = body.get("session_id") or f"session_{uuid.uuid4().hex[:16]}"

    if not text and not upload_s3_key:
        return _error_response(400, "missing_fields", "text or s3_key is required.", meta)

    # Extract text from uploaded file if no inline text provided
    if upload_s3_key and not text:
        try:
            from interface_lambda.actions.reference_check.pdf_converter import extract_text_from_s3
            text = extract_text_from_s3(upload_s3_key)
        except Exception as e:
            logger.error(f"[API_HANDLER] Text extraction failed: {e}", exc_info=True)
            return _error_response(500, "extraction_failed", f"Could not extract text from file: {e}", meta)

    if not text:
        return _error_response(400, "empty_text", "No text could be extracted from the provided file.", meta)

    try:
        from interface_lambda.actions.reference_check.conversation import handle_reference_check_start_async
        resp = asyncio.run(handle_reference_check_start_async(
            {"email": email, "session_id": session_id, "submitted_text": text},
            None,
        ))
    except Exception as e:
        logger.error(f"[API_HANDLER] Reference check start failed: {e}", exc_info=True)
        return _error_response(500, "server_error", f"Failed to start reference check: {e}", meta)

    parsed = _parse_handler_response(resp)
    if parsed["status_code"] >= 400 or parsed["body"].get("success") is False:
        b = parsed["body"]
        return _error_response(
            parsed["status_code"],
            b.get("error", "request_failed"),
            b.get("message") or "Failed to start reference check",
            meta,
        )

    body_data = parsed["body"]
    return _success_response(202, {
        "job_id": session_id,
        "conversation_id": body_data.get("conversation_id"),
        "status": "processing",
        "urls": {
            "status": f"/v1/jobs/{session_id}",
            "results": f"/v1/jobs/{session_id}/reference-results",
        },
        "polling": {
            "recommended_interval_seconds": 10,
            "max_wait_seconds": 300,
        },
    }, meta)


def _handle_get_job_messages(job_id, email, query_params, meta):
    """GET /v1/jobs/{job_id}/messages?since_seq=0&limit=100

    Returns persisted WebSocket progress messages for a job/session.
    These are the same real-time updates that WebSocket clients receive,
    stored to DynamoDB so REST polling clients can retrieve them.

    Use since_seq to page through messages (start at 0, then pass the last
    returned seq on the next call to get only new messages).
    """
    try:
        since_seq = int(query_params.get("since_seq") or 0)
        limit = min(int(query_params.get("limit") or 100), 200)
    except (ValueError, TypeError):
        since_seq, limit = 0, 100

    try:
        from dynamodb_schemas import get_messages_since
        result = get_messages_since(job_id, since_seq, limit)

        # Extract a simplified progress view from the messages
        latest_pct = None
        latest_step = None
        for msg in result.get("messages", []):
            data = msg.get("data") or msg
            if "progress_percent" in data:
                latest_pct = data["progress_percent"]
            if "message" in data:
                latest_step = data["message"]

        return _success_response(200, {
            "job_id": job_id,
            "messages": result["messages"],
            "last_seq": result["last_seq"],
            "has_more": result["has_more"],
            "summary": {
                "latest_progress_percent": latest_pct,
                "latest_step": latest_step,
                "message_count": len(result["messages"]),
            },
        }, meta)
    except Exception as e:
        logger.error(f"[API_HANDLER] get_job_messages failed for {job_id}: {e}", exc_info=True)
        return _error_response(500, "server_error", "Failed to retrieve job messages.", meta)


def _handle_get_reference_results(job_id, email, meta):
    """GET /v1/jobs/{job_id}/reference-results"""
    request_data = {
        "_api_email": email,
        "_verified_email": email,
        "job_id": job_id,
    }
    from interface_lambda.actions import status_check
    resp = status_check.handle_get_reference_results(request_data, None)
    return _wrap_handler_response(resp, meta)


# ---------------------------------------------------------------------------
# Conversation handlers
# ---------------------------------------------------------------------------

def _handle_start_table_maker(body, email, meta):
    """POST /v1/conversations/table-maker"""
    from interface_lambda.actions.table_maker.conversation import handle_table_conversation_start_async

    session_id = body.get("session_id") or f"session_{uuid.uuid4().hex[:16]}"
    resp = handle_table_conversation_start_async(
        {
            "email": email,
            "session_id": session_id,
            "user_message": body.get("message", ""),
        },
        None,
    )
    parsed = _parse_handler_response(resp)
    if parsed["status_code"] >= 400 or parsed["body"].get("success") is False:
        b = parsed["body"]
        return _error_response(
            parsed["status_code"],
            b.get("error", "request_failed"),
            b.get("message") or "Failed to start table maker",
            meta,
        )
    b = parsed["body"]
    conv_id = b.get("conversation_id")
    actual_session_id = b.get("session_id", session_id)

    # Write processing marker so GET /v1/conversations/{conv_id} returns
    # status='processing' rather than 404 while SQS initialises.
    if conv_id:
        _write_processing_state(conv_id, email, actual_session_id)

    return _success_response(202, {
        "session_id": actual_session_id,
        "conversation_id": conv_id,
        "status": "processing",
        "urls": {
            "job_status": f"/v1/jobs/{actual_session_id}",
            "conversation": f"/v1/conversations/{conv_id}",
        },
        "polling": {
            "recommended_interval_seconds": 10,
            "max_wait_seconds": 600,
        },
    }, meta)


def _handle_start_upload_interview(body, email, meta):
    """POST /v1/conversations/upload-interview"""
    import asyncio
    from interface_lambda.actions.upload_interview import handle_upload_interview_start_async

    session_id = body.get("session_id")
    if not session_id:
        return _error_response(400, "missing_fields", "session_id is required for upload interview.", meta)

    conv_id = f"upload_conv_{uuid.uuid4().hex[:12]}"
    resp = asyncio.run(handle_upload_interview_start_async(
        {
            "email": email,
            "session_id": session_id,
            "conversation_id": conv_id,
            "user_message": body.get("message", ""),
        },
        None,
    ))
    parsed = _parse_handler_response(resp)
    if parsed["status_code"] >= 400 or parsed["body"].get("success") is False:
        b = parsed["body"]
        return _error_response(
            parsed["status_code"],
            b.get("error", "request_failed"),
            b.get("message") or "Failed to start upload interview",
            meta,
        )
    b = parsed["body"]
    actual_conv_id = b.get("conversation_id", conv_id)

    # Write processing marker so GET /v1/conversations/{conv_id} returns
    # status='processing' rather than 404 while SQS initialises.
    _write_processing_state(actual_conv_id, email, session_id)

    return _success_response(202, {
        "session_id": session_id,
        "conversation_id": actual_conv_id,
        "status": "processing",
        "urls": {
            "conversation": f"/v1/conversations/{actual_conv_id}",
            "select": f"/v1/conversations/{actual_conv_id}/select",
        },
        "polling": {
            "recommended_interval_seconds": 5,
            "max_wait_seconds": 120,
        },
    }, meta)


def _conv_state_key(conv_id, email, session_id):
    """Return the S3 key for a conversation state file.

    Paths must match what the background handler writes:
      table_conv_  → UnifiedS3Manager.get_table_maker_path → results/{domain}/{prefix}/{session}/table_maker/{conv}/conversation_state.json
      upload_conv_ → same base path but /upload_interview/ subdir and filename state.json
      refcheck_    → reference_checks/{email}/{session}/{conv}/conversation_state.json  (uses raw email)
      refine_      → refine/{email}/{session}/{conv}/conversation_state.json
    """
    if conv_id.startswith("table_conv_"):
        from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
        mgr = UnifiedS3Manager()
        return mgr.get_table_maker_path(email, session_id, conv_id, "conversation_state.json")
    if conv_id.startswith("refcheck_"):
        return f"reference_checks/{email}/{session_id}/{conv_id}/conversation_state.json"
    if conv_id.startswith("upload_conv_"):
        from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
        mgr = UnifiedS3Manager()
        base = mgr.get_table_maker_path(email, session_id, conv_id, "state.json")
        return base.replace("/table_maker/", "/upload_interview/")
    if conv_id.startswith("refine_"):
        return f"refine/{email}/{session_id}/{conv_id}/conversation_state.json"
    return None


def _write_processing_state(conv_id, email, session_id, existing_state=None):
    """
    Write (or patch) the conversation state to status='processing' immediately
    after queuing an SQS message.  This ensures GET /v1/conversations/{conv_id}
    always returns a meaningful response while the background worker is running,
    rather than a 404 or stale 'awaiting_reply' from the previous turn.
    """
    import json as _json
    try:
        from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
        state_key = _conv_state_key(conv_id, email, session_id)
        if not state_key:
            return
        mgr = UnifiedS3Manager()
        state = dict(existing_state) if existing_state else {}
        state["status"] = "processing"
        state.setdefault("conversation_id", conv_id)
        state.setdefault("session_id", session_id)
        state.setdefault("turn_count", 0)
        mgr.s3_client.put_object(
            Bucket=mgr.bucket_name,
            Key=state_key,
            Body=_json.dumps(state).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception as e:
        logger.warning(f"[API_HANDLER] Could not write processing state for {conv_id}: {e}")


def _extract_last_ai_message(state):
    """
    Pull the most recent AI message out of a conversation state dict.

    Both the table maker and upload interview store conversation history in a
    'messages' list of {'role': 'user'|'assistant', 'content': str} dicts.
    There is no top-level 'last_ai_message' field — we derive it here.
    """
    messages = state.get("messages") or []
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            return msg.get("content") or msg.get("ai_message")
    # Fallback to any top-level field the background processor might have written
    return (
        state.get("ai_message")
        or state.get("last_ai_message")
        or state.get("follow_up_question")
    )


def _compute_conversation_signals(conv_id, state):
    """
    Derive user_reply_needed and trigger_execution from raw S3 state.

    State machines differ by conversation type:

    upload_conv_*:
      status='processing'                          → user_reply_needed=False (SQS running)
      status='in_progress', tcg=False              → user_reply_needed=True  (AI asked Q, mode 1)
      status='awaiting_approval'                   → user_reply_needed=True  (AI presented plan, mode 2)
      status='in_progress', tcg=True               → user_reply_needed=False (config gen queued)
      trigger_execution=True                       → user_reply_needed=False (done)

    table_conv_*:
      status='processing'                          → user_reply_needed=False (SQS running)
      status='in_progress',  trigger_execution=F   → user_reply_needed=True  (AI asking questions)
      status='recovery'                            → user_reply_needed=True  (zero rows, needs guidance)
      status='execution_ready' / trigger_exec=True → user_reply_needed=False (execution pipeline running)
      status='preview_generated'                   → user_reply_needed=False (preview in progress)
    """
    status = state.get("status", "processing")
    trigger_execution = bool(state.get("trigger_execution", False))
    trigger_config_generation = bool(state.get("trigger_config_generation", False))

    if trigger_execution:
        return False, trigger_execution

    if status == "processing":
        return False, False

    if conv_id.startswith("upload_conv_"):
        if status == "awaiting_approval":
            return True, False
        if status == "in_progress" and not trigger_config_generation:
            return True, False
        # in_progress + trigger_config_generation=True → config gen running
        return False, False

    if conv_id.startswith("table_conv_"):
        if status in ("in_progress",) and not trigger_execution:
            return True, False
        if status == "recovery":
            return True, False
        # execution_ready, preview_generated, or trigger_execution=True
        return False, trigger_execution

    if conv_id.startswith("refine_"):
        # Fire-and-forget — never needs a user reply.
        # trigger_execution is set by _handle_get_conversation once a newer
        # config version is detected in S3.
        return False, trigger_execution

    return False, trigger_execution


def _handle_get_conversation(conv_id, email, query_params, meta):
    """GET /v1/conversations/{conv_id}"""
    import json as _json
    session_id = query_params.get("session_id")
    if not session_id:
        return _error_response(400, "missing_fields", "session_id query parameter is required.", meta)

    state_key = _conv_state_key(conv_id, email, session_id)
    if not state_key:
        return _error_response(400, "unknown_conversation", f"Cannot determine type of conversation: {conv_id}", meta)

    try:
        from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
        mgr = UnifiedS3Manager()

        # If the state file doesn't exist yet (SQS hasn't run), return a
        # 'processing' response rather than a 404 — the conversation exists,
        # it's just still being initialised in the background.
        try:
            state_obj = mgr.s3_client.get_object(Bucket=mgr.bucket_name, Key=state_key)
            state = _json.loads(state_obj["Body"].read())
        except mgr.s3_client.exceptions.NoSuchKey:
            return _success_response(200, {
                "conversation_id": conv_id,
                "session_id": session_id,
                "status": "processing",
                "turn_count": 0,
                "last_ai_message": None,
                "user_reply_needed": False,
                "trigger_execution": False,
                "table_name": None,
            }, meta, extra_headers={"Retry-After": "5"})
        except Exception:
            # head_object style 404 arrives as a generic ClientError
            return _success_response(200, {
                "conversation_id": conv_id,
                "session_id": session_id,
                "status": "processing",
                "turn_count": 0,
                "last_ai_message": None,
                "user_reply_needed": False,
                "trigger_execution": False,
                "table_name": None,
            }, meta, extra_headers={"Retry-After": "5"})

        # For refine_ convs: lazily detect completion by checking if a new
        # config version was saved to S3 since the refinement was queued.
        if conv_id.startswith("refine_") and state.get("status") == "processing":
            try:
                from interface_lambda.actions.generate_config_unified import find_latest_config_in_session
                mgr2 = mgr  # already initialised above
                latest = find_latest_config_in_session(
                    mgr2.s3_client, mgr2.bucket_name,
                    mgr2.get_session_path(email, session_id)
                )
                if latest:
                    current_version = int(
                        (latest.get("storage_metadata") or {}).get("version") or 0
                    )
                    started_version = int(state.get("started_version") or 0)
                    if current_version > started_version:
                        # New config version exists — refinement is done
                        sm = latest.get("storage_metadata") or {}
                        new_config_id = sm.get("config_id") or sm.get("filename", "").replace(".json", "")
                        ai_summary = (
                            (latest.get("generation_metadata") or {}).get("ai_summary")
                            or "Config updated."
                        )
                        state["status"] = "completed"
                        state["trigger_execution"] = True
                        state["completed_config_id"] = new_config_id
                        state["ai_summary"] = ai_summary
                        # Persist so subsequent polls are instant
                        import json as _json2
                        mgr2.s3_client.put_object(
                            Bucket=mgr2.bucket_name, Key=state_key,
                            Body=_json2.dumps(state).encode("utf-8"),
                            ContentType="application/json",
                        )
            except Exception as _re:
                logger.warning(f"[REFINE_POLL] Could not check config version: {_re}")

        user_reply_needed, trigger_execution = _compute_conversation_signals(conv_id, state)
        last_ai_message = _extract_last_ai_message(state) or state.get("ai_summary")
        status = state.get("status", "processing")

        data = {
            "conversation_id": conv_id,
            "session_id": session_id,
            "status": status,
            "turn_count": state.get("turn_count"),
            "last_ai_message": last_ai_message,
            "user_reply_needed": user_reply_needed,
            "trigger_execution": trigger_execution,
            "table_name": state.get("table_name"),
        }

        if user_reply_needed:
            # Spell out exactly how to reply
            if status == "awaiting_approval":
                data["next_step"] = {
                    "action": "send_message",
                    "method": "POST",
                    "url": f"/v1/conversations/{conv_id}/message",
                    "body": {"session_id": session_id, "message": "<your reply>"},
                    "description": (
                        "The AI has proposed a validation plan (see last_ai_message). "
                        "Reply with a confirmation (e.g. 'Yes, proceed') to start config "
                        "generation, or describe any changes you want first."
                    ),
                }
            else:
                data["next_step"] = {
                    "action": "send_message",
                    "method": "POST",
                    "url": f"/v1/conversations/{conv_id}/message",
                    "body": {"session_id": session_id, "message": "<your reply>"},
                    "description": (
                        "The AI has asked a question (see last_ai_message). "
                        "Send your reply to continue the conversation."
                    ),
                }

        elif trigger_execution:
            job_body = {"session_id": session_id, "preview_rows": 3}
            description = (
                "The workflow is complete and a config has been written to the session. "
                "Submit a preview job to validate the results before full processing."
            )
            if conv_id.startswith("refine_") and state.get("completed_config_id"):
                job_body["config_id"] = state["completed_config_id"]
                description = (
                    f"Config refinement complete (config_id: {state['completed_config_id']}). "
                    "Submit a preview job to validate the updated configuration."
                )
            data["next_step"] = {
                "action": "submit_preview",
                "method": "POST",
                "url": "/v1/jobs",
                "body": job_body,
                "description": description,
            }

        elif status == "processing":
            data["next_step"] = {
                "action": "poll",
                "description": "The AI is still working. Poll again in a few seconds.",
            }

        extra = {"Retry-After": "5"} if status == "processing" else None
        return _success_response(200, data, meta, extra_headers=extra)

    except Exception as e:
        logger.error(f"[API_HANDLER] Get conversation failed for {conv_id}: {e}", exc_info=True)
        return _error_response(500, "server_error", f"Could not load conversation state: {e}", meta)


def _handle_conversation_message(conv_id, body, email, meta):
    """POST /v1/conversations/{conv_id}/message"""
    import asyncio

    if conv_id.startswith("table_conv_"):
        from interface_lambda.actions.table_maker.conversation import handle_table_conversation_continue_async
        session_id = body.get("session_id")
        if not session_id:
            return _error_response(400, "missing_fields", "session_id is required.", meta)
        resp = handle_table_conversation_continue_async(
            {
                "email": email,
                "session_id": session_id,
                "conversation_id": conv_id,
                "user_message": body.get("message", ""),
            },
            None,
        )
    elif conv_id.startswith("upload_conv_"):
        from interface_lambda.actions.upload_interview import handle_upload_interview_continue_async
        session_id = body.get("session_id")
        if not session_id:
            return _error_response(400, "missing_fields", "session_id is required.", meta)
        resp = asyncio.run(handle_upload_interview_continue_async(
            {
                "email": email,
                "session_id": session_id,
                "conversation_id": conv_id,
                "user_message": body.get("message", ""),
            },
            None,
        ))
    elif conv_id.startswith("refcheck_"):
        return _error_response(405, "method_not_allowed", "Reference checks do not support multi-turn messages.", meta)
    else:
        return _error_response(400, "unknown_conversation", f"Cannot determine type of conversation: {conv_id}", meta)

    # Mark state as 'processing' immediately after queuing so subsequent polls
    # see status='processing' + user_reply_needed=False rather than the stale
    # 'awaiting_reply' state from the previous turn.
    _write_processing_state(conv_id, email, session_id)

    return _wrap_handler_response(resp, meta, success_status=202)


def _handle_conversation_select(conv_id, body, email, meta):
    """POST /v1/conversations/{conv_id}/select"""
    session_id = body.get("session_id")
    if not session_id:
        return _error_response(400, "missing_fields", "session_id is required.", meta)

    selection = body.get("selection")
    if selection not in ("use_match", "create_ai", "use_code"):
        return _error_response(400, "invalid_selection", "selection must be use_match, create_ai, or use_code.", meta)

    try:
        if selection == "use_match":
            # Find the best matching config and apply it.
            # find_matching_configs can be slow (S3 + DynamoDB scan) so run it in
            # a thread with a hard timeout to prevent a Lambda timeout → API GW 503.
            import threading
            from interface_lambda.actions.find_matching_config import find_matching_configs
            _result: list = [None]
            _err: list = [None]

            def _run_matching():
                try:
                    _result[0] = find_matching_configs(email, session_id)
                except Exception as _e:
                    _err[0] = _e

            _t = threading.Thread(target=_run_matching, daemon=True)
            _t.start()
            _t.join(timeout=12)  # 12 s budget — leaves headroom before Lambda timeout

            if _err[0]:
                logger.warning(f"[API_HANDLER] find_matching_configs error: {_err[0]}")
            matches = _result[0]
            if matches:
                top = ((matches.get("matches") or [])[0:1] or [None])[0]
                if top and top.get("config_id"):
                    from interface_lambda.actions.use_config_by_id import handle_use_config_by_id
                    handle_use_config_by_id(
                        {"email": email, "_verified_email": email, "session_id": session_id, "config_id": top["config_id"]},
                        None,
                    )
                    return _success_response(200, {"applied": "use_match", "config_id": top["config_id"]}, meta)
            return _error_response(404, "no_match", "No matching config found.", meta)

        elif selection == "create_ai":
            # Queue AI config generation
            from interface_lambda.actions import generate_config_unified
            resp = generate_config_unified.handle(
                {"_verified_email": email, "session_id": session_id, "action": "generateConfig"},
                None,
            )
            return _wrap_handler_response(resp, meta, success_status=202)

        elif selection == "use_code":
            config_id = body.get("config_id")
            if not config_id:
                return _error_response(400, "missing_fields", "config_id is required for use_code selection.", meta)
            from interface_lambda.actions.use_config_by_id import handle_use_config_by_id
            resp = handle_use_config_by_id(
                {"email": email, "_verified_email": email, "session_id": session_id, "config_id": config_id},
                None,
            )
            parsed = _parse_handler_response(resp)
            if parsed["body"].get("success") is False:
                return _error_response(400, "config_error", parsed["body"].get("message", "Failed to apply config"), meta)
            return _success_response(200, {"applied": "use_code", "config_id": config_id}, meta)

    except Exception as e:
        logger.error(f"[API_HANDLER] Conversation select failed: {e}", exc_info=True)
        return _error_response(500, "server_error", f"Failed to apply selection: {e}", meta)


def _handle_refine_config(conv_id, body, email, meta):
    """POST /v1/conversations/{conv_id}/refine-config

    Queues a config refinement (modifyConfig) for the session.  The current
    config is auto-discovered; a new versioned config is written to S3 by the
    background handler.  Poll GET /v1/conversations/{conv_id}?session_id=...
    until next_step.action == "submit_preview" to know the refinement is done.
    """
    session_id = body.get("session_id")
    instructions = (body.get("instructions") or "").strip()

    if not session_id:
        return _error_response(400, "missing_fields", "session_id is required.", meta)
    if not instructions:
        return _error_response(400, "missing_fields", "instructions is required.", meta)

    # Record the current config version so polling can detect when a new one lands
    started_version = 0
    try:
        from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
        from interface_lambda.actions.generate_config_unified import find_latest_config_in_session
        mgr = UnifiedS3Manager()
        existing = find_latest_config_in_session(
            mgr.s3_client, mgr.bucket_name, mgr.get_session_path(email, session_id)
        )
        if existing:
            started_version = int(
                (existing.get("storage_metadata") or {}).get("version") or 0
            )
    except Exception as e:
        logger.warning(f"[REFINE_CONFIG] Could not read current config version: {e}")

    # Write processing marker immediately so first poll returns 200 not 404
    _write_processing_state(conv_id, email, session_id, existing_state={
        "started_version": started_version,
        "instructions": instructions,
    })

    # Queue the SQS refinement job
    try:
        from interface_lambda.actions.generate_config_unified import handle_generate_config_async
        resp = handle_generate_config_async(
            {"email": email, "session_id": session_id, "instructions": instructions},
            None,
        )
    except Exception as e:
        logger.error(f"[REFINE_CONFIG] Failed to queue refinement: {e}", exc_info=True)
        return _error_response(500, "server_error", f"Failed to queue refinement: {e}", meta)

    parsed = _parse_handler_response(resp)
    if parsed["status_code"] >= 400:
        b = parsed["body"]
        return _error_response(
            parsed["status_code"],
            b.get("error", "request_failed"),
            b.get("message") or "Failed to queue config refinement.",
            meta,
        )

    return _success_response(202, {
        "conversation_id": conv_id,
        "session_id": session_id,
        "status": "processing",
        "instructions": instructions,
        "urls": {
            "conversation": f"/v1/conversations/{conv_id}?session_id={session_id}",
        },
        "polling": {
            "recommended_interval_seconds": 10,
            "max_wait_seconds": 300,
            "note": "Poll until next_step.action == 'submit_preview', then POST to /v1/jobs with next_step.body.",
        },
    }, meta)


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
        "body": json.dumps({"success": True, "data": data, "error": None, "meta": meta}, default=_json_default),
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
        "body": json.dumps({"success": False, "data": None, "error": error, "meta": meta}, default=_json_default),
    }
