#!/usr/bin/env python3
"""
Schemas for initial decision layer.
First call decides: Answer directly OR Search.
"""


def get_initial_decision_schema() -> dict:
    """
    Schema for initial smart routing decision with breadth/depth assessment.

    Decides:
    1. Answer directly OR Search
    2. If search: Breadth (narrow/broad) and Depth (shallow/deep)
    3. Search terms (minimize - only if different domains needed)

    Returns:
        JSON schema
    """
    return {
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
            "synthesis_tier": {
                "type": "string",
                "enum": ["tier1", "tier2", "tier3", "tier4"],
                "description": "Synthesis complexity tier: tier1 (fast/simple), tier2 (balanced), tier3 (strong reasoning), tier4 (deepest analysis, hardest problems only)"
            }
        },
        "required": ["decision", "breadth", "depth", "search_terms", "synthesis_tier"]
    }
