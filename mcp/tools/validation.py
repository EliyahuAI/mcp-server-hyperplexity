"""Validation tools: approve_validation, get_results, get_reference_results."""

from __future__ import annotations

import json
from typing import Optional

from mcp import types

from client import get_client
from guidance import build_guidance


def register(server):
    client = get_client()

    @server.tool()
    def approve_validation(
        job_id: str,
        approved_cost_usd: Optional[float] = None,
    ) -> list[types.TextContent]:
        """Approve a preview and start full validation processing.

        approved_cost_usd should match the estimated_cost_usd from get_job_status
        (preview_complete state). Omit to approve without a cost cap.
        """
        payload: dict = {}
        if approved_cost_usd is not None:
            payload["approved_cost_usd"] = approved_cost_usd

        data = client.post(f"/jobs/{job_id}/validate", json=payload)
        data.setdefault("job_id", job_id)
        data["_guidance"] = build_guidance("approve_validation", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def get_results(job_id: str) -> list[types.TextContent]:
        """Fetch the final validated/enriched results for a completed job."""
        data = client.get(f"/jobs/{job_id}/results")
        data["_guidance"] = build_guidance("get_results", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def get_reference_results(job_id: str) -> list[types.TextContent]:
        """Fetch reference-check sub-results for a completed job (if applicable)."""
        data = client.get(f"/jobs/{job_id}/reference-results")
        data["_guidance"] = build_guidance("get_reference_results", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
