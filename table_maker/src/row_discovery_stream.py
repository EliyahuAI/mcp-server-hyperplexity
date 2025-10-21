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
        target_rows: int = 7,
        scoring_model: str = 'sonar-pro'
    ) -> Dict[str, Any]:
        """
        Discover candidate rows for a single subdomain using integrated scoring.

        Uses a single sonar-pro call to both search and score candidates.
        Scoring is based on three dimensions:
        - Relevancy to requirements (40%)
        - Source reliability (30%)
        - Recency of information (30%)

        Args:
            subdomain: Subdomain definition with:
                - name: str (e.g., "AI Research Companies")
                - focus: str (description of focus area)
                - search_queries: List[str] (specific queries for this subdomain)
                - target_rows: int (how many to find)
            columns: List of column definitions (ID + research columns)
            search_strategy: Overall search strategy with description
            target_rows: Number of candidates to find for this subdomain (default: 7)
            scoring_model: Model to use for integrated search+scoring (default: 'sonar-pro')

        Returns:
            Dictionary with:
            {
                "subdomain": str,
                "candidates": List[{
                    "id_values": Dict[str, str],
                    "match_score": float (0-1),
                    "score_breakdown": {
                        "relevancy": float (0-1),
                        "reliability": float (0-1),
                        "recency": float (0-1)
                    },
                    "match_rationale": str,
                    "source_urls": List[str]
                }],
                "processing_time": float
            }

        Raises:
            ValueError: If subdomain or columns are malformed
            Exception: If integrated search/scoring fails
        """
        start_time = time.time()
        subdomain_name = subdomain.get('name', 'Unknown')

        try:
            # Validate inputs
            self._validate_inputs(subdomain, columns, search_strategy)

            logger.info(
                f"Starting integrated row discovery for subdomain: {subdomain_name} "
                f"(target: {target_rows} rows)"
            )

            # Try low context first, escalate to high if insufficient results
            logger.info(f"Attempt 1: Trying low context search")
            candidates_data = await self._discover_and_score(
                subdomain,
                columns,
                search_strategy,
                target_rows,
                scoring_model,
                search_context_size='low'
            )

            # Check if we got enough candidates
            candidate_count = len(candidates_data.get('candidates', []))
            min_required = max(3, target_rows // 2)  # At least 3 or half of target

            if candidate_count < min_required:
                logger.warning(
                    f"Low context found only {candidate_count} candidates "
                    f"(need {min_required}). Retrying with high context..."
                )
                candidates_data = await self._discover_and_score(
                    subdomain,
                    columns,
                    search_strategy,
                    target_rows,
                    scoring_model,
                    search_context_size='high'
                )
                candidate_count = len(candidates_data.get('candidates', []))
                logger.info(f"High context search found {candidate_count} candidates")

            # Validate output against schema
            is_valid, error = self.schema_validator.validate(
                candidates_data,
                'row_discovery_response'
            )

            if not is_valid:
                logger.error(f"Schema validation failed: {error}")
                raise ValueError(f"Row discovery output validation failed: {error}")

            # Add metadata
            processing_time = time.time() - start_time
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

    async def _discover_and_score(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        target_rows: int,
        scoring_model: str,
        search_context_size: str = 'low'
    ) -> Dict[str, Any]:
        """
        Execute web search with integrated scoring in ONE call.

        Uses sonar-pro (or configured model) to:
        1. Search for entities matching subdomain focus
        2. Score each entity using the rubric
        3. Return top N scored candidates

        Returns candidates with score_breakdown showing:
        - relevancy_score (0-1)
        - reliability_score (0-1)
        - recency_score (0-1)
        - final_score (weighted average)

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Search strategy
            target_rows: How many rows to find
            scoring_model: Model to use (default: sonar-pro)

        Returns:
            Dictionary matching row_discovery_response schema with score_breakdown
        """
        # Build prompt with integrated scoring rubric
        prompt = self._build_integrated_scoring_prompt(
            subdomain,
            columns,
            search_strategy,
            target_rows
        )

        # Load schema for structured output
        schema = self.schema_validator.load_schema('row_discovery_response')

        logger.info(
            f"Calling {scoring_model} for integrated discovery+scoring: "
            f"'{subdomain['name']}' (target: {target_rows} rows, context: {search_context_size})"
        )

        try:
            # Single call to sonar-pro with structured output
            result = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=scoring_model,
                tool_name='row_discovery_integrated',
                use_cache=False,  # Don't cache - web results change
                max_tokens=8000,
                max_web_searches=len(subdomain.get('search_queries', [])),  # Use all queries
                search_context_size=search_context_size  # Progressive: low → high
            )

            # call_structured_api returns dict with 'response', 'token_usage', etc.
            # Check if we got a valid response
            if 'response' not in result:
                raise ValueError(f"LLM call failed: {result.get('error', 'No response returned')}")

            # Extract structured response
            response_data = result.get('response', {})

            # If response is in Perplexity unified format, extract the JSON
            if isinstance(response_data, dict) and 'choices' in response_data:
                content = response_data['choices'][0]['message']['content']
                if isinstance(content, str):
                    response_data = json.loads(content)
            elif isinstance(response_data, str):
                response_data = json.loads(response_data)

            # Ensure subdomain is set correctly
            response_data['subdomain'] = subdomain['name']

            # Limit to target_rows
            candidates = response_data.get('candidates', [])
            response_data['candidates'] = candidates[:target_rows]

            return response_data

        except Exception as e:
            logger.error(f"Error in integrated discovery+scoring: {str(e)}")
            # Return empty candidates on error
            return {
                'subdomain': subdomain['name'],
                'candidates': []
            }

    def _build_integrated_scoring_prompt(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        target_rows: int
    ) -> str:
        """
        Build prompt with integrated scoring rubric.

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Search strategy
            target_rows: How many rows to find

        Returns:
            Filled prompt string with scoring rubric
        """
        # Extract ID columns
        id_columns = [col['name'] for col in columns if col.get('is_identification')]

        # Build search queries section
        search_queries_text = '\n'.join(f'- {q}' for q in subdomain['search_queries'])

        # Build ID columns section
        id_columns_text = '\n'.join(f'- {col}' for col in id_columns)

        prompt = f"""You are finding and scoring entities for: {subdomain['name']}

FOCUS: {subdomain['focus']}

REQUIREMENTS: {search_strategy.get('description', 'Find relevant entities')}

TARGET: Find {target_rows} best-matching entities

SEARCH QUERIES (prioritize multi-row results):
{search_queries_text}

CRITICAL: Use EXACT field names for ID columns in your response:
{id_columns_text}

For example, if columns are "Company Name" and "Website", use those EXACT names:
  {{"id_values": {{"Company Name": "Anthropic", "Website": "https://anthropic.com"}}}}

Do NOT rename to "entity_name", "Entity Name", "company", etc.
Use the EXACT field names listed above.

SCORING RUBRIC (0-1.0 scale):
Final Score = (Relevancy × 0.4) + (Source Reliability × 0.3) + (Recency × 0.3)

**Relevancy (0-1.0):** How well does the entity match requirements?
  1.0 = Perfect match to all requirements
  0.7 = Matches most requirements, minor gaps
  0.4 = Matches core requirements only
  0.0 = Weak or no match

**Source Reliability (0-1.0):** How reliable are your sources?
  1.0 = Primary sources (company site, Crunchbase, official docs)
  0.7 = Secondary sources (TechCrunch, LinkedIn, WSJ, Bloomberg)
  0.4 = Tertiary sources (blogs, aggregators, forums)
  0.0 = Unreliable or unverified

**Recency (0-1.0):** How recent is the information?
  1.0 = <3 months old
  0.7 = 3-6 months old
  0.4 = 6-12 months old
  0.0 = >12 months or undated

For each entity:
1. Populate ID columns using EXACT field names from list above
2. Calculate individual dimension scores (relevancy, reliability, recency)
3. Calculate final weighted score: (relevancy × 0.4) + (reliability × 0.3) + (recency × 0.3)
4. Provide 1-sentence rationale explaining score
5. Include source URLs

Return top {target_rows} candidates sorted by final score (highest first).
"""
        return prompt


# Convenience function for easy usage
async def discover_rows(
    ai_client,
    prompt_loader,
    schema_validator,
    subdomain: Dict[str, Any],
    columns: List[Dict[str, Any]],
    search_strategy: Dict[str, Any],
    target_rows: int = 7,
    scoring_model: str = 'sonar-pro'
) -> Dict[str, Any]:
    """
    Convenience function to discover rows for a subdomain with integrated scoring.

    Args:
        ai_client: AI API client instance
        prompt_loader: PromptLoader instance
        schema_validator: SchemaValidator instance
        subdomain: Subdomain definition
        columns: Column definitions
        search_strategy: Search strategy
        target_rows: Number of rows to find (default: 7)
        scoring_model: Model for integrated scoring (default: sonar-pro)

    Returns:
        Row discovery results dictionary
    """
    stream = RowDiscoveryStream(ai_client, prompt_loader, schema_validator)
    return await stream.discover_rows(subdomain, columns, search_strategy, target_rows, scoring_model)
