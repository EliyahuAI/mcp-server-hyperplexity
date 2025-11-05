# Column Definition Task

{{RESTRUCTURING_SECTION}}

═══════════════════════════════════════════════════════════════
## 📊 DATA SOURCES AVAILABLE
═══════════════════════════════════════════════════════════════

**From Background Research (Step 0 + Step 0b):**

1. **tablewide_research** - Domain overview with key facts and patterns (already researched for you)
2. **starting_tables** - Sample entities (5-15) showing what's findable
3. **extracted_tables** - Complete table extractions from Step 0b (if available)
4. **authoritative_sources** - Databases, directories where entities exist
5. **discovery_patterns** - How entities are typically found

**From Conversation:**
- User's original request and requirements
- Possibly pasted document text with complete entity list

**Priority for Complete Rows:**
1. **extracted_tables** (if exists) - Complete data already extracted by Step 0b
2. **starting_tables.is_complete_enumeration=true** - Complete list in starting_tables
3. **Conversation document text** - User pasted full list in conversation
4. **Otherwise** - Use starting_tables samples and trigger row discovery

═══════════════════════════════════════════════════════════════
## 🎯 YOUR TASK & OUTPUTS
═══════════════════════════════════════════════════════════════

**ALWAYS OUTPUT (Both Paths):**
- ✅ Column definitions (ID + research columns)
- ✅ Requirements (hard + soft, minimum 1) within search_strategy
- ✅ Table name

**NOTE:** tablewide_research comes from background research (input) and is NOT output by you.

**CONDITIONAL OUTPUT (Depends on Path):**

**Path A: Complete Rows** (if extracted_tables OR complete enumeration detected)
- ✅ complete_rows (all entities from extracted_tables or starting_tables or conversation)
- ✅ search_strategy (with requirements only, NO subdomains needed)
- ❌ NO sample_rows (have complete rows instead)

**Path B: Row Discovery** (normal flow - need to discover rows)
- ✅ search_strategy (with requirements AND subdomains)
- ✅ sample_rows (5-15 from starting_tables)
- ❌ NO complete_rows (will discover via row discovery)

═══════════════════════════════════════════════════════════════
## ⚡ DECISION LOGIC: Which Path?
═══════════════════════════════════════════════════════════════

### Check in Priority Order:

**1. Do you have extracted_tables?**
- If YES → **Path A: Complete Rows (JUMP START)**
- These are complete table extractions from Step 0b
- Use extracted_tables.rows directly as complete_rows
- Skip row discovery

**2. Does starting_tables have is_complete_enumeration: true?**
- Check if entity_count_estimate matches sample_entities length
- Example: "54 entities" and 54 items in sample_entities
- If YES → **Path A: Complete Rows (Complete Enumeration)**
- Use starting_tables.sample_entities as complete_rows
- Skip row discovery

**3. Does conversation have pasted document text?**
- Look for large text blocks with entity lists in CONVERSATION CONTEXT
- If YES → **Path A: Complete Rows (Manual Extraction)**
- Extract all entities from conversation text
- Skip row discovery

**4. None of the above?**
- **Path B: Row Discovery (Normal Flow)**
- Use starting_tables samples to design columns
- Output subdomains and search_strategy
- Trigger row discovery

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

═══════════════════════════════════════════════════════════════
## ✔️ REQUIREMENTS SPECIFICATION (ALWAYS REQUIRED)
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

═══════════════════════════════════════════════════════════════
## 📊 PATH A: COMPLETE ROWS (Skip Row Discovery)
═══════════════════════════════════════════════════════════════

**WHEN TO USE:** You have complete entity data available (extracted_tables, complete enumeration, or conversation text)

### Scenario 1: JUMP START (extracted_tables available)

**Step 0b extracted complete tables for you.**

**How to Use:**
1. Check background_research for `extracted_tables` field
2. Use extracted_tables[].rows directly as complete_rows
3. Each extracted table has: table_name, source_url, rows[], extraction_complete
4. Copy rows with all available columns (ID + research columns if present)

