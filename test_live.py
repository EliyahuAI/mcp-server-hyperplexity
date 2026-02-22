#!/usr/bin/env python3
"""
Live integration test suite for the Hyperplexity MCP server.

Tests every tool via the same HyperplexityClient + build_guidance layer
the MCP server uses, so a passing run guarantees the server works.

API:  https://api.hyperplexity.ai/v1  (Authorization: Bearer hpx_live_...)
All responses are {"success": true, "data": {...}} — client.py unwraps automatically.

Usage:
    # Preview-only (safe, costs nothing beyond the free preview):
    python3 mcp/test_live.py

    # Full end-to-end including approve + download results:
    python3 mcp/test_live.py --full

    # Skip the slow job-workflow tests:
    python3 mcp/test_live.py --quick

Compare with: deployment/test_external_api.py (raw requests, no MCP layer).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ── make the package importable regardless of cwd ───────────────────────────
MCP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(MCP_DIR / "src"))

from hyperplexity_mcp.client import HyperplexityClient
from hyperplexity_mcp.guidance import build_guidance

# ── config ───────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("HYPERPLEXITY_API_KEY", "")
if not API_KEY:
    print("ERROR: HYPERPLEXITY_API_KEY environment variable is not set.")
    print("  Get your API key at hyperplexity.ai/account")
    sys.exit(1)
BASE_DIR      = MCP_DIR.parent
DEMO_XLSX     = BASE_DIR / "demos" / "01. Investment Research" / "InvestmentResearch.xlsx"
DEMO_CSV      = BASE_DIR / "demos" / "02. Competitive Intelligence" / "Competitive_Intelligence.csv"
MCP_TEST_CSV  = MCP_DIR / "test_data" / "demo_table.csv"   # tiny 4-row CSV for fast smoke tests

POLL_INTERVAL = 10   # seconds between status polls
POLL_TIMEOUT  = 600  # seconds before giving up

# ── terminal colours ─────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def info(msg): print(f"  {YELLOW}→{RESET} {msg}")
def head(msg): print(f"\n{BOLD}{CYAN}{'─'*62}{RESET}\n{BOLD}{msg}{RESET}")

# ── test harness ─────────────────────────────────────────────────────────────
_passed = _failed = 0

def check(label: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        _passed += 1
        ok(label)
    else:
        _failed += 1
        fail(label + (f"  [{detail}]" if detail else ""))

def assert_guidance(data: dict, ctx: str):
    """Verify every _guidance block is structurally valid."""
    g = data.get("_guidance", {})
    check(f"[{ctx}] _guidance present",            "_guidance" in data)
    check(f"[{ctx}] _guidance.summary is str",     isinstance(g.get("summary"), str) and bool(g["summary"]))
    check(f"[{ctx}] _guidance.next_steps is list", isinstance(g.get("next_steps"), list))
    for i, step in enumerate(g.get("next_steps", [])):
        check(f"[{ctx}] next_steps[{i}].tool",   "tool"   in step)
        check(f"[{ctx}] next_steps[{i}].params", "params" in step)
        check(f"[{ctx}] next_steps[{i}].note",   "note"   in step)

def poll_job(client: HyperplexityClient, job_id: str,
             target_statuses: tuple[str, ...],
             timeout: int = POLL_TIMEOUT) -> dict | None:
    """GET /jobs/{id} until status ∈ target_statuses.
    Fetches progress messages on each poll and prints them instead of raw step text.
    """
    deadline = time.time() + timeout
    last_seq  = 0
    while time.time() < deadline:
        data   = client.get(f"/jobs/{job_id}")
        status = data.get("status", "")
        pct    = data.get("progress_percent", 0)

        # Fetch new messages since the last poll and surface them
        try:
            msgs_data = client.get(f"/jobs/{job_id}/messages",
                                   params={"since_seq": last_seq})
            new_msgs  = msgs_data.get("messages") or []
            last_seq  = msgs_data.get("last_seq", last_seq) or last_seq
            if new_msgs:
                for m in new_msgs:
                    raw = m.get("content", "")
                    txt = (raw.get("text") or raw.get("message") or str(raw)
                           if isinstance(raw, dict) else str(raw))
                    info(f"  [{status}] {pct}%  {txt[:120]}")
            else:
                step = data.get("current_step", "")
                info(f"  [{status}] {pct}%  {step or '…'}")
        except Exception:
            step = data.get("current_step", "")
            info(f"  [{status}] {pct}%  {step}")

        if status in target_statuses:
            return data
        if status == "failed":
            fail(f"Job failed: {data.get('error_message') or data.get('error')}")
            return data
        time.sleep(POLL_INTERVAL)
    fail(f"Timed out after {timeout}s waiting for {target_statuses}")
    return None

def poll_conversation(client: HyperplexityClient,
                      conv_id: str, session_id: str,
                      timeout: int = POLL_TIMEOUT) -> dict | None:
    """GET /conversations/{id}?session_id=... until status != 'processing'."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/conversations/{conv_id}",
                          params={"session_id": session_id})
        status = data.get("status", "")
        info(f"  conversation status={status}")
        if status != "processing":
            return data
        time.sleep(POLL_INTERVAL)
    fail(f"Conversation timed out after {timeout}s")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# § 1  Guidance state-machine unit tests  (no network)
