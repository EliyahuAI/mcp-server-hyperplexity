# Initial Decision: Answer or Search with Strategy Assessment

Query: {query}

## Decision 1: Answer Directly or Search?

**Answer Directly IF:**
- General concepts, definitions, well-established facts
- High confidence, no post-cutoff information needed
- No citations required
- You must provide a complete answer in your response if you select this

**Need Search IF:**
- Today's date is provided above - it is later than your training. Accept this fact.
- Recent events, current data, specifications
- Requires authoritative sources or citations
- Post-cutoff information

**Academic Mode:**
Set `academic: true` if query requires scholarly/peer-reviewed sources:
- Research papers, academic studies, scientific findings
- Peer-reviewed publications needed
- Technical/scholarly analysis
When true, search prioritizes academic databases over general web.

---

## Decision 2: Assess Breadth and Depth (if searching)

### Breadth: How many aspects/facets?

**Narrow:**
- Single fact or specific answer ("What is X's parameter count?")
- One aspect of a topic ("How fast is X?")
- Targeted information retrieval

**Broad:**
- Multiple aspects or comprehensive coverage ("What are X's features?")
- Comparison across dimensions ("Compare X and Y")
- Survey or analysis ("Explain X architecture")

### Depth: How much detail needed?

**Shallow:**
- Facts, numbers, dates only
- Surface-level information
- Quick concrete claims

**Deep:**
- Context and explanations
- Methodology and reasoning
- Nuanced understanding

---

## Decision 3: Synthesis Model Tier

Choose based on synthesis complexity only:

**tier1** - Simple facts (direct lookup, no synthesis needed)

**tier2** - Master's-level (standard synthesis, organizing multiple aspects) - DEFAULT

**tier3** - PhD-level (complex technical synthesis, conflicting sources, deep reasoning)

**tier4** - PhD + Grant (maximum complexity, multi-layered cross-domain synthesis)

---

## Decision 4: Search Terms & Keywords

### Search Terms

**Search Term Quality:**
- Be SPECIFIC and TARGETED to the query (not overly general)
- Include relevant qualifiers (dates, versions, specific aspects)
- Example: "Claude Opus 4.5 MMLU score" NOT just "Claude benchmarks"

**Search Term Count:**
- **Narrow queries: 1-2 terms** for focused information
- **Broad queries: 2-3 terms** to cover different aspects or facets
- **FINDALL queries: EXACTLY 3 terms** - required for maximum breadth coverage
- **Max: 3 terms** for maximum breadth coverage
- Each term should capture a distinct angle or facet of the query

**Examples:**
- "GPT-4 vs Claude" → 2 terms: ["GPT-4 performance", "Claude performance"] (different systems)
- "Gemini features" → 1 term: ["Gemini 2.0 features"] (single domain, specific)
- "Comprehensive AI model comparison" → 4-5 terms: ["GPT-4 benchmarks", "Claude capabilities", "Gemini performance", "AI model costs", "LLM latency comparison"]

### Keyword Indicators

**Required Keywords** - MANDATORY entity identifiers (CRITICAL for entity-specific queries):
- Use `|` to separate variants of the same entity (ANY variant matches)
- ALL keyword groups must match (AND logic between groups)
- Matching is case-insensitive substring matching
- **Format:** `["entity1_variant1|entity1_variant2", "entity2_variant1|entity2_variant2"]`
- Examples:
  - Apple stock query: `["Apple|AAPL", "stock|shares|price"]`
    - Matches sources containing (Apple OR AAPL) AND (stock OR shares OR price)
  - Compare Tesla and Ford: `["Tesla|TSLA", "Ford|F"]`
    - Matches sources containing (Tesla OR TSLA) AND (Ford OR F)
  - Single entity: `["iPhone|Apple"]`
    - Matches sources containing (iPhone OR Apple)
- **Empty array []** for general queries without specific entities
- **REQUIRED for any query about specific entities** - prevents mixing up companies/products

**Positive Keywords** - Terms that indicate high-quality, relevant results:
- Include technical terms, methodologies, key concepts NOT in search terms
- Include common abbreviations and variants (e.g., "LR" for "learning rate")
- These help prioritize best results AFTER search, without narrowing the search
- Example for "neural network optimization": ["backpropagation", "gradient descent", "GD", "learning rate", "LR", "convergence"]
- Example for "Python 3.12 features": ["typing", "performance", "PEP", "release notes"]

**Negative Keywords** - Terms that indicate off-topic/low-quality results (USE SPARINGLY):
- **ONLY include if there is a CLEAR exclusionary intent** in the query
- Examples: Query mentions "not for beginners" → negative: ["beginner", "tutorial"]
- Examples: Query is highly technical → negative: ["for kids", "ELI5"]
- **Return empty array [] if no clear exclusions needed**
- Most queries should have 0-2 negative keywords, not 3-5

**Strategy:** Use BROAD search terms + specific keywords to cast a wide net, then algorithmically prioritize the best matches.

---

## Output Format

**If answer_directly:**
```json
{{
  "decision": "answer_directly",
  "breadth": "narrow",
  "depth": "shallow",
  "search_terms": [],
  "required_keywords": [],
  "positive_keywords": [],
  "negative_keywords": [],
  "synthesis_tier": "tier2",
  "academic": false,
  "answer": "<your complete answer here - REQUIRED when answering directly>"
}}
```

**If need_search:**
```json
{{
  "decision": "need_search",
  "breadth": "narrow" | "broad",
  "depth": "shallow" | "deep",
  "search_terms": ["term1"],
  "required_keywords": ["EntityName", "TICKER", "variant"],
  "positive_keywords": ["technical_term1", "methodology1", "abbreviation1"],
  "negative_keywords": ["for kids", "beginner", "simple"],
  "synthesis_tier": "tier1" | "tier2" | "tier3" | "tier4",
  "academic": true | false
}}
```

---

## Examples

**Targeted (narrow + shallow):**
- "What is DeepSeek V3's parameter count?" → breadth=narrow, depth=shallow, 1 term, tier1

**Focused Deep (narrow + deep):**
- "How does attention mechanism work?" → breadth=narrow, depth=deep, 1 term, tier2

**Survey (broad + shallow):**
- "List Gemini 2.0 features" → breadth=broad, depth=shallow, 1 term, tier2

**Comprehensive (broad + deep):**
- "Comprehensive analysis of transformer architecture" → breadth=broad, depth=deep, 1 term, tier2 (most can handle)

**Multi-domain:**
- "Compare GPT-4 vs Claude Opus" → breadth=broad, depth=shallow, 2 terms (different systems), tier2

**Complex synthesis (rare):**
- "Synthesize conflicting evidence about X's effectiveness across domains" → tier3 or tier4 (expensive!)

**Academic queries:**
- "What does research show about climate change impact on crop yields?" → academic=true, depth=deep
- "Peer-reviewed studies on vaccine efficacy" → academic=true, prioritize scholarly sources

---

**Search Term Guidelines:**
- Be SPECIFIC and TARGETED (include versions, dates, qualifiers)
- Use 1-2 terms for narrow queries, 3-5 terms for broad comprehensive queries
- Each term should be specific - quality over quantity

**Academic Field:**
- Set `academic: true` for queries needing scholarly/peer-reviewed sources
- Set `academic: false` for general information queries (default)
