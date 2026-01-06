"""
JSON schemas for Perplexity API requests and responses.
"""

# Schema for multiplex validation responses (multiple fields at once)
# Compact cell array format: [column, answer, confidence, original_confidence, consistent, explanation]
MULTIPLEX_RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "array",
        "items": [
            {"type": "string", "description": "Column name"},
            {"type": ["string", "null"], "description": "Answer value"},
            {"type": ["string", "null"], "enum": ["H", "M", "L", None], "description": "Confidence: H(igh), M(edium), L(ow), or null"},
            {"type": ["string", "null"], "enum": ["H", "M", "L", None], "description": "Original confidence"},
            {"type": ["string", "null"], "enum": ["T", "F", None], "description": "Consistent with model knowledge: T(rue), F(alse), or null"},
            {"type": "string", "description": "Explanation"}
        ]
    }
}

def get_response_format_schema(is_multiplex=True):
    """
    Get the multiplex schema for response formatting.
    
    Args:
        is_multiplex: Kept for compatibility, but we always use multiplex now
        
    Returns:
        The JSON schema for multiplex response formatting
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "schema": MULTIPLEX_RESPONSE_SCHEMA
        }
    }

# Additional fields for QC responses that extend the multiplex response schema
ADDITIONAL_QC_FIELDS = {
    "qc_reasoning": {
        "type": "string",
        "description": "Detailed explanation of why QC revision was necessary and what specific issue was addressed"
    }
}

def get_qc_response_format_schema():
    """
    Get the QC-only schema that contains only QC-specific fields.
    QC does not duplicate validation fields - it only provides QC overlay data.

    Compact cell array format (7 elements):
    [column, answer, confidence, original_confidence, updated_confidence, key_citation, update_importance]
    - Confidence values: "H", "M", "L", or null
    - key_citation: Reference validation citations as [V1], [V2] or new QC citations as [1], [2]
    - update_importance: integer 0-5

    Returns:
        The JSON schema for QC-only response formatting
    """
    qc_only_schema = {
        "type": "array",
        "items": {
            "type": "array",
            "items": [
                {"type": "string", "description": "Column name"},
                {"type": ["string", "null"], "description": "Answer value"},
                {"type": ["string", "null"], "enum": ["H", "M", "L", None], "description": "Confidence: H(igh), M(edium), L(ow), or null"},
                {"type": ["string", "null"], "enum": ["H", "M", "L", None], "description": "Original confidence (null if original was blank)"},
                {"type": ["string", "null"], "enum": ["H", "M", "L", None], "description": "Updated confidence"},
                {"type": "string", "description": "Key citation: use [V1], [V2] for validation citations or [1], [2] for new QC web search citations"},
                {"type": "integer", "description": "Update importance (0-5)"}
            ]
        }
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "schema": qc_only_schema
        }
    } 