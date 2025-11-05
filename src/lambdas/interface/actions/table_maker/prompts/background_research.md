# Background Research - Tablewide Context and Discovery Patterns

═══════════════════════════════════════════════════════════════
## 🔍 YOUR RESEARCH TASK
═══════════════════════════════════════════════════════════════

**SEARCH FOR:**

{{CONTEXT_RESEARCH_ITEMS}}

**For:** {{USER_REQUIREMENTS}}

**Your research will inform column design and row discovery strategy.**

═══════════════════════════════════════════════════════════════
## 📋 YOUR DELIVERABLES
═══════════════════════════════════════════════════════════════

1. **Tablewide research** - Domain overview (2-3 paragraphs) for the topics you searched for.
2. **Discovery patterns** - How entities are typically found
3. **Authoritative sources** - Databases/directories containing entities
4. **Starting tables** - Extract 5-15 sample entities from lists you find
5. **Identified tables** (optional) - Larger tables that should be fully extracted by an additional step (more than 15 entities)

═══════════════════════════════════════════════════════════════
## 📚 USER CONTEXT
═══════════════════════════════════════════════════════════════

**Conversation History:**
{{CONVERSATION_CONTEXT}}

═══════════════════════════════════════════════════════════════
## 🎯 DETAILED GUIDANCE
═══════════════════════════════════════════════════════════════

### 1. Tablewide Research (Required)
Synthesise your research into each of these search items:
{{CONTEXT_RESEARCH_ITEMS}}

- Be concise but comprehensive.

### 2. Discovery Patterns (Required)

Provide 2-3 paragraph overview covering:
- How entities are typically identified/catalogued in this domain
- What authoritative sources exist (databases, directories, rankings)
- Discovery challenges and recommended approaches
- Domain-specific considerations

Identify the primary pattern:
- **complete_list**: Finite, well-defined sets (countries, states, specific paper references)
- **searchable_database**: Queryable databases (NIH RePORTER, USPTO, PubMed)
- **aggregator**: Curated lists/rankings (Forbes, TechCrunch lists)
- **distributed**: No central source, requires broad web search

Provide challenges and recommendations for successful discovery.

### 3. Authoritative Sources (Required)

List databases/directories/APIs where entities can be found:
- Name, URL, type (database/directory/list/api)
- What it contains, coverage, access level
- Update frequency

### 4. Starting Tables (Required)

**SIZE-BASED DECISION:** How many entities does the table have?

**Small Tables (≤15 rows):**
- Extract ALL entities inline (not just 5-15 samples)
- Put complete list in `sample_entities`
- Set `is_complete_enumeration: true`
- Set exact count: "12 entities" (not "~10-15")
- Example: User wants "all 12 Zodiac signs" → Extract all 12

**Large Tables (>15 rows):**
- Extract 5-15 samples only
- Note the table in `identified_tables` instead (see Section 5)
- Set `is_complete_enumeration: false`
- Example: Forbes AI 50 has 50 companies → Extract 5-15 samples, add to identified_tables

**Format:**
- Extract ACTUAL entity names with details
- Example: "Dr. Jane Smith - Stanford - Neural Networks for Medical Imaging"
- NOT just "See Forbes list" - extract actual names

### 5. Identified Tables (Optional - Trigger Step 0b Extraction)

**SIZE-BASED DECISION:** Use identified_tables for large datasets (>15 entities) or multiple sources

**NOTE: "Table" means any page/article/document with entity information (not just HTML tables)**

**When to set extract_table=true:**

✅ **Trigger if source has >15 entities:**
- Article/page with 20+ candidates/companies/people → Too large for inline extraction
- Examples:
  - Election results article with 20 candidates
  - Forbes AI 50 list article (50 companies)
  - Faculty directory page (30+ professors)
  - News article covering 25+ entities
- Extract 5-15 samples for starting_tables, add URL to identified_tables

✅ **Trigger if multiple sources:**
- Found 3 different articles/pages to extract from → Use identified_tables for all
- Each source gets its own entry with extract_table=true

✅ **Trigger if user explicitly requested specific URL:**
- User said "extract from this document" with URL
- Even if small, use identified_tables to ensure complete extraction

❌ **Don't trigger if:**
- Source has ≤15 entities → Extract ALL inline in starting_tables
- Just a database/directory without specific page URL
- Searchable/queryable source (not static content)

