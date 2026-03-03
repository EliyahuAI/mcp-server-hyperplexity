#!/usr/bin/env python3
"""
Config Probe — upload each test table without a configuration and report
what model / QC assignments the system auto-generates.

Usage:
    cd benchmark/config_probe
    python upload_and_report.py

Pulls the generated config JSON directly from S3 once the interview completes.
"""

import json
import sys
import time
import pathlib
import requests
import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Hardcoded credentials
# ---------------------------------------------------------------------------
API_URL = "https://07w4n09m95.execute-api.us-east-1.amazonaws.com/v1"
API_KEY = "hpx_live_r0GWnJjjCHBKWP45ZzZkB28_MvUBREuOJfTLb4Mm"

S3_BUCKET     = "hyperplexity-storage-dev"
S3_EMAIL_PATH = "eliyahu.ai/eliyahu"   # domain/email_prefix

PROBE_DIR      = pathlib.Path(__file__).parent
POLL_INTERVAL  = 8    # seconds between S3 polls
CONFIG_TIMEOUT = 300  # seconds to wait for config file to appear

TEST_FILES = [
    "test_01_isotope_nmr.csv",
    "test_02_hts_superconductors.csv",
    "test_03_diatomic_spectroscopy.csv",
    "test_04_mineral_lattice.csv",
    "test_05_meson_properties.csv",
    "test_06_reaction_thermodynamics.csv",
    "test_07_oncology_trials.csv",
    "test_08_immunotherapy_os.csv",
    "test_09_mab_mechanisms.csv",
]

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def _headers():
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

def _url(path):
    return f"{API_URL}{path}"

def upload_file(csv_path: pathlib.Path) -> dict:
    """3-step presigned upload. Returns confirm response fields."""
    filename  = csv_path.name
    file_size = csv_path.stat().st_size

    # Step 1: presigned URL
    r = requests.post(_url("/uploads/presigned"), headers=_headers(), json={
        "file_type": "csv",
        "filename":  filename,
        "file_size": file_size,
    }, timeout=30)
    r.raise_for_status()
    presigned     = r.json().get("data", r.json())   # unwrap {success, data, ...} envelope
    session_id    = presigned["session_id"]
    presigned_url = presigned["presigned_url"]
    s3_key        = presigned["s3_key"]
    upload_id     = presigned.get("upload_id", "")

    # Step 2: PUT to S3
    with open(csv_path, "rb") as fh:
        requests.put(presigned_url, data=fh,
                     headers={"Content-Type": "text/csv"}, timeout=60).raise_for_status()

    # Step 3: confirm
    r = requests.post(_url("/uploads/confirm"), headers=_headers(), json={
        "session_id": session_id,
        "s3_key":     s3_key,
        "upload_id":  upload_id,
        "filename":   filename,
    }, timeout=30)
    r.raise_for_status()
    confirm = r.json()

    return {
        "session_id":             session_id,
        "conversation_id":        confirm.get("conversation_id"),
        "interview_auto_started": confirm.get("interview_auto_started", False),
        "match_count":            confirm.get("match_count", 0),
        "perfect_match":          confirm.get("perfect_match", False),
    }

# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------
def _s3():
    return boto3.client("s3")

def fetch_config_from_s3(session_id: str, timeout: int) -> dict | None:
    """
    Poll S3 until a config*.json file appears under:
      results/{S3_EMAIL_PATH}/{session_id}/config*.json
    Returns parsed JSON or None on timeout.
    """
    prefix   = f"results/{S3_EMAIL_PATH}/{session_id}/"
    client   = _s3()
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            resp = client.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
            keys = [obj["Key"] for obj in resp.get("Contents", [])
                    if "/config" in obj["Key"] and obj["Key"].endswith(".json")]
            if keys:
                # Take the last alphabetically (config_v1_api_inline.json or similar)
                key = sorted(keys)[-1]
                print(f"    Found config: s3://{S3_BUCKET}/{key}")
                obj = client.get_object(Bucket=S3_BUCKET, Key=key)
                return json.loads(obj["Body"].read()), key
        except ClientError as e:
            print(f"    S3 error: {e}")

        time.sleep(POLL_INTERVAL)

    return None, None

