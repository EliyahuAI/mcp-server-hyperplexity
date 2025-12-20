#!/usr/bin/env python.exe
"""
Comparison Test: Sonar Pro vs Claude Web Search vs The Clone (Baseten)
Tests multiple queries at each complexity level with schema validation.
Saves one file per question with all model responses.
"""
import os
import sys
import asyncio
import json
import time
from datetime import datetime
from jsonschema import validate, ValidationError

# Set environment variables
os.environ['GOOGLE_CLOUD_PROJECT'] = 'gen-lang-client-0650358146'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'C:\Users\ellio\OneDrive - Eliyahu.AI\Desktop\src\other\gen-lang-client-0650358146-897394b730e6.json'
os.environ['PERPLEXITY_API_KEY'] = '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'

# Add parent to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '../..'))
sys.path.insert(0, parent_dir)

from the_clone.the_clone import TheClone2Refined as TheClone
from shared.ai_api_client import AIAPIClient

# Test queries with schemas - multiple per complexity level
TEST_QUERIES = [
    # SIMPLE QUERIES
    {
        "id": 1,
        "query": "What is machine learning?",
        "complexity": "Simple",
        "schema": {
            "type": "object",
            "properties": {
                "definition": {"type": "string"},
                "key_concepts": {"type": "array", "items": {"type": "string"}},
                "applications": {"type": "string"}
            },
            "required": ["definition"]
        }
    },
    {
        "id": 2,
        "query": "Define transformer architecture",
        "complexity": "Simple",
        "schema": {
            "type": "object",
            "properties": {
                "definition": {"type": "string"},
                "key_components": {"type": "array", "items": {"type": "string"}},
                "purpose": {"type": "string"}
            },
            "required": ["definition"]
        }
    },
    {
        "id": 3,
        "query": "What is natural language processing?",
        "complexity": "Simple",
        "schema": {
            "type": "object",
            "properties": {
                "definition": {"type": "string"},
                "main_tasks": {"type": "array", "items": {"type": "string"}},
                "examples": {"type": "string"}
            },
            "required": ["definition"]
        }
    },

    # MODERATE QUERIES
    {
        "id": 4,
        "query": "What are the key features of Gemini 2.0 Flash?",
        "complexity": "Moderate",
        "schema": {
            "type": "object",
            "properties": {
                "overview": {"type": "string"},
                "key_features": {"type": "object"},
                "release_info": {"type": "object"}
            },
            "required": ["overview", "key_features"]
        }
    },
    {
        "id": 5,
        "query": "Compare BERT and GPT architectures",
        "complexity": "Moderate",
        "schema": {
            "type": "object",
            "properties": {
                "bert_overview": {"type": "string"},
                "gpt_overview": {"type": "string"},
                "key_differences": {"type": "array", "items": {"type": "string"}},
                "use_cases": {"type": "object"}
            },
            "required": ["bert_overview", "gpt_overview", "key_differences"]
        }
    },
    {
        "id": 6,
        "query": "How does RAG improve LLM accuracy?",
        "complexity": "Moderate",
        "schema": {
            "type": "object",
            "properties": {
                "explanation": {"type": "string"},
                "mechanism": {"type": "string"},
                "benefits": {"type": "array", "items": {"type": "string"}},
                "limitations": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["explanation", "mechanism", "benefits"]
        }
    },

    # COMPLEX QUERIES
    {
        "id": 7,
        "query": "Compare Claude Opus 4, GPT-4.5, and DeepSeek V3 architecture and performance",
        "complexity": "Complex",
        "schema": {
            "type": "object",
            "properties": {
                "comparison": {"type": "object"},
                "summary": {"type": "string"}
            },
            "required": ["comparison"]
        }
    },
    {
        "id": 8,
        "query": "Analyze the evolution of attention mechanisms from 2017 to 2025",
        "complexity": "Complex",
        "schema": {
            "type": "object",
            "properties": {
                "timeline": {"type": "array", "items": {"type": "object"}},
                "key_innovations": {"type": "array", "items": {"type": "string"}},
                "impact": {"type": "string"}
            },
            "required": ["timeline", "key_innovations"]
        }
    },
    {
        "id": 9,
        "query": "Compare MoE vs dense transformer architectures across efficiency, performance, and cost",
        "complexity": "Complex",
        "schema": {
            "type": "object",
            "properties": {
                "moe_analysis": {"type": "object"},
                "dense_analysis": {"type": "object"},
                "comparison_matrix": {"type": "object"},
                "recommendations": {"type": "string"}
            },
            "required": ["moe_analysis", "dense_analysis", "comparison_matrix"]
        }
    }
]


async def test_system(system_name: str, query_info: dict, **kwargs):
    """Test a single system with schema validation."""
    query = query_info['query']
    schema = query_info['schema']

    start = time.time()

    try:
        if "sonar" in system_name.lower():
            # Sonar Pro
            client = AIAPIClient()
            model = "sonar-pro"

            result = await client.call_structured_api(
                prompt=query,
                schema=schema,
                model=model,
                search_context_size="high",
                use_cache=False
            )

            elapsed = time.time() - start

            # Parse response
            response_obj = result.get('response', result)
            if 'choices' in response_obj:
                content = response_obj['choices'][0]['message']['content']
                answer = json.loads(content) if isinstance(content, str) else content
            else:
                answer = response_obj

            # Get metadata
            enhanced = result.get('enhanced_data', {})
            cost = enhanced.get('costs', {}).get('actual', {}).get('total_cost', 0)
            citations = result.get('citations', [])

        elif "claude" in system_name.lower() and "web" in system_name.lower():
            # Claude with web searches
            client = AIAPIClient()
            max_searches = kwargs.get('max_web_searches', 3)

            result = await client.call_structured_api(
                prompt=query,
                schema=schema,
                model="claude-sonnet-4-5",
                max_web_searches=max_searches,
                use_cache=False
            )

            elapsed = time.time() - start

            # Parse response
            response_obj = result.get('response', result)
            if 'choices' in response_obj:
                content = response_obj['choices'][0]['message']['content']
                answer = json.loads(content) if isinstance(content, str) else content
            else:
                answer = response_obj

            # Get metadata and citations
            enhanced = result.get('enhanced_data', {})
            cost = enhanced.get('costs', {}).get('actual', {}).get('total_cost', 0)
            citations = result.get('citations', [])

        else:
            # The Clone (Baseten/DeepSeek)
            clone = TheClone()
            config_variant = kwargs.get('config_variant', 'deepseek_variant')

            result = await clone.query(
                prompt=query,
                config_variant=config_variant,
                schema=schema
            )

            elapsed = time.time() - start

            answer = result.get('answer', {})
            citations = result.get('citations', [])
            metadata = result.get('metadata', {})
            cost = metadata.get('total_cost', 0)

        # Schema validation
        schema_valid = False
        schema_error = None
        try:
            validate(instance=answer, schema=schema)
            schema_valid = True
        except ValidationError as e:
            schema_error = str(e.message)

        return {
            "system": system_name,
            "time_seconds": round(elapsed, 2),
            "cost": cost,
            "answer": answer,
            "citations": citations,
            "citations_count": len(citations),
            "schema_valid": schema_valid,
            "schema_error": schema_error,
            "success": True
        }

    except Exception as e:
        elapsed = time.time() - start
        return {
            "system": system_name,
            "time_seconds": round(elapsed, 2),
            "error": str(e),
            "success": False
        }


async def main():
    """Run comprehensive comparison tests."""
    print("=" * 80)
    print("SONAR PRO vs CLAUDE WEB SEARCH vs THE CLONE (BASETEN)")
    print("=" * 80)
    print(f"\nTesting {len(TEST_QUERIES)} queries across 3 systems")
    print("Saving one file per question with all model responses\n")
    print("-" * 80)

    # Test systems
    systems = [
        ("Sonar Pro (HIGH)", {}),
        ("Claude Web Search (3)", {"max_web_searches": 3}),
        ("The Clone (Baseten)", {"config_variant": "deepseek_variant"})
    ]

    # Create output directory
    output_dir = os.path.join(os.path.dirname(__file__), '../test_results/comparison_sonar_claude_baseten')
    os.makedirs(output_dir, exist_ok=True)

    # Track all results for summary report
    all_query_results = []

    # Run tests
    for query_info in TEST_QUERIES:
        query_id = query_info['id']
        query = query_info['query']
        complexity = query_info['complexity']

        print(f"\n{'='*80}")
        print(f"Query {query_id}: [{complexity}] {query}")
        print(f"{'='*80}\n")

        # Run all systems in parallel for this query
        tasks = [
            test_system(system_name, query_info, **system_kwargs)
            for system_name, system_kwargs in systems
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        query_results = []
        for r in results:
            if isinstance(r, Exception):
                query_results.append({
                    "system": "Unknown",
                    "error": str(r),
                    "success": False
                })
            else:
                query_results.append(r)

        # Display summary
        print(f"{'System':<25} {'Time':>8} {'Cost':>10} {'Cites':>6} {'Schema':>8}")
        print("-" * 65)
        for r in query_results:
            if r.get('success'):
                schema_status = "[OK]" if r.get('schema_valid') else "[FAIL]"
                print(f"{r['system']:<25} {r['time_seconds']:>7.1f}s "
                      f"${r['cost']:>8.4f} {r['citations_count']:>6} {schema_status:>8}")
                if not r.get('schema_valid') and r.get('schema_error'):
                    print(f"  Schema error: {r['schema_error'][:80]}")
            else:
                print(f"{r.get('system','Unknown'):<25} ERROR: {r.get('error','')[:40]}")

        # Save individual file for this question
        question_file = os.path.join(output_dir, f'q{query_id:02d}_{complexity.lower()}.json')
        with open(question_file, 'w', encoding='utf-8') as f:
            json.dump({
                "query": query,
                "complexity": complexity,
                "schema": query_info['schema'],
                "timestamp": datetime.now().isoformat(),
                "results": query_results
            }, f, indent=2)

        print(f"\n[SUCCESS] Saved to: {os.path.basename(question_file)}")

        # Track for summary
        all_query_results.append({
            "query_id": query_id,
            "query": query,
            "complexity": complexity,
            "file": os.path.basename(question_file),
            "results": query_results
        })

        # Brief pause between queries
        await asyncio.sleep(2)

    # Generate main summary report
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    summary_file = os.path.join(output_dir, f'SUMMARY_{timestamp}.md')

    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("# Sonar Pro vs Claude Web Search vs The Clone (Baseten)\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Total Queries:** {len(TEST_QUERIES)}\n")
        f.write(f"**Systems Tested:** {len(systems)}\n\n")
        f.write("---\n\n")

        # Overall summary table
        f.write("## Results by Query\n\n")
        f.write("| ID | Complexity | Query | File |\n")
        f.write("|----|------------|-------|------|\n")
        for qr in all_query_results:
            f.write(f"| {qr['query_id']} | {qr['complexity']} | {qr['query'][:60]}... | `{qr['file']}` |\n")

        f.write("\n---\n\n")

        # Detailed results per query
        for qr in all_query_results:
            f.write(f"## Query {qr['query_id']}: {qr['query']}\n\n")
            f.write(f"**Complexity:** {qr['complexity']}\n\n")
            f.write(f"**Detailed results:** See `{qr['file']}`\n\n")

            f.write("| System | Time | Cost | Citations | Schema Valid |\n")
            f.write("|--------|------|------|-----------|-------------|\n")

            for r in qr['results']:
                if r.get('success'):
                    schema_status = "[OK]" if r.get('schema_valid') else "[FAIL]"
                    f.write(f"| {r['system']} | {r['time_seconds']:.1f}s | "
                           f"${r['cost']:.4f} | {r['citations_count']} | {schema_status} |\n")
                    if not r.get('schema_valid') and r.get('schema_error'):
                        f.write(f"| -> Schema Error | {r['schema_error'][:80]}... |\n")
                else:
                    f.write(f"| {r.get('system','Unknown')} | ERROR | - | - | - |\n")

            f.write("\n")

        # Cost analysis
        f.write("---\n\n## Cost Analysis\n\n")
        for system_name, _ in systems:
            system_results = []
            for qr in all_query_results:
                for r in qr['results']:
                    if r.get('system') == system_name and r.get('success'):
                        system_results.append(r)

            if system_results:
                total_cost = sum(r['cost'] for r in system_results)
                avg_cost = total_cost / len(system_results)
                total_time = sum(r['time_seconds'] for r in system_results)
                avg_time = total_time / len(system_results)

                f.write(f"### {system_name}\n")
                f.write(f"- Total Cost: ${total_cost:.4f}\n")
                f.write(f"- Average Cost: ${avg_cost:.4f}\n")
                f.write(f"- Total Time: {total_time:.1f}s\n")
                f.write(f"- Average Time: {avg_time:.1f}s\n")
                f.write(f"- Queries Completed: {len(system_results)}/{len(TEST_QUERIES)}\n\n")

        # Complexity breakdown
        f.write("---\n\n## Breakdown by Complexity\n\n")
        for complexity_level in ["Simple", "Moderate", "Complex"]:
            f.write(f"### {complexity_level} Queries\n\n")
            f.write("| System | Avg Time | Avg Cost | Success Rate |\n")
            f.write("|--------|----------|----------|-------------|\n")

            for system_name, _ in systems:
                complexity_results = []
                for qr in all_query_results:
                    if qr['complexity'] == complexity_level:
                        for r in qr['results']:
                            if r.get('system') == system_name:
                                complexity_results.append(r)

                if complexity_results:
                    successful = [r for r in complexity_results if r.get('success')]
                    success_rate = len(successful) / len(complexity_results) * 100

                    if successful:
                        avg_time = sum(r['time_seconds'] for r in successful) / len(successful)
                        avg_cost = sum(r['cost'] for r in successful) / len(successful)
                        f.write(f"| {system_name} | {avg_time:.1f}s | ${avg_cost:.4f} | {success_rate:.0f}% |\n")
                    else:
                        f.write(f"| {system_name} | - | - | 0% |\n")

            f.write("\n")

    print(f"\n{'='*80}")
    print(f"[SUCCESS] Summary report: {os.path.basename(summary_file)}")
    print(f"[SUCCESS] Individual files: {output_dir}/q*.json")
    print(f"[SUCCESS] Output directory: {output_dir}")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
