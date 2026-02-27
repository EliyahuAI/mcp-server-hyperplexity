# Model Control & Benchmark Suite

## Overview

Model selection was previously scattered across 6+ files with no audit trail. This system consolidates all model configuration into a single CSV that is:

1. **The runtime source of truth** — loaded at Lambda startup, hot-swappable via S3
2. **Stored per-run** — every run writes a `model_snapshot.csv` to S3 alongside results
3. **Tracked in DynamoDB** — every run record carries the `deploy_commit` of the code that ran it
4. **Benchmarked** — a structured suite compares every model combination on 5 esoteric scientific test tables

---

## Part 1: Model Control CSV

### File

```
src/model_config/model_control.csv
```

### Schema

```
role, context, model, fallback_1, fallback_2, description
```

### Roles

| Role | Context | Default Model | Notes |
|------|---------|--------------|-------|
| `config_gen_primary` | config_gen | `deepseek-v3.2` | Upload-interview config generation |
| `config_gen_qc_default` | qc | `moonshotai/kimi-k2.5` | QC for config generation |
| `table_maker_interview` | table_maker | `deepseek-v3.2` | Table maker interview phase |
| `table_maker_background_research` | table_maker | `sonar-pro` | Step 0 background research |
| `table_maker_column_definition` | table_maker | `gemini-3-flash-preview` | Step 1 column definition |
| `table_maker_row_discovery_l1` | table_maker | `sonar` | Active escalation level |
| `table_maker_row_discovery_l2` | table_maker | `sonar-pro` | Disabled escalation level |
| `table_maker_row_discovery_l3` | table_maker | `claude-haiku-4-5` | Disabled escalation level |
| `table_maker_qc` | table_maker | `claude-opus-4-6` | Step 3 QC review |
| `upload_interview` | interview | `openrouter/gemini-3-flash-preview-low` | Upload interview dialog |
| `validation_qc_default` | qc | `moonshotai/kimi-k2.5` | Validation run QC |
| `clone_extraction_default` | clone_deepseek | `gemini-2.5-flash-lite` | Extraction across all clone providers |
| `clone_deepseek_t1..t4` | clone_deepseek | t1=flash-lite, t2=deepseek-v3.2, t3=sonnet-4-5, t4=opus-4-6 | |
| `clone_claude_t1..t4` | clone_claude | t1=haiku-4-5, t2..t3=sonnet-4-5, t4=opus-4-6 | |
| `clone_flash_t1..t4` | clone_flash | t1=flash-low, t2=flash, t3=sonnet-4-6, t4=opus-4-6 | |
| `clone_kimi_t1..t4` | clone_kimi | t1..t2=kimi-k2.5, t3=sonnet-4-6, t4=opus-4-6 | |
| `clone_baseten_t1..t4` | clone_baseten | t1..t2=deepseek-baseten, t3=sonnet-4-5, t4=opus-4-6 | |

### Hot-swap via S3

Upload a new CSV to:
```
s3://hyperplexity-storage/config/model_control.csv
```

The Lambda picks it up on the next process start (or after the 30-day in-process TTL expires). No redeploy needed to change models.

---

## Part 2: ModelConfig Loader

### File

```
src/shared/model_config_loader.py
```

### Usage

```python
from model_config_loader import ModelConfig

# Get primary model for a role
model = ModelConfig.get('clone_deepseek_t2')           # → 'deepseek-v3.2'

# Get fallback chain
fallbacks = ModelConfig.get_fallbacks('clone_deepseek_t2')  # → ['claude-sonnet-4-5']

# Get primary + fallbacks as one list (ready for ai_client fallback chain)
chain = ModelConfig.get_with_fallbacks('validation_qc_default')
# → ['moonshotai/kimi-k2.5', 'claude-sonnet-4-6']

# Get full CSV text (for per-run snapshot)
csv_text = ModelConfig.snapshot()

# Get git commit of the deployed code
commit = ModelConfig.deploy_commit
```

### Load order

1. `s3://hyperplexity-storage/config/model_control.csv` (hot-swap, cached 30 days in-process)
2. `model_config/model_control.csv` bundled in the Lambda package (set at deploy time)

### JSON config integration

Every JSON config file that specifies a model now has a companion `model_role` field:

```json
{
  "model": "deepseek-v3.2",
  "model_role": "config_gen_primary"
}
```

The loading code resolves `model_role` via `ModelConfig.get()` at startup and overrides the hardcoded `model` value. If the CSV is unavailable, the hardcoded `model` value is used as a fallback — fully backward-compatible.

