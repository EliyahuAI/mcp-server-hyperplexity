"""
Benchmark Claude Sonnet 4.5 vs DeepSeek V3.2 for structured outputs
Measures TPS (tokens per second) for both models
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

async def test_claude(prompt: str, schema: dict, num_runs: int = 5):
    """Test Claude Sonnet 4.5 with structured output"""
    print(f"\n[CLAUDE SONNET 4.5] Testing (runs={num_runs})")
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

        # Claude's structured output format (Anthropic doesn't have response_format like OpenAI)
        # We'll request JSON in the prompt
        enhanced_prompt = f"{prompt}\n\nProvide your response as valid JSON matching this exact schema:\n{json.dumps(schema, indent=2)}"

        data = {
            "model": "claude-sonnet-4-6-20250929",
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
    print("Claude Sonnet 4.5 vs DeepSeek V3.2 - Structured Output Benchmark")
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
    claude_simple = await test_claude(prompt1, SIMPLE_SCHEMA, num_runs=5)

    # Test 2: Complex schema
    print("\n" + "=" * 70)
    print("TEST 2: Complex Schema (summary + arrays + nested data)")
    print("=" * 70)

    prompt2 = "Analyze the current state of AI development. Include key points and recommendations."

    deepseek_complex = await test_deepseek(prompt2, COMPLEX_SCHEMA, num_runs=5)
    claude_complex = await test_claude(prompt2, COMPLEX_SCHEMA, num_runs=5)

    # Final comparison
    print("\n" + "=" * 70)
    print("FINAL COMPARISON")
    print("=" * 70)

    if deepseek_simple and claude_simple:
        print("\nSimple Schema:")
        print(f"  DeepSeek V3.2: {deepseek_simple['avg_tps']:.1f} TPS, {deepseek_simple['avg_time']:.2f}s")
        print(f"  Claude Sonnet 4.5: {claude_simple['avg_tps']:.1f} TPS, {claude_simple['avg_time']:.2f}s")

        winner = "DeepSeek" if deepseek_simple['avg_tps'] > claude_simple['avg_tps'] else "Claude"
        speedup = max(deepseek_simple['avg_tps'], claude_simple['avg_tps']) / min(deepseek_simple['avg_tps'], claude_simple['avg_tps'])
        print(f"  Winner: {winner} ({speedup:.1f}x faster TPS)")

    if deepseek_complex and claude_complex:
        print("\nComplex Schema:")
        print(f"  DeepSeek V3.2: {deepseek_complex['avg_tps']:.1f} TPS, {deepseek_complex['avg_time']:.2f}s")
        print(f"  Claude Sonnet 4.5: {claude_complex['avg_tps']:.1f} TPS, {claude_complex['avg_time']:.2f}s")

        winner = "DeepSeek" if deepseek_complex['avg_tps'] > claude_complex['avg_tps'] else "Claude"
        speedup = max(deepseek_complex['avg_tps'], claude_complex['avg_tps']) / min(deepseek_complex['avg_tps'], claude_complex['avg_tps'])
        print(f"  Winner: {winner} ({speedup:.1f}x faster TPS)")

    print("\n" + "=" * 70)
    print("COST COMPARISON (Estimated)")
    print("=" * 70)

    # Approximate pricing (as of early 2025)
    # DeepSeek V3.2: ~$0.14/M input, ~$0.55/M output via Vertex
    # Claude Sonnet 4.5: ~$3/M input, ~$15/M output

    if deepseek_simple and claude_simple:
        ds_cost = (deepseek_simple['avg_output'] * 0.55) / 1000000 * 1000
        cl_cost = (claude_simple['avg_output'] * 15) / 1000000 * 1000
        print(f"\nSimple Schema (per 1000 requests):")
        print(f"  DeepSeek V3.2: ~${ds_cost:.2f}")
        print(f"  Claude Sonnet 4.5: ~${cl_cost:.2f}")
        print(f"  Savings with DeepSeek: {((cl_cost - ds_cost) / cl_cost * 100):.0f}%")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n[ERROR] Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
