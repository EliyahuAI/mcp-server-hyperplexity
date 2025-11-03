# Column Definition Task

{{RESTRUCTURING_SECTION}}
═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **YOUR CORE TASK**: Define columns and search strategy using background research
2. **BACKGROUND RESEARCH**: Authoritative sources and starting tables (Step 0 output)
3. **DESIGN PRINCIPLES**: Discoverability, support columns, ID vs research columns
4. **REQUIREMENTS**: Hard vs soft requirements, self-contained specifications
5. **SUBDOMAINS**: Strategy for organizing parallel discovery
6. **COMPLETE ROWS (OPTIONAL)**: When to skip row discovery with complete enumeration
7. **OUTPUT FORMAT**: JSON structure with sample_rows or complete_rows
8. **FINAL REMINDER**: Critical requirements checklist

═══════════════════════════════════════════════════════════════
## 🎯 YOUR CORE TASK
═══════════════════════════════════════════════════════════════

**GOAL:** Define table structure and search strategy using background research as foundation

**DELIVERABLES:**
- Column definitions (ID + research columns)
- Search strategy with 2-10 subdomains
- Hard and soft requirements (minimum 1)
- Sample rows from starting tables (5-15 rows)
- Table name and tablewide research

**KEY RULES:**
1. ✅ **Use background research** - Starting tables show what's findable
2. ✅ **Design for discoverability** - Make row identification EASY
3. ✅ **Use support columns** - Break complex validations into steps
4. ✅ **Keep ID columns simple** - 1-5 words, no synthesis required
5. ✅ **Offload to research columns** - Let validation handle specifics
6. ✅ **Output sample rows** - Extract 5-15 from starting tables

---

═══════════════════════════════════════════════════════════════
## 📚 BACKGROUND RESEARCH (From Step 0)
═══════════════════════════════════════════════════════════════

**The background research phase has already identified authoritative sources and starting tables.**

{{BACKGROUND_RESEARCH}}

**How to Use This Research:**
1. **Starting Tables** → Use sample entities to design ID column structure
2. **Authoritative Sources** → Reference these in subdomain `discovered_list_url` fields
3. **Discovery Patterns** → Follow recommended approach (complete list, searchable database, etc.)
4. **Common Identifiers** → Use these for ID column naming
5. **Sample Entities** → Extract 5-15 as sample_rows in your output

---

═══════════════════════════════════════════════════════════════
## 💡 DESIGN PRINCIPLES
═══════════════════════════════════════════════════════════════

### Principle 1: Design for Discoverability

**Your table design determines whether rows can be found.**

**The Discovery Reality Check:**
- Can I find entities matching these requirements via web search?
- What information actually appears in search results? (Names, headlines, directories - NOT internal programs, proprietary data)
- Am I making requirements too narrow? (Every hard requirement ELIMINATES rows)

**Solution: Broad Discovery + Validation Filtering**
- ❌ BAD: Hard requirement "Must have active AI/ML job posting" → 0 rows found
- ✅ GOOD: Soft requirement "Prefers companies with AI teams" + Research column "Has Active Job Posting" → 50 discovered, 15 pass validation

### Principle 2: Support Columns Strategy

**Break complex validations into discoverable steps.**

**Example: Finding Email Addresses**
- ❌ Direct: "Find researcher's email" → 30% success
- ✅ Support Columns:
  1. "Institution Email Pattern" (e.g., firstname.lastname@stanford.edu) → 90% success
  2. "Email" (apply pattern to name) → 85% success

**When to Use:**
- Multi-step reasoning required
- Pattern-based construction (emails, URLs)
- Hierarchical information (department → program)
- Conditional validation (IF has AI team THEN check for ethics program)

### Principle 3: ID vs Research Columns

**ID Columns (Simple Identifiers):**
- 1-5 words typically
- Found in lists, directories, indexes
- NO synthesis or complex reasoning
- Set `importance: "ID"` and `validation_strategy: ""`
- Examples: ✅ Company Name, Paper Title, Date, URL  ❌ "Story Description", "Key Responsibilities"

**Research Columns (Validated Data):**
- Complex information requiring validation
- Can be filtering criteria (Has Active Job Posting, Employee Count)
- Set `importance: "RESEARCH"` and provide detailed `validation_strategy`
- Examples: Job posting status, funding stage, program existence, detailed descriptions

