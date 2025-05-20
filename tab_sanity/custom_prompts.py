"""Custom prompts for tab-sanity with fixes for formatting issues."""

# Define JSON example separately to avoid format string issues
JSON_EXAMPLE = '''[
  {
    "column": "Column Name 1",
    "answer": "validated value 1",
    "quote": "direct quote from source",
    "sources": ["url1", "url2"],
    "confidence": "HIGH",
    "update_required": true,
    "explanation": "brief explanation"
  },
  {
    "column": "Column Name 2",
    "answer": "validated value 2",
    "quote": "direct quote from source",
    "sources": ["url1", "url2"],
    "confidence": "HIGH", 
    "update_required": false,
    "explanation": "brief explanation"
  }
]'''

def get_fixed_multiplex_prompt(context: str, columns_to_validate: str) -> str:
    """Return a properly formatted multiplex prompt."""
    prompt = """You are a data validation expert. Your task is to validate multiple fields:

Context:
{}

I need you to validate the following columns:

{}

Provide your answer as a valid JSON array with objects for each column. Format your response as JSON only:

{}

IMPORTANT: Your response must be valid JSON containing objects for ALL the requested columns. No text outside of the JSON array."""
    
    # Use direct formatting to avoid any possible string.format() curly brace issues
    return prompt.format(context, columns_to_validate, JSON_EXAMPLE) 