# Background Research - Tablewide Context and Entity Discovery

## YOUR RESEARCH TASK

**SEARCH FOR:**

{{CONTEXT_RESEARCH_ITEMS}}

**For:** {{USER_REQUIREMENTS}}

**Your research will inform column design and row discovery strategy.**

## YOUR DELIVERABLES

1. **Tablewide research** - Domain overview (2-3 paragraphs) covering: how entities are identified, what authoritative sources exist, discovery challenges and recommendations, domain-specific key facts
2. **Authoritative sources** - Databases/directories/APIs containing entities (name, URL, description only)
3. **Starting tables markdown** - Markdown table with entities you found, using citations
4. **Citations** - Map of citation numbers to source URLs
5. **Identified tables** (optional) - Larger tables (>15 entities) that need full extraction

## USER CONTEXT

**Conversation History:**
{{CONVERSATION_CONTEXT}}

## DETAILED GUIDANCE

### 1. Tablewide Research (Required)

Synthesize your research into 2-3 paragraphs covering:

{{CONTEXT_RESEARCH_ITEMS}}

Include in your summary:
- How entities are typically identified/catalogued in this domain
- What authoritative sources exist (databases, directories, rankings)
- Primary discovery pattern: complete_list / searchable_database / aggregator / distributed
- Discovery challenges and recommended approaches
- Domain-specific key facts and common identifiers
- Assessment of data availability

### 2. Authoritative Sources (Required)

List databases/directories/APIs where entities can be found. Keep simple:
- Name
- URL
- Description (what it contains and why it's valuable)

### 3. Starting Tables Markdown (Required)

Create a **markdown table** with entities you discovered. Use numbered citations [1] [2] to indicate sources.

**SIZE-BASED DECISION:**

**Small Tables (<=15 rows):**
- Include ALL entities in the markdown table
- Set `is_complete_enumeration: true`
- Example: "All 12 Zodiac signs" -> Include all 12 rows

**Large Tables (>15 rows):**
- Include 5-15 sample rows
- Add the full table to `identified_tables` for extraction
- Set `is_complete_enumeration: false`

**Format:**
```markdown
| Source | Entity | Details |
|--------|--------|---------|
| Forbes AI 50[1] | Anthropic | AI safety, $7.3B funding |
| Forbes AI 50[1] | OpenAI | GPT models, $13B funding |
| NIH RePORTER[2] | Dr. Jane Smith | Stanford, Neural Networks |
```

Each cell should have a citation number in brackets [1] linking to the citations object.

### 4. Citations (Required)

Map citation numbers to source URLs:
```json
{
  "1": "https://forbes.com/ai-50-2024",
  "2": "https://reporter.nih.gov"
}
```

### 5. Identified Tables (Optional - Trigger Step 0b Extraction)

**Use for large datasets (>15 entities) or multiple sources that need complete extraction.**

**When to set extract_table=true:**

- Source has >15 entities that should be fully extracted
- User explicitly requested a specific URL
- Multiple sources to extract from

**What to provide:**
- `url`: URL of the page/article/document
- `table_name`: Descriptive name
- `description`: Short description of what this table contains and why it should be extracted
- `estimated_rows`: How many entities at this URL
- `columns`: Expected data fields
- `extract_table: true`
- `target_rows`: Optional filter (e.g., "only winners")
- `extraction_priority`: "high" if user requested, "medium" otherwise

## RESEARCH METHODOLOGY

### Step 1: Understand the Domain

Read the research questions above:
- Entity type (companies, researchers, references, locations, etc.)
- Characteristics (AI companies, NIH-funded, from specific paper, etc.)
- Geography, time period, constraints

### Step 2: Find Where Entities Are Listed

Search for:
- "[Entity type] list [year]"
- "[Database name] [entity type]"
- Specific document URLs if user provided them

Look for:
- Government databases (NIH, USPTO, official registries)
- Curated lists (Forbes, rankings, directories)
- Official directories (faculty lists, member rosters)
- Academic sources (paper references, citations)

### Step 3: Extract Entities into Markdown Table

**CRITICAL:** Extract REAL entity names with details into the markdown table with citations.

**Good:**
| Source | Entity | Details |
|--------|--------|---------|
| Forbes[1] | Anthropic | AI safety startup, $7.3B funding |
| Paper[2] | Vaswani et al. | Attention Is All You Need, arXiv:1706.03762 |

**Bad:**
- "See Forbes list" (no actual entities)
- "Various companies" (vague)
- Just URLs without entity names

## OUTPUT FORMAT

Return JSON matching this structure:

```json
{
  "tablewide_research": "2-3 paragraph overview covering: how entities are identified, authoritative sources, discovery pattern (complete_list/searchable_database/aggregator/distributed), challenges, recommendations, key facts, common identifiers, data availability assessment.",

  "authoritative_sources": [
    {
      "name": "Source name",
      "url": "https://...",
      "description": "What it contains and why it's valuable"
    }
  ],

  "starting_tables_markdown": "| Source | Entity | Details |\n|--------|--------|--------|\n| Forbes AI 50[1] | Anthropic | AI safety, $7.3B funding |\n| Forbes AI 50[1] | OpenAI | GPT models |\n| NIH RePORTER[2] | Dr. Jane Smith | Stanford, Neural Networks |",

  "citations": {
    "1": "https://forbes.com/ai-50-2024",
    "2": "https://reporter.nih.gov"
  },

  "is_complete_enumeration": false,

  "identified_tables": [
    {
      "url": "https://specific-table-url.com",
      "table_name": "Descriptive name",
      "description": "Short description of what this table contains",
      "estimated_rows": 50,
      "columns": ["Column 1", "Column 2"],
      "extract_table": true,
      "target_rows": "optional filter",
      "extraction_priority": "high|medium|low"
    }
  ]
}
```

### Field Requirements:

**Required:**
- `tablewide_research` - 2-3 paragraphs (includes discovery patterns, domain context)
- `authoritative_sources` - At least 1 source (simplified: name, url, description)
- `starting_tables_markdown` - Markdown table with citations
- `citations` - Map of citation numbers to URLs

**Optional:**
- `is_complete_enumeration` - Set true if markdown contains ALL entities (default false)
- `identified_tables` - Only if you found specific URLs needing extraction

**Complete Enumeration:**
- Set `is_complete_enumeration: true`
- Include ALL entities in starting_tables_markdown (not just samples)

**Identified Tables:**
- Only include if: specific URL, clear structure, >15 entities
- Include `description` field for extraction context
- Set `extract_table: true` to trigger Step 0b

## FINAL REMINDER

**YOUR RESEARCH QUESTIONS:** {{CONTEXT_RESEARCH_ITEMS}}

**CRITICAL REQUIREMENTS:**
1. Extract ACTUAL entity names with citations into markdown table
2. Use citation numbers [1] [2] linking to the citations object
3. For complete enumeration: Include ALL entities if <=15
4. For identified_tables: Only include specific URLs with extractable tables
5. Return valid JSON matching format above

**What happens next:**
- Your tablewide_research -> Guides column definition
- Your starting_tables_markdown + citations -> Passed to column definition for prepopulated_rows
- Your identified_tables -> Passed to table extraction (Step 0b)

**Return your research as valid JSON.**
