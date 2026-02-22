#!/usr/bin/env python3
"""
Hyperplexity MCP Server — entry point.

Registers all 17 tools across 6 modules and runs a stdio-based MCP server
via FastMCP (the high-level MCP Python SDK).

Usage (after pip install):
    HYPERPLEXITY_API_KEY=hpx_live_... mcp-server-hyperplexity

Usage (development):
    HYPERPLEXITY_API_KEY=hpx_live_... python3 -m hyperplexity_mcp.server

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
    # FastMCP defaults to stdio transport, which is what MCP clients expect.
    server.run()


if __name__ == "__main__":
    main()
