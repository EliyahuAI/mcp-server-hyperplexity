# Background Research - Tablewide Context and Discovery Patterns

═══════════════════════════════════════════════════════════════
## 🔍 YOUR RESEARCH TASK
═══════════════════════════════════════════════════════════════

Research the domain to answer these questions:

{{CONTEXT_RESEARCH_ITEMS}}

**PRIMARY GOAL:** Understand how entities in this domain are identified, catalogued, and found

**YOUR DELIVERABLES:**
1. **Tablewide research** - Domain overview with key facts and patterns
2. **Discovery patterns** - Where/how entities are typically listed
3. **Authoritative sources** - Databases, directories, rankings that contain entities
4. **Starting tables** (with samples) - If you find existing lists, extract 5-15 sample entities
5. **Identified tables** (optional) - If you find extractable tables with clear structure, note them for Step 0b extraction

═══════════════════════════════════════════════════════════════
## 📋 USER CONTEXT
═══════════════════════════════════════════════════════════════

**User's Request:** {{USER_REQUIREMENTS}}

**Conversation History:**
{{CONVERSATION_CONTEXT}}

═══════════════════════════════════════════════════════════════
## 🎯 RESEARCH FOCUS AREAS
═══════════════════════════════════════════════════════════════

### 1. Tablewide Research (Required)

Provide 2-3 paragraph overview covering:
- How entities are typically identified/catalogued in this domain
- What authoritative sources exist (databases, directories, rankings)
- Discovery challenges and recommended approaches
- Domain-specific considerations

### 2. Discovery Patterns (Required)

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

### 4. Starting Tables (Required - Extract Samples)

If you find existing lists/tables with entities:
- Extract 5-15 ACTUAL sample entities with identifying details
- Example: "Dr. Jane Smith - Stanford - Neural Networks for Medical Imaging"
- NOT just "See Forbes list" - extract the actual names

**Complete Enumeration Detection:**
If user request indicates complete enumeration (e.g., "all references from paper X", "all countries in region Y"):
- Set `is_complete_enumeration: true`
- Extract ALL entities if possible (not just 5-15 samples)
- If document text was pasted in conversation, extract from there
- Set exact entity count (e.g., "54 references")

### 5. Identified Tables (Optional - For Step 0b Extraction)

If you find specific URLs with extractable table structure:
- Note the URL, table name, estimated rows, expected columns
- Set `extract_table: true` to trigger Step 0b (table extraction)
- Use when: clear table structure, specific URL, need complete extraction
- Skip when: just found a database/directory without specific table URL

**When to identify tables for extraction:**
- User explicitly requests data from specific URL/document
- You found a table with clear structure (e.g., election results table, Forbes ranked list)
- Complete enumeration needed and table accessible
- User pasted document text but you need web access to specific table

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
