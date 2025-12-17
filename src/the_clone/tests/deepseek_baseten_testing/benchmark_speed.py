"""
Benchmark DeepSeek V3.2 via Baseten for speed and performance
"""
from openai import OpenAI
import time
import statistics
import json

def benchmark_streaming_speed(client, prompt, max_tokens=500, num_runs=3):
    """Benchmark streaming response speed"""
    print(f"\n[INFO] Benchmarking streaming (max_tokens={max_tokens}, runs={num_runs})")
    print("-" * 70)

    results = {
        "time_to_first_token": [],
        "total_time": [],
        "tokens_generated": [],
        "tokens_per_second": [],
        "characters_generated": []
    }

    for run in range(num_runs):
        print(f"Run {run + 1}/{num_runs}...", end=" ", flush=True)

        start_time = time.time()
        first_token_time = None
        full_response = ""
        token_count = 0

        response = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3.2",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            stream_options={
                "include_usage": True,
                "continuous_usage_stats": True
            },
            max_tokens=max_tokens,
            temperature=0.7
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content is not None:
                if first_token_time is None:
                    first_token_time = time.time()
                content = chunk.choices[0].delta.content
                full_response += content
                token_count += 1

        end_time = time.time()

        # Calculate metrics
        ttft = (first_token_time - start_time) if first_token_time else 0
        total_time = end_time - start_time
        tps = token_count / (end_time - first_token_time) if first_token_time else 0

        results["time_to_first_token"].append(ttft)
        results["total_time"].append(total_time)
        results["tokens_generated"].append(token_count)
        results["tokens_per_second"].append(tps)
        results["characters_generated"].append(len(full_response))

        print(f"TTFT: {ttft:.3f}s, Total: {total_time:.2f}s, TPS: {tps:.1f}")

    # Calculate averages
    avg_results = {
        "avg_ttft": statistics.mean(results["time_to_first_token"]),
        "avg_total_time": statistics.mean(results["total_time"]),
        "avg_tokens": statistics.mean(results["tokens_generated"]),
        "avg_tps": statistics.mean(results["tokens_per_second"]),
        "avg_chars": statistics.mean(results["characters_generated"])
    }

    print(f"\n[SUMMARY]")
    print(f"  Average Time to First Token: {avg_results['avg_ttft']:.3f}s")
    print(f"  Average Total Time: {avg_results['avg_total_time']:.2f}s")
    print(f"  Average Tokens Generated: {avg_results['avg_tokens']:.1f}")
    print(f"  Average Tokens/Second: {avg_results['avg_tps']:.1f}")
    print(f"  Average Characters: {avg_results['avg_chars']:.0f}")

    return avg_results

def benchmark_non_streaming_speed(client, prompt, max_tokens=500, num_runs=3):
    """Benchmark non-streaming response speed"""
    print(f"\n[INFO] Benchmarking non-streaming (max_tokens={max_tokens}, runs={num_runs})")
    print("-" * 70)

    results = {
        "total_time": [],
        "characters_generated": []
    }

    for run in range(num_runs):
        print(f"Run {run + 1}/{num_runs}...", end=" ", flush=True)

        start_time = time.time()

        response = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3.2",
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            max_tokens=max_tokens,
            temperature=0.7
        )

        end_time = time.time()
        total_time = end_time - start_time
        content = response.choices[0].message.content

        results["total_time"].append(total_time)
        results["characters_generated"].append(len(content))

        print(f"Total: {total_time:.2f}s, Chars: {len(content)}")

    # Calculate averages
    avg_results = {
        "avg_total_time": statistics.mean(results["total_time"]),
        "avg_chars": statistics.mean(results["characters_generated"])
    }

    print(f"\n[SUMMARY]")
    print(f"  Average Total Time: {avg_results['avg_total_time']:.2f}s")
    print(f"  Average Characters: {avg_results['avg_chars']:.0f}")

    return avg_results

def benchmark_structured_outputs(client, num_runs=3):
    """Benchmark structured output speed"""
    print(f"\n[INFO] Benchmarking structured outputs (runs={num_runs})")
    print("-" * 70)

    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "analysis",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "key_points": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                        "maxItems": 5
                    },
                    "confidence": {"type": "number"}
                },
                "required": ["summary", "key_points", "confidence"],
                "additionalProperties": False
            }
        }
    }

    results = {"total_time": []}

    for run in range(num_runs):
        print(f"Run {run + 1}/{num_runs}...", end=" ", flush=True)

        start_time = time.time()

        response = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3.2",
            messages=[{
                "role": "user",
                "content": "Analyze the benefits of cloud computing. Provide 3-5 key points."
            }],
            response_format=schema,
            max_tokens=500,
            temperature=0.7
        )

        end_time = time.time()
        total_time = end_time - start_time

        results["total_time"].append(total_time)

        # Validate JSON
        try:
            parsed = json.loads(response.choices[0].message.content)
            print(f"Total: {total_time:.2f}s [VALID JSON]")
        except:
            print(f"Total: {total_time:.2f}s [INVALID JSON]")

    avg_time = statistics.mean(results["total_time"])
    print(f"\n[SUMMARY]")
    print(f"  Average Total Time: {avg_time:.2f}s")

    return {"avg_total_time": avg_time}

def main():
    """Run all benchmarks"""
    client = OpenAI(
        api_key="sxYEtips.xoyFieypSXbMhxi72ZW0en4OiU35idb1",
        base_url="https://inference.baseten.co/v1"
    )

    print("=" * 70)
    print("DeepSeek V3.2 via Baseten - Speed Benchmark")
    print("=" * 70)

    all_results = {}

    # Test 1: Short prompt, streaming
    all_results["short_streaming"] = benchmark_streaming_speed(
        client,
        "Write a short paragraph about Python programming.",
        max_tokens=200,
        num_runs=3
    )

    # Test 2: Medium prompt, streaming
    all_results["medium_streaming"] = benchmark_streaming_speed(
        client,
        "Write a detailed explanation of how neural networks work, including forward propagation and backpropagation.",
        max_tokens=500,
        num_runs=3
    )

    # Test 3: Short prompt, non-streaming
    all_results["short_non_streaming"] = benchmark_non_streaming_speed(
        client,
        "Write a short paragraph about Python programming.",
        max_tokens=200,
        num_runs=3
    )

    # Test 4: Structured outputs
    all_results["structured"] = benchmark_structured_outputs(client, num_runs=3)

    # Final summary
    print("\n" + "=" * 70)
    print("FINAL BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"\nShort Prompt (Streaming):")
    print(f"  TTFT: {all_results['short_streaming']['avg_ttft']:.3f}s")
    print(f"  Total: {all_results['short_streaming']['avg_total_time']:.2f}s")
    print(f"  TPS: {all_results['short_streaming']['avg_tps']:.1f}")

    print(f"\nMedium Prompt (Streaming):")
    print(f"  TTFT: {all_results['medium_streaming']['avg_ttft']:.3f}s")
    print(f"  Total: {all_results['medium_streaming']['avg_total_time']:.2f}s")
    print(f"  TPS: {all_results['medium_streaming']['avg_tps']:.1f}")

    print(f"\nShort Prompt (Non-Streaming):")
    print(f"  Total: {all_results['short_non_streaming']['avg_total_time']:.2f}s")

    print(f"\nStructured Outputs:")
    print(f"  Total: {all_results['structured']['avg_total_time']:.2f}s")

    print("\n[SUCCESS] Benchmark completed!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
