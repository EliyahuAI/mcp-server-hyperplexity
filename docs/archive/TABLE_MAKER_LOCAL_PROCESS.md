# Independent Row Discovery - Local Process Description

**Date:** October 21, 2025
**Location:** `table_maker/` directory (local, tested, working)

---

## Overview

A 4-step pipeline that creates research tables by discovering and validating rows through progressive model escalation and quality control.

---

## The 4 Steps

### **Step 1: Column Definition**

**Purpose:** Define precise column specifications and search strategy

**Input:**
- User's request (e.g., "Track AI companies that are hiring")
- Conversation context
- Optional: context_web_research items (for unknowns LLM doesn't know)

**Process:**
- Uses claude-haiku-4-5 (fast, cheap) OR sonar-pro (if context research needed)
- Creates detailed column specifications with validation strategies
- Defines 2-5 subdomains for parallel row discovery
- Each subdomain gets: name, focus, search_queries (3-5), target_rows

**Output:**
```json
{
  "columns": [
    {"name": "Company Name", "is_identification": true, ...},
    {"name": "Website", "is_identification": true, ...},
    {"name": "Is Hiring for AI?", "is_identification": false, "validation_strategy": "..."}
  ],
  "search_strategy": {
    "description": "Find AI companies actively hiring",
    "user_context": "Original user request",
    "table_purpose": "Track AI hiring status",
    "tablewide_research": "Research findings about AI hiring trends",
    "subdomains": [
      {
        "name": "AI Research Companies",
        "focus": "Research-focused AI companies",
        "search_queries": ["top AI research labs 2024", ...],
        "target_rows": 10
      }
    ]
  },
  "table_name": "AI Companies Hiring Status"
}
```

**Cost:** ~$0.002-0.035 (depends on web search)
**Time:** ~10-40 seconds

---

### **Step 2: Row Discovery**

**Purpose:** Find entities matching requirements using progressive escalation

**Input:**
- Columns (with descriptions)
- Search strategy (with subdomains)
- Escalation strategy from config

**Process:**

**For each subdomain (sequential or parallel):**

**Level 1: sonar (high context)**
- Execute web searches using search_queries
- Score each entity found (relevancy, reliability, recency)
- Tag with model_used, context_used, round number
- Check: Found >= 75% of target? → Stop, skip Level 2

**Level 2: sonar-pro (high context)** (only if Level 1 insufficient)
- More comprehensive search
- Better quality results
- Higher cost
- Always completes (final level)

**Tags on each candidate:**
```json
{
  "id_values": {"Company Name": "Anthropic", "Website": "..."},
  "score_breakdown": {"relevancy": 0.95, "reliability": 1.0, "recency": 0.9},
  "match_rationale": "...",
  "source_urls": [...],
  "model_used": "sonar",
  "context_used": "high",
  "round": 1
}
```

**Output:**
- 20-40 candidates total (from all subdomains)
- Each tagged with which model/round found it
- All unique entities from web search

**Cost:** ~$0.01-0.06
**Time:** ~60-120 seconds (sequential), ~30-60 seconds (parallel)

---

### **Step 3: Consolidation**

**Purpose:** Deduplicate and prepare for QC

**Input:**
- All candidates from all subdomains (20-40 rows)

**Process:**

**3a. Recalculate Scores**
- Formula: match_score = (relevancy × 0.4) + (reliability × 0.3) + (recency × 0.3)
- Don't trust LLM math - calculate in code

**3b. Deduplicate**
- Fuzzy matching on ID columns
- "Anthropic" = "Anthropic Inc" = "Anthropic PBC"
- Prefer candidates from better models (sonar-pro rank 5 > sonar rank 3)
- Merge source URLs from all duplicates
- Track: found_by_models, model_quality_rank

**3c. Filter**
- Remove candidates with match_score < 0.6 (configurable threshold)
- Keep everything else

**3d. Sort**
- By match_score descending
- No cutoff - pass ALL above-threshold rows to QC

**Output:**
- 15-30 unique candidates above threshold
- Sorted by quality
- Ready for QC review

**Cost:** $0.00 (no API calls)
**Time:** <1 second

---

### **Step 4: QC Review**

**Purpose:** Final quality control - decide which rows to keep

**Input:**
- All consolidated candidates (15-30 rows)
- Full context (user request, columns, table purpose, research background)

**Process:**
- Uses claude-sonnet-4-5 (no web search needed)
- Reviews each candidate for:
  - Does it match user requirements?
  - Is it unique (not redundant)?
  - Is it actionable (can we validate it)?
  - Strategic value (good example)?

**Assigns:**
- qc_score (0-1, more flexible than discovery rubric)
- keep (true/false)
- priority_adjustment (promote/demote/none)
- qc_rationale (explanation)

**Merges with original:**
- Starts with discovery metadata (match_score, model_used, source_urls, etc.)
- Overlays QC fields (qc_score, qc_rationale, keep, priority_adjustment)

**Filters:**
- Keep only: keep=true AND qc_score >= 0.5
- Sort by qc_score descending
- Return ALL that pass (no max_rows cutoff)

**Output:**
- 8-25 approved rows (QC-determined, flexible count)
- Each has BOTH discovery metadata AND QC assessment
- Sorted by qc_score

**Cost:** ~$0.015-0.035
**Time:** ~8-15 seconds

---

## Complete Example Flow

**User Request:**
> "Track AI companies that are hiring"

**Step 1 Output:**
- Columns: Company Name, Website, Is Hiring?, Team Size, Recent Funding
- 3 Subdomains: AI Research (target: 10), Healthcare AI (target: 10), Enterprise AI (target: 10)

**Step 2 Execution:**
```
AI Research:
  Level 1 (sonar-high): 8 candidates → Stop (80% of target)

Healthcare AI:
  Level 1 (sonar-high): 4 candidates → Continue (40% of target)
  Level 2 (sonar-pro-high): 7 candidates → Stop (total 11)

Enterprise AI:
  Level 1 (sonar-high): 6 candidates → Stop (60% of target)

Total discovered: 8 + 11 + 6 = 25 candidates
```

**Step 3 Output:**
- Deduplication: 25 → 20 unique (5 duplicates merged)
- Filter <0.6: 20 → 19 (1 removed)
- Sorted by match_score
- Pass all 19 to QC

**Step 4 Output:**
- QC reviews 19
- Keeps 15 (qc_score >= 0.5)
- Rejects 4 (off-topic or low quality)
- Promotes 3 exceptional fits
- **Final: 15 rows** (QC-determined)

---

## Configuration

**File:** `table_maker/table_maker_config.json`

```json
{
  "column_definition": {
    "model": "claude-haiku-4-5",
    "max_tokens": 12000
  },
  "row_discovery": {
    "escalation_strategy": [
      {
        "model": "sonar",
        "search_context_size": "high",
        "min_candidates_percentage": 75
      },
      {
        "model": "sonar-pro",
        "search_context_size": "high",
        "min_candidates_percentage": null
      }
    ],
    "max_tokens": 16000,
    "min_match_score": 0.6
  },
  "qc_review": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 16000,
    "min_qc_score": 0.5
  }
}
```

---

## Key Files (Local)

**Core Components:**
- `src/column_definition_handler.py` - Step 1
- `src/row_discovery_stream.py` - Step 2 (per subdomain)
- `src/row_discovery.py` - Step 2 (orchestrator)
- `src/row_consolidator.py` - Step 3
- `src/qc_reviewer.py` - Step 4

**Schemas:**
- `schemas/column_definition_response.json`
- `schemas/row_discovery_response.json`
- `schemas/qc_review_response.json`

**Prompts:**
- `prompts/column_definition.md`
- `prompts/row_discovery.md`
- `prompts/qc_review.md`

**Tests:**
- `test_local_e2e_sequential.py` - Full pipeline, sequential mode
- `test_local_e2e_parallel.py` - Full pipeline, parallel mode (3 subdomains concurrent)

**Config:**
- `table_maker_config.json` - All settings

---

## How to Run

```bash
cd table_maker

# Set API key
export ANTHROPIC_API_KEY="your-key"

# Run sequential test (detailed logs)
python test_local_e2e_sequential.py

# Run parallel test (faster)
python test_local_e2e_parallel.py

# View prompts from latest test
python view_prompts.py
```

**Expected:**
- Time: 1-3 minutes
- Cost: $0.05-0.12
- Output: 8-15 real companies (QC-determined)
- JSON saved to: `output/local_tests/`

---

## Success Indicators

✅ **Proper columns** (not "Table Name", "Entity Name" meta-columns)
✅ **Real companies** (OpenAI, Anthropic, PathAI, etc.)
✅ **Progressive escalation** working (logs show rounds)
✅ **Model tracking** (sonar-high, sonar-pro-high)
✅ **QC filtering** (reviews, keeps, rejects)
✅ **Flexible row count** (could be 8, could be 20)
✅ **Cost tracking** in API calls summary

---

**This is the complete, working local system ready for Lambda integration.**
