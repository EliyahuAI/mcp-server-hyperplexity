# Model Resilience: Liveness Guard + Health Tracker

Two complementary systems that protect validation runs from degraded or unresponsive models.

---

## Overview

| System | Scope | Signal | Reacts to |
|---|---|---|---|
| **Liveness Guard** | Single call, in-flight | Endpoint probe at 20% of timeout | Stuck/hung endpoint |
| **Model Health Tracker** | All calls, cross-Lambda | TPS median vs baseline | Slow degradation, quota exhaustion, repeated hard failures |

They operate independently but are designed to feed each other: a pattern of liveness cancellations is one of the strongest inputs for the health tracker's `record_failure()`.

---

## Part 1: Liveness Guard (implemented)

### What it does

Every provider call through `call_structured_api` (gemini, vertex, openrouter, baseten) is wrapped in `liveness_guard`. At **20% of the call timeout**, a lightweight probe fires in parallel — a `make_single_call('1+1=?', max_tokens=5)` to the same provider and model. If the probe raises an unrecoverable exception, the main call is cancelled immediately rather than waiting for the full timeout.

**Benefit**: for a 120s timeout, a hung endpoint fails fast at ~24s instead of burning 120s and blocking the retry chain.

### Skipped for
- `sonar*` — Perplexity search; always-on, per-call cost makes pinging wasteful
- `the-clone*` — Agentic flow; underlying sub-model calls each get their own guard
- `anthropic` — Highly reliable; no cheap probe endpoint worth adding

### Files

| File | Role |
|---|---|
| `src/shared/ai_client/liveness.py` | `should_liveness_ping()`, `liveness_guard()` |
| `src/shared/ai_client/core.py` | `_build_ping_fn()` — builds the probe closure; wires guard in dispatch |

### How it works

```
call_structured_api(prompt, model='openrouter/gemini-3-flash-preview')
  └─ dispatch: _build_ping_fn + liveness_guard
       ├─ main_task  = make_single_call(real prompt, schema, ...)   ──→ runs normally
       └─ ping_task  = _delayed_ping()
            ├─ sleep(timeout_s * 0.2)                               ──→ e.g. 24s at timeout=120
            ├─ if main_task.done(): return                          ──→ no-op if already finished
            └─ make_single_call('1+1=?', max_tokens=5)
                 ├─ success / [MAX_TOKENS] / [SCHEMA_ERROR]         ──→ endpoint alive, continue
                 └─ exception                                       ──→ main_task.cancel()
                      └─ liveness_guard raises [LIVENESS_CANCELLED]
                           └─ call_structured_api retries next backup model
```

### Ping timeout

`ping_timeout = min(8, max(3, int(call_timeout * 0.1)))` — always 3–8 seconds, regardless of main call timeout.

### Cancellation safety

- `_cancelled_by_ping` flag distinguishes our cancellation from external `CancelledError` (Lambda timeout, outer task cancel). External cancellations are **re-raised** as `CancelledError`, not wrapped as `[LIVENESS_CANCELLED]`.
- `ping_task` is awaited after cancel in the `finally` block to ensure clean connection teardown.

### Log messages

```
[LIVENESS] Pinging openrouter/gemini-3-flash-preview at 24s elapsed...
[LIVENESS] openrouter/gemini-3-flash-preview is alive
[LIVENESS] openrouter/gemini-3-flash-preview unhealthy (Connection timeout) — cancelling call
[LIVENESS_CANCELLED] openrouter/gemini-3-flash-preview cancelled at 24s — endpoint unresponsive
```

---

## Part 2: Model Health Tracker (planned)

### Problem

Liveness catches a *single hung call*, but it can't see patterns across calls or Lambda instances. When a model degrades gradually (TPS drops to 5% of normal due to quota pressure), every call still starts, the liveness probe may pass (the endpoint responds), but the actual generation is painfully slow. Other Lambda instances don't know — they keep routing to the degraded model.

TPS (`total_tokens / processing_time_s`) is already computed per call in `usage.py` but never aggregated.

### Design

**Module**: `src/shared/ai_client/model_health.py` — module-level singleton `ModelHealthTracker`.

```
Per-call: record_success(model, tokens, time_s)
          record_failure(model, reason)
          ↓
In-memory state per model (deques, baseline, consecutive_failures)
          ↓
On state change: async DynamoDB write (non-blocking)
          ↓
Cold-start: one DynamoDB scan loads all degraded state
          ↓
Backup chain: reorder_for_health(models) moves degraded to end
```

### State machine

```
  ┌──────────────────────────────────────────────────────────────────┐
  │                         run_in                                   │
  │   First 10 calls accumulate in run_in_window.                    │
  │   No TPS-based degradation until baseline_tps is established.    │
  └──────────────────────┬───────────────────────────────────────────┘
                         │ 10th success → baseline_tps = median(run_in_window)
                         ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                         healthy                                  │
  │   Each success: append TPS to rolling window (last 5).           │
  │   Check: rolling_median < 30% of baseline_tps → DEGRADE          │
  │   Check: 2 consecutive hard failures → DEGRADE                   │
  └──────────────────────┬───────────────────────────────────────────┘
                         │ trigger
                         ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                         degraded                                 │
  │   reorder_for_health() moves this model to end of backup list.   │
  │   DynamoDB record written immediately.                           │
  │   Auto-expires after 5 minutes (degraded_until).                 │
  │   OR: 2 consecutive healthy calls → RECOVER                      │
  └──────────────────────────────────────────────────────────────────┘
```

### TPS baseline

No hardcoded expected values. Baseline = median of first 10 successful calls. This self-calibrates per environment and per model without any configuration.

Conservative floor TPS (for logging only — not used for degradation before baseline is set):

