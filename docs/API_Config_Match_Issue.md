# API Config Match Issue — Investigation Notes

**Date:** 2026-03-03
**Branch:** `api`
**Status:** Three backend fixes applied + probe script fix. Pending verification via CloudWatch.

---

## Symptom

When the same CSV is uploaded via the API multiple times, `match_count` in the confirm response is always 0. The system re-runs the full upload interview and regenerates a config on every run instead of reusing the existing one.

---

## Root Causes (Three-Layer Bug)

### 1. Probe script missing response envelope unwrap *(fixed in probe)*

`upload_and_report.py` read the confirm response as:
```python
confirm = r.json()   # BUG: fields are inside {"success": true, "data": {...}}
```
Result: `match_count`, `interview_auto_started`, `perfect_match`, `matches` always read as defaults (0 / False / []).
Fix: `confirm = r.json().get("data", r.json())`

When a perfect match IS found, the interview is suppressed (no new config generated), so the probe also timed out polling S3 for a config that was never written. Additional fix: skip the S3 poll when `match_count > 0 AND interview_auto_started == False`.

---

### 2. Wrong `configuration_id` source in DynamoDB run record *(Fix 1 — background_handler.py)*

`handle_config_generation_async` reads the config_id from the response immediately after the config lambda returns:
```python
# BUG — generation_metadata.config_id does not exist; real id is in storage_metadata
configuration_id = uc.get('generation_metadata', {}).get('config_id') or 'unknown'
```
The fallback `f"{session_id}_{version}_config"` doesn't match the actual stored config filename, so `get_successfully_used_config_ids` can't look it up later.

**Fix (line ~6418):** Check `storage_metadata.config_id` first, then `generation_metadata.config_id`, then generate fallback.

---

### 3. DynamoDB written before S3 storage completes *(Fix 2 — background_handler.py)*

`update_run_status(configuration_id=...)` was called at line ~6542, **before** `store_config_with_versioning` at line ~6659. The real `config_id` (with the correct filename) only exists after storage completes, so DynamoDB was always patched with the fallback value.

**Fix:** After `store_config_with_versioning` returns `storage_result`, add a second `update_run_status` call to patch the real config_id:
```python
if storage_result.get('success') and storage_result.get('config_id') and DYNAMODB_AVAILABLE:
    real_config_id = storage_result['config_id']
    if real_config_id and real_config_id != 'unknown':
        update_run_status(
            session_id=original_session_id,
            run_key=run_key,
            status='COMPLETED',
            run_type="Config Generation",
            configuration_id=real_config_id,
            results_s3_key=storage_result.get('s3_key', config_s3_key),
        )
        logger.info(f"[CONFIG_ID] Patched DynamoDB run record with real config_id: {real_config_id}")
```

---

## API Path vs Web UI Path

The confirm upload flow is **different** between the two:

| | API (`_handle_confirm_upload`) | Web UI (`confirm_upload_complete`) |
|---|---|---|
| Config matching | `find_matching_configs_optimized(email, session_id)` via **8-second background thread** | Imports `_find_matching_configs` from `process_excel_unified` — **that function doesn't exist**, silently returns `{matches: []}` |
| Matching timing | Inline in confirm response (subject to 8s timeout) | Web UI calls `findMatchingConfig` as a **separate HTTP action** after upload (its own Lambda invocation, no hard timeout) |
| Underlying function | Same `find_matching_configs_optimized` | Same `find_matching_configs_optimized` |

Both paths require the DynamoDB whitelist (`perplexity-validator-runs` table, `EmailStartTimeIndex` GSI, `status=COMPLETED AND configuration_id != 'unknown'`). The API path's 8-second timeout may cause the matching to be skipped on cold Lambda starts.

**Config matching only returns PERFECT matches (score = 1.0).** Any score below 1.0 returns empty — partial matches are not surfaced.

---

## How `find_matching_configs_optimized` Works

1. Get the uploaded table's columns (DynamoDB `qc_by_column` → S3 CSV parse fallback)
2. Query `EmailStartTimeIndex` GSI for all `COMPLETED` runs with a `configuration_id` → whitelist
3. Batch-fetch `qc_by_column` for whitelisted sessions (exclusionary fast filter)
4. For each whitelisted config with no QC data: load config from S3 via `find_config_by_id`, compute column match score
5. Return only perfect matches (score ≥ 1.0)

**config_id format:** `session_YYYYMMDD_HHMMSS_xxxxxxxx_config_v1_ai_generated`
**S3 path:** `results/{domain}/{email_prefix}/{session_id}/config_v1_ai_generated.json`

`find_config_by_id` reconstructs the S3 key from the config_id using a regex:
```python
session_pattern = r'^(session_(?:demo_)?\d{8}_\d{6}_[a-f0-9]{8})'
```

---

## CloudWatch Log Groups to Check

The probe uses `hyperplexity-storage-dev` → **dev environment** Lambdas.

| Log Group | What it covers |
|---|---|
| `/aws/lambda/perplexity-validator-interface-dev` | API confirm upload, config matching |
| `/aws/lambda/perplexity-validator-background-dev` | Config generation, Fix 2 patch, interview processing |

**Key log lines to search for:**

| Log line | Meaning |
|---|---|
| `[CONFIRM_UPLOAD] Saved session_info for session_XXX` | API confirm IS running ✓ |
| `[CONFIRM_UPLOAD] find_matching_configs timed out after 8s` | 8s timeout hit — matching never completed |
| `[FIND_CONFIG] Found 0 successfully used configs` | Whitelist empty — Fix 2 didn't fire or didn't deploy |
| `[FIND_CONFIG] Found N successfully used configs` | Whitelist populated — matching should work |
| `PERFECT MATCH: config_id with score 1.000` | Match found ✓ |
| `[CONFIG_ID] Patched DynamoDB run record with real config_id:` | Fix 2 ran ✓ |

> **Note:** Most `[FIND_CONFIG]` detail logs are at `DEBUG` level (not INFO) and won't appear unless the Lambda log level is lowered.

---

## Most Likely Remaining Issue

If Fix 2 deployed correctly and the probe script envelope fix is in place, the most probable remaining problem is the **8-second timeout** in `_handle_confirm_upload`. On a cold Lambda start, the sequence of:
1. Import `find_matching_config` module
2. DynamoDB query for current session's columns (cache miss)
3. S3 fetch of uploaded CSV
4. CSV parse to extract column names
5. DynamoDB query for whitelist (EmailStartTimeIndex GSI)
6. DynamoDB batch query for qc_by_column
7. S3 fetch of matched config(s)

…can exceed 8 seconds. On a **warm** Lambda the same path typically completes in 2–4 seconds. Run the probe twice in quick succession — if the second run finds a match (Lambda warm), it confirms timeout is the culprit.

**Potential fix:** Increase `_MATCH_TIMEOUT` from 8 to 12–15 seconds in `api_handler.py`, or break the matching into two steps (confirm returns immediately; a follow-up `GET /sessions/{id}/match` endpoint returns matches asynchronously).
