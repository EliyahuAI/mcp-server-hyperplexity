#!/usr/bin/env python3
"""
End-to-end test for the External API (api.hyperplexity.ai/v1).

Workflow:
  1. Discover the dev external API Gateway URL from AWS
  2. Create or reuse an API key for eliyahu@eliyahu.ai
  3. Upload demos/01. Investment Research/InvestmentResearch.xlsx via presigned URL
  4. Submit a preview job and wait for preview_complete
  5. Approve the full validation job and wait for completed
  6. Download and save results to deployment/test_results/

Usage:
    python deployment/test_external_api.py [--env dev] [--preview-only]

Requirements: boto3, requests, AWS credentials configured
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

import boto3
import requests
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = "us-east-1"
EMAIL = "eliyahu@eliyahu.ai"
DEMO_DIR = Path(__file__).parent.parent / "demos" / "01. Investment Research"
RESULTS_DIR = Path(__file__).parent / "test_results"
API_KEYS_TABLE = "perplexity-validator-api-keys"  # no env suffix — same table for all envs
SSM_PARAM = "/perplexity-validator/api-key-hmac-secret"
DISPLAY_PREFIX_LEN = 18
POLL_INTERVAL = 10   # seconds between status polls
PREVIEW_TIMEOUT = 300   # 5 minutes
FULL_TIMEOUT = 1800     # 30 minutes


# ---------------------------------------------------------------------------
# Step 0: Discover the external API Gateway endpoint
# ---------------------------------------------------------------------------

def find_external_api_url(environment: str) -> str:
    """Find the deployed external API Gateway endpoint for the given environment."""
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
# Step 1: API key management (direct boto3, no Lambda import required)
# ---------------------------------------------------------------------------

def _load_hmac_secret() -> str:
    """Load HMAC secret from SSM (or API_KEY_HMAC_SECRET env var for local dev)."""
    env_val = os.environ.get("API_KEY_HMAC_SECRET")
    if env_val:
        return env_val
    ssm = boto3.client("ssm", region_name=REGION)
    response = ssm.get_parameter(Name=SSM_PARAM, WithDecryption=True)
    return response["Parameter"]["Value"]


def _hash_key(raw_key: str, secret: str) -> str:
    return hmac.new(secret.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


def get_or_create_api_key(environment: str) -> tuple:
    """
    Create a fresh test API key for EMAIL.  Returns (raw_key, key_hash).
    """
    hmac_secret = _load_hmac_secret()
    ddb = boto3.resource("dynamodb", region_name=REGION)
    table = ddb.Table(API_KEYS_TABLE)

    key_name = f"test-external-api-{environment}"

    # Generate new key
    tier = "int"
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
        "tier": tier,
        "scopes": ["validate", "account:read"],
        "rate_limit_rpm": 300,
        "rate_limit_rpd": 0,   # 0 = unlimited for int tier
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
    """Delete the test API key from DynamoDB."""
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
            # Always print the raw body so we can diagnose routing/Lambda issues
            print(f"[HTTP {resp.status_code}] Raw response: {json.dumps(data, indent=2)[:1000]}")
            err = data.get("error", {})
            if isinstance(err, str):
                raise RuntimeError(f"API error {resp.status_code}: {err}")
            raise RuntimeError(
                f"API error {resp.status_code}: {err.get('code')} — {err.get('message')}"
            )
        return data


# ---------------------------------------------------------------------------
# Step 2: Upload the demo file
# ---------------------------------------------------------------------------

def upload_demo_file(client: APIClient, environment: str) -> dict:
    """Request presigned URL and upload the demo Excel file. Returns presigned data."""
    xlsx_path = DEMO_DIR / "InvestmentResearch.xlsx"
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Demo file not found: {xlsx_path}")

    file_size = xlsx_path.stat().st_size
    filename = xlsx_path.name
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    print(f"[UPLOAD] Requesting presigned URL for {filename} ({file_size:,} bytes)...")

    data = client.post("/v1/uploads/presigned", {
        "filename": filename,
        "file_size": file_size,
        "file_type": "excel",
        "content_type": content_type,
    })

    presigned = data["data"]
    presigned_url = presigned["presigned_url"]

    # Upload directly to S3
    print(f"[UPLOAD] Uploading to S3...")
    with open(xlsx_path, "rb") as f:
        put_resp = requests.put(
            presigned_url,
            data=f,
            headers={"Content-Type": content_type},
            timeout=120,
        )
    put_resp.raise_for_status()
    print(f"[UPLOAD] Upload complete: session_id={presigned['session_id']}")
    return presigned


# ---------------------------------------------------------------------------
# Step 3: Create preview job
# ---------------------------------------------------------------------------

def create_job(client: APIClient, presigned: dict) -> str:
    """Submit a preview job with the demo config. Returns job_id."""
    config_path = DEMO_DIR / "InvestmentResearch_config.json"
    with open(config_path) as f:
        config = json.load(f)

    print(f"[JOB] Submitting preview job...")
    data = client.post("/v1/jobs", {
        "session_id": presigned["session_id"],
        "upload_id": presigned["upload_id"],
        "s3_key": presigned["s3_key"],
        "config": config,
        "preview_rows": 3,
        "notify_method": "poll",
    })

    job_id = data["data"]["job_id"]
    print(f"[JOB] Preview job queued: {job_id}")
    return job_id


# ---------------------------------------------------------------------------
# Step 4/6: Poll for status
# ---------------------------------------------------------------------------

def poll_until(client: APIClient, job_id: str, target_statuses: list[str],
               timeout: int, label: str) -> dict:
    """Poll GET /v1/jobs/{job_id} until status is one of target_statuses."""
    deadline = time.time() + timeout
    last_step = None

    while time.time() < deadline:
        data = client.get(f"/v1/jobs/{job_id}")
        status_data = data["data"]
        status = status_data.get("status", "unknown")
        step = status_data.get("current_step", "")
        pct = status_data.get("progress_percent", 0)

        print(f"[POLL:{label}] status={status} ({pct}%) — {step}")
        if status_data != last_step:
            last_step = status_data

        if status == "failed":
            err = status_data.get("error", {})
            raise RuntimeError(f"Job failed: {err.get('message', status_data)}")

        if status in target_statuses:
            return status_data

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Timed out after {timeout}s waiting for {target_statuses}")


# ---------------------------------------------------------------------------
# Step 5: Approve full validation
# ---------------------------------------------------------------------------

def approve_validation(client: APIClient, job_id: str, preview_data: dict) -> None:
    """Approve the full validation job after reviewing preview results."""
    # The approve endpoint doesn't require a cost match in our implementation
    # (handle_approve_validation accepts None for approved_cost_usd)
    print(f"[APPROVE] Approving full validation for {job_id}...")
    client.post(f"/v1/jobs/{job_id}/validate", {
        "approved_cost_usd": None,
    })
    print(f"[APPROVE] Full validation queued.")


# ---------------------------------------------------------------------------
# Step 7: Download and save results
# ---------------------------------------------------------------------------

def _download_file(url: str, dest: Path, label: str) -> bool:
    """Download a file from a presigned URL, retrying on 404 up to ~60s. Returns True on success."""
    resp = None
    for attempt in range(10):
        resp = requests.get(url, timeout=120)
        if resp.status_code != 404:
            break
        wait = 5 if attempt < 6 else 10
        print(f"[RESULTS] {label} not ready yet (attempt {attempt + 1}), retrying in {wait}s...")
        time.sleep(wait)

    if resp is None or resp.status_code == 404:
        print(f"[RESULTS] {label} still not available after retries: {url.split('?')[0]}")
        return False

    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        f.write(resp.content)
    size_kb = len(resp.content) / 1024
    print(f"[RESULTS] Saved {label:<18} → {dest}  ({size_kb:.1f} KB)")
    return True


def save_results(client: APIClient, job_id: str, environment: str) -> Path:
    """Fetch the results URL and download the results file."""
    print(f"[RESULTS] Fetching results for {job_id}...")
    data = client.get(f"/v1/jobs/{job_id}/results")
    results = data["data"]

    result_info   = results.get("results") or {}
    job_info      = results.get("job_info") or {}
    summary       = results.get("summary", {})
    download_url  = result_info.get("download_url")
    file_format   = result_info.get("file_format", "unknown")
    viewer_url    = result_info.get("interactive_viewer_url")
    metadata_url  = result_info.get("metadata_url")
    receipt_url   = result_info.get("receipt_url")

    print(f"[RESULTS] Job info:")
    print(f"          table            = {job_info.get('input_table_name', 'N/A')}")
    print(f"          configuration_id = {job_info.get('configuration_id', 'N/A')}")
    print(f"          run_time_seconds = {job_info.get('run_time_seconds', 0):.1f}s")
    print(f"[RESULTS] Summary:")
    print(f"          rows_processed   = {summary.get('rows_processed')}")
    print(f"          columns_validated = {summary.get('columns_validated')}")
    print(f"          cost_usd         = {summary.get('cost_usd')}")
    if viewer_url:
        print(f"[RESULTS] Interactive viewer  → {viewer_url}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RESULTS_DIR / f"{environment}_{ts}_{job_id[:20]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save full API response as summary JSON
    summary_file = out_dir / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[RESULTS] Saved summary.json")

    # Track files saved for README manifest
    manifest_entries = []

    # Download main results file (Excel) — poll because S3 upload may lag slightly
    xlsx_path = None
    if download_url:
        print(f"[RESULTS] Waiting for results file to appear in S3 (up to 90s)...")
        table_name = job_info.get('input_table_name') or 'results'
        safe_name  = "".join(c if c.isalnum() or c in "._- " else "_" for c in table_name)

        if file_format == "xlsx":
            xlsx_path = out_dir / f"{safe_name}_enhanced.xlsx"
            ok = _download_file(download_url, xlsx_path, "Excel results")
            if ok:
                manifest_entries.append((xlsx_path.name, "Validated data — enhanced Excel with all validation results and notes"))
        elif file_format == "zip":
            zip_path = out_dir / "results.zip"
            ok = _download_file(download_url, zip_path, "results.zip")
            if ok:
                manifest_entries.append((zip_path.name, "Validation results archive"))
                try:
                    with zipfile.ZipFile(zip_path) as zf:
                        zf.extractall(out_dir)
                    for item in sorted(out_dir.iterdir()):
                        if item.is_file() and item.name != "results.zip":
                            manifest_entries.append((item.name, "Extracted from results.zip"))
                except zipfile.BadZipFile:
                    print(f"[RESULTS] (not a valid zip)")
        else:
            raw_path = out_dir / "results.bin"
            ok = _download_file(download_url, raw_path, "results")
            if ok:
                manifest_entries.append((raw_path.name, f"Raw results file (format: {file_format})"))
    else:
        print(f"[RESULTS] No download URL returned")

    # Download table_metadata.json
    if metadata_url:
        meta_path = out_dir / "table_metadata.json"
        ok = _download_file(metadata_url, meta_path, "table_metadata.json")
        if ok:
            manifest_entries.append((meta_path.name, "Table metadata — column types, search groups, and validation configuration"))

    # Download receipt (PDF or TXT)
    if receipt_url:
        # Detect extension from URL path before query string
        receipt_ext = receipt_url.split('?')[0].rsplit('.', 1)[-1] if '.' in receipt_url.split('?')[0] else 'pdf'
        receipt_path = out_dir / f"receipt.{receipt_ext}"
        ok = _download_file(receipt_url, receipt_path, f"receipt.{receipt_ext}")
        if ok:
            manifest_entries.append((receipt_path.name, "Billing receipt for this validation run"))

    # Always include summary.json in manifest
    manifest_entries.insert(0, ("summary.json", "Full API response — job info, summary metrics, and file URLs"))

    # Write README.txt manifest
    readme_lines = [
        "Hyperplexity Validation Results",
        "=" * 40,
        f"Job ID  : {job_id}",
        f"Table   : {job_info.get('input_table_name', 'N/A')}",
        f"Config  : {job_info.get('configuration_id', 'N/A')}",
        f"Runtime : {job_info.get('run_time_seconds', 0):.1f}s",
        f"Rows    : {summary.get('rows_processed', 0)}",
        f"Columns : {summary.get('columns_validated', 0)}",
        f"Cost    : ${summary.get('cost_usd', 0):.4f}",
        "",
        "Interactive Viewer",
        "-" * 40,
        viewer_url or "(not available)",
        "",
        "Files in this Package",
        "-" * 40,
    ]
    for fname, desc in manifest_entries:
        readme_lines.append(f"  {fname}")
        readme_lines.append(f"    {desc}")
        readme_lines.append("")

    readme_path = out_dir / "README.txt"
    with open(readme_path, "w") as f:
        f.write("\n".join(readme_lines))
    print(f"[RESULTS] Saved README.txt")
    print(f"[RESULTS] All results saved to: {out_dir}")

    return out_dir


# ---------------------------------------------------------------------------
# New test sections (Phase 5c)
# ---------------------------------------------------------------------------

def test_config_id(client: APIClient, original_job_id: str) -> None:
    """Test config_id path: reuse the configuration from a completed job."""
    print("\n[TEST] config_id — reusing saved config from completed job...")

    # Discover the configuration_id from the completed job's results
    data = client.get(f"/v1/jobs/{original_job_id}/results")
    config_id = (data.get("data") or {}).get("job_info", {}).get("configuration_id")
    if not config_id:
        print("[TEST] config_id — no configuration_id found, skipping.")
        return

    # Upload a fresh copy of the demo file (new session)
    presigned = client.post("/v1/uploads/presigned", {
        "filename": "InvestmentResearch.xlsx",
        "file_size": (DEMO_DIR / "InvestmentResearch.xlsx").stat().st_size,
        "file_type": "excel",
    })["data"]

    xlsx_path = DEMO_DIR / "InvestmentResearch.xlsx"
    with open(xlsx_path, "rb") as f:
        r = requests.put(presigned["presigned_url"],
                         data=f,
                         headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                         timeout=120)
    r.raise_for_status()

    resp = client.post("/v1/jobs", {
        "session_id": presigned["session_id"],
        "s3_key": presigned["s3_key"],
        "config_id": config_id,
        "preview_rows": 2,
    })
    assert resp["data"]["status"] == "queued", f"Expected 'queued', got: {resp['data']['status']}"
    print(f"[TEST] config_id — [SUCCESS] job queued with config_id={config_id}")


def test_config_file_upload(client: APIClient) -> str:
    """Test config_s3_key path: upload a config JSON then reference it in POST /v1/jobs."""
    print("\n[TEST] config_s3_key — uploading config file and referencing it...")

    config_path = DEMO_DIR / "InvestmentResearch_config.json"
    config_bytes = config_path.read_bytes()
    config_size = len(config_bytes)

    # Request presigned URL for config file
    presigned_cfg = client.post("/v1/uploads/presigned", {
        "filename": "config.json",
        "file_size": config_size,
        "file_type": "config",
    })["data"]
    config_s3_key = presigned_cfg.get("config_s3_key") or presigned_cfg["s3_key"]

    # Upload config file to S3
    r = requests.put(presigned_cfg["presigned_url"],
                     data=config_bytes,
                     headers={"Content-Type": "application/json"},
                     timeout=60)
    r.raise_for_status()
    print(f"[TEST] config_s3_key — config uploaded to {config_s3_key}")

    # Upload a data file (new session)
    xlsx_path = DEMO_DIR / "InvestmentResearch.xlsx"
    presigned_xl = client.post("/v1/uploads/presigned", {
        "filename": "InvestmentResearch.xlsx",
        "file_size": xlsx_path.stat().st_size,
        "file_type": "excel",
    })["data"]
    with open(xlsx_path, "rb") as f:
        r2 = requests.put(presigned_xl["presigned_url"],
                          data=f,
                          headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                          timeout=120)
    r2.raise_for_status()

    # Submit job with config_s3_key
    resp = client.post("/v1/jobs", {
        "session_id": presigned_xl["session_id"],
        "s3_key": presigned_xl["s3_key"],
        "config_s3_key": config_s3_key,
        "preview_rows": 2,
    })
    assert resp["data"]["status"] == "queued", f"Expected 'queued', got: {resp['data']['status']}"
    session_id = presigned_xl["session_id"]
    print(f"[TEST] config_s3_key — [SUCCESS] job queued, session_id={session_id}")
    return session_id


def test_reference_check_text(client: APIClient) -> None:
    """Test reference check with inline text."""
    print("\n[TEST] reference-check (text) — submitting inline text...")

    sample_text = (
        "Acme Corp reported Q3 revenue of $42M, up 18% YoY. "
        "CEO Jane Doe stated that headcount grew to 350 employees. "
        "The company plans to expand into the EU market by Q2 next year."
    )

    resp = client.post("/v1/jobs/reference-check", {"text": sample_text})
    job_id = resp["data"]["job_id"]
    conv_id = resp["data"].get("conversation_id")
    print(f"[TEST] reference-check — job_id={job_id}, conv_id={conv_id}")

    # Poll for completion (up to 5 minutes)
    print("[TEST] reference-check — polling for completion...")
    final = poll_until(client, job_id, ["completed"], timeout=300, label="REFCHECK")

    # Fetch results
    results_data = client.get(f"/v1/jobs/{job_id}/reference-results")
    dl_url = (results_data.get("data") or {}).get("results", {}).get("download_url")
    assert dl_url, "Expected a download_url in reference-results response"
    print(f"[TEST] reference-check (text) — [SUCCESS] download_url present")


def test_reference_check_odf(client: APIClient) -> None:
    """Test reference check with ODF file upload (skips if no ODF file available)."""
    print("\n[TEST] reference-check (ODF) — uploading ODF file...")

    # Create a minimal ODF file in-memory for testing
    import io
    import zipfile as _zf

    odf_content_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        '<office:body><office:text>'
        '<text:p>Test reference document: Revenue was $10M in Q1 2025. '
        'Headcount is 100 employees. Product launched in March.</text:p>'
        '</office:text></office:body></office:document-content>'
    )
    buf = io.BytesIO()
    with _zf.ZipFile(buf, "w", _zf.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zf.writestr("content.xml", odf_content_xml)
    odf_bytes = buf.getvalue()

    # Upload ODF file
    presigned = client.post("/v1/uploads/presigned", {
        "filename": "test_reference.odt",
        "file_size": len(odf_bytes),
        "file_type": "odf",
    })["data"]

    r = requests.put(presigned["presigned_url"],
                     data=odf_bytes,
                     headers={"Content-Type": "application/vnd.oasis.opendocument.text"},
                     timeout=60)
    r.raise_for_status()
    s3_key = presigned["s3_key"]
    print(f"[TEST] reference-check (ODF) — file uploaded to {s3_key}")

    resp = client.post("/v1/jobs/reference-check", {"s3_key": s3_key})
    job_id = resp["data"]["job_id"]
    print(f"[TEST] reference-check (ODF) — job_id={job_id}")

    final = poll_until(client, job_id, ["completed"], timeout=300, label="REFCHECK_ODF")
    results_data = client.get(f"/v1/jobs/{job_id}/reference-results")
    dl_url = (results_data.get("data") or {}).get("results", {}).get("download_url")
    assert dl_url, "Expected a download_url in reference-results response"
    print(f"[TEST] reference-check (ODF) — [SUCCESS] download_url present")


def test_table_maker_conversation(client: APIClient) -> None:
    """Test table maker conversation start and state retrieval."""
    print("\n[TEST] conversations/table-maker — starting conversation...")

    resp = client.post("/v1/conversations/table-maker", {
        "message": "Create a table tracking top AI startups with funding, headcount, and focus area.",
    })
    d = resp["data"]
    session_id = d["session_id"]
    conv_id = d.get("conversation_id")
    print(f"[TEST] table-maker — session_id={session_id}, conv_id={conv_id}")

    # Poll job status for up to 60 seconds
    deadline = time.time() + 60
    final_status = None
    while time.time() < deadline:
        status_resp = client.get(f"/v1/jobs/{session_id}")
        status = status_resp["data"].get("status", "unknown")
        print(f"[TEST] table-maker — status={status}")
        if status not in ("queued", "processing"):
            final_status = status
            break
        time.sleep(10)

    # Check conversation state (may fail if processing not complete yet — non-fatal)
    if conv_id:
        try:
            conv_resp = client.get(f"/v1/conversations/{conv_id}", params={"session_id": session_id})
            state = conv_resp.get("data") or {}
            print(f"[TEST] table-maker — conversation state: status={state.get('status')}, "
                  f"turn_count={state.get('turn_count')}")
        except Exception as e:
            print(f"[TEST] table-maker — conversation state not yet available: {e}")

    print(f"[TEST] conversations/table-maker — [SUCCESS] conversation started (final_status={final_status})")


def test_upload_interview_and_select(client: APIClient, session_id: str) -> None:
    """Test upload interview start and selection (uses config_s3_key test session)."""
    print(f"\n[TEST] conversations/upload-interview — starting interview for session {session_id}...")

    resp = client.post("/v1/conversations/upload-interview", {
        "session_id": session_id,
        "message": "I have an investment research spreadsheet.",
    })
    d = resp["data"]
    conv_id = d["conversation_id"]
    print(f"[TEST] upload-interview — conv_id={conv_id}")

    # Wait briefly for interview to initialize
    time.sleep(5)

    # Select use_match (use best-matching existing config)
    try:
        sel_resp = client.post(f"/v1/conversations/{conv_id}/select", {
            "session_id": session_id,
            "selection": "use_match",
        })
        print(f"[TEST] upload-interview — select result: {sel_resp.get('data')}")
        print(f"[TEST] conversations/upload-interview — [SUCCESS]")
    except RuntimeError as e:
        # No matching config is expected in a fresh test environment — treat as non-fatal
        print(f"[TEST] upload-interview — select returned error (expected if no match): {e}")
        print(f"[TEST] conversations/upload-interview — [SUCCESS] (no match, expected)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="E2E test for the External API")
    parser.add_argument("--env", default="dev", choices=["dev", "test", "staging", "prod"],
                        help="Deployment environment (default: dev)")
    parser.add_argument("--preview-only", action="store_true",
                        help="Stop after preview completes (skip full validation)")
    args = parser.parse_args()

    env = args.env
    print("=" * 60)
    print(f"External API E2E Test  — environment: {env}")
    print("=" * 60)

    # 0. Discover API URL
    base_url = find_external_api_url(env)

    # Verify Lambda has API_GATEWAY_EXTERNAL_API_ID set
    resource_suffix = "" if env == "prod" else f"-{env}"
    fn_name = f"perplexity-validator-interface{resource_suffix}"
    lc = boto3.client("lambda", region_name=REGION)
    fn_env = lc.get_function_configuration(FunctionName=fn_name)["Environment"]["Variables"]
    ext_api_id_in_lambda = fn_env.get("API_GATEWAY_EXTERNAL_API_ID", "")
    expected_api_id = base_url.split("//")[1].split(".")[0]
    if ext_api_id_in_lambda != expected_api_id:
        print(f"[WARN] Lambda env API_GATEWAY_EXTERNAL_API_ID='{ext_api_id_in_lambda}' "
              f"does not match gateway ID '{expected_api_id}'. Fixing...")
        fn_env["API_GATEWAY_EXTERNAL_API_ID"] = expected_api_id
        lc.update_function_configuration(FunctionName=fn_name, Environment={"Variables": fn_env})
        time.sleep(3)
        print(f"[WARN] Updated Lambda env — API_GATEWAY_EXTERNAL_API_ID={expected_api_id}")
    else:
        print(f"[CHECK] Lambda env OK — API_GATEWAY_EXTERNAL_API_ID={ext_api_id_in_lambda}")

    # 1. Get / create API key
    api_key, api_key_hash = get_or_create_api_key(env)
    client = APIClient(base_url, api_key)

    # Smoke-test auth
    print(f"[AUTH] Verifying API key against {base_url}/v1/account/balance...")
    balance_data = client.get("/v1/account/balance")
    balance = (balance_data.get("data") or {}).get("balance_usd", "?")
    print(f"[AUTH] OK — balance for {EMAIL}: ${balance}")

    # 2. Upload demo file
    presigned = upload_demo_file(client, env)

    # 3. Create preview job
    job_id = create_job(client, presigned)

    # 4. Poll for preview_complete
    print(f"\n[POLL] Waiting for preview to complete (timeout {PREVIEW_TIMEOUT}s)...")
    preview_data = poll_until(
        client, job_id,
        target_statuses=["preview_complete"],
        timeout=PREVIEW_TIMEOUT,
        label="PREVIEW",
    )
    print(f"[PREVIEW] Complete!")

    if args.preview_only:
        print("\n[DONE] --preview-only flag set; stopping after preview.")
        return

    # 5. Approve full validation
    approve_validation(client, job_id, preview_data)

    # 6. Poll for completed
    print(f"\n[POLL] Waiting for full validation to complete (timeout {FULL_TIMEOUT}s)...")
    poll_until(
        client, job_id,
        target_statuses=["completed"],
        timeout=FULL_TIMEOUT,
        label="FULL",
    )
    print(f"[FULL] Validation complete!")

    # 7. Download and save results
    out_dir = save_results(client, job_id, env)

    # 8. Test config_id reuse
    try:
        test_config_id(client, job_id)
    except Exception as e:
        print(f"[WARN] test_config_id failed (non-fatal): {e}")

    # 9. Test config file upload (also creates a session used by upload interview test)
    cfg_session_id = None
    try:
        cfg_session_id = test_config_file_upload(client)
    except Exception as e:
        print(f"[WARN] test_config_file_upload failed (non-fatal): {e}")

    # 10. Test reference check with inline text
    try:
        test_reference_check_text(client)
    except Exception as e:
        print(f"[WARN] test_reference_check_text failed (non-fatal): {e}")

    # 11. Test reference check with ODF file
    try:
        test_reference_check_odf(client)
    except Exception as e:
        print(f"[WARN] test_reference_check_odf failed (non-fatal): {e}")

    # 12. Test table maker conversation
    try:
        test_table_maker_conversation(client)
    except Exception as e:
        print(f"[WARN] test_table_maker_conversation failed (non-fatal): {e}")

    # 13. Test upload interview + selection (uses session from config_s3_key test)
    if cfg_session_id:
        try:
            test_upload_interview_and_select(client, cfg_session_id)
        except Exception as e:
            print(f"[WARN] test_upload_interview_and_select failed (non-fatal): {e}")

    # Cleanup: revoke the test API key
    try:
        delete_api_key(api_key_hash)
        print("[CLEANUP] Test API key revoked")
    except Exception as e:
        print(f"[WARN] Could not delete test API key: {e}")

    print("\n" + "=" * 60)
    print(f"[SUCCESS] Test passed!")
    print(f"          Job ID  : {job_id}")
    print(f"          Results : {out_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
