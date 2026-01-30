# Row Discovery Task

**⚠️ BE TERSE: Entity names and key identifiers only. Validation expands details later.**

═══════════════════════════════════════════════════════════════
## 🔍 YOUR SEARCH TASK
═══════════════════════════════════════════════════════════════

Find entities within **{{SUBDOMAIN_NAME}}** matching:

{{HARD_REQUIREMENTS}}

{{AUTHORITATIVE_SOURCE}}

{{PRIORITY_SEARCH_QUERIES}}

═══════════════════════════════════════════════════════════════
## 📋 RESULTS SPECIFICATION
═══════════════════════════════════════════════════════════════

**TARGET:** Return {{TARGET_ROWS}} entities

**IDENTIFY EACH ENTITY USING:**
{{ID_COLUMNS}}

{{EXAMPLE_ENTITIES}}

**FILTERING RULES:**
- Search results must match ALL hard requirements above
- If you see unrelated results (wrong geography, wrong time period, wrong domain), refine your queries
- Only include REAL entities you actually found (never fabricate)
- Include entities even with moderate scores (we filter later)

═══════════════════════════════════════════════════════════════
## 📋 ADDITIONAL CONTEXT
═══════════════════════════════════════════════════════════════

**About This Table:**
- User's Original Request: {{USER_CONTEXT}}
- Table Purpose: {{TABLE_PURPOSE}}
- Background Research: {{TABLEWIDE_RESEARCH}}

**Focus Area:** {{SUBDOMAIN_FOCUS}}

**Note:** This subdomain is a suggested focus to organize parallel work. Include relevant entities outside this focus if you find them during searches.

**Soft Requirements (Preferences - better scores if met):**
{{SOFT_REQUIREMENTS}}

**All Search Queries (if you need more options):**
{{SEARCH_QUERIES}}

---

═══════════════════════════════════════════════════════════════
## 📊 TABLE COLUMNS - Your Output Must Include These
═══════════════════════════════════════════════════════════════

**Your markdown table MUST have these exact columns (in this order):**

{{COLUMN_HEADERS}}

**Column Descriptions:**
{{COLUMN_DESCRIPTIONS}}

