"""Preview editor tools: structural row/column manipulation before full validation."""
from __future__ import annotations

import json
from typing import Annotated, List

from mcp import types
from mcp.types import ToolAnnotations
from pydantic import Field

from hyperplexity_mcp.client import get_client
from hyperplexity_mcp.guidance import build_guidance


def register(server):

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def get_preview_state(
        session_id: Annotated[str, Field(description="Session ID.")],
    ) -> list[types.TextContent]:
        """Get the current structural editing state of a session.

        Returns the preview table, excluded rows, pending rows, ignored columns,
        and current row order so you can review before triggering the full validation run.
        """
        client = get_client()
        data = client.get(f"/sessions/{session_id}/preview-state")
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("get_preview_state", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def exclude_row(
        session_id: Annotated[str, Field(description="Session ID.")],
        row_key: Annotated[str, Field(description="Row key of the row to exclude.")],
        confirmed: Annotated[bool, Field(description="Set True to confirm exclusion. Set False (default) to preview the warning first.")] = False,
    ) -> list[types.TextContent]:
        """Exclude a row from the full validation run.

        Call with confirmed=False first to see a warning, then re-call with
        confirmed=True to apply. Reversible via include_row at any point before
        approving the full validation run.
        """
        client = get_client()
        data = client.post(f"/sessions/{session_id}/rows/exclude", json={"row_key": row_key, "confirmed": confirmed})
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("exclude_row", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def include_row(
        session_id: Annotated[str, Field(description="Session ID.")],
        row_key: Annotated[str, Field(description="Row key of the row to re-include.")],
    ) -> list[types.TextContent]:
        """Re-include a previously excluded row.

        No confirmation needed. Can be called at any point before approving
        the full validation run.
        """
        client = get_client()
        data = client.post(f"/sessions/{session_id}/rows/include", json={"row_key": row_key})
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("include_row", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def add_pending_row(
        session_id: Annotated[str, Field(description="Session ID.")],
        entity_id: Annotated[str, Field(description="Unique identifier for the new entity (e.g. ticker, ID, slug).")],
        entity_name: Annotated[str, Field(description="Human-readable name of the entity.")],
        extra_fields: Annotated[dict, Field(description="Additional column values as a dict, e.g. {\"Ticker\": \"AAPL\", \"Exchange\": \"NASDAQ\"}.")] = None,
    ) -> list[types.TextContent]:
        """Add a new entity as a pending row to be included in the full validation run.

        The source Excel is NOT modified — the row is stored in session state and
        injected in-memory at validation time. Fully reversible before approving
        the full run.

        The full-run cost quote updates to include the new row count.
        """
        client = get_client()
        payload = {
            "entity_id": entity_id,
            "entity_name": entity_name,
            "extra_fields": extra_fields or {},
        }
        data = client.post(f"/sessions/{session_id}/rows/add", json=payload)
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("add_pending_row", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def reorder_preview_rows(
        session_id: Annotated[str, Field(description="Session ID.")],
        row_keys_in_order: Annotated[List[str], Field(description="Complete ordered list of row keys defining the desired output order.")],
    ) -> list[types.TextContent]:
        """Set the output row order for the validation run.

        This is a display preference — it does not affect which rows are validated
        or the validation itself. Rows not in the list are sorted to the end.
        """
        client = get_client()
        data = client.post(f"/sessions/{session_id}/rows/reorder", json={"row_keys_in_order": row_keys_in_order})
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("reorder_preview_rows", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def trigger_preview(
        session_id: Annotated[str, Field(description="Session ID to trigger preview for.")],
    ) -> list[types.TextContent]:
        """Trigger a preview run after structural editing is complete.

        Call this after finishing row/column edits (exclude_row, add_pending_row,
        add_column, etc.) to explicitly queue a preview job.

        This clears skip_auto_preview and queues the preview. Then call
        wait_for_job(session_id) to track progress.
        """
        client = get_client()
        # Clear skip_auto_preview flag
        client.post(f"/sessions/{session_id}/skip-auto-preview", json={"skip": False})
        # Trigger the preview via jobs endpoint
        data = client.post("/jobs", json={"session_id": session_id, "preview_max_rows": 3})
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("trigger_preview", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
