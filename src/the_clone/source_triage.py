#!/usr/bin/env python3
"""
Source Triage for Clone 2.
Evaluates search results per-search-term and selects 0-3 best diverse sources.
"""

import sys
import os
import asyncio
import json
import logging
from typing import Dict, Any, List

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../shared'))

from shared.ai_api_client import AIAPIClient
from shared.ai_client.utils import extract_structured_response
from the_clone.triage_schemas import get_source_triage_schema
from the_clone.text_labeler import TextLabeler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SourceTriage:
    """
    Ranks sources from search results by yield potential.
    Ranks ALL sources from best to worst for iterative extraction.
    """

    def __init__(self, ai_client: AIAPIClient = None, use_labeled_text: bool = True):
        """
        Initialize source triage.

        Args:
            ai_client: Optional AIAPIClient instance
            use_labeled_text: Whether to use labeled text format for triage (default True)
        """
        self.ai_client = ai_client or AIAPIClient()
        self.use_labeled_text = use_labeled_text
        self.text_labeler = TextLabeler() if use_labeled_text else None

    async def triage_all_searches(
        self,
        search_results: List[Dict[str, Any]],
        search_terms: List[str],
        query: str,
        existing_snippets: List[Dict],
        model: str = "claude-haiku-4-5",
        max_sources_per_search: int = 3,
        soft_schema: bool = False,
        clone_logger: Any = None,
        log_prompt_collapsed: bool = False
    ) -> List[List[int]]:
        """
        Triage ALL search results in PARALLEL.

        Args:
            search_results: List of search result dicts (one per search term)
            search_terms: List of search terms used
            query: Original user query
            existing_snippets: Snippets already collected
            model: Model to use for triage
            max_sources_per_search: Max sources to select per search (0-3)

        Returns:
            List of lists of selected indices, one list per search term
            Example: [[0,1,2], [1], [], [0,2]] means:
                     Search 1: sources 0,1,2
                     Search 2: source 1 only
                     Search 3: no sources (nothing new)
                     Search 4: sources 0,2
        """
        logger.info(f"[TRIAGE] Starting parallel triage for {len(search_results)} searches")

        # Create triage tasks for each search
        triage_tasks = []
        for i, (search_result, search_term) in enumerate(zip(search_results, search_terms)):
            if isinstance(search_result, Exception):
                triage_tasks.append(asyncio.create_task(self._return_empty()))
                continue

            task = self.triage_single_search(
                search_result=search_result,
                search_term=search_term,
                search_index=i + 1,
                query=query,
                existing_snippets=existing_snippets,
                model=model,
                max_sources=max_sources_per_search,
                soft_schema=soft_schema,
                clone_logger=clone_logger,
                log_prompt_collapsed=log_prompt_collapsed
            )
            triage_tasks.append(task)

        # Execute all triages in parallel
        triage_results = await asyncio.gather(*triage_tasks, return_exceptions=True)

        # Extract ranked indices
        ranked_indices_list = []
        for i, result in enumerate(triage_results):
            if isinstance(result, Exception):
                logger.error(f"[TRIAGE] Search {i+1} triage failed: {result}")
                ranked_indices_list.append([])
            else:
                indices = result.get('ranked_indices', [])
                ranked_indices_list.append(indices)

        logger.info(f"[TRIAGE] Parallel triage complete. All sources ranked.")

        return ranked_indices_list, triage_results  # Return both indices and full results for cost extraction

    async def _return_empty(self) -> Dict[str, Any]:
        """Return empty triage result for failed searches."""
        return {"ranked_indices": []}

    async def triage_single_search(
        self,
        search_result: Dict[str, Any],
        search_term: str,
        search_index: int,
        query: str,
        existing_snippets: List[Dict],
        model: str,
        max_sources: int,
        soft_schema: bool = False,
        clone_logger: Any = None,
        log_prompt_collapsed: bool = False
    ) -> Dict[str, Any]:
        """
        Triage a single search's results.

        Args:
            search_result: Search results dict with 'results' array
            search_term: The search term used
            search_index: Index of this search (1-indexed)
            query: Original user query
            existing_snippets: Already collected snippets
            model: Model to use for triage
            max_sources: Max sources to select (0-3)

        Returns:
            Dict with selected_indices (0-3 indices)
        """
        results = search_result.get('results', [])

        if not results:
            logger.info(f"[TRIAGE] Search {search_index} has no results")
            return {"selected_indices": []}

        logger.debug(f"[TRIAGE] Triaging search {search_index}: '{search_term[:60]}...' ({len(results)} results)")

        # Build triage prompt
        triage_prompt = self._build_triage_prompt(
            search_term=search_term,
            results=results,
            query=query,
            existing_snippets=existing_snippets,
            max_sources=max_sources
        )

        if clone_logger:
            clone_logger.log_section(f"Triage Prompt (Search {search_index})", triage_prompt, level=4, collapse=log_prompt_collapsed)

        try:
            # Call triage model
            response = await self.ai_client.call_structured_api(
                prompt=triage_prompt,
                schema=get_source_triage_schema(),
                model=model,
                use_cache=False,
                max_web_searches=0,
                context=f"source_triage_s{search_index}",
                soft_schema=soft_schema
            )

            # Save first triage prompt for debugging (search_index==1 only)
            if search_index == 1:
                try:
                    debug_dir = os.path.join(os.path.dirname(__file__), '../test_results/debug')
                    os.makedirs(debug_dir, exist_ok=True)
                    with open(os.path.join(debug_dir, 'last_triage_prompt.md'), 'w', encoding='utf-8') as f:
                        f.write(triage_prompt)
                except:
                    pass  # Don't fail if debug save fails

            # Extract ranked indices using centralized parsing
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            ranked_indices = data.get('ranked_indices', [])

            if clone_logger:
                 clone_logger.log_section(f"Triage Result (Search {search_index})", data, level=4, collapse=True)

            logger.info(f"[TRIAGE] Search {search_index}: Ranked {len(ranked_indices)} sources")
            if len(ranked_indices) == 0:
                logger.info(f"[TRIAGE DEBUG] Model response data: {data}")

            return {
                "ranked_indices": ranked_indices,
                "search_term": search_term,
                "search_index": search_index,
                "model_response": response  # For cost extraction
            }

        except Exception as e:
            logger.error(f"[TRIAGE] Search {search_index} triage failed: {e}")
            return {"ranked_indices": []}

    def _build_triage_prompt(
        self,
        search_term: str,
        results: List[Dict],
        query: str,
        existing_snippets: List[Dict],
        max_sources: int = None
    ) -> str:
        """
        Build triage prompt from template.

        Args:
            search_term: The search term for this batch
            results: Search results to triage
            query: Original user query
            existing_snippets: Already collected snippets
            max_sources: Max sources to select

        Returns:
            Formatted prompt string
        """
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__),
            'prompts',
            'source_triage.md'
        )

        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # Format sources for evaluation
        formatted_sources = self._format_sources_for_triage(results)

        # Format existing snippets
        formatted_existing = self._format_existing_snippets(existing_snippets)

        # Fill template (max_sources not used in new ranking prompt)
        prompt = template.format(
            query=query,
            search_term=search_term,
            source_count=len(results),
            formatted_sources=formatted_sources,
            existing_snippet_count=len(existing_snippets),
            formatted_existing_snippets=formatted_existing or "(No snippets collected yet)"
        )

        return prompt

    def _format_sources_for_triage(self, results: List[Dict]) -> str:
        """Format sources with position, reliability, content preview, and date."""
        if not results:
            return "(No sources)"

        formatted = []
        for i, result in enumerate(results):
            title = result.get('title', 'No title')
            url = result.get('url', 'No URL')
            snippet = result.get('snippet', '')
            # Use date, fall back to last_updated if date not available
            source_date = result.get('date') or result.get('last_updated', '')

            # Use labeled text format for better structure visibility
            if self.use_labeled_text and self.text_labeler and snippet:
                preview = self._create_labeled_preview(snippet)
            else:
                # Fallback to old preview format
                preview = self._extract_content_preview(snippet)

            # Build source info with date
            source_info = f"[{i}] {title}\n    URL: {url}\n"
            if source_date:
                source_info += f"    Date: {source_date}\n"
            source_info += f"    Preview:\n{preview}\n"

            formatted.append(source_info)

        return '\n'.join(formatted)

    def _create_labeled_preview(self, snippet: str) -> str:
        """
        Create labeled preview showing structure and first/last sentences.
        More informative than simple first/last for triage.
        """
        if not snippet:
            return "    (No content)"

        try:
            labeled_text, structure = self.text_labeler.label_text(snippet)

            # Create compact preview
            preview_parts = []

            for section in structure.get('sections', []):
                heading = section.get('heading', '')
                sentences = section['sentences']
                sent_count = len(sentences)

                if sent_count == 0:
                    continue

                # Section header
                if heading:
                    preview_parts.append(f"    {section['id']}: {heading} ({sent_count} sentences)")
                else:
                    preview_parts.append(f"    {section['id']}: ({sent_count} sentences)")

                # Show first sentence
                sent_ids = list(sentences.keys())
                first_id = sent_ids[0]
                first_text = sentences[first_id]['text'][:100]
                preview_parts.append(f"      {first_id}: {first_text}...")

                # Show last sentence if different
                if len(sent_ids) > 1:
                    last_id = sent_ids[-1]
                    last_text = sentences[last_id]['text'][:100]
                    preview_parts.append(f"      {last_id}: {last_text}...")

            return '\n'.join(preview_parts) if preview_parts else "    (No content)"

        except Exception as e:
            logger.warning(f"[TRIAGE] Failed to create labeled preview: {e}, using fallback")
            return self._extract_content_preview(snippet)

    def _extract_content_preview(self, text: str, max_chars: int = 300) -> str:
        """Extract headings + first/last sentences from text."""
        if not text:
            return "    (No content)"

        # Simple extraction: first and last sentence
        sentences = [s.strip() for s in text.split('. ') if s.strip()]

        if not sentences:
            return f"    {text[:max_chars]}"

        if len(sentences) == 1:
            return f"    - {sentences[0][:max_chars]}"

        first = sentences[0][:150]
        last = sentences[-1][:150]

        if first == last:
            return f"    - {first}"
        else:
            return f"    - {first}\n    - ... {last}"

    def _format_existing_snippets(self, snippets: List[Dict]) -> str:
        """Format existing snippets for triage context."""
        if not snippets:
            return ""

        # Group by source
        by_source = {}
        for snippet in snippets:
            snippet_id = snippet.get('id', 'Unknown')
            parts = snippet_id.split('.')
            if len(parts) >= 3:
                source_prefix = '.'.join(parts[:3])
            else:
                source_prefix = snippet_id

            if source_prefix not in by_source:
                by_source[source_prefix] = {
                    'title': snippet.get('_source_title', 'Unknown'),
                    'reliability': snippet.get('_source_reliability', 'M')[0],
                    'count': 0
                }
            by_source[source_prefix]['count'] += 1

        # Format
        formatted = []
        for source_prefix, data in list(by_source.items())[:5]:
            formatted.append(f"[{source_prefix}-{data['reliability']}] {data['title']} ({data['count']} quotes)")

        if len(by_source) > 5:
            formatted.append(f"... and {len(by_source) - 5} more sources")

        return '\n'.join(formatted)
