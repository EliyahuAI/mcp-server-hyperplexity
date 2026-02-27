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
        preview_cost = _safe_float(meta.get("preview_cost")) or 0.0
        val_cost = _safe_float(meta.get("validation_cost")) or 0.0
        total_cost = preview_cost + val_cost
        total_time = _safe_float(meta.get("total_elapsed_s"))
        session_id = meta.get("session_id", "")
        started_at = meta.get("started_at", "")

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
                    # Cost / timing
                    "total_cost_usd": round(total_cost, 5),
                    "preview_cost_usd": round(preview_cost, 5),
                    "validation_cost_usd": round(val_cost, 5),
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
                        "qc_reasoning": "", "total_cost_usd": round(total_cost, 5),
                        "preview_cost_usd": round(preview_cost, 5),
                        "validation_cost_usd": round(val_cost, 5),
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

        cost = cells[0]["total_cost_usd"] if cells else 0
        elapsed = cells[0]["total_elapsed_s"] if cells else 0

        # Confidence breakdown for this run
        conf_counts = defaultdict(int)
        for c in cells:
            conf_counts[(c.get("confidence") or "UNKNOWN").upper()] += 1

        rows.append({
            "run_id": run_id, "test_id": test_id, "search_model": search_model,
            "qc_model": qc_model, "complexity_tier": complexity, "is_ground_truth": is_gt,
            "total_cells": len(cells), "scoreable_cells": total,
            "exact": exact, "close": close, "wrong": wrong,
            "accuracy_pct": accuracy_pct, "exact_pct": exact_pct,
            "high_conf_cells": conf_counts.get("HIGH", 0),
            "medium_conf_cells": conf_counts.get("MEDIUM", 0),
            "low_conf_cells": conf_counts.get("LOW", 0),
            "cost_usd": round(cost, 4),
            "elapsed_s": round(elapsed, 1) if elapsed else 0,
        })

    return sorted(rows, key=lambda r: (r["test_id"], -r["accuracy_pct"]))


