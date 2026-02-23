"""Validation tools: approve_validation, get_results, get_reference_results."""

from __future__ import annotations

import json
from typing import Optional

import requests as _requests
from mcp import types

from hyperplexity_mcp.client import APIError, get_client
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

        try:
            data = client.post(f"/jobs/{job_id}/validate", json=payload)
        except APIError as exc:
            if exc.status_code == 409:
                result = {
                    "error": "cannot_approve",
                    "message": (
                        "Cannot approve: job is not in `preview_complete` state. "
                        "Call get_job_status to check the current state."
                    ),
                    "api_detail": str(exc),
                    "job_id": job_id,
                    "_guidance": {
                        "summary": (
                            "Approval rejected — job is not in preview_complete state. "
                            "Check current state with get_job_status before retrying."
                        ),
                        "next_steps": [
                            {
                                "tool": "get_job_status",
                                "params": {"job_id": job_id},
                                "note": "Verify the job is in preview_complete before approving.",
                            }
                        ],
                    },
                }
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
            raise

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
        try:
            data = client.get(f"/jobs/{job_id}/results")
        except APIError as exc:
            if exc.status_code == 404:
                result = {
                    "error": "results_not_found",
                    "message": str(exc),
                    "job_id": job_id,
                    "_guidance": {
                        "summary": (
                            "Results not found. If this is a table maker job, results are "
                            "not available at the standard /results endpoint — check the "
                            "Hyperplexity web viewer for your table. Otherwise, the job may "
                            "still be processing; call get_job_status to verify."
                        ),
                        "next_steps": [
                            {
                                "tool": "get_job_status",
                                "params": {"job_id": job_id},
                                "note": "Check if the job is complete or still processing.",
                            }
                        ],
                    },
                }
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
            raise

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
