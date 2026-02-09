#!/usr/bin/env python3
"""
Contamination analysis for take3 - comparing all three versions.
"""

import json
import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

def load_json(filepath: str) -> dict:
    """Load JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def normalize_name(name: str) -> str:
    """Normalize company/product name for matching."""
    name = name.lower().strip()
    # Remove common suffixes
    name = re.sub(r'\s*(inc\.?|ltd\.?|llc|corporation|corp\.?|company|co\.?|pharmaceuticals?|therapeutics?|ag|gmbh)\s*$', '', name, flags=re.IGNORECASE)
    # Remove parenthetical info
    name = re.sub(r'\([^)]*\)', '', name)
    name = name.strip()
    return name

def build_entity_mapping(data: dict) -> Tuple[Dict[int, Tuple[str, str]], Set[str], Set[str]]:
    """
    Build mapping of row index to (company, product) and sets of all entities.
    Returns: (row_mapping, all_companies, all_products)
    """
    row_mapping = {}
    all_companies = set()
    all_products = set()

    rows = data.get('rows', [])
    for idx, row in enumerate(rows):
        cells = row.get('cells', {})
        company = cells.get('Company Name', {}).get('full_value', 'Unknown')
        product = cells.get('Product / Candidate Name', {}).get('full_value', 'Unknown')

        row_mapping[idx] = (company, product)

        if company and company != 'Unknown':
            all_companies.add(company)
        if product and product != 'Unknown':
            all_products.add(product)

    return row_mapping, all_companies, all_products

def check_row_contamination(row_idx: int, row_data: dict, current_company: str,
                           current_product: str, all_companies: Set[str],
                           all_products: Set[str]) -> Dict:
    """
    Check if this row's validation sources reference OTHER rows' entities.
    """
    result = {
        'row_idx': row_idx,
        'company': current_company,
        'product': current_product,
        'total_validations': 0,
        'contaminated_validations': 0,
        'contamination_details': []
    }

    # Normalize current entities
    current_company_norm = normalize_name(current_company)
    current_product_norm = normalize_name(current_product)

    # Build sets of foreign entities (excluding current row's entities and variants)
    foreign_companies = set()
    foreign_products = set()

    for comp in all_companies:
        comp_norm = normalize_name(comp)
        # Skip if it's the same as current company or substring match
        if comp_norm == current_company_norm:
            continue
        if current_company_norm and (comp_norm in current_company_norm or current_company_norm in comp_norm):
            continue
        foreign_companies.add(comp)

    for prod in all_products:
        prod_norm = normalize_name(prod)
        # Skip if it's the same as current product or substring match
        if prod_norm == current_product_norm:
            continue
        if current_product_norm and (prod_norm in current_product_norm or current_product_norm in prod_norm):
            continue
        foreign_products.add(prod)

    # Check all cells in this row
    cells = row_data.get('cells', {})
    for col_name, cell_data in cells.items():
        if not isinstance(cell_data, dict):
            continue

        comment = cell_data.get('comment', {})
        sources = comment.get('sources', [])

        if not sources:
            continue

        result['total_validations'] += 1

        # Collect all source text
        sources_text = ""
        for source in sources:
            if isinstance(source, dict):
                title = source.get('title', '')
                snippet = source.get('snippet', '')
                url = source.get('url', '')
                sources_text += f"{title} {snippet} ".lower()

        if not sources_text:
            continue

        # Check for foreign entity mentions
        found_foreign_companies = []
        found_foreign_products = []

        for foreign_comp in foreign_companies:
            # Simple substring check
            if foreign_comp.lower() in sources_text:
                # Additional check: not in URL
                if not any(foreign_comp.lower() in s.get('url', '').lower() for s in sources if isinstance(s, dict)):
                    found_foreign_companies.append(foreign_comp)

        for foreign_prod in foreign_products:
            if foreign_prod.lower() in sources_text:
                if not any(foreign_prod.lower() in s.get('url', '').lower() for s in sources if isinstance(s, dict)):
                    found_foreign_products.append(foreign_prod)

        if found_foreign_companies or found_foreign_products:
            result['contaminated_validations'] += 1
            result['contamination_details'].append({
                'column': col_name,
                'foreign_companies': found_foreign_companies[:3],
                'foreign_products': found_foreign_products[:3],
                'snippet': sources_text[:250]
            })

    return result

def analyze_file_comprehensive(filepath: str, sample_indices: List[int] = None) -> Dict:
    """Comprehensive contamination analysis."""
    data = load_json(filepath)
    rows = data.get('rows', [])

    # Build entity database
    row_mapping, all_companies, all_products = build_entity_mapping(data)

    print(f"  Dataset: {len(rows)} rows, {len(all_companies)} companies, {len(all_products)} products")

    # Determine which rows to analyze
    if sample_indices is None:
        # Sample evenly
        step = max(1, len(rows) // 10)
        sample_indices = list(range(0, len(rows), step))[:10]

    results = {
        'total_rows': len(rows),
        'sampled_rows': [],
        'sample_indices': sample_indices,
        'overall_stats': {
            'total_validations': 0,
            'contaminated_validations': 0,
            'rows_with_contamination': 0
        }
    }

    for idx in sample_indices:
        if idx >= len(rows):
            continue

        row = rows[idx]
        company, product = row_mapping[idx]

        contamination = check_row_contamination(
            idx, row, company, product, all_companies, all_products
        )

        results['sampled_rows'].append(contamination)

        # Update overall stats
        results['overall_stats']['total_validations'] += contamination['total_validations']
        results['overall_stats']['contaminated_validations'] += contamination['contaminated_validations']
        if contamination['contaminated_validations'] > 0:
            results['overall_stats']['rows_with_contamination'] += 1

    # Calculate rate
    if results['overall_stats']['total_validations'] > 0:
        results['overall_stats']['contamination_rate'] = (
            results['overall_stats']['contaminated_validations'] /
            results['overall_stats']['total_validations']
        )
    else:
        results['overall_stats']['contamination_rate'] = 0.0

    return results

def print_three_way_report(take1_results: Dict, take2_results: Dict, take3_results: Dict):
    """Print comprehensive three-way comparison report."""

    print("\n" + "=" * 80)
    print("MEMORY CONTAMINATION ANALYSIS - THREE-WAY COMPARISON")
    print("=" * 80)
    print()

    print("OVERALL STATISTICS")
    print("-" * 80)
    print(f"Total Rows in Dataset: {take1_results['total_rows']}")
    print(f"Sampled Rows: {len(take1_results['sampled_rows'])}")
    print()

    # Print stats for all three versions
    for label, results in [("TAKE 1 (Original)", take1_results),
                           ("TAKE 2 (First Fix)", take2_results),
                           ("TAKE 3 (Latest)", take3_results)]:
        print(f"{label}:")
        print(f"  Total Validations Checked: {results['overall_stats']['total_validations']}")
        print(f"  Contaminated Validations: {results['overall_stats']['contaminated_validations']}")
        print(f"  Rows with Contamination: {results['overall_stats']['rows_with_contamination']}/{len(results['sampled_rows'])}")
        print(f"  Contamination Rate: {results['overall_stats']['contamination_rate']:.1%}")
        print()

    # Calculate improvements
    take1_rate = take1_results['overall_stats']['contamination_rate']
    take2_rate = take2_results['overall_stats']['contamination_rate']
    take3_rate = take3_results['overall_stats']['contamination_rate']

    print("IMPROVEMENT ANALYSIS")
    print("-" * 80)
    if take1_rate > 0:
        take2_reduction = ((take1_rate - take2_rate) / take1_rate) * 100
        take3_reduction = ((take1_rate - take3_rate) / take1_rate) * 100
        take2_to_3_change = ((take2_rate - take3_rate) / take2_rate) * 100 if take2_rate > 0 else 0

        print(f"Take 1 → Take 2: {take2_reduction:+.1f}% ({take1_rate:.1%} → {take2_rate:.1%})")
        print(f"Take 1 → Take 3: {take3_reduction:+.1f}% ({take1_rate:.1%} → {take3_rate:.1%})")
        print(f"Take 2 → Take 3: {take2_to_3_change:+.1f}% ({take2_rate:.1%} → {take3_rate:.1%})")
    print()

    # Side-by-side comparison (Take 1 vs Take 2 only if rows match)
    # Take 3 has different rows, so only show Take 1 vs Take 2
    print("=" * 80)
    print("ROW-BY-ROW COMPARISON (Take 1 vs Take 2 - Same Rows)")
    print("=" * 80)

    for take1_row in take1_results['sampled_rows'][:10]:
        take2_row = next(
            (r for r in take2_results['sampled_rows'] if r['row_idx'] == take1_row['row_idx']),
            None
        )

        if take2_row:
            print(f"\nRow {take1_row['row_idx']}: {take1_row['company']} / {take1_row['product']}")

            take1_cont = take1_row['contaminated_validations']
            take1_total = take1_row['total_validations']
            take2_cont = take2_row['contaminated_validations']
            take2_total = take2_row['total_validations']

            print(f"  Take 1: {take1_cont}/{take1_total} contaminated ({100*take1_cont/take1_total if take1_total > 0 else 0:.0f}%)")
            print(f"  Take 2: {take2_cont}/{take2_total} contaminated ({100*take2_cont/take2_total if take2_total > 0 else 0:.0f}%)")

            # Status determination
            if take2_cont == 0 and take1_cont > 0:
                print(f"  ✓✓ FULLY CLEANED in take 2")
            elif take2_cont < take1_cont:
                print(f"  ✓ IMPROVED: Reduced from {take1_cont} to {take2_cont}")
            elif take2_cont > take1_cont:
                print(f"  ✗ WORSENED: Increased from {take1_cont} to {take2_cont}")
            elif take2_cont == 0:
                print(f"  ✓ CLEAN in both versions")
            else:
                print(f"  = NO CHANGE")

    # Show Take 3 rows separately
    print("\n" + "=" * 80)
    print("TAKE 3 CONTAMINATION STATUS (New Rows)")
    print("=" * 80)

    for take3_row in take3_results['sampled_rows'][:10]:
        print(f"\nRow {take3_row['row_idx']}: {take3_row['company']} / {take3_row['product']}")
        take3_cont = take3_row['contaminated_validations']
        take3_total = take3_row['total_validations']
        print(f"  Contaminated: {take3_cont}/{take3_total} ({100*take3_cont/take3_total if take3_total > 0 else 0:.0f}%)")

        if take3_cont == 0:
            print(f"  ✓ CLEAN")
        elif take3_cont <= 2:
            print(f"  ~ Low contamination")
        elif take3_cont <= 5:
            print(f"  ⚠ Moderate contamination")
        else:
            print(f"  ✗ High contamination")

    # Final verdict
    print("\n" + "=" * 80)
    print("FINAL VERDICT")
    print("=" * 80)
    print()

    if take3_rate == 0 and take1_rate > 0:
        print("✓✓✓ CONTAMINATION ELIMINATED IN TAKE 3")
        print(f"    Take 1: {take1_rate:.1%} contamination rate")
        print(f"    Take 3: 0% contamination rate")
        print(f"    All cross-row entity references have been removed!")
    elif take3_rate < take1_rate * 0.2:
        reduction = ((take1_rate - take3_rate) / take1_rate) * 100
        print("✓✓ CONTAMINATION GREATLY REDUCED")
        print(f"    {reduction:.0f}% reduction from take 1 to take 3")
        print(f"    {take1_rate:.1%} → {take3_rate:.1%}")
    elif take3_rate < take1_rate * 0.5:
        reduction = ((take1_rate - take3_rate) / take1_rate) * 100
        print("✓ CONTAMINATION SIGNIFICANTLY REDUCED")
        print(f"    {reduction:.0f}% reduction from take 1 to take 3")
        print(f"    {take1_rate:.1%} → {take3_rate:.1%}")
    elif take3_rate < take1_rate:
        reduction = ((take1_rate - take3_rate) / take1_rate) * 100
        print("~ CONTAMINATION SLIGHTLY REDUCED")
        print(f"    {reduction:.0f}% reduction from take 1 to take 3")
        print(f"    {take1_rate:.1%} → {take3_rate:.1%}")
        print("    More work needed to reach target (<5% contamination)")
    elif take3_rate == take1_rate:
        print("✗ NO IMPROVEMENT")
        print(f"    Contamination rate unchanged at {take1_rate:.1%}")
    else:
        print("✗✗ CONTAMINATION INCREASED")
        print(f"    Contamination rate increased from {take1_rate:.1%} to {take3_rate:.1%}")

    # Show examples of contamination remaining in take 3
    if take3_rate > 0:
        print("\n" + "=" * 80)
        print("REMAINING CONTAMINATION EXAMPLES IN TAKE 3")
        print("=" * 80)

        examples_count = 0
        for row_result in take3_results['sampled_rows']:
            if row_result['contaminated_validations'] > 0 and examples_count < 3:
                print(f"\nRow {row_result['row_idx']}: {row_result['company']} / {row_result['product']}")
                print(f"  Contaminated: {row_result['contaminated_validations']}/{row_result['total_validations']} validations")

                for i, detail in enumerate(row_result['contamination_details'][:2]):
                    print(f"\n  Column: {detail['column']}")
                    if detail['foreign_companies']:
                        print(f"    Foreign Companies: {', '.join(detail['foreign_companies'])}")
                    if detail['foreign_products']:
                        print(f"    Foreign Products: {', '.join(detail['foreign_products'])}")
                    print(f"    Snippet: {detail['snippet'][:150]}...")

                examples_count += 1

    print()

def main():
    base_path = '/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator'
    take1_file = f'{base_path}/theranostic_CI_metadata.json'
    take2_file = f'{base_path}/theranostic_CI_metadata_take2.json'
    take3_file = f'{base_path}/theranostic_CI_metadata_take3.json'

    print("Analyzing TAKE 1 (original)...")
    take1_results = analyze_file_comprehensive(take1_file)

    print("\nAnalyzing TAKE 2 (first fix)...")
    # Use same sample indices for fair comparison
    take2_results = analyze_file_comprehensive(take2_file, sample_indices=take1_results['sample_indices'])

    print("\nAnalyzing TAKE 3 (latest - NEW ROWS)...")
    # Take 3 has entirely new rows, so analyze independently
    take3_results = analyze_file_comprehensive(take3_file)

    print("\n" + "=" * 80)
    print("NOTE: Take 3 contains entirely new rows, so row-by-row comparison is not applicable.")
    print("Comparison will focus on overall contamination rates only.")
    print("=" * 80)

    print_three_way_report(take1_results, take2_results, take3_results)

if __name__ == '__main__':
    main()
