#!/usr/bin/env python3
"""
Example 3: Update Table — re-run validation on a completed job

This is the equivalent of the "Update Table" button in the Hyperplexity viewer.
No manual edits or re-upload required — the table iterates automatically,
re-validating the existing data with the same config.

Workflow:
  1. Pass the source job ID of a completed validation.
  2. Hyperplexity re-validates the enriched output with the same config.
  3. A new preview job is queued automatically.
  4. Review and approve as usual.

If you want to incorporate manual edits to the output, re-upload the edited
file via upload_file + confirm_upload — a matching config will be found.

Usage:
    export HYPERPLEXITY_API_KEY=hpx_live_your_key_here
    python 03_update_table.py session_20260217_103045_abc123

    # Pin to a specific result version:
    python 03_update_table.py session_20260217_103045_abc123 --version 2

Requirements: pip install requests
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import hyperplexity_client as hpx


def main(source_job_id: str, source_version: int | None = None) -> None:
    print("\n=== Hyperplexity: Update Table ===")
    print(f"Source job: {source_job_id}")
    if source_version is not None:
        print(f"Source version: {source_version}")
    print()

    # ------------------------------------------------------------------
    # Step 1: Create update job
    # ------------------------------------------------------------------
    print("[1/3] Creating update job...")
    payload: dict = {"source_job_id": source_job_id}
    if source_version is not None:
        payload["source_version"] = source_version

    update = hpx.post("/jobs/update-table", json=payload)
    new_job_id = update.get("job_id")
    print(f"  New job queued: {new_job_id}")

    warning = update.get("warning")
    if warning:
        print(f"  Warning: {warning}")

    # ------------------------------------------------------------------
    # Step 2: Wait for preview
    # ------------------------------------------------------------------
    print(f"\n[2/3] Waiting for preview...")
    preview = hpx.poll_job(new_job_id, terminal=("preview_complete", "failed"), timeout=600)

    if preview.get("status") == "failed":
        print(f"  Preview failed: {preview.get('error', {}).get('message')}")
        sys.exit(1)

    preview_table = preview.get("preview_table")
    if preview_table:
        print("\n  Preview (first few rows):")
        print(preview_table)

    cost_estimate = preview.get("cost_estimate", {})
    cost_usd = cost_estimate.get("estimated_total_cost_usd", 0)
    row_count = cost_estimate.get("estimated_rows", "?")
    print(f"\n  Estimated cost: ${cost_usd:.2f} for ~{row_count} rows")

    # ------------------------------------------------------------------
    # Step 3: Approve full validation
    # ------------------------------------------------------------------
    print(f"\n[3/3] Approve full validation for ${cost_usd:.2f}?")
    answer = input("  Type 'yes' to approve and charge your account: ").strip().lower()
    if answer != "yes":
        print("  Aborted.")
        return

    completed = hpx.approve_and_wait(new_job_id, cost_usd)

    if completed.get("status") == "failed":
        print(f"  Validation failed: {completed.get('error', {}).get('message')}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    results = hpx.get_results(new_job_id)
    r = results.get("results", {})
    summary = results.get("summary", {})

    print("\n=== Complete ===")
    print(f"  Rows processed : {summary.get('rows_processed', '?')}")
    print(f"  Cost charged   : ${summary.get('cost_usd', 0):.2f}")
    print(f"  New job ID     : {new_job_id}")

    # For humans — view results in browser (must be logged in) or download Excel
    print(f"\n  [Human] Interactive viewer : {r.get('interactive_viewer_url', 'N/A')}")
    print(f"  [Human] Download Excel     : {r.get('download_url', 'N/A')}")

    # For AI agents — use metadata_url to read per-cell results with citations
    metadata_url = r.get("metadata_url")
    if metadata_url:
        print(f"\n  [AI]    metadata_url: {metadata_url}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Re-validate an enriched table after analyst corrections"
    )
    parser.add_argument("source_job_id", help="Job ID of the completed source validation")
    parser.add_argument(
        "--version",
        type=int,
        default=None,
        metavar="N",
        help="Pin to a specific result version (default: latest)",
    )
    args = parser.parse_args()
    main(args.source_job_id, args.version)
