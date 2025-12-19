# Initial Decision: Answer or Search with Strategy Assessment

Query: {query}

## Decision 1: Answer Directly or Search?

**Answer Directly IF:**
- General concepts, definitions, well-established facts
- High confidence, no post-cutoff information needed
- No citations required
- You must provide a complete answer in your response if you select this

**Need Search IF:**
- Recent events, current data, specifications
- Requires authoritative sources or citations
- Post-cutoff information

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

## Decision 4: Search Terms (MINIMIZE!)

**Default: 1 search term** for single domain

**Multiple terms ONLY if:**
- Different domains need independent investigation
- Example: "GPT-4 vs Claude" → 2 terms (different systems)
- Example: "Gemini features" → 1 term (single domain)

**Max: 3 terms** - only for complex multi-domain queries

---

## Output Format

**If answer_directly:**
```json
{{
  "decision": "answer_directly",
  "breadth": "narrow",
  "depth": "shallow",
  "search_terms": [],
  "synthesis_tier": "tier2"
}}
```

**If need_search:**
```json
{{
  "decision": "need_search",
  "breadth": "narrow" | "broad",
  "depth": "shallow" | "deep",
  "search_terms": ["term1"],
  "synthesis_tier": "tier1" | "tier2" | "tier3" | "tier4"
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

---

**Minimize search terms. Default to 1 term unless truly different domains.**