**What to provide:**
- `url`: URL of the page/article/document (doesn't need to be HTML table)
- `table_name`: Descriptive name
- `estimated_rows`: How many entities at this URL
- `columns`: Expected data fields (from your research, not literal table columns)
- `extract_table: true`
- `target_rows`: Optional filter (e.g., "only winners", "School Committee only")
- `extraction_priority`: "high" if user requested, "medium" otherwise

═══════════════════════════════════════════════════════════════
## 💡 RESEARCH METHODOLOGY
═══════════════════════════════════════════════════════════════

### Step 1: Understand the Domain

Read the research questions above. What domain is this?
- Entity type (companies, researchers, references, locations, etc.)
- Characteristics (AI companies, NIH-funded, from specific paper, etc.)
- Geography, time period, constraints

### Step 2: Find Where Entities Are Listed

Search for:
- "[Entity type] list [year]"
- "[Database name] [entity type]"
- "site:[domain] [entity type]"
- Specific document URLs if user provided them

Look for:
- Government databases (NIH, USPTO, official registries)
- Curated lists (Forbes, rankings, directories)
- Official directories (faculty lists, member rosters)
- Academic sources (paper references, citations)

### Step 3: Extract Sample Entities

**CRITICAL:** For starting_tables, extract REAL entity names with details

✅ **Good extraction:**
- "Dr. Jane Smith - Stanford - Neural Networks"
- "Anthropic - $7.3B funding - AI safety"
- "[1] Vaswani et al. - Attention Is All You Need - arXiv:1706.03762"

❌ **Bad extraction:**
- "See Forbes list" (no actual entities)
- "Various companies" (vague)
- Just URLs (need names)

### Step 4: Identify Tables for Step 0b (Optional)

If you found a specific table URL that needs complete extraction:
- User specifically requested this URL
- Clear table structure visible
- Need more than 5-15 samples (need complete extraction)
- Example: Election results table, ranked company list with details

Add to `identified_tables` with extract_table=true

═══════════════════════════════════════════════════════════════
## 📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════

Return JSON matching this structure:

```json
{
  "tablewide_research": "2-3 paragraph overview of domain, identification patterns, sources, challenges, recommendations",

  "authoritative_sources": [
    {
      "name": "Source name",
      "url": "https://...",
      "type": "database|directory|list|api|index|aggregator",
      "description": "What it contains",
      "coverage": "How comprehensive",
      "access": "public|requires_auth|paid",
      "update_frequency": "real-time|daily|weekly|monthly|annual|static"
    }
  ],

  "starting_tables": [
    {
      "source_name": "Name of list/table",
      "source_url": "https://...",
      "entity_type": "What entities are these",
      "entity_count_estimate": "50 entities" or "~150 entities",
      "is_complete_enumeration": false,
      "sample_entities": [
        "Entity 1 with full details",
        "Entity 2 with full details",
        "Entity 3 with full details",
        "... (5-15 for normal, ALL for complete enumeration)"
      ],
      "completeness": "How complete this source is",
      "update_frequency": "static|weekly|monthly|annual",
      "discovery_notes": "How to use this source"
    }
  ],

  "discovery_patterns": {
    "primary_pattern": "complete_list|searchable_database|aggregator|distributed",
    "description": "How entities are found",
    "challenges": ["Challenge 1", "Challenge 2"],
    "recommendations": ["Rec 1", "Rec 2"]
  },

  "domain_specific_context": {
    "key_facts": ["Fact 1", "Fact 2"],
    "common_identifiers": ["ID type 1", "ID type 2"],
    "data_availability": "Assessment of findability"
  },

  "identified_tables": [
    {
      "url": "https://specific-table-url.com",
      "table_name": "Descriptive name",
      "estimated_rows": 50,
      "columns": ["Column 1", "Column 2", "Column 3"],
      "extract_table": true,
      "target_rows": "only winners" or "School Committee only",
      "extraction_priority": "high|medium|low",
      "notes": "Optional notes about structure/pagination"
    }
  ]
}
```

### Field Requirements:

**Required:**
- `tablewide_research` - 2-3 paragraphs
- `authoritative_sources` - At least 1 source
- `starting_tables` - At least 1 table with 5+ sample entities
- `discovery_patterns` - Primary pattern with recommendations
- `domain_specific_context` - Key facts and identifiers

**Optional:**
- `identified_tables` - Only if you found specific extractable table URLs

**Complete Enumeration:**
- Set `is_complete_enumeration: true` in starting_tables
- Provide ALL entities in sample_entities (not just 5-15)
- Set exact count in entity_count_estimate

**Identified Tables:**
- Only include if: specific URL, clear table structure, extraction needed
- Don't include if: just a database/directory without specific table URL
- Set `extract_table: true` to trigger Step 0b

═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER
═══════════════════════════════════════════════════════════════

**YOUR RESEARCH QUESTIONS:** {{CONTEXT_RESEARCH_ITEMS}}

**CRITICAL REQUIREMENTS:**
1. ✅ Focus on RESEARCH and PATTERNS (primary goal)
2. ✅ Extract ACTUAL entity names in starting_tables (not just URLs)
3. ✅ For complete enumeration: Extract ALL entities if user pasted document text
4. ✅ For identified_tables: Only include specific URLs with extractable tables
5. ✅ Provide at least 5-15 sample entities per starting_table
6. ✅ Return valid JSON matching format above

**What happens next:**
- Your research → Used by column definition (Step 1)
- Your starting_tables → Converted to sample_rows
- Your identified_tables → Passed to table extraction (Step 0b)

**Return your research as valid JSON.**
