"""
Minimal Hyperplexity REST API client for use in example scripts.

Set HYPERPLEXITY_API_KEY in your environment before running any example:
    export HYPERPLEXITY_API_KEY=hpx_live_...

Get your key (and $20 free credits) at https://hyperplexity.ai/account
"""

import os
import time
from typing import Optional

import requests

BASE_URL = os.environ.get("HYPERPLEXITY_API_URL", "https://api.hyperplexity.ai/v1")
POLL_INTERVAL = 10   # seconds between job status polls
CONV_INTERVAL = 15   # seconds between conversation polls


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _api_key() -> str:
    key = os.environ.get("HYPERPLEXITY_API_KEY", "")
    if not key:
        raise RuntimeError(
            "HYPERPLEXITY_API_KEY is not set. "
            "Get your key at https://hyperplexity.ai/account"
        )
    return key


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _unwrap(response: requests.Response) -> dict:
    """Raise on HTTP or API errors, return data payload."""
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        err = payload.get("error", {})
        raise RuntimeError(f"[{err.get('code', 'error')}] {err.get('message', payload)}")
    return payload["data"]


# ---------------------------------------------------------------------------
# Core request methods
# ---------------------------------------------------------------------------

def get(path: str, params: Optional[dict] = None) -> dict:
    r = requests.get(f"{BASE_URL}{path}", headers=_headers(), params=params)
    return _unwrap(r)


def post(path: str, json: Optional[dict] = None) -> dict:
    r = requests.post(f"{BASE_URL}{path}", headers=_headers(), json=json)
    return _unwrap(r)


def upload_to_s3(presigned_url: str, file_bytes: bytes, content_type: str) -> None:
    """PUT file bytes to a presigned S3 URL (no auth headers needed)."""
    r = requests.put(presigned_url, data=file_bytes, headers={"Content-Type": content_type})
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------

_CONTENT_TYPES = {
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "pdf": "application/pdf",
}


def upload_file(file_path: str, file_type: str, session_id: Optional[str] = None) -> dict:
    """Read a local file, get a presigned URL, and upload to S3.

    Returns dict with: session_id, upload_id, s3_key, filename, bytes_uploaded
    """
    if file_type not in _CONTENT_TYPES:
        raise ValueError(f"file_type must be one of {list(_CONTENT_TYPES)}")

    content_type = _CONTENT_TYPES[file_type]
    filename = os.path.basename(file_path)

    with open(file_path, "rb") as fh:
        file_bytes = fh.read()

    payload: dict = {
        "filename": filename,
        "file_size": len(file_bytes),
        "file_type": file_type,
        "content_type": content_type,
    }
    if session_id:
        payload["session_id"] = session_id

    presign = post("/uploads/presigned", json=payload)
    upload_to_s3(presign["presigned_url"], file_bytes, content_type)

    print(f"  Uploaded {filename} ({len(file_bytes):,} bytes) → session {presign['session_id']}")
    return {
        "session_id": presign["session_id"],
        "upload_id": presign.get("upload_id", ""),
        "s3_key": presign["s3_key"],
        "filename": filename,
        "bytes_uploaded": len(file_bytes),
    }


def confirm_upload(
    session_id: str,
    s3_key: str,
    filename: str,
    instructions: str = "",
) -> dict:
    """Verify the upload and detect any matching prior configs.

    If no strong config match is found (score < 0.85) an AI interview is
    auto-started and conversation_id is included in the response.

    instructions: Optional natural-language description of what to validate.
      When provided, the AI reads the table + instructions and generates a
      config directly (no Q&A). Response includes instructions_mode=True.
      Config generation and the 3-row preview are free; full validation is
      charged at approve_validation.
    """
    payload: dict = {"session_id": session_id, "s3_key": s3_key, "filename": filename}
    if instructions:
        payload["instructions"] = instructions
    return post("/uploads/confirm", json=payload)


# ---------------------------------------------------------------------------
# Conversation helpers
# ---------------------------------------------------------------------------

