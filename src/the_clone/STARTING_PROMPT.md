# Testing The Clone - Starting Prompt for New Chat

**Use this prompt to start a new chat for testing The Clone**

---

## THE PROMPT

```
I want to test "The Clone" - an intelligent search system located in @src/the_clone/

See @src/the_clone/README.md for architecture and @src/the_clone/KEY_FIXES.md for important solutions.

## Primary Test: Comprehensive 5-Way Comparison

Run this command:
```bash
cd src/the_clone/tests
python.exe comprehensive_test.py
```

This tests 1 query across 5 systems in parallel:
1. Sonar (HIGH context)
2. Sonar Pro (HIGH context)
3. Claude Web Search (3 searches)
4. The Clone (Claude variant)
5. The Clone (DeepSeek variant)

**Output:**
- JSON: `test_results/parallel_comparison/comparison_{timestamp}.json`
- Report: `test_results/parallel_comparison/report_{timestamp}.md`
- Debug: `test_results/debug/{system}_{timestamp}/` (prompts, schemas, responses)

**Report includes:**
- Performance comparison table
- Full answers from all systems
- All citations with snippet content
- Cost breakdowns
- Winners analysis

## Additional Tests

**Schema-Validated Tests** (with individual question files):
```bash
python.exe comprehensive_schema_test.py
```
- Output: SUMMARY.md + q01_*.json, q02_*.json, etc.
- Each question file contains all 5 models' responses
- Schema validation for all responses

**Varied Complexity** (8 queries from simple to complex):
```bash
python.exe varied_complexity_test.py
```
- Tests 5 systems across complexity levels
- Shows context/tier adaptation
- Identifies answer_directly vs need_search decisions

**Single System Test:**
```bash
python.exe single_test.py                    # Claude variant
python.exe single_test_deepseek.py           # DeepSeek variant (triage/extraction only)
python.exe single_test_deepseek_synthesis.py # DeepSeek variant (all components)
```

## Test Queries for Varied Complexity

### Simple (expect: answer_directly or low context, fast tier)
1. "What is machine learning?"
2. "Define transformer architecture"

### Moderate (expect: medium context, strong tier)
3. "Compare BERT and GPT architectures"
4. "What are the key features of Gemini 2.0 Flash?"
5. "How does RAG improve LLM accuracy?"

### Complex (expect: high context, strong/deep tier)
6. "Compare Claude Opus 4, GPT-4.5, and DeepSeek V3 architecture and performance"
7. "Analyze the evolution of attention mechanisms from 2017 to 2025"
8. "Compare MoE vs dense transformer architectures across efficiency, performance, and cost"

### Very Complex (expect: high context, deep_thinking tier)
9. "Compare the reasoning capabilities of Claude Opus 4, GPT-o1, Gemini 2.5, and DeepSeek R1 across mathematical, coding, and scientific domains with specific benchmark analysis"
10. "Analyze the trade-offs between model size, training compute, inference cost, and performance across the current generation of frontier models"

## Expected Performance

### Sonar (HIGH)
- Time: 10-20s
- Cost: $0.0004-0.0007
- Citations: 7-23

### Sonar Pro (HIGH)
- Time: 8-30s
- Cost: $0.006-0.02
- Citations: 6-23

### The Clone (Claude)
- Time: 40-130s
- Cost: $0.10-0.27
- Citations: 5-16
- Decision: answer_directly (simple) or need_search (moderate/complex)

### The Clone (DeepSeek)
- Time: 40-90s
- Cost: $0.012-0.070 (66-71% cheaper than Claude)
- Citations: 7-16 (Sonar-compatible format)
- Uses DeepSeek V3.2 for ALL components including synthesis
- soft_schema=true with Haiku fallback
- Schema field: "answer_raw" (DeepSeek preference)

## Comprehensive Comparison Query

Use this query for comparing to Sonar/Sonar Pro:

**Query:** "Compare the architectural differences and capabilities of Claude Opus 4, GPT-4.5, and DeepSeek V3"

**Test matrix:**
- The Clone (auto-determined context)
- The Clone (forced LOW context)
- The Clone (forced HIGH context)
- Sonar (LOW context)
- Sonar (HIGH context)
- Sonar Pro (LOW context)
- Sonar Pro (HIGH context)

## Success Criteria

✅ All 5 systems produce valid answers
✅ DeepSeek variant works with 7-16 citations
✅ DeepSeek uses DeepSeek V3.2 for synthesis (check logs for "deepseek-v3.2")
✅ Cost tracking accurate (DeepSeek 66-71% cheaper than Claude)
✅ Citations in Sonar-compatible format (cited_text, date, last_updated)
✅ Schema compliance with "answer_raw" field (zero cleanup needed)
✅ Debug files saved for all components
✅ Schema validation passes for all responses

## Critical Configuration (Already Set)

✅ `config.json` - soft_schema: true for DeepSeek variants
✅ Schema field: "answer_raw" (DeepSeek's preferred name - zero cleanup!)
✅ Enhanced soft schema prompt: "Use EXACT field names"
✅ Haiku fallback: Built into ai_api_client.py for schema violations
✅ soft_schema parameter: Passed through all components
✅ Model tiers: DeepSeek variant uses DeepSeek for synthesis
✅ Citations: Sonar-compatible format (cited_text + Clone extras)
✅ All schemas: Required fields with placeholders
✅ Triage: Constrained indices (0-20, unique)
✅ Sources: Sorted by date (most recent = index 0)

## Environment Setup

Required environment variables:
- `PERPLEXITY_API_KEY`: Your Perplexity API key
- `GOOGLE_CLOUD_PROJECT`: Google Cloud project ID
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to GCP service account JSON
- `ANTHROPIC_API_KEY`: Anthropic API key (usually auto-detected)

---

**Start testing The Clone and report results!**
```

---

## Additional Context

The Clone implements:
- Configuration-driven design (no hardcoded values)
- Dynamic schema generation from config
- Intelligent context/tier selection
- Full cost aggregation
- Off-topic quote detection with context markers

All files are self-contained in `@src/the_clone/` directory.