**Example:**
```json
{
  "complete_rows": {
    "skip_row_discovery": true,
    "skip_rationale": "JUMP START: Step 0b extracted complete table with 50 rows from Forbes AI 50 2024",
    "mode": "jump_start",
    "rows": [
      // Copy from extracted_tables[0].rows
      {
        "id_values": {"Company Name": "Anthropic", "Website": "anthropic.com"},
        "research_values": {"Description": "...", "Funding": "$7.3B"},
        "source": "Forbes AI 50 2024",
        "match_score": 0.95
      }
    ]
  }
}
```

### Scenario 2: Complete Enumeration (starting_tables)

**Background research extracted ALL entities in starting_tables.sample_entities**

**How to Recognize:**
- `starting_tables[].is_complete_enumeration: true`
- `entity_count_estimate` matches `sample_entities.length`
- Example: "54 entities" and 54 items in array

**How to Use:**
1. Extract all entities from starting_tables[].sample_entities
2. Parse each entity string into ID column values
3. Use complete_enumeration mode

**Example:**
```json
{
  "complete_rows": {
    "skip_row_discovery": true,
    "skip_rationale": "Complete enumeration: Background research extracted all 54 references from paper",
    "mode": "complete_enumeration",
    "rows": [
      {
        "id_values": {"Reference": "[1] Vaswani et al.", "Title": "Attention Is All You Need"},
        "source": "Paper references",
        "match_score": 1.0
      }
    ]
  }
}
```

### Scenario 3: Manual Extraction (conversation text)

**User pasted complete document in conversation**

**How to Recognize:**
- Background research incomplete/empty
- Large text block in CONVERSATION CONTEXT
- User explicitly said "extract all from this document"

**How to Use:**
1. Extract ALL entities from conversation text
2. Parse into ID columns
3. Use complete_enumeration mode

**⚠️ CRITICAL - Output Priority:**
When using complete_rows:
1. Output complete_rows FIRST and COMPLETELY
2. Keep columns/requirements sections minimal
3. If token budget limited, prioritize rows over everything else
4. Better to have complete rows with minimal columns than truncated rows

**Requirements for complete_rows:**
- ✅ MUST BE REAL (no made-up examples)
- ✅ MUST BE ORDERED (logical order)
- ✅ MUST BE EXHAUSTIVE (ALL entities)
- ✅ MUST BE ACCURATE (correct values)

═══════════════════════════════════════════════════════════════
## 📊 PATH B: ROW DISCOVERY (Normal Flow)
═══════════════════════════════════════════════════════════════

**WHEN TO USE:** No complete data available - need to discover rows via web search

### Use Background Research

**How to Use starting_tables:**
1. Look at sample_entities to understand entity structure
2. Design ID columns based on what appears in samples
3. Use authoritative_sources for subdomain discovered_list_url
4. Follow discovery_patterns recommendations

**Example:**
If starting_tables shows: "Dr. Jane Smith - Stanford - Neural Networks"
→ ID columns: "Researcher Name", "Institution"
→ Research columns: "Research Area"

### Subdomains Strategy (2-10 subdomains)

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
- `discovered_list_url`: URL of authoritative list from authoritative_sources
- `candidates`: 3-10 sample entities from starting_tables

**Search Queries Must Find LISTS:**
- ❌ BAD: "AI researcher Stanford" → Returns individuals
- ✅ GOOD: "Stanford AI faculty list" → Returns many at once

### Domain Filtering (Optional)

**Include Domains (USE SPARINGLY):**
- ONLY add if user EXPLICITLY requested specific sources
- Example: User says "focusing on Crunchbase" → `["crunchbase.com"]`

**Exclude Domains (Safe to Use):**
- Default: `["youtube.com", "reddit.com"]`
- Add more based on needs (news sites for technical queries, forums for factual queries)

### Sample Rows

**Extract 5-15 sample rows from starting_tables:**
- Use ACTUAL entities from starting_tables.sample_entities
- Fill ID column values only (research columns stay empty)
- Set `match_score` based on fit (0.7-0.95 typical)
- Set `source` to starting table name
- Set `model_used` to "column_definition"

