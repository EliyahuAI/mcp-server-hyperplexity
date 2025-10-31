# Column Definition Task

{{#RESTRUCTURING_GUIDANCE}}
═══════════════════════════════════════════════════════════════
## 🔄 RESTRUCTURING MODE - Previous Attempt Failed
═══════════════════════════════════════════════════════════════

**IMPORTANT: This is a RESTRUCTURE after a previous execution found 0 rows.**

### Previous Failure Context
- **Previous attempt**: Found 0 rows with the table structure you defined earlier
- **Reason**: {{FAILURE_REASON}}

### QC's Analysis and Guidance

**Column Changes Needed:**
{{COLUMN_CHANGES}}

**Requirement Changes Needed:**
{{REQUIREMENT_CHANGES}}

**Search Strategy Changes:**
{{SEARCH_BROADENING}}

### Your Task for This Restructure

You MUST incorporate the guidance above when redefining the table:
1. **Simplify ID columns** as instructed - Keep them to 1-5 words, simple identifiers
2. **Relax requirements** - Move hard requirements to soft, move soft to research columns
3. **Broaden search domains/queries** as suggested - Find entities where they're actually listed
4. **Add support columns** if needed - Break complex validations into discoverable steps
5. **Design for discoverability** - Think about what's actually findable via web search
6. **Keep user's intent** but make it MORE DISCOVERABLE

**Key principle**: The entities likely exist, but your previous structure made them hard to find via web search. Make it simpler and broader this time.

**Pay special attention to:**
- Are my new ID columns ACTUALLY simple? (Not "story description", use "story headline")
- Have I moved enough criteria to research columns? (Not discovery requirements)
- Do my search queries target LISTS of entities? (Not individual entities)
- Have I added support columns for complex validations? (Email pattern before email)

---

{{/RESTRUCTURING_GUIDANCE}}
═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **YOUR CORE TASK**: Define columns, find authoritative lists, create search strategy
2. **DESIGN FOR ROW DISCOVERY** (NEW - CRITICAL): How to structure tables for successful row finding
3. **SUPPORT COLUMNS STRATEGY** (NEW - CRITICAL): Breaking complex validations into discoverable steps
4. **STEP 1**: Find authoritative lists that can provide row candidates en masse
5. **INFORMATION PROVIDED**: Conversation context, user requirements, research topics
6. **EXAMPLE**: Job search table showing complete output structure
7. **ROW REQUIREMENTS**: Define hard and soft requirements for valid rows
8. **KEY PRINCIPLES**: Column naming, ID vs research columns, descriptions, validation
9. **YOUR TASK**: Step-by-step instructions with subdomain strategy
10. **DOMAIN FILTERING**: Optional include/exclude domains (use carefully)
11. **SUBDOMAIN DESIGN**: How to structure subdomains as organizational tools
12. **FINAL REMINDER**: Core task repeated with critical constraints

═══════════════════════════════════════════════════════════════
## 🎯 YOUR CORE TASK
═══════════════════════════════════════════════════════════════

**GOAL:** Define precise column specifications and search strategy for populating a research table

**DELIVERABLES:**
- Column definitions (ID columns + research columns) with detailed descriptions
- Search strategy with 2-10 subdomains covering the search space
- Authoritative lists (URLs + candidates) for as many subdomains as possible
- Hard and soft requirements defining valid rows
- Table name and tablewide research context

**KEY RULES:**
1. ✅ **Design for discoverability** - Structure tables so rows are FINDABLE via web search
2. ✅ **Use support columns** - Break complex validations into intermediate steps
3. ✅ Find authoritative lists FIRST (NIH grants, Wikipedia lists, Crunchbase, etc.)
4. ✅ Use SHORT column names (details go in description)
5. ✅ ID columns = simple identifiers, Research columns = validated complex data
6. ✅ Search queries must find LISTS not individual entities
7. ✅ Each subdomain gets its own discovered list and candidates

---

═══════════════════════════════════════════════════════════════
## 🎯 DESIGN FOR ROW DISCOVERY (CRITICAL - READ THIS FIRST!)
═══════════════════════════════════════════════════════════════

**CORE PRINCIPLE: Your table design determines whether rows can be found at all.**

### Why This Matters

When you define requirements and columns, you're not just organizing data - you're determining whether the row discovery process will succeed or fail. **If requirements are too specific or hard to verify from web searches, you will get 0 rows, no matter how good the search strategy.**

### The Discovery Reality Check

**Before finalizing your table design, ask yourself:**

1. **"Can I find entities matching these requirements via web search?"**
   - ❌ BAD: "Companies with internal GenAI adoption AND active hiring AND Series B+ funding"
   - ✅ GOOD: "Well-funded tech companies" + research columns for GenAI adoption, hiring status

2. **"What information actually appears in web search results?"**
   - Web searches return: Company names, headlines, basic facts, public directories
   - Web searches DON'T easily return: Internal programs, unpublished initiatives, proprietary data

3. **"Am I making the row requirements too narrow?"**
   - Every hard requirement ELIMINATES potential rows
   - Every complex ID column makes discovery HARDER
   - Overly specific = 0 rows found

### The Solution: Offload Requirements to Research Columns

**STRATEGY: Make row identification EASY, then filter/validate via research columns.**

**Instead of:**
```
Hard Requirements:
- Must be biotech company
- Must have active AI/ML job posting
- Must be Series B funded or later
- Must have published research in last 2 years
```

**Do this:**
```
Hard Requirements:
- Must be a company

Soft Requirements:
- Prefers biotech or life sciences sector
- Prefers well-funded startups

Research Columns:
- "Has Active AI/ML Job Posting" (Boolean/URL) - validation will check
- "Funding Stage" (String) - validation will determine
- "Recent Publications" (Boolean/Description) - validation will verify
```

**Result:** Row discovery finds MANY biotech companies easily, then validation filters to only those with job postings, correct funding, and publications.

### Discovery-Friendly Table Design Patterns

**Pattern 1: Broad Discovery + Validation Filtering**
- ✅ Discover: All AI companies (easy to find via lists)
- ✅ Validate: Has GenAI program, Has hiring page, Founded after 2020
- Result: 50 companies discovered → 15 pass validation

**Pattern 2: Multiple Simple Criteria vs One Complex Criterion**
- ❌ Hard Requirement: "Radiology departments with AI programs"
- ✅ Better: Discover all major hospital radiology departments → Research column "Has AI Program"

**Pattern 3: Public Data First, Private Data via Validation**
- ✅ ID Columns: Company name, website (publicly listed)
- ✅ Research Columns: Internal programs, hiring status, tech stack (validated later)

### When You're in Restructure Mode

**If you're seeing this after a 0-row failure, PAY EXTRA ATTENTION to the QC guidance above.**

The QC has analyzed WHY the previous attempt failed. Common causes:
- ID columns were too complex ("Detailed story description" instead of "Story headline")
- Requirements were too restrictive (too many hard requirements)
- Search domains were too niche (entities exist but not in searchable form)
- Criteria required proprietary/internal data not available via web search

**Your restructure task:**
- Simplify ID columns to basic identifiers only
- Move restrictive criteria from hard requirements to soft requirements
- Convert verification criteria into research columns
- Broaden search domains to where entities are actually listed

---

═══════════════════════════════════════════════════════════════
## 🔧 SUPPORT COLUMNS STRATEGY (CRITICAL - NEW CONCEPT!)
═══════════════════════════════════════════════════════════════

**CORE PRINCIPLE: Break complex validations into discoverable intermediate steps.**

### Why Support Columns?

Some research columns are HARD to validate directly but EASY to validate if you have supporting information first. By adding intermediate "support columns," you dramatically increase validation success rates.

### The Problem: Complex Single-Step Validations

**Example 1: Finding a specific person's email**
- ❌ Direct approach: "Find Jane Smith's email at Stanford University"
- Problem: Requires knowing BOTH the person AND the institution's email format
- Success rate: 30% (often fails)

**Example 2: Verifying a niche program exists**
- ❌ Direct approach: "Does company X have an AI ethics program?"
- Problem: Requires finding specific internal program information
- Success rate: 40% (hit or miss)

### The Solution: Support Columns as Stepping Stones

**Support columns gather intermediate information that makes the final validation easier.**

### Support Column Pattern Examples

**Pattern 1: Email Discovery via Institution Pattern**

Instead of:
```json
{
  "name": "Email",
  "description": "Contact email for the researcher",
  "validation_strategy": "Find the researcher's email address"
}
```

Use support columns:
```json
[
  {
    "name": "Institution Email Pattern",
    "description": "The email format used by the researcher's institution (e.g., firstname.lastname@stanford.edu, flast@mit.edu)",
    "importance": "RESEARCH",
    "validation_strategy": "Visit the institution's directory or faculty page. Look for 2-3 example email addresses from the same department. Identify the pattern: firstname.lastname@domain, flast@domain, firstinitiallastname@domain, etc."
  },
  {
    "name": "Email",
    "description": "Contact email for the researcher, constructed using the institution's email pattern and the researcher's name",
    "importance": "RESEARCH",
    "validation_strategy": "Using the Institution Email Pattern and the researcher's name, construct the likely email address. Verify if possible by checking the institution directory, publications, or Google Scholar profile."
  }
]
```

**Why this works:**
1. First validation: Find institution email pattern (easier - just need 2-3 examples)
2. Second validation: Apply pattern to researcher's name (mechanical step)
3. Result: 85% success rate vs 30% direct approach

---

**Pattern 2: Program Discovery via Department Check**

Instead of:
```json
{
  "name": "Has AI Ethics Program",
  "description": "Whether the company has an AI ethics initiative",
  "validation_strategy": "Search for AI ethics program at the company"
}
```

Use support columns:
```json
[
  {
    "name": "Has Dedicated AI/ML Team",
    "description": "Whether the company has a clearly defined AI or machine learning team/department",
    "importance": "RESEARCH",
    "validation_strategy": "Check company website, LinkedIn company page, and job postings. Look for: AI team mentioned on About page, AI/ML job postings, LinkedIn employees with 'AI' or 'ML' in titles. Much easier to find than specific ethics programs."
  },
  {
    "name": "Has AI Ethics Program",
    "description": "Whether the company has a formal AI ethics, responsible AI, or AI safety initiative",
    "importance": "RESEARCH",
    "validation_strategy": "NOW that we know they have an AI team (from previous column), search more specifically: '[company name] AI ethics', '[company name] responsible AI', check their AI team's page for ethics mentions, look for ethics-related job postings or blog posts. If no AI team exists, mark as 'N/A - No AI team found'."
  }
]
```

**Why this works:**
1. First validation: Find AI team (broad, easy to verify from jobs/LinkedIn)
2. Second validation: Look for ethics program within that team (narrower scope)
3. If no AI team found, skip ethics check entirely (saves time)
4. Result: 70% success rate vs 40% direct approach

---

**Pattern 3: Contact Discovery via Role Hierarchy**

Instead of:
```json
{
  "name": "Head of AI Contact",
  "description": "Contact information for the head of AI",
  "validation_strategy": "Find the head of AI's contact information"
}
```

Use support columns:
```json
[
  {
    "name": "Head of AI Name",
    "description": "Name of the person leading AI initiatives (Head of AI, VP of AI, Chief AI Officer, or similar title)",
    "importance": "RESEARCH",
    "validation_strategy": "Check company website leadership page, LinkedIn company page for employees with 'AI' in title, press releases mentioning AI leadership, Crunchbase team info. Just need the NAME first, not contact info."
  },
  {
    "name": "Head of AI LinkedIn",
    "description": "LinkedIn profile URL for the head of AI",
    "importance": "RESEARCH",
    "validation_strategy": "Using the Head of AI Name from previous column, search LinkedIn: '[name] [company] AI'. Verify it's the correct person by checking their current role matches the company."
  },
  {
    "name": "Head of AI Email",
    "description": "Contact email for the head of AI",
    "importance": "RESEARCH",
    "validation_strategy": "Using the Head of AI Name and company email pattern (if available from other columns), construct likely email. Or check their LinkedIn profile for contact info, company directory, or conference speaker bios."
  }
]
```

**Why this works:**
1. First: Get the NAME (easiest - from leadership page, LinkedIn, press)
2. Second: Find their LinkedIn (easier with name - just search)
3. Third: Get email (easier with name + LinkedIn + pattern)
4. Each step builds on previous, increasing success rate at each stage

---

### When to Use Support Columns

**Use support columns when validation requires:**

1. **Multi-step reasoning**
   - Example: Verifying a specific person's role requires finding the person first

2. **Pattern-based construction**
   - Example: Email addresses follow institutional patterns

3. **Hierarchical information**
   - Example: Finding a department program requires confirming the department exists first

4. **Conditional validation**
   - Example: Only check for ethics program IF company has an AI team

5. **Hard-to-find niche data**
   - Example: Internal initiatives easier to find if you know the relevant team first

### Support Column Design Guidelines

**Good support columns are:**
- ✅ **Easier to validate** than the final target column
- ✅ **Mechanically useful** for the next validation step
- ✅ **Independently valuable** (useful even if next step fails)
- ✅ **Publicly available** (not requiring insider knowledge)

**Examples of good support columns:**
- Institution email pattern (helps with individual emails)
- Department/team existence (helps with program discovery)
- Person's name (helps with contact discovery)
- General company info (helps with specific program verification)
- Public leadership roster (helps with role-specific contact info)

---

═══════════════════════════════════════════════════════════════
## ⚠️ STEP 1: Find Authoritative Lists (CRITICAL - Do This First!)
═══════════════════════════════════════════════════════════════

**BEFORE defining columns, use web search to find authoritative lists that can provide row candidates en masse.**

### Strategy: Think "Where is the complete list?"

Ask yourself: **"Is there an existing directory, database, or authoritative list I can use?"**

#### Examples of Authoritative Lists:

**Need funded researchers?**
- NIH RePORTER database of all NIH grants
- NSF Awards database
- EU Horizon grants database

**Need countries?**
- Wikipedia list of sovereign states
- UN member states list
- ISO 3166 country codes

**Need AI companies?**
- Crunchbase AI category companies
- LinkedIn companies tagged "artificial intelligence"
- CBInsights AI 100 list

**Need universities?**
- Carnegie Classification of institutions
- Times Higher Education rankings
- National university associations

**Need government officials?**
- Official government directories
- Wikipedia lists by position/country
- Parliamentary/Congressional databases

**Need academic papers?**
- arXiv categories
- PubMed searches with filters
- Google Scholar subject searches

**Need companies in sector X?**
- Industry association member lists
- Stock exchange sector listings
- Trade publication directories

### How to Use Lists in Subdomains

**If you find a complete authoritative list**, structure subdomains by SEGMENTS of that list:

**Example 1: Countries**
```json
"subdomains": [
  {
    "name": "Countries A-E",
    "focus": "Sovereign nations from Afghanistan to Estonia",
    "discovered_list_url": "https://en.wikipedia.org/wiki/List_of_sovereign_states",
    "candidates": ["Afghanistan", "Albania", "Algeria", "Angola", "Argentina"],
    "search_queries": [
      "site:wikipedia.org list of sovereign states",
      "UN member states alphabetical list"
    ],
    "target_rows": 50
  },
  {
    "name": "Countries F-M",
    "focus": "Sovereign nations from Fiji to Myanmar",
    "discovered_list_url": "https://en.wikipedia.org/wiki/List_of_sovereign_states",
    "candidates": ["Fiji", "Finland", "France", "Gabon", "Gambia"],
    "search_queries": [
      "site:wikipedia.org list of sovereign states",
      "UN member states alphabetical list"
    ],
    "target_rows": 60
  }
]
```

**Example 2: NIH Researchers**
```json
"subdomains": [
  {
    "name": "2024 NIH Awardees (Surnames A-D)",
    "focus": "NIH-funded researchers with surnames starting A-D",
    "discovered_list_url": "https://reporter.nih.gov/",
    "candidates": ["John Andrews - USC", "Sarah Davis - MIT", "Robert Chen - Stanford"],
    "search_queries": [
      "site:reporter.nih.gov 2024 grants awarded",
      "NIH RePORTER principal investigators 2024"
    ],
    "target_rows": 50
  }
]
```

**Example 3: Top AI Companies**
```json
"subdomains": [
  {
    "name": "Forbes AI 50 Companies",
    "focus": "Companies from Forbes AI 50 2024 list",
    "discovered_list_url": "https://www.forbes.com/lists/ai50/",
    "candidates": ["Anthropic", "OpenAI", "Databricks", "Scale AI", "Hugging Face"],
    "search_queries": [
      "site:forbes.com AI 50 list 2024",
      "Forbes top AI companies 2024 complete list"
    ],
    "target_rows": 50
  },
  {
    "name": "Crunchbase AI Companies (Series B+)",
    "focus": "Well-funded AI companies from Crunchbase",
    "discovered_list_url": "https://www.crunchbase.com/discover/organization.companies",
    "candidates": ["Cohere", "Inflection AI", "Adept", "Character.AI", "Jasper"],
    "search_queries": [
      "site:crunchbase.com AI companies Series B funding",
      "Crunchbase artificial intelligence category funded"
    ],
    "target_rows": 30
  }
]
```

### When No Complete List Exists

If you can't find ONE complete authoritative list, look for MULTIPLE partial lists:

**Example: GenAI Job Postings**
```json
"subdomains": [
  {
    "name": "LinkedIn GenAI Jobs - Top Tech",
    "focus": "Generative AI positions at major tech companies on LinkedIn",
    "discovered_list_url": "https://www.linkedin.com/jobs/search/?keywords=generative%20AI",
    "candidates": ["Senior GenAI Engineer at Google", "AI Researcher at Meta", "ML Engineer at Anthropic"],
    "search_queries": [
      "LinkedIn jobs generative AI FAANG",
      "site:linkedin.com/jobs generative AI engineer 2024"
    ],
    "target_rows": 40
  },
  {
    "name": "Y Combinator AI Startups Hiring",
    "focus": "YC-backed AI companies with open positions",
    "discovered_list_url": "https://www.ycombinator.com/companies",
    "candidates": ["ML Engineer at Vanta", "AI Researcher at Ramp", "GenAI Engineer at Brex"],
    "search_queries": [
      "Y Combinator batch 2024 AI companies hiring",
      "site:ycombinator.com/companies AI machine learning"
    ],
    "target_rows": 20
  }
]
```

**Note how search_queries target AGGREGATOR SITES that list many entities at once, not individual entity searches.**

---

### Output Format for Discovered Lists

**CRITICAL:** Each subdomain should have its OWN discovered list and candidates specific to that subdomain's focus area.

In each subdomain object, include:
- `discovered_list_url`: URL of the authoritative list source (if found for THIS subdomain)
- `candidates`: Array of 3-10 specific example candidates from THIS subdomain's list with their primary ID values
- If candidates include compound IDs, format them clearly (e.g., "John Andrews - USC" for researcher + institution)

**Search Queries Must Find LISTS, Not Individual Entities:**
- ❌ BAD: "preclinical imaging director pharma" → Returns individuals one at a time
- ✅ GOOD: "Charles River Laboratories imaging staff directory" → Returns many people at once
- ❌ BAD: "AI researcher Stanford" → Returns individuals
- ✅ GOOD: "Stanford AI faculty list" → Returns many researchers at once
- ❌ BAD: "biotech startup founder" → Returns individuals
- ✅ GOOD: "Y Combinator biotech batch 2024" → Returns many companies at once

**Examples of Good List-Finding Search Queries:**
- "NIH RePORTER grants [disease/field]" → Grant database with many recipients
- "[University] faculty directory [department]" → Complete faculty list
- "[Conference] speakers 2024" → List of all speakers
- "Forbes [industry] 50 list 2024" → Curated top 50 list
- "[Company] leadership team" → Complete team roster
- "Crunchbase [category] companies series B" → Database of companies

**IMPORTANT:**
- These candidates should be ACTUAL entities you found via web search, not made-up examples!
- Each subdomain's candidates should be DIFFERENT and specific to that subdomain's focus
- If a subdomain focuses on "NIH-funded researchers", candidates should come from NIH RePORTER
- If a subdomain focuses on "EU researchers", candidates should come from EU grant databases

---

═══════════════════════════════════════════════════════════════
## 📚 INFORMATION PROVIDED
═══════════════════════════════════════════════════════════════

**Conversation History:** The discussion with the user that led to this table
{{CONVERSATION_CONTEXT}}

**User's Requirements:** What the user wants to track
{{USER_REQUIREMENTS}}

**Background Research Topics:** Specific items to research that affect column design (if any)
{{CONTEXT_RESEARCH}}

---

═══════════════════════════════════════════════════════════════
## 📝 EXAMPLE: Job Search Table
═══════════════════════════════════════════════════════════════

**User wants:** Track great jobs for Jenifer Siegelman (see LinkedIn profile)

**Column outline from user:**
- Job title and company
- Responsibilities
- Goodness of fit
- Location
- Job posting URL

**Your output should be:**

```json
{
  "columns": [
    {
      "name": "Job Title",
      "description": "Official job title as listed in the posting",
      "format": "String",
      "importance": "ID",
      "validation_strategy": ""
    },
    {
      "name": "Company",
      "description": "Organization or institution offering the position",
      "format": "String",
      "importance": "ID",
      "validation_strategy": ""
    },
    {
      "name": "Job Responsibilities",
      "description": "Key duties and expectations for the role, including clinical, technical, research, and leadership responsibilities. Focus on specific tasks related to medical imaging, AI/ML development, protocol development, or team leadership.",
      "format": "String",
      "importance": "RESEARCH",
      "validation_strategy": "Extract from job posting description section, focusing on day-to-day responsibilities, required tasks, and key deliverables. Look for bullet points under 'Responsibilities' or 'What You'll Do' sections."
    },
    {
      "name": "Match Score",
      "description": "Numerical score (1-10) indicating how well this role matches Jenifer's background in radiology, AI/ML, public health, and leadership. Higher scores indicate better alignment with her expertise.",
      "format": "Number",
      "importance": "RESEARCH",
      "validation_strategy": "Compare job requirements against Jenifer's LinkedIn profile. Score based on: radiology/medical imaging requirements (0-3 points), AI/ML technical skills (0-3 points), public health or research focus (0-2 points), leadership opportunities (0-2 points). Sum for total score."
    },
    {
      "name": "Key Match Reasons",
      "description": "2-3 bullet points explaining the strongest alignment points between this role and Jenifer's background. Focus on specific skills, experiences, or qualifications that make her an excellent candidate.",
      "format": "String",
      "importance": "RESEARCH",
      "validation_strategy": "Extract top 2-3 requirements from job posting that match Jenifer's background. Reference specific experiences from her LinkedIn: radiology board certification, AI/ML publications, public health MPH, leadership roles. Format as concise bullet points."
    },
    {
      "name": "Location",
      "description": "Geographic location of the position (city, state/region). Note if remote, hybrid, or on-site. Include relocation considerations if relevant.",
      "format": "String",
      "importance": "RESEARCH",
      "validation_strategy": "Extract from job posting location field or description. Check if remote/hybrid options mentioned. Note any relocation assistance or geographic flexibility mentioned in the posting."
    },
    {
      "name": "Job Posting URL",
      "description": "Direct link to the job application page or posting. Must be an active, accessible URL that leads to the specific position.",
      "format": "URL",
      "importance": "RESEARCH",
      "validation_strategy": "Verify URL is active and leads to the correct job posting. Check that it's a direct link (not a search results page) and includes application instructions or an apply button."
    }
  ],
  "search_strategy": {
    "description": "Find medical imaging and AI/healthcare job opportunities matching Jenifer Siegelman's expertise in radiology, AI/ML, and public health",
    "requirements": [
      {
        "requirement": "Must be a job posting (not a person, company, or article)",
        "type": "hard",
        "rationale": "Basic entity type - universally verifiable"
      },
      {
        "requirement": "Prefers positions in healthcare, medical, or health-tech sector",
        "type": "soft",
        "rationale": "Jenifer's background is specifically in healthcare and medicine"
      },
      {
        "requirement": "Prefers roles that combine clinical expertise with AI/ML technology",
        "type": "soft",
        "rationale": "Best fit leverages both her medical training and technical skills"
      },
      {
        "requirement": "Prefers leadership or senior-level positions",
        "type": "soft",
        "rationale": "Matches her experience level and career trajectory"
      }
    ],
    "requirements_notes": "Ideal roles bridge clinical medicine and AI innovation, allowing her to leverage both her MD and technical expertise.",
    "subdomains": [
      {
        "name": "Medical Imaging & Radiology Positions",
        "focus": "Radiologist roles, medical imaging directors, and clinical AI positions in healthcare",
        "search_queries": [
          "radiologist AI positions 2025",
          "medical imaging director jobs with AI focus",
          "clinical radiology positions with machine learning"
        ],
        "target_rows": 10
      },
      {
        "name": "AI/ML Healthcare Roles",
        "focus": "AI research and development positions in healthcare and medical technology companies",
        "search_queries": [
          "healthcare AI researcher jobs 2025",
          "medical AI/ML engineer positions",
          "AI for healthcare product manager roles"
        ],
        "target_rows": 10
      }
    ]
  },
  "table_name": "Job Opportunities for Jenifer Siegelman",
  "tablewide_research": "Target roles combining radiology expertise with AI/ML skills in healthcare settings"
}
```

---

═══════════════════════════════════════════════════════════════
## ✔️ ROW REQUIREMENTS (Minimum 1 Required)
═══════════════════════════════════════════════════════════════

**CRITICAL:** You must define at least ONE requirement for what makes a good row. You can specify hard requirements, soft requirements, or both.

**NOTE:** It is completely valid to have NO hard requirements and ONLY soft requirements. The schema requires at least 1 requirement total, but it can be entirely soft.

### Requirements Must Be Self-Contained and Comprehensive

Requirements should be comprehensive enough that someone could understand exactly what rows are needed by ONLY reading the requirements, WITHOUT needing to see the user's original request or table purpose.

**Before finalizing requirements:**
- Could someone understand exactly what rows we need by ONLY reading these requirements?
- Have I captured ALL key aspects of what makes a valid row?
- Don't assume context - make everything explicit
- Every key aspect mentioned by the user should appear in requirements

### Hard Requirements

Typically 0-2 hard requirements. Use for entity type, geography, or time period if critical.

**Examples:**
- "Must be a biotech company" (specific entity type)
- "Must be US-based" (if geography is critical)
- "Must be from 2024" (if time period is critical)
- Can have none (all soft) if entity type would be too generic

**What NOT to use as hard requirements:**
- Size/scale → Make it soft + add research column
- Industry activities → Make it soft + add research column
- Specific characteristics → Make it soft + add research column

### Soft Requirements

Most requirements should be soft. Use "Prefers" language.

**Examples:**
- "Prefers midsized companies (100-500 employees)"
- "Prefers biotech sector"
- "Prefers companies with active job postings"
- "Prefers companies founded after 2020"

### Converting Criteria to Research Columns

Complex criteria should become research columns for validation:
- "midsized" → Research column "Employee Count"
- "in biotech" → Research column "Industry Sector"
- "actively hiring" → Research column "Has Active Job Postings"
- "has GenAI program" → Research column "Has GenAI Program"

### Requirements Notes

In addition to the requirements array, provide a `requirements_notes` field with 1-2 sentences of overall guidance about what makes a good row for this table. This is not a requirement itself but helps guide the discovery process.

Example: "Looking for authoritative sources with detailed analysis. Company size and funding stage matter less than innovation in the space."

---

═══════════════════════════════════════════════════════════════
## 🔑 KEY PRINCIPLES
═══════════════════════════════════════════════════════════════

### Column Naming Guidelines

**Keep column names SHORT and friendly:**
- ✅ "Far-Right US Coverage"
- ✅ "Publication Date"
- ✅ "Meta-Analysis"
- ❌ "Far-Right US Coverage (Breitbart, Daily Wire, etc.)"
- ❌ "International Right Coverage (Daily Mail UK, The Telegraph, etc.)"

**Put details in the description field:**
- Column name: "Far-Right US Coverage"
- Description: "How far-right US sources like Breitbart, Daily Wire, OAN report this story"

**Avoid special characters in column names:**
- Don't use: Parentheses (), Commas, Quotes
- Use simple alphanumeric with spaces and hyphens

### ID Columns (Define the row, NOT validated)

**CRITICAL CONSTRAINTS FOR ID COLUMNS:**
- Must be SHORT, simple, repeatable identifiers
- Maximum 1-5 words typically (e.g., "Google", "2025-01-15", "Chief Data Officer")
- Must be easily discoverable from web searches or listings
- Should NOT require complex reasoning or synthesis
- Should NOT be paragraphs or detailed descriptions

**Good ID Column Examples:**
- ✅ Company Name (e.g., "Anthropic", "OpenAI")
- ✅ Job Title (e.g., "Senior ML Engineer", "Product Manager")
- ✅ Paper Title (e.g., "Attention Is All You Need")
- ✅ Product Name (e.g., "ChatGPT", "Claude")
- ✅ Date (e.g., "2025-01-15")
- ✅ Person Name (e.g., "Sam Altman")
- ✅ URL (e.g., "https://example.com/article")

**Bad ID Column Examples:**
- ❌ "Basic Story Description" - Too detailed, requires synthesis
- ❌ "Key Responsibilities" - Paragraphs of text, not a simple identifier
- ❌ "Detailed Analysis" - Requires research, not straightforward
- ❌ "Summary of Findings" - Multiple sentences, too complex
- ❌ "Goodness of Fit Analysis" - Requires reasoning and comparison

**Rule of Thumb:** If you can find this value in a bullet-point list, directory, or index, it's a good ID column. If it requires reading multiple paragraphs and synthesizing information, it should be a research column instead.

**Technical Requirements:**
- Set `importance: "ID"`
- Set `validation_strategy: ""` (empty string - no validation needed)
- Used to uniquely identify each row
- Will be discovered during row discovery phase (not validated later)

### Research Columns (To be validated)

**Purpose:** These columns will be populated during validation and can encode complex criteria.

**Use research columns for:**
- Criteria that require visiting websites/reading content
- Criteria that require cross-referencing multiple sources
- Binary checks that could filter entities: "Has Active Job Posting", "Has GenAI Program"
- Detailed information: descriptions, counts, dates

**Examples:**
- "Has Head of AI Job Posting" (Boolean/URL) - Checks careers page
- "Has Existing GenAI Program" (Boolean/Description) - Checks news and company site
- "Recent Funding Round" (Date/Amount) - Checks Crunchbase recent activity
- "Uses Technology X" (Boolean) - Checks tech stack indicators

**These act as validation filters:** Rows with "No" for critical research columns can be filtered out during validation.

**Technical requirements:**
- Set `importance: "RESEARCH"` (or "CRITICAL" for must-have data)
- Detailed descriptions explaining EXACTLY what data to find
- Specific validation strategies explaining HOW to find the data (REQUIRED - cannot be empty)
- May reference specific sources, methods, or criteria
- Focus on actionable, findable information

### Detailed Descriptions
Make descriptions comprehensive and specific:
- ✅ "Key duties and expectations for the role, including clinical, technical, research, and leadership responsibilities"
- ❌ "Job responsibilities"

### Validation Strategies
Be explicit and actionable:
- ✅ "Extract from job posting description section, focusing on day-to-day responsibilities. Look for bullet points under 'Responsibilities' or 'What You'll Do' sections."
- ❌ "Check job posting"

---

═══════════════════════════════════════════════════════════════
## 📋 YOUR TASK - Step by Step
═══════════════════════════════════════════════════════════════

Using the information provided above:

1. **Define columns** based on what the user outlined
   - Expand brief mentions into detailed specifications
   - Add comprehensive descriptions
   - Create specific validation strategies for research columns

**CRITICAL Column Naming Rules:**
- Column names: Short, friendly, CSV-safe (no commas, parentheses, quotes)
- Column descriptions: Detailed, include source examples and specifics
- Example sources/details go in description, NOT in the column name

2. **Create search strategy**
   - 2-10 subdomains that cover the search space
   - Each subdomain has: name, focus, search_queries (3-5), target_rows
   - Search queries should yield multiple entities (lists, directories)

   **CRITICAL: Subdomain Count & Row Target Strategy**

   The number of subdomains and total target rows should be determined strategically based on:
   - **Discovery difficulty** (how niche/rare the entities are)
   - **User's requested row count** (what they asked for in conversation)
   - **Requirement complexity** (simple list vs. multi-criteria search)

   **Subdomain Count Decision Matrix:**
   | User Wants | Topic Difficulty | Complexity | Use Subdomains | Rationale |
   |------------|------------------|------------|----------------|-----------|
   | ≤20 rows | Common/Easy | Simple | 2-3 | Efficient, low overlap |
   | 21-50 rows | Moderate | Moderate | 4-5 | Balanced coverage |
   | 51-100 rows | Challenging/Niche | Complex | 6-8 | Wide net needed |
   | 100+ rows | Very Niche | Very Complex | 8-10 | Maximum coverage |

   **Examples:**
   - "Fortune 500 companies" → 2-3 subdomains (common, easy to find)
   - "Biotech companies hiring AI engineers" → 5-6 subdomains (niche, multiple criteria)
   - "Academic papers on quantum AI from 2024" → 7-8 subdomains (very specific, time-bound)
   - "Local government AI initiatives globally" → 9-10 subdomains (very rare, dispersed)

   **Target Row Calculation Formula:**
   ```
   overshoot_factor = 1.3 to 1.5 (30-50% buffer to ensure delivery)
   dedup_compensation = 1.0 + ((subdomain_count - 2) * 0.10)  # 10% overlap per extra subdomain

   total_internal_target = user_requested * overshoot_factor * dedup_compensation
   target_per_subdomain = total_internal_target / subdomain_count (can be weighted or even)
   ```

   **Worked Examples:**

   1. **User wants 20 rows, common topic (Fortune 500):**
      - Subdomains: 3 (easy topic)
      - overshoot_factor: 1.3
      - dedup_compensation: 1.0 + (1 * 0.10) = 1.1
      - total_internal_target: 20 * 1.3 * 1.1 = 28.6 ≈ 29
      - target_per_subdomain: 29 / 3 ≈ 10 each

   2. **User wants 50 rows, niche topic (biotech hiring AI engineers):**
      - Subdomains: 6 (challenging, multi-criteria)
      - overshoot_factor: 1.4
      - dedup_compensation: 1.0 + (4 * 0.10) = 1.4
      - total_internal_target: 50 * 1.4 * 1.4 = 98
      - target_per_subdomain: 98 / 6 ≈ 16 each

   3. **User wants 100 rows, very niche (government AI initiatives):**
      - Subdomains: 9 (very rare, global search)
      - overshoot_factor: 1.5
      - dedup_compensation: 1.0 + (7 * 0.10) = 1.7
      - total_internal_target: 100 * 1.5 * 1.7 = 255
      - target_per_subdomain: 255 / 9 ≈ 28 each

   **Why Overshoot:**
   - QC review rejects 10-30% of candidates on average
   - Deduplication removes overlaps between subdomains
   - We want to DELIVER what we promised, not fall short
   - Better to have options than to scramble for more rows

   **Why More Subdomains for Challenging Topics:**
   - Niche entities are spread across different niches
   - Each subdomain explores a different angle
   - Wider net → better chance of finding rare entities
   - More subdomains = more overlap, hence higher targets needed

   **Why Complex Requirements Need More Subdomains:**
   - Multi-criteria searches ("biotech" AND "hiring" AND "AI") are harder
   - Each subdomain can focus on one aspect of complexity
   - Parallel workers can specialize in different criteria combinations
   - Lower per-subdomain targets prevent worker fatigue

   **Subdomain Design Guidelines:**
   - First subdomains: Specific, focused categories (e.g., "AI Research", "Healthcare AI")
   - Last subdomain: Catch-all for remaining entities (e.g., "Other AI Companies", "Additional Opportunities Not in Above Categories")
   - This ensures complete coverage - nothing is excluded

   **Distribution Strategy (target_rows per subdomain):**
   - **Even distribution:** When all subdomains are equally productive
   - **Weighted distribution:** When some subdomains are richer than others
     - High-yield subdomain: 1.2x average
     - Medium-yield subdomain: 1.0x average
     - Low-yield/catch-all subdomain: 0.6x average

3. **Name the table** clearly and descriptively

4. **Provide tablewide_research** context (2-3 sentences about overall goals)

---

═══════════════════════════════════════════════════════════════
## 🌐 DOMAIN FILTERING (Optional - Use Carefully)
═══════════════════════════════════════════════════════════════

You can optionally specify domain filtering to focus searches on reliable sources and avoid noise.

### CRITICAL WARNING: Include Filters are VERY Restrictive

**If you specify include domains (e.g., ["crunchbase.com"]), the search will be heavily biased toward ONLY those domains. This is rarely what you want unless the user explicitly requested specific sources.**

**Example:**
- `included_domains: ["crunchbase.com"]` → Will mostly return only Crunchbase results, missing other valuable sources
- `excluded_domains: ["youtube.com", "reddit.com"]` → Will search all sources EXCEPT these

### Include Filters (Use ONLY if user explicitly requested specific sources)

**ONLY add domains to included_domains if the user specifically said to focus on those sources.**

**Examples where you SHOULD use include filters:**
- User: "Find companies, focusing on Crunchbase data"
- User: "Search only LinkedIn and AngelList for this"

**If user didn't specify sources → Leave included_domains EMPTY (do not guess)**

❌ **WRONG (speculating on includes):**
```
User: "Find biotech companies"
included_domains: ["crunchbase.com", "biotech.com"]  // Don't guess!
```

✅ **CORRECT:**
```
User: "Find biotech companies"
included_domains: []  // User didn't specify sources
excluded_domains: ["youtube.com", "reddit.com"]  // Safe defaults
```

✅ **ALSO CORRECT (user specified):**
```
User: "Find biotech companies using Crunchbase and LinkedIn"
included_domains: ["crunchbase.com", "linkedin.com"]  // User explicitly requested
excluded_domains: ["youtube.com", "reddit.com"]
```

### Exclude Filters (You can use these liberally)

**Safe to add without user specification. Exclusions help filter noise without over-constraining results.**

**Default exclusions (unless user wants video/social):**
- youtube.com
- reddit.com

**You can add more based on the research needs:**
- Avoid news sites for technical queries: "cnn.com", "foxnews.com"
- Avoid forums for factual queries: "stackexchange.com", "quora.com"

**Exclusions are iteratively refined by discovery workers via search_improvements feedback.**

### Iterative Refinement

**Discovery workers can recommend additional exclusions via domain_filtering_recommendations:**
- These recommendations are reviewed by QC and may be applied in retriggers
- This allows the system to learn which domains are unhelpful for specific queries
- **Never** recommend adding to included_domains unless user explicitly requested more sources

**This iterative process:**
1. Worker discovers that certain domains return low-quality results
2. Worker adds domain_filtering_recommendations in search_improvements
3. QC reviews and decides whether to apply in retrigger
4. Next discovery round benefits from refined exclusions

### Suggested Include Domains by Research Type

**ONLY use these if the user explicitly requested focus on specific sources:**

- **Company research:** crunchbase.com, linkedin.com, techcrunch.com
- **Academic research:** scholar.google.com, arxiv.org, pubmed.ncbi.nlm.nih.gov
- **News coverage:** nytimes.com, wsj.com, reuters.com
- **Job searches:** linkedin.com, indeed.com, glassdoor.com

**Again: Only add these if the user specifically asked for them!**

### Format

- `default_included_domains`: Array of domains to focus on (optional, USE SPARINGLY)
- `default_excluded_domains`: Array of domains to avoid (optional, defaults to ["youtube.com", "reddit.com"])

Subdomains can override these settings if needed for specific searches.

---

═══════════════════════════════════════════════════════════════
## 🎯 SUBDOMAIN DESIGN GUIDELINES
═══════════════════════════════════════════════════════════════

**IMPORTANT: Subdomains are focus areas to help parallel workers avoid overlap, NOT strict boundaries.**

### Purpose of Subdomains

Subdomains help organize the search space so multiple parallel discovery processes can work efficiently without duplicating effort. They are:
- **Suggested focus areas** - not rigid categories
- **Organizational tools** - not filters
- **Overlap prevention** - not exclusion rules

### Key Principle: Flexibility Over Boundaries

**Rows can come from any subdomain, regardless of which subdomain discovered them.**

A row discovered in the "AI Research Companies" subdomain might actually fit better in "Healthcare AI" - and that's okay! The QC review process will handle the final determination of fit.

### Subdomain Strategy

1. **First subdomains:** Specific, focused categories that naturally divide the search space
   - Example: "AI Research Companies", "Healthcare AI Companies", "AI Infrastructure Companies"

2. **Last subdomain:** Catch-all for entities that don't fit neatly into other categories
   - Example: "Other AI Companies Not in Above Categories: AI Research Companies, Healthcare AI Companies, AI Infrastructure Companies" (must be explicit about other groups)
   - This ensures nothing gets excluded due to subdomain boundaries

3. **Soft suggestions to avoid overlap:**
   - Each subdomain provides a suggested focus to prevent workers from finding the same entities
   - Workers CAN include entities outside their focus if found during searches
   - Think of it as "start here, but don't feel constrained"

---

═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER - Your Core Task
═══════════════════════════════════════════════════════════════

**GOAL:** Define precise column specifications and search strategy for populating a research table

**CRITICAL INSTRUCTIONS:**

**🎯 DESIGN FOR DISCOVERABILITY (MOST IMPORTANT!):**
1. ✅ **Make row identification EASY** - Broad entity types, minimal hard requirements
2. ✅ **Offload filtering to research columns** - Let validation handle specifics, not discovery
3. ✅ **Think about web search reality** - What info actually appears in search results?
4. ✅ **In restructure mode** - Carefully apply QC guidance to fix previous failures

**🔧 USE SUPPORT COLUMNS STRATEGICALLY:**
5. ✅ **Break complex validations into steps** - Email pattern → Email, Team exists → Program exists
6. ✅ **Add intermediate columns** - Name → LinkedIn → Contact, not direct to contact
7. ✅ **Each support column should be easier** than the final target column

**📋 STANDARD REQUIREMENTS:**
8. ✅ Use web search to find authoritative lists FIRST (NIH RePORTER, Wikipedia lists, Crunchbase, etc.)
9. ✅ Structure subdomains as SEGMENTS of discovered lists when possible
10. ✅ Each subdomain gets its OWN discovered_list_url and candidates array
11. ✅ Search queries must target LISTS/aggregators, not individual entities
   - ❌ BAD: "AI researcher Stanford" → Returns individuals
   - ✅ GOOD: "Stanford AI faculty list" → Returns many researchers at once
12. ✅ Keep column names SHORT (details in description)
13. ✅ ID columns: Set `importance: "ID"` and `validation_strategy: ""` (empty). Use for simple identifiers (1-5 words)
14. ✅ Research columns: Set `importance: "RESEARCH"` and provide detailed `validation_strategy` (REQUIRED)
15. ✅ At least ONE requirement (hard or soft) is required
16. ✅ Use 2-10 subdomains based on difficulty (more for niche topics)
17. ✅ Overshoot target rows by 30-50% to ensure delivery after QC
18. ✅ Only use included_domains if user EXPLICITLY requested specific sources

**🚨 BEFORE SUBMITTING - FINAL CHECKS:**
- [ ] Can I find entities matching these requirements via a simple web search?
- [ ] Are my ID columns simple identifiers (not complex descriptions)?
- [ ] Have I moved filtering criteria from requirements to research columns?
- [ ] Have I added support columns for any complex multi-step validations?
- [ ] If in restructure mode, have I applied ALL the QC guidance provided?

**Return your column definitions and search strategy as valid JSON.**
