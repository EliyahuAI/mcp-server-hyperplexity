#!/usr/bin/env python3
"""
run_benchmark.py — Benchmark orchestrator for Hyperplexity validation quality.

Runs all combinations defined in model_matrix.csv against the 5 esoteric-science
test datasets, collects results + metadata per run, and saves everything
to a timestamped results/ directory.

Usage:
    python benchmark/run_benchmark.py --smoke-test              # 1 run: test_01 × the-clone × no_qc
    python benchmark/run_benchmark.py --minimal                 # test_01 × all 7 search models
    python benchmark/run_benchmark.py --full                    # all 46 runs in model_matrix.csv
    python benchmark/run_benchmark.py --full --resume           # skip runs that already have results.json
    python benchmark/run_benchmark.py --run-ids 001 005 016     # specific run IDs only
    python benchmark/run_benchmark.py --minimal --parallel      # run all selected runs concurrently
    python benchmark/run_benchmark.py --full --test-id test_01  # all runs for test_01 only

Configuration (env vars or .env file in benchmark/):
    HYPERPLEXITY_API_URL     Base URL, e.g. https://abc123.execute-api.us-east-1.amazonaws.com/prod
    HYPERPLEXITY_API_KEY     External API key
    BENCHMARK_RESULTS_DIR    Override results directory (default: benchmark/results/)
"""

import argparse
import copy
import csv
import json
import logging
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Setup paths
# ---------------------------------------------------------------------------
BENCHMARK_DIR = Path(__file__).parent
REPO_ROOT = BENCHMARK_DIR.parent
TEST_DATA_DIR = BENCHMARK_DIR / "test_data"
TEST_CONFIGS_DIR = BENCHMARK_DIR / "test_configs_base"
MODEL_MATRIX_PATH = BENCHMARK_DIR / "model_matrix.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load .env if present (simple key=value parser, no dependency on dotenv)
# ---------------------------------------------------------------------------
def _load_dotenv():
    env_path = BENCHMARK_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_dotenv()

# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------
class HyperplexityClient:
    """Thin REST client for the Hyperplexity external API."""

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _unwrap(resp_json: Dict) -> Dict:
        """Unwrap { success, data, meta } envelope — return data if present."""
        return resp_json.get("data") if "data" in resp_json else resp_json

    def upload_file(self, file_path: Path) -> Dict:
        """3-step presigned upload. Returns {session_id, upload_id, s3_key}."""
        filename = file_path.name

        # Step 1: Get presigned S3 URL
        file_size = file_path.stat().st_size
        resp = self.session.post(
            self._url("/uploads/presigned"),
            json={"filename": filename, "file_type": "csv", "file_size": file_size},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        presigned = self._unwrap(resp.json())
        presigned_url = presigned["presigned_url"]
        session_id = presigned["session_id"]
        upload_id = presigned.get("upload_id", "")
        s3_key = presigned["s3_key"]
        content_type = presigned.get("content_type", "text/csv")

        # Step 2: PUT file bytes directly to S3 — Content-Type must match signed header
        with file_path.open("rb") as fh:
            put_resp = requests.put(presigned_url, data=fh,
                                    headers={"Content-Type": content_type}, timeout=120)
        put_resp.raise_for_status()

        # Step 3: Confirm upload (seeds session state for POST /jobs)
        confirm_resp = self.session.post(
            self._url("/uploads/confirm"),
            json={"session_id": session_id, "s3_key": s3_key,
                  "upload_id": upload_id, "filename": filename,
                  "skip_interview": True},
            timeout=self.timeout,
        )
        confirm_resp.raise_for_status()

        return {"session_id": session_id, "upload_id": upload_id, "s3_key": s3_key}

    def create_job(self, session_id: str, upload_id: str, s3_key: str, config: Dict) -> Dict:
        """Create a job with inline config (bypasses interview)."""
        resp = self.session.post(
            self._url("/jobs"),
            json={"session_id": session_id, "upload_id": upload_id,
                  "s3_key": s3_key, "config": config},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return self._unwrap(resp.json())

    def get_job_status(self, session_id: str) -> Dict:
        resp = self.session.get(self._url(f"/jobs/{session_id}"), timeout=self.timeout)
        resp.raise_for_status()
        return self._unwrap(resp.json())

    def get_job_messages(self, session_id: str, after_seq: int = 0) -> Dict:
        resp = self.session.get(
            self._url(f"/jobs/{session_id}/messages"),
            params={"after_seq": after_seq},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return self._unwrap(resp.json())

    def approve_validation(self, session_id: str, approved_cost_usd: float = None) -> Dict:
        payload = {}
        if approved_cost_usd is not None:
            payload["approved_cost_usd"] = approved_cost_usd
        resp = self.session.post(
            self._url(f"/jobs/{session_id}/validate"),
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return self._unwrap(resp.json())

    def get_results(self, session_id: str) -> Dict:
        resp = self.session.get(self._url(f"/jobs/{session_id}/results"), timeout=self.timeout)
        resp.raise_for_status()
        return self._unwrap(resp.json())

    def wait_for_status(
        self,
        session_id: str,
        target_statuses: List[str],
        timeout_seconds: int = 900,
        poll_interval: int = 8,
        label: str = "",
    ) -> Dict:
        """Poll get_job_status until one of target_statuses is reached or timeout."""
        deadline = time.time() + timeout_seconds
        last_status = None
        last_pct = -1

        while time.time() < deadline:
            try:
                status_resp = self.get_job_status(session_id)
            except requests.RequestException as e:
                logger.warning(f"  [poll] get_job_status error: {e}, retrying...")
                time.sleep(poll_interval)
                continue

            status = status_resp.get("status", "")
            pct = status_resp.get("progress_percent", 0)

            if status != last_status or pct != last_pct:
                logger.info(f"  [{label or session_id[:12]}] {status} {pct}%")
                last_status = status
                last_pct = pct

            if status in target_statuses:
                return status_resp

            if status in ("failed", "error", "cancelled"):
                raise RuntimeError(f"Job reached terminal error status: {status}")

            time.sleep(poll_interval)

        raise TimeoutError(
            f"Timed out after {timeout_seconds}s waiting for {target_statuses}. "
            f"Last status: {last_status}"
        )


# ---------------------------------------------------------------------------
# Config injection
# ---------------------------------------------------------------------------
def make_config(base_config: Dict, search_model: str, qc_model: str, web_searches: int,
                no_cache: bool = False) -> Dict:
    """Inject search_model + qc_model into a base config template."""
    config = copy.deepcopy(base_config)

    # Set top-level default_model (internal format)
    config["default_model"] = search_model

    # Also set model on each non-ID search group (used by background handler for display)
    for sg in config.get("search_groups", []):
        if sg.get("group_id", 0) == 0:
            sg.pop("model", None)
            continue
        sg["model"] = search_model
        if web_searches > 0 and search_model.startswith("claude-"):
            sg["anthropic_max_web_searches"] = web_searches

    # QC settings
    qc = config.get("qc_settings", {})
    if qc_model == "none":
        qc["enable_qc"] = False
        qc.pop("model", None)
    else:
        qc["enable_qc"] = True
        qc["model"] = [qc_model]
    config["qc_settings"] = qc

    # Force cache bypass (0-day TTL = always treat cached results as expired)
    if no_cache:
        config["cache_ttl_days"] = 0

    return config


# ---------------------------------------------------------------------------
# Model matrix loading
# ---------------------------------------------------------------------------
def load_model_matrix() -> List[Dict]:
    rows = []
    with MODEL_MATRIX_PATH.open() as fh:
        for row in csv.DictReader(fh):
            row["enabled"] = row["enabled"].lower() == "true"
            row["is_ground_truth"] = row["is_ground_truth"].lower() == "true"
            row["web_searches"] = int(row["web_searches"])
            rows.append(row)
    return rows


def filter_matrix(
    rows: List[Dict],
    mode: str,
    run_ids: Optional[List[str]] = None,
    test_id: Optional[str] = None,
) -> List[Dict]:
    if run_ids:
        result = [r for r in rows if r["run_id"] in run_ids and r["enabled"]]
    elif mode == "smoke-test":
        # Exactly 1 run: test_01 × the-clone × no_qc
        result = [r for r in rows if r["test_id"] == "test_01" and r["search_model"] == "the-clone"
                and r["qc_model"] == "none" and r["enabled"]][:1]
    elif mode == "minimal":
        # test_01 × all search models × qc=none only
        result = [r for r in rows if r["test_id"] == "test_01" and r["qc_model"] == "none" and r["enabled"]]
    else:
        # full
        result = [r for r in rows if r["enabled"]]

    # Optional test_id filter (applied on top of mode)
    if test_id:
        result = [r for r in result if r["test_id"] == test_id]

    return result


# ---------------------------------------------------------------------------
# Single run execution
# ---------------------------------------------------------------------------
def run_single(
    row: Dict,
    client: HyperplexityClient,
    results_dir: Path,
    resume: bool = False,
    no_cache: bool = False,
) -> Dict:
    run_id = row["run_id"]
    test_id = row["test_id"]
    search_model = row["search_model"]
    qc_model = row["qc_model"]
    web_searches = row["web_searches"]

    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    results_file = run_dir / "results.json"

    if resume and results_file.exists():
        logger.info(f"[{run_id}] Skipping (results.json exists, --resume)")
        return {"run_id": run_id, "skipped": True}

    logger.info(
        f"\n{'='*60}\n[{run_id}] {test_id} | search={search_model} | qc={qc_model}\n{'='*60}"
    )

    # Load test CSV and base config
    csv_files = list(TEST_DATA_DIR.glob(f"{test_id}_*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV found for {test_id} in {TEST_DATA_DIR}")
    csv_path = csv_files[0]

    config_path = TEST_CONFIGS_DIR / f"{test_id}_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"No base config found: {config_path}")
    base_config = json.loads(config_path.read_text())

    # Build config
    config = make_config(base_config, search_model, qc_model, web_searches, no_cache=no_cache)
    (run_dir / "config_used.json").write_text(json.dumps(config, indent=2))

    run_result = {
        "run_id": run_id,
        "test_id": test_id,
        "search_model": search_model,
        "qc_model": qc_model,
        "web_searches": web_searches,
        "is_ground_truth": row["is_ground_truth"],
        "complexity_tier": row["complexity_tier"],
        "started_at": datetime.utcnow().isoformat() + "Z",
        "session_id": None,
        "status": "started",
        "error": None,
        "preview_cost": None,
        "validation_cost": None,
        "total_elapsed_s": None,
        "preview_elapsed_s": None,
        "validation_elapsed_s": None,
        "model_snapshot_s3_key": None,
        "results_summary": None,
    }
    t0 = time.time()

    try:
        # 1. Upload CSV (presigned → PUT → confirm)
        logger.info(f"[{run_id}] Uploading {csv_path.name}...")
        upload_resp = client.upload_file(csv_path)
        session_id = upload_resp["session_id"]
        upload_id = upload_resp["upload_id"]
        s3_key = upload_resp["s3_key"]
        run_result["session_id"] = session_id
        logger.info(f"[{run_id}] session_id={session_id} upload_id={upload_id}")

        # 2. Create job with inline config (bypasses interview → triggers preview)
        logger.info(f"[{run_id}] Creating job with inline config...")
        create_resp = client.create_job(session_id, upload_id, s3_key, config)
        logger.info(f"[{run_id}] create_job response: {create_resp.get('status', create_resp)}")

        # 3. Wait for preview
        logger.info(f"[{run_id}] Waiting for preview_complete...")
        t_preview = time.time()
        preview_status = client.wait_for_status(
            session_id,
            target_statuses=["preview_complete", "preview_failed"],
            timeout_seconds=900,
            label=run_id,
        )
        run_result["preview_elapsed_s"] = round(time.time() - t_preview, 1)

        if preview_status.get("status") == "preview_failed":
            raise RuntimeError(f"Preview failed: {preview_status.get('error_message', '')}")

        # Capture preview cost if available
        cost_est = preview_status.get("cost_estimate") or preview_status.get("preview_cost", {})
        run_result["preview_cost"] = cost_est.get("estimated_total_cost_usd") or cost_est.get("total_cost") or cost_est.get("preview_cost")
        run_result["estimated_validation_time_s"] = cost_est.get("estimated_validation_time_seconds")

        run_result["model_snapshot_s3_key"] = preview_status.get("model_snapshot_s3_key")

        # 4. Approve validation (pass cost so backend doesn't reject mismatched estimate)
        logger.info(f"[{run_id}] Approving validation...")
        approve_resp = client.approve_validation(session_id, approved_cost_usd=run_result.get("preview_cost"))
        logger.info(f"[{run_id}] approve response: {approve_resp.get('status', approve_resp)}")

        # 5. Wait for validation_complete
        logger.info(f"[{run_id}] Waiting for validation_complete...")
        t_val = time.time()
        est_secs = run_result.get("estimated_validation_time_s") or 300
        val_timeout = max(900, int(est_secs * 2))
        logger.info(f"[{run_id}] Validation timeout: {val_timeout}s (2× estimated {est_secs}s)")
        val_status = client.wait_for_status(
            session_id,
            target_statuses=["validation_complete", "validation_failed", "completed"],
            timeout_seconds=val_timeout,
            label=run_id,
        )
        run_result["validation_elapsed_s"] = round(time.time() - t_val, 1)

        if val_status.get("status") in ("validation_failed",):
            raise RuntimeError(f"Validation failed: {val_status.get('error_message', '')}")

        # Capture validation cost
        val_cost = val_status.get("cost") or val_status.get("validation_cost")
        run_result["validation_cost"] = val_cost

        # 6. Get results
        logger.info(f"[{run_id}] Fetching results...")
        results_resp = client.get_results(session_id)
        run_result["results_summary"] = _summarize_results(results_resp)

        # Save full results response
        results_file.write_text(json.dumps(results_resp, indent=2))

        # 7. Fetch and save metadata JSON (per-cell data: confidence, sources, explanations)
        # The metadata_url is presigned and expires — fetch it immediately while it's valid
        metadata_url = (results_resp.get("results") or {}).get("metadata_url")
        if metadata_url:
            try:
                logger.info(f"[{run_id}] Fetching per-cell metadata...")
                meta_resp = requests.get(metadata_url, timeout=60)
                meta_resp.raise_for_status()
                (run_dir / "metadata.json").write_text(meta_resp.text)
                logger.info(f"[{run_id}] Metadata saved ({len(meta_resp.content):,} bytes)")
            except Exception as e:
                logger.warning(f"[{run_id}] Could not fetch metadata: {e}")
        else:
            logger.warning(f"[{run_id}] No metadata_url in results response")

        run_result["status"] = "completed"
        logger.info(
            f"[{run_id}] Done. Preview: {run_result['preview_elapsed_s']}s, "
            f"Validation: {run_result['validation_elapsed_s']}s"
        )

    except Exception as exc:
        run_result["status"] = "error"
        run_result["error"] = str(exc)
        logger.error(f"[{run_id}] FAILED: {exc}")

    run_result["total_elapsed_s"] = round(time.time() - t0, 1)
    run_result["finished_at"] = datetime.utcnow().isoformat() + "Z"

    # 8. Enrich with DynamoDB actual costs (only possible after run completes)
    # estimated_eliyahu_cost  = full-table cost estimate from preview (no caching distortion)
    # eliyahu_cost_validation = actual cost paid for the validation run (cached rows cheaper)
    # quoted_cost             = what user was charged ($2 minimum applies)
    if run_result.get("session_id") and run_result.get("status") == "completed":
        logger.info(f"[{run_id}] Fetching DynamoDB cost data...")
        dynamo = fetch_dynamo_costs(run_result["session_id"])
        if dynamo:
            run_result["dynamo"] = dynamo
            # Convenience top-level aliases used by analyze_results.py
            run_result["estimated_eliyahu_cost"] = dynamo.get("estimated_eliyahu_cost", 0.0)
            run_result["eliyahu_cost_validation"] = dynamo.get("eliyahu_cost_validation", 0.0)
            run_result["eliyahu_cost_total"] = dynamo.get("eliyahu_cost_total", 0.0)
            run_result["quoted_cost"] = dynamo.get("quoted_cost", 0.0)
            run_result["provider_costs"] = dynamo.get("provider_costs", {})

    # Save run metadata (includes DynamoDB costs if fetched)
    (run_dir / "run_meta.json").write_text(json.dumps(run_result, indent=2))
    return run_result


def _summarize_results(results_resp: Dict) -> Dict:
    """Extract compact summary from full results response."""
    summary = results_resp.get("summary") or {}
    job_info = results_resp.get("job_info") or {}
    return {
        "rows_processed": summary.get("rows_processed"),
        "columns_validated": summary.get("columns_validated"),
        "cost_usd": summary.get("cost_usd"),
        "run_time_seconds": job_info.get("run_time_seconds"),
    }


# ---------------------------------------------------------------------------
# DynamoDB cost enrichment
# ---------------------------------------------------------------------------

def _float(v: Any) -> float:
    """Convert Decimal/str/None to float safely."""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def fetch_dynamo_costs(session_id: str) -> Dict:
    """
    Query perplexity-validator-runs for a session and return detailed cost data.

    Returns a dict with:
        eliyahu_cost_validation   — actual cost we paid for the full validation run
        eliyahu_cost_preview      — actual cost we paid for the preview run
        eliyahu_cost_total        — sum of the two
        quoted_cost               — what the user was charged (includes $2 min)
        estimated_eliyahu_cost    — estimated full-table cost from the preview (no caching)
        provider_costs            — {provider_name: {actual, estimated, calls}} for validation run
        models_used               — raw models field from validation run
        preview_run_time_s        — actual run time of the preview
        validation_run_time_s     — actual run time of the validation
    """
    try:
        import boto3
        from boto3.dynamodb.conditions import Key
    except ImportError:
        logger.warning("boto3 not available — skipping DynamoDB cost enrichment")
        return {}

    try:
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.Table("perplexity-validator-runs")
        resp = table.query(KeyConditionExpression=Key("session_id").eq(session_id))
        items = resp.get("Items", [])
    except Exception as e:
        logger.warning(f"DynamoDB query failed for {session_id}: {e}")
        return {}

    if not items:
        logger.warning(f"No DynamoDB records found for session {session_id}")
        return {}

    preview_item = next((i for i in reversed(items) if str(i.get("run_key", "")).startswith("Preview")), None)
    val_item = next((i for i in items if str(i.get("run_key", "")).startswith("Validation")), None)

    result = {
        "eliyahu_cost_validation": 0.0,
        "eliyahu_cost_preview": 0.0,
        "eliyahu_cost_total": 0.0,
        "quoted_cost": 0.0,
        "estimated_eliyahu_cost": 0.0,
        "provider_costs": {},
        "models_used": "",
        "preview_run_time_s": 0.0,
        "validation_run_time_s": 0.0,
    }

    if preview_item:
        result["eliyahu_cost_preview"] = _float(preview_item.get("eliyahu_cost", 0))
        result["quoted_cost"] = _float(preview_item.get("quoted_validation_cost", 0))
        result["estimated_eliyahu_cost"] = _float(preview_item.get("estimated_validation_eliyahu_cost", 0))
        result["preview_run_time_s"] = _float(preview_item.get("run_time_s", 0))

    if val_item:
        result["eliyahu_cost_validation"] = _float(val_item.get("eliyahu_cost", 0))
        result["validation_run_time_s"] = _float(val_item.get("run_time_s", 0))
        # If preview quoted_cost wasn't set, try validation record
        if not result["quoted_cost"]:
            result["quoted_cost"] = _float(val_item.get("quoted_validation_cost", 0))
        # Provider cost breakdown from validation run
        provider_metrics = val_item.get("provider_metrics") or {}
        for pname, pdata in provider_metrics.items():
            if not isinstance(pdata, dict):
                continue
            if pdata.get("is_metadata_only"):
                continue
            ca = _float(pdata.get("cost_actual", 0))
            ce = _float(pdata.get("cost_estimated", 0))
            calls = _float(pdata.get("calls", 0))
            if ca > 0 or ce > 0:
                result["provider_costs"][pname] = {
                    "cost_actual": round(ca, 6),
                    "cost_estimated": round(ce, 6),
                    "calls": int(calls),
                }
        # Models field
        models_raw = val_item.get("models", "")
        if isinstance(models_raw, dict):
            # Summarize model names from the nested structure
            names = []
            for sg_data in models_raw.values():
                if isinstance(sg_data, dict):
                    m = sg_data.get("mode_model_used", "")
                    if m:
                        names.append(m)
            result["models_used"] = ", ".join(sorted(set(names)))
        else:
            result["models_used"] = str(models_raw)

    result["eliyahu_cost_total"] = round(
        result["eliyahu_cost_preview"] + result["eliyahu_cost_validation"], 6
    )

    logger.info(
        f"  DynamoDB costs: preview=${result['eliyahu_cost_preview']:.4f}, "
        f"validation=${result['eliyahu_cost_validation']:.4f}, "
        f"quoted=${result['quoted_cost']:.2f}, "
        f"providers={list(result['provider_costs'].keys())}"
    )
    return result


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Hyperplexity benchmark runner")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--smoke-test", action="store_true", help="1 run only (test_01 × the-clone × no_qc)")
    mode_group.add_argument("--minimal", action="store_true", help="test_01 × all search models × no_qc (7 runs)")
    mode_group.add_argument("--full", action="store_true", default=True, help="All enabled rows in model_matrix.csv")
    parser.add_argument("--run-ids", nargs="+", metavar="ID", help="Run specific run_ids only (e.g. 001 005)")
    parser.add_argument("--test-id", metavar="TEST_ID", help="Filter to a specific test table (e.g. test_01)")
    parser.add_argument("--resume", action="store_true", help="Skip runs that already have results.json")
    parser.add_argument("--parallel", action="store_true", help="Run all selected runs concurrently")
    parser.add_argument("--max-workers", type=int, default=6, help="Max concurrent workers for --parallel (default: 6)")
    parser.add_argument("--results-dir", type=Path, help="Override results output directory")
    parser.add_argument("--matrix", type=Path, help="Override model matrix CSV (default: model_matrix.csv)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run, do not execute")
    parser.add_argument("--no-cache", action="store_true", help="Bypass S3 cache (sets cache_ttl_days=0 in config)")
    args = parser.parse_args()

    # Resolve mode
    if args.smoke_test:
        mode = "smoke-test"
    elif args.minimal:
        mode = "minimal"
    else:
        mode = "full"

    # Check required env
    api_url = os.environ.get("HYPERPLEXITY_API_URL", "").rstrip("/")
    api_key = os.environ.get("HYPERPLEXITY_API_KEY", "")
    if not api_url or not api_key:
        logger.error(
            "Missing required env vars: HYPERPLEXITY_API_URL and HYPERPLEXITY_API_KEY\n"
            "Set them in environment or create benchmark/.env"
        )
        sys.exit(1)

    # Results directory
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    default_results = BENCHMARK_DIR / "results" / f"run_{timestamp}"
    results_dir = args.results_dir or default_results
    if not args.dry_run:
        results_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Results directory: {results_dir}")
        # Snapshot reference files so the results directory is self-contained
        for src in [
            BENCHMARK_DIR / "ground_truth_verified.csv",
            REPO_ROOT / "src" / "model_config" / "model_control.csv",
        ]:
            if src.exists():
                shutil.copyfile(src, results_dir / src.name)

    # Load and filter matrix
    if args.matrix:
        global MODEL_MATRIX_PATH
        MODEL_MATRIX_PATH = args.matrix if args.matrix.is_absolute() else BENCHMARK_DIR / args.matrix
    matrix = load_model_matrix()
    runs_to_execute = filter_matrix(matrix, mode, args.run_ids, args.test_id)

    if not runs_to_execute:
        logger.error("No runs matched the specified filter. Check model_matrix.csv and --run-ids.")
        sys.exit(1)

    logger.info(f"Mode: {mode} | Runs to execute: {len(runs_to_execute)}"
                + (f" | test_id filter: {args.test_id}" if args.test_id else "")
                + (" | parallel" if args.parallel else ""))
    for r in runs_to_execute:
        gt_marker = " [GT]" if r["is_ground_truth"] else ""
        logger.info(f"  [{r['run_id']}] {r['test_id']} | {r['search_model']} × {r['qc_model']}{gt_marker}")

    if args.dry_run:
        logger.info("--dry-run: exiting without executing runs")
        return

    all_results = []
    all_results_lock = __import__("threading").Lock()

    def _run_and_save(run_row: Dict) -> Dict:
        """Run single benchmark and update the shared summary CSV."""
        thread_client = HyperplexityClient(api_url, api_key)
        result = run_single(run_row, thread_client, results_dir, resume=args.resume, no_cache=args.no_cache)
        with all_results_lock:
            all_results.append(result)
            _write_summary_csv(all_results, results_dir / "summary.csv")
        return result

    if args.parallel and len(runs_to_execute) > 1:
        max_workers = min(len(runs_to_execute), args.max_workers)

        # Two-phase execution: no-QC runs first (warm the search cache), then QC variants.
        # QC runs reuse cached search results from Phase 1, which is the intended production
        # behavior. Running them in parallel would distort timing and may miss cache hits.
        phase1 = [r for r in runs_to_execute if r["qc_model"] == "none"]
        phase2 = [r for r in runs_to_execute if r["qc_model"] != "none"]

        def _run_phase(phase_rows: List[Dict], label: str):
            if not phase_rows:
                return
            workers = min(len(phase_rows), max_workers)
            logger.info(f"{label}: {len(phase_rows)} runs (max_workers={workers})")
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_run_and_save, row): row for row in phase_rows}
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        row = futures[future]
                        logger.error(f"[{row['run_id']}] Unhandled exception in thread: {exc}")

        _run_phase(phase1, "Phase 1 (no-QC, cache warm)")
        _run_phase(phase2, "Phase 2 (QC variants, cache hot)")
    else:
        client = HyperplexityClient(api_url, api_key)
        for run_row in runs_to_execute:
            result = run_single(run_row, client, results_dir, resume=args.resume, no_cache=args.no_cache)
            all_results.append(result)
            _write_summary_csv(all_results, results_dir / "summary.csv")
            # Brief pause between sequential runs to avoid rate-limiting
            if run_row is not runs_to_execute[-1]:
                time.sleep(3)

    # Final summary
    completed = sum(1 for r in all_results if r.get("status") == "completed")
    errors = sum(1 for r in all_results if r.get("status") == "error")
    skipped = sum(1 for r in all_results if r.get("skipped"))
    logger.info(
        f"\n{'='*60}\nBenchmark complete.\n"
        f"  Completed: {completed} | Errors: {errors} | Skipped: {skipped}\n"
        f"  Results: {results_dir}\n{'='*60}"
    )

    if errors:
        sys.exit(1)


def _write_summary_csv(results: List[Dict], path: Path):
    if not results:
        return
    fields = [
        "run_id", "test_id", "search_model", "qc_model", "is_ground_truth",
        "complexity_tier", "status", "error", "preview_elapsed_s",
        "validation_elapsed_s", "total_elapsed_s", "preview_cost",
        "validation_cost", "session_id",
    ]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)


if __name__ == "__main__":
    main()
