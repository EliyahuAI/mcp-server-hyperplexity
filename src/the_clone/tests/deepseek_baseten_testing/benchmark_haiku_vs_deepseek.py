"""
Benchmark Claude Haiku 4.5 vs DeepSeek V3.2 for structured outputs
Haiku is optimized for speed - let's see how it compares to DeepSeek
"""
import os
import json
import time
import asyncio
import aiohttp
import statistics
from google.auth.transport.requests import Request
from google.oauth2 import service_account

# Configuration
VERTEX_CREDENTIALS_PATH = r"C:\Users\ellio\OneDrive - Eliyahu.AI\Desktop\src\other\gen-lang-client-0650358146-897394b730e6.json"
VERTEX_PROJECT_ID = "gen-lang-client-0650358146"
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# Test schemas
SIMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "explanation": {"type": "string"},
        "confidence": {"type": "number"}
    },
    "required": ["answer", "explanation", "confidence"]
}

COMPLEX_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 5
        },
        "complexity_score": {"type": "integer"},
        "recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 4
        }
    },
    "required": ["summary", "key_points", "complexity_score", "recommendations"]
}

async def get_vertex_token():
    """Get OAuth token for Vertex AI"""
    credentials = service_account.Credentials.from_service_account_file(
        VERTEX_CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    if not credentials.valid:
        await asyncio.to_thread(credentials.refresh, Request())
    return credentials.token

async def test_deepseek(prompt: str, schema: dict, num_runs: int = 5):
    """Test DeepSeek V3.2 with structured output"""
    print(f"\n[DEEPSEEK V3.2] Testing (runs={num_runs})")
    print("-" * 70)

    access_token = await get_vertex_token()
    url = f"https://aiplatform.googleapis.com/v1/projects/{VERTEX_PROJECT_ID}/locations/global/endpoints/openapi/chat/completions"

    results = {
        "total_time": [],
        "input_tokens": [],
        "output_tokens": [],
        "tps": []
    }

    for run in range(num_runs):
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        data = {
            "model": "deepseek-ai/deepseek-v3.2-maas",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": schema
                }
            },
            "temperature": 0.7,
            "max_tokens": 1000
        }

        start = time.time()

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    elapsed = time.time() - start

                    usage = result.get('usage', {})
                    input_tokens = usage.get('prompt_tokens', 0)
                    output_tokens = usage.get('completion_tokens', 0)
                    tps = output_tokens / elapsed if elapsed > 0 else 0

                    results["total_time"].append(elapsed)
                    results["input_tokens"].append(input_tokens)
                    results["output_tokens"].append(output_tokens)
                    results["tps"].append(tps)

                    print(f"Run {run+1}: {elapsed:.2f}s, {output_tokens} tokens, {tps:.1f} TPS")
                else:
                    print(f"Run {run+1}: ERROR - {await response.text()}")

    if results["total_time"]:
        avg_tps = statistics.mean(results["tps"])
        avg_time = statistics.mean(results["total_time"])
        avg_output = statistics.mean(results["output_tokens"])

        print(f"\n[SUMMARY]")
        print(f"  Average Time: {avg_time:.2f}s")
        print(f"  Average Output Tokens: {avg_output:.0f}")
        print(f"  Average TPS: {avg_tps:.1f}")

        return {
            "avg_tps": avg_tps,
            "avg_time": avg_time,
            "avg_output": avg_output
        }
    return None

async def test_haiku(prompt: str, schema: dict, num_runs: int = 5):
    """Test Claude Haiku 4.5 with structured output"""
    print(f"\n[CLAUDE HAIKU 4.5] Testing (runs={num_runs})")
    print("-" * 70)

    url = "https://api.anthropic.com/v1/messages"

    results = {
        "total_time": [],
        "input_tokens": [],
        "output_tokens": [],
        "tps": []
    }

    for run in range(num_runs):
        headers = {
            'x-api-key': ANTHROPIC_API_KEY,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        }

        # Haiku doesn't support response_format, so we request JSON in prompt
        enhanced_prompt = f"{prompt}\n\nProvide your response as valid JSON matching this exact schema:\n{json.dumps(schema, indent=2)}"

        data = {
            "model": "claude-haiku-4-5",  # Haiku 4.5 (with dashes, not dots!)
            "max_tokens": 1000,
            "temperature": 0.7,
            "messages": [
                {"role": "user", "content": enhanced_prompt}
            ]
        }

        start = time.time()

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    elapsed = time.time() - start

                    usage = result.get('usage', {})
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                    tps = output_tokens / elapsed if elapsed > 0 else 0

                    results["total_time"].append(elapsed)
                    results["input_tokens"].append(input_tokens)
                    results["output_tokens"].append(output_tokens)
                    results["tps"].append(tps)

                    print(f"Run {run+1}: {elapsed:.2f}s, {output_tokens} tokens, {tps:.1f} TPS")
                else:
                    error = await response.text()
                    print(f"Run {run+1}: ERROR - {error}")

    if results["total_time"]:
        avg_tps = statistics.mean(results["tps"])
        avg_time = statistics.mean(results["total_time"])
        avg_output = statistics.mean(results["output_tokens"])

        print(f"\n[SUMMARY]")
        print(f"  Average Time: {avg_time:.2f}s")
        print(f"  Average Output Tokens: {avg_output:.0f}")
        print(f"  Average TPS: {avg_tps:.1f}")

        return {
            "avg_tps": avg_tps,
            "avg_time": avg_time,
            "avg_output": avg_output
        }
    return None

