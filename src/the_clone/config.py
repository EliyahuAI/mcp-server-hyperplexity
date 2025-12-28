#!/usr/bin/env python3
"""
Configuration and strategies for Perplexity Clone.
Defines search context strategies (low/medium/high) that guide search behavior.
"""

# Search context strategies - analogous to Perplexity's low/medium/high context
SEARCH_CONTEXT_STRATEGIES = {
    "low": {
        "description": "Low context - Fast, focused search for simple queries",
        "max_results_per_search": 10,
        "max_iterations": 1,
        "max_sources_to_review": 8,
        "optimization_guidance": """
SEARCH STRATEGY: Low Context (Fast & Focused)

Guidelines:
- Generate 1-2 highly targeted search terms
- Focus on the most direct answer sources
- Prefer recent, authoritative results
- Keep searches narrow and specific
- Optimize for speed over comprehensiveness

Use this for:
- Simple factual queries
- Quick lookups
- Well-defined questions with clear answers
""",
        "evaluation_strictness": "moderate",
        "synthesis_guidance": """
SYNTHESIS DEPTH: Low Context (Concise & Direct)

Guidelines:
- Provide direct, focused answers
- Cover the main points without extensive elaboration
- Use 3-5 key facts
- Keep explanations brief and clear
- Minimal contextual background
- Focus on answering the specific question asked

SOURCE PRIORITY:
- **Prioritize HIGH reliability sources** (H) over MEDIUM (M) and LOW (L)
- Only use MEDIUM/LOW sources if HIGH sources don't cover that aspect

Target: Concise, fact-focused response
"""
    },

    "medium": {
        "description": "Medium context - Balanced search for typical queries",
        "max_results_per_search": 15,
        "max_iterations": 2,
        "max_sources_to_review": 12,
        "optimization_guidance": """
SEARCH STRATEGY: Medium Context (Balanced)

Guidelines:
- Generate 2-3 focused search terms covering key aspects
- Balance breadth and depth of sources
- Include both primary sources and synthesis
- Allow for one refinement iteration if needed
- Prioritize relevance and quality

Use this for:
- Typical questions requiring some synthesis
- Comparative queries
- Questions with multiple aspects
- Standard research queries
""",
        "evaluation_strictness": "moderate",
        "synthesis_guidance": """
SYNTHESIS DEPTH: Medium Context (Balanced Detail)

Guidelines:
- Provide comprehensive coverage of main aspects
- Include relevant context and background where helpful
- Use 5-8 key facts with supporting details
- Explain relationships and comparisons clearly
- Balance breadth (covering all aspects) with depth (adequate detail)
- Include important nuances when relevant

SOURCE PRIORITY:
- **Prioritize HIGH reliability sources** (H) over MEDIUM (M) and LOW (L)
- Only use MEDIUM/LOW sources if HIGH sources don't cover that aspect
- When multiple sources say the same thing, cite the highest reliability one

Target: Well-rounded, informative response with good coverage
"""
    },

    "high": {
        "description": "High context - Comprehensive search for complex queries",
        "max_results_per_search": 20,
        "max_iterations": 3,
        "max_sources_to_review": 18,
        "optimization_guidance": """
SEARCH STRATEGY: High Context (Comprehensive)

Guidelines:
- Generate 3+ diverse search terms covering all angles
- Seek comprehensive, authoritative sources
- Include technical documentation, research papers, and expert analysis
- Allow multiple refinement iterations to fill gaps
- Prioritize depth and accuracy over speed
- Cross-reference multiple sources for verification

Use this for:
- Complex, multi-faceted questions
- Technical deep dives
- Comparison of multiple systems/approaches
- Questions requiring synthesis of multiple domains
- Historical or evolutionary analysis
- Questions where accuracy is critical
""",
        "evaluation_strictness": "strict",
        "synthesis_guidance": """
SYNTHESIS DEPTH: High Context (Maximum Nuance & Breadth)

Guidelines:
- Provide deeply comprehensive coverage of ALL aspects
- Include extensive contextual background and technical details
- Use 8+ key facts with rich supporting information
- Explain subtle distinctions, trade-offs, and nuances
- Cover edge cases, limitations, and implications
- Cross-reference and synthesize information across multiple sources
- Include technical specifications, architectural details, and methodological approaches
- Address both breadth (comprehensive coverage) AND depth (detailed analysis)
- Acknowledge uncertainty and conflicting information when present

SOURCE PRIORITY:
- **Prioritize HIGH reliability sources** (H) over MEDIUM (M) and LOW (L)
- Only use MEDIUM/LOW sources if HIGH sources don't cover that aspect
- When multiple sources say the same thing, cite the highest reliability one
- Provide historical context and evolution when relevant

Target: Authoritative, deeply nuanced response with comprehensive breadth
"""
    },

    "findall": {
        "description": "FindAll mode - Entity identification across independent domains",
        "max_results_per_search": 20,
        "max_iterations": 1,
        "max_sources_to_review": 100,
        "synthesis_guidance": """
SYNTHESIS MODE: FindAll - Entity Identification & Enumeration

**Primary Goal: Extract and list ALL distinct entities/instances that match the query criteria.**

Critical Instructions:
- This is ENTITY IDENTIFICATION, not narrative synthesis
- Extract EVERY entity mentioned across all snippets (from all 5 independent domain searches)
- Create comprehensive tables or structured lists
- Maximize entity count - include ALL relevant instances, not just highlights
- Do NOT be selective - if it matches criteria, include it
- Organize by category/type if appropriate for scannability

Entity Extraction Guidelines:
- Include specific identifying details for each entity:
  - Names, identifiers, codes
  - Key specifications or characteristics
  - Dates, locations, or temporal information
  - Quantitative data where available
- Deduplicate identical entities across searches
- Preserve unique variations (e.g., different trials of same drug)
- Use structured format (table/list) for easy reference

CRITICAL - SOURCE CITATIONS (INLINE ONLY):
- MUST cite sources INLINE within text/facts using snippet IDs
- Format: [verbal_handle, snippet_id] immediately after each claim
- Example: "Cristiano Ronaldo earned $275 million [ronaldo_earnings_275m, S1.2.3.0-p0.85]"
- Include citations inline in table cells, descriptions, or any text field
- Multiple sources for same fact: [handle1, id1] [handle2, id2]
- DO NOT create a separate "citations" field/array in the schema
- DO NOT add citations as a property - embed them in the text only
- Citations are REQUIRED but must be INLINE, not separate fields

SOURCE USAGE:
- Use ALL quality levels (p >= 0.0) - findall accepts everything
- Sources below warning threshold (p < 0.65) are included but marked as lower quality
- Cross-reference entities mentioned in multiple sources
- Extract from ALL 5 search domains for maximum coverage

FORMAT:
- Prefer tables for entities with multiple attributes
- Use lists for simpler enumerations
- Include source citations for EVERY entity and fact
- Group by logical categories if helpful

Target: Maximum entity coverage in structured, scannable format WITH full source attribution
"""
    }
}


