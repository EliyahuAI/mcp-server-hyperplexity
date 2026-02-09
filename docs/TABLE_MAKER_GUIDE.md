# Table Maker - Independent Row Discovery System

**Version:** 2.8.2 (Strict Dedup + Prepopulated Row QC + ID Sorting)
**Last Updated:** February 9, 2026
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
User Request → Interview → Background Research → Table Extraction → Column Definition → Row Discovery → QC Review → CSV + Config
                                (Step 0)            (Step 0b)           (Step 1)          (Step 2)       (Step 3)
                           Find sources        Extract tables     Generate rows     Merge initial
                           Identify tables     (if needed)        Decide trigger    + discovered
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

## What's New in Version 2.8.2

### Strict Deduplication - Evident Uniqueness Required (QUALITY ENHANCEMENT)
**Problem:** Near-duplicate rows were passing QC review, resulting in redundant entries (e.g., "EarPopper" and "Ear Popper" both appearing).

**Solution:** QC now requires **evident uniqueness** for every row. The burden of proof is on uniqueness, not on duplication.

**Key Changes:**
- **Aggressive cross-set dedup** - QC checks for duplicates across BOTH pre-existing and discovered rows
- **When in doubt, REMOVE** - Better to have fewer unique rows than near-duplicates
- **Expanded duplicate detection** - Covers name variants, trademark symbols, abbreviations, subsidiaries, spelling differences

### QC Can Now Remove Pre-existing Rows (BREAKING CHANGE)
**Problem:** Pre-existing rows from column definition were "PRE-APPROVED" and could never be removed, even when duplicated by discovered rows or irrelevant.

**Solution:** QC now reviews ALL rows (both pre-existing and discovered) and can flag pre-existing rows for removal.

**Key Changes:**
- **`remove_prepopulated_row_ids`** - New QC output field listing P-prefixed row_ids to remove from pre-existing rows
- **P-prefixed row_ids** - Pre-existing rows now have row_ids like `P1-Anthropic`, `P2-OpenAI` in the QC prompt
- **Cross-set dedup** - If same entity appears in both pre-existing and discovered, the more complete version is kept
- **Execution filtering** - `_filter_prepopulated_rows()` removes flagged rows before merge

### A-Z ID Column Sorting (OUTPUT ENHANCEMENT)
**Problem:** Final rows had no consistent ordering, making tables harder to read.

**Solution:** All final rows are sorted alphabetically (A-Z) by ID columns, right to left.

**Sort Order:** For columns `[Company, Category, Subcategory]`:
- Primary sort: Subcategory (A-Z)
- Secondary sort: Category (A-Z)
- Tertiary sort: Company (A-Z)

Applies to both skip mode (no discovery) and normal mode (after QC merge).

### Missing ID Column Rejection (QUALITY ENHANCEMENT)
**Problem:** Rows with placeholder ID values ("Unknown", "N/A", "-") were passing through.

**Solution:** Rows with ANY missing or placeholder ID column value are automatically removed.

**Rejected values:** empty, "Unknown", "N/A", "TBD", "-", "None", "?", "null"

**New QC Output Format (v2.8.2):**
```json
{
  "action": "filter",
  "keep_row_ids_in_order": ["1-Anthropic", "2-OpenAI"],
  "remove_prepopulated_row_ids": ["P5-OldCompany"],
  "removal_reasons": {"3-FakeCompany": "Duplicate of row 1", "P5-OldCompany": "Duplicate of discovered 2-OpenAI"},
  "overall_score": 0.85
}
```

---

## What's New in Version 2.8

### Unified Row Discovery Output Format (MAJOR ENHANCEMENT)
**Problem:** Row discovery used different columns than column_definition, citations were lost during parsing, QC rewrote entire rows instead of filtering, and parallel subdomains had colliding citation numbers.

**Solution:** Unified output format with citation tracking across the entire pipeline.

**Key Changes:**
- **Same columns everywhere** - Row discovery outputs ALL columns (ID + RESEARCH) matching column_definition
- **Inline citations preserved** - Citations `[n]` are tracked per-cell and flow through to final output
- **Citation numbering coordination** - Global counter prevents collisions across subdomains and retrigger cycles
- **QC simplified** - Rows kept by default, only specify `remove_row_ids` (no more rewriting full table)
- **Separate scoring array** - Scoring data moved out of markdown table for cleaner parsing

