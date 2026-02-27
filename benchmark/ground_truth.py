#!/usr/bin/env python3
"""
ground_truth.py — Agentic ground truth arbiter for benchmark results.

This script runs ONCE after ALL benchmark runs have completed.  It:
  1. Loads every results.json from the specified run directory.
  2. Collects ALL model answers for every (test, row, column) cell.
  3. Submits a single, comprehensive prompt to Claude that shows:
       - The cell's expected source / reference info (from the base config notes)
       - ALL answers observed across every model run for that cell
     Claude then arbitrates a single authoritative "ground truth" value
     for each cell, plus a confidence score and reasoning.
  4. Writes ground_truth_verified.csv  and  ground_truth_reasoning.json
     into the run directory alongside analyze_results.py inputs.

Claude review happens EXACTLY ONCE — not per-run and not per-cell.
Claude sees all model answers before making any judgement.

Usage:
    python benchmark/ground_truth.py --results-dir benchmark/results/run_20260227_120000
    python benchmark/ground_truth.py --results-dir benchmark/results/run_20260227_120000 \\
        --claude-model claude-opus-4-6
"""

import argparse
import csv
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BENCHMARK_DIR = Path(__file__).parent
TEST_CONFIGS_DIR = BENCHMARK_DIR / "test_configs_base"
TEST_DATA_DIR = BENCHMARK_DIR / "test_data"
MODEL_MATRIX_PATH = BENCHMARK_DIR / "model_matrix.csv"

# Ground truth review uses Opus by default — authoritative and thorough
DEFAULT_CLAUDE_MODEL = "claude-opus-4-6"

# ---------------------------------------------------------------------------
# Reference data: known correct values from authoritative databases.
# Used to seed the prompt — Claude should confirm these, not guess from scratch.
# ---------------------------------------------------------------------------
REFERENCE_ANSWERS = {
    "test_01_isotope_nmr": {
        "Xe-129":  {"Natural Abundance (%)": "26.401",   "Nuclear Spin (hbar)": "1/2"},
        "Xe-131":  {"Natural Abundance (%)": "21.232",   "Nuclear Spin (hbar)": "3/2"},
        "Kr-83":   {"Natural Abundance (%)": "11.593",   "Nuclear Spin (hbar)": "9/2"},
        "Hg-199":  {"Natural Abundance (%)": "16.873",   "Nuclear Spin (hbar)": "1/2"},
        "Tl-203":  {"Natural Abundance (%)": "29.524",   "Nuclear Spin (hbar)": "1/2"},
    },
    "test_02_hts_superconductors": {
        "YBa2Cu3O7 (YBCO)":          {"Critical Temperature Tc (K)": "93",  "Year First Synthesized": "1987"},
        "Bi2Sr2Ca2Cu3O10 (Bi-2223)": {"Critical Temperature Tc (K)": "110", "Year First Synthesized": "1988"},
        "HgBa2Ca2Cu3O8 (Hg-1223)":   {"Critical Temperature Tc (K)": "134", "Year First Synthesized": "1993"},
        "Tl2Ba2Ca2Cu3O10 (Tl-2223)": {"Critical Temperature Tc (K)": "127", "Year First Synthesized": "1988"},
        "La1.85Sr0.15CuO4 (LSCO)":   {"Critical Temperature Tc (K)": "38",  "Year First Synthesized": "1986"},
    },
    "test_03_diatomic_spectroscopy": {
        "H-35Cl":    {"Vibrational Wavenumber we (cm-1)": "2990.946", "Anharmonicity constant wexe (cm-1)": "52.819"},
        "H-79Br":    {"Vibrational Wavenumber we (cm-1)": "2648.975", "Anharmonicity constant wexe (cm-1)": "45.217"},
        "32S-16O":   {"Vibrational Wavenumber we (cm-1)": "1149.2",   "Anharmonicity constant wexe (cm-1)": "5.602"},
        "79Br-19F":  {"Vibrational Wavenumber we (cm-1)": "670.75",   "Anharmonicity constant wexe (cm-1)": "4.05"},
        "12C-16O":   {"Vibrational Wavenumber we (cm-1)": "2169.814", "Anharmonicity constant wexe (cm-1)": "13.288"},
    },
    "test_04_mineral_lattice": {
        "Corundum (alpha-Al2O3)": {"a-axis (Angstrom)": "4.7591", "c-axis (Angstrom)": "12.9894"},
        "Hematite (alpha-Fe2O3)": {"a-axis (Angstrom)": "5.0356", "c-axis (Angstrom)": "13.7489"},
        "Quartz (alpha-SiO2)":    {"a-axis (Angstrom)": "4.9134", "c-axis (Angstrom)": "5.4052"},
        "Calcite (CaCO3)":        {"a-axis (Angstrom)": "4.9898", "c-axis (Angstrom)": "17.0615"},
        "Cinnabar (alpha-HgS)":   {"a-axis (Angstrom)": "4.1449", "c-axis (Angstrom)": "9.4959"},
    },
    "test_05_meson_properties": {
        "rho(770)0":    {"Mass (MeV/c2)": "775.26",   "Full Width Gamma (MeV)": "147.8"},
        "K*(892)0":     {"Mass (MeV/c2)": "895.55",   "Full Width Gamma (MeV)": "47.3"},
        "phi(1020)":    {"Mass (MeV/c2)": "1019.461", "Full Width Gamma (MeV)": "4.249"},
        "J/psi(1S)":    {"Mass (MeV/c2)": "3096.900", "Full Width Gamma (MeV)": "0.09294"},
        "Upsilon(1S)":  {"Mass (MeV/c2)": "9460.30",  "Full Width Gamma (MeV)": "0.05402"},
    },
}

