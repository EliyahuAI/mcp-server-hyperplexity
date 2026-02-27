# MCP Server Distribution Guide
### Complete Release Guide — Claude Code · OpenAI Codex · OpenClaw

*Packaging · Publishing · Marketing · Per-Platform Config*

---

## Table of Contents

1. [Strategic Overview](#part-1--strategic-overview)
2. [Packaging Your Server](#part-2--packaging-your-server)
3. [Publishing](#part-3--publishing)
4. [Per-Platform Configuration](#part-4--per-platform-configuration)
5. [Discoverability & Marketing](#part-5--discoverability--marketing)
6. [Best Practices & Launch Checklist](#part-6--best-practices--launch-checklist)

---

# PART 1 — STRATEGIC OVERVIEW

## The Three-Platform Landscape

Distributing a Python MCP server to reach all three major agentic environments — Claude Code, OpenAI Codex, and OpenClaw — requires a clear strategy. Each platform has a different user profile, installation method, and discovery mechanism. This guide walks you through the entire lifecycle: from packaging and publishing, to per-platform configuration, to smart marketing that gets your server noticed.

## Platform Comparison at a Glance

| Attribute | Claude Code | Codex | OpenClaw |
|---|---|---|---|
| **User type** | Developers / CLI power users | Developers using OpenAI API | Personal automation enthusiasts |
| **Discovery** | MCP servers GitHub list, direct CLI | OpenAI docs, GitHub | ClawHub registry, community |
| **Install method** | uvx / pip, `claude mcp add` CLI | HTTP/SSE remote endpoint | SKILL.md via ClawHub |
| **Transport** | stdio (subprocess) | HTTP / SSE (remote) | stdio + optional HTTP |
| **Auth** | Environment variables | Environment variables / OAuth | Environment variables |
| **Config file** | `~/.claude/claude.json` | API call parameters | `~/.openclaw/workspace/` |

> **Key Insight:** One well-packaged PyPI release covers Claude Code and OpenClaw (both use uvx/stdio). Codex requires an additional HTTP transport deployment, but shares the same underlying tool logic. Build once, deploy twice.

---

# PART 2 — PACKAGING YOUR SERVER

## Recommended Directory Layout

```
mcp-server-yourapi/
├── src/
│   └── yourapi/
│       ├── __init__.py
│       ├── server.py        ← main MCP server logic
│       └── http_server.py   ← HTTP/SSE transport for Codex
├── pyproject.toml
├── README.md
├── SKILL.md                 ← OpenClaw skill descriptor
├── .env.example
└── LICENSE
```

## pyproject.toml — Complete Template

This is the single most important file. It controls how your package is discovered, installed, and run. Pay particular attention to the `[project.scripts]` entry — it creates the CLI entrypoint that `uvx` uses.

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mcp-server-yourapi"
version = "0.1.0"
description = "MCP server for Your API — description of what it does"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
keywords = ["mcp", "model-context-protocol", "claude", "ai", "llm", "agent"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Topic :: Software Development :: Libraries",
]
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
]

[project.urls]
Homepage = "https://github.com/yourname/mcp-server-yourapi"
Repository = "https://github.com/yourname/mcp-server-yourapi"

[project.scripts]
mcp-server-yourapi = "yourapi.server:main"
```

## server.py — Dual Transport Entry Point

Your `server.py` needs a `main()` function that can run in either stdio mode (for Claude Code and OpenClaw) or HTTP/SSE mode (for Codex). Detect the mode via an environment variable.

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
import asyncio, os

app = Server("yourapi")

@app.list_tools()
async def list_tools():
    return [...]  # your tool definitions

@app.call_tool()
async def call_tool(name, arguments):
    ...  # your tool logic

async def serve_stdio():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

async def serve_http():
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    import uvicorn
    transport = SseServerTransport("/messages")
    starlette_app = Starlette(routes=transport.routes(app))
    await uvicorn.serve(starlette_app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

def main():
    mode = os.getenv("MCP_TRANSPORT", "stdio")
    if mode == "http":
        asyncio.run(serve_http())
    else:
        asyncio.run(serve_stdio())

if __name__ == "__main__":
    main()
```

## Environment Variables — Best Practices

Never hardcode secrets. All credentials must come from environment variables. Provide a thorough `.env.example` so users know exactly what they need.

| Variable | Description |
|---|---|
| `YOUR_API_KEY` | **Required.** API key from yourapi.com/keys |
| `YOUR_API_BASE_URL` | Optional. Default: `https://api.yourapi.com/v1` |
| `MCP_TRANSPORT` | Optional. `stdio` (default) or `http` for Codex |
| `PORT` | Optional. HTTP port when `MCP_TRANSPORT=http`. Default: 8000 |
| `LOG_LEVEL` | Optional. `DEBUG` / `INFO` / `WARNING`. Default: INFO |

---

# PART 3 — PUBLISHING

## Publishing to PyPI

PyPI is the primary distribution channel for Python MCP servers. Once published, your server is installable with a single `uvx` command — no git clone or manual setup required.

### Step-by-Step PyPI Release

```bash
# 1. Create a PyPI account at pypi.org and get an API token

# 2. Install build tools
pip install build twine --break-system-packages

# 3. Build the distribution packages
python -m build
# Creates dist/mcp-server-yourapi-0.1.0.tar.gz and .whl

# 4. Test on TestPyPI first (strongly recommended)
twine upload --repository testpypi dist/*
uvx --index-url https://test.pypi.org/simple/ mcp-server-yourapi

# 5. Publish to production PyPI
twine upload dist/*

# 6. Verify installation works cleanly
uvx mcp-server-yourapi --help
```

> **Versioning:** Use semantic versioning — MAJOR.MINOR.PATCH. Increment PATCH for bug fixes, MINOR for new tools/features, MAJOR for breaking changes. Tag every release on GitHub to match.

### Automate Releases with GitHub Actions

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI
on:
  release:
    types: [published]
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install build twine
      - run: python -m build
      - run: twine upload dist/*
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
```

## Deploying for Codex — HTTP Transport

OpenAI Codex uses MCP via HTTP/SSE rather than stdio. You need a publicly accessible endpoint. The same Docker container can handle both modes.

### Recommended Hosting Platforms

| Platform | Notes |
|---|---|
| **Railway.app** | Easiest. Connect GitHub repo, set env vars, get a URL instantly. Free tier available. |
| **Render.com** | Good free tier. Add a `render.yaml` to repo for one-click deploys. |
| **Fly.io** | More control, great for always-on servers. Generous free allowance. |
| **Docker / VPS** | Full control. Use if you already have infrastructure or need custom networking. |

### Dockerfile for HTTP Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
ENV MCP_TRANSPORT=http
ENV PORT=8000
EXPOSE 8000
CMD ["mcp-server-yourapi"]
```

---

# PART 4 — PER-PLATFORM CONFIGURATION

## Claude Code

Claude Code is Anthropic's CLI coding agent. It reads MCP server configuration from a JSON config file and manages servers as background processes. It supports both project-level and user-level configuration.

### Option A: One-liner CLI (recommended — document this prominently)

```bash
claude mcp add yourapi uvx mcp-server-yourapi \
  -e YOUR_API_KEY=your_key_here
```

### Option B: Manual config in `~/.claude/claude.json`

```json
{
  "mcpServers": {
    "yourapi": {
      "command": "uvx",
      "args": ["mcp-server-yourapi"],
      "env": {
        "YOUR_API_KEY": "your_key_here"
      }
    }
  }
}
```

### Option C: Project-level `.mcp.json` (for team sharing)

Add a `.mcp.json` file to your project root. Claude Code picks this up automatically when run inside that directory, so the whole team gets the server without individual setup.

```json
{
  "mcpServers": {
    "yourapi": {
      "command": "uvx",
      "args": ["mcp-server-yourapi"],
      "env": {
        "YOUR_API_KEY": "${YOUR_API_KEY}"
      }
    }
  }
}
```

---

## OpenAI Codex

Codex (via the Responses API) connects to MCP servers over HTTP rather than spawning a subprocess. You provide a URL to your deployed endpoint, and Codex calls it remotely. Your server must be publicly reachable.

### Connecting via the Responses API

```python
from openai import OpenAI

client = OpenAI()
response = client.responses.create(
    model="codex-mini-latest",
    tools=[{
        "type": "mcp",
        "server_label": "yourapi",
        "server_url": "https://your-server.railway.app/sse",
        "require_approval": "never"
    }],
    input="Use the yourapi tool to ..."
)
```

> **Codex Tip:** Set `MCP_TRANSPORT=http` and deploy to Railway or Fly.io. Your `/sse` endpoint is what Codex connects to. Add a `/health` endpoint that returns `200 OK` so hosting platforms can verify your server is alive.

---

## OpenClaw (formerly Clawdbot / Moltbot)

OpenClaw uses a "skills" system. A skill is a `SKILL.md` file with YAML frontmatter that describes how to install and invoke your MCP server. Skills can be installed manually or discovered through ClawHub, OpenClaw's community registry.

### SKILL.md — Complete Template

Include this file in the root of your GitHub repo.

```yaml
---
name: yourapi
version: 0.1.0
description: >
  Access YourAPI through your OpenClaw agent. Use this skill when you need
  to [describe what your API does]. Supports [list key operations].
author: Your Name
homepage: https://github.com/yourname/mcp-server-yourapi
license: MIT
requires:
  env:
    YOUR_API_KEY:
      description: API key from yourapi.com/keys
      required: true
install:
  command: uvx
  args: ["mcp-server-yourapi"]
mcp:
  transport: stdio
tags: [api, productivity, automation]
---

# YourAPI Skill

This skill connects your OpenClaw agent to YourAPI.

## What this enables
- **Tool 1**: describe what it does
- **Tool 2**: describe what it does

## Setup
1. Get your API key at yourapi.com/keys
2. Add YOUR_API_KEY to your OpenClaw environment
3. Install: tell your agent 'install the yourapi skill'
```

### Submitting to ClawHub

ClawHub is OpenClaw's built-in skill registry. Getting listed here means users can install your skill by simply asking their agent. Submit by opening a pull request on the ClawHub repository.

```bash
# Steps to submit to ClawHub:
# 1. Fork https://github.com/openclaw/clawhub
# 2. Add your SKILL.md to the skills/ directory
# 3. Open a pull request with:
#    - Clear title: 'Add mcp-server-yourapi skill'
#    - Brief description of what your API does
#    - Confirmation that your PyPI package is live

# Once merged, OpenClaw users can install with:
# 'Install the yourapi skill' (sent as a chat message to their agent)
```

> **OpenClaw Security Note:** OpenClaw users are security-conscious after Cisco highlighted supply chain risks in community skills. Make your server open-source, clearly document what data it accesses, and avoid requesting unnecessary permissions. Transparency is your most powerful trust signal.

---

# PART 5 — DISCOVERABILITY & MARKETING

## Registries & Directories

Getting listed in the right places is more valuable than any other marketing activity. These are the places developers actively search for MCP servers.

| Registry | Action |
|---|---|
| **Smithery.ai** | Primary MCP marketplace — integrated directly into Cline's VS Code UI. Submit at smithery.ai/submit. High visibility. |
| **MCP Servers GitHub** | Anthropic's official list at github.com/modelcontextprotocol/servers. Open a PR. Many tools reference this list. |
| **ClawHub** | OpenClaw's built-in registry. Essential for the OpenClaw audience. PR to github.com/openclaw/clawhub. |
| **mcp.so** | Community MCP directory. Easy submission, good for additional exposure. |
| **PyPI** | Good discoverability via keyword search if `pyproject.toml` keywords are correct. |
| **awesome-mcp** | Community-curated GitHub list. Search GitHub for "awesome-mcp" and open a PR. |

## GitHub Repository Optimization

Many developers discover servers via GitHub search. Optimize your repo to surface in the right searches and convert visitors into installers.

**Repository settings to configure:**
- **Topics:** Add `mcp`, `model-context-protocol`, `claude`, `llm-tools`, `ai-agent`, `mcp-server`, `python`
- **Description:** One sentence on what your API does — not what MCP is
- **Website:** Link to your PyPI page or docs site
- **Releases:** Tag every version — release pages are indexed and build credibility

## README Structure

Your README is your landing page, sales pitch, and documentation all in one. Structure it so someone can go from zero to running your server in under 5 minutes.

| Section | Content |
|---|---|
| **Hero section** | One sentence: what your API does + one-liner install command. Lead with value. |
| **Badges** | PyPI version, Python version, license, Smithery install count. Social proof. |
| **What it does** | Bullet list of the tools your server exposes and what a user can do with each one. |
| **Quickstart** | Copy-pasteable commands for all 3 platforms. No explanation — just commands. |
| **Environment variables** | Table of all env vars, whether required, and where to get values. |
| **Tool reference** | For each tool: name, description, parameters, example output. |
| **Security** | Briefly note what data your server accesses and what it does not store. |
| **License** | MIT is preferred — it signals you want community adoption. |

### README Quickstart Section Template

````markdown
## Quickstart

### Claude Code
```bash
claude mcp add yourapi uvx mcp-server-yourapi -e YOUR_API_KEY=your_key
```

### OpenClaw
Tell your agent: *"Install the yourapi skill"*
Or manually: set `YOUR_API_KEY` in your env, then add to your workspace config.

### Codex (Responses API)
Deploy to Railway/Fly.io with `MCP_TRANSPORT=http`, then:
```python
tools=[{"type": "mcp", "server_url": "https://your-server.railway.app/sse"}]
```
````

## Community Marketing

The MCP ecosystem is tight-knit and moves fast. Authentic participation in these communities will drive more adoption than any ad or cold outreach.

| Channel | Strategy |
|---|---|
| **Anthropic Discord** | Share in #mcp-servers or #tools channels. Include a one-line description and install command. |
| **OpenClaw Discord** | Very active community. Share when your ClawHub skill is live. Offer to help users get set up. |
| **X / Twitter** | Tag @AnthropicAI and @steipete (OpenClaw creator). Use #MCP and #ModelContextProtocol hashtags. |
| **Hacker News** | Show HN post at launch. Lead with the problem you solve, not the technology. |
| **Reddit** | r/ClaudeAI, r/LocalLLaMA, r/OpenAI. Be genuinely helpful, not promotional. |
| **Dev.to / Medium** | Write a tutorial: "How I connected [Your API] to Claude Code in 10 minutes." Drives long-tail search traffic. |

> **Marketing Principle:** Developers trust other developers. The most effective marketing is a clear demo, a working install command, and someone in a Discord saying "I got it working in 5 minutes." Prioritize making the first-install experience frictionless above all else.

---

# PART 6 — BEST PRACTICES & LAUNCH CHECKLIST

## Tool Design Best Practices

How you design your tools is as important as how you publish them. Well-designed tools get used; poorly-described tools get abandoned.

### Writing Good Tool Descriptions

Tool descriptions are read by the LLM to decide when and how to use your tools. Write them as if explaining to a smart person who has never seen your API.

**Bad:**
```
search(query) — searches things
```

**Good:**
```
search(query: str, limit: int = 10) — Search the product catalog by keyword or
natural language description. Returns a list of matching products with name, price,
availability, and product ID. Use this when the user wants to find or browse products.
Example: search('wireless headphones under $100')
```

### Tool Naming Conventions

- **Use snake_case:** `get_customer`, `list_orders`, `create_invoice`
- **Start with a verb:** `get_`, `list_`, `create_`, `update_`, `delete_`, `search_`
- **Be specific:** `get_order_by_id` is better than `get_thing`
- **Keep it flat:** 5–10 focused tools beats one mega-tool with 20 parameters

### Error Handling

Return structured, helpful error messages. When a tool fails, the LLM should understand what went wrong and either retry correctly or explain the issue to the user.

```python
# Good error response pattern
return {
    "error": "INVALID_API_KEY",
    "message": "The API key provided is invalid or expired.",
    "help": "Get a new key at yourapi.com/keys"
}

# Not this
return {"error": "401"}
```

## Security Best Practices

Security is a first-class concern in the MCP ecosystem, especially after Cisco's research highlighted supply chain risks in OpenClaw skills. Being security-conscious is both the right thing to do and a genuine marketing advantage.

| Practice | Details |
|---|---|
| **Read-only defaults** | Where possible, make destructive operations (delete, write, send) require explicit opt-in via env var. Default to read-only. |
| **Log what you access** | Document clearly in your README what data your tools read and write. Never log API keys. |
| **Validate inputs** | Sanitize and validate all tool inputs before passing to your API. Reject unexpected input shapes. |
| **Pin dependencies** | Use exact version pins in `pyproject.toml` for security-sensitive packages. |
| **Audit trail** | Consider logging tool invocations (without payloads) so users can verify what their agent did. |
| **No telemetry** | Do not send any usage data or analytics. OpenClaw users in particular are highly sensitive to this. |

---

## Pre-Launch Checklist

### Package & Code
- [ ] `pyproject.toml` has correct name (`mcp-server-yourapi`), keywords, and entry point
- [ ] `server.py` has a working `main()` and supports both stdio and http transports
- [ ] `.env.example` lists every required and optional environment variable
- [ ] All secrets come from environment variables — nothing hardcoded
- [ ] Tool descriptions are clear, specific, and include examples
- [ ] Error responses are structured and helpful
- [ ] `uvx mcp-server-yourapi` works cleanly from a fresh environment *(test this!)*

### Publishing
- [ ] Package is live on PyPI and installable with `uvx`
- [ ] HTTP endpoint is deployed and accessible (for Codex)
- [ ] GitHub repo has correct topics, description, and a tagged release
- [ ] GitHub Actions workflow publishes new releases automatically

### Documentation
- [ ] README has hero section, quickstart for all 3 platforms, tool reference, and env var table
- [ ] `SKILL.md` is in repo root with correct YAML frontmatter
- [ ] `.mcp.json` example is included for Claude Code project-level config

### Registries
- [ ] Submitted to Smithery.ai
- [ ] PR opened to `modelcontextprotocol/servers` GitHub list
- [ ] PR opened to ClawHub (`github.com/openclaw/clawhub`)
- [ ] Submitted to `mcp.so`

### Community
- [ ] Announcement drafted for Anthropic Discord, OpenClaw Discord, X
- [ ] First-install tested by at least one person who wasn't involved in building it
- [ ] Support channel defined (GitHub Issues or Discord) and linked from README
