#!/usr/bin/env python3
"""
Schemas for The Clone 2 - Snippet Extraction and Synthesis.
Defines structured output formats for per-source snippet extraction and synthesis.
"""


def get_snippet_extraction_schema() -> dict:
    """
    Schema for extracting quotes organized by search term.
    Can extract quotes for multiple search terms from single source (off-topic quotes).

    Returns:
        JSON schema for snippet extraction response
    """
    return {
        "type": "object",
        "properties": {
            "quotes_by_search": {
                "type": "object",
                "description": "Quotes organized by search term number (e.g., '1', '2', '3')",
                "additionalProperties": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "Exact quote with [...] for orientation and ... for omissions"
                    }
                }
            }
        },
        "required": ["quotes_by_search"]
    }


def get_snippet_synthesis_schema() -> dict:
    """
    Schema for synthesizing answer from pre-extracted snippets.
    Model references snippet IDs, does NOT generate new snippets.

    Returns:
        JSON schema for synthesis response
    """
    return {
        "type": "object",
        "properties": {
            "comparison": {
                "type": "object",
                "description": "Structured comparison organized by aspects/topics. Each value should reference snippet IDs like [S1.1-H]"
            }
        },
        "required": ["comparison"]
    }


def get_sufficiency_check_schema() -> dict:
    """
    Schema for checking if accumulated snippets are sufficient.

    Returns:
        JSON schema for sufficiency check response
    """
    return {
        "type": "object",
        "properties": {
            "is_sufficient": {
                "type": "boolean",
                "description": "Do we have enough information to answer the query?"
            },
            "snippet_count": {
                "type": "integer",
                "description": "Current number of snippets"
            },
            "coverage_assessment": {
                "type": "string",
                "description": "Assessment of how well the query is covered"
            },
            "missing_aspects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "What key aspects are still missing (if insufficient)"
            }
        },
        "required": ["is_sufficient", "snippet_count", "coverage_assessment"]
    }
