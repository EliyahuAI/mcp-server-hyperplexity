#!/usr/bin/env python3
"""
Test and deploy Hyperplexity example scripts.

Steps:
1. Create a temp int-tier API key
2. Smoke test: get_balance, upload_file, confirm_upload
3. Test 01_validate_table flow: config match → preview (abort before approval)
4. Update docs/API_GUIDE.md with permanent S3 download links
5. Upload examples + API_GUIDE.md to S3 website_downloads/
6. Update S3 bucket policy to allow public reads on website_downloads/*
7. Verify public URLs return 200
8. Delete the temp API key

Usage:
    python deployment/test_and_deploy_examples.py [--env prod|dev] [--skip-tests] [--skip-upload]

Requirements: boto3, requests
"""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = REPO_ROOT / "mcp" / "examples"
DOCS_DIR = REPO_ROOT / "docs"
DEMO_DIR = REPO_ROOT / "demos" / "01. Investment Research"

S3_BUCKET = "hyperplexity-storage"
PUBLIC_URL_BASE = f"https://{S3_BUCKET}.s3.amazonaws.com/website_downloads"

REGION = "us-east-1"
EMAIL = "eliyahu@eliyahu.ai"
API_KEYS_TABLE = "perplexity-validator-api-keys"
SSM_PARAM = "/perplexity-validator/api-key-hmac-secret"
DISPLAY_PREFIX_LEN = 18

FILES_TO_UPLOAD = [
    ("mcp/examples/hyperplexity_client.py", "website_downloads/examples/hyperplexity_client.py"),
    ("mcp/examples/01_validate_table.py",   "website_downloads/examples/01_validate_table.py"),
    ("mcp/examples/02_generate_table.py",   "website_downloads/examples/02_generate_table.py"),
    ("mcp/examples/03_update_table.py",     "website_downloads/examples/03_update_table.py"),
    ("mcp/examples/04_reference_check.py",  "website_downloads/examples/04_reference_check.py"),
    ("docs/API_GUIDE.md",                   "website_downloads/API_GUIDE.md"),
]


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------

def _load_hmac_secret() -> str:
    env_val = os.environ.get("API_KEY_HMAC_SECRET")
    if env_val:
        return env_val
    ssm = boto3.client("ssm", region_name=REGION)
    response = ssm.get_parameter(Name=SSM_PARAM, WithDecryption=True)
    return response["Parameter"]["Value"]


def _hash_key(raw_key: str, secret: str) -> str:
    return hmac.new(secret.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


def create_test_api_key() -> tuple:
    """Create a fresh int-tier API key for testing. Returns (raw_key, key_hash)."""
    hmac_secret = _load_hmac_secret()
    ddb = boto3.resource("dynamodb", region_name=REGION)
    table = ddb.Table(API_KEYS_TABLE)

    raw_key = f"hpx_int_{secrets.token_urlsafe(30)}"
    key_hash = _hash_key(raw_key, hmac_secret)
    key_prefix = raw_key[:DISPLAY_PREFIX_LEN]
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "api_key_hash": key_hash,
        "key_prefix": key_prefix,
        "email": EMAIL,
        "key_name": "test-deploy-examples",
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
        "metadata": {"created_via": "test_deploy_examples"},
    }
    table.put_item(Item=item)
    print(f"[KEY] Created int-tier test key: {key_prefix}...")
    return raw_key, key_hash


def delete_api_key(key_hash: str) -> None:
    ddb = boto3.resource("dynamodb", region_name=REGION)
    table = ddb.Table(API_KEYS_TABLE)
    table.delete_item(Key={"api_key_hash": key_hash})
    print(f"[KEY] Deleted test key (hash: {key_hash[:12]}...)")


# ---------------------------------------------------------------------------
# API URL discovery
# ---------------------------------------------------------------------------

def find_api_url(environment: str) -> str:
    resource_suffix = "" if environment == "prod" else f"-{environment}"
    api_name = f"hyperplexity-external-api{resource_suffix}"
    apigw = boto3.client("apigatewayv2", region_name=REGION)
    for api in apigw.get_apis().get("Items", []):
        if api["Name"] == api_name:
            endpoint = api["ApiEndpoint"].rstrip("/")
            print(f"[API] Found: {api_name} → {endpoint}/v1")
            return endpoint + "/v1"
    raise RuntimeError(f"API Gateway '{api_name}' not found.")