**New Row Discovery Output Format:**
```json
{
  "subdomain": "AI Research Companies",
  "candidates_markdown": "| Company Name | CEO Name | Funding |\n|---|---|---|\n| Anthropic[1] | Dario Amodei[1][2] | $7.3B[3] |",
  "citations": {
    "1": "https://anthropic.com/about",
    "2": "https://en.wikipedia.org/wiki/Dario_Amodei",
    "3": "https://crunchbase.com/anthropic"
  },
  "scoring": [
    {"row_id": "Anthropic", "relevancy": 0.95, "reliability": 1.0, "recency": 0.9, "rationale": "Leading AI safety company"}
  ]
}
```

**New QC Output Format:**
```json
{
  "action": "filter",
  "remove_row_ids": [
    {"row_id": "3-FakeCompany", "reason": "Not a real Fortune 500 company"}
  ],
  "overall_score": 0.85
}
```

**Citation Flow:**
```
Column Definition (citations 1-10)
    ↓
Row Discovery Subdomain A (citations 11-20)
    ↓
Row Discovery Subdomain B (citations 21-30)
    ↓
QC Review (prunes unused citations)
    ↓
Final Output (all citations preserved with correct numbering)
```

**Benefits:**
- Cell-level citation tracking enables Excel footnotes
- No citation collisions in parallel or retrigger scenarios
- QC filtering is faster (no table rewriting)
- Research column data discovered during row discovery is preserved

---

## What's New in Version 2.7

### Unified Rows Model (MAJOR SIMPLIFICATION)
**Problem:** Artificial split between `complete_rows` and `sample_rows` created confusion
**Solution:** Column definition always generates `rows` (as many as possible), then decides if discovery needed

**Key Changes:**
- **Single `rows` field** - No more complete_rows vs sample_rows split
- **Always populate data** - Fill both ID AND research columns when data available
- **`trigger_row_discovery` boolean** - Simple yes/no decision
- **Flexible combinations** - Can provide 30 rows AND trigger discovery for 20 more
- **Smarter column definition** - Generates rows from extracted_tables, starting_tables, conversation, or model knowledge

**Example Flow:**
```
Column Definition receives Forbes AI 50 table (50 companies with funding data)
→ Generates 50 rows with: Company Name, Website, Funding, Description (populated)
→ Still needs: Employee Count, Has Job Posting (empty)
→ Sets trigger_row_discovery=true
→ Provides discovery_guidance: "Have 50 rows with basic data. Need to populate Employee Count and Has Job Posting for all rows"
→ Row Discovery: Validates existing 50 rows to fill missing columns
→ Result: 50 rows with ALL columns populated
```

### Table Extraction (Step 0b) - Sequential After Background Research
**New optional step for extracting complete tables from identified URLs**

**When Triggered:**
- Background research identifies specific table URLs with structure
- User requests data from specific document/URL
- Complete enumeration needed but requires web access

**How It Works:**
1. Step 0 outputs `identified_tables` with URLs and structure
2. Step 0b extracts ALL rows from those tables
3. Uses site-specific search (include_domains from URL)
4. Results flow to column definition as `extracted_tables`
5. Column definition uses for JUMP START (generate complete rows)

**Benefits:**
- Separates research (patterns/context) from extraction (complete data)
- Site-specific search improves extraction accuracy
- Handles pagination and structured tables
- Optional: only runs when needed
- Enables JUMP START with rich pre-populated data

### Focused Search Instructions (All Prompts)
**All prompts now lead with focused task in first 10-15 lines:**

- **background_research.md** - Leads with "SEARCH FOR: [research questions]"
- **row_discovery.md** - Leads with subdomain + requirements + source + queries
- **column_definition.md** - Leads with data sources + unified rows task

**Benefits:**
- Fast models see task immediately
- Reduces irrelevant searches
- Clearer prompt structure

---

## What's New in Version 2.6

