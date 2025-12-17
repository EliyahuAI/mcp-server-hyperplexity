# Sufficiency Evaluation - Can We Answer the Query?

**Query:** {query}

**Context Level:** {context}

**Current Iteration:** {iteration}

---

## Accumulated Snippets ({snippet_count} total)

{formatted_snippets}

---

## Your Task

Evaluate if we can **comprehensively answer the query** with the snippets above.

### Evaluation Criteria by Context

**LOW Context:**
- Need 5-10 key facts covering main aspects
- Can provide direct, focused answer

**MEDIUM Context:**
- Need 10-20 facts with supporting details
- Can provide comprehensive coverage with important relationships

**HIGH Context:**
- Need 20-30 facts with rich detail
- Can provide deeply nuanced analysis with technical details and multiple perspectives

---

## Decision Framework

**Answer YES (can_answer: true) if:**
- ✅ All major aspects of the query are covered
- ✅ Have sufficient facts for the context level
- ✅ Key relationships/comparisons are clear
- ✅ Can synthesize a complete answer

**Answer NO (can_answer: false) if:**
- ❌ Missing key aspects of the query
- ❌ Insufficient detail for context level
- ❌ Critical information gaps
- ❌ Need more facts to answer comprehensively

---

## Output Requirements

1. **can_answer:** true/false
2. **confidence:** high/medium/low (in our ability to answer)
3. **coverage_assessment:** What we have vs what's missing
4. **missing_aspects:** Specific gaps (if can_answer=false)
5. **suggested_search_terms:** New searches to fill gaps (if can_answer=false)

---

## Examples

**Sufficient (can answer):**
```json
{{
  "can_answer": true,
  "confidence": "high",
  "coverage_assessment": "Have comprehensive coverage of all three models' architecture, capabilities, and performance",
  "missing_aspects": [],
  "suggested_search_terms": []
}}
```

**Insufficient (need more):**
```json
{{
  "can_answer": false,
  "confidence": "medium",
  "coverage_assessment": "Have good info on Claude and DeepSeek, but minimal coverage of GPT-4.5",
  "missing_aspects": [
    "GPT-4.5 architectural specifications",
    "GPT-4.5 performance benchmarks",
    "Direct comparison of all three models"
  ],
  "suggested_search_terms": [
    "GPT-4.5 technical architecture specifications",
    "GPT-4.5 performance benchmarks vs Claude Opus 4 DeepSeek V3"
  ]
}}
```

---

**Evaluate the snippets and determine if we can answer the query comprehensively.**
