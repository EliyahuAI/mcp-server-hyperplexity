"""
Reference Extractor

Extracts and confirms references from submitted text using AI when Python parsing fails.
Uses a lightweight model (default: claude-haiku-4-5) for cost efficiency.
"""

import json
import logging
import os
from typing import Dict, Any, List
from ai_api_client import AIAPIClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ReferenceExtractor:
    """Extracts references from text using AI."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize reference extractor.

        Args:
            config: Reference check configuration dict
        """
        self.config = config
        self.ai_client = AIAPIClient()

        # Load prompt template
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'prompts',
            'reference_extraction.md'
        )
        with open(prompt_path, 'r') as f:
            self.prompt_template = f.read()

    def _get_schema(self) -> Dict[str, Any]:
        """Get JSON schema for reference extraction."""
        return {
            "type": "object",
            "required": ["python_refs_acceptable", "total_references", "references"],
            "properties": {
                "python_refs_acceptable": {
                    "type": "boolean",
                    "description": "True if Python-parsed references are complete and acceptable (no need to regenerate). False if you need to extract your own."
                },
                "reason": {
                    "type": "string",
                    "description": "Brief reason for your decision (why Python refs are acceptable OR why you needed to extract your own)"
                },
                "total_references": {
                    "type": "integer",
                    "description": "Total number of references (either confirmed Python refs OR newly extracted refs)"
                },
                "references": {
                    "type": "array",
                    "description": "List of references (either Python refs confirmed as-is OR newly extracted refs)",
                    "items": {
                        "type": "object",
                        "required": ["ref_id", "full_citation"],
                        "properties": {
                            "ref_id": {
                                "type": "string",
                                "description": "Reference identifier (e.g., [1], [2])"
                            },
                            "full_citation": {
                                "type": "string",
                                "description": "Complete citation text with author, year, title, source"
                            }
                        }
                    }
                }
            }
        }

    async def extract_references(self, text: str, parsed_refs: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Extract references from text using AI.

        Args:
            text: The text to analyze
            parsed_refs: Optional Python-parsed references (for context/validation)

        Returns:
            Extraction result dict with structure:
            {
                'success': bool,
                'total_references': int,
                'references': List[Dict],  # [{"ref_id": "[1]", "full_citation": "..."}]
                'api_response': {...},  # For metrics
                'processing_time': float
            }
        """
        logger.info(f"[REF EXTRACT] Extracting references from {len(text)} chars of text")

        # Build prompt with optional parsed reference context
        prompt = self.prompt_template.replace('{{SUBMITTED_TEXT}}', text)

        if parsed_refs:
            ref_context = "\n".join([f"{ref_id} {citation}" for ref_id, citation in sorted(parsed_refs.items(), key=lambda x: int(x[0].strip('[]')))])
            prompt = prompt.replace('{{PARSED_REFERENCES}}', f"\n\n--- PYTHON PARSED REFERENCES (may be incomplete) ---\n{ref_context}\n\nVerify and complete these if needed.")
        else:
            prompt = prompt.replace('{{PARSED_REFERENCES}}', '')

        # Get model config
        ref_extraction_config = self.config.get('reference_extraction', {})
        model = ref_extraction_config.get('model', 'claude-haiku-4-5')
        max_tokens = ref_extraction_config.get('max_tokens', 4096)

        # Call AI with structured output
        logger.info(f"[REF EXTRACT] Calling {model} for reference extraction")
        try:
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=self._get_schema(),
                model=model,
                max_tokens=max_tokens,
                use_cache=True,
                max_web_searches=0,  # No web search for extraction
                debug_name="reference_check_reference_extraction"
            )

            # Check for errors
            if 'response' not in response and 'error' in response:
                error_msg = response.get('error', 'Unknown error during reference extraction')
                logger.error(f"[REF EXTRACT] AI call failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'total_references': 0,
                    'references': []
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
                logger.error(f"[REF EXTRACT] Unexpected response structure")
                structured_data = raw_response

            # Add processing metadata
            extraction_result = {
                **structured_data,
                'success': True,
                'api_response': response,  # For metrics tracking
                'processing_time': response.get('processing_time', 0)
            }

            total_refs = extraction_result.get('total_references', 0)
            logger.info(f"[REF EXTRACT] Extracted {total_refs} references successfully")

            return extraction_result

        except Exception as e:
            logger.error(f"[REF EXTRACT] Exception during extraction: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'total_references': 0,
                'references': []
            }


async def extract_references(text: str, config: Dict[str, Any], parsed_refs: Dict[str, str] = None) -> Dict[str, Any]:
    """
    Convenience function to extract references.

    Args:
        text: Text to analyze
        config: Reference check configuration
        parsed_refs: Optional Python-parsed references

    Returns:
        Extraction result dict
    """
    extractor = ReferenceExtractor(config)
    return await extractor.extract_references(text, parsed_refs)
