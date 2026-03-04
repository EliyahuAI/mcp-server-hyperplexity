# Hyperplexity — MCP & API Guide

> Generate, validate, and fact-check research tables using AI — via Claude, any MCP-compatible agent, or direct REST API.

---

## Get Your API Key

Log in at **[hyperplexity.ai](https://hyperplexity.ai)** and click your email at the top of the first card to access account info and API keys. New accounts receive $20 in free credits.

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

## Quick Start: MCP (Claude)

The MCP server lets Claude drive the full Hyperplexity workflow autonomously — no scripting required.

### Claude Code (one-liner)

```bash
claude mcp add hyperplexity uvx mcp-server-hyperplexity \
  -e HYPERPLEXITY_API_KEY=hpx_live_your_key_here
```

### Claude Desktop

Add to `claude_desktop_config.json`:

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

### Project config (shared repo)

Add `.mcp.json` to your repo root so the server is available when anyone runs Claude Code in that directory. Each person must use their own API key — keys are tied to individual email accounts and should not be shared:

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

Each team member sets `HYPERPLEXITY_API_KEY` in their own shell profile. No key is committed to the repo.

---

## Using with Claude — What to Say

Once the MCP server is installed, describe your task in plain English. Claude drives the full workflow, pausing only when user input is genuinely needed.

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

**Full flow: upload → interview → preview → refine → approve → download**

```
upload_file(path)
  → confirm_upload(session_id, s3_key, filename)
      ┌── match found (score ≥ 0.85) → create_job(session_id, config_id)
      └── no match → interview auto-started
            → wait_for_conversation / poll get_conversation
              → send_conversation_reply  (if AI asks questions)
              → [interview complete → preview auto-queued]

  → wait_for_job(session_id)          ← blocks until preview_complete
      → [optional] refine_config(conv_id, session_id, instructions)
      → approve_validation(job_id, cost_usd)
      → wait_for_job(job_id)          ← blocks until completed
      → get_results(job_id)
```

> **Key behavior:** After the interview finishes (`trigger_execution=true`), the preview is auto-queued. Do **not** call `create_job()`. Call `wait_for_job(session_id)` directly — it detects the config-generation phase automatically.

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
```

---

### 2. Generate a Table from a Prompt

Describe the table you want — rows, columns, scope — and Hyperplexity builds and validates it from scratch.

```
start_table_maker("Top 20 US biotech companies: name, ticker, market cap, lead drug, phase")
  → wait_for_conversation / poll get_conversation
    → send_conversation_reply  (if AI asks clarifying questions)
    → [table builds → preview auto-queued, do NOT call create_job()]

  → wait_for_job(session_id)          ← spans table-maker + preview phases
    → approve_validation(job_id, cost_usd)
    → wait_for_job(job_id)
    → get_results(job_id)
```

> **Cost:** ~$0.05/cell (standard), up to ~$0.25/cell (advanced). $2 minimum per run.

**Python script:** [`examples/02_generate_table.py`](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/02_generate_table.py)

```bash
python examples/02_generate_table.py "Top 10 US hedge funds: fund name, AUM, strategy, HQ city"
python examples/02_generate_table.py --prompt-file my_spec.txt
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

Submit any text, report, or document. Hyperplexity checks each factual claim against authoritative sources and returns a structured confidence report.

```
reference_check(text="...")           ← inline text
  or
upload_file(path, "pdf")              ← upload PDF/document first
  → reference_check(s3_key=s3_key)

→ wait_for_job(job_id)
  → get_reference_results(job_id)
```

**Python script:** [`examples/04_reference_check.py`](https://hyperplexity-storage.s3.amazonaws.com/website_downloads/examples/04_reference_check.py)

```bash
# Fact-check inline text
python examples/04_reference_check.py --text "Bitcoin was created by Satoshi Nakamoto in 2009."

# Fact-check a PDF
python examples/04_reference_check.py --file analyst_report.pdf

# Fact-check multiple documents concatenated
cat doc1.txt doc2.txt | python examples/04_reference_check.py --stdin
```

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

---

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/conversations/table-maker` | Start a Table Maker session with a natural language prompt |
| `GET`  | `/conversations/{id}?session_id=` | Poll conversation for status / AI messages |
| `POST` | `/conversations/{id}/message` | Send a reply to the AI |
| `POST` | `/conversations/{id}/refine-config` | Refine the config with natural language instructions |

---

### Jobs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/jobs` | Create a preview validation job (only when reusing a `config_id`) |
| `GET`  | `/jobs/{id}` | Get job status and progress |
| `GET`  | `/jobs/{id}/messages` | Fetch live progress messages (paginated by `since_seq`) |
| `POST` | `/jobs/{id}/validate` | Approve full validation — credits charged here |
| `GET`  | `/jobs/{id}/results` | Fetch download URL, metadata, viewer URL |
| `POST` | `/jobs/update-table` | Re-validate enriched output after corrections |
| `POST` | `/jobs/reference-check` | Submit text or file for claim verification |
| `GET`  | `/jobs/{id}/reference-results` | Fetch completed reference-check report |

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
| `refine_config` | Refine the validation config with natural language instructions |
| `create_job` | Submit a preview job — **only when reusing a known `config_id`** |
| `wait_for_job` | Block until `preview_complete`, `completed`, or `failed` (preferred progress tracker) |
| `get_job_status` | One-shot status poll |
| `get_job_messages` | Fetch progress messages with native percentages (paginated) |
| `approve_validation` | Approve preview → start full validation (credits charged here) |
| `get_results` | Download URL, inline metadata, interactive viewer URL |
| `update_table` | Re-validate enriched output after analyst corrections |
| `reference_check` | Submit text or file for claim and citation verification |
| `get_reference_results` | Fetch the reference-check report |
| `get_balance` | Check credit balance |
| `get_usage` | Review billing history |

---

## Key Behaviors

### Auto-queued preview

After the **upload interview** finishes (`trigger_execution=true` and `status=approved`) or after a **Table Maker** session completes, the preview is **automatically queued**. Do not call `create_job()`. Call `wait_for_job(session_id)` — it detects the intermediate config-generation or table-making phase automatically.

Only call `create_job()` when you already have a `config_id` from a prior run.

### Config reuse

If `confirm_upload` returns a match with `match_score ≥ 0.85`, skip the interview and call `create_job(session_id, config_id=...)` directly. The `configuration_id` from any completed job's `get_results` response can be reused on future uploads.

### Cost confirmation gate

`approve_validation` requires `approved_cost_usd` matching the preview estimate. This prevents surprise charges. The estimate is in the `preview_complete` job status response under `cost_estimate.estimated_total_cost_usd`.

### Consuming results: humans vs AI agents

`get_results` returns:

| Field | Type | Best for |
|-------|------|----------|
| `results.interactive_viewer_url` | URL | **Humans** — web viewer with confidence indicators (requires login with the account email) |
| `results.download_url` | Presigned URL | **Humans** — download the enriched Excel (.xlsx) directly |
| `results.metadata_url` | Presigned URL | **AI agents** — JSON file with all rows, per-cell details, and source citations |

**Recommended AI agent workflow:**

1. At `preview_complete`: read the inline `preview_table` (markdown, 3 rows) from `GET /jobs/{id}` to survey the table structure and spot-check values.
2. After full validation: fetch `results.metadata_url` → `table_metadata.json`. This contains every validated row.
3. Use `rows[].row_key` (stable SHA-256) to cross-reference rows between the markdown summary and the detailed JSON.
4. Per-cell fields in `table_metadata.json`:
   - `cells[col].full_value` — validated value
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

Credits are prepaid. Get $20 free at **[hyperplexity.ai/account](https://hyperplexity.ai/account)**.

---

## Links

- **MCP server (PyPI):** `pip install mcp-server-hyperplexity`
- **Source:** [github.com/EliyahuAI/mcp-server-hyperplexity](https://github.com/EliyahuAI/mcp-server-hyperplexity)
- **Documentation:** [hyperplexity.ai/mcp](https://hyperplexity.ai/mcp)
- **API reference:** [hyperplexity.ai/api](https://hyperplexity.ai/api)
- **Account & credits:** [hyperplexity.ai/account](https://hyperplexity.ai/account)
