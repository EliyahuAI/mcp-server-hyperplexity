# Hyperplexity MCP Server

> Generate, validate, and fact-check research tables using AI — directly from Claude, Claude Desktop, or any MCP-compatible agent.

[![PyPI version](https://img.shields.io/pypi/v/mcp-server-hyperplexity)](https://pypi.org/project/mcp-server-hyperplexity/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Install in one line (Claude Code)

```bash
claude mcp add hyperplexity uvx mcp-server-hyperplexity \
  -e HYPERPLEXITY_API_KEY=hpx_live_your_key_here
```

**Get your API key:** log in at [hyperplexity.ai](https://hyperplexity.ai) and click your email at the top of the first card. New accounts receive $20 in free credits.

> **Tip — store your key once, never re-enter it:**
> Add `export HYPERPLEXITY_API_KEY=hpx_live_your_key_here` to `~/.bashrc` or `~/.zshrc`, then use `${HYPERPLEXITY_API_KEY}` everywhere (see [API Key Storage](#api-key-storage) below).

---

## What Hyperplexity does

### 1. Generate validated research tables from a prompt

Describe the table you want — subject matter, columns, scope — and Hyperplexity builds and populates it with AI-researched data. Every cell is validated against authoritative sources and returned with citations, confidence scores, and supporting evidence. Output is a structured Excel file ready for immediate use.

*Example: "Give me a table of the top 10 US hedge funds with columns: fund name, AUM, founding year, primary strategy, and HQ city."*

### 2. Validate and update existing research tables

Upload any Excel or CSV file. Hyperplexity inspects each column, validates every cell against live data and authoritative sources, and returns an enriched file with per-cell confidence scores, validator explanations, and citations. Use `update_table` to re-run validation automatically on the same data — no re-upload or edits needed. To incorporate manual changes to the output, re-upload the edited file and a matching config will be found automatically.

*Example: Upload a company list; get back every website, LinkedIn URL, headcount, and funding round verified with citations.*

### 3. Fact-check claims and citations in any text

Pass a paragraph, a report, or any block of text and Hyperplexity checks each factual claim and citation against authoritative sources. Returns a structured report of what checks out, what doesn't, and with what confidence.

*Example: Paste an analyst report; get back a cell-by-cell breakdown of which claims are supported, which are contested, and which can't be verified.*

---

## API Key Storage

Store your key once in your shell profile so you never have to paste it again:

```bash
# Add to ~/.bashrc or ~/.zshrc (then restart your terminal or run: source ~/.bashrc)
export HYPERPLEXITY_API_KEY=hpx_live_your_key_here
```

All config examples below use `${HYPERPLEXITY_API_KEY}` — they will pick it up automatically.

---

## Quickstart

### Claude Code

**Install from PyPI (recommended):**
```bash
claude mcp add hyperplexity uvx mcp-server-hyperplexity \
  -e HYPERPLEXITY_API_KEY=${HYPERPLEXITY_API_KEY}
```

**Install from the public GitHub repo (for testing the latest code):**
```bash
claude mcp add hyperplexity uvx \
  --from git+https://github.com/EliyahuAI/mcp-server-hyperplexity \
  mcp-server-hyperplexity \
  -e HYPERPLEXITY_API_KEY=${HYPERPLEXITY_API_KEY}
```

**Verify the server is running:**
```bash
claude mcp list         # should show "hyperplexity"
claude mcp get hyperplexity
```

**Basic test** — run this in Claude Code after installation:
> "Use the hyperplexity get_balance tool to check my credit balance."

Claude should call `get_balance` and return your current balance and this-month usage.

### Claude Desktop

Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "hyperplexity": {
      "command": "uvx",
      "args": ["mcp-server-hyperplexity"],
      "env": {
        "HYPERPLEXITY_API_KEY": "${HYPERPLEXITY_API_KEY}"
      }
    }
  }
}
```

**Config file locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

After saving, restart Claude Desktop. You should see "hyperplexity" listed in the MCP servers panel.

### OpenAI Codex CLI

Add to `~/.codex/config.toml`:
```toml
[mcp_servers.hyperplexity]
command = "uvx"
args = ["mcp-server-hyperplexity"]

[mcp_servers.hyperplexity.env]
HYPERPLEXITY_API_KEY = "${HYPERPLEXITY_API_KEY}"
```

Or pass inline when starting a session:
```bash
HYPERPLEXITY_API_KEY=$HYPERPLEXITY_API_KEY codex --mcp-server "hyperplexity:uvx mcp-server-hyperplexity"
```

### OpenClaw
Tell your agent: *"Install the hyperplexity skill"*

### Project-level config (shared repo)

Add a `.mcp.json` to your project root so the server is available when anyone runs Claude Code in that directory:

```json
{
  "mcpServers": {
    "hyperplexity": {
      "command": "uvx",
      "args": ["mcp-server-hyperplexity"],
      "env": {
        "HYPERPLEXITY_API_KEY": "${HYPERPLEXITY_API_KEY}"
      }
    }
  }
}
```

**Note:** API keys are tied to individual email accounts — each person needs their own key and should set it in their own shell profile. Never share or commit a key.

---

## Testing the installation

After installation, run these quick tests in order:

**1. Check balance** (confirms auth + connectivity):
> "Use hyperplexity get_balance to check my balance."

**2. Generate a small table** (free — preview only):
> "Use hyperplexity to generate a table of the 3 largest S&P 500 companies by market cap: company name, ticker, market cap, sector. Run the preview. Do not approve full validation."

**3. Validate an uploaded file** (if you have an Excel/CSV):
> "Validate `companies.xlsx` with hyperplexity. Interview me about the columns, then run the preview. Abort before approving."

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `HYPERPLEXITY_API_KEY` | **Yes** | API key from [hyperplexity.ai/account](https://hyperplexity.ai/account). New accounts get $20 free. |
| `HYPERPLEXITY_API_URL` | No | Override the API base URL. Default: `https://api.hyperplexity.ai/v1` |

---

## Tool reference (18 tools)

Every tool response includes a `_guidance` block with a plain-English summary of where you are in the workflow and the exact next tool call(s) to make — so Claude can drive the full workflow autonomously.

### Generate a research table

| Tool | Description |
|---|---|
| `start_table_maker` | Start an AI conversation — describe the table you want in natural language |
| `get_conversation` | Poll the conversation for AI responses or status changes |
| `send_conversation_reply` | Reply to AI questions during table generation |

### Validate an existing table

| Tool | Description |
|---|---|
| `upload_file` | Upload an Excel or CSV file (handles presigned S3 upload automatically) |
| `confirm_upload` | Verify upload, detect matching prior validation configs (reuse if score ≥ 0.85). When no strong match is found, an AI interview is automatically started and `conversation_id` is returned. |
| `refine_config` | Adjust how columns are validated (sources, strictness, interpretation) — cannot add or remove columns |
| `create_job` | Submit a validation job (preview first, then approve for full run) — only needed when reusing a known `config_id`. Preview is auto-queued after interview or table-maker flows. |
| `wait_for_job` | **Preferred progress tracker.** Blocks until a terminal state (`preview_complete`, `completed`, `failed`), emitting live MCP progress notifications. Drives from the messages endpoint (more reliable than status polling) and handles multi-phase pipelines (e.g. table-maker → preview) automatically. No extra token cost. |
| `get_job_status` | One-shot status poll — fallback when `wait_for_job` is not suitable |
| `get_job_messages` | Fetch live progress messages with native progress percentages (paginated by `since_seq`) |
| `approve_validation` | Approve the preview and start full validation (credits are charged here) |
| `get_results` | Fetch enriched results: Excel download URL, table metadata (inline), interactive viewer URL |
| `update_table` | Re-run validation on a completed job — iterates automatically, no re-upload or edits needed |

### Fact-check text

| Tool | Description |
|---|---|
| `reference_check` | Submit text or a file for claim and citation verification |
| `get_reference_results` | Fetch the reference-check report for a completed job |

### Account

| Tool | Description |
|---|---|
| `get_balance` | Check current credit balance |
| `get_usage` | Review usage and billing history with optional date filters |

---

## Typical workflows

### Validate a table (config match found)

```
upload_file("companies.xlsx")
  → confirm_upload(session_id, s3_key)           # score ≥ 0.85 → match returned
    → create_job(session_id, config_id)          # free preview (a few rows)
      → wait_for_job(job_id)                     # blocks until preview_complete; live progress
        → approve_validation(job_id, cost_usd)   # charges credits
          → wait_for_job(job_id)                 # blocks until completed; live progress
            → get_results(job_id)                # download enriched Excel + inline metadata
```

### Validate a table (no prior config — AI interview)

```
upload_file("companies.xlsx")
  → confirm_upload(session_id, s3_key)           # no strong match → interview auto-started
    [response includes conversation_id]
    → get_conversation(conv_id, session_id)      # poll every 15s
      → send_conversation_reply(...)             # answer AI questions
        [interview complete → preview auto-queued]
        → wait_for_job(session_id)               # blocks until preview_complete; live progress
          → approve_validation(job_id, cost_usd)
            → wait_for_job(job_id)               # blocks until completed; live progress
              → get_results(job_id)
```

### Generate a table from a prompt

```
start_table_maker("Top 20 US biotech companies: name, market cap, lead drug, phase, ticker")
  → get_conversation(conv_id, session_id)        # poll every 15s for AI questions
    → send_conversation_reply(...)               # answer any clarifying questions
      [table builds → preview auto-queued, do NOT call create_job()]
      → wait_for_job(session_id)                 # spans table-maker + preview phases; live progress
        → approve_validation(job_id, cost_usd)
          → get_results(job_id)                  # download generated + validated table
```

### Fact-check a document

```
reference_check(text="...")       # or upload_file(...) first, then pass s3_key
  → wait_for_job(job_id)          # blocks until completed; live progress
    → get_reference_results(job_id)
```

---

## Understanding results

The `get_results` tool returns an inline `results.metadata` JSON with full per-cell detail:

```
results.metadata
  ├── table_name
  ├── columns[]         — column descriptions, importance, notes
  └── rows[]            — one entry per row
       └── cells{}
            ├── full_value                  — validated/corrected value
            ├── confidence                  — HIGH / MEDIUM / LOW / ID
            └── comment
                 ├── validator_explanation  — why the value was accepted or changed
                 ├── qc_reasoning           — QC layer reasoning
                 ├── key_citation           — the single most important source
                 └── sources[]              — [{title, url, snippet}] supporting sources
```

The `interactive_viewer_url` in the results opens a shareable web view with all citations and confidence scores rendered for human review.

---

## Security

- Your file data is uploaded to Hyperplexity's secure AWS S3 storage and processed in isolated, single-tenant jobs
- API keys are hashed with HMAC-SHA256 — never stored in plaintext
- This server sends no telemetry and stores no data locally
- The server is open source — audit the code at [github.com/EliyahuAI/mcp-server-hyperplexity](https://github.com/EliyahuAI/mcp-server-hyperplexity)

---

## Links

- **Documentation:** [hyperplexity.ai/mcp](https://hyperplexity.ai/mcp)
- **API reference:** [hyperplexity.ai/api](https://hyperplexity.ai/api)
- **Account & API keys:** [hyperplexity.ai/account](https://hyperplexity.ai/account)
- **Main site:** [hyperplexity.ai](https://hyperplexity.ai)
- **License:** MIT