async def main():
    """Run comparison benchmarks"""
    print("=" * 70)
    print("Claude Haiku 4.5 vs DeepSeek V3.2 - Speed Benchmark")
    print("=" * 70)

    if not ANTHROPIC_API_KEY:
        print("[ERROR] ANTHROPIC_API_KEY environment variable not set")
        return

    # Test 1: Simple schema
    print("\n" + "=" * 70)
    print("TEST 1: Simple Schema (answer + explanation + confidence)")
    print("=" * 70)

    prompt1 = "What are the main benefits of using Python for data science? Be concise."

    deepseek_simple = await test_deepseek(prompt1, SIMPLE_SCHEMA, num_runs=5)
    haiku_simple = await test_haiku(prompt1, SIMPLE_SCHEMA, num_runs=5)

    # Test 2: Complex schema
    print("\n" + "=" * 70)
    print("TEST 2: Complex Schema (summary + arrays + nested data)")
    print("=" * 70)

    prompt2 = "Analyze the current state of AI development. Include key points and recommendations."

    deepseek_complex = await test_deepseek(prompt2, COMPLEX_SCHEMA, num_runs=5)
    haiku_complex = await test_haiku(prompt2, COMPLEX_SCHEMA, num_runs=5)

    # Final comparison
    print("\n" + "=" * 70)
    print("FINAL COMPARISON")
    print("=" * 70)

    if deepseek_simple and haiku_simple:
        print("\nSimple Schema:")
        print(f"  DeepSeek V3.2: {deepseek_simple['avg_tps']:.1f} TPS, {deepseek_simple['avg_time']:.2f}s")
        print(f"  Claude Haiku 4.5: {haiku_simple['avg_tps']:.1f} TPS, {haiku_simple['avg_time']:.2f}s")

        winner = "DeepSeek" if deepseek_simple['avg_tps'] > haiku_simple['avg_tps'] else "Haiku"
        faster_tps = max(deepseek_simple['avg_tps'], haiku_simple['avg_tps'])
        slower_tps = min(deepseek_simple['avg_tps'], haiku_simple['avg_tps'])
        speedup_tps = faster_tps / slower_tps

        faster_time = min(deepseek_simple['avg_time'], haiku_simple['avg_time'])
        slower_time = max(deepseek_simple['avg_time'], haiku_simple['avg_time'])
        speedup_time = slower_time / faster_time

        print(f"  TPS Winner: {winner} ({speedup_tps:.1f}x faster)")
        time_winner = "DeepSeek" if deepseek_simple['avg_time'] < haiku_simple['avg_time'] else "Haiku"
        print(f"  Time Winner: {time_winner} ({speedup_time:.1f}x faster)")

    if deepseek_complex and haiku_complex:
        print("\nComplex Schema:")
        print(f"  DeepSeek V3.2: {deepseek_complex['avg_tps']:.1f} TPS, {deepseek_complex['avg_time']:.2f}s")
        print(f"  Claude Haiku 4.5: {haiku_complex['avg_tps']:.1f} TPS, {haiku_complex['avg_time']:.2f}s")

        winner = "DeepSeek" if deepseek_complex['avg_tps'] > haiku_complex['avg_tps'] else "Haiku"
        faster_tps = max(deepseek_complex['avg_tps'], haiku_complex['avg_tps'])
        slower_tps = min(deepseek_complex['avg_tps'], haiku_complex['avg_tps'])
        speedup_tps = faster_tps / slower_tps

        faster_time = min(deepseek_complex['avg_time'], haiku_complex['avg_time'])
        slower_time = max(deepseek_complex['avg_time'], haiku_complex['avg_time'])
        speedup_time = slower_time / faster_time

        print(f"  TPS Winner: {winner} ({speedup_tps:.1f}x faster)")
        time_winner = "DeepSeek" if deepseek_complex['avg_time'] < haiku_complex['avg_time'] else "Haiku"
        print(f"  Time Winner: {time_winner} ({speedup_time:.1f}x faster)")

    print("\n" + "=" * 70)
    print("COST COMPARISON (Estimated per 1,000 requests)")
    print("=" * 70)

    # Approximate pricing (as of early 2025)
    # DeepSeek V3.2: ~$0.14/M input, ~$0.55/M output via Vertex
    # Claude Haiku 4.5: ~$0.40/M input, ~$2/M output

    if deepseek_simple and haiku_simple:
        ds_cost = (deepseek_simple['avg_output'] * 0.55) / 1000000 * 1000
        haiku_cost = (haiku_simple['avg_output'] * 2) / 1000000 * 1000
        savings = ((haiku_cost - ds_cost) / haiku_cost * 100) if haiku_cost > 0 else 0

        print(f"\nSimple Schema:")
        print(f"  DeepSeek V3.2: ~${ds_cost:.3f}")
        print(f"  Claude Haiku 4.5: ~${haiku_cost:.3f}")
        print(f"  Savings with DeepSeek: {savings:.0f}%")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n[ERROR] Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