def get_search_strategy(context: str = "medium") -> dict:
    """
    Get search strategy configuration for the specified context level.

    Args:
        context: "low" | "medium" | "high" (default: "medium")

    Returns:
        Strategy configuration dict

    Raises:
        ValueError: If context is not one of the valid options
    """
    if context not in SEARCH_CONTEXT_STRATEGIES:
        raise ValueError(f"Invalid search context '{context}'. Must be one of: {list(SEARCH_CONTEXT_STRATEGIES.keys())}")

    return SEARCH_CONTEXT_STRATEGIES[context]


def get_optimization_guidance(context: str = "medium") -> str:
    """
    Get optimization guidance text for the specified context level.

    Args:
        context: "low" | "medium" | "high" (default: "medium")

    Returns:
        Optimization guidance string to pass to search model
    """
    strategy = get_search_strategy(context)
    return strategy["optimization_guidance"]


def get_synthesis_guidance(context: str = "medium") -> str:
    """
    Get synthesis guidance text for the specified context level.

    Args:
        context: "low" | "medium" | "high" (default: "medium")

    Returns:
        Synthesis guidance string to pass to synthesis model
    """
    strategy = get_search_strategy(context)
    return strategy["synthesis_guidance"]


# Default configuration
DEFAULT_SEARCH_CONTEXT = "medium"

# Progressive result fetching strategy
# Starts with fewer results, increases in later iterations
# Avoids fetching/evaluating unnecessary results when early results are sufficient
PROGRESSIVE_MAX_RESULTS = [5, 10, 15, 20]  # Iteration 1: 5, Iteration 2: 10, etc.

# URL deduplication
# Tracks viewed URLs across iterations to avoid re-evaluating same sources
# Saves evaluation tokens and ensures diverse information sources

# Cost per 1000 Perplexity API searches
PERPLEXITY_COST_PER_1000 = 5.0

# DeepSeek V3.2 pricing (per million tokens)
DEEPSEEK_INPUT_COST_PER_M = 0.27
DEEPSEEK_OUTPUT_COST_PER_M = 1.10
