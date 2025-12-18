#!/usr/bin/env python3
"""
Unified schemas for Clone 2.
Combines evaluation and synthesis into single calls.
"""


def get_unified_evaluation_synthesis_schema(answer_schema: dict = None) -> dict:
    """
    Schema for combined evaluation + synthesis.

    Used during iterations (not last):
    - If can answer: provides answer immediately
    - If cannot: provides missing aspects and suggested searches

    Returns:
        JSON schema
    """
    return {
        "type": "object",
        "properties": {
            "can_answer": {
                "type": "boolean",
                "description": "Can we comprehensively answer the query with current quotes?"
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Confidence in our ability to answer"
            },
            "answer_raw": answer_schema if answer_schema else {
                "type": "object",
                "description": "Complete answer when can_answer=true, empty object {{}} when can_answer=false"
            },
            "missing_aspects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "What's missing (ONLY if can_answer=false)"
            },
            "suggested_search_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New searches to fill gaps (ONLY if can_answer=false)"
            }
        },
        "required": ["can_answer", "confidence", "answer_raw"]
    }


def get_synthesis_only_schema(answer_schema: dict = None) -> dict:
    """
    Schema for synthesis-only (last iteration).
    No evaluation, just generate answer with self-assessment.

    Returns:
        JSON schema
    """
    return {
        "type": "object",
        "properties": {
            "comparison": {
                "type": "object",
                "description": "Nested comparison structure. Avoid repetitive keys."
            },
            "self_assessment": {
                "type": "string",
                "enum": ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-"],
                "description": "Grade synthesis quality: A+/A if handled well OR info not available, B if struggled with complexity, C if insufficient"
            }
        },
        "required": ["comparison", "self_assessment"]
    }
