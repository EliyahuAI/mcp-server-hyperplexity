#!/usr/bin/env python3
"""
Streamlined Snippet Extractor for Clone 2.
Extracts only essential quotes from sources.
"""

import sys
import os
import json
import logging
from typing import Dict, Any, List

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../shared'))

from shared.ai_api_client import AIAPIClient
from shared.ai_client.utils import extract_structured_response
from the_clone.snippet_schemas import get_snippet_extraction_schema

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SnippetExtractorStreamlined:
    """
    Streamlined extractor - returns only essential quotes.
    No topics, no relevance, no metadata - just quotes.
    """

    def __init__(self, ai_client: AIAPIClient = None):
        """Initialize the streamlined extractor.

        Args:
            ai_client: AIAPIClient instance
        """
        self.ai_client = ai_client or AIAPIClient()

    async def extract_from_source(
        self,
        source: Dict[str, Any],
        query: str,
        snippet_id_prefix: str,
        all_search_terms: List[str],
        primary_search_index: int,
        model: str = "deepseek-v3.2",
        soft_schema: bool = False,
        min_quality_threshold: float = 0.0,
        extraction_mode: str = "simple_facts",
        max_snippets_per_source: int = 5
    ) -> Dict[str, Any]:
        """
        Extract essential quotes from a single source for ALL search terms.
        Can extract off-topic quotes if source has info for other search terms.

        Args:
            source: Search result dict
            query: User's query
            snippet_id_prefix: Prefix for snippet IDs (e.g., "S1.2.3")
            all_search_terms: List of ALL search terms from this iteration
            primary_search_index: Which search term found this source (1-indexed)
            model: Model to use for extraction (also performs validation)
            soft_schema: Whether to use soft schema mode
            min_quality_threshold: Minimum p score to keep snippets (0.0 = keep all)
            extraction_mode: "simple_facts" (targeted) or "nuanced" (detailed)
            max_snippets_per_source: Maximum snippets to extract from this source

        Returns:
            Dict with:
                - snippets: List of snippet dicts with IDs and search_ref
                - source_info: Title, URL, reliability
        """
        source_title = source.get('title', 'No title')
        source_url = source.get('url', 'No URL')
        source_text = source.get('snippet', '')
        source_reliability = source.get('reliability', 'MEDIUM')
        # Use date, fall back to last_updated if date not available
        source_date = source.get('date') or source.get('last_updated', '')
        # Get search term that found this source
        source_search_term = source.get('_search_term', '')

        logger.debug(f"[EXTRACTOR] Extracting from: {source_title[:60]}...")
        logger.info(f"[EXTRACTOR_DEBUG] Source _search_term: '{source_search_term}'")

        # Build extraction prompt with all search terms
        extraction_prompt = self._build_prompt(
            query=query,
            source_title=source_title,
            source_url=source_url,
            source_text=source_text,
            source_reliability=source_reliability,
            source_date=source_date,
            all_search_terms=all_search_terms,
            primary_search_index=primary_search_index,
            extraction_mode=extraction_mode,
            max_snippets=max_snippets_per_source
        )

        try:
            # Call extraction model
            response = await self.ai_client.call_structured_api(
                prompt=extraction_prompt,
                schema=get_snippet_extraction_schema(),
                model=model,
                use_cache=False,
                max_web_searches=0,
                context=f"extract_{snippet_id_prefix}",
                soft_schema=soft_schema
            )

            # Extract quotes using centralized parsing
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            quotes_by_search = data.get('quotes_by_search', {})

            # Assign snippet IDs to each quote, organized by search term
            # Quotes now come as objects with {text, p, reason}
            snippets = []
            total_quotes = 0

            for search_num_str, quotes in quotes_by_search.items():
                search_num = int(search_num_str)

                for i, quote_obj in enumerate(quotes):
                    # Handle both old format (string) and new format (object)
                    if isinstance(quote_obj, str):
                        # Old format - assign default validation
                        quote_text = quote_obj
                        p_score = 0.50
                        reason = "OK"
                    else:
                        # New format with validation
                        quote_text = quote_obj.get('text', '')
                        p_score = quote_obj.get('p', 0.50)
                        reason = quote_obj.get('reason', 'OK')

                    # Filter by quality threshold
                    if p_score < min_quality_threshold:
                        logger.debug(f"[EXTRACTOR] Filtered quote (p={p_score:.2f} < {min_quality_threshold}): {quote_text[:50]}...")
                        continue

                    # Use p-score in snippet ID instead of source reliability
                    snippet_id = f"{snippet_id_prefix}.{total_quotes}-p{p_score:.2f}"

                    # Add context marker for off-topic quotes
                    if search_num != primary_search_index and len(all_search_terms) > search_num - 1:
                        # Off-topic quote - add search term reference for context
                        search_term = all_search_terms[search_num - 1]
                        # Extract key topic from search term (simplified)
                        topic = search_term.split()[0:3]  # First 3 words
                        topic_str = ' '.join(topic)
                        quote_with_context = f"[re: {topic_str}] {quote_text}"
                    else:
                        quote_with_context = quote_text

                    snippet = {
                        "id": snippet_id,
                        "text": quote_with_context,
                        "p": p_score,
                        "validation_reason": reason,
                        "search_ref": search_num,
                        "_source_title": source_title,
                        "_source_url": source_url,
                        "_source_date": source_date,
                        "_source_reliability": source_reliability,
                        "_search_term": source_search_term,
                        "_primary_search": primary_search_index,
                        "_is_off_topic": search_num != primary_search_index
                    }
                    snippets.append(snippet)
                    total_quotes += 1

            logger.info(f"[EXTRACTOR] {snippet_id_prefix}: {len(snippets)} quotes across {len(quotes_by_search)} search terms (threshold: {min_quality_threshold})")

            # Calculate validation stats
            if snippets:
                avg_p = sum(s["p"] for s in snippets) / len(snippets)
                high_q = sum(1 for s in snippets if s["p"] >= 0.85)
                low_q = sum(1 for s in snippets if s["p"] <= 0.15)
                logger.info(f"[EXTRACTOR] Quality: avg_p={avg_p:.2f}, high={high_q}, low={low_q}")

            return {
                "snippets": snippets,
                "source_info": {
                    "title": source_title,
                    "url": source_url,
                    "reliability": source_reliability
                },
                "model_response": response  # For cost extraction
            }

        except Exception as e:
            logger.error(f"[EXTRACTOR] {snippet_id_prefix} failed: {e}")
            return {
                "snippets": [],
                "source_info": {
                    "title": source_title,
                    "url": source_url,
                    "reliability": source_reliability
                },
                "error": str(e)
            }

    def _build_prompt(
        self,
        query: str,
        source_title: str,
        source_url: str,
        source_text: str,
        source_reliability: str,
        source_date: str,
        all_search_terms: List[str],
        primary_search_index: int,
        extraction_mode: str = "simple_facts",
        max_snippets: int = 5
    ) -> str:
        """Build extraction prompt with all search terms."""
        template_path = os.path.join(
            os.path.dirname(__file__),
            'prompts',
            'snippet_extraction_streamlined.md'
        )

        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # Format all search terms with numbers
        formatted_terms = []
        for i, term in enumerate(all_search_terms, 1):
            marker = " ← THIS SOURCE" if i == primary_search_index else ""
            formatted_terms.append(f"{i}. {term}{marker}")

        all_search_terms_formatted = '\n'.join(formatted_terms)

        # Mode guidance
        mode_guidance = {
            "simple_facts": "Extract ONLY concrete atomic facts (numbers, dates, entities). Prefer brevity.",
            "nuanced": "Extract facts with context, explanations, and methodology when relevant."
        }.get(extraction_mode, "Extract essential quotes.")

        prompt = template.format(
            query=query,
            source_title=source_title,
            source_url=source_url,
            source_date=source_date or "Unknown",
            primary_search_num=primary_search_index,
            all_search_terms_formatted=all_search_terms_formatted,
            source_full_text=source_text,
            extraction_mode_guidance=mode_guidance,
            max_snippets=max_snippets
        )

        return prompt