### Complete Rows Mode - Skip Row Discovery (NEW FEATURE)
- **Two Skip Modes**: Complete enumeration OR jump start from starting tables
- **Skips Row Discovery & QC**: When enabled, saves 60-120s and $0.05-0.15 per table
- **AI Decision**: Column definition AI autonomously decides when to use each mode
- **Safe Default**: When in doubt, AI runs normal row discovery flow

#### Mode 1: Complete Enumeration (Well-Known Lists)
For obvious, exhaustive, well-defined lists that don't require web research.

**Examples:**
- ✅ Items from a specific document (references, chapters, sections, authors)
- ✅ Geographic/political entities (countries in a region, states, provinces)
- ✅ Well-defined finite sets (planets, elements, calendar units)
- ✅ Official rosters (cabinet members, board members, committee members)

#### Mode 2: JUMP START (Perfect Starting Table Match)
**MAJOR VALUE:** When background research found a reliable starting table that perfectly matches user request.

**How It Works:**
1. Background research finds authoritative starting table (Forbes list, NIH database, Wikipedia list)
2. Column definition AI recognizes starting table perfectly matches user intent
3. AI directly copies ALL rows with ALL available columns from starting table
4. Rows go straight to CSV with research columns pre-filled
5. Saves 60-120s + gives user pre-populated data columns

**Examples:**
- ✅ Background research found authoritative ranked list that matches user's request perfectly
- ✅ Background research found official database/registry with all needed entities
- ✅ Background research found curated directory with comprehensive entity details

**Key Benefit:** Not just faster - user gets a **pre-populated table** with descriptions, URLs, dates, and other data already filled in from the authoritative source!

**Examples Where Row Discovery Still Needed:**
- ❌ Open-ended discovery (dynamic, constantly changing entities) - **unless** perfect starting table exists (then use JUMP START)
- ❌ Broad topic searches (requires web search for entity discovery)
- ❌ Real-time data (needs active discovery)

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

### Strategic Subdomain Scaling (2-5 Subdomains)
- **Lambda Timeout Protection**: Subdomain max limited to 5 to ensure completion within Lambda's 15-minute timeout
- **Adaptive Scaling**: More subdomains for challenging/niche topics (up to limit)
- **Decision Matrix**: Clear guidelines for when to use 2-3 vs 4-5 subdomains
- **Examples**: Fortune 500 (2-3) vs Government AI Initiatives (5 max)

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
- **Clear Guidelines**: When to use 2-3 vs 4-5 subdomains (max 5 for Lambda timeout)

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

### The Pipeline (Step 0/0b Internal, Step 2 Conditional)

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 0: Background Research (~30-60s) INTERNAL                  │
│  • Answer tablewide research questions                          │
│  • Find authoritative sources (databases, directories)          │
│  • Extract 5-15 sample entities in starting_tables              │
│  • Identify extractable tables for Step 0b                      │
│  • Model: sonar-pro (configurable)                              │
│  • On restructure: ALWAYS cached and reused                     │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 0b: Table Extraction (OPTIONAL, ~20-40s) SEQUENTIAL       │
│  • Triggered if Step 0 identified extractable tables            │
│  • Extracts ALL rows from table URLs                            │
│  • Uses site-specific search (include_domains)                  │
│  • Output: extracted_tables with complete data                  │
│  • Model: sonar (fast extraction)                               │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Column Definition (~10-20s)                             │
│  • Design table structure using research                        │
│  • Generate rows from ALL available sources:                    │
│    - extracted_tables (Step 0b)                                 │
│    - starting_tables (samples or complete enumeration)          │
│    - Conversation (user pasted text)                            │
│    - Model knowledge (well-known finite sets)                   │
│  • Populate ALL columns with reliable data (ID + research)      │
│  • Decide: trigger_row_discovery (true/false)                   │
│  • Model: gemini-2.5-flash (fast, no web search needed)         │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                   ┌────────┴────────┐
                   │ trigger_row_     │
                   │  discovery?      │
                   └────────┬────────┘
                            │
              ┌─────────────┴─────────────┐
              │ NO                        │ YES
              ↓                           ↓
     ┌────────────────────┐      ┌─────────────────────────────────────┐
     │ SKIP Step 2        │      │ Step 2: Row Discovery + Config Gen  │
     │                    │      │  • Row Discovery (60-120s)          │
     │ Use initial rows   │      │  • Uses discovery_guidance          │
     │ (already complete) │      │  • 3-Level escalation               │
     │                    │      │  • Merge initial + discovered rows  │
     │ Saves 60-120s      │      │  • Citation tracking across streams │
     │                    │      │  • Outputs: candidates_markdown +   │
     │                    │      │    citations dict + scoring array   │
     │                    │      └──────────┬──────────────────────────┘
     └────────┬───────────┘                 ↓
              │                  ┌─────────────────────────────────────┐
              │                  │ Step 3: QC Review                   │
              │                  │  • Review merged rows (with row_ids)│
              │                  │  • Rows KEPT by default (v2.8)      │
              │                  │  • Only specify remove_row_ids      │
              │                  │  • Prune unused citations           │
              │                  │  • Autonomous recovery if 0 rows    │
              │                  └──────────┬──────────────────────────┘
              │                             │
              └─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Mutual Completion: Wait for Config + Generate CSV               │