---

═══════════════════════════════════════════════════════════════
## 📚 INFORMATION PROVIDED
═══════════════════════════════════════════════════════════════

**Conversation History:**
{{CONVERSATION_CONTEXT}}

**User's Requirements:**
{{USER_REQUIREMENTS}}

---

═══════════════════════════════════════════════════════════════
## ✔️ REQUIREMENTS SPECIFICATION
═══════════════════════════════════════════════════════════════

**You must define at least ONE requirement (hard or soft, or both).**

### Hard Requirements (0-2 typical)

Use for entity type, geography, or time period if truly essential.

**Examples:**
- "Must be a company" (entity type)
- "Must be from 2024" (time-bound)
- "Must be US-based" (if geography critical)

**What NOT to make hard:**
- Size/scale → Soft requirement + research column
- Industry activities → Soft requirement + research column
- Specific characteristics → Soft requirement + research column

### Soft Requirements (Most should be soft)

Use "Prefers" language. Most filtering should happen here or in research columns.

**Examples:**
- "Prefers midsized companies (100-500 employees)"
- "Prefers companies with active job postings"
- "Prefers biotech sector"

### Converting to Research Columns

Complex criteria → Research columns for validation:
- "midsized" → Research column "Employee Count"
- "actively hiring" → Research column "Has Active Job Postings"
- "has GenAI program" → Research column "Has GenAI Program"

### Self-Contained Requirements

**Requirements must be comprehensive enough that someone can understand what rows are needed by ONLY reading the requirements, WITHOUT the user's original request.**

Before finalizing:
- [ ] Could someone understand what we need by only reading requirements?
- [ ] Have I captured ALL key aspects?
- [ ] Every user-mentioned criterion appears in requirements?

### Requirements Notes

Provide 1-2 sentences of overall guidance about good rows. Not a requirement itself, but helps discovery.

**Example:** "Looking for authoritative sources with detailed analysis. Company size matters less than innovation."

---

═══════════════════════════════════════════════════════════════
## 📊 SUBDOMAINS STRATEGY
═══════════════════════════════════════════════════════════════

**Subdomains organize parallel discovery workers. They are focus areas, not strict boundaries.**

### Subdomain Count (2-10)

**Decision Matrix:**
| User Wants | Topic Difficulty | Use Subdomains | Rationale |
|------------|-----------------|----------------|-----------|
| ≤20 rows | Common/Easy | 2-3 | Efficient, low overlap |
| 21-50 rows | Moderate | 4-5 | Balanced coverage |
| 51-100 rows | Challenging | 6-8 | Wide net needed |
| 100+ rows | Very Niche | 8-10 | Maximum coverage |

### Target Row Calculation

**Formula:**
```
overshoot_factor = 1.3 to 1.5 (30-50% buffer for QC rejection)
dedup_compensation = 1.0 + ((subdomain_count - 2) * 0.10)
total_target = user_requested * overshoot_factor * dedup_compensation
target_per_subdomain = total_target / subdomain_count
```

**Why Overshoot:** QC rejects 10-30%, deduplication removes overlaps. We want to DELIVER what we promised.

### Subdomain Structure

**Use background research starting tables to structure subdomains:**

**If complete list exists:** Segment it
- Example: "Countries A-E", "Countries F-M" (from UN member states list)
- Example: "NIH Awardees A-D", "NIH Awardees E-H" (from NIH RePORTER)

**If multiple partial lists:** One subdomain per list
- Example: "Forbes AI 50 Companies", "Crunchbase AI Series B+"
- Example: "LinkedIn GenAI Jobs - Top Tech", "Y Combinator AI Startups"

**Last subdomain:** Catch-all
- Example: "Other AI Companies (not in Forbes/Crunchbase lists above)"

### Per-Subdomain Fields

**Required:**
- `name`: Concise subdomain name
- `focus`: Detailed description of focus area
- `search_queries`: 2-5 queries that find LISTS (not individuals)
- `target_rows`: How many to find here

**Optional (from background research):**
- `discovered_list_url`: URL of authoritative list
- `candidates`: 3-10 sample entities from starting tables

**Search Queries Must Find LISTS:**
- ❌ BAD: "AI researcher Stanford" → Returns individuals
- ✅ GOOD: "Stanford AI faculty list" → Returns many at once

---

