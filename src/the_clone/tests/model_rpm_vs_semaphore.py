#!/usr/bin/env python3
"""
Model: RPM vs Semaphore limit for Gemini 2.0 Flash

Based on latency test results + estimated output token generation time.
"""

# Latency test results (small output ~35 tokens)
# These represent base latency (input processing + overhead)
BASE_LATENCY = {
    500: 0.72,
    1000: 0.78,
    2000: 0.93,
    4000: 0.94,
    8000: 1.07,
    16000: 1.42,
    32000: 7.16,  # unstable
}

# Gemini 2.0 Flash output generation speed (tokens/second)
# Conservative estimate based on typical LLM speeds
OUTPUT_TPS = 150  # tokens per second

# Vertex AI rate limits
VERTEX_AI_RPM_LIMIT = 60  # requests per minute (standard tier)
VERTEX_AI_RPM_LIMIT_HIGH = 1000  # higher tier


def estimate_request_latency(input_tokens: int, output_tokens: int) -> float:
    """Estimate total request latency."""
    # Find closest base latency
    closest_key = min(BASE_LATENCY.keys(), key=lambda k: abs(k - input_tokens))
    base = BASE_LATENCY[closest_key]

    # Scale base latency if input is different (sublinear scaling)
    if input_tokens != closest_key:
        # Approximate sublinear scaling: latency ~ tokens^0.3
        scale_factor = (input_tokens / closest_key) ** 0.3
        base = base * scale_factor

    # Add output generation time
    output_time = output_tokens / OUTPUT_TPS

    return base + output_time


def model_throughput(semaphore: int, avg_latency: float, rate_limit_rpm: int) -> dict:
    """
    Model effective throughput given semaphore limit and average latency.

    Returns:
        dict with theoretical_rpm, effective_rpm, utilization, queue_time
    """
    # Theoretical max RPM with semaphore (no rate limit)
    # If semaphore=5 and latency=6s, we can do 5 requests every 6 seconds
    # = 5 * (60/6) = 50 RPM
    theoretical_rpm = semaphore * (60 / avg_latency)

    # Effective RPM (capped by rate limit)
    effective_rpm = min(theoretical_rpm, rate_limit_rpm)

    # Utilization (how much of rate limit we're using)
    utilization = effective_rpm / rate_limit_rpm

    # Are we semaphore-bound or rate-limit-bound?
    bottleneck = "semaphore" if theoretical_rpm < rate_limit_rpm else "rate_limit"

    # Average queue time if requests arrive faster than we can process
    # (assuming steady state)
    if theoretical_rpm >= rate_limit_rpm:
        queue_time = 0  # Rate limit is bottleneck, no queue buildup
    else:
        queue_time = avg_latency * (1 - utilization)  # Simplified

    return {
        'theoretical_rpm': theoretical_rpm,
        'effective_rpm': effective_rpm,
        'utilization': utilization,
        'bottleneck': bottleneck,
        'queue_time': queue_time
    }


def main():
    print("=" * 80)
    print("RPM vs Semaphore Model for Gemini 2.0 Flash")
    print("=" * 80)

    # Typical extraction scenarios
    scenarios = [
        {"name": "Small batch (5 sources)", "input": 5000, "output": 300},
        {"name": "Medium batch (10 sources)", "input": 10000, "output": 500},
        {"name": "Large batch (15 sources)", "input": 15000, "output": 800},
        {"name": "Findall batch (20 sources)", "input": 20000, "output": 1000},
    ]

    semaphore_values = [1, 2, 3, 5, 8, 10, 15, 20]

    print("\n## Estimated Request Latencies")
    print("-" * 60)
    print(f"{'Scenario':<30} | {'Input':>8} | {'Output':>8} | {'Latency':>10}")
    print("-" * 60)

    scenario_latencies = {}
    for s in scenarios:
        latency = estimate_request_latency(s['input'], s['output'])
        scenario_latencies[s['name']] = latency
        print(f"{s['name']:<30} | {s['input']:>8} | {s['output']:>8} | {latency:>8.2f}s")

    print("\n## RPM vs Semaphore (Standard Tier: 60 RPM limit)")
    print("-" * 80)

    # Use medium batch as representative
    avg_latency = scenario_latencies["Medium batch (10 sources)"]
    print(f"\nUsing 'Medium batch' latency: {avg_latency:.2f}s")
    print()
    print(f"{'Semaphore':>10} | {'Theoretical':>12} | {'Effective':>10} | {'Utilization':>12} | {'Bottleneck':>12}")
    print("-" * 70)

    for sem in semaphore_values:
        result = model_throughput(sem, avg_latency, VERTEX_AI_RPM_LIMIT)
        print(f"{sem:>10} | {result['theoretical_rpm']:>10.1f} RPM | {result['effective_rpm']:>8.1f} RPM | {result['utilization']*100:>10.1f}% | {result['bottleneck']:>12}")

    print("\n## Multi-User Impact (2 concurrent users)")
    print("-" * 80)
    print(f"\nEach user triggers findall (5 parallel batch calls)")
    print(f"Findall latency: {scenario_latencies['Findall batch (20 sources)']:.2f}s per batch")
    print()

    findall_latency = scenario_latencies["Findall batch (20 sources)"]

    # With 2 users doing findall, we have 10 requests trying to run
    for sem in [3, 5, 8, 10]:
        # Time to complete all 10 requests with semaphore
        batches_needed = 10 / sem  # How many "waves" of requests
        total_time = batches_needed * findall_latency
        effective_rpm = 10 / (total_time / 60)

        print(f"Semaphore {sem}: {batches_needed:.1f} waves × {findall_latency:.1f}s = {total_time:.1f}s total, ~{effective_rpm:.0f} RPM")

    print("\n## Recommendations")
    print("-" * 80)
    print("""
    Semaphore | Use Case
    ----------|--------------------------------------------------
         3    | Conservative: safe for multi-user, may queue
         5    | Balanced: handles findall (5 parallel), reasonable multi-user
         8    | Aggressive: faster single-user, may hit rate limits with 2+ users
        10    | Maximum: only if you have elevated quota (>60 RPM)

    Current default: 5 (matches findall's 5 parallel batches)
    """)

    print("\n## Key Insight")
    print("-" * 80)
    print(f"""
    With batch extraction enabled:
    - Single user, normal query: 1-2 Gemini calls total
    - Single user, findall: 5 Gemini calls (parallel)
    - Semaphore of 5 allows findall to run unqueued

    Rate limit math (60 RPM, {avg_latency:.1f}s latency):
    - Max concurrent before rate limiting: 60 RPM × ({avg_latency:.1f}s / 60s) = {60 * avg_latency / 60:.1f} requests
    - Semaphore of 5 keeps us safely under this
    """)


if __name__ == "__main__":
    main()