**Instructions:**
- Use the EXACT column names shown above in your table header
- For ID columns: Always populate (these identify the entity)
- For RESEARCH columns: Populate if information is readily available from search results
- Leave cells blank if data not found (don't fabricate)
- Use inline citations [n] after each value you find (e.g., "Anthropic[1]")
- **BE TERSE:** Short values only. Validation expands later.

---

═══════════════════════════════════════════════════════════════
## 📈 SCORING - Rate Each Entity on 3 Dimensions (0-1.0 scale)
═══════════════════════════════════════════════════════════════

Provide scores in the separate `scoring` array (NOT as columns in the table).

### 1. Relevancy (0-1.0)
How well does this entity match the requirements?
- **1.0** = Perfect match (meets all hard + most soft requirements)
- **0.7** = Strong match (meets all hard + some soft requirements)
- **0.4** = Moderate match (meets all hard requirements, few soft)
- **0.0** = Weak match (violates hard requirements - don't include)

### 2. Source Reliability (0-1.0)
How reliable are your information sources?
- **1.0** = Primary sources (official website, government database, official docs)
- **0.7** = Secondary sources (LinkedIn, major news outlets, TechCrunch)
- **0.4** = Tertiary sources (blogs, forums, aggregators)
- **0.0** = Unreliable or unverified

### 3. Recency (0-1.0)
How recent is the information?
- **1.0** = Less than 3 months old
- **0.7** = 3-6 months old
- **0.4** = 6-12 months old
- **0.0** = More than 12 months or date unknown

---

{{PREVIOUS_SEARCH_IMPROVEMENTS}}

═══════════════════════════════════════════════════════════════
## 📤 OUTPUT FORMAT - JSON with Markdown Table + Citations Map
═══════════════════════════════════════════════════════════════

**IMPORTANT: Output as JSON with a markdown table string and citations dictionary.**

```json
{
  "subdomain": "{{SUBDOMAIN_NAME}}",
  "candidates_markdown": "| Company Name | CEO Name | CEO Education |\n|---|---|---|\n| Anthropic[1] | Dario Amodei[1][2] | Princeton[2] |\n| OpenAI[3] | Sam Altman[3] | Stanford[4] |",
  "citations": {
    "1": "https://anthropic.com/about",
    "2": "https://en.wikipedia.org/wiki/Dario_Amodei",
    "3": "https://openai.com/about",
    "4": "https://en.wikipedia.org/wiki/Sam_Altman"
  },
  "scoring": [
    {"row_id": "Anthropic", "relevancy": 0.95, "reliability": 1.0, "recency": 0.9, "rationale": "Leading AI safety company, meets all requirements"},
    {"row_id": "OpenAI", "relevancy": 0.90, "reliability": 1.0, "recency": 0.95, "rationale": "Major AI research lab, strong match"}
  ]
}
```

### Candidates Table Format

The `candidates_markdown` field must be a markdown table with:
1. **ALL columns from the specification above** (ID columns first, then RESEARCH columns)
2. **Inline citations** [n] after each value (e.g., "Value[1][2]")
3. **Standard markdown table format** with header row and separator row

**Example with ALL columns:**
```
| Company Name | Industry | Revenue | CEO Name |
|---|---|---|---|
| Anthropic[1] | AI Safety[1] | $500M[2] | Dario Amodei[1] |
| OpenAI[3] | AI Research[3] | $1.3B[4] | Sam Altman[3] |
```

### Citations Format

The `citations` field maps citation numbers to URLs:
```json
{
  "1": "https://source1.com",
  "2": "https://source2.com"
}
```

**Citation Rules:**
- Start numbering from 1 (or from {{CITATION_START_NUMBER}} if provided)
- Each unique source gets a unique number
- The same source can be cited multiple times using the same number
- Include ALL sources used for any value in the table

### Scoring Format

The `scoring` array contains one entry per row:
```json
{
  "row_id": "First ID column value",
  "relevancy": 0.95,
  "reliability": 1.0,
  "recency": 0.9,
  "rationale": "Brief reason"
}
```

---

═══════════════════════════════════════════════════════════════
## ⚠️ IF NO MATCHES FOUND (This is a bad outcome - avoid if possible)
═══════════════════════════════════════════════════════════════

**Lower quality results are greatly preferred over no results** - as long as they are real entities.

If you absolutely cannot find ANY entities that meet the hard requirements, explain why:

```json
{
  "subdomain": "{{SUBDOMAIN_NAME}}",
  "candidates_markdown": "",
  "citations": {},
  "scoring": [],
  "no_matches_reason": "Specific explanation of why no matches were found",
  "search_improvements": [
    "Suggestion 1 for improving search strategy",
    "Suggestion 2 for different query approaches"
  ]
}
```

**Note:** When no matches found, `candidates_markdown` should be an empty string `""`.

**Possible reasons to report:**
- "Search queries too broad/narrow, no specific entity results"
- "Authoritative list database not accessible or returned no results"
- "Queries found general information but no identifiable entities"
- "Technical/niche subdomain with limited public information"

---

═══════════════════════════════════════════════════════════════
## 💡 SEARCH IMPROVEMENTS (Optional - Help Future Searches)
═══════════════════════════════════════════════════════════════

If you experienced difficulties finding candidates or had to try multiple search approaches, provide suggestions in the `search_improvements` array.

**Include search_improvements if:**
- Initial search queries didn't work well and you had to reformulate
- You found better query patterns that could help other subdomains
- Certain search terms or approaches proved more effective than others
- You discovered missing context that would help narrow results

---

═══════════════════════════════════════════════════════════════
## 🚫 DOMAIN FILTERING FEEDBACK (Optional - Reduce Noise)
═══════════════════════════════════════════════════════════════

If you notice patterns about which domains provided poor results, provide feedback in `domain_filtering_recommendations`.

**IMPORTANT: You can only recommend EXCLUSIONS, not inclusions.**

**Format:**
```json
{
  "subdomain": "{{SUBDOMAIN_NAME}}",
  "domain_filtering_recommendations": {
    "add_to_excluded": ["domain1.com", "domain2.com"],
    "reasoning": "Specific explanation of why these domains should be excluded"
  },
  "candidates_markdown": "| ... |",
  "citations": {...}
}
```

---

═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER - Your Core Task
═══════════════════════════════════════════════════════════════

**GOAL:** Find **{{TARGET_ROWS}} unique, real entities** for: **{{SUBDOMAIN_NAME}}**

**CRITICAL INSTRUCTIONS:**
1. ✅ If authoritative source provided above → **SEARCH THERE FIRST**
2. ✅ Use example entities to understand what types of entities to find
3. ✅ Only include REAL entities you actually found (never fabricate)
4. ✅ Use EXACT column names from the specification above
5. ✅ Include ALL columns (ID + RESEARCH) in your markdown table
6. ✅ Use inline citations [n] after each value
7. ✅ Include entities even with moderate scores (we filter later)
8. ✅ Return valid JSON in the format specified above
9. ✅ **BE TERSE** - validation expands later

**Return your findings as valid JSON.**