═══════════════════════════════════════════════════════════════
## 🌐 DOMAIN FILTERING (Optional)
═══════════════════════════════════════════════════════════════

### Include Domains (USE SPARINGLY)

**ONLY add if user EXPLICITLY requested specific sources.**

- User: "Find companies, focusing on Crunchbase" → `["crunchbase.com"]` ✅
- User: "Find biotech companies" → `[]` (don't guess) ✅

### Exclude Domains (Safe to Use)

**Default exclusions:**
- `["youtube.com", "reddit.com"]` (unless user wants video/social)

**Add more based on needs:**
- Avoid news for technical queries: `["cnn.com", "foxnews.com"]`
- Avoid forums for factual queries: `["quora.com"]`

---

═══════════════════════════════════════════════════════════════
## ⚡ OPTIONAL: COMPLETE ROWS (Skip Row Discovery)
═══════════════════════════════════════════════════════════════

**WHEN TO USE:** Two scenarios when you should skip row discovery:

### Scenario 1: Complete Enumeration (Well-Known Lists)
When the list of rows is **obvious, exhaustive, and well-defined**.

**Examples Where You SHOULD Use complete_enumeration mode:**
- ✅ Items from a specific document (when ALL items provided by background research)
- ✅ Geographic/political entities (countries, states, provinces)
- ✅ Well-defined finite sets (planets, elements, calendar units)
- ✅ Official rosters (cabinet members, board members, committee members)

**How to Recognize Complete Enumeration from Background Research:**
- Look for starting_tables with `is_complete_enumeration: true`
- Check if `sample_entities` contains ALL entities or just a sample:
  - Count in entity_count_estimate should match sample_entities array length
  - If counts match → Use complete_rows mode
  - If only partial extraction → Fall back to normal row discovery

**IMPORTANT:** You do NOT have web search access - you can only use what background research provided

**Validation Rules:**
```json
// ✅ GOOD - Use complete_rows
{
  "entity_count_estimate": "54 entities",  // Exact count
  "is_complete_enumeration": true,
  "sample_entities": [ /* 54 items */ ]  // Count matches!
}

// ❌ BAD - Don't use complete_rows, run discovery
{
  "entity_count_estimate": "~50-60 entities",  // Vague
  "is_complete_enumeration": true,
  "sample_entities": [ /* only 5 items */ ]  // Incomplete!
}
```

### Scenario 2: JUMP START (Perfect Starting Table Match)
When background research found a **reliable starting table that perfectly matches** the user's request.

**Examples Where You SHOULD Use jump_start mode:**
- ✅ User wants "top AI companies" → Background research found "Forbes AI 50 2024" list with 50 companies
- ✅ User wants "NIH dementia research grants" → Background research found NIH RePORTER database with grant details
- ✅ User wants "countries in Africa with capitals" → Background research found Wikipedia list with all data
- ✅ User wants "S&P 500 companies" → Background research found authoritative S&P 500 list with company details
- ✅ User wants "FDA approved drugs for diabetes" → Background research found FDA database with complete drug list

**Key Criteria for JUMP START:**
1. Starting table source is **reliable/authoritative** (Forbes, NIH, Wikipedia, FDA, etc.)
2. Starting table **perfectly matches user intent** (not tangentially related)
3. Starting table has **good coverage** (most or all entities the user wants)
4. Starting table includes **multiple columns** (not just names - has descriptions, URLs, metadata)
5. You can **directly copy** the data without needing to transform it significantly

**Examples Where You SHOULD NOT Use complete_rows:**
- ❌ AI companies (open-ended, constantly changing) - unless a perfect starting table exists (JUMP START)
- ❌ Research papers on a topic (needs discovery) - too broad
- ❌ Job postings (dynamic, requires search)
- ❌ News articles about X (requires web search)
- ❌ People who work at a company (not publicly enumerable)

**Quality Requirements When Providing complete_rows:**

1. **MUST BE REAL**: Every row must be a real entity, not made-up examples
2. **MUST BE ORDERED**: Rows should be in a logical order (alphabetical, chronological, by importance)
3. **MUST BE EXHAUSTIVE/COMPLETE**: For complete_enumeration: ALL entities. For jump_start: ALL rows from starting table
4. **MUST BE ACCURATE**: ID values must be correct and properly formatted
5. **FOR JUMP START**: Copy as many columns as available from the starting table, not just ID columns

**Structure Examples:**

**Complete Enumeration Mode:**
```json
{
  "complete_rows": {
    "skip_row_discovery": true,
    "skip_rationale": "Background research extracted complete list of all entities. This is a finite, well-defined set where all items were enumerated in the starting table.",
    "mode": "complete_enumeration",
    "rows": [
      {
        "id_values": {
          "Entity ID": "Item 1",
          "Additional ID": "Detail 1"
        },
        "source": "Source name from background research",
        "match_score": 1.0
      },
      {
        "id_values": {
          "Entity ID": "Item 2",
          "Additional ID": "Detail 2"
        },
        "source": "Source name from background research",
        "match_score": 1.0
      }
      // ... all entities from background research starting_table
    ]
  }
}
```

**JUMP START Mode (Copy from Starting Table):**
```json
{
  "complete_rows": {
    "skip_row_discovery": true,
    "skip_rationale": "JUMP START: Forbes AI 50 2024 list from background research perfectly matches user request for top AI companies. Directly copying all 50 rows with company names, descriptions, and funding data already available in the starting table.",
    "mode": "jump_start",
    "rows": [
      {
        "id_values": {
          "Company Name": "Anthropic",
          "Website": "anthropic.com"
        },
        "research_values": {
          "Description": "AI safety and research company focused on developing reliable, interpretable AI systems",
          "Total Funding": "$7.3B",
          "Founded": "2021"
        },
        "source": "Forbes AI 50 2024",
        "match_score": 0.95
      },
      {
        "id_values": {
          "Company Name": "OpenAI",
          "Website": "openai.com"
        },
        "research_values": {
          "Description": "AI research and deployment company creating safe AGI",
          "Total Funding": "$11.3B",
          "Founded": "2015"
        },
        "source": "Forbes AI 50 2024",
        "match_score": 0.95
      }
      // ... all 50 companies from Forbes list
    ]
  }
}
```

**What Happens When You Use complete_rows:**
- ✅ Row discovery phase is **SKIPPED** (saves 60-120s and $0.05-0.15)
- ✅ QC review is **SKIPPED** (saves 8-15s and $0.015-0.035)
- ✅ For **jump_start**: Research columns pre-filled from starting table (huge time saver!)
- ✅ Rows go directly to CSV generation
- ✅ Config generation still runs in parallel

**When in doubt, DO NOT use complete_rows.** It's better to run row discovery than to provide incomplete or inaccurate rows.

**JUMP START is most valuable when the starting table has rich data** - don't just copy names, copy descriptions, URLs, dates, and any other relevant columns from the source!

---

═══════════════════════════════════════════════════════════════
## 📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════

Return JSON with this structure:

```json
{
  "columns": [
    {
      "name": "Company Name",
      "description": "Name of the AI company",
      "format": "String",
      "importance": "ID",
      "validation_strategy": ""
    },
    {
      "name": "Institution Email Pattern",
      "description": "Email format used by the institution (support column)",
      "format": "String",
      "importance": "RESEARCH",
      "validation_strategy": "Visit institution directory, find 2-3 example emails, identify pattern"
    },
    {
      "name": "Has Active Job Posting",
      "description": "Whether company has open AI/ML positions",
      "format": "Boolean/URL",
      "importance": "RESEARCH",
      "validation_strategy": "Check careers page, LinkedIn jobs, note posting URL if found"
    }
  ],
  "search_strategy": {
    "description": "Find AI companies with comprehensive coverage",
    "requirements": [
      {
        "requirement": "Must be a company",
        "type": "hard",
        "rationale": "Basic entity type"
      },
      {
        "requirement": "Prefers companies with AI/ML teams",
        "type": "soft",
        "rationale": "Increases likelihood of relevant job postings"
      }
    ],
    "requirements_notes": "Focus on well-known companies first, expand to startups.",
    "default_excluded_domains": ["youtube.com", "reddit.com"],
    "subdomains": [
      {
        "name": "Forbes AI 50 Companies",
        "focus": "Top AI companies from Forbes 2024 list",
        "discovered_list_url": "https://www.forbes.com/lists/ai50/",
        "candidates": ["Anthropic", "OpenAI", "Databricks", "Scale AI"],
        "search_queries": [
          "Forbes AI 50 2024 complete list",
          "site:forbes.com AI 50"
        ],
        "target_rows": 25
      }
    ]
  },
  "table_name": "AI Companies Hiring Status",
  "tablewide_research": "Track AI companies and their hiring activities for ML positions",
  "sample_rows": [
    {
      "id_values": {
        "Company Name": "Anthropic",
        "Website": "anthropic.com"
      },
      "source": "Forbes AI 50 2024",
      "match_score": 0.95,
      "model_used": "column_definition"
    },
    {
      "id_values": {
        "Company Name": "OpenAI",
        "Website": "openai.com"
      },
      "source": "Forbes AI 50 2024",
      "match_score": 0.90,
      "model_used": "column_definition"
    }
  ]
}
```

### Sample Rows (NEW - IMPORTANT)

**Extract 5-15 sample rows from background research starting tables.**

**CRITICAL: These MUST be REAL entities from the starting tables provided in background research. Do NOT make up, invent, or create example entities.**

**Why:** Gives QC immediate candidates without waiting for discovery. Discovery will find more rows and merge them (discovery takes precedence for duplicates based on model quality).

**How to Populate:**
1. **Look at `starting_tables`** from background research section above
2. **Extract 5-15 ACTUAL sample entities** from the sample_entities lists provided
3. **Use REAL entity names** - these must be entities that actually appear in the starting tables
4. Fill ID column values only (research columns stay empty)
5. Set `match_score` based on fit with requirements (0.7-0.95 typical)
6. Set `source` to the starting table name (must match one of the starting_tables)
7. Set `model_used` to "column_definition"

**Example:**
If background research shows starting table "Forbes AI 50 2024" with sample_entities: ["Anthropic", "OpenAI", "Scale AI"], then your sample_rows should use THOSE ACTUAL NAMES (Anthropic, OpenAI, Scale AI), NOT made-up examples.

### Required vs Optional Fields

**Required Fields (Must Be Present):**
- `columns` (array) - Column definitions
  - Each column needs: name, description, format, importance
  - ID columns need: validation_strategy = ""
  - Research columns need: validation_strategy = detailed instructions
- `search_strategy` (object)
  - `description` (string)
  - `requirements` (array, minimum 1) - At least one hard or soft requirement
  - `requirements_notes` (string)
  - `subdomains` (array, 2-10 items)
    - Each needs: name, focus, search_queries (2-5), target_rows
    - Optional: discovered_list_url, candidates
- `table_name` (string)
- `tablewide_research` (string)

**Optional Fields:**
- `sample_rows` (array) - Highly recommended, extracted from starting_tables
- `search_strategy.default_included_domains` (array) - Use sparingly
- `search_strategy.default_excluded_domains` (array) - Safe to use

### Column Naming Rules

**Column Names:** Short, friendly, CSV-safe (no commas, parentheses, quotes)
- ✅ "Far-Right US Coverage"
- ❌ "Far-Right US Coverage (Breitbart, Daily Wire)"

**Details go in description field:**
- Name: "Far-Right US Coverage"
- Description: "How far-right US sources like Breitbart, Daily Wire report this story"

---

═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER - Critical Requirements
═══════════════════════════════════════════════════════════════

**GOAL:** Define table structure using background research as foundation

**CRITICAL CHECKLIST:**

**🔍 Design for Discoverability:**
- [ ] Can I find entities matching requirements via simple web search?
- [ ] Are ID columns simple identifiers (1-5 words)?
- [ ] Have I moved filtering criteria to research columns?

**📚 Use Background Research:**
- [ ] Have I referenced starting tables in subdomains?
- [ ] Have I extracted 5-15 sample_rows from starting tables?
- [ ] Have I used authoritative sources in `discovered_list_url`?
- [ ] Have I followed the recommended discovery pattern?

**🔧 Support Columns:**
- [ ] Have I added support columns for complex validations?
- [ ] Are support columns easier to validate than final targets?

**📋 Requirements:**
- [ ] At least ONE requirement defined (hard or soft)?
- [ ] Are requirements self-contained (understandable without context)?
- [ ] Are most requirements soft (not overly restrictive)?

**🎯 If Restructuring:**
- [ ] Have I applied QC's column_changes guidance?
- [ ] Have I applied requirement_changes guidance?
- [ ] Have I applied search_broadening guidance?
- [ ] Is the table simpler and more discoverable now?

**Return your response as valid JSON matching the format above.**
