# Column Definition Task

{{RESTRUCTURING_SECTION}}

═══════════════════════════════════════════════════════════════
## 📊 DATA SOURCES AVAILABLE
═══════════════════════════════════════════════════════════════

**From Background Research (Step 0 + Step 0b):**

1. **tablewide_research** - Domain overview (already researched)
2. **extracted_tables** - Complete tables from Step 0b (if available)
3. **starting_tables** - Sample entities (5-15) or complete enumeration
4. **authoritative_sources** - Databases/directories
5. **discovery_patterns** - How entities are found

**From Conversation:**
- User's requirements
- Possibly pasted document text

═══════════════════════════════════════════════════════════════
## 🎯 YOUR TASK
═══════════════════════════════════════════════════════════════

**Design the table and generate as many rows as you can from available data.**

**ALWAYS OUTPUT:**
1. **columns** (ID + research columns)
2. **search_strategy** with requirements (hard + soft, minimum 1)
3. **table_name**
4. **rows** (generate ALL you can from: extracted_tables, starting_tables, conversation, or model knowledge)
5. **trigger_row_discovery** (true/false - do we need row discovery to find/populate more?)

**CONDITIONAL OUTPUT:**
- **subdomains** (in search_strategy) - MANDATORY if trigger_row_discovery=true, FORBIDDEN if false
- **skip_rationale** - MANDATORY if trigger_row_discovery=false, FORBIDDEN if true
- **discovery_guidance** - MANDATORY if trigger_row_discovery=true, FORBIDDEN if false

═══════════════════════════════════════════════════════════════
## 📋 ROW GENERATION STRATEGY
═══════════════════════════════════════════════════════════════

**Generate rows from ANY available source:**

### Source 1: extracted_tables (Priority)
If background_research has `extracted_tables`:
- Parse ALL rows from extracted_tables
- Map source columns to your defined columns
- Populate ID columns + any research columns present in source

### Source 2: starting_tables
- If `is_complete_enumeration: true` → Parse ALL sample_entities
- Otherwise → Parse 5-15 samples from sample_entities
- Map entity strings to your ID columns

### Source 3: Conversation
- If user pasted document with entity list → Extract ALL
- Parse into your column structure

### Source 4: Model Knowledge
- If well-known finite set (countries, states, etc.) → Enumerate ALL
- Generate from your knowledge (accurate as of January 2025)

**POPULATE ALL COLUMNS YOU CAN:**
- Don't just fill ID columns - populate research columns too!
- If extracted_tables has "Funding" and you defined "Funding" column → Include it
- If you know the US state capitals → Include them
- Mark populated_columns and missing_columns for each row

═══════════════════════════════════════════════════════════════
## ⚡ DECISION: Trigger Row Discovery?
═══════════════════════════════════════════════════════════════

**Set trigger_row_discovery based on:**

### trigger_row_discovery = false (Skip Discovery)

**When:**
- You generated ALL rows the user wants
- Most/all columns are populated with reliable data
- Set is complete and finite

**Examples:**
- Generated 50 US states with capitals from knowledge → Complete
- Extracted 54 paper references from conversation → Complete
- Parsed 50 companies from extracted_tables with funding/description → Complete

**Requirements:**
- Provide skip_rationale explaining why discovery not needed
- Do NOT output subdomains

### trigger_row_discovery = true (Run Discovery)

**When:**
- Need more rows than you can generate
- User will not be content with what you have
- Some columns still empty across all rows

**Examples:**
- Generated 30 companies from starting_tables, user specified 50, need 20 more → Discovery
- Have 9 City Council winners, user wants all election winners (School Committee too) → Discovery

**MANDATORY Requirements:**
- ✅ Provide discovery_guidance (what discovery should focus on)
- ✅ Output subdomains (2-10) in search_strategy - **THIS IS REQUIRED, NOT OPTIONAL**

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

**Research Columns (Validated Data):**
- Complex information requiring validation
- Set `importance: "RESEARCH"` and provide `validation_strategy`
- Examples: Funding stage, employee count, program existence

═══════════════════════════════════════════════════════════════
## ✔️ REQUIREMENTS SPECIFICATION (ALWAYS REQUIRED)
═══════════════════════════════════════════════════════════════

**You must define at least ONE requirement (hard or soft).**

### Hard Requirements (0-2 typical)
Use for entity type, geography, or time period if truly essential.

**Examples:**
- "Must be a company"
- "Must be from 2024"
- "Must be US-based"

### Soft Requirements (Most should be soft)
Use "Prefers" language.

**Examples:**
- "Prefers midsized companies (100-500 employees)"
- "Prefers companies with active job postings"

### Requirements Notes
Provide 1-2 sentences of overall guidance.

**Example:** "Focus on well-known companies. Innovation matters more than size."

