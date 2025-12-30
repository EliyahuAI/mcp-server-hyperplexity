#!/usr/bin/env python3
"""
Updated schemas for snippet extraction with source-level c/p assessment.
Source-level: c (classification), p (probability), source_handle
Snippet-level: code, detail_limitation
"""


def convert_p_string_to_number(p_value):
    """
    Convert p string format (p05, p15, etc.) to number (0.05, 0.15, etc.).

    Args:
        p_value: Either string format ("p05") or already a number (0.05)

    Returns:
        float: Probability as a number (0.05-0.95)
    """
    # If already a number, return as-is
    if isinstance(p_value, (int, float)):
        return float(p_value)

    # If string in pXX format, convert to number
    if isinstance(p_value, str) and p_value.startswith('p'):
        try:
            # Extract number part (05 -> 5, 15 -> 15, etc.)
            num = int(p_value[1:])
            # Convert to decimal (5 -> 0.05, 15 -> 0.15, etc.)
            return num / 100.0
        except (ValueError, IndexError):
            # Fallback to 0.50 if conversion fails
            return 0.50

    # Fallback for any other type
    return 0.50


def get_snippet_extraction_batch_code_schema_v2() -> dict:
    """
    Schema for batch extraction with source-level assessment.

    Structure:
    - Each source has: source_handle, c (classification), p (probability)
    - Each snippet has: [code, detail_limitation]
    - Full handle assembled later: {source_handle}_{detail}_{limitation}

    Returns:
        JSON schema for batch code-based extraction with source-level assessment
    """
    return {
        "type": "object",
        "properties": {
            "quotes_by_source": {
                "type": "object",
                "description": "Quotes organized by source ID (e.g., 'S1', 'S2', 'S3')",
                "additionalProperties": {
                    "type": "object",
                    "description": "Source-level assessment + snippets",
                    "properties": {
                        "source_handle": {
                            "type": "string",
                            "description": "1-word source identifier (freddie, nih, pubmed, nrel, bankrate, etc.)"
                        },
                        "c": {
                            "type": "string",
                            "description": "Classification: Authority + all applicable quality codes (e.g., H/P, M/A/O, L/U/S, H/P/D). Authority (required): H (high), M (medium), L (low). Quality (include all that apply): P, D, A, O, C, U, PR, S, SL, IR. Format: H/P or M/A/O or H/P/D (multiple quality codes allowed)."
                        },
                        "p": {
                            "type": "string",
                            "description": "Source-level probability score (expected pass-rate if judge tests all atomic claims). Format: p05, p15, p30, p50, p65, p85, p95",
                            "enum": ["p05", "p15", "p30", "p50", "p65", "p85", "p95"]
                        },
                        "quotes_by_search": {
                            "type": "object",
                            "description": "Snippets organized by search term number (e.g., '1', '2', '3')",
                            "additionalProperties": {
                                "type": "array",
                                "description": "Array of snippets for this search term, each as [code, detail_limitation]",
                                "items": {
                                    "type": "array",
                                    "description": "Snippet as [detail_limitation, code]. Position-based: [0]=detail_limitation, [1]=code. HANDLE FIRST, code second. Always exactly 2 elements.",
                                    "items": {
                                        "type": "string",
                                        "description": "Either detail_limitation (position 0) or location code (position 1). Location codes start with backtick like S1:1.1 or S2:2.3-2.5 or S1:* for pass-all."
                                    }
                                }
                            }
                        }
                    },
                    "required": ["source_handle", "c", "p", "quotes_by_search"]
                }
            }
        },
        "required": ["quotes_by_source"]
    }


def get_snippet_extraction_code_schema_v2() -> dict:
    """
    Schema for single-source extraction with source-level assessment.
    Same structure as batch but for one source.

    Returns:
        JSON schema for single-source code-based extraction
    """
    return {
        "type": "object",
        "properties": {
            "source_handle": {
                "type": "string",
                "description": "1-word source identifier (freddie, nih, pubmed, etc.)"
            },
            "c": {
                "type": "string",
                "description": "Classification: Authority + all applicable quality codes (e.g., H/P, M/A/O, L/U/S, H/P/D). Authority (required): H (high), M (medium), L (low). Quality (include all that apply): P, D, A, O, C, U, PR, S, SL, IR. Format: H/P or M/A/O or H/P/D (multiple quality codes allowed)."
            },
            "p": {
                "type": "string",
                "description": "Source-level probability score. Format: p05, p15, p30, p50, p65, p85, p95",
                "enum": ["p05", "p15", "p30", "p50", "p65", "p85", "p95"]
            },
            "quotes_by_search": {
                "type": "object",
                "description": "Snippets organized by search term number",
                "additionalProperties": {
                    "type": "array",
                    "description": "Array of snippets, each as [detail_limitation, code]. HANDLE FIRST, code second.",
                    "items": {
                        "type": "array",
                        "description": "Snippet as [detail_limitation, code]. Always exactly 2 elements.",
                        "items": {
                            "type": "string",
                            "description": "Either detail_limitation (position 0) or location code (position 1). Location codes start with backtick like 1.1 or 2.3-2.5."
                        }
                    }
                }
            }
        },
        "required": ["source_handle", "c", "p", "quotes_by_search"]
    }


def get_snippet_extraction_schema() -> dict:
    """
    Legacy text-based extraction schema (not code-based).
    Returns schema for old format with text quotes.
    """
    return {
        "type": "object",
        "properties": {
            "quotes_by_search": {
                "type": "object",
                "description": "Quotes organized by search term number",
                "additionalProperties": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "p": {"type": "number", "enum": [0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95]},
                            "reason": {"type": "string"}
                        },
                        "required": ["text", "p", "reason"]
                    }
                }
            }
        },
        "required": ["quotes_by_search"]
    }


# Backward compatibility - keep old schema function names
def get_snippet_extraction_batch_code_schema() -> dict:
    """Legacy schema - redirects to v2."""
    return get_snippet_extraction_batch_code_schema_v2()


def get_snippet_extraction_code_schema() -> dict:
    """Legacy schema - redirects to v2."""
    return get_snippet_extraction_code_schema_v2()
