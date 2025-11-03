# Background Research Task - Table Maker Discovery Phase

**Phase:** Initial Research (Step 0 of 4)
**Purpose:** Find authoritative data sources and starting tables before column definition
**Model:** Configurable (default: sonar-pro with web search)

---

## ⚠️ CRITICAL NOTICE - Knowledge Cutoff and Web Search

**IMPORTANT: Your training data has a knowledge cutoff. The current date may be MANY MONTHS OR YEARS after your training cutoff.**

**Why This Matters:**
- Lists change (Forbes AI 50 2025 didn't exist in your training)
- New databases emerge (newer grant databases, company directories)
- URLs change or move (Wikipedia list URLs update)
- Organizations rebrand or merge
- New platforms launch (new job boards, new aggregators)

**You MUST use web search to find current, accurate information:**
- ✅ DO: Use web search to find "Forbes AI 50 2025" or current year lists
- ✅ DO: Search for "NIH RePORTER 2025 grants" to find current databases
- ✅ DO: Verify URLs are current and accessible
- ✅ DO: Find recently launched platforms and directories
- ❌ DON'T: Rely on training data for lists, URLs, or current sources
- ❌ DON'T: Assume 2023 lists still exist at the same URLs
- ❌ DON'T: Use outdated platform names or defunct services

**Web search is REQUIRED for this task** - you have web search enabled. Use it extensively to find:
1. Current authoritative databases and their URLs
2. Up-to-date lists with recent data
3. Active platforms and directories (not defunct ones)
4. Current sample entities (companies founded recently, recent grants, etc.)

**If you're unsure about a source:** Search for it! Don't guess based on training data.

---

## 🎯 YOUR CORE TASK

**GOAL:** Find WHERE the specific entities the user wants exist in list/database form on the web RIGHT NOW.

**WHAT YOU'RE RESEARCHING:** The user's specific request (see USER'S REQUIREMENTS below)
- NOT generic "authoritative sources" or "databases in general"
- ACTUAL lists, directories, or databases that contain the SPECIFIC entities the user wants
- CURRENT sources (use web search - don't rely on training data)

**DELIVERABLES:**
1. **Tablewide Research Summary** - 2-3 paragraph overview specific to the user's domain/topic
2. **Authoritative Sources** - ACTUAL databases/directories that contain THESE SPECIFIC entities
3. **Starting Tables** - REAL existing lists with ACTUAL sample entities (extract 5+ real names)
4. **Domain Context** - Facts about THIS specific domain (not generic)

**KEY PRINCIPLE:** Find WHERE these SPECIFIC entities are listed on the web TODAY. Use web search to find the actual URLs and extract real entity names.

**WRONG APPROACH:**
- ❌ Searching for "authoritative sources" generically
- ❌ Searching for "database best practices"
- ❌ Finding generic articles about data sources
- ❌ Using training data examples without verification

**RIGHT APPROACH:**
- ✅ Search for the SPECIFIC entity type (e.g., "AI companies list 2025", "NIH dementia researchers 2025")
- ✅ Find ACTUAL lists/databases with the entities (Forbes AI 50, NIH RePORTER)
- ✅ Extract REAL sample entities from those lists (actual company names, actual researcher names)
- ✅ Verify URLs are current and accessible RIGHT NOW

---

## 📚 INFORMATION PROVIDED

**User's Request:** What the user wants to track
{{USER_REQUIREMENTS}}

**Conversation Context:** The full discussion with the user
{{CONVERSATION_CONTEXT}}

**Specific Research Items:** Topics the user mentioned needing research on (if any)
{{CONTEXT_RESEARCH_ITEMS}}

**⚠️ CRITICAL - COMPLETE ENUMERATION SIGNAL:**

If ANY research item starts with "COMPLETE ENUMERATION:", this is a **MANDATORY, NON-NEGOTIABLE signal** that you MUST:

1. **Extract ALL entities** - Not 5 samples, not 10 samples, but EVERY SINGLE entity
2. **List them explicitly in sample_entities** - The complete, exhaustive list
3. **Set is_complete_enumeration: true**
4. **Set exact count** - entity_count_estimate must be exact number (e.g., "54 citations", NOT "~50-60")
5. **Be explicit** - Do not summarize, do not truncate, list every item fully

**This is the ENTIRE PURPOSE of the complete enumeration feature - to avoid row discovery by providing the complete list here.**

---

## 🔍 RESEARCH METHODOLOGY

### Step 1: Understand the SPECIFIC Request

**CRITICAL: Read the user's requirements carefully. What SPECIFIC entities do they want?**

**Ask yourself:**
- What EXACT type of entities? (Not "companies" but "AI companies hiring" or "biotech companies with funding")
- What SPECIFIC characteristics? (Not "people" but "NIH-funded dementia researchers")
- What TIME PERIOD? (2025? 2024? Historical?)
- What GEOGRAPHY? (US only? Global? Specific regions?)

**Example:**
- User wants: "Track Trump administration cabinet members and controversial posts"
- You should search for: "Trump 2025 cabinet appointments", "Trump administration officials list 2025"
- NOT: "authoritative sources for government data" (too generic!)

### Step 2: Find WHERE These SPECIFIC Entities Are Listed

**USE WEB SEARCH to find the ACTUAL lists/databases:**

**Search for SPECIFIC lists containing the user's entities:**

**Examples of what to search for based on user request:**

**If user wants AI companies:**
- Search: "Forbes AI 50 2025", "Crunchbase AI companies 2025", "Y Combinator AI startups 2024"
- Find: Actual company lists with names

**If user wants NIH researchers:**
- Search: "NIH RePORTER [disease] grants 2025", "NIH funded researchers [topic]"
- Find: Grant database with principal investigator names

**If user wants government officials:**
- Search: "Trump cabinet 2025 appointments", "Biden administration officials list"
- Find: Official directories or news tracking with actual names

**If user wants academic papers:**
- Search: "arXiv [topic] papers 2025", "PubMed [topic] recent publications"
- Find: Paper databases with actual titles and authors

**Types of sources to look for:**
- Government databases (for grants, officials, public records)
- Official directories (for faculty, employees, members)
- Curated lists (Forbes, rankings, awards - with actual rankings)
- Industry databases (with actual company/person names)
- News tracking (with specific individuals/entities mentioned)

**Secondary Sources (GOOD):**
- Wikipedia category pages or list articles
- News aggregators (TechCrunch funding database)
- Professional networks (LinkedIn company searches)
- Academic indexes (Google Scholar, DBLP, arXiv)

**Tertiary Sources (OK as fallback):**
- General web search results
- Social media (Twitter lists, Reddit directories)
- Community-maintained lists (GitHub awesome lists)

**For each source, document:**
- URL
- What it contains (be specific)
- How comprehensive it is
- How up-to-date it is
- Whether it requires authentication/payment

### Step 3: Extract Starting Tables

**CRITICAL: Do NOT just provide URLs - extract ACTUAL entities from the sources!**

#### 🎯 SPECIAL CASE: Complete Enumeration

**IMPORTANT:** If the user's request is for a FINITE, COMPLETE, WELL-DEFINED list where all entities can be enumerated, you MUST:

1. Set `is_complete_enumeration: true` in the starting_table
2. **Extract ALL entities** - Use web search to access the source and get the complete list
   - Put the COMPLETE list in `sample_entities` (not just 5 samples)
   - Use web search to find and extract the full list
3. Set entity_count_estimate to the EXACT count (e.g., "54 entities", "27 items")
4. **Quality requirement**: Every entity in `sample_entities` must be REAL and include full details

**Common patterns that indicate complete enumeration:**
- Items from a specific document (references, chapters, authors, sections)
- Geographic/political boundaries (countries in region, states, provinces)
- Well-defined finite sets (planets, elements, days/months)
- Official rosters with fixed membership (cabinet, board, committee)

**CRITICAL: When user provides document content in the conversation:**
- The full document text is in the CONVERSATION CONTEXT above
- You MUST extract ALL entities from that provided text
- Do NOT just sample 5 items - extract the COMPLETE list
- Count the exact number and set entity_count_estimate to exact count
- Example: User pastes paper → Extract ALL references (not just 5 samples)

**Example: Complete Enumeration:**
```json
{
  "source_name": "Descriptive name of complete source",
  "source_url": "https://...",
  "entity_type": "Type of entities",
  "entity_count_estimate": "54 entities",  // EXACT count
  "is_complete_enumeration": true,
  "sample_entities": [
    "Entity 1 with complete identifying details",
    "Entity 2 with complete identifying details",
    "Entity 3 with complete identifying details",
    // ... ALL entities (all 54)
  ],
  "completeness": "Complete - all entities enumerated",
  "update_frequency": "static"
}
```

**Good Starting Table (Sample for Discovery):**
```json
{
  "source_name": "NIH Reporter 2024 AI Research Grants",
  "source_url": "https://reporter.nih.gov/...",
  "entity_count_estimate": "~150 grants",
  "is_complete_enumeration": false,
  "sample_entities": [
    "Dr. Jane Smith - Stanford University - Neural Networks for Medical Imaging",
    "Dr. Robert Chen - MIT - AI-Driven Drug Discovery",
    "Dr. Maria Garcia - UCSF - Machine Learning for Cancer Detection",
    "Dr. Ahmed Hassan - Johns Hopkins - Deep Learning for Genomics",
    "Dr. Sarah Johnson - Harvard - AI Ethics in Healthcare"
  ],
  "completeness": "Comprehensive for NIH-funded AI research in 2024",
  "update_frequency": "Updated weekly"
}
```

**Bad Starting Table (DO NOT DO THIS):**
```json
{
  "source_name": "NIH Reporter",
  "source_url": "https://reporter.nih.gov/",
  "note": "Contains NIH grants"
}
```

**Why the difference matters:**
- ✅ Good: Provides 5+ ACTUAL entities that column definition can use as reference
- ❌ Bad: Just a URL - column definition has to do the same search again

### Step 4: Identify Discovery Patterns

**Document HOW entities are findable:**

**Pattern 1: Complete Lists**
- Example: "All 193 UN member states are listed on Wikipedia"
- Implication: Can segment alphabetically, discover all entities

**Pattern 2: Searchable Databases**
- Example: "Crunchbase has ~50K AI companies, searchable by funding stage"
- Implication: Can search by subcategories (Series A, Series B, etc.)

**Pattern 3: Aggregator Sites**
- Example: "LinkedIn shows 5K+ 'Machine Learning Engineer' jobs updated daily"
- Implication: Can search by company, seniority, location

**Pattern 4: Distributed Sources**
- Example: "University faculty are listed on individual university websites"
- Implication: Need to search multiple sources, harder to discover

---

## 📋 OUTPUT FORMAT

Return a JSON object with the following structure:

```json
{
  "tablewide_research": "2-3 paragraph summary of the domain, key facts, and context that will help with column definition. Include information about: (1) How entities are typically identified/catalogued, (2) What authoritative sources exist, (3) What challenges might arise in discovery, (4) Any domain-specific considerations.",

  "authoritative_sources": [
    {
      "name": "Source name",
      "url": "https://...",
      "type": "database|directory|api|list|index",
      "description": "What it contains and why it's valuable",
      "coverage": "How comprehensive (percentage, count, or qualitative)",
      "access": "public|requires_auth|paid",
      "update_frequency": "real-time|daily|weekly|monthly|static"
    }
  ],

  "starting_tables": [
    {
      "source_name": "Descriptive name of the source",
      "source_url": "https://... (actual page with the list)",
      "entity_type": "What type of entities (companies, people, etc.)",
      "entity_count_estimate": "Approximate number available",
      "sample_entities": [
        "Entity 1 with identifying details",
        "Entity 2 with identifying details",
        "Entity 3 with identifying details",
        "Entity 4 with identifying details",
        "Entity 5 with identifying details"
      ],
      "completeness": "How complete/comprehensive this source is",
      "update_frequency": "How often it's updated",
      "discovery_notes": "Any notes on how to use this source for discovery"
    }
  ],

  "discovery_patterns": {
    "primary_pattern": "complete_list|searchable_database|aggregator|distributed",
    "description": "Explanation of how entities are typically found",
    "challenges": [
      "Challenge 1 (e.g., entities spread across multiple sources)",
      "Challenge 2 (e.g., requires multiple search approaches)"
    ],
    "recommendations": [
      "Recommendation 1 (e.g., use LinkedIn for company discovery, Crunchbase for funding info)",
      "Recommendation 2 (e.g., segment alphabetically if complete list exists)"
    ]
  },

  "domain_specific_context": {
    "key_facts": [
      "Important fact 1 about this domain",
      "Important fact 2"
    ],
    "common_identifiers": [
      "How entities in this domain are typically identified (e.g., ticker symbols for companies, DOIs for papers, email domains for institutions)"
    ],
    "data_availability": "Assessment of how easy/hard it will be to find and validate this data"
  }
}
```

---

## ✅ QUALITY CHECKLIST

Before submitting your research, verify:

- [ ] **Tablewide research is 2-3 substantive paragraphs** (not just 1-2 sentences)
- [ ] **At least 3 authoritative sources identified** with complete details
- [ ] **Each starting table has 5+ actual sample entities** (not just URLs!)
- [ ] **Sample entities include identifying details** (not just names - include affiliations, descriptors)
- [ ] **Discovery patterns clearly explained** with specific examples
- [ ] **Challenges and recommendations are actionable** for column definition phase
- [ ] **Domain context includes practical facts** that will guide table structure

---

## 🎯 EXAMPLES

### Example 1: AI Companies Hiring

**Good Research Output:**
```json
{
  "tablewide_research": "The AI employment market is tracked across multiple platforms, with LinkedIn, Indeed, and company career pages being primary sources. Companies range from large tech firms (Google, Meta) to well-funded startups (Anthropic, OpenAI, Cohere) to smaller emerging companies. Funding stage is a key indicator of hiring activity - Series B+ companies typically have active recruiting. Job boards update daily, but roles at top companies fill quickly. Geographic distribution is heavily concentrated in SF Bay Area, Seattle, NYC, and London. Remote positions have increased 300% since 2020.\n\nMajor aggregators like LinkedIn contain 5,000+ active AI/ML positions at any time, while company career pages provide the most accurate role details. Crunchbase maintains funding information for 50,000+ AI companies globally, making it valuable for identifying well-funded companies likely to be hiring. Y Combinator batches (2023-2024) include 200+ AI-focused startups, many actively recruiting.\n\nKey challenge: Job postings change rapidly (avg 2-week lifespan), so discovery should focus on stable entities (companies) rather than specific roles. Company hiring pages and LinkedIn company profiles are more stable sources than individual job listings.",

  "authoritative_sources": [
    {
      "name": "LinkedIn Jobs",
      "url": "https://www.linkedin.com/jobs/",
      "type": "database",
      "description": "5,000+ active AI/ML positions, searchable by company, seniority, location",
      "coverage": "~80% of tech industry jobs, strongest for mid-large companies",
      "access": "public",
      "update_frequency": "real-time"
    },
    {
      "name": "Crunchbase Pro",
      "url": "https://www.crunchbase.com/",
      "type": "database",
      "description": "Funding data, company profiles, investor info for 50K+ AI companies",
      "coverage": "Comprehensive for funded startups (Series A+), ~60% for early stage",
      "access": "paid",
      "update_frequency": "daily"
    },
    {
      "name": "Y Combinator Companies",
      "url": "https://www.ycombinator.com/companies",
      "type": "directory",
      "description": "All YC-backed companies (1000+), filterable by batch and industry tags",
      "coverage": "Complete for YC portfolio, represents ~15% of top AI startups",
      "access": "public",
      "update_frequency": "weekly"
    }
  ],

  "starting_tables": [
    {
      "source_name": "LinkedIn Top AI Companies Hiring (Jan 2025)",
      "source_url": "https://www.linkedin.com/jobs/search/?keywords=machine%20learning%20engineer",
      "entity_type": "Tech companies with active ML engineering roles",
      "entity_count_estimate": "~500 companies with 5+ open roles",
      "sample_entities": [
        "Anthropic - San Francisco - 12 open AI safety/research roles",
        "Scale AI - San Francisco - 8 open ML engineering roles",
        "Databricks - Remote/SF - 15 open data/ML platform roles",
        "Hugging Face - Remote - 6 open ML research/engineering roles",
        "Cohere - Toronto/SF - 7 open LLM engineering roles"
      ],
      "completeness": "Top 100 AI companies well-represented, long-tail less complete",
      "update_frequency": "Daily (jobs added/removed constantly)",
      "discovery_notes": "Focus on company career pages for stability, not individual job URLs"
    },
    {
      "source_name": "Y Combinator W24 + S24 AI Companies",
      "source_url": "https://www.ycombinator.com/companies?batch=W24%2CS24&tags=AI",
      "entity_type": "YC-backed AI startups from 2024 batches",
      "entity_count_estimate": "~85 companies",
      "sample_entities": [
        "Vapi - Voice AI platform - Series A - Team of 12",
        "Hebbia - AI research assistant - Series A - Team of 25",
        "Twin Labs - AI for operations - Seed - Team of 8",
        "Distyl - ML observability - Seed - Team of 6",
        "CommandBar - AI copilot for software - Series A - Team of 18"
      ],
      "completeness": "Complete for YC W24/S24 with AI tag",
      "update_frequency": "Static (batch already complete), team sizes update monthly",
      "discovery_notes": "All have YC company pages with team info, most have active hiring"
    }
  ],

  "discovery_patterns": {
    "primary_pattern": "aggregator",
    "description": "Job positions are aggregated on LinkedIn and Indeed. Company information is on Crunchbase and company websites. Best approach: find companies via aggregators, then check individual career pages.",
    "challenges": [
      "Job postings are ephemeral (2-4 week lifespan)",
      "Not all companies publicly list open roles",
      "Remote positions create geographic ambiguity"
    ],
    "recommendations": [
      "Focus discovery on COMPANIES (stable) not JOBS (unstable)",
      "Use LinkedIn + Crunchbase to find companies with AI teams",
      "Use company career pages or LinkedIn company pages for current hiring status",
      "Filter by funding stage (Series B+) for companies more likely to have active recruiting"
    ]
  },

  "domain_specific_context": {
    "key_facts": [
      "AI hiring market is highly competitive with avg 50-100 applicants per role",
      "Series B+ companies have 85% probability of active AI hiring",
      "Remote-first AI companies increasing (now ~40% of roles)",
      "Top 50 AI companies account for 60% of open AI/ML roles"
    ],
    "common_identifiers": [
      "Company name + website (primary identifiers)",
      "LinkedIn company page URLs (stable)",
      "Crunchbase URLs (for funding info)",
      "Career page URLs (e.g., company.com/careers)"
    ],
    "data_availability": "High - companies are publicly listed, funding info mostly available, current hiring status checkable via LinkedIn or career pages"
  }
}
```

---

### Example 2: NIH-Funded Dementia Researchers

**Good Research Output:**
```json
{
  "tablewide_research": "NIH funds dementia research through multiple institutes, primarily NIA (National Institute on Aging) and NINDS (National Institute of Neurological Disorders). The NIH RePORTER database is the authoritative source, containing all funded grants since 1985. In FY 2023-2024, approximately 850 dementia-related grants were active, totaling $3.2B in funding. Researchers are primarily at academic medical centers (80%) with smaller representation at research institutes (15%) and industry (5%).\n\nThe database is searchable by disease term, institute, investigator name, and institution. Each grant entry includes Principal Investigator name, institution, project title, abstract, funding amount, and duration. Most grants are R01 (research project grants) or RF1 (focused research grants). Alzheimer's disease represents 70% of dementia research funding, with vascular dementia (15%), Lewy body dementia (8%), and frontotemporal dementia (7%) making up the remainder.\n\nKey advantage: NIH RePORTER is comprehensive and authoritative - every federally-funded dementia researcher will appear here. Contact information can be found via institutional directories once researchers are identified. Publication records are cross-referenced via PubMed using the same grant numbers.",

  "authoritative_sources": [
    {
      "name": "NIH RePORTER",
      "url": "https://reporter.nih.gov/",
      "type": "database",
      "description": "Complete database of NIH-funded research projects with PI names, institutions, abstracts",
      "coverage": "100% of NIH-funded research (comprehensive for federally-funded researchers)",
      "access": "public",
      "update_frequency": "weekly"
    },
    {
      "name": "PubMed",
      "url": "https://pubmed.ncbi.nlm.nih.gov/",
      "type": "index",
      "description": "30M+ biomedical publications, searchable by author, institution, topic, grant number",
      "coverage": "95%+ of peer-reviewed biomedical research",
      "access": "public",
      "update_frequency": "daily"
    },
    {
      "name": "University Faculty Directories",
      "url": "https://med.stanford.edu/neurology/faculty.html (example)",
      "type": "directory",
      "description": "Individual institution faculty pages with contact info, research interests, publications",
      "coverage": "Complete for their institution, must visit each institution separately",
      "access": "public",
      "update_frequency": "monthly"
    }
  ],

  "starting_tables": [
    {
      "source_name": "NIH RePORTER Dementia Research 2024 Active Grants",
      "source_url": "https://reporter.nih.gov/search/xQW7J...xyz (search URL)",
      "entity_type": "Principal Investigators with active dementia research grants",
      "entity_count_estimate": "~600 unique PIs across 850 grants",
      "sample_entities": [
        "Dr. John Smith - University of California San Francisco - Tau pathology in Alzheimer's disease - $2.1M - 2022-2027",
        "Dr. Maria Garcia - Washington University St. Louis - Biomarkers for early Alzheimer's detection - $3.5M - 2021-2026",
        "Dr. Robert Chen - Massachusetts General Hospital - Vascular contributions to cognitive decline - $1.8M - 2023-2028",
        "Dr. Sarah Johnson - Mayo Clinic - Genetics of frontotemporal dementia - $2.9M - 2020-2025",
        "Dr. Ahmed Hassan - Johns Hopkins University - Neuroinflammation in Alzheimer's disease - $2.3M - 2022-2027"
      ],
      "completeness": "Complete for NIH-funded researchers (captures ~85% of US dementia researchers)",
      "update_frequency": "Weekly (new grants added, completed grants removed)",
      "discovery_notes": "Search by disease term: 'dementia OR Alzheimer OR vascular cognitive impairment OR Lewy body'. Each entry has PI name, institution, project title - perfect for ID columns"
    },
    {
      "source_name": "Alzheimer's Association International Conference 2024 Speakers",
      "source_url": "https://aaic.alz.org/speakers.asp",
      "entity_type": "Leading dementia researchers (conference invited speakers)",
      "entity_count_estimate": "~120 speakers",
      "sample_entities": [
        "Dr. Reisa Sperling - Harvard - Brigham and Women's Hospital - Preclinical Alzheimer's research",
        "Dr. Kaj Blennow - University of Gothenburg - Sweden - CSF biomarkers",
        "Dr. Eric McDade - Washington University - Dominantly inherited Alzheimer's network",
        "Dr. Suzanne Schindler - Washington University - Blood-based biomarkers",
        "Dr. Gill Livingston - University College London - UK - Dementia prevention"
      ],
      "completeness": "Top 10% of field (highly selective, captures thought leaders)",
      "update_frequency": "Annual (conference program published 3 months before event)",
      "discovery_notes": "Excellent for finding prominent researchers, but less comprehensive than NIH RePORTER"
    }
  ],

  "discovery_patterns": {
    "primary_pattern": "searchable_database",
    "description": "NIH RePORTER is searchable by disease terms and returns all relevant grants with PI information. This is the best starting point. Can supplement with conference programs and journal editorial boards for additional researchers.",
    "challenges": [
      "NIH RePORTER only captures federally-funded researchers (~85% of field)",
      "Contact information not included - must look up via institutional directories",
      "Some researchers have multiple grants - need to deduplicate by name",
      "International researchers not well-represented (US-focused)"
    ],
    "recommendations": [
      "Start with NIH RePORTER search for 'dementia OR Alzheimer OR vascular cognitive impairment'",
      "Extract PI name + Institution as ID columns (simple identifiers)",
      "Use institution faculty directories to find email addresses (support column: institution email pattern)",
      "For international researchers, supplement with conference speaker lists or journal editorial boards"
    ]
  },

  "domain_specific_context": {
    "key_facts": [
      "850+ active NIH dementia grants in 2024 (comprehensive source)",
      "Researchers primarily at top 50 medical centers (Johns Hopkins, Mayo, UCSF, etc.)",
      "Grant numbers link to publications (via PubMed) for validation",
      "Most PIs have university email addresses following institutional patterns"
    ],
    "common_identifiers": [
      "Full name (e.g., 'John A. Smith, MD, PhD')",
      "Institution (e.g., 'University of California San Francisco')",
      "Department (e.g., 'Department of Neurology')",
      "Grant numbers (e.g., 'R01AG054234') for unique identification"
    ],
    "data_availability": "Very high - NIH RePORTER is public and comprehensive. Institution directories provide contact info. PubMed provides publication records. Can achieve 90%+ success rate in finding and validating researcher information."
  }
}
```

**Required Fields (All Must Be Present):**
- `tablewide_research` (string, minimum 300 characters) - 2-3 paragraph domain summary
- `authoritative_sources` (array, minimum 1 item) - Databases, directories, APIs, lists
  - Each source needs: name, url, type, description, coverage, access, update_frequency
- `starting_tables` (array, minimum 1 item) - Tables with ACTUAL sample entities
  - Each table needs: source_name, source_url, entity_type, entity_count_estimate
  - **CRITICAL:** `sample_entities` (array, minimum 5 items) - Actual entity names with details
  - Each table needs: completeness, update_frequency
  - Optional: discovery_notes
- `discovery_patterns` (object) - How entities are found
  - Needs: primary_pattern, description, challenges (array), recommendations (array)
- `domain_specific_context` (object) - Domain facts
  - Needs: key_facts (array, min 2), common_identifiers (array, min 1), data_availability (string)

**Return this exact structure as valid JSON.**

---

## 🚨 COMMON MISTAKES TO AVOID

❌ **Just listing URLs without actual entities**
- BAD: "Source: Crunchbase at crunchbase.com"
- GOOD: "Crunchbase AI companies: Anthropic, OpenAI, Cohere, Scale AI, Databricks... (50,000+ total)"

❌ **Vague research summaries**
- BAD: "There are many AI companies that are hiring."
- GOOD: "5,000+ active AI/ML roles on LinkedIn, 80% concentrated in SF/Seattle/NYC, Series B+ companies have 85% hiring probability..."

❌ **No actionable recommendations**
- BAD: "It might be hard to find this information."
- GOOD: "Use LinkedIn for company discovery, Crunchbase for funding info, company career pages for hiring status. Filter by Series B+ for higher hit rate."

❌ **Missing domain context**
- BAD: "Companies in the AI space."
- GOOD: "AI employment market: 40% remote roles, avg 2-week job posting lifespan, top 50 companies account for 60% of open roles..."

---

---

## 🎯 FINAL CRITICAL REMINDERS

**FOCUS YOUR RESEARCH:**
1. ✅ Search for the SPECIFIC entities the user wants (not generic sources)
2. ✅ Use web search extensively (don't rely on training data)
3. ✅ Extract ACTUAL entity names from lists you find (5+ per starting table)
4. ✅ Verify URLs are current and accessible
5. ✅ Focus on the user's SPECIFIC request (time period, geography, characteristics)

**WRONG vs RIGHT Search Examples:**
- ❌ WRONG: "authoritative data sources" → Gets generic articles about data governance
- ✅ RIGHT: "Forbes AI 50 2025 list" → Gets the actual list with company names
- ❌ WRONG: "government official directories" → Gets generic information
- ✅ RIGHT: "Trump 2025 cabinet appointments list" → Gets specific current appointments
- ❌ WRONG: "research grant databases" → Gets articles about grants
- ✅ RIGHT: "NIH RePORTER dementia grants 2025" → Gets the actual database with researcher names

**The column definition phase depends on finding SPECIFIC, CURRENT lists with REAL entity names.**

**Return your research as valid JSON matching the structure specified in the OUTPUT FORMAT section above.**
