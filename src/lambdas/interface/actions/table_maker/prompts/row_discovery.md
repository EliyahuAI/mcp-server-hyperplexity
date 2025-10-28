# Row Discovery Task

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **YOUR CORE TASK**: Find {{TARGET_ROWS}} unique entities for subdomain "{{SUBDOMAIN_NAME}}"
2. **AUTHORITATIVE SOURCE** (if found): The specific database/list to search first
3. **REQUIREMENTS**: Hard (dealbreakers) and soft (preferences) criteria
4. **ID FIELDS**: The identification columns you must populate
5. **RESEARCH FIELDS**: Optional additional data to include if found
6. **SCORING GUIDE**: How to score relevancy, reliability, and recency
7. **OUTPUT FORMAT**: Exact JSON structure to return
8. **FINAL REMINDER**: Core task repeated with key instructions

═══════════════════════════════════════════════════════════════
## 🎯 YOUR CORE TASK
═══════════════════════════════════════════════════════════════

**GOAL:** Find **{{TARGET_ROWS}} unique, real entities** for subdomain: **{{SUBDOMAIN_NAME}}**

**DELIVERABLE:** JSON array of candidates with:
- ID fields populated (required)
- Research fields populated (if information readily available)
- Scores for relevancy, reliability, recency
- Source URLs and match rationale

**KEY RULES:**
1. ✅ Only real entities - NEVER fabricate
2. ✅ Use exact field names from ID fields list below
3. ✅ Include entities even with moderate scores (we'll filter later)
4. ✅ If you find < {{TARGET_ROWS}}, return what you found (don't invent more)

---

{{DISCOVERED_LIST_INFO}}

═══════════════════════════════════════════════════════════════
## ⚙️ YOUR SPECIFIC ASSIGNMENT
═══════════════════════════════════════════════════════════════

**Subdomain:** {{SUBDOMAIN_NAME}}

**Focus Area:** {{SUBDOMAIN_FOCUS}}

**Note:** This subdomain is a suggested focus to organize parallel work. Include relevant entities outside this focus if you find them during searches.

---

**Recommended Search Queries:**
{{SEARCH_QUERIES}}

**Search Strategy:**
1. If an authoritative list URL is provided above → **START THERE FIRST**
2. Use the example candidates to understand what types of entities to find
3. Use aggregator sites that list many entities at once (e.g., NIH RePORTER, faculty directories, company databases)
4. Only use general web search if authoritative sources are insufficient
5. Do not fabricate - only include real entities you actually found

---

═══════════════════════════════════════════════════════════════
## ✔️ REQUIREMENTS - What Entities Must/Should Have
═══════════════════════════════════════════════════════════════

**Context About This Table:**
- User's Original Request: {{USER_CONTEXT}}
- Table Purpose: {{TABLE_PURPOSE}}
- Background Research: {{TABLEWIDE_RESEARCH}}

**Hard Requirements (Absolute - entity MUST meet ALL of these):**
{{HARD_REQUIREMENTS}}

**Soft Requirements (Preferences - better scores if met):**
{{SOFT_REQUIREMENTS}}

**Instructions:**
- ❌ **Hard requirements are dealbreakers** - don't include entities that violate these
- ✅ **Soft requirements improve scoring** but aren't required
- Score entities higher when they meet more soft requirements
- An entity meeting all hard requirements but few soft requirements should still be included (with moderate score)

---

═══════════════════════════════════════════════════════════════
## 🆔 ID FIELDS - Must Populate for Every Entity
═══════════════════════════════════════════════════════════════

For each entity you find, populate these ID fields with ACTUAL values from your search:

{{ID_COLUMNS}}

**Example:**
```json
{
  "id_values": {
    "Researcher Name": "Elizabeth Hillman",
    "Institution": "Columbia University"
  }
}
```

---

═══════════════════════════════════════════════════════════════
## 📊 RESEARCH FIELDS - Optional (Populate If Readily Available)
═══════════════════════════════════════════════════════════════

**Opportunistic Population:** If you find this information during your search, include it. If not readily available, leave blank or omit.

{{RESEARCH_COLUMNS}}

**Instructions:**
- Try to populate as many as possible from search results
- If information is in search snippets or easily accessible pages, include it
- If information requires deep research or isn't found, leave blank or omit
- Don't fabricate - only include what you actually found
- Focus on finding good ID matches first, research data is secondary

**Example:**
```json
{
  "id_values": {
    "Researcher Name": "Elizabeth Hillman",
    "Institution": "Columbia University"
  },
  "research_values": {
    "Title": "Professor of Biomedical Engineering",
    "Country": "United States",
    "Research Focus Area": "Optical imaging and microscopy for neuroscience"
  },
  "populated_columns": ["Researcher Name", "Institution", "Title", "Country", "Research Focus Area"],
  "missing_columns": ["Email Address", "LinkedIn Profile", "Funding Amount"]
}
```

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
## 📤 OUTPUT FORMAT - Return Exactly This JSON Structure
═══════════════════════════════════════════════════════════════

```json
{
  "subdomain": "{{SUBDOMAIN_NAME}}",
  "candidates": [
    {
      "id_values": {
        "Field Name 1": "value",
        "Field Name 2": "value"
      },
      "research_values": {
        "Optional Field 1": "value",
        "Optional Field 2": "value"
      },
      "populated_columns": ["Field Name 1", "Field Name 2", "Optional Field 1"],
      "missing_columns": ["Optional Field 3", "Optional Field 4"],
      "score_breakdown": {
        "relevancy": 0.95,
        "reliability": 1.0,
        "recency": 0.9
      },
      "match_rationale": "Brief 1-2 sentence explanation of why this entity is a good match",
      "source_urls": [
        "https://source1.com/page",
        "https://source2.com/page"
      ]
    }
  ]
}
```

**Requirements:**
- ✅ Use EXACT field names from ID fields list above (copy them exactly)
- ✅ Each entity must be UNIQUE (different from other entries)
- ✅ Always include all three dimension scores (relevancy, reliability, recency)
- ✅ Keep match_rationale to 1-2 sentences
- ✅ Include specific source URLs where you found the information
- ✅ `research_values`, `populated_columns`, and `missing_columns` are OPTIONAL

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
  "candidates": []
}
```

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
  "candidates": [...]
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
  "candidates": [...]
}
```

---

═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER - Your Core Task
═══════════════════════════════════════════════════════════════

**GOAL:** Find **{{TARGET_ROWS}} unique, real entities** for: **{{SUBDOMAIN_NAME}}**

**CRITICAL INSTRUCTIONS:**
1. ✅ If authoritative list URL provided above → **SEARCH THERE FIRST**
2. ✅ Use example candidates to understand what types of entities to find
3. ✅ Only include REAL entities you actually found (never fabricate)
4. ✅ Use EXACT field names from ID fields list
5. ✅ Include entities even with moderate scores (we filter later)
6. ✅ Return valid JSON in the format specified above

**Return your findings as valid JSON.**
