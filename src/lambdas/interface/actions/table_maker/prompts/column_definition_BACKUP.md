# Column Definition Task

## What You're Doing

We have an outline of a series of columns for a research table. Your job is to:
1. **Precisely specify these columns** with detailed descriptions and validation strategies
2. **Provide background research** from specific research topics (if provided)
3. **Create a search strategy** to find the entities that will populate this table

## Information Provided

**Conversation History:** The discussion with the user that led to this table
{{CONVERSATION_CONTEXT}}

**User's Requirements:** What the user wants to track
{{USER_REQUIREMENTS}}

**Background Research Topics:** Specific items to research that affect column design (if any)
{{CONTEXT_RESEARCH}}

---

## Example: Job Search Table

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
      "is_identification": true,
      "validation_strategy": ""
    },
    {
      "name": "Company",
      "description": "Organization or institution offering the position",
      "format": "String",
      "importance": "ID",
      "is_identification": true,
      "validation_strategy": ""
    },
    {
      "name": "Job Responsibilities",
      "description": "Key duties and expectations for the role, including clinical, technical, research, and leadership responsibilities. Focus on specific tasks related to medical imaging, AI/ML development, protocol development, or team leadership.",
      "format": "String",
      "importance": "RESEARCH",
      "is_identification": false,
      "validation_strategy": "Extract from job posting description section, focusing on day-to-day responsibilities, required tasks, and key deliverables. Look for bullet points under 'Responsibilities' or 'What You'll Do' sections."
    },
    {
      "name": "Match Score",
      "description": "Numerical score (1-10) indicating how well this role matches Jenifer's background in radiology, AI/ML, public health, and leadership. Higher scores indicate better alignment with her expertise.",
      "format": "Number",
      "importance": "RESEARCH",
      "is_identification": false,
      "validation_strategy": "Compare job requirements against Jenifer's LinkedIn profile. Score based on: radiology/medical imaging requirements (0-3 points), AI/ML technical skills (0-3 points), public health or research focus (0-2 points), leadership opportunities (0-2 points). Sum for total score."
    },
    {
      "name": "Key Match Reasons",
      "description": "2-3 bullet points explaining the strongest alignment points between this role and Jenifer's background. Focus on specific skills, experiences, or qualifications that make her an excellent candidate.",
      "format": "String",
      "importance": "RESEARCH",
      "is_identification": false,
      "validation_strategy": "Extract top 2-3 requirements from job posting that match Jenifer's background. Reference specific experiences from her LinkedIn: radiology board certification, AI/ML publications, public health MPH, leadership roles. Format as concise bullet points."
    },
    {
      "name": "Location",
      "description": "Geographic location of the position (city, state/region). Note if remote, hybrid, or on-site. Include relocation considerations if relevant.",
      "format": "String",
      "importance": "RESEARCH",
      "is_identification": false,
      "validation_strategy": "Extract from job posting location field or description. Check if remote/hybrid options mentioned. Note any relocation assistance or geographic flexibility mentioned in the posting."
    },
    {
      "name": "Job Posting URL",
      "description": "Direct link to the job application page or posting. Must be an active, accessible URL that leads to the specific position.",
      "format": "URL",
      "importance": "RESEARCH",
      "is_identification": false,
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

## Row Requirements (Minimum 1 Required)

**CRITICAL:** You must define at least ONE requirement for what makes a good row. You can specify hard requirements, soft requirements, or both.

**NOTE:** It is completely valid to have NO hard requirements and ONLY soft requirements. The schema requires at least 1 requirement total, but it can be entirely soft.

### Requirements Must Be Self-Contained and Comprehensive

**GOLDEN RULE:** Requirements should be comprehensive enough that someone could understand exactly what rows are needed by ONLY reading the requirements, WITHOUT needing to see the user's original request or table purpose.

**Before finalizing requirements, ask yourself:**
- Could someone understand exactly what rows we need by ONLY reading these requirements?
- Have I captured ALL key aspects of what makes a valid row?
- If not, add more detail to the requirements until they are self-contained.

**Capture ALL essential criteria from the user's request:**
- Don't assume context - make everything explicit
- Every key aspect mentioned by the user should appear in requirements
- Requirements are used independently during discovery - they must stand alone

## Discovery vs Validation Criteria (CRITICAL DESIGN DECISION)

**Key Principle:** During row discovery, hard requirements should be LIMITED to basic common knowledge attributes. Almost everything else should be soft requirements or research columns.

### Discovery Requirements (Common Knowledge ONLY)
Use these as hard requirements during row discovery:
- **Entity type/category**: "company" (vs person, paper, product), "research paper" (vs blog post, news article)
- **Geographic location** (if absolutely critical): "US-based", "European" - only when geography is fundamental to the request
- **Time period** (if absolutely critical): "published in 2024", "founded after 2020" - only when timing is fundamental

**That's it.** Size, industry, activities, and specific characteristics should be soft requirements or research columns.

These minimal attributes can be determined from:
- Search result snippets showing entity type
- Basic search context (location, date)

### The Golden Rule for Hard Requirements

**Ask:** "Is this attribute part of the entity's basic identity that EVERYONE would agree on?"

Examples:
- ✅ "Is a company" (vs person, paper, product)
- ✅ "Is in the United States" (if geography is critical to user's request)
- ✅ "Published in 2024" (if time period is critical to user's request)
- ❌ "Is midsized" → Soft requirement + research column "Employee Count"
- ❌ "Is in biotech" → Soft requirement + research column "Industry Classification"
- ❌ "Is actively hiring" → Soft requirement + research column "Has Active Job Postings"
- ❌ "Has X characteristic" → Soft requirement + research column to validate X

**Result:** ID columns are just identifiers (Company Name, Website). Everything else is validated through research columns.

### Validation Criteria (Requires Research)
Convert these into RESEARCH COLUMNS and/or SOFT REQUIREMENTS:
- **Size/scale**: "midsized", "Fortune 500" → Soft requirement + research column "Employee Count"
- **Industry/sector**: "biotech", "fintech" → Soft requirement + research column "Industry Sector"
- **Specific programs/initiatives**: "has GenAI program" → Research column "Has GenAI Program"
- **Job postings**: "is hiring for X role" → Research column "Has X Job Posting"
- **Recent activities**: "raised funding recently" → Research column "Recent Funding Round"
- **Technology stack**: "uses React" → Research column "Technology Stack"
- **Relationships**: "partnered with X" → Research column "Partnerships"

These require:
- Reading job posting pages
- Analyzing company websites in depth
- Checking recent news and announcements
- Cross-referencing multiple sources

### Example Transformation

❌ **WRONG (too many hard requirements):**
```
Hard Requirements for Discovery:
- Must be a midsized biotech company
- Must be actively hiring for GenAI leadership roles
- Must not have an existing GenAI program

Columns:
- Company Name
- Website
```

✅ **CORRECT (Option 1 - no hard requirements, maximal soft + research columns):**
```
Hard Requirements for Discovery: (none)

Soft Requirements:
- Prefers biotech companies
- Prefers midsized companies (100-500 employees)
- Prefers companies with active GenAI leadership job postings
- Prefers companies without existing GenAI programs

Columns:
- Company Name (ID)
- Website (ID)
- Industry Sector (Research) - Primary industry classification
- Employee Count (Research) - Approximate number of employees
- Has GenAI Leadership Job Posting (Research) - Yes/No, URL if yes
- Has Existing GenAI Program (Research) - Yes/No, description if yes
```

✅ **ALSO CORRECT (Option 2 - specific hard requirement):**
```
Hard Requirements for Discovery:
- Must be a biotech company

Soft Requirements:
- Prefers midsized companies (100-500 employees)
- Prefers companies with active GenAI leadership job postings
- Prefers companies without existing GenAI programs

Columns:
- Company Name (ID)
- Website (ID)
- Industry Sector (Research) - Primary industry classification
- Employee Count (Research) - Approximate number of employees
- Has GenAI Leadership Job Posting (Research) - Yes/No, URL if yes
- Has Existing GenAI Program (Research) - Yes/No, description if yes
```

**Why these are better:**
- Discovery finds ALL companies broadly (Option 1) or biotech specifically (Option 2), not overly constrained
- Soft requirements guide discovery toward better matches without excluding entities
- Research columns validate and filter each candidate
- Much more efficient, comprehensive, and flexible
- Clear separation of concerns
- Avoids overly generic hard requirements like "Must be a company" as the only constraint

### Hard vs Soft Requirements

**Hard Requirements (Discovery Phase - Common Knowledge ONLY):**

**PURPOSE:** Limit search space to basic entity type. That's it.

**GOLDEN RULE:** Hard requirements should be limited to attributes that are:
- Universally agreed upon (no ambiguity)
- Instantly verifiable from basic search results
- Part of the entity's fundamental identity

**IMPORTANT:** If your only hard requirement would be a generic entity type (e.g., "Must be a company"), consider one of these approaches:

1. **No hard requirements (preferred):** If there are no other fundamental constraints, use ONLY soft requirements
   - Example: User wants "biotech companies" → Hard: (none), Soft: "Prefers biotech companies"

2. **Make entity type more specific:** If entity type can be more specific, do so
   - Example: User wants "biotech companies" → Hard: "Must be a biotech company"
   - Example: User wants "AI companies" → Hard: "Must be an AI/ML company"

3. **Only use generic "must be a company" if there are OTHER hard requirements:**
   - Example: Hard: "Must be a company", "Must be US-based"
   - In this case, geography justifies having entity type as well

**In most cases:** Prefer approach #1 (no hard requirements) or #2 (specific entity type).

**Typically, you should have 0-2 hard requirements:**
- Entity type (optional): "Must be a company" / "Must be a research paper" / "Must be a person"
  - Only include if made more specific OR if combined with other hard requirements
- Geography (optional): "Must be US-based" (only if absolutely critical to user's request)
- Time period (optional): "Must be from 2024" (only if absolutely critical to user's request)

**Examples:**
- ✅ "Must be a biotech company" (specific entity type)
- ✅ "Must be an AI/ML company" (specific entity type)
- ✅ "Must be a company" AND "Must be US-based" (entity type + geography)
- ✅ No hard requirements, only soft (when entity type would be too generic)
- ❌ "Must be a company" as the ONLY hard requirement → Make it specific or remove it
- ❌ "Must be midsized" → SOFT requirement + research column "Employee Count"
- ❌ "Must be in biotech" → Either make it a specific hard requirement "Must be a biotech company" OR soft requirement + research column
- ❌ "Must have job postings" → SOFT requirement + research column "Has Job Postings"
- ❌ "Must not have X" → SOFT requirement + research column "Has X"

**Default approach:** No hard requirements, OR 1 specific hard requirement. Add geography/time only if absolutely critical.

**Soft Requirements (Preferences - Most Requirements Go Here):**

**PURPOSE:** Guide discovery toward better matches without filtering them out.

**MOST REQUIREMENTS SHOULD BE SOFT**, including:
- Size/scale: "Prefers midsized companies (100-500 employees)"
- Industry/sector: "Prefers biotech sector"
- Activities: "Prefers companies actively hiring"
- Attributes: "Prefers companies without existing X"
- Quality indicators: "Prefers recent publications", "Prefers well-funded companies"

**These improve scoring during discovery and are validated through research columns.**

**Key indicators:** "preferably", "ideally", "bonus if", "better if", "prefers"

Examples:
- "Prefers companies with 100-500 employees"
- "Prefers biotechnology or pharmaceutical sector"
- "Prefers companies with recent news (last 6 months)"
- "Prefers positions with remote work options"
- "Prefers companies founded after 2020"

### Distinguishing Hard from Soft: The Critical Test

**NEW PHILOSOPHY: Almost everything should be soft + research columns.**

**Look at the user's request and ask:**
1. "What is the basic entity type?" → Hard requirement
2. "Is geography/time absolutely fundamental?" → Hard requirement if yes
3. "Everything else?" → Soft requirements + research columns

❌ **WRONG** - Too many hard requirements:
```
User request: "Find midsized biotech companies actively hiring for GenAI leadership roles"

Hard: Must be biotech, must be midsized, must have active GenAI leadership job postings
Soft: Prefers companies founded after 2020

Problem: Size, industry, and hiring status require research - they're not basic identity!
```

✅ **CORRECT (Option 1 - No hard requirements):**
```
User request: "Find midsized biotech companies actively hiring for GenAI leadership roles"

Hard Requirements: (none)

Soft:
- Prefers biotech companies
- Prefers midsized companies (100-500 employees)
- Prefers companies with active GenAI leadership job postings

Research Columns:
- Industry Sector (to validate biotech)
- Employee Count (to validate midsized)
- Has GenAI Leadership Job Posting (to validate hiring status)

Why? "Company" is the only entity type, but it's too generic to be useful alone. Better to have no hard requirements.
```

✅ **ALSO CORRECT (Option 2 - Specific entity type):**
```
User request: "Find midsized biotech companies actively hiring for GenAI leadership roles"

Hard: Must be a biotech company

Soft:
- Prefers midsized companies (100-500 employees)
- Prefers companies with active GenAI leadership job postings

Research Columns:
- Industry Sector (to validate biotech)
- Employee Count (to validate midsized)
- Has GenAI Leadership Job Posting (to validate hiring status)

Why? Made entity type specific to "biotech company" rather than generic "company". Everything else validated through research.
```

**More Examples:**

Example 1:
```
User: "Find AI companies that have raised Series B funding, preferably in healthcare"

Hard Requirements: (none)
Soft: Prefers AI/ML companies, prefers Series B funding stage, prefers healthcare sector
Research Columns: Industry Focus, Funding Stage, Healthcare Involvement

Rationale: Generic "company" would be the only hard requirement, so better to use all soft. Funding and industry require research.
```

Example 2:
```
User: "Find research papers on transformer models from 2024, ideally with code available"

Hard: Must be a research paper, must be from 2024
Soft: Prefers papers on transformer models, prefers papers with available code
Research Columns: Primary Topic, Code Availability

Rationale: Entity type (paper) and time (2024) are both critical and specific. Topic and code require validation.
```

Example 3:
```
User: "Find US-based companies building AI safety tools"

Hard: Must be a company, must be US-based
Soft: Prefers companies focused on AI safety tools
Research Columns: Primary Focus Area, AI Safety Product/Service

Rationale: Geography (US-based) is explicitly critical, which justifies also including generic entity type. "Building X" requires research.
```

### Guidance on Hard vs Soft

**New Default:** Start with NO hard requirements, OR 1 specific hard requirement. Add geography/time only if critical.

**Decision tree for hard requirements:**
1. Would the only hard requirement be generic entity type ("Must be a company")? → Use NO hard requirements instead
2. Can entity type be made specific ("Must be a biotech company")? → Use that as the hard requirement
3. Is geography/time critical to the request? → Include as hard requirement along with entity type

**Everything else is soft + research columns:**
- Size/scale → Soft + research column
- Industry/sector → Soft + research column (unless made specific in hard requirement)
- Activities/characteristics → Soft + research column
- Programs/initiatives → Soft + research column

**Why this approach is better:**
- Discovery casts a wide net, finding more candidates
- Soft requirements guide scoring and ranking
- Research columns provide validation and filtering
- More efficient and comprehensive results
- Flexibility to handle edge cases
- Avoids overly basic hard requirements that provide little value

### Requirements Notes

In addition to the requirements array, provide a `requirements_notes` field with 1-2 sentences of overall guidance about what makes a good row for this table. This is not a requirement itself but helps guide the discovery process.

Example: "Looking for authoritative sources with detailed analysis. Company size and funding stage matter less than innovation in the space."

---

## Key Principles

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
- No validation strategy needed (empty string)
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
- Detailed descriptions explaining EXACTLY what data to find
- Specific validation strategies explaining HOW to find the data
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

## Your Task

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
   - 2-5 subdomains that cover the search space
   - Each subdomain has: name, focus, search_queries (3-5), target_rows
   - Search queries should yield multiple entities (lists, directories)

   **Subdomain Design Guidelines:**
   - First subdomains: Specific, focused categories (e.g., "AI Research", "Healthcare AI")
   - Last subdomain: Catch-all for remaining entities (e.g., "Other AI Companies", "Additional Opportunities Not in Above Categories")
   - This ensures complete coverage - nothing is excluded

   **target_rows Strategy:**
   - Use "up to N" approach where N = total target for entire table
   - Each subdomain can return UP TO the full target
   - Richer subdomains will naturally return more candidates
   - Less relevant subdomains will return fewer
   - Deduplication and QC will select the best from all subdomains

   **Example for 3 subdomains (total target: 10 rows):**
   - Subdomain 1: "AI Research Companies" - target_rows: 10 (up to 10)
   - Subdomain 2: "Healthcare AI Companies" - target_rows: 10 (up to 10)
   - Subdomain 3: "Other AI Companies" - target_rows: 10 (up to 10)
   - Total discovered: might be 8 + 7 + 3 = 18 candidates
   - After deduplication + QC: final 10 best selected

3. **Name the table** clearly and descriptively

4. **Provide tablewide_research** context (2-3 sentences about overall goals)

---

## Domain Filtering (Optional)

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

## Subdomain Design Guidelines (Updated)

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

Return valid JSON matching the schema.
