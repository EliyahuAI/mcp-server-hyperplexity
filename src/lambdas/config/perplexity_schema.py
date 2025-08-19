"""
JSON schemas for Perplexity API requests and responses.
"""

# Schema for multiplex validation responses (multiple fields at once)
MULTIPLEX_RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "The name of the field being validated"},
            "answer": {"type": "string", "description": "The validated value that should be used"},
            "confidence": {
                "type": "string", 
                "enum": ["HIGH", "MEDIUM", "LOW"], 
                "description": "Confidence level in the validation"
            },
            "quote": {"type": "string", "description": "Direct quote from a source that supports the answer - only if one exists. If it is accepted general knowledge you can specify the sources as accepted general knowledge."},
            "sources": {"type": "array", "items": {"type": "string"}, "description": "List of source URLs that support the validation"},
            "update_required": {"type": "boolean", "description": "Whether the existing value needs to be updated - only if it is substantially_different"},
            "explanation": {"type": "string", "description": "Explanation of the validation result, succinct reason you believe the provided answer is correct"},
            "substantially_different": {"type": "boolean", "description": "Whether the validated value is substantially different from the input. Would you want to notify someone about this change - or is it trivial?"},
            "consistent_with_model_knowledge": {"type": "string", "description": "Whether the answer is consistent with general knowledge outside of the provided sources"}
        },
        "required": ["column", "answer", "confidence", "sources", "update_required"]
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