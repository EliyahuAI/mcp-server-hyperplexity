# Snippet Extraction from Source

Query: "{query}"
Context Level: {context}

## Existing Snippets Already Collected

{formatted_existing_snippets}

## New Source to Analyze

**Title:** {source_title}
**URL:** {source_url}
**Reliability:** {source_reliability}
**Source Length:** {source_length} characters

**Full Text:**
{source_full_text}

## Your Task

Extract key facts/snippets from this source that ADD NEW INFORMATION not already covered by existing snippets.

### Efficiency Rule: 50% Reduction Threshold

**IMPORTANT:** Before extracting snippets, evaluate if it's worth condensing:

- Count the relevant content in the source (characters)
- Estimate how much you would extract (characters)
- If reduction is < 50%, set `use_full_text: true` and skip snippet extraction
- If reduction >= 50%, extract snippets and set `use_full_text: false`

**Examples:**
- Source has 1000 chars, snippets would be 800 chars → 20% reduction → `use_full_text: true`
- Source has 2000 chars, snippets would be 600 chars → 70% reduction → `use_full_text: false`, extract snippets
- Source has 500 chars, all relevant → 0% reduction → `use_full_text: true`

**When use_full_text=true:** Return empty snippets array. We'll use the full source text.

### Snippet Extraction Rules (when use_full_text=false)

Extract 1-5 key facts/snippets following these STRICT rules:

1. **EXACT QUOTES ONLY** - Word-for-word from source
2. **Brackets for orientation** - [of DeepSeek V3], [in 2024], [method] - paraphrase non-critical remarks for clarity
3. **Use "..." for omissions** - Skip non-essential text
4. **Coherent** - Snippets must make sense and be understandable
5. **No hallucination** - If not in text, don't include
6. **Check for duplicates** - Skip if already covered by existing snippets
7. **Topic labeling** - Label each snippet with its topic/aspect (like Agent V3's fact topics)

**Good Examples:**
- "DeepSeek V3 uses MoE architecture with 671B total parameters ... 37B activated per token"
- "Multi-head Latent Attention (MLA) [used in DeepSeek V3] reduces KV cache size"
- "Achieves 85.2% accuracy on MMLU [reasoning benchmark]"

**Bad Examples:**
- "Model employs an advanced architecture" (added "advanced" not in source)
- "Uses efficient MoE design" (added judgment "efficient" not in quote)

### Sufficiency Check

{context_guidance}

**Current Status:**
- Existing snippets: {existing_snippet_count}
- After adding yours: {existing_snippet_count} + your new snippets

**Question:** Do we have SUFFICIENT information to answer the query?

Guidelines:
- Review existing snippets + your new snippets
- Consider context level requirements
- Return `has_sufficient_info: true` only if we can provide a complete answer
- If insufficient, specify what aspects are still missing

## Output Format

Return JSON with:
1. **use_full_text**: Boolean (true if reduction < 50%)
2. **snippets**: Array of new facts/snippets (empty if source adds nothing OR use_full_text=true)
3. **has_sufficient_info**: Boolean
4. **missing_aspects**: Array (if insufficient)

**Note:** Every fact must have textual basis. Be conservative. When in doubt, use direct quotes.
