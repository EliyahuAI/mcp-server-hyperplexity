"""
Benchmark DeepSeek V3.2 via Vertex AI using the existing AIApiClient
"""
import os
import sys
import time
import json
import asyncio
import statistics
from datetime import datetime

# Set up environment
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r"C:\Users\ellio\OneDrive - Eliyahu.AI\Desktop\src\other\gen-lang-client-0650358146-897394b730e6.json"
os.environ['GOOGLE_CLOUD_PROJECT'] = 'gen-lang-client-0650358146'

# Add parent directory to path to import ai_api_client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.shared.ai_api_client import AIApiClient

async def benchmark_vertex_call(client: AIApiClient, prompt: str, model: str = "deepseek-v3.2",
                                max_tokens: int = 500, num_runs: int = 3, schema: dict = None):
    """Benchmark Vertex AI calls"""
    print(f"\n[INFO] Benchmarking Vertex AI (model={model}, max_tokens={max_tokens}, runs={num_runs})")
    print("-" * 70)

    results = {
        "total_time": [],
        "tokens_input": [],
        "tokens_output": [],
        "tps": [],
        "cost": []
    }

    for run in range(num_runs):
        print(f"Run {run + 1}/{num_runs}...", end=" ", flush=True)

        start_time = datetime.now()

        try:
            # Make the API call
            response = await client._make_single_vertex_call(
                prompt=prompt,
                schema=schema,
                model=client._normalize_vertex_model(model),
                use_cache=False,
                cache_key=None,
                start_time=start_time,
                max_tokens=max_tokens,
                soft_schema=True  # Use soft schema as required
            )

            end_time = datetime.now()
            elapsed = (end_time - start_time).total_seconds()

            # Extract metrics
            token_usage = response.get('token_usage', {})
            input_tokens = token_usage.get('input_tokens', 0)
            output_tokens = token_usage.get('output_tokens', 0)

            tps = output_tokens / elapsed if elapsed > 0 else 0

            # Calculate cost (from enhanced_data if available)
            enhanced = response.get('enhanced_data', {})
            cost = enhanced.get('estimated_cost', 0)

            results["total_time"].append(elapsed)
            results["tokens_input"].append(input_tokens)
            results["tokens_output"].append(output_tokens)
            results["tps"].append(tps)
            results["cost"].append(cost)

            print(f"Time: {elapsed:.2f}s, Output: {output_tokens} tokens, TPS: {tps:.1f}, Cost: ${cost:.6f}")

        except Exception as e:
            print(f"[ERROR] {str(e)}")
            continue

    if not results["total_time"]:
        print("[ERROR] All runs failed!")
        return None

    # Calculate averages
    avg_results = {
        "avg_time": statistics.mean(results["total_time"]),
        "avg_input": statistics.mean(results["tokens_input"]),
        "avg_output": statistics.mean(results["tokens_output"]),
        "avg_tps": statistics.mean(results["tps"]),
        "avg_cost": statistics.mean(results["cost"])
    }

    print(f"\n[SUMMARY]")
    print(f"  Average Time: {avg_results['avg_time']:.2f}s")
    print(f"  Average Input Tokens: {avg_results['avg_input']:.0f}")
    print(f"  Average Output Tokens: {avg_results['avg_output']:.0f}")
    print(f"  Average TPS: {avg_results['avg_tps']:.1f}")
    print(f"  Average Cost: ${avg_results['avg_cost']:.6f}")

    return avg_results

async def main():
    """Run all benchmarks"""
    print("=" * 70)
    print("DeepSeek V3.2 via Vertex AI - Speed Benchmark")
    print("=" * 70)

    # Initialize client
    client = AIApiClient()

    all_results = {}

    # Test 1: Short prompt
    all_results["short"] = await benchmark_vertex_call(
        client,
        "Write a short paragraph about Python programming.",
        max_tokens=200,
        num_runs=3
    )

    # Test 2: Medium prompt
    all_results["medium"] = await benchmark_vertex_call(
        client,
        "Write a detailed explanation of how neural networks work, including forward propagation and backpropagation.",
        max_tokens=500,
        num_runs=3
    )

    # Test 3: Structured output
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "key_points": {
                "type": "array",
                "items": {"type": "string"}
            },
            "confidence": {"type": "number"}
        },
        "required": ["summary", "key_points", "confidence"]
    }

    all_results["structured"] = await benchmark_vertex_call(
        client,
        "Analyze the benefits of cloud computing. Provide 3-5 key points.",
        max_tokens=500,
        num_runs=3,
        schema=schema
    )

    # Final summary
    print("\n" + "=" * 70)
    print("FINAL BENCHMARK SUMMARY - VERTEX AI")
    print("=" * 70)

    if all_results.get("short"):
        print(f"\nShort Prompt (~200 tokens):")
        print(f"  Time: {all_results['short']['avg_time']:.2f}s")
        print(f"  TPS: {all_results['short']['avg_tps']:.1f}")
        print(f"  Cost: ${all_results['short']['avg_cost']:.6f}")

    if all_results.get("medium"):
        print(f"\nMedium Prompt (~500 tokens):")
        print(f"  Time: {all_results['medium']['avg_time']:.2f}s")
        print(f"  TPS: {all_results['medium']['avg_tps']:.1f}")
        print(f"  Cost: ${all_results['medium']['avg_cost']:.6f}")

    if all_results.get("structured"):
        print(f"\nStructured Output:")
        print(f"  Time: {all_results['structured']['avg_time']:.2f}s")
        print(f"  TPS: {all_results['structured']['avg_tps']:.1f}")
        print(f"  Cost: ${all_results['structured']['avg_cost']:.6f}")

    print("\n[SUCCESS] Vertex AI benchmark completed!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n[ERROR] Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
