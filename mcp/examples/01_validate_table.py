#!/usr/bin/env python3
"""
Example 1: Validate an existing table — AI interview → preview → refine → full validation

Workflow:
  1. Upload Excel/CSV file
  2. Confirm upload — if a strong config match is found (score ≥ 0.85), reuse it;
     otherwise the AI interview auto-starts to generate a new validation config
  3. Drive the interview (answer AI questions in the terminal)
  4. Wait for the preview (auto-queued after interview completes)
  5. Optionally refine the config with natural language instructions
  6. Approve full validation (charges credits)
  7. Download results

Usage:
    export HYPERPLEXITY_API_KEY=hpx_live_your_key_here
    python 01_validate_table.py path/to/your_table.xlsx

Requirements: pip install requests
"""

import sys
import os

# Make sure we can import the shared client from this directory
sys.path.insert(0, os.path.dirname(__file__))
import hyperplexity_client as hpx


def main(file_path: str, refine_instructions: str = "") -> None:
    print(f"\n=== Hyperplexity: Validate Table ===")
    print(f"File: {file_path}\n")

    # Detect file type
    ext = os.path.splitext(file_path)[1].lower()
    file_type = "csv" if ext == ".csv" else "excel"

    # ------------------------------------------------------------------
    # Step 1: Upload file
    # ------------------------------------------------------------------
    print("[1/6] Uploading file...")
    upload = hpx.upload_file(file_path, file_type)
    session_id = upload["session_id"]
    s3_key = upload["s3_key"]
    filename = upload["filename"]

    # ------------------------------------------------------------------
    # Step 2: Confirm upload — check for existing config matches
    # ------------------------------------------------------------------
    print("\n[2/6] Confirming upload and checking for matching configs...")
    confirm = hpx.confirm_upload(session_id, s3_key, filename)

    config_id = None
    conversation_id = confirm.get("conversation_id")
    matches = confirm.get("matches") or confirm.get("config_matches") or []

    if matches:
        best = max(matches, key=lambda m: m.get("match_score", 0))
        score = best.get("match_score", 0)
        if score >= 0.85:
            config_id = best.get("config_id")
            print(f"  Found matching config (score={score:.2f}): {config_id}")
        else:
            print(f"  Best config match score {score:.2f} < 0.85 — proceeding with AI interview")

    if not config_id and not conversation_id:
        # Shouldn't happen — confirm always returns one or the other
        raise RuntimeError("No config match and no conversation_id returned from confirm_upload")

    # ------------------------------------------------------------------
    # Step 3: If no config match, drive the AI interview
    # ------------------------------------------------------------------
    if config_id:
        # Reuse existing config — create preview job directly
        print(f"\n[3/6] Using existing config {config_id} — creating preview job...")
        job_data = hpx.post("/jobs", json={
            "session_id": session_id,
            "config_id": config_id,
            "preview_rows": 3,
        })
        job_id = job_data.get("job_id", session_id)
        print(f"  Preview job queued: {job_id}")
    else:
        # Drive the upload interview
        print(f"\n[3/6] Starting AI interview (conversation: {conversation_id})...")
        print("  Answer the AI's questions to configure validation for your table.")
        print("  (Press Enter to accept defaults, or type your answer)\n")
        hpx.drive_interview(conversation_id, session_id)
        job_id = session_id  # preview is auto-queued; job_id == session_id

    # ------------------------------------------------------------------
    # Step 4: Wait for preview to complete
    # ------------------------------------------------------------------
    print(f"\n[4/6] Waiting for preview (job: {job_id})...")
    preview = hpx.poll_job(job_id, terminal=("preview_complete", "failed"), timeout=600)

    if preview.get("status") == "failed":
        print(f"  Preview failed: {preview.get('error', {}).get('message')}")
        sys.exit(1)

    # Show inline preview table if available
    preview_table = preview.get("preview_table")
    if preview_table:
        print("\n  Preview results:")
        print(preview_table)

    cost_estimate = preview.get("cost_estimate", {})
    cost_usd = cost_estimate.get("estimated_total_cost_usd", 0)
    row_count = cost_estimate.get("estimated_rows", "?")
    print(f"\n  Estimated cost: ${cost_usd:.2f} for ~{row_count} rows")

    # Get conversation_id for refinement (from preview data or confirm)
    refine_conv_id = (
        preview.get("conversation_id")
        or preview.get("refine_session")
        or conversation_id
    )

    # ------------------------------------------------------------------
    # Step 5: Optionally refine the config
    # ------------------------------------------------------------------
    if refine_instructions:
        print(f"\n[5/6] Refining config: {refine_instructions!r}")
        if refine_conv_id:
            hpx.post(f"/conversations/{refine_conv_id}/refine-config", json={
                "session_id": session_id,
                "instructions": refine_instructions,
            })
            # Wait for refined preview
            print("  Waiting for updated preview...")
            preview = hpx.poll_job(job_id, terminal=("preview_complete", "failed"), timeout=600)
            cost_estimate = preview.get("cost_estimate", {})
            cost_usd = cost_estimate.get("estimated_total_cost_usd", 0)
            print(f"  Updated cost estimate: ${cost_usd:.2f}")
        else:
            print("  No conversation_id available for refinement — skipping")
    else:
        print("\n[5/6] Skipping refinement (pass --refine 'instructions' to refine config)")

    # ------------------------------------------------------------------
    # Step 6: Approve full validation
    # ------------------------------------------------------------------
    print(f"\n[6/6] Approve full validation for ${cost_usd:.2f}?")
    answer = input("  Type 'yes' to approve and charge your account: ").strip().lower()
    if answer != "yes":
        print("  Aborted. Preview data is saved — you can approve later via the API.")
        return

    completed = hpx.approve_and_wait(job_id, cost_usd)

    if completed.get("status") == "failed":
        print(f"  Validation failed: {completed.get('error', {}).get('message')}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    results = hpx.get_results(job_id)
    r = results.get("results", {})
    summary = results.get("summary", {})

    print("\n=== Complete ===")
    print(f"  Rows processed : {summary.get('rows_processed', '?')}")
    print(f"  Cost charged   : ${summary.get('cost_usd', 0):.2f}")

    # For humans — view results in browser (must be logged in) or download Excel
    print(f"\n  [Human] Interactive viewer : {r.get('interactive_viewer_url', 'N/A')}")
    print(f"  [Human] Download Excel     : {r.get('download_url', 'N/A')}")

    # For AI agents — survey the preview_table markdown first (available at preview_complete),
    # then use metadata.json for per-cell details with _row_key cross-references.
    metadata_url = r.get("metadata_url")
    if metadata_url:
        print(f"\n  [AI]    metadata_url: {metadata_url}")
        print("  Fetch metadata_url → parse rows[].cells[col].full_value / confidence / comment")
        print("  Use rows[].row_key to cross-reference with the markdown preview table.")
        # Optional: fetch and print a quick summary
        # metadata = hpx.fetch_table_metadata(metadata_url)
        # for row in metadata.get("rows", []):
        #     print(f"  Row {row['row_key'][:8]}...: {list(row['cells'].keys())}")
    else:
        print("\n  [AI]    metadata_url: N/A")

    config_id_out = results.get("job_info", {}).get("configuration_id")
    if config_id_out:
        print(f"\n  Config ID for future runs: {config_id_out}")
        print("  Pass this as config_id to skip the interview next time.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Validate a table with Hyperplexity")
    parser.add_argument("file", help="Path to Excel (.xlsx) or CSV file to validate")
    parser.add_argument(
        "--refine",
        default="",
        metavar="INSTRUCTIONS",
        help="Natural language config refinement after preview "
             "(e.g. 'Add LinkedIn URL column. Remove revenue.')",
    )
    args = parser.parse_args()
    main(args.file, args.refine)
