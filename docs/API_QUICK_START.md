# Hyperplexity API — Quick Start Guide

**Base URL:** `https://api.hyperplexity.ai/v1`
**Auth:** `Authorization: Bearer <your_api_key>`
**API keys:** Create and manage at `https://app.hyperplexity.ai/account`

---

## Contents

1. [Setup](#1-setup)
2. [The Model — Table, Configuration, Preview, Full](#2-the-model)
3. [Rerun with a Known Config](#3-rerun-with-a-known-config)
4. [Update Table (re-validate past output)](#4-update-table)
5. [Upload a Table](#5-upload-a-table)
6. [Table Maker (AI generates the table from a prompt)](#6-table-maker)
7. [Chex (Reference Check)](#7-chex-reference-check)
8. [Refinement — Adjust Config After Preview](#8-refinement--adjust-config-after-preview)
9. [Output Structure — Excel and Metadata JSON](#9-output-structure--excel-and-metadata-json)
10. [Status Reference, Errors & Polling](#10-status-reference-errors--polling)

---

## 1. Setup

```python
import time
import requests

API_KEY = "hpx_your_api_key_here"
BASE_URL = "https://api.hyperplexity.ai/v1"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Verify your key and check your balance
resp = requests.get(f"{BASE_URL}/account/balance", headers=HEADERS)
print(resp.json())
# → {"success": true, "data": {"balance_usd": 42.50, "email": "you@example.com"}}
```

---

## 2. The Model

Hyperplexity organises work around three concepts.

---

### Where does the table come from?

| Source | When to use it |
|--------|---------------|
| **Table Maker** | Describe what you need in natural language — the AI generates the table schema and initial data for you. |
| **Upload a Table** | You already have data in an Excel file. Includes uploading the *output* of a past validation if you want to manually edit it before re-running. |
| **Update Table (API)** | You have a completed validation and want to re-run with its enhanced output as the new input, without any manual editing step. The API copies the validated Excel automatically. |

---

### Where does the configuration come from?

The configuration tells the system what each column means, what to look up, and which AI models to use.

| Source | How |
|--------|-----|
| **New — AI interview** | When you upload a table whose headers don't match any past run, the system starts an AI conversation to build the config from scratch. |
| **New — Table Maker** | The Table Maker conversation produces a config automatically alongside the table. |
| **Reused — header match** | When you upload a table, the system checks whether its column headers match a previous configuration. If there's a good match it offers to use that config or start a fresh AI interview — your choice. |
| **Reused — `config_id`** | After any preview completes, the response includes a `config_id`. Pass it into `POST /v1/jobs` to skip the interview on a new upload. |

A configuration defines column rules, not row counts. You can add new rows to your
table and rerun with the same `config_id` — no interview or reconfiguration needed.

---

### Preview → Full Validation

Every job — regardless of how the table or config was obtained — starts with a free **preview** (default 3 rows). The preview costs nothing and returns a cost estimate for the full run. Download the preview Excel to verify column mappings, then call `POST /v1/jobs/{id}/validate` to approve and charge for the full run. Nothing is billed until you explicitly approve.

---

## 3. Rerun with a Known Config

Use this when you have a new version of a table and already know the `config_id`
(returned in `preview_complete` from any prior run).

```python
import os

CONFIG_ID = "cfg_xyz789"   # from a previous preview_complete response
EXCEL_PATH = "my_table.xlsx"

# ── Step 1: Get a presigned upload URL ──────────────────────────────────────
resp = requests.post(f"{BASE_URL}/uploads/presigned", headers=HEADERS, json={
    "file_type": "excel",
    "filename": os.path.basename(EXCEL_PATH),
})
upload = resp.json()["data"]
s3_key     = upload["s3_key"]
session_id = upload["session_id"]

# ── Step 2: Upload the file directly to S3 ──────────────────────────────────
with open(EXCEL_PATH, "rb") as f:
    requests.put(upload["upload_url"], data=f,
                 headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})

# ── Step 3: Confirm the upload ───────────────────────────────────────────────
requests.post(f"{BASE_URL}/uploads/confirm", headers=HEADERS, json={
    "session_id": session_id,
    "s3_key": s3_key,
    "filename": os.path.basename(EXCEL_PATH),
})

# ── Step 4: Create the validation job with your saved config ─────────────────
resp = requests.post(f"{BASE_URL}/jobs", headers=HEADERS, json={
    "session_id": session_id,
    "config_id": CONFIG_ID,
})
job_id = resp.json()["data"]["job_id"]
print(f"Job started: {job_id}")

# ── Step 5: Poll for preview completion ──────────────────────────────────────
def poll_until(job_id, target_status, timeout=600, interval=10):
    for _ in range(timeout // interval):
        r = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS).json()
        data = r["data"]
        status = data["status"]
        print(f"  {status} ({data.get('progress_percent', 0)}%)")
        if status == target_status:
            return data
        if status in ("failed", "error"):
            raise RuntimeError(f"Job failed: {r}")
        time.sleep(interval)
    raise TimeoutError("Timed out waiting for job")

data = poll_until(job_id, "preview_complete")

# ── Step 6: Review the preview ────────────────────────────────────────────────
config_id = data.get("config_id")          # ← save this for future reruns
cost  = data["cost_estimate"]["estimated_total_cost_usd"]
rows  = data["cost_estimate"]["estimated_rows"]
prev  = data["preview_results"]["download_url"]   # presigned Excel URL
print(f"Preview ready — {rows} rows, estimated cost: ${cost:.4f}")
print(f"Preview Excel: {prev}")
print(f"Config ID for future reruns: {config_id}")
# Download and inspect `prev` to verify column mappings before spending credits.

# ── Step 7: Approve and run the full validation ───────────────────────────────
requests.post(f"{BASE_URL}/jobs/{job_id}/validate", headers=HEADERS, json={})
data = poll_until(job_id, "completed")

# ── Step 8: Get results ───────────────────────────────────────────────────────
resp = requests.get(f"{BASE_URL}/jobs/{job_id}/results", headers=HEADERS)
results = resp.json()["data"]["results"]
print(f"Download: {results['download_url']}")
print(f"Viewer:   {results['interactive_viewer_url']}")
```

> **Finding a config ID from older runs:** `GET /v1/account/usage` returns a list of
> past jobs each with `configuration_id`. For any run done after API v2.0, the
> `config_id` is returned directly in the `preview_complete` response (Step 6 above)
> so you no longer need to call `account/usage` to find it.

---

## 4. Update Table

Use **Update Table** when you have a completed validation and want to re-validate
its enhanced output as the new input — for example, to keep enriching the same
dataset over time without any manual editing step.

The API automatically copies the enhanced Excel from the source job and the source
config. No `config_id` or file upload is needed.

```python
COMPLETED_JOB_ID = "session_20260217_103045_abc123"

# ── Step 1: Create the update job ────────────────────────────────────────────
resp = requests.post(f"{BASE_URL}/jobs/update-table", headers=HEADERS, json={
    "source_job_id": COMPLETED_JOB_ID,
    # "source_version": 1  # optional; defaults to latest completed version
})
data = resp.json()["data"]
new_job_id = data["job_id"]
print(f"Update job queued: {new_job_id}")
# data["note"] → "Enhanced output from source job used as new input. Config automatically copied."

# ── Step 2: Poll → approve → results (same as Section 3, Steps 5–8) ──────────
data = poll_until(new_job_id, "preview_complete")
cost = data["cost_estimate"]["estimated_total_cost_usd"]
config_id = data.get("config_id")    # config was copied from the source job
print(f"Preview ready — estimated cost: ${cost:.4f}")
print(f"Config ID: {config_id}")

requests.post(f"{BASE_URL}/jobs/{new_job_id}/validate", headers=HEADERS, json={})
poll_until(new_job_id, "completed")

resp = requests.get(f"{BASE_URL}/jobs/{new_job_id}/results", headers=HEADERS)
print(resp.json()["data"]["results"]["download_url"])
```

**Error cases:**
- `404 source_not_found` — source job doesn't exist or wasn't found in results storage
- `used_preview_data: true` in the response — source job had only preview data; run a
  full validation on it first for complete results

**Manual-editing variant:** If you want to edit the validated Excel before re-running
(correct rows, add notes, etc.), download the results Excel, make your changes, and
then upload it via the standard **Upload a Table** flow (Section 5). The system will
recognise the matching column headers and offer the same config automatically.

---

## 5. Upload a Table

Use this when you have a table to validate — whether it's a fresh dataset or the
output of a past validation that you've manually edited.

**Accepted formats:**
- **Excel** (`.xlsx` or `.xls`) — data must be on the first worksheet (or a sheet
  named "Updated Values", which is preferred automatically).
- **CSV** (`.csv`) — comma-separated; other delimiters (`;`, `\t`, `|`) are
  auto-detected.

After confirming the upload the system checks whether the column headers match any
previous configuration. If there's a good match it offers to use that config or start
a fresh AI interview. If there's no match at all the system starts an AI interview to
build a new config.

```python
TABLE_PATH = "new_dataset.xlsx"   # or "new_dataset.csv"

# ── Step 1–2: Upload ──────────────────────────────────────────────────────────
# Use file_type="excel" for .xlsx/.xls, or file_type="csv" for .csv
file_type = "csv" if TABLE_PATH.endswith(".csv") else "excel"
resp = requests.post(f"{BASE_URL}/uploads/presigned", headers=HEADERS, json={
    "file_type": file_type,
    "filename": os.path.basename(TABLE_PATH),
})
upload = resp.json()["data"]
s3_key     = upload["s3_key"]
session_id = upload["session_id"]

content_type = "text/csv" if file_type == "csv" else \
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
with open(TABLE_PATH, "rb") as f:
    requests.put(upload["upload_url"], data=f, headers={"Content-Type": content_type})

# ── Step 3: Confirm and get config options ────────────────────────────────────
resp = requests.post(f"{BASE_URL}/uploads/confirm", headers=HEADERS, json={
    "session_id": session_id,
    "s3_key": s3_key,
    "filename": os.path.basename(TABLE_PATH),
})
confirm = resp.json()["data"]
matches  = confirm.get("matches", [])

print(f"Matches found: {confirm['match_count']}")
for m in matches:
    print(f"  [{m['match_score']:.0%}] {m['name']}  →  config_id: {m['config_id']}")

# ── Path A: Headers matched a past config — use it automatically ──────────────
if matches and matches[0]["match_score"] >= 0.85:
    config_id = matches[0]["config_id"]
    print(f"\nUsing match: {matches[0]['name']}")

    resp = requests.post(f"{BASE_URL}/jobs", headers=HEADERS, json={
        "session_id": session_id,
        "config_id": config_id,
    })
    job_id = resp.json()["data"]["job_id"]

# ── Path B: No match — AI interview to build a new config ─────────────────────
else:
    print("\nNo match found — starting AI interview...")

    resp = requests.post(f"{BASE_URL}/conversations/upload-interview", headers=HEADERS, json={
        "session_id": session_id,
        "message": "Please help me configure validation for this table.",
    })
    data = resp.json()["data"]
    conv_id = data["conversation_id"]

    # Poll + reply until config generation is triggered
    def conversation_loop(conv_id, session_id, max_turns=20):
        for turn in range(max_turns):
            time.sleep(8)
            resp = requests.get(
                f"{BASE_URL}/conversations/{conv_id}",
                headers=HEADERS,
                params={"session_id": session_id},
            )
            state = resp.json()["data"]
            status = state.get("status")
            ai_msg = state.get("last_ai_message")

            if ai_msg:
                print(f"\n[Turn {turn+1}] AI: {ai_msg}")

            if status == "processing":
                continue

            if state.get("user_reply_needed"):
                reply = input("Your reply: ").strip()
                requests.post(f"{BASE_URL}/conversations/{conv_id}/message",
                              headers=HEADERS,
                              json={"session_id": session_id, "message": reply})
                continue

            next_step = state.get("next_step", {})
            if next_step.get("action") == "submit_preview":
                print("\nConfig ready — starting preview...")
                resp = requests.post(f"{BASE_URL}/jobs", headers=HEADERS,
                                     json={"session_id": session_id, "preview_rows": 3})
                return resp.json()["data"]["job_id"]

        raise RuntimeError("Conversation did not complete")

    job_id = conversation_loop(conv_id, session_id)

# ── Continue with standard preview → approve → results ───────────────────────
data = poll_until(job_id, "preview_complete")
print(f"\nPreview ready — cost: ${data['cost_estimate']['estimated_total_cost_usd']:.4f}")
print(f"Config ID: {data.get('config_id')}")    # save this for future reruns

confirm = input("\nApprove full validation? [y/N]: ").strip().lower()
if confirm == "y":
    requests.post(f"{BASE_URL}/jobs/{job_id}/validate", headers=HEADERS, json={})
    poll_until(job_id, "completed")
    resp = requests.get(f"{BASE_URL}/jobs/{job_id}/results", headers=HEADERS)
    print(resp.json()["data"]["results"]["download_url"])
```

---

## 6. Table Maker

Use Table Maker when you want AI to generate a new table from a plain-language
description — it designs the schema, populates the rows, and automatically starts
a preview at the end of the conversation.

```python
# ── Step 1: Start the conversation ──────────────────────────────────────────
resp = requests.post(f"{BASE_URL}/conversations/table-maker", headers=HEADERS, json={
    "message": "I need a table of the capital cities of the 5 largest US states "
               "by land area. Include columns for state name, capital city, "
               "state area in sq miles, and population of the capital.",
})
data = resp.json()["data"]
conv_id    = data["conversation_id"]
session_id = data["session_id"]
print(f"Conversation: {conv_id}  Session: {session_id}")

# ── Step 2: Poll + reply until done ─────────────────────────────────────────
def conversation_loop(conv_id, session_id, max_turns=20):
    for turn in range(max_turns):
        time.sleep(8)
        resp = requests.get(
            f"{BASE_URL}/conversations/{conv_id}",
            headers=HEADERS,
            params={"session_id": session_id},
        )
        state = resp.json()["data"]
        status = state.get("status")
        ai_msg = state.get("last_ai_message")

        print(f"\n[Turn {turn+1}] status={status}")
        if ai_msg:
            print(f"AI: {ai_msg}")

        if status == "processing":
            continue

        if state.get("user_reply_needed"):
            reply = input("Your reply: ").strip()
            requests.post(f"{BASE_URL}/conversations/{conv_id}/message",
                          headers=HEADERS,
                          json={"session_id": session_id, "message": reply})
            continue

        next_step = state.get("next_step", {})
        if next_step.get("action") == "submit_preview":
            print("\nTable design complete — starting preview...")
            resp = requests.post(f"{BASE_URL}/jobs", headers=HEADERS,
                                 json={"session_id": session_id, "preview_rows": 3})
            return resp.json()["data"]["job_id"]

    raise RuntimeError("Conversation did not complete")

job_id = conversation_loop(conv_id, session_id)
print(f"\nPreview job: {job_id}")

# ── Step 3: Standard poll → approve → results ────────────────────────────────
data = poll_until(job_id, "preview_complete")
print(f"Cost estimate: ${data['cost_estimate']['estimated_total_cost_usd']:.4f}")
print(f"Config ID: {data.get('config_id')}")    # save this for future reruns

requests.post(f"{BASE_URL}/jobs/{job_id}/validate", headers=HEADERS, json={})
poll_until(job_id, "completed")
resp = requests.get(f"{BASE_URL}/jobs/{job_id}/results", headers=HEADERS)
print(resp.json()["data"]["results"]["download_url"])
```

---

## 7. Chex (Reference Check)

Chex is a separate product that extracts and validates factual claims from text or
documents (papers, reports, slide decks). The table of claims is derived directly
from the input text — you don't supply a table or configure columns. Chex uses a
fixed internal validation logic; there is no preview step, no cost approval, and no
refinement options. Output is a CSV of claims with validation status.

### Option A — Paste text directly

```python
text = """
Aspirin reduces the risk of cardiovascular events by 25% in high-risk patients [1].
Johnson et al. (2019) demonstrated a 40% reduction in mortality. The drug was approved
by the FDA in 1987 for this indication.

References:
[1] Smith, J. et al. (2018). NEJM 378:1203-1215.
"""

resp = requests.post(f"{BASE_URL}/jobs/reference-check", headers=HEADERS, json={
    "text": text,
})
data = resp.json()["data"]
job_id = data["job_id"]
print(f"Chex job: {job_id}")

# Poll until complete (typically 45–150 seconds)
poll_until(job_id, "completed")

# Get the results CSV
resp = requests.get(f"{BASE_URL}/jobs/{job_id}/reference-results", headers=HEADERS)
csv_url = resp.json()["data"]["results"]["download_url"]
print(f"CSV: {csv_url}")
```

### Option B — Upload a PDF

```python
PDF_PATH = "paper.pdf"

# Step 1: Presigned upload
resp = requests.post(f"{BASE_URL}/uploads/presigned", headers=HEADERS, json={
    "file_type": "pdf",
    "filename": os.path.basename(PDF_PATH),
})
upload = resp.json()["data"]

# Step 2: Upload
with open(PDF_PATH, "rb") as f:
    requests.put(upload["upload_url"], data=f, headers={"Content-Type": "application/pdf"})

# Step 3: Start Chex with the S3 key
resp = requests.post(f"{BASE_URL}/jobs/reference-check", headers=HEADERS, json={
    "s3_key": upload["s3_key"],
})
job_id = resp.json()["data"]["job_id"]

poll_until(job_id, "completed")

resp = requests.get(f"{BASE_URL}/jobs/{job_id}/reference-results", headers=HEADERS)
print(resp.json()["data"]["results"]["download_url"])
```

> ODF/ODT files work the same way — use `file_type: "odf"` in the presigned request.

---

## 8. Refinement — Adjust Config After Preview

If the preview shows wrong column mappings or logic, refine the config via natural
language before approving. A new config version is generated asynchronously; poll
`GET /v1/conversations/{conv_id}` until `status == "completed"`.

Refinement can be called after `preview_complete` **or** after full `completed` status —
it always produces a new `config_id` you can use on the next run.

```python
# After poll_until(job_id, "preview_complete") — job_id is also used as session_id
CONV_ID = f"refine_{job_id}"
resp = requests.post(f"{BASE_URL}/conversations/{CONV_ID}/refine-config",
                     headers=HEADERS, json={
    "session_id": job_id,
    "instructions": "Change 'Drug Name' column to also accept brand-name synonyms.",
})
conv_data = resp.json()["data"]
print(f"Refine queued: {conv_data['conversation_id']}")

# Poll until the refined config is ready
for _ in range(30):
    time.sleep(10)
    state = requests.get(
        f"{BASE_URL}/conversations/{conv_data['conversation_id']}",
        headers=HEADERS,
        params={"session_id": job_id},
    ).json()["data"]
    if state["status"] == "completed":
        new_config_id = state["next_step"]["body"].get("config_id")
        print(f"Refined config ready: {new_config_id}")
        # Re-run the preview with the refined config
        resp2 = requests.post(f"{BASE_URL}/jobs", headers=HEADERS, json={
            "session_id": job_id,
            "config_id": new_config_id,
            "preview_rows": 5,
        })
        job_id = resp2.json()["data"]["job_id"]
        data = poll_until(job_id, "preview_complete")
        break
    if state["status"] != "processing":
        break
```

---

## 9. Output Structure — Result Files

### Files returned by `GET /v1/jobs/{id}/results`

```json
{
  "results": {
    "download_url":           "https://...",   // presigned — main Excel file
    "file_format":            "xlsx",
    "metadata_url":           "https://...",   // presigned — table_metadata.json
    "receipt_url":            "https://...",   // presigned — receipt.pdf or receipt.txt
    "interactive_viewer_url": "https://eliyahu.ai/viewer?session=...&version=1"
  },
  "job_info": {
    "input_table_name":  "clinical_trials.xlsx",
    "configuration_id":  "cfg_abc123",
    "run_time_seconds":  142.3
  },
  "summary": {
    "rows_processed":     500,
    "columns_validated":  6,
    "cost_usd":           4.20
  }
}
```

---

### Excel file (`download_url`) — 4 sheets

| Sheet | What it contains |
|-------|-----------------|
| **Updated Values** | Primary output. All original columns with AI-validated values, colour-coded by confidence: 🟢 HIGH · 🟡 MEDIUM · 🔴 LOW · 🔵 ID/Ignored · ⭕ Blank. Each row has a `_row_key` column for cross-referencing. |
| **Original Values** | Your input data exactly as uploaded, for side-by-side comparison. |
| **Validation Record** | Run audit trail — session ID, config ID, run number, timestamps, row/column counts, and aggregate confidence statistics for every run on this session. |
| **Details** | Row-by-row breakdown: original value, validated value, confidence, validator explanation, QC reasoning, and numbered source citations. One row per validated field. |

Presigned URLs expire after 1 hour. Download the file promptly or re-fetch the
URL from the API.

---

### Metadata JSON (`metadata_url`)

Powers the interactive viewer and is designed for direct LLM or programmatic
consumption. The `schema_markdown` field at the top of the JSON gives a complete
orientation to the table without parsing the nested structure.

**Structure:**

```json
{
  "_llm_hint": "START HERE: read `schema_markdown` before processing this file. It contains the table title, configuration notes, a confidence key, and the complete column schema in one readable block. Each entry in `rows[]` is identified by `row_key`. For any row, look up `rows[].cells[column_name]` to find: `original_value` (input before validation), `validator_explanation` (why the AI chose the validated value), `qc_reasoning` (quality-control reasoning), `key_citation` (primary citation), and `sources[]` — each with `title`, `url`, and `snippet`.",
  "schema_markdown": "# Clinical Trials Analysis\n\nAI-validated table · 500 rows × 6 columns\n\n## Configuration Notes\n...\n\n## Confidence Key\n| Icon | Level | Meaning |\n...\n\n## Column Schema\n| Column | Importance | Description |\n...",
  "table_name":    "Clinical Trials Analysis",
  "general_notes": "Config-level notes from the configuration.",
  "columns": [
    { "name": "Drug Name", "importance": "HIGH",   "description": "...", "notes": "..." },
    { "name": "Phase",     "importance": "MEDIUM", "description": "...", "notes": "..." }
  ],
  "rows": [
    {
      "row_key": "a3f9c2...",
      "cells": {
        "Drug Name": {
          "display_value": "🟢 Pembrolizumab",
          "full_value":    "Pembrolizumab",
          "confidence":    "HIGH",
          "comment": {
            "original_value":        "Keytruda",
            "validator_explanation": "Brand name resolved to INN.",
            "qc_reasoning":          "Cross-checked against WHO INN list.",
            "key_citation":          "WHO INN 2023",
            "sources": [
              { "id": 1, "title": "WHO INN list", "url": "https://...", "snippet": "..." }
            ]
          }
        }
      }
    }
  ],
  "is_transposed": true
}
```

**`_llm_hint`** — the first key in the file. Tells an LLM exactly where to start
and what each key contains, so it can orient itself without reading the full
nested structure first.

**`schema_markdown`** — a self-contained markdown document at the top of the
JSON. Contains:
- **Title** (table name) and **subtitle** (row × column count)
- **Configuration Notes** (`general_notes` from the config)
- **Confidence Key** — icon legend
- **Column Schema** — markdown table listing every column plus `_row_key`

**`display_value`** — the validated cell value prefixed with a confidence icon
for direct rendering. `full_value` always contains the raw text without the icon.

**Confidence icons:**

| Icon | Level | Meaning |
|------|-------|---------|
| 🟢 | HIGH | Verified with high confidence |
| 🟡 | MEDIUM | Verified with moderate confidence |
| 🔴 | LOW | Could not be verified or may be incorrect |
| 🔵 | ID / Ignored | Not validated — identity or pass-through column |
| ⭕ | Blank | Validation was attempted but no helpful information found |

**`_row_key` / `row_key`** — 64-character hex SHA-256 hash uniquely identifying
each row. Derived from the primary-key columns in the config, or the full row
content if no primary keys are defined. The same key appears in the `_row_key`
column of the Excel output.

Use `row_key` to look up the full validation detail for a row in `rows[]`. Each
entry in `rows[].cells[column_name]` exposes:
- `original_value` — the input value before AI validation
- `validator_explanation` — why the AI chose the validated value
- `qc_reasoning` — quality-control reasoning applied after initial validation
- `key_citation` — the single most relevant citation supporting the value
- `sources[]` — list of `{id, title, url, snippet}` references used during validation

---

### Receipt (`receipt_url`)

A PDF (or plain-text fallback) invoice showing the job ID, session, config used,
row count, per-row cost, and total amount charged.

---

### Interactive viewer (`interactive_viewer_url`)

A hosted web viewer at `eliyahu.ai/viewer` — the URL does not expire and can be
shared with stakeholders. The viewer fetches fresh presigned URLs for the data
on load, so recipients always see the latest results as long as the session
exists in storage.

---

## 10. Status Reference, Errors & Polling

### Preview response shape

When `GET /v1/jobs/{job_id}` returns `status: "preview_complete"`:

```json
{
  "status": "preview_complete",
  "config_id": "cfg_abc123",
  "progress_percent": 100,
  "preview_results": {
    "download_url": "https://...",
    "file_format": "xlsx",
    "metadata_url": "https://..."
  },
  "cost_estimate": {
    "estimated_total_cost_usd": 4.20,
    "estimated_rows": 500
  },
  "next_steps": {
    "approve_url": "/v1/jobs/{id}/validate",
    "requires_approval": true
  }
}
```

`config_id` is present for all runs after API version 2.0. For older runs it may be
absent — use `GET /v1/account/usage` as a fallback.

Download the `preview_results.download_url` Excel to inspect column mappings and sample
outputs before committing credits.

---

### Job status values

| Status | Meaning | What to do |
|--------|---------|------------|
| `queued` | Job accepted, waiting to start | Keep polling |
| `processing` | Actively running | Keep polling |
| `preview_complete` | Preview done, awaiting your approval | Review preview Excel + cost, optionally refine, then call `POST /v1/jobs/{id}/validate` |
| `completed` | Full validation done | Call `GET /v1/jobs/{id}/results` |
| `failed` | Something went wrong | Check `error_message` field |

### Conversation status

| `status` | `user_reply_needed` | Meaning |
|----------|--------------------|----|
| `processing` | `false` | AI still running — keep polling |
| `in_progress` | `true` | AI asked a question — send a reply |
| `in_progress` | `false` | Config generation queued — keep polling |
| any | `false` + `next_step.action == "submit_preview"` | Done — submit the job |

---

### Polling helper

```python
def poll_until(job_id, target_status, timeout=600, interval=10):
    """Poll GET /v1/jobs/{job_id} until target_status is reached."""
    for _ in range(timeout // interval):
        resp = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS)
        data = resp.json().get("data", {})
        status = data.get("status", "")
        pct    = data.get("progress_percent", 0)
        step   = data.get("current_step", "")
        print(f"  [{status}] {pct}%  {step}")
        if status == target_status:
            return data
        if status in ("failed", "error"):
            raise RuntimeError(f"Job {job_id} failed: {data}")
        time.sleep(interval)
    raise TimeoutError(f"Timed out after {timeout}s waiting for {target_status}")
```

---

### Polling progress notes

`GET /v1/jobs/{job_id}` returns a **DynamoDB snapshot**, not a real-time stream.
Progress is written at checkpoints (job start, each batch, job end), so:

- `progress_percent` may stay at a low value (e.g. 2%) for many polls while
  the batch-processing engine works through rows — this is **normal, not stuck**.
- The percentage can jump from a low value directly to 100% in the final poll.
- `current_step` similarly reflects the last checkpoint message, not every row.

**Table-maker conversations** are multi-turn: poll
`GET /v1/conversations/{conv_id}?session_id=...` (not `/jobs`) to read the AI's
questions and send replies.

#### Real-time progress via message replay

```
GET /v1/jobs/{job_id}/messages?since_seq=0
```

Returns persisted WebSocket messages emitted during processing:

```json
{
  "messages": [
    { "type": "progress_update", "data": { "progress_percent": 25, "message": "Processing row 25/100" }, "_seq": 5 },
    { "type": "progress_update", "data": { "progress_percent": 50, "message": "Processing row 50/100" }, "_seq": 10 }
  ],
  "last_seq": 10,
  "has_more": false
}
```

Pass `since_seq=<last_seq>` on the next call to get only new messages:

```python
seq = 0
while True:
    r = requests.get(f"{BASE_URL}/jobs/{job_id}/messages",
                     headers=HEADERS, params={"since_seq": seq}).json()
    for msg in r["data"]["messages"]:
        pct  = (msg.get("data") or {}).get("progress_percent", "?")
        step = (msg.get("data") or {}).get("message", "")
        print(f"  {pct}%  {step}")
    seq = r["data"]["last_seq"]
    if not r["data"]["has_more"]:
        time.sleep(5)
```

> **Note:** Only messages from the validation/table-maker execution pipeline are
> persisted. Reference-check progress messages are delivered only via WebSocket.

---

### Common errors

| Error code | Meaning | Fix |
|------------|---------|-----|
| `401 Unauthorized` | Invalid or missing API key | Check `Authorization: Bearer hpx_...` header |
| `402 Payment Required` | Insufficient credits | Top up at `eliyahu.ai/account` |
| `400 missing_config` | No config provided in `POST /jobs` | Add `config_id`, `config_s3_key`, or `config` |
| `400 missing_fields` | Required field absent | Check request body against docs |
| `404 source_not_found` | Source job not found in `POST /jobs/update-table` | Confirm job completed successfully |
| `404 results_not_ready` | Job not yet complete | Keep polling |
| `429 Too Many Requests` | Rate limit hit | Back off and retry |
