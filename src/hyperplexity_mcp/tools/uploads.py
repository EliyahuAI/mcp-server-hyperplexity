"""Upload tools: upload_file, start_table_validation."""

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
        filename: Annotated[str, Field(description="Original filename including extension (e.g. 'data.xlsx', 'report.csv', 'doc.pdf').")],
        file_type: Annotated[str, Field(description='File format — must be one of: "excel", "csv", "pdf".')],
        file_size: Annotated[int, Field(description="File size in bytes. Run: stat -c%s <file> (Linux/macOS) or (Get-Item '<file>').Length (PowerShell).")],
        file_path: Annotated[Optional[str], Field(description="Absolute local path to upload directly (uvx/local transport only — the MCP server reads the file). Omit when using HTTP/Railway transport; the response curl_command handles the upload instead.")] = None,
        session_id: Annotated[Optional[str], Field(description="Optional existing session ID to associate this upload with.")] = None,
    ) -> list[types.TextContent]:
        """Upload a file to Hyperplexity.

        RECOMMENDED: always try with file_path first. If the server can read the
        file (stdio/uvx transport), it uploads in one step and returns session_id
        + s3_key immediately. If the server is remote (HTTP/Railway transport),
        file_path raises "File not found" — in that case call again without
        file_path to get a presigned S3 upload_url and curl_command instead.

        With file_path (one step — stdio/uvx transport):
          upload_file(filename="data.xlsx", file_type="excel", file_size=12345,
                      file_path="/abs/path/data.xlsx")
          → server reads + uploads → returns session_id, s3_key

        Without file_path (two step — HTTP/Railway transport or any remote server):
          upload_file(filename="data.xlsx", file_type="excel", file_size=12345)
          → returns upload_url + curl_command
          → run the curl_command (requires shell/Bash access), then call
             start_table_validation(session_id, s3_key, filename)

        Note: the two-step path requires shell access to run curl. If you have no
        shell (e.g. Claude Desktop), use the stdio/uvx transport instead so
        file_path works.

        file_type must be one of: "excel", "csv", "pdf"
        The presigned URL expires in ~15 minutes — run curl immediately.
        """
        client = get_client()
        if file_type not in _CONTENT_TYPES:
            raise ValueError(f"file_type must be one of {list(_CONTENT_TYPES)}; got '{file_type}'")

        content_type = _CONTENT_TYPES[file_type]
        payload: dict = {
            "filename": filename,
            "file_size": file_size,
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

        if file_path:
            # Local transport: server reads and PUTs the file directly.
            if not os.path.isfile(file_path):
                raise FileNotFoundError(
                    f"File not found: {file_path}\n"
                    "If using HTTP/Railway transport the server is remote and cannot read "
                    "local paths. Call upload_file without file_path — the response will "
                    "include a curl_command to upload directly from your machine."
                )
            with open(file_path, "rb") as fh:
                file_bytes = fh.read()
            client.put_raw(upload_url, file_bytes, content_type)
            result = {
                "session_id": returned_session_id,
                "upload_id": upload_id,
                "s3_key": s3_key,
                "filename": filename,
                "file_type": file_type,
                "bytes_uploaded": len(file_bytes),
            }
        else:
            # HTTP/Railway transport: return presigned URL for the caller to PUT directly.
            result = {
                "upload_url": upload_url,
                "session_id": returned_session_id,
                "s3_key": s3_key,
                "filename": filename,
                "file_type": file_type,
                "content_type": content_type,
                "curl_command": (
                    f'curl -X PUT -H "Content-Type: {content_type}" '
                    f'--upload-file "<local_file_path>" "{upload_url}"'
                ),
            }

        result["_guidance"] = build_guidance("upload_file", result)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def start_table_validation(
        session_id: Annotated[str, Field(description="Session ID returned by upload_file.")],
        s3_key: Annotated[str, Field(description="S3 key returned by upload_file identifying the uploaded file.")],
        filename: Annotated[str, Field(description="Original filename of the uploaded file.")],
        instructions: Annotated[Optional[str], Field(description="Optional natural-language description of what to validate; bypasses the upload interview when provided.")] = None,
        config_id: Annotated[Optional[str], Field(description="Optional ID of a prior configuration to reuse; skips the interview and queues the preview immediately.")] = None,
    ) -> list[types.TextContent]:
        """Confirm the upload and detect matching prior configs.

        Call this immediately after upload_file completes (or after the curl upload
        finishes when using HTTP/Railway transport). Returns config_matches with
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
        data["_guidance"] = build_guidance("start_table_validation", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
