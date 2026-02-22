"""Validation tools: approve_validation, get_results, get_reference_results."""

from __future__ import annotations

import json
from typing import Optional

import requests as _requests
from mcp import types

from hyperplexity_mcp.client import get_client
from hyperplexity_mcp.guidance import build_guidance


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
        """Fetch the final validated/enriched results for a completed job.

        Automatically downloads table_metadata.json and embeds it inline as
        results.metadata — no extra tool call needed. The metadata contains
        per-cell confidence scores, validator explanations, and sources/citations.
        """
        data = client.get(f"/jobs/{job_id}/results")

        # Fetch and embed table_metadata.json inline so the LLM can read it
        # directly without needing a separate HTTP fetch tool.
        metadata_url = (data.get("results") or {}).get("metadata_url", "")
        if metadata_url:
            try:
                resp = _requests.get(metadata_url, timeout=15)
                resp.raise_for_status()
                data.setdefault("results", {})["metadata"] = resp.json()
            except Exception as exc:
                data.setdefault("results", {})["metadata_fetch_error"] = str(exc)

        data["_guidance"] = build_guidance("get_results", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def get_reference_results(job_id: str) -> list[types.TextContent]:
        """Fetch reference-check sub-results for a completed job (if applicable)."""
        data = client.get(f"/jobs/{job_id}/reference-results")
        data["_guidance"] = build_guidance("get_reference_results", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
