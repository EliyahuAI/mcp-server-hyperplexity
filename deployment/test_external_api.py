#!/usr/bin/env python3
"""
End-to-end test for the External API.

Workflow:
  1. Resolve the API URL (--url override, or discover from AWS API Gateway)
  2. Create a fresh int-tier API key for eliyahu@eliyahu.ai
  3. Smoke-test auth with GET /v1/account/balance
  4. Main flow: upload → confirm_upload (instructions mode) → wait preview_complete
               → approve → wait completed → save results
  5. Additional tests (non-fatal):
       - confirm_upload auto-match (config reuse → preview_queued=True)
       - reference check text (two-phase flow)
       - reference check PDF
       - table maker conversation
       - update table
       - refine config
       - below-minimum table (2 rows)
       - below-minimum reference check (2 claims)

Usage:
    # Use the hardcoded dev URL (no AWS credentials needed for URL discovery):
    python deployment/test_external_api.py

    # Discover URL from AWS API Gateway (requires boto3 + AWS credentials):
    python deployment/test_external_api.py --env dev

    # Override URL explicitly:
    python deployment/test_external_api.py --url https://07w4n09m95.execute-api.us-east-1.amazonaws.com/v1

    # Stop after preview (skip full validation and additional tests):
    python deployment/test_external_api.py --preview-only

Requirements: boto3, requests, AWS credentials configured (only needed for URL discovery)
"""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = "us-east-1"
EMAIL = "eliyahu@eliyahu.ai"
DEMO_FILE = Path(__file__).parent.parent / "mcp" / "test_data" / "demo_table.csv"
RESULTS_DIR = Path(__file__).parent / "test_results"
API_KEYS_TABLE = "perplexity-validator-api-keys"  # no env suffix — same table for all envs
SSM_PARAM = "/perplexity-validator/api-key-hmac-secret"
DISPLAY_PREFIX_LEN = 18
POLL_INTERVAL = 20   # seconds between status polls
PREVIEW_TIMEOUT = 900    # 15 minutes
FULL_TIMEOUT = 3600      # 60 minutes

# Hardcoded dev URL — use this by default so the test runs without AWS credentials.
DEV_URL = "https://07w4n09m95.execute-api.us-east-1.amazonaws.com/v1"


# ---------------------------------------------------------------------------
# Step 0: Resolve API URL
# ---------------------------------------------------------------------------

def resolve_api_url(environment: str, url_override: Optional[str]) -> str:
    """Return the API base URL, with priority: --url > DEV_URL (env=dev) > AWS discovery."""
    if url_override:
        url = url_override.rstrip("/")
        print(f"[DISCOVER] Using --url override: {url}")
        return url

    if environment == "dev":
        print(f"[DISCOVER] Using hardcoded dev URL: {DEV_URL}")
        return DEV_URL

    # For non-dev environments, discover from API Gateway
    import boto3
    from botocore.exceptions import ClientError
    resource_suffix = "" if environment == "prod" else f"-{environment}"
    api_name = f"hyperplexity-external-api{resource_suffix}"
    apigw = boto3.client("apigatewayv2", region_name=REGION)
    try:
        apis = apigw.get_apis().get("Items", [])
    except ClientError as e:
        raise RuntimeError(f"Cannot list API Gateways: {e}") from e
    for api in apis:
        if api["Name"] == api_name:
            endpoint = api["ApiEndpoint"].rstrip("/")
            print(f"[DISCOVER] Found external API: {api_name} → {endpoint}")
            return endpoint
    raise RuntimeError(
        f"External API Gateway '{api_name}' not found. "
        f"Run deployment/create_interface_package.py --deploy-external-api first."
    )


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------

def _load_hmac_secret() -> str:
    """Load HMAC secret from SSM (or API_KEY_HMAC_SECRET env var for local dev)."""
    env_val = os.environ.get("API_KEY_HMAC_SECRET")
    if env_val:
        return env_val
    import boto3
    ssm = boto3.client("ssm", region_name=REGION)
    response = ssm.get_parameter(Name=SSM_PARAM, WithDecryption=True)
    return response["Parameter"]["Value"]


