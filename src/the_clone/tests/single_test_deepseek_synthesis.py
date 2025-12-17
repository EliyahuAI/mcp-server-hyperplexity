#!/usr/bin/env python.exe
"""Test DeepSeek V3.2 for synthesis (strong tier) + Sonnet for deep thinking."""
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


async def main():
    """Test DeepSeek for synthesis."""
    query = "What are the key features of Gemini 2.0 Flash?"

    print("=" * 80)
    print("DEEPSEEK SYNTHESIS TEST")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  - Routing: DeepSeek V3.2")
    print(f"  - Triage: DeepSeek V3.2")
    print(f"  - Extraction: DeepSeek V3.2")
    print(f"  - Synthesis (strong tier): DeepSeek V3.2")
    print(f"  - Deep thinking tier: Sonnet 4.5")
    print(f"\nQuery: {query}\n")

    # Create debug directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    debug_dir = os.path.join(os.path.dirname(__file__), f'../test_results/debug/deepseek_synthesis_{timestamp}')
    os.makedirs(debug_dir, exist_ok=True)
    print(f"Debug output: {debug_dir}\n")

    clone = TheClone()
    start_time = time.time()

    result = await clone.query(prompt=query, config_variant="deepseek_synthesis_variant", debug_dir=debug_dir)
    elapsed = time.time() - start_time

    metadata = result['metadata']

    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f'Time: {elapsed:.2f}s')
    print(f'Cost: ${metadata["total_cost"]:.4f}')
    print(f'Citations: {metadata["citations_count"]}')
    print(f'Snippets: {metadata["total_snippets"]}')
    print(f'Synthesis tier used: {metadata.get("synthesis_model_tier")}')

    print(f'\nCost breakdown:')
    for component, cost in metadata['cost_breakdown'].items():
        if cost > 0:
            pct = (cost / metadata['total_cost'] * 100) if metadata['total_cost'] > 0 else 0
            print(f'  {component:20s}: ${cost:.4f} ({pct:5.1f}%)')

    # Save result
    output_dir = '../test_results/deepseek_synthesis_test'
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'{output_dir}/result_{timestamp}.json'

    with open(output_file, 'w') as f:
        json.dump({
            'query': query,
            'time_seconds': elapsed,
            'cost': metadata['total_cost'],
            'citations_count': metadata['citations_count'],
            'snippets_extracted': metadata['total_snippets'],
            'synthesis_tier': metadata.get('synthesis_model_tier'),
            'answer': result.get('answer'),
            'citations': result.get('citations'),
            'synthesis_prompt': result.get('synthesis_prompt'),
            'cost_breakdown': metadata['cost_breakdown'],
            'metadata': metadata
        }, f, indent=2)

    # Save synthesis prompt if available
    if result.get('synthesis_prompt'):
        prompt_file = f'{output_dir}/result_{timestamp}_synthesis_prompt.md'
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(result['synthesis_prompt'])
        print(f'Synthesis prompt saved to: {prompt_file}')

    # Save schemas for debugging
    from the_clone.triage_schemas import get_source_triage_schema
    from the_clone.unified_schemas import get_unified_evaluation_synthesis_schema, get_synthesis_only_schema

    schema_file = f'{output_dir}/result_{timestamp}_schemas.json'
    with open(schema_file, 'w', encoding='utf-8') as f:
        json.dump({
            'triage_schema': get_source_triage_schema(),
            'synthesis_evaluation_schema': get_unified_evaluation_synthesis_schema(),
            'synthesis_only_schema': get_synthesis_only_schema()
        }, f, indent=2)
    print(f'Schemas saved to: {schema_file}')

    # Save example triage prompt (reconstruct from last run)
    # Note: We'd need to capture this during execution for the actual prompt

    print(f'\n[SUCCESS] Result saved to: {output_file}')


if __name__ == "__main__":
    asyncio.run(main())
