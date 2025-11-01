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
            "sources": {"type": "array", "items": {"type": "string"}, "description": "List of source URLs that support the validation"},
            "supporting_quotes": {"type": "string", "description": "Key quotes from sources with citation references. Format: '[1] \"exact quote\" - optional context' where [1] refers to the citation number from the sources list. Include specific data points, dates, or statements. Example: '[1] \"Revenue increased 11% to $158.9B\" from Q3 2024 earnings' or '[2] \"CEO announced\" and [3] \"Company confirmed partnership\"'. Always include quote marks around direct quotes and reference the citation number."},
            "explanation": {"type": "string", "description": "Explanation of the validation result, succinct reason you believe the provided answer is correct"},
            "consistent_with_model_knowledge": {"type": "string", "description": "Whether the answer is consistent with general knowledge outside of the provided sources"}
        },
        "required": ["column", "answer", "confidence", "original_confidence", "sources", "explanation"]
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

    Returns:
        The JSON schema for QC-only response formatting
    """
    qc_only_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "column": {
                    "type": "string",
                    "description": "The name of the field being QC'd - exactly as defined in the FIELD input"
                },
                "qc_reasoning": {
                    "type": "string",
                    "description": "Detailed explanation of why QC revision was necessary and what specific issue was addressed"
                },
                "answer": {
                    "type": "string",
                    "description": "MANDATORY: The QC Entry/value - required for ALL QC responses regardless of action type. This must be the actual content value, NOT a confidence level.",
                    "not": {
                        "enum": ["HIGH", "MEDIUM", "LOW"]
                    }
                },
                "confidence": {
                    "type": "string",
                    "enum": ["HIGH", "MEDIUM", "LOW"],
                    "description": "MANDATORY: QC confidence level for the QC Entry - required for ALL QC responses"
                },
                "original_confidence": {
                    "type": "string",
                    "enum": ["HIGH", "MEDIUM", "LOW"],
                    "description": "MANDATORY: Final confidence level for the original value after QC review (must be provided for all QC responses)"
                },
                "updated_confidence": {
                    "type": "string",
                    "enum": ["HIGH", "MEDIUM", "LOW"],
                    "description": "MANDATORY: Final confidence level for the updated value after QC review (must be provided for all QC responses)"
                },
                "qc_citations": {
                    "type": "string",
                    "description": "ONLY include actual source citations if QC performed additional research and found new sources. Format: '[QC1] Title: \"key quote\" (URL)' or '[QC1] Title (URL)'. Leave empty if no new sources were consulted. DO NOT use this field for [UNVERIFIED] or explanatory text - those belong in qc_reasoning."
                },
                "update_importance": {
                    "type": "string",
                    "description": "0-5 scale rating of change criticality given table purpose, degree of change, and confidence. Format: 'N - Explanation text' where N is 0-5 (score 0 needs no explanation). High importance (4-5) = meaningful changes with high final confidence. Example: '4 - Volatility in market price for Amazon results in hold investment recommendation'"
                }
            },
            "required": ["column", "qc_reasoning", "answer", "confidence", "original_confidence", "updated_confidence", "qc_citations", "update_importance"]
        }
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "schema": qc_only_schema
        }
    } 