def parse_model_assignments(cfg: dict) -> dict:
    """Extract search_groups and qc_settings from config JSON."""
    groups = []
    for sg in cfg.get("search_groups", []):
        if sg.get("group_id") == 0:
            continue  # skip the entity-id group
        groups.append({
            "group_id":    sg.get("group_id"),
            "group_name":  sg.get("group_name"),
            "capability":  sg.get("capability", ""),
            "model":       sg.get("model"),
            "columns":     sg.get("column_names") or sg.get("columns"),
            "description": (sg.get("description") or "")[:120],
        })
    qc = cfg.get("qc_settings", {})
    return {
        "search_groups": groups,
        "qc_enable":     qc.get("enable_qc"),
        "qc_model":      qc.get("model"),
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Optional: filter to specific test(s) via CLI args, e.g. "python upload_and_report.py test_01"
    filters = [a.lower() for a in sys.argv[1:]]
    files_to_run = [f for f in TEST_FILES if not filters or any(filt in f for filt in filters)]
    if not files_to_run:
        sys.exit(f"No files matched filters: {filters}")

    results = []

    for fname in files_to_run:
        csv_path = PROBE_DIR / fname
        if not csv_path.exists():
            print(f"[SKIP] {fname} not found")
            continue

        test_id = "_".join(fname.split("_")[:2])
        print(f"\n{'='*60}")
        print(f"[{test_id}] {fname}")

        entry = {
            "test_id":      test_id,
            "filename":     fname,
            "session_id":   None,
            "conv_id":      None,
            "match_count":  None,
            "perfect_match": None,
            "s3_config_key": None,
            "assignments":  None,
            "viewer_url":   None,
            "error":        None,
        }
        results.append(entry)

        try:
            up = upload_file(csv_path)
        except Exception as e:
            print(f"  Upload failed: {e}")
            entry["error"] = str(e)
            continue

        entry["session_id"]   = up["session_id"]
        entry["conv_id"]      = up["conversation_id"]
        entry["match_count"]  = up["match_count"]
        entry["perfect_match"] = up["perfect_match"]
        entry["viewer_url"]   = f"https://eliyahu.ai/viewer?session={up['session_id']}"

        print(f"  session_id  = {up['session_id']}")
        print(f"  conv_id     = {up['conversation_id']}")
        print(f"  match_count = {up['match_count']}  perfect_match = {up['perfect_match']}")
        print(f"  interview_auto_started = {up['interview_auto_started']}")

        if up["perfect_match"]:
            print("  WARNING: perfect config match — column rename may not have been enough, config reused")

        print(f"  Polling S3 for config (up to {CONFIG_TIMEOUT}s)...")
        cfg, s3_key = fetch_config_from_s3(up["session_id"], CONFIG_TIMEOUT)
        if cfg:
            entry["s3_config_key"] = s3_key
            entry["assignments"]   = parse_model_assignments(cfg)
            a = entry["assignments"]
            print(f"  qc_enable={a['qc_enable']}  qc_model={a['qc_model']}")
            for sg in a["search_groups"]:
                cap = sg['capability'] or "(none)"
                print(f"  group {sg['group_id']}: capability={cap}  model={sg['model']}  cols={sg['columns']}")
        else:
            print("  Timed out waiting for config — session_id recorded for manual review")

    # ---------------------------------------------------------------------------
    # Markdown report
    # ---------------------------------------------------------------------------
    lines = [
        "# Config Probe Report\n\n",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n\n",
        "Tables uploaded without explicit configuration. "
        "First column header pluralized (+s) to avoid config cache hits.\n\n",
        "## Summary\n\n",
        "| test | match | qc | qc_model | group | capability | model | viewer |\n",
        "|---|---|---|---|---|---|---|---|\n",
    ]
    for e in results:
        if e["error"]:
            lines.append(f"| {e['test_id']} | ERROR | — | — | — | — | — | — |\n")
            continue
        a   = e["assignments"] or {}
        mc  = "PERFECT" if e["perfect_match"] else (str(e["match_count"]) if e["match_count"] else "0")
        qce = str(a.get("qc_enable", "?"))
        qcm = str(a.get("qc_model") or "—")
        view = f"[view]({e['viewer_url']})" if e["viewer_url"] else "—"
        sgs = a.get("search_groups") or []
        if sgs:
            for sg in sgs:
                name = sg.get("group_name") or str(sg["group_id"])
                cap  = sg.get("capability") or "—"
                mdl  = sg.get("model") or "?"
                lines.append(f"| {e['test_id']} | {mc} | {qce} | {qcm} | {name} | {cap} | {mdl} | {view} |\n")
        else:
            lines.append(f"| {e['test_id']} | {mc} | {qce} | {qcm} | ? | ? | ? | {view} |\n")

    lines.append("\n## Per-Test Detail\n\n")
    for e in results:
        lines.append(f"### {e['test_id']} — {e['filename']}\n\n")
        if e["error"]:
            lines.append(f"**Error:** {e['error']}\n\n")
            continue
        lines.append(f"- **session_id:** `{e['session_id']}`\n")
        lines.append(f"- **conv_id:** `{e['conv_id']}`\n")
        lines.append(f"- **viewer:** {e['viewer_url']}\n")
        lines.append(f"- **match_count:** {e['match_count']}  perfect: {e['perfect_match']}\n")
        if e["s3_config_key"]:
            lines.append(f"- **s3_config:** `{e['s3_config_key']}`\n")
        a = e.get("assignments") or {}
        if a:
            lines.append(f"\n```json\n{json.dumps(a, indent=2)}\n```\n")
        else:
            lines.append("\n_Config not yet retrieved — check viewer manually._\n")
        lines.append("\n")

    report = "".join(lines)
    print("\n" + "="*60)
    print(report)
    out = PROBE_DIR / "report.md"
    out.write_text(report, encoding="utf-8")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