│  • Wait for config generation to finish                         │
│  • Generate CSV with populated columns                          │
│  • Ready for validation workflow                                │
└─────────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Background Research First** (Step 0): Find authoritative sources before designing table structure
2. **Table Extraction** (Step 0b): Extract complete tables from identified URLs when available
3. **Unified Rows Model** (v2.7): Column definition always generates rows, decides if discovery needed
4. **Populate All Columns**: Fill both ID AND research columns when data available (not just IDs)
5. **Flexible Triggers**: Can provide 30 rows AND trigger discovery for 20 more (not either/or)
6. **Design for Discoverability**: Table structure determines if rows can be found
7. **Support Columns Strategy**: Break complex validations into discoverable steps
8. **Research Caching**: Always reuse research on restructure (mandatory optimization)
9. **Progressive Escalation**: Start with sonar-pro, escalate to claude-haiku if needed
10. **Continuous Learning**: Search improvements feed back into subsequent rounds
11. **Initial + Discovered Rows**: Column definition provides initial rows, discovery appends/merges
12. **Quality Over Quantity**: QC layer ensures relevance
13. **Simple ID Columns**: Short, repeatable identifiers (1-5 words)
14. **Strategic Overshooting**: Target 30-50% more rows to ensure delivery after QC
15. **Unified Output Format** (v2.8): Row discovery outputs same columns as column_definition
16. **Citation Tracking** (v2.8): Global citation counter prevents collisions across subdomains
17. **QC Simplification** (v2.8): Rows kept by default, only specify removals
18. **Strict Deduplication** (v2.8.2): Every row must be evidently unique, when in doubt remove
19. **QC Reviews All Rows** (v2.8.2): QC can remove pre-existing rows via `remove_prepopulated_row_ids`
20. **A-Z ID Column Sorting** (v2.8.2): Final output sorted alphabetically by ID columns, right to left
21. **No Placeholder IDs** (v2.8.2): Rows with missing/placeholder ID values are automatically rejected

### Complete Data Flow Algorithm (v2.8)