def poll_conversation(
    conversation_id: str,
    session_id: str,
    *,
    timeout: int = 900,
    interval: int = CONV_INTERVAL,
) -> dict:
    """Poll until the conversation needs a reply or finishes.

    Returns when:
      - user_reply_needed=True  → AI asked a question
      - trigger_execution=True  → AI approved execution, preview auto-queued
      - status is not processing/queued/in_progress
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = get(f"/conversations/{conversation_id}", params={"session_id": session_id})
        status = data.get("status", "processing")
        if data.get("user_reply_needed") or data.get("trigger_execution"):
            return data
        if status not in ("processing", "queued", "in_progress"):
            return data
        print(f"  Conversation processing... (status={status})")
        time.sleep(interval)
    raise TimeoutError(f"Conversation timed out after {timeout}s")


def drive_interview(conversation_id: str, session_id: str) -> None:
    """Interactively drive an upload interview or table-maker conversation.

    Prints AI messages and prompts user for replies until trigger_execution.
    """
    while True:
        data = poll_conversation(conversation_id, session_id)
        if data.get("trigger_execution"):
            print("  Interview complete — preview is auto-queued.")
            return
        if data.get("user_reply_needed"):
            ai_msg = data.get("last_ai_message", "")
            # last_ai_message may be a JSON string
            if isinstance(ai_msg, str) and ai_msg.startswith("{"):
                import json
                try:
                    parsed = json.loads(ai_msg)
                    ai_msg = parsed.get("ai_message") or parsed.get("content") or ai_msg
                except Exception:
                    pass
            print(f"\n  AI: {ai_msg}")
            reply = input("  Your reply: ").strip()
            if reply:
                post(f"/conversations/{conversation_id}/message", json={
                    "session_id": session_id,
                    "message": reply,
                })


# ---------------------------------------------------------------------------
# Job helpers
# ---------------------------------------------------------------------------

def poll_job(
    job_id: str,
    *,
    terminal: tuple = ("preview_complete", "completed", "failed"),
    timeout: int = 1800,
    interval: int = POLL_INTERVAL,
) -> dict:
    """Poll a job until it reaches a terminal status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = get(f"/jobs/{job_id}")
        status = data.get("status", "unknown")
        pct = data.get("progress_percent", 0)
        step = data.get("current_step", "")
        print(f"  [{status}] {step} ({pct}%)")
        if status in terminal:
            return data
        time.sleep(interval)
    raise TimeoutError(f"Job {job_id} did not reach {terminal} within {timeout}s")


def approve_and_wait(job_id: str, cost_usd: float) -> dict:
    """Approve full validation and wait for completion.

    This charges your account the cost_usd amount.
    """
    print(f"\n  Approving full validation (${cost_usd:.2f}) for job {job_id}...")
    post(f"/jobs/{job_id}/validate", json={"approved_cost_usd": cost_usd})
    print("  Approved. Waiting for full validation...")
    return poll_job(job_id, terminal=("completed", "failed"), timeout=3600)


def get_results(job_id: str) -> dict:
    """Fetch download URLs and inline metadata for a completed job.

    Response includes:
      results.download_url         — presigned URL for the enriched Excel (.xlsx)
      results.interactive_viewer_url — web viewer (user must be logged in to see it)
      results.metadata_url         — presigned URL for table_metadata.json (AI-readable,
                                     contains all rows with _row_key, confidence, citations)
    """
    return get(f"/jobs/{job_id}/results")


def fetch_table_metadata(metadata_url: str) -> dict:
    """Download and parse table_metadata.json from a presigned S3 URL.

    table_metadata.json is the recommended way for AI agents to consume results:
      - rows[].row_key           — stable SHA-256 identifier linking to the markdown table
      - rows[].cells[col].full_value        — validated value
      - rows[].cells[col].confidence        — HIGH / MEDIUM / LOW / ID
      - rows[].cells[col].comment.validator_explanation — reasoning
      - rows[].cells[col].comment.key_citation          — top source
      - rows[].cells[col].comment.sources[]             — all sources with URLs

    Recommended agent workflow:
      1. Survey the inline preview_table (markdown) from the preview_complete status.
      2. After full validation, fetch metadata_url → parse rows with row_key.
      3. Use _row_key to cross-reference rows between the markdown table and citations.
      4. For human consumption: share interactive_viewer_url (requires login) or download_url.
    """
    import json as _json
    r = requests.get(metadata_url, timeout=60)
    r.raise_for_status()
    return _json.loads(r.content)


def get_balance() -> dict:
    """Return current credit balance and this-month usage."""
    return get("/account/balance")
