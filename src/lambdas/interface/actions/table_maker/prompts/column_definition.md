# Column Definition Task

{{RESTRUCTURING_SECTION}}

═══════════════════════════════════════════════════════════════
## 🚨 CRITICAL DECISION: Read This FIRST
═══════════════════════════════════════════════════════════════

**BEFORE you do ANYTHING, answer these 2 questions:**

1. **Did I identify enough ENTITIES (rows)?**
   - User asked for "top 20 richest" → I identified 20 people by name? → YES
   - User asked for "AI companies" → I have 0 companies identified? → NO

2. **Are ID columns populated to uniquely identify each entity?**
   - Person Name, Company Name filled in? → YES
   - Cannot identify the entities? → NO

**NOTE: Empty research columns (net worth, funding, etc.) are FINE - validator fills those**

**DECISION RULE:**
```
IF both answers are YES (have enough entities with ID columns populated):
  → trigger_row_discovery = FALSE
  → Provide skip_rationale
  → DO NOT include subdomains (will cause error)

IF any answer is NO (need more entities):
  → trigger_row_discovery = TRUE
  → Provide discovery_guidance
  → MUST include subdomains array (1-10 items) in search_strategy
```

**⚠️ SCHEMA ENFORCEMENT:** The JSON schema will REJECT your response if you set trigger_row_discovery=true without subdomains!

**When in doubt, choose FALSE - it's safer!**

═══════════════════════════════════════════════════════════════
## 📊 DATA SOURCES AVAILABLE
═══════════════════════════════════════════════════════════════

**From Background Research (Step 0 + Step 0b):**

1. **tablewide_research** - Domain overview (includes discovery patterns, key facts)
2. **extracted_tables** - Complete tables from Step 0b (if available)
3. **starting_tables_markdown** - Markdown table with entities and citations
4. **citations** - Map of citation numbers to source URLs
5. **authoritative_sources** - Databases/directories (name, url, description)

**From Conversation:**
- User's requirements
- Possibly pasted document text

═══════════════════════════════════════════════════════════════
## 🎯 YOUR TASK
═══════════════════════════════════════════════════════════════

**Design the table and generate as many rows as you can from available data.**

**Target row count: {{TARGET_ROW_COUNT}}** — Use this to gauge how exhaustively to populate rows. If "find-all mode", include every qualifying entity you can identify.

**⚠️ Response length limit: {{WORD_LIMIT}} words. If approaching the limit, prioritise ID column values over research column data — a row with only the ID column populated is far more valuable than a truncated list.**

**ALWAYS OUTPUT:**
1. **columns** (ID + research columns)
2. **search_strategy** object with:
   - `description` (what entities to find)
   - `requirements` array (hard + soft, minimum 1)
3. **table_name**
4. **rows** (generate ALL you can from: extracted_tables, starting_tables_markdown, conversation, or model knowledge)
5. **trigger_row_discovery** (true/false - do we need row discovery to find/populate more?)

**CONDITIONAL OUTPUT:**
- **subdomains** (in search_strategy) - MANDATORY if trigger_row_discovery=true, FORBIDDEN if false
- **skip_rationale** - MANDATORY if trigger_row_discovery=false, FORBIDDEN if true
- **discovery_guidance** - MANDATORY if trigger_row_discovery=true, FORBIDDEN if false

**🚨 CRITICAL VALIDATION RULE:**
```
IF trigger_row_discovery = true AND subdomains is missing/empty
    → EXECUTION ERROR (system will reject your response)

IF trigger_row_discovery = false AND subdomains is present
    → EXECUTION ERROR (system will reject your response)
```
**Default to false if unsure - it's the safer path**

═══════════════════════════════════════════════════════════════
## 📋 ROW GENERATION STRATEGY
═══════════════════════════════════════════════════════════════

**Generate rows from ANY available source:**

### Source 1: extracted_tables (Priority)
If background_research has `extracted_tables`:
- Parse ALL rows from extracted_tables
- Map source columns to your defined columns
- Populate ID columns + any research columns present in source

