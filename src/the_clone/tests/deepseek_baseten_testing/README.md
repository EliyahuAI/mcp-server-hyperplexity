# DeepSeek V3.2 via Baseten - Testing Results

This folder contains tests and benchmarks for DeepSeek V3.2 accessed through Baseten's inference API.

## Test Files

### 1. test_basic_inference.py
Tests basic inference capabilities with streaming responses.

**Result:** [SUCCESS]
- Successfully generates responses
- Streaming works correctly
- Time: ~6 seconds for short prompts

### 2. test_structured_simple.py
Tests structured outputs with a simple JSON schema (answer + confidence).

**Result:** [SUCCESS]
- Returns valid JSON matching schema
- Response time: ~0.96 seconds
- Strict schema adherence works

### 3. test_structured_better.py
Tests structured outputs with a more complex schema (person info with constrained fields).

**Result:** [SUCCESS]
- Returns valid JSON with all required fields
- Respects array constraints (maxItems, minItems)
- Response time: ~1.84 seconds
- Schema validation works correctly

### 4. benchmark_speed.py
Comprehensive speed benchmark testing multiple scenarios.

## Benchmark Results

### Short Prompt (Streaming, ~200 tokens)
- **Time to First Token:** 0.366s
- **Total Time:** 3.05s
- **Tokens/Second:** 49.6

### Medium Prompt (Streaming, ~500 tokens)
- **Time to First Token:** 0.255s
- **Total Time:** 8.95s
- **Tokens/Second:** 56.4

### Short Prompt (Non-Streaming, ~200 tokens)
- **Total Time:** 2.93s

### Structured Outputs
- **Total Time:** 4.00s
- All responses returned valid JSON

## Key Findings

1. **Basic Inference:** Works perfectly with streaming support
2. **Structured Outputs:** Fully functional with OpenAI-compatible JSON schema
3. **Speed:**
   - Fast time-to-first-token (~250-370ms)
   - Good throughput (~50-56 tokens/second)
   - Competitive with other inference providers
4. **Reliability:** All tests passed consistently across multiple runs

## API Configuration

```python
from openai import OpenAI

client = OpenAI(
    api_key="sxYEtips.xoyFieypSXbMhxi72ZW0en4OiU35idb1",
    base_url="https://inference.baseten.co/v1"
)
```

Model ID: `deepseek-ai/DeepSeek-V3.2`

## Compatibility

- Fully compatible with OpenAI Python SDK
- Supports streaming and non-streaming
- Supports structured outputs with JSON schema (strict mode)
- Supports standard OpenAI parameters (temperature, max_tokens, etc.)

## Running the Tests

```bash
# Basic inference
python.exe test_basic_inference.py

# Simple structured output
python.exe test_structured_simple.py

# Complex structured output
python.exe test_structured_better.py

# Full benchmark
python.exe benchmark_speed.py
```

## Conclusion

DeepSeek V3.2 via Baseten is production-ready with:
- Solid performance metrics
- Full structured output support
- OpenAI-compatible API
- Reliable streaming
- Good latency and throughput