# ---------------------------------------------------------------------------
# Test client
# ---------------------------------------------------------------------------

class TestClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def get(self, path: str, params: dict = None) -> dict:
        r = requests.get(f"{self.base_url}{path}", headers=self.headers, params=params, timeout=30)
        return self._unwrap(r)

    def post(self, path: str, body: dict = None) -> dict:
        r = requests.post(f"{self.base_url}{path}", headers=self.headers, json=body, timeout=30)
        return self._unwrap(r)

    def _unwrap(self, r: requests.Response) -> dict:
        try:
            p = r.json()
        except Exception:
            r.raise_for_status()
            return {}
        if not r.ok or not p.get("success"):
            print(f"  [HTTP {r.status_code}] {json.dumps(p, indent=2)[:600]}")
            err = p.get("error", {})
            if isinstance(err, str):
                raise RuntimeError(f"API error {r.status_code}: {err}")
            raise RuntimeError(f"[{err.get('code', 'error')}] {err.get('message', p)}")
        return p["data"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_smoke(client: TestClient) -> None:
    print("\n--- Smoke: get_balance ---")
    balance = client.get("/account/balance")
    print(f"  Balance: ${balance.get('balance_usd', '?')} | Usage this month: ${balance.get('usage_usd_this_month', balance.get('usage_usd', '?'))}")


def test_upload_and_confirm(client: TestClient) -> dict:
    print("\n--- Test: upload_file + confirm_upload ---")
    xlsx_path = DEMO_DIR / "InvestmentResearch.xlsx"
    file_bytes = xlsx_path.read_bytes()
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # Presigned URL
    presign = client.post("/uploads/presigned", {
        "filename": xlsx_path.name,
        "file_size": len(file_bytes),
        "file_type": "excel",
        "content_type": content_type,
    })
    print(f"  Got presigned URL → session_id: {presign['session_id']}")

    # Upload to S3
    r = requests.put(presign["presigned_url"], data=file_bytes,
                     headers={"Content-Type": content_type})
    r.raise_for_status()
    print(f"  Uploaded {len(file_bytes):,} bytes to S3")

    # Confirm
    confirm = client.post("/uploads/confirm", {
        "session_id": presign["session_id"],
        "s3_key": presign["s3_key"],
        "filename": xlsx_path.name,
    })
    print(f"  confirm_upload → keys: {list(confirm.keys())}")

    matches = confirm.get("matches") or confirm.get("config_matches") or []
    if matches:
        best = max(matches, key=lambda m: m.get("match_score", 0))
        score = best.get("match_score", 0)
        cid = best.get("config_id", "?")
        print(f"  Best config match: score={score:.2f}, config_id={cid}")
    else:
        print("  No config matches found")

    conv_id = confirm.get("conversation_id")
    if conv_id:
        print(f"  Interview started: conversation_id={conv_id}")

    return {
        "session_id": presign["session_id"],
        "s3_key": presign["s3_key"],
        "filename": xlsx_path.name,
        "confirm": confirm,
    }


def test_preview(client: TestClient, upload_result: dict) -> None:
    print("\n--- Test: preview job (config-reuse path) ---")
    confirm = upload_result["confirm"]
    session_id = upload_result["session_id"]

    matches = confirm.get("matches") or confirm.get("config_matches") or []
    if not matches:
        print("  No config matches — skipping preview test")
        return

    best = max(matches, key=lambda m: m.get("match_score", 0))
    score = best.get("match_score", 0)
    if score < 0.85:
        print(f"  Best match score {score:.2f} < 0.85 — skipping preview test")
        return

    config_id = best.get("config_id")
    print(f"  Creating preview job with config {config_id}...")
    job_data = client.post("/jobs", {
        "session_id": session_id,
        "config_id": config_id,
        "preview_rows": 3,
    })
    job_id = job_data.get("job_id", session_id)
    print(f"  Preview job: {job_id}")

    deadline = time.time() + 600
    data = {}
    while time.time() < deadline:
        data = client.get(f"/jobs/{job_id}")
        status = data.get("status", "unknown")
        pct = data.get("progress_percent", 0)
        step = data.get("current_step", "")
        print(f"  [{status}] {step} ({pct}%)")
        if status in ("preview_complete", "completed", "failed"):
            break
        time.sleep(10)
    else:
        print("  Timed out waiting for preview")
        return

    if data.get("status") == "preview_complete":
        print("  ✓ Preview complete!")
        cost = data.get("cost_estimate", {})
        print(f"  Estimated full cost: ${cost.get('estimated_total_cost_usd', '?')}")
        tbl = data.get("preview_table", "")
        if tbl:
            lines = tbl.split("\n")[:8]
            print("  Preview table (first 8 lines):")
            print("\n".join("    " + ln for ln in lines))
        print("  (Aborting — not approving full validation)")
    else:
        print(f"  Final status: {data.get('status')} — {data.get('error', {}).get('message', '')}")


# ---------------------------------------------------------------------------
# API_GUIDE.md update
# ---------------------------------------------------------------------------

DOWNLOAD_SECTION = """\
## Download Examples

> All scripts require Python 3.10+ and `pip install requests`.

| Script | Description | Download |
|--------|-------------|----------|
| `hyperplexity_client.py` | Shared REST client (required by all examples) | [download]({base}/examples/hyperplexity_client.py) |
| `01_validate_table.py` | Validate an existing table | [download]({base}/examples/01_validate_table.py) |
| `02_generate_table.py` | Generate a table from a prompt | [download]({base}/examples/02_generate_table.py) |
| `03_update_table.py` | Re-validate after analyst corrections | [download]({base}/examples/03_update_table.py) |
| `04_reference_check.py` | Fact-check text or documents | [download]({base}/examples/04_reference_check.py) |

Or clone the full example set:

```bash
# Download all examples at once
curl -O {base}/examples/hyperplexity_client.py \\
     -O {base}/examples/01_validate_table.py \\
     -O {base}/examples/02_generate_table.py \\
     -O {base}/examples/03_update_table.py \\
     -O {base}/examples/04_reference_check.py
pip install requests
export HYPERPLEXITY_API_KEY=hpx_live_...
```

---

"""


def update_api_guide() -> None:
    print("\n--- Updating API_GUIDE.md ---")
    guide_path = DOCS_DIR / "API_GUIDE.md"
    content = guide_path.read_text(encoding="utf-8")

    # Don't double-insert
    if "## Download Examples" in content:
        print("  'Download Examples' section already present — skipping insert")
    else:
        insert_before = "## Quick Start: MCP (Claude)"
        if insert_before not in content:
            insert_before = "## Workflows"
        section = DOWNLOAD_SECTION.format(base=PUBLIC_URL_BASE)
        content = content.replace(insert_before, section + insert_before)
        print("  Inserted 'Download Examples' section")

    # Update per-workflow script references to permanent S3 URLs
    replacements = [
        ("](../mcp/examples/hyperplexity_client.py)", f"]({PUBLIC_URL_BASE}/examples/hyperplexity_client.py)"),
        ("](../mcp/examples/01_validate_table.py)",   f"]({PUBLIC_URL_BASE}/examples/01_validate_table.py)"),
        ("](../mcp/examples/02_generate_table.py)",   f"]({PUBLIC_URL_BASE}/examples/02_generate_table.py)"),
        ("](../mcp/examples/03_update_table.py)",     f"]({PUBLIC_URL_BASE}/examples/03_update_table.py)"),
        ("](../mcp/examples/04_reference_check.py)",  f"]({PUBLIC_URL_BASE}/examples/04_reference_check.py)"),
    ]
    changed = 0
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            changed += 1
    if changed:
        print(f"  Updated {changed} per-workflow script link(s) to S3 URLs")

    guide_path.write_text(content, encoding="utf-8")
    print(f"  Saved {guide_path}")


# ---------------------------------------------------------------------------
# S3 upload + policy
# ---------------------------------------------------------------------------

def upload_files_to_s3() -> None:
    print("\n--- Uploading files to S3 ---")
    s3 = boto3.client("s3", region_name=REGION)

    for local_path, s3_key in FILES_TO_UPLOAD:
        full_path = REPO_ROOT / local_path
        content = full_path.read_bytes()

        if local_path.endswith(".py"):
            content_type = "text/x-python"
        elif local_path.endswith(".md"):
            content_type = "text/markdown; charset=utf-8"
        else:
            content_type = "application/octet-stream"

        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=content,
            ContentType=content_type,
        )
        url = f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}"
        print(f"  ✓ {local_path}")
        print(f"      → {url}")