def aggregate_confidence_by_model(cell_scores: List[Dict]) -> List[Dict]:
    """
    Per (search_model, qc_model, confidence_tier): count cells and accuracy.
    Useful for calibration analysis (does HIGH confidence → higher accuracy?).
    """
    by_model_conf = defaultdict(lambda: defaultdict(list))

    for cs in cell_scores:
        if cs["verdict"] == "no_gt":
            continue
        conf = (cs.get("confidence") or "UNKNOWN").upper()
        if conf not in ("HIGH", "MEDIUM", "LOW"):
            conf = "UNKNOWN"
        key = (cs["search_model"], cs["qc_model"])
        by_model_conf[key][conf].append(cs["verdict"])

    rows = []
    for (sm, qm), conf_dict in sorted(by_model_conf.items()):
        total_scoreable = sum(len(v) for v in conf_dict.values())
        for conf in CONFIDENCE_TIERS:
            verdicts = conf_dict.get(conf, [])
            if not verdicts:
                continue
            n = len(verdicts)
            pct_of_cells = round(100 * n / total_scoreable, 1) if total_scoreable else 0
            exact = sum(1 for v in verdicts if v == "exact")
            close = sum(1 for v in verdicts if v == "close")
            wrong = sum(1 for v in verdicts if v == "wrong")
            accuracy = round(100 * (exact + close * 0.5) / n, 1) if n else 0
            rows.append({
                "search_model": sm, "qc_model": qm, "confidence": conf,
                "cell_count": n, "pct_of_cells": pct_of_cells,
                "exact": exact, "close": close, "wrong": wrong,
                "accuracy_pct": accuracy,
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
        if has_gt:
            lines.append("| Search Model | QC | Accuracy | Exact% | HIGH | MED | LOW | Cost ($) | Time (s) | GT |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|")
            for r in sorted(test_rows, key=lambda x: -x["accuracy_pct"]):
                gt_marker = "✓" if r["is_ground_truth"] else ""
                lines.append(
                    f"| {r['search_model']} | {r['qc_model']} | "
                    f"{r['accuracy_pct']}% | {r['exact_pct']}% | "
                    f"{r['high_conf_cells']} | {r['medium_conf_cells']} | {r['low_conf_cells']} | "
                    f"${r['cost_usd']:.3f} | {r['elapsed_s']}s | {gt_marker} |"
                )
        else:
            lines.append("| Search Model | QC | HIGH conf | MED conf | LOW conf | Cost ($) | Time (s) |")
            lines.append("|---|---|---|---|---|---|---|")
            for r in sorted(test_rows, key=lambda x: -x["high_conf_cells"]):
                lines.append(
                    f"| {r['search_model']} | {r['qc_model']} | "
                    f"{r['high_conf_cells']} | {r['medium_conf_cells']} | {r['low_conf_cells']} | "
                    f"${r['cost_usd']:.3f} | {r['elapsed_s']}s |"
                )
        lines.append("")

    # --- Aggregate across all tests (only if GT available) ---
    if has_gt:
        lines.append("## Overall Summary (averaged across tests)\n")
        by_model = defaultdict(list)
        for r in run_rows:
            by_model[(r["search_model"], r["qc_model"])].append(r)

        lines.append("| Search Model | QC | Avg Accuracy | Avg Exact% | Avg Cost ($) | Avg Time (s) | Runs |")
        lines.append("|---|---|---|---|---|---|---|")
        model_summaries = []
        for (sm, qm), rows_list in by_model.items():
            scoreable = [r for r in rows_list if r["scoreable_cells"] > 0]
            if not scoreable:
                continue
            avg_acc = round(sum(r["accuracy_pct"] for r in scoreable) / len(scoreable), 1)
            avg_exact = round(sum(r["exact_pct"] for r in scoreable) / len(scoreable), 1)
            avg_cost = round(sum(r["cost_usd"] for r in rows_list) / len(rows_list), 4)
            avg_time = round(sum(r["elapsed_s"] for r in rows_list) / len(rows_list), 1)
            model_summaries.append((sm, qm, avg_acc, avg_exact, avg_cost, avg_time, len(rows_list)))

        for sm, qm, avg_acc, avg_exact, avg_cost, avg_time, n in sorted(model_summaries, key=lambda x: -x[2]):
            lines.append(f"| {sm} | {qm} | {avg_acc}% | {avg_exact}% | ${avg_cost:.3f} | {avg_time}s | {n} |")
        lines.append("")

        # --- Cost-accuracy frontier ---
        lines.append("## Cost-Accuracy Frontier\n")
        lines.append("Models on the frontier: highest accuracy for a given cost budget.\n")
        pareto = []
        for sm, qm, avg_acc, avg_exact, avg_cost, avg_time, n in sorted(model_summaries, key=lambda x: x[4]):
            dominated = any(
                other_cost <= avg_cost and other_acc > avg_acc
                for _, _, other_acc, _, other_cost, _, _ in model_summaries
            )
            pareto.append((sm, qm, avg_acc, avg_cost, not dominated))

        lines.append("| Search Model | QC | Avg Accuracy | Avg Cost ($) | On Frontier |")
        lines.append("|---|---|---|---|---|")
        for sm, qm, avg_acc, avg_cost, on_frontier in sorted(pareto, key=lambda x: x[3]):
            frontier_marker = "★" if on_frontier else ""
            lines.append(f"| {sm} | {qm} | {avg_acc}% | ${avg_cost:.3f} | {frontier_marker} |")
        lines.append("")

    # --- Confidence Distribution ---
    conf_rows = aggregate_confidence_by_model(cell_scores)
    if conf_rows:
        lines.append("## Confidence Distribution by Model\n")
        lines.append(
            "Each model's tendency to produce HIGH/MEDIUM/LOW confidence cells, "
            "and whether that confidence is calibrated (higher confidence → higher accuracy).\n"
        )
        lines.append("| Search Model | QC | Confidence | Cells | % of Cells | Accuracy |")
        lines.append("|---|---|---|---|---|---|")
        for r in conf_rows:
            acc_str = f"{r['accuracy_pct']}%" if has_gt else "—"
            lines.append(
                f"| {r['search_model']} | {r['qc_model']} | {r['confidence']} | "
                f"{r['cell_count']} | {r['pct_of_cells']}% | {acc_str} |"
            )
        lines.append("")

        if has_gt:
            # Calibration summary: one row per model
            lines.append("### Confidence Calibration\n")
            lines.append(
                "Well-calibrated models have HIGH accuracy > MEDIUM accuracy > LOW accuracy.\n"
            )
            lines.append("| Search Model | QC | HIGH acc | MEDIUM acc | LOW acc | Calibrated? |")
            lines.append("|---|---|---|---|---|---|")
            by_model_conf = defaultdict(dict)
            for r in conf_rows:
                by_model_conf[(r["search_model"], r["qc_model"])][r["confidence"]] = r["accuracy_pct"]
            for (sm, qm), conf_acc in sorted(by_model_conf.items()):
                high_acc = conf_acc.get("HIGH")
                med_acc = conf_acc.get("MEDIUM")
                low_acc = conf_acc.get("LOW")
                h_str = f"{high_acc}%" if high_acc is not None else "—"
                m_str = f"{med_acc}%" if med_acc is not None else "—"
                l_str = f"{low_acc}%" if low_acc is not None else "—"
                # Check calibration
                calibrated = ""
                if high_acc is not None and med_acc is not None and low_acc is not None:
                    calibrated = "✓" if high_acc >= med_acc >= low_acc else "✗"
                elif high_acc is not None and med_acc is not None:
                    calibrated = "✓" if high_acc >= med_acc else "✗"
                lines.append(f"| {sm} | {qm} | {h_str} | {m_str} | {l_str} | {calibrated} |")
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
                f"on {top['test_id']} — {top['accuracy_pct']}% accuracy, ${top['cost_usd']:.3f}"
            )
    else:
        # Show confidence distribution summary
        high_total = sum(1 for cs in cell_scores if cs.get("confidence") == "HIGH")
        total = len(cell_scores)
        if total:
            print(f"\nConfidence summary: {high_total}/{total} cells ({round(100*high_total/total)}%) rated HIGH")


if __name__ == "__main__":
    main()