**Example:**
```json
{
  "sample_rows": [
    {
      "id_values": {"Company Name": "Anthropic", "Website": "anthropic.com"},
      "source": "Forbes AI 50 2024",
      "match_score": 0.95,
      "model_used": "column_definition"
    }
  ]
}
```

═══════════════════════════════════════════════════════════════
## 📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════

### Path A: Complete Rows Output

```json
{
  "columns": [
    {
      "name": "Column Name",
      "description": "Description",
      "format": "String",
      "importance": "ID",
      "validation_strategy": ""
    }
  ],
  "search_strategy": {
    "description": "Brief description",
    "requirements": [
      {"requirement": "Must be X", "type": "hard", "rationale": "Why"},
      {"requirement": "Prefers Y", "type": "soft", "rationale": "Why"}
    ],
    "requirements_notes": "Overall guidance"
  },
  "table_name": "Table Name",
  "complete_rows": {
    "skip_row_discovery": true,
    "skip_rationale": "Why skipping (JUMP START, complete enumeration, etc.)",
    "mode": "jump_start" or "complete_enumeration",
    "rows": [
      {
        "id_values": {"Col1": "val1", "Col2": "val2"},
        "research_values": {"Col3": "val3"},
        "source": "Source name",
        "match_score": 0.95
      }
    ]
  }
}
```

### Path B: Row Discovery Output

```json
{
  "columns": [
    {
      "name": "Column Name",
      "description": "Description",
      "format": "String",
      "importance": "ID",
      "validation_strategy": ""
    }
  ],
  "search_strategy": {
    "description": "Search strategy description",
    "requirements": [
      {"requirement": "Must be X", "type": "hard", "rationale": "Why"},
      {"requirement": "Prefers Y", "type": "soft", "rationale": "Why"}
    ],
    "requirements_notes": "Overall guidance",
    "default_excluded_domains": ["youtube.com", "reddit.com"],
    "subdomains": [
      {
        "name": "Subdomain Name",
        "focus": "Focus description",
        "discovered_list_url": "https://source.com",
        "candidates": ["Entity 1", "Entity 2"],
        "search_queries": ["query 1", "query 2"],
        "target_rows": 25
      }
    ]
  },
  "table_name": "Table Name",
  "sample_rows": [
    {
      "id_values": {"Col1": "val1", "Col2": "val2"},
      "source": "Starting table name",
      "match_score": 0.95,
      "model_used": "column_definition"
    }
  ]
}
```

### Column Naming Rules

**Column Names:** Short, friendly, CSV-safe (no commas, parentheses, quotes)
- ✅ "Far-Right US Coverage"
- ❌ "Far-Right US Coverage (Breitbart, Daily Wire)"

**Details go in description field:**
- Name: "Far-Right US Coverage"
- Description: "How far-right US sources like Breitbart, Daily Wire report this story"

═══════════════════════════════════════════════════════════════
## 🎯 FINAL CHECKLIST
═══════════════════════════════════════════════════════════════

**ALWAYS OUTPUT:**
- [ ] Column definitions (ID + research columns)
- [ ] Requirements (at least 1 hard or soft)
- [ ] Table name

**CHECK DATA SOURCES (Priority Order):**
- [ ] Do I have extracted_tables? → Use for JUMP START
- [ ] Is starting_tables.is_complete_enumeration: true? → Use for complete enumeration
- [ ] Does conversation have pasted document? → Extract manually
- [ ] None of above? → Row discovery path

**IF COMPLETE ROWS PATH:**
- [ ] Output complete_rows with ALL entities
- [ ] Output search_strategy with requirements (NO subdomains)
- [ ] Prioritize rows output if token limited

**IF ROW DISCOVERY PATH:**
- [ ] Use starting_tables to design discoverable columns
- [ ] Output subdomains (2-10) with search strategy
- [ ] Output sample_rows from starting_tables
- [ ] Design for discoverability (not too narrow)

**Return your response as valid JSON matching the format above.**
