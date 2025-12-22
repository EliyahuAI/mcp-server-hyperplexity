#!/usr/bin/env python3
"""
Schemas for The Clone 2 - Snippet Extraction and Synthesis.
Defines structured output formats for per-source snippet extraction and synthesis.
"""


def get_snippet_extraction_schema() -> dict:
    """
    Schema for extracting quotes organized by search term WITH validation scores.
    Each quote includes quality assessment (p score and reason).

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
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "Exact quote with [...] for orientation and ... for omissions. For ATTRIBUTED quotes, include the attribution in the text (e.g., 'Dr. Jane Smith, Chief Scientist, stated that...')"
                            },
                            "p": {
                                "type": "number",
                                "description": "Quality probability score. MUST be one of: 0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95",
                                "enum": [0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95]
                            },
                            "reason": {
                                "type": "string",
                                "description": "Validation reason: PRIMARY/DOCUMENTED/ATTRIBUTED (p>=0.85), CONTRADICTED/UNSOURCED/ANONYMOUS/PROMOTIONAL/STALE (p<=0.15), or OK"
                            }
                        },
                        "required": ["text", "p", "reason"]
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
                "description": "Structured comparison organized by aspects/topics. Each value should reference snippet IDs like [S1.1.0-p0.95]"
            }
        },
        "required": ["comparison"]
    }


def get_snippet_extraction_code_schema() -> dict:
    """
    Schema for code-based extraction - compact array format.
    Each quote is [code, p_score, reason_abbrev, verbal_handle].

    Returns:
        JSON schema for code-based snippet extraction response
    """
    return {
        "type": "object",
        "properties": {
            "quotes_by_search": {
                "type": "object",
                "description": "Quotes organized by search term number (e.g., '1', '2', '3')",
                "additionalProperties": {
                    "type": "array",
                    "description": "Array of quotes, each as [code, p_score, reason_abbrev, verbal_handle]",
                    "items": {
                        "type": "array",
                        "description": "Quote as [code, p, reason, handle]. Position-based: [0]=code, [1]=p-score, [2]=reason, [3]=handle.",
                        "minItems": 4,
                        "maxItems": 4,
                        "prefixItems": [
                            {
                                "type": "string",
                                "description": "Location code with backtick, e.g., '`1.1', '`1.2-1.3'"
                            },
                            {
                                "type": "number",
                                "description": "Quality probability",
                                "enum": [0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95]
                            },
                            {
                                "type": "string",
                                "description": "Reason: P/D/A (≥0.85), O (mid), C/U/N/PR/S/SL (≤0.15, SL=AI slop)",
                                "enum": ["P", "D", "A", "O", "C", "U", "N", "PR", "S", "SL"]
                            },
                            {
                                "type": "string",
                                "description": "Verbal handle: short semantic tag with qualifications (e.g., 'mortgage_rate_dec2025', 'solar_residential_only', 'opus_4.5_mmlu')"
                            }
                        ],
                        "items": False
                    }
                }
            }
        },
        "required": ["quotes_by_search"]
    }


def get_snippet_extraction_batch_code_schema() -> dict:
    """
    Schema for batch code-based extraction from multiple sources.
    Organizes quotes by source ID first, then by search term within each source.
    Each quote is [code, p_score, reason_abbrev, verbal_handle] with source-prefixed codes.

    Returns:
        JSON schema for batch code-based extraction response
    """
    return {
        "type": "object",
        "properties": {
            "quotes_by_source": {
                "type": "object",
                "description": "Quotes organized by source ID (e.g., 'S1', 'S2', 'S3'), then by search term number within each source",
                "additionalProperties": {
                    "type": "object",
                    "description": "For this source, quotes organized by search term number (e.g., '1', '2', '3')",
                    "additionalProperties": {
                        "type": "array",
                        "description": "Array of quotes from this source for this search term, each as [code, p_score, reason_abbrev, verbal_handle]",
                        "items": {
                            "type": "array",
                            "description": "Quote as [code, p, reason, handle]. Position-based: [0]=code, [1]=p-score, [2]=reason, [3]=handle.",
                            "minItems": 4,
                            "maxItems": 4,
                            "prefixItems": [
                                {
                                    "type": "string",
                                    "description": "Source-prefixed location code with backtick, e.g., '`S1:1.1', '`S2:2.3-2.5'"
                                },
                                {
                                    "type": "number",
                                    "description": "Quality probability",
                                    "enum": [0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95]
                                },
                                {
                                    "type": "string",
                                    "description": "Reason: P/D/A (≥0.85), O (mid), C/U/N/PR/S/SL (≤0.15, SL=AI slop)",
                                    "enum": ["P", "D", "A", "O", "C", "U", "N", "PR", "S", "SL"]
                                },
                                {
                                    "type": "string",
                                    "description": "Verbal handle: short semantic tag with qualifications/limitations (e.g., 'mortgage_rate_dec2025', 'solar_residential_only', 'opus_4.5_mmlu', 'post_2024')"
                                }
                            ],
                            "items": False
                        }
                    }
                }
            }
        },
        "required": ["quotes_by_source"]
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
