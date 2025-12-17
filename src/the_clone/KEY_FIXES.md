# Key Fixes and Learnings

**Last Updated:** 2025-12-17

---

## Critical Schema Fix: "answer" → "response" → "answer_raw"

### Evolution
**Phase 1:** "answer" → "response" (eliminated double-nesting)
- Double-nesting occurred when "answer" appeared at multiple levels
- Renamed to "response" to avoid confusion

**Phase 2:** "response" → "answer_raw" (DeepSeek preference discovered)
- DeepSeek consistently returned "answer_raw" even when schema specified "response"
- Triggered Haiku cleanup fallback repeatedly
- Changed schema to "answer_raw" → **zero cleanup needed** ✅

### Final Schema Structure
```json
{
  "can_answer": true,
  "confidence": "high",
  "answer_raw": {        ← DeepSeek's preferred field name
    "overview": "...",
    "key_features": {...}
  }
}
```

**Key Learning:** DeepSeek has strong preference for semantic field names like "answer_raw" over generic ones like "response". Aligning schema with model preferences eliminates validation failures.

---

## DeepSeek V3.2 Requirements

### Soft Schema Required
- ✅ **soft_schema=true** (prompt-based enforcement)
- ❌ Hard schemas fail (DeepSeek doesn't support full `json_schema` mode)
- ✅ Works via Vertex AI OpenAI-compatible endpoint

### Schema Constraints Needed
**Triage schema:**
```json
"items": {
  "type": "integer",
  "minimum": 0,
  "maximum": 20,
  "uniqueItems": true
}
```

**All schemas:**
- Make all fields required (no conditionals)
- Use placeholder values ("none", {}, [])
- Avoid field name collisions (answer/response)

---

## Soft Schema with Haiku Cleanup Fallback

**Location:** `src/shared/ai_api_client.py:2417-2447, 3505-3604`

### Implementation Details

**soft_schema parameter:**
- Passed from config through all components (triage, extraction, synthesis)
- Config: `use_soft_schema: true` for DeepSeek variants
- Enables prompt-based JSON enforcement instead of API-level enforcement

**Enhanced Prompt Instructions:**
```
Return your answer as valid JSON matching this schema.
IMPORTANT: Use the EXACT field names specified in the schema (do not rename or modify them)
```

**Cleanup Mechanism:**
1. DeepSeek with soft_schema returns result
2. `_clean_anthropic_soft_schema_response` validates against schema
3. `_validate_and_normalize_soft_schema` with fuzzy_keys=True
4. If field names don't match (e.g., "response" vs "answer_raw"):
   - Triggers Haiku cleanup: `[SOFT_SCHEMA_CLEANUP]`
   - Haiku reformats to exact schema using hard schema
   - Returns cleaned result
5. **With schema="answer_raw":** No cleanup needed! ✅

**Applies to:** All Vertex/DeepSeek calls with soft_schema=True

---

## Date Handling

### Sources Sorted by Recency
- Most recent date → index 0
- Sources reindexed after sorting
- Snippet IDs reflect date-sorted order

### Date Priority in Triage
- Recency is criterion #1
- Dates shown in source headers
- Current date provided to synthesis

---

## Citation Format - Sonar Compatible

### Unified Citation Structure
Citations now use Sonar-compatible format with additional Clone-specific fields:
```json
{
  "url": "...",              ← Sonar field (position 1)
  "title": "...",            ← Sonar field (position 2)
  "cited_text": "...\n...",  ← Sonar field (newline-joined snippets)
  "date": "2025-12-17",      ← Sonar field
  "last_updated": "2025-12-17", ← Sonar field
  "index": 1,                ← Clone extra field
  "reliability": "MEDIUM",   ← Clone extra field
  "snippets": ["...", "..."] ← Clone extra field (array)
}
```

**Benefits:**
- Compatible with Sonar/Sonar Pro tools and parsers
- Retains Clone-specific metadata (index, reliability, snippets array)
- cited_text provides quick preview, snippets array for detailed analysis

### Snippet ID Format
`S{iter}.{search}.{source}.{snippet}-{rel}`
- Source index based on date-sorted order (0 = most recent)

---

## Production Configuration

**Recommended:** `deepseek_variant`
```json
{
  "initial_decision_model": "deepseek-v3.2",
  "triage_model": "deepseek-v3.2",
  "extraction_model": "deepseek-v3.2",
  "use_soft_schema": true,
  "synthesis": "claude-sonnet-4-5"
}
```

**Cost:** ~$0.07/query (30% savings vs Claude-only)
**Quality:** 8 citations avg, comprehensive answers
**Reliability:** Haiku fallback ensures valid outputs

---

## Testing Infrastructure

### Debug Files Saved
For each test run: `test_results/debug/{system}_{timestamp}/`
- `00_config.json` - Configuration used
- `01_initial_decision_prompt.md` - Routing prompt
- `01_initial_decision_schema.json` - Routing schema
- `01_initial_decision_response.json` - Routing response
- `04_synthesis_iter{n}_prompt.md` - Synthesis prompt
- `04_synthesis_iter{n}_schema.json` - Synthesis schema
- `04_synthesis_iter{n}_response.json` - Synthesis response

### Reports Generated
- `parallel_comparison/report_{timestamp}.md` - 4-way comparison
- `varied_complexity/report_{timestamp}.md` - 8 queries across complexity

---

## Known Limitations

### DeepSeek
- ❌ Hard schemas not supported
- ❌ Complex nested schemas can confuse
- ✅ Works well with soft schemas + Haiku fallback
- ✅ 70-90% cost savings on routing/triage/extraction

### The Clone vs Sonar
- The Clone: Slower (50-100s vs 10-30s)
- The Clone: More expensive ($0.07-0.22 vs $0.0004-0.02)
- The Clone: Similar citation count (5-15 vs 6-23)
- The Clone: Shows snippet content (transparency)
- Sonar: Fast, cheap, good citations

**Use The Clone when:** You need transparency, detailed snippets, custom synthesis
**Use Sonar when:** You need speed and low cost
