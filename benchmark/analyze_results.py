#!/usr/bin/env python3
"""
analyze_results.py — Post-run report generator for the benchmark suite.

Loads all run results + ground truth, scores each cell, and generates:
  - master_data.csv       (one row per cell × run — the primary analysis sheet)
  - benchmark_report.md   (human-readable summary, accuracy tables, confidence analysis)

Can be run before ground truth exists (all verdicts will be "no_gt"), and re-run
after adjudication to fill in verdicts. The master_data.csv is always regenerated.

Usage:
    # Produce raw data before GT is established:
    python benchmark/analyze_results.py --results-dir benchmark/results/run_20260227_120000

    # Re-run after creating ground_truth_verified.csv to score everything:
    python benchmark/analyze_results.py --results-dir benchmark/results/run_20260227_120000

Ground truth file (optional — can be created later):
    benchmark/results/run_YYYYMMDD_HHMMSS/ground_truth_verified.csv
    Columns: test_id, entity_id, column, ground_truth_value
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BENCHMARK_DIR = Path(__file__).parent

# Scoring tolerances for numeric cells
EXACT_TOLERANCE = 0.01   # within 1% of ground truth → "exact"
CLOSE_TOLERANCE = 0.10   # within 10%               → "close"

# Confidence tiers in display order
CONFIDENCE_TIERS = ("HIGH", "MEDIUM", "LOW", "UNKNOWN")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_ground_truth(results_dir: Path) -> Dict[Tuple, str]:
    """Returns {(test_id, entity_id, column): ground_truth_value}. Returns {} if file absent."""
    gt_path = results_dir / "ground_truth_verified.csv"
    if not gt_path.exists():
        return {}
    gt = {}
    with gt_path.open() as fh:
        for row in csv.DictReader(fh):
            key = (row["test_id"], row["entity_id"], row["column"])
            gt[key] = row["ground_truth_value"]
    return gt


def _index_metadata(metadata: Dict) -> Dict[Tuple[str, str], Dict]:
    """
    Parse metadata.json (table_metadata format) into a lookup dict.

    Returns:
        {(entity_id, column_name): {
            "display_value": str,    # full_value preferred (untruncated)
            "confidence": str,       # HIGH / MEDIUM / LOW / ID / UNKNOWN
            "sources_count": int,
            "key_citation": str,
            "validator_explanation": str,  # truncated to 500 chars
            "original_value": str,
            "qc_reasoning": str,     # truncated to 300 chars
        }}
    Only RESEARCH/non-ID cells are included (ID cells are used to identify the row).
    """
    index = {}
    rows = metadata.get("rows", [])

    for row in rows:
        cells = row.get("cells", {})
        if not cells:
            continue

        # Find entity_id: the cell(s) with confidence == "ID"
        entity_id = None
        for col_name, cell in cells.items():
            if (cell.get("confidence") or "").upper() == "ID":
                entity_id = (cell.get("full_value") or cell.get("display_value") or "").strip()
                break

        # Fallback: first cell value if no ID column marked
        if entity_id is None and cells:
            first_cell = next(iter(cells.values()))
            entity_id = (first_cell.get("full_value") or first_cell.get("display_value") or "").strip()

        if not entity_id:
            continue

        for col_name, cell in cells.items():
            conf = (cell.get("confidence") or "").upper()
            if conf == "ID":
                continue  # skip the identifier column itself

            comment = cell.get("comment") or {}
            sources = comment.get("sources") or []
            explanation = (comment.get("validator_explanation") or "")
            qc_reasoning = (comment.get("qc_reasoning") or "")
            display_val = (cell.get("full_value") or cell.get("display_value") or "").strip()

            index[(entity_id, col_name)] = {
                "display_value": display_val,
                "confidence": conf if conf else "UNKNOWN",
                "sources_count": len(sources),
                "key_citation": (comment.get("key_citation") or "")[:300],
                "validator_explanation": explanation[:500] if explanation else "",
                "original_value": (comment.get("original_value") or ""),
                "qc_reasoning": qc_reasoning[:300] if qc_reasoning else "",
            }

    return index


def load_run_results(results_dir: Path) -> List[Dict]:
    """Load all completed runs from a results directory."""
    runs = []
    for run_dir in sorted(results_dir.iterdir()):
        if not run_dir.is_dir() or run_dir.name.startswith("ground_truth"):
            continue
        meta_path = run_dir / "run_meta.json"
        results_path = run_dir / "results.json"
        metadata_path = run_dir / "metadata.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("status") != "completed":
            continue

        results_data = {}
        if results_path.exists():
            results_data = json.loads(results_path.read_text())

        # Load and index metadata.json (per-cell confidence + source data)
        metadata_index = {}
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text())
                metadata_index = _index_metadata(metadata)
            except Exception as e:
                print(f"  Warning: could not parse metadata for {run_dir.name}: {e}")

        runs.append({
            "meta": meta,
            "results": results_data,
            "metadata_index": metadata_index,
        })
    return runs


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_cell(predicted: str, ground_truth: str) -> str:
    """Return 'exact', 'close', or 'wrong'."""
    if not predicted or not ground_truth:
        return "wrong"

    pred_clean = predicted.strip().lower()
    gt_clean = ground_truth.strip().lower()

    if pred_clean == gt_clean:
        return "exact"

    # Try numeric comparison
    try:
        pred_num = float(pred_clean.replace(",", ""))
        gt_num = float(gt_clean.replace(",", ""))
        if gt_num == 0:
            return "exact" if pred_num == 0 else "wrong"
        rel_error = abs(pred_num - gt_num) / abs(gt_num)
        if rel_error <= EXACT_TOLERANCE:
            return "exact"
        if rel_error <= CLOSE_TOLERANCE:
            return "close"
        return "wrong"
    except (ValueError, TypeError):
        pass

    # String partial match (e.g. nuclear spin "1/2" vs "0.5")
    if _normalize_string(pred_clean) == _normalize_string(gt_clean):
        return "exact"

    return "wrong"


def _normalize_string(s: str) -> str:
    """Normalize strings for comparison: strip spaces, unify fractions."""
    s = s.strip()
    if "/" in s:
        try:
            num, den = s.split("/")
            return f"{float(num)/float(den):.4f}"
        except Exception:
            pass
    return s


def _extract_costs(meta: Dict) -> Dict:
    """
    Return the best available cost fields from run_meta.

    Priority:
      - dynamo.estimated_eliyahu_cost  — projected full-table cost from preview (no caching
        distortion; best apples-to-apples comparison across models)
      - dynamo.eliyahu_cost_validation — actual cost paid for validation run
      - dynamo.eliyahu_cost_total      — preview + validation actual
      - dynamo.quoted_cost             — $2 minimum flat fee charged to account
      Falls back to the coarse API fields if DynamoDB data is absent.
    """
    # DynamoDB enriched costs (preferred)
    est = _safe_float(meta.get("estimated_eliyahu_cost"))       # from preview extrapolation
    val_actual = _safe_float(meta.get("eliyahu_cost_validation"))
    total_actual = _safe_float(meta.get("eliyahu_cost_total"))
    quoted = _safe_float(meta.get("quoted_cost"))

    # Fallback to coarse API fields
    if not est and not val_actual:
        preview_cost = _safe_float(meta.get("preview_cost")) or 0.0
        val_cost = _safe_float(meta.get("validation_cost")) or 0.0
        total_actual = preview_cost + val_cost
        est = total_actual  # best guess

    return {
        "estimated_eliyahu_cost": est or 0.0,
        "eliyahu_cost_validation": val_actual or 0.0,
        "eliyahu_cost_total": total_actual or 0.0,
        "quoted_cost": quoted or 0.0,
    }


def score_runs(runs: List[Dict], ground_truth: Dict[Tuple, str]) -> List[Dict]:
    """
    Build the master data sheet: one row per (run × entity × column).

    Cell values and confidence come from metadata.json (primary source).
    Ground truth verdicts are populated if ground_truth is non-empty.
    """
    cell_scores = []

    for run in runs:
        meta = run["meta"]
        test_id = meta.get("test_id", "")
        run_id = meta.get("run_id", "")
        search_model = meta.get("search_model", "")
        qc_model = meta.get("qc_model", "")
        complexity = meta.get("complexity_tier", "")
        is_gt_run = meta.get("is_ground_truth", False)
        total_time = _safe_float(meta.get("total_elapsed_s"))
        # estimated_validation_time_s is extrapolated from preview rows before caching occurs.
        # It is the fair time metric — wall-clock elapsed is distorted by cache hits on QC runs.
        est_val_time = _safe_float(meta.get("estimated_validation_time_s"))
        session_id = meta.get("session_id", "")
        started_at = meta.get("started_at", "")
        costs = _extract_costs(meta)

        metadata_index = run.get("metadata_index") or {}

        if metadata_index:
            # Primary path: use per-cell data from metadata.json
            for (entity_id, col_name), cell_info in metadata_index.items():
                predicted = cell_info.get("display_value", "")
                confidence = cell_info.get("confidence", "UNKNOWN")

                gt_key = (test_id, entity_id, col_name)
                gt_val = ground_truth.get(gt_key, "")
                verdict = score_cell(predicted, gt_val) if gt_val else "no_gt"

                cell_scores.append({
                    # Run identification
                    "run_id": run_id,
                    "test_id": test_id,
                    "session_id": session_id,
                    "started_at": started_at,
                    # Model configuration
                    "search_model": search_model,
                    "qc_model": qc_model,
                    "complexity_tier": complexity,
                    "is_ground_truth_run": is_gt_run,
                    # Data point
                    "entity_id": entity_id,
                    "column": col_name,
                    # Values
                    "predicted": predicted,
                    "original_value": cell_info.get("original_value", ""),
                    "ground_truth": gt_val,
                    # Scoring
                    "verdict": verdict,
                    # Confidence + evidence quality
                    "confidence": confidence,
                    "sources_count": cell_info.get("sources_count", 0),
                    "key_citation": cell_info.get("key_citation", ""),
                    "validator_explanation": cell_info.get("validator_explanation", ""),
                    "qc_reasoning": cell_info.get("qc_reasoning", ""),
                    # Cost — use DynamoDB estimated cost (no caching distortion) as primary
                    "estimated_eliyahu_cost": round(costs["estimated_eliyahu_cost"], 6),
                    "eliyahu_cost_validation": round(costs["eliyahu_cost_validation"], 6),
                    "quoted_cost": round(costs["quoted_cost"], 2),
                    # Timing — estimated_validation_time_s is the fair comparison metric;
                    # wall-clock times are preserved for debugging but not used in the report.
                    "estimated_validation_time_s": est_val_time,
                    "total_elapsed_s": total_time,
                    "preview_elapsed_s": meta.get("preview_elapsed_s"),
                    "validation_elapsed_s": meta.get("validation_elapsed_s"),
                })
        else:
            # Fallback: try results rows (no confidence data available)
            rows = run["results"].get("rows") or run["results"].get("data") or []
            for row in rows:
                cols = list(row.keys())
                if not cols:
                    continue
                entity_id = str(row[cols[0]])
                for col_name, value in row.items():
                    if col_name == cols[0]:
                        continue
                    predicted = str(value) if value is not None else ""
                    gt_key = (test_id, entity_id, col_name)
                    gt_val = ground_truth.get(gt_key, "")
                    verdict = score_cell(predicted, gt_val) if gt_val else "no_gt"
                    cell_scores.append({
                        "run_id": run_id, "test_id": test_id, "session_id": session_id,
                        "started_at": started_at, "search_model": search_model,
                        "qc_model": qc_model, "complexity_tier": complexity,
                        "is_ground_truth_run": is_gt_run, "entity_id": entity_id,
                        "column": col_name, "predicted": predicted, "original_value": "",
                        "ground_truth": gt_val, "verdict": verdict, "confidence": "UNKNOWN",
                        "sources_count": 0, "key_citation": "", "validator_explanation": "",
                        "qc_reasoning": "",
                        "estimated_eliyahu_cost": round(costs["estimated_eliyahu_cost"], 6),
                        "eliyahu_cost_validation": round(costs["eliyahu_cost_validation"], 6),
                        "quoted_cost": round(costs["quoted_cost"], 2),
                        "estimated_validation_time_s": est_val_time,
                        "total_elapsed_s": total_time,
                        "preview_elapsed_s": meta.get("preview_elapsed_s"),
                        "validation_elapsed_s": meta.get("validation_elapsed_s"),
                    })

    return cell_scores


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_by_run(cell_scores: List[Dict]) -> List[Dict]:
    """Aggregate cell scores to run-level accuracy metrics."""
    by_run = defaultdict(list)
    for s in cell_scores:
        by_run[(s["run_id"], s["test_id"], s["search_model"], s["qc_model"],
                s["complexity_tier"], s["is_ground_truth_run"])].append(s)

    rows = []
    for (run_id, test_id, search_model, qc_model, complexity, is_gt), cells in sorted(by_run.items()):
        scoreable = [c for c in cells if c["verdict"] != "no_gt"]
        total = len(scoreable)
        exact = sum(1 for c in scoreable if c["verdict"] == "exact")
        close = sum(1 for c in scoreable if c["verdict"] == "close")
        wrong = sum(1 for c in scoreable if c["verdict"] == "wrong")
        accuracy_pct = round(100 * (exact + close * 0.5) / total, 1) if total else 0
        exact_pct = round(100 * exact / total, 1) if total else 0

        # Cost: use estimated_eliyahu_cost (projected full-table, no caching distortion)
        # All cells in a run share the same run-level cost, so take from first cell.
        est_cost = _safe_float(cells[0].get("estimated_eliyahu_cost")) if cells else 0.0
        val_cost = _safe_float(cells[0].get("eliyahu_cost_validation")) if cells else 0.0
        quoted = _safe_float(cells[0].get("quoted_cost")) if cells else 0.0
        # est_time: use preview-extrapolated estimate (unaffected by cache hits on QC runs).
        # Falls back to actual validation wall-clock if estimate not available.
        est_time = (
            _safe_float(cells[0].get("estimated_validation_time_s"))
            or _safe_float(cells[0].get("validation_elapsed_s"))
        ) if cells else 0.0

        # Cost per validated cell (estimated cost ÷ total cells scored in this run)
        # Uses total_cells (not just scoreable) so it reflects the actual workload
        n_cells = len(cells)
        cost_per_cell = round(est_cost / n_cells, 6) if n_cells and est_cost else 0.0

        # Confidence breakdown for this run
        conf_counts = defaultdict(int)
        for c in cells:
            conf_counts[(c.get("confidence") or "UNKNOWN").upper()] += 1

        rows.append({
            "run_id": run_id, "test_id": test_id, "search_model": search_model,
            "qc_model": qc_model, "complexity_tier": complexity, "is_ground_truth": is_gt,
            "total_cells": n_cells, "scoreable_cells": total,
            "exact": exact, "close": close, "wrong": wrong,
            "accuracy_pct": accuracy_pct, "exact_pct": exact_pct,
            "high_conf_cells": conf_counts.get("HIGH", 0),
            "medium_conf_cells": conf_counts.get("MEDIUM", 0),
            "low_conf_cells": conf_counts.get("LOW", 0),
            # Cost fields
            "estimated_eliyahu_cost": round(est_cost, 5),   # projected full-table (no caching)
            "eliyahu_cost_validation": round(val_cost, 5),  # actual cost paid for validation
            "quoted_cost": round(quoted, 2),                # $2-minimum flat fee
            "cost_per_cell": cost_per_cell,                 # estimated_cost / total_cells
            # Time: preview-extrapolated estimate (fair; unaffected by cache hits on QC runs)
            "est_time_s": round(est_time, 1) if est_time else 0,
        })

    return sorted(rows, key=lambda r: (r["test_id"], r["search_model"], r["qc_model"] or ""))


def aggregate_confidence_by_model(cell_scores: List[Dict]) -> List[Dict]:
    """
    One row per (search_model, qc_model) with per-tier confidence stats.

    Each row has nested dicts for HIGH, MEDIUM, LOW tiers (or None if absent):
        {"n": int, "pct_cells": float, "accuracy_pct": float}

    Also includes a "calibrated" string: "✓" (HIGH acc ≥ MED acc ≥ LOW acc),
    "✗" (not monotone), or "" (only one tier — can't assess).
    """
    by_model: Dict[Tuple, Dict[str, List[str]]] = defaultdict(lambda: {"HIGH": [], "MEDIUM": [], "LOW": []})

    for cs in cell_scores:
        if cs["verdict"] == "no_gt":
            continue
        conf = (cs.get("confidence") or "UNKNOWN").upper()
        if conf not in ("HIGH", "MEDIUM", "LOW"):
            continue  # skip UNKNOWN for calibration analysis
        key = (cs["search_model"], cs["qc_model"])
        by_model[key][conf].append(cs["verdict"])

    _TIER_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

    rows = []
    for (sm, qm), tiers in sorted(by_model.items()):
        total_scoreable = sum(len(v) for v in tiers.values())

        tier_stats: Dict[str, Optional[Dict]] = {}
        for tier in ("HIGH", "MEDIUM", "LOW"):
            verdicts = tiers[tier]
            if not verdicts:
                tier_stats[tier] = None
                continue
            n = len(verdicts)
            pct_cells = round(100 * n / total_scoreable, 1) if total_scoreable else 0.0
            exact = sum(1 for v in verdicts if v == "exact")
            close = sum(1 for v in verdicts if v == "close")
            accuracy = round(100 * (exact + close * 0.5) / n, 1) if n else 0.0
            tier_stats[tier] = {"n": n, "pct_cells": pct_cells, "accuracy_pct": accuracy}

        # Calibration: does accuracy decrease from HIGH → MEDIUM → LOW?
        present = [(t, d["accuracy_pct"]) for t, d in tier_stats.items() if d is not None]
        present.sort(key=lambda x: -_TIER_ORDER[x[0]])  # HIGH first
        calibrated = ""
        if len(present) >= 2:
            calibrated = "✓" if all(
                present[i][1] >= present[i + 1][1] for i in range(len(present) - 1)
            ) else "✗"

        rows.append({
            "search_model": sm,
            "qc_model": qm,
            "HIGH": tier_stats.get("HIGH"),
            "MEDIUM": tier_stats.get("MEDIUM"),
            "LOW": tier_stats.get("LOW"),
            "calibrated": calibrated,
            "total_scored": total_scoreable,
        })

    return rows


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(run_rows: List[Dict], cell_scores: List[Dict], results_dir: Path) -> str:
    has_gt = any(cs["verdict"] != "no_gt" for cs in cell_scores)
    lines = [
        "# Hyperplexity Benchmark Report",
        f"\nGenerated from: `{results_dir}`\n",
    ]

    if not has_gt:
        lines.append("> **Note:** No ground truth available yet — accuracy columns show n/a. "
                     "Create `ground_truth_verified.csv` and re-run to score results.\n")

    lines += [
        "## Test Descriptions\n",
        "| Test | Domain | ID Column | Research Columns | Difficulty |",
        "|------|--------|-----------|-----------------|------------|",
        "| test_01 | Nuclear Physics | Isotope | Natural Abundance (%), Nuclear Spin | Hard |",
        "| test_02 | Condensed Matter | Compound | Critical Tc (K), Year Synthesized | Hard |",
        "| test_03 | Molecular Spectroscopy | Molecule | ωₑ (cm⁻¹), ωₑxₑ (cm⁻¹) | Very Hard |",
        "| test_04 | Crystallography | Mineral | a-axis (Å), c-axis (Å) | Very Hard |",
        "| test_05 | Particle Physics | Meson | Mass (MeV/c²), Full Width Γ (MeV) | Extreme |",
        "| test_06 | Reaction Thermodynamics | Reaction | ΔH°rxn (kJ/mol), log10(Keq) at 298 K | Extreme |",
        "| test_07 | Oncology Clinical Trials | Trial | PFS Hazard Ratio, Median PFS – experimental arm (months) | Extreme+ |",
        "\n## Scoring\n",
        f"- **Exact** (≤{EXACT_TOLERANCE*100:.0f}% relative error or string match): 1.0 point",
        f"- **Close** (≤{CLOSE_TOLERANCE*100:.0f}% relative error): 0.5 points",
        "- **Wrong**: 0 points",
        "- **Accuracy %** = (exact + 0.5×close) / total × 100\n",
    ]

    # --- Per-test summary tables ---
    lines.append("## Results by Test\n")
    test_ids = sorted(set(r["test_id"] for r in run_rows))

    for test_id in test_ids:
        test_rows = [r for r in run_rows if r["test_id"] == test_id]
        if not test_rows:
            continue
        lines.append(f"### {test_id}\n")
        sort_key = lambda x: (x["search_model"], x["qc_model"] or "")
        if has_gt:
            lines.append("| Search Model | QC | Accuracy | Exact% | HIGH | MED | LOW | Est Cost ($) | ¢/cell | Est Time (s) | GT |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
            for r in sorted(test_rows, key=sort_key):
                gt_marker = "✓" if r["is_ground_truth"] else ""
                cost_str = f"${r['estimated_eliyahu_cost']:.4f}" if r["estimated_eliyahu_cost"] else "—"
                cpc_str = f"{r['cost_per_cell']*100:.2f}¢" if r["cost_per_cell"] else "—"
                time_str = f"{r['est_time_s']}s" if r["est_time_s"] else "—"
                lines.append(
                    f"| {r['search_model']} | {r['qc_model']} | "
                    f"{r['accuracy_pct']}% | {r['exact_pct']}% | "
                    f"{r['high_conf_cells']} | {r['medium_conf_cells']} | {r['low_conf_cells']} | "
                    f"{cost_str} | {cpc_str} | {time_str} | {gt_marker} |"
                )
        else:
            lines.append("| Search Model | QC | HIGH conf | MED conf | LOW conf | Est Cost ($) | ¢/cell | Est Time (s) |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for r in sorted(test_rows, key=sort_key):
                cost_str = f"${r['estimated_eliyahu_cost']:.4f}" if r["estimated_eliyahu_cost"] else "—"
                cpc_str = f"{r['cost_per_cell']*100:.2f}¢" if r["cost_per_cell"] else "—"
                time_str = f"{r['est_time_s']}s" if r["est_time_s"] else "—"
                lines.append(
                    f"| {r['search_model']} | {r['qc_model']} | "
                    f"{r['high_conf_cells']} | {r['medium_conf_cells']} | {r['low_conf_cells']} | "
                    f"{cost_str} | {cpc_str} | {time_str} |"
                )
        lines.append("")

    # --- Aggregate across all tests (only if GT available) ---
    if has_gt:
        lines.append("## Overall Summary (averaged across tests)\n")
        by_model = defaultdict(list)
        for r in run_rows:
            by_model[(r["search_model"], r["qc_model"])].append(r)

        lines.append("| Search Model | QC | Avg Accuracy | Avg Exact% | Avg Est Cost ($) | Avg ¢/cell | Avg Est Time (s) | Runs |")
        lines.append("|---|---|---|---|---|---|---|---|")
        model_summaries = []
        for (sm, qm), rows_list in by_model.items():
            scoreable = [r for r in rows_list if r["scoreable_cells"] > 0]
            if not scoreable:
                continue
            avg_acc = round(sum(r["accuracy_pct"] for r in scoreable) / len(scoreable), 1)
            avg_exact = round(sum(r["exact_pct"] for r in scoreable) / len(scoreable), 1)
            avg_cost = round(sum(r["estimated_eliyahu_cost"] for r in rows_list) / len(rows_list), 5)
            avg_cpc = round(sum(r["cost_per_cell"] for r in rows_list) / len(rows_list), 6)
            avg_time = round(sum(r["est_time_s"] for r in rows_list) / len(rows_list), 1)
            model_summaries.append((sm, qm, avg_acc, avg_exact, avg_cost, avg_cpc, avg_time, len(rows_list)))

        for sm, qm, avg_acc, avg_exact, avg_cost, avg_cpc, avg_time, n in sorted(model_summaries, key=lambda x: (x[0], x[1] or "")):
            cost_str = f"${avg_cost:.4f}" if avg_cost else "—"
            cpc_str = f"{avg_cpc*100:.2f}¢" if avg_cpc else "—"
            lines.append(f"| {sm} | {qm} | {avg_acc}% | {avg_exact}% | {cost_str} | {cpc_str} | {avg_time}s | {n} |")
        lines.append("")

        # --- Cost-accuracy frontier ---
        lines.append("## Cost-Accuracy Frontier\n")
        lines.append("Models on the frontier: highest accuracy for a given estimated cost.\n")
        pareto = []
        for sm, qm, avg_acc, avg_exact, avg_cost, avg_cpc, avg_time, n in sorted(model_summaries, key=lambda x: x[4]):
            dominated = any(
                oc <= avg_cost and oa > avg_acc
                for _, _, oa, _, oc, _, _, _ in model_summaries
            )
            pareto.append((sm, qm, avg_acc, avg_cost, avg_cpc, not dominated))

        lines.append("| Search Model | QC | Avg Accuracy | Avg Est Cost ($) | Avg ¢/cell | On Frontier |")
        lines.append("|---|---|---|---|---|---|")
        for sm, qm, avg_acc, avg_cost, avg_cpc, on_frontier in sorted(pareto, key=lambda x: x[3]):
            frontier_marker = "★" if on_frontier else ""
            cost_str = f"${avg_cost:.4f}" if avg_cost else "—"
            cpc_str = f"{avg_cpc*100:.2f}¢" if avg_cpc else "—"
            lines.append(f"| {sm} | {qm} | {avg_acc}% | {cost_str} | {cpc_str} | {frontier_marker} |")
        lines.append("")

    # --- Confidence Distribution ---
    conf_rows = aggregate_confidence_by_model(cell_scores)
    if conf_rows:
        lines.append("## Confidence Distribution by Model\n")
        lines.append(
            "One row per model. For each tier: **n (% of cells) / accuracy%**. "
            "Calibrated ✓ means accuracy decreases from HIGH → MED → LOW (well-ordered).\n"
        )

        def _tier_cell(tier_data: Optional[Dict], show_acc: bool) -> str:
            if tier_data is None:
                return "—"
            n = tier_data["n"]
            pct = tier_data["pct_cells"]
            if show_acc:
                acc = tier_data["accuracy_pct"]
                return f"{n} ({pct}%) / {acc}%"
            return f"{n} ({pct}%)"

        lines.append("| Search Model | QC | HIGH n(%)/acc% | MED n(%)/acc% | LOW n(%)/acc% | Calibrated |")
        lines.append("|---|---|---|---|---|---|")
        for r in conf_rows:
            h = _tier_cell(r["HIGH"], has_gt)
            m = _tier_cell(r["MEDIUM"], has_gt)
            lo = _tier_cell(r["LOW"], has_gt)
            cal = r["calibrated"] if has_gt else "—"
            lines.append(
                f"| {r['search_model']} | {r['qc_model']} | {h} | {m} | {lo} | {cal} |"
            )
        lines.append("")

    # --- Hard cells analysis (only with GT) ---
    if has_gt:
        lines.append("## Hardest Cells (most models got wrong)\n")
        wrong_counts = defaultdict(int)
        total_counts = defaultdict(int)
        for cs in cell_scores:
            if cs["verdict"] == "no_gt":
                continue
            key = (cs["test_id"], cs["entity_id"], cs["column"])
            total_counts[key] += 1
            if cs["verdict"] == "wrong":
                wrong_counts[key] += 1

        hard_cells = [
            (test_id, eid, col, wrong_counts[(test_id, eid, col)], total_counts[(test_id, eid, col)])
            for (test_id, eid, col) in total_counts
            if total_counts[(test_id, eid, col)] > 0
        ]
        hard_cells.sort(key=lambda x: -x[3] / x[4])

        lines.append("| Test | Entity | Column | Wrong % | (wrong/total) |")
        lines.append("|---|---|---|---|---|")
        for test_id, eid, col, wrong, total in hard_cells[:15]:
            pct = round(100 * wrong / total)
            lines.append(f"| {test_id} | {eid} | {col} | {pct}% | ({wrong}/{total}) |")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Benchmark results analyzer")
    parser.add_argument("--results-dir", type=Path, required=True,
                        help="Benchmark run directory containing run_id/ subdirs")
    args = parser.parse_args()

    results_dir = args.results_dir
    if not results_dir.exists():
        print(f"ERROR: results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    # Ground truth is optional — can be added later and re-run
    print(f"Loading ground truth from {results_dir}...")
    ground_truth = load_ground_truth(results_dir)
    if ground_truth:
        print(f"  {len(ground_truth)} ground truth cells loaded")
    else:
        print("  No ground_truth_verified.csv found — verdicts will be 'no_gt'")
        print("  (Create it and re-run to score results)")

    print("Loading run results...")
    runs = load_run_results(results_dir)
    print(f"  {len(runs)} completed runs loaded")

    if not runs:
        print("No completed runs found. Exiting.")
        sys.exit(1)

    metadata_count = sum(1 for r in runs if r["metadata_index"])
    print(f"  {metadata_count}/{len(runs)} runs have metadata.json (per-cell data)")

    print("Building master data sheet...")
    cell_scores = score_runs(runs, ground_truth)
    print(f"  {len(cell_scores)} cell records")

    print("Aggregating by run...")
    run_rows = aggregate_by_run(cell_scores)

    # Write master data CSV (the primary analysis sheet)
    master_path = results_dir / "master_data.csv"
    if cell_scores:
        fields = list(cell_scores[0].keys())
        with master_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(cell_scores)
        print(f"Written: {master_path}  ({len(cell_scores)} rows × {len(fields)} columns)")

    # Generate and write report
    print("Generating benchmark report...")
    report = generate_report(run_rows, cell_scores, results_dir)
    report_path = results_dir / "benchmark_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Written: {report_path}")

    # Quick summary
    has_gt = any(cs["verdict"] != "no_gt" for cs in cell_scores)
    if has_gt and run_rows:
        scoreable = [r for r in run_rows if r["scoreable_cells"] > 0]
        if scoreable:
            top = max(scoreable, key=lambda r: r["accuracy_pct"])
            print(
                f"\nTop performer: {top['search_model']} + qc={top['qc_model']} "
                f"on {top['test_id']} — {top['accuracy_pct']}% accuracy, "
            f"${top['estimated_eliyahu_cost']:.4f} est ({top['cost_per_cell']*100:.2f}¢/cell)"
            )
    else:
        # Show confidence distribution summary
        high_total = sum(1 for cs in cell_scores if cs.get("confidence") == "HIGH")
        total = len(cell_scores)
        if total:
            print(f"\nConfidence summary: {high_total}/{total} cells ({round(100*high_total/total)}%) rated HIGH")


if __name__ == "__main__":
    main()
