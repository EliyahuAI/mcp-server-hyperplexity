# The Clone - Intelligent Search System

**Complete self-contained implementation**
**Date:** 2025-12-16

---

## Overview

The Clone is an advanced search system that intelligently routes queries, extracts essential quotes with off-topic detection, and synthesizes comprehensive answers with full cost tracking.

### Key Features

✅ **Smart Initial Routing** - Answers simple queries directly (6s), searches when needed
✅ **Dynamic Configuration** - Context and model tier determined automatically
✅ **Parallel Processing** - Triage and extraction happen concurrently
✅ **Off-Topic Detection** - Captures cross-search information (36% bonus quotes)
✅ **Unified Synthesis** - Evaluation + synthesis in single call
✅ **Full Cost Tracking** - Actual costs from enhanced_data
✅ **Schema Validation** - All internal calls use JSON schemas

### Performance

- **69% faster than baseline** (125s vs 400s)
- **8.4x more citations** (92 vs 11)
- **$0.21 per complex query**
- **36% off-topic quotes** (cross-topic information)

---

## Quick Start

```python
import os
import asyncio

# Set environment variables
os.environ['PERPLEXITY_API_KEY'] = 'your-key'
os.environ['GOOGLE_CLOUD_PROJECT'] = 'your-project'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'path-to-creds.json'

from the_clone import TheClone

async def main():
    clone = TheClone()

    result = await clone.query(
        prompt="Compare Claude Opus 4 and GPT-4.5",
        search_context="medium"  # Optional - will be auto-determined if not specified
    )

    print(f"Answer: {result['answer']}")
    print(f"Citations: {len(result['citations'])}")
    print(f"Cost: ${result['metadata']['total_cost']:.4f}")

asyncio.run(main())
```

---

## Architecture

### Complete Flow

```
Step 0: Initial Decision (Sonnet 4.5)
  ├─→ Answer Directly (6s) → Done!
  └─→ Need Search → Determines:
      - Search context (low/medium/high)
      - Synthesis model tier (fast/strong/deep_thinking)
      - Initial search terms (1-5)

      Then iterates (1-3 times based on context):
        Step 1: Use initial terms or generate new
        Step 2: Execute searches (Perplexity)
        Step 3: Parallel Triage (0-5 per search, diversity-focused)
        Step 4: Parallel Extraction (essential quotes + off-topic)
        Step 5: Unified Eval+Synthesis
          ├─→ Can answer → Done!
          └─→ Need more → Next iteration
```

### Model Usage

**Default (common):**
| Component | Model | Cost |
|-----------|-------|------|
| Initial Decision | Sonnet 4.5 | ~$0.008 |
| Triage | Haiku 4.5 | ~$0.012 |
| Extraction | Haiku 4.5 | ~$0.035 |
| Synthesis | Sonnet 4.5 | ~$0.030 |
| **Total** | | **~$0.085-0.10/query** |

**DeepSeek Variant (deepseek_variant):**
| Component | Model | Cost |
|-----------|-------|------|
| Initial Decision | DeepSeek V3.2 | ~$0.0003 |
| Triage | DeepSeek V3.2 | ~$0.002 |
| Extraction | DeepSeek V3.2 | ~$0.008 |
| Synthesis | DeepSeek V3.2 | ~$0.001-0.004 |
| **Total** | | **~$0.012-0.070/query** |

**Cost Savings:** 66-71% cheaper than Claude variant across query complexities