### Source 2: starting_tables_markdown
- Parse the markdown table with citations
- If `is_complete_enumeration: true` → Use ALL rows (skip discovery)
- Otherwise → Copy ALL rows into prepopulated_rows_markdown (discovery will append more on top)
- Preserve citations [1] [2] from the markdown

### Source 3: Conversation
- If user pasted document with entity list → Extract ALL
- Parse into your column structure

### Source 4: Model Knowledge
- If well-known finite set (countries, states, etc.) → Enumerate ALL
- Generate from your knowledge

**🎯 YOUR PRIMARY JOB: IDENTIFY ROWS (ID Columns)**
- **CRITICAL: Populate ID columns** - these uniquely identify the entity (e.g., Company Name, Person Name)
- **OPPORTUNISTIC: Populate other columns** - only if you have data from sources
- **DO NOT infer or guess missing research column values** - leave empty if not in sources
- Empty research columns are NORMAL - the validator will populate them downstream via web search
- If extracted_tables has "Funding" and you defined "Funding" column → Include it
- If you know the US state capitals → Include them
- Mark populated_columns and missing_columns for each row

**🚨 AVOID DUPLICATES - Before adding a row, check if it already exists:**
- Same entity with different names: "EarPopper" = "EarPopper®" = "Ear Popper" (add ONCE)
- Same entity with different verbosity: "Anthropic" = "Anthropic AI" (add ONCE)
- Trademark symbols (®, ™) don't make entries unique
- If multiple sources list the same entity differently, use the MOST AUTHORITATIVE name

═══════════════════════════════════════════════════════════════
## ⚡ DECISION: Trigger Row Discovery?
═══════════════════════════════════════════════════════════════

**🚨 CRITICAL: trigger_row_discovery is ONLY about ROW QUANTITY, not column completeness**

### trigger_row_discovery = false (Skip Discovery)

**When you have ENOUGH ROWS identified:**
- You identified ALL entities the user wants (exact count or sufficient set)
- ID columns are populated to uniquely identify each entity
- **Research columns can be mostly empty - the validator handles that downstream**
- Set is complete and finite

**Examples:**
- Generated 50 US states with just names → Complete (validator adds population data)
- Extracted 54 paper references with titles/authors → Complete (validator adds citations)
- Identified 20 billionaires by name from tables → Complete (validator populates net worth, tax data)
- **User asks for "top 5 LLMs", you identified 5 by name → Complete (even if ALL research columns empty)**

**"Good Enough" Threshold for ROWS:**
- Have you identified enough ENTITIES? (they asked for 5, you identified 5)
- Are the ID columns populated? (can uniquely identify each entity)
- **Empty research columns are FINE** - validator will populate them
- Would the user say "you found the right entities" if they saw the row IDs?

**If YES → Set trigger_row_discovery=false (even if most columns are empty)**

**Requirements:**
- Provide skip_rationale explaining why discovery not needed
- Do NOT output subdomains

### trigger_row_discovery = true (Run Discovery)

**When you need MORE ROWS (more entities):**
- Need MORE entities than you can identify (quantity gap)
- User explicitly requested "all X" and you only have samples
- You have 0 rows or far fewer than requested
- Cannot identify enough entities from available sources

**Examples:**
- Generated 30 companies from starting_tables_markdown, user specified 50, need 20 more → Discovery
- Have 9 City Council winners, user wants all election winners (School Committee too) → Discovery
- User asks "find AI companies hiring", you have 0 rows → Discovery
- User asks for 100 researchers, you only identified 20 → Discovery

**Counter-Examples (DO NOT trigger discovery):**
- Identified 5 entities by name, user asked for "top 5" → Skip (have enough rows, even if columns empty)
- Identified 50 papers by title, most columns empty → Skip (have enough rows, validator fills columns)
- Identified 20 billionaires by name, missing net worth data → Skip (have enough rows, validator fills data)
- Generated all 50 US states by name, missing population → Skip (have enough rows, validator fills data)

**🚨 CRITICAL REQUIREMENT - READ CAREFULLY:**