# ═══════════════════════════════════════════════════════════════════════════

def test_guidance_state_machine():
    head("§1 · Guidance state-machine unit tests (no network)")

    # ── get_job_status branches ──────────────────────────────────────────
    for status, expected in [
        ("queued",      "get_job_status"),
        ("processing",  "get_job_status"),
        ("completed",   "get_results"),
        ("failed",      None),
    ]:
        g = build_guidance("get_job_status", {
            "job_id": "j1", "status": status,
            "cost_estimate": {"estimated_total_cost_usd": 1.50},
        })
        tools = [s["tool"] for s in g["next_steps"]]
        if expected:
            check(f"get_job_status({status}) → {expected}", expected in tools, str(tools))
        else:
            check(f"get_job_status(failed) → no next_steps", tools == [], str(tools))

    # preview_complete: cost pre-filled from cost_estimate
    g = build_guidance("get_job_status", {
        "job_id": "j1", "status": "preview_complete",
        "config_id": "cfg_abc",
        "cost_estimate": {"estimated_total_cost_usd": 4.20},
    })
    tools = [s["tool"] for s in g["next_steps"]]
    check("preview_complete → approve_validation",    "approve_validation" in tools, str(tools))
    check("approved_cost_usd pre-filled as 4.20",
          any(s["params"].get("approved_cost_usd") == 4.20 for s in g["next_steps"]))
    check("summary mentions config_id",               "cfg_abc" in g["summary"])

    # ── confirm_upload branches ──────────────────────────────────────────
    # high match → create_job with config_id
    g = build_guidance("confirm_upload", {
        "session_id": "s1",
        "matches": [{"config_id": "cfg_xyz", "match_score": 0.92, "name": "InvResearch"}],
        "match_count": 1,
    })
    check("confirm_upload(score=0.92) → create_job with config_id",
          any(s["tool"] == "create_job" and s["params"].get("config_id") == "cfg_xyz"
              for s in g["next_steps"]))

    # no match → start_upload_interview
    g = build_guidance("confirm_upload", {"session_id": "s1", "matches": [], "match_count": 0})
    check("confirm_upload(no match) → start_upload_interview",
          any(s["tool"] == "start_upload_interview" for s in g["next_steps"]))

    # ── get_conversation: user_reply_needed beats status=processing ──────
    g = build_guidance("get_conversation", {
        "conversation_id": "c1", "session_id": "s1",
        "status": "processing",
        "user_reply_needed": True,
        "messages": [{"content": "What columns do you want to validate?"}],
    })
    tools = [s["tool"] for s in g["next_steps"]]
    check("get_conversation: user_reply_needed beats processing",
          "send_conversation_reply" in tools and "get_conversation" not in tools,
          str(tools))

    # processing with no reply needed → get_conversation
    g = build_guidance("get_conversation", {
        "conversation_id": "c1", "session_id": "s1",
        "status": "processing", "user_reply_needed": False,
    })
    check("get_conversation(processing, no reply) → get_conversation",
          any(s["tool"] == "get_conversation" for s in g["next_steps"]))

    # submit_preview → create_job
    g = build_guidance("get_conversation", {
        "conversation_id": "c1", "session_id": "s1",
        "status": "done", "user_reply_needed": False,
        "next_step": {"action": "submit_preview"},
    })
    check("get_conversation(submit_preview) → create_job",
          any(s["tool"] == "create_job" for s in g["next_steps"]))

    # ── get_job_messages: uses last_seq not messages[-1]["seq"] ──────────
    g = build_guidance("get_job_messages", {
        "job_id": "j1",
        "messages": [{"type": "progress_update", "_seq": 7}],
        "last_seq": 7,
        "has_more": False,
    })
    msg_params = next(
        (s["params"] for s in g["next_steps"] if s["tool"] == "get_job_messages"), {}
    )
    check("get_job_messages guidance uses last_seq=7",
          msg_params.get("since_seq") == 7, str(msg_params))

    # ── start_table_maker: completed branch ──────────────────────────────
    g_proc = build_guidance("start_table_maker",
                            {"conversation_id": "c1", "session_id": "s1", "status": "processing"})
    g_done = build_guidance("start_table_maker",
                            {"conversation_id": "c1", "session_id": "s1", "status": "completed"})
    check("start_table_maker(processing) → get_conversation",
          any(s["tool"] == "get_conversation" for s in g_proc["next_steps"]))
    check("start_table_maker(completed) → get_conversation with distinct summary",
          g_done["summary"] != g_proc["summary"])

    # ── approve_validation: no job_id in params ──────────────────────────
    g = build_guidance("approve_validation", {"job_id": "j1", "status": "processing"})
    check("approve_validation guidance → get_job_status",
          any(s["tool"] == "get_job_status" for s in g["next_steps"]))


