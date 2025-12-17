#!/usr/bin/env python3
"""
Schemas for initial decision layer.
First call decides: Answer directly OR Search.
"""


def get_initial_decision_schema(model_tiers: list = None, contexts: list = None) -> dict:
    """
    Schema for initial smart routing decision.
    Dynamically built from config.

    Decides:
    1. Answer directly OR Search
    2. If search: Context level
    3. If search: Synthesis model tier

    Args:
        model_tiers: List of available tier names (from config)
        contexts: List of available context names (from config)

    Returns:
        JSON schema
    """
    # Defaults if not provided
    if model_tiers is None:
        model_tiers = ["fast", "strong", "deep_thinking"]
    if contexts is None:
        contexts = ["low", "medium", "high"]

    return {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["answer_directly", "need_search"],
                "description": "Can we answer from model knowledge or need to search?"
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Confidence in this decision"
            },
            "answer": {
                "type": "string",
                "minLength": 1,
                "description": "Complete answer (as JSON string) if decision='answer_directly', or 'Searching before answering' if decision='need_search'"
            },
            "search_context": {
                "type": "string",
                "enum": ["none"] + contexts,
                "description": "Search depth if decision='need_search', 'none' if decision='answer_directly'"
            },
            "synthesis_model_tier": {
                "type": "string",
                "enum": ["none"] + model_tiers,
                "description": "Model tier if decision='need_search', 'none' if decision='answer_directly'"
            },
            "search_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Search terms if decision='need_search', empty array [] if decision='answer_directly'",
                "minItems": 0,
                "maxItems": 10
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of decisions"
            }
        },
        "required": ["decision", "confidence", "answer", "search_context", "synthesis_model_tier", "search_terms", "reasoning"]
    }
