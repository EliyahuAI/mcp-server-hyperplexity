"""Upload tools: upload_file (compound), confirm_upload."""

from __future__ import annotations

import json
import os
from typing import Annotated, Optional

from mcp import types
from mcp.types import ToolAnnotations
from pydantic import Field

from hyperplexity_mcp.client import get_client
from hyperplexity_mcp.guidance import build_guidance

_CONTENT_TYPES = {
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "pdf": "application/pdf",
}


def register(server):

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def upload_file(
        file_path: Annotated[str, Field(description="Absolute or relative path to the local file to upload.")],
        file_type: Annotated[str, Field(description='File format — must be one of: "excel", "csv", "pdf".')],
        session_id: Annotated[Optional[str], Field(description="Optional existing session ID to associate this upload with.")] = None,
    ) -> list[types.TextContent]:
        """Upload a local file to Hyperplexity.

        Compound tool: reads the file, gets a presigned S3 URL, PUTs the bytes
        (without auth headers — presigned URL carries the credentials), and
        returns session_id + s3_key ready for confirm_upload.

        file_type must be one of: "excel", "csv", "pdf"
        """
        client = get_client()
        if file_type not in _CONTENT_TYPES:
            raise ValueError(f"file_type must be one of {list(_CONTENT_TYPES)}; got '{file_type}'")

        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        filename = os.path.basename(file_path)
        content_type = _CONTENT_TYPES[file_type]

        # Step 1: read file to get size
        with open(file_path, "rb") as fh:
            file_bytes = fh.read()

        # Step 2: get presigned upload URL
        payload: dict = {
            "filename": filename,
            "file_size": len(file_bytes),
            "file_type": file_type,
            "content_type": content_type,
        }
        if session_id:
            payload["session_id"] = session_id

        presign_data = client.post("/uploads/presigned", json=payload)
        upload_url = presign_data.get("presigned_url") or presign_data.get("upload_url", "")
        s3_key = presign_data["s3_key"]
        returned_session_id = presign_data.get("session_id", session_id or "")
        upload_id = presign_data.get("upload_id", "")

        # Step 3: PUT file bytes to S3 (bare requests, no auth header)
        client.put_raw(upload_url, file_bytes, content_type)

        result = {
            "session_id": returned_session_id,
            "upload_id": upload_id,
            "s3_key": s3_key,
            "filename": filename,
            "file_type": file_type,
            "bytes_uploaded": len(file_bytes),
        }
        result["_guidance"] = build_guidance("upload_file", result)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def confirm_upload(
        session_id: Annotated[str, Field(description="Session ID returned by upload_file.")],
        s3_key: Annotated[str, Field(description="S3 key returned by upload_file identifying the uploaded file.")],
        filename: Annotated[str, Field(description="Original filename of the uploaded file.")],
        instructions: Annotated[Optional[str], Field(description="Optional natural-language description of what to validate; bypasses the upload interview when provided.")] = None,
        config_id: Annotated[Optional[str], Field(description="Optional ID of a prior configuration to reuse; skips the interview and queues the preview immediately.")] = None,
    ) -> list[types.TextContent]:
        """Confirm the upload and detect matching prior configs.

        Call this immediately after upload_file. Returns config_matches with
        match_score — if score >= 0.85 a prior config can be reused directly.

        instructions: Optional natural-language description of what to validate
          and how (e.g. "This table lists clinical trials — validate that trial IDs,
          phase, and primary endpoints are accurate"). When provided, the upload
          interview is bypassed: the AI reads the table structure + instructions
          and generates a config directly without asking clarifying questions.
          Preview is auto-triggered immediately after.

        config_id: Optional ID of a known prior configuration to reuse directly.
          When provided, skips matching and the interview entirely — applies the
          config and queues the preview immediately. Response includes
          preview_queued=true and job_id. Use when you already know the config_id
          (e.g. from a previous job's get_results response).

          Config generation and the 3-row preview are free. Full validation is
          charged at approve_validation — you still see the cost at preview_complete
          before anything is billed. If balance is insufficient at that point,
          approve_validation returns an insufficient_balance error.
        """
        client = get_client()
        payload = {"session_id": session_id, "s3_key": s3_key, "filename": filename}
        if instructions:
            payload["instructions"] = instructions
        if config_id:
            payload["config_id"] = config_id
        data = client.post("/uploads/confirm", json=payload)
        data["_guidance"] = build_guidance("confirm_upload", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
