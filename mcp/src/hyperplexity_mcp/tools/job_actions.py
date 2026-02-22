"""Job action tools: update_table, reference_check."""

from __future__ import annotations

import json
from typing import Optional

from mcp import types

from hyperplexity_mcp.client import get_client
from hyperplexity_mcp.guidance import build_guidance


def register(server):
    client = get_client()

    @server.tool()
    def update_table(
        source_job_id: str,
        source_version: Optional[str] = None,
    ) -> list[types.TextContent]:
        """Re-run validation on a previously processed table (update in place).

        source_version can pin a specific prior result version; omit for latest.
        """
        payload: dict = {"source_job_id": source_job_id}
        if source_version:
            payload["source_version"] = source_version

        data = client.post("/jobs/update-table", json=payload)
        data["_guidance"] = build_guidance("update_table", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def reference_check(
        text: Optional[str] = None,
        s3_key: Optional[str] = None,
    ) -> list[types.TextContent]:
        """Submit a reference-check job for a text snippet or uploaded file.

        Provide either text (inline) or s3_key (already-uploaded file).
        """
        if not text and not s3_key:
            raise ValueError("Provide either 'text' or 's3_key'.")

        payload: dict = {}
        if text:
            payload["text"] = text
        if s3_key:
            payload["s3_key"] = s3_key

        data = client.post("/jobs/reference-check", json=payload)
        data["_guidance"] = build_guidance("reference_check", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
