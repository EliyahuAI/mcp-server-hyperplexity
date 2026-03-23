"""Job action tools: update_table, reference_check."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp import types
from mcp.types import ToolAnnotations
from pydantic import Field

from hyperplexity_mcp.client import get_client
from hyperplexity_mcp.guidance import build_guidance


def register(server):

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def update_table(
        source_job_id: Annotated[str, Field(description="Job ID of the previously processed table to re-run validation on.")],
        source_version: Annotated[Optional[str], Field(description="Specific prior result version to pin; omit to use the latest version.")] = None,
    ) -> list[types.TextContent]:
        """Re-run validation on a previously processed table (update in place).

        source_version can pin a specific prior result version; omit for latest.
        """
        client = get_client()
        payload: dict = {"source_job_id": source_job_id}
        if source_version:
            payload["source_version"] = source_version

        data = client.post("/jobs/update-table", json=payload)
        data["_guidance"] = build_guidance("update_table", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def reference_check(
        text: Annotated[Optional[str], Field(description="Inline text to fact-check (provide either text or s3_key, not both).")] = None,
        s3_key: Annotated[Optional[str], Field(description="S3 key of an already-uploaded file to fact-check (provide either text or s3_key).")] = None,
        auto_approve: Annotated[bool, Field(description="Skip the preview approval gate and run straight through to full validation automatically.")] = False,
    ) -> list[types.TextContent]:
        """Submit a reference-check job to fact-check text or a document.

        For inline text:
          reference_check(text="The claims to fact-check...")

        For a PDF or document, upload it first then pass the s3_key:
          upload_file(file_path, file_type="pdf")  → returns s3_key
          reference_check(s3_key=s3_key)
          Do NOT call confirm_upload for PDFs — that starts the table validation
          pipeline, which is not what you want for a reference check.

        Designed for text with 4 or more factual claims; fewer claims may produce
        low-quality results.

        Three phases:
        - Phase 1 (free): claim extraction + 3-row preview validation (auto-triggered).
          wait_for_job blocks until status=preview_complete. Review preview_table
          (3 validated sample claims) and cost_estimate.
        - Approval gate: call approve_validation to proceed.
        - Phase 2 (charged): full claim validation. Returns XLSX, viewer URL, metadata.

        Set auto_approve=True to skip the approval gate and run straight through
        to completion automatically.
        """
        client = get_client()
        if not text and not s3_key:
            raise ValueError("Provide either 'text' or 's3_key'.")

        payload: dict = {}
        if text:
            payload["text"] = text
        if s3_key:
            payload["s3_key"] = s3_key
        if auto_approve:
            payload["auto_approve"] = True

        data = client.post("/jobs/reference-check", json=payload)
        data["_guidance"] = build_guidance("reference_check", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