def _hash_key(raw_key: str, secret: str) -> str:
    return hmac.new(secret.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


def get_or_create_api_key(environment: str) -> tuple:
    """Create a fresh int-tier test API key for EMAIL. Returns (raw_key, key_hash)."""
    import boto3
    hmac_secret = _load_hmac_secret()
    ddb = boto3.resource("dynamodb", region_name=REGION)
    table = ddb.Table(API_KEYS_TABLE)

    key_name = f"test-external-api-{environment}"
    prefix = "hpx_int_"
    random_part = secrets.token_urlsafe(30)
    raw_key = f"{prefix}{random_part}"
    key_hash = _hash_key(raw_key, hmac_secret)
    key_prefix = raw_key[:DISPLAY_PREFIX_LEN]
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "api_key_hash": key_hash,
        "key_prefix": key_prefix,
        "email": EMAIL,
        "key_name": key_name,
        "tier": "int",
        "scopes": ["validate", "account:read"],
        "rate_limit_rpm": 300,
        "rate_limit_rpd": 0,
        "created_at": now,
        "last_used_at": None,
        "expires_at": None,
        "is_active": True,
        "revoked_at": None,
        "revoked_reason": None,
        "ip_whitelist": [],
        "cors_origins": ["*"],
        "metadata": {"created_via": "test_script"},
    }
    table.put_item(Item=item)
    print(f"[API_KEY] Created new int-tier key: {key_prefix}... for {EMAIL}")
    return raw_key, key_hash


def delete_api_key(key_hash: str) -> None:
    import boto3
    ddb = boto3.resource("dynamodb", region_name=REGION)
    table = ddb.Table(API_KEYS_TABLE)
    table.delete_item(Key={"api_key_hash": key_hash})
    print(f"[CLEANUP] Deleted test API key (hash prefix: {key_hash[:12]}...)")


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

class APIClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        resp = requests.post(url, headers=self.headers, json=body, timeout=30)
        return self._check(resp)

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        return self._check(resp)

    def _check(self, resp: requests.Response) -> dict:
        try:
            data = resp.json()
        except Exception:
            resp.raise_for_status()
            return {}
        if not resp.ok or data.get("success") is False:
            print(f"[HTTP {resp.status_code}] Raw response: {json.dumps(data, indent=2)[:1000]}")
            err = data.get("error", {})
            if isinstance(err, str):
                raise RuntimeError(f"API error {resp.status_code}: {err}")
            raise RuntimeError(
                f"API error {resp.status_code}: {err.get('code')} — {err.get('message')}"
            )
        return data


# ---------------------------------------------------------------------------
# Upload helper (presigned URL + S3 PUT)
# ---------------------------------------------------------------------------

def _presign_and_upload(client: APIClient, file_path: Path, file_type: str,
                         content_type: str, session_id: Optional[str] = None) -> dict:
    """Request a presigned URL and PUT the file to S3. Returns the presigned response data."""
    payload = {
        "filename": file_path.name,
        "file_size": file_path.stat().st_size,
        "file_type": file_type,
        "content_type": content_type,
    }
    if session_id:
        payload["session_id"] = session_id
    presigned = client.post("/v1/uploads/presigned", payload)["data"]

    with open(file_path, "rb") as f:
        r = requests.put(
            presigned["presigned_url"],
            data=f,
            headers={"Content-Type": content_type},
            timeout=120,
        )
    r.raise_for_status()
    print(f"[UPLOAD] Uploaded {file_path.name} → session_id={presigned['session_id']}")
    return presigned


# ---------------------------------------------------------------------------
# Polling helper
# ---------------------------------------------------------------------------

def poll_until(client: APIClient, job_id: str, target_statuses: list[str],
               timeout: int, label: str) -> dict:
    """Poll GET /v1/jobs/{job_id} until status is one of target_statuses."""
    deadline = time.time() + timeout

    while time.time() < deadline:
        data = client.get(f"/v1/jobs/{job_id}")
        status_data = data["data"]
        status = status_data.get("status", "unknown")
        step = status_data.get("current_step", "")
        pct = status_data.get("progress_percent", 0)

        print(f"[POLL:{label}] status={status} ({pct}%) — {step}")

        if status == "failed":
            err = status_data.get("error", {})
            raise RuntimeError(f"Job failed: {err.get('message', status_data)}")

        if status in target_statuses:
            return status_data

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Timed out after {timeout}s waiting for {target_statuses}")


