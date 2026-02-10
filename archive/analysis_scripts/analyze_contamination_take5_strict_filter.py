#!/usr/bin/env python3
"""
Contamination analysis for Take 5 (Strict Memory Filtering)
Direct comparison with Take 4 to measure impact of strict row filtering.
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

    # Build sets of foreign entities
    foreign_companies = set()
    foreign_products = set()

    for comp in all_companies:
        comp_norm = normalize_name(comp)
        if comp_norm == current_company_norm:
            continue
        if current_company_norm and (comp_norm in current_company_norm or current_company_norm in comp_norm):
            continue
        foreign_companies.add(comp)

    for prod in all_products:
        prod_norm = normalize_name(prod)
        if prod_norm == current_product_norm:
            continue
        if current_product_norm and (prod_norm in current_product_norm or current_product_norm in prod_norm):
            continue
        foreign_products.add(prod)

    # Check all cells
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
                sources_text += f"{title} {snippet} ".lower()

        if not sources_text:
            continue

        # Check for foreign entity mentions
        found_foreign_companies = []
        found_foreign_products = []

        for foreign_comp in foreign_companies:
            if foreign_comp.lower() in sources_text:
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

def print_strict_filter_comparison(take4_results: Dict, take5_results: Dict):
    """Print comparison report focusing on strict filtering impact."""

    print("\n" + "=" * 80)
    print("STRICT MEMORY FILTERING IMPACT ANALYSIS")
    print("Take 4: Scoring Approach → Take 5: Strict Binary Filtering")
    print("=" * 80)
    print()

    print("CONFIGURATION")
    print("-" * 80)
    print("Take 4: Fresh memory + Scoring approach (row penalty -5)")
    print("Take 5: Fresh memory + STRICT filtering (different rows blocked)")
    print("Dataset: Take 4: 68 rows, Take 5: 71 rows (slightly larger)")
    print()

    print("OVERALL STATISTICS")
    print("-" * 80)
    print(f"Take 4 Sampled: {len(take4_results['sampled_rows'])} rows")
    print(f"Take 5 Sampled: {len(take5_results['sampled_rows'])} rows")
    print()

    # Take 4 stats
    print(f"TAKE 4 (Scoring Approach - Penalty for Different Rows):")
    print(f"  Total Validations: {take4_results['overall_stats']['total_validations']}")
    print(f"  Contaminated: {take4_results['overall_stats']['contaminated_validations']}")
    print(f"  Rows with Contamination: {take4_results['overall_stats']['rows_with_contamination']}/{len(take4_results['sampled_rows'])}")
    print(f"  Contamination Rate: {take4_results['overall_stats']['contamination_rate']:.1%}")
    print()

    # Take 5 stats
    print(f"TAKE 5 (Strict Filtering - Different Rows Blocked):")
    print(f"  Total Validations: {take5_results['overall_stats']['total_validations']}")
    print(f"  Contaminated: {take5_results['overall_stats']['contaminated_validations']}")
    print(f"  Rows with Contamination: {take5_results['overall_stats']['rows_with_contamination']}/{len(take5_results['sampled_rows'])}")
    print(f"  Contamination Rate: {take5_results['overall_stats']['contamination_rate']:.1%}")
    print()

    # Calculate improvement
    take4_rate = take4_results['overall_stats']['contamination_rate']
    take5_rate = take5_results['overall_stats']['contamination_rate']

    print("STRICT FILTERING IMPACT")
    print("-" * 80)
    if take4_rate > 0:
        reduction = ((take4_rate - take5_rate) / take4_rate) * 100
        abs_change = take4_rate - take5_rate
        print(f"Contamination Rate: {take4_rate:.1%} → {take5_rate:.1%}")
        print(f"Absolute Change: {abs_change:+.1%} ({abs_change*100:+.1f} percentage points)")
        print(f"Relative Improvement: {reduction:+.1f}%")
        print()

        if reduction > 50:
            print("✓✓✓ STRICT FILTERING DRAMATICALLY REDUCED CONTAMINATION")
        elif reduction > 30:
            print("✓✓ STRICT FILTERING SIGNIFICANTLY REDUCED CONTAMINATION")
        elif reduction > 10:
            print("✓ STRICT FILTERING REDUCED CONTAMINATION")
        elif reduction > 0:
            print("~ STRICT FILTERING SLIGHTLY REDUCED CONTAMINATION")
        elif reduction == 0:
            print("= STRICT FILTERING HAD NO EFFECT")
        else:
            print("✗ CONTAMINATION INCREASED")
    print()

    # Detailed comparison
    print("=" * 80)
    print("DETAILED CONTAMINATION BREAKDOWN")
    print("=" * 80)
    print()

    # Group by contamination level
    take4_clean = sum(1 for r in take4_results['sampled_rows'] if r['contaminated_validations'] == 0)
    take4_low = sum(1 for r in take4_results['sampled_rows'] if 0 < r['contaminated_validations'] <= 2)
    take4_med = sum(1 for r in take4_results['sampled_rows'] if 2 < r['contaminated_validations'] <= 5)
    take4_high = sum(1 for r in take4_results['sampled_rows'] if r['contaminated_validations'] > 5)

    take5_clean = sum(1 for r in take5_results['sampled_rows'] if r['contaminated_validations'] == 0)
    take5_low = sum(1 for r in take5_results['sampled_rows'] if 0 < r['contaminated_validations'] <= 2)
    take5_med = sum(1 for r in take5_results['sampled_rows'] if 2 < r['contaminated_validations'] <= 5)
    take5_high = sum(1 for r in take5_results['sampled_rows'] if r['contaminated_validations'] > 5)

    print("Contamination Distribution:")
    print(f"  Clean (0):        T4: {take4_clean}/10 ({take4_clean*10}%)  →  T5: {take5_clean}/10 ({take5_clean*10}%)")
    print(f"  Low (1-2):        T4: {take4_low}/10 ({take4_low*10}%)  →  T5: {take5_low}/10 ({take5_low*10}%)")
    print(f"  Moderate (3-5):   T4: {take4_med}/10 ({take4_med*10}%)  →  T5: {take5_med}/10 ({take5_med*10}%)")
    print(f"  High (6+):        T4: {take4_high}/10 ({take4_high*10}%)  →  T5: {take5_high}/10 ({take5_high*10}%)")
    print()

    # Show Take 5 results
    print("=" * 80)
    print("TAKE 5 CONTAMINATION STATUS (Strict Filtering)")
    print("=" * 80)

    for take5_row in take5_results['sampled_rows']:
        print(f"\nRow {take5_row['row_idx']}: {take5_row['company']} / {take5_row['product']}")
        take5_cont = take5_row['contaminated_validations']
        take5_total = take5_row['total_validations']

        if take5_total > 0:
            pct = 100*take5_cont/take5_total
            print(f"  Contaminated: {take5_cont}/{take5_total} ({pct:.0f}%)")
        else:
            print(f"  Contaminated: {take5_cont}/{take5_total}")

        if take5_cont == 0:
            print(f"  ✓✓ CLEAN - No contamination")
        elif take5_cont <= 2:
            print(f"  ✓ LOW - Minimal contamination")
        elif take5_cont <= 5:
            print(f"  ~ MODERATE - Some contamination remains")
        else:
            print(f"  ✗ HIGH - Significant contamination")

        # Show contamination examples
        if take5_cont > 0 and take5_row['contamination_details']:
            detail = take5_row['contamination_details'][0]
            if detail['foreign_companies']:
                print(f"    Foreign companies: {', '.join(detail['foreign_companies'][:2])}")
            if detail['foreign_products']:
                print(f"    Foreign products: {', '.join(detail['foreign_products'][:2])}")

    # Final verdict
    print("\n" + "=" * 80)
    print("FINAL VERDICT ON STRICT FILTERING")
    print("=" * 80)
    print()

    if take5_rate == 0 and take4_rate > 0:
        print("✓✓✓ CONTAMINATION ELIMINATED")
        print(f"    Take 4: {take4_rate:.1%}")
        print(f"    Take 5: 0%")
        print(f"    Strict filtering eliminated ALL cross-row contamination!")
    elif take5_rate < take4_rate * 0.5:
        reduction = ((take4_rate - take5_rate) / take4_rate) * 100
        print("✓✓ STRICT FILTERING HIGHLY EFFECTIVE")
        print(f"    {reduction:.0f}% reduction ({take4_rate:.1%} → {take5_rate:.1%})")
        print(f"    Multi-product contamination greatly reduced")
    elif take5_rate < take4_rate:
        reduction = ((take4_rate - take5_rate) / take4_rate) * 100
        print("✓ STRICT FILTERING EFFECTIVE")
        print(f"    {reduction:.0f}% reduction ({take4_rate:.1%} → {take5_rate:.1%})")
    elif take5_rate == take4_rate:
        print("= NO CHANGE")
        print(f"    Contamination unchanged at {take4_rate:.1%}")
    else:
        print("✗ CONTAMINATION INCREASED")
        print(f"    {take4_rate:.1%} → {take5_rate:.1%}")

    print()
    print("PROGRESS TOWARD <5% TARGET:")
    remaining = take5_rate * 100
    target_gap = remaining - 5
    if remaining <= 5:
        print(f"  ✓✓✓ TARGET ACHIEVED! ({remaining:.1f}% ≤ 5%)")
    elif remaining <= 10:
        print(f"  ✓✓ CLOSE TO TARGET ({remaining:.1f}%, gap: {target_gap:.1f} pp)")
    elif remaining <= 15:
        print(f"  ✓ GOOD PROGRESS ({remaining:.1f}%, gap: {target_gap:.1f} pp)")
    elif remaining <= 20:
        print(f"  ~ MODERATE PROGRESS ({remaining:.1f}%, gap: {target_gap:.1f} pp)")
    else:
        print(f"  More work needed ({remaining:.1f}%, gap: {target_gap:.1f} pp)")

    print()

def main():
    base_path = '/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator'
    take4_file = f'{base_path}/theranostic_CI_metadata_take4.json'
    take5_file = f'{base_path}/theranostic_CI_metadata_take5.json'

    print("Analyzing TAKE 4 (Scoring Approach)...")
    take4_results = analyze_file_comprehensive(take4_file)

    print("\nAnalyzing TAKE 5 (Strict Filtering)...")
    take5_results = analyze_file_comprehensive(take5_file)

    print_strict_filter_comparison(take4_results, take5_results)

if __name__ == '__main__':
    main()
