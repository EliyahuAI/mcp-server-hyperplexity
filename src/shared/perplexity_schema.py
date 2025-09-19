"""
JSON schemas for Perplexity API requests and responses.
"""

# Schema for multiplex validation responses (multiple fields at once)
MULTIPLEX_RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "The name of the field being validated - exactly as defined in the FIELD input"},
            "answer": {"type": "string", "description": "The validated value that should be used"},
            "confidence": {
                "type": "string", 
                "enum": ["HIGH", "MEDIUM", "LOW", None], 
                "description": "Confidence level in the validation, HIGH=correct, MEDIUM=minor issues, LOW=wrong, None=blank stays blank"
            },
            "original_confidence": {
                "type": ["string", "null"],
                "enum": ["HIGH", "MEDIUM", "LOW", None],
                "description": "Confidence in the original value: HIGH=correct, MEDIUM=minor issues, LOW=wrong, None=blank stays blank"
            },
            "reasoning": {"type": "string", "description": "Direct quote from web search results (when available), authoritative sources, or current data. When web search is available, use it to verify recent information for accuracy. When not available, use training knowledge and note any limitations."},
            "sources": {"type": "array", "items": {"type": "string"}, "description": "List of source URLs that support the validation"},
            "explanation": {"type": "string", "description": "Explanation of the validation result, succinct reason you believe the provided answer is correct"},
            "consistent_with_model_knowledge": {"type": "string", "description": "Whether the answer is consistent with general knowledge outside of the provided sources"}
        },
        "required": ["column", "answer", "confidence", "original_confidence", "reasoning", "sources"]
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
    "qc_action_taken": {
        "type": "string",
        "enum": ["confidence_lowered", "value_replaced", "no_change"],
        "description": "The QC action taken: confidence_lowered (only confidence changed), value_replaced (answer and/or confidence changed), no_change (should not appear in QC output)"
    },
    "qc_reasoning": {
        "type": "string",
        "description": "Detailed explanation of why QC revision was necessary and what specific issue was addressed"
    }
}

def get_qc_response_format_schema():
    """
    Get the QC schema that extends the multiplex schema with additional QC fields.

    Returns:
        The JSON schema for QC response formatting
    """
    # Deep copy the multiplex schema and add QC fields
    import copy
    qc_schema = copy.deepcopy(MULTIPLEX_RESPONSE_SCHEMA)

    # Add QC-specific fields to the properties
    qc_schema["items"]["properties"].update(ADDITIONAL_QC_FIELDS)

    # Update required fields to include QC fields
    qc_schema["items"]["required"].extend(["qc_action_taken", "qc_reasoning"])

    return {
        "type": "json_schema",
        "json_schema": {
            "schema": qc_schema
        }
    } 