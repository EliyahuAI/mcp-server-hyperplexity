"""Upload tools: upload_file (compound), confirm_upload."""

from __future__ import annotations

import json
import os
from typing import Optional

from mcp import types

from hyperplexity_mcp.client import get_client
from hyperplexity_mcp.guidance import build_guidance

_CONTENT_TYPES = {
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "pdf": "application/pdf",
}


def register(server):
    client = get_client()

    @server.tool()
    def upload_file(
        file_path: str,
        file_type: str,
        session_id: Optional[str] = None,
    ) -> list[types.TextContent]:
        """Upload a local file to Hyperplexity.

        Compound tool: reads the file, gets a presigned S3 URL, PUTs the bytes
        (without auth headers — presigned URL carries the credentials), and
        returns session_id + s3_key ready for confirm_upload.

        file_type must be one of: "excel", "csv", "pdf"
        """
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

    @server.tool()
    def confirm_upload(
        session_id: str,
        s3_key: str,
        filename: str,
    ) -> list[types.TextContent]:
        """Confirm the upload and detect matching prior configs.

        Call this immediately after upload_file. Returns config_matches with
        match_score — if score >= 0.85 a prior config can be reused directly.
        """
        payload = {"session_id": session_id, "s3_key": s3_key, "filename": filename}
        data = client.post("/uploads/confirm", json=payload)
        data["_guidance"] = build_guidance("confirm_upload", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
