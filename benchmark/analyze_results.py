#!/usr/bin/env python3
"""
analyze_results.py — Post-run report generator for the benchmark suite.

Loads all run results + ground truth, scores each cell, and generates:
  - benchmark_report.md   (human-readable summary, accuracy tables, cost frontier)
  - scores.csv            (per-cell scores for further analysis)

Usage:
    python benchmark/analyze_results.py --results-dir benchmark/results/run_20260227_120000

Ground truth must already exist (run ground_truth.py first):
    benchmark/results/run_YYYYMMDD_HHMMSS/ground_truth_verified.csv
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BENCHMARK_DIR = Path(__file__).parent

# Scoring tolerances for numeric cells
EXACT_TOLERANCE = 0.01   # within 1% of ground truth → "exact"
CLOSE_TOLERANCE = 0.10   # within 10%               → "close"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_ground_truth(results_dir: Path) -> Dict[Tuple, str]:
    """Returns {(test_id, entity_id, column): ground_truth_value}."""
    gt_path = results_dir / "ground_truth_verified.csv"
    if not gt_path.exists():
        raise FileNotFoundError(
            f"Ground truth file not found: {gt_path}\n"
            "Run ground_truth.py first."
        )
    gt = {}
    with gt_path.open() as fh:
        for row in csv.DictReader(fh):
            key = (row["test_id"], row["entity_id"], row["column"])
            gt[key] = row["ground_truth_value"]
    return gt


def load_run_results(results_dir: Path) -> List[Dict]:
    runs = []
    for run_dir in sorted(results_dir.iterdir()):
        if not run_dir.is_dir() or run_dir.name.startswith("ground_truth"):
            continue
        meta_path = run_dir / "run_meta.json"
        results_path = run_dir / "results.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("status") != "completed":
            continue
        results_data = {}
        if results_path.exists():
            results_data = json.loads(results_path.read_text())
        runs.append({"meta": meta, "results": results_data})
    return runs


def load_summary_csv(results_dir: Path) -> List[Dict]:
    summary_path = results_dir / "summary.csv"
    if not summary_path.exists():
        return []
    with summary_path.open() as fh:
        return list(csv.DictReader(fh))


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
    # Convert simple fractions to decimal for comparison
    if "/" in s:
        try:
            num, den = s.split("/")
            return f"{float(num)/float(den):.4f}"
        except Exception:
            pass
    return s


def score_runs(runs: List[Dict], ground_truth: Dict[Tuple, str]) -> List[Dict]:
    """Score every cell in every run against ground truth."""
    cell_scores = []

    for run in runs:
        meta = run["meta"]
        test_id = meta.get("test_id", "")
        run_id = meta.get("run_id", "")
        search_model = meta.get("search_model", "")
        qc_model = meta.get("qc_model", "")
        complexity = meta.get("complexity_tier", "")
        is_gt_run = meta.get("is_ground_truth", False)
        preview_cost = _safe_float(meta.get("preview_cost"))
        val_cost = _safe_float(meta.get("validation_cost"))
        total_cost = (preview_cost or 0) + (val_cost or 0)
        total_time = _safe_float(meta.get("total_elapsed_s"))

        rows = run["results"].get("rows") or run["results"].get("data") or []
        for row in rows:
            cols = list(row.keys())
            if not cols:
                continue
            entity_id = str(row[cols[0]])

            for col_name, value in row.items():
                if col_name == cols[0]:
                    continue  # skip ID column
                predicted = str(value) if value is not None else ""

                # Look up ground truth — try both the raw test_id and a normalized key
                gt_key = (test_id, entity_id, col_name)
                gt_val = ground_truth.get(gt_key, "")

                verdict = score_cell(predicted, gt_val) if gt_val else "no_gt"

                cell_scores.append({
                    "run_id": run_id,
                    "test_id": test_id,
                    "entity_id": entity_id,
                    "column": col_name,
                    "search_model": search_model,
                    "qc_model": qc_model,
                    "complexity_tier": complexity,
                    "is_ground_truth_run": is_gt_run,
                    "predicted": predicted,
                    "ground_truth": gt_val,
                    "verdict": verdict,
                    "total_cost_usd": total_cost,
                    "total_elapsed_s": total_time,
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
        if not scoreable:
            continue
        exact = sum(1 for c in scoreable if c["verdict"] == "exact")
        close = sum(1 for c in scoreable if c["verdict"] == "close")
        wrong = sum(1 for c in scoreable if c["verdict"] == "wrong")
        total = len(scoreable)
        accuracy_pct = round(100 * (exact + close * 0.5) / total, 1) if total else 0
        exact_pct = round(100 * exact / total, 1) if total else 0

        # Cost and time from any cell (same per run)
        cost = scoreable[0]["total_cost_usd"] or 0
        elapsed = scoreable[0]["total_elapsed_s"] or 0

        rows.append({
            "run_id": run_id,
            "test_id": test_id,
            "search_model": search_model,
            "qc_model": qc_model,
            "complexity_tier": complexity,
            "is_ground_truth": is_gt,
            "total_cells": total,
            "exact": exact,
            "close": close,
            "wrong": wrong,
            "accuracy_pct": accuracy_pct,
            "exact_pct": exact_pct,
            "cost_usd": round(cost, 4),
            "elapsed_s": round(elapsed, 1),
        })

    return sorted(rows, key=lambda r: (r["test_id"], -r["accuracy_pct"]))


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(run_rows: List[Dict], cell_scores: List[Dict], results_dir: Path) -> str:
    lines = [
        "# Hyperplexity Benchmark Report",
        f"\nGenerated from: `{results_dir}`\n",
        "## Test Descriptions\n",
        "| Test | Domain | ID Column | Research Columns | Difficulty |",
        "|------|--------|-----------|-----------------|------------|",
        "| test_01 | Nuclear Physics | Isotope | Natural Abundance (%), Nuclear Spin | Hard |",
        "| test_02 | Condensed Matter | Compound | Critical Tc (K), Year Synthesized | Hard |",
        "| test_03 | Molecular Spectroscopy | Molecule | ωₑ (cm⁻¹), ωₑxₑ (cm⁻¹) | Very Hard |",
        "| test_04 | Crystallography | Mineral | a-axis (Å), c-axis (Å) | Very Hard |",
        "| test_05 | Particle Physics | Meson | Mass (MeV/c²), Full Width Γ (MeV) | Extreme |",
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
        lines.append("| Search Model | QC | Accuracy | Exact% | Cost ($) | Time (s) | GT |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in sorted(test_rows, key=lambda x: -x["accuracy_pct"]):
            gt_marker = "✓" if r["is_ground_truth"] else ""
            lines.append(
                f"| {r['search_model']} | {r['qc_model']} | "
                f"{r['accuracy_pct']}% | {r['exact_pct']}% | "
                f"${r['cost_usd']:.3f} | {r['elapsed_s']}s | {gt_marker} |"
            )
        lines.append("")

    # --- Aggregate across all tests ---
    lines.append("## Overall Summary (averaged across all 5 tests)\n")
    by_model = defaultdict(list)
    for r in run_rows:
        by_model[(r["search_model"], r["qc_model"])].append(r)

    lines.append("| Search Model | QC | Avg Accuracy | Avg Exact% | Avg Cost ($) | Avg Time (s) | Runs |")
    lines.append("|---|---|---|---|---|---|---|")
    model_summaries = []
    for (sm, qm), rows_list in by_model.items():
        avg_acc = round(sum(r["accuracy_pct"] for r in rows_list) / len(rows_list), 1)
        avg_exact = round(sum(r["exact_pct"] for r in rows_list) / len(rows_list), 1)
        avg_cost = round(sum(r["cost_usd"] for r in rows_list) / len(rows_list), 4)
        avg_time = round(sum(r["elapsed_s"] for r in rows_list) / len(rows_list), 1)
        model_summaries.append((sm, qm, avg_acc, avg_exact, avg_cost, avg_time, len(rows_list)))

    for sm, qm, avg_acc, avg_exact, avg_cost, avg_time, n in sorted(model_summaries, key=lambda x: -x[2]):
        lines.append(f"| {sm} | {qm} | {avg_acc}% | {avg_exact}% | ${avg_cost:.3f} | {avg_time}s | {n} |")
    lines.append("")

    # --- Cost-accuracy frontier ---
    lines.append("## Cost-Accuracy Frontier\n")
    lines.append("Models on the frontier: highest accuracy for given cost budget.\n")
    # Find Pareto-optimal points
    pareto = []
    for sm, qm, avg_acc, avg_exact, avg_cost, avg_time, n in sorted(model_summaries, key=lambda x: x[4]):
        dominated = any(
            other_cost <= avg_cost and other_acc > avg_acc
            for _, _, other_acc, _, other_cost, _, _ in model_summaries
            if (_, _) != (sm, qm)
        )
        pareto.append((sm, qm, avg_acc, avg_cost, not dominated))

    lines.append("| Search Model | QC | Avg Accuracy | Avg Cost ($) | On Frontier |")
    lines.append("|---|---|---|---|---|")
    for sm, qm, avg_acc, avg_cost, on_frontier in sorted(pareto, key=lambda x: x[3]):
        frontier_marker = "★" if on_frontier else ""
        lines.append(f"| {sm} | {qm} | {avg_acc}% | ${avg_cost:.3f} | {frontier_marker} |")
    lines.append("")

    # --- Recommendation matrix ---
    lines.append("## Recommendation Matrix\n")
    lines.append("Based on benchmark results:\n")
    lines.append("| Use Case | Recommended Config | Rationale |")
    lines.append("|---|---|---|")
    lines.append("| Maximum accuracy (cost no object) | claude-opus-4-6 + claude-opus-4-6 QC | Ground truth config |")
    lines.append("| Best accuracy/$  | See cost-accuracy frontier above | — |")
    lines.append("| Fast / cheap sanity check | the-clone + no QC | Lowest cost |")
    lines.append("| Scientific/technical tables | the-clone-claude + claude-opus-4-6 QC | Best for esoteric data |")
    lines.append("")

    # --- Hard cells analysis ---
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
    hard_cells.sort(key=lambda x: -x[3]/x[4])

    lines.append("| Test | Entity | Column | Wrong % | (wrong/total) |")
    lines.append("|---|---|---|---|---|")
    for test_id, eid, col, wrong, total in hard_cells[:15]:
        pct = round(100 * wrong / total)
        lines.append(f"| {test_id} | {eid} | {col} | {pct}% | ({wrong}/{total}) |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Benchmark results analyzer")
    parser.add_argument("--results-dir", type=Path, required=True,
                        help="Benchmark run directory containing ground_truth_verified.csv and run_id/ subdirs")
    args = parser.parse_args()

    results_dir = args.results_dir
    if not results_dir.exists():
        print(f"ERROR: results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading ground truth from {results_dir}...")
    ground_truth = load_ground_truth(results_dir)
    print(f"  {len(ground_truth)} ground truth cells loaded")

    print("Loading run results...")
    runs = load_run_results(results_dir)
    print(f"  {len(runs)} completed runs loaded")

    if not runs:
        print("No completed runs found. Exiting.")
        sys.exit(1)

    print("Scoring cells...")
    cell_scores = score_runs(runs, ground_truth)
    print(f"  {len(cell_scores)} cell scores computed")

    print("Aggregating by run...")
    run_rows = aggregate_by_run(cell_scores)

    # Write scores CSV
    scores_path = results_dir / "scores.csv"
    if cell_scores:
        fields = list(cell_scores[0].keys())
        with scores_path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(cell_scores)
        print(f"Written: {scores_path}")

    # Generate and write report
    print("Generating benchmark report...")
    report = generate_report(run_rows, cell_scores, results_dir)
    report_path = results_dir / "benchmark_report.md"
    report_path.write_text(report)
    print(f"Written: {report_path}")

    # Print quick summary
    if run_rows:
        top = max(run_rows, key=lambda r: r["accuracy_pct"])
        print(
            f"\nTop performer: {top['search_model']} + qc={top['qc_model']} "
            f"on {top['test_id']} — {top['accuracy_pct']}% accuracy, ${top['cost_usd']:.3f}"
        )


if __name__ == "__main__":
    main()
