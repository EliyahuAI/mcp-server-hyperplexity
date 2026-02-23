"""Job tools: create_job, get_job_status, get_job_messages."""

from __future__ import annotations

import json
from typing import Optional

from mcp import types

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
                            "If this is a table-maker session, the config is written during "
                            "execution — poll get_job_status until current_step contains "
                            "'Config Generation completed', then retry create_job."
                        ),
                        "next_steps": [
                            {
                                "tool": "get_job_status",
                                "params": {"job_id": session_id},
                                "note": (
                                    "Poll every 15s. When status='completed' and current_step "
                                    "contains 'Config Generation completed', the config is ready "
                                    "and you can retry create_job(session_id=session_id)."
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
        """Poll job status. _guidance tells you exactly what to do next.

        Key statuses:
          queued / processing  → keep polling (~10s interval)
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
