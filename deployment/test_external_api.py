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


def get_or_create_api_key(environment: str) -> str:
    """
    Look for an existing active API key for EMAIL.  If found, we cannot recover
    the raw key (it's never stored), so we create a fresh one with name
    'test-external-api-{env}'.  Returns the raw key.
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
    return raw_key


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

def save_results(client: APIClient, job_id: str, environment: str) -> Path:
    """Fetch the results URL and download the results zip."""
    print(f"[RESULTS] Fetching results for {job_id}...")
    data = client.get(f"/v1/jobs/{job_id}/results")
    results = data["data"]

    download_url = (results.get("results") or {}).get("download_url")
    summary = results.get("summary", {})

    print(f"[RESULTS] Summary:")
    print(f"          rows_processed   = {summary.get('rows_processed')}")
    print(f"          columns_validated = {summary.get('columns_validated')}")
    print(f"          valid_count      = {summary.get('valid_count')}")
    print(f"          invalid_count    = {summary.get('invalid_count')}")
    print(f"          cost_usd         = {summary.get('cost_usd')}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RESULTS_DIR / f"{environment}_{ts}_{job_id[:20]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save summary JSON
    summary_file = out_dir / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[RESULTS] Saved summary → {summary_file}")

    # Download results zip if available
    if download_url:
        print(f"[RESULTS] Downloading results file...")
        zip_path = out_dir / "results.zip"
        resp = requests.get(download_url, timeout=120)
        if resp.status_code == 404:
            print(f"[RESULTS] Download URL returned 404 — file not yet at expected S3 path: {download_url.split('?')[0]}")
            download_url = None  # fall through to "no download URL" path
        else:
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                f.write(resp.content)
        print(f"[RESULTS] Saved zip → {zip_path}")

        # Extract zip
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(out_dir)
            print(f"[RESULTS] Extracted to {out_dir}")
            for item in out_dir.iterdir():
                if item.is_file():
                    print(f"          • {item.name}")
        except zipfile.BadZipFile:
            print(f"[RESULTS] (zip extraction skipped — file may not be a zip)")
    else:
        print(f"[RESULTS] No download URL returned (results may be in S3 directly)")

    return out_dir


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
    api_key = get_or_create_api_key(env)
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

    print("\n" + "=" * 60)
    print(f"[SUCCESS] Test passed!")
    print(f"          Job ID  : {job_id}")
    print(f"          Results : {out_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
