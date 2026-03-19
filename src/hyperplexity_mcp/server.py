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
        import uvicorn
        from starlette.middleware.base import BaseHTTPMiddleware
        from hyperplexity_mcp.client import _request_api_key

        class _ApiKeyMiddleware(BaseHTTPMiddleware):
            """Extract API key from Authorization: Bearer header and store in contextvar.

            This lets each Smithery user supply their own HYPERPLEXITY_API_KEY per
            request rather than requiring a single server-level env var.
            """
            async def dispatch(self, request, call_next):
                auth = request.headers.get("authorization", "")
                key = ""
                if auth.lower().startswith("bearer "):
                    key = auth[7:].strip()
                if not key:
                    key = request.headers.get("x-api-key", "").strip()
                token = _request_api_key.set(key) if key else None
                try:
                    return await call_next(request)
                finally:
                    if token is not None:
                        _request_api_key.reset(token)

        port = int(os.getenv("PORT", "8000"))
        app = server.streamable_http_app()
        app.add_middleware(_ApiKeyMiddleware)
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        server.run()


if __name__ == "__main__":
    main()
