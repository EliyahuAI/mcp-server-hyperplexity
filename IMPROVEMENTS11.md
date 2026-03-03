# Agent UX Notes: Naive-Agent Test — Upload & Table-Maker Flows

*Captured from a structured naive-agent test session (2026-03-03, run 6):*
- *Test 1: uploading `brooklyn_margherita.csv` (10-row NYC pizza restaurant table, upload-interview flow)*
- *Test 2: table-maker request — "4 most popular pizza toppings in the US" (4 rows requested)*

*Perspective: an LLM agent (Claude) operating the MCP tools autonomously, following tool descriptions and `_guidance` fields without prior session knowledge.*

---

## What Was Fixed Since IMPROVEMENTS10

### 1. Table-maker job failure: guidance now returns actionable error message and recovery options

**Previously:** `wait_for_job` returned `status: failed` with a leaked internal schema error (`search_strategy.requirements must have at least 1 item (hard or soft)`), while `_guidance` said "Unknown error. No further actions available." — suppressing the detail and offering no recovery path.

**Now fixed:** Error messages are translated to user-facing language and `_guidance.next_steps` includes retry options so the agent can recover without user intervention.

---

### 2. `next_step` and `_guidance` no longer contradict at `trigger_execution: true` (table-maker)

**Previously:** The table-maker's final `wait_for_conversation` response had `next_step.action = "submit_preview"` with `method: POST, url: /v1/jobs` — implying the agent should call `create_job()` — while `_guidance` correctly said the opposite.

**Now fixed:** `next_step` now reads:
```json
{
  "action": "wait",
  "description": "Preview is auto-queued — do NOT submit a job manually. Call wait_for_job(session_id) to track progress."
}
```
Both `next_step` and `_guidance` are now fully aligned. A naive agent following either field will reach the correct outcome. This was the highest-impact ongoing issue and is confirmed fixed.

---

### 2. `_guidance.summary` now populates the AI question when `user_reply_needed: true`

**Previously:** `_guidance.summary` said `"AI is waiting for your reply. Question: "` with the question text left blank. The actual question appeared only inside the double-encoded `last_ai_message` JSON string.

**Now fixed:** The `_guidance.summary` field reads:
```
"AI is waiting for your reply. Question: I'll create a table of the top 4 most popular pizza toppings in the US with these columns: ..."
```
The AI question is now embedded inline in `_guidance.summary`. An agent can read the question and reply without parsing nested JSON.

---

## What Was Confusing

### 1. `preview_complete` guidance doesn't mention `refine_config` or the metadata download URL

**Description:** Two capabilities exist at `preview_complete` that the guidance never surfaces:

1. **`refine_config`** — The agent can refine the validation config before approving (e.g., change columns, adjust strictness). This is mentioned once, briefly, in the upfront `cost_guidance` from `start_table_maker`: *"use refine_config after the preview to adjust column selection before approving."* But at `preview_complete` — the actual decision point — `_guidance.next_steps` lists only `approve_validation` and `wait_for_job`. A naive agent following `_guidance` at this step would never know it could refine instead of approve.

2. **`preview_results.download_url`** — The `approve_validation` note says *"Review preview_results.download_url and preview_table first, then approve"* but `preview_results` is not a field in the `preview_complete` response. It's a dead reference — the download URL is never actually provided.