| Prefix | Floor tok/s |
|---|---|
| `gemini-*` | 50 |
| `claude-haiku*` | 80 |
| `claude-sonnet*`, `claude-opus*` | 50 |
| `sonar*` | 40 |
| default | 50 |

TPS includes thinking tokens — captures total latency + generation as one signal.

### Data model

**DynamoDB table**: `perplexity-validator-model-health`
Billing: PAY_PER_REQUEST. TTL: 24h (auto-purge stale records).

| Attribute | Type | Notes |
|---|---|---|
| `model` | String (PK) | Internal model name |
| `status` | String | `healthy` \| `degraded` \| `run_in` |
| `degraded_until` | String | ISO timestamp; absent when healthy |
| `degraded_reason` | String | e.g. `"TPS median 3.1 < threshold 24.0 (baseline 80.0)"` |
| `baseline_tps` | Number | Median of run_in_window |
| `last_tps_median` | Number | Most recent rolling median |
| `run_in_count` | Number | 0–10 during run-in |
| `last_updated` | String | ISO timestamp |
| `ttl` | Number | Unix epoch, 24h from last write |

### Key methods

```python
class ModelHealthTracker:
    def record_success(model, total_tokens, processing_time_s)
        # TPS = total_tokens / processing_time_s
        # Phase 1 (run_in): append to run_in_window; on 10th call set baseline_tps
        # Phase 2 (healthy): append to tps_window (maxlen=5); check rolling median
        # On degradation: _transition(model, 'degraded', reason)

    def record_failure(model, reason)
        # consecutive_failures += 1
        # If >= _FAILURE_THRESHOLD: _transition(model, 'degraded', reason)
        # Reset consecutive_failures on next success

    def is_degraded(model) -> bool
        # Check degraded_until; auto-recover if expired

    def reorder_for_health(models: List[str]) -> List[str]
        # Stable sort: healthy/run_in models first, degraded models appended at end
        # Logs when reordering occurs

    def _transition(model, new_status, reason)
        # Update in-memory state
        # Fire non-blocking async DynamoDB write

    def _load_dynamodb_cold_start()
        # Lazy, called once on first access
        # Scan table, load non-expired degraded records into memory
```

### Integration with liveness guard

Liveness cancellations feed directly into the health tracker:

```python
# In call_structured_api except block:
except Exception as e:
    if '[LIVENESS_CANCELLED]' in str(e):
        get_tracker().record_failure(current_model, reason='liveness_cancelled')
    elif ...:
        get_tracker().record_failure(current_model, reason=type(e).__name__)
```

Two `[LIVENESS_CANCELLED]` events in a row → health tracker degrades the model → it drops to the end of the backup chain → other instances see the DynamoDB record on cold-start and skip it pre-emptively. This is the handoff between the two systems.

### Integration in `core.py`

After each successful provider call:
```python
from .model_health import get_tracker

if result and result.get('token_usage', {}).get('total_tokens', 0) > 0:
    get_tracker().record_success(
        current_model,
        result['token_usage']['total_tokens'],
        result.get('processing_time', 1.0)
    )
```

In the `except` block:
```python
get_tracker().record_failure(current_model, reason=type(e).__name__)
```

In `_get_backup_models()`:
```python
return get_tracker().reorder_for_health(backups[:count])
```

### Operations

```bash
# One-time setup
python manage_dynamodb_tables.py create-model-health-table

# Inspect current state across all models
python manage_dynamodb_tables.py list-model-health

# Clear degraded state (one model or all)
python manage_dynamodb_tables.py reset-model-health openrouter/gemini-3-flash-preview
python manage_dynamodb_tables.py reset-model-health --all
```

### Log messages

```
[MODEL_HEALTH] openrouter/gemini-3-flash-preview: run_in 7/10 calls (TPS 81.2)
[MODEL_HEALTH] openrouter/gemini-3-flash-preview DEGRADED — TPS median 3.1 < threshold 24.0 (baseline 80.0) — until 12:35:00
[MODEL_HEALTH] Reordering [gemini-3-flash-preview, openrouter/gemini-3-flash-preview, claude-sonnet-4-6] — degraded: [openrouter/gemini-3-flash-preview]
[MODEL_HEALTH] openrouter/gemini-3-flash-preview RECOVERED after 2 healthy calls (TPS 91.2)
[MODEL_HEALTH] Cold-start: loaded 2 degraded models from DynamoDB
```

---

## Interaction between the two systems

```
Normal call flow:
  liveness_guard → pass → record_success(model, tokens, time_s) → TPS window grows

Degraded endpoint (hung):
  liveness_guard → [LIVENESS_CANCELLED] → record_failure(model, 'liveness_cancelled')
  If 2× in a row → health tracker degrades model → backup chain reordered
  DynamoDB written → other Lambda instances load on cold-start → skip model pre-emptively

Degraded endpoint (slow but responding):
  liveness passes (endpoint responded) → but record_success records low TPS
  After 5 calls with low TPS → health tracker degrades model
  Next backup chain call → degraded model at end

Recovery:
  degraded_until expires (5 min) OR 2 consecutive healthy calls
  → health tracker sets status=healthy, deletes DynamoDB record
```

---

## Implementation status

| Component | Status |
|---|---|
| `liveness.py` — `should_liveness_ping`, `liveness_guard` | ✅ done |
| `core.py` — `_build_ping_fn`, liveness wired in dispatch | ✅ done |
| `model_health.py` — `ModelHealthTracker` | ⬜ planned |
| `core.py` — `record_success` / `record_failure` / `reorder_for_health` hooks | ⬜ planned |
| `manage_dynamodb_tables.py` — `create-model-health-table`, `list-model-health`, `reset-model-health` | ⬜ planned |
