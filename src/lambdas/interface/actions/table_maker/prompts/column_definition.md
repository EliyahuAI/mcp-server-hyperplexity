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
6. **OUTPUT FORMAT**: JSON structure with sample_rows
7. **FINAL REMINDER**: Critical requirements checklist

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

**Why:** Gives QC immediate candidates without waiting for discovery. Discovery will find more rows and merge them (discovery takes precedence for duplicates based on model quality).

**How to Populate:**
1. Look at `starting_tables` from background research
2. Extract 5-15 sample entities (prefer entities with complete info)
3. Fill ID column values only (research columns stay empty)
4. Set `match_score` based on fit with requirements (0.7-0.95 typical)
5. Set `source` to starting table name
6. Set `model_used` to "column_definition"

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
