#!/usr/bin/env python3
"""
Contamination analysis for Take 4 (QC model upgrade: DeepSeek V3.2 → Sonnet 4.5)
Direct comparison with Take 3 using same dataset.
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

def print_qc_comparison_report(take3_results: Dict, take4_results: Dict):
    """Print comparison report focusing on QC model upgrade impact."""

    print("\n" + "=" * 80)
    print("QC MODEL UPGRADE IMPACT ANALYSIS")
    print("Take 3: DeepSeek V3.2 QC → Take 4: Claude Sonnet 4.5 QC")
    print("=" * 80)
    print()

    print("CONFIGURATION")
    print("-" * 80)
    print("Take 3: Fresh memory + DeepSeek V3.2 for QC")
    print("Take 4: Fresh memory + Claude Sonnet 4.5 for QC")
    print("Dataset: Same 68 rows (direct comparison)")
    print()

    print("OVERALL STATISTICS")
    print("-" * 80)
    print(f"Sampled Rows: {len(take3_results['sampled_rows'])}")
    print()

    # Take 3 stats
    print(f"TAKE 3 (DeepSeek V3.2 QC):")
    print(f"  Total Validations Checked: {take3_results['overall_stats']['total_validations']}")
    print(f"  Contaminated Validations: {take3_results['overall_stats']['contaminated_validations']}")
    print(f"  Rows with Contamination: {take3_results['overall_stats']['rows_with_contamination']}/{len(take3_results['sampled_rows'])}")
    print(f"  Contamination Rate: {take3_results['overall_stats']['contamination_rate']:.1%}")
    print()

    # Take 4 stats
    print(f"TAKE 4 (Sonnet 4.5 QC):")
    print(f"  Total Validations Checked: {take4_results['overall_stats']['total_validations']}")
    print(f"  Contaminated Validations: {take4_results['overall_stats']['contaminated_validations']}")
    print(f"  Rows with Contamination: {take4_results['overall_stats']['rows_with_contamination']}/{len(take4_results['sampled_rows'])}")
    print(f"  Contamination Rate: {take4_results['overall_stats']['contamination_rate']:.1%}")
    print()

    # Calculate improvement
    take3_rate = take3_results['overall_stats']['contamination_rate']
    take4_rate = take4_results['overall_stats']['contamination_rate']

    print("QC MODEL UPGRADE IMPACT")
    print("-" * 80)
    if take3_rate > 0:
        reduction = ((take3_rate - take4_rate) / take3_rate) * 100
        abs_change = take3_rate - take4_rate
        print(f"Contamination Rate Change: {take3_rate:.1%} → {take4_rate:.1%}")
        print(f"Absolute Change: {abs_change:+.1%} ({abs_change*100:+.1f} percentage points)")
        print(f"Relative Improvement: {reduction:+.1f}%")

        if reduction > 0:
            print(f"✓ QC model upgrade REDUCED contamination")
        elif reduction < 0:
            print(f"✗ QC model upgrade INCREASED contamination")
        else:
            print(f"= QC model upgrade had NO EFFECT on contamination")
    print()

    # Row-by-row comparison
    print("=" * 80)
    print("ROW-BY-ROW COMPARISON (Same Dataset)")
    print("=" * 80)

    improved = 0
    worsened = 0
    unchanged = 0
    clean_both = 0

    for take3_row in take3_results['sampled_rows']:
        take4_row = next(
            (r for r in take4_results['sampled_rows'] if r['row_idx'] == take3_row['row_idx']),
            None
        )

        if take4_row:
            print(f"\nRow {take3_row['row_idx']}: {take3_row['company']} / {take3_row['product']}")

            take3_cont = take3_row['contaminated_validations']
            take3_total = take3_row['total_validations']
            take4_cont = take4_row['contaminated_validations']
            take4_total = take4_row['total_validations']

            print(f"  DeepSeek QC: {take3_cont}/{take3_total} contaminated ({100*take3_cont/take3_total if take3_total > 0 else 0:.0f}%)")
            print(f"  Sonnet QC:   {take4_cont}/{take4_total} contaminated ({100*take4_cont/take4_total if take4_total > 0 else 0:.0f}%)")

            # Status determination
            if take4_cont == 0 and take3_cont > 0:
                print(f"  ✓✓ CLEANED: Contamination eliminated with Sonnet QC")
                improved += 1
            elif take4_cont < take3_cont:
                print(f"  ✓ IMPROVED: Reduced from {take3_cont} to {take4_cont}")
                improved += 1
            elif take4_cont > take3_cont:
                print(f"  ✗ WORSENED: Increased from {take3_cont} to {take4_cont}")
                worsened += 1
            elif take4_cont == 0:
                print(f"  ✓ CLEAN: No contamination in either version")
                clean_both += 1
                unchanged += 1
            else:
                print(f"  = NO CHANGE: {take3_cont} contaminated in both")
                unchanged += 1

    # Summary stats
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    print(f"Rows Improved: {improved}")
    print(f"Rows Worsened: {worsened}")
    print(f"Rows Unchanged: {unchanged}")
    print(f"Rows Clean in Both: {clean_both}")
    print()

    # Show examples of changes
    if improved > 0:
        print("=" * 80)
        print("EXAMPLES OF IMPROVEMENT WITH SONNET QC")
        print("=" * 80)

        examples_shown = 0
        for take3_row in take3_results['sampled_rows']:
            take4_row = next(
                (r for r in take4_results['sampled_rows'] if r['row_idx'] == take3_row['row_idx']),
                None
            )

            if take4_row and take4_row['contaminated_validations'] < take3_row['contaminated_validations']:
                if examples_shown < 3:
                    print(f"\nRow {take3_row['row_idx']}: {take3_row['company']} / {take3_row['product']}")
                    print(f"  Contamination: {take3_row['contaminated_validations']} → {take4_row['contaminated_validations']}")

                    # Show what was cleaned
                    take3_cols = set(d['column'] for d in take3_row['contamination_details'])
                    take4_cols = set(d['column'] for d in take4_row['contamination_details'])
                    cleaned_cols = take3_cols - take4_cols

                    if cleaned_cols:
                        print(f"  Cleaned columns: {', '.join(list(cleaned_cols)[:3])}")

                    examples_shown += 1

    if worsened > 0:
        print("\n" + "=" * 80)
        print("EXAMPLES OF WORSENING WITH SONNET QC")
        print("=" * 80)

        examples_shown = 0
        for take3_row in take3_results['sampled_rows']:
            take4_row = next(
                (r for r in take4_results['sampled_rows'] if r['row_idx'] == take3_row['row_idx']),
                None
            )

            if take4_row and take4_row['contaminated_validations'] > take3_row['contaminated_validations']:
                if examples_shown < 3:
                    print(f"\nRow {take3_row['row_idx']}: {take3_row['company']} / {take3_row['product']}")
                    print(f"  Contamination: {take3_row['contaminated_validations']} → {take4_row['contaminated_validations']}")

                    # Show what got worse
                    take3_cols = set(d['column'] for d in take3_row['contamination_details'])
                    take4_cols = set(d['column'] for d in take4_row['contamination_details'])
                    new_contaminated_cols = take4_cols - take3_cols

                    if new_contaminated_cols:
                        print(f"  New contaminated columns: {', '.join(list(new_contaminated_cols)[:3])}")

                    examples_shown += 1

    # Final verdict
    print("\n" + "=" * 80)
    print("FINAL VERDICT ON QC MODEL UPGRADE")
    print("=" * 80)
    print()

    if take4_rate == 0 and take3_rate > 0:
        print("✓✓✓ QC MODEL UPGRADE ELIMINATED ALL CONTAMINATION")
        print(f"    DeepSeek V3.2: {take3_rate:.1%} contamination")
        print(f"    Sonnet 4.5: 0% contamination")
    elif take4_rate < take3_rate * 0.5:
        reduction = ((take3_rate - take4_rate) / take3_rate) * 100
        print("✓✓ QC MODEL UPGRADE SIGNIFICANTLY REDUCED CONTAMINATION")
        print(f"    {reduction:.0f}% reduction ({take3_rate:.1%} → {take4_rate:.1%})")
    elif take4_rate < take3_rate:
        reduction = ((take3_rate - take4_rate) / take3_rate) * 100
        print("✓ QC MODEL UPGRADE REDUCED CONTAMINATION")
        print(f"    {reduction:.0f}% reduction ({take3_rate:.1%} → {take4_rate:.1%})")
    elif take4_rate == take3_rate:
        print("= QC MODEL UPGRADE HAD NO EFFECT")
        print(f"    Contamination unchanged at {take3_rate:.1%}")
        print("    QC model choice does not appear to impact contamination")
    else:
        increase = ((take4_rate - take3_rate) / take3_rate) * 100
        print("✗ QC MODEL UPGRADE INCREASED CONTAMINATION")
        print(f"    {increase:.0f}% increase ({take3_rate:.1%} → {take4_rate:.1%})")

    print()
    print("INTERPRETATION:")
    if abs(take4_rate - take3_rate) < 0.01:  # Less than 1 percentage point difference
        print("  The QC model (DeepSeek vs Sonnet) has minimal impact on contamination.")
        print("  Contamination is primarily a memory/filtering issue, not a QC issue.")
    else:
        if take4_rate < take3_rate:
            print("  Sonnet 4.5 QC appears to better filter or correct contaminated sources.")
        else:
            print("  Sonnet 4.5 QC may be introducing different sources or validation patterns.")
        print("  Further investigation recommended to understand the mechanism.")

    print()

def main():
    base_path = '/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator'
    take3_file = f'{base_path}/theranostic_CI_metadata_take3.json'
    take4_file = f'{base_path}/theranostic_CI_metadata_take4.json'

    print("Analyzing TAKE 3 (DeepSeek V3.2 QC)...")
    take3_results = analyze_file_comprehensive(take3_file)

    print("\nAnalyzing TAKE 4 (Sonnet 4.5 QC)...")
    # Use same sample indices for fair comparison
    take4_results = analyze_file_comprehensive(take4_file, sample_indices=take3_results['sample_indices'])

    print_qc_comparison_report(take3_results, take4_results)

if __name__ == '__main__':
    main()
