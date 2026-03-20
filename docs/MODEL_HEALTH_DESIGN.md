# Model Health Tracker — Design Plan

## Problem

When a model degrades (TPS collapse, repeated failures, quota exhaustion), other concurrent tasks and other Lambda instances don't know. They keep routing to the degraded model until their own timeouts fire. A cross-Lambda health state that propagates immediately would let healthy models get priority in the backup chain.

The TPS signal (`total_tokens / processing_time_s`) is already available per call from `usage.py`; it just isn't aggregated anywhere.

---

## Proposed Architecture

### Module: `src/shared/ai_client/model_health.py`

Module-level singleton `ModelHealthTracker` that:
1. Accumulates TPS observations per model
2. Establishes a baseline from the first 10 successful calls (no hardcoded expected values)
3. Detects degradation via rolling median TPS vs. baseline
4. Propagates state change immediately via async DynamoDB write
5. Loads degraded state on cold-start via a single DynamoDB scan

```python
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

_FLOOR_TPS = {
    # Conservative floors prevent false-positives before run-in completes.
    # Key = prefix matched against model name (lowercase).
    'gemini':           50,
    'claude-haiku':     80,
    'claude-sonnet':    50,
    'claude-opus':      50,
    'sonar':            40,
}
_FLOOR_TPS_DEFAULT = 50

_THRESHOLD      = 0.30   # degrade if rolling median < 30% of baseline
_RECOVERY_MINS  = 5      # auto-expire degraded state after N minutes
_ROLLING_WINDOW = 5      # rolling median window (post run-in)
_FAILURE_THRESHOLD = 2   # consecutive hard failures → degrade immediately
_RUN_IN_CALLS   = 10     # calls before TPS-based degradation activates

@dataclass
class ModelHealthState:
    status: str              # 'healthy' | 'degraded' | 'run_in'
    tps_window: deque        # last _ROLLING_WINDOW TPS observations (post run-in)
    run_in_window: deque     # first _RUN_IN_CALLS observations (establishes baseline)
    baseline_tps: float      # median of run_in_window once full
    consecutive_failures: int
    degraded_until: Optional[datetime]
    degraded_reason: str
```

#### Key methods

```python
class ModelHealthTracker:
    def record_success(model: str, total_tokens: int, processing_time_s: float)
        # Computes TPS = total_tokens / processing_time_s.
        # Appends to run_in_window (first 10) or tps_window (after).
        # After run-in completes: sets baseline_tps = median(run_in_window).
        # After each post-run-in call: checks if rolling_median < THRESHOLD * baseline_tps.
        # On state change: calls _transition(model, 'degraded', reason).

    def record_failure(model: str, reason: str)
        # Increments consecutive_failures.
        # If consecutive_failures >= _FAILURE_THRESHOLD → _transition(model, 'degraded', reason).

    def is_degraded(model: str) -> bool
        # Checks degraded_until expiry; auto-recovers if expired.

    def reorder_for_health(models: List[str]) -> List[str]
        # Moves degraded models to end of list, leaving order otherwise unchanged.
        # Logs: [MODEL_HEALTH] Reordering [...] — degraded: [...]

    def _transition(model: str, new_status: str, reason: str)
        # Updates in-memory state.
        # Fires async DynamoDB write (non-blocking — uses asyncio.ensure_future).
        # Recovery: 2 consecutive healthy calls OR degraded_until auto-expiry.

    def _load_dynamodb_cold_start()
        # Called lazily on first is_degraded() / record_success() call.
        # Scans entire model-health table; loads all non-expired degraded records.
        # Logs: [MODEL_HEALTH] Cold-start: loaded N degraded models from DynamoDB
```

---

## DynamoDB Table: `perplexity-validator-model-health`

| Attribute | Type | Notes |
|---|---|---|
| `model` | String (PK) | Internal model name |
| `status` | String | `healthy` \| `degraded` \| `run_in` |
| `degraded_until` | String | ISO timestamp; absent when healthy |
| `degraded_reason` | String | e.g. `"TPS median 3.1 < threshold 24.0"` |
| `baseline_tps` | Number | Median of first 10 successful calls |
| `last_tps_median` | Number | Most recent rolling median |
| `run_in_count` | Number | Calls accumulated so far (0–10 during run-in) |
| `last_updated` | String | ISO timestamp |
| `ttl` | Number | Unix epoch; 24h from last write (auto-purge) |

Billing mode: PAY_PER_REQUEST (low-traffic, burst-tolerant).

---

## TPS Baseline Strategy

No hardcoded expected values. Baseline = median of first 10 successful calls per model.

Floor TPS (see `_FLOOR_TPS` above) prevents false positives before run-in completes — TPS-based degradation is gated on `baseline_tps > 0`, so the floor is never used for degradation logic; it only affects what's logged.

TPS = `total_tokens / processing_time_s` (thinking tokens included — captures latency + generation together as a single quality signal).

---

## Integration Points

### `core.py` — after each successful provider call

```python
from .model_health import get_tracker

# Record success (all providers except clone top-level)
if result and result.get('token_usage', {}).get('total_tokens', 0) > 0:
    tps = result.get('enhanced_data', {}).get('timing', {}).get('tokens_per_second_actual', 0)
    if tps > 0:
        get_tracker().record_success(
            current_model,
            result['token_usage']['total_tokens'],
            result.get('processing_time', 1.0)
        )
```

In the failure `except` block:
```python
get_tracker().record_failure(current_model, reason=type(e).__name__)
```

In `_get_backup_models()`:
```python
return get_tracker().reorder_for_health(backups[:count])
```

---

## manage_dynamodb_tables.py Commands

Three new commands:

```bash
# Create the table (one-time setup)
python manage_dynamodb_tables.py create-model-health-table

# List all models with their current health state
python manage_dynamodb_tables.py list-model-health

# Reset degraded state (one model or all)
python manage_dynamodb_tables.py reset-model-health openrouter/gemini-3.1-flash-lite-preview-min
python manage_dynamodb_tables.py reset-model-health --all
```

---

## Log Messages

```
[MODEL_HEALTH] openrouter/gemini-3.1-flash-lite-preview-min: run_in 7/10 calls (TPS 81.2)
[MODEL_HEALTH] openrouter/gemini-3.1-flash-lite-preview-min DEGRADED — TPS median 3.1 < threshold 24.0 (baseline 80.0) — until 12:35:00
[MODEL_HEALTH] Reordering [gemini-3-flash-preview, openrouter/gemini-3-flash-preview, claude-sonnet-4-6] — degraded: [openrouter/gemini-3-flash-preview]
[MODEL_HEALTH] openrouter/gemini-3.1-flash-lite-preview-min RECOVERED after 2 healthy calls (TPS 91.2)
[MODEL_HEALTH] Cold-start: loaded 2 degraded models from DynamoDB
```

---

## Verification Steps

1. `python manage_dynamodb_tables.py create-model-health-table`
2. Run validation with `the-clone-flash` — sub-model calls (gemini, vertex, anthropic) accumulate TPS observations
3. `python manage_dynamodb_tables.py list-model-health` — shows run-in progress per model
4. Force 2 consecutive failures on a model — logs show degradation + DynamoDB record written
5. `python manage_dynamodb_tables.py reset-model-health openrouter/gemini-3.1-flash-lite-preview-min` — clears state

---

## Not Yet Implemented

- `src/shared/ai_client/model_health.py`
- DynamoDB table creation in `manage_dynamodb_tables.py`
- `core.py` integration for `record_success` / `record_failure` / `reorder_for_health`