This section details the exact data transformations at each step:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 0: BACKGROUND RESEARCH                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Input:  User request, conversation history                                  │
│ Output: authoritative_sources, starting_tables_markdown, citations          │
│                                                                             │
│ Example Output:                                                             │
│   starting_tables_markdown: "| Company | Funding |\n|---|---|\n| Anthropic[1] | $7.3B[2] |"
│   citations: {"1": "https://anthropic.com", "2": "https://crunchbase.com"}  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 0b: TABLE EXTRACTION (Optional)                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ Input:  identified_tables from Step 0                                       │
│ Output: extracted_tables with complete rows                                 │
│                                                                             │
│ Example Output:                                                             │
│   extracted_tables: [{                                                      │
│     "markdown_table": "| Company | CEO | Revenue |\n...",                   │
│     "source_urls": ["https://forbes.com/ai50"],                             │
│     "rows_count": 50                                                        │
│   }]                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: COLUMN DEFINITION                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Input:  research results, extracted_tables, starting_tables                 │
│ Output: columns[], prepopulated_rows_markdown, citations, subdomains        │
│                                                                             │
│ Example Output:                                                             │
│   columns: [                                                                │
│     {"name": "Company Name", "importance": "ID"},                           │
│     {"name": "CEO Name", "importance": "RESEARCH"},                         │
│     {"name": "Funding", "importance": "RESEARCH"}                           │
│   ]                                                                         │
│   prepopulated_rows_markdown: "| Company Name | CEO Name | Funding |\n..."  │
│   citations: {"1": "url1", "2": "url2", ...}  ← Starting citation count     │
│   trigger_row_discovery: true                                               │
│   subdomains: [{name: "Tech Giants", target_rows: 10, ...}]                 │
│                                                                             │
│ Citation Counter: next = max(citations.keys()) + 1 = 11                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: ROW DISCOVERY (if trigger_row_discovery=true)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Input:  columns, subdomains, citation_start_number=11                       │
│ Output: candidates_markdown, citations, scoring per subdomain               │
│                                                                             │
│ Processing (Sequential Mode):                                               │
│   Subdomain A (citation_start=11):                                          │
│     Round 1: Finds 5 rows → citations [11]-[15]                             │
│     Round 2: Finds 3 rows → citations [16]-[18]                             │
│     Returns: candidates_markdown + citations + max_citation=18              │
│                                                                             │
│   Subdomain B (citation_start=19):                                          │
│     Round 1: Finds 4 rows → citations [19]-[22]                             │
│     Returns: candidates_markdown + citations + max_citation=22              │
│                                                                             │
│ Processing (Parallel Mode - pre-allocated ranges):                          │
│   Subdomain A (citation_start=11, range 11-110)                             │
│   Subdomain B (citation_start=111, range 111-210)                           │
│   Subdomain C (citation_start=211, range 211-310)                           │
│                                                                             │
│ Combined Output:                                                            │
│   candidates_markdown: merged from all subdomains (same columns as Step 1)  │
│   citations: {"11": "url", "12": "url", ..., "22": "url"}                   │
│   scoring: [{"row_id": "Anthropic", "relevancy": 0.95, ...}]                │
│   max_citation_number: 22                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: QC REVIEW                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ Input:  prepopulated_rows + discovered_rows (with row_ids), all citations   │
│ Output: action, remove_row_ids (if filtering), overall_score                │
│                                                                             │
│ QC Sees (with row_ids added):                                               │
│   | row_id | Company Name | CEO Name | Funding |                            │
│   |--------|--------------|----------|---------|                            │
│   | 1-Anthropic | Anthropic[1] | Dario Amodei[11] | $7.3B[12] |             │
│   | 2-OpenAI | OpenAI[2] | Sam Altman[13] | $10B[14] |                      │
│                                                                             │
│ QC Output (v2.8.2 - rows KEPT by default, cross-set dedup):                 │
│   {                                                                         │
│     "action": "filter",                                                     │
│     "keep_row_ids_in_order": ["1-Anthropic", "2-OpenAI"],                   │
│     "remove_prepopulated_row_ids": ["P5-OldCompany"],                       │
│     "removal_reasons": {"5-Fake": "Not real", "P5-OldCompany": "Dup"},     │
│     "overall_score": 0.85                                                   │
│   }                                                                         │
│                                                                             │
│ Post-processing:                                                            │
│   - Keep discovered rows in keep_row_ids_in_order (or all if null)          │
│   - Remove prepopulated rows in remove_prepopulated_row_ids                 │
│   - Filter rows with missing/placeholder ID values                          │
│   - Sort all rows A-Z by ID columns (right to left: ID3→ID2→ID1)           │
│   - Prune citations no longer referenced in kept rows                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ FINAL OUTPUT                                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ approved_rows: List of row dicts with:                                      │
│   - id_values: {"Company Name": "Anthropic"}                                │
│   - research_values: {"CEO Name": "Dario Amodei", "Funding": "$7.3B"}       │
│   - cell_citations: {"Company Name": ["1"], "CEO Name": ["11"]}             │
│   - source_urls: ["https://anthropic.com", ...]                             │
│   - row_id: "1-Anthropic"                                                   │
│   - match_score, qc_score, etc.                                             │
│                                                                             │
│ citations: {"1": "url1", "11": "url11", ...}  (pruned, only referenced)     │
│                                                                             │
│ CSV generation uses:                                                        │
│   - id_values for ID columns                                                │
│   - research_values for RESEARCH columns                                    │
│   - cell_citations for Excel footnotes (future)                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

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
| 21-50 rows | Moderate | Moderate | 3-4 | Balanced coverage |
| 51-100 rows | Challenging/Niche | Complex | 4-5 | Wide net for rare entities |
| 100+ rows | Very Niche | Very Complex | 5 | Maximum (hard limit for Lambda timeout) |

