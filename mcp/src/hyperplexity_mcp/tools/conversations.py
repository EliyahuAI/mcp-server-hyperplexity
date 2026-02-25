"""Conversation tools: start_table_maker, get_conversation,
send_conversation_reply, refine_config, wait_for_conversation.

Note: start_upload_interview is intentionally not exposed as an MCP tool —
the server auto-starts an upload interview from confirm_upload when no strong
config match is found, returning conversation_id directly in that response.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Optional

from mcp import types
from mcp.server.fastmcp import Context

from hyperplexity_mcp.client import get_client
from hyperplexity_mcp.guidance import build_guidance


def register(server):
    client = get_client()

    @server.tool()
    def start_table_maker(message: str) -> list[types.TextContent]:
        """Start a Table Maker conversation to generate a research table.

        Describe the table you want in natural language, e.g.:
        'Create a table of AI startups that raised Series A in 2024 with columns:
        company name, funding amount, investors, product description.'
        """
        data = client.post("/conversations/table-maker", json={"message": message})
        data["_guidance"] = build_guidance("start_table_maker", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def get_conversation(
        conversation_id: str,
        session_id: str,
    ) -> list[types.TextContent]:
        """Poll a conversation for new messages or a status change.

        Key statuses:
          processing         → poll again in ~15s
          user_reply_needed  → send_conversation_reply
          trigger_execution  → preview is auto-queued; switch to get_job_status
        """
        data = client.get(f"/conversations/{conversation_id}", params={"session_id": session_id})
        data.setdefault("conversation_id", conversation_id)
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("get_conversation", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def send_conversation_reply(
        conversation_id: str,
        session_id: str,
        message: str,
    ) -> list[types.TextContent]:
        """Send a user reply in an ongoing conversation (interview or table-maker).

        After sending, poll get_conversation for the AI's next response.
        """
        payload = {"session_id": session_id, "message": message}
        data = client.post(f"/conversations/{conversation_id}/message", json=payload)
        data.setdefault("conversation_id", conversation_id)
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("send_conversation_reply", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def refine_config(
        conversation_id: str,
        session_id: str,
        instructions: str,
    ) -> list[types.TextContent]:
        """Refine the generated validation config using natural language instructions.

        Example instructions:
        'Add a column for LinkedIn URL. Remove the revenue column. Make email validation stricter.'
        """
        payload = {"session_id": session_id, "instructions": instructions}
        data = client.post(f"/conversations/{conversation_id}/refine-config", json=payload)
        data.setdefault("conversation_id", conversation_id)
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("refine_config", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    async def wait_for_conversation(
        conversation_id: str,
        session_id: str,
        ctx: Context,
        expected_seconds: int = 120,
        timeout_seconds: int = 600,
        poll_interval: int = 8,
    ) -> list[types.TextContent]:
        """Wait for a conversation turn to complete, emitting live synthetic progress.

        Preferred over manually polling get_conversation. Since conversation
        processing has no native progress signal, this tool emits time-based
        synthetic progress — advancing quickly at first, then slowing as it
        approaches expected_seconds — so the MCP host shows a "still thinking"
        indicator rather than a frozen bar.

        Returns when any of these conditions are met:
          user_reply_needed=True  → AI asked a question; call send_conversation_reply
          trigger_execution=True  → AI approved execution; preview is auto-queued,
                                    switch to wait_for_job(session_id)
          Non-processing status   → unexpected terminal (inspect status field)
          Timeout                 → returns last known state with _wait_timeout note

        Applies to all conversation types: upload interview, table-maker
        interview, config refinement.

        expected_seconds: typical AI response time for this turn (default 120).
          First table-maker turn (research + planning): ~120–180s.
          Upload interview first turn (CSV analysis + plan): ~90–150s.
          Follow-up confirmations ("yes, proceed"): ~30–60s.
        poll_interval:    seconds between status checks (default 8).
        timeout_seconds:  max wall time before returning (default 600).
        """

        def _synthetic_progress(elapsed: float, expected: float) -> float:
            """Advance quickly within the expected window (sqrt curve → 90% at
            t=expected_seconds), then crawl asymptotically toward 98% beyond it."""
            if elapsed <= 0:
                return 2.0
            if elapsed < expected:
                return min(90.0, 90.0 * math.sqrt(elapsed / expected))
            else:
                # ~2% per extra minute, capped at 98
                extra_minutes = (elapsed - expected) / 60.0
                return min(98.0, 90.0 + extra_minutes * 2.0)

        async def _report(pct: float) -> None:
            try:
                await ctx.report_progress(pct, 100.0)
            except Exception:
                pass

        deadline = time.monotonic() + timeout_seconds
        start = time.monotonic()
        last_emitted = 0.0
        data: dict = {}

        while True:
            # Emit monotonically non-decreasing synthetic progress
            elapsed = time.monotonic() - start
            candidate = _synthetic_progress(elapsed, float(expected_seconds))
            emit_pct = max(candidate, last_emitted)
            last_emitted = emit_pct
            await _report(emit_pct)

            try:
                data = await asyncio.to_thread(
                    lambda: client.get(
                        f"/conversations/{conversation_id}",
                        params={"session_id": session_id},
                    )
                )
                data.setdefault("conversation_id", conversation_id)
                data.setdefault("session_id", session_id)

                user_reply_needed = data.get("user_reply_needed", False)
                trigger_execution = data.get("trigger_execution", False)
                status = data.get("status", "processing")

                if (user_reply_needed or trigger_execution
                        or status not in ("processing", "queued", "in_progress")):
                    await _report(100.0)
                    data["_guidance"] = build_guidance("get_conversation", data)
                    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

            except Exception:
                pass  # transient failure; keep polling

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if not data:
                    data = {
                        "conversation_id": conversation_id,
                        "session_id": session_id,
                        "status": "unknown",
                    }
                data["_wait_timeout"] = (
                    f"wait_for_conversation timed out after {timeout_seconds}s. "
                    "The AI has not responded yet. "
                    "Call wait_for_conversation again or poll get_conversation manually."
                )
                data["_guidance"] = build_guidance("get_conversation", data)
                return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

            await asyncio.sleep(min(float(poll_interval), remaining))
