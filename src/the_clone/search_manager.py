#!/usr/bin/env python3
"""
Search Management Module for Perplexity Clone.
Handles search term generation, execution, and result evaluation.
"""

import sys
import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../shared'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../perplexity_search_tests'))

from shared.ai_api_client import AIAPIClient
from shared.ai_client.utils import extract_structured_response
from the_clone.perplexity_search import PerplexitySearchClient
from the_clone.schemas import get_search_generation_schema, get_result_evaluation_schema
from the_clone.prompt_loader import PromptLoader

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SearchManager:
    """
    Manages search term generation, execution, and result evaluation.
    Uses AI models to intelligently generate and refine search queries.
    """

    def __init__(self, ai_client: AIAPIClient = None, search_client: PerplexitySearchClient = None):
        """
        Initialize the search manager.

        Args:
            ai_client: Optional AIAPIClient instance (creates new if not provided)
            search_client: Optional PerplexitySearchClient instance (creates new if not provided)
        """
        self.ai_client = ai_client or AIAPIClient()
        self.search_client = search_client or PerplexitySearchClient()
        self.prompt_loader = PromptLoader()

    async def generate_search_terms(
        self,
        prompt: str,
        model: str = "deepseek-v3.2",
        optimization_notes: str = ""
    ) -> Dict[str, Any]:
        """
        Generate optimal search terms and settings for a user query.

        Args:
            prompt: User's original query
            model: Model to use for search term generation
            optimization_notes: Optional guidance for search optimization

        Returns:
            Dict containing:
                - search_terms: List of search queries
                - search_settings: Dict with max_results, search_recency_filter
                - reasoning: Explanation of strategy
                - model_response: Full model response with metadata
        """
        logger.info(f"[SEARCH_MANAGER] Generating search terms for: '{prompt[:100]}...'")

        # Load prompt template from file
        generation_prompt = self.prompt_loader.load_prompt(
            'search_generation',
            prompt=prompt,
            optimization_notes=optimization_notes
        )

        try:
            # Call AI model with search generation schema
            response = await self.ai_client.call_structured_api(
                prompt=generation_prompt,
                schema=get_search_generation_schema(),
                model=model,
                use_cache=False,  # Cache disabled for DeepSeek calls
                max_web_searches=0,  # DeepSeek cannot use web search
                context="search_term_generation"
            )

            # Extract structured data using centralized parsing
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            logger.info(f"[SEARCH_MANAGER] Generated {len(data.get('search_terms', []))} search terms")
            logger.debug(f"[SEARCH_MANAGER] Search terms: {data.get('search_terms')}")

            return {
                "search_terms": data.get("search_terms", []),
                "search_settings": data.get("search_settings", {"max_results": 20}),
                "reasoning": data.get("reasoning", ""),
                "model_response": response
            }

        except Exception as e:
            logger.error(f"[SEARCH_MANAGER] Error generating search terms: {e}")
            raise

    async def execute_searches(
        self,
        search_terms: List[str],
        search_settings: Dict[str, Any],
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute searches for all terms using Perplexity Search API.
        Uses optimized multi-query batching (up to 5 queries per API call).

        Args:
            search_terms: List of search queries
            search_settings: Dict with max_results, search_recency_filter

        Returns:
            List of search results, one dict per search term
        """
        logger.info(f"[SEARCH_MANAGER] Executing {len(search_terms)} searches "
                   f"(will batch into {(len(search_terms) + 4) // 5} API call(s))")

        max_results = search_settings.get("max_results", 20)
        recency_filter = search_settings.get("search_recency_filter")

        # Handle empty string as None for recency filter
        if recency_filter == "":
            recency_filter = None

        try:
            # Execute all searches with optimized batching (up to 5 queries per call)
            results = await self.search_client.batch_search(
                queries=search_terms,
                max_results=max_results,
                search_recency_filter=recency_filter,
                include_domains=include_domains,
                exclude_domains=exclude_domains
            )

            # Check for errors
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"[SEARCH_MANAGER] Search {i+1} failed: {result}")
                else:
                    result_count = len(result.get('results', []))
                    logger.info(f"[SEARCH_MANAGER] Search {i+1} returned {result_count} results")

            return results

        except Exception as e:
            logger.error(f"[SEARCH_MANAGER] Error executing searches: {e}")
            raise

    async def evaluate_results(
        self,
        prompt: str,
        current_iteration: int,
        current_search_results: List[Dict[str, Any]],
        accumulated_results: List[Dict[str, Any]],
        model: str = "deepseek-v3.2",
        max_sources: int = 12
    ) -> Dict[str, Any]:
        """
        Evaluate search results and determine if more searches are needed.

        Args:
            prompt: Original user query
            current_iteration: Current iteration number (1-indexed)
            current_search_results: Results from current search iteration
            accumulated_results: All results from previous iterations
            model: Model to use for evaluation
            max_sources: Maximum number of sources to review (context-dependent: 8/12/18)

        Returns:
            Dict containing:
                - relevant_citations: List of citation indices
                - additional_search_needed: "low" | "medium" | "high"
                - next_search_terms: List of new search terms (if needed)
                - next_search_settings: Settings for next search (if needed)
                - reasoning: Explanation of assessment
                - model_response: Full model response with metadata
        """
        logger.info(f"[SEARCH_MANAGER] Evaluating results for iteration {current_iteration}")

        # Format current search results (titles + URLs only for quick scanning)
        formatted_current = self._format_search_results_concise(current_search_results)

        # Load evaluation prompt from file
        evaluation_prompt = self.prompt_loader.load_prompt(
            'result_evaluation',
            prompt=prompt,
            iteration=current_iteration,
            formatted_current_results=formatted_current,
            formatted_accumulated_results="",  # Removed - keeping evaluation simple
            max_sources=max_sources  # Context-dependent limit (8/12/18)
        )

        try:
            # Call AI model with evaluation schema
            response = await self.ai_client.call_structured_api(
                prompt=evaluation_prompt,
                schema=get_result_evaluation_schema(),
                model=model,
                use_cache=False,  # Cache disabled for DeepSeek calls
                max_web_searches=0,  # DeepSeek cannot use web search
                context=f"result_evaluation_iter{current_iteration}"
            )

            # Extract structured data using centralized parsing
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            # Extract evaluation data (new simplified schema with reliability)
            relevant_count = data.get('relevant_count', 0)
            high_reliability = data.get('high_reliability_count', 0)
            medium_reliability = data.get('medium_reliability_count', 0)
            low_reliability = data.get('low_reliability_count', 0)
            best_source_indices = data.get('best_source_indices', [])
            has_sufficient = data.get('has_sufficient_info', False)
            missing_aspects = data.get('missing_aspects', [])
            next_terms = data.get('next_search_terms', [])

            # Context-aware cap: Limit sources based on context level (8/12/18)
            if len(best_source_indices) > max_sources:
                logger.info(f"[SEARCH_MANAGER] Capping sources: {len(best_source_indices)} → {max_sources} (context-dependent limit)")
                best_source_indices = best_source_indices[:max_sources]

            # Map to old format for compatibility
            need_level = "low" if has_sufficient else ("medium" if next_terms else "high")

            logger.info(f"[SEARCH_MANAGER] Evaluation: {relevant_count} relevant, "
                       f"Reliability: {high_reliability}H/{medium_reliability}M/{low_reliability}L, "
                       f"Best sources: {len(best_source_indices)}, Sufficient: {has_sufficient}")

            return {
                "relevant_citations": best_source_indices,  # Only pass forward BEST sources
                "relevant_count": relevant_count,
                "high_reliability_count": high_reliability,
                "medium_reliability_count": medium_reliability,
                "low_reliability_count": low_reliability,
                "additional_search_needed": need_level,
                "next_search_terms": next_terms,
                "next_search_settings": {"max_results": 20, "search_recency_filter": ""},
                "reasoning": f"Found {relevant_count} relevant ({high_reliability}H/{medium_reliability}M/{low_reliability}L). " +
                           (f"Sufficient info." if has_sufficient else f"Missing: {', '.join(missing_aspects)}"),
                "model_response": response
            }

        except Exception as e:
            logger.error(f"[SEARCH_MANAGER] Error evaluating results: {e}")
            raise

    def _format_search_results_concise(self, search_results: List[Dict[str, Any]]) -> str:
        """
        Format search results for triage evaluation.
        Extracts: title + headings + first/last sentence per section.

        Args:
            search_results: List of search results from Perplexity API

        Returns:
            Formatted string with title, headings, and key sentences
        """
        formatted = ""
        for search_result in search_results:
            if isinstance(search_result, Exception):
                continue

            results = search_result.get('results', [])
            for i, result in enumerate(results):
                title = result.get('title', 'No title')
                url = result.get('url', 'No URL')
                snippet = result.get('snippet', '')

                formatted += f"\n[{i}] {title}\n"
                formatted += f"URL: {url}\n"

                # Extract structure from snippet
                if snippet:
                    extracted = self._extract_snippet_structure(snippet)
                    if extracted:
                        formatted += f"Content:\n{extracted}\n"

                formatted += "\n"

        return formatted

    def _extract_snippet_structure(self, snippet: str) -> str:
        """
        Extract headings + first/last sentence per section from snippet.

        Args:
            snippet: Full text snippet from search result

        Returns:
            Formatted string with headings and key sentences
        """
        if not snippet:
            return ""

        lines = snippet.split('\n')
        extracted = []
        current_section = []

        for line in lines:
            line = line.strip()
            if not line:
                # Empty line - might be section boundary
                if current_section:
                    # Extract first and last sentence from section
                    section_text = ' '.join(current_section)
                    sentences = [s.strip() for s in section_text.split('. ') if s.strip()]
                    if sentences:
                        if len(sentences) == 1:
                            extracted.append(f"  - {sentences[0]}")
                        else:
                            extracted.append(f"  - {sentences[0]}")
                            if sentences[-1] != sentences[0]:
                                extracted.append(f"  - ... {sentences[-1]}")
                    current_section = []
                continue

            # Check if line looks like a heading (short, possibly ends with :, or all caps)
            is_heading = (
                len(line) < 80 and
                (line.endswith(':') or line.isupper() or
                 (len(line.split()) < 10 and not line.endswith('.')))
            )

            if is_heading:
                # Save previous section
                if current_section:
                    section_text = ' '.join(current_section)
                    sentences = [s.strip() for s in section_text.split('. ') if s.strip()]
                    if sentences:
                        if len(sentences) == 1:
                            extracted.append(f"  - {sentences[0]}")
                        else:
                            extracted.append(f"  - {sentences[0]}")
                            if sentences[-1] != sentences[0]:
                                extracted.append(f"  - ... {sentences[-1]}")
                    current_section = []

                # Add heading
                extracted.append(f"\n**{line}**")
            else:
                current_section.append(line)

        # Process last section
        if current_section:
            section_text = ' '.join(current_section)
            sentences = [s.strip() for s in section_text.split('. ') if s.strip()]
            if sentences:
                if len(sentences) == 1:
                    extracted.append(f"  - {sentences[0]}")
                else:
                    extracted.append(f"  - {sentences[0]}")
                    if sentences[-1] != sentences[0]:
                        extracted.append(f"  - ... {sentences[-1]}")

        return '\n'.join(extracted) if extracted else snippet[:500]  # Fallback to first 500 chars

    def _format_search_results_for_evaluation(self, search_results: List[Dict[str, Any]]) -> str:
        """
        Format search results for presentation to the evaluation model.
        (Legacy method - kept for compatibility)

        Args:
            search_results: List of search results from Perplexity API

        Returns:
            Formatted string for model consumption
        """
        formatted = ""
        citation_index = 0

        for search_result in search_results:
            if isinstance(search_result, Exception):
                continue

            results = search_result.get('results', [])
            for result in results:
                title = result.get('title', 'No title')
                url = result.get('url', 'No URL')
                snippet = result.get('snippet', 'No snippet')
                date = result.get('date', '')

                formatted += f"\n[{citation_index}] {title}\n"
                formatted += f"URL: {url}\n"
                if date:
                    formatted += f"Date: {date}\n"
                formatted += f"Snippet: {snippet}\n"

                citation_index += 1

        return formatted
