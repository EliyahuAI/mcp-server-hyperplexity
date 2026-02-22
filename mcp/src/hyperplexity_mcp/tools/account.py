"""Account tools: get_balance, get_usage."""

from __future__ import annotations

import json
from typing import Optional

from mcp import types

from hyperplexity_mcp.client import get_client
from hyperplexity_mcp.guidance import build_guidance


def register(server):
    client = get_client()

    @server.tool()
    def get_balance() -> list[types.TextContent]:
        """Return the current account credit balance in USD."""
        data = client.get("/account/balance")
        data["_guidance"] = build_guidance("get_balance", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def get_usage(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[types.TextContent]:
        """Return API usage history. Dates in YYYY-MM-DD format."""
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
