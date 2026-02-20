# Hyperplexity API — Quick Start Guide

**Base URL:** `https://api.hyperplexity.ai/v1`
**Auth:** `Authorization: Bearer <your_api_key>`
**API keys:** Create and manage at `https://app.hyperplexity.ai/account`

---

## Contents

1. [Setup](#1-setup)
2. [The Model — Table, Configuration, Preview, Full](#2-the-model)
3. [Rerun with a Known Config](#3-rerun-with-a-known-config)
4. [Update Table (iterate on validated output)](#4-update-table)
5. [New Table — Upload First, Then Configure](#5-new-table--upload-first-then-configure)
6. [New Table — Table Maker (AI builds the structure)](#6-new-table--table-maker-ai-builds-the-structure)
7. [Chex (Reference Check)](#7-chex-reference-check)
8. [Refinement — Adjust Config After Preview](#8-refinement--adjust-config-after-preview)
9. [Status Reference, Errors & Polling](#9-status-reference-errors--polling)

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

Hyperplexity organises work around three concepts:

**Table** — your data, one row per record. You provide it as an Excel file (upload)
or have AI design a new schema from scratch (Table Maker). Each Table lives in a
*session* identified by a `session_id`.

**Configuration** — tells the system what each column means, what to look up, and
which AI models to use. You get a config from one of three places:
- **AI interview** — the system asks a few questions about your data and builds
  the config for you.
- **Past run** — when a preview completes, the `config_id` is returned in the
  response so you can reuse it on a new table with the same structure.
- **Direct `config_id`** — paste a `config_id` you saved earlier into `POST /v1/jobs`.

**Preview → Full Validation** — every job starts with a free preview (default 3 rows)
that costs nothing and returns a cost estimate for the full run. You review the preview
Excel, approve the cost, and only then is a full validation charged. Nothing is billed
until you call `POST /v1/jobs/{id}/validate`.

---

## 3. Rerun with a Known Config

Use this when you have a new version of a table and already know the `config_id`
(returned in `preview_complete` from any prior run).

```python
import os

CONFIG_ID = "cfg_xyz789"   # from a previous preview_complete or GET /v1/account/usage
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
> past jobs each with `configuration_id`. But for any run done after this API version,
> the `config_id` is returned directly in the `preview_complete` response (Step 6 above)
> so you no longer need to call `account/usage` just to find it.

---

## 4. Update Table

Use **Update Table** when you've already completed a full validation and want to
re-validate the *enhanced output* (the validated Excel the system produced) as your new
input — for example, after an analyst has corrected some rows.

The system automatically copies the config from the source job so you don't need to
specify a `config_id`.

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
print(f"Preview ready — estimated cost: ${cost:.4f}")

requests.post(f"{BASE_URL}/jobs/{new_job_id}/validate", headers=HEADERS, json={})
poll_until(new_job_id, "completed")

resp = requests.get(f"{BASE_URL}/jobs/{new_job_id}/results", headers=HEADERS)
print(resp.json()["data"]["results"]["download_url"])
```

**Error cases:**
- `404 source_not_found` — source job doesn't exist or wasn't found in results storage
- `used_preview_data: true` in the response — source job had only preview data; run a
  full validation on it first for complete results

---

## 5. New Table — Upload First, Then Configure

Use this when you already have an Excel file and want to either reuse a matching
config or create a new one with AI help.

```python
EXCEL_PATH = "new_dataset.xlsx"

# ── Step 1–2: Upload ──────────────────────────────────────────────────────────
resp = requests.post(f"{BASE_URL}/uploads/presigned", headers=HEADERS, json={
    "file_type": "excel",
    "filename": os.path.basename(EXCEL_PATH),
})
upload = resp.json()["data"]
s3_key     = upload["s3_key"]
session_id = upload["session_id"]

with open(EXCEL_PATH, "rb") as f:
    requests.put(upload["upload_url"], data=f,
                 headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})

# ── Step 3: Confirm and get config options ────────────────────────────────────
resp = requests.post(f"{BASE_URL}/uploads/confirm", headers=HEADERS, json={
    "session_id": session_id,
    "s3_key": s3_key,
    "filename": os.path.basename(EXCEL_PATH),
})
confirm = resp.json()["data"]
matches     = confirm.get("matches", [])

print(f"Matches found: {confirm['match_count']}")
for m in matches:
    print(f"  [{m['match_score']:.0%}] {m['name']}  →  config_id: {m['config_id']}")

# ── Path A: A good match was found — use it ───────────────────────────────────
if matches and matches[0]["match_score"] >= 0.85:
    config_id = matches[0]["config_id"]
    print(f"\nUsing match: {matches[0]['name']}")

    resp = requests.post(f"{BASE_URL}/jobs", headers=HEADERS, json={
        "session_id": session_id,
        "config_id": config_id,
    })
    job_id = resp.json()["data"]["job_id"]

# ── Path B: No match — let AI build one via upload interview ──────────────────
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

## 6. New Table — Table Maker (AI builds the structure)

Use this when you want AI to design a new table schema by describing what you need
in natural language. At the end of the conversation the AI builds the table schema and
kicks off a preview automatically.

```python
# ── Step 1: Start the conversation ──────────────────────────────────────────
resp = requests.post(f"{BASE_URL}/conversations/table-maker", headers=HEADERS, json={
    "message": "I need a table tracking clinical trials for oncology drugs. "
               "Each row should be one trial, with columns for drug name, phase, "
               "indication, sponsor, enrollment count, and primary endpoint.",
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

Chex is a separate product that extracts and validates factual claims in text or
documents (papers, reports, slide decks). It has its own fixed internal logic — there
is no preview step, no config management, and no cost approval. Input is plain text or
a PDF/ODF file; output is a CSV of claims with validation status.

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
it always generates a new config version you can use on the next run.

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

## 9. Status Reference, Errors & Polling

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
| `402 Payment Required` | Insufficient credits | Top up at `/account` |
| `400 missing_config` | No config provided in `POST /jobs` | Add `config_id`, `config_s3_key`, or `config` |
| `400 missing_fields` | Required field absent | Check request body against docs |
| `404 source_not_found` | Source job not found in `POST /jobs/update-table` | Confirm job completed successfully |
| `404 results_not_ready` | Job not yet complete | Keep polling |
| `429 Too Many Requests` | Rate limit hit | Back off and retry |