**Consequence:**
- Agent approves (or doesn't approve) without knowing it can iterate. If preview quality is low (e.g., empty cells, wrong data), the only apparent options are approve or abandon.
- The metadata JSON — which contains per-cell confidence scores, validator explanations, and citations — is unreachable because the download URL is never returned.

**Suggested fix:**
- Add `refine_config` to `_guidance.next_steps` at `preview_complete` as an explicit option: *"Not satisfied with the preview? Call `refine_config` to adjust columns or validation approach before approving."*
- Either return `preview_results.download_url` as a real field in the `preview_complete` response, or remove the reference from the guidance note.

---

### 2. Table-maker timing estimate is too optimistic — AI and guidance both understate worst-case duration

**Description:** When `trigger_execution: true` fires, the AI's `last_ai_message` says:
> *"In the next 3-4 minutes, I will: ..."*

The `_guidance.summary` says:
> *"typically 3–10 minutes"*

Observed reality across runs: the table-maker phase is highly variable. Fast runs complete in under 15 minutes. Slow runs take 25–35 minutes and may require two sequential calls to `wait_for_job(timeout_seconds=900)` — the first call times out at the progress bar, and the second call reaches `preview_complete`.

**Consequence:** A naive agent following the guidance sets `timeout_seconds=900` (the recommended default) and may interpret a timeout as a failure rather than a normal slow-run condition. The AI's "3-4 minutes" promise creates a false expectation that makes any run over 10 minutes feel broken.

**Suggested fix:**
- In the AI `last_ai_message`: change "3-4 minutes" to "anywhere from 5 to 30 minutes depending on research complexity."
- In `_guidance.summary` at `trigger_execution: true`: update to "typically 5–30 minutes; if `wait_for_job` times out, call it again — the job is still running."
- In `wait_for_job` timeout response: explicitly say "Job is still running — call `wait_for_job` again to continue tracking."

---

### 3. Cost estimate only surfaces at `preview_complete` — partially improved

**Description:** No real-time cost signal is available at `trigger_execution: true`. The first confirmed estimate appears only after the full table-building + preview phase completes.

**Improvement since last run:** An upfront cost estimate is now included in `start_table_maker`'s `_guidance.cost_guidance`:
> *"Tables start at ~$2 minimum. Standard validation is ~$0.05 per validated cell (rows × validated columns)..."*

This gives the agent a rough mental model before committing. However, the estimate at `trigger_execution: true` — the point of no return — still contains no cost projection tied to the specific `target_row_count` and column count the AI just confirmed.

**Remaining gap:** The per-session projection (*"4 rows × 4 columns × ~$0.05 = ~$0.80 minimum"*) should appear in `_guidance` at `trigger_execution: true`, not just generic rate card info at the start of the session.

---

## What Went Well

- **Task 1 fully autonomous** — `upload_file` → `confirm_upload` → `wait_for_conversation` → `wait_for_job` reached `preview_complete` with zero manual interventions. All `_guidance` fields were accurate and consistent.
- **Upload-interview completed in 1 turn, no questions** — AI analyzed the CSV and proposed the full validation config without asking any clarifying questions. Fast and correct.
- **`next_step` and `_guidance` aligned throughout Task 1** — `confirm_upload` guidance, `wait_for_conversation` final response, and `wait_for_job` result all agreed at every step. A naive agent could follow any single field and reach the right next tool call.
- **Upload preview quality** — Confidence legend, inline cell values, and correct `approved_cost_usd` in `_guidance`. Cost: $4 for 10 rows, `preview_complete` reached cleanly.
- **Table-maker conversation guidance corrected (Issues #1 and #2 from IMPROVEMENTS10 fixed)** — The table-maker conversation flow itself worked correctly through both turns. Both fixes held.

---

## Summary Table

| # | Issue | Impact | Status | Suggested Fix |
|---|---|---|---|---|
| 1 | `preview_complete` doesn't surface `refine_config`; `preview_results.download_url` is a dead reference | **Medium** — agent can't iterate on preview; metadata unreachable | **Open** | Add `refine_config` to `next_steps`; return real download URL or remove the reference |
| 2 | Table-maker timing estimate too optimistic: AI says "3-4 min", guidance says "3-10 min"; actual can be 25-35 min | **Medium** — agent may treat slow runs as failures | **Open** | Update to "5–30 min"; note that `wait_for_job` timeout is normal and agent should retry |
| 3 | No per-session cost projection at `trigger_execution: true` (upfront rate card added, specific estimate still missing) | **Low** — generic guidance now present at session start | **Partially improved** | Emit `target_row_count × columns × rate` projection at `trigger_execution: true` |
| 4 | ~~Table-maker job failure: guidance said "Unknown error / No further actions"~~ | ~~**High**~~ | **FIXED** (this run) | N/A |
| 5 | ~~`next_step` and `_guidance` contradict on `create_job` vs. `wait_for_job` at `trigger_execution: true`~~ | ~~**Medium**~~ | **FIXED** (this run) | N/A |
| 6 | ~~`_guidance.summary` question blank when `user_reply_needed: true`~~ | ~~**Low**~~ | **FIXED** (this run) | N/A |
| 7 | ~~Post-interview `_guidance` pointed to `get_conversation` on finished conversation~~ | ~~**High**~~ | **FIXED** (stable) | N/A |
| 8 | ~~`confirm_upload` guidance contradicted upload-interview reality~~ | ~~**High**~~ | **FIXED** (stable) | N/A |
| 9 | ~~`target_row_count` not enforced in table-maker~~ | ~~**High**~~ | **FIXED** (stable, 4th run) | N/A |
