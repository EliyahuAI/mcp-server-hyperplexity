"""Job tools: create_job, get_job_status, get_job_messages, wait_for_job."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from mcp import types
from mcp.server.fastmcp import Context

from hyperplexity_mcp.client import APIError, get_client
from hyperplexity_mcp.guidance import build_guidance


def register(server):
    client = get_client()

    @server.tool()
    def create_job(
        session_id: str,
        upload_id: Optional[str] = None,
        config_id: Optional[str] = None,
        config: Optional[dict] = None,
        s3_key: Optional[str] = None,
        notify_method: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ) -> list[types.TextContent]:
        """Create a validation job.

        Always runs as a 3-row preview first — approve_validation is required
        before full processing begins.

        Provide one of:
          - config_id  — reuse a known config (fastest)
          - config     — supply a config dict directly
          - (neither)  — session must already hold a config from upload_interview

        upload_id comes from the upload_file response.
        notify_method: "poll" (default) or "webhook".
        """
        payload: dict = {"session_id": session_id, "preview_rows": 3}
        if upload_id:
            payload["upload_id"] = upload_id
        if config_id:
            payload["config_id"] = config_id
        if config is not None:
            payload["config"] = config
        if s3_key:
            payload["s3_key"] = s3_key
        if notify_method:
            payload["notify_method"] = notify_method
        if webhook_url:
            payload["webhook_url"] = webhook_url

        try:
            data = client.post("/jobs", json=payload)
        except APIError as exc:
            if "missing_config" in str(exc):
                result = {
                    "error": "missing_config",
                    "message": str(exc),
                    "session_id": session_id,
                    "_guidance": {
                        "summary": (
                            "No validation config found for this session. "
                            "For table-maker sessions, the preview is auto-queued once execution "
                            "finishes — do NOT call create_job(). "
                            "Use wait_for_job(session_id) to track the table-maker and preview "
                            "phases with live progress until preview_complete."
                        ),
                        "next_steps": [
                            {
                                "tool": "wait_for_job",
                                "params": {"job_id": session_id},
                                "note": (
                                    "Preferred: handles the table-maker → preview phase boundary "
                                    "automatically and blocks until preview_complete."
                                ),
                            }
                        ],
                    },
                }
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
            raise

        data["_guidance"] = build_guidance("create_job", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def get_job_status(job_id: str) -> list[types.TextContent]:
        """One-shot job status check. Prefer wait_for_job for tracking long-running jobs.

        Use this for quick status inspections or as a fallback when wait_for_job
        is not appropriate. For polling loops, wait_for_job is more efficient —
        it holds the connection, emits live MCP progress notifications, and handles
        the multi-phase pipeline (table-maker → preview) automatically.

        Key statuses:
          queued / processing  → call wait_for_job instead of re-polling manually
          preview_complete     → approve_validation (or refine_config)
          completed            → get_results
          failed               → check error field
        """
        data = client.get(f"/jobs/{job_id}")
        data["_guidance"] = build_guidance("get_job_status", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def get_job_messages(
        job_id: str,
        since_seq: Optional[int] = None,
    ) -> list[types.TextContent]:
        """Fetch live progress messages for a running job.

        Pass since_seq from the last message to receive only new messages.
        """
        params = {}
        if since_seq is not None:
            params["since_seq"] = since_seq
        data = client.get(f"/jobs/{job_id}/messages", params=params or None)
        data["job_id"] = job_id  # ensure job_id present for guidance
        data["_guidance"] = build_guidance("get_job_messages", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    async def wait_for_job(
        job_id: str,
        ctx: Context,
        timeout_seconds: int = 600,
        poll_interval: int = 10,
    ) -> list[types.TextContent]:
        """Wait for a job to reach a terminal state, emitting live MCP progress notifications.

        Preferred over manually looping get_job_status. The MCP host shows a live
        progress indicator while this tool holds the connection — no extra token cost.

        Architecture
        ────────────
        Every poll cycle does two things in sequence:
          1. Fetch /messages → extract native progress %, emit MCP notification
          2. Fetch /status   → act on phase transitions or terminal states

        This separation means messages drive the visual indicator (they are more
        real-time) while status is the authoritative source for workflow transitions.
        Neither endpoint is used as a shortcut to skip the other; both are polled
        every cycle so transient failures in one don't cause false terminations.

        Progress is always monotonically non-decreasing.  Within a phase,
        msg_progress can oscillate (e.g. QC triggers new row-discovery rounds in
        the table-maker), but the emitted value is clamped to last_emitted.
        Across phases a geometric slice scheme is used so the bar never goes
        backward regardless of how many phases occur.

        Progress geometry (lazy split)
        ──────────────────────────────
        Starts with the full 0–99 range so single-phase jobs (e.g. full
        validation after approve_validation) map their native 0–100% directly
        across the whole bar.  On each intermediate phase transition, 80% of
        the current range is "spent" on the completed phase and the remaining
        20% is handed to the next phase — keeping progress monotonic for any
        number of QC re-discovery rounds or pipeline stages.
        True terminal always emits exactly 100.

        Terminal states: preview_complete, failed, completed-without-intermediate-step.
        Intermediate:    completed + current_step in (Config Generation, Table Making,
                         Claim Extraction, …) — tool advances phase and keeps polling.

        Returns the same payload shape as get_job_status so downstream tools
        (approve_validation, get_results, etc.) apply directly.

        timeout_seconds: max wall time before returning last known state (default 600)
        poll_interval:   seconds between poll cycles (default 10)
        """
        # ── Helpers: phase and terminal classification ────────────────────────

        # Step names (lowercased) embedded in current_step that mark an
        # intermediate completed state (generator phase done, next pipeline
        # stage not yet started).  Lowercase comparison avoids mismatches like
        # "Config Generation" vs "Configuration generation completed…" (Issue #1).
        _INTERMEDIATE_STEPS = (
            "config generation",
            "configuration generation",
            "table making",
            "table maker",
            "claim extraction",
        )

        # Track the last current_step that triggered a phase split so that a
        # stuck status endpoint returning the same stale response doesn't keep
        # re-splitting the progress range on every poll cycle.
        _last_intermediate_step: list = [None]

        def _is_intermediate_complete(d: dict) -> bool:
            if d.get("status") != "completed":
                return False
            step = (d.get("current_step") or d.get("step") or "").lower()
            return any(s in step for s in _INTERMEDIATE_STEPS)

        def _is_true_terminal(d: dict) -> bool:
            status = d.get("status", "")
            if status in ("preview_complete", "failed"):
                return True
            if status == "completed" and not _is_intermediate_complete(d):
                return True
            return False

        # ── Helpers: progress geometry ────────────────────────────────────────
        #
        # Lazy-split approach: start with the full 0–99 range so that
        # single-phase jobs (e.g. full validation after approve_validation)
        # map their native 0–100% progress directly across the whole bar.
        # Only when an intermediate phase transition is detected do we
        # "spend" 80% of the current range on the completed phase and hand
        # the remaining 20% to the next phase.  This ensures:
        #   • Validation (always the last phase) always uses the full range.
        #   • Multi-phase compound jobs (table-maker → preview) still produce
        #     monotonically non-decreasing progress.
        #   • Unbounded QC re-discovery rounds within a phase are handled by
        #     last_emitted clamping rather than pre-allocated geometry.

        # Mutable range for the current phase; updated on intermediate transitions.
        # These are captured by the `if _is_intermediate_complete` block below.
        _pf: list = [0.0]   # phase_floor (use list so inner references stay valid)
        _pc: list = [99.0]  # phase_ceiling

        def _scale_to_range(phase_pct: float) -> float:
            """Map a within-phase 0–100 value into [phase_floor, phase_ceiling]."""
            clamped = min(max(phase_pct, 0.0), 99.0)
            return _pf[0] + (clamped / 100.0) * (_pc[0] - _pf[0])

        # ── Helpers: async I/O ────────────────────────────────────────────────

        last_seq: Optional[int] = None
        _cursor_primed: bool = False  # True after the first fetch has advanced last_seq

        def _extract_progress(messages: list) -> Optional[float]:
            """Return the latest progress % from message payloads, or None.

            Uses an explicit key-in check so that progress=0 (a valid value at
            the start of a new sub-task) is never silently dropped by an or-chain.
            """
            for msg in reversed(messages):
                payload = msg.get("message_data") or msg.get("data") or {}
                if isinstance(payload, dict):
                    for key in ("progress", "percent", "progress_percent", "value"):
                        if key in payload:
                            return float(payload[key])
            return None

        async def _fetch_messages() -> list:
            """Fetch messages since last_seq.

            The first call (last_seq=None) advances the cursor to the current
            tail of the log without returning those messages for progress use.
            This prevents stale messages from a previous phase (e.g. a preview
            completion at 100%) from poisoning last_emitted at the start of a
            new wait_for_job invocation (e.g. full validation after approval).
            """
            nonlocal last_seq, _cursor_primed
            # Use a lambda so asyncio.to_thread passes params unambiguously.
            params = {"since_seq": last_seq} if last_seq is not None else None
            resp = await asyncio.to_thread(
                lambda: client.get(f"/jobs/{job_id}/messages", params)
            )
            messages = resp.get("messages") or []
            new_seq = resp.get("last_seq")
            if new_seq is None and messages:
                new_seq = messages[-1].get("_seq") or messages[-1].get("seq")
            if new_seq is not None:
                last_seq = new_seq
            if not _cursor_primed:
                # Cursor is now at the current tail; discard this batch so old
                # phase messages don't influence last_emitted.
                _cursor_primed = True
                return []
            return messages

        async def _fetch_status() -> dict:
            return await asyncio.to_thread(client.get, f"/jobs/{job_id}")

        async def _report(progress: float) -> None:
            try:
                await ctx.report_progress(progress, 100.0)
            except Exception:
                pass

        # ── Main loop state ───────────────────────────────────────────────────

        deadline = time.monotonic() + timeout_seconds
        msg_progress: float = 2.0  # latest within-phase progress % from messages
        last_emitted: float = 0.0  # monotonic floor — never report below this
        data: dict = {}

        while True:
            # ── 1. Poll messages → update within-phase progress ───────────────
            try:
                messages = await _fetch_messages()
                if messages:
                    extracted = _extract_progress(messages)
                    if extracted is not None:
                        msg_progress = extracted
            except Exception:
                pass  # transient message-endpoint failure; keep going

            # ── 2. Emit monotonically non-decreasing progress notification ────
            # Within a phase, msg_progress can dip (e.g. QC restarts row
            # discovery in the table-maker).  last_emitted ensures the bar never
            # visually regresses.
            candidate = _scale_to_range(max(msg_progress, 2.0))
            emit_pct = max(candidate, last_emitted)
            last_emitted = emit_pct
            await _report(emit_pct)

            # ── 3. Poll status → authoritative source for transitions ─────────
            # Status is polled every cycle (not only when messages look done) so
            # a network hiccup on the message endpoint never causes a missed
            # terminal state, and a transient 100% message value never causes a
            # false completion.
            #
            # Architecture note: during full validation the interface Lambda is
            # not active — the validation Lambda runs async and writes status and
            # messages directly to DynamoDB.  The REST API reads DynamoDB, so
            # polling works correctly regardless of which Lambda is live.
            try:
                data = await _fetch_status()

                if _is_intermediate_complete(data):
                    # Generator phase done (e.g. table-maker finished, preview
                    # about to start).  Apply a lazy split: "spend" 80% of the
                    # current range on the completed phase and give the remainder
                    # to the next phase.  This keeps progress monotonic while
                    # ensuring the final phase (validation) always uses whatever
                    # range is left — usually the full 0–99 if this is the only
                    # transition seen.
                    #
                    # Only apply the phase split if this is a NEW intermediate
                    # step — if the status endpoint is stuck returning the same
                    # stale "completed / Config Generation" response on every
                    # poll, skip the split to prevent the range from converging
                    # toward 99% without the job actually advancing (Issue #2).
                    #
                    # Do NOT reset last_seq — keep consuming new messages from
                    # where we are; resetting would replay stale messages and
                    # re-trigger this block.
                    current_step_key = (data.get("current_step") or "").lower()
                    if current_step_key != _last_intermediate_step[0]:
                        _last_intermediate_step[0] = current_step_key
                        spend = _pf[0] + (_pc[0] - _pf[0]) * 0.8   # 80% of range used
                        new_floor = max(spend, last_emitted + 0.5)   # never regress
                        new_floor = min(new_floor, _pc[0] - 1.0)     # always leave room
                        _pf[0] = new_floor
                        # _pc[0] stays at 99 — the next phase inherits the rest
                        msg_progress = 2.0

                elif _is_true_terminal(data):
                    await _report(100.0)
                    data["_guidance"] = build_guidance("get_job_status", data)
                    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

            except Exception:
                pass  # transient status-endpoint failure; keep polling

            # ── 4. Timeout guard ──────────────────────────────────────────────
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if not data:
                    data = {"job_id": job_id, "status": "unknown"}
                data["_guidance"] = build_guidance("get_job_status", data)
                data["_wait_timeout"] = (
                    f"wait_for_job timed out after {timeout_seconds}s. "
                    "Job has not reached a terminal state. "
                    "Call wait_for_job again or poll get_job_status manually."
                )
                return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

            await asyncio.sleep(min(float(poll_interval), remaining))
