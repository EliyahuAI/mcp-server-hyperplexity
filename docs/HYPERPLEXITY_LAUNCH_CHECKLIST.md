# Hyperplexity Launch Checklist

**Goal:** Get `hyperplexity.ai` live, the MCP server on PyPI, and the API accessible at `api.hyperplexity.ai`.

---

## Part A — GitHub Repository (do this first)

The MCP server code lives in `mcp/` in this repo. It needs its own **public GitHub repo** so PyPI and the registries can link to it. The current CodeCommit repo stays as-is (private infrastructure).

### A1 — Create the GitHub repo
- [ ] Go to github.com, sign in as **EliyahuAI**
- [ ] Click **New repository**
  - Name: `mcp-server-hyperplexity`
  - Visibility: **Public**
  - Do NOT initialize with README (we'll push our own)
- [ ] Copy the repo URL: `https://github.com/EliyahuAI/mcp-server-hyperplexity.git`

### A2 — Push the MCP code
Run these commands from your terminal (the `mcp/` folder contents become the root of the new repo):

```bash
# Create a fresh local repo from just the mcp/ directory
cd "/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/mcp"
git init
git add .
git commit -m "feat: initial release of Hyperplexity MCP server v1.0.0"
git branch -M main
git remote add origin https://github.com/EliyahuAI/mcp-server-hyperplexity.git
git push -u origin main
```

### A3 — Configure the repo on GitHub
After pushing, go to the repo settings on GitHub:
- [ ] **Description:** "Generate, validate, and fact-check research tables — MCP server for Claude, Claude Desktop, and OpenClaw"
- [ ] **Website:** `https://hyperplexity.ai/mcp`
- [ ] **Topics:** click the gear → add: `mcp` `model-context-protocol` `claude` `ai-agent` `data-validation` `research` `fact-check` `hyperplexity`
- [ ] Make sure the repo is **Public**

### A4 — Update URLs in pyproject.toml
Once the GitHub repo is live, open `mcp/pyproject.toml` and update the Repository URL:
```toml
Repository = "https://github.com/EliyahuAI/mcp-server-hyperplexity"
```
Then also update the same URL in `mcp/README.md` (the security section links to it).

---

## Part B — AWS: Custom Domains for hyperplexity.ai

### B1 — ACM Certificate (do this in us-east-1)
- [ ] Open AWS Console → **Certificate Manager** → make sure you're in **us-east-1**
- [ ] Click **Request** → **Request a public certificate**
- [ ] Add both domain names:
  - `hyperplexity.ai`
  - `*.hyperplexity.ai`  ← covers api, app, www, etc.
- [ ] Validation method: **DNS validation**
- [ ] Click through to finish → open the certificate → click **Create records in Route 53** (if your DNS is in Route 53) OR copy the CNAME name/value and add it manually at your registrar
- [ ] Wait for status to show **Issued** (usually 1–5 minutes)
- [ ] Copy the **Certificate ARN** — you'll need it in B2 and B3

### B2 — Custom Domain for the External API (api.hyperplexity.ai)

First, deploy the external API Gateway for prod if you haven't already:
```bash
cd "/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator"
python3 deployment/create_interface_package.py --environment prod --deploy-external-api
```
Note the **API ID** printed at the end.

Then in AWS Console:
- [ ] Open **API Gateway** → **Custom domain names** → **Create**
  - Domain name: `api.hyperplexity.ai`
  - TLS: 1.2
  - ACM certificate: select the one from B1
- [ ] After creating → go to **API mappings** tab → **Add mapping**
  - API: `hyperplexity-external-api` (the prod one)
  - Stage: `$default`
  - Path: *(leave blank)*
- [ ] Copy the **API Gateway domain name** shown (looks like `d-xxxxxxxx.execute-api.us-east-1.amazonaws.com`)
- [ ] In your DNS (Route 53 or registrar):
  - Type: `CNAME`
  - Name: `api`
  - Value: the API Gateway domain name above
- [ ] Test it works:
  ```bash
  curl https://api.hyperplexity.ai/v1/account/balance \
    -H "Authorization: Bearer hpx_live_your_key"
  ```
  → Should return JSON, not an AWS error

### B3 — Custom Domain for the Web UI (app.hyperplexity.ai)
- [ ] **API Gateway** → **Custom domain names** → **Create**
  - Domain name: `app.hyperplexity.ai`
  - ACM certificate: same cert from B1
- [ ] Add API mapping → your existing REST API Gateway → stage `prod`
- [ ] Copy its API Gateway domain name
- [ ] In DNS: `CNAME` record: `app` → that domain name
- [ ] Update Squarespace embed and CORS configs to use `app.hyperplexity.ai` instead of the raw AWS URL

### B4 — Main site (hyperplexity.ai)
- [ ] Decide: redirect to your existing Squarespace content, OR set up a new Squarespace site on hyperplexity.ai
- [ ] Add `hyperplexity.ai` and `www.hyperplexity.ai` DNS records per your Squarespace setup

---

## Part C — PyPI Publishing

```bash
cd "/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/mcp"

# Install build tools (one-time)
pip install build twine

# Build the package
python -m build
# Creates dist/mcp_server_hyperplexity-1.0.0.tar.gz and .whl

# Test on TestPyPI first
twine upload --repository testpypi dist/*
# Verify it installs cleanly from TestPyPI:
uvx --index-url https://test.pypi.org/simple/ mcp-server-hyperplexity

# Publish to production PyPI
twine upload dist/*

# Final smoke test from a clean environment:
HYPERPLEXITY_API_KEY=hpx_live_xxx uvx mcp-server-hyperplexity
```

Prerequisites:
- [ ] Create account at pypi.org (if you don't have one)
- [ ] In PyPI account settings → **API tokens** → create a token scoped to the new package
- [ ] `twine` will ask for username `__token__` and the API token as password

---

## Part D — Registry Submissions (after PyPI + GitHub are live)

Submit in this order — Smithery is highest priority:

| Registry | How | Why |
|---|---|---|
| **Smithery.ai** | Go to smithery.ai → click Submit | Integrated into Cline VS Code — highest install volume |
| **MCP Servers (official)** | Open PR on `github.com/modelcontextprotocol/servers` | Anthropic's official list, widely referenced |
| **ClawHub** | Fork `github.com/openclaw/clawhub`, add `mcp/SKILL.md` to their `skills/` dir, open PR | Required for OpenClaw "install skill" command |
| **mcp.so** | Submit via their web form | Additional discovery |

---

## Quick Reference

| Thing | Value |
|---|---|
| GitHub repo | `github.com/EliyahuAI/mcp-server-hyperplexity` |
| PyPI package | `mcp-server-hyperplexity` |
| Install command | `uvx mcp-server-hyperplexity` |
| Claude Code add | `claude mcp add hyperplexity uvx mcp-server-hyperplexity -e HYPERPLEXITY_API_KEY=...` |
| External API | `api.hyperplexity.ai/v1` |
| Web UI API | `app.hyperplexity.ai` |
| API keys page | `hyperplexity.ai/account` |
| MCP docs | `hyperplexity.ai/mcp` |