**IF YOU SET trigger_row_discovery=true, YOU MUST:**
1. ✅ Include `subdomains` array (2-5 subdomains, MAXIMUM 5) in search_strategy object
2. ✅ Provide discovery_guidance explaining what discovery should do
3. ✅ Each subdomain MUST have: name, focus, search_queries (2-5), target_rows

**FAILURE TO INCLUDE SUBDOMAINS WILL CAUSE EXECUTION ERROR!**
**MAXIMUM 5 SUBDOMAINS - Using more than 5 will cause timeout issues.**

**The system will reject your response if:**
- trigger_row_discovery=true AND subdomains is missing → ERROR
- trigger_row_discovery=true AND subdomains is empty array → ERROR

**If you're unsure whether you have enough rows, default to trigger_row_discovery=false (safer path)**

**Example for your current case:**
```json
{
  "trigger_row_discovery": true,
  "discovery_guidance": "Have 9 City Council winners. Need School Committee winners (6 seats) to complete all election winners.",
  "search_strategy": {
    "requirements": [...],
    "subdomains": [
      {
        "name": "School Committee Winners",
        "focus": "6 elected School Committee members from November 2025 Cambridge election",
        "search_queries": [
          "Cambridge School Committee election results November 2025",
          "Cambridge MA School Committee winners November 2025"
        ],
        "target_rows": 6
      }
    ]
  }
}
```

═══════════════════════════════════════════════════════════════
## 📚 INFORMATION PROVIDED
═══════════════════════════════════════════════════════════════

**Conversation History:**
{{CONVERSATION_CONTEXT}}

**User's Requirements:**
{{USER_REQUIREMENTS}}

**Background Research:**
{{BACKGROUND_RESEARCH}}

═══════════════════════════════════════════════════════════════
## 💡 DESIGN PRINCIPLES (ALWAYS APPLY)
═══════════════════════════════════════════════════════════════

### Principle 0: Build Around Existing Tables

**If you were provided sourced tables - start with these columns.**

- This will allow you to jumpstart the rows
- Provides an already thought through way to structure the data
- Intersect multiple tables if provided. 

### Principle 1: Design for Discoverability

**Your table design determines whether rows can be found.**

- Can entities matching these requirements be found via simple web search?
- What information appears in search results? (Names, headlines, directories) 


**Solution: Broad Discovery + Validation Filtering**
- Am I making requirements too narrow? (Every hard requirement ELIMINATES rows) and harder to search.
- ❌ BAD: Hard requirement "Must have active AI/ML job posting" → 0 rows found
- ✅ GOOD: Soft requirement "Prefers companies with AI teams" + Research column "Has Active Job Posting"

### Principle 2: Support Columns Strategy

**Break complex validations into discoverable steps.**

**Example: Finding Email Addresses**
- ❌ Direct: "Find researcher's email" → 30% success
- ✅ Support Columns:
  1. "Institution Email Pattern" (e.g., firstname.lastname@stanford.edu)
  2. "Email" (apply pattern to name)

### Principle 3: ID vs Research Columns

**ID Columns (Simple Identifiers):**
- 1-5 words, found in lists/directories
- NO synthesis or complex reasoning
- Set `importance: "ID"` and `validation_strategy: ""`
- Examples: ✅ Company Name, Paper Title, Headline,  ❌ "Story Description"
- Should uniquely define the entity in the row without further columns
- **⚠️ Soft requirements must NEVER become ID columns.** A soft requirement like "Prefers companies with 50+ employees" or "Prefers trials with active enrollment" describes a property to validate, not an identifier. Never encode soft requirements as ID column values or use them to restrict what counts as a valid entity. If a soft requirement can be validated per row, make it a RESEARCH column instead.

**Research Columns (Validated Data):**
- Complex information requiring validation
- Set `importance: "RESEARCH"` and provide `validation_strategy`
- Examples: Funding stage, employee count, program existence

### Principle 4: Hard Requirements as First Research Columns

