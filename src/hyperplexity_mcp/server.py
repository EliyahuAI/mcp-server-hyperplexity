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
from mcp.server.fastmcp.server import Icon
from mcp.server.transport_security import TransportSecuritySettings

# ---- Tool modules ----
from hyperplexity_mcp.tools import account, uploads, jobs, validation, job_actions, conversations

# ---------------------------------------------------------------------------
# Server + tool registration
# ---------------------------------------------------------------------------

# Disable DNS-rebinding protection so the server is reachable from Railway /
# Smithery (non-localhost hosts). stdio mode ignores this setting entirely.
# Mount at "/" so the Railway base URL works without requiring a "/mcp" suffix.
server = FastMCP(
    "hyperplexity",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    streamable_http_path="/",
    instructions=(
        "Hyperplexity lets you generate, validate, and fact-check research tables with "
        "AI-sourced citations and per-cell confidence scores. "
        "Use start_table_maker to create a new table from a natural language description, "
        "or upload_file + confirm_upload to validate an existing Excel/CSV file. "
        "Every cell in the output table has a confidence score and citation links. "
        "Full workflow: start_table_maker → wait_for_conversation → wait_for_job → "
        "approve_validation → wait_for_job → get_results."
    ),
    website_url="https://hyperplexity.ai",
    icons=[Icon(src="https://hyperplexity.ai/favicon.ico", mimeType="image/x-icon")],
)

# Each module's register() calls @server.tool() decorators, adding tools to
# the FastMCP instance.
account.register(server)
uploads.register(server)
jobs.register(server)
validation.register(server)
job_actions.register(server)
conversations.register(server)

# ---------------------------------------------------------------------------
# Prompts — workflow starters surfaced in Smithery's Capabilities section
# ---------------------------------------------------------------------------

@server.prompt()
def generate_table(description: str, columns: str = "") -> str:
    """Generate a new research table from a natural language description.

    description: What the table should cover (topic, entities, scope).
    columns: Optional comma-separated list of columns to include.
    """
    col_hint = f" Include these columns: {columns}." if columns else ""
    return (
        f"Use start_table_maker to create a research table with this description: "
        f"{description}.{col_hint} "
        f"Once the conversation starts, answer any clarifying questions, then "
        f"call wait_for_conversation (expected_seconds=120) until trigger_execution=True. "
        f"Then call wait_for_job to track the preview, review the preview_table and "
        f"cost_estimate, and call approve_validation to run the full table. "
        f"Finally call wait_for_job again and get_results to retrieve the finished table."
    )


@server.prompt()
def validate_file(file_path: str, instructions: str = "") -> str:
    """Validate an existing Excel or CSV file with AI fact-checking.

    file_path: Absolute path to the local .xlsx or .csv file.
    instructions: Optional description of what to validate (bypasses the interview).
    """
    file_type = "excel" if file_path.lower().endswith((".xlsx", ".xls")) else "csv"
    instr_hint = f' Pass instructions="{instructions}" to confirm_upload to skip the interview.' if instructions else ""
    return (
        f"Validate the file at {file_path}. "
        f"1. Call upload_file(file_path='{file_path}', file_type='{file_type}'). "
        f"2. Call confirm_upload with the returned session_id, s3_key, and filename.{instr_hint} "
        f"3. Call wait_for_job (timeout_seconds=900) until preview_complete. "
        f"4. Review the preview_table and cost_estimate, then call approve_validation. "
        f"5. Call wait_for_job again until completed, then get_results."
    )


@server.prompt()
def fact_check_text(text: str) -> str:
    """Fact-check a text passage by extracting and verifying its claims.

    text: The text to fact-check (works best with 4+ factual claims).
    """
    return (
        f"Run a reference check on the following text using reference_check(text=...). "
        f"After the preview completes (wait_for_job until preview_complete), review "
        f"the claims_summary and cost_estimate, then call approve_validation to verify "
        f"all claims. Retrieve final results with get_results.\n\nText:\n{text}"
    )

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        import uvicorn
        from starlette.requests import Request
        from starlette.responses import JSONResponse, Response
        from hyperplexity_mcp.client import _request_api_key

        # Pure-ASGI middleware — avoids BaseHTTPMiddleware breaking SSE/streaming.
        class _ApiKeyMiddleware:
            """Extract API key from Authorization: Bearer, X-Api-Key header, or ?api_key= query param."""
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
                    if not key:
                        from urllib.parse import parse_qs
                        qs = parse_qs(scope.get("query_string", b"").decode())
                        key = (qs.get("api_key", [""])[0] or qs.get("apiKey", [""])[0]).strip()
                    token = _request_api_key.set(key) if key else None
                    try:
                        await self.app(scope, receive, send)
                    finally:
                        if token is not None:
                            _request_api_key.reset(token)
                else:
                    await self.app(scope, receive, send)

        # /.well-known/mcp/server-card.json — lets Smithery skip auto-scanning.
        # /.health — health check for Railway / load balancers.
        # Registered via server.custom_route so they're included inside the
        # streamable_http_app() Starlette instance (preserving its lifespan).
        @server.custom_route("/.well-known/mcp/server-card.json", methods=["GET"])
        async def server_card(request: Request) -> JSONResponse:
            return JSONResponse({
                "name": "hyperplexity",
                "version": "1.0.17",
                "description": (
                    "Generate, validate, and fact-check research tables with "
                    "AI-sourced citations and per-cell confidence scores."
                ),
                "mcp_endpoint": "/",
            })

        @server.custom_route("/health", methods=["GET"])
        async def health(request: Request) -> Response:
            return Response("ok")

        port = int(os.getenv("PORT", "8000"))
        app = server.streamable_http_app()
        app = _ApiKeyMiddleware(app)
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        server.run()


if __name__ == "__main__":
    main()