**Requirements:**
- DeepSeek **requires soft_schema=true** (prompt-based schema enforcement)
- Schema field name: **"answer_raw"** (DeepSeek's preferred field name)
- Haiku cleanup fallback for schema violations
- model_tiers_deepseek configured in config.json
- Haiku cleanup fallback built into ai_api_client for invalid DeepSeek outputs

### Configuration (`config.json`)

**Config Variants:**
- `common`: Claude models (Haiku for triage/extraction, Sonnet for synthesis)
- `deepseek_variant`: DeepSeek V3.2 for all components including synthesis
- `deepseek_synthesis_variant`: Same as deepseek_variant (legacy name)

**Model Tiers (common):**
- `fast`: Haiku 4.5 (simple synthesis, cost-effective)
- `strong`: Sonnet 4.5 (default, balanced)
- `deep_thinking`: Opus 4.5 (complex reasoning)

**Model Tiers (deepseek_variant):**
- `fast`: DeepSeek V3.2
- `strong`: DeepSeek V3.2 (uses soft_schema with Haiku fallback)
- `deep_thinking`: DeepSeek V3.2

**Context Levels:**

| Context | Iterations | Searches | Results/Search | Sources/Search |
|---------|------------|----------|----------------|----------------|
| **LOW** | 1 | 1-2 | 5 | 1-2 |
| **MEDIUM** | 2 | 1-3 | 10 | 1-3 |
| **HIGH** | 3 | 1-5 | 15 | 1-5 |

---

## File Structure

```
the_clone/
├── config.json                        # Configuration (tiers, contexts, DeepSeek variant)
├── the_clone.py                       # Main orchestrator
├── config_loader.py                   # Configuration with variant support
├── initial_decision.py                # Step 0: Answer/Search routing
├── initial_decision_schemas.py        # Routing schemas (required fields)
├── source_triage.py                   # Step 3: Date-aware source selection
├── triage_schemas.py                  # Triage schemas (constrained indices)
├── snippet_extractor_streamlined.py   # Step 4: Quote extraction with dates
├── snippet_schemas.py                 # Extraction schemas
├── unified_synthesizer.py             # Step 5: Eval+Synthesis with legend
├── unified_schemas.py                 # Synthesis schemas (answer_raw field)
├── perplexity_search.py               # Perplexity Search API client
├── search_manager.py                  # Search orchestration
├── config.py                          # Synthesis guidance
├── schemas.py                         # Search generation schemas
├── prompt_loader.py                   # Prompt template loader
├── prompts/
│   ├── source_triage.md               # Triage with recency priority
│   ├── snippet_extraction_streamlined.md  # Off-topic detection hardened
│   └── search_generation.md           # Search term generation
├── README.md                          # This file
├── STARTING_PROMPT.md                 # Testing instructions
└── tests/
    ├── single_test.py                 # Basic test (Claude)
    ├── single_test_deepseek.py        # DeepSeek variant test
    ├── single_test_deepseek_synthesis.py  # DeepSeek with synthesis
    ├── comprehensive_test.py          # 5-way comparison (Sonar, Sonar Pro, Claude Web, Clone Claude, Clone DeepSeek)
    ├── comprehensive_schema_test.py   # Schema-validated tests with individual question files
    ├── varied_complexity_test.py      # 8 queries across 5 systems with complexity analysis
    └── test_results/
        ├── parallel_comparison/       # Comprehensive test reports
        ├── schema_validated/          # Schema test results (SUMMARY.md + q*.json)
        └── varied_complexity/         # Complexity test results
```

---

## Key Components

### 1. Initial Decision (`initial_decision.py`)
**Decides:** Answer directly OR Search (with context + model tier)

**Output:**
```json
{
  "decision": "need_search",
  "search_context": "high",
  "synthesis_model_tier": "strong",
  "search_terms": ["term1", "term2", ...]
}
```

### 2. Source Triage (`source_triage.py`)
**Parallel triage** of all search results

**Selects:** 0-max sources per search (diversity-focused)

### 3. Quote Extraction (`snippet_extractor_streamlined.py`)
**Extracts:** Essential quotes organized by search term

**Off-topic detection:** Can extract quotes for OTHER search terms

**Output:**
```json
{
  "quotes_by_search": {
    "1": ["quote1", "quote2"],
    "2": ["off-topic quote"]
  }
}
```

### 4. Unified Synthesizer (`unified_synthesizer.py`)
**Two modes:**
- Evaluation: Can answer? If yes, provide answer
- Synthesis: Just generate answer (last iteration)

**Groups quotes by search term** with reliability markers

---

## Quote Format

### Snippet IDs
```
S{iteration}.{search}.{source}.{quote}-{reliability}

Example: S1.2.3.0-H
  - Iteration 1
  - Search term 2
  - Source 3
  - Quote 0
  - HIGH reliability
```

### Off-Topic Context
Off-topic quotes get context markers:
```
"[re: GPT-4.5 performance] Model achieves 92% accuracy"
```

### Synthesis Input Format
```
=== Search Term 1: "Claude Opus 4 architecture" ===
[S1.1.0-H] Source Title
  - [S1.1.0.0-H] "Quote 1"
  - [S1.1.0.1-H] "Quote 2"

=== Search Term 2: "GPT-4.5 performance" ===
[S1.2.0-M] GPT Source
  - [S1.2.0.0-M] "Quote 1"
[S1.1.0-H] Source Title (off-topic)
  - [S1.1.0.2-H] "[re: GPT-4.5] Off-topic quote"
```

---

## Cost Tracking

Actual costs aggregated from `enhanced_data`:

```
Component          Cost      % of Total
──────────────────────────────────────
Initial Decision   $0.0081   3.9%
Triage            $0.0194   9.2%
Extraction        $0.0723   34.5%
Synthesis         $0.0848   40.5%
Search            $0.0250   11.9%
──────────────────────────────────────
TOTAL             $0.2096   100%
```

---

## Usage Examples

### Example 1: Simple Query (Direct Answer)
```python
result = await clone.query("What is machine learning?")
# Decision: answer_directly
# Time: ~6s
# Cost: ~$0.01
# No search needed!
```

### Example 2: Moderate Complexity
```python
result = await clone.query("Compare Model A vs Model B architecture")
# Decision: need_search
# Context: medium (auto-determined)
# Model tier: strong (Sonnet)
# Time: ~50s
# Cost: ~$0.10
```

### Example 3: Complex Multi-Dimensional (Claude variant)
```python
result = await clone.query(
    "Compare Claude Opus 4, GPT-4.5, and DeepSeek V3 across "
    "architecture, performance, capabilities, and cost",
    config_variant="common"
)
# Decision: need_search
# Context: high (auto-determined)
# Model tier: strong (Sonnet)
# Time: ~105-125s
# Cost: ~$0.25
# Citations: 16 with Sonar-compatible format
```

### Example 4: Complex Multi-Dimensional (DeepSeek variant)
```python
result = await clone.query(
    "Compare Claude Opus 4, GPT-4.5, and DeepSeek V3 across "
    "architecture, performance, capabilities, and cost",
    config_variant="deepseek_variant"
)
# Decision: need_search
# Context: high (auto-determined)
# Model tier: strong (DeepSeek V3.2)
# Time: ~82-90s
# Cost: ~$0.06-0.07 (71% cheaper!)
# Citations: 14-16 with Sonar-compatible format
```

---

## Testing

See `STARTING_PROMPT.md` for instructions on testing in a new chat.

### Available Tests

**1. Comprehensive 5-Way Comparison** (`comprehensive_test.py`)
- Tests: Sonar, Sonar Pro, Claude Web Search (3), Clone (Claude), Clone (DeepSeek)
- Output: JSON + Markdown report with full answers and citations
- Run: `python.exe comprehensive_test.py`

**2. Schema-Validated Tests** (`comprehensive_schema_test.py`)
- Validates all responses against expected schemas
- One file per question with all model responses
- Main summary report references individual files
- Run: `python.exe comprehensive_schema_test.py`

**3. Varied Complexity Suite** (`varied_complexity_test.py`)
- 8 queries from simple to complex
- Tests all 5 systems per query
- Shows how context/tier selection adapts
- Run: `python.exe varied_complexity_test.py`

---

## Recent Improvements (2025-12-17)

### 1. DeepSeek Full Integration
- ✅ DeepSeek now used for synthesis (not just triage/extraction)
- ✅ 66-71% cost savings vs Claude variant
- ✅ Schema field "answer_raw" matches DeepSeek preference → zero cleanup needed

### 2. Soft Schema Enhancement
- ✅ soft_schema parameter now passed to all components
- ✅ Enhanced prompt: "Use EXACT field names specified in schema"
- ✅ Haiku cleanup fallback working for schema violations
- ✅ Fuzzy key matching with 0.8 similarity threshold

### 3. Sonar-Compatible Citations
- ✅ Citations include: url, title, cited_text, date, last_updated
- ✅ Plus Clone extras: index, reliability, snippets array
- ✅ Compatible with Sonar/Sonar Pro tools and parsers

### 4. Comprehensive Test Suite
- ✅ 5-way comparison (added Claude Web Search)
- ✅ Schema validation tests
- ✅ Varied complexity tests (8 queries)
- ✅ Individual question files with all model responses

---

## Next Steps

1. Review `STARTING_PROMPT.md`
2. Start new chat for testing
3. Run varied complexity tests
4. Run comprehensive comparison
5. Analyze results

---

**The Clone is ready for production testing!** 🚀