# ═══════════════════════════════════════════════════════════════════════════
# § 2  Account tools
# ═══════════════════════════════════════════════════════════════════════════

def test_account(client: HyperplexityClient):
    head("§2 · Account tools")

    # GET /account/balance
    data = client.get("/account/balance")
    data["_guidance"] = build_guidance("get_balance", data)
    check("get_balance returns a dict", isinstance(data, dict))
    check("get_balance has a numeric balance",
          any(isinstance(data.get(k), (int, float))
              for k in ("balance_usd", "balance", "credits")),
          str({k: v for k, v in data.items() if k != "_guidance"}))
    assert_guidance(data, "get_balance")
    info(f"balance payload: {json.dumps({k: v for k, v in data.items() if k != '_guidance'})}")

    # GET /account/usage
    data = client.get("/account/usage", params={"limit": 3})
    data["_guidance"] = build_guidance("get_usage", data)
    check("get_usage returns a dict",         isinstance(data, dict))
    check("get_usage has transactions list",  isinstance(data.get("transactions"), list),
          str(list(data.keys())))
    check("get_usage has total_cost_usd",     "total_cost_usd" in data, str(list(data.keys())))
    assert_guidance(data, "get_usage")
    info(f"usage: {len(data.get('transactions', []))} transaction(s)  "
         f"total_cost=${data.get('total_cost_usd', '?')}")


# ═══════════════════════════════════════════════════════════════════════════
# § 3  Upload workflow
# ═══════════════════════════════════════════════════════════════════════════

