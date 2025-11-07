"""
Reference Validator

Validates claims against their references (or via fact-check) using HAIKU 4.5.
"""

import json
import logging
import os
from typing import Dict, Any
from ai_api_client import AIAPIClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ReferenceValidator:
    """Validates claims using AI with web search."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize reference validator.

        Args:
            config: Reference check configuration dict
        """
        self.config = config
        self.ai_client = AIAPIClient()

        # Load prompt template
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'prompts',
            'reference_validation.md'
        )
        with open(prompt_path, 'r') as f:
            self.prompt_template = f.read()

        # Load schema
        schema_path = os.path.join(
            os.path.dirname(__file__),
            'schemas',
            'reference_validation_schema.json'
        )
        # If schema file doesn't exist, use inline schema
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)
        else:
            self.schema = self._get_default_schema()

    def _get_default_schema(self) -> Dict[str, Any]:
        """Get default JSON schema for reference validation."""
        return {
            "type": "object",
            "required": ["claim_id", "statement", "support_level", "confidence", "accessible"],
            "properties": {
                "claim_id": {"type": "string"},
                "statement": {"type": "string"},
                "context": {"type": "string"},
                "reference": {"type": ["string", "null"]},
                "reference_description": {"type": "string"},
                "reference_says": {"type": "string"},
                "qualified_fact": {
                    "type": "string",
                    "description": "The fact as stated by the reference, written in same format as claim, or 'N/A' if claim matches exactly"
                },
                "support_level": {
                    "type": "string",
                    "enum": [
                        "strongly_supported",
                        "supported",
                        "partially_supported",
                        "unclear",
                        "contradicted",
                        "inaccessible"
                    ]
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1
                },
                "validation_notes": {"type": "string"},
                "accessible": {"type": "boolean"},
                "sources_consulted": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        }

    def _build_prompt(self, claim: Dict[str, Any]) -> str:
        """
        Build validation prompt from claim data.

        Args:
            claim: Claim dict from extraction

        Returns:
            Formatted prompt string
        """
        prompt = self.prompt_template

        # Replace placeholders
        replacements = {
            '{{CLAIM_ID}}': claim.get('claim_id', ''),
            '{{STATEMENT}}': claim.get('statement', ''),
            '{{CONTEXT}}': claim.get('context', ''),
            '{{REFERENCE}}': claim.get('reference') or 'None',
            '{{REFERENCE_DETAILS}}': json.dumps(claim.get('reference_details') or {}, indent=2)
        }

        for placeholder, value in replacements.items():
            prompt = prompt.replace(placeholder, value)

        return prompt

    async def validate_claim(self, claim: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a single claim using HAIKU 4.5 with web search.

        Args:
            claim: Claim dict from extraction

        Returns:
            Validation result dict with structure:
            {
                'claim_id': str,
                'statement': str,
                'reference_says': str,
                'support_level': str,
                'confidence': float,
                'validation_notes': str,
                'accessible': bool,
                'api_response': {...},  # For metrics
                'processing_time': float
            }
        """
        claim_id = claim.get('claim_id', 'unknown')
        logger.info(f"[VALIDATE] Validating claim {claim_id}: {claim.get('statement', '')[:100]}...")

        # Build prompt
        prompt = self._build_prompt(claim)

        # Get model config
        validation_config = self.config['validation']
        model = validation_config['model']
        max_tokens = validation_config['max_tokens']
        temperature = validation_config['temperature']
        max_web_searches = validation_config['max_web_searches']

        # Call AI with structured output + web search
        logger.info(f"[VALIDATE] Calling {model} with {max_web_searches} web searches")
        try:
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=self.schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=True,
                max_web_searches=max_web_searches,  # Enable web search for validation
                debug_name=f"reference_check_validation_{claim_id}"
            )

            # Check for errors
            if 'response' not in response and 'error' in response:
                error_msg = response.get('error', 'Unknown error during validation')
                logger.error(f"[VALIDATE] AI call failed for {claim_id}: {error_msg}")
                return {
                    'claim_id': claim_id,
                    'statement': claim.get('statement', ''),
                    'context': claim.get('context', ''),
                    'reference': claim.get('reference'),
                    'reference_description': 'Error during validation',
                    'reference_says': error_msg,
                    'support_level': 'unclear',
                    'confidence': 0.0,
                    'validation_notes': f'Error: {error_msg}',
                    'accessible': False,
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
                logger.error(f"[VALIDATE] Unexpected response structure for {claim_id}")
                structured_data = raw_response

            # Add processing metadata
            validation_result = {
                **structured_data,
                'api_response': response,  # For metrics tracking
                'processing_time': response.get('processing_time', 0)
            }

            logger.info(
                f"[VALIDATE] {claim_id} → {validation_result.get('support_level', 'unknown')} "
                f"(confidence: {validation_result.get('confidence', 0):.2f})"
            )

            return validation_result

        except Exception as e:
            logger.error(f"[VALIDATE] Exception for {claim_id}: {str(e)}", exc_info=True)
            return {
                'claim_id': claim_id,
                'statement': claim.get('statement', ''),
                'context': claim.get('context', ''),
                'reference': claim.get('reference'),
                'reference_description': 'Exception during validation',
                'reference_says': str(e),
                'support_level': 'unclear',
                'confidence': 0.0,
                'validation_notes': f'Exception: {str(e)}',
                'accessible': False,
                'error': str(e)
            }


async def validate_claim(claim: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to validate a single claim.

    Args:
        claim: Claim dict from extraction
        config: Reference check configuration

    Returns:
        Validation result dict
    """
    validator = ReferenceValidator(config)
    return await validator.validate_claim(claim)
