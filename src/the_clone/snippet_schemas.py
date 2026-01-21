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


def _get_source_metadata_schema() -> dict:
    """Schema for a single source's metadata."""
    return {
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "1-word source identifier (nih, webmd, pubmed, etc.)"
            },
            "c": {
                "type": "string",
                "description": "Classification: Authority + quality codes (H/P, M/A/O, L/U/S)"
            },
            "p": {
                "type": "string",
                "description": "Probability score: p05, p15, p30, p50, p65, p85, p95",
                "enum": ["p05", "p15", "p30", "p50", "p65", "p85", "p95"]
            }
        },
        "required": ["handle", "c", "p"]
    }


def _get_quotes_array_schema() -> dict:
    """Schema for an array of quote pairs."""
    return {
        "type": "array",
        "description": "Array of [detail_limitation, code] pairs",
        "items": {
            "type": "array",
            "description": "[detail_limitation, code] - source derived from code prefix",
            "items": {"type": "string"}
        }
    }


def get_snippet_extraction_batch_code_schema_v4() -> dict:
    """
    Schema for batch extraction with explicit keys (v4) - AI Studio compatible.

    Structure:
    - source_metadata: Per-source assessment with explicit S1-S10 keys
    - quotes_by_search: Quotes per search term with explicit 1-10 keys
    - Source is derived from code prefix (§S1:1.2 -> S1)

    Uses explicit keys instead of additionalProperties for AI Studio compatibility.

    Returns:
        JSON schema for batch code-based extraction
    """
    # Build source_metadata with explicit S1-S10 keys
    source_props = {f"S{i}": _get_source_metadata_schema() for i in range(1, 11)}

    # Build quotes_by_search with explicit 1-10 keys
    search_props = {str(i): _get_quotes_array_schema() for i in range(1, 11)}

    return {
        "type": "object",
        "properties": {
            "source_metadata": {
                "type": "object",
                "description": "Source-level assessment keyed by source ID (S1, S2, ... S10)",
                "properties": source_props
            },
            "quotes_by_search": {
                "type": "object",
                "description": "Quotes organized by search term number (1, 2, ... 10)",
                "properties": search_props
            }
        },
        "required": ["source_metadata", "quotes_by_search"]
    }


def get_snippet_extraction_batch_code_schema_v3() -> dict:
    """
    Schema for batch extraction with flattened structure (v3).
    DEPRECATED: Use v4 for AI Studio compatibility.

    Structure:
    - source_metadata: Per-source assessment (handle, c, p)
    - quotes_by_search: Flat list of quotes per search term
    - Source is derived from code prefix (§S1:1.2 -> S1)

    Returns:
        JSON schema for batch code-based extraction
    """
    return {
        "type": "object",
        "properties": {
            "source_metadata": {
                "type": "object",
                "description": "Source-level assessment keyed by source ID (S1, S2, S3)",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "handle": {
                            "type": "string",
                            "description": "1-word source identifier (nih, webmd, pubmed, etc.)"
                        },
                        "c": {
                            "type": "string",
                            "description": "Classification: Authority + quality codes (H/P, M/A/O, L/U/S)"
                        },
                        "p": {
                            "type": "string",
                            "description": "Probability score: p05, p15, p30, p50, p65, p85, p95",
                            "enum": ["p05", "p15", "p30", "p50", "p65", "p85", "p95"]
                        }
                    },
                    "required": ["handle", "c", "p"]
                }
            },
            "quotes_by_search": {
                "type": "object",
                "description": "Quotes organized by search term number (1, 2, 3)",
                "additionalProperties": {
                    "type": "array",
                    "description": "Array of [detail_limitation, code] pairs",
                    "items": {
                        "type": "array",
                        "description": "[detail_limitation, code] - source derived from code prefix",
                        "items": {"type": "string"}
                    }
                }
            }
        },
        "required": ["source_metadata", "quotes_by_search"]
    }


def get_snippet_extraction_batch_code_schema_v2() -> dict:
    """
    DEPRECATED: Old nested schema. Use v3 instead.
    Kept for backward compatibility.
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
                                        "description": "Either detail_limitation (position 0) or location code (position 1). Location codes start with § like §S1:1.1 or §S2:2.3-2.5 or §S1:* for pass-all."
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
                            "description": "Either detail_limitation (position 0) or location code (position 1). Location codes start with § like §1.1 or §2.3-2.5."
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
    """Current schema - uses v4 with explicit keys for AI Studio compatibility."""
    return get_snippet_extraction_batch_code_schema_v4()


def get_snippet_extraction_code_schema() -> dict:
    """Legacy schema - redirects to v2."""
    return get_snippet_extraction_code_schema_v2()
