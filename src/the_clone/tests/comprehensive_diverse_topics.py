#!/usr/bin/env python.exe
"""
Comprehensive test across diverse topics (non-ML).
Tests all strategies with parallel system comparison per query.
"""
import os
import sys
import asyncio
import json
import time
from datetime import datetime

# Set environment
os.environ['GOOGLE_CLOUD_PROJECT'] = 'gen-lang-client-0650358146'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'C:\Users\ellio\OneDrive - Eliyahu.AI\Desktop\src\other\gen-lang-client-0650358146-897394b730e6.json'
os.environ['PERPLEXITY_API_KEY'] = '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'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from the_clone.the_clone import TheClone2Refined as TheClone
from shared.ai_api_client import AIAPIClient


# Diverse test queries across different topics
TEST_QUERIES = [
    {
        "category": "Business/Finance",
        "name": "Targeted - Stock Price",
        "query": "What is the current market cap of NVIDIA?",
        "expected_strategy": "targeted",
        "schema": {
            "type": "object",
            "properties": {
                "market_cap": {"type": "string"},
                "date": {"type": "string"}
            }
        }
    },
    {
        "category": "Geography",
        "name": "Targeted - Population",
        "query": "What is the population of Tokyo in 2025?",
        "expected_strategy": "targeted",
        "schema": {
            "type": "object",
            "properties": {
                "population": {"type": "string"},
                "year": {"type": "string"}
            }
        }
    },
    {
        "category": "Technology",
        "name": "Survey - Smartphone Features",
        "query": "What are the key features of the iPhone 16 Pro?",
        "expected_strategy": "survey",
        "schema": {
            "type": "object",
            "properties": {
                "features": {"type": "object"}
            }
        }
    },
    {
        "category": "Science",
        "name": "Survey - Planetary Data",
        "query": "List the main characteristics of Jupiter's moons",
        "expected_strategy": "survey",
        "schema": {
            "type": "object",
            "properties": {
                "moons": {"type": "object"}
            }
        }
    },
    {
        "category": "History",
        "name": "Focused Deep - Historical Event",
        "query": "Explain the causes and significance of the 2008 financial crisis",
        "expected_strategy": "focused_deep",
        "schema": {
            "type": "object",
            "properties": {
                "causes": {"type": "string"},
                "significance": {"type": "string"},
                "timeline": {"type": "string"}
            }
        }
    },
    {
        "category": "Climate/Environment",
        "name": "Comprehensive - Climate Analysis",
        "query": "Provide a comprehensive analysis of renewable energy adoption trends in 2024-2025 including solar, wind, and battery storage growth, policy changes, and economic impacts",
        "expected_strategy": "comprehensive",
        "schema": {
            "type": "object",
            "properties": {
                "solar_trends": {"type": "string"},
                "wind_trends": {"type": "string"},
                "battery_storage": {"type": "string"},
                "policy_changes": {"type": "string"},
                "economic_impact": {"type": "string"}
            }
        }
    },
    {
        "category": "Sports",
        "name": "Targeted - Championship Winner",
        "query": "Who won the 2024 NBA Championship?",
        "expected_strategy": "targeted",
        "schema": {
            "type": "object",
            "properties": {
                "winner": {"type": "string"},
                "year": {"type": "string"}
            }
        }
    },
    {
        "category": "Medicine/Health",
        "name": "Survey - Drug Information",
        "query": "What are the main uses and side effects of Ozempic?",
        "expected_strategy": "survey",
        "schema": {
            "type": "object",
            "properties": {
                "uses": {"type": "object"},
                "side_effects": {"type": "array", "items": {"type": "string"}}
            }
        }
    }
]


