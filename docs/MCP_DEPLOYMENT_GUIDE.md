# Hyperplexity MCP Server — Operations Guide

Logo: `C:\Users\ellio\OneDrive - Eliyahu.AI\Desktop\eliyahu.ai\Marketing\Images\hyperplexity\hyperplexity-logo-2.png`

---

## Architecture Overview

```
GitHub (source of truth)
    ↓  auto-deploy on push
Railway (live HTTP server)
    ↑  Smithery connects to this
Smithery (MCP registry — users discover + connect here)

PyPI (package distribution — separate, for stdio users)
    ↑  users install with: uvx mcp-server-hyperplexity
```

### What each piece does

| Component | What it does | Who uses it |
|-----------|-------------|-------------|
| **GitHub** | Stores the source code. Railway auto-deploys every time you push to `main`. | You (developer) |
| **Railway** | Runs the MCP server 24/7 as a Docker container. Exposes `https://mcp-server-hyperplexity-production.up.railway.app`. Smithery connects here. | Smithery (and any HTTP MCP client) |
| **Smithery** | Public MCP registry. Users browse it, click "Connect", enter their Hyperplexity API key, and get an MCP server wired into their AI client. | End users |
| **PyPI** | Package index. Users who run Claude Code or Claude Desktop locally install the package directly with `uvx` and run it as a stdio process on their own machine. | End users (local/stdio) |

---

## Credentials & Keys

> ⚠️ Store these securely. Rotate the GitHub PAT immediately if it is ever shared publicly.

### GitHub Personal Access Token (PAT)
Used to push code to the GitHub repo from the command line.

```
Token:  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
Scope:  repo (full control of private repositories)
Repo:   https://github.com/EliyahuAI/mcp-server-hyperplexity
```

**To rotate:** GitHub → Settings → Developer settings → Personal access tokens → Generate new token → replace above.

To use in git commands:
```bash
git remote set-url origin https://<PAT>@github.com/EliyahuAI/mcp-server-hyperplexity.git
git push origin main
```

### Hyperplexity API Key (for testing)
Used to test the live server end-to-end.

```
Key:  hpx_live_r0GWnJjjCHBKWP45ZzZkB28_MvUBREuOJfTLb4Mm
```

**Note:** This is a test key. Rotate at hyperplexity.ai/account if compromised.

### Railway
- Account: linked via GitHub OAuth — no separate credential needed
- Plan: **$5/month (Hobby)**
  - 1 replica (no autoscaling)
  - Resources allocated: **1 vCPU, 1 GB memory**
  - If traffic grows and you need autoscaling → upgrade to $20/month Pro plan
- Project URL: `https://mcp-server-hyperplexity-production.up.railway.app`
- No `HYPERPLEXITY_API_KEY` set in Railway environment — each Smithery user passes their own key via `Authorization: Bearer` header