# Tolerance for scoring (used by analyze_results.py)
NUMERIC_TOLERANCE_EXACT = 0.01   # within 1% → exact
NUMERIC_TOLERANCE_CLOSE = 0.10   # within 10% → close


# ---------------------------------------------------------------------------
# Load run results
# ---------------------------------------------------------------------------
def load_all_run_results(results_dir: Path) -> List[Dict]:
    """Load run_meta.json + results.json for every run_id subdirectory."""
    runs = []
    for run_dir in sorted(results_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        meta_path = run_dir / "run_meta.json"
        results_path = run_dir / "results.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("status") != "completed":
            logger.debug(f"Skipping {run_dir.name}: status={meta.get('status')}")
            continue
        results_data = {}
        if results_path.exists():
            results_data = json.loads(results_path.read_text())
        runs.append({"meta": meta, "results": results_data, "run_id": run_dir.name})
    logger.info(f"Loaded {len(runs)} completed runs from {results_dir}")
    return runs


def extract_cell_answers(runs: List[Dict]) -> Dict:
    """
    Build: cell_answers[(test_id, entity_id, column_name)] = [
        {"run_id": ..., "model": ..., "qc": ..., "value": ..., "is_ground_truth": ...},
        ...
    ]
    """
    cell_answers = defaultdict(list)

    for run in runs:
        meta = run["meta"]
        test_id = meta.get("test_id", "")
        search_model = meta.get("search_model", "")
        qc_model = meta.get("qc_model", "")
        is_gt = meta.get("is_ground_truth", False)

        rows = (
            run["results"].get("rows")
            or run["results"].get("data")
            or []
        )
        for row in rows:
            # The first column is the entity ID
            cols = list(row.keys())
            if not cols:
                continue
            entity_id = str(row[cols[0]])

            for col_name, value in row.items():
                if col_name == cols[0]:
                    continue  # skip ID column
                key = (test_id, entity_id, col_name)
                cell_answers[key].append({
                    "run_id": meta["run_id"],
                    "search_model": search_model,
                    "qc_model": qc_model,
                    "value": str(value) if value is not None else "",
                    "is_ground_truth_run": is_gt,
                })

    return dict(cell_answers)


# ---------------------------------------------------------------------------
# Build the comprehensive prompt for Claude
# ---------------------------------------------------------------------------
def build_arbitration_prompt(cell_answers: Dict) -> str:
    """
    Build a single large prompt that shows Claude EVERY cell's observed answers
    across all models, plus the expected reference value, and asks it to
    arbitrate the correct ground truth for each cell.
    """
    lines = [
        "You are a scientific fact-checker with deep expertise across nuclear physics, "
        "condensed matter physics, molecular spectroscopy, crystallography, and particle physics.\n",
        "Below is a comprehensive table of benchmark results. For each (test, entity, column) cell, "
        "I have run many different AI models and collected their answers. I also provide the "
        "expected reference value from authoritative databases (NUBASE2020, ICDD, NIST WebBook, "
        "PDG 2024, and original HTS discovery papers).\n",
        "Your task:\n"
        "1. For EACH cell, determine the single most accurate ground truth value.\n"
        "2. State your confidence: HIGH (you are certain), MEDIUM (likely correct, minor ambiguity), "
        "or LOW (conflicting evidence or genuinely uncertain).\n"
        "3. Provide a brief note if the reference value is being corrected or confirmed.\n\n",
        "IMPORTANT: You see ALL model answers before making any determination. "
        "Consider consensus across models as a signal, but override consensus with "
        "known authoritative values when you are confident.\n\n",
        "Output your response as a JSON array with one object per cell:\n"
        "[\n"
        "  {\n"
        '    "test_id": "test_01_isotope_nmr",\n'
        '    "entity_id": "Xe-129",\n'
        '    "column": "Natural Abundance (%)",\n'
        '    "ground_truth_value": "26.401",\n'
        '    "confidence": "HIGH",\n'
        '    "source": "IUPAC 2016 / NUBASE2020",\n'
        '    "note": "Confirmed — all models converged on 26.401%"\n'
        "  },\n"
        "  ...\n"
        "]\n\n",
        "--- BENCHMARK CELLS ---\n",
    ]

    # Group cells by test_id for readability
    by_test = defaultdict(list)
    for (test_id, entity_id, col_name), answers in sorted(cell_answers.items()):
        by_test[test_id].append((entity_id, col_name, answers))

    for test_id, cells in sorted(by_test.items()):
        # Derive test key for reference lookup
        test_key = _test_key(test_id)
        ref_data = REFERENCE_ANSWERS.get(test_key, {})

        lines.append(f"\n### TEST: {test_id}\n")
        for entity_id, col_name, answers in sorted(cells):
            ref_val = ref_data.get(entity_id, {}).get(col_name, "UNKNOWN")
            lines.append(f"  Entity: {entity_id!r}  |  Column: {col_name!r}")
            lines.append(f"  Reference (authoritative DB): {ref_val}")
            lines.append(f"  Model answers ({len(answers)} runs):")
            # Sort: ground-truth runs first, then alphabetically by model
            sorted_answers = sorted(answers, key=lambda a: (not a["is_ground_truth_run"], a["search_model"]))
            for ans in sorted_answers:
                gt_tag = " [GROUND_TRUTH_RUN]" if ans["is_ground_truth_run"] else ""
                lines.append(
                    f"    [{ans['run_id']}] {ans['search_model']} + qc={ans['qc_model']}: "
                    f"{ans['value']!r}{gt_tag}"
                )
            lines.append("")

    lines.append("--- END OF BENCHMARK CELLS ---\n")
    lines.append("Now output the JSON array of ground truth arbitrations:")

    return "\n".join(lines)


def _test_key(test_id: str) -> str:
    """Map test_id (e.g. 'test_01') to the REFERENCE_ANSWERS key."""
    mapping = {
        "test_01": "test_01_isotope_nmr",
        "test_02": "test_02_hts_superconductors",
        "test_03": "test_03_diatomic_spectroscopy",
        "test_04": "test_04_mineral_lattice",
        "test_05": "test_05_meson_properties",
    }
    return mapping.get(test_id, test_id)


# ---------------------------------------------------------------------------
# Claude API call (single invocation)
# ---------------------------------------------------------------------------
def call_claude(prompt: str, model: str, api_key: str) -> str:
    """Call Claude API once and return the raw text response."""
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": model,
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode())
            return body["content"][0]["text"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise RuntimeError(f"Claude API error {e.code}: {error_body}") from e


def parse_claude_response(text: str) -> List[Dict]:
    """Extract the JSON array from Claude's response (handles markdown code fences)."""
    # Strip markdown code fences if present
    if "```json" in text:
        text = text.split("```json", 1)[1]
        text = text.split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1]
        text = text.split("```", 1)[0]
    text = text.strip()

    # Find the JSON array
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"Could not find JSON array in Claude response:\n{text[:500]}")

    return json.loads(text[start:end])


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def write_ground_truth_csv(arbitrations: List[Dict], output_path: Path):
    """Write ground_truth_verified.csv in a format ready for analyze_results.py."""
    fields = ["test_id", "entity_id", "column", "ground_truth_value", "confidence", "source", "note"]
    with output_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(arbitrations)
    logger.info(f"Wrote ground truth CSV: {output_path} ({len(arbitrations)} cells)")


