#!/usr/bin/env python3
"""
Schemas for source triage and sufficiency evaluation in Clone 2.
"""


def get_source_triage_schema() -> dict:
    """
    Schema for triaging sources from a single search term.
    Selects 0-3 sources that add new information with diversity.

    Returns:
        JSON schema for triage response
    """
    return {
        "type": "object",
        "properties": {
            "selected_indices": {
                "type": "array",
                "items": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 20
                },
                "description": "Indices of 0-3 sources to extract (empty if nothing new)",
                "minItems": 0,
                "maxItems": 3,
                "uniqueItems": True
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of selection (optional for debugging)"
            }
        },
        "required": ["selected_indices"]
    }


def get_sufficiency_evaluation_schema() -> dict:
    """
    Schema for evaluating if we can answer the query with accumulated snippets.
    Used between iterations (not on last iteration).

    Returns:
        JSON schema for sufficiency evaluation response
    """
    return {
        "type": "object",
        "properties": {
            "can_answer": {
                "type": "boolean",
                "description": "Can we comprehensively answer the query with current snippets?"
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Confidence in our ability to answer"
            },
            "coverage_assessment": {
                "type": "string",
                "description": "What aspects are covered vs missing"
            },
            "missing_aspects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key aspects still missing (if can_answer=false)"
            },
            "suggested_search_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New search terms to fill gaps (if can_answer=false)"
            }
        },
        "required": ["can_answer", "confidence", "coverage_assessment"]
    }
