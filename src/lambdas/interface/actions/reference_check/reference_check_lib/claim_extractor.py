"""
Claim Extractor

Extracts verifiable claims from submitted text using SONNET 4.5.
"""

import json
import logging
import os
from typing import Dict, Any
from ai_api_client import AIAPIClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ClaimExtractor:
    """Extracts claims from text using AI."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize claim extractor.

        Args:
            config: Reference check configuration dict
        """
        self.config = config
        self.ai_client = AIAPIClient()

        # Load prompt template
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'prompts',
            'claim_extraction.md'
        )
        with open(prompt_path, 'r') as f:
            self.prompt_template = f.read()

        # Load schema
        schema_path = os.path.join(
            os.path.dirname(__file__),
            'schemas',
            'claim_extraction_schema.json'
        )
        # If schema file doesn't exist, we'll use inline schema
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)
        else:
            # Inline schema definition
            self.schema = self._get_default_schema()

    def _get_default_schema(self) -> Dict[str, Any]:
        """Get default JSON schema for claim extraction."""
        return {
            "type": "object",
            "required": ["is_suitable", "total_claims", "claims_with_references", "claims_without_references", "claims"],
            "properties": {
                "is_suitable": {
                    "type": "boolean",
                    "description": "Whether the text is suitable for reference checking"
                },
                "reason": {
                    "type": "string",
                    "description": "Why text is unsuitable (if is_suitable=false)"
                },
                "suggestion": {
                    "type": "string",
                    "description": "What kind of text would work better (if unsuitable)"
                },
                "total_claims": {
                    "type": "integer",
                    "description": "Total number of claims extracted"
                },
                "claims_with_references": {
                    "type": "integer",
                    "description": "Number of claims with citations"
                },
                "claims_without_references": {
                    "type": "integer",
                    "description": "Number of claims without citations"
                },
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["claim_id", "statement", "context"],
                        "properties": {
                            "claim_id": {"type": "string"},
                            "statement": {"type": "string"},
                            "context": {"type": "string"},
                            "reference": {"type": ["string", "null"]},
                            "reference_details": {
                                "type": ["object", "null"],
                                "properties": {
                                    "authors": {"type": "array", "items": {"type": "string"}},
                                    "year": {"type": "string"},
                                    "title": {"type": "string"},
                                    "doi": {"type": ["string", "null"]},
                                    "url": {"type": ["string", "null"]},
                                    "source": {"type": "string"}
                                }
                            },
                            "text_location": {
                                "type": "object",
                                "properties": {
                                    "start_char": {"type": "integer"},
                                    "end_char": {"type": "integer"},
                                    "paragraph_index": {"type": "integer"}
                                }
                            }
                        }
                    }
                },
                "reference_list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ref_id": {"type": "string"},
                            "full_citation": {"type": "string"}
                        }
                    }
                }
            }
        }

    async def extract_claims(self, submitted_text: str) -> Dict[str, Any]:
        """
        Extract claims from submitted text using SONNET 4.5.

        Args:
            submitted_text: The text to analyze

        Returns:
            Extraction result dict with structure:
            {
                'is_suitable': bool,
                'total_claims': int,
                'claims': [...],
                'reference_list': [...],
                'api_response': {...},  # For metrics
                'processing_time': float
            }
        """
        logger.info(f"[CLAIM EXTRACT] Extracting claims from {len(submitted_text)} chars of text")

        # Build prompt
        prompt = self.prompt_template.replace('{{SUBMITTED_TEXT}}', submitted_text)

        # Get model config
        extraction_config = self.config['extraction']
        model = extraction_config['model']
        max_tokens = extraction_config['max_tokens']
        temperature = extraction_config['temperature']

        # Call AI with structured output
        logger.info(f"[CLAIM EXTRACT] Calling {model} with schema validation")
        try:
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=self.schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=True,
                max_web_searches=0,  # No web search for extraction
                debug_name="reference_check_claim_extraction"
            )

            # Check for errors
            if 'response' not in response and 'error' in response:
                error_msg = response.get('error', 'Unknown error during claim extraction')
                logger.error(f"[CLAIM EXTRACT] AI call failed: {error_msg}")
                return {
                    'is_suitable': False,
                    'reason': f'Error extracting claims: {error_msg}',
                    'total_claims': 0,
                    'claims': [],
                    'error': error_msg
                }

            # Extract structured response
            raw_response = response.get('response', {})

            # Parse the structured content
            if 'choices' in raw_response and len(raw_response['choices']) > 0:
                content = raw_response['choices'][0]['message']['content']
                structured_data = json.loads(content) if isinstance(content, str) else content
            elif 'ai_message' in raw_response:
                # Response is already structured (from cache)
                structured_data = raw_response
            else:
                logger.error(f"[CLAIM EXTRACT] Unexpected response structure")
                structured_data = raw_response

            # Add processing metadata
            extraction_result = {
                **structured_data,
                'api_response': response,  # For metrics tracking
                'processing_time': response.get('processing_time', 0)
            }

            logger.info(
                f"[CLAIM EXTRACT] Extracted {extraction_result.get('total_claims', 0)} claims "
                f"({extraction_result.get('claims_with_references', 0)} with refs, "
                f"{extraction_result.get('claims_without_references', 0)} without)"
            )

            return extraction_result

        except Exception as e:
            logger.error(f"[CLAIM EXTRACT] Exception during extraction: {str(e)}", exc_info=True)
            return {
                'is_suitable': False,
                'reason': f'Exception during extraction: {str(e)}',
                'total_claims': 0,
                'claims': [],
                'error': str(e)
            }


async def extract_claims(submitted_text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to extract claims.

    Args:
        submitted_text: Text to analyze
        config: Reference check configuration

    Returns:
        Extraction result dict
    """
    extractor = ClaimExtractor(config)
    return await extractor.extract_claims(submitted_text)
