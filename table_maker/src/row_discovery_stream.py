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

    async def discover_rows_progressive(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        target_rows: int,
        escalation_strategy: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Discover rows using progressive model escalation.

        Tries each strategy in order, stopping early if sufficient candidates found.
        Returns ALL candidates from all rounds for later consolidation.

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Overall search strategy
            target_rows: Number of rows to target for this subdomain
            escalation_strategy: List of strategies to try:
              [
                {"model": "sonar", "search_context_size": "low", "min_candidates_percentage": 50},
                {"model": "sonar", "search_context_size": "high", "min_candidates_percentage": 75},
                {"model": "sonar-pro", "search_context_size": "high", "min_candidates_percentage": null}
              ]

        Returns:
            {
              "subdomain": str,
              "all_rounds": [
                {
                  "round": 1,
                  "model": "sonar",
                  "context": "low",
                  "candidates": [...],
                  "count": 5
                },
                ...
              ],
              "candidates": [...],  # All candidates combined
              "total_candidates": 15,
              "rounds_executed": 2,
              "rounds_skipped": 1,
              "processing_time": float
            }
        """
        start_time = time.time()
        subdomain_name = subdomain.get('name', 'Unknown')

        try:
            # Validate inputs
            self._validate_inputs(subdomain, columns, search_strategy)

            logger.info(
                f"Starting progressive row discovery for subdomain: {subdomain_name} "
                f"(target: {target_rows} rows, {len(escalation_strategy)} round(s) max)"
            )

            all_rounds = []
            accumulated_candidates = []

            for round_idx, strategy in enumerate(escalation_strategy, 1):
                model = strategy['model']
                context = strategy['search_context_size']
                min_percentage = strategy.get('min_candidates_percentage')

                logger.info(
                    f"Round {round_idx}/{len(escalation_strategy)}: {model} ({context} context)"
                )

                # Execute this round
                round_candidates = await self._discover_and_score(
                    subdomain,
                    columns,
                    search_strategy,
                    target_rows,
                    model,
                    context
                )

                # Tag each candidate with model/context info
                candidates = round_candidates.get('candidates', [])
                for candidate in candidates:
                    candidate['model_used'] = model
                    candidate['context_used'] = context
                    candidate['round'] = round_idx

                # PHASE 1: Record round results with enhanced_data and prompt
                round_data = {
                    'round': round_idx,
                    'model': model,
                    'context': context,
                    'candidates': candidates,
                    'count': len(candidates),
                    'enhanced_data': round_candidates.get('enhanced_data', {}),
                    'prompt_used': round_candidates.get('prompt_used', ''),
                    'call_description': f"Finding Rows - {subdomain_name} - Round {round_idx} ({model}-{context})"
                }
                all_rounds.append(round_data)

                # Accumulate candidates
                accumulated_candidates.extend(candidates)
                total_so_far = len(accumulated_candidates)

                logger.info(f"Round {round_idx}: Found {len(candidates)} candidates (total: {total_so_far})")

                # Check if we should stop early
                if min_percentage is not None:
                    threshold = int(target_rows * (min_percentage / 100))

                    if total_so_far >= threshold:
                        rounds_skipped = len(escalation_strategy) - round_idx
                        logger.info(
                            f"Early stop: {total_so_far} candidates >= {threshold} threshold "
                            f"({min_percentage}% of {target_rows}). Skipping {rounds_skipped} round(s)"
                        )
                        break

            # Prepare result
            processing_time = time.time() - start_time
            rounds_executed = len(all_rounds)
            rounds_skipped = len(escalation_strategy) - rounds_executed

            result = {
                'subdomain': subdomain_name,
                'all_rounds': all_rounds,
                'candidates': accumulated_candidates,
                'total_candidates': len(accumulated_candidates),
                'rounds_executed': rounds_executed,
                'rounds_skipped': rounds_skipped,
                'processing_time': processing_time
            }

            logger.info(
                f"Progressive discovery completed for '{subdomain_name}': "
                f"{len(accumulated_candidates)} candidates from {rounds_executed} round(s) "
                f"in {processing_time:.2f}s"
            )

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Progressive row discovery failed for '{subdomain_name}': {str(e)}"
            logger.error(error_msg)

            # Return empty result on error
            return {
                'subdomain': subdomain_name,
                'all_rounds': [],
                'candidates': [],
                'total_candidates': 0,
                'rounds_executed': 0,
                'rounds_skipped': len(escalation_strategy),
                'processing_time': processing_time,
                'error': error_msg
            }

    async def discover_rows(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        target_rows: int = 7,
        scoring_model: str = 'sonar-pro',
        escalation_strategy: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Discover candidate rows for a single subdomain using integrated scoring.

        If escalation_strategy is provided, uses progressive escalation.
        Otherwise, uses legacy two-step context escalation.

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
            escalation_strategy: Optional list of progressive strategies (default: None for legacy mode)

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
                    "source_urls": List[str],
                    "model_used": str (if progressive),
                    "context_used": str (if progressive),
                    "round": int (if progressive)
                }],
                "processing_time": float
            }

        Raises:
            ValueError: If subdomain or columns are malformed
            Exception: If integrated search/scoring fails
        """
        # If escalation_strategy provided, use progressive mode
        if escalation_strategy is not None:
            result = await self.discover_rows_progressive(
                subdomain, columns, search_strategy, target_rows, escalation_strategy
            )
            # Return progressive result with all_rounds for detailed tracking
            return {
                'subdomain': result['subdomain'],
                'candidates': result['candidates'],
                'processing_time': result['processing_time'],
                'rounds_executed': result.get('rounds_executed', 0),
                'rounds_skipped': result.get('rounds_skipped', 0),
                'all_rounds': result.get('all_rounds', []),  # Include all rounds with prompts/enhanced_data
                'error': result.get('error')
            }

        # Legacy mode: two-step context escalation
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

            # PHASE 2: DEBUG logging when 0 candidates found
            if len(candidates) == 0:
                logger.warning(f"[DEBUG] {scoring_model} ({search_context_size}) returned 0 candidates!")
                logger.warning(f"[DEBUG] Subdomain: {subdomain['name']}")
                logger.warning(f"[DEBUG] Search queries: {subdomain.get('search_queries', [])}")
                logger.warning(f"[DEBUG] Prompt (first 500 chars): {prompt[:500]}")
                logger.warning(f"[DEBUG] Response type: {type(response_data)}")
                logger.warning(f"[DEBUG] Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'N/A'}")

                # Try to extract any text content
                raw_response = result.get('response', {})
                if 'choices' in raw_response:
                    try:
                        content = raw_response['choices'][0]['message']['content']
                        logger.warning(f"[DEBUG] Response content (first 500 chars): {str(content)[:500]}")
                    except Exception as e:
                        logger.warning(f"[DEBUG] Could not extract response content: {e}")

            response_data['candidates'] = candidates[:target_rows]

            # PHASE 1: Include enhanced_data in return
            response_data['enhanced_data'] = result.get('enhanced_data', {})

            # Save prompt for debugging/analysis
            response_data['prompt_used'] = prompt

            return response_data

        except Exception as e:
            logger.error(f"Error in integrated discovery+scoring: {str(e)}")
            # Return empty candidates on error
            return {
                'subdomain': subdomain['name'],
                'candidates': [],
                'enhanced_data': {}
            }

    def _build_integrated_scoring_prompt(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        target_rows: int
    ) -> str:
        """
        Build prompt with integrated scoring rubric using template.

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Search strategy
            target_rows: How many rows to find

        Returns:
            Filled prompt string from template
        """
        # Extract ID columns with descriptions
        id_columns = [col for col in columns if col.get('is_identification')]

        # Format ID columns with descriptions
        id_columns_text = []
        for col in id_columns:
            name = col['name']
            desc = col.get('description', 'No description')
            id_columns_text.append(f"- **{name}**: {desc}")

        # Try to load template (if exists), otherwise use inline
        try:
            variables = {
                'SUBDOMAIN_NAME': subdomain['name'],
                'SUBDOMAIN_FOCUS': subdomain['focus'],
                'SEARCH_REQUIREMENTS': search_strategy.get('description', 'Find relevant entities'),
                'SEARCH_QUERIES': '\n'.join(f'- {q}' for q in subdomain['search_queries']),
                'TARGET_ROWS': str(target_rows),
                'ID_COLUMNS': '\n'.join(id_columns_text),
                'USER_CONTEXT': search_strategy.get('user_context', 'General research table'),
                'TABLE_PURPOSE': search_strategy.get('table_purpose', search_strategy.get('description', '')),
                'TABLEWIDE_RESEARCH': search_strategy.get('tablewide_research', '')
            }

            # Try template first
            prompt = self.prompt_loader.load_prompt('row_discovery', variables)
            return prompt

        except Exception as e:
            logger.debug(f"Could not load template, using inline prompt: {e}")

        # Fallback: Build inline (for backward compat)
        search_queries_text = '\n'.join(f'- {q}' for q in subdomain['search_queries'])
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
