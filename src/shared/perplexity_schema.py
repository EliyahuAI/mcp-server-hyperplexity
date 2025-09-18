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