# ---------------------------------------------------------------------------
# Approve full validation (reads actual cost from preview data)
# ---------------------------------------------------------------------------

def approve_validation(client: APIClient, job_id: str, preview_data: dict) -> None:
    """Approve full validation using the cost from the preview_complete response."""
    cost_usd = (preview_data.get("cost_estimate") or {}).get("estimated_total_cost_usd")
    print(f"[APPROVE] Approving full validation for {job_id} (cost=${cost_usd})...")
    client.post(f"/v1/jobs/{job_id}/validate", {"approved_cost_usd": cost_usd})
    print(f"[APPROVE] Full validation queued.")


# ---------------------------------------------------------------------------
# Main flow: upload → confirm_upload (instructions) → preview → full → results
# ---------------------------------------------------------------------------

def run_main_flow(client: APIClient) -> tuple[str, dict]:
    """
    Primary test flow using confirm_upload with instructions= to bypass the interview.

    Returns (job_id, out_dir).
    """
    if not DEMO_FILE.exists():
        raise FileNotFoundError(f"Demo file not found: {DEMO_FILE}")

    # Step 1: Upload
    print("\n[1/5] Uploading demo file...")
    presigned = _presign_and_upload(client, DEMO_FILE, "csv", "text/csv")
    session_id = presigned["session_id"]
    s3_key = presigned["s3_key"]

    # Step 2: confirm_upload with instructions= (bypasses interview)
    print("\n[2/5] Confirming upload (instructions mode — no interview)...")
    confirm = client.post("/v1/uploads/confirm", {
        "session_id": session_id,
        "s3_key": s3_key,
        "filename": DEMO_FILE.name,
        "instructions": (
            "This table lists stock tickers. Validate the company name and "
            "current stock price for each ticker. Use financial data sources."
        ),
    })["data"]

    # The response should have interview_auto_started=True (instructions mode)
    # OR preview_queued=True (if a matching config was found)
    preview_queued = confirm.get("preview_queued", False)
    instructions_mode = confirm.get("instructions_mode", False)
    job_id = confirm.get("job_id", session_id)

    if preview_queued:
        print(f"  Config match found — preview auto-queued (job_id={job_id})")
    elif instructions_mode:
        print(f"  Instructions mode — config generation + preview in progress (session_id={session_id})")
        job_id = session_id
    else:
        # Fallback: neither path triggered; something unexpected
        print(f"  confirm_upload response: {json.dumps(confirm, indent=2)[:500]}")
        raise RuntimeError("confirm_upload did not return preview_queued or instructions_mode")

    # Step 3: Wait for preview_complete
    print(f"\n[3/5] Waiting for preview (job={job_id}, timeout={PREVIEW_TIMEOUT}s)...")
    preview_data = poll_until(client, job_id, ["preview_complete"],
                               timeout=PREVIEW_TIMEOUT, label="PREVIEW")
    cost = (preview_data.get("cost_estimate") or {}).get("estimated_total_cost_usd", "?")
    config_id = preview_data.get("config_id")
    print(f"  Preview complete — cost=${cost}, config_id={config_id}")

    # Verify inline preview_table is present (Issue #9 fix)
    preview_table = preview_data.get("preview_table")
    if preview_table:
        print(f"  preview_table present ({len(preview_table)} chars) ✓")
    else:
        print(f"  WARNING: preview_table missing from preview_complete response")

    # Step 4: Approve
    print(f"\n[4/5] Approving full validation...")
    approve_validation(client, job_id, preview_data)

    # Step 5: Wait for completed
    print(f"\n[5/5] Waiting for full validation (timeout={FULL_TIMEOUT}s)...")
    poll_until(client, job_id, ["completed"], timeout=FULL_TIMEOUT, label="FULL")
    print(f"  Validation complete!")

    # Save results
    out_dir = save_results(client, job_id, "main")
    return job_id, out_dir


# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------

def save_results(client: APIClient, job_id: str, label: str) -> Path:
    """Fetch and download results for a completed job."""
    print(f"[RESULTS] Fetching results for {job_id}...")
    data = client.get(f"/v1/jobs/{job_id}/results")
    results = data["data"]

    result_info  = results.get("results") or {}
    job_info     = results.get("job_info") or {}
    summary      = results.get("summary", {})
    download_url = result_info.get("download_url")
    file_format  = result_info.get("file_format", "unknown")
    viewer_url   = result_info.get("interactive_viewer_url")
    metadata_url = result_info.get("metadata_url")
    receipt_url  = result_info.get("receipt_url")

    print(f"[RESULTS] table={job_info.get('input_table_name')}  "
          f"config={job_info.get('configuration_id')}  "
          f"rows={summary.get('rows_processed')}  "
          f"cost=${summary.get('cost_usd')}")
    if viewer_url:
        print(f"[RESULTS] Viewer → {viewer_url}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RESULTS_DIR / f"{label}_{ts}_{job_id[:20]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "summary.json", "w") as f:
        json.dump(results, f, indent=2)

    def _dl(url: str, dest: Path, dlabel: str) -> bool:
        for attempt in range(10):
            resp = requests.get(url, timeout=120)
            if resp.status_code != 404:
                break
            wait = 5 if attempt < 6 else 10
            print(f"[RESULTS] {dlabel} not ready (attempt {attempt+1}), retrying in {wait}s...")
            time.sleep(wait)
        if resp.status_code == 404:
            print(f"[RESULTS] {dlabel} still unavailable after retries")
            return False
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(resp.content)
        print(f"[RESULTS] Saved {dlabel} ({len(resp.content)/1024:.1f} KB) → {dest.name}")
        return True

    if download_url:
        table_name = job_info.get("input_table_name") or "results"
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in table_name)
        if file_format == "xlsx":
            _dl(download_url, out_dir / f"{safe_name}_enhanced.xlsx", "Excel results")
        elif file_format == "zip":
            zip_path = out_dir / "results.zip"
            if _dl(download_url, zip_path, "results.zip"):
                try:
                    with zipfile.ZipFile(zip_path) as zf:
                        zf.extractall(out_dir)
                except zipfile.BadZipFile:
                    print(f"[RESULTS] (not a valid zip)")
        else:
            _dl(download_url, out_dir / "results.bin", f"results ({file_format})")

    if metadata_url:
        _dl(metadata_url, out_dir / "table_metadata.json", "table_metadata.json")
    if receipt_url:
        receipt_ext = receipt_url.split("?")[0].rsplit(".", 1)[-1] if "." in receipt_url.split("?")[0] else "pdf"
        _dl(receipt_url, out_dir / f"receipt.{receipt_ext}", f"receipt.{receipt_ext}")

    print(f"[RESULTS] All results saved to: {out_dir}")
    return out_dir


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------

def test_confirm_upload_auto_match(client: APIClient, completed_job_id: str) -> None:
    """
    Test confirm_upload config auto-match path.

    Upload the same demo file again — confirm_upload should detect the config
    match (score >= 0.85) and auto-queue the preview, returning preview_queued=True.
    Verifies the new behavior: no create_job() call needed.
    """
    print("\n[TEST] confirm_upload auto-match — uploading same file again...")
    presigned = _presign_and_upload(client, DEMO_FILE, "csv", "text/csv")
    confirm = client.post("/v1/uploads/confirm", {
        "session_id": presigned["session_id"],
        "s3_key": presigned["s3_key"],
        "filename": DEMO_FILE.name,
    })["data"]

    preview_queued = confirm.get("preview_queued", False)
    job_id = confirm.get("job_id", presigned["session_id"])
    best_score = (confirm.get("matches") or [{}])[0].get("match_score", 0) if confirm.get("matches") else 0

    assert preview_queued, (
        f"Expected preview_queued=True for re-upload of same file (best_score={best_score}). "
        f"Response: {json.dumps(confirm, indent=2)[:500]}"
    )
    print(f"[TEST] confirm_upload auto-match — [SUCCESS] "
          f"preview_queued=True, match_score={best_score:.2f}, job_id={job_id}")