### Smithery
- Account: linked via GitHub OAuth
- Namespace: `hyperplexity`
- Server slug: `production`
- Run.tools URL: `production--hyperplexity.run.tools` (Smithery's hosted domain, not used — we use Railway directly)
- MCP Server URL entered in Smithery: `https://mcp-server-hyperplexity-production.up.railway.app`

### PyPI
- Package name: `mcp-server-hyperplexity`
- API token: `pypi-AgEIcHlwaS5vcmcCJDkxYTE1Y2I2LTNmN2YtNGRiZS1hMWU1LTgxMmQyODhjYWFkYwACKlszLCI5MDkwYmQ1Ny0xMmE3LTRiZDktYmU0OC00YjczNmZjZjdjNjMiXQAABiBPsReon8hbtiLYvptFl3gEJvspJl_mEQ9iFJCDSnkIIQ`
- Publishing is automated via GitHub Actions on every push to `main` (secret `PYPI_API_TOKEN` set in repo settings)

---

## Repository Layout

```
mcp/
├── src/hyperplexity_mcp/
│   ├── server.py          # Entry point — FastMCP setup, dual transport, custom routes
│   ├── client.py          # HyperplexityClient + contextvar for per-request API key
│   ├── guidance.py        # _guidance_* functions injected into every tool response
│   └── tools/
│       ├── account.py         # get_balance, get_usage
│       ├── uploads.py         # upload_file, confirm_upload
│       ├── jobs.py            # create_job, get_job_status, get_job_messages, wait_for_job
│       ├── validation.py      # approve_validation, get_results, get_reference_results
│       ├── job_actions.py     # update_table, reference_check
│       └── conversations.py   # start_table_maker, get_conversation,
│                              # send_conversation_reply, refine_config,
│                              # wait_for_conversation
├── pyproject.toml         # Package metadata + version number
├── Dockerfile             # Railway deployment config
├── smithery.yaml          # Smithery registry config (stdio commandFunction + configSchema)
└── OPERATIONS_GUIDE.md    # This file
```

---

## How the Dual Transport Works

The server supports two transports selected by the `MCP_TRANSPORT` environment variable:

### stdio (default — for local users)
```
User installs:  uvx mcp-server-hyperplexity
Process:        runs locally on the user's machine
API key:        set in the user's environment (HYPERPLEXITY_API_KEY=hpx_live_...)
Used by:        Claude Code, Claude Desktop, any local MCP client
```

### http (Railway — for Smithery and remote clients)
```
Process:        runs on Railway, always on
API key:        user passes it as Authorization: Bearer <key> header per-request
                stored in a contextvar so each user's key is isolated per-request
MCP endpoint:   POST https://mcp-server-hyperplexity-production.up.railway.app/
Health check:   GET  .../health  → "ok"
Server card:    GET  .../.well-known/mcp/server-card.json
```

The `_ApiKeyMiddleware` in `server.py` extracts the `Authorization: Bearer` or `X-Api-Key` header and stores it in a `ContextVar` so each concurrent user's key is isolated. No key is stored in Railway's environment — each request carries its own.

---

## Deploying a Change

### 1. Edit files in `/tmp/mcp_build/` (or copy from `mcp/`)

The `/tmp/mcp_build/` directory is a WSL-native clone of the GitHub repo used for building and committing. Edits go there because building from the Windows filesystem causes a cross-device link error in WSL.

### 2. Bump the version

In `/tmp/mcp_build/pyproject.toml`:
```toml
version = "1.0.X"   ← increment this
```

Also update the `"version"` string in the `server_card` function in `server.py`.

### 3. Commit and push

```bash
cd /tmp/mcp_build

# Set PAT in remote URL (only needed if not already set)
git remote set-url origin https://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@github.com/EliyahuAI/mcp-server-hyperplexity.git

git add -A
git commit -m "fix: description of change"
git push origin main
```

Railway detects the push and auto-deploys within ~2 minutes. Confirm:
```bash
curl https://mcp-server-hyperplexity-production.up.railway.app/.well-known/mcp/server-card.json
# → should show new version number
```

### 4. Copy back to local mcp/ directory

```bash
cp /tmp/mcp_build/src/hyperplexity_mcp/server.py \
   "/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/mcp/src/hyperplexity_mcp/server.py"
cp /tmp/mcp_build/pyproject.toml \
   "/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/mcp/pyproject.toml"
# etc. for any other changed files
```

---

## Updating the API Guide (eliyahu.ai/api-guide)

The public API guide at `https://eliyahu.ai/api-guide` is generated from `mcp/README.md` and served as HTML from S3.

### Source files
| File | Role |
|------|------|
| `mcp/README.md` | Source of truth — edit this |
| `frontend/API_GUIDE.html` | Generated HTML — do not edit directly |
| `frontend/md_to_html.py` | Converter script |
| `deployment/upload_api_docs.py` | S3 upload script |

### Full update process

```bash
cd "/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator"

# Step 1: Edit mcp/README.md as needed

# Step 2: Regenerate the HTML
python3 frontend/md_to_html.py
# → writes frontend/API_GUIDE.html

# Step 3: Dry run to confirm what will be uploaded
python deployment/upload_api_docs.py --dry-run
# Shows:
#   hyperplexity_client.py  → s3://hyperplexity-storage/website_downloads/examples/
#   01_validate_table.py    → s3://hyperplexity-storage/website_downloads/examples/
#   02_generate_table.py    → ...
#   03_update_table.py      → ...
#   04_reference_check.py   → ...
#   README.md               → s3://hyperplexity-storage/website_downloads/API_GUIDE.md
#   API_GUIDE.html          → s3://hyperplexity-storage/website_downloads/API_GUIDE.html

# Step 4: Upload (requires AWS credentials in environment)
python deployment/upload_api_docs.py --upload
```

### What gets uploaded where

| Local file | S3 key | Served at |
|-----------|--------|-----------|
| `mcp/README.md` | `website_downloads/API_GUIDE.md` | Download link |
| `frontend/API_GUIDE.html` | `website_downloads/API_GUIDE.html` | `eliyahu.ai/api-guide` (via CloudFront) |
| `mcp/examples/*.py` | `website_downloads/examples/*.py` | Download links in README |

### AWS credentials
The upload script uses `boto3` which reads from `~/.aws/credentials` or environment variables:
```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
```

---

## Publishing to PyPI

PyPI publishing is **automated via GitHub Actions** (`.github/workflows/publish.yml`). Every push to `main` triggers a build and upload automatically using the `PYPI_API_TOKEN` secret.

After a push, users can install the new version immediately:
```bash
uvx mcp-server-hyperplexity
```

### Manual publish (if needed)

```bash
cd /tmp/mcp_build
python3 -m build
python3 -m twine upload dist/* --username __token__ --password pypi-AgEIcHlwaS5vcmcCJDkxYTE1Y2I2LTNmN2YtNGRiZS1hMWU1LTgxMmQyODhjYWFkYwACKlszLCI5MDkwYmQ1Ny0xMmE3LTRiZDktYmU0OC00YjczNmZjZjdjNjMiXQAABiBPsReon8hbtiLYvptFl3gEJvspJl_mEQ9iFJCDSnkIIQ
```

---

## Updating Smithery

Smithery reads the live Railway server on every connection. You do **not** need to republish to Smithery after pushing code — Railway auto-deploys and Smithery connects fresh each time.

If you change the `smithery.yaml` (e.g. add a new config option), you need to re-submit via Smithery's dashboard:
1. Go to your server in Smithery → Edit
2. Re-submit with the updated YAML

To trigger a quality rescan after making improvements:
1. Go to your server in Smithery
2. Click "Rescan" or re-save the server settings

---

## Testing the Live Endpoint

```bash
# Health check
curl https://mcp-server-hyperplexity-production.up.railway.app/health
# → ok

# Server card (check version)
curl https://mcp-server-hyperplexity-production.up.railway.app/.well-known/mcp/server-card.json

# MCP initialize handshake (what Smithery does on connect)
curl -X POST https://mcp-server-hyperplexity-production.up.railway.app/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
# → SSE event with serverInfo and capabilities

# Test a tool call (requires a real API key)
curl -X POST https://mcp-server-hyperplexity-production.up.railway.app/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hpx_live_r0GWnJjjCHBKWP45ZzZkB28_MvUBREuOJfTLb4Mm" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_balance","arguments":{}}}'
```

---

## Railway Resource Limits

Current plan: **Hobby ($5/month)**

| Setting | Value |
|---------|-------|
| Plan | Hobby |
| vCPU limit | 1 vCPU |
| Memory limit | 1 GB |
| Replicas | 1 (no autoscaling) |
| Monthly cost | ~$5 |

The server is lightweight (pure Python async proxy, no ML inference) and comfortably fits within these limits for moderate traffic. If Smithery usage grows and you see Railway CPU throttling or OOM errors, upgrade to **Pro ($20/month)** which allows multiple replicas and autoscaling.

---

## Current Version History

| Version | What changed |
|---------|-------------|
| 1.0.1 | Initial PyPI release |
| 1.0.2 | Fix: lazy client init (get_client inside tool functions, not at register time) |
| 1.0.3 | Fix: per-request API key via contextvar; pure-ASGI middleware for Smithery |
| 1.0.4 | Fix: use server.custom_route for health/server-card to preserve lifespan |
| 1.0.5 | Fix: disable DNS rebinding protection so Railway hostname is accepted |
| 1.0.6 | Fix: mount MCP at root path "/" so Smithery base URL works without /mcp suffix |
| 1.0.7 | Feat: param descriptions, tool annotations, server metadata for Smithery quality score |
| 1.0.8–1.0.9 | Various guidance and wait_for_job improvements |
| 1.0.10 | Feat: cells[col].value (rename from full_value); preview download_url + metadata_url at preview_complete; reference check metadata_url fix; CI auto-publish |