async def test_system(system_name: str, query: str, schema: dict):
    """Test a single system and return results."""
    start = time.time()

    try:
        if "sonar" in system_name.lower():
            client = AIAPIClient()
            model = "sonar-pro" if "pro" in system_name.lower() else "sonar"

            result = await client.call_structured_api(
                prompt=query,
                schema=schema,
                model=model,
                search_context_size="high",
                use_cache=False
            )

            elapsed = time.time() - start
            response = result.get('response', result)
            if 'choices' in response:
                content = response['choices'][0]['message']['content']
                answer = json.loads(content) if isinstance(content, str) else content
            else:
                answer = response

            enhanced = result.get('enhanced_data', {})
            cost = enhanced.get('costs', {}).get('actual', {}).get('total_cost', 0)

            return {
                "system": system_name,
                "time": round(elapsed, 2),
                "cost": cost,
                "citations": len(result.get('citations', [])),
                "status": "SUCCESS"
            }

        elif "claude web" in system_name.lower():
            client = AIAPIClient()
            result = await client.call_structured_api(
                prompt=query,
                schema=schema,
                model="claude-sonnet-4-5",
                max_web_searches=3,
                use_cache=False
            )

            elapsed = time.time() - start
            response = result.get('response', result)
            if 'choices' in response:
                content = response['choices'][0]['message']['content']
                answer = json.loads(content) if isinstance(content, str) else content
            else:
                answer = response

            enhanced = result.get('enhanced_data', {})
            cost = enhanced.get('costs', {}).get('actual', {}).get('total_cost', 0)

            return {
                "system": system_name,
                "time": round(elapsed, 2),
                "cost": cost,
                "citations": len(result.get('citations', [])),
                "status": "SUCCESS"
            }

        else:  # The Clone
            clone = TheClone()
            result = await clone.query(prompt=query, schema=schema)

            elapsed = time.time() - start
            metadata = result['metadata']

            return {
                "system": system_name,
                "time": round(elapsed, 2),
                "cost": metadata['total_cost'],
                "citations": metadata['citations_count'],
                "snippets": metadata['total_snippets'],
                "strategy": metadata.get('strategy'),
                "breadth": metadata.get('breadth'),
                "depth": metadata.get('depth'),
                "sources": metadata.get('sources_pulled'),
                "status": "SUCCESS"
            }

    except Exception as e:
        elapsed = time.time() - start
        return {
            "system": system_name,
            "time": round(elapsed, 2),
            "error": str(e)[:100],
            "status": "ERROR"
        }


async def run_query_test(test_case: dict, test_num: int, total: int):
    """Run all systems on one query in parallel."""
    print(f"\n{'='*80}")
    print(f"TEST {test_num}/{total}: {test_case['name']} ({test_case['category']})")
    print(f"{'='*80}")
    print(f"Query: {test_case['query']}")
    print(f"Expected: {test_case['expected_strategy']}")
    print(f"\nRunning 4 systems in parallel...")
    print('-'*80)

    # Run all systems in parallel
    results = await asyncio.gather(
        test_system("Sonar", test_case['query'], test_case['schema']),
        test_system("Sonar Pro", test_case['query'], test_case['schema']),
        test_system("Claude Web (3)", test_case['query'], test_case['schema']),
        test_system("The Clone", test_case['query'], test_case['schema']),
        return_exceptions=True
    )

    # Process results
    processed = []
    for r in results:
        if isinstance(r, Exception):
            processed.append({"system": "Unknown", "status": "ERROR", "error": str(r)[:100]})
        else:
            processed.append(r)

    # Display
    print(f"\n{'System':<20} {'Time':>8} {'Cost':>10} {'Cites':>7} {'Status':>10}")
    print('-'*80)
    for r in processed:
        if r['status'] == 'ERROR':
            print(f"{r['system']:<20} ERROR: {r.get('error', '')[:40]}")
        else:
            print(f"{r['system']:<20} {r['time']:>7.1f}s ${r['cost']:>8.4f} {r.get('citations', 0):>7} {r['status']:>10}")
            if 'strategy' in r:
                match = "OK" if r['strategy'] == test_case['expected_strategy'] else "MISMATCH"
                print(f"  > Strategy: {r['strategy']} ({match}), Sources: {r.get('sources', 0)}, Snippets: {r.get('snippets', 0)}")

    return {
        "category": test_case['category'],
        "test_name": test_case['name'],
        "query": test_case['query'],
        "expected_strategy": test_case['expected_strategy'],
        "results": processed
    }