def test_reference_check_text(client: APIClient) -> None:
    """
    Test reference check with inline text — two-phase flow.

    Phase 1 (claim extraction, free): submit → poll until preview_complete.
    Phase 2 (validation, charged): approve → poll until completed → fetch results.
    """
    print("\n[TEST] reference-check (text) — two-phase flow...")

    sample_text = (
        "Apple was founded in 1976 by Steve Jobs, Steve Wozniak, and Ronald Wayne. "
        "The company is headquartered in Cupertino, California. "
        "In fiscal year 2023, Apple reported annual revenue of approximately $383 billion. "
        "The iPhone was first introduced in 2007 and revolutionised the smartphone industry. "
        "Tim Cook has served as Apple's CEO since 2011."
    )

    resp = client.post("/v1/jobs/reference-check", {"text": sample_text})
    job_id = resp["data"]["job_id"]
    print(f"[TEST] reference-check — job_id={job_id}")

    # Phase 1: wait for preview_complete
    print("[TEST] reference-check — Phase 1: waiting for preview_complete...")
    preview_data = poll_until(client, job_id, ["preview_complete"],
                               timeout=PREVIEW_TIMEOUT, label="REFCHECK_P1")

    claims_summary = preview_data.get("claims_summary") or {}
    cost_usd = (preview_data.get("cost_estimate") or {}).get("estimated_total_cost_usd")
    print(f"[TEST] reference-check — Phase 1 complete: "
          f"claims={claims_summary.get('total_claims')}, cost=${cost_usd}")

    # Phase 2: approve → wait for completed
    print("[TEST] reference-check — Phase 2: approving...")
    approve_validation(client, job_id, preview_data)

    print("[TEST] reference-check — Phase 2: waiting for completed...")
    poll_until(client, job_id, ["completed"], timeout=PREVIEW_TIMEOUT, label="REFCHECK_P2")

    # Fetch reference results
    results_data = client.get(f"/v1/jobs/{job_id}/reference-results")
    dl_url = (results_data.get("data") or {}).get("results", {}).get("download_url")
    assert dl_url, "Expected download_url in reference-results response"
    print(f"[TEST] reference-check (text) — [SUCCESS] download_url present")


def test_reference_check_pdf(client: APIClient) -> None:
    """Test reference check with a PDF upload — two-phase flow."""
    print("\n[TEST] reference-check (PDF) — uploading PDF...")

    # Generate a minimal valid 1-page PDF in-memory
    import tempfile
    minimal_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>"
        b"/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 44>>stream\n"
        b"BT /F1 12 Tf 100 700 Td "
        b"(Apple was founded in 1976 in California.) Tj ET\n"
        b"endstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f\n"
        b"0000000009 00000 n\n0000000058 00000 n\n"
        b"0000000115 00000 n\n0000000266 00000 n\n"
        b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n359\n%%EOF"
    )
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(minimal_pdf)
    tmp.close()
    pdf_path = Path(tmp.name)
    print(f"[TEST] reference-check (PDF) — created minimal test PDF")

    presigned = _presign_and_upload(client, pdf_path, "pdf", "application/pdf")
    s3_key = presigned["s3_key"]

    resp = client.post("/v1/jobs/reference-check", {"s3_key": s3_key})
    job_id = resp["data"]["job_id"]
    print(f"[TEST] reference-check (PDF) — job_id={job_id}")

    # Phase 1
    preview_data = poll_until(client, job_id, ["preview_complete"],
                               timeout=PREVIEW_TIMEOUT, label="REFCHECK_PDF_P1")
    cost_usd = (preview_data.get("cost_estimate") or {}).get("estimated_total_cost_usd")
    print(f"[TEST] reference-check (PDF) — Phase 1 complete, cost=${cost_usd}")

    # Phase 2
    approve_validation(client, job_id, preview_data)
    poll_until(client, job_id, ["completed"], timeout=PREVIEW_TIMEOUT, label="REFCHECK_PDF_P2")

    results_data = client.get(f"/v1/jobs/{job_id}/reference-results")
    dl_url = (results_data.get("data") or {}).get("results", {}).get("download_url")
    assert dl_url, "Expected download_url in reference-results response"
    print(f"[TEST] reference-check (PDF) — [SUCCESS] download_url present")


