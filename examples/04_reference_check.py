#!/usr/bin/env python3
"""
Example 4: Fact-check text or a document corpus with Chex (reference_check)

Checks factual claims and citations against authoritative sources.
Returns a structured report of what checks out, what doesn't, and with
what confidence.

Accepts:
  - Inline text (single claim, paragraph, or full report)
  - A single file (txt, PDF, etc.) uploaded to Hyperplexity
  - Multiple files — upload each and pass the last s3_key, or concatenate text

Usage:
    export HYPERPLEXITY_API_KEY=hpx_live_your_key_here

    # Fact-check inline text
    python 04_reference_check.py --text "Bitcoin was created by Satoshi Nakamoto in 2009."

    # Fact-check a text file
    python 04_reference_check.py --file analyst_report.txt

    # Fact-check a PDF
    python 04_reference_check.py --file research_paper.pdf

    # Fact-check multiple documents — concatenate text
    cat doc1.txt doc2.txt | python 04_reference_check.py --stdin

Requirements: pip install requests
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import hyperplexity_client as hpx


def main(text: str = "", file_path: str = "") -> None:
    print("\n=== Hyperplexity: Reference Check (Chex) ===\n")

    s3_key = None

    if file_path:
        # ------------------------------------------------------------------
        # Upload the document first, then use its s3_key
        # ------------------------------------------------------------------
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            file_type = "pdf"
        elif ext in (".xlsx", ".xls"):
            file_type = "excel"
        elif ext in (".csv",):
            file_type = "csv"
        else:
            file_type = "pdf"  # treat unknown as generic binary (PDF path)

        print(f"[1/4] Uploading {os.path.basename(file_path)}...")
        upload = hpx.upload_file(file_path, file_type)
        s3_key = upload["s3_key"]
        session_id = upload.get("session_id")
        print(f"  s3_key: {s3_key}")

    elif text:
        print(f"[1/4] Text input: {text[:120]}{'...' if len(text) > 120 else ''}")
        session_id = None

    else:
        print("Error: provide --text, --file, or --stdin")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 2: Submit reference check job
    #
    # The reference check runs in two phases:
    #   Phase 1 (free):    claim extraction — pauses at status=preview_complete
    #   Phase 2 (charged): claim validation — triggered by POST /jobs/{id}/validate
    #
    # Pass auto_approve=True (used below) to skip the approval gate and run
    # straight through. Remove it if you want to review claims_summary and
    # cost_estimate before being charged.
    # ------------------------------------------------------------------
    print("\n[2/4] Submitting reference check job...")
    payload: dict = {"auto_approve": True}
    if text:
        payload["text"] = text
    if s3_key:
        payload["s3_key"] = s3_key
    if session_id:
        payload["session_id"] = session_id

    job_data = hpx.post("/jobs/reference-check", json=payload)
    job_id = job_data.get("job_id")
    print(f"  Job queued: {job_id}")

    # ------------------------------------------------------------------
    # Step 3: Wait for completion
    # (auto_approve=True means we go straight to completed;
    #  without it, poll would stop at preview_complete — then call
    #  hpx.approve_and_wait(job_id, cost) to trigger Phase 2)
    # ------------------------------------------------------------------
    print("\n[3/4] Processing claims...")
    completed = hpx.poll_job(job_id, terminal=("completed", "failed"), timeout=1800)

    if completed.get("status") == "failed":
        print(f"  Job failed: {completed.get('error', {}).get('message')}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Results — available via /results (CSV + viewer) or /reference-results
    # ------------------------------------------------------------------
    print("\n[4/4] Fetching results...")
    results = hpx.get(f"/jobs/{job_id}/results")

    results_data = results.get("results", {})
    download_url = results_data.get("download_url") or results.get("download_url")
    viewer_url = results_data.get("interactive_viewer_url") or results.get("interactive_viewer_url")

    print("\n=== Reference Check Complete ===")
    if download_url:
        print(f"  Download CSV: {download_url}")
        print(f"  (Columns: Claim ID, Statement, Reference, Supporting Data, Support Level, Validation Notes)")
    else:
        import json
        print(json.dumps(results, indent=2))

    if viewer_url:
        print(f"  Viewer URL:   {viewer_url}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Fact-check text or a document with Hyperplexity Chex"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="Inline text to fact-check")
    group.add_argument("--file", help="Path to a text file, PDF, or document to fact-check")
    group.add_argument(
        "--stdin",
        action="store_true",
        help="Read text from stdin (pipe multiple files with `cat`)",
    )
    args = parser.parse_args()

    if args.stdin:
        text = sys.stdin.read().strip()
        main(text=text)
    elif args.text:
        main(text=args.text)
    else:
        main(file_path=args.file)