def write_ground_truth_json(arbitrations: List[Dict], prompt: str, output_path: Path):
    """Write full reasoning JSON including the prompt sent to Claude."""
    payload = {
        "arbitration_count": len(arbitrations),
        "arbitrations": arbitrations,
        "prompt_sent_to_claude": prompt,
    }
    output_path.write_text(json.dumps(payload, indent=2))
    logger.info(f"Wrote ground truth reasoning JSON: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Ground truth arbiter — runs ONCE after all benchmarks complete")
    parser.add_argument("--results-dir", type=Path, required=True,
                        help="Path to a benchmark results run directory (contains run_id/ subdirs)")
    parser.add_argument("--claude-model", default=DEFAULT_CLAUDE_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_CLAUDE_MODEL})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the prompt and print it, but do not call Claude")
    args = parser.parse_args()

    results_dir = args.results_dir
    if not results_dir.exists():
        logger.error(f"Results directory not found: {results_dir}")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.dry_run:
        logger.error("Missing ANTHROPIC_API_KEY environment variable")
        sys.exit(1)

    logger.info(f"Loading all run results from: {results_dir}")
    runs = load_all_run_results(results_dir)

    if not runs:
        logger.error("No completed runs found. Run benchmark first.")
        sys.exit(1)

    logger.info("Extracting cell-level answers across all runs...")
    cell_answers = extract_cell_answers(runs)
    logger.info(f"Total unique cells: {len(cell_answers)}")

    logger.info("Building comprehensive arbitration prompt...")
    prompt = build_arbitration_prompt(cell_answers)
    prompt_len = len(prompt)
    logger.info(f"Prompt length: {prompt_len:,} characters (~{prompt_len//4:,} tokens)")

    if args.dry_run:
        print("\n" + "="*80)
        print("DRY RUN — prompt that would be sent to Claude:\n")
        print(prompt[:5000] + ("\n... [truncated]" if len(prompt) > 5000 else ""))
        print("="*80)
        return

    logger.info(f"Calling Claude ({args.claude_model}) for single-pass ground truth arbitration...")
    raw_response = call_claude(prompt, args.claude_model, api_key)
    logger.info(f"Claude responded ({len(raw_response):,} chars). Parsing...")

    arbitrations = parse_claude_response(raw_response)
    logger.info(f"Parsed {len(arbitrations)} arbitrated cells")

    # Write outputs
    gt_csv_path = results_dir / "ground_truth_verified.csv"
    gt_json_path = results_dir / "ground_truth_reasoning.json"
    write_ground_truth_csv(arbitrations, gt_csv_path)
    write_ground_truth_json(arbitrations, prompt, gt_json_path)

    # Print summary
    confidences = [a.get("confidence", "?") for a in arbitrations]
    logger.info(
        f"\nGround truth summary:\n"
        f"  HIGH confidence:   {confidences.count('HIGH')}\n"
        f"  MEDIUM confidence: {confidences.count('MEDIUM')}\n"
        f"  LOW confidence:    {confidences.count('LOW')}\n"
        f"  Total cells:       {len(arbitrations)}"
    )

    logger.info(f"\nDone. Ground truth files:\n  {gt_csv_path}\n  {gt_json_path}")


if __name__ == "__main__":
    main()