def test_table_maker_conversation(client: APIClient) -> Optional[str]:
    """
    Test table maker: start conversation, auto-reply 'Confirmed', wait for
    trigger_execution, then poll the auto-queued preview to preview_complete.
    Returns the session_id (job_id) on success, or None on timeout.
    """
    print("\n[TEST] table-maker conversation — starting...")

    resp = client.post("/v1/conversations/table-maker", {
        "message": (
            "I need a table of the capital cities of the 5 largest US states by land area. "
            "Include: state name, capital city, state area in sq miles, capital population."
        ),
    })
    d = resp["data"]
    session_id = d["session_id"]
    conv_id = d.get("conversation_id")
    print(f"[TEST] table-maker — session_id={session_id}, conv_id={conv_id}")

    if not conv_id:
        print("[TEST] table-maker — no conversation_id returned, skipping")
        return None

    # Conversation loop: reply "Confirmed" to every AI question until trigger_execution
    deadline = time.time() + PREVIEW_TIMEOUT
    job_id: Optional[str] = None
    turn = 0

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        conv_resp = client.get(f"/v1/conversations/{conv_id}", params={"session_id": session_id})
        state = conv_resp["data"]
        status = state.get("status", "unknown")
        user_reply_needed = state.get("user_reply_needed", False)
        trigger_execution = state.get("trigger_execution", False)

        print(f"[TEST] table-maker [turn {turn}] status={status} "
              f"reply_needed={user_reply_needed} trigger={trigger_execution}")

        if status == "processing" and not user_reply_needed:
            continue

        if user_reply_needed:
            turn += 1
            ai_msg = state.get("last_ai_message", "")
            print(f"[TEST] table-maker — AI: {str(ai_msg)[:200]}")
            print(f"[TEST] table-maker — replying 'Confirmed' (turn {turn})")
            client.post(f"/v1/conversations/{conv_id}/message", {
                "session_id": session_id,
                "message": "Confirmed",
            })
            continue

        if trigger_execution:
            print(f"[TEST] table-maker — table design complete, preview auto-queued")
            job_id = session_id
            break

        print(f"[TEST] table-maker — unexpected state: {status}, stopping")
        break

    if not job_id:
        print(f"[TEST] table-maker — [TIMEOUT] conversation did not trigger within {PREVIEW_TIMEOUT}s")
        return None

    # Poll for preview_complete (preview was auto-queued by the backend)
    print(f"[TEST] table-maker — polling {job_id} for preview_complete...")
    try:
        preview_data = poll_until(client, job_id, ["preview_complete"],
                                   timeout=PREVIEW_TIMEOUT, label="TABLE_MAKER_PREVIEW")
        config_id = preview_data.get("config_id")
        cost = (preview_data.get("cost_estimate") or {}).get("estimated_total_cost_usd")
        print(f"[TEST] table-maker — [SUCCESS] preview_complete "
              f"config_id={config_id} cost=${cost}")
    except Exception as e:
        print(f"[TEST] table-maker — preview poll failed (non-fatal): {e}")

    return job_id


def test_update_table(client: APIClient, completed_job_id: str) -> Optional[str]:
    """
    Test POST /v1/jobs/update-table — re-validate the enhanced output of a completed job.
    Full cycle: create → preview_complete → approve → completed → save results.
    """
    print(f"\n[TEST] update-table — creating update job from {completed_job_id}...")

    resp = client.post("/v1/jobs/update-table", {"source_job_id": completed_job_id})
    data = resp["data"]
    new_job_id = data["job_id"]
    source_returned = data.get("source_job_id")
    assert source_returned == completed_job_id, (
        f"source_job_id mismatch: expected {completed_job_id}, got {source_returned}"
    )
    print(f"[TEST] update-table — new_job_id={new_job_id}")

    preview_data = poll_until(client, new_job_id, ["preview_complete"],
                               timeout=PREVIEW_TIMEOUT, label="UPDATE_PREVIEW")
    config_id = preview_data.get("config_id")
    assert config_id, "Expected config_id in preview_complete response"
    cost = (preview_data.get("cost_estimate") or {}).get("estimated_total_cost_usd")
    print(f"[TEST] update-table — preview_complete: config_id={config_id}, cost=${cost}")

    approve_validation(client, new_job_id, preview_data)
    poll_until(client, new_job_id, ["completed"], timeout=FULL_TIMEOUT, label="UPDATE_FULL")

    out_dir = save_results(client, new_job_id, "update_table")
    print(f"[TEST] update-table — [SUCCESS] results saved to {out_dir}")
    return new_job_id


