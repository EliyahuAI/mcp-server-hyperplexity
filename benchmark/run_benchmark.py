#!/usr/bin/env python3
"""
run_benchmark.py — Benchmark orchestrator for Hyperplexity validation quality.

Runs all combinations defined in model_matrix.csv against the 5 esoteric-science
test datasets, collects results + model_snapshot.csv per run, and saves everything
to a timestamped results/ directory.

Usage:
    python benchmark/run_benchmark.py --smoke-test              # 1 run: test_01 × the-clone × no_qc
    python benchmark/run_benchmark.py --minimal                 # test_01 × all 7 search models
    python benchmark/run_benchmark.py --full                    # all 46 runs in model_matrix.csv
    python benchmark/run_benchmark.py --full --resume           # skip runs that already have results.json
    python benchmark/run_benchmark.py --run-ids 001 005 016     # specific run IDs only

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
import sys
import time
from datetime import datetime
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
                  "upload_id": upload_id, "filename": filename},
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
def make_config(base_config: Dict, search_model: str, qc_model: str, web_searches: int) -> Dict:
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


def filter_matrix(rows: List[Dict], mode: str, run_ids: Optional[List[str]] = None) -> List[Dict]:
    if run_ids:
        return [r for r in rows if r["run_id"] in run_ids and r["enabled"]]
    if mode == "smoke-test":
        # Exactly 1 run: test_01 × the-clone × no_qc
        return [r for r in rows if r["test_id"] == "test_01" and r["search_model"] == "the-clone"
                and r["qc_model"] == "none" and r["enabled"]][:1]
    if mode == "minimal":
        # test_01 × all search models × qc=none only
        return [r for r in rows if r["test_id"] == "test_01" and r["qc_model"] == "none" and r["enabled"]]
    # full
    return [r for r in rows if r["enabled"]]


# ---------------------------------------------------------------------------
# Single run execution
# ---------------------------------------------------------------------------
def run_single(
    row: Dict,
    client: HyperplexityClient,
    results_dir: Path,
    resume: bool = False,
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
    csv_path = TEST_DATA_DIR / f"{test_id}_*.csv"
    # Find actual file
    csv_files = list(TEST_DATA_DIR.glob(f"{test_id}_*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV found for {test_id} in {TEST_DATA_DIR}")
    csv_path = csv_files[0]

    config_path = TEST_CONFIGS_DIR / f"{test_id}_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"No base config found: {config_path}")
    base_config = json.loads(config_path.read_text())

    # Build config
    config = make_config(base_config, search_model, qc_model, web_searches)
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
        run_result["preview_cost"] = cost_est.get("total_cost") or cost_est.get("preview_cost")
        run_result["estimated_validation_time_s"] = cost_est.get("estimated_validation_time_seconds")

        # Capture model snapshot S3 key hint (may appear in status response)
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

        # Save full results
        results_file.write_text(json.dumps(results_resp, indent=2))

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

    # Save run metadata
    (run_dir / "run_meta.json").write_text(json.dumps(run_result, indent=2))
    return run_result


def _summarize_results(results_resp: Dict) -> Dict:
    """Extract compact summary from full results response."""
    rows = results_resp.get("rows") or results_resp.get("data") or []
    return {
        "row_count": len(rows),
        "columns": list(rows[0].keys()) if rows else [],
        "sample": rows[:2] if rows else [],
    }


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
    parser.add_argument("--resume", action="store_true", help="Skip runs that already have results.json")
    parser.add_argument("--results-dir", type=Path, help="Override results output directory")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run, do not execute")
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

    # Load and filter matrix
    matrix = load_model_matrix()
    runs_to_execute = filter_matrix(matrix, mode, args.run_ids)

    if not runs_to_execute:
        logger.error("No runs matched the specified filter. Check model_matrix.csv and --run-ids.")
        sys.exit(1)

    logger.info(f"Mode: {mode} | Runs to execute: {len(runs_to_execute)}")
    for r in runs_to_execute:
        gt_marker = " [GT]" if r["is_ground_truth"] else ""
        logger.info(f"  [{r['run_id']}] {r['test_id']} | {r['search_model']} × {r['qc_model']}{gt_marker}")

    if args.dry_run:
        logger.info("--dry-run: exiting without executing runs")
        return

    client = HyperplexityClient(api_url, api_key)
    all_results = []

    for run_row in runs_to_execute:
        result = run_single(run_row, client, results_dir, resume=args.resume)
        all_results.append(result)

        # Write running summary CSV after each run
        _write_summary_csv(all_results, results_dir / "summary.csv")

        # Brief pause between runs to avoid rate-limiting
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
