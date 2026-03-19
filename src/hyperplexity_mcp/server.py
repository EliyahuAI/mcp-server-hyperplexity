#!/usr/bin/env python3
"""
Hyperplexity MCP Server — entry point.

Registers all 18 tools across 6 modules. Supports two transports:

  stdio (default) — for Claude Code / Claude Desktop / local MCP clients
    HYPERPLEXITY_API_KEY=hpx_live_... mcp-server-hyperplexity

  streamable-http — for Smithery and remote HTTP clients
    MCP_TRANSPORT=http HYPERPLEXITY_API_KEY=hpx_live_... mcp-server-hyperplexity
    Listens on 0.0.0.0:$PORT (default 8000), path /mcp

Claude Code (one-liner):
    claude mcp add hyperplexity uvx mcp-server-hyperplexity \\
      -e HYPERPLEXITY_API_KEY=hpx_live_your_key_here

Claude Desktop config:
    {
      "mcpServers": {
        "hyperplexity": {
          "command": "uvx",
          "args": ["mcp-server-hyperplexity"],
          "env": { "HYPERPLEXITY_API_KEY": "hpx_live_your_key_here" }
        }
      }
    }

Get your API key at hyperplexity.ai/account — new accounts get $20 free credits.
"""

import os

from mcp.server.fastmcp import FastMCP

# ---- Tool modules ----
from hyperplexity_mcp.tools import account, uploads, jobs, validation, job_actions, conversations

# ---------------------------------------------------------------------------
# Server + tool registration
# ---------------------------------------------------------------------------

server = FastMCP("hyperplexity")

# Each module's register() calls @server.tool() decorators, adding tools to
# the FastMCP instance.
account.register(server)
uploads.register(server)
jobs.register(server)
validation.register(server)
job_actions.register(server)
conversations.register(server)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        import json
        import uvicorn
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse, Response
        from starlette.routing import Mount, Route
        from hyperplexity_mcp.client import _request_api_key

        # Pure-ASGI middleware — avoids BaseHTTPMiddleware breaking SSE/streaming.
        class _ApiKeyMiddleware:
            """Extract HYPERPLEXITY_API_KEY from Authorization: Bearer or X-Api-Key header."""
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if scope["type"] in ("http", "websocket"):
                    headers = dict(scope.get("headers", []))
                    auth = headers.get(b"authorization", b"").decode()
                    key = ""
                    if auth.lower().startswith("bearer "):
                        key = auth[7:].strip()
                    if not key:
                        key = headers.get(b"x-api-key", b"").decode().strip()
                    token = _request_api_key.set(key) if key else None
                    try:
                        await self.app(scope, receive, send)
                    finally:
                        if token is not None:
                            _request_api_key.reset(token)
                else:
                    await self.app(scope, receive, send)

        # /.well-known/mcp/server-card.json — lets Smithery skip auto-scanning.
        async def server_card(request: Request) -> JSONResponse:
            return JSONResponse({
                "name": "hyperplexity",
                "version": "1.0.3",
                "description": (
                    "Generate, validate, and fact-check research tables with "
                    "AI-sourced citations and per-cell confidence scores."
                ),
                "mcp_endpoint": "/mcp",
            })

        # Health check for Railway / load balancers.
        async def health(request: Request) -> Response:
            return Response("ok")

        port = int(os.getenv("PORT", "8000"))
        mcp_app = server.streamable_http_app()

        app = Starlette(routes=[
            Route("/.well-known/mcp/server-card.json", server_card),
            Route("/health", health),
            Mount("/", app=mcp_app),
        ])
        app = _ApiKeyMiddleware(app)
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        server.run()


if __name__ == "__main__":
    main()
