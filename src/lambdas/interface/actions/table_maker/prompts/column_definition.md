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
      "importance": "CRITICAL",
      "is_identification": false,
      "validation_strategy": "Extract from job posting description section, focusing on day-to-day responsibilities, required tasks, and key deliverables. Look for bullet points under 'Responsibilities' or 'What You'll Do' sections."
    },
    {
      "name": "Match Score",
      "description": "Numerical score (1-10) indicating how well this role matches Jenifer's background in radiology, AI/ML, public health, and leadership. Higher scores indicate better alignment with her expertise.",
      "format": "Number",
      "importance": "CRITICAL",
      "is_identification": false,
      "validation_strategy": "Compare job requirements against Jenifer's LinkedIn profile. Score based on: radiology/medical imaging requirements (0-3 points), AI/ML technical skills (0-3 points), public health or research focus (0-2 points), leadership opportunities (0-2 points). Sum for total score."
    },
    {
      "name": "Key Match Reasons",
      "description": "2-3 bullet points explaining the strongest alignment points between this role and Jenifer's background. Focus on specific skills, experiences, or qualifications that make her an excellent candidate.",
      "format": "String",
      "importance": "CRITICAL",
      "is_identification": false,
      "validation_strategy": "Extract top 2-3 requirements from job posting that match Jenifer's background. Reference specific experiences from her LinkedIn: radiology board certification, AI/ML publications, public health MPH, leadership roles. Format as concise bullet points."
    },
    {
      "name": "Location",
      "description": "Geographic location of the position (city, state/region). Note if remote, hybrid, or on-site. Include relocation considerations if relevant.",
      "format": "String",
      "importance": "CRITICAL",
      "is_identification": false,
      "validation_strategy": "Extract from job posting location field or description. Check if remote/hybrid options mentioned. Note any relocation assistance or geographic flexibility mentioned in the posting."
    },
    {
      "name": "Job Posting URL",
      "description": "Direct link to the job application page or posting. Must be an active, accessible URL that leads to the specific position.",
      "format": "URL",
      "importance": "CRITICAL",
      "is_identification": false,
      "validation_strategy": "Verify URL is active and leads to the correct job posting. Check that it's a direct link (not a search results page) and includes application instructions or an apply button."
    }
  ],
  "search_strategy": {
    "description": "Find medical imaging and AI/healthcare job opportunities matching Jenifer Siegelman's expertise in radiology, AI/ML, and public health",
    "requirements": [
      {
        "requirement": "Must be in healthcare, medical, or health-tech sector",
        "type": "hard",
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

### Hard vs Soft Requirements

**Hard Requirements (Core Must-Haves):**
- Absolute dealbreakers that entities MUST meet
- Any entity that violates a hard requirement will be rejected
- Use for NON-NEGOTIABLE criteria from the user's request
- **Key indicator:** If the user says "find X that ARE Y" or "find X doing Y", then Y is a hard requirement
- Examples:
  - "Must be a biotech company" (user specifically wants biotech)
  - "Must be published after 2020" (user specified timeframe)
  - "Must have active GenAI leadership job postings" (user wants companies actively hiring)
  - "Must be US-based" (user specified geography)

**Soft Requirements (Nice-to-Have Preferences):**
- Preferences that improve scoring and ranking
- Entities can still be included even if they don't meet soft requirements
- Help prioritize the best matches
- **Key indicators:** "preferably", "ideally", "bonus if", "better if"
- Examples:
  - "Prefers companies with more than 50 employees"
  - "Prefers recent news (last 6 months)"
  - "Prefers positions with remote work options"
  - "Prefers companies founded after 2020"

### Distinguishing Hard from Soft: The Critical Test

**Look for action verbs and core intent in the user's request:**

❌ **WRONG** - Misclassifying core requirements as preferences:
```
User request: "Find midsized biotech companies actively hiring for GenAI leadership roles"

Hard: Must be biotech, must be midsized, must have no existing GenAI program
Soft: Prefers companies with recent job postings

Problem: "Actively hiring" is CORE to the request but was classified as soft!
```

✅ **CORRECT** - Properly identifying all core requirements:
```
User request: "Find midsized biotech companies actively hiring for GenAI leadership roles"

Hard: Must be biotech, must be midsized, must have active GenAI leadership job postings
Soft: Prefers companies founded after 2020, prefers companies with <500 employees

Why? "Actively hiring" is fundamental to what we're looking for, not optional.
```

**More Examples:**

Example 1:
```
User: "Find AI companies that have raised Series B funding, preferably in healthcare"

Hard: Must be AI company, must have raised Series B funding
Soft: Prefers healthcare focus

Rationale: "Have raised" is a core requirement. "Preferably" signals a soft preference.
```

Example 2:
```
User: "Find research papers on transformer models, ideally with code available"

Hard: Must be about transformer models
Soft: Prefers papers with available code

Rationale: "On transformer models" is the core topic. "Ideally" signals nice-to-have.
```

Example 3:
```
User: "Find companies building AI safety tools"

Hard: Must be building AI safety tools
Soft: [Define based on other context, e.g., "Prefers well-funded companies"]

Rationale: "Building" indicates core activity, not a preference.
```

### Guidance on Hard vs Soft

**When in doubt, ask:** If removing this criterion would fundamentally change what we're looking for, it's a hard requirement. If it would just make results slightly less ideal, it's a soft requirement.

**Default to soft for ambiguous cases, but don't underspecify hard requirements:**
- ✅ Good use of hard requirement: "Must have active GenAI job postings" (user wants companies hiring)
- ❌ Bad use of soft requirement: "Prefers companies with job postings" (when user said "actively hiring")
- ✅ Good use of soft requirement: "Prefers companies with remote options" (enhances quality but not core)

**Why proper classification matters:**
- Hard requirements filter out non-matches completely
- Soft requirements help rank and prioritize matches
- Misclassifying core criteria as soft leads to irrelevant results
- Over-using hard requirements may produce zero results

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