def test_refine_config(client: APIClient, job_id: str) -> None:
    """
    Test POST /v1/conversations/{conv_id}/refine-config — submit a refinement,
    poll until trigger_execution=True, verify a new config version is ready.
    """
    print(f"\n[TEST] refine-config — submitting for session {job_id}...")

    conv_id = f"refine_{job_id}"
    resp = client.post(f"/v1/conversations/{conv_id}/refine-config", {
        "session_id": job_id,
        "instructions": (
            "Add a brief one-sentence analyst commentary column that summarises "
            "the key finding for each row."
        ),
    })
    data = resp["data"]
    returned_conv_id = data.get("conversation_id", conv_id)
    assert data.get("status") == "processing", (
        f"Expected status='processing', got: {data.get('status')}"
    )
    print(f"[TEST] refine-config — queued: conv_id={returned_conv_id}")

    deadline = time.time() + PREVIEW_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        state_resp = client.get(f"/v1/conversations/{returned_conv_id}",
                                params={"session_id": job_id})
        state = state_resp["data"]
        status = state.get("status", "unknown")
        trigger = state.get("trigger_execution", False)
        print(f"[TEST] refine-config — status={status} trigger_execution={trigger}")

        if trigger or status == "completed":
            next_step = state.get("next_step") or {}
            new_config_id = (next_step.get("body") or {}).get("config_id")
            print(f"[TEST] refine-config — [SUCCESS] new config ready: config_id={new_config_id}")
            return

        if status not in ("processing",):
            print(f"[TEST] refine-config — unexpected state={status}, stopping")
            return

    print(f"[TEST] refine-config — [TIMEOUT]")


def test_below_minimum_table(client: APIClient) -> None:
    """
    Test upload and validation of a table with only 2 data rows (below the 4-row minimum).

    The guide warns "may produce low-quality results" — this test records what actually happens:
    error, warning, or silent proceed.
    """
    print("\n[TEST] below-minimum table — uploading 2-row CSV...")

    import io
    csv_content = (
        "Company,Founded,HQ City\n"
        "Apple,1976,Cupertino\n"
        "Microsoft,1975,Redmond\n"
    ).encode()

    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    tmp.write(csv_content)
    tmp.close()
    csv_path = Path(tmp.name)

    try:
        presigned = _presign_and_upload(client, csv_path, "csv", "text/csv")
        session_id = presigned["session_id"]
        s3_key = presigned["s3_key"]
        print(f"[TEST] below-min table — upload OK, session_id={session_id}")

        try:
            confirm = client.post("/v1/uploads/confirm", {
                "session_id": session_id,
                "s3_key": s3_key,
                "filename": "tiny_table.csv",
                "instructions": (
                    "This table lists tech companies. "
                    "Validate founding year and HQ city."
                ),
            })["data"]
            print(f"[TEST] below-min table — confirm_upload OK: "
                  f"preview_queued={confirm.get('preview_queued')}, "
                  f"interview_auto_started={confirm.get('interview_auto_started')}")
        except RuntimeError as e:
            print(f"[TEST] below-min table — confirm_upload returned error (recording): {e}")
            return

        job_id = confirm.get("job_id", session_id)
        try:
            preview_data = poll_until(client, job_id, ["preview_complete", "failed"],
                                       timeout=PREVIEW_TIMEOUT, label="BELOW_MIN_TABLE")
            status = preview_data.get("status")
            if status == "failed":
                print(f"[TEST] below-min table — job failed: "
                      f"{preview_data.get('error', {}).get('message')}")
            else:
                cost = (preview_data.get("cost_estimate") or {}).get("estimated_total_cost_usd")
                print(f"[TEST] below-min table — reached preview_complete (cost=${cost}) — "
                      f"proceeded without error despite 2 rows")
        except Exception as e:
            print(f"[TEST] below-min table — poll error (recording): {e}")

    finally:
        csv_path.unlink(missing_ok=True)

    print(f"[TEST] below-min table — [RECORDED] (see output above for actual behavior)")


