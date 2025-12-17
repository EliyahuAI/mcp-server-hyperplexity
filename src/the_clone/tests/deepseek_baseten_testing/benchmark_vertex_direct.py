"""
Benchmark DeepSeek V3.2 via Vertex AI using direct API calls
"""
import os
import json
import time
import asyncio
import aiohttp
import statistics
from google.auth.transport.requests import Request
from google.oauth2 import service_account

# Set up credentials
CREDENTIALS_PATH = r"C:\Users\ellio\OneDrive - Eliyahu.AI\Desktop\src\other\gen-lang-client-0650358146-897394b730e6.json"
PROJECT_ID = "gen-lang-client-0650358146"

async def get_access_token():
    """Get OAuth access token for Vertex AI"""
    credentials = service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )

    # Refresh token if needed
    if not credentials.valid:
        await asyncio.to_thread(credentials.refresh, Request())

    return credentials.token

async def make_vertex_call(prompt: str, max_tokens: int = 500):
    """Make a single Vertex AI API call"""
    access_token = await get_access_token()

    url = f"https://aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/global/endpoints/openapi/chat/completions"

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    data = {
        "model": "deepseek-ai/deepseek-v3.2-maas",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": max_tokens,
        "stream": False
    }

    start = time.time()

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            elapsed = time.time() - start

            if response.status == 200:
                result = await response.json()
                return {
                    'success': True,
                    'elapsed': elapsed,
                    'content': result['choices'][0]['message']['content'],
                    'usage': result.get('usage', {}),
                    'raw': result
                }
            else:
                error_text = await response.text()
                return {
                    'success': False,
                    'elapsed': elapsed,
                    'error': f"Status {response.status}: {error_text}"
                }

async def benchmark_vertex(prompt: str, max_tokens: int = 500, num_runs: int = 3):
    """Benchmark Vertex AI calls"""
    print(f"\n[INFO] Benchmarking (max_tokens={max_tokens}, runs={num_runs})")
    print("-" * 70)

    results = {
        "total_time": [],
        "tokens_input": [],
        "tokens_output": [],
        "tps": []
    }

    for run in range(num_runs):
        print(f"Run {run + 1}/{num_runs}...", end=" ", flush=True)

        result = await make_vertex_call(prompt, max_tokens)

        if result['success']:
            usage = result['usage']
            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)
            elapsed = result['elapsed']
            tps = output_tokens / elapsed if elapsed > 0 else 0

            results["total_time"].append(elapsed)
            results["tokens_input"].append(input_tokens)
            results["tokens_output"].append(output_tokens)
            results["tps"].append(tps)

            print(f"Time: {elapsed:.2f}s, Output: {output_tokens} tokens, TPS: {tps:.1f}")
        else:
            print(f"[ERROR] {result['error']}")

    if not results["total_time"]:
        print("[ERROR] All runs failed!")
        return None

    # Calculate averages
    avg_results = {
        "avg_time": statistics.mean(results["total_time"]),
        "avg_input": statistics.mean(results["tokens_input"]),
        "avg_output": statistics.mean(results["tokens_output"]),
        "avg_tps": statistics.mean(results["tps"])
    }

    print(f"\n[SUMMARY]")
    print(f"  Average Time: {avg_results['avg_time']:.2f}s")
    print(f"  Average Input Tokens: {avg_results['avg_input']:.0f}")
    print(f"  Average Output Tokens: {avg_results['avg_output']:.0f}")
    print(f"  Average TPS: {avg_results['avg_tps']:.1f}")

    return avg_results

async def main():
    """Run all benchmarks"""
    print("=" * 70)
    print("DeepSeek V3.2 via Vertex AI - Speed Benchmark")
    print("=" * 70)

    all_results = {}

    # Test 1: Short prompt
    all_results["short"] = await benchmark_vertex(
        "Write a short paragraph about Python programming.",
        max_tokens=200,
        num_runs=5
    )

    # Test 2: Medium prompt
    all_results["medium"] = await benchmark_vertex(
        "Write a detailed explanation of how neural networks work, including forward propagation and backpropagation.",
        max_tokens=500,
        num_runs=5
    )

    # Final summary
    print("\n" + "=" * 70)
    print("FINAL BENCHMARK SUMMARY - VERTEX AI")
    print("=" * 70)

    if all_results.get("short"):
        print(f"\nShort Prompt (~200 tokens):")
        print(f"  Time: {all_results['short']['avg_time']:.2f}s")
        print(f"  TPS: {all_results['short']['avg_tps']:.1f}")

    if all_results.get("medium"):
        print(f"\nMedium Prompt (~500 tokens):")
        print(f"  Time: {all_results['medium']['avg_time']:.2f}s")
        print(f"  TPS: {all_results['medium']['avg_tps']:.1f}")

    print("\n" + "=" * 70)
    print("COMPARISON: VERTEX AI vs BASETEN")
    print("=" * 70)

    # Baseten results from earlier
    print("\nBASETEN (Non-Streaming):")
    print("  Short Prompt: ~4.61s, 34.5 TPS")
    print("  Medium Prompt: ~14.54s, 35.3 TPS")

    if all_results.get("short") and all_results.get("medium"):
        print("\nVERTEX AI:")
        print(f"  Short Prompt: ~{all_results['short']['avg_time']:.2f}s, {all_results['short']['avg_tps']:.1f} TPS")
        print(f"  Medium Prompt: ~{all_results['medium']['avg_time']:.2f}s, {all_results['medium']['avg_tps']:.1f} TPS")

        # Calculate speed difference
        short_speedup = all_results['short']['avg_time'] / 4.61
        medium_speedup = all_results['medium']['avg_time'] / 14.54

        print("\n[SPEED COMPARISON]")
        if short_speedup < 1:
            print(f"  Vertex is {1/short_speedup:.1f}x FASTER for short prompts")
        else:
            print(f"  Baseten is {short_speedup:.1f}x FASTER for short prompts")

        if medium_speedup < 1:
            print(f"  Vertex is {1/medium_speedup:.1f}x FASTER for medium prompts")
        else:
            print(f"  Baseten is {medium_speedup:.1f}x FASTER for medium prompts")

    print("\n[SUCCESS] Vertex AI benchmark completed!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n[ERROR] Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
