#!/usr/bin/env python3
"""
Schemas for merged synthesis (combines snippet extraction + synthesis).
Citations use code format with p-scores and reasons: ["`1.1", 0.95, "P"]
"""


def get_merged_evaluation_synthesis_schema(answer_schema: dict = None) -> dict:
    """
    Schema for merged evaluation + synthesis with code-based citations.

    Used during iterations (not last):
    - If can answer: provides answer with code citations
    - If cannot: provides missing aspects and suggested searches

    Citations format: ["`code", p_score, "reason"] inline in answer text
    Example: "Fact ["`1.1", 0.95, "P"] and another ["`2.3-2.5", 0.85, "A"]"

    Returns:
        JSON schema
    """
    return {
        "type": "object",
        "properties": {
            "can_answer": {
                "type": "boolean",
                "description": "Can we comprehensively answer the query with current sources?"
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Confidence in our ability to answer"
            },
            "answer_raw": answer_schema if answer_schema else {
                "type": "object",
                "description": "Complete answer with code citations when can_answer=true, empty object {} when can_answer=false. Citations format: [\"`code\", p_score, \"reason\"]"
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


def get_merged_synthesis_only_schema(answer_schema: dict = None) -> dict:
    """
    Schema for merged synthesis-only (last iteration) with code citations.
    No evaluation, just generate answer with self-assessment.

    Citations format: ["`code", p_score, "reason"] inline in answer text
    Example: "Fact ["`1.1", 0.95, "P"] and another ["`2.3-2.5", 0.85, "A"]"

    Returns:
        JSON schema
    """
    # If custom schema provided, use it; otherwise use flexible comparison structure
    if answer_schema:
        base_schema = answer_schema
    else:
        base_schema = {
            "type": "object",
            "description": "Nested answer structure with code citations. Citations format: [\"`code\", p_score, \"reason\"]. Avoid repetitive keys."
        }

    return {
        "type": "object",
        "properties": {
            "comparison": base_schema,
            "self_assessment": {
                "type": "string",
                "enum": ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-"],
                "description": "Grade synthesis quality: A+/A if handled well OR info not available, B if struggled with complexity, C if insufficient"
            }
        },
        "required": ["comparison", "self_assessment"]
    }
