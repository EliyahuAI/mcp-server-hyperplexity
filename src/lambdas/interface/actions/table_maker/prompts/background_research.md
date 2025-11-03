# Background Research - Find Sources and Extract Starting Tables

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **YOUR SEARCH TASK**: Specific entities to find and extract
2. **COMPLETE ENUMERATION CHECK**: Special handling for finite lists
3. **SEARCH METHODOLOGY**: How to find authoritative sources
4. **OUTPUT REQUIREMENTS**: Starting tables with sample entities
5. **FINAL REMINDER**: Core task and validation

═══════════════════════════════════════════════════════════════
## 🎯 YOUR SEARCH TASK
═══════════════════════════════════════════════════════════════

**USER WANTS:** {{USER_REQUIREMENTS}}

**YOUR JOB:** Find WHERE these specific entities exist as lists/databases on the web RIGHT NOW.

**SEARCH FOR:**
{{CONTEXT_RESEARCH_ITEMS}}

**DELIVERABLES:**
1. **starting_tables** - Lists with ACTUAL entity names (minimum 5-15 per table)
2. **authoritative_sources** - Databases/directories containing these entities
3. **tablewide_research** - 2-3 paragraph domain overview
4. **discovery_patterns** - How to find entities
5. **domain_specific_context** - Key facts and identifiers

---

═══════════════════════════════════════════════════════════════
## ⚠️ CRITICAL: COMPLETE ENUMERATION CHECK
═══════════════════════════════════════════════════════════════

**CHECK YOUR SEARCH TASK ABOVE:** Does it start with "COMPLETE ENUMERATION:"?

### IF YES → COMPLETE ENUMERATION MODE

**THIS IS MANDATORY:**
1. Extract **ALL entities** (not 5 samples - EVERY SINGLE ONE)
2. Set `is_complete_enumeration: true`
3. Set `entity_count_estimate` to EXACT number (e.g., "54 citations")
4. List ALL entities explicitly in `sample_entities` array
5. Do NOT summarize or truncate - list every item with full details

**Common cases:**
- Document items: Extract ALL references/chapters/sections from the document
- Geographic sets: List ALL countries/states/provinces
- Official rosters: List ALL members/appointees
- Finite collections: List ALL elements/planets/units

**Where to find entities:**
- If user pasted document text → Extract from CONVERSATION CONTEXT below
- If document URL provided → Access the document via web search
- If well-known set (countries, states) → Use knowledge or search for authoritative list

### IF NO → NORMAL SAMPLING MODE

Extract 5-15 sample entities from authoritative sources.
Set `is_complete_enumeration: false`

---

═══════════════════════════════════════════════════════════════
## 📚 USER CONTEXT
═══════════════════════════════════════════════════════════════

**Conversation:**
{{CONVERSATION_CONTEXT}}

---

═══════════════════════════════════════════════════════════════
## 🔍 SEARCH METHODOLOGY
═══════════════════════════════════════════════════════════════

### Step 1: Determine What to Search

**Read your search task above. What SPECIFIC entities?**
- Entity type? (companies, researchers, references, countries, etc.)
- Characteristics? (AI companies, NIH-funded, from specific paper, in specific region)
- Time period? (2025, 2024, historical)
- Geography? (US, global, specific region)

### Step 2: Search for Lists/Databases

**Use web search to find WHERE these entities are listed:**

**Search queries to try:**
- "[Entity type] list [year]" (e.g., "AI companies list 2025")
- "[Database name] [entity type]" (e.g., "NIH RePORTER dementia grants")
- "[Specific list] complete" (e.g., "Forbes AI 50 2025 complete list")
- "site:[domain] [entity type]" (e.g., "site:arxiv.org 2510.13928")

**For documents (PDFs, papers):**
- Search for the document URL or ID
- Access the full text
- Extract the complete list (references, chapters, etc.)

**What to look for:**
- Curated lists (Forbes, rankings, directories)
- Government databases (NIH, USPTO, official registries)
- Official directories (faculty lists, member rosters)
- Document content (references, sections, authors)

### Step 3: Extract Entity Names

**CRITICAL: Extract ACTUAL entity names, not just URLs**

**For each starting_table:**
- Access the source (via web search if needed)
- Extract real entity names with details
- For COMPLETE ENUMERATION: Extract ALL entities
- For normal mode: Extract 5-15 samples

**Good entity extraction:**
- "Dr. Jane Smith - Stanford - Neural Networks for Medical Imaging"
- "Anthropic - $7.3B funding - AI safety company"
- "[1] Vaswani et al. - Attention Is All You Need - arXiv:1706.03762"

**Bad entity extraction:**
- "See Forbes list" ❌
- "Various companies" ❌
- "[URLs provided]" ❌

---

═══════════════════════════════════════════════════════════════
## 📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════

```json
{
  "starting_tables": [
    {
      "source_name": "Name of list/database",
      "source_url": "https://...",
      "entity_type": "What entities are these",
      "entity_count_estimate": "50 entities" OR "~150 entities",
      "is_complete_enumeration": true OR false,
      "sample_entities": [
        "Entity 1 with full details",
        "Entity 2 with full details",
        "Entity 3 with full details"
        // ... 5-15 for normal, ALL for complete enumeration
      ],
      "completeness": "How complete this source is",
      "update_frequency": "static|weekly|monthly|annual",
      "discovery_notes": "How to use this source"
    }
  ],
  "authoritative_sources": [
    {
      "name": "Source name",
      "url": "https://...",
      "type": "database|list|directory|index",
      "description": "What it contains",
      "coverage": "How comprehensive",
      "access": "public|requires_auth|paid",
      "update_frequency": "real-time|daily|weekly|monthly|annual|static"
    }
  ],
  "tablewide_research": "2-3 paragraph overview of domain",
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
  }
}
```

---

═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER
═══════════════════════════════════════════════════════════════

**YOUR SEARCH TASK:** {{CONTEXT_RESEARCH_ITEMS}}

**CRITICAL REQUIREMENTS:**
1. ✅ If "COMPLETE ENUMERATION:" → Extract ALL entities from CONVERSATION CONTEXT, set is_complete_enumeration=true, exact count
2. ✅ Extract ACTUAL entity names (not just URLs)
3. ✅ For complete enumeration, user should have pasted document text in conversation - extract from there
4. ✅ Provide 5-15 samples for discovery mode, or ALL entities for complete enumeration
5. ✅ Return valid JSON matching format above

**Return your research as valid JSON.**
