# FindAll Mode: Entity Identification Strategy

Query: {query}

## Mission: Identify & List Entities

**FINDALL is about ENTITY IDENTIFICATION** - finding as many distinct instances, examples, or entities as possible that match the query criteria.

Your goal: Generate 5 search terms that target **INDEPENDENT DOMAINS** to maximize coverage and minimize source overlap.

## Critical: Domain Independence Strategy

**Each of the 5 search terms MUST target DIFFERENT sources/domains to avoid overlap.**

Use these diversification strategies:

### 1. **Subcategory Segmentation**
Break the domain into distinct subcategories
- Example (oncology drugs): "lung cancer phase 3 drugs", "breast cancer phase 3 drugs", "immunotherapy phase 3", "targeted therapy phase 3", "chemotherapy phase 3"

### 2. **Temporal Segmentation**
Split by time periods to access different sources
- Example: "phase 3 oncology drugs 2024-2025", "phase 3 oncology drugs 2022-2023", "phase 3 oncology drugs 2020-2021", "FDA approved oncology drugs 2024", "oncology drugs clinical trials database"

### 3. **Geographic/Regional**
Target different geographic regions
- Example: "US FDA phase 3 oncology drugs", "European EMA oncology trials", "Asian oncology drug trials", "global oncology clinical trials", "Australia oncology drug approvals"

### 4. **Institutional/Database Sources**
Target specific authoritative sources
- Example: "ClinicalTrials.gov phase 3 oncology", "FDA oncology drug approvals", "NIH cancer treatment trials", "ASCO oncology presentations", "pharma company oncology pipelines"

### 5. **Demographic/Population**
Segment by patient populations
- Example: "pediatric oncology phase 3 trials", "elderly cancer treatment trials", "rare cancer drug trials", "common cancer drug trials", "precision oncology biomarker trials"

### 6. **Mixed Strategies**
Combine approaches for maximum independence
- Subcategory + Time: "lung cancer drugs 2024", "breast cancer trials 2023"
- Geographic + Institutional: "US clinical trials database", "European oncology approvals"

## Search Term Requirements

**Generate EXACTLY 3 search terms using this pattern:**

**Strategy: 1 General + 2 Subdomain Searches**

1. **Search 1 (General/Broad):** Main topic with comprehensive list focus
   - Example: "complete list top athletes 2025 rankings"
   - Goal: Capture primary authoritative lists

2-3. **Searches 2-3 (Subdomain Segmentation):** Target specific segments
   - Use subcategory, temporal, geographic, or demographic splits
   - Each should yield DIFFERENT entities from the general search
   - Cover complementary aspects to fill gaps

Each search should:
- Minimize overlap with other searches
- Target specific entity segments
- Be specific enough to find distinct entities
- Together provide comprehensive domain coverage

**Good Example (Drug Trials):**
1. "ClinicalTrials.gov phase 3 oncology 2024-2025" ← Database + time (broad)
2. "FDA approved cancer drugs 2024" ← Regulatory + recent approvals
3. "immunotherapy phase 3 trials" ← Specific mechanism

**Bad Example (Overlapping domains):**
1. "phase 3 oncology drugs"
2. "phase 3 cancer drugs"
3. "oncology clinical trials phase 3"
← All will return similar sources!

## Examples by Query Type

**Query: "AI image generation models"**
Domain Independence Strategy:
1. "Stable Diffusion DALL-E Midjourney 2024-2025" ← Major models + recent
2. "open source image generation models GitHub" ← Source type (open source)
3. "enterprise AI image APIs comparison" ← Commercial perspective

**Query: "renewable energy storage"**
Domain Independence Strategy:
1. "battery storage projects 2024 lithium-ion" ← Recent projects + dominant tech
2. "pumped hydro energy storage installations" ← Alternative technology
3. "residential solar battery systems cost" ← Consumer segment

---

## Keyword Indicators

**Required Keywords** - MANDATORY entity identifiers (CRITICAL for entity-specific queries):
- Use `|` to separate variants of the same entity (ANY variant matches)
- ALL keyword groups must match (AND logic between groups)
- Format: `["entity1|variant1", "entity2|variant2"]`
- Example for oncology drugs: `["cancer|oncology", "phase 3|phase III|P3"]`
- Empty `[]` for general/conceptual queries without specific entities

**Positive Keywords** - Terms that indicate high-quality, relevant results:
- Technical terms, methodologies, key concepts NOT already in search terms
- Common abbreviations and variants
- These help prioritize best results AFTER search
- Focus on domain-specific technical language

**Negative Keywords** - Terms that indicate off-topic/low-quality results:
- Beginner-focused content if query is technical
- Unrelated topics that might appear in broad searches
- Content types to avoid (if any)
- Strong filter - even ONE match suggests result is likely irrelevant

---

## Academic Mode

Set `academic: true` if query requires scholarly/peer-reviewed sources:
- Research papers, studies, scientific findings
- Peer-reviewed publications needed
- Technical/scholarly analysis
- Medical/pharmaceutical research

When true, search prioritizes academic databases over general web.

---

## Output Format

```json
{{
  "search_terms": [
    "term1 covering dimension 1",
    "term2 covering dimension 2",
    "term3 covering dimension 3"
  ],
  "required_keywords": ["entity1|variant1", "entity2|variant2"],
  "positive_keywords": ["technical_term1", "methodology1", "abbreviation1"],
  "negative_keywords": ["irrelevant_term1", "off_topic_term2"],
  "academic": true | false
}}
```

---

**Remember:**
- EXACTLY 3 search terms targeting INDEPENDENT DOMAINS
- Minimize source overlap between searches
- Use subcategory, temporal, geographic, or institutional segmentation
- Goal: Maximum entity coverage across different information sources
