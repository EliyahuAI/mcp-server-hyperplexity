#!/usr/bin/env python3
"""
Example 2: Generate a validated research table from a prompt (Table Maker)

Workflow:
  1. Start a Table Maker conversation with a natural language description
  2. Answer any clarifying questions from the AI
  3. Table builds and preview is auto-queued — wait for preview_complete
  4. Approve full validation (charges credits)
  5. Download the generated + validated table

Usage:
    export HYPERPLEXITY_API_KEY=hpx_live_your_key_here
    python 02_generate_table.py "Top 10 US hedge funds: fund name, AUM, strategy, HQ city"

    # Or with a longer description piped from stdin:
    python 02_generate_table.py --prompt-file my_table_spec.txt

    # Fire-and-forget: skip all AI questions and generate immediately from the prompt
    python 02_generate_table.py --auto-start "Top 10 US hedge funds: fund name, AUM, strategy, HQ city"

Requirements: pip install requests
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import hyperplexity_client as hpx


def main(prompt: str, auto_start: bool = False) -> None:
    print("\n=== Hyperplexity: Generate Table ===")
    print(f"Prompt: {prompt[:120]}{'...' if len(prompt) > 120 else ''}\n")
    if auto_start:
        print("Auto-start mode: skipping Q&A, generating table directly\n")

    # ------------------------------------------------------------------
    # Step 1: Start the Table Maker conversation
    # ------------------------------------------------------------------
    print("[1/4] Starting Table Maker...")
    body: dict = {"message": prompt}
    if auto_start:
        body["auto_start"] = True
    data = hpx.post("/conversations/table-maker", json=body)
    conversation_id = data.get("conversation_id")
    session_id = data.get("session_id")
    print(f"  Conversation: {conversation_id}")
    print(f"  Session: {session_id}")

    if not conversation_id or not session_id:
        raise RuntimeError(f"Unexpected response: {data}")

    # ------------------------------------------------------------------
    # Step 2: Drive the conversation (answer AI questions)
    # With auto_start=True the AI outputs trigger_execution immediately —
    # the first poll returns trigger_execution=True and the loop exits.
    # ------------------------------------------------------------------
    if auto_start:
        print("\n[2/4] Waiting for table generation (auto-start, no Q&A)...")
    else:
        print("\n[2/4] Building table — answer any AI questions below.")
        print("  (The AI may ask about scope, data sources, or column details)\n")

    while True:
        conv = hpx.poll_conversation(conversation_id, session_id, timeout=900)

        if conv.get("trigger_execution"):
            print("  Table build complete — preview is auto-queued.")
            break

        if conv.get("user_reply_needed"):
            if auto_start:
                # Shouldn't happen with auto_start, but handle gracefully
                print("  (Unexpected question in auto-start mode — skipping with best-judgment)")
                hpx.post(f"/conversations/{conversation_id}/message", json={
                    "session_id": session_id,
                    "message": "Please proceed with your best judgment.",
                })
                continue
            ai_msg = conv.get("last_ai_message", "")
            # last_ai_message may be a JSON string
            if isinstance(ai_msg, str) and ai_msg.startswith("{"):
                import json
                try:
                    parsed = json.loads(ai_msg)
                    ai_msg = parsed.get("ai_message") or parsed.get("content") or ai_msg
                except Exception:
                    pass
            print(f"\n  AI: {ai_msg}")
            reply = input("  Your reply (or press Enter to skip): ").strip()
            if reply:
                hpx.post(f"/conversations/{conversation_id}/message", json={
                    "session_id": session_id,
                    "message": reply,
                })
            else:
                # Send a blank confirm to proceed
                hpx.post(f"/conversations/{conversation_id}/message", json={
                    "session_id": session_id,
                    "message": "Please proceed with your best judgment.",
                })

    # ------------------------------------------------------------------
    # Step 3: Wait for preview
    # Preview is auto-queued after the table maker finishes.
    # Do NOT call create_job() — use session_id as the job_id.
    # ------------------------------------------------------------------
    print(f"\n[3/4] Waiting for preview (job_id = session_id = {session_id})...")
    preview = hpx.poll_job(session_id, terminal=("preview_complete", "failed"), timeout=1800)

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
    # Step 4: Approve full validation
    # ------------------------------------------------------------------
    print(f"\n[4/4] Approve full validation for ${cost_usd:.2f}?")
    answer = input("  Type 'yes' to approve and charge your account: ").strip().lower()
    if answer != "yes":
        print("  Aborted. You can approve later via the API or web UI.")
        return

    completed = hpx.approve_and_wait(session_id, cost_usd)

    if completed.get("status") == "failed":
        print(f"  Validation failed: {completed.get('error', {}).get('message')}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    results = hpx.get_results(session_id)
    r = results.get("results", {})
    summary = results.get("summary", {})

    print("\n=== Complete ===")
    print(f"  Rows generated  : {summary.get('rows_processed', '?')}")
    print(f"  Cost charged    : ${summary.get('cost_usd', 0):.2f}")

    # For humans — view results in browser (must be logged in) or download Excel
    print(f"\n  [Human] Interactive viewer : {r.get('interactive_viewer_url', 'N/A')}")
    print(f"  [Human] Download Excel     : {r.get('download_url', 'N/A')}")

    # For AI agents — use metadata_url (table_metadata.json) which contains all rows
    # with per-cell confidence ratings, validator explanations, and citations.
    # Use rows[].row_key to cross-reference with the preview markdown table.
    metadata_url = r.get("metadata_url")
    if metadata_url:
        print(f"\n  [AI]    metadata_url: {metadata_url}")
        print("  Fetch metadata_url → rows[].cells[col].full_value, .confidence, .comment.sources")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate a validated research table")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("prompt", nargs="?", help="Table description in natural language")
    group.add_argument(
        "--prompt-file",
        metavar="FILE",
        help="Path to a text file containing the table description",
    )
    parser.add_argument(
        "--auto-start",
        action="store_true",
        default=False,
        help="Skip clarifying Q&A and generate the table directly from the prompt. "
             "The AI uses its best judgment for any unspecified details.",
    )
    args = parser.parse_args()

    if args.prompt_file:
        with open(args.prompt_file) as f:
            prompt = f.read().strip()
    else:
        prompt = args.prompt

    main(prompt, auto_start=args.auto_start)
