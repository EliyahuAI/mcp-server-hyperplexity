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
from the_clone.strategy_loader import get_model_with_backups
from the_clone.relevance_scorer import RelevanceScorer

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
        self.relevance_scorer = RelevanceScorer(positive_weight=1.0, negative_weight=5.0)

    async def triage_all_searches(
        self,
        search_results: List[Dict[str, Any]],
        search_terms: List[str],
        query: str,
        existing_snippets: List[Dict],
        positive_keywords: List[str] = None,
        negative_keywords: List[str] = None,
        model: str = "claude-haiku-4-5",
        max_sources_per_search: int = 3,
        soft_schema: bool = False,
        clone_logger: Any = None,
        log_prompt_collapsed: bool = False,
        provider: str = None
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
        logger.debug(f"[TRIAGE] Starting parallel triage for {len(search_results)} searches")

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
                positive_keywords=positive_keywords or [],
                negative_keywords=negative_keywords or [],
                model=model,
                max_sources=max_sources_per_search,
                soft_schema=soft_schema,
                clone_logger=clone_logger,
                log_prompt_collapsed=log_prompt_collapsed,
                provider=provider
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

        logger.debug(f"[TRIAGE] Parallel triage complete. All sources ranked.")

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
        positive_keywords: List[str],
        negative_keywords: List[str],
        model: str,
        max_sources: int,
        soft_schema: bool = False,
        clone_logger: Any = None,
        log_prompt_collapsed: bool = False,
        provider: str = None
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
            logger.debug(f"[TRIAGE] Search {search_index} has no results")
            return {"selected_indices": []}

        logger.debug(f"[TRIAGE] Triaging search {search_index}: '{search_term[:60]}...' ({len(results)} results)")

        # Score results based on rank + keywords
        scored_results = self.relevance_scorer.score_search_results(
            results=results,
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords
        )

        # Build triage prompt with scoring information
        triage_prompt = self._build_triage_prompt(
            search_term=search_term,
            results=results,
            scored_results=scored_results,
            query=query,
            existing_snippets=existing_snippets,
            max_sources=max_sources,
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords
        )

        if clone_logger:
            clone_logger.log_section(f"Triage Prompt (Search {search_index})", triage_prompt, level=4, collapse=log_prompt_collapsed)

        try:
            # Get model with backups to override ai_client defaults
            model_chain = get_model_with_backups(model, provider)

            # Call triage model
            response = await self.ai_client.call_structured_api(
                prompt=triage_prompt,
                schema=get_source_triage_schema(),
                model=model_chain,
                use_cache=False,
                max_web_searches=0,
                context=f"source_triage_s{search_index}",
                soft_schema=soft_schema
            )

            # Save first triage prompt for debugging (search_index==1 only)
            if search_index == 1:
                try:
                    # Use /tmp in Lambda (read-only filesystem), else local test_results
                    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
                        debug_dir = '/tmp/debug'
                    else:
                        debug_dir = os.path.join(os.path.dirname(__file__), '../test_results/debug')
                    os.makedirs(debug_dir, exist_ok=True)
                    with open(os.path.join(debug_dir, 'last_triage_prompt.md'), 'w', encoding='utf-8') as f:
                        f.write(triage_prompt)
                except:
                    pass  # Don't fail if debug save fails

            # Log model attempts if backups were used
            if clone_logger and response.get('attempted_models'):
                clone_logger.log_model_attempts(response['attempted_models'], f"Triage Search {search_index}")

            # Extract ranked indices using centralized parsing
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            ranked_indices = data.get('ranked_indices', [])

            if clone_logger:
                 clone_logger.log_section(f"Triage Result (Search {search_index})", data, level=4, collapse=True)

            logger.debug(f"[TRIAGE] Search {search_index}: Ranked {len(ranked_indices)} sources")
            if len(ranked_indices) == 0:
                logger.debug(f"[TRIAGE] Model response data: {data}")

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
        scored_results: List[Dict],
        query: str,
        existing_snippets: List[Dict],
        max_sources: int = None,
        positive_keywords: List[str] = None,
        negative_keywords: List[str] = None
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

        # Format keyword info section
        keyword_info = self._format_keyword_info(positive_keywords or [], negative_keywords or [])

        # Format sources with integrated keyword sentences
        formatted_sources = self._format_sources_with_keywords(
            results, scored_results, positive_keywords or [], negative_keywords or []
        )

        # Format existing snippets
        formatted_existing = self._format_existing_snippets(existing_snippets)

        # Fill template
        prompt = template.format(
            query=query,
            search_term=search_term,
            keyword_info=keyword_info,
            source_count=len(results),
            formatted_sources=formatted_sources,
            existing_snippet_count=len(existing_snippets),
            formatted_existing_snippets=formatted_existing or "(None yet)"
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

    def _format_keyword_info(self, positive_keywords: List[str], negative_keywords: List[str]) -> str:
        """Format keyword information for triage prompt header."""
        if not positive_keywords and not negative_keywords:
            return ""

        lines = ["**Keywords for Relevance Assessment:**"]
        if positive_keywords:
            lines.append(f"  Positive: {', '.join(positive_keywords)}")
        if negative_keywords:
            lines.append(f"  Negative: {', '.join(negative_keywords)}")

        return '\n'.join(lines)

    def _format_sources_with_keywords(
        self,
        results: List[Dict],
        scored_results: List[Dict],
        positive_keywords: List[str],
        negative_keywords: List[str]
    ) -> str:
        """Format sources with integrated keyword information and scores."""
        if not results:
            return "(No sources)"

        formatted = []
        for i, result in enumerate(results):
            score_info = scored_results[i]
            title = result.get('title', 'No title')[:70]
            date = result.get('date') or result.get('last_updated', '')
            snippet = result.get('snippet', '')

            # Build header with score if keywords were used
            source_text = f"[{i}] {title}"
            if date:
                source_text += f" ({date})"

            # Add score info if keyword adjustment exists
            if score_info['keyword_adjustment'] != 0:
                source_text += f" | Score: {score_info['relevance_score']:.0f} ({score_info['keyword_adjustment']:+.0f})"

            # Extract first substantive sentence
            sentences = [s.strip() for s in snippet.split('. ') if s.strip() and len(s.strip()) > 20]
            preview = sentences[0][:120] + "..." if sentences else "(No preview)"
            source_text += f"\n    {preview}"

            # Add keyword-matching sentence if exists
            if score_info['keyword_adjustment'] != 0:
                # Find best matching sentence
                for sentence in sentences[1:]:  # Skip first (already shown)
                    sentence_lower = sentence.lower()
                    matched_kw = []

                    for kw in positive_keywords:
                        if kw.lower() in sentence_lower:
                            matched_kw.append(f"+{kw}")
                    for kw in negative_keywords:
                        if kw.lower() in sentence_lower:
                            matched_kw.append(f"-{kw}")

                    if len(matched_kw) >= 2 or any('-' in k for k in matched_kw):  # Multiple matches or negative
                        kw_str = ', '.join(matched_kw[:3])
                        if len(matched_kw) > 3:
                            kw_str += f" +{len(matched_kw)-3} more"
                        source_text += f"\n    [{kw_str}] \"{sentence[:100]}...\""
                        break

            formatted.append(source_text)

        return '\n\n'.join(formatted)

    def _extract_keyword_highlights(
        self,
        results: List[Dict],
        scored_results: List[Dict],
        positive_keywords: List[str],
        negative_keywords: List[str]
    ) -> str:
        """
        Show keyword-matched sentences ONLY for sources with non-zero keyword scores.
        Concise format - 1-2 best matching sentences per source.
        """
        if not positive_keywords and not negative_keywords:
            return ""

        lines = ["**Keyword Highlights:**"]

        # Only show sources with keyword matches
        sources_with_matches = []
        for idx, scored in enumerate(scored_results):
            if scored['keyword_adjustment'] != 0:
                sources_with_matches.append((idx, scored))

        if not sources_with_matches:
            return "**Keyword Highlights:** (No keyword matches found)"

        # Sort by absolute keyword impact
        sources_with_matches.sort(key=lambda x: abs(x[1]['keyword_adjustment']), reverse=True)

        # Show top sources with keyword matches (limit to 5)
        for idx, score_info in sources_with_matches[:5]:
            result = results[idx]
            km = score_info['keyword_matches']
            adj = score_info['keyword_adjustment']
            final_score = score_info['relevance_score']

            title = result.get('title', '')[:60]
            snippet = result.get('snippet', '')

            lines.append(f"\n[{idx}] {title}")
            lines.append(f"    Score: {final_score:.1f} ({adj:+.1f} from keywords)")

            # Find best matching sentence
            sentences = [s.strip() for s in snippet.split('. ') if s.strip()]
            best_match = None

            for sentence in sentences:
                sentence_lower = sentence.lower()
                match_count = sum(1 for kw in (positive_keywords + negative_keywords) if kw.lower() in sentence_lower)
                if match_count > 0:
                    # Check if negative
                    has_negative = any(kw.lower() in sentence_lower for kw in negative_keywords)
                    if has_negative or match_count >= 2:  # Show if negative OR multiple positives
                        best_match = sentence[:120]
                        break

            if best_match:
                # Find which keywords matched
                matched = []
                for kw in positive_keywords:
                    if kw.lower() in best_match.lower():
                        matched.append(f"+{kw}")
                for kw in negative_keywords:
                    if kw.lower() in best_match.lower():
                        matched.append(f"-{kw}")

                kw_str = ', '.join(matched[:3])
                if len(matched) > 3:
                    kw_str += f" (+{len(matched)-3} more)"
                lines.append(f"    [{kw_str}] \"{best_match}...\"")

        if len(sources_with_matches) > 5:
            lines.append(f"\n... and {len(sources_with_matches) - 5} more sources with keyword matches")

        return '\n'.join(lines)

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
