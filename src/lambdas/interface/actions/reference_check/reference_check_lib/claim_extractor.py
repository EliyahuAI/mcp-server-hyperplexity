"""
Claim Extractor

Extracts verifiable claims from submitted text using SONNET 4.5.
Supports parallel chunked extraction for large texts.
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any, List
from ai_api_client import ai_client

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
        self.ai_client = ai_client

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
                        "required": ["claim_id", "statement", "context", "criticality", "claim_order"],
                        "properties": {
                            "claim_id": {
                                "type": "string",
                                "description": "Unique identifier for the claim (e.g., claim_001)"
                            },
                            "claim_order": {
                                "type": "integer",
                                "description": "REQUIRED: Sequential order as claim appears in original document (1, 2, 3, etc.). This preserves document position before criticality sorting."
                            },
                            "statement": {
                                "type": "string",
                                "description": "The actual claim being made (1-3 sentences max)"
                            },
                            "context": {
                                "type": "string",
                                "description": "Surrounding text that provides context (1-2 sentences)"
                            },
                            "criticality": {
                                "type": "string",
                                "description": "REQUIRED: Criticality assessment in format '{level} - {level_name}: {brief reason}' where level is 1-5 (1=Critical, 5=Context). Example: '1 - Critical: Core thesis claim'"
                            },
                            "reference": {
                                "type": ["string", "null"],
                                "description": "Citation/reference NUMBERS ONLY (e.g., [1], [2][3], or null if none). DO NOT include author names or years - just the number."
                            },
                            "supporting_data": {
                                "type": ["string", "null"],
                                "description": "OPTIONAL: When claim is supported by original measurements/data from THIS paper, provide the ACTUAL data explicitly with numbers, sample sizes, metrics, and table/figure references. Example: 'Model achieved 92% accuracy on benchmark dataset (n=10,000 samples, Table 2, Results section)' or 'Survey results: 78% of 500 participants reported daily social media use averaging 3.2 hours (Figure 1, Methods section)'"
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
                }
            }
        }

    async def extract_claims(self, submitted_text: str) -> Dict[str, Any]:
        """
        Extract claims from submitted text.

        Automatically uses chunked parallel extraction for large texts.

        Args:
            submitted_text: The text to analyze (may be enriched with references)

        Returns:
            Extraction result dict with structure:
            {
                'is_suitable': bool,
                'total_claims': int,
                'claims': [...],
                'reference_list': [...],
                'api_response': {...},  # For metrics
                'processing_time': float,
                'chunked': bool  # True if chunked extraction was used
            }
        """
        # Check if chunking is needed
        from .text_chunker import TextChunker

        chunker = TextChunker(self.config)
        if chunker.should_chunk(submitted_text):
            logger.info(
                f"[CLAIM EXTRACT] Text is large (~{chunker.estimate_tokens(submitted_text)} tokens), "
                f"using chunked parallel extraction"
            )
            return await self.extract_claims_chunked(submitted_text)

        # Standard single-batch extraction for smaller texts
        logger.info(f"[CLAIM EXTRACT] Extracting claims from {len(submitted_text)} chars of text")

        # Build prompt (no extraction range for full text)
        prompt = self._build_prompt(submitted_text, extraction_range=None)

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

    def _build_prompt(self, submitted_text: str, extraction_range: Dict[str, int] = None) -> str:
        """
        Build extraction prompt with optional character range instructions.

        Args:
            submitted_text: Full text to extract from
            extraction_range: Optional dict with 'start_char' and 'end_char' for focused extraction

        Returns:
            Formatted prompt
        """
        # Add extraction range instructions if specified
        if extraction_range:
            range_instructions = f"""
## EXTRACTION RANGE (PARALLEL CHUNKING MODE)

**IMPORTANT**: You are processing a section of a larger document as part of parallel extraction.

**Your assigned extraction range**:
- **Start position**: Character {extraction_range['start_char']}
- **End position**: Character {extraction_range['end_char']}

**Instructions**:
1. **You have access to the FULL DOCUMENT for context** (important for understanding surrounding context)
2. **Extract claims ONLY from characters {extraction_range['start_char']} to {extraction_range['end_char']}**
3. **Do NOT extract claims from outside this range** (other ranges are handled by parallel processes)
4. **Use the full document context** to assess criticality and understand references
5. **All text_location positions must be absolute** (measured from the start of the full document, not from the chunk start)

**Character counting**:
- Character 0 = first character of the document
- Your range: characters {extraction_range['start_char']}-{extraction_range['end_char']}
- If a claim's start_char is {extraction_range['start_char'] + 100}, record it as {extraction_range['start_char'] + 100} (not 100)