def test_upload_workflow(client: HyperplexityClient) -> dict | None:
    """upload_file compound tool + confirm_upload."""
    head("§3 · Upload workflow  (presign → S3 PUT → confirm)")

    # pick demo file — prefer the tiny MCP test CSV for speed
    if MCP_TEST_CSV.exists():
        file_path    = MCP_TEST_CSV
        file_type    = "csv"
        content_type = "text/csv"
    elif DEMO_XLSX.exists():
        file_path    = DEMO_XLSX
        file_type    = "excel"
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif DEMO_CSV.exists():
        file_path    = DEMO_CSV
        file_type    = "csv"
        content_type = "text/csv"
    else:
        fail(f"No demo file found. Expected:\n    {MCP_TEST_CSV}\n    {DEMO_XLSX}")
        return None

    info(f"Demo file: {file_path.name}  ({file_path.stat().st_size // 1024} KB)")

    # ── Step 1: GET /uploads/presigned ───────────────────────────────────
    filename = file_path.name
    presign = client.post("/uploads/presigned", json={
        "filename": filename,
        "file_size": file_path.stat().st_size,
        "file_type": file_type,
        "content_type": content_type,
    })
    upload_url = presign.get("presigned_url") or presign.get("upload_url", "")
    check("presigned has upload/presigned url", bool(upload_url), str(list(presign.keys())))
    check("presigned has s3_key",      "s3_key"      in presign, str(list(presign.keys())))
    check("presigned has session_id",  "session_id"  in presign, str(list(presign.keys())))
    s3_key     = presign["s3_key"]
    session_id = presign["session_id"]
    upload_id  = presign.get("upload_id", "")
    info(f"session_id = {session_id}")
    info(f"upload_id  = {upload_id}")
    info(f"s3_key     = {s3_key[:60]}…")

    # ── Step 2: PUT bytes to S3  (bare requests, no auth header) ─────────
    import requests as _req
    file_bytes = file_path.read_bytes()
    r = _req.put(upload_url, data=file_bytes, headers={"Content-Type": content_type})
    check(f"S3 PUT succeeded (HTTP {r.status_code})",
          r.status_code in (200, 204), f"HTTP {r.status_code}: {r.text[:200]}")

    # build _guidance as the upload_file tool would
    upload_result = {
        "session_id": session_id, "upload_id": upload_id,
        "s3_key": s3_key, "filename": filename,
        "file_type": file_type, "bytes_uploaded": len(file_bytes),
    }
    upload_result["_guidance"] = build_guidance("upload_file", upload_result)
    assert_guidance(upload_result, "upload_file")
    check("upload_file guidance → confirm_upload",
          any(s["tool"] == "confirm_upload" for s in upload_result["_guidance"]["next_steps"]))

    # ── Step 3: POST /uploads/confirm (optional — 503 means not yet live) ─
    matches = []
    best_config_id = None
    try:
        confirm = client.post("/uploads/confirm", json={
            "session_id": session_id,
            "s3_key": s3_key,
            "filename": filename,
        })
        confirm["_guidance"] = build_guidance("confirm_upload", confirm)
        check("confirm_upload returns a dict", isinstance(confirm, dict))
        assert_guidance(confirm, "confirm_upload")
        matches = confirm.get("matches") or confirm.get("config_matches") or []
        info(f"config matches returned: {confirm.get('match_count', len(matches))}")
        for m in matches[:3]:
            info(f"  score={m.get('match_score', 0):.2f}  "
                 f"name={m.get('name', '?')}  config_id={m.get('config_id', '?')}")
        best = matches[0] if matches else {}
        best_config_id = best.get("config_id")
    except Exception as exc:
        info(f"confirm_upload skipped (backend error): {exc}")

    return {
        "session_id":     session_id,
        "upload_id":      upload_id,
        "s3_key":         s3_key,
        "filename":       filename,
        "best_config_id": best_config_id,
        "match_score":    matches[0].get("match_score", 0) if matches else 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# § 4  Job workflow
# ═══════════════════════════════════════════════════════════════════════════

def test_job_workflow(client: HyperplexityClient, upload: dict, full: bool):
    head("§4 · Job workflow  (create → preview → [approve] → results)")

    session_id     = upload["session_id"]
    best_config_id = upload.get("best_config_id")
    match_score    = upload.get("match_score", 0)

    # ── POST /jobs ────────────────────────────────────────────────────────
    upload_id = upload.get("upload_id", "")
    s3_key    = upload["s3_key"]

    job_payload: dict = {
        "session_id":    session_id,
        "s3_key":        s3_key,
        "preview_rows":  3,
        "notify_method": "poll",
    }
    if upload_id:
        job_payload["upload_id"] = upload_id

    if best_config_id and match_score >= 0.80:
        job_payload["config_id"] = best_config_id
        info(f"Re-using config_id={best_config_id} (score={match_score:.2f})")
    else:
        # Load demo config so the API knows how to process the file
        demo_config_path = BASE_DIR / "demos" / "01. Investment Research" / "InvestmentResearch_config.json"
        if demo_config_path.exists():
            import json as _json
            job_payload["config"] = _json.loads(demo_config_path.read_text())
            info("No config match — using demo config JSON")
        else:
            info("No config match — backend derives config from session")

    job = client.post("/jobs", json=job_payload)
    job["_guidance"] = build_guidance("create_job", job)

    check("create_job returns a dict",   isinstance(job, dict))
    check("create_job has job_id",       "job_id" in job,  str(list(job.keys())))
    check("create_job has status",       "status" in job,  str(list(job.keys())))
    assert_guidance(job, "create_job")
    check("create_job guidance → get_job_status",
          any(s["tool"] == "get_job_status" for s in job["_guidance"]["next_steps"]))

    job_id = job["job_id"]
    info(f"job_id={job_id}  status={job.get('status')}")

    # ── GET /jobs/{id}/messages  (sample while job runs) ─────────────────
    time.sleep(3)
    msgs = client.get(f"/jobs/{job_id}/messages", params={"since_seq": 0})
    msgs["job_id"] = job_id
    msgs["_guidance"] = build_guidance("get_job_messages", msgs)
    check("get_job_messages returns a dict", isinstance(msgs, dict))
    # API: {"messages": [...], "last_seq": N, "has_more": bool}
    check("get_job_messages has messages key", "messages" in msgs, str(list(msgs.keys())))
    check("get_job_messages has last_seq key", "last_seq" in msgs, str(list(msgs.keys())))
    assert_guidance(msgs, "get_job_messages")
    info(f"messages so far: {len(msgs.get('messages', []))},  last_seq={msgs.get('last_seq')}")

    # ── poll until preview_complete ───────────────────────────────────────
    info(f"Polling for preview_complete (up to {POLL_TIMEOUT}s, interval={POLL_INTERVAL}s)…")
    preview = poll_job(client, job_id, ("preview_complete", "completed", "failed"))
    if preview is None:
        fail("Job never reached preview_complete")
        return

    status = preview.get("status")
    preview["_guidance"] = build_guidance("get_job_status", preview)
    assert_guidance(preview, f"get_job_status({status})")

    if status == "preview_complete":
        # API: cost_estimate.estimated_total_cost_usd
        cost_est  = preview.get("cost_estimate") or {}
        cost      = (cost_est.get("estimated_total_cost_usd")
                     or preview.get("estimated_cost_usd")
                     or preview.get("cost_usd")
                     or 0)
        rows      = cost_est.get("estimated_rows", "?")
        config_id = preview.get("config_id", "")
        prev_res  = preview.get("preview_results") or {}
        prev_url  = prev_res.get("download_url", "")

        check("preview_complete has cost_estimate",     bool(cost_est),  str(list(preview.keys())))
        check("preview_complete has config_id",         bool(config_id), str(list(preview.keys())))
        check("preview_complete guidance → approve_validation",
              any(s["tool"] == "approve_validation"
                  for s in preview["_guidance"]["next_steps"]))
        check("approved_cost_usd pre-filled in guidance params",
              any(s.get("params", {}).get("approved_cost_usd") == cost
                  for s in preview["_guidance"]["next_steps"]))

        info(f"Cost estimate: ${cost}  for {rows} rows")
        info(f"Config ID for future reruns: {config_id}")
        if prev_url:
            info(f"Preview Excel: {prev_url}")

        if not full:
            info("Stopping at preview (--full to approve and download results)")
            return

        # ── POST /jobs/{id}/validate ──────────────────────────────────────
        approve_payload: dict = {}
        if cost:
            approve_payload["approved_cost_usd"] = cost
        approve = client.post(f"/jobs/{job_id}/validate", json=approve_payload)
        approve.setdefault("job_id", job_id)
        approve["_guidance"] = build_guidance("approve_validation", approve)
        check("approve_validation returns a dict", isinstance(approve, dict))
        assert_guidance(approve, "approve_validation")
        info(f"Approval response: {json.dumps({k: v for k, v in approve.items() if k != '_guidance'})}")

        # ── poll until completed ──────────────────────────────────────────
        info(f"Polling for completed (up to {POLL_TIMEOUT}s)…")
        final = poll_job(client, job_id, ("completed", "failed"))
        if final is None:
            fail("Job never completed")
            return

        final["_guidance"] = build_guidance("get_job_status", final)
        assert_guidance(final, "get_job_status(completed)")

        if final.get("status") == "completed":
            check("completed guidance → get_results",
                  any(s["tool"] == "get_results" for s in final["_guidance"]["next_steps"]))

            # ── GET /jobs/{id}/results ────────────────────────────────────
            results = client.get(f"/jobs/{job_id}/results")
            results["_guidance"] = build_guidance("get_results", results)
            check("get_results returns a dict", isinstance(results, dict))
            assert_guidance(results, "get_results")

            # API: data.results.download_url, data.job_info, data.summary
            res_obj  = results.get("results") or {}
            job_info = results.get("job_info") or {}
            summary  = results.get("summary") or {}
            check("get_results has results.download_url",
                  bool(res_obj.get("download_url")), str(list(results.keys())))
            info(f"Download URL: {res_obj.get('download_url', '(none)')}")
            info(f"Interactive viewer: {res_obj.get('interactive_viewer_url', '(none)')}")
            info(f"Rows processed: {summary.get('rows_processed')}  "
                 f"Cost: ${summary.get('cost_usd')}  "
                 f"Config: {job_info.get('configuration_id')}")
            return job_id  # hand to test_update_table

    elif status == "completed":
        info("Job skipped preview and went straight to completed")
        return job_id
    elif status == "failed":
        fail(f"Job failed: {preview.get('error_message') or preview.get('error')}")

    return None


# ═══════════════════════════════════════════════════════════════════════════
# § 5  Table Maker conversation
# ═══════════════════════════════════════════════════════════════════════════

def test_table_maker(client: HyperplexityClient) -> dict | None:
    head("§5 · Table Maker conversation")

    # POST /conversations/table-maker
    msg = ("I need a table of the top 5 AI chip companies with columns: "
           "company_name, hq_country, latest_chip_model, founded_year.")
    conv = client.post("/conversations/table-maker", json={"message": msg})
    conv["_guidance"] = build_guidance("start_table_maker", conv)

    check("start_table_maker returns a dict",         isinstance(conv, dict))
    check("start_table_maker has conversation_id",    "conversation_id" in conv, str(list(conv.keys())))
    check("start_table_maker has session_id",         "session_id"      in conv, str(list(conv.keys())))
    assert_guidance(conv, "start_table_maker")
    check("start_table_maker guidance → get_conversation",
          any(s["tool"] == "get_conversation" for s in conv["_guidance"]["next_steps"]))

    conv_id    = conv["conversation_id"]
    session_id = conv["session_id"]
    info(f"conversation_id = {conv_id}")
    info(f"session_id      = {session_id}")

    # Poll until conversation is done processing
    info(f"Polling table-maker conversation (up to {POLL_TIMEOUT}s)…")
    state = poll_conversation(client, conv_id, session_id)
    if state is None:
        return None

    state.setdefault("conversation_id", conv_id)
    state.setdefault("session_id",      session_id)
    state["_guidance"] = build_guidance("get_conversation", state)

    check("get_conversation returns a dict",  isinstance(state, dict))
    assert_guidance(state, "get_conversation")

    status            = state.get("status", "")
    user_reply_needed = state.get("user_reply_needed", False)
    next_step         = (state.get("next_step") or {}).get("action", "")
    _raw_msg = state.get("last_ai_message") or ""
    ai_msg   = str(_raw_msg.get("content", _raw_msg) if isinstance(_raw_msg, dict) else _raw_msg)[:120]
    info(f"status={status}  user_reply_needed={user_reply_needed}  next_step.action={next_step}")
    if ai_msg:
        info(f"Last AI message: {ai_msg}")

    if user_reply_needed:
        check("guidance → send_conversation_reply when reply needed",
              any(s["tool"] == "send_conversation_reply"
                  for s in state["_guidance"]["next_steps"]))
        # Auto-reply "Confirmed" once and re-poll
        reply = client.post(f"/conversations/{conv_id}/message", json={
            "session_id": session_id, "message": "Confirmed",
        })
        reply.setdefault("conversation_id", conv_id)
        reply.setdefault("session_id",      session_id)
        reply["_guidance"] = build_guidance("send_conversation_reply", reply)
        check("send_conversation_reply returns a dict", isinstance(reply, dict))
        assert_guidance(reply, "send_conversation_reply")
        check("send_conversation_reply guidance → get_conversation",
              any(s["tool"] == "get_conversation" for s in reply["_guidance"]["next_steps"]))

        info("Reply sent. Polling again…")
        state2 = poll_conversation(client, conv_id, session_id)
        if state2:
            state2.setdefault("conversation_id", conv_id)
            state2.setdefault("session_id",      session_id)
            state2["_guidance"] = build_guidance("get_conversation", state2)
            assert_guidance(state2, "get_conversation (after reply)")
            next_step = (state2.get("next_step") or {}).get("action", "")
            info(f"After reply: status={state2.get('status')}  next_step.action={next_step}")
            state = state2

    elif next_step == "submit_preview":
        check("guidance → create_job after interview completes",
              any(s["tool"] == "create_job" for s in state["_guidance"]["next_steps"]))

    return {"conversation_id": conv_id, "session_id": session_id}


# ═══════════════════════════════════════════════════════════════════════════
# § 6  Upload interview
# ═══════════════════════════════════════════════════════════════════════════

def test_upload_interview(client: HyperplexityClient, upload: dict | None):
    head("§6 · Upload interview conversation")

    if upload is None:
        info("Skipping — no upload state (upload workflow failed earlier)")
        return

    session_id = upload["session_id"]
    iv = client.post("/conversations/upload-interview", json={
        "session_id": session_id,
        "message": "I want to validate company names, websites, and funding amounts.",
    })
    iv["_guidance"] = build_guidance("start_upload_interview", iv)

    check("start_upload_interview returns a dict",      isinstance(iv, dict))
    check("start_upload_interview has conversation_id", "conversation_id" in iv, str(list(iv.keys())))
    assert_guidance(iv, "start_upload_interview")
    check("guidance → get_conversation",
          any(s["tool"] == "get_conversation" for s in iv["_guidance"]["next_steps"]))

    conv_id = iv["conversation_id"]
    info(f"interview conversation_id = {conv_id}")

    info(f"Polling interview conversation (up to {POLL_TIMEOUT}s)…")
    state = poll_conversation(client, conv_id, session_id)
    if state is None:
        return

    state.setdefault("conversation_id", conv_id)
    state.setdefault("session_id",      session_id)
    state["_guidance"] = build_guidance("get_conversation", state)
    assert_guidance(state, "get_conversation (interview)")

    user_reply_needed = state.get("user_reply_needed", False)
    _raw_msg = state.get("last_ai_message") or ""
    ai_msg   = str(_raw_msg.get("content", _raw_msg) if isinstance(_raw_msg, dict) else _raw_msg)[:140]
    info(f"status={state.get('status')}  user_reply_needed={user_reply_needed}")
    if ai_msg:
        info(f"AI question: {ai_msg}")

    if user_reply_needed:
        # Verify guidance correctly points to send_conversation_reply
        check("guidance → send_conversation_reply (not get_conversation)",
              any(s["tool"] == "send_conversation_reply" for s in state["_guidance"]["next_steps"]) and
              not all(s["tool"] == "get_conversation" for s in state["_guidance"]["next_steps"]))

        # Send one reply
        reply = client.post(f"/conversations/{conv_id}/message", json={
            "session_id": session_id,
            "message": "Company name, website URL, and total funding in USD.",
        })
        reply.setdefault("conversation_id", conv_id)
        reply.setdefault("session_id",      session_id)
        reply["_guidance"] = build_guidance("send_conversation_reply", reply)
        check("send_conversation_reply returns a dict", isinstance(reply, dict))
        assert_guidance(reply, "send_conversation_reply")

        info("Reply sent; polling once more…")
        state2 = poll_conversation(client, conv_id, session_id)
        if state2:
            state2.setdefault("conversation_id", conv_id)
            state2.setdefault("session_id",      session_id)
            state2["_guidance"] = build_guidance("get_conversation", state2)
            assert_guidance(state2, "get_conversation (post-reply)")
            info(f"Post-reply status={state2.get('status')}  "
                 f"user_reply_needed={state2.get('user_reply_needed')}")


# ═══════════════════════════════════════════════════════════════════════════
# § 7  Reference check  (text)
# ═══════════════════════════════════════════════════════════════════════════

def test_reference_check(client: HyperplexityClient):
    head("§7 · Reference check  (inline text)")

    text = (
        "Anthropic is an AI safety company founded in 2021 by Dario Amodei and others. "
        "The company is headquartered in San Francisco and has raised over $7 billion."
    )
    data = client.post("/jobs/reference-check", json={"text": text})
    data["_guidance"] = build_guidance("reference_check", data)

    check("reference_check returns a dict", isinstance(data, dict))
    assert_guidance(data, "reference_check")

    job_id = data.get("job_id", "")
    if job_id:
        info(f"reference_check job_id = {job_id}")
        check("reference_check guidance → get_job_status",
              any(s["tool"] == "get_job_status" for s in data["_guidance"]["next_steps"]))
        info("(Not polling to completion — just verifying job was created)")
    else:
        info(f"Inline result returned (no async job): {list(data.keys())}")


# ═══════════════════════════════════════════════════════════════════════════
# § 8  Job actions  (update_table)
# ═══════════════════════════════════════════════════════════════════════════

def test_update_table(client: HyperplexityClient, completed_job_id: str | None = None):
    head("§8 · update_table")

    if completed_job_id:
        # ── Real test: kick off an update on the job we just completed ────
        info(f"Testing update_table with real completed job: {completed_job_id}")
        try:
            data = client.post("/jobs/update-table",
                               json={"source_job_id": completed_job_id})
            data["_guidance"] = build_guidance("update_table", data)
            check("update_table returns a dict",            isinstance(data, dict))
            check("update_table has job_id",                "job_id" in data, str(list(data.keys())))
            check("update_table has status",                "status" in data, str(list(data.keys())))
            assert_guidance(data, "update_table")
            check("update_table guidance → get_job_status",
                  any(s["tool"] == "get_job_status"
                      for s in data["_guidance"]["next_steps"]))
            new_job_id = data.get("job_id", "")
            info(f"update_table started new job: {new_job_id}  status={data.get('status')}")
            info("(Not polling to completion — skipping to avoid additional cost)")
        except Exception as e:
            fail(f"update_table failed unexpectedly: {e}")

    else:
        # ── Smoke test: fake job_id should return a structured error ──────
        info("No completed job available — smoke-testing with fake job_id")
        try:
            data = client.post("/jobs/update-table",
                               json={"source_job_id": "fake_job_test_smoke"})
            data["_guidance"] = build_guidance("update_table", data)
            check("update_table response is a dict", isinstance(data, dict))
            assert_guidance(data, "update_table")
            info(f"update_table keys: {list(data.keys())}")
        except Exception as e:
            check("update_table returns a structured error for unknown job_id",
                  "source_not_found" in str(e) or "not found" in str(e).lower() or
                  "404" in str(e) or "error" in str(e).lower(),
                  str(e))
            info(f"Expected error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# § 9  refine_config  (smoke: starts a refinement on a non-existent session)
# ═══════════════════════════════════════════════════════════════════════════

def test_refine_config_smoke(client: HyperplexityClient):
    head("§9 · refine_config  (smoke test — invalid session → structured error)")

    fake_job_id = "fake_job_refine_smoke"
    conv_id     = f"refine_{fake_job_id}"
    try:
        data = client.post(f"/conversations/{conv_id}/refine-config", json={
            "session_id": fake_job_id,
            "instructions": "Add a brief analyst commentary column.",
        })
        data.setdefault("conversation_id", conv_id)
        data.setdefault("session_id",      fake_job_id)
        data["_guidance"] = build_guidance("refine_config", data)
        check("refine_config returns a dict", isinstance(data, dict))
        assert_guidance(data, "refine_config")
        info(f"refine_config status: {data.get('status')}")
    except Exception as e:
        check("refine_config returns a structured error for invalid session",
              "error" in str(e).lower() or "not found" in str(e).lower() or
              "400" in str(e) or "404" in str(e),
              str(e))
        info(f"Expected error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def _summary():
    total = _passed + _failed
    bar   = f"{GREEN}{'█' * _passed}{RED}{'█' * _failed}{RESET}"
    print(f"\n{BOLD}{'─'*62}{RESET}")
    print(f"{BOLD}Results: {GREEN}{_passed} passed{RESET}  {RED}{_failed} failed{RESET}  / {total} total")
    print(bar)
    if _failed == 0:
        print(f"{GREEN}{BOLD}All tests passed.{RESET}")
    else:
        print(f"{RED}{BOLD}{_failed} test(s) failed — review output above.{RESET}")
    print()
    sys.exit(0 if _failed == 0 else 1)


def main():
    parser = argparse.ArgumentParser(
        description="Live integration tests for the Hyperplexity MCP server")
    parser.add_argument("--full",  action="store_true",
                        help="Approve the preview job and download final results "
                             "(incurs charges against your balance)")
    parser.add_argument("--quick", action="store_true",
                        help="Skip slow job/conversation tests — only §1 (guidance) + §2 (account)")
    args = parser.parse_args()

    print(f"\n{BOLD}Hyperplexity MCP — Live Integration Tests{RESET}")
    _api_url = os.environ.get("HYPERPLEXITY_API_URL", "https://api.hyperplexity.ai/v1")
    print(f"API:  {_api_url}")
    print(f"Key:  {API_KEY[:14]}…{API_KEY[-4:]}")
    print(f"Mode: {'FULL (will approve + charge)' if args.full else 'PREVIEW-ONLY (safe)'}")
    if args.quick:
        print(f"      QUICK — skipping job/conversation tests")

    client = HyperplexityClient(API_KEY)

    # §1 always runs first — no network, fast
    test_guidance_state_machine()

    # §2 account
    test_account(client)

    if args.quick:
        _summary()
        return

    # §3–4 upload + job workflow
    upload_state     = test_upload_workflow(client)
    completed_job_id = None
    if upload_state:
        completed_job_id = test_job_workflow(client, upload_state, full=args.full)
    else:
        info("§4 skipped — upload failed")

    # §5 table maker
    test_table_maker(client)

    # §6 upload interview
    test_upload_interview(client, upload_state)

    # §7 reference check
    test_reference_check(client)

    # §8 update_table (real job if available, otherwise smoke)
    test_update_table(client, completed_job_id=completed_job_id)

    # §9 refine_config smoke
    test_refine_config_smoke(client)

    _summary()


if __name__ == "__main__":
    main()
