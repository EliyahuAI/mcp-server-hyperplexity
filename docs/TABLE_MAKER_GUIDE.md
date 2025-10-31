# Table Maker - Independent Row Discovery System

**Version:** 2.5 (Background Research Phase + Enhanced Discoverability)
**Last Updated:** October 31, 2025
**Status:** Production Ready (Lambda Integrated)

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Components](#components)
4. [Configuration](#configuration)
5. [Local Testing](#local-testing)
6. [Lambda Integration](#lambda-integration)
7. [Frontend Integration](#frontend-integration)
8. [Troubleshooting](#troubleshooting)
9. [Next Steps](#next-steps)

---

## Quick Start

### What It Does

The Table Maker system generates research tables by discovering entities through web search and validating them through progressive model escalation and quality control.

**Example:** "Track AI companies that are hiring"

**Output:**
- 8-25 validated rows (company names, websites, etc.)
- Validation configuration for data quality checks
- CSV template ready for population

### 30-Second Overview

```
User Request → Interview → Background Research → Column Definition → Row Discovery → QC Review → CSV + Config
                                (Step 0)              (Step 1)          (Step 2)       (Step 3)
                           Find sources & tables   Use research      Merge samples
                           Extract sample rows     Output samples    + discovered
```

### Running a Test

```bash
cd table_maker
export ANTHROPIC_API_KEY="your-key"
python test_local_e2e_sequential.py
```

**Expected:**
- Duration: 1-3 minutes
- Cost: $0.05-0.15
- Output: 8-15 validated companies in `output/local_tests/`

---

## What's New in Version 2.5

### Background Research Phase (MAJOR ENHANCEMENT)
- **Separate Research Step**: Background research now runs BEFORE column definition (Step 0)
- **Finds Authoritative Sources**: Identifies databases, directories, and lists that contain entities
- **Extracts Starting Tables**: Gets ACTUAL sample entities (not just URLs) from sources
- **Sample Rows to QC**: Column definition extracts 5-15 sample rows that go straight to QC
- **Research Caching**: On restructure, research is ALWAYS reused (saves 30-60s and $0.02-0.05)
- **Model Split**: Research uses sonar-pro, column definition uses claude-sonnet-4-5
- **Better Discoverability**: Column definition designs table based on what's actually findable

**Key Benefits:**
- Higher success rate (research shows what's findable before designing table)
- Faster column definition (no web search needed)
- Immediate candidates (sample rows from research)
- Efficient restructure (research reused, not repeated)

### Enhanced Discoverability Guidance
- **Design for Row Discovery**: New prompt sections emphasizing table structure affects findability
- **Support Columns Strategy**: Break complex validations into discoverable steps
  - Example: Institution Email Pattern → Email (85% success vs 30% direct)
  - Example: Has AI Team → Has AI Ethics Program (70% vs 40%)
- **Original Structure on Restructure**: Shows what failed to help AI understand what to fix

### Streamlined Prompts
- **Column Definition**: Reduced from 1115 to 427 lines (62% reduction)
- **Proper Conditionals**: Restructuring section only shows when needed (not hardcoded)
- **Clear Sections**: Follows PROMPT_STRUCTURING.md guidelines

---

## What's New in Version 2.4

### Autonomous Failure Recovery (MAJOR ENHANCEMENT)
- **AI Makes Recovery Decision**: When 0 rows found, QC autonomously decides: restructure or give up
- **Two-Path Recovery Flow**:
  - **RECOVERABLE** → AI restructures table automatically and retries execution
  - **UNRECOVERABLE** → AI apologizes, frontend shows "Get Started" card for new table
- **No User Intervention Needed**: System handles recovery automatically without asking user
- **Intelligent Analysis**: QC analyzes if entities exist but structure was wrong, or if request is impossible
- **Restructuring Guidance**: QC provides specific instructions:
  - `column_changes`: How to simplify ID columns
  - `requirement_changes`: How to relax hard requirements
  - `search_broadening`: How to expand search domains
- **Friendly User Messages**: Non-technical messages for both restructure and give-up scenarios
- **Frontend Integration**: New WebSocket messages (`table_execution_restructure`, `table_execution_unrecoverable`)

**Result:** Zero-row failures either self-correct automatically or fail gracefully with clear explanation.

---

## What's New in Version 2.3.1 (Superseded by 2.4)

### Zero-Row Failure Handling
- **Early Exit on Zero Rows**: System stops execution when QC approves 0 rows
- **User-Facing Feedback**: Provides `insufficient_rows_statement` and recommendations

**Note:** Version 2.4 replaces hard failure with conversational recovery.

---

## What's New in Version 2.3

### Strategic Subdomain Scaling (2-10 Subdomains)
- **Raised Limit**: Subdomain max increased from 5 to 10
- **Adaptive Scaling**: More subdomains for challenging/niche topics
- **Decision Matrix**: Clear guidelines for when to use 2-3 vs 8-10 subdomains
- **Examples**: Fortune 500 (2-3) vs Government AI Initiatives (8-10)

### Intelligent Overshoot Targeting
- **30-50% Buffer**: Always target more rows than promised to user
- **Deduplication Compensation**: Formula adjusts for overlap (10% per extra subdomain)
- **Guaranteed Delivery**: Ensures we deliver what we promised after QC
- **Formula-Driven**: `total_target = user_requested × overshoot × dedup_compensation`

### Comprehensive Row Allocation Strategy
- **Worked Examples**: Detailed calculations for common scenarios
- **Distribution Options**: Even or weighted distribution based on subdomain yield
- **Integration with Global Counter**: Strategy works synergistically with early stopping
- **Documented in Config**: `overshoot_factor_min/max` in table_maker_config.json

### Updated Column Definition Prompt
- **Decision Matrix**: Table showing subdomain count by difficulty/complexity
- **Calculation Examples**: Step-by-step worked examples with math
- **Rationale Explained**: Why more subdomains for challenging topics
- **Clear Guidelines**: When to use 2-3 vs 6-8 vs 8-10 subdomains

**Result:** Reliable delivery of promised row counts, even for challenging/niche topics.

---

## What's New in Version 2.2

### Search Improvements Feedback System
- **Continuous Learning**: Each round collects search improvement suggestions
- **Intra-Subdomain Propagation**: Round 2 receives learnings from Round 1
- **Cross-Subdomain Propagation**: Later subdomains benefit from earlier ones
- **Automatic Embedding**: Improvements automatically added to prompts
- **Storage**: All improvements saved in `discovery_result.json` for future reference

### 3-Level Escalation Strategy
- **Level 1**: sonar (high context) - Fast, cost-efficient baseline (75% threshold)
- **Level 2**: sonar-pro (high context) - Premium search for better quality (90% threshold)
- **Level 3**: claude-haiku-4-5 (3 web searches) - Fallback when Perplexity struggles
- **Automatic Fallback**: Claude ensures results even for niche/difficult topics
- **Model-Appropriate Parameters**: search_context_size for Perplexity, max_web_searches for Claude

### Stricter ID Column Constraints
- **Clear Guidelines**: ID columns must be short (1-5 words), simple, repeatable
- **Good Examples**: Company Name, Job Title, Paper Title, Date, URL
- **Bad Examples**: Story Description, Key Responsibilities, Detailed Analysis
- **Rule of Thumb**: If it appears in a list/directory, it's a good ID column
- **Prevents Failures**: Avoids row discovery failures from complex ID requirements

### Enhanced Storage
- **Organized Structure**: All results saved to S3 table_maker subfolder
- **column_definition_result.json**: Columns, search_strategy, table_name, tablewide_research
- **discovery_result.json**: Final rows, stream_results with search_improvements, stats
- **qc_result.json**: Approved/rejected rows with scores
- **Easy Retrieval**: All data available for generating additional rows later

---

## What's New in Version 2.1

### Dynamic Parallelism
- **Auto-scales** based on subdomain count: `max_parallel_streams = min(num_subdomains, 5)`
- 2 subdomains → 2 streams, 10 subdomains → 5 streams (capped for API safety)
- Set `max_parallel_streams: null` in config to enable dynamic mode

### Global Counter with Cross-Subdomain Early Stopping
- Tracks total discovered rows across ALL subdomains
- Stops discovering once target is met globally (saves costs)
- Example: Found 16 rows after 3 subdomains → Skip remaining subdomains
- Logs show `[GLOBAL STOP]` vs `[LOCAL STOP]` decisions

### Phase-Aware Frontend
- **Interview Phase:** Dummy progress messages (10%, 25%, 40%) keep user engaged
- **Execution Phase:** Real progress with subdomain updates
- Frontend distinguishes phases via `phase='interview'` vs `phase='execution'`
- Smooth 2.5s transition: Progress complete → Pause → Fade → Auto-preview

### Real-Time WebSocket Updates
- Per-subdomain progress: "Finding rows in Healthcare AI..."
- Running total: "8 of 15 target found"
- Colored info boxes appear progressively (ID/Research/Discovered rows)
- Auto-trigger preview when complete

---

## Architecture Overview

### The 5-Step Pipeline (Step 0 Internal)

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 0: Background Research (~30-60s) INTERNAL                  │
│  • Find authoritative sources (databases, directories, lists)   │
│  • Extract starting tables with ACTUAL sample entities          │
│  • Document discovery patterns and domain context               │
│  • Model: sonar-pro (configurable)                              │
│  • On restructure: ALWAYS cached and reused (skips this step)   │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Column Definition (~10-20s)                             │
│  • Use background research to design table structure            │
│  • Define columns (ID vs research columns)                      │
│  • Create search strategy referencing starting tables           │
│  • Extract 5-15 sample rows from starting tables                │
│  • Model: claude-sonnet-4-5 (no web search needed)              │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Row Discovery + Config Generation (PARALLEL)            │
│                                                                  │
│  Row Discovery (60-120s):              Config Generation (20-40s)│
│   • Process subdomains in parallel      • Build validation rules │
│   • 3-Level progressive escalation:     • Based on columns       │
│     - Level 1: sonar-pro (high)        • Runs in background     │
│     - Level 2: claude-haiku (fallback)                          │
│     - Level 3: claude-sonnet (final)                            │
│   • Merge with sample rows from Step 1                          │
│   • Collect search improvements feedback                        │
│   • Tag candidates with metadata                                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Consolidation & QC Review (~8-15s)                      │
│  • Deduplicate merged rows (fuzzy matching)                     │
│  • Review each candidate (claude-sonnet-4-5)                    │
│  • Assign qc_score, keep/reject, priority                       │
│  • Filter: keep=true AND qc_score >= 0.5                        │
│  • If 0 rows: Autonomous recovery decision                      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Mutual Completion: Wait for Config + Generate CSV               │
│  • Wait for config generation to finish                         │
│  • Generate CSV with ID columns filled, other columns empty     │
│  • Ready for validation workflow                                │
└─────────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Background Research First:** Find authoritative sources before designing table structure
2. **Design for Discoverability:** Table structure determines if rows can be found
3. **Support Columns Strategy:** Break complex validations into discoverable steps
4. **Research Caching:** Always reuse research on restructure (mandatory optimization)
5. **Progressive Escalation:** Start with sonar-pro, escalate to claude-haiku, final claude-sonnet
6. **Continuous Learning:** Search improvements feed back into subsequent rounds and subdomains
7. **Sample + Discovered Rows:** Column definition provides samples, discovery finds more, merged for QC
8. **Quality Over Quantity:** QC layer ensures relevance
9. **No Row Limits:** Keep all quality rows (not arbitrarily capped)
10. **Simple ID Columns:** Short, repeatable identifiers prevent discovery failures
11. **Strategic Overshooting:** Target 30-50% more rows to ensure delivery after QC

---

## Subdomain & Row Allocation Strategy

**Version 2.3 Enhancement:** Strategic subdomain count and row targeting to ensure reliable delivery.

### Core Philosophy

**We prefer to overshoot the number of rows we promise in conversation.**

The system automatically adjusts subdomain count and row targets based on:
- Discovery difficulty (how niche/rare the entities are)
- User's requested row count
- Requirement complexity (simple list vs. multi-criteria)

### Subdomain Count Decision Matrix

| User Requested | Topic Difficulty | Complexity | Subdomains | Rationale |
|----------------|------------------|------------|------------|-----------|
| ≤20 rows | Common/Easy | Simple | 2-3 | Efficient, minimal overlap |
| 21-50 rows | Moderate | Moderate | 4-5 | Balanced coverage |
| 51-100 rows | Challenging/Niche | Complex | 6-8 | Wide net for rare entities |
| 100+ rows | Very Niche | Very Complex | 8-10 | Maximum parallel coverage |

**Examples:**
- "Fortune 500 companies" → 2-3 subdomains (well-known, easy to find)
- "Biotech companies hiring AI engineers" → 5-6 subdomains (niche intersection, multiple criteria)
- "Academic papers on quantum AI from 2024" → 7-8 subdomains (very specific, time-bound)
- "Local government AI initiatives globally" → 9-10 subdomains (very rare, geographically dispersed)

### Row Target Calculation Formula

```python
# Step 1: Determine overshoot factor based on complexity
overshoot_factor = 1.3 to 1.5  # 30-50% buffer

# Step 2: Calculate deduplication compensation (more subdomains = more overlap)
dedup_compensation = 1.0 + ((subdomain_count - 2) * 0.10)

# Step 3: Calculate total internal target
total_internal_target = user_requested * overshoot_factor * dedup_compensation

# Step 4: Distribute across subdomains
target_per_subdomain = total_internal_target / subdomain_count
```

### Worked Examples

**Example 1: User wants 20 rows, common topic**
- Topic: "Fortune 500 companies"
- Subdomains: 3 (easy to find)
- Overshoot: 1.3 (30% buffer)
- Dedup: 1.0 + (1 × 0.10) = 1.1
- Total target: 20 × 1.3 × 1.1 = 29 rows
- Per subdomain: 29 ÷ 3 ≈ 10 rows each

**Example 2: User wants 50 rows, niche topic**
- Topic: "Biotech companies hiring AI engineers"
- Subdomains: 6 (challenging, multi-criteria)
- Overshoot: 1.4 (40% buffer)
- Dedup: 1.0 + (4 × 0.10) = 1.4
- Total target: 50 × 1.4 × 1.4 = 98 rows
- Per subdomain: 98 ÷ 6 ≈ 16 rows each

**Example 3: User wants 100 rows, very niche**
- Topic: "Government AI initiatives globally"
- Subdomains: 9 (very rare, dispersed)
- Overshoot: 1.5 (50% buffer)
- Dedup: 1.0 + (7 × 0.10) = 1.7
- Total target: 100 × 1.5 × 1.7 = 255 rows
- Per subdomain: 255 ÷ 9 ≈ 28 rows each

### Why This Strategy Works

**Why Overshoot:**
- QC review rejects 10-30% of discovered candidates
- Deduplication removes overlaps between subdomains
- We want to DELIVER what we promised, not fall short
- Better to have extra options than to scramble for more rows

**Why More Subdomains for Challenging Topics:**
- Niche entities are spread across different niches/categories
- Each subdomain explores a different angle or approach
- Wider net → better chance of finding rare entities
- More parallel workers → faster discovery

**Why More Subdomains = Higher Targets:**
- More subdomains → more overlap in discovered entities
- Deduplication removes 10-15% per extra subdomain
- Compensation factor ensures we still hit final target
- Example: 10 subdomains might find same company 3-4 times

**Why Complex Requirements Need More Subdomains:**
- Multi-criteria searches ("biotech" AND "hiring" AND "AI") are harder
- Each subdomain can focus on one aspect of complexity
- Parallel workers can specialize in different criteria combinations
- Lower per-subdomain targets prevent worker fatigue

### Distribution Strategies

**Even Distribution (Default):**
```json
{
  "total_target": 60,
  "subdomains": 6,
  "distribution": [10, 10, 10, 10, 10, 10]
}
```

**Weighted Distribution (When Yield Varies):**
```json
{
  "total_target": 60,
  "subdomains": 5,
  "distribution": [15, 12, 12, 12, 9],
  "rationale": {
    "subdomain_1": "High-yield category (1.5x average)",
    "subdomain_2-4": "Medium-yield (1.2x average)",
    "subdomain_5": "Catch-all (0.9x average)"
  }
}
```

### Integration with Global Counter

The subdomain strategy works synergistically with the global counter:

1. **Target calculation** determines total rows needed across all subdomains
2. **Global counter** tracks progress and stops early when target met
3. **Early stopping** at 100% threshold (configurable)

**Example:**
- User wants: 50 rows
- System targets: 70 rows (40% overshoot)
- Subdomains: 5 × 14 rows each
- Global counter: Stops after subdomain 3 if 70 rows found
- Final result: 60-65 rows after QC → deliver 50+ to user

---

## Components

### 1. Column Definition Handler
**File:** `table_maker/src/column_definition_handler.py`

**Purpose:** Define table structure and search strategy

**Key Features:**
- Generates columns (ID vs data columns)
- Creates subdomains for parallel discovery
- Uses web search for unknowns (via `context_web_research`)
- Model: claude-haiku-4-5 (or sonar-pro if web search needed)

**Output:**
```json
{
  "columns": [...],
  "search_strategy": {
    "subdomains": [
      {
        "name": "AI Research Companies",
        "search_queries": ["top AI research labs 2024", ...],
        "target_rows": 10
      }
    ]
  }
}
```

### 2. Row Discovery Orchestrator
**File:** `table_maker/src/row_discovery.py`

**Purpose:** Coordinate subdomain discovery with progressive escalation

**Key Features:**
- Processes subdomains (sequential or parallel)
- Implements escalation strategy from config
- Consolidates results (deduplication, scoring)
- Tracks which model/round found each candidate

**Output:**
```json
{
  "final_rows": [...],  // Consolidated, deduplicated candidates
  "stream_results": [...],  // Per-subdomain details
  "stats": {
    "total_candidates_found": 25,
    "duplicates_removed": 5,
    "below_threshold": 1
  }
}
```

### 3. Row Discovery Stream
**File:** `src/lambdas/interface/actions/table_maker/table_maker_lib/row_discovery_stream.py`

**Purpose:** Execute progressive escalation for a single subdomain

**Key Features:**
- 3-level escalation (sonar → sonar-pro → claude-haiku)
- Early stopping based on percentage thresholds
- Collects search improvements from each round
- Passes accumulated improvements to next round
- Tags each candidate with model_used, round, context
- Uses web searches from subdomain.search_queries

**Escalation Logic:**
```python
Level 1: sonar (high context) - cheap, fast
  → If found >= 75% of target: STOP
  → Else: Continue to Level 2
  → Collects search_improvements, passes to Level 2

Level 2: sonar-pro (high context) - premium quality
  → If found >= 90% of target: STOP
  → Else: Continue to Level 3
  → Receives improvements from Level 1, adds its own

Level 3: claude-haiku-4-5 (3 web searches) - fallback
  → Always completes (final level)
  → Receives all previous improvements
  → Ensures results even for difficult topics
```

**Search Improvements Flow:**
```python
Round 1 discovers: "Use aggregator sites not individual articles"
  → Round 2 receives this in prompt
Round 2 discovers: "Date ranges improve relevance"
  → Round 3 receives both improvements
  → Next subdomain receives all improvements
```

### 4. Row Consolidator
**File:** `src/lambdas/interface/actions/table_maker/table_maker_lib/row_consolidator.py`

**Purpose:** Deduplicate and score candidates

**Key Features:**
- Fuzzy matching on ID columns ("Anthropic" = "Anthropic Inc")
- Recalculates match scores (don't trust LLM math)
- Prefers candidates from better models
- Merges source URLs from duplicates

### 5. QC Reviewer
**File:** `src/lambdas/interface/actions/table_maker/table_maker_lib/qc_reviewer.py`

**Purpose:** Final quality control and prioritization

**Key Features:**
- Uses claude-sonnet-4-5 (no web search)
- Reviews all consolidated candidates
- Assigns qc_score (0-1), more flexible than discovery rubric
- Can promote/demote based on strategic value
- No max_rows cutoff - keeps all quality rows

**Decision Criteria:**
- Does it match user requirements?
- Is it unique (not redundant)?
- Is it actionable (can we validate it)?
- Strategic value (good example)?

---

## Configuration

**File:** `src/lambdas/interface/actions/table_maker/table_maker_config.json`

### Column Definition
```json
{
  "column_definition": {
    "model": "claude-haiku-4-5",
    "max_tokens": 8000,
    "subdomain_count_min": 2,
    "subdomain_count_max": 10,
    "overshoot_factor_min": 1.3,
    "overshoot_factor_max": 1.5
  }
}
```

### Row Discovery
```json
{
  "row_discovery": {
    "escalation_strategy": [
      {
        "model": "sonar",
        "search_context_size": "high",
        "description": "Initial thorough search with sonar",
        "min_candidates_percentage": 75  // Early stop at 75% of target
      },
      {
        "model": "sonar-pro",
        "search_context_size": "high",
        "description": "Premium search if sonar insufficient",
        "min_candidates_percentage": 90  // Early stop at 90% of target
      },
      {
        "model": "claude-haiku-4-5",
        "max_web_searches": 3,  // Use web searches instead of search_context_size
        "description": "Fallback to Claude with web search if both Perplexity models fail",
        "min_candidates_percentage": null  // Final level, always completes
      }
    ],
    "max_tokens": 16000,
    "min_match_score": 0.6,  // Filter threshold after consolidation
    "max_parallel_streams": null,  // null = dynamic (based on subdomain count, capped at 5)
    "check_targets_between_subdomains": true,  // Enable global counter
    "early_stop_threshold_percentage": 100  // Stop when global count = 100% of target
  }
}
```

### QC Review
```json
{
  "qc_review": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 16000,
    "min_qc_score": 0.5,  // Final quality threshold
    "min_row_count": 4,  // Minimum rows to guarantee (promotes rejected if needed)
    "min_row_count_for_frontend": 4  // Threshold for triggering recovery decision
  }
}
```

**Recovery Threshold Configuration:**
- `min_row_count`: QC will promote rejected rows to meet this minimum
- `min_row_count_for_frontend`: Below this, QC makes autonomous recovery decision (restructure or give up)
- Both are configurable - adjust based on your use case
- Typical values: 3-8 rows depending on table complexity

### ID Column Requirements (CRITICAL)

**ID columns must be SHORT, simple, and easily discoverable:**
- Maximum 1-5 words typically
- Must be found in lists, directories, or indexes
- Should NOT require synthesis or reading paragraphs
- Will be discovered during row discovery (not validated later)

**Good ID Column Examples:**
- ✅ Company Name (e.g., "Anthropic", "OpenAI")
- ✅ Job Title (e.g., "Senior ML Engineer")
- ✅ Paper Title (e.g., "Attention Is All You Need")
- ✅ Date (e.g., "2025-01-15")
- ✅ Story Headline (e.g., "Senate Passes AI Safety Bill")
- ✅ URL (e.g., "https://example.com/article")

**Bad ID Column Examples:**
- ❌ "Basic Story Description" - Requires synthesis, multiple sentences
- ❌ "Key Responsibilities" - Paragraphs of text
- ❌ "Detailed Analysis" - Requires research and reasoning
- ❌ "Summary of Findings" - Too complex, not simple identifier

**Rule of Thumb:** If it appears in a bullet-point list or index, it's a good ID column. If it requires reading and synthesizing paragraphs, make it a research column instead.

**Why This Matters:**
- Row discovery fails when ID columns are too complex
- Models struggle to populate detailed fields from web searches
- Simple IDs ensure reliable, repeatable discovery

---

### Key Settings to Tune

**`max_parallel_streams` (null):**
- `null` → Dynamic mode (uses subdomain count, capped at 5)
- `1` → Sequential mode (slower but predictable)
- `3` → Fixed 3 parallel streams (override dynamic)
- **Recommended:** `null` for optimal performance

**`check_targets_between_subdomains` (true):**
- `true` → Enable global counter (stop early if target met)
- `false` → Each subdomain decides independently
- **Recommended:** `true` for cost savings

**`early_stop_threshold_percentage` (100):**
- `100` → Stop when global count = target exactly
- `120` → Discover 20% extra before stopping (more QC options)
- `80` → Stop early at 80% of target (aggressive cost savings)
- **Recommended:** `100` for balanced approach

**`min_candidates_percentage` (75):**
- Higher → More early stops per subdomain (cheaper, faster)
- Lower → More escalations (more expensive, more rows)
- **Recommended:** `75` for balanced quality/cost

**`min_match_score` (0.6):**
- Higher → Fewer candidates pass to QC (stricter)
- Lower → More candidates pass to QC (more lenient)
- **Recommended:** `0.6` for good quality baseline

**`min_qc_score` (0.5):**
- Higher → Fewer final rows (stricter quality)
- Lower → More final rows (more lenient quality)
- **Recommended:** `0.5` for flexible quality

**`min_row_count` (4):**
- Minimum rows QC guarantees by promoting rejected rows
- Higher → More rows guaranteed but lower quality
- Lower → Fewer rows but higher quality
- **Recommended:** `4` for most use cases, `2-3` for niche topics

**`min_row_count_for_frontend` (4):**
- Threshold below which autonomous recovery kicks in
- Should typically match or be slightly lower than `min_row_count`
- Below this threshold, QC decides: restructure or give up
- **Recommended:** Same as `min_row_count`

---

## Example Execution Output (Lambda)

**Expected CloudWatch logs showing v2.2 features:**
```
[INFO] [EXECUTION] Step 1/4: Defining columns and search strategy
[INFO] [EXECUTION] Step 1 complete: 5 columns, table: AI Companies Hiring
[INFO] [GLOBAL COUNTER] Enabled. Target: 15, Threshold: 100%
[INFO] Step 2/3: Processing subdomains SEQUENTIALLY
[INFO] Processing subdomain 1/3: AI Research Companies (target: 10 rows)
[INFO]   Round 1/3: sonar (high context)
[INFO]   Round 1: 8 candidates
[INFO]   Round 1: Collected 1 search improvement(s). Total improvements available: 1
[INFO]   [GLOBAL COUNTER] AI Research Companies Round 1: +8 candidates. Subdomain: 8, Global: 8/15
[INFO]   [LOCAL STOP] Round 1: 8 candidates >= 7 threshold (75% of 10). Skipping 2 round(s)
[INFO] Processing subdomain 2/3: Healthcare AI (target: 10 rows)
[INFO]   Round 1/3: sonar (high context)
[INFO]   Round 1: 4 candidates
[INFO]   Round 1: Collected 1 search improvement(s). Total improvements available: 2
[INFO]   [GLOBAL COUNTER] Healthcare AI Round 1: +4 candidates. Subdomain: 4, Global: 12/15
[INFO]   Round 2/3: sonar-pro (high context)
[INFO]   Round 2: 7 candidates
[INFO]   [GLOBAL COUNTER] Healthcare AI Round 2: +7 candidates. Subdomain: 11, Global: 19/15
[INFO] Collected 2 search improvement(s) from 'Healthcare AI'. Total improvements: 2
[INFO] Processing subdomain 3/3: Enterprise AI (target: 10 rows)
[INFO]   [GLOBAL STOP] Enterprise AI Round 1: Global count 19 >= threshold 15. Skipping 3 round(s)
[INFO] [EXECUTION] Step 2 complete: 15 consolidated rows
[INFO] [EXECUTION] Step 4: QC Review
[SUCCESS] QC approved 14 rows
[SUCCESS] Total cost: $0.087, Total time: 142.5s
```

**Search Improvements Example:**
```json
// From discovery_result.json
"stream_results": [
  {
    "subdomain": "AI Research Companies",
    "search_improvements": [
      "Exclude YouTube and video results - web sources only",
      "Aggregator sites like TechCrunch yield better multi-result lists"
    ],
    "candidates": [...]
  },
  {
    "subdomain": "Healthcare AI",
    "search_improvements": [
      "Healthcare + AI + startup queries work better than general healthcare AI",
      "Crunchbase and AngelList more reliable than news articles"
    ],
    "candidates": [...]
  }
]
```

---

## Lambda Integration

**Location:** `src/lambdas/interface/actions/table_maker/`

### Entry Point

**File:** `conversation.py` → `_trigger_execution()`

Called when interview completes and user approves the table.

### Execution Orchestrator

**File:** `execution.py` → `execute_full_table_generation()`

**Key differences from local:**
- Uses `UnifiedS3Manager` for state persistence
- Sends WebSocket updates for real-time feedback
- Tracks metrics in DynamoDB runs table
- Runs config generation in parallel with row discovery
- Generates CSV template at the end

**Integration pattern:**
```python
# Initialize LOCAL components (no modifications)
from .table_maker_lib.column_definition_handler import ColumnDefinitionHandler
from .table_maker_lib.row_discovery import RowDiscovery
from .table_maker_lib.qc_reviewer import QCReviewer

# Use them exactly as in local tests
column_result = await column_handler.define_columns(...)
discovery_result = await row_discovery.discover_rows(...)
qc_result = await qc_reviewer.review_rows(...)

# Add Lambda wrappers
_add_api_call_to_runs(session_id, run_key, column_result, 'Column Definition')
_save_to_s3(storage_manager, email, session_id, conversation_id, 'column_result.json', column_result)
```

### WebSocket Messages

**Interview progress (dummy messages):**
```json
{
  "type": "table_interview_progress",
  "conversation_id": "...",
  "phase": "interview",
  "status": "Understanding your table requirements...",
  "progress_percent": 10,
  "turn_number": 1
}
```

**Execution progress updates:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "...",
  "phase": "execution",
  "current_step": 2,
  "total_steps": 4,
  "status": "Finding rows in Healthcare AI...",
  "progress_percent": 45,
  "subdomain": "Healthcare AI",
  "subdomain_index": 1,
  "total_subdomains": 3,
  "global_discovered": 8,
  "global_target": 15
}
```

**Step-specific fields:**
- **Step 1 complete:** Includes `columns` array and `table_name`
- **Step 3 complete:** Includes `discovered_rows` (top 10) and `total_discovered`
- **Step 4 complete:** Includes `approved_row_count`

**Completion:**
```json
{
  "type": "table_execution_complete",
  "conversation_id": "...",
  "phase": "execution",
  "status": "Table ready for validation!",
  "table_name": "AI Companies Hiring Status",
  "row_count": 15,
  "approved_rows": [...],
  "config_s3_key": "path/to/config.json",
  "csv_s3_key": "path/to/template.csv"
}
```

### Config Generation Integration

**Runs in parallel with row discovery:**
```python
# Start config generation in background
config_task = asyncio.create_task(
    _generate_validation_config(...)
)

# Run row discovery (blocks until complete)
discovery_result = await row_discovery.discover_rows(...)

# QC starts immediately (config still running)
qc_result = await qc_reviewer.review_rows(...)

# Wait for config to finish
config_result = await config_task

# Generate CSV with ID columns filled
```

**Benefits:**
- No added time (runs during row discovery)
- Validation config ready when rows are approved
- CSV template immediately available

**Context Injection (Fixed 2025-10-28):**

The config generation receives rich context from the Table Maker conversation via `config_bridge.py`:

**Data Flow:**
```
conversation_state → config_bridge.py → table_analysis → config_generation/__init__.py
                                             ↓
                                    conversation_context:
                                    - research_purpose
                                    - user_requirements
                                    - tablewide_research
                                    - column_details (name, description, validation_strategy, format, is_identification)
                                    - identification_columns
```

The `build_table_analysis_section()` function injects this context into the `{{TABLE_ANALYSIS}}` section of the prompt, ensuring the AI sees:
1. **Research Purpose** - Why the user wanted this table
2. **User Requirements** - What the user asked for
3. **Tablewide Research** - Concise research summary about the domain
4. **Column Definitions** - Full description and validation_strategy for EXACT use in notes
5. **Identification Columns** - Which columns define what each row represents

**Key Files:**
- `src/lambdas/interface/actions/table_maker/config_bridge.py` - Assembles conversation_context
- `src/lambdas/interface/actions/config_generation/__init__.py:build_table_analysis_section()` - Injects context into prompt
- `src/lambdas/interface/actions/config_generation/prompts/table_maker_config_prompt.md` - Specialized prompt for Table Maker configs

---

## Frontend Integration

**Location:** `frontend/perplexity_validator_interface2.html`

### WebSocket Event Handlers

Listen for `table_interview_progress`, `table_execution_update`, and `table_execution_complete` events.

**Key handlers (lines 4740-5049):**
- `handleTableExecutionUpdate()` - Phase-aware progress updates
- `handleTableExecutionComplete()` - 2.5s transition sequence
- `showColumnsBoxes()` - Blue/purple colored boxes
- `showDiscoveredRowsBox()` - Orange box with top 10 rows
- `collapseConversation()` - Smooth fade animation
- `autoTriggerPreview()` - Auto-trigger validation preview

### Phase-Aware Updates

**Interview phase (dummy messages):**
```javascript
{
  type: 'table_interview_progress',
  phase: 'interview',  // Frontend only updates progress bar
  status: "Analyzing table structure...",
  progress_percent: 25
}
```

**Execution phase (real progress):**
```javascript
{
  type: 'table_execution_update',
  phase: 'execution',  // Frontend triggers UI changes
  current_step: 2,
  status: "Finding rows in Healthcare AI...",
  progress_percent: 45,
  subdomain: "Healthcare AI",
  global_discovered: 8,
  global_target: 15
}
```

### UI Flow

**Step 1 Complete (Columns Defined):**
- Conversation collapses with smooth animation
- Blue box appears: ID Columns (Company Name, Website)
- Purple box appears: Research Columns (Is Hiring?, Team Size)

**Step 3 Complete (Rows Discovered):**
- Orange box appears: Discovered Rows (14 candidates)
- Shows top 10 rows with ID values
- "+4 more rows in full CSV" indicator

**Step 4 Complete (QC Done):**
- Orange box updates: "12 approved of 14 discovered"

**Execution Complete:**
- 2.5s transition: Progress → Pause → Fade
- Auto-trigger preview (no button click needed)
- Preview card appears with CSV template + config

### CSV Download

User can download the CSV template with:
- ID columns filled (Company Name, Website, etc.)
- Other columns empty (ready for manual population or validation)

---

## Troubleshooting

### Common Issues

**0. Zero Rows Found - Autonomous Recovery**

**Symptoms:** Discovery found 0 rows or QC approved 0 rows after reviewing candidates

**What Happens (NEW in v2.4):**
- QC approves 0 rows after reviewing discovered candidates
- **QC makes autonomous decision**: Can this be fixed by restructuring?
- System takes one of two paths automatically (no user input needed)

**Path A: RECOVERABLE - Autonomous Restructure**

**QC Determines:**
- Entities exist but table structure made them hard to discover
- Can fix by: simpler ID columns, relaxed requirements, broader search

**System Actions:**
1. QC provides `restructuring_guidance` with specific instructions
2. Frontend shows friendly message: "Restructuring table with simpler columns..."
3. System restarts from column definition with guidance
4. Retries execution automatically
5. Run status: `IN_PROGRESS` (not failed)

**User Experience:**
- Sees progress message: "I found that the table structure was too specific. I'm restructuring it with simpler columns and broader criteria. Retrying discovery now..."
- No action required - system handles it
- Progress continues as if nothing failed

**Path B: UNRECOVERABLE - Give Up**

**QC Determines:**
- Entities don't exist or are impossible to discover via web search
- Examples: Proprietary data, fabricated topics, contradictory requirements

**System Actions:**
1. QC provides `user_facing_apology` explaining why
2. Frontend shows apology + "Get Started" card for new table
3. Run status: `FAILED`
4. Conversation ends

**User Experience:**
- Sees apology: "I apologize, but I wasn't able to find any rows for this table. This type of information requires proprietary data that isn't publicly available. Would you like to try a different table topic?"
- Sees "Get Started" card to create new table
- Can start fresh with different topic

**Causes:**
- Discovery found few/no candidates matching requirements
- QC rejected all discovered candidates as low quality
- Topic too niche or search strategy too narrow
- Requirements too strict or contradictory
- ID columns too complex or specific
- Request requires proprietary/internal data

**System Behavior (v2.4):**
- QC analyzes subdomain results, search improvements, domain recommendations
- Makes intelligent decision based on evidence
- Provides restructuring guidance if recoverable
- Admits defeat with explanation if unrecoverable
- No user decision-making required
- System will NOT generate empty CSV when 0 rows approved

**Decision Flow:**
```
0 Rows Found → QC Analyzes
                  ↓
      ┌───────────┴────────────┐
      ↓                        ↓
  RECOVERABLE             UNRECOVERABLE
      ↓                        ↓
Restructure + Retry       Apology + New Card
      ↓                        ↓
(Automatic)              (User starts over)
```

**1. Row Discovery Fails - Complex ID Columns**

**Symptoms:** Error messages like "no specific entity results" or "not enough detail to populate required ID fields"

**Causes:**
- ID columns require synthesis (e.g., "Basic Story Description")
- ID columns expect paragraphs instead of short identifiers
- Column definition used research-level complexity for IDs

**Solutions:**
- Review ID columns - should be 1-5 words max
- Use simple identifiers: "Story Headline" not "Story Description"
- Move complex fields to research columns
- Check `column_definition_result.json` in S3 to see what was defined

**Prevention:**
- Interview prompt now guides toward simple ID columns
- Column definition prompt has strict ID column constraints
- Examples show good vs bad ID column choices

**2. No rows discovered despite escalation**

**Symptoms:** `final_rows` is empty after all 3 escalation levels

**Causes:**
- Search queries too specific
- min_match_score threshold too high
- No web search results for queries
- ID columns still too complex (see issue #1)

**Solutions:**
- Check `discovery_result.json` → `stream_results` → `search_improvements`
- Review collected search improvement suggestions
- Check `no_matches_reason` in each subdomain result
- Lower `min_match_score` from 0.6 to 0.5
- Verify ID columns are simple (not complex)

**3. Too many duplicates**

**Symptoms:** Many similar entities after consolidation

**Causes:**
- Fuzzy matching not catching variations
- Different subdomains finding same entities

**Solutions:**
- Review `row_consolidator.py` matching logic
- Check ID column definitions (should be unique identifiers)
- Increase `min_match_score` to filter marginal matches

**4. QC rejects too many rows**

**Symptoms:** Large gap between `final_rows` and `approved_rows`

**Causes:**
- min_qc_score too high
- User requirements unclear
- Discovery finding off-topic entities

**Solutions:**
- Lower `min_qc_score` from 0.5 to 0.4
- Improve column definitions with better descriptions
- Add more context to `table_purpose` and `tablewide_research`

**5. Progressive escalation not working**

**Symptoms:** Always escalates to sonar-pro, even when finding enough

**Causes:**
- `min_candidates_percentage` set too low
- Not finding enough candidates in Level 1

**Solutions:**
- Check `escalation_strategy[0].min_candidates_percentage` (should be 75)
- Review search queries (may be too narrow)
- Check logs for "Early stop" vs "Continue" messages

**6. Search improvements not being applied**

**Symptoms:** Later rounds/subdomains still making same mistakes as earlier ones

**Causes:**
- Search improvements not being collected from responses
- Improvements not being formatted into prompt
- Schema doesn't include search_improvements field

**Solutions:**
- Check `discovery_result.json` → `stream_results[].search_improvements`
- Verify `row_discovery_response.json` schema includes `search_improvements` field
- Check logs for "Collected N search improvement(s)" messages
- Verify prompt template has `{{PREVIOUS_SEARCH_IMPROVEMENTS}}` placeholder

**Debug:**
```bash
# Check if improvements are being collected
aws s3 cp s3://bucket/path/to/discovery_result.json - | jq '.stream_results[].search_improvements'

# Should show arrays of improvement strings from each subdomain
```

### S3 Storage Structure

All table_maker results are stored in S3 at:
```
s3://bucket/tables/{email}/{session_id}/table_maker/{conversation_id}/
```

**Key Files:**
- **`column_definition_result.json`**: Column definitions, search_strategy with subdomains, table_name
- **`discovery_result.json`**: Final rows, stream_results (with search_improvements per subdomain), stats
- **`qc_result.json`**: Approved/rejected rows with QC scores and reasoning

**To retrieve for generating more rows:**
```bash
# Get column definitions
aws s3 cp s3://bucket/tables/email/session/table_maker/conv_id/column_definition_result.json -

# Get search improvements from previous run
aws s3 cp s3://bucket/tables/email/session/table_maker/conv_id/discovery_result.json - | jq '.stream_results[].search_improvements'

# Get approved rows (to avoid re-discovering)
aws s3 cp s3://bucket/tables/email/session/table_maker/conv_id/qc_result.json - | jq '.approved_rows[].id_values'
```

### Debug Logging

**Lambda CloudWatch:**
```bash
# Tail logs
aws logs tail /aws/lambda/interface-lambda --follow

# Search for specific conversation
aws logs filter-pattern "{$.conversation_id = 'abc123'}"

# Find search improvement collection
aws logs filter-pattern "Collected * search improvement" --follow

# Find escalation decisions
aws logs filter-pattern "GLOBAL STOP|LOCAL STOP|Round" --follow
```

### Cost Optimization

**Current costs (typical run with 3-level escalation):**
- Column Definition: $0.002-0.035 (depends on web search)
- Row Discovery: $0.01-0.08 (3-level escalation: sonar → sonar-pro → claude-haiku)
  - Level 1 (sonar-high): $0.005-0.015
  - Level 2 (sonar-pro-high): $0.010-0.030 (if needed)
  - Level 3 (claude-haiku + web): $0.005-0.020 (if needed, rare)
- QC Review: $0.015-0.035
- Config Generation: $0.01-0.03
- **Total: $0.05-0.25** (usually $0.05-0.15 with early stopping)

**To reduce costs:**
1. Increase `min_candidates_percentage` → More early stops
2. Reduce `target_rows` per subdomain → Less discovery needed
3. Use `max_parallel_streams=1` → Sequential (slower but cheaper)
4. Decrease number of subdomains → Fewer API calls

**To improve quality (may increase cost):**
1. Decrease `min_candidates_percentage` → More escalations
2. Increase `target_rows` → More comprehensive discovery
3. Add more subdomains → Better coverage
4. Use `search_context_size: "very_high"` → More context

---

## Next Steps

### Immediate (Already Implemented)

- ✅ Local system working end-to-end
- ✅ Lambda integration complete
- ✅ Config generation in parallel
- ✅ CSV template generation
- ✅ Cost tracking and metrics

### Near-Term Enhancements

**1. Global Counter with Exclusion** ✅ IMPLEMENTED (v2.1)

Cross-subdomain early stopping is now active:
- Tracks `global_counter['total_discovered']` across all subdomains
- Checks before each escalation level: "Do we have enough globally?"
- Logs `[GLOBAL STOP]` when target met
- **Result:** Saves costs by skipping unnecessary escalations

**2. Search Improvements Feedback** ✅ IMPLEMENTED (v2.2)

Continuous learning system now active:
- Each round collects `search_improvements` array
- Improvements propagate to next round within same subdomain
- Improvements propagate to subsequent subdomains
- All improvements saved in `discovery_result.json`
- **Result:** Later searches benefit from earlier learnings

**3. 3-Level Escalation with Claude Fallback** ✅ IMPLEMENTED (v2.2)

Robust escalation strategy now deployed:
- Level 1: sonar (high context) - 75% threshold
- Level 2: sonar-pro (high context) - 90% threshold
- Level 3: claude-haiku-4-5 (3 web searches) - final fallback
- **Result:** Always gets results, even for niche/difficult topics

**4. Strict ID Column Constraints** ✅ IMPLEMENTED (v2.2)

ID column validation now enforced:
- Must be short (1-5 words), simple, repeatable
- Clear guidance in interview and column definition prompts
- Examples show good vs bad ID columns
- **Result:** Prevents row discovery failures from complex ID requirements

**Next enhancement:** Add exclusion list to prevent rediscovery:
```json
{
  "subdomain_exclusions": {
    "Healthcare AI": ["Anthropic"]  // Already found, don't search again
  }
}
```

**5. Phase-Aware Progress** ✅ IMPLEMENTED (v2.1)

Two-phase progress tracking now working:
- **Interview phase:** Dummy messages keep user engaged (10%, 25%, 40%)
- **Execution phase:** Real subdomain updates with running totals
- Frontend uses `phase` field to distinguish and handle appropriately

### Long-Term

**1. Iterative Refinement**

User can refine table after initial generation:
- Add/remove columns
- Re-run discovery with new criteria
- Merge with existing rows

**2. Row Expansion**

Automatically fill data columns using web search:
- "Is Hiring?" → Check careers page
- "Team Size" → LinkedIn company page
- "Recent Funding" → Crunchbase

**3. Multi-Table Workflows**

Generate related tables in sequence:
- Table 1: AI companies
- Table 2: Key people at those companies
- Table 3: Recent products from those companies

---

## Additional Resources

### Detailed Documentation

- **Architecture:** `docs/table_maker/architecture/overview.md`
- **Components:** `docs/table_maker/components/*.md`
- **Configuration:** `docs/table_maker/configuration/config_reference.md`
- **Deployment:** `docs/table_maker/deployment/lambda_integration.md`

### Source Code

- **Lambda Implementation:** `src/lambdas/interface/actions/table_maker/`
- **Core Libraries:** `src/lambdas/interface/actions/table_maker/table_maker_lib/`
- **Archived Standalone:** `temp_unnecessary_files/table_maker/` (deprecated, use Lambda version)

### Key Files

- **Config:** `src/lambdas/interface/actions/table_maker/table_maker_config.json`
- **Prompts:** `src/lambdas/interface/actions/table_maker/prompts/*.md`
- **Schemas:** `src/lambdas/interface/actions/table_maker/schemas/*.json`
- **Execution:** `src/lambdas/interface/actions/table_maker/execution.py`

---

**Questions?** See `docs/table_maker/` for detailed documentation or check the troubleshooting section above.