def generate_meta_report(all_test_results: list, output_file: str):
    """Generate meta report across all tests."""
    with open(output_file, 'w') as f:
        f.write("# Comprehensive Multi-Topic Test Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Total Tests:** {len(all_test_results)}\n\n")
        f.write("="*80 + "\n\n")

        # Summary table
        f.write("## Overall Performance Summary\n\n")
        f.write("| System | Avg Time | Avg Cost | Avg Citations | Success Rate |\n")
        f.write("|--------|----------|----------|---------------|-------------|\n")

        systems = ["Sonar", "Sonar Pro", "Claude Web (3)", "The Clone"]
        for system in systems:
            system_results = []
            for test in all_test_results:
                sys_result = next((r for r in test['results'] if system.lower() in r['system'].lower()), None)
                if sys_result and sys_result['status'] == 'SUCCESS':
                    system_results.append(sys_result)

            if system_results:
                avg_time = sum(r['time'] for r in system_results) / len(system_results)
                avg_cost = sum(r['cost'] for r in system_results) / len(system_results)
                avg_cites = sum(r.get('citations', 0) for r in system_results) / len(system_results)
                success_rate = f"{len(system_results)}/{len(all_test_results)}"

                f.write(f"| {system} | {avg_time:.1f}s | ${avg_cost:.4f} | {avg_cites:.1f} | {success_rate} |\n")

        f.write("\n---\n\n")

        # Per-test details
        f.write("## Test Details\n\n")
        for i, test in enumerate(all_test_results, 1):
            f.write(f"### Test {i}: {test['test_name']} ({test['category']})\n\n")
            f.write(f"**Query:** {test['query']}\n\n")
            f.write(f"**Expected Strategy:** {test['expected_strategy']}\n\n")

            f.write("| System | Time | Cost | Citations | Status |\n")
            f.write("|--------|------|------|-----------|--------|\n")

            for r in test['results']:
                if r['status'] == 'ERROR':
                    f.write(f"| {r['system']} | - | - | - | ERROR |\n")
                else:
                    f.write(f"| {r['system']} | {r['time']:.1f}s | ${r['cost']:.4f} | {r.get('citations', 0)} | {r['status']} |\n")

            # Show Clone strategy
            clone_result = next((r for r in test['results'] if 'clone' in r['system'].lower()), None)
            if clone_result and clone_result['status'] == 'SUCCESS':
                f.write(f"\n**The Clone Strategy:** {clone_result.get('strategy')} ")
                if clone_result.get('strategy') == test['expected_strategy']:
                    f.write("(Correct)\n")
                else:
                    f.write(f"(Expected: {test['expected_strategy']})\n")
                f.write(f"- Sources: {clone_result.get('sources', 0)}\n")
                f.write(f"- Snippets: {clone_result.get('snippets', 0)}\n")
                f.write(f"- Breadth x Depth: {clone_result.get('breadth')} x {clone_result.get('depth')}\n")

            f.write("\n---\n\n")

        # Strategy performance breakdown
        f.write("## Strategy Performance (The Clone)\n\n")
        f.write("| Strategy | Tests | Avg Cost | Avg Time | Avg Snippets |\n")
        f.write("|----------|-------|----------|----------|-------------|\n")

        strategies_seen = {}
        for test in all_test_results:
            clone_r = next((r for r in test['results'] if 'clone' in r['system'].lower()), None)
            if clone_r and clone_r['status'] == 'SUCCESS':
                strat = clone_r.get('strategy', 'unknown')
                if strat not in strategies_seen:
                    strategies_seen[strat] = []
                strategies_seen[strat].append(clone_r)

        for strat, results in strategies_seen.items():
            avg_cost = sum(r['cost'] for r in results) / len(results)
            avg_time = sum(r['time'] for r in results) / len(results)
            avg_snippets = sum(r.get('snippets', 0) for r in results) / len(results)
            f.write(f"| {strat} | {len(results)} | ${avg_cost:.4f} | {avg_time:.1f}s | {avg_snippets:.0f} |\n")

        f.write("\n")


async def main():
    """Run comprehensive test across diverse topics."""
    print("="*80)
    print("COMPREHENSIVE DIVERSE TOPICS TEST")
    print(f"Testing {len(TEST_QUERIES)} queries across varied domains")
    print("="*80)

    all_results = []

    for i, test_case in enumerate(TEST_QUERIES, 1):
        result = await run_query_test(test_case, i, len(TEST_QUERIES))
        all_results.append(result)

    # Generate meta report
    output_dir = os.path.join(os.path.dirname(__file__), '../test_results/diverse_topics')
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Save JSON
    json_file = os.path.join(output_dir, f'results_{timestamp}.json')
    with open(json_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    # Generate markdown report
    report_file = os.path.join(output_dir, f'report_{timestamp}.md')
    generate_meta_report(all_results, report_file)

    # Final summary
    print(f"\n{'='*80}")
    print("META SUMMARY")
    print('='*80)

    # Calculate averages per system
    systems = {}
    for test in all_results:
        for result in test['results']:
            if result['status'] == 'SUCCESS':
                sys_name = result['system']
                if sys_name not in systems:
                    systems[sys_name] = {'times': [], 'costs': [], 'citations': []}
                systems[sys_name]['times'].append(result['time'])
                systems[sys_name]['costs'].append(result['cost'])
                systems[sys_name]['citations'].append(result.get('citations', 0))

    print(f"\n{'System':<20} {'Avg Time':>10} {'Avg Cost':>12} {'Avg Citations':>15} {'Tests':>8}")
    print('-'*80)
    for sys_name, data in systems.items():
        avg_time = sum(data['times']) / len(data['times'])
        avg_cost = sum(data['costs']) / len(data['costs'])
        avg_cites = sum(data['citations']) / len(data['citations'])
        print(f"{sys_name:<20} {avg_time:>9.1f}s ${avg_cost:>10.4f} {avg_cites:>15.1f} {len(data['times']):>8}")

    print(f"\nJSON: {json_file}")
    print(f"Report: {report_file}")


if __name__ == "__main__":
    asyncio.run(main())