**Examples:**
- "Fortune 500 companies" → 2-3 subdomains (well-known, easy to find)
- "Biotech companies hiring AI engineers" → 4-5 subdomains (niche intersection, multiple criteria)
- "Academic papers on quantum AI from 2024" → 5 subdomains (max limit, very specific)
- "Local government AI initiatives globally" → 5 subdomains (max limit, very rare)

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

### 0b. Table Extraction Handler (NEW in v2.7)
**File:** `table_maker_lib/table_extraction_handler.py`

**Purpose:** Extract complete tables from URLs identified by background research

**Key Features:**
- Sequential extraction (after Step 0, before Step 1)
- Site-specific search (include_domains from URL)
- Supports target_rows filter (e.g., "only winners")
- Handles pagination detection
- Model: sonar (fast, cost-effective)

**Output:**
```json
{
  "extracted_tables": [
    {
      "table_name": "Forbes AI 50 2024",
      "source_url": "https://...",
      "extraction_complete": true,
      "rows_extracted": 50,
      "rows": [
        {"Company Name": "Anthropic", "Funding": "$7.3B", ...},
        ...
      ]
    }
  ]
}
```

### 1. Column Definition Handler
**File:** `table_maker_lib/column_definition_handler.py`

**Purpose:** Design table and generate initial rows from available data

**Key Features:**
- Generates columns (ID vs research columns)
- Generates rows from: extracted_tables, starting_tables, conversation, or model knowledge
- Populates ALL columns with reliable data (not just ID columns)
- Decides trigger_row_discovery (true/false)
- Creates subdomains (only if triggering discovery)
- Model: gemini-2.5-flash (fast, no web search needed)

**Output:**
```json
{
  "columns": [...],
  "search_strategy": {
    "requirements": [...],
    "subdomains": [...]  // Only if trigger_row_discovery=true
  },
  "table_name": "...",
  "rows": [
    {
      "id_values": {"Company": "Anthropic"},
      "research_values": {"Funding": "$7.3B"},  // Populated when available!
      "populated_columns": ["Company", "Website", "Funding"],
      "missing_columns": ["Employee Count", "Has Job Posting"]
    }
  ],
  "trigger_row_discovery": true,
  "discovery_guidance": "Have 30 rows with basic data. Need 20 more + populate missing columns"
}
```

### 2. Row Discovery Orchestrator
**File:** `src/lambdas/interface/actions/table_maker/table_maker_lib/row_discovery.py`

**Purpose:** Coordinate subdomain discovery with progressive escalation and citation tracking

**Key Features:**
- Processes subdomains (sequential or parallel)
- Implements escalation strategy from config
- Consolidates results (deduplication, scoring)
- Tracks which model/round found each candidate
- **NEW (v2.8):** Global citation counter across all subdomains
- **NEW (v2.8):** Pre-allocates citation ranges for parallel execution (100 per subdomain)
- **NEW (v2.8):** Combines citations from all streams in final output

**Output:**
```json
{
  "final_rows": [...],  // Consolidated, deduplicated candidates
  "stream_results": [...],  // Per-subdomain details with citations
  "citations": {  // Combined citations from all subdomains (NEW v2.8)
    "1": "https://source1.com",
    "11": "https://source11.com",
    "101": "https://parallel-source.com"
  },
  "max_citation_number": 115,  // For next cycle (NEW v2.8)
  "stats": {
    "total_candidates_found": 25,
    "duplicates_removed": 5,
    "below_threshold": 1
  }
}
```

**Citation Coordination (v2.8):**
```
Sequential Mode:
  Subdomain A (start=1) → max=10 → Subdomain B (start=11) → max=20

Parallel Mode (pre-allocated ranges):
  Subdomain A (start=1, range 1-100)
  Subdomain B (start=101, range 101-200)
  Subdomain C (start=201, range 201-300)
```

