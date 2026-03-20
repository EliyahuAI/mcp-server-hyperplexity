# Lightweight Validation Mode

**Status:** Production
**Added:** 2026-03-19

---

## Overview

Lightweight validation uses a minimal prompt and forces all output confidences to **MEDIUM**, making it significantly cheaper than standard validation. It is designed for use cases where:

- Rows have already been vetted by a discovery pipeline (e.g., table maker)
- The goal is existence checking / quick filtering, not deep research
- Cost and speed matter more than high-confidence answers

The model and search context size are still configured via the validation config — use `sonar` with `search_context_size: "low"` for cheapest results.

---

## How It Works

When `validation_mode: "lightweight"` is active:

1. **Prompt** — `multiplex_validation_lightweight.md` is loaded instead of `multiplex_validation.md`. The lightweight prompt omits:
   - Previous-results and validation-history sections
   - "Inherent suspicion" warnings
   - Elaborate multi-section structure
   It retains only: search instruction, research questions, and field details.

2. **Confidence** — All output confidences are forced to `MEDIUM` in post-processing regardless of what the model returns. This is a hard override applied in `parse_multiplex_result()`.

3. **QC** — Not affected by this mode. QC runs if specified in the validation config; omit QC config fields to skip it (which is the default for table-maker-generated configs).

4. **Output format** — Identical to standard validation. All downstream consumers (Excel export, results viewer, MCP tools) receive the same structure.

---

## Usage

### Via API (full validation)

Pass `validation_mode` in the `POST /v1/jobs/{job_id}/validate` body:

```json
{
  "approved_cost_usd": 5.00,
  "validation_mode": "lightweight"
}
```

This threads through: `api_handler` → `start_preview` → SQS → `background_handler` → validator lambda.

### Via Direct Lambda Invocation (`invoke_validator_lambda_with_rows`)

Used internally by table-maker pipelines:

```python
from interface_lambda.core.validator_invoker import invoke_validator_lambda_with_rows

results = invoke_validator_lambda_with_rows(
    rows=rows_with_keys,
    config_s3_key=config_s3_key,
    S3_CACHE_BUCKET=bucket,
    VALIDATOR_LAMBDA_NAME=lambda_name,
    session_id=session_id,
    email=email,
    validation_mode='lightweight',
)
```

---

## Rumor Validation (Table Maker)

The **rumor validation step** in the table maker pipeline always uses lightweight mode.

Rumor validation checks V-disposition candidates against the table's hard requirements after row discovery. The validator asks Perplexity sonar **T/F/?** for each hard requirement — one search call per row.

**Location:** `src/lambdas/interface/actions/table_maker/table_maker_lib/rumor_validator.py`
**Config builder:** `src/lambdas/interface/actions/table_maker/table_maker_lib/validation_config_builder.py`
**Called from:** `src/lambdas/interface/actions/table_maker/execution.py`

### What Gets Validated

`ValidationConfigBuilder` generates a config with:
- ID columns (context only, not validated)
- One column per hard requirement, asking: *"Answer T (yes), F (no), or ? (uncertain)"*

No Entity Exists column. No soft requirements. No numeric scales.

### Pass/Fail Algorithm

| Hard requirement answers | Result |
|---|---|
| All T | pass |
| Any F | fail |
| T + ? (mix, no F) | pass |
| All ? (no T, no F) | fail |

### Output Files

- `rumor_validate_candidates.csv` — raw input rows sent to validator
- `rumor_validation_config.json` — generated config (ID cols + hard req T/F/? columns)
- `rumor_result.json` — all validated rows with `hard_req_results`, `validation_passed`, `validation_reasoning`
- `rumor_results.csv` — human-readable: ID cols + Disposition + Passed + one T/F/? column per hard req + Reasoning

### Cost Comparison

| Mode | Prompt size | Model | Confidence |
|------|------------|-------|------------|
| Standard | ~2000 tokens | any | AI-determined (H/M/L) |
| Lightweight | ~400 tokens | sonar low-context | Always MEDIUM |

Typical rumor validation cost: **$0.002–0.01** per batch of 20 candidates.

---

## Implementation Details

| File | Change |
|------|--------|
| `src/shared/prompts/multiplex_validation_lightweight.md` | New minimal prompt template |
| `src/shared/schema_validator_simplified.py` | `generate_multiplex_prompt()` selects template; `parse_multiplex_result()` forces MEDIUM |
| `src/lambdas/validation/lambda_function.py` | Reads `validation_mode` from event; stamps onto validator instance |
| `src/lambdas/interface/core/validator_invoker.py` | `invoke_validator_lambda_with_rows()` accepts `validation_mode` |
| `src/lambdas/interface/handlers/background_handler.py` | Reads `validation_mode` from SQS event; adds to payload |
| `src/lambdas/interface/core/sqs_service.py` | `send_full_request()` accepts and forwards `validation_mode` |
| `src/lambdas/interface/actions/start_preview.py` | Forwards `validation_mode` from request_data |
| `src/lambdas/interface/handlers/api_handler.py` | Reads `validation_mode` from POST body |
| `src/lambdas/interface/actions/table_maker/table_maker_lib/rumor_validator.py` | Passes `validation_mode='lightweight'` |
