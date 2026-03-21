"""Account tools: get_balance, get_usage."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp import types
from mcp.types import ToolAnnotations
from pydantic import Field

from hyperplexity_mcp.client import get_client
from hyperplexity_mcp.guidance import build_guidance


def register(server):

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def get_balance() -> list[types.TextContent]:
        """Return the current account credit balance in USD."""
        client = get_client()
        data = client.get("/account/balance")
        data["_guidance"] = build_guidance("get_balance", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def get_usage(
        start_date: Annotated[Optional[str], Field(description="Filter start date in YYYY-MM-DD format.")] = None,
        end_date: Annotated[Optional[str], Field(description="Filter end date in YYYY-MM-DD format.")] = None,
        limit: Annotated[Optional[int], Field(description="Maximum number of records to return.")] = None,
        offset: Annotated[Optional[int], Field(description="Number of records to skip for pagination.")] = None,
    ) -> list[types.TextContent]:
        """Return API usage history. Dates in YYYY-MM-DD format."""
        client = get_client()
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        data = client.get("/account/usage", params=params or None)
        data["_guidance"] = build_guidance("get_usage", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
