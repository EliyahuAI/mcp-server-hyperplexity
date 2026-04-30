"""Post-validation tools: add rows and patch columns after full validation completes."""
from __future__ import annotations

import json
from typing import Annotated, List

from mcp import types
from mcp.types import ToolAnnotations
from pydantic import Field

from subindex_mcp.client import get_client
from subindex_mcp.guidance import build_guidance


def register(server):

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def add_validated_rows(
        session_id: Annotated[str, Field(description="Session ID of a completed validation.")],
        entities: Annotated[List[dict], Field(description="List of new entities to add. Each dict must have 'entity_id', 'entity_name', and optional 'extra_fields'.")],
        confirmed: Annotated[bool, Field(description="Set True to approve and trigger the RowAdd run. Set False (default) to see the cost quote first.")] = False,
    ) -> list[types.TextContent]:
        """Add new rows to a completed validation table.

        Deduplication runs against existing rows. If confirmed=False, returns
        a cost quote (N_new_rows x per_row_rate from last run). If confirmed=True,
        appends rows to source Excel, runs validation on new rows only, and merges
        results into the output Excel.

        Only available after full validation completes (status=completed).
        """
        client = get_client()
        payload = {"entities": entities, "confirmed": confirmed}
        data = client.post(f"/sessions/{session_id}/rows/validate", json=payload)
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("add_validated_rows", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def discover_rows(
        session_id: Annotated[str, Field(description="Session ID of a completed validation.")],
        instruction: Annotated[str, Field(description="What rows to discover, e.g. 'add 5 EU pharma companies' or 'find more entries matching the existing pattern'.")],
        count: Annotated[int, Field(description="Target number of new rows to discover.")] = 10,
        confirmed: Annotated[bool, Field(description="Set True to approve and trigger the RowDiscover run. Set False (default) to see the cost quote first.")] = False,
    ) -> list[types.TextContent]:
        """Discover and add new rows to an existing validated table using AI-powered search.

        Uses the existing table's config and validated data to plan a targeted
        row discovery run. The planner derives search strategy from the config,
        then RowDiscovery finds candidates and QC filters them.

        If confirmed=False, returns a cost estimate. If confirmed=True, enqueues
        the discovery pipeline (planner -> search -> QC -> pending_rows).

        Discovered rows land in pending_rows with source='row_discover'. Run
        add_validated_rows to validate them, or trigger a preview to see them.
        """
        client = get_client()
        payload = {"instruction": instruction, "count": count, "confirmed": confirmed}
        data = client.post(f"/sessions/{session_id}/rows/discover", json=payload)
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("discover_rows", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def patch_column(
        session_id: Annotated[str, Field(description="Session ID of a completed validation.")],
        column_name: Annotated[str, Field(description="Name of the new column to add.")],
        validation_target: Annotated[dict, Field(description="Validation target spec for the new column (same structure as config.validation_targets entries).")],
        confirmed: Annotated[bool, Field(description="Set True to approve and trigger the ColPatch run. Set False (default) to see the cost estimate first.")] = False,
    ) -> list[types.TextContent]:
        """Add a new column to a completed validation table.

        If confirmed=False, returns a cost ceiling estimate (max-case: all rows x
        all columns x per_cell_cost x 1.25; likely much less if run within 1 day
        of original validation due to cache).

        If confirmed=True, adds column header to source Excel, runs validation with
        updated config (old columns hit cache, new column fully validated), merges
        new column results into output Excel. No QC on column patch runs (single-column
        QC is not meaningful; full-table QC ran on the original validation).

        Only available after full validation completes (status=completed).
        """
        client = get_client()
        payload = {
            "column_name": column_name,
            "validation_target": validation_target,
            "confirmed": confirmed,
        }
        data = client.post(f"/sessions/{session_id}/columns/patch", json=payload)
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("patch_column", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