**For each hard requirement, add a corresponding research column — unless that criterion is already obviously captured by an existing column.**

- **Hard requirements only** (soft requirements don't need columns — they are preferences, not gates; if a soft requirement can be validated per row, add a RESEARCH column for it)
- **Place these columns first** among the research columns, before any other research columns
- This lets the validator verify rows actually meet the hard requirements, and row expansion can filter on these criteria later

**Examples:**

| Hard Requirement | Obvious existing column? | Action |
|------------------|--------------------------|--------|
| "Must be US-based" | "Country" or "HQ Location" already present | No new column needed |
| "Must be US-based" | No geography column | Add "HQ Country" as first research column |
| "Must be from 2024" | "Year" or "Published Date" already present | No new column needed |
| "Must be from 2024" | No date column | Add "Year" as first research column |
| "Must be a publicly traded company" | No stock/exchange column | Add "Stock Exchange" as first research column |

**Rule of thumb:** If you defined a hard requirement and can't point to an existing column that directly validates it, add one — and put it at the top of your research columns list.

═══════════════════════════════════════════════════════════════
## ✔️ REQUIREMENTS SPECIFICATION (ALWAYS REQUIRED — even when skipping discovery)
═══════════════════════════════════════════════════════════════

**You must define at least ONE requirement (hard or soft), regardless of trigger_row_discovery.**

**Why always required:** Requirements are sent to the frontend and stored permanently. They will be used for row expansion (adding more rows to the table later) — so they matter even when row discovery is skipped today.

### Hard Requirements (0-2 typical)
Use for entity type, geography, or time period if truly essential.

**Examples:**
- "Must be a pizza topping"
- "Must be from 2024"
- "Must be US-based"

### Soft Requirements (Most should be soft)
Use "Prefers" language.

**Examples:**
- "Prefers toppings ranked in national consumer surveys"
- "Prefers companies with active job postings"

### Requirements Notes
Provide 1-2 sentences of overall guidance.

**Example:** "Focus on well-known companies. Innovation matters more than size."

═══════════════════════════════════════════════════════════════
## 📊 SUBDOMAINS (CRITICAL - Only if trigger_row_discovery=true)
═══════════════════════════════════════════════════════════════

**🚨 IF trigger_row_discovery=true, YOU MUST provide 2-5 subdomains. EXECUTION WILL FAIL WITHOUT THEM.**

**⚠️ MAXIMUM 5 SUBDOMAINS - This is a hard limit to ensure timely completion.**

### Subdomain Count Guide

| User Wants | Subdomains | Rationale |
|------------|-----------|-----------|
| ≤20 rows | 2-3 | Efficient |
| 21-50 rows | 3-4 | Balanced |
| 51-100 rows | 4-5 | Wide net |
| 100+ rows | 5 | Maximum (hard limit) |

**NOTE:** Even for very large requests (100+ rows), use exactly 5 subdomains with higher target_rows per subdomain rather than more subdomains.

### Per-Subdomain Fields (ALL REQUIRED)

Each subdomain MUST have:
- `name`: Short identifier (e.g., "biotech_startups", "fortune_500_tech")
- `focus`: What specific entities to find in this segment
- `search_queries`: 2-5 queries that find LISTS of entities, not individuals
- `target_rows`: How many rows to find in this subdomain (minimum 5)

**Optional:**
- `discovered_list_url`: URL from authoritative_sources (boosts search)
- `candidates`: 3-10 sample entity names from starting_tables_markdown

### Good vs Bad Subdomain Examples

**✅ GOOD subdomain structure:**
```json
{
  "name": "Forbes AI Companies",
  "focus": "AI companies featured in Forbes AI 50 list 2024-2025",
  "search_queries": [
    "Forbes AI 50 2024 complete list",
    "Forbes artificial intelligence companies ranking 2025",
    "site:forbes.com AI 50 list"
  ],
  "target_rows": 25
}
```

**❌ BAD subdomain structure:**
```json
{
  "name": "AI",
  "focus": "Find AI companies",
  "search_queries": ["AI company"],  // Too vague, only 1 query
  "target_rows": 10  // Too few for most requests
}
```

### Search Query Guidelines

**Queries MUST find LISTS, not individual entities:**
- ❌ BAD: "AI researcher Stanford" → finds individual profiles
- ✅ GOOD: "Stanford AI faculty list 2024" → finds directory pages
- ❌ BAD: "OpenAI company" → finds company homepage
- ✅ GOOD: "top AI companies list 2024 2025" → finds ranking articles
- ❌ BAD: "company funding" → too generic
- ✅ GOOD: "AI startups Series B funding list database" → finds aggregators

**Include year modifiers (2024, 2025) to get current results.**

### Target Row Calculation

**CRITICAL: Discovery finds raw candidates, but ~50% are lost to dedup + QC filtering + quality thresholds. You MUST overshoot aggressively.**

```
overshoot_factor = 1.8 to 2.5 (use 2.5 for niche/strict topics, 1.8 for broad/easy topics)
dedup_compensation = 1.0 + ((subdomain_count - 2) * 0.10)
qc_compensation = 1.5 (QC rejects ~40% of discovered rows)
total_target = user_requested * overshoot_factor * dedup_compensation
target_per_subdomain = ceil(total_target / subdomain_count)
```

**Example: User wants 100 rows, 5 subdomains:**
- total_target = 100 * 2.0 * 1.3 = 260
- target_per_subdomain = ceil(260 / 5) = 52
- Each subdomain targets ~52 rows

**Minimum target_rows per subdomain: 10**
**Minimum total_target across all subdomains: user_requested * 1.8**

═══════════════════════════════════════════════════════════════
## 📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════

### Example: trigger_row_discovery = true (WITH SUBDOMAINS - REQUIRED!)

```json
{
  "columns": [...],

  "search_strategy": {
    "description": "Find AI companies",
    "requirements": [
      {"requirement": "Must be a company", "type": "hard", "rationale": "Entity type"},
      {"requirement": "Prefers companies with AI teams", "type": "soft", "rationale": "Relevance"}
    ],
    "requirements_notes": "Focus on well-known companies first",
    "default_excluded_domains": ["youtube.com", "reddit.com"],

    "subdomains": [
      {
        "name": "Forbes AI 50 Companies",
        "focus": "Top AI companies from Forbes 2024",
        "discovered_list_url": "https://forbes.com/ai50",
        "candidates": ["Anthropic", "OpenAI", "Scale AI"],
        "search_queries": ["Forbes AI 50 2024", "site:forbes.com AI 50"],
        "target_rows": 25
      },
      {
        "name": "Y Combinator AI Startups",
        "focus": "AI startups from Y Combinator portfolio",
        "search_queries": ["Y Combinator AI companies", "YC AI startups 2024"],
        "target_rows": 15
      }
    ]
  },

  "table_name": "AI Companies Analysis",

  "prepopulated_rows_markdown": "| Company Name | Total Funding | Employee Count | Has Job Posting |\n|--------------|---------------|----------------|------------------|\n| Anthropic[1] | $7.3B[1] | | |\n| OpenAI[1] | $11.3B[1] | | |\n| Scale AI[1] | $600M[1] | | |",

  "citations": {
    "1": "https://forbes.com/ai50/2024"
  },

  "trigger_row_discovery": true,
  "discovery_guidance": "Have 30 companies identified by name from Forbes. Need to find 20 more companies from Y Combinator and other sources to reach 50 total entities."
}
```

**CRITICAL:** When trigger_row_discovery=true, you MUST include subdomains array (2-10 subdomains). Omitting subdomains will cause execution failure!

**OR if complete:**

```json
{
  "columns": [...],
  "search_strategy": {
    "description": "All 50 US states with capitals and population data",
    "requirements": [
      {"requirement": "Must be one of the 50 US states", "type": "hard", "rationale": "Entity type definition"},
      {"requirement": "Prefers current population figures (2020 census or later)", "type": "soft", "rationale": "Data recency"}
    ],
    "requirements_notes": "Well-known finite set. Use official government sources for population data."
  },
  "table_name": "US States and Capitals",

  "prepopulated_rows_markdown": "| State | Capital | Population | Region |\n|-------|---------|------------|--------|\n| Alabama[1] | Montgomery[1] | 5.1M[1] | Southeast[1] |\n| Alaska[1] | Juneau[1] | 0.7M[1] | Pacific[1] |\n| Arizona[1] | Phoenix[1] | 7.4M[1] | Southwest[1] |\n... (all 50 states)",

  "citations": {
    "1": "Model Knowledge (January 2025)"
  },

  "trigger_row_discovery": false,
  "skip_rationale": "Generated complete set of all 50 US states with capitals, population, and regions from model knowledge. No discovery needed."
}
```

### Key Points:

**About prepopulated_rows_markdown:**
- Create a markdown table with ALL rows you can extract from available sources
- Use numbered citations [1] [2] [3] after each cell value to indicate source
- Include header row and separator (| --- |)
- Empty cells should be blank (no citation needed)
- Example: `| Walmart[1] | $680B[2] | 24%[3] |`

**About citations:**
- Map each citation number to its source URL
- Use the URLs from extracted_tables source_urls
- Format: `{"1": "https://url1.com", "2": "https://url2.com"}`
- Reuse citation numbers for the same source across different cells

**About trigger_row_discovery:**
- false: Identified enough entities (rows) - validator fills empty columns
- true: Need to find MORE entities (more rows)
- Provide appropriate rationale/guidance

**About subdomains:**
- ONLY include in search_strategy if trigger_row_discovery=true
- Required: 2-10 subdomains with search queries
- Use starting_tables_markdown and authoritative_sources to structure them

═══════════════════════════════════════════════════════════════
## 🎯 FINAL CHECKLIST
═══════════════════════════════════════════════════════════════

**ALWAYS OUTPUT:**
- [ ] Column definitions (ID + research columns)
- [ ] Requirements (at least 1 hard or soft) in search_strategy — **REQUIRED even when skipping discovery** (used for row expansion)
- [ ] Table name
- [ ] Rows (as many as you can generate with as much data as you have)
- [ ] trigger_row_discovery (true or false)

**IF trigger_row_discovery = false:**
- [ ] Provided skip_rationale
- [ ] Identified ALL entities (rows) user wants
- [ ] ID columns populated (research columns can be empty - validator handles those)
- [ ] NO subdomains in search_strategy
- [ ] **Requirements still specified** — they are stored for future row expansion

**IF trigger_row_discovery = true:**
- [ ] Provided discovery_guidance (what's still needed)
- [ ] **MANDATORY: Subdomains (2-10) in search_strategy.subdomains** - EXECUTION WILL FAIL IF MISSING
- [ ] Each subdomain has: name, focus, search_queries (2-5), target_rows
- [ ] Rows serve as starting point (discovery will append/merge)
- [ ] Clear what discovery needs to do
- [ ] Confirmed you don't have "good enough" rows already (if you do, use false instead)

**🚨 EXECUTION ERROR CHECK:**
```python
# System validation (execution.py:1212-1216):
if trigger_row_discovery == true AND len(subdomains) == 0:
    raise Error("trigger_row_discovery=true but no subdomains provided")
```

**Before setting trigger_row_discovery=true, ask yourself:**
- Do I have enough ENTITIES identified (row quantity)? → If YES, set to false
- Are ID columns populated to uniquely identify entities? → If YES, set to false
- **Ignore empty research columns** - validator fills those downstream
- **Only set to true if you need to find MORE ENTITIES (more rows)**

**ALWAYS:**
- [ ] Populate research_values for columns you have reliable data for
- [ ] Mark populated_columns and missing_columns
- [ ] Design for discoverability (if triggering discovery)

**⚠️ RESPONSE LENGTH LIMIT: {{WORD_LIMIT}} words max. If nearing the limit, drop research column data and keep ID column values — a stub row with only the term name is better than a truncated table.**

**Return your response as valid JSON matching the format above.**
