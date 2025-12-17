"""
Measure tokens per second for non-streaming requests
"""
from openai import OpenAI
import time
import statistics

client = OpenAI(
    api_key="sxYEtips.xoyFieypSXbMhxi72ZW0en4OiU35idb1",
    base_url="https://inference.baseten.co/v1"
)

def measure_tps(prompt, max_tokens=500, num_runs=5):
    """Measure TPS for non-streaming"""
    print(f"[INFO] Measuring TPS (max_tokens={max_tokens}, runs={num_runs})")
    print("-" * 60)

    results = {
        "total_time": [],
        "tokens": [],
        "tps": []
    }

    for run in range(num_runs):
        start = time.time()

        response = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3.2",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.7
        )

        elapsed = time.time() - start

        # Get token count from usage if available
        tokens = None
        if hasattr(response, 'usage') and response.usage:
            tokens = response.usage.completion_tokens
        else:
            # Estimate: ~4 characters per token
            tokens = len(response.choices[0].message.content) // 4

        tps = tokens / elapsed

        results["total_time"].append(elapsed)
        results["tokens"].append(tokens)
        results["tps"].append(tps)

        print(f"Run {run+1}: {elapsed:.2f}s, {tokens} tokens, {tps:.1f} TPS")

    # Calculate averages
    avg_time = statistics.mean(results["total_time"])
    avg_tokens = statistics.mean(results["tokens"])
    avg_tps = statistics.mean(results["tps"])

    print(f"\n[SUMMARY]")
    print(f"  Average Time: {avg_time:.2f}s")
    print(f"  Average Tokens: {avg_tokens:.1f}")
    print(f"  Average TPS: {avg_tps:.1f}")

    return avg_tps

print("=" * 60)
print("Non-Streaming TPS Measurement")
print("=" * 60)

# Test with different prompt sizes
print("\n--- Short Prompt (~200 tokens) ---")
short_tps = measure_tps(
    "Write a paragraph about Python programming.",
    max_tokens=200,
    num_runs=5
)

print("\n--- Medium Prompt (~500 tokens) ---")
medium_tps = measure_tps(
    "Write a detailed explanation of how neural networks work.",
    max_tokens=500,
    num_runs=5
)

print("\n" + "=" * 60)
print("FINAL RESULTS")
print("=" * 60)
print(f"Short Prompt TPS: {short_tps:.1f} tokens/second")
print(f"Medium Prompt TPS: {medium_tps:.1f} tokens/second")
