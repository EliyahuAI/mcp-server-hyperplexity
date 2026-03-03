# Agent UX Notes: Naive-Agent Test — Upload & Table-Maker Flows

*Captured from a structured naive-agent test session (2026-03-03):*
- *Test 1: uploading `brooklyn_margherita.csv` (10-row NYC pizza restaurant table, upload-interview flow)*
- *Test 2: table-maker request — "4 most popular pizza toppings in the US" (4 rows requested)*

*Perspective: an LLM agent (Claude) operating the MCP tools autonomously, following tool descriptions and `_guidance` fields without prior session knowledge.*

---

## What Was Fixed Since IMPROVEMENTS9

### 1. Upload-interview guidance is stable and fully correct

Both `confirm_upload` and the final `wait_for_conversation` response now consistently direct the agent to `wait_for_job(session_id)` and explicitly say NOT to call `create_job()`. In this run:

- `confirm_upload._guidance.next_steps[0]` → `wait_for_conversation`, with note: *"When the interview finishes (trigger_config_generation=true or status=approved), call wait_for_job(session_id) directly — it waits for config generation to complete, then tracks the preview phase automatically until preview_complete. Do NOT call create_job()."*
- `wait_for_conversation` final response: `next_step.action = "wait_for_job"` and `_guidance.next_steps[0].tool = "wait_for_job"` — both fields agree.

The upload-interview flow is now fully autonomous with zero manual intervention required. This fix is confirmed stable.

### 2. `target_row_count` enforcement confirmed stable (3rd run)

4 rows requested → 4 rows delivered, cost $2. No row count explosion. Third run confirms stability.

### 3. Table-maker preview completed in a single `wait_for_job` call (vs. two calls in previous runs)

Previously, `wait_for_job(timeout_seconds=900)` would time out at ~5% progress, requiring a second call. In this run, the table-maker preview reached `preview_complete` within a single 900s call. Timing appears to be variable (this run was faster), but the two-call pattern should still be documented as a possible scenario.

---

## What Was Confusing

### 1. `next_step` and `_guidance` contradict each other at `trigger_execution: true` for table-maker (ongoing from IMPROVEMENTS9)

**Description:** After the table-maker conversation reaches `trigger_execution: true`, the same `wait_for_conversation` payload contains two conflicting fields:

- `next_step.action = "submit_preview"`, `method: POST`, `url: /v1/jobs`, `description: "The workflow is complete and a config has been written to the session. Submit a preview job to validate the results before full processing."` — This implies calling `create_job()`.
- `_guidance.summary`: *"Do NOT call create_job() — the preview is auto-queued. Use wait_for_job(session_id)."* — This is the correct instruction.

**Consequence:** A naive agent reading the structured `next_step` field (a prominent, machine-readable block) before `_guidance` will call `create_job()`. The contradiction exists in the same JSON payload in the same response. This run only succeeded because `_guidance` was followed.

**Suggested fix:** When `trigger_execution: true` for table-maker sessions, set `next_step.action = "wait"` with `description: "Preview is auto-queued — do NOT submit a job. Call wait_for_job(session_id) to track progress."` The machine-readable field and `_guidance` must agree.

---

### 2. `_guidance.summary` in `wait_for_conversation` omits the AI's actual question

**Description:** When `user_reply_needed: true` (Task 2, Turn 1), the `_guidance.summary` field returned was:

```
"AI is waiting for your reply. Question: "
```

The `"Question: "` field is present but the question text is empty — the AI's message appears only in `last_ai_message` (as a JSON-encoded string inside a string). A naive agent relying on `_guidance.summary` alone would not know what question to answer.

**Consequence:** Agent must parse the nested `last_ai_message` JSON to retrieve the question. The `_guidance.summary` "Question: " field advertises content it doesn't deliver, creating an inconsistency between what the summary promises and what's actually there.

**Suggested fix:** Populate the `"Question: "` field with the extracted AI question text (e.g., the content of `last_ai_message.ai_message`), so `_guidance.summary` is self-sufficient.

---

### 3. Cost estimate only surfaces at `preview_complete`, after all processing is done (ongoing from IMPROVEMENTS8)

**Description:** For table-maker jobs, the first cost signal appears only at `preview_complete`. At the `trigger_execution: true` checkpoint, there is no preliminary estimate. In this run both costs were low ($5 and $2), so this did not cause harm. The structural risk remains for larger or differently-scoped tables.

**Consequence:** No opportunity to abort before processing begins. User only discovers cost after the full table is built.

**Suggested fix:** When `trigger_execution: true` fires, include a rough estimate in `_guidance`:
> *"Estimated cost based on `target_row_count=4` × 4 columns × ~$0.40/cell: ~$6. Actual cost confirmed at `preview_complete`."*

---

## What Went Well

- **Both flows fully autonomous** — No manual interventions required in either task. Every `_guidance` instruction was accurate and sufficient.
- **Upload-interview guidance stable** — `confirm_upload` → `wait_for_conversation` → `wait_for_job` worked end-to-end without confusion. All guidance fields agreed.
- **Table-maker `target_row_count` enforced** — 4 rows requested → 4 rows delivered, correct content (Pepperoni #1, Mushroom #3, Bacon #4), cost $2. Third consecutive correct run.
- **`wait_for_job` completed in one call** — Table-maker preview reached `preview_complete` within the 900s window. No second call needed (faster than prior runs).
- **Upload-interview completed in one turn** — AI analyzed the CSV and proposed a full validation config without asking any clarifying questions. Fast and accurate.
- **Preview table quality** — Confidence emoji + inline cell values in both tasks. L'Industrie / Sottocasa / Di Fara pizza data looked accurate. Topping data (Pepperoni, Mushroom, Bacon) was correct.
- **Cost gate clearly enforced** — Both `preview_complete` responses included exact `approved_cost_usd` in `_guidance`. Clear billing gate.

---

## Summary Table

| # | Issue | Impact | Status | Suggested Fix |
|---|---|---|---|---|
| 1 | `next_step` and `_guidance` contradict on `create_job` vs. `wait_for_job` for table-maker at `trigger_execution: true` | **Medium** — naive agent may call `create_job` incorrectly | **Ongoing** (3rd run) | Set `next_step.action = "wait"` with description aligned to `_guidance` |
| 2 | `_guidance.summary` says "Question: " but leaves it blank; actual question only in `last_ai_message` | **Low** — parsing workaround exists, but inconsistent | **New** | Populate "Question: " with extracted `ai_message` text |
| 3 | Cost estimate only surfaces at `preview_complete` after all processing | **Medium** — no early abort opportunity | **Ongoing** (4th run) | Emit rough cost projection at `trigger_execution: true` |
| 4 | ~~Post-interview `_guidance` pointed to `get_conversation` on finished conversation~~ | ~~High~~ | **FIXED** (stable) | N/A |
| 5 | ~~`confirm_upload` guidance contradicted upload-interview reality~~ | ~~High~~ | **FIXED** (stable) | N/A |
| 6 | ~~`target_row_count` not enforced in table-maker~~ | ~~High~~ | **FIXED** (stable, 3rd run) | N/A |
| 7 | ~~Table-maker preview takes 30–40 min; guidance says 3–10 min~~ | ~~Medium~~ | **IMPROVED** — this run completed in one `wait_for_job` call; timing appears variable | Update guidance to acknowledge variability |
