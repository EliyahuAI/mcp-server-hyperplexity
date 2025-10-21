#!/usr/bin/env python3
"""
Row Consolidator Demo - Example usage and benchmarks
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from row_consolidator import RowConsolidator


def demo_basic_consolidation():
    """Demonstrate basic consolidation with fuzzy matching."""
    print("\n" + "=" * 70)
    print("DEMO 1: Basic Consolidation with Fuzzy Matching")
    print("=" * 70)

    # Simulate results from 3 parallel discovery streams
    stream_results = [
        {
            "subdomain": "AI Research Companies",
            "candidates": [
                {
                    "id_values": {"Company Name": "Anthropic", "Website": "anthropic.com"},
                    "match_score": 0.95,
                    "match_rationale": "Leading AI safety research company",
                    "source_urls": ["https://anthropic.com/research"]
                },
                {
                    "id_values": {"Company Name": "OpenAI", "Website": "openai.com"},
                    "match_score": 0.93,
                    "match_rationale": "AI research and deployment company",
                    "source_urls": ["https://openai.com/research"]
                }
            ]
        },
        {
            "subdomain": "Healthcare AI",
            "candidates": [
                {
                    "id_values": {"Company Name": "Anthropic Inc.", "Website": "anthropic.com"},
                    "match_score": 0.88,
                    "match_rationale": "AI safety applications in healthcare",
                    "source_urls": ["https://anthropic.com/healthcare"]
                },
                {
                    "id_values": {"Company Name": "Tempus", "Website": "tempus.com"},
                    "match_score": 0.90,
                    "match_rationale": "Precision medicine AI platform",
                    "source_urls": ["https://tempus.com"]
                }
            ]
        },
        {
            "subdomain": "Enterprise AI",
            "candidates": [
                {
                    "id_values": {"Company Name": "Anthropic PBC", "Website": "anthropic.com"},
                    "match_score": 0.91,
                    "match_rationale": "Enterprise AI safety solutions",
                    "source_urls": ["https://anthropic.com/enterprise"]
                },
                {
                    "id_values": {"Company Name": "Cohere", "Website": "cohere.ai"},
                    "match_score": 0.87,
                    "match_rationale": "Enterprise NLP platform",
                    "source_urls": ["https://cohere.ai"]
                }
            ]
        }
    ]

    # Create consolidator and process
    consolidator = RowConsolidator(fuzzy_similarity_threshold=0.85)
    result = consolidator.consolidate(
        stream_results,
        target_row_count=10,
        min_match_score=0.6
    )

    # Display results
    print(consolidator.get_consolidation_summary(result))

    print("\nDetailed Results:")
    for i, row in enumerate(result['final_rows'], 1):
        print(f"\n{i}. {row['id_values']['Company Name']}")
        print(f"   Score: {row['match_score']:.2f}")
        print(f"   Sources: {len(row['source_urls'])} URL(s)")
        if len(row['merged_from_streams']) > 1:
            print(f"   Merged from: {', '.join(row['merged_from_streams'])}")


def demo_threshold_comparison():
    """Demonstrate different fuzzy matching thresholds."""
    print("\n" + "=" * 70)
    print("DEMO 2: Fuzzy Matching Threshold Comparison")
    print("=" * 70)

    # Test data with similar company names
    stream_results = [
        {
            "subdomain": "Test",
            "candidates": [
                {
                    "id_values": {"Company Name": "Anthropic"},
                    "match_score": 0.95,
                    "match_rationale": "Base",
                    "source_urls": ["https://anthropic.com"]
                },
                {
                    "id_values": {"Company Name": "Anthropic Inc"},
                    "match_score": 0.90,
                    "match_rationale": "Variant 1",
                    "source_urls": ["https://anthropic1.com"]
                },
                {
                    "id_values": {"Company Name": "Anthropic PBC"},
                    "match_score": 0.88,
                    "match_rationale": "Variant 2",
                    "source_urls": ["https://anthropic2.com"]
                },
                {
                    "id_values": {"Company Name": "Anthropic Corporation"},
                    "match_score": 0.85,
                    "match_rationale": "Variant 3",
                    "source_urls": ["https://anthropic3.com"]
                }
            ]
        }
    ]

    # Test with different thresholds
    thresholds = [0.70, 0.85, 0.95]

    for threshold in thresholds:
        consolidator = RowConsolidator(fuzzy_similarity_threshold=threshold)
        result = consolidator.consolidate(stream_results, target_row_count=20)

        print(f"\nThreshold: {threshold}")
        print(f"  Total candidates: {result['stats']['total_candidates']}")
        print(f"  Duplicates merged: {result['stats']['duplicates_removed']}")
        print(f"  Final unique: {result['stats']['final_count']}")


def demo_performance_benchmark():
    """Benchmark consolidation performance."""
    print("\n" + "=" * 70)
    print("DEMO 3: Performance Benchmark")
    print("=" * 70)

    import time

    # Generate test data of varying sizes
    sizes = [10, 50, 100, 200]

    for size in sizes:
        # Generate test candidates
        candidates = []
        for i in range(size):
            candidates.append({
                "id_values": {"Company Name": f"Company{i:04d}", "Website": f"company{i}.com"},
                "match_score": 0.95 - (i * 0.001),
                "match_rationale": f"Test company {i}",
                "source_urls": [f"https://company{i}.com"]
            })

        stream_results = [{"subdomain": "Test", "candidates": candidates}]

        # Benchmark
        consolidator = RowConsolidator()
        start = time.time()
        result = consolidator.consolidate(stream_results, target_row_count=20)
        elapsed = time.time() - start

        print(f"\nCandidates: {size}")
        print(f"  Processing time: {elapsed*1000:.2f}ms")
        print(f"  Throughput: {size/elapsed:.0f} candidates/second")
        print(f"  Final rows: {result['stats']['final_count']}")


def demo_edge_cases():
    """Demonstrate handling of edge cases."""
    print("\n" + "=" * 70)
    print("DEMO 4: Edge Case Handling")
    print("=" * 70)

    consolidator = RowConsolidator()

    # Edge case 1: Empty results
    print("\nCase 1: Empty stream results")
    result = consolidator.consolidate([], target_row_count=20)
    print(f"  Result: {result['stats']['final_count']} rows")

    # Edge case 2: All below threshold
    print("\nCase 2: All candidates below score threshold")
    low_score_results = [
        {
            "subdomain": "Test",
            "candidates": [
                {
                    "id_values": {"Company Name": "LowScore1"},
                    "match_score": 0.45,
                    "match_rationale": "Low quality",
                    "source_urls": ["https://test.com"]
                }
            ]
        }
    ]
    result = consolidator.consolidate(low_score_results, min_match_score=0.8)
    print(f"  Candidates: 1")
    print(f"  Below threshold: {result['stats']['below_threshold']}")
    print(f"  Final rows: {result['stats']['final_count']}")

    # Edge case 3: Request more rows than available
    print("\nCase 3: Request 100 rows but only 3 available")
    small_results = [
        {
            "subdomain": "Test",
            "candidates": [
                {"id_values": {"Company Name": f"Company{i}"}, "match_score": 0.9, "match_rationale": "Test", "source_urls": [""]}
                for i in range(3)
            ]
        }
    ]
    result = consolidator.consolidate(small_results, target_row_count=100)
    print(f"  Requested: 100")
    print(f"  Returned: {result['stats']['final_count']}")


if __name__ == "__main__":
    print("\nRow Consolidator Demonstration")
    print("=" * 70)

    demo_basic_consolidation()
    demo_threshold_comparison()
    demo_performance_benchmark()
    demo_edge_cases()

    print("\n" + "=" * 70)
    print("All demos complete!")
    print("=" * 70 + "\n")
