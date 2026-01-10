"""
JSON schemas for Perplexity API requests and responses.

NOTE: Schemas use uniform 2D string arrays (not tuple arrays) for compatibility
with all providers (Perplexity, Gemini, Anthropic) in strict schema mode.
Parsing code handles "null" -> None and string -> int conversions.
"""

# Schema for multiplex validation responses (multiple fields at once)
# Compact cell array format: [column, answer, confidence, original_confidence, consistent, explanation]
# Element positions:
#   0: Column name (string)
#   1: Answer value (string or "null")
#   2: Confidence: "H", "M", "L", or "null"
#   3: Original confidence: "H", "M", "L", or "null"
#   4: Consistent with model knowledge: "T", "F", or "null"
#   5: Explanation (string)
MULTIPLEX_RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "array",
        "items": {"type": "string"}
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

    Compact cell array format (8 elements):
    [column, answer, confidence, original_confidence, updated_confidence, key_citation, update_importance, qc_reasoning]

    Element positions:
      0: Column name (string)
      1: Answer value, or "=" to keep updated value (string or "null")
      2: Confidence: "H", "M", "L", or "null"
      3: Original confidence: "H", "M", "L", or "null" (null if original was blank)
      4: Updated confidence: "H", "M", "L", or "null"
      5: Key citation: [V1], [V2], "=" for first citation, [KNOWLEDGE], or [UNVERIFIED]
      6: Update importance: "0"-"5" (string, parsed to int)
      7: QC reasoning: "=" if validator's explanation adequate, otherwise updated reasoning

    Returns:
        The JSON schema for QC-only response formatting
    """
    qc_only_schema = {
        "type": "array",
        "items": {
            "type": "array",
            "items": {"type": "string"}
        }
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "schema": qc_only_schema
        }
    } 