Files that carry `model_role`:
- `src/lambdas/interface/actions/config_generation/config_settings.json`
- `src/lambdas/interface/actions/table_maker/table_maker_config.json` (interview, background_research, column_definition, qc_review phases)
- `src/lambdas/interface/actions/upload_interview/upload_interview_config.json`
- `src/the_clone/strategy_config.json` (all provider tiers + `default_extraction_model_role`)

---

## Part 3: Deploy Commit Tracking

### Two independent Lambdas

There are two separate deployment scripts that can be run at different points in code evolution:

| Script | Lambda | Function name |
|--------|--------|---------------|
| `deployment/create_interface_package.py` | Interface Lambda | `perplexity-validator-interface` |
| `deployment/create_package.py` | Validation Lambda | `perplexity-validator` |

Both scripts now:
1. Bundle `model_config/model_control.csv` into the package
2. Generate a `version.json` at build time with the git commit of that deployment

They can be — and often are — at different commits. `version.json` carries a `"lambda"` field so each file is self-identifying.

### `version.json` structure

```json
{
  "commit": "abc123def456...",
  "short_commit": "abc123d",
  "deployed_at": "2026-02-27T12:00:00Z",
  "lambda": "perplexity-validator-interface"
}
```

`ModelConfig.deploy_commit` reads this file from the package root.

### `model_config_loader.py` in each Lambda

- **Interface Lambda**: `model_config_loader.py` is copied explicitly in `copy_source_files()` (step 9)
- **Validation Lambda**: `model_config_loader.py` lands automatically because step 2 of `create_package.py` does `shutil.copytree(SHARED_SRC_DIR, PACKAGE_DIR)` — it copies all of `src/shared/`

`model_control.csv` is in `src/model_config/` (not `src/shared/`), so both scripts now explicitly copy `src/model_config/` into their respective packages.

### Per-run: DynamoDB

Two commit fields are written to every run record in `perplexity-validator-runs`:

| Field | Written by | When |
|-------|-----------|------|
| `deploy_commit` | Interface Lambda (`create_run_record`) | At run record creation (preview or validation start) |
| `validation_deploy_commit` | Validation Lambda (`lambda_function.py`) | At first async processing touch (`ASYNC_PROCESSING_STARTED`) |

This means for any run you can answer: *"exactly which code version ran each Lambda?"*

### Per-run: S3 model snapshot

At the start of every preview or validation run, `background_handler.py` (interface Lambda) writes:

```
s3://hyperplexity-storage/results/{domain}/{email_prefix}/{session_id}/{run_key}/model_snapshot.csv
```

Content is the full `model_control.csv` text with a `# deploy_commit: {sha}` header, reflecting the **interface** Lambda's model config. The validation Lambda resolves its own model config independently from its bundled CSV when executing QC (via `qc_module.py`).

---

## Part 4: Benchmark Suite

### Directory structure

```
benchmark/
  run_benchmark.py          # Orchestrator
  model_matrix.csv          # 46 run definitions
  ground_truth.py           # Single-pass Claude arbiter (runs once after all runs)
  analyze_results.py        # Post-run report generator
  test_data/
    test_01_isotope_nmr.csv
    test_02_hts_superconductors.csv
    test_03_diatomic_spectroscopy.csv
    test_04_mineral_lattice.csv
    test_05_meson_properties.csv
  test_configs_base/
    test_01_config.json  ..  test_05_config.json
  results/                  # gitignored
    run_YYYYMMDD_HHMMSS/
      summary.csv
      ground_truth_verified.csv
      ground_truth_reasoning.json
      benchmark_report.md
      scores.csv
      {run_id}/
        config_used.json
        results.json
        run_meta.json
```

### Test tables

All tests have 5 rows, 1 ID column, and 2 numeric research columns. Questions are chosen from domains that require deep specialist knowledge and have single authoritative numerical answers.

| Test | Domain | ID Column | Col 1 | Col 2 | Source |
|------|--------|-----------|-------|-------|--------|
| 01 | Nuclear Physics | Isotope | Natural Abundance (%) | Nuclear Spin I (ħ) | NUBASE2020 / IUPAC |
| 02 | Condensed Matter | Compound | Critical Temp Tc (K) | Year First Synthesized | Discovery papers / RMP |
| 03 | Molecular Spectroscopy | Molecule (isotopologue) | ωₑ (cm⁻¹) | ωₑxₑ (cm⁻¹) | NIST WebBook / Huber-Herzberg |
| 04 | Crystallography | Mineral (polymorph) | a-axis (Å) | c-axis (Å) | ICDD PDF-4+ / RRUFF |
| 05 | Particle Physics | Meson | Mass (MeV/c²) | Full width Γ (MeV) | PDG 2024 |

