# Capability-Based Model Selection

## Design philosophy

The config-generation LLM describes *what each search group needs* using a small set of flags set on the group itself. The system derives models algorithmically from those flags. The LLM never sees model names and is never asked to make cost or capability trade-offs — that is the system's job.

This separation means:
- Changing a model requires editing one JSON file, not re-prompting the LLM
- The LLM's decisions are stable and interpretable (flag semantics, not model knowledge)
- Refinement passes cannot accidentally downgrade or lock in a model

---

## Flags

Each search group (Groups 1+) in a config carries a `capability` field with pipe-separated flags. Flags describe what that **group as a whole** needs — think about the dominant requirement across the columns in the group.

| Flag | What the LLM is deciding |
|------|--------------------------|
| `Ql` | The group's answers are qualitative — summaries, labels, or narratives rather than precise numeric values |
| `P` | Exact supporting text required — the answer must be matched to specific verbatim figures or data from a primary source. Do NOT use just because a topic is important or non-obvious. Forces search track (overrides `N`) and the-clone models (overrides `Ql`) |
| `C` | PhD-level reasoning required — a competent domain expert with internet access could not answer this without applying deep specialised expertise or synthesising genuinely conflicting evidence. Do NOT use for hard-to-find facts or technical multi-field lookups — **2–5× cost increase** |
| `N` | The group contains only derived/calculated columns — no web search is needed |
| `U` | Model sophistication was insufficient — results were wrong AND other fixes (notes, search group restructuring) have already been tried or clearly won't help. True last resort — **2–5× cost increase**, refinement only |

The LLM decides only whether these descriptions match the group's needs. Model routing is handled entirely by `capability_model_derivation.py` reading `capability_config.json`.

> **Cost note**: `C` and `U` each step up to a significantly more expensive model tier. They should be reserved for groups where simpler processing has demonstrably failed — not applied speculatively or as a default for hard-looking groups.

---

## Tracks

`N` determines the track for a group. All other flags are modifiers within the track.

### No-search track (`N` present)

The group synthesises from context rather than searching the web. C and U each contribute one upgrade step.

| C + U count | Tier |
|-------------|------|
| 0 | Base synthesis (fast, cheap) |
| 1 | Mid synthesis (domain reasoning) |
| 2 | Top synthesis (full expert reasoning) |

### Search track (no `N`)

The group retrieves from the web. `Ql` selects the lightweight retrieval tier; absence of `Ql` selects the deep-search tier. C and U push to the top tier regardless.

| Flags | Tier |
|-------|------|
| `Ql` only | Lightweight retrieval |
| untagged (no `Ql`, no upgrades) | Deep-search retrieval |
| `C` or `U` present | Top-tier deep search |
| both `C` and `U` | Top-tier deep search (same as one upgrade) |

**Why `Ql` routes to a lighter model:** Qualitative answers — company descriptions, brief summaries, category labels — do not require precision retrieval or citation pinning. Sonar-pro handles these well at a fraction of the cost. The system makes this call; the LLM just flags the answer type.

**Why the search top tier caps at one model for both upgrade counts:** On the search track the top tier (`the-clone-claude`) is already a full-reasoning deep-search model. There is no meaningful tier above it in the search family; C+U together do not warrant a different search model, only the no-search track has a second step because switching from Sonnet to Opus synthesis is a meaningful jump.

---

## QC

A second model reviews all group outputs together after validation completes. Its purpose is cross-group coherence — catching cases where Group 1 and Group 2 produce outputs that contradict each other, or where a value looks plausible in isolation but is inconsistent with context.

**QC is disabled for single-group configs.** With one group there is nothing to cross-check and QC adds latency and cost with no accuracy benefit (confirmed by benchmark: single the-clone-flash group with gemini QC scored lower than without QC, because clone errors are high-confidence wrong answers that QC passes through).

**QC triggers at 2+ groups.** The model used depends on what the groups are running:
- Any group running a claude-family model → elevated QC (a stronger claude model). A gemini QC reviewer cannot reliably catch reasoning errors made by claude-class models.
- All groups on sonar or the-clone-flash → standard QC (gemini-3-flash-preview). Benchmark: sonar-pro + gemini QC reached 100% accuracy on hard science cells at 1.71¢/cell — the best cost-accuracy point in a 14-model × 8-test matrix.

---

## Configuration

All model names and thresholds live in `capability_config.json` alongside each field's `_note_*` explaining the design intent. To change a model, edit the JSON. No Python changes required.

The Python interpreter (`capability_model_derivation.py`) is a pure rule follower: it reads the config, applies the track logic, and writes `model` onto each search group and `qc_settings` onto the config. It contains no model names.

---

## Benchmark evidence

Results from `benchmark/results/run_comprehensive_20260227_165000/benchmark_report.md` (14 models × 8 tests, 112 runs):

| Config | Accuracy | Cost/cell |
|--------|----------|-----------|
| sonar-pro, no QC | 95.2% | 0.75¢ |
| sonar-pro + gemini QC | 100.0% | 1.71¢ |
| the-clone-flash, no QC | 93.8% (test_06) | ~1¢ |
| the-clone-flash + gemini QC | 68.8% (test_06) | higher |
| the-clone-claude, no QC | 98.8% avg | 3.93¢ |
| claude-opus + opus QC | 100.0% | 19.10¢ |

Key findings that shaped the model selection rules:
- Gemini QC dramatically helps sonar-class models on hard tests (chemistry, spectroscopy constants)
- Gemini QC can hurt the-clone models — clone errors are high-confidence and pass QC unchanged
- Multi-group configs benefit from QC for cross-group coherence even when single-group would not
