# Row Discovery Task

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
## 📊 RESEARCH FIELDS - Optional (Populate If Readily Available)
═══════════════════════════════════════════════════════════════

**Opportunistic Population:** If you find this information during your search, include it in additional columns after the ID columns in your markdown table. If not readily available, leave cells blank.

{{RESEARCH_COLUMNS}}

**Instructions:**
- Try to populate as many as possible from search results
- If information is in search snippets or easily accessible pages, include it
- If information requires deep research or isn't found, leave cell blank
- Don't fabricate - only include what you actually found
- Focus on finding good ID matches first, research data is secondary
- Add research columns between ID columns and the Score columns in your table

---

═══════════════════════════════════════════════════════════════
## 📈 SCORING - Rate Each Entity on 3 Dimensions (0-1.0 scale)
═══════════════════════════════════════════════════════════════

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
## 📤 OUTPUT FORMAT - Return JSON with Markdown Table for Candidates
═══════════════════════════════════════════════════════════════

**IMPORTANT: `candidates` must be a MARKDOWN TABLE STRING, not a JSON array.**

```json
{
  "subdomain": "{{SUBDOMAIN_NAME}}",
  "candidates": "| ID Column 1 | ID Column 2 | Relevancy | Reliability | Recency | Rationale | Sources |\n|---|---|---|---|---|---|---|\n| Value 1 | Value 2 | 0.95 | 1.0 | 0.9 | Brief explanation | url1, url2 |"
}
```

### Candidates Table Format

The `candidates` field is a markdown table with these columns (in order):
1. **ID columns** - All ID fields from the specification above (use exact names)
2. **Relevancy** - Score 0-1
3. **Reliability** - Score 0-1
4. **Recency** - Score 0-1
5. **Rationale** - 1-2 sentence explanation (keep brief, no pipes)
6. **Sources** - Comma-separated URLs

**Example candidates table:**
```
| Company Name | Industry | Relevancy | Reliability | Recency | Rationale | Sources |
|---|---|---|---|---|---|---|
| Anthropic | AI | 0.95 | 1.0 | 0.9 | Leading AI safety company, meets all requirements | anthropic.com, crunchbase.com/anthropic |
| OpenAI | AI | 0.90 | 1.0 | 0.95 | Major AI research lab, strong match | openai.com, techcrunch.com/openai |
| Scale AI | AI/Data | 0.85 | 0.9 | 0.8 | AI data platform, good fit | scale.com, forbes.com/scale-ai |
```

**Requirements:**
- ✅ Use EXACT field names from ID fields list above (copy them exactly)
- ✅ Each row must be UNIQUE (different from other entries)
- ✅ Always include all three scores (Relevancy, Reliability, Recency)
- ✅ Keep Rationale brief (no pipe characters `|` in text)
- ✅ List source URLs comma-separated in Sources column
- ✅ Include header row and separator row (`|---|---|...`)

---

═══════════════════════════════════════════════════════════════
## ⚠️ IF NO MATCHES FOUND (This is a bad outcome - avoid if possible)
═══════════════════════════════════════════════════════════════

**Lower quality results are greatly preferred over no results** - as long as they are real entities.

If you absolutely cannot find ANY entities that meet the hard requirements, explain why:

```json
{
  "subdomain": "{{SUBDOMAIN_NAME}}",
  "no_matches_reason": "Specific explanation of why no matches were found (e.g., search queries returned general information but no specific entities, database was not accessible, etc.)",
  "search_improvements": [
    "Suggestion 1 for improving search strategy",
    "Suggestion 2 for different query approaches"
  ],
  "candidates": ""
}
```

**Note:** When no matches found, `candidates` should be an empty string `""`.

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

**Example:**
```json
{
  "subdomain": "{{SUBDOMAIN_NAME}}",
  "search_improvements": [
    "Faculty directories work better than general web search for researchers",
    "Adding institution name to queries improves result specificity",
    "Grant databases provide more complete contact information than publications"
  ],
  "candidates": "| Researcher Name | Institution | Relevancy | ... |..."
}
```

---

═══════════════════════════════════════════════════════════════
## 🚫 DOMAIN FILTERING FEEDBACK (Optional - Reduce Noise)
═══════════════════════════════════════════════════════════════

If you notice patterns about which domains provided poor results, provide feedback in `domain_filtering_recommendations`.

**IMPORTANT: You can only recommend EXCLUSIONS, not inclusions.**

**Provide domain_filtering_recommendations if:**
- You encountered noise or low-quality results from certain domains
- Specific domains consistently provided irrelevant or low-quality information

**Format:**
```json
{
  "subdomain": "{{SUBDOMAIN_NAME}}",
  "domain_filtering_recommendations": {
    "add_to_excluded": ["domain1.com", "domain2.com"],
    "reasoning": "Specific explanation of why these domains should be excluded"
  },
  "candidates": "| ID Column | ... | Relevancy | ... |..."
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
4. ✅ Use EXACT field names from ID fields list
5. ✅ Include entities even with moderate scores (we filter later)
6. ✅ Return valid JSON in the format specified above

**Return your findings as valid JSON.**
