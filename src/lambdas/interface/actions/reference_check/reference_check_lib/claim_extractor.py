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
            "required": ["is_suitable", "table_name", "total_claims", "claims_with_references", "claims_without_references", "claims"],
            "properties": {
                "is_suitable": {
                    "type": "boolean",
                    "description": "Whether the text is suitable for reference checking"
                },
                "table_name": {
                    "type": "string",
                    "description": "Concise descriptive name for this reference check table (2-5 words)"
                },
                "source_type_guess": {
                    "type": "string",
                    "description": "AI's guess at the source type (e.g., Perplexity, ChatGPT, Academic Paper, etc.)"
                },
                "source_confidence": {
                    "type": "number",
                    "description": "Confidence in source type guess (0.0-1.0)",
                    "minimum": 0,
                    "maximum": 1
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
                    "description": "List of extracted claims",
                    "items": {
                        "type": "object",
                        "required": ["claim_id", "statement", "context"],
                        "properties": {
                            "claim_id": {
                                "type": "string",
                                "description": "Unique identifier for the claim (e.g., claim_001)"
                            },
                            "statement": {
                                "type": "string",
                                "description": "The actual claim being made (1-3 sentences max)"
                            },
                            "context": {
                                "type": "string",
                                "description": "Surrounding text that provides context (1-2 sentences)"
                            },
                            "reference": {
                                "type": ["string", "null"],
                                "description": "Citation/reference linked to this claim (e.g., [1], [2][3], or null if none)"
                            },
                            "reference_details": {
                                "type": ["object", "null"],
                                "description": "Parsed information about the reference (if identifiable)",
                                "properties": {
                                    "authors": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "List of author names"
                                    },
                                    "year": {
                                        "type": "string",
                                        "description": "Publication year"
                                    },
                                    "title": {
                                        "type": "string",
                                        "description": "Paper/article title"
                                    },
                                    "doi": {
                                        "type": ["string", "null"],
                                        "description": "DOI identifier (if present)"
                                    },
                                    "url": {
                                        "type": ["string", "null"],
                                        "description": "URL or arXiv ID (if present)"
                                    },
                                    "source": {
                                        "type": "string",
                                        "description": "Publication venue (journal, conference, etc.)"
                                    }
                                }
                            },
                            "text_location": {
                                "type": "object",
                                "description": "Location of claim in original text",
                                "properties": {
                                    "start_char": {
                                        "type": "integer",
                                        "description": "Character index where claim starts (from document start)"
                                    },
                                    "end_char": {
                                        "type": "integer",
                                        "description": "Character index where claim ends (from document start)"
                                    },
                                    "paragraph_index": {
                                        "type": "integer",
                                        "description": "Which paragraph (0-indexed)"
                                    },
                                    "sentence_index": {
                                        "type": "integer",
                                        "description": "Which sentence within paragraph (0-indexed, optional)"
                                    },
                                    "word_start": {
                                        "type": "integer",
                                        "description": "Starting word index from document start (optional)"
                                    },
                                    "word_end": {
                                        "type": "integer",
                                        "description": "Ending word index from document start (optional)"
                                    },
                                    "section_name": {
                                        "type": "string",
                                        "description": "Section name from markdown headings or labels, prefer last 2 levels (e.g., 'Methods > Data Collection')"
                                    }
                                }
                            }
                        }
                    }
                },
                "reference_list": {
                    "type": "array",
                    "description": "OPTIONAL - Complete reference list (only include if: Path B parsed refs are wrong/unusable, OR Path C numbered citations exist but no refs found)",
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
                                "description": "Complete citation text"
                            }
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