═══════════════════════════════════════════════════════════════
## 📊 SUBDOMAINS (Only if trigger_row_discovery=true)
═══════════════════════════════════════════════════════════════

**If you set trigger_row_discovery=true, provide 2-10 subdomains.**

### Subdomain Count

| User Wants | Subdomains | Rationale |
|------------|-----------|-----------|
| ≤20 rows | 2-3 | Efficient |
| 21-50 rows | 4-5 | Balanced |
| 51-100 rows | 6-8 | Wide net |
| 100+ rows | 8-10 | Maximum coverage |

### Per-Subdomain Fields

**Required:**
- `name`: Concise subdomain name
- `focus`: Detailed description
- `search_queries`: 2-5 queries that find LISTS
- `target_rows`: How many to find

**Optional:**
- `discovered_list_url`: URL from authoritative_sources
- `candidates`: 3-10 sample entities from starting_tables

**Search Queries Must Find LISTS:**
- ❌ BAD: "AI researcher Stanford" → individuals
- ✅ GOOD: "Stanford AI faculty list" → many at once

### Target Row Calculation

```
overshoot_factor = 1.3 to 1.5
dedup_compensation = 1.0 + ((subdomain_count - 2) * 0.10)
total_target = user_requested * overshoot_factor * dedup_compensation
target_per_subdomain = total_target / subdomain_count
```

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

  "rows": [
    {
      "id_values": {"Company Name": "Anthropic"},
      "research_values": {"Total Funding": "$7.3B"},
      "source": "Forbes AI 50 2024",
      "populated_columns": ["Company Name", "Total Funding"],
      "missing_columns": ["Employee Count", "Has Job Posting"],
      "match_score": 0.95,
      "model_used": "column_definition"
    }
  ],

  "trigger_row_discovery": true,
  "discovery_guidance": "Have 30 companies from Forbes. Need to: (1) Find 20 more companies from Y Combinator and other sources, (2) Populate Employee Count and Has Job Posting columns"
}
```

**CRITICAL:** When trigger_row_discovery=true, you MUST include subdomains array (2-10 subdomains). Omitting subdomains will cause execution failure!

**OR if complete:**

```json
{
  "columns": [...],
  "search_strategy": {
    "description": "...",
    "requirements": [...]
  },
  "table_name": "US States and Capitals",
  "rows": [
    {
      "id_values": {"State": "Alabama", "Capital": "Montgomery"},
      "research_values": {"Population": "5.1M", "Region": "Southeast"},
      "source": "Model Knowledge (as of January 2025)",
      "populated_columns": ["State", "Capital", "Population", "Region"],
      "missing_columns": [],
      "match_score": 1.0,
      "model_used": "column_definition"
    }
    // ... all 50 states
  ],
  "trigger_row_discovery": false,
  "skip_rationale": "Generated complete set of all 50 US states with capitals, population, and regions from model knowledge. No discovery needed."
}
```

### Key Points:

**About rows field:**
- Generate as many as you can from available sources
- Populate ALL columns you have reliable data for (not just ID columns)
- Can combine from multiple sources (extracted_tables + starting_tables + knowledge)
- Mark populated_columns and missing_columns for each row

**About trigger_row_discovery:**
- false: You have ALL rows with sufficient data
- true: Need discovery to find more rows OR populate missing columns
- Provide appropriate rationale/guidance

**About subdomains:**
- ONLY include in search_strategy if trigger_row_discovery=true
- Required: 2-10 subdomains with search queries
- Use starting_tables and authoritative_sources to structure them

═══════════════════════════════════════════════════════════════
## 🎯 FINAL CHECKLIST
═══════════════════════════════════════════════════════════════

**ALWAYS OUTPUT:**
- [ ] Column definitions (ID + research columns)
- [ ] Requirements (at least 1) in search_strategy
- [ ] Table name
- [ ] Rows (as many as you can generate with as much data as you have)
- [ ] trigger_row_discovery (true or false)

**IF trigger_row_discovery = false:**
- [ ] Provided skip_rationale
- [ ] Generated ALL rows user wants
- [ ] Most columns populated with reliable data
- [ ] NO subdomains in search_strategy

**IF trigger_row_discovery = true:**
- [ ] Provided discovery_guidance (what's still needed)
- [ ] **MANDATORY: Subdomains (2-10) in search_strategy** - YOU WILL GET AN ERROR IF MISSING
- [ ] Each subdomain has: name, focus, search_queries (2-5), target_rows
- [ ] Rows serve as starting point (discovery will append/merge)
- [ ] Clear what discovery needs to do

**CRITICAL:** trigger_row_discovery=true WITHOUT subdomains will cause execution failure!

**ALWAYS:**
- [ ] Populate research_values for columns you have reliable data for
- [ ] Mark populated_columns and missing_columns
- [ ] Design for discoverability (if triggering discovery)

**Return your response as valid JSON matching the format above.**
