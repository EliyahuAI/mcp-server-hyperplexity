#!/usr/bin/env python3
"""
Row Discovery Stream for table maker.

Discovers and scores candidate rows for a SINGLE subdomain by:
1. Executing web searches for the subdomain
2. Extracting candidate entities from search results
3. Scoring each candidate against table criteria
4. Returning scored candidates with rationale
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class RowDiscoveryStream:
    """
    Discover and score candidate rows for a single subdomain.

    Example:
        >>> stream = RowDiscoveryStream(ai_client, prompt_loader, schema_validator)
        >>> subdomain = {
        ...     "name": "AI Research Companies",
        ...     "focus": "Academic/research-focused AI companies",
        ...     "search_queries": ["AI research labs hiring", "machine learning research companies"]
        ... }
        >>> columns = [
        ...     {"name": "Company Name", "is_identification": True, ...},
        ...     {"name": "Website", "is_identification": True, ...}
        ... ]
        >>> search_strategy = {"description": "Find AI companies...", ...}
        >>> result = await stream.discover_rows(subdomain, columns, search_strategy)
        >>> print(f"Found {len(result['candidates'])} candidates")
    """

    def __init__(self, ai_client, prompt_loader, schema_validator):
        """
        Initialize row discovery stream.

        Args:
            ai_client: AI API client instance (supports Perplexity for web search)
            prompt_loader: PromptLoader instance for loading templates
            schema_validator: SchemaValidator instance for validating outputs
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator

        logger.info("RowDiscoveryStream initialized")

    async def discover_rows(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        web_search_limit: int = 3
    ) -> Dict[str, Any]:
        """
        Discover candidate rows for a single subdomain.

        Args:
            subdomain: Subdomain definition with:
                - name: str (e.g., "AI Research Companies")
                - focus: str (description of focus area)
                - search_queries: List[str] (specific queries for this subdomain)
            columns: List of column definitions (ID + research columns)
            search_strategy: Overall search strategy with description
            web_search_limit: Maximum number of web searches to perform (default: 3)

        Returns:
            Dictionary with:
            {
                "subdomain": str,
                "candidates": List[{
                    "id_values": Dict[str, str],
                    "match_score": float (0-1),
                    "match_rationale": str,
                    "source_urls": List[str]
                }],
                "web_searches_performed": int,
                "processing_time": float
            }

        Raises:
            ValueError: If subdomain or columns are malformed
            Exception: If web search or LLM processing fails
        """
        start_time = time.time()
        subdomain_name = subdomain.get('name', 'Unknown')

        try:
            # Validate inputs
            self._validate_inputs(subdomain, columns, search_strategy)

            logger.info(f"Starting row discovery for subdomain: {subdomain_name}")
            # Step 1: Execute web searches
            web_search_results = await self._execute_web_searches(
                subdomain,
                web_search_limit
            )

            # Step 2: Extract and score candidates using LLM
            candidates_data = await self._extract_and_score_candidates(
                subdomain,
                columns,
                search_strategy,
                web_search_results
            )

            # Step 3: Validate output against schema
            is_valid, error = self.schema_validator.validate(
                candidates_data,
                'row_discovery_response'
            )

            if not is_valid:
                logger.error(f"Schema validation failed: {error}")
                raise ValueError(f"Row discovery output validation failed: {error}")

            # Add metadata
            processing_time = time.time() - start_time
            candidates_data['web_searches_performed'] = len(web_search_results)
            candidates_data['processing_time'] = processing_time

            candidate_count = len(candidates_data.get('candidates', []))
            logger.info(
                f"Row discovery completed for '{subdomain_name}': "
                f"{candidate_count} candidates found in {processing_time:.2f}s"
            )

            return candidates_data

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Row discovery failed for '{subdomain_name}': {str(e)}"
            logger.error(error_msg)

            # Return empty result on error (graceful degradation)
            return {
                'subdomain': subdomain_name,
                'candidates': [],
                'web_searches_performed': 0,
                'processing_time': processing_time,
                'error': error_msg
            }

    def _validate_inputs(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any]
    ):
        """
        Validate input parameters.

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Search strategy

        Raises:
            ValueError: If inputs are malformed
        """
        # Validate subdomain
        if not isinstance(subdomain, dict):
            raise ValueError("Subdomain must be a dictionary")

        required_subdomain_fields = ['name', 'focus', 'search_queries']
        for field in required_subdomain_fields:
            if field not in subdomain:
                raise ValueError(f"Subdomain missing required field: {field}")

        if not isinstance(subdomain['search_queries'], list):
            raise ValueError("Subdomain search_queries must be a list")

        if len(subdomain['search_queries']) == 0:
            raise ValueError("Subdomain must have at least one search query")

        # Validate columns
        if not isinstance(columns, list) or len(columns) == 0:
            raise ValueError("Columns must be a non-empty list")

        # Check for at least one ID column
        id_columns = [col for col in columns if col.get('is_identification', False)]
        if len(id_columns) == 0:
            raise ValueError("At least one column must be marked as identification")

        # Validate search strategy
        if not isinstance(search_strategy, dict):
            raise ValueError("Search strategy must be a dictionary")

    async def _execute_web_searches(
        self,
        subdomain: Dict[str, Any],
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Execute web searches for the subdomain.

        Args:
            subdomain: Subdomain definition with search_queries
            limit: Maximum number of searches to perform

        Returns:
            List of search results, each containing:
            {
                "query": str,
                "response": str,
                "sources": List[str],
                "success": bool
            }
        """
        search_queries = subdomain['search_queries'][:limit]  # Limit to max searches
        subdomain_name = subdomain['name']

        logger.info(f"Executing {len(search_queries)} web searches for '{subdomain_name}'")

        search_results = []

        for query in search_queries:
            try:
                logger.debug(f"Searching: {query}")

                # Use Perplexity API for web search
                # Using high context for comprehensive research
                result = await self.ai_client.validate_with_perplexity(
                    prompt=query,
                    model='sonar-pro',
                    search_context_size='high',
                    use_cache=True
                )

                # Extract response and citations
                search_result = {
                    'query': query,
                    'response': self._extract_response_text(result.get('response', {})),
                    'sources': result.get('citations', []),
                    'success': True
                }

                search_results.append(search_result)
                logger.debug(f"Search successful: {len(search_result['sources'])} sources found")

            except Exception as e:
                logger.warning(f"Web search failed for query '{query}': {str(e)}")
                # Add failed search with empty results
                search_results.append({
                    'query': query,
                    'response': '',
                    'sources': [],
                    'success': False,
                    'error': str(e)
                })

        successful_searches = sum(1 for r in search_results if r['success'])
        logger.info(f"Web searches completed: {successful_searches}/{len(search_results)} successful")

        return search_results

    def _extract_response_text(self, response: Dict[str, Any]) -> str:
        """
        Extract response text from API response.

        Args:
            response: API response dictionary

        Returns:
            Extracted response text
        """
        try:
            # Handle different response formats
            if isinstance(response, str):
                return response

            if 'choices' in response:
                # OpenAI/Perplexity format
                content = response['choices'][0]['message']['content']
                if isinstance(content, str):
                    return content
                elif isinstance(content, dict):
                    return content.get('text', str(content))

            if 'content' in response:
                # Anthropic format
                content = response['content']
                if isinstance(content, str):
                    return content
                elif isinstance(content, list) and len(content) > 0:
                    return content[0].get('text', '')

            # Fallback: convert to string
            return str(response)

        except Exception as e:
            logger.error(f"Error extracting response text: {e}")
            return str(response)

    async def _extract_and_score_candidates(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        web_search_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Use LLM to extract and score candidates from web search results.

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Search strategy
            web_search_results: Results from web searches

        Returns:
            Dictionary matching row_discovery_response schema
        """
        # Load and fill prompt template
        prompt = self._build_prompt(
            subdomain,
            columns,
            search_strategy,
            web_search_results
        )

        # Load schema for structured output
        schema = self.schema_validator.load_schema('row_discovery_response')

        logger.debug(f"Calling LLM to extract candidates for '{subdomain['name']}'")

        try:
            # Call LLM with structured output
            result = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model='claude-sonnet-4-5',
                tool_name='row_discovery',
                use_cache=False,  # Don't cache - web results change
                max_tokens=8000
            )

            if not result.get('success', False):
                raise ValueError(f"LLM call failed: {result.get('error', 'Unknown error')}")

            # Extract structured response
            response_data = result.get('response', {})

            # Ensure subdomain is set correctly
            response_data['subdomain'] = subdomain['name']

            return response_data

        except Exception as e:
            logger.error(f"Error extracting candidates: {str(e)}")
            # Return empty candidates on error
            return {
                'subdomain': subdomain['name'],
                'candidates': []
            }

    def _build_prompt(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        web_search_results: List[Dict[str, Any]]
    ) -> str:
        """
        Build prompt for candidate extraction using template.

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Search strategy
            web_search_results: Web search results

        Returns:
            Filled prompt string
        """
        # Format subdomain
        subdomain_text = f"{subdomain['name']}\n{subdomain['focus']}"

        # Format search strategy
        strategy_text = search_strategy.get('description', 'Find relevant entities')

        # Format columns as JSON
        columns_json = json.dumps(columns, indent=2)

        # Format web search results
        web_results_text = self._format_web_search_results(web_search_results)

        # Load and fill template
        variables = {
            'SUBDOMAIN': subdomain_text,
            'SEARCH_STRATEGY': strategy_text,
            'COLUMNS': columns_json,
            'WEB_SEARCH_RESULTS': web_results_text
        }

        prompt = self.prompt_loader.load_prompt('row_discovery', variables)

        return prompt

    def _format_web_search_results(self, search_results: List[Dict[str, Any]]) -> str:
        """
        Format web search results for prompt.

        Args:
            search_results: List of search result dictionaries

        Returns:
            Formatted string with all search results
        """
        if not search_results or all(not r['success'] for r in search_results):
            return "No web search results available."

        formatted_parts = []

        for i, result in enumerate(search_results, 1):
            if not result['success']:
                continue

            formatted_parts.append(f"### Search {i}: {result['query']}")
            formatted_parts.append("")
            formatted_parts.append(result['response'])
            formatted_parts.append("")

            if result.get('sources'):
                formatted_parts.append("**Sources:**")
                for source in result['sources'][:5]:  # Limit to 5 sources per search
                    if isinstance(source, dict):
                        url = source.get('url', '')
                    else:
                        url = str(source)

                    if url:
                        formatted_parts.append(f"- {url}")
                formatted_parts.append("")

        if not formatted_parts:
            return "No successful web search results."

        return "\n".join(formatted_parts)


# Convenience function for easy usage
async def discover_rows(
    ai_client,
    prompt_loader,
    schema_validator,
    subdomain: Dict[str, Any],
    columns: List[Dict[str, Any]],
    search_strategy: Dict[str, Any],
    web_search_limit: int = 3
) -> Dict[str, Any]:
    """
    Convenience function to discover rows for a subdomain.

    Args:
        ai_client: AI API client instance
        prompt_loader: PromptLoader instance
        schema_validator: SchemaValidator instance
        subdomain: Subdomain definition
        columns: Column definitions
        search_strategy: Search strategy
        web_search_limit: Maximum web searches (default: 3)

    Returns:
        Row discovery results dictionary
    """
    stream = RowDiscoveryStream(ai_client, prompt_loader, schema_validator)
    return await stream.discover_rows(subdomain, columns, search_strategy, web_search_limit)
