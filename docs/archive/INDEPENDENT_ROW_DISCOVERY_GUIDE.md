# Independent Row Discovery System - Complete Guide

**Version:** 1.0
**Date:** October 20, 2025
**Status:** Implemented and Deployed
**Branch:** `table-maker` (merged into main)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [How It Works](#how-it-works)
4. [Components](#components)
5. [Parallel Stream Execution](#parallel-stream-execution)
6. [Deduplication Algorithm](#deduplication-algorithm)
7. [Configuration Options](#configuration-options)
8. [Usage Examples](#usage-examples)
9. [WebSocket Messages](#websocket-messages)
10. [Troubleshooting](#troubleshooting)
11. [Performance Characteristics](#performance-characteristics)

---

## Overview

The Independent Row Discovery system transforms table generation from an iterative refinement process into a **two-phase approval workflow**:

### Phase 1: Interview (Fast, Interactive)
- **Duration:** 1-3 turns, 10-30 seconds per turn
- **Purpose:** Get user approval on WHAT to build
- **Model:** Claude Sonnet 4.5 (no web search)
- **Output:** Table concept sketch and approval decision

### Phase 2: Execution (Slow, Automatic)
- **Duration:** 3-4 minutes
- **Purpose:** Build complete, validated table
- **Model:** Claude Sonnet 4.5 (with web search)
- **Output:** Complete table with all rows populated and validated

### Key Innovation

**Row discovery is separated from table generation**. Instead of the LLM generating rows inline with columns (which produces poor quality), the system:

1. Defines precise column specifications
2. Discovers high-quality rows through **parallel web search streams**
3. Deduplicates and scores candidates
4. Populates data for top-scoring rows only

This eliminates quality drop-off and produces consistent, high-quality results.

---

## Architecture

### Two-Phase Workflow

```
PHASE 1: INTERVIEW (Fast, 1-3 turns)
==========================================
User Request
    |
    v
[Interview Handler]
    |
    +-- No web search
    +-- Fast Sonnet 4.5
    +-- Gather context
    +-- Ask clarifying questions
    |
    v
User Approval? --> No --> Continue conversation
    |
   Yes (trigger_execution=true)
    |
    v
PHASE 2: EXECUTION (Automatic, 3-4 minutes)


PHASE 2: EXECUTION (3-4 minutes, automatic)
==========================================

Step 1: Column Definition (30s)
    |
    v
[Column Definition Handler]
    +-- Define precise column specs
    +-- Create search strategy
    +-- Identify subdomains
    |
    v
Step 2: PARALLEL EXECUTION (90s)
    |
    +---> [Row Discovery]              [Config Generation]
    |     |                            |
    |     +-- Subdomain Analysis       +-- Validation config
    |     +-- Parallel Streams (2-5)   +-- From conversation
    |     +-- Web searches per stream  |
    |     +-- Consolidation            |
    |     +-- Deduplication            |
    |     |                            |
    +<----+----------------------------+
    |
    v
Step 3: Table Population (90s)
    |
    v
[Row Expander]
    +-- Populate data columns
    +-- Batch processing
    +-- Parallel execution
    |
    v
Step 4: Validation (10s)
    |
    v
[Validator]
    +-- Apply validation config
    +-- Confidence scores
    +-- Quality checks
    |
    v
Complete Validated Table
```

---

## How It Works

### The Problem We Solved

**Before:** LLMs generating rows inline with columns produced:
- Great first 3 rows (preview)
- Poor quality additional rows (drop-off)
- No systematic entity discovery
- Inconsistent results

**After:** Independent row discovery produces:
- Consistent quality across ALL rows
- Systematic web search for each subdomain
- Match scoring and deduplication
- Transparent source URLs

### The Solution: Parallel Stream Discovery

Instead of asking the LLM to generate rows, we:

1. **Analyze the domain** - Break into 2-5 natural subdomains
2. **Launch parallel streams** - Each stream searches one subdomain
3. **Score candidates** - Each entity gets 0-1 match score
4. **Consolidate results** - Deduplicate and rank across all streams
5. **Take top N** - Select highest-scoring unique entities

### Example Flow

**User Request:** "Find AI companies that are hiring"

**Step 1 - Column Definition:**
```json
{
  "columns": [
    {"name": "Company Name", "is_identification": true},
    {"name": "Website", "is_identification": true},
    {"name": "Is Hiring for AI?", "importance": "CRITICAL"},
    {"name": "Team Size", "importance": "NORMAL"}
  ],
  "search_strategy": {
    "description": "Find AI/ML companies with active hiring",
    "subdomain_hints": ["AI Research", "Healthcare AI", "Enterprise AI"]
  }
}
```

**Step 2a - Subdomain Analysis:**
```json
{
  "subdomains": [
    {
      "name": "AI Research Companies",
      "focus": "Academic/research-focused AI",
      "search_queries": [
        "AI research labs hiring",
        "machine learning research companies"
      ]
    },
    {
      "name": "Healthcare AI",
      "focus": "AI in healthcare/biotech",
      "search_queries": [
        "healthcare AI companies hiring",
        "medical ML startups"
      ]
    },
    {
      "name": "Enterprise AI",
      "focus": "B2B AI solutions",
      "search_queries": [
        "enterprise AI companies",
        "B2B machine learning hiring"
      ]
    }
  ]
}
```

**Step 2b - Parallel Stream Discovery:**

Three streams run in parallel, each executing web searches and extracting candidates:

*Stream 1 (AI Research):*
- Search: "AI research labs hiring"
- Found: Anthropic (score: 0.95), OpenAI (0.92), DeepMind (0.90)

*Stream 2 (Healthcare AI):*
- Search: "healthcare AI companies hiring"
- Found: Tempus (0.88), Insitro (0.85), PathAI (0.82)

*Stream 3 (Enterprise AI):*
- Search: "enterprise AI companies"
- Found: Scale AI (0.91), Databricks (0.87), Anthropic (0.93)

**Step 2c - Consolidation:**

```
Total candidates: 9
Duplicates: Anthropic appears in Stream 1 (0.95) and Stream 3 (0.93)
  --> Keep highest score: 0.95
  --> Merge source URLs from both streams

Final candidates: 8 unique entities
Filter: min_match_score = 0.6 (all pass)
Sort: By match_score descending
Select: Top 20 (we have 8, all included)
```

**Step 3 - Table Population:**

For each of the 8 discovered rows, populate data columns:
- "Is Hiring for AI?" - Research via web search
- "Team Size" - Research via web search

**Step 4 - Validation:**

Apply validation config to check data quality and assign confidence scores.

**Result:** Complete table with 8 high-quality, deduplicated rows.

---

## Components

### 1. Interview Handler (`interview.py`)

**Purpose:** Gather context and decide WHEN to start execution

**Input:**
- User message
- Conversation history

**Output Schema:**
```json
{
  "trigger_execution": true/false,
  "follow_up_question": "Table proposal in markdown",
  "context_web_research": ["Specific entities to research"],
  "processing_steps": ["Action phrase 1", "Action phrase 2"],
  "table_name": "Title Case Table Name"
}
```

**Configuration:**
```json
{
  "interview": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "use_web_search": false,
    "max_turns": 5,
    "emphasis": "sketch_approval"
  }
}
```

**When to trigger execution:**
- User has clearly described research need
- Scope is well-defined
- No major ambiguities remain

### 2. Column Definition Handler (`column_definition.py`)

**Purpose:** Define precise column specifications and search strategy

**Input:**
- Approved conversation context
- Interview history

**Output Schema:**
```json
{
  "columns": [
    {
      "name": "Company Name",
      "description": "Official company name",
      "format": "String",
      "is_identification": true,
      "importance": "ID"
    },
    {
      "name": "Is Hiring?",
      "description": "Active AI/ML job postings",
      "format": "Boolean",
      "importance": "CRITICAL",
      "validation_strategy": "Check careers page for AI/ML keywords"
    }
  ],
  "search_strategy": {
    "description": "Find AI companies with active hiring",
    "subdomain_hints": ["AI Research", "Healthcare AI"],
    "search_queries": [
      "AI companies hiring ML engineers",
      "artificial intelligence startups jobs"
    ]
  },
  "table_name": "AI Companies Hiring Status",
  "tablewide_research": "Context about AI job market 2025"
}
```

**Key Features:**
- Defines both ID columns and data columns
- Includes validation strategy for each column
- Generates search strategy with subdomain hints
- Uses web search for recent context (3 searches)

**Configuration:**
```json
{
  "column_definition": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "use_web_search": true,
    "web_searches": 3
  }
}
```

### 3. Subdomain Analyzer (`subdomain_analyzer.py`)

**Purpose:** Split search into parallel streams for better coverage

**Input:**
- Search strategy from column definition
- Column specifications

**Output Schema:**
```json
{
  "subdomains": [
    {
      "name": "AI Research",
      "focus": "Academic/research-focused companies",
      "search_queries": ["Query 1", "Query 2"],
      "expected_count": 7
    }
  ],
  "total_subdomains": 3,
  "parallelization_strategy": "Independent streams"
}
```

**Algorithm:**
1. Analyze search strategy description
2. Identify 2-5 natural subdivisions
3. Generate focused queries per subdomain
4. Balance parallelization (don't over-split)

**Configuration:**
```json
{
  "row_discovery": {
    "automatic_subdomain_splitting": true,
    "subdomain_analysis_model": "claude-sonnet-4-5",
    "max_parallel_streams": 5
  }
}
```

### 4. Row Discovery Stream (`row_discovery_stream.py`)

**Purpose:** Find and score candidates in ONE subdomain

**Input:**
- Subdomain definition
- Column specifications
- Search strategy
- Web search limit (3 searches per stream)

**Process:**
1. Execute web searches for subdomain queries
2. Extract candidate entities from search results
3. LLM evaluates each candidate against criteria
4. Score each candidate (0-1 match score)
5. Return scored candidates with rationale

**Output Schema:**
```json
{
  "subdomain": "AI Research Companies",
  "candidates": [
    {
      "id_values": {
        "Company Name": "Anthropic",
        "Website": "anthropic.com"
      },
      "match_score": 0.95,
      "match_rationale": "Leading AI safety research with active ML hiring",
      "source_urls": ["https://anthropic.com/careers", "..."]
    }
  ],
  "total_found": 8,
  "web_searches_used": 2
}
```

**Configuration:**
```json
{
  "row_discovery": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "web_searches_per_stream": 3
  }
}
```

### 5. Row Consolidator (`row_consolidator.py`)

**Purpose:** Deduplicate and prioritize rows from all streams

**Algorithm:**

```python
# 1. Fuzzy Matching on ID Columns
for each candidate pair:
    similarity = fuzzy_match(candidate1.id_values, candidate2.id_values)
    if similarity > 0.85:  # Threshold for "same entity"
        mark as duplicate

# 2. Merge Duplicates
for each duplicate group:
    keep highest match_score
    combine source_urls from all duplicates
    merge match_rationale

# 3. Filter by Score
candidates = [c for c in candidates if c.match_score >= min_match_score]

# 4. Sort by Score
candidates.sort(key=lambda c: c.match_score, reverse=True)

# 5. Take Top N
final_rows = candidates[:target_row_count]
```

**Fuzzy Matching Logic:**
- Normalize: lowercase, remove punctuation
- Compare: "Anthropic" vs "Anthropic Inc." vs "Anthropic PBC"
- Similarity metrics: Levenshtein distance, token overlap
- Threshold: 0.85 = same entity

**Output Schema:**
```json
{
  "final_rows": [
    {
      "id_values": {...},
      "match_score": 0.95,
      "merged_from": ["Stream 1 candidate", "Stream 3 candidate"],
      "source_urls": ["url1", "url2", "url3"]
    }
  ],
  "deduplication_stats": {
    "total_candidates": 45,
    "duplicates_removed": 12,
    "below_threshold": 3,
    "final_count": 20
  }
}
```

**Configuration:**
```json
{
  "row_discovery": {
    "target_row_count": 20,
    "min_match_score": 0.6
  }
}
```

### 6. Row Discovery Orchestrator (`row_discovery.py`)

**Purpose:** Coordinate parallel row discovery

**Process:**
```python
async def discover_rows(search_strategy, columns):
    # 1. Analyze subdomains
    subdomains = await subdomain_analyzer.analyze(search_strategy)

    # 2. Launch parallel streams
    tasks = [
        row_discovery_stream.discover(subdomain, columns)
        for subdomain in subdomains
    ]

    # 3. Collect results (max 5 concurrent)
    results = await asyncio.gather(*tasks)

    # 4. Consolidate
    final_rows = row_consolidator.consolidate(results)

    return final_rows
```

**Configuration:**
```json
{
  "row_discovery": {
    "max_parallel_streams": 5
  }
}
```

### 7. Execution Orchestrator (`execution.py`)

**Purpose:** Run complete Phase 2 pipeline

**Pipeline Steps:**

```python
async def execute_full_table_generation(conversation_id):
    # Step 1: Column Definition (30s)
    columns = await column_definition.define(conversation_id)

    # Step 2: PARALLEL (90s)
    rows_task = row_discovery.discover(columns['search_strategy'])
    config_task = config_generator.generate(conversation_context)

    rows, config = await asyncio.gather(rows_task, config_task)

    # Step 3: Table Population (90s)
    table = await row_expander.populate(columns, rows)

    # Step 4: Validation (10s)
    validated = await validator.validate(table, config)

    return validated
```

**WebSocket Updates:**
- Step 0: "Execution starting"
- Step 1: "Defining columns..." (0-25%)
- Step 2: "Discovering rows..." (25-50%)
- Step 3: "Populating table..." (50-75%)
- Step 4: "Validating..." (75-100%)

---

## Parallel Stream Execution

### Why Parallel Streams?

**Problem:** Single web search finds limited entities
**Solution:** Multiple parallel searches across subdomains

**Benefits:**
1. **Better Coverage** - Each subdomain gets dedicated searches
2. **Higher Quality** - Focused queries find better matches
3. **Faster Execution** - Parallel execution saves time
4. **Diversity** - Captures entities from different angles

### Stream Execution Model

```
Subdomain Analysis
    |
    v
Launch 3 Parallel Streams
    |
    +---> Stream 1: "AI Research"
    |     |
    |     +-- Search 1: "AI research labs hiring"
    |     +-- Search 2: "ML research companies"
    |     +-- Extract: 8 candidates
    |     +-- Score: 0.85 - 0.95
    |     |
    +---> Stream 2: "Healthcare AI"
    |     |
    |     +-- Search 1: "healthcare AI companies"
    |     +-- Search 2: "medical ML startups"
    |     +-- Extract: 6 candidates
    |     +-- Score: 0.75 - 0.90
    |     |
    +---> Stream 3: "Enterprise AI"
          |
          +-- Search 1: "enterprise AI hiring"
          +-- Search 2: "B2B ML companies"
          +-- Extract: 7 candidates
          +-- Score: 0.80 - 0.92
          |
    <-----+
    |
    v
Consolidation: 21 candidates --> 18 unique --> Top 20 selected
```

### Concurrency Control

**Configuration:**
```json
{
  "row_discovery": {
    "max_parallel_streams": 5
  }
}
```

**Why limit to 5?**
- API rate limits
- Diminishing returns (over-splitting reduces quality)
- Resource constraints

**Stream Count Logic:**
```python
if num_subdomains <= 5:
    # Run all in parallel
    streams = num_subdomains
else:
    # Run top 5 most promising
    streams = 5
```

---

## Deduplication Algorithm

### The Challenge

Parallel streams find the same entities with different names:
- "Anthropic" (Stream 1)
- "Anthropic Inc." (Stream 3)
- "Anthropic PBC" (Stream 3)

All refer to the same company!

### Fuzzy Matching Algorithm

```python
def fuzzy_match(id_values_1, id_values_2, threshold=0.85):
    """
    Determine if two sets of ID values represent the same entity.

    Args:
        id_values_1: {"Company Name": "Anthropic", "Website": "anthropic.com"}
        id_values_2: {"Company Name": "Anthropic Inc.", "Website": "anthropic.com"}
        threshold: Similarity threshold (0-1)

    Returns:
        bool: True if same entity
    """
    scores = []

    for id_col in id_values_1.keys():
        val1 = normalize(id_values_1[id_col])
        val2 = normalize(id_values_2[id_col])

        # Exact match
        if val1 == val2:
            scores.append(1.0)
            continue

        # Fuzzy string matching
        similarity = levenshtein_ratio(val1, val2)
        scores.append(similarity)

    # Average similarity across all ID columns
    avg_similarity = sum(scores) / len(scores)

    return avg_similarity >= threshold


def normalize(text):
    """Normalize text for comparison."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
    text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace

    # Remove common suffixes
    for suffix in ['inc', 'llc', 'ltd', 'corp', 'corporation', 'pbc']:
        text = re.sub(rf'\b{suffix}\b', '', text)

    return text.strip()
```

### Merging Strategy

When duplicates are found:

```python
def merge_duplicates(duplicate_group):
    """
    Merge multiple candidates that represent the same entity.

    Args:
        duplicate_group: List of candidates flagged as duplicates

    Returns:
        Single merged candidate
    """
    # Keep highest match score
    best_candidate = max(duplicate_group, key=lambda c: c['match_score'])

    # Combine source URLs from all duplicates
    all_urls = []
    for candidate in duplicate_group:
        all_urls.extend(candidate.get('source_urls', []))
    best_candidate['source_urls'] = list(set(all_urls))

    # Merge rationales
    all_rationales = [c['match_rationale'] for c in duplicate_group]
    best_candidate['match_rationale'] = combine_rationales(all_rationales)

    # Track merge metadata
    best_candidate['merged_from'] = [
        c.get('subdomain', 'unknown') for c in duplicate_group
    ]

    return best_candidate
```

### Example Deduplication

**Input Candidates:**
```
Stream 1: Anthropic (0.95)
Stream 2: OpenAI (0.92)
Stream 2: DeepMind (0.90)
Stream 3: Anthropic Inc. (0.93)  # DUPLICATE
Stream 3: Google DeepMind (0.88)  # DUPLICATE
Stream 3: Scale AI (0.91)
```

**Fuzzy Matching:**
```
"Anthropic" vs "Anthropic Inc."
  normalize("Anthropic") = "anthropic"
  normalize("Anthropic Inc.") = "anthropic"
  similarity = 1.0 --> DUPLICATE

"DeepMind" vs "Google DeepMind"
  normalize("DeepMind") = "deepmind"
  normalize("Google DeepMind") = "google deepmind"
  similarity = 0.87 --> DUPLICATE (above 0.85 threshold)
```

**Merged Results:**
```
1. Anthropic (0.95) - merged from Stream 1 & 3
2. OpenAI (0.92)
3. Scale AI (0.91)
4. DeepMind (0.90) - merged from Stream 2 & 3
```

**Statistics:**
```json
{
  "total_candidates": 6,
  "duplicates_removed": 2,
  "final_count": 4
}
```

---

## Configuration Options

### Complete Configuration

See `table_maker_config.json` for all settings.

### Interview Phase

```json
{
  "interview": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "use_web_search": false,
    "max_turns": 5,
    "emphasis": "sketch_approval"
  }
}
```

**Parameters:**
- `model` - AI model for interview (Sonnet 4.5 recommended)
- `max_tokens` - Token limit per call
- `use_web_search` - Disable for fast interview
- `max_turns` - Max conversation turns before forcing decision
- `emphasis` - "sketch_approval" or "detailed_refinement"

### Row Discovery

```json
{
  "row_discovery": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "target_row_count": 20,
    "min_match_score": 0.6,
    "max_parallel_streams": 5,
    "web_searches_per_stream": 3,
    "automatic_subdomain_splitting": true
  }
}
```

**Parameters:**
- `target_row_count` - Desired number of final rows (default: 20)
- `min_match_score` - Minimum quality threshold 0-1 (default: 0.6)
- `max_parallel_streams` - Max concurrent subdomain searches (default: 5)
- `web_searches_per_stream` - Web searches per subdomain (default: 3)
- `automatic_subdomain_splitting` - Auto-detect subdomains (default: true)

### Table Population

```json
{
  "table_population": {
    "model": "claude-sonnet-4-5",
    "max_tokens": 16000,
    "batch_size": 10,
    "parallel_batches": 2,
    "use_web_search": true
  }
}
```

**Parameters:**
- `batch_size` - Rows processed per batch (default: 10)
- `parallel_batches` - Number of parallel batches (default: 2)
- `use_web_search` - Enable web search for data population (default: true)

### Execution Pipeline

```json
{
  "execution": {
    "total_steps": 4,
    "estimated_duration_seconds": 240,
    "enable_parallel_step2": true
  }
}
```

---

## Usage Examples

### Example 1: Simple Request

**User:** "Find AI companies that are hiring"

**Interview Turn 1:**
```
AI: "I'll create a table tracking AI companies and their hiring status.

**Table Structure:**
- ID Columns: Company Name, Website
- Research Questions:
  - Is hiring for AI/ML roles?
  - Number of AI job postings
  - Recent funding
  - Company focus area

I'll find approximately 20 AI companies across research, healthcare, and enterprise sectors.

Does this match your needs?"
```

**User:** "Yes, go ahead"

**Execution (4 minutes):**
```
[Step 1/4] Defining columns and search strategy... (30s)
[Step 2/4] Discovering 20 companies across 3 sectors... (90s)
  - AI Research: 8 companies found
  - Healthcare AI: 6 companies found
  - Enterprise AI: 9 companies found
  - Deduplication: 23 --> 20 unique companies
[Step 3/4] Populating data for 20 companies... (90s)
[Step 4/4] Validating results... (10s)
```

**Result:** Complete table with 20 companies, all columns filled, validated.

### Example 2: Refinement Request

**User:** "Find companies in the generative AI space"

**Interview Turn 1:**
```
AI: "I'll create a table of generative AI companies.

**Table Structure:**
- ID Columns: Company Name, Website
- Research Questions:
  - Primary product (text, image, video, audio)
  - Business model (API, SaaS, Enterprise)
  - Recent funding
  - Team size

Approximately 20 companies in GenAI.

Does this match your needs?"
```

**User:** "Also add whether they have open source models"

**Interview Turn 2:**
```
AI: "Updated! Added 'Has Open Source Models' column.

**Table Structure:**
- ID Columns: Company Name, Website
- Research Questions:
  - Primary product
  - Business model
  - Has open source models? (Yes/No)
  - Recent funding
  - Team size

Ready to proceed?"
```

**User:** "Yes"

**Execution:** Same 4-step pipeline as Example 1.

---

## WebSocket Messages

### Phase 1: Interview

**Message Type:** `table_conversation_update`

**Interview Turn Complete (Not Ready):**
```json
{
  "type": "table_conversation_update",
  "conversation_id": "table_conv_123",
  "progress": 100,
  "status": "Interview turn 1 complete",
  "trigger_execution": false,
  "follow_up_question": "Does this match your needs?",
  "table_name": "AI Hiring Companies",
  "processing_steps": [
    "Define search strategy",
    "Discover companies",
    "Research hiring status",
    "Validate data"
  ]
}
```

**Interview Turn Complete (Ready to Execute):**
```json
{
  "type": "table_conversation_update",
  "conversation_id": "table_conv_123",
  "progress": 100,
  "status": "Interview complete, ready to execute",
  "trigger_execution": true,
  "follow_up_question": "Here's what I'll create: [markdown table proposal]",
  "table_name": "AI Hiring Companies",
  "processing_steps": [...]
}
```

### Phase 2: Execution

**Message Type:** `table_execution_update`

**Execution Start:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_123",
  "current_step": 0,
  "total_steps": 4,
  "status": "Execution starting",
  "progress_percent": 0,
  "estimated_duration_seconds": 240
}
```

**Step 1 Progress:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_123",
  "current_step": 1,
  "total_steps": 4,
  "status": "Step 1/4: Defining columns and search strategy...",
  "progress_percent": 5
}
```

**Step 1 Complete:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_123",
  "current_step": 1,
  "total_steps": 4,
  "status": "Step 1/4 complete: Columns and search strategy defined",
  "progress_percent": 25,
  "columns_defined": 7
}
```

**Step 2 Progress:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_123",
  "current_step": 2,
  "total_steps": 4,
  "status": "Step 2/4: Discovering rows across 3 sectors...",
  "progress_percent": 30,
  "detail": "Found 12 candidates so far"
}
```

**Step 2 Complete:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_123",
  "current_step": 2,
  "total_steps": 4,
  "status": "Step 2/4 complete: Rows discovered and config generated",
  "progress_percent": 50,
  "rows_discovered": 20
}
```

**Step 3 & 4:** Similar pattern

**Execution Complete:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_123",
  "current_step": 4,
  "total_steps": 4,
  "status": "Execution complete! Table is ready.",
  "progress_percent": 100,
  "table_data": {...},
  "validation_summary": {...}
}
```

**Execution Error:**
```json
{
  "type": "table_execution_update",
  "conversation_id": "table_conv_123",
  "current_step": 2,
  "total_steps": 4,
  "status": "Failed at step 2: Row discovery timeout",
  "progress_percent": 50,
  "error": "Row discovery timeout after 120s",
  "failed_at_step": 2
}
```

---

## Troubleshooting

### Issue: No Rows Discovered

**Symptoms:** Step 2 completes with 0 rows found

**Possible Causes:**
1. Search queries too specific
2. Min match score too high
3. Web search API errors

**Solutions:**
```json
// Lower match score threshold
{
  "row_discovery": {
    "min_match_score": 0.5  // Was 0.6
  }
}

// Increase searches per stream
{
  "row_discovery": {
    "web_searches_per_stream": 5  // Was 3
  }
}
```

**Check Logs:**
```
[ROW_DISCOVERY] Total candidates before filtering: 45
[ROW_DISCOVERY] Candidates after min_match_score filter: 0
--> All candidates scored below 0.6 threshold
```

### Issue: Too Many Duplicates

**Symptoms:** Deduplication removes 80%+ of candidates

**Possible Causes:**
1. Subdomains overlap too much
2. Search queries too similar
3. Fuzzy match threshold too low

**Solutions:**
```python
# Adjust fuzzy match threshold
ROW_CONSOLIDATOR_CONFIG = {
    "fuzzy_match_threshold": 0.90  # Was 0.85 (stricter matching)
}
```

**Check Logs:**
```
[CONSOLIDATOR] Fuzzy match: "Anthropic" vs "Anthropic Inc" = 1.0 (duplicate)
[CONSOLIDATOR] Fuzzy match: "OpenAI" vs "OpenAI LP" = 0.95 (duplicate)
```

### Issue: Execution Timeout

**Symptoms:** Step 2 or 3 times out after 300s

**Possible Causes:**
1. Too many parallel streams
2. Web search API slow
3. Complex column definitions

**Solutions:**
```json
// Reduce parallelism
{
  "row_discovery": {
    "max_parallel_streams": 3  // Was 5
  }
}

// Reduce batch size for population
{
  "table_population": {
    "batch_size": 5,  // Was 10
    "parallel_batches": 1  // Was 2
  }
}
```

### Issue: Poor Quality Rows

**Symptoms:** Rows have low relevance or wrong entities

**Possible Causes:**
1. Column definitions too vague
2. Search strategy not specific enough
3. Match scoring logic incorrect

**Solutions:**

**1. Improve Column Definitions:**
```json
// Before (vague)
{
  "name": "Company Name",
  "description": "The company"
}

// After (specific)
{
  "name": "Company Name",
  "description": "Official legal name of AI company with active ML hiring",
  "validation_strategy": "Verify company exists and has AI/ML focus"
}
```

**2. Refine Search Strategy:**
```json
// Before (broad)
{
  "search_queries": ["AI companies"]
}

// After (specific)
{
  "search_queries": [
    "AI companies actively hiring machine learning engineers 2025",
    "artificial intelligence startups with open ML positions"
  ]
}
```

**Check Logs:**
```
[ROW_DISCOVERY_STREAM] Candidate: "Tesla"
  Match score: 0.45 (below threshold 0.6)
  Rationale: "Has AI team but not primarily AI company"
  --> Correctly filtered out
```

### Issue: Validation Failures

**Symptoms:** Step 4 validation marks many cells as low confidence

**Possible Causes:**
1. Data sources unreliable
2. Validation config too strict
3. Missing data

**Solutions:**
```json
// Adjust validation threshold
{
  "validation": {
    "confidence_threshold": 0.6  // Was 0.7 (more lenient)
  }
}
```

---

## Performance Characteristics

### Typical Execution Times

| Step | Operation | Duration | Notes |
|------|-----------|----------|-------|
| 0 | Interview | 10-30s | Per turn, varies with user |
| 1 | Column Definition | 20-40s | Includes 3 web searches |
| 2a | Row Discovery | 60-120s | 3-5 parallel streams |
| 2b | Config Generation | 60-90s | Parallel with 2a |
| 3 | Table Population | 60-120s | Depends on row count |
| 4 | Validation | 5-15s | Simple validation |
| **Total** | **Complete Pipeline** | **3-5 min** | From approval to table |

### Resource Usage

**API Calls per Execution:**
```
Interview:           1-3 calls (no web search)
Column Definition:   1 call + 3 web searches
Subdomain Analysis:  1 call
Row Discovery:       3-5 calls (parallel streams) + 9-15 web searches
Config Generation:   1 call
Table Population:    2-4 calls (batched)
Validation:          1 call
--------------------------
Total:              10-17 API calls
Total Web Searches: 9-18 searches
```

**Cost Estimate (Sonnet 4.5):**
```
Interview:          $0.01 - $0.03
Column Definition:  $0.02 + $0.03 (searches)
Row Discovery:      $0.08 - $0.15 + $0.09-$0.15 (searches)
Config Generation:  $0.02
Table Population:   $0.10 - $0.20
Validation:         $0.01
--------------------------
Total per table:    $0.33 - $0.73
```

### Scaling Characteristics

**Row Count Impact:**
- 10 rows: ~2.5 min total
- 20 rows: ~4 min total
- 50 rows: ~8 min total
- 100 rows: ~15 min total

**Column Count Impact:**
- 5 columns: Normal speed
- 10 columns: +20% time
- 20 columns: +50% time

**Web Search Impact:**
- 3 searches/stream: Baseline
- 5 searches/stream: +30% time, +20% cost
- 10 searches/stream: +70% time, +40% cost

---

## Best Practices

### 1. Interview Phase

**DO:**
- Keep questions focused and specific
- Use A/B style questions when unclear
- Infer reasonable defaults
- Trigger execution when 80% clear

**DON'T:**
- Ask too many clarifying questions
- Wait for perfect information
- Get stuck in refinement loop

### 2. Column Definitions

**DO:**
- Include validation strategy for each column
- Mark ID columns clearly
- Use specific, actionable descriptions
- Define importance levels

**DON'T:**
- Create vague column descriptions
- Skip validation strategies
- Mix ID and data columns

### 3. Search Strategy

**DO:**
- Include subdomain hints
- Use specific, recent search queries
- Focus on findability
- Consider multiple angles

**DON'T:**
- Use overly broad queries
- Create too many subdomains (3-5 is optimal)
- Ignore temporal aspects (add "2025" for recent)

### 4. Row Discovery

**DO:**
- Set realistic target_row_count
- Use appropriate min_match_score (0.6 is good default)
- Enable automatic subdomain splitting
- Monitor deduplication stats

**DON'T:**
- Request 100+ rows in first attempt
- Set min_match_score too high (>0.8)
- Disable automatic subdomain splitting
- Ignore duplicate warnings

### 5. Error Handling

**DO:**
- Check logs for specific error messages
- Retry with adjusted parameters
- Fall back to fewer parallel streams if timeout
- Validate inputs before execution

**DON'T:**
- Retry immediately without changes
- Ignore warning messages
- Skip validation step

---

## See Also

- [API Reference](API_REFERENCE_ROW_DISCOVERY.md) - Technical API documentation
- [Migration Guide](MIGRATION_GUIDE_ROW_DISCOVERY.md) - Upgrading from preview/refinement
- [Implementation Complete](TABLE_MAKER_IMPLEMENTATION_COMPLETE.md) - Full system overview
- [Infrastructure Guide](INFRASTRUCTURE_GUIDE.md) - Deployment and infrastructure

---

**Last Updated:** October 20, 2025
**Version:** 1.0
**Authors:** Table Maker Implementation Team