def test_below_minimum_reference_check(client: APIClient) -> None:
    """
    Test reference check with only 2 factual claims (below the 4-claim minimum).

    Records whether the API errors, warns, or proceeds silently.
    """
    print("\n[TEST] below-minimum reference check — submitting 2-claim text...")

    text = "The Eiffel Tower is located in Paris. It was completed in 1889."

    try:
        resp = client.post("/v1/jobs/reference-check", {"text": text})
        job_id = resp["data"]["job_id"]
        print(f"[TEST] below-min refcheck — submitted OK, job_id={job_id}")
    except RuntimeError as e:
        print(f"[TEST] below-min refcheck — submission returned error (recording): {e}")
        return

    try:
        preview_data = poll_until(client, job_id, ["preview_complete", "failed"],
                                   timeout=PREVIEW_TIMEOUT, label="BELOW_MIN_REFCHECK")
        status = preview_data.get("status")
        if status == "failed":
            print(f"[TEST] below-min refcheck — job failed: "
                  f"{preview_data.get('error', {}).get('message')}")
        else:
            claims = (preview_data.get("claims_summary") or {}).get("total_claims")
            cost = (preview_data.get("cost_estimate") or {}).get("estimated_total_cost_usd")
            print(f"[TEST] below-min refcheck — reached preview_complete "
                  f"(claims={claims}, cost=${cost}) — proceeded without error despite 2 claims")
    except Exception as e:
        print(f"[TEST] below-min refcheck — poll error (recording): {e}")

    print(f"[TEST] below-min refcheck — [RECORDED] (see output above for actual behavior)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="E2E test for the External API")
    parser.add_argument("--env", default="dev", choices=["dev", "test", "staging", "prod"],
                        help="Deployment environment (default: dev)")
    parser.add_argument("--url", default=None,
                        help=f"Override the API base URL (default for dev: {DEV_URL})")
    parser.add_argument("--preview-only", action="store_true",
                        help="Stop after preview completes (skip full validation and extra tests)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"External API E2E Test  — env: {args.env}")
    print("=" * 60)

    # 0. Resolve API URL
    base_url = resolve_api_url(args.env, args.url)

    # 1. Get / create API key
    api_key, api_key_hash = get_or_create_api_key(args.env)
    client = APIClient(base_url, api_key)

    # Smoke-test auth
    print(f"\n[AUTH] GET /v1/account/balance...")
    balance_data = client.get("/v1/account/balance")
    balance = (balance_data.get("data") or {}).get("balance_usd", "?")
    print(f"[AUTH] OK — {EMAIL}: ${balance}")

    try:
        # 2–6. Main flow
        job_id, out_dir = run_main_flow(client)

        if args.preview_only:
            print("\n[DONE] --preview-only set; stopping after main flow.")
            return

        # Additional tests (non-fatal)
        for label, fn, kwargs in [
            ("confirm_upload auto-match",       test_confirm_upload_auto_match,       {"completed_job_id": job_id}),
            ("update-table",                    test_update_table,                    {"completed_job_id": job_id}),
            ("refine-config",                   test_refine_config,                   {"job_id": job_id}),
            ("reference-check (text)",          test_reference_check_text,            {}),
            ("reference-check (PDF)",           test_reference_check_pdf,             {}),
            ("table-maker conversation",        test_table_maker_conversation,        {}),
            ("below-minimum table",             test_below_minimum_table,             {}),
            ("below-minimum reference-check",   test_below_minimum_reference_check,   {}),
        ]:
            try:
                fn(client, **kwargs)
            except Exception as e:
                print(f"[WARN] {label} failed (non-fatal): {e}")

        print("\n" + "=" * 60)
        print(f"[SUCCESS] All tests complete!")
        print(f"          Job ID  : {job_id}")
        print(f"          Results : {out_dir}")
        print("=" * 60)

    finally:
        try:
            delete_api_key(api_key_hash)
        except Exception as e:
            print(f"[WARN] Could not delete test API key: {e}")


if __name__ == "__main__":
    main()
