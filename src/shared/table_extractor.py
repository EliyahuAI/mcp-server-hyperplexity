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

    async def extract_simple_table(
        self,
        description: str,
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Simple table extraction - no schema required.
        Returns raw markdown table for downstream processing.

        Args:
            description: Description of what table to find (e.g., "Fortune 500 companies 2024")
            url: Optional URL to extract from. If not provided, will search.

        Returns:
            {
                'success': bool,
                'url': str,
                'table_name': str,
                'markdown_table': str,  # Raw markdown table
                'rows_count': int,
                'columns_found': List[str],
                'extraction_method': str,
                'metadata': Dict
            }
        """
        start_time = time.time()
        result = {
            'success': False,
            'url': url,  # Primary URL
            'source_urls': [],  # All URLs that contributed data
            'table_name': description,
            'markdown_table': None,
            'rows_count': 0,
            'columns_found': [],
            'extraction_method': None,
            'error': None
        }

        cost_tracking = {
            'total_cost': 0.0,
            'cost_by_provider': {},
            'strategies_attempted': []
        }

        try:
            # If URL provided, try direct extraction
            if url:
                logger.info(f"Simple extraction from URL: {url}")

                # Strategy 1: Jina (best for JS-rendered content)
                jina_start = time.time()
                jina_result = await self.html_parser.fetch_via_jina(url)
                jina_time = time.time() - jina_start

                cost_tracking['strategies_attempted'].append({
                    'name': 'jina_reader',
                    'success': jina_result['success'],
                    'cost': 0.0,
                    'time': jina_time
                })

                if jina_result['success']:
                    markdown = jina_result['markdown']
                    parse_result = self.html_parser.parse_markdown_tables(markdown)

                    if parse_result['success'] and parse_result.get('tables'):
                        # Get largest table
                        tables = parse_result['tables']
                        best_table = max(tables, key=lambda t: t['rows_count'])

                        # Convert to markdown table format
                        markdown_table = self._convert_to_markdown(
                            best_table['headers'],
                            best_table['rows']
                        )

                        result.update({
                            'success': True,
                            'source_urls': [url],  # Single source
                            'markdown_table': markdown_table,
                            'rows_count': best_table['rows_count'],
                            'columns_found': best_table['headers'],
                            'extraction_method': 'jina_reader'
                        })

                        logger.info(f"[SUCCESS] Jina: {best_table['rows_count']} rows, {len(best_table['headers'])} columns")
                        result['metadata'] = self._build_simple_metadata(cost_tracking, time.time() - start_time)
                        return result

                # Strategy 2: HTML Direct
                html_start = time.time()
                html_result = await self.html_parser.fetch_and_parse(url, description)
                html_time = time.time() - html_start

                cost_tracking['strategies_attempted'].append({
                    'name': 'html_direct',
                    'success': html_result['success'],
                    'cost': 0.0,
                    'time': html_time
                })

                if html_result['success'] and html_result.get('tables'):
                    tables = html_result['tables']
                    best_table = max(tables, key=lambda t: t['rows_count'])

                    markdown_table = self._convert_to_markdown(
                        best_table['headers'],
                        best_table['rows']
                    )

                    result.update({
                        'success': True,
                        'source_urls': [url],  # Single source
                        'markdown_table': markdown_table,
                        'rows_count': best_table['rows_count'],
                        'columns_found': best_table['headers'],
                        'extraction_method': 'html_direct'
                    })

                    logger.info(f"[SUCCESS] HTML: {best_table['rows_count']} rows, {len(best_table['headers'])} columns")
                    result['metadata'] = self._build_simple_metadata(cost_tracking, time.time() - start_time)
                    return result

            # Strategy 3: Search API → Parallel Gemini (schema-free)
            if not url or not result['success']:
                logger.info(f"Using Search API → Parallel Gemini (no schema) for: {description}")

                # Extract domain if URL provided
                domain = None
                if url:
                    parsed_url = urlparse(url)
                    domain = parsed_url.netloc.replace('www.', '')

                search_start = time.time()
                search_result = await self.search_client.search(
                    query=f'site:{domain} {description}' if domain else description,
                    max_results=10,  # Get 10 sources for Gemini to select from
                    max_tokens_per_page=8192,
                    include_domains=[domain] if domain else None
                )
                search_time = time.time() - search_start

                # Track search cost
                search_cost = 0.005
                cost_tracking['total_cost'] += search_cost
                cost_tracking['cost_by_provider']['perplexity'] = {'cost': search_cost, 'calls': 1}
                cost_tracking['strategies_attempted'].append({
                    'name': 'search_api',
                    'success': len(search_result.get('results', [])) > 0,
                    'cost': search_cost,
                    'time': search_time
                })

                search_results = search_result.get('results', [])
                if search_results:
                    logger.info(f"Search API returned {len(search_results)} results")

                    # Update URL from first result if not provided
                    if not url:
                        result['url'] = search_results[0].get('url')

                    # SINGLE GEMINI CALL: Analyze all sources and select best ones
                    # Build markdown with all sources
                    sources_markdown = []
                    source_list = []  # Keep ordered list of sources

                    for i, res in enumerate(search_results[:10], 1):  # Process up to 10 results
                        snippet = res.get('snippet', '')
                        source_url = res.get('url', '')

                        if len(snippet) < 100:
                            continue

                        source_list.append({'index': i, 'url': source_url, 'snippet': snippet})
                        sources_markdown.append(f"# Source {i}\nURL: {source_url}\n\n{snippet}")

                    # Combine all sources
                    all_sources_text = "\n\n---\n\n".join(sources_markdown)

                    # Ask Gemini to select best sources with TABLE data
                    selection_prompt = f"""You are analyzing sources to find TABLE data about: {description}

Below are {len(source_list)} sources with their content.

GOAL: Select which sources contain ACTUAL TABLE DATA (rankings, lists, structured data) to get the highest quality information while limiting redundancy.

{all_sources_text}

Return a list of source numbers (1-{len(source_list)}) to include. Select sources that:
- Contain ACTUAL TABLES or LISTS (not just articles about the topic)
- Have the most complete/detailed tabular data
- Minimize redundancy (don't select duplicate/similar sources)
- Maximize coverage of different table data

Only select sources with real table/list data. Skip articles that just discuss the topic without tables.

Example: [1, 3, 4] means include sources 1, 3, and 4."""

                    schema = {
                        "type": "object",
                        "required": ["selected_sources"],
                        "properties": {
                            "selected_sources": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "List of source numbers to include (1-based)"
                            }
                        }
                    }

                    logger.info(f"Asking Gemini to select best sources from {len(source_list)} options")

                    # Single Gemini call to select sources
                    check_start = time.time()
                    selection_response = await self.ai_client.call_structured_api(
                        prompt=selection_prompt,
                        schema=schema,
                        model="gemini-2.0-flash",
                        max_tokens=500,  # Just need list of integers
                        use_cache=True,
                        tool_name="source_selection"
                    )
                    check_time = time.time() - check_start

                    # Extract selected sources
                    gemini_cost = 0.0
                    gemini_calls = 1
                    text_sections = []
                    successful_source_urls = []

                    if 'response' in selection_response and 'error' not in selection_response:
                        try:
                            # Extract cost
                            cost_info = self._extract_cost_from_response(selection_response)
                            gemini_cost = cost_info['cost']

                            # Get selected source numbers
                            raw_response = selection_response.get('response', {})
                            structured = self.ai_client.extract_structured_response(
                                raw_response,
                                tool_name="source_selection"
                            )

                            selected_indices = structured.get('selected_sources', [])
                            logger.info(f"Gemini selected sources: {selected_indices}")

                            # Collect selected sources
                            for source in source_list:
                                if source['index'] in selected_indices:
                                    source_url = source['url']
                                    snippet = source['snippet']

                                    if source_url not in successful_source_urls:
                                        successful_source_urls.append(source_url)

                                    # Add raw snippet with URL header
                                    text_sections.append(f"# Source: {source_url}\n\n{snippet}")

                        except Exception as e:
                            logger.warning(f"Source selection error: {str(e)}")
                            # Fallback: include all sources if selection fails
                            for source in source_list:
                                successful_source_urls.append(source['url'])
                                text_sections.append(f"# Source: {source['url']}\n\n{source['snippet']}")

                    # Track Gemini costs
                    cost_tracking['total_cost'] += gemini_cost
                    if gemini_calls > 0:
                        cost_tracking['cost_by_provider']['gemini'] = {
                            'cost': gemini_cost,
                            'calls': gemini_calls
                        }

                    cost_tracking['strategies_attempted'].append({
                        'name': 'source_selection_gemini',
                        'success': len(text_sections) > 0,
                        'cost': gemini_cost,
                        'time': check_time
                    })

                    if text_sections:
                        # Concatenate selected source texts with URL headers
                        combined_text = "\n\n---\n\n".join(text_sections)

                        result.update({
                            'success': True,
                            'source_urls': successful_source_urls,  # URLs of selected sources
                            'markdown_table': combined_text,  # Raw text from selected sources
                            'rows_count': len(text_sections),  # Count of selected sources
                            'columns_found': [],  # Unknown - column definition will determine
                            'extraction_method': 'search_api_source_selection'
                        })

                        logger.info(
                            f"[SUCCESS] Search+Gemini: Selected {len(text_sections)}/{len(source_list)} sources "
                            f"(deduplicated by Gemini)"
                        )
                        result['metadata'] = self._build_simple_metadata(cost_tracking, time.time() - start_time)
                        return result

            # All strategies failed
            result['error'] = 'Could not extract table'
            result['metadata'] = self._build_simple_metadata(cost_tracking, time.time() - start_time)

        except Exception as e:
            logger.error(f"Simple table extraction error: {str(e)}")
            result['error'] = str(e)
            result['metadata'] = self._build_simple_metadata(cost_tracking, time.time() - start_time)

        return result

    def _convert_to_markdown(self, headers: List[str], rows: List[Dict]) -> str:
        """Convert headers and rows to markdown table format."""
        if not headers or not rows:
            return ""

        # Build markdown table
        lines = []

        # Header row
        lines.append("| " + " | ".join(headers) + " |")

        # Separator row
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # Data rows
        for row in rows:
            row_values = [str(row.get(col, "")) for col in headers]
            lines.append("| " + " | ".join(row_values) + " |")

        return "\n".join(lines)

    def _build_simple_metadata(self, cost_tracking: Dict, total_time: float) -> Dict:
        """Build simplified metadata for schema-free extraction."""
        return {
            'total_cost': round(cost_tracking['total_cost'], 4),
            'processing_time': round(total_time, 2),
            'cost_by_provider': cost_tracking['cost_by_provider'],
            'strategies_attempted': cost_tracking['strategies_attempted']
        }

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

        # Initialize cost tracking
        total_cost = 0.0
        cost_by_provider = {}
        strategies_attempted = []

        try:
            logger.info(f"Starting table extraction: {table_name} from {url}")
            logger.info(f"  URL quality: {url_quality:.2f}, Confidence: {result['confidence']}")

            # Strategy 1: Jina AI Reader (handles both static AND JS-rendered)
            jina_result = await self._try_jina_extraction(
                url, table_name, expected_columns, estimated_rows
            )

            # Track Jina strategy attempt
            jina_metadata = jina_result.get('metadata', {})
            strategies_attempted.append({
                'name': 'jina_reader',
                'success': jina_result['success'],
                'cost': jina_metadata.get('cost', 0.0),
                'time': jina_metadata.get('processing_time', 0.0),
                'error': jina_result.get('error')
            })
            # Jina is free, but track provider anyway
            total_cost += jina_metadata.get('cost', 0.0)

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
                    total_time = time.time() - start_time
                    result.update({
                        'success': True,
                        'rows': jina_result['rows'],
                        'rows_extracted': rows_count,
                        'extraction_complete': is_complete,
                        'iterations_used': 1,
                        'strategy_used': 'jina_reader',
                        'citations': self._build_citations(url, f"Jina AI Reader extraction (handles JS)"),
                        'metadata': self._build_metadata(
                            strategies_attempted, total_cost, cost_by_provider,
                            total_time=total_time
                        )
                    })
                    logger.info(f"  [SUCCESS] Jina extraction: {rows_count} rows")
                    return result

            # Strategy 2: Search API → Gemini (deep content extraction)
            search_api_result = await self._try_search_api_extraction(
                url, table_name, expected_columns, estimated_rows, max_tokens
            )

            # Track Search API strategy attempt
            search_metadata = search_api_result.get('metadata', {})
            strategies_attempted.append({
                'name': 'search_api_gemini',
                'success': search_api_result['success'],
                'cost': search_metadata.get('cost', 0.0),
                'time': search_metadata.get('processing_time', 0.0),
                'error': search_api_result.get('error')
            })
            total_cost += search_metadata.get('cost', 0.0)

            # Accumulate costs by provider from Search API
            search_cost_by_provider = search_metadata.get('cost_by_provider', {})
            for provider, info in search_cost_by_provider.items():
                if provider not in cost_by_provider:
                    cost_by_provider[provider] = {'cost': 0.0, 'calls': 0}
                cost_by_provider[provider]['cost'] += info.get('cost', 0.0)
                cost_by_provider[provider]['calls'] += info.get('calls', 0)

            if search_api_result['success']:
                rows_count = len(search_api_result['rows'])
                logger.info(f"  Search API extraction: {rows_count} rows")

                # Accept if we got substantial data
                if rows_count >= 10:
                    total_time = time.time() - start_time
                    result.update({
                        'success': True,
                        'rows': search_api_result['rows'],
                        'rows_extracted': rows_count,
                        'extraction_complete': search_api_result.get('extraction_complete', True),
                        'iterations_used': 1,
                        'strategy_used': 'search_api_gemini',
                        'citations': self._build_citations(url, f"Search API (8K tokens/page) + Gemini extraction"),
                        'metadata': self._build_metadata(
                            strategies_attempted, total_cost, cost_by_provider,
                            extraction_details=search_metadata.get('extraction_details'),
                            performance=search_metadata.get('performance'),
                            total_time=total_time
                        )
                    })
                    logger.info(f"  [SUCCESS] Search API + Gemini: {rows_count} rows")
                    return result

            # Strategy 3: Direct HTML extraction (fallback)
            html_result = await self._try_html_extraction(
                url, table_name, expected_columns, estimated_rows, max_tokens
            )

            # Track HTML strategy attempt
            html_metadata = html_result.get('metadata', {})
            strategies_attempted.append({
                'name': 'html_direct',
                'success': html_result['success'],
                'cost': html_metadata.get('cost', 0.0),
                'time': html_metadata.get('processing_time', 0.0),
                'error': html_result.get('error')
            })
            total_cost += html_metadata.get('cost', 0.0)

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
                    total_time = time.time() - start_time
                    result.update({
                        'success': True,
                        'rows': html_result['rows'],
                        'rows_extracted': rows_count,
                        'extraction_complete': True,
                        'iterations_used': 1,
                        'strategy_used': 'html_direct',
                        'citations': self._build_citations(url, f"Direct HTML extraction from {url}"),
                        'metadata': self._build_metadata(
                            strategies_attempted, total_cost, cost_by_provider,
                            total_time=total_time
                        )
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

                    # Track iteration costs
                    iteration_metadata = iteration_result.get('metadata', {})
                    strategies_attempted.append({
                        'name': 'iterative_html',
                        'success': iteration_result['success'],
                        'cost': iteration_metadata.get('cost', 0.0),
                        'time': iteration_metadata.get('processing_time', 0.0),
                        'iterations': iteration_result.get('iterations_used', 0),
                        'error': iteration_result.get('error')
                    })
                    total_cost += iteration_metadata.get('cost', 0.0)
                    # Accumulate Gemini costs from iteration
                    if iteration_metadata.get('cost', 0.0) > 0:
                        self._accumulate_costs(cost_by_provider, 'gemini', iteration_metadata.get('cost', 0.0))

                    if iteration_result['success']:
                        total_time = time.time() - start_time
                        result.update({
                            'success': True,
                            'rows': iteration_result['rows'],
                            'rows_extracted': len(iteration_result['rows']),
                            'extraction_complete': iteration_result['extraction_complete'],
                            'iterations_used': iteration_result['iterations_used'],
                            'strategy_used': 'iterative_html',
                            'citations': self._build_citations(url, f"Iterative extraction from {url}"),
                            'metadata': self._build_metadata(
                                strategies_attempted, total_cost, cost_by_provider,
                                total_time=total_time
                            )
                        })
                        logger.info(
                            f"  [SUCCESS] Iterative extraction: {result['rows_extracted']} rows "
                            f"in {result['iterations_used']} iterations"
                        )
                        return result

            # Strategy 4: AI-based extraction with Gemini
            logger.info("  [FALLBACK] Trying AI-based extraction")
            ai_result = await self._try_ai_extraction(
                url, table_name, expected_columns, estimated_rows, model, max_tokens
            )

            # Track AI extraction attempt
            ai_metadata = ai_result.get('metadata', {})
            strategies_attempted.append({
                'name': 'ai_extraction',
                'success': ai_result['success'],
                'cost': ai_metadata.get('cost', 0.0),
                'time': ai_metadata.get('processing_time', 0.0),
                'error': ai_result.get('error')
            })
            total_cost += ai_metadata.get('cost', 0.0)
            # Accumulate costs by provider
            if ai_metadata.get('cost', 0.0) > 0:
                provider = ai_metadata.get('provider', 'gemini')
                self._accumulate_costs(cost_by_provider, provider, ai_metadata.get('cost', 0.0))

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

                    # Track iteration costs
                    iteration_metadata = iteration_result.get('metadata', {})
                    strategies_attempted.append({
                        'name': 'iterative_ai',
                        'success': iteration_result['success'],
                        'cost': iteration_metadata.get('cost', 0.0),
                        'time': iteration_metadata.get('processing_time', 0.0),
                        'iterations': iteration_result.get('iterations_used', 0),
                        'error': iteration_result.get('error')
                    })
                    total_cost += iteration_metadata.get('cost', 0.0)
                    if iteration_metadata.get('cost', 0.0) > 0:
                        self._accumulate_costs(cost_by_provider, 'gemini', iteration_metadata.get('cost', 0.0))

                    if iteration_result['success']:
                        total_time = time.time() - start_time
                        result.update({
                            'success': True,
                            'rows': iteration_result['rows'],
                            'rows_extracted': len(iteration_result['rows']),
                            'extraction_complete': iteration_result['extraction_complete'],
                            'iterations_used': iteration_result['iterations_used'],
                            'strategy_used': 'iterative_ai',
                            'citations': self._build_citations(url, f"AI-based iterative extraction"),
                            'metadata': self._build_metadata(
                                strategies_attempted, total_cost, cost_by_provider,
                                total_time=total_time
                            )
                        })
                        logger.info(f"  [SUCCESS] AI iterative: {result['rows_extracted']} rows")
                        return result

                # Single AI extraction worked
                total_time = time.time() - start_time
                result.update({
                    'success': True,
                    'rows': ai_result['rows'],
                    'rows_extracted': rows_count,
                    'extraction_complete': is_complete,
                    'iterations_used': 1,
                    'strategy_used': 'ai_extraction',
                    'citations': self._build_citations(url, f"AI extraction from {url}"),
                    'metadata': self._build_metadata(
                        strategies_attempted, total_cost, cost_by_provider,
                        total_time=total_time
                    )
                })
                logger.info(f"  [SUCCESS] AI extraction: {rows_count} rows")
                return result

            # Strategy 5: Search-based fallback (the_clone findall)
            if use_search_fallback:
                logger.info("  [FALLBACK] Trying search-based extraction (the_clone findall)")
                search_result = await self._try_search_extraction(
                    url, table_name, expected_columns, estimated_rows, max_tokens
                )

                # Track search extraction attempt
                search_metadata = search_result.get('metadata', {})
                strategies_attempted.append({
                    'name': 'search_based',
                    'success': search_result['success'],
                    'cost': search_metadata.get('cost', 0.0),
                    'time': search_metadata.get('processing_time', 0.0),
                    'error': search_result.get('error')
                })
                total_cost += search_metadata.get('cost', 0.0)
                if search_metadata.get('cost', 0.0) > 0:
                    # the_clone may use multiple providers
                    provider = search_metadata.get('provider', 'the-clone')
                    self._accumulate_costs(cost_by_provider, provider, search_metadata.get('cost', 0.0))

                if search_result['success']:
                    total_time = time.time() - start_time
                    result.update({
                        'success': True,
                        'rows': search_result['rows'],
                        'rows_extracted': len(search_result['rows']),
                        'extraction_complete': search_result.get('extraction_complete', False),
                        'iterations_used': 1,
                        'strategy_used': 'search_based',
                        'citations': self._build_citations(url, f"Search-based extraction"),
                        'metadata': self._build_metadata(
                            strategies_attempted, total_cost, cost_by_provider,
                            total_time=total_time
                        )
                    })
                    logger.info(f"  [SUCCESS] Search-based: {result['rows_extracted']} rows")
                    return result

            # All strategies failed
            total_time = time.time() - start_time
            result['error'] = 'All extraction strategies failed'
            result['metadata'] = self._build_metadata(
                strategies_attempted, total_cost, cost_by_provider,
                total_time=total_time
            )
            logger.warning(f"  [FAILED] All extraction strategies failed for {table_name}")

        except Exception as e:
            logger.error(f"Table extraction failed: {str(e)}", exc_info=True)
            result['error'] = str(e)
            total_time = time.time() - start_time
            result['metadata'] = self._build_metadata(
                strategies_attempted, total_cost, cost_by_provider,
                total_time=total_time
            )

        result['processing_time'] = time.time() - start_time
        return result

    async def _try_search_api_extraction(
        self, url: str, table_name: str, expected_columns: List[str],
        estimated_rows: int, max_tokens: int
    ) -> Dict[str, Any]:
        """
        Try Search API → Gemini extraction (8K tokens/page + structured extraction).

        Returns:
            Dict with 'success', 'rows', 'extraction_complete', 'error', 'metadata'
        """
        start_time = time.time()
        result = {
            'success': False,
            'rows': [],
            'extraction_complete': False,
            'error': None,
            'metadata': {
                'cost': 0.0,
                'processing_time': 0.0,
                'cost_by_provider': {},
                'extraction_details': {
                    'search_api_calls': 0,
                    'search_results_found': 0,
                    'sources_processed': 0,
                    'parallel_gemini_calls': 0,
                    'rows_before_dedup': 0,
                    'rows_after_dedup': 0,
                    'duplicates_removed': 0
                },
                'performance': {
                    'time_by_stage': {},
                    'tokens_by_provider': {}
                }
            }
        }

        try:
            # Extract domain
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.replace('www.', '')

            # Use Search API with high max_tokens_per_page for deep content
            logger.info(f"    Using Search API with max_tokens_per_page=8192 for {domain}")

            search_start = time.time()
            search_result = await self.search_client.search(
                query=f'site:{domain} {table_name}',
                max_results=5,  # Get top 5 most relevant results
                max_tokens_per_page=8192,  # 5x more content than default!
                include_domains=[domain]  # Focus on this domain
            )
            result['metadata']['performance']['time_by_stage']['search_api'] = time.time() - search_start

            # Track Search API cost (Perplexity)
            result['metadata']['extraction_details']['search_api_calls'] = 1
            # Perplexity Search API typically costs ~$0.005 per request
            search_cost = 0.005
            result['metadata']['cost'] += search_cost
            if 'perplexity' not in result['metadata']['cost_by_provider']:
                result['metadata']['cost_by_provider']['perplexity'] = {'cost': 0.0, 'calls': 0}
            result['metadata']['cost_by_provider']['perplexity']['cost'] += search_cost
            result['metadata']['cost_by_provider']['perplexity']['calls'] += 1

            search_results = search_result.get('results', [])
            if not search_results:
                result['error'] = 'No search results found'
                result['metadata']['processing_time'] = time.time() - start_time
                return result

            result['metadata']['extraction_details']['search_results_found'] = len(search_results)
            logger.info(f"    Search API returned {len(search_results)} results")

            # PARALLEL APPROACH: Extract from each source separately, then merge
            columns_str = ', '.join(expected_columns)

            schema = {
                "type": "object",
                "required": ["rows"],
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": {"type": "string"}
                        }
                    }
                }
            }

            # Create parallel extraction tasks (one per source)
            extraction_tasks = []
            for i, res in enumerate(search_results[:5], 1):  # Process top 5 results
                snippet = res.get('snippet', '')
                if not snippet or len(snippet) < 100:  # Skip tiny snippets
                    continue

                prompt = f"""Extract table rows from this content:

Table: {table_name}
Columns: {columns_str}

Source content:
{snippet}

Extract ALL complete rows you can find."""

                task = self.ai_client.call_structured_api(
                    prompt=prompt,
                    schema=schema,
                    model=["gemini-2.0-flash", "gemini-2.5-flash"],  # Try both Gemini models
                    max_tokens=8000,
                    use_cache=True,
                    tool_name=f"parallel_extraction_{i}"
                )
                extraction_tasks.append(task)

            logger.info(f"    Running {len(extraction_tasks)} parallel Gemini extractions")
            result['metadata']['extraction_details']['parallel_gemini_calls'] = len(extraction_tasks)

            # Execute all extractions in parallel
            import asyncio as aio
            extraction_start = time.time()
            extraction_responses = await aio.gather(*extraction_tasks, return_exceptions=True)
            result['metadata']['performance']['time_by_stage']['parallel_extraction'] = time.time() - extraction_start

            # Merge results and deduplicate
            all_rows = []
            seen_rows = set()  # For deduplication
            total_input_tokens = 0
            total_output_tokens = 0

            dedup_start = time.time()
            for i, response in enumerate(extraction_responses, 1):
                if isinstance(response, Exception):
                    logger.warning(f"    Source {i} extraction failed: {str(response)[:100]}")
                    continue

                if 'response' not in response or 'error' in response:
                    continue

                try:
                    # Extract cost from this Gemini call
                    cost_info = self._extract_cost_from_response(response)
                    result['metadata']['cost'] += cost_info['cost']

                    # Track Gemini costs
                    if 'gemini' not in result['metadata']['cost_by_provider']:
                        result['metadata']['cost_by_provider']['gemini'] = {'cost': 0.0, 'calls': 0}
                    result['metadata']['cost_by_provider']['gemini']['cost'] += cost_info['cost']
                    result['metadata']['cost_by_provider']['gemini']['calls'] += 1

                    # Track tokens
                    tokens = cost_info.get('tokens', {})
                    total_input_tokens += tokens.get('input', 0)
                    total_output_tokens += tokens.get('output', 0)

                    raw_response = response.get('response', {})
                    structured = self.ai_client.extract_structured_response(
                        raw_response,
                        tool_name=f"parallel_extraction_{i}"
                    )

                    source_rows = structured.get('rows', [])
                    result['metadata']['extraction_details']['rows_before_dedup'] += len(source_rows)
                    result['metadata']['extraction_details']['sources_processed'] += 1

                    # Deduplicate based on row content
                    for row in source_rows:
                        row_key = json.dumps(row, sort_keys=True)
                        if row_key not in seen_rows:
                            seen_rows.add(row_key)
                            all_rows.append(row)

                    logger.info(f"    Source {i}: +{len(source_rows)} rows ({len(all_rows)} total after dedup)")

                except Exception as e:
                    logger.warning(f"    Source {i} extraction error: {str(e)[:100]}")

            result['metadata']['performance']['time_by_stage']['deduplication'] = time.time() - dedup_start
            result['metadata']['extraction_details']['rows_after_dedup'] = len(all_rows)
            result['metadata']['extraction_details']['duplicates_removed'] = (
                result['metadata']['extraction_details']['rows_before_dedup'] - len(all_rows)
            )

            # Track token usage
            if 'gemini' not in result['metadata']['performance']['tokens_by_provider']:
                result['metadata']['performance']['tokens_by_provider']['gemini'] = {}
            result['metadata']['performance']['tokens_by_provider']['gemini'] = {
                'input': total_input_tokens,
                'output': total_output_tokens
            }

            result['success'] = len(all_rows) > 0
            result['rows'] = all_rows
            result['extraction_complete'] = len(all_rows) >= (estimated_rows * 0.8 if estimated_rows else 20)
            result['metadata']['processing_time'] = time.time() - start_time

            logger.info(f"    Search API + Gemini 2.0 (parallel): {len(all_rows)} unique rows from {len(extraction_tasks)} sources")

        except Exception as e:
            result['error'] = str(e)
            result['metadata']['processing_time'] = time.time() - start_time
            logger.error(f"Search API + Gemini extraction error: {str(e)}")

        return result

    async def _try_jina_extraction(
        self, url: str, table_name: str, expected_columns: List[str],
        estimated_rows: int
    ) -> Dict[str, Any]:
        """
        Try Jina AI Reader extraction (handles JS-rendered content).

        Returns:
            Dict with 'success', 'rows', 'error', 'metadata'
        """
        start_time = time.time()
        result = {
            'success': False,
            'rows': [],
            'error': None,
            'metadata': {
                'cost': 0.0,  # Jina is free
                'processing_time': 0.0,
                'api_calls': 0,
                'provider': 'jina'
            }
        }

        try:
            # Fetch via Jina
            jina_result = await self.html_parser.fetch_via_jina(url)

            if not jina_result['success']:
                result['error'] = jina_result.get('error', 'Jina fetch failed')
                result['metadata']['processing_time'] = time.time() - start_time
                return result

            # Parse markdown tables
            markdown = jina_result['markdown']
            parse_result = self.html_parser.parse_markdown_tables(markdown)

            if not parse_result['success']:
                result['error'] = parse_result.get('error', 'No markdown tables found')
                result['metadata']['processing_time'] = time.time() - start_time
                return result

            # Get the largest table
            tables = parse_result.get('tables', [])
            if not tables:
                result['error'] = 'No tables in Jina markdown'
                result['metadata']['processing_time'] = time.time() - start_time
                return result

            best_table = max(tables, key=lambda t: t['rows_count'])

            result['success'] = True
            result['rows'] = best_table['rows']
            result['headers'] = best_table['headers']
            result['metadata']['api_calls'] = 1
            result['metadata']['processing_time'] = time.time() - start_time

            logger.info(f"    Jina extraction: {len(result['rows'])} rows from markdown table")

        except Exception as e:
            result['error'] = str(e)
            result['metadata']['processing_time'] = time.time() - start_time
            logger.error(f"Jina extraction error: {str(e)}")

        return result

    async def _try_html_extraction(
        self, url: str, table_name: str, expected_columns: List[str],
        estimated_rows: int, max_tokens: int
    ) -> Dict[str, Any]:
        """
        Try direct HTML extraction.

        Returns:
            Dict with 'success', 'rows', 'error', 'metadata'
        """
        start_time = time.time()
        result = {
            'success': False,
            'rows': [],
            'error': None,
            'metadata': {
                'cost': 0.0,  # HTML parsing is free
                'processing_time': 0.0,
                'api_calls': 0,
                'provider': 'html'
            }
        }

        try:
            # Fetch and parse HTML
            parse_result = await self.html_parser.fetch_and_parse(url, table_name)

            if not parse_result['success']:
                result['error'] = parse_result.get('error', 'HTML parsing failed')
                result['metadata']['processing_time'] = time.time() - start_time
                return result

            # Get the first/largest table
            tables = parse_result.get('tables', [])
            if not tables:
                result['error'] = 'No tables found in HTML'
                result['metadata']['processing_time'] = time.time() - start_time
                return result

            # Use the largest table (by row count)
            best_table = max(tables, key=lambda t: t['rows_count'])

            result['success'] = True
            result['rows'] = best_table['rows']
            result['headers'] = best_table['headers']
            result['metadata']['processing_time'] = time.time() - start_time

            logger.info(f"    HTML extraction: {len(result['rows'])} rows from table")

        except Exception as e:
            result['error'] = str(e)
            result['metadata']['processing_time'] = time.time() - start_time
            logger.error(f"HTML extraction error: {str(e)}")

        return result

    async def _try_ai_extraction(
        self, url: str, table_name: str, expected_columns: List[str],
        estimated_rows: int, model: str, max_tokens: int
    ) -> Dict[str, Any]:
        """
        Try AI-based extraction using Gemini.

        Returns:
            Dict with 'success', 'rows', 'extraction_complete', 'error', 'metadata'
        """
        start_time = time.time()
        result = {
            'success': False,
            'rows': [],
            'extraction_complete': False,
            'error': None,
            'metadata': {
                'cost': 0.0,
                'processing_time': 0.0,
                'api_calls': 0,
                'provider': 'gemini'
            }
        }

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

            # Track API costs
            cost_info = self._extract_cost_from_response(api_response)
            result['metadata']['cost'] = cost_info['cost']
            result['metadata']['api_calls'] = 1
            result['metadata']['provider'] = cost_info['provider']

            if 'response' not in api_response or 'error' in api_response:
                result['error'] = api_response.get('error', 'AI API call failed')
                result['metadata']['processing_time'] = time.time() - start_time
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
                result['metadata']['processing_time'] = time.time() - start_time
                return result

            # Validate response
            rows = structured_response.get('rows', [])
            extraction_complete = structured_response.get('extraction_complete', False)
            rows_extracted = structured_response.get('rows_extracted', len(rows))

            result['success'] = len(rows) > 0
            result['rows'] = rows
            result['extraction_complete'] = extraction_complete
            result['rows_extracted'] = rows_extracted
            result['metadata']['processing_time'] = time.time() - start_time

            logger.info(f"    AI extraction: {len(rows)} rows, complete={extraction_complete}")

        except Exception as e:
            result['error'] = str(e)
            result['metadata']['processing_time'] = time.time() - start_time
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
            Dict with 'success', 'rows', 'extraction_complete', 'iterations_used', 'metadata'
        """
        start_time = time.time()
        result = {
            'success': False,
            'rows': initial_rows.copy(),
            'extraction_complete': False,
            'iterations_used': 1,  # Count initial extraction
            'error': None,
            'metadata': {
                'cost': 0.0,
                'processing_time': 0.0,
                'api_calls': 0,
                'provider': 'gemini'
            }
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
                    model=["gemini-2.0-flash", "gemini-2.5-flash"],  # Try both Gemini models
                    max_tokens=max_tokens,
                    use_cache=False,  # Don't cache iterative calls
                    include_domains=[domain],
                    tool_name="table_extraction_continuation"
                )

                # Track iteration cost
                cost_info = self._extract_cost_from_response(api_response)
                result['metadata']['cost'] += cost_info['cost']
                result['metadata']['api_calls'] += 1

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
            result['metadata']['processing_time'] = time.time() - start_time

        except Exception as e:
            logger.error(f"Iterative extraction error: {str(e)}")
            result['error'] = str(e)
            result['metadata']['processing_time'] = time.time() - start_time

        return result

    async def _try_search_extraction(
        self, url: str, table_name: str, expected_columns: List[str],
        estimated_rows: int, max_tokens: int
    ) -> Dict[str, Any]:
        """
        Try the_clone extraction mode (8K tokens/page, parallel, Gemini synthesis).

        Returns:
            Dict with 'success', 'rows', 'extraction_complete', 'error', 'metadata'
        """
        start_time = time.time()
        result = {
            'success': False,
            'rows': [],
            'extraction_complete': False,
            'error': None,
            'metadata': {
                'cost': 0.0,
                'processing_time': 0.0,
                'api_calls': 0,
                'provider': 'the-clone'
            }
        }

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

            # Track the_clone costs
            cost_info = self._extract_cost_from_response(api_response)
            result['metadata']['cost'] = cost_info['cost']
            result['metadata']['api_calls'] = 1

            if 'response' not in api_response or 'error' in api_response:
                result['error'] = api_response.get('error', 'Clone extraction failed')
                result['metadata']['processing_time'] = time.time() - start_time
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
            result['metadata']['processing_time'] = time.time() - start_time

            logger.info(f"    the_clone EXTRACTION mode: {len(rows)} rows (8K tokens/page, Gemini)")

        except Exception as e:
            result['error'] = str(e)
            result['metadata']['processing_time'] = time.time() - start_time
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

    def _extract_cost_from_response(self, api_response: Dict) -> Dict[str, Any]:
        """
        Extract cost and provider info from API response.

        Args:
            api_response: Response from AI API client

        Returns:
            Dict with cost, provider, model, and token info
        """
        enhanced_data = api_response.get('enhanced_data', {})

        # Cost is in enhanced_data['costs']['actual']['total_cost']
        costs = enhanced_data.get('costs', {})
        actual_costs = costs.get('actual', {})
        total_cost = actual_costs.get('total_cost', 0.0)

        # Provider info is in call_info
        call_info = enhanced_data.get('call_info', {})

        return {
            'cost': total_cost,
            'provider': call_info.get('api_provider', 'unknown'),
            'model': call_info.get('model', api_response.get('model_used', 'unknown')),
            'tokens': api_response.get('token_usage', {})
        }

    def _accumulate_costs(
        self,
        cost_by_provider: Dict[str, Dict[str, float]],
        provider: str,
        cost: float
    ) -> None:
        """
        Accumulate costs by provider.

        Args:
            cost_by_provider: Dict to accumulate into
            provider: Provider name (perplexity, gemini, vertex, anthropic)
            cost: Cost to add
        """
        if provider not in cost_by_provider:
            cost_by_provider[provider] = {'cost': 0.0, 'calls': 0}

        cost_by_provider[provider]['cost'] += cost
        cost_by_provider[provider]['calls'] += 1

    def _build_metadata(
        self,
        strategies_attempted: List[Dict],
        total_cost: float,
        cost_by_provider: Dict,
        cost_breakdown: Dict = None,
        extraction_details: Dict = None,
        performance: Dict = None,
        total_time: float = 0.0
    ) -> Dict:
        """
        Build comprehensive metadata for table extraction result.

        Args:
            strategies_attempted: List of strategies tried
            total_cost: Total cost across all strategies
            cost_by_provider: Cost breakdown by provider
            cost_breakdown: Cost breakdown by stage
            extraction_details: Detailed extraction stats
            performance: Performance metrics
            total_time: Total processing time

        Returns:
            Comprehensive metadata dict
        """
        successful_strategy = next(
            (s for s in strategies_attempted if s.get('success', False)),
            strategies_attempted[-1] if strategies_attempted else {'name': 'none'}
        )

        metadata = {
            'total_cost': round(total_cost, 4),
            'processing_time': round(total_time, 2),
            'strategy_used': successful_strategy.get('name', 'none'),
            'iterations_used': successful_strategy.get('iterations', 1),
            'strategies_attempted': strategies_attempted,
            'cost_by_provider': cost_by_provider,
        }

        if cost_breakdown:
            metadata['cost_breakdown'] = cost_breakdown

        if extraction_details:
            metadata['extraction_details'] = extraction_details

        if performance:
            metadata['performance'] = performance

        return metadata