### 3. Row Discovery Stream
**File:** `src/lambdas/interface/actions/table_maker/table_maker_lib/row_discovery_stream.py`

**Purpose:** Execute progressive escalation for a single subdomain with unified output format

**Key Features:**
- 3-level escalation (sonar → sonar-pro → claude-haiku)
- Early stopping based on percentage thresholds
- Collects search improvements from each round
- Passes accumulated improvements to next round
- Tags each candidate with model_used, round, context
- Uses web searches from subdomain.search_queries
- **NEW (v2.8):** Outputs ALL columns (ID + RESEARCH) with inline citations
- **NEW (v2.8):** Citation renumbering to avoid collisions across rounds/subdomains

**Unified Output Format (v2.8):**
```json
{
  "subdomain": "AI Research Companies",
  "candidates_markdown": "| Company Name | CEO Name | Funding |\n|---|---|---|\n| Anthropic[1] | Dario Amodei[2] | $7.3B[3] |",
  "citations": {
    "1": "https://anthropic.com/about",
    "2": "https://wikipedia.org/Dario_Amodei",
    "3": "https://crunchbase.com/anthropic"
  },
  "scoring": [
    {"row_id": "Anthropic", "relevancy": 0.95, "reliability": 1.0, "recency": 0.9, "rationale": "Leading AI safety"}
  ],
  "max_citation_number": 3
}
```

**Escalation Logic:**
```python
Level 1: sonar (high context) - cheap, fast
  → If found >= 75% of target: STOP
  → Else: Continue to Level 2
  → Collects search_improvements, passes to Level 2
  → Citations renumbered from citation_start_number

Level 2: sonar-pro (high context) - premium quality
  → If found >= 90% of target: STOP
  → Else: Continue to Level 3
  → Receives improvements from Level 1, adds its own
  → Citations continue from Level 1's max

Level 3: claude-haiku-4-5 (3 web searches) - fallback
  → Always completes (final level)
  → Receives all previous improvements
  → Ensures results even for difficult topics
  → Citations continue from Level 2's max
```

**Citation Numbering Flow:**
```
Column Definition: prepopulated rows with citations [1]-[10]
  → citation_counter = 11
Subdomain A Round 1: citations [11]-[15]
  → citation_counter = 16
Subdomain A Round 2: citations [16]-[20]
  → citation_counter = 21
Subdomain B (parallel, pre-allocated): citations [101]-[115]
  → Ranges pre-allocated for parallel execution (100 per subdomain)
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
- **NEW (v2.8):** Preserves cell-level citations when merging duplicates
- **NEW (v2.8):** Merges research_values from candidates

### 5. QC Reviewer
**File:** `src/lambdas/interface/actions/table_maker/table_maker_lib/qc_reviewer.py`

**Purpose:** Final quality control and prioritization

**Key Features:**
- Uses claude-sonnet-4-5 (no web search)
- Reviews all consolidated candidates
- Assigns qc_score (0-1), more flexible than discovery rubric
- Can promote/demote based on strategic value
- No max_rows cutoff - keeps all quality rows
- **NEW (v2.8):** Simplified output - rows kept by default
- **NEW (v2.8):** Only specifies `remove_row_ids` (not full table rewrite)
- **NEW (v2.8):** Prunes unused citations from final output
- **NEW (v2.8.2):** Can remove pre-existing rows via `remove_prepopulated_row_ids`
- **NEW (v2.8.2):** Strict deduplication - every row must be evidently unique
- **NEW (v2.8.2):** Rejects rows with missing/placeholder ID values

**QC Actions (v2.8):**
| Action | Output | Description |
|--------|--------|-------------|
| `pass` | `overall_score` only | All rows approved as-is |
| `filter` | `remove_row_ids` + `overall_score` | Remove specific rows (others kept) |
| `retrigger_discovery` | `new_subdomains` + `discovery_guidance` | Need more entities |
| `restructure` | `restructuring_guidance` + `user_message` | Table needs redesign |

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
    "model": "gemini-2.5-flash",
    "max_tokens": 32000,
    "subdomain_count_min": 2,
    "subdomain_count_max": 5,
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
- Conversation remains visible (preserved during execution)
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
