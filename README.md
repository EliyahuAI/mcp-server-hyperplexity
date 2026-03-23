# Hyperplexity

**Verified Research Engine** · [hyperplexity.ai](https://hyperplexity.ai) · [Launch App](https://hyperplexity.ai/app)

Hyperplexity generates, validates, and updates research tables by synthesizing hundreds of calls to Perplexity and Claude. Give it a prompt or an existing table and it returns structured, verified answers across an entire research domain — not just a single query, but a complete field of questions answered at once.

| What you want to do | How | Live example |
|---|---|---|
| **Gather everything** — survey a complete research domain at once | Prompt → structured verified table | [50+ Phase 3 oncology trials](https://eliyahu.ai/viewer?demo=phase-3-oncology-drug-trials-9383b5) |
| **Monitor anything** — news, analyst projections, time-sensitive data | Upload or generate → keep current | [Market info for 10 stocks](https://eliyahu.ai/viewer?demo=investmentresearch-779dfe) |
| **See everywhere** — run the same questions across many entities | One table, many subjects | [GenAI adoption across Fortune 500](https://eliyahu.ai/viewer?demo=fortune-500-genai-deployment-and-upskilling-0c5503) |

## How to Access

| You want to… | Use |
|---|---|
| Try it out or iron out your use case | **[hyperplexity.ai/app](https://hyperplexity.ai/app)** — web GUI for table validation and generation |
| Fact-check text or documents interactively | **[hyperplexity.ai/chex](https://hyperplexity.ai/chex)** — web GUI for reference checks |
| Let an AI agent drive a workflow autonomously | **MCP server** — install once, describe your task in plain English |
| One-off automation without writing code | **MCP server** via Claude Code, Claude Desktop, or any MCP-compatible client |
| Run repeatable pipelines or batch jobs | **REST API** + example scripts |
| Integrate into a product or SaaS | **REST API** directly |

> **GUI → API:** The web GUIs are ideal for exploring and refining your use case. Once you know what you want, the MCP server or REST API is the better path — faster, repeatable, and fully automatable.

---

## Table of Contents

- [Get Your API Key](#get-your-api-key)
- [Download Examples](#download-examples)
- [Quick Start: MCP](#quick-start-mcp)
  - [Option A: Direct HTTP connection to Railway (recommended)](#option-a--direct-http-connection-to-railway-recommended-for-claude-code)
  - [Option B: Local install via uvx](#option-b--local-install-via-uvx)
  - [Option C: Smithery](#option-c--smithery)
  - [What to Ask Your Agent](#what-to-ask-your-agent)
- [Workflows](#workflows)
  - [1. Validate an Existing Table](#1-validate-an-existing-table)
  - [2. Generate a Table from a Prompt](#2-generate-a-table-from-a-prompt)
  - [3. Update a Table](#3-update-a-table-re-run-validation-pass)
  - [4. Fact-Check Text or Documents](#4-fact-check-text-or-documents-chex)
- [Environment Variables](#environment-variables)
- [Direct REST API](#direct-rest-api)
  - [API Endpoint Reference](#api-endpoint-reference)
- [MCP Prompts](#mcp-prompts)
- [MCP Tool Reference](#mcp-tool-reference)
- [Key Behaviors](#key-behaviors)
- [Pricing](#pricing)
- [Links](#links)

---

## Get Your API Key

Get your API key at **[hyperplexity.ai/account](https://hyperplexity.ai/account)**. New accounts receive $20 in free credits.

---

## Download Examples

> All scripts require Python 3.10+ and `pip install requests`.

| Script | Description | Download |
|--------|-------------|----------|
| `hyperplexity_client.py` | Shared REST client (required by all examples) | [download](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/hyperplexity_client.py) |
| `01_validate_table.py` | Validate an existing table | [download](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/01_validate_table.py) |
| `02_generate_table.py` | Generate a table from a prompt | [download](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/02_generate_table.py) |
| `03_update_table.py` | Re-run validation on a completed job | [download](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/03_update_table.py) |
| `04_reference_check.py` | Fact-check text or documents | [download](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/04_reference_check.py) |

Or clone the full example set:

```bash
# Download all examples at once
curl -O https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/hyperplexity_client.py \
     -O https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/01_validate_table.py \
     -O https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/02_generate_table.py \
     -O https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/03_update_table.py \
     -O https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/04_reference_check.py
pip install requests
export HYPERPLEXITY_API_KEY=hpx_live_...
```

---

## Quick Start: MCP

The MCP server lets any AI agent drive the full Hyperplexity workflow autonomously — no scripting required.

### Option A — Direct HTTP connection to Railway (recommended for Claude Code)

Connects directly to the hosted Hyperplexity server over HTTP. No local install, no `uvx`, no package management — just one command.

**Claude Code:**
```bash
claude mcp add hyperplexity \
  --transport http \
  https://mcp-server-hyperplexity-production.up.railway.app/ \
  --header "X-Api-Key: hpx_live_your_key_here"
```

**Via config file** (`.mcp.json` in your repo root, or `claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "hyperplexity": {
      "type": "http",
      "url": "https://mcp-server-hyperplexity-production.up.railway.app/",
      "headers": {
        "X-Api-Key": "hpx_live_your_key_here"
      }
    }
  }
}
```

> **Why HTTP over uvx?** The HTTP connection runs on Railway — always up to date, no local Python environment needed, and no version drift between the package you installed and the live server. Recommended for Claude Code and any project-level config.

### Option B — Local install via uvx

Runs the server locally on your machine using `uvx`. Useful for Claude Desktop or offline/air-gapped environments.

**Claude Code:**
```bash
claude mcp add hyperplexity uvx mcp-server-hyperplexity \
  -e HYPERPLEXITY_API_KEY=hpx_live_your_key_here
```

**Claude Desktop** — add to `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "hyperplexity": {
      "command": "uvx",
      "args": ["mcp-server-hyperplexity"],
      "env": {
        "HYPERPLEXITY_API_KEY": "hpx_live_your_key_here"
      }
    }
  }
}
```

**Project config (shared repo)** — add `.mcp.json` to your repo root. Each person uses their own key; no key is committed to the repo:

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

**OpenAI Codex CLI** — add to your Codex config file (`~/.codex/config.toml` on macOS/Linux, `%USERPROFILE%\.codex\config.toml` on Windows):

```toml
[mcp_servers.hyperplexity]
command = "uvx"
args = ["mcp-server-hyperplexity"]

[mcp_servers.hyperplexity.env]
HYPERPLEXITY_API_KEY = "hpx_live_your_key_here"
```

Then restart Codex and verify:
```bash
codex mcp list
```

### Option C — Smithery

[Smithery](https://smithery.ai) is an MCP registry that works with Claude Code and other MCP-compatible clients including OpenClaw.

**Step 1 — Install and log in:**
```bash
npx -y @smithery/cli@latest login
npx -y @smithery/cli@latest mcp add hyperplexity/hyperplexity --client claude-code
```

**Step 2 — Authenticate with your API key:**

Open your MCP client (e.g. Claude Code), go to `/mcp`, click **hyperplexity → Authenticate**, and enter your Hyperplexity API key in the Smithery page that opens.

> Smithery login is a one-time step. You must log in before adding servers, or authentication will not be set up correctly.

---

## What to Ask Your Agent

Once the MCP server is installed, describe your task in plain English. The agent drives the full workflow, pausing only when your input is genuinely needed.

**Validate a table:**
> "Validate `companies.xlsx` using Hyperplexity. Interview me about what each column means, then run the preview. If the results look good, approve the full validation."

**Generate a table:**
> "Use Hyperplexity to generate a table of the top 20 US hedge funds with columns: fund name, AUM, primary strategy, founding year, and HQ city. Approve the full validation when the preview looks right."

**Re-run validation on the same table:**
> "Re-run update_table on job `session_20260217_103045_abc123` to get an updated validation pass."

**Fact-check a document:**
> "Use Hyperplexity to fact-check this analyst report." *(paste the text or share the file path)*

---

## Workflows

### 1. Validate an Existing Table

> **Minimum rows:** Hyperplexity is designed for tables with **4 or more data rows**. Fewer rows may produce low-quality results.

**Full flow: upload → interview → preview → refine → approve → download**

```
upload_file(path)
  → confirm_upload(session_id, s3_key, filename)
      ┌── match found (score ≥ 0.85) → [preview auto-queued; response has preview_queued=true + job_id]
      └── no match → interview auto-started
            → wait_for_conversation / poll get_conversation
              → send_conversation_reply  (if AI asks questions)
              → [interview complete → preview auto-queued]

  → wait_for_job(job_id or session_id)  ← blocks until preview_complete
      → [optional] refine_config(conv_id, session_id, instructions)
      → approve_validation(job_id, cost_usd)
      → wait_for_job(job_id)            ← blocks until completed
      → get_results(job_id)
```

> **Key behavior:** The preview is always auto-queued — after the interview finishes (`trigger_config_generation=true`), or when a config match is found (`match_score ≥ 0.85`, response includes `preview_queued: true` and `job_id`). Call `wait_for_job(session_id)` directly in all cases (see [Config reuse](#config-reuse)).

> **Upload interview auto-approval:** The interview may auto-approve in a single turn. If the conversation response has `user_reply_needed: false` and `status: approved`, proceed to `wait_for_job(session_id)` immediately — no reply is needed, even if the AI's message appears to ask for confirmation.

**Skip the interview with `instructions` (fire-and-forget config generation):**

Pass `instructions` to `confirm_upload` to bypass the interactive interview. The AI reads the table structure + your instructions and generates a config directly, then auto-triggers the preview — no clarifying questions needed.

```
confirm_upload(session_id, s3_key, filename,
  instructions="This table lists hedge funds. Validate AUM, strategy, and HQ city. Use Bloomberg and SEC filings.")
  → response includes instructions_mode=true
  → wait_for_job(session_id)          ← config generation + preview tracked automatically
  → approve_validation(job_id, cost_usd)
  → wait_for_job(job_id)
  → get_results(job_id)
```

> **Cost gate:** Config generation and the 3-row preview are **free**. Full validation is charged at `approve_validation` — you always see the cost estimate at `preview_complete` before anything is billed. If your balance is insufficient, `approve_validation` returns an `insufficient_balance` error with the required amount.

**Refine the config** before approving by calling `refine_config`. This adjusts how columns are validated (sources, strictness, interpretation) — it cannot add or remove columns:

```
refine_config(conversation_id, session_id,
  "Use SEC filings as the primary source for revenue. Require exact match for ticker symbols.")
```

A new preview runs automatically after refinement.

**Python script:** [`examples/01_validate_table.py`](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/01_validate_table.py)

```bash
export HYPERPLEXITY_API_KEY=hpx_live_...
python examples/01_validate_table.py companies.xlsx
python examples/01_validate_table.py companies.xlsx --refine "Add LinkedIn URL column"

 Fire-and-forget: provide instructions to skip the interview entirely
python examples/01_validate_table.py companies.xlsx \
    --instructions "This table lists hedge funds. Validate AUM, strategy, and HQ city."
```

---

### 2. Generate a Table from a Prompt

Describe the table you want — rows, columns, scope — and Hyperplexity builds and validates it from scratch. Designed for tables with **4 or more rows**.

```
start_table_maker("Top 20 US biotech companies: name, ticker, market cap, lead drug, phase")
  → wait_for_conversation / poll get_conversation
    → send_conversation_reply  (if AI asks clarifying questions)
    → [table builds → preview auto-queued]

  → wait_for_job(session_id)          ← spans table-maker + preview phases
    → approve_validation(job_id, cost_usd)
    → wait_for_job(job_id)
    → get_results(job_id)
```

> **Auto-approve:** The agent can auto-approve the preview and proceed to full validation without human intervention. The preview table is included inline in the `preview_complete` response.

> **Cost:** ~$0.05/cell (standard), up to ~$0.25/cell (advanced). $2 minimum per run.

**Skip confirmation with `auto_start=True` (fire-and-forget generation):**

Pass `auto_start=True` to skip the AI's clarifying questions and structure-confirmation step. The AI generates the table immediately from the message alone. Use when your message fully describes the desired table.

```
start_table_maker(
  "Top 20 US hedge funds: fund name, AUM, primary strategy, founding year, HQ city",
  auto_start=True)
  → wait_for_conversation(conversation_id, session_id)
      ← returns trigger_execution=true on first response (no Q&A)
  → wait_for_job(session_id)          ← table building + preview
  → approve_validation(job_id, cost_usd)
  → wait_for_job(job_id)
  → get_results(job_id)
```

> **Why `wait_for_conversation` with `auto_start=True`?** Even though there is no Q&A, `wait_for_conversation` is still required — it returns `trigger_execution: true` in a single blocking call (no reply needed), signaling that the table-maker has started. Calling `wait_for_job` before this call returns would be premature, as the table-maker may not have been triggered yet.

> **Cost gate:** Table building and the 3-row preview are **free**. Full validation is charged at `approve_validation` — you always see the cost estimate at `preview_complete` before anything is billed. If your balance is insufficient, `approve_validation` returns an `insufficient_balance` error with the required amount.

**Python script:** [`examples/02_generate_table.py`](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/02_generate_table.py)

```bash
python examples/02_generate_table.py "Top 10 US hedge funds: fund name, AUM, strategy, HQ city"
python examples/02_generate_table.py --prompt-file my_spec.txt

 Fire-and-forget: skip clarifying Q&A and generate immediately from the prompt
python examples/02_generate_table.py --auto-start "Top 10 US hedge funds: fund name, AUM, strategy, HQ city"
```

---

### 3. Update a Table (Re-run Validation Pass)

Re-run validation on a completed job — no re-upload or manual edits needed. The table iterates automatically, re-validating the same data with the same config to pick up any changes in source data.

If you want to incorporate manual edits to the output file, re-upload the edited file via `upload_file` + `confirm_upload` — a matching config will be found automatically (score ≥ 0.85).

```
update_table(source_job_id)           ← re-validates existing enriched output
  → wait_for_job(new_job_id)          ← blocks until preview_complete
    → approve_validation(new_job_id, cost_usd)
    → wait_for_job(new_job_id)
    → get_results(new_job_id)
```

**Python script:** [`examples/03_update_table.py`](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/03_update_table.py)

```bash
python examples/03_update_table.py session_20260217_103045_abc123
python examples/03_update_table.py session_20260217_103045_abc123 --version 2
```

---

### 4. Fact-Check Text or Documents (Chex)

Submit any text, report, or document. Hyperplexity checks each factual claim against authoritative sources and returns the same output format as standard table validation: an Excel (XLSX) file, an interactive viewer URL, and a metadata JSON.

> **Minimum claims:** Hyperplexity is designed for text with **4 or more factual claims**. Fewer claims may produce low-quality results.

```
reference_check(text="...")           ← inline text (or auto_approve=True to skip the gate)
  or
upload_file(path, "pdf")              ← upload PDF/document first
  → reference_check(s3_key=s3_key)

→ wait_for_job(job_id)                ← spans extraction + 3-row preview; stops at preview_complete
  → preview_table (3 validated sample claims) + cost_estimate shown in response
  → approve_validation(job_id, approved_cost_usd=X)   ← triggers Phase 2
  → wait_for_job(job_id)              ← waits for completed
  → get_results(job_id)               ← download_url (XLSX) + interactive_viewer_url + metadata_url
```

> **Three-phase flow:** Phase 1 (claim extraction, free) runs automatically, then a 3-row preview validates sample claims (free, auto-triggered). Both phases are tracked by a single `wait_for_job` call that stops at `status=preview_complete`. Review `preview_table` (3 validated sample claims with support level and citations) and `cost_estimate`, then call `approve_validation` to start Phase 2 (full validation, charged). Pass `auto_approve=True` to skip the gate and run straight through to `completed`.

> **Progress tracking:** `get_job_messages` always returns empty for reference-check jobs. Use `get_job_status` (`current_step`, `progress_percent`) to track progress.

**Output:** Excel (XLSX) file with per-claim rows. Support levels: SUPPORTED / PARTIAL / UNSUPPORTED / UNVERIFIABLE. Share `interactive_viewer_url` with human stakeholders — it renders sources and confidence scores in a clean UI.

**Python script:** [`examples/04_reference_check.py`](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/04_reference_check.py) | **Sample output:** [`sample_outputs/reference_check_output.json`](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/sample_outputs/reference_check_output.json)

```bash
# Fact-check inline text
python examples/04_reference_check.py --text "Bitcoin was created by Satoshi Nakamoto in 2009."

# Fact-check a PDF
python examples/04_reference_check.py --file analyst_report.pdf

# Fact-check multiple documents concatenated
cat doc1.txt doc2.txt | python examples/04_reference_check.py --stdin
```

> **--stdin:** Concatenates all piped content as a single inline text payload. All claims are attributed to the combined document.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `HYPERPLEXITY_API_KEY` | API key from [hyperplexity.ai/account](https://hyperplexity.ai/account). Required. New accounts get $20 free. |
| `HYPERPLEXITY_API_URL` | Override the API base URL (useful for dev/staging environments). |

---

## Direct REST API

All tools in the MCP server are thin wrappers over the REST API. You can call it directly from any language.

**Base URL:** `https://api.hyperplexity.ai/v1`

**Auth:** `Authorization: Bearer hpx_live_your_key_here`

**Response envelope:**

```json
{
  "success": true,
  "data": { ... },
  "meta": { "request_id": "...", "timestamp": "..." }
}
```

### Python client (minimal)

```python
import os, requests

BASE_URL = "https://api.hyperplexity.ai/v1"
HEADERS  = {"Authorization": f"Bearer {os.environ['HYPERPLEXITY_API_KEY']}"}

def api_get(path, **kwargs):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, **kwargs)
    r.raise_for_status()
    return r.json()["data"]

def api_post(path, **kwargs):
    r = requests.post(f"{BASE_URL}{path}", headers=HEADERS, **kwargs)
    r.raise_for_status()
    return r.json()["data"]
```

A full standalone client module is in [`examples/hyperplexity_client.py`](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/hyperplexity_client.py).

---

## API Endpoint Reference

### Uploads

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/uploads/presigned` | Get a presigned S3 URL to upload a file |
| `PUT`  | `<presigned_url>` | Upload file bytes directly to S3 (no auth header) |
| `POST` | `/uploads/confirm` | Confirm upload; detect config matches; auto-start interview if no match |

**Presigned upload request:**

```json
{
  "filename": "companies.xlsx",
  "file_size": 2048000,
  "file_type": "excel",
  "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
}
```

Content types: `excel` → `.xlsx`, `csv` → `.csv`, `pdf` → `.pdf`

**Confirm upload request** (optional fields):

```json
{
  "session_id": "session_20260305_...",
  "s3_key": "results/.../file.xlsx",
  "filename": "companies.xlsx",
  "instructions": "Validate AUM, strategy, and HQ city. Use Bloomberg and SEC filings as sources.",
  "config_id": "session_20260217_103045_abc123_config_v1_..."
}
```

`instructions` — if provided, bypasses the interactive upload interview. The AI generates the config directly from the table structure + instructions. Response includes `instructions_mode: true` and `conversation_id`. Use `wait_for_job(session_id)` to track progress — do NOT poll the conversation.

`config_id` — if provided, skips matching and the interview entirely. The specified config is applied immediately and the preview is auto-queued. Response includes `preview_queued: true` and `job_id`. Use `wait_for_job(job_id)` to track progress. The `configuration_id` for any completed job is returned by `GET /jobs/{id}/results` under `job_info.configuration_id`.

---

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/conversations/table-maker` | Start a Table Maker session with a natural language prompt |
| `GET`  | `/conversations/{id}?session_id=` | Poll conversation for status / AI messages |
| `POST` | `/conversations/{id}/message` | Send a reply to the AI |
| `POST` | `/conversations/{id}/refine-config` | Refine the config with natural language instructions |

**Table Maker request body:**

```json
{
  "message": "Top 20 US hedge funds: fund name, AUM, primary strategy, founding year, HQ city",
  "auto_start": true
}
```

`auto_start` — if `true`, the AI skips clarifying questions and the structure-confirmation step, proceeding directly to table generation. The first `get_conversation` response will have `trigger_execution: true`. Use when your message fully describes the desired table.

---

### Jobs

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/jobs/{id}` | Get job status and progress |
| `GET`  | `/jobs/{id}/messages` | Fetch live progress messages (paginated by `since_seq`) |
| `POST` | `/jobs/{id}/validate` | Approve full validation — credits charged here |
| `GET`  | `/jobs/{id}/results` | Fetch download URL, metadata, viewer URL |
| `POST` | `/jobs/update-table` | Re-validate enriched output after corrections |
| `POST` | `/jobs/reference-check` | Submit text or file for claim verification |

**Job status values:**

| Status | Meaning |
|--------|---------|
| `queued` | Accepted, waiting to start |
| `processing` | Actively running |
| `preview_complete` | Free preview done — review results and approve full run |
| `completed` | Full validation complete, results ready |
| `failed` | Error — check `error.message` |

---

### Account

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/account/balance` | Current credit balance and this-month usage |
| `GET`  | `/account/usage` | Billing history (supports `start_date`, `end_date`, `limit`, `offset`) |

---

## MCP Prompts

Three built-in prompts act as workflow starters — select them from the prompt picker in your MCP client (Claude Code: `/` menu; Claude Desktop: the prompt icon) and fill in the arguments.

| Prompt | Arguments | What it does |
|--------|-----------|--------------|
| `generate_table` | `description` (required), `columns` (optional) | Builds a step-by-step instruction for creating a new research table from a natural language description |
| `validate_file` | `file_path` (required), `instructions` (optional) | Generates the full validation workflow for an existing Excel or CSV file |
| `fact_check_text` | `text` (required) | Generates the reference-check workflow for fact-checking a text passage |

---

## MCP Tool Reference

Every tool response includes a `_guidance` block with a plain-English summary and the exact next tool call(s) — enabling fully autonomous agent workflows.

| Tool | Description |
|------|-------------|
| `upload_file` | Upload Excel, CSV, or PDF (handles presigned S3 automatically) |
| `confirm_upload` | Confirm upload; detect config matches; auto-start interview if needed |
| `start_table_maker` | Start an AI conversation to generate a table from a prompt |
| `get_conversation` | Poll a conversation for AI responses or status changes |
| `send_conversation_reply` | Reply to AI questions during an interview or table-maker session |
| `wait_for_conversation` | Block until conversation needs input or finishes (emits live progress) |
| `refine_config` | Refine the validation config with natural language instructions (adjusts sources, strictness, interpretation — cannot add or remove columns) |
| `wait_for_job` | Block until `preview_complete`, `completed`, or `failed` (preferred progress tracker) |
| `get_job_status` | One-shot status poll |
| `get_job_messages` | Fetch progress messages with native percentages (paginated) |
| `approve_validation` | Approve preview → start full validation (credits charged here) |
| `get_results` | Download URL, inline metadata, interactive viewer URL |
| `update_table` | Re-validate enriched output after analyst corrections |
| `reference_check` | Submit text or file for claim and citation verification |
| `get_balance` | Check credit balance |
| `get_usage` | Review billing history |

---

## Key Behaviors

### Auto-queued preview

The preview is **automatically queued** in all three paths after `confirm_upload`:

| Path | Trigger | What to call next |
|------|---------|-------------------|
| Config match (score ≥ 0.85) | `preview_queued: true` in response | `wait_for_job(job_id)` |
| `instructions=` provided | `instructions_mode: true` in response | `wait_for_job(session_id)` |
| Interview ran | `trigger_config_generation=true` from conversation | `wait_for_job(session_id)` |

To reuse a config from a different session, pass `config_id` to `confirm_upload` — the preview will be auto-queued immediately.

### Config reuse

If `confirm_upload` returns `match_score ≥ 0.85`, the preview is automatically queued using the matched config. The response includes `preview_queued: true` and `job_id` — call `wait_for_job(job_id)` directly, no interview needed.

The `configuration_id` from any completed job's `get_results` response can be reused on future uploads of similar tables.

### Cost confirmation gate

`approve_validation` requires `approved_cost_usd` matching the preview estimate. This prevents surprise charges. The estimate is in the `preview_complete` job status response under `cost_estimate.estimated_total_cost_usd`.

This gate applies regardless of whether `instructions` or `auto_start` was used — both only skip the *interview/confirmation conversation*, not the cost approval step. If your balance is insufficient when `approve_validation` is called, the API returns:

```json
{ "error": "insufficient_balance", "required_usd": 4.20, "current_balance_usd": 1.50 }
```

### Fire-and-forget shortcuts

Two optional flags let fully automated pipelines skip interactive steps:

| Flag | Tool | Skips | Next step |
|------|------|-------|-----------|
| `instructions="..."` | `confirm_upload` | Upload interview Q&A | `wait_for_job(session_id)` |
| `auto_start=True` | `start_table_maker` | Structure confirmation | `wait_for_conversation` → `wait_for_job` |

These flags use different terminal signals: `instructions=` (a config-gen flow) causes `trigger_config_generation: true` on the conversation response; `auto_start=True` (a table-maker flow) causes `trigger_execution: true`. Both skip interactive Q&A but produce different fields — do not wait for `trigger_execution` when using the `instructions=` upload path. The `preview_complete` cost gate and `approve_validation` still apply.

### Consuming results: humans vs AI agents

**Output files generated per run:**

| File | Format | Description |
|------|--------|-------------|
| Preview table | Markdown (inline) | First 3 rows as markdown text; returned inline in the `preview_complete` job status response (not a separate download). Also available in `metadata.json` under `markdown_table`. |
| Enriched results | Excel (`.xlsx`) | Ideal for sharing with humans; sources and citations are embedded in cell comments |
| Full metadata | `metadata.json` | Complete per-cell detail for every row; use the `row_key` field to drill into specific rows programmatically |

`get_results` returns:

| Field | Type | Best for |
|-------|------|----------|
| `results.interactive_viewer_url` | URL | **Humans** — web viewer with confidence indicators (requires login at hyperplexity.ai with the same email as your API key) |
| `results.download_url` | Presigned URL | **Humans** — download the enriched Excel (.xlsx) directly |
| `results.metadata_url` | Presigned URL | **AI agents** — JSON file with all rows, per-cell details, and source citations |

**Recommended AI agent workflow:**

1. At `preview_complete`: read the inline `preview_table` (markdown, 3 rows) from `GET /jobs/{id}` to survey the table structure and spot-check values. The AI agent can review this inline table and call `approve_validation` directly — no human approval step is required.
2. After full validation: fetch `results.metadata_url` → `table_metadata.json`. This contains every validated row.
3. Use `rows[].row_key` (stable SHA-256) to cross-reference rows between the markdown summary and the detailed JSON.
4. Per-cell fields in `table_metadata.json`:
   - `cells[col].value` — validated value (legacy files may use `full_value`)
   - `cells[col].confidence` — `HIGH` / `MEDIUM` / `LOW` / `ID`
   - `cells[col].comment.validator_explanation` — reasoning
   - `cells[col].comment.key_citation` — top authoritative source
   - `cells[col].comment.sources[]` — all sources with `url` and `snippet`

---

## Pricing

| Mode | Cost |
|------|------|
| Preview (first 3 rows) | Free |
| Standard validation | ~$0.05 / cell |
| Advanced validation | up to ~$0.25 / cell |
| Minimum per run | $2.00 |
| Reference check | TBD — contact support |

Credits are prepaid. Get $20 free at **[hyperplexity.ai/account](https://hyperplexity.ai/account)**.

Standard validation is used for most tables. Advanced validation is selected automatically when the table requires more sophisticated reasoning (e.g., scientific data, complex financial metrics, or cells with high ambiguity).

---

## Links

- **MCP server (HTTP, recommended):** `claude mcp add hyperplexity --transport http https://mcp-server-hyperplexity-production.up.railway.app/ --header "X-Api-Key: hpx_live_..."` — no install needed
- **MCP server (PyPI/uvx):** `uvx mcp-server-hyperplexity` — for Claude Desktop or offline use
- **Source:** [github.com/EliyahuAI/mcp-server-hyperplexity](https://github.com/EliyahuAI/mcp-server-hyperplexity)
- **Documentation:** [hyperplexity.ai/mcp](https://hyperplexity.ai/mcp)
- **API reference:** [hyperplexity.ai/api](https://hyperplexity.ai/api)
- **Account & credits:** [hyperplexity.ai/account](https://hyperplexity.ai/account)
