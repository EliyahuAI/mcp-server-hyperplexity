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

Return valid JSON matching the schema.
