# Initial Decision: Answer, Search Context, and Model Selection

Query: {query}

## Decisions to Make

1. **Answer directly OR Search?**
2. **If search: What context level?**
3. **If search: What synthesis model tier?**

---

## Decision 1: Answer or Search?

**Answer Directly IF:**
- General concepts, definitions, well-established facts
- High confidence, no post-cutoff information needed
- No need for specific citations
- When answering: Provide a complete answer in the answer object

**Need Search IF:**
- Recent events, current data, benchmarks, specifications
- Comparisons requiring up-to-date information
- Benefits from authoritative sources
- When searching: Set answer to empty object {{}}

---

## Decision 2: Search Context (if searching)

{context_guidance}

---

## Decision 3: Synthesis Model Tier (if searching)

{tier_guidance}

---

## Output Format

**If answer_directly:**
- decision: "answer_directly"
- answer: (provide your complete answer as a JSON-formatted string)
- search_context: "none"
- synthesis_model_tier: "none"
- search_terms: []

**If need_search:**
- decision: "need_search"
- answer: "Searching before answering"
- search_context: "low" | "medium" | "high"
- synthesis_model_tier: "fast" | "strong" | "deep_thinking"
- search_terms: ["term1", "term2", ...]

**CRITICAL:** The 'answer' field must NEVER be empty. Always provide content.

Make your decision to get a reliable answer quickly.
