#!/usr/bin/env python.exe
"""Single query test using DeepSeek V3.2 for routing, triage, and extraction."""
import os
import sys
import asyncio
import json
import time
from datetime import datetime

# Set environment variables
os.environ['GOOGLE_CLOUD_PROJECT'] = 'gen-lang-client-0650358146'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'C:\Users\ellio\OneDrive - Eliyahu.AI\Desktop\src\other\gen-lang-client-0650358146-897394b730e6.json'
os.environ['PERPLEXITY_API_KEY'] = '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'

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from the_clone.the_clone import TheClone2Refined as TheClone


async def run_deepseek_test(query: str, complexity: str):
    """Run a single test with DeepSeek V3.2 configuration."""
    print("=" * 80)
    print(f"THE CLONE - DEEPSEEK V3.2 TEST ({complexity} complexity)")
    print("=" * 80)
    print(f"\nQuery: {query}")
    print(f"\nConfiguration:")
    print(f"  - Initial routing: DeepSeek V3.2")
    print(f"  - Triage: DeepSeek V3.2")
    print(f"  - Extraction: DeepSeek V3.2")
    print(f"  - Synthesis: Sonnet 4.5 (unchanged)")
    print(f"\nRunning...\n")

    # Create clone instance
    clone = TheClone()
    start_time = time.time()

    try:
        # Use DeepSeek variant config
        result = await clone.query(prompt=query, config_variant="deepseek_variant")
        elapsed = time.time() - start_time

        # Extract metadata
        metadata = result['metadata']
        answer = result.get('answer', {})
        citations = result.get('citations', [])
        synthesis_prompt = result.get('synthesis_prompt', '')

        # Build test result
        test_result = {
            "query": query,
            "complexity": complexity,
            "configuration": "deepseek_v3.2",
            "timestamp": datetime.now().isoformat(),
            "decision": metadata.get('decision', 'need_search'),
            "determined_context": metadata.get('search_context'),
            "synthesis_tier": metadata.get('synthesis_model_tier'),
            "iterations": metadata.get('iterations', 0),
            "time_seconds": round(elapsed, 2),
            "cost": round(metadata['total_cost'], 4),
            "citations_count": len(citations),
            "snippets_extracted": metadata.get('total_snippets', 0),
            "answer": answer,
            "citations": citations,
            "synthesis_prompt": synthesis_prompt,
            "cost_breakdown": metadata.get('cost_breakdown', {}),
            "search_terms_used": metadata.get('search_terms', [])
        }

        # Display results
        print("\n" + "=" * 80)
        print("RESULTS:")
        print("=" * 80)
        print(f"Decision:           {test_result['decision']}")

        if test_result['decision'] == 'need_search':
            print(f"Context:            {test_result['determined_context']}")
            print(f"Synthesis tier:     {test_result['synthesis_tier']}")
            print(f"Iterations:         {test_result['iterations']}")

        print(f"\nTime:               {test_result['time_seconds']}s")
        print(f"Cost:               ${test_result['cost']:.4f}")
        print(f"Citations:          {test_result['citations_count']}")

        if test_result['cost_breakdown']:
            print(f"\nCost breakdown:")
            total = sum(test_result['cost_breakdown'].values())
            for component, cost in test_result['cost_breakdown'].items():
                if cost > 0:
                    pct = (cost / total * 100) if total > 0 else 0
                    print(f"  {component:20s}: ${cost:.4f} ({pct:5.1f}%)")

        print("\n" + "=" * 80)
        print("[SUCCESS] DeepSeek test complete!")
        print("=" * 80)

        return test_result

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Run DeepSeek variant test."""
    # Use exact same query as Haiku test
    query = "What are the key features of Gemini 2.0 Flash?"
    complexity = "Moderate"

    result = await run_deepseek_test(query, complexity)

    if result:
        # Save result
        output_dir = os.path.join(os.path.dirname(__file__), '../test_results/deepseek_test')
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(output_dir, f"result_{timestamp}.json")

        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        # Save synthesis prompt
        if result.get('synthesis_prompt'):
            prompt_file = os.path.join(output_dir, f"result_{timestamp}_synthesis_prompt.md")
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(result['synthesis_prompt'])

        print(f"\nResult saved to: {output_file}")
        if result.get('synthesis_prompt'):
            print(f"Synthesis prompt saved to: {prompt_file}")


if __name__ == "__main__":
    asyncio.run(main())
