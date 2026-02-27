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

    Args:
        answer_schema: Optional custom schema to embed in answer_raw

    Returns:
        JSON schema
    """
    # Build answer_raw schema with custom properties if provided
    answer_raw_schema = {
        "type": "object",
        "description": "Complete answer when can_answer=true, empty object {{}} when can_answer=false"
    }

    # Embed custom schema properties in answer_raw
    if answer_schema and answer_schema.get('properties'):
        answer_raw_schema["properties"] = answer_schema["properties"]
        if "required" in answer_schema:
            answer_raw_schema["required"] = answer_schema["required"]

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
            "answer_raw": answer_raw_schema,
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

    Args:
        answer_schema: Optional custom schema to embed in comparison

    Returns:
        JSON schema
    """
    # Base comparison schema
    comparison_schema = {
        "type": "object",
        "description": "Nested comparison structure. Avoid repetitive keys."
    }

    # If custom schema provided, embed its properties in comparison
    if answer_schema and answer_schema.get('properties'):
        comparison_schema["properties"] = answer_schema["properties"]
        if "required" in answer_schema:
            comparison_schema["required"] = answer_schema["required"]

    return {
        "type": "object",
        "properties": {
            "comparison": comparison_schema,
            "self_assessment": {
                "type": "string",
                "description": (
                    "Grade synthesis quality with optional pipe-separated action signals. "
                    "Format: GRADE[|T][|S][|E]. "
                    "Grades: A+/A (expert quality), A-/B (partial/incomplete), C (insufficient). "
                    "|T = more thinking depth needed (bumps thinking budget or escalates model). "
                    "|S = more/better search needed — also provide suggested_search_terms. "
                    "|E = escalate to a smarter expert model (PhD+ reasoning required). "
                    "Examples: 'A', 'B|S', 'C|T|S', 'A+|T', 'B|E', 'C|T|S|E'"
                )
            },
            "suggested_search_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional: Search terms to improve answer if grade < A (use with |S signal)"
            },
            "note_to_self": {
                "type": "string",
                "description": "Optional: Note for next attempt if grade < A"
            }
        },
        "required": ["comparison", "self_assessment"]
    }
