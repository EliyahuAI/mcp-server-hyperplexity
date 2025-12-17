# Claude Haiku 3.5 vs DeepSeek V3.2 - TPS Comparison

## Executive Summary

**Split Decision:**
- **TPS Winner (Simple)**: DeepSeek V3.2 - 18% faster
- **TPS Winner (Complex)**: Haiku 3.5 - Slightly faster (tie)
- **Speed Winner**: Haiku 3.5 - 30-50% faster response times
- **Cost Winner**: DeepSeek V3.2 - 57% cheaper

## Performance Results

### Simple Schema (answer + explanation + confidence)

| Metric | DeepSeek V3.2 | Claude Haiku 3.5 | Winner |
|--------|---------------|------------------|--------|
| **TPS** | 47.2 | 40.1 | **DeepSeek (+18%)** |
| **Avg Time** | 3.34s | 2.54s | **Haiku (1.3x faster)** |
| **Avg Output** | 161 tokens | 102 tokens | N/A |

### Complex Schema (summary + arrays + recommendations)

| Metric | DeepSeek V3.2 | Claude Haiku 3.5 | Winner |
|--------|---------------|------------------|--------|
| **TPS** | 44.3 | 45.0 | **Haiku (+2%)** (tie) |
| **Avg Time** | 7.54s | 5.11s | **Haiku (1.5x faster)** |
| **Avg Output** | 335 tokens | 229 tokens | N/A |

## Key Findings

### Tokens Per Second (TPS)
- **Simple tasks**: DeepSeek 18% faster (47.2 vs 40.1 TPS)
- **Complex tasks**: Essentially tied (44.3 vs 45.0 TPS)
- **Conclusion**: TPS is comparable, slight edge to DeepSeek on simple tasks

### Response Time
- **Simple tasks**: Haiku 30% faster (2.5s vs 3.3s)
- **Complex tasks**: Haiku 47% faster (5.1s vs 7.5s)
- **Conclusion**: Haiku consistently faster overall response time

### Why The Paradox?

**DeepSeek has higher TPS but slower overall time because it generates MORE tokens:**
- Simple task: 161 vs 102 tokens (58% more)
- Complex task: 335 vs 229 tokens (46% more)

**Interpretation:**
- DeepSeek generates tokens faster per second (higher TPS)
- BUT DeepSeek is more verbose, so total time is longer
- Haiku is more concise, leading to faster completion despite lower TPS

### Output Verbosity
- **DeepSeek**: More verbose/detailed (40-60% more tokens)
- **Haiku**: More concise (fewer tokens)
- **Impact**: Affects total time significantly

### Cost Analysis

**Per 1,000 Requests (Simple Schema):**
- DeepSeek V3.2: $0.088
- Claude Haiku 3.5: $0.204
- **Savings with DeepSeek: 57%**

**Pricing (Approximate):**
- DeepSeek: $0.28/M input, $0.40/M output
- Haiku 3.5: $0.80/M input, $4.00/M output

## Detailed Test Results

### Test 1: Simple Schema

**DeepSeek V3.2:**
- Run times: 3.70s, 2.70s, 3.30s, 4.47s, 2.55s
- TPS: 51.9, 43.7, 51.5, 51.0, 37.6
- Average: 47.2 TPS, 3.34s
- Output: 96-228 tokens (highly variable)

**Claude Haiku 3.5:**
- Run times: 2.49s, 2.49s, 2.56s, 2.61s, 2.54s
- TPS: 39.8, 41.4, 42.5, 39.1, 37.8
- Average: 40.1 TPS, 2.54s
- Output: 96-109 tokens (very consistent)

### Test 2: Complex Schema

**DeepSeek V3.2:**
- Run times: 8.11s, 6.49s, 3.57s, 10.35s, 9.17s
- TPS: 44.8, 44.4, 42.3, 41.2, 48.7
- Average: 44.3 TPS, 7.54s
- Output: 151-447 tokens (very variable)

**Claude Haiku 3.5:**
- Run times: 5.09s, 4.72s, 4.80s, 5.30s, 5.64s
- TPS: 46.4, 44.7, 46.5, 43.8, 43.4
- Average: 45.0 TPS, 5.11s
- Output: 211-245 tokens (consistent)

## Consistency Analysis

### DeepSeek V3.2
- **Variability**: High variance in output length
- **TPS Range**: 37.6-51.9 (simple), 41.2-48.7 (complex)
- **Time Range**: 2.55-4.47s (simple), 3.57-10.35s (complex)
- **Consistency**: Moderate to low

### Claude Haiku 3.5
- **Variability**: Low variance in output length
- **TPS Range**: 37.8-42.5 (simple), 43.4-46.5 (complex)
- **Time Range**: 2.49-2.61s (simple), 4.72-5.64s (complex)
- **Consistency**: Very high

## Use Case Recommendations

### Choose DeepSeek V3.2 When:
- ✅ **Cost is critical** (57% cheaper)
- ✅ **More detailed responses desired**
- ✅ **TPS throughput matters** (on simple tasks)
- ✅ **Budget-constrained applications**

### Choose Claude Haiku 3.5 When:
- ✅ **Speed is critical** (30-50% faster)
- ✅ **Consistency required** (low variance)
- ✅ **Concise responses preferred**
- ✅ **Lower latency needed**
- ✅ **User-facing applications** (better UX)

## Performance Summary Table

| Dimension | DeepSeek V3.2 | Claude Haiku 3.5 | Winner |
|-----------|---------------|------------------|---------|
| **TPS (Simple)** | 47.2 | 40.1 | DeepSeek (+18%) |
| **TPS (Complex)** | 44.3 | 45.0 | Haiku (+2%) |
| **Speed (Simple)** | 3.34s | 2.54s | Haiku (1.3x) |
| **Speed (Complex)** | 7.54s | 5.11s | Haiku (1.5x) |
| **Consistency** | Moderate | Very High | Haiku |
| **Verbosity** | High | Low | Depends on need |
| **Cost** | $0.088/1K | $0.204/1K | DeepSeek (57% cheaper) |

## Conclusion

### TPS: **Slight Edge to DeepSeek** (18% on simple, tie on complex)
### Overall Speed: **Clear Winner: Haiku 3.5** (30-50% faster)
### Cost: **Clear Winner: DeepSeek V3.2** (57% cheaper)

**The Paradox Explained:**
DeepSeek generates tokens faster (higher TPS) but produces more tokens (more verbose), resulting in longer total time. Haiku generates tokens slightly slower but is more concise, resulting in faster completion.

**Recommendation:**
- **For user-facing apps**: Use **Haiku 3.5** (faster, more predictable)
- **For batch processing**: Use **DeepSeek V3.2** (cheaper, acceptable speed)
- **For mixed workloads**: Use **Haiku 3.5** for interactive, **DeepSeek** for background

**Note**: Haiku 4.5 was not available via API at time of testing. Once released, expect even better performance from Haiku.
