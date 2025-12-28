#!/usr/bin/env python3
"""
Schemas for initial decision layer.
First call decides: Answer directly OR Search.
"""


def get_initial_decision_schema(answer_schema: dict = None) -> dict:
    """
    Schema for initial smart routing decision with breadth/depth assessment.

    Decides:
    1. Answer directly OR Search
    2. If search: Breadth (narrow/broad) and Depth (shallow/deep)
    3. Search terms (minimize - only if different domains needed)
    4. If answer_directly: Include answer in custom schema format

    Args:
        answer_schema: Optional custom schema for direct answers (e.g., validation_results)

    Returns:
        JSON schema
    """
    base_schema = {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["answer_directly", "need_search"],
                "description": "Can we answer from model knowledge or need to search?"
            },
            "breadth": {
                "type": "string",
                "enum": ["narrow", "broad"],
                "description": "Narrow=single fact/aspect, Broad=multiple aspects/comprehensive"
            },
            "depth": {
                "type": "string",
                "enum": ["shallow", "deep"],
                "description": "Shallow=facts only, Deep=context+explanation+methodology"
            },
            "search_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Search terms - MINIMIZE! Use 1 term unless different domains need separate searches. Empty [] if answer_directly.",
                "minItems": 0,
                "maxItems": 3
            },
            "positive_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords (including abbreviations/variants) that indicate high-quality, relevant search results. NOT in search terms but suggest valuable information. Empty [] if answer_directly. Examples: technical terms, methodologies, key concepts.",
                "minItems": 0
            },
            "negative_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords indicating off-topic/low-quality results. Empty [] if answer_directly. Examples: 'for kids', 'beginner', 'ELI5', unrelated topics. Strong filter - one match suggests irrelevance.",
                "minItems": 0
            },
            "synthesis_tier": {
                "type": "string",
                "enum": ["tier1", "tier2", "tier3", "tier4"],
                "description": "Synthesis complexity tier: tier1 (fast/simple), tier2 (balanced), tier3 (strong reasoning), tier4 (deepest analysis, hardest problems only)"
            },
            "academic": {
                "type": "boolean",
                "description": "Set true if query requires scholarly/peer-reviewed sources (research papers, academic studies, scientific findings). Prioritizes academic databases over general web."
            }
        },
        "required": ["decision", "breadth", "depth", "search_terms", "positive_keywords", "negative_keywords", "synthesis_tier", "academic"]
    }

    # If custom answer schema provided, merge it for direct answers
    # Keep fields REQUIRED to prevent DeepSeek from skipping them
    if answer_schema and answer_schema.get('properties'):
        for prop_name, prop_schema in answer_schema['properties'].items():
            # Add description: null/empty OK for routing, required for direct answers
            prop_schema_copy = prop_schema.copy()
            if 'description' in prop_schema_copy:
                prop_schema_copy['description'] += " (Provide null/empty if decision='need_search', will be ignored)"
            else:
                prop_schema_copy['description'] = "Provide null/empty if decision='need_search', will be ignored"
            base_schema['properties'][prop_name] = prop_schema_copy

        # Add custom required fields to schema (keeps DeepSeek from skipping)
        if 'required' in answer_schema:
            base_schema['required'].extend(answer_schema['required'])

    return base_schema


def get_findall_schema() -> dict:
    """
    Dedicated schema for FINDALL mode.

    Simplified schema since we already know:
    - decision: "need_search"
    - breadth: "findall"
    - depth: "shallow"

    Only need to determine:
    - search_terms (exactly 5)
    - keywords (positive/negative)
    - synthesis_tier
    - academic flag

    Returns:
        JSON schema for findall mode
    """
    return {
        "type": "object",
        "properties": {
            "search_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "EXACTLY 5 diverse search terms, each covering a different aspect/angle/dimension of the query",
                "minItems": 5,
                "maxItems": 5
            },
            "positive_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords (including abbreviations/variants) that indicate high-quality, relevant search results. NOT in search terms. Domain-specific technical language, methodologies, key concepts.",
                "minItems": 0
            },
            "negative_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords indicating off-topic/low-quality results. Examples: beginner content for technical queries, unrelated topics. Strong filter - one match suggests irrelevance.",
                "minItems": 0
            },
            "academic": {
                "type": "boolean",
                "description": "Set true if query requires scholarly/peer-reviewed sources (research papers, academic studies, scientific findings). Prioritizes academic databases."
            }
        },
        "required": ["search_terms", "positive_keywords", "negative_keywords", "academic"]
    }