**Boundary handling**:
- If a claim starts before your range but ends in it: **SKIP** (will be extracted by previous chunk)
- If a claim starts in your range but ends after it: **INCLUDE** (better to have it than miss it)
- Use your judgment for claims that span the boundary
"""
        else:
            # No range specified - extract from full text
            range_instructions = ""

        # Replace placeholders
        prompt = self.prompt_template.replace('{{EXTRACTION_RANGE_INSTRUCTIONS}}', range_instructions)
        prompt = prompt.replace('{{SUBMITTED_TEXT}}', submitted_text)

        return prompt

    async def extract_claims_chunked(self, enriched_text: str) -> Dict[str, Any]:
        """
        Extract claims from large text using chunked parallel extraction.

        The full enriched text is sent to each parallel call, but each is instructed
        to extract claims only from its assigned character range. This preserves
        context while enabling parallelization.

        Args:
            enriched_text: Full text with CONFIRMED REFERENCES appended

        Returns:
            Merged extraction result with all claims
        """
        from .text_chunker import TextChunker

        logger.info("[CLAIM EXTRACT CHUNKED] Starting chunked parallel extraction")

        try:
            # Initialize chunker and get chunk boundaries
            chunker = TextChunker(self.config)
            chunks = chunker.get_chunk_boundaries(enriched_text)

            # Format chunk sizes for logging
            chunk_sizes = [f"{c['estimated_tokens']}tok" for c in chunks]
            logger.info(
                f"[CLAIM EXTRACT CHUNKED] Processing {len(chunks)} chunks in parallel: "
                f"{chunk_sizes}"
            )

            # Extract claims from each chunk in parallel
            extraction_tasks = [
                self._extract_from_chunk(enriched_text, chunk, chunk_idx, len(chunks))
                for chunk_idx, chunk in enumerate(chunks)
            ]

            chunk_results = await asyncio.gather(*extraction_tasks)

            # Merge results
            merged_result = self._merge_chunk_results(chunk_results, chunks)

            logger.info(
                f"[CLAIM EXTRACT CHUNKED] Merged {merged_result.get('total_claims', 0)} claims "
                f"from {len(chunks)} chunks"
            )

            return merged_result

        except Exception as e:
            logger.error(
                f"[CLAIM EXTRACT CHUNKED] Chunked extraction failed: {e}, "
                f"falling back to single-batch extraction",
                exc_info=True
            )

            # Fallback to single-batch extraction
            # This may still fail if text is too large, but worth trying
            from .text_chunker import TextChunker
            chunker = TextChunker(self.config)
            # Temporarily disable chunking to avoid infinite recursion
            original_threshold = chunker.threshold_tokens
            chunker.threshold_tokens = float('inf')

            try:
                result = await self.extract_claims(enriched_text)
                return result
            finally:
                chunker.threshold_tokens = original_threshold

    async def _extract_from_chunk(
        self,
        full_text: str,
        chunk: Dict[str, Any],
        chunk_idx: int,
        total_chunks: int
    ) -> Dict[str, Any]:
        """
        Extract claims from a specific character range of the full text.

        Args:
            full_text: Complete enriched text (sent for context)
            chunk: Chunk metadata with start_char, end_char, chunk_id
            chunk_idx: Index of this chunk (for logging)
            total_chunks: Total number of chunks (for logging)

        Returns:
            Extraction result for this chunk
        """
        logger.info(
            f"[CHUNK {chunk_idx+1}/{total_chunks}] Extracting from "
            f"chars {chunk['start_char']}-{chunk['end_char']} "
            f"(~{chunk['estimated_tokens']} tokens)"
        )

        # Build prompt with extraction range
        extraction_range = {
            'start_char': chunk['start_char'],
            'end_char': chunk['end_char']
        }
        prompt = self._build_prompt(full_text, extraction_range)

        # Get model config
        extraction_config = self.config['extraction']
        model = extraction_config['model']
        max_tokens = extraction_config['max_tokens']

        # Call AI with structured output
        try:
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=self.schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=True,
                max_web_searches=0,
                debug_name=f"reference_check_claim_extraction_chunk_{chunk_idx}"
            )

            # Parse response
            if 'response' not in response:
                error_msg = response.get('error', 'Unknown error')
                logger.error(f"[CHUNK {chunk_idx+1}] AI call failed: {error_msg}")
                return {
                    'is_suitable': False,
                    'reason': f'Chunk {chunk_idx+1} extraction failed: {error_msg}',
                    'total_claims': 0,
                    'claims': [],
                    'error': error_msg,
                    'chunk_id': chunk['chunk_id']
                }

            # Extract structured response
            raw_response = response.get('response', {})
            if 'choices' in raw_response and len(raw_response['choices']) > 0:
                content = raw_response['choices'][0]['message']['content']
                structured_data = json.loads(content) if isinstance(content, str) else content
            else:
                structured_data = raw_response

            # Add chunk metadata
            result = {
                **structured_data,
                'api_response': response,
                'processing_time': response.get('processing_time', 0),
                'chunk_id': chunk['chunk_id'],
                'chunk_start_char': chunk['start_char'],
                'chunk_end_char': chunk['end_char']
            }

            logger.info(
                f"[CHUNK {chunk_idx+1}/{total_chunks}] Extracted "
                f"{result.get('total_claims', 0)} claims"
            )

            return result

        except Exception as e:
            logger.error(
                f"[CHUNK {chunk_idx+1}] Exception during extraction: {e}",
                exc_info=True
            )
            return {
                'is_suitable': False,
                'reason': f'Chunk {chunk_idx+1} exception: {str(e)}',
                'total_claims': 0,
                'claims': [],
                'error': str(e),
                'chunk_id': chunk['chunk_id']
            }

    def _merge_chunk_results(
        self,
        chunk_results: List[Dict[str, Any]],
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge extraction results from multiple chunks.

        Args:
            chunk_results: List of extraction results from each chunk
            chunks: List of chunk metadata

        Returns:
            Merged extraction result
        """
        # Check if any chunk failed suitability
        for result in chunk_results:
            if not result.get('is_suitable', True):
                logger.warning(
                    f"[MERGE] Chunk {result.get('chunk_id')} marked as unsuitable: "
                    f"{result.get('reason')}"
                )
                # If any chunk is unsuitable, return unsuitable
                return result

        # Collect all claims
        all_claims = []
        for result in chunk_results:
            claims = result.get('claims', [])
            all_claims.extend(claims)

        logger.info(f"[MERGE] Collected {len(all_claims)} total claims from {len(chunk_results)} chunks")

        # Sort claims by document position (start_char)
        all_claims.sort(key=lambda c: c.get('text_location', {}).get('start_char', 0))

        # Renumber claims sequentially
        for idx, claim in enumerate(all_claims, start=1):
            claim['claim_id'] = f"claim_{idx:03d}"
            claim['claim_order'] = idx

        # Aggregate metadata
        total_claims = len(all_claims)
        claims_with_refs = sum(
            1 for c in all_claims
            if c.get('reference') and c.get('reference') != 'null' and c.get('reference') is not None
        )
        claims_without_refs = total_claims - claims_with_refs

        # Use first chunk's metadata as base
        base_result = chunk_results[0]

        # Aggregate processing time
        total_processing_time = sum(r.get('processing_time', 0) for r in chunk_results)

        # Aggregate token usage across all chunks
        total_input_tokens = 0
        total_output_tokens = 0
        total_cache_read_tokens = 0
        total_cache_creation_tokens = 0

        for result in chunk_results:
            api_response = result.get('api_response', {})
            token_usage = api_response.get('token_usage', {})

            total_input_tokens += token_usage.get('input_tokens', 0)
            total_output_tokens += token_usage.get('output_tokens', 0)
            total_cache_read_tokens += token_usage.get('cache_read_input_tokens', 0)
            total_cache_creation_tokens += token_usage.get('cache_creation_input_tokens', 0)

        # Create aggregated API response for cost tracking
        aggregated_api_response = {
            'token_usage': {
                'input_tokens': total_input_tokens,
                'output_tokens': total_output_tokens,
                'cache_read_input_tokens': total_cache_read_tokens,
                'cache_creation_input_tokens': total_cache_creation_tokens
            },
            'response': base_result.get('api_response', {}).get('response', {}),
            'model_used': base_result.get('api_response', {}).get('model_used'),
            'is_cached': False  # Chunked calls are never fully cached
        }

        # Build merged response
        merged = {
            'is_suitable': True,
            'table_name': base_result.get('table_name', 'Reference Check'),
            'source_type_guess': base_result.get('source_type_guess'),
            'source_confidence': base_result.get('source_confidence'),
            'total_claims': total_claims,
            'claims_with_references': claims_with_refs,
            'claims_without_references': claims_without_refs,
            'claims': all_claims,
            'processing_time': total_processing_time,
            'chunked': True,
            'num_chunks': len(chunks),
            'chunk_stats': [
                {
                    'chunk_id': r.get('chunk_id'),
                    'claims_extracted': r.get('total_claims', 0),
                    'processing_time': r.get('processing_time', 0),
                    'char_range': f"{r.get('chunk_start_char')}-{r.get('chunk_end_char')}"
                }
                for r in chunk_results
            ],
            'api_response': aggregated_api_response
        }

        logger.info(
            f"[MERGE] Final result: {total_claims} claims "
            f"({claims_with_refs} with refs, {claims_without_refs} without)"
        )
        logger.info(
            f"[MERGE] Aggregated token usage: "
            f"{total_input_tokens:,} input, {total_output_tokens:,} output, "
            f"{total_cache_read_tokens:,} cache read, {total_cache_creation_tokens:,} cache creation"
        )

        return merged


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
