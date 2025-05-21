"""
JSON schemas for Perplexity API requests and responses.
"""

# Schema for validation responses from Perplexity API
VALIDATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "The validated value that should be used"},
        "confidence": {
            "type": "string", 
            "enum": ["HIGH", "MEDIUM", "LOW"], 
            "description": "Confidence level in the validation, based on the following rubric: 1) Model certainty: H = core fact, no hedging | M = familiar, slight doubt | L = guess / qualifiers; 2) Perplexity.ai check (≤ 3 links): H = ≥ 1 independent authoritative match, no conflict | M = one solid secondary or partial match | L = no credible match, conflict, or only informal sources; 3) Topic volatility: H = stable fact | M = slow‑moving data | L = fast‑changing info. Scoring: High = H in all three steps, Medium = no L's + at least one M, Low = any L (or a step can't be checked)"
        },
        "quote": {"type": "string", "description": "Direct quote from a source that supports the answer"},
        "sources": {"type": "array", "items": {"type": "string"}, "description": "List of source URLs that support the validation"},
        "update_required": {"type": "boolean", "description": "Whether the existing value needs to be updated"},
        "explanation": {"type": "string", "description": "Explanation of the validation result"},
        "substantially_different": {"type": "boolean", "description": "Whether the validated value is substantially different from the input"},
        "consistent_with_model_knowledge": {"type": "string", "description": "Whether the answer is consistent with general knowledge, 'Yes' or 'No' followed by explanation"}
    },
    "required": ["answer", "confidence", "sources", "update_required"]
}

# Schema for multiplex validation responses
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
                "description": "Confidence level in the validation, based on the following rubric: 1) Model certainty: H = core fact, no hedging | M = familiar, slight doubt | L = guess / qualifiers; 2) Perplexity.ai check (≤ 3 links): H = ≥ 1 independent authoritative match, no conflict | M = one solid secondary or partial match | L = no credible match, conflict, or only informal sources; 3) Topic volatility: H = stable fact | M = slow‑moving data | L = fast‑changing info. Scoring: High = H in all three steps, Medium = no L's + at least one M, Low = any L (or a step can't be checked)"
            },
            "quote": {"type": "string", "description": "Direct quote from a source that supports the answer"},
            "sources": {"type": "array", "items": {"type": "string"}, "description": "List of source URLs that support the validation"},
            "update_required": {"type": "boolean", "description": "Whether the existing value needs to be updated"},
            "explanation": {"type": "string", "description": "Explanation of the validation result"},
            "substantially_different": {"type": "boolean", "description": "Whether the validated value is substantially different from the input"},
            "consistent_with_model_knowledge": {"type": "string", "description": "Whether the answer is consistent with general knowledge, 'Yes' or 'No' followed by explanation"}
        },
        "required": ["column", "answer", "confidence", "sources", "update_required"]
    },
    "description": "Array of validation results, one for each field"
}

def get_response_format_schema(is_multiplex=True):
    """
    Get the appropriate schema based on whether we're doing multiplex validation.
    
    Args:
        is_multiplex: Whether we're validating multiple fields
        
    Returns:
        The JSON schema for response formatting
    """
    if is_multiplex:
        return {
            "type": "json_schema",
            "json_schema": {
                "schema": MULTIPLEX_RESPONSE_SCHEMA
            }
        }
    else:
        return {
            "type": "json_schema",
            "json_schema": {
                "schema": VALIDATION_RESPONSE_SCHEMA
            }
        } 