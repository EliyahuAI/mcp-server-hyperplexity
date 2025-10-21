#!/usr/bin/env python3
"""
DEPRECATED: This component is no longer used in the table generation system.

Date Deprecated: October 20, 2025
Reason: Subdomains are now defined directly in the column_definition step,
        eliminating the need for a separate subdomain analysis call.

Replaced By: Subdomain specification in column_definition_response.json schema.
             The search_strategy now includes a 'subdomains' array with 2-5
             subdomain definitions, each containing name, focus, search_queries,
             and target_rows.

Original Purpose: Analyze search strategies to identify natural subdivisions (subdomains)
                 for parallel row discovery. This required a separate AI call to split
                 a broad search strategy into 2-5 focused subdomains.

Migration Path: Instead of calling subdomain_analyzer.analyze(), subdomains are now
               returned directly from the column definition step as part of the
               search_strategy object.

Code Kept For: Reference and potential future use if manual subdomain splitting
              becomes needed outside the column definition flow.

See: table_maker/src/SUBDOMAIN_ANALYZER_DEPRECATED.md for more details.

---

Subdomain analyzer for table generation system.
Analyzes search strategies to identify natural subdivisions for parallel row discovery.
"""

import json
import logging
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)


class SubdomainAnalyzer:
    """
    Analyze search strategies to identify natural subdivisions (subdomains) for parallel row discovery.

    This component helps split broad search strategies into 2-5 focused subdomains that can be
    searched in parallel, improving the efficiency and coverage of row discovery.
    """

    def __init__(self, ai_client, prompt_loader, schema_validator):
        """
        Initialize subdomain analyzer.

        Args:
            ai_client: AI API client instance (from ../../src/shared/ai_api_client.py)
            prompt_loader: PromptLoader instance for loading prompt templates
            schema_validator: SchemaValidator instance for validating AI responses
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator

        logger.info("Initialized SubdomainAnalyzer")

    async def analyze(
        self,
        search_strategy: Dict[str, Any],
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 4000
    ) -> Dict[str, Any]:
        """
        Analyze search strategy and identify 2-5 natural subdivisions.

        This method uses an LLM to intelligently split a search strategy into subdomains
        that can be searched in parallel. The analysis considers:
        - Natural divisions in the search space (e.g., industry sectors, regions)
        - Balance between parallelization and over-splitting
        - Coverage of the full search scope
        - Quality and specificity of search queries per subdomain

        Args:
            search_strategy: Dictionary containing search strategy information with keys:
                - 'description': str - Description of what to search for
                - 'subdomain_hints': List[str] - Optional hints for subdivision
                - 'search_queries': List[str] - General search queries
            model: AI model to use for analysis
            max_tokens: Maximum tokens for LLM response

        Returns:
            Dictionary with analysis results:
            {
                'success': bool,
                'subdomains': List[Dict] - List of subdomain definitions, each with:
                    - 'name': str - Short descriptive name
                    - 'focus': str - Detailed description of subdomain scope
                    - 'search_queries': List[str] - Focused queries for this subdomain
                'reasoning': str - Explanation of subdomain choices
                'subdomain_count': int,
                'execution_time_seconds': float,
                'token_usage': Dict - Token usage information
                'error': Optional[str]
            }

        Raises:
            ValueError: If search_strategy is invalid or missing required fields
            Exception: If AI API call fails or response validation fails
        """
        import time

        result = {
            'success': False,
            'subdomains': [],
            'reasoning': '',
            'subdomain_count': 0,
            'execution_time_seconds': 0.0,
            'token_usage': {},
            'error': None
        }

        start_time = time.time()

        try:
            # Validate search_strategy input
            self._validate_search_strategy(search_strategy)

            logger.info(
                f"Analyzing search strategy: '{search_strategy.get('description', '')[:60]}...'"
            )

            # Format search strategy for prompt
            search_strategy_str = self._format_search_strategy(search_strategy)

            # Load prompt template with variable substitution
            variables = {
                'SEARCH_STRATEGY': search_strategy_str
            }
            prompt = self.prompt_loader.load_prompt('subdomain_analysis', variables)

            # Load response schema
            schema = self.schema_validator.load_schema('subdomain_analysis')

            # Call AI API with structured output
            logger.debug(f"Calling AI API with model: {model}")
            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=True,
                debug_name=None
            )

            # Check for API errors
            if 'response' not in api_response and 'error' in api_response:
                error_detail = api_response.get('error', 'Unknown error')
                logger.error(f"API call failed: {error_detail}")
                raise Exception(f"AI API call failed: {error_detail}")

            # Extract and validate response
            raw_response = api_response.get('response', {})
            ai_response = self._extract_structured_response(raw_response)

            logger.debug(f"Extracted AI response keys: {list(ai_response.keys())}")

            # Validate response against schema
            validation_result = self.schema_validator.validate_ai_response(
                ai_response,
                'subdomain_analysis'
            )

            if not validation_result['is_valid']:
                error_msg = f"AI response validation failed: {validation_result['errors']}"
                logger.error(error_msg)
                raise Exception(error_msg)

            # Extract subdomain information
            subdomains = ai_response.get('subdomains', [])
            reasoning = ai_response.get('reasoning', '')

            # Validate subdomain count (2-5 is optimal, but 1 is acceptable for narrow searches)
            subdomain_count = len(subdomains)
            if subdomain_count < 1:
                logger.warning("No subdomains returned - this is unexpected")
            elif subdomain_count > 5:
                logger.warning(
                    f"AI returned {subdomain_count} subdomains, which may be too many. "
                    "Consider using only the top 5."
                )
                # Optionally truncate to 5
                subdomains = subdomains[:5]
                subdomain_count = len(subdomains)

            # Calculate execution time
            execution_time = time.time() - start_time

            # Build successful result
            result['success'] = True
            result['subdomains'] = subdomains
            result['reasoning'] = reasoning
            result['subdomain_count'] = subdomain_count
            result['execution_time_seconds'] = round(execution_time, 2)

            # Extract token usage if available
            if 'token_usage' in api_response:
                result['token_usage'] = api_response['token_usage']
                self._log_token_usage(api_response['token_usage'])

            logger.info(
                f"Subdomain analysis complete: {subdomain_count} subdomain(s) identified "
                f"in {result['execution_time_seconds']}s"
            )

            # Log subdomain names for debugging
            subdomain_names = [s.get('name', 'Unnamed') for s in subdomains]
            logger.debug(f"Identified subdomains: {', '.join(subdomain_names)}")

        except ValueError as e:
            error_msg = f"Invalid input: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['execution_time_seconds'] = round(time.time() - start_time, 2)

        except Exception as e:
            error_msg = f"Error during subdomain analysis: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['execution_time_seconds'] = round(time.time() - start_time, 2)

        return result

    def _validate_search_strategy(self, search_strategy: Dict[str, Any]) -> None:
        """
        Validate search_strategy input.

        Args:
            search_strategy: Search strategy dictionary to validate

        Raises:
            ValueError: If search_strategy is invalid
        """
        if not isinstance(search_strategy, dict):
            raise ValueError(
                f"search_strategy must be a dictionary, got {type(search_strategy).__name__}"
            )

        # Check for required field
        if 'description' not in search_strategy:
            raise ValueError("search_strategy must contain 'description' field")

        description = search_strategy.get('description', '')
        if not description or not isinstance(description, str):
            raise ValueError("search_strategy 'description' must be a non-empty string")

        logger.debug("Search strategy validation passed")

    def _format_search_strategy(self, search_strategy: Dict[str, Any]) -> str:
        """
        Format search strategy as a readable string for the prompt.

        Args:
            search_strategy: Search strategy dictionary

        Returns:
            Formatted string representation
        """
        lines = []

        # Description
        description = search_strategy.get('description', '')
        lines.append(f"**Description:** {description}")

        # Subdomain hints (optional)
        subdomain_hints = search_strategy.get('subdomain_hints', [])
        if subdomain_hints:
            hints_str = ', '.join(subdomain_hints)
            lines.append(f"\n**Suggested Subdivisions:** {hints_str}")

        # General search queries (optional)
        search_queries = search_strategy.get('search_queries', [])
        if search_queries:
            lines.append("\n**General Search Queries:**")
            for query in search_queries:
                lines.append(f"- {query}")

        return '\n'.join(lines)

    def _extract_structured_response(self, raw_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured response from raw API response.

        Args:
            raw_response: Raw API response

        Returns:
            Parsed structured response dictionary

        Raises:
            Exception: If response cannot be parsed
        """
        try:
            # Check if response is already structured (from cache or direct return)
            if 'subdomains' in raw_response:
                return raw_response

            # Extract from Perplexity/Anthropic response format
            if 'choices' in raw_response:
                content = raw_response['choices'][0]['message']['content']
                # Parse JSON string to dict
                if isinstance(content, str):
                    return json.loads(content)
                return content

            # If content is in different format
            if 'content' in raw_response:
                content = raw_response['content']
                if isinstance(content, str):
                    return json.loads(content)
                elif isinstance(content, list) and len(content) > 0:
                    # Anthropic format: content[0]['text']
                    text_content = content[0].get('text', '{}')
                    return json.loads(text_content)
                return content

            # Fallback: return as-is and let validation catch issues
            logger.warning(f"Unknown response structure, keys: {list(raw_response.keys())}")
            return raw_response

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from response content: {e}")
            raise Exception(f"Failed to parse structured response: {e}")
        except Exception as e:
            logger.error(f"Error extracting structured response: {e}")
            raise

    def _log_token_usage(self, token_usage: Dict[str, Any]) -> None:
        """
        Log token usage information.

        Args:
            token_usage: Token usage dictionary from API response
        """
        input_tokens = token_usage.get('input_tokens', 0)
        output_tokens = token_usage.get('output_tokens', 0)
        total_tokens = token_usage.get('total_tokens', 0)

        logger.info(
            f"Token usage - Input: {input_tokens}, Output: {output_tokens}, "
            f"Total: {total_tokens}"
        )

    def get_subdomain_summary(self, analysis_result: Dict[str, Any]) -> str:
        """
        Generate a human-readable summary of subdomain analysis.

        Args:
            analysis_result: Result from analyze() method

        Returns:
            Formatted summary string
        """
        if not analysis_result.get('success'):
            return f"Analysis failed: {analysis_result.get('error', 'Unknown error')}"

        lines = []
        lines.append(f"Identified {analysis_result['subdomain_count']} subdomain(s):")
        lines.append("")

        for idx, subdomain in enumerate(analysis_result.get('subdomains', []), 1):
            name = subdomain.get('name', 'Unnamed')
            focus = subdomain.get('focus', 'No description')
            query_count = len(subdomain.get('search_queries', []))

            lines.append(f"{idx}. {name}")
            lines.append(f"   Focus: {focus}")
            lines.append(f"   Search queries: {query_count}")
            lines.append("")

        lines.append(f"Reasoning: {analysis_result.get('reasoning', 'N/A')}")
        lines.append("")
        lines.append(
            f"Analysis completed in {analysis_result.get('execution_time_seconds', 0)}s"
        )

        return '\n'.join(lines)
