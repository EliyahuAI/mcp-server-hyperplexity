#!/usr/bin/env python3
"""
Hyperplexity MCP Server — entry point.

Registers all 17 tools across 5 modules and runs a stdio-based MCP server
via FastMCP (the high-level MCP Python SDK).

Usage (shell):
    HYPERPLEXITY_API_KEY=hpx_live_... python3 mcp/server.py

Claude Desktop config (~/.config/claude/claude_desktop_config.json or
~/Library/Application Support/Claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "hyperplexity": {
          "command": "python3",
          "args": ["/absolute/path/to/mcp/server.py"],
          "env": { "HYPERPLEXITY_API_KEY": "hpx_live_your_key_here" }
        }
      }
    }

Setup:
    cd mcp
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    # Then use the venv python in the Claude Desktop config:
    #   "command": "/absolute/path/to/mcp/.venv/bin/python3"
"""

import sys
import os

# Ensure mcp/ directory is on sys.path so sibling modules (client, guidance,
# tools.*) can be imported regardless of the working directory.
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from mcp.server.fastmcp import FastMCP

# ---- Tool modules ----
from tools import account, uploads, jobs, validation, job_actions, conversations

# ---------------------------------------------------------------------------
# Server + tool registration
# ---------------------------------------------------------------------------

server = FastMCP("hyperplexity")

# Each module's register() calls @server.tool() decorators, adding tools to
# the FastMCP instance.  Modules are small so they import fast.
account.register(server)
uploads.register(server)
jobs.register(server)
validation.register(server)
job_actions.register(server)
conversations.register(server)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # FastMCP defaults to stdio transport, which is what MCP clients expect.
    server.run()
