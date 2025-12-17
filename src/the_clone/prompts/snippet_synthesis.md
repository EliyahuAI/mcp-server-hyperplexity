# Answer Synthesis from Pre-Extracted Snippets

User query: "{query}"

## Synthesis Depth Instructions

{synthesis_guidance}

## Pre-Extracted Snippets

You have {snippet_count} pre-extracted facts/snippets to work with:

{formatted_snippets}

## Your Task

Generate a **structured JSON response** that synthesizes an answer by REFERENCING snippet IDs.

**CRITICAL RULES:**

1. **DO NOT extract new snippets** - All snippets are already provided above
2. **ONLY reference snippet IDs** - Use [S1.1-H], [S1.2-M], etc. in your answer
3. **Use ONLY the snippet IDs shown above** - Do not invent new IDs
4. **Every factual claim must reference snippet ID(s)** - No unsourced claims
5. **Multiple sources for same fact**: [S1.1-H][S1.2-M]

### Snippet ID Format and Quality Scores

- Format: `S{{iteration}}.{{source}}.{{snippet}}-p{{score}}`
- Example: `S1.1.0-p0.95` = Iteration 1, Source 1, Snippet 0, p-score 0.95
- Example: `S1.2.3-p0.65` = Iteration 1, Source 2, Snippet 3, p-score 0.65
- **p-score** (shown in snippet listings and IDs) indicates expected factual accuracy:
  - 0.85-0.95: PRIMARY/DOCUMENTED/ATTRIBUTED sources - prefer these
  - 0.30-0.65: OK quality
  - 0.05-0.20: STALE/PROMOTIONAL/UNSOURCED - use cautiously or avoid

### Output Format

Return JSON with structured comparison organized by aspects/topics:

**comparison**: Structured object with snippet ID references like [S1.1-H]
- Organize by logical aspects (architecture, performance, training, etc.)
- Each value should include snippet ID citations

### Synthesis Guidelines

1. **Organize logically** - Group by aspects/topics that make sense for the query
2. **Prefer high p-scores** - Prioritize snippets with p≥0.85 for factual claims
3. **Be comprehensive** - Cover all relevant high-quality snippets
4. **Cite immediately** - Snippet ID right after each fact
5. **No hallucination** - Only state what snippets support
6. **Weight by quality** - When snippets conflict, prefer higher p-scores
7. **Synthesize across snippets** - Connect related information from multiple sources

### Quality Checklist

- ✅ Every claim has snippet ID reference
- ✅ All snippet IDs are valid (from the list above)
- ✅ Comparison is well-structured and logical
- ✅ No new snippets extracted (only references)

**Remember:** You are synthesizing from pre-extracted snippets, NOT extracting new ones. Your job is to organize and reference the snippets provided, not to generate new content from sources.