def update_bucket_policy() -> None:
    print("\n--- Updating S3 bucket policy ---")
    s3 = boto3.client("s3", region_name=REGION)

    resp = s3.get_bucket_policy(Bucket=S3_BUCKET)
    policy = json.loads(resp["Policy"])

    # Check if website_downloads/* is already covered
    for stmt in policy["Statement"]:
        resources = stmt.get("Resource", [])
        if isinstance(resources, str):
            resources = [resources]
        if any("website_downloads" in r for r in resources):
            print("  website_downloads/* already in policy — no change needed")
            return

    policy["Statement"].append({
        "Sid": "PublicReadWebsiteDownloads",
        "Effect": "Allow",
        "Principal": "*",
        "Action": "s3:GetObject",
        "Resource": f"arn:aws:s3:::{S3_BUCKET}/website_downloads/*",
    })
    s3.put_bucket_policy(Bucket=S3_BUCKET, Policy=json.dumps(policy))
    print("  ✓ Added PublicReadWebsiteDownloads statement")


def verify_public_urls() -> bool:
    print("\n--- Verifying public URLs ---")
    ok = True
    urls = [
        f"{PUBLIC_URL_BASE}/examples/hyperplexity_client.py",
        f"{PUBLIC_URL_BASE}/examples/01_validate_table.py",
        f"{PUBLIC_URL_BASE}/examples/02_generate_table.py",
        f"{PUBLIC_URL_BASE}/examples/03_update_table.py",
        f"{PUBLIC_URL_BASE}/examples/04_reference_check.py",
        f"{PUBLIC_URL_BASE}/API_GUIDE.md",
    ]
    for url in urls:
        try:
            r = requests.head(url, timeout=10)
            status = "✓" if r.status_code == 200 else f"✗ ({r.status_code})"
            if r.status_code != 200:
                ok = False
        except Exception as e:
            status = f"✗ ({e})"
            ok = False
        print(f"  {status} {url}")
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Test and deploy Hyperplexity example scripts")
    parser.add_argument("--env", default="prod", choices=["prod", "dev"],
                        help="API environment to test against (default: prod)")
    parser.add_argument("--skip-tests", action="store_true",
                        help="Skip live API tests, go straight to S3 upload")
    parser.add_argument("--skip-upload", action="store_true",
                        help="Skip S3 upload (only run API tests)")
    args = parser.parse_args()

    raw_key = None
    key_hash = None

    try:
        # ── Step 1: Create test API key ─────────────────────────────────────
        if not args.skip_tests:
            print("\n=== Step 1: Create test API key ===")
            raw_key, key_hash = create_test_api_key()

            if args.env == "prod":
                api_url = "https://api.hyperplexity.ai/v1"
                print(f"[API] Using production URL: {api_url}")
            else:
                api_url = find_api_url(args.env)

            client = TestClient(api_url, raw_key)

            # ── Step 2: Smoke test ───────────────────────────────────────────
            print("\n=== Step 2: Smoke tests ===")
            test_smoke(client)

            # ── Step 3: Upload + preview ─────────────────────────────────────
            print("\n=== Step 3: Upload + confirm + preview test ===")
            upload_result = test_upload_and_confirm(client)
            test_preview(client, upload_result)

        # ── Step 4: Update API_GUIDE.md ──────────────────────────────────────
        if not args.skip_upload:
            print("\n=== Step 4: Update API_GUIDE.md ===")
            update_api_guide()

            # ── Step 5: Upload to S3 ─────────────────────────────────────────
            print("\n=== Step 5: Upload files to S3 ===")
            upload_files_to_s3()

            # ── Step 6: Update bucket policy ─────────────────────────────────
            print("\n=== Step 6: Update bucket policy ===")
            update_bucket_policy()

            # ── Step 7: Verify ───────────────────────────────────────────────
            print("\n=== Step 7: Verify public URLs ===")
            success = verify_public_urls()
            if not success:
                print("\n  Some URLs failed — check bucket policy and S3 upload logs above.")

    finally:
        # ── Step 8: Clean up test key ─────────────────────────────────────────
        if key_hash:
            print("\n=== Step 8: Cleanup ===")
            delete_api_key(key_hash)

    print("\n=== Done! ===")
    print(f"\nPublic download base: {PUBLIC_URL_BASE}/examples/")


if __name__ == "__main__":
    main()