**Why these are hard**: values require 3–5 significant figure precision from specialist databases (NUBASE, NIST WebBook, ICDD, PDG). General web search often returns rounded or context-specific variants. Models with web-grounded synthesis (the-clone family) may outperform pure-reasoning models here.

### Run matrix

46 runs across 5 tests × 7 search models × 2–4 QC options:

**Search models tested**: `the-clone`, `the-clone-claude`, `the-clone-flash`, `sonar`, `sonar-pro`, `claude-opus-4-6` (+3 web searches)

**QC options**: `none`, `gemini-3-flash-preview`, `claude-sonnet-4-6`, `claude-opus-4-6`

**Ground truth runs** (1 per test): `claude-opus-4-6` + `claude-opus-4-6` QC + 3 web searches

### Running benchmarks

**Required env vars** (set in environment or `benchmark/.env`):
```
HYPERPLEXITY_API_URL=https://your-api-gateway.execute-api.us-east-1.amazonaws.com/prod
HYPERPLEXITY_API_KEY=your-api-key
ANTHROPIC_API_KEY=your-anthropic-key   # for ground_truth.py only
```

**Smoke test** (1 run — verify end-to-end API flow):
```bash
python benchmark/run_benchmark.py --smoke-test
```

**Minimal** (7 runs — test_01 × all search models × no QC):
```bash
python benchmark/run_benchmark.py --minimal
```

**Full** (46 runs):
```bash
python benchmark/run_benchmark.py --full
# Resume after partial failure:
python benchmark/run_benchmark.py --full --resume
```

**Specific run IDs**:
```bash
python benchmark/run_benchmark.py --run-ids 001 008 016
```

**Dry run** (shows what would execute):
```bash
python benchmark/run_benchmark.py --full --dry-run
```

### Ground truth arbitration

Run **once** after all benchmark runs complete. Sees ALL model answers for ALL cells before making any determination:

```bash
python benchmark/ground_truth.py --results-dir benchmark/results/run_20260227_120000
```

This makes a **single Claude API call** with a comprehensive prompt showing:
- The authoritative reference value (from NUBASE, NIST, ICDD, PDG)
- Every model's answer across all 46 runs for that cell
- Which runs are ground truth runs

Claude outputs confidence (HIGH / MEDIUM / LOW) + reasoning per cell. Result is written to `ground_truth_verified.csv` and `ground_truth_reasoning.json`.

### Analysis and report

```bash
python benchmark/analyze_results.py --results-dir benchmark/results/run_20260227_120000
```

Produces:
- `scores.csv` — per-cell verdicts (exact / close / wrong)
- `benchmark_report.md` — accuracy tables per test, overall summary, cost-accuracy frontier, recommendation matrix, hardest cells

**Scoring**: exact (≤1% error or string match) = 1 pt, close (≤10% error) = 0.5 pt, wrong = 0. Accuracy % = (exact + 0.5×close) / total × 100.

---

## Verification checklist

```bash
# 1. CSV loader works locally
cd src && python -c "
import sys; sys.path.insert(0, 'shared'); sys.path.insert(0, '.')
from model_config_loader import ModelConfig
print(ModelConfig.get('clone_deepseek_t2'))        # → deepseek-v3.2
print(ModelConfig.get('validation_qc_default'))    # → moonshotai/kimi-k2.5
"

# 2. Deploy commit bundled in each Lambda's package
#    version.json is generated inside copy_source_files() of each deploy script.
#    Both scripts require --deploy to actually upload to Lambda; without it they just build the ZIP.
#    Inspect the last-built ZIPs:
unzip -p deployment/interface_lambda_package.zip version.json   # interface Lambda
unzip -p deployment/lambda_package.zip version.json             # validation Lambda
#    Rebuild ZIPs (no Lambda upload):
python deployment/create_interface_package.py
python deployment/create_package.py

# 3. Model snapshot appears in S3 after a live run
aws s3 ls s3://hyperplexity-storage/results/ --recursive | grep model_snapshot

# 4. Benchmark smoke test (end-to-end API + snapshot flow)
python benchmark/run_benchmark.py --smoke-test

# 5. Full benchmark
python benchmark/run_benchmark.py --full
# Resume after partial failure:
python benchmark/run_benchmark.py --full --resume

# 6. Ground truth (after all runs complete — runs Claude once)
python benchmark/ground_truth.py --results-dir benchmark/results/run_YYYYMMDD_HHMMSS

# 7. Report
python benchmark/analyze_results.py --results-dir benchmark/results/run_YYYYMMDD_HHMMSS
```
