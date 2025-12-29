#!/usr/bin/env python3
"""
Standalone table extractor with iterative extraction support.
Extracts complete tables from URLs with fallback strategies and citation tracking.
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

from shared.html_table_parser import HTMLTableParser
from the_clone.perplexity_search import PerplexitySearchClient

logger = logging.getLogger(__name__)


class TableExtractor:
    """
    Standalone table extractor with iteration support.

    Supports:
    - Direct HTML extraction
    - Iterative extraction for large tables
    - Search-based fallback (via the_clone)
    - Citation quality tracking
    """

    def __init__(self, ai_client, schema_validator=None):
        """
        Initialize table extractor.

        Args:
            ai_client: AI API client instance
            schema_validator: Optional schema validator for response validation
        """
        self.ai_client = ai_client
        self.schema_validator = schema_validator
        self.html_parser = HTMLTableParser(timeout=30)
        self.search_client = PerplexitySearchClient()

        logger.info("Initialized TableExtractor with Search API support")

    def _map_url_quality_to_confidence(self, url_quality: float) -> str:
        """
        Map URL quality score to confidence level.

        Args:
            url_quality: Quality score from background research (0.0-1.0)

        Returns:
            Confidence level: HIGH, MEDIUM, or LOW
        """
        if url_quality >= 0.85:
            return 'HIGH'
        elif url_quality >= 0.70:
            return 'MEDIUM'
        else:
            return 'LOW'

    async def extract_table(
        self,
        url: str,
        table_name: str,
        expected_columns: List[str],
        estimated_rows: int = None,
        url_quality: float = 0.85,
        max_iterations: int = 5,
        model: str = "gemini-2.0-flash",
        max_tokens: int = 8000,
        use_search_fallback: bool = True
    ) -> Dict[str, Any]:
        """
        Extract complete table from URL with iteration.

        Args:
            url: URL to extract from
            table_name: Name of the table
            expected_columns: List of expected column names
            estimated_rows: Estimated number of rows (optional)
            url_quality: Quality score from background research (0.0-1.0)
            max_iterations: Maximum extraction iterations
            model: AI model to use (default: gemini-2-flash)
            max_tokens: Maximum tokens per call
            use_search_fallback: Whether to use search-based fallback

        Returns:
            Dictionary with:
            {
                'success': bool,
                'url': str,
                'rows': List[Dict],
                'rows_extracted': int,
                'extraction_complete': bool,
                'iterations_used': int,
                'confidence': str,  # HIGH/MEDIUM/LOW
                'citations': List[Dict],
                'strategy_used': str,
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'url': url,
            'rows': [],
            'rows_extracted': 0,
            'extraction_complete': False,
            'iterations_used': 0,
            'confidence': self._map_url_quality_to_confidence(url_quality),
            'citations': [],
            'strategy_used': None,
            'error': None,
            'table_name': table_name
        }

        start_time = time.time()

        try:
            logger.info(f"Starting table extraction: {table_name} from {url}")
            logger.info(f"  URL quality: {url_quality:.2f}, Confidence: {result['confidence']}")

            # Strategy 1: Jina AI Reader (handles both static AND JS-rendered)
            jina_result = await self._try_jina_extraction(
                url, table_name, expected_columns, estimated_rows
            )

            if jina_result['success']:
                rows_count = len(jina_result['rows'])

                # Check completeness
                is_complete = True
                if estimated_rows and estimated_rows > 0:
                    completeness = rows_count / estimated_rows
                    is_complete = completeness >= 0.8
                    logger.info(f"  Jina extraction: {rows_count}/{estimated_rows} rows ({completeness*100:.0f}%)")
                else:
                    logger.info(f"  Jina extraction: {rows_count} rows")

                if is_complete or rows_count >= 20:  # Accept if complete OR got substantial data
                    result.update({
                        'success': True,
                        'rows': jina_result['rows'],
                        'rows_extracted': rows_count,
                        'extraction_complete': is_complete,
                        'iterations_used': 1,
                        'strategy_used': 'jina_reader',
                        'citations': self._build_citations(url, f"Jina AI Reader extraction (handles JS)")
                    })
                    logger.info(f"  [SUCCESS] Jina extraction: {rows_count} rows")
                    return result

            # Strategy 2: Search API → Gemini (deep content extraction)
            search_api_result = await self._try_search_api_extraction(
                url, table_name, expected_columns, estimated_rows, max_tokens
            )

            if search_api_result['success']:
                rows_count = len(search_api_result['rows'])
                logger.info(f"  Search API extraction: {rows_count} rows")

                # Accept if we got substantial data
                if rows_count >= 10:
                    result.update({
                        'success': True,
                        'rows': search_api_result['rows'],
                        'rows_extracted': rows_count,
                        'extraction_complete': search_api_result.get('extraction_complete', True),
                        'iterations_used': 1,
                        'strategy_used': 'search_api_gemini',
                        'citations': self._build_citations(url, f"Search API (8K tokens/page) + Gemini extraction")
                    })
                    logger.info(f"  [SUCCESS] Search API + Gemini: {rows_count} rows")
                    return result

            # Strategy 3: Direct HTML extraction (fallback)
            html_result = await self._try_html_extraction(
                url, table_name, expected_columns, estimated_rows, max_tokens
            )

            if html_result['success']:
                rows_count = len(html_result['rows'])

                # Check if we got most of the expected rows (80% threshold)
                is_complete = True
                if estimated_rows and estimated_rows > 0:
                    completeness = rows_count / estimated_rows
                    is_complete = completeness >= 0.8
                    logger.info(f"  HTML extraction: {rows_count}/{estimated_rows} rows ({completeness*100:.0f}%)")
                else:
                    logger.info(f"  HTML extraction: {rows_count} rows")

                if is_complete:
                    # Direct HTML extraction successful and complete
                    result.update({
                        'success': True,
                        'rows': html_result['rows'],
                        'rows_extracted': rows_count,
                        'extraction_complete': True,
                        'iterations_used': 1,
                        'strategy_used': 'html_direct',
                        'citations': self._build_citations(url, f"Direct HTML extraction from {url}")
                    })
                    logger.info(f"  [SUCCESS] HTML direct extraction: {rows_count} rows")
                    return result
                else:
                    # Partial success - try iteration
                    logger.info(f"  [PARTIAL] HTML extraction incomplete, trying iteration")
                    iteration_result = await self._extract_iteratively(
                        url, table_name, expected_columns, html_result['rows'],
                        estimated_rows, max_iterations, max_tokens
                    )

                    if iteration_result['success']:
                        result.update({
                            'success': True,
                            'rows': iteration_result['rows'],
                            'rows_extracted': len(iteration_result['rows']),
                            'extraction_complete': iteration_result['extraction_complete'],
                            'iterations_used': iteration_result['iterations_used'],
                            'strategy_used': 'iterative_html',
                            'citations': self._build_citations(url, f"Iterative extraction from {url}")
                        })
                        logger.info(
                            f"  [SUCCESS] Iterative extraction: {result['rows_extracted']} rows "
                            f"in {result['iterations_used']} iterations"
                        )
                        return result

            # Strategy 2: AI-based extraction with Gemini
            logger.info("  [FALLBACK] Trying AI-based extraction")
            ai_result = await self._try_ai_extraction(
                url, table_name, expected_columns, estimated_rows, model, max_tokens
            )

            if ai_result['success']:
                rows_count = len(ai_result['rows'])

                # If partial, try iteration
                is_complete = ai_result.get('extraction_complete', True)
                if not is_complete and rows_count > 0:
                    logger.info(f"  [PARTIAL] AI extraction incomplete, trying iteration")
                    iteration_result = await self._extract_iteratively(
                        url, table_name, expected_columns, ai_result['rows'],
                        estimated_rows, max_iterations, max_tokens
                    )

                    if iteration_result['success']:
                        result.update({
                            'success': True,
                            'rows': iteration_result['rows'],
                            'rows_extracted': len(iteration_result['rows']),
                            'extraction_complete': iteration_result['extraction_complete'],
                            'iterations_used': iteration_result['iterations_used'],
                            'strategy_used': 'iterative_ai',
                            'citations': self._build_citations(url, f"AI-based iterative extraction")
                        })
                        logger.info(f"  [SUCCESS] AI iterative: {result['rows_extracted']} rows")
                        return result

                # Single AI extraction worked
                result.update({
                    'success': True,
                    'rows': ai_result['rows'],
                    'rows_extracted': rows_count,
                    'extraction_complete': is_complete,
                    'iterations_used': 1,
                    'strategy_used': 'ai_extraction',
                    'citations': self._build_citations(url, f"AI extraction from {url}")
                })
                logger.info(f"  [SUCCESS] AI extraction: {rows_count} rows")
                return result

            # Strategy 3: Search-based fallback (the_clone findall)
            if use_search_fallback:
                logger.info("  [FALLBACK] Trying search-based extraction (the_clone findall)")
                search_result = await self._try_search_extraction(
                    url, table_name, expected_columns, estimated_rows, max_tokens
                )

                if search_result['success']:
                    result.update({
                        'success': True,
                        'rows': search_result['rows'],
                        'rows_extracted': len(search_result['rows']),
                        'extraction_complete': search_result.get('extraction_complete', False),
                        'iterations_used': 1,
                        'strategy_used': 'search_based',
                        'citations': self._build_citations(url, f"Search-based extraction")
                    })
                    logger.info(f"  [SUCCESS] Search-based: {result['rows_extracted']} rows")
                    return result

            # All strategies failed
            result['error'] = 'All extraction strategies failed'
            logger.warning(f"  [FAILED] All extraction strategies failed for {table_name}")

        except Exception as e:
            logger.error(f"Table extraction failed: {str(e)}", exc_info=True)
            result['error'] = str(e)

        result['processing_time'] = time.time() - start_time
        return result

    async def _try_search_api_extraction(
        self, url: str, table_name: str, expected_columns: List[str],
        estimated_rows: int, max_tokens: int
    ) -> Dict[str, Any]:
        """
        Try Search API → Gemini extraction (8K tokens/page + structured extraction).

        Returns:
            Dict with 'success', 'rows', 'extraction_complete', 'error'
        """
        result = {'success': False, 'rows': [], 'extraction_complete': False, 'error': None}

        try:
            # Extract domain
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.replace('www.', '')

            # Use Search API with high max_tokens_per_page for deep content
            logger.info(f"    Using Search API with max_tokens_per_page=8192 for {domain}")

            search_result = await self.search_client.search(
                query=f'site:{domain} {table_name}',
                max_results=10,  # Get multiple results
                max_tokens_per_page=8192,  # 5x more content than default!
                include_domains=[domain]  # Focus on this domain
            )

            search_results = search_result.get('results', [])
            if not search_results:
                result['error'] = 'No search results found'
                return result

            logger.info(f"    Search API returned {len(search_results)} results")

            # Combine snippets from top results
            combined_content = []
            for i, res in enumerate(search_results[:5], 1):  # Use top 5
                snippet = res.get('snippet', '')
                if snippet:
                    combined_content.append(f"[Source {i}: {res.get('title', 'Unknown')}]\n{snippet}\n")

            content_text = '\n'.join(combined_content)
            logger.info(f"    Combined content: {len(content_text)} chars from {len(combined_content)} sources")

            # Feed to Gemini for structured extraction
            columns_str = ', '.join(expected_columns)

            prompt = f"""Extract the table from the following search results content:

Table name: {table_name}
Expected columns: {columns_str}

Content from search results:
{content_text}

Extract ALL table rows you can find in this content. Return them in the specified schema format."""

            schema = {
                "type": "object",
                "required": ["rows", "extraction_complete", "rows_extracted"],
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": {"type": "string"}
                        }
                    },
                    "extraction_complete": {"type": "boolean"},
                    "rows_extracted": {"type": "number"}
                }
            }

            # Call Gemini 2.5 Flash (higher token limits than 2.0)
            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model="gemini-2.5-flash",
                max_tokens=max_tokens,
                use_cache=True,
                tool_name="search_api_gemini_extraction"
            )

            if 'response' not in api_response or 'error' in api_response:
                result['error'] = api_response.get('error', 'Gemini extraction failed')
                return result

            # Extract structured response
            raw_response = api_response.get('response', {})
            structured_response = self.ai_client.extract_structured_response(
                raw_response,
                tool_name="search_api_gemini_extraction"
            )

            rows = structured_response.get('rows', [])
            extraction_complete = structured_response.get('extraction_complete', False)

            result['success'] = len(rows) > 0
            result['rows'] = rows
            result['extraction_complete'] = extraction_complete

            logger.info(f"    Search API + Gemini: {len(rows)} rows extracted from {len(content_text)} chars")

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Search API + Gemini extraction error: {str(e)}")

        return result

    async def _try_jina_extraction(
        self, url: str, table_name: str, expected_columns: List[str],
        estimated_rows: int
    ) -> Dict[str, Any]:
        """
        Try Jina AI Reader extraction (handles JS-rendered content).

        Returns:
            Dict with 'success', 'rows', 'error'
        """
        result = {'success': False, 'rows': [], 'error': None}

        try:
            # Fetch via Jina
            jina_result = await self.html_parser.fetch_via_jina(url)

            if not jina_result['success']:
                result['error'] = jina_result.get('error', 'Jina fetch failed')
                return result

            # Parse markdown tables
            markdown = jina_result['markdown']
            parse_result = self.html_parser.parse_markdown_tables(markdown)

            if not parse_result['success']:
                result['error'] = parse_result.get('error', 'No markdown tables found')
                return result

            # Get the largest table
            tables = parse_result.get('tables', [])
            if not tables:
                result['error'] = 'No tables in Jina markdown'
                return result

            best_table = max(tables, key=lambda t: t['rows_count'])

            result['success'] = True
            result['rows'] = best_table['rows']
            result['headers'] = best_table['headers']

            logger.info(f"    Jina extraction: {len(result['rows'])} rows from markdown table")

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Jina extraction error: {str(e)}")

        return result

    async def _try_html_extraction(
        self, url: str, table_name: str, expected_columns: List[str],
        estimated_rows: int, max_tokens: int
    ) -> Dict[str, Any]:
        """
        Try direct HTML extraction.

        Returns:
            Dict with 'success', 'rows', 'error'
        """
        result = {'success': False, 'rows': [], 'error': None}

        try:
            # Fetch and parse HTML
            parse_result = await self.html_parser.fetch_and_parse(url, table_name)

            if not parse_result['success']:
                result['error'] = parse_result.get('error', 'HTML parsing failed')
                return result

            # Get the first/largest table
            tables = parse_result.get('tables', [])
            if not tables:
                result['error'] = 'No tables found in HTML'
                return result

            # Use the largest table (by row count)
            best_table = max(tables, key=lambda t: t['rows_count'])

            result['success'] = True
            result['rows'] = best_table['rows']
            result['headers'] = best_table['headers']

            logger.info(f"    HTML extraction: {len(result['rows'])} rows from table")

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"HTML extraction error: {str(e)}")

        return result

    async def _try_ai_extraction(
        self, url: str, table_name: str, expected_columns: List[str],
        estimated_rows: int, model: str, max_tokens: int
    ) -> Dict[str, Any]:
        """
        Try AI-based extraction using Gemini.

        Returns:
            Dict with 'success', 'rows', 'extraction_complete', 'error'
        """
        result = {'success': False, 'rows': [], 'extraction_complete': False, 'error': None}

        try:
            # Build schema for table extraction
            schema = {
                "type": "object",
                "required": ["rows", "extraction_complete", "rows_extracted"],
                "properties": {
                    "rows": {
                        "type": "array",
                        "description": "Array of extracted rows",
                        "items": {
                            "type": "object",
                            "description": "Single row with column names as keys",
                            "additionalProperties": {"type": "string"}
                        }
                    },
                    "extraction_complete": {
                        "type": "boolean",
                        "description": "Whether all rows were extracted"
                    },
                    "rows_extracted": {
                        "type": "number",
                        "description": "Number of rows extracted"
                    },
                    "extraction_notes": {
                        "type": "string",
                        "description": "Notes about extraction"
                    }
                }
            }

            # Build prompt
            columns_str = ', '.join(expected_columns)
            estimated_str = f"{estimated_rows} rows" if estimated_rows else "unknown count"

            prompt = f"""You have access to web search to retrieve content from URLs.

Search and extract the complete table from: {url}

Table name: {table_name}
Expected columns: {columns_str}
Estimated rows: {estimated_str}

Use your web search capability to access the page content and extract ALL rows from the table. If the table has more rows than you can extract in one response, set extraction_complete to false.

Return the data in JSON format with:
- rows: array of row objects (each row is an object with column names as keys)
- extraction_complete: boolean indicating if all rows were extracted
- rows_extracted: total count of rows extracted
- extraction_notes: any relevant notes about the extraction

Search the URL and extract the table rows now."""

            # Extract domain for focused search
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            if domain.startswith('www.'):
                domain = domain[4:]

            # Call AI API (models auto-switch to soft_schema if needed)
            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=True,
                include_domains=[domain],
                tool_name="table_extraction"
            )

            if 'response' not in api_response or 'error' in api_response:
                result['error'] = api_response.get('error', 'AI API call failed')
                return result

            # Extract structured response
            raw_response = api_response.get('response', {})

            try:
                structured_response = self.ai_client.extract_structured_response(
                    raw_response,
                    tool_name="table_extraction"
                )
            except Exception as e:
                result['error'] = f"Response extraction failed: {str(e)}"
                return result

            # Validate response
            rows = structured_response.get('rows', [])
            extraction_complete = structured_response.get('extraction_complete', False)
            rows_extracted = structured_response.get('rows_extracted', len(rows))

            result['success'] = len(rows) > 0
            result['rows'] = rows
            result['extraction_complete'] = extraction_complete
            result['rows_extracted'] = rows_extracted

            logger.info(f"    AI extraction: {len(rows)} rows, complete={extraction_complete}")

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"AI extraction error: {str(e)}")

        return result

    async def _extract_iteratively(
        self, url: str, table_name: str, expected_columns: List[str],
        initial_rows: List[Dict], estimated_rows: int, max_iterations: int,
        max_tokens: int
    ) -> Dict[str, Any]:
        """
        Extract table iteratively when initial extraction is incomplete.

        Args:
            url: URL to extract from
            table_name: Table name
            expected_columns: Expected columns
            initial_rows: Already-extracted rows (context)
            estimated_rows: Estimated total rows
            max_iterations: Maximum iterations
            max_tokens: Max tokens per call

        Returns:
            Dict with 'success', 'rows', 'extraction_complete', 'iterations_used'
        """
        result = {
            'success': False,
            'rows': initial_rows.copy(),
            'extraction_complete': False,
            'iterations_used': 1,  # Count initial extraction
            'error': None
        }

        try:
            iteration = 2  # Start from 2 (initial is 1)
            all_rows = initial_rows.copy()

            logger.info(f"    Starting iterative extraction (already have {len(all_rows)} rows)")

            while iteration <= max_iterations:
                # Check if we're close to target
                if estimated_rows and len(all_rows) >= estimated_rows * 0.95:
                    logger.info(f"    Iteration {iteration}: Near target ({len(all_rows)}/{estimated_rows})")
                    result['extraction_complete'] = True
                    break

                # Build continuation prompt
                columns_str = ', '.join(expected_columns)
                sample_rows = all_rows[-5:] if len(all_rows) >= 5 else all_rows
                sample_json = json.dumps(sample_rows, indent=2)

                prompt = f"""Continue extracting table data from: {url}

Table name: {table_name}
Expected columns: {columns_str}

Already extracted {len(all_rows)} rows. Last rows extracted:
{sample_json}

Extract the REMAINING rows that have NOT been captured yet.
Start from row {len(all_rows) + 1}.

Return only the NEW rows (not the ones already extracted)."""

                # Schema for continuation
                schema = {
                    "type": "object",
                    "required": ["rows", "extraction_complete"],
                    "properties": {
                        "rows": {
                            "type": "array",
                            "description": "NEW rows not yet extracted",
                            "items": {
                                "type": "object",
                                "additionalProperties": {"type": "string"}
                            }
                        },
                        "extraction_complete": {
                            "type": "boolean",
                            "description": "Whether all remaining rows were extracted"
                        }
                    }
                }

                # Extract domain
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.replace('www.', '')

                # Call AI for iteration (auto-switches to soft_schema if needed)
                api_response = await self.ai_client.call_structured_api(
                    prompt=prompt,
                    schema=schema,
                    model="gemini-2.0-flash",
                    max_tokens=max_tokens,
                    use_cache=False,  # Don't cache iterative calls
                    include_domains=[domain],
                    tool_name="table_extraction_continuation"
                )

                if 'response' not in api_response or 'error' in api_response:
                    logger.warning(f"    Iteration {iteration} failed: {api_response.get('error')}")
                    break

                # Extract response
                raw_response = api_response.get('response', {})
                structured_response = self.ai_client.extract_structured_response(
                    raw_response,
                    tool_name="table_extraction_continuation"
                )

                new_rows = structured_response.get('rows', [])
                extraction_complete = structured_response.get('extraction_complete', False)

                logger.info(f"    Iteration {iteration}: +{len(new_rows)} rows (total: {len(all_rows) + len(new_rows)})")

                # Append new rows
                all_rows.extend(new_rows)
                result['iterations_used'] = iteration

                # Check completion
                if extraction_complete or len(new_rows) == 0:
                    result['extraction_complete'] = True
                    logger.info(f"    Extraction complete at iteration {iteration}")
                    break

                iteration += 1

            # Success if we got more rows
            result['success'] = len(all_rows) > len(initial_rows)
            result['rows'] = all_rows

        except Exception as e:
            logger.error(f"Iterative extraction error: {str(e)}")
            result['error'] = str(e)

        return result

    async def _try_search_extraction(
        self, url: str, table_name: str, expected_columns: List[str],
        estimated_rows: int, max_tokens: int
    ) -> Dict[str, Any]:
        """
        Try the_clone extraction mode (8K tokens/page, parallel, Gemini synthesis).

        Returns:
            Dict with 'success', 'rows', 'extraction_complete', 'error'
        """
        result = {'success': False, 'rows': [], 'extraction_complete': False, 'error': None}

        try:
            # Build extraction prompt for the_clone
            columns_str = ', '.join(expected_columns)

            prompt = f"""Extract the complete table from: {url}

Table name: {table_name}
Expected columns: {columns_str}
Estimated rows: {estimated_rows or 'unknown'}

Extract ALL rows from this table with complete data."""

            # Schema for table extraction
            schema = {
                "type": "object",
                "required": ["rows", "rows_extracted", "extraction_complete"],
                "properties": {
                    "rows": {
                        "type": "array",
                        "description": "Extracted table rows",
                        "items": {
                            "type": "object",
                            "additionalProperties": {"type": "string"}
                        }
                    },
                    "rows_extracted": {
                        "type": "number",
                        "description": "Number of rows extracted"
                    },
                    "extraction_complete": {
                        "type": "boolean",
                        "description": "Whether all rows were captured"
                    }
                }
            }

            # Extract domain
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.replace('www.', '')

            # Call the_clone with extraction=True
            # This triggers: 8K tokens/page, parallel extraction, Gemini synthesis
            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model="the-clone",
                max_tokens=max_tokens,
                use_cache=True,
                include_domains=[domain],
                extraction=True,  # NEW: Triggers extraction strategy
                tool_name="clone_extraction"
            )

            if 'response' not in api_response or 'error' in api_response:
                result['error'] = api_response.get('error', 'Clone extraction failed')
                return result

            # Extract response
            raw_response = api_response.get('response', {})
            structured_response = self.ai_client.extract_structured_response(
                raw_response,
                tool_name="clone_extraction"
            )

            rows = structured_response.get('rows', [])
            extraction_complete = structured_response.get('extraction_complete', False)

            result['success'] = len(rows) > 0
            result['rows'] = rows
            result['extraction_complete'] = extraction_complete

            logger.info(f"    the_clone EXTRACTION mode: {len(rows)} rows (8K tokens/page, Gemini)")

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Clone extraction error: {str(e)}")

        return result

    def _build_citations(self, url: str, description: str) -> List[Dict[str, str]]:
        """
        Build citation list for tracking sources.

        Args:
            url: Source URL
            description: Description of extraction method

        Returns:
            List of citation dictionaries
        """
        return [
            {
                'url': url,
                'snippet': description,
                'extraction_method': description
            }
        ]
