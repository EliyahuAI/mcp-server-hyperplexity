# QC Validation Scripts

Scripts for validating drug metadata entries for factual accuracy.

## Scripts

### `run_qc_validation.py`
Generates validation tasks from metadata JSON file.

**Usage:**
```bash
python3 scripts/run_qc_validation.py
```

**Output:** `validation_batch.json`

---

### `select_validation_sample.py`
Selects stratified sample of 100 entries for validation.

**Usage:**
```bash
python3 scripts/select_validation_sample.py
```

**Input:** `validation_batch.json`
**Output:** `validation_sample_100.json`

---

### `qc_validation_framework.py`
Core framework classes and scoring rubric (imported by other scripts).

---

## Workflow

1. Run `run_qc_validation.py` to generate tasks
2. Run `select_validation_sample.py` to sample entries
3. Use Claude Code Task tool to deploy validation agents
4. Compile results into validation report

See `docs/METADATA_QC_VALIDATION_GUIDE.md` for complete instructions.
