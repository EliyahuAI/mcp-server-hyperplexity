# Hyperplexity API — Quick Start Guide

**Base URL:** `https://api.hyperplexity.ai/v1`
**Auth:** `Authorization: Bearer <your_api_key>`
**API keys:** Create and manage at `https://app.hyperplexity.ai/account`

---

## Contents

1. [Setup](#1-setup)
2. [Rerun a Table You've Run Before](#2-rerun-a-table-youve-run-before)
3. [Run a Chex (Reference Check)](#3-run-a-chex-reference-check)
4. [New Table — Table Maker (AI builds the structure)](#4-new-table--table-maker-ai-builds-the-structure)
5. [New Table — Upload First, Then Configure](#5-new-table--upload-first-then-configure)

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

**Finding your config ID from a previous run:**

```python
resp = requests.get(f"{BASE_URL}/account/usage", headers=HEADERS)
jobs = resp.json()["data"]["jobs"]
for job in jobs:
    print(job["job_id"], job.get("configuration_id"), job.get("input_table_name"))
# → session_abc123   cfg_xyz789   Clinical Trials Master List
```

Save the `configuration_id` — that's the code you pass to reuse a config.

---

## 2. Rerun a Table You've Run Before

Use this when you have a new version of a table (more rows, updated data) and want to
validate it with the same configuration as a previous run.

**You need:** your Excel file + the `config_id` from a prior run.

```python
import os

CONFIG_ID = "cfg_xyz789"         # from GET /v1/account/usage
EXCEL_PATH = "my_table.xlsx"

# ── Step 1: Get a presigned upload URL ──────────────────────────────────────
resp = requests.post(f"{BASE_URL}/uploads/presigned", headers=HEADERS, json={
    "file_type": "excel",
    "filename": os.path.basename(EXCEL_PATH),
})
upload = resp.json()["data"]
s3_key    = upload["s3_key"]
session_id = upload["session_id"]

# ── Step 2: Upload the file directly to S3 ──────────────────────────────────
with open(EXCEL_PATH, "rb") as f:
    requests.put(upload["upload_url"], data=f,
                 headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})

# ── Step 3: Confirm the upload and name the table ───────────────────────────
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
def poll_until(job_id, target_status, timeout=300, interval=10):
    for _ in range(timeout // interval):
        r = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS).json()
        status = r["data"]["status"]
        print(f"  {status} ({r['data'].get('progress_percent', 0)}%)")
        if status == target_status:
            return r["data"]
        if status in ("failed", "error"):
            raise RuntimeError(f"Job failed: {r}")
        time.sleep(interval)
    raise TimeoutError("Timed out waiting for job")

data = poll_until(job_id, "preview_complete")

# ── Step 6: Review the preview ────────────────────────────────────────────────
cost  = data["cost_estimate"]["estimated_total_cost_usd"]
rows  = data["cost_estimate"]["estimated_rows"]
prev  = data["preview_results"]["download_url"]       # presigned Excel URL
print(f"Preview ready — {rows} rows, estimated cost: ${cost:.4f}")
print(f"Preview Excel: {prev}")
# Download and inspect `prev` to verify column mappings before spending credits.

# ── Step 6a (optional): Refine the configuration ──────────────────────────────
# If the preview shows the wrong columns, wrong logic, etc., refine the config
# via natural language before approving.  A new config version is generated
# asynchronously; poll GET /v1/conversations/{conv_id} until status=="completed".
CONV_ID = f"refine_{job_id}"
resp = requests.post(f"{BASE_URL}/conversations/{CONV_ID}/refine-config",
                     headers=HEADERS, json={
    "session_id": job_id,
    "message": "Change 'Drug Name' column to also accept brand-name synonyms.",
})
conv_data = resp.json()["data"]
print(f"Refine conversation: {conv_data['conversation_id']}")

# Poll until the refined config is ready
for _ in range(30):
    time.sleep(10)
    state = requests.get(f"{BASE_URL}/conversations/{conv_data['conversation_id']}",
                         headers=HEADERS,
                         params={"session_id": job_id}).json()["data"]
    if state["status"] == "completed":
        print(f"Refined config ready: {state['next_step']['request']['body']['config_id']}")
        # Re-run the preview with the refined config
        resp2 = requests.post(f"{BASE_URL}/jobs", headers=HEADERS,
                              json={"session_id": job_id,
                                    "config_id": state["next_step"]["request"]["body"]["config_id"],
                                    "preview_rows": 5})
        job_id = resp2.json()["data"]["job_id"]
        data = poll_until(job_id, "preview_complete")
        break
    if state["status"] != "processing":
        break

# ── Step 7: Approve and run the full validation ───────────────────────────────
requests.post(f"{BASE_URL}/jobs/{job_id}/validate", headers=HEADERS, json={})
data = poll_until(job_id, "completed")

# ── Step 8: Get results ───────────────────────────────────────────────────────
resp = requests.get(f"{BASE_URL}/jobs/{job_id}/results", headers=HEADERS)
results = resp.json()["data"]["results"]
print(f"Download: {results['download_url']}")
print(f"Viewer:   {results['interactive_viewer_url']}")
```

---

## 3. Run a Chex (Reference Check)

Chex extracts and validates claims in text or documents. Input can be plain text,
a PDF, or an ODF/ODT file.

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

## 4. New Table — Table Maker (AI builds the structure)

Use this when you want AI to design a new table schema by describing what you need
in natural language. At the end of the conversation the AI will build the table and
kick off a preview automatically.

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

        # Still processing — keep waiting
        if status == "processing":
            continue

        # AI asked a question — reply
        if state.get("user_reply_needed"):
            reply = input("Your reply: ").strip()
            requests.post(f"{BASE_URL}/conversations/{conv_id}/message",
                          headers=HEADERS,
                          json={"session_id": session_id, "message": reply})
            continue

        # AI finished building the table — trigger the job
        next_step = state.get("next_step", {})
        if next_step.get("action") == "submit_preview":
            print("\nTable design complete — starting preview...")
            job_body = next_step["request"]["body"]
            job_body["session_id"] = session_id
            resp = requests.post(f"{BASE_URL}/jobs", headers=HEADERS, json=job_body)
            return resp.json()["data"]["job_id"]

    raise RuntimeError("Conversation did not complete")

job_id = conversation_loop(conv_id, session_id)
print(f"\nPreview job: {job_id}")

# ── Step 3: Standard poll → approve → results (same as Section 2, Steps 5–7) ──
data = poll_until(job_id, "preview_complete")
print(f"Cost estimate: ${data['cost_estimate']['estimated_total_cost_usd']:.4f}")
requests.post(f"{BASE_URL}/jobs/{job_id}/validate", headers=HEADERS, json={})
poll_until(job_id, "completed")
resp = requests.get(f"{BASE_URL}/jobs/{job_id}/results", headers=HEADERS)
print(resp.json()["data"]["results"]["download_url"])
```

---

## 5. New Table — Upload First, Then Configure

Use this when you already have an Excel file and want to either reuse a matching
config or create a new one with AI help.

```python
EXCEL_PATH = "new_dataset.xlsx"

# ── Step 1–2: Upload (same as Section 2) ─────────────────────────────────────
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
next_steps  = confirm.get("next_steps", {})

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

    # Same conversation loop as Section 4
    # When status="processing" and user_reply_needed=False → config generation is running
    # When next_step.action="submit_preview" → config is ready; submit the job
    job_id = conversation_loop(conv_id, session_id)

# ── Continue with standard preview → approve → results ───────────────────────
data = poll_until(job_id, "preview_complete")
print(f"\nPreview ready — cost: ${data['cost_estimate']['estimated_total_cost_usd']:.4f}")
print(f"Preview file:  {data['preview_results']['download_url']}")

confirm = input("\nApprove full validation? [y/N]: ").strip().lower()
if confirm == "y":
    requests.post(f"{BASE_URL}/jobs/{job_id}/validate", headers=HEADERS, json={})
    poll_until(job_id, "completed")
    resp = requests.get(f"{BASE_URL}/jobs/{job_id}/results", headers=HEADERS)
    print(resp.json()["data"]["results"]["download_url"])
```

---

## Preview Response Fields

When `GET /v1/jobs/{job_id}` returns `status: "preview_complete"`, the response includes:

```json
{
  "status": "preview_complete",
  "progress_percent": 100,
  "preview_results": {
    "download_url": "https://...",     // presigned Excel URL (expires in 1 hour)
    "file_format": "xlsx",
    "metadata_url": "https://..."      // presigned URL for table_metadata.json
  },
  "cost_estimate": {
    "estimated_total_cost_usd": 4.20,  // total cost for full run
    "estimated_rows": 500
  },
  "next_steps": {
    "approve_url": "/v1/jobs/{id}/validate",
    "requires_approval": true
  }
}
```

Download the `preview_results.download_url` Excel to inspect column mappings, sample outputs,
and accuracy before committing credits. If the config needs changes, use
`POST /v1/conversations/{conv_id}/refine-config` (see Section 2, Step 6a).

---

## Status Reference

| Status | Meaning | What to do |
|--------|---------|------------|
| `queued` | Job accepted, waiting to start | Keep polling |
| `processing` | Actively running | Keep polling |
| `preview_complete` | Preview done, awaiting your approval | Review preview Excel + cost, optionally refine, then call `POST /v1/jobs/{id}/validate` |
| `completed` | Full validation done | Call `GET /v1/jobs/{id}/results` |
| `failed` | Something went wrong | Check `error_message` field |

**Conversation status:**

| `status` | `user_reply_needed` | Meaning |
|----------|--------------------|----|
| `processing` | `false` | AI still running — keep polling |
| `in_progress` | `true` | AI asked a question — send a reply |
| `in_progress` | `false` | Config generation queued — keep polling |
| any | `false` + `next_step.action == "submit_preview"` | Done — submit the job |

---

## Polling Helper (copy-paste ready)

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

## Common Errors

| Error code | Meaning | Fix |
|------------|---------|-----|
| `401 Unauthorized` | Invalid or missing API key | Check `Authorization: Bearer hpx_...` header |
| `402 Payment Required` | Insufficient credits | Top up at `/account` |
| `400 missing_config` | No config provided in `POST /jobs` | Add `config_id`, `config_s3_key`, or `config` |
| `400 missing_fields` | Required field absent | Check request body against docs |
| `404 results_not_ready` | Job not yet complete | Keep polling |
| `429 Too Many Requests` | Rate limit hit | Back off and retry |
