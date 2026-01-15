#!/usr/bin/env python3
"""
The Clone 2 - Strategy-Based Architecture.
Clean implementation with breadth/depth-based strategies.
"""

import sys
import os
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../shared'))

from shared.ai_api_client import AIAPIClient
from the_clone.perplexity_search import PerplexitySearchClient
from the_clone.search_manager import SearchManager
from the_clone.strategy_loader import get_strategy, get_global_limits, get_default_models, should_stop_iteration
from the_clone.source_triage import SourceTriage
from the_clone.snippet_extractor_streamlined import SnippetExtractorStreamlined
from the_clone.unified_synthesizer import UnifiedSynthesizer
from the_clone.initial_decision import InitialDecision

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TheClone2Refined:
    """
    The Clone 2 - Strategy-based architecture.

    Strategies:
    - Targeted: narrow+shallow (find specific fact, iterate until 1 reliable snippet)
    - Focused Deep: narrow+deep (detailed on one topic, pull 10 sources)
    - Survey: broad+shallow (list many aspects, pull 12 sources)
    - Comprehensive: broad+deep (detailed on many aspects, pull 15 sources)
    """

    def __init__(
        self,
        ai_client: AIAPIClient = None,
        search_client: PerplexitySearchClient = None
    ):
        """Initialize The Clone 2 Refined."""
        self.ai_client = ai_client or AIAPIClient()
        self.search_client = search_client or PerplexitySearchClient()
        self.search_manager = SearchManager(
            ai_client=self.ai_client,
            search_client=self.search_client
        )
        self.initial_decision = InitialDecision(ai_client=self.ai_client)
        self.source_triage = SourceTriage(ai_client=self.ai_client)
        self.snippet_extractor = SnippetExtractorStreamlined(ai_client=self.ai_client)
        self.unified_synthesizer = UnifiedSynthesizer(ai_client=self.ai_client)

    async def query(
        self,
        prompt: str,
        search_context: str = "medium",
        schema: Optional[Dict] = None,
        config_variant: str = "common",
        debug_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute query with strategy-based architecture.

        Args:
            prompt: User's query
            schema: Optional schema for synthesis
            debug_dir: Optional directory for debug output

        Returns:
            Dict containing answer, citations, and metadata
        """
        start_time = datetime.now()

        logger.debug("=" * 80)
        logger.debug(f"[CLONE] Query: {prompt[:100]}...")
        logger.debug("=" * 80)

        # Load configuration
        models = get_default_models()
        global_limits = get_global_limits()

        # Save debug config
        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, '00_config.json'), 'w') as f:
                json.dump({'query': prompt, 'models': models, 'limits': global_limits}, f, indent=2)

        # Cost tracking
        costs = {'initial': 0.0, 'search': 0.0, 'triage': 0.0, 'extraction': 0.0, 'synthesis': 0.0}

        # Step 1: Initial Decision
        logger.debug("\n[CLONE] Step 1: Initial Decision...")
        initial_result = await self.initial_decision.make_decision(
            query=prompt,
            model=models['initial_decision'],
            soft_schema=True,
            debug_dir=debug_dir
        )

        decision = initial_result.get('decision', 'need_search')
        costs['initial'] = self._extract_cost(initial_result.get('model_response', {}))

        if decision == "answer_directly":
            logger.debug("[CLONE] Answered directly - no search needed")
            return self._build_direct_answer_response(prompt, initial_result, costs)

        # Get strategy
        breadth = initial_result.get('breadth', 'narrow')
        depth = initial_result.get('depth', 'shallow')
        strategy = get_strategy(breadth, depth)
        search_terms = initial_result.get('search_terms', [prompt])

        logger.debug(f"[CLONE] Strategy: {strategy['name']} (breadth={breadth}, depth={depth})")
        logger.debug(f"[CLONE] Params: batch={strategy['sources_per_batch']}, mode={strategy['extraction_mode']}, max_snippets={strategy['max_snippets_per_source']}, min_p={strategy['min_p_threshold']}")
        logger.debug(f"[CLONE] Search terms: {search_terms}")

        # Step 2: Search
        logger.debug(f"\n[CLONE] Step 2: Executing {len(search_terms)} searches...")
        search_results = await self.search_manager.execute_searches(
            search_terms=search_terms,
            search_settings={'max_results': 10}
        )
        costs['search'] = len(search_terms) * 0.005  # Perplexity cost per search

        # Step 3: Triage (rank ALL sources)
        logger.debug(f"\n[CLONE] Step 3: Ranking sources...")
        ranked_lists, triage_results = await self.source_triage.triage_all_searches(
            search_results=search_results,
            search_terms=search_terms,
            query=prompt,
            existing_snippets=[],
            model=models['triage'],
            soft_schema=True
        )

        # Extract triage costs
        for result in triage_results:
            if not isinstance(result, Exception):
                costs['triage'] += self._extract_cost(result.get('model_response', {}))

        # Build ranked source pool
        ranked_sources = self._build_ranked_source_pool(search_results, ranked_lists, search_terms)
        logger.debug(f"[CLONE] Ranked {len(ranked_sources)} relevant sources")

        if len(ranked_sources) == 0:
            logger.debug("[CLONE] No relevant sources found")
            return self._build_empty_response(prompt, search_terms, costs)

        # Step 4: Iterative Extraction
        logger.debug(f"\n[CLONE] Step 4: Iterative extraction (max {global_limits['max_iterations']} iterations)...")
        all_snippets = []
        sources_pulled = 0

        for iteration in range(1, global_limits['max_iterations'] + 1):
            logger.debug(f"\n[CLONE] Iteration {iteration}/{global_limits['max_iterations']}")

            # Determine batch
            batch_size = strategy['sources_per_batch']
            batch_end = min(sources_pulled + batch_size, len(ranked_sources))
            sources_this_batch = ranked_sources[sources_pulled:batch_end]

            if len(sources_this_batch) == 0:
                logger.debug("[CLONE] No more sources to pull")
                break

            logger.debug(f"[CLONE] Pulling sources {sources_pulled}-{batch_end-1} ({len(sources_this_batch)} sources)")

            # Extract from batch
            extraction_tasks = []
            for idx, source in enumerate(sources_this_batch):
                snippet_id_prefix = f"S{iteration}.{source['_search_index']}.{sources_pulled + idx}"
                task = self.snippet_extractor.extract_from_source(
                    source=source,
                    query=prompt,
                    snippet_id_prefix=snippet_id_prefix,
                    all_search_terms=search_terms,
                    primary_search_index=source['_search_index'],
                    model=models['extraction'],
                    soft_schema=True,
                    min_quality_threshold=strategy['min_p_threshold'],
                    extraction_mode=strategy['extraction_mode'],
                    max_snippets_per_source=strategy['max_snippets_per_source']
                )
                extraction_tasks.append(task)

            results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

            # Collect snippets and costs
            new_snippets = []
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"[CLONE] Extraction error: {result}")
                    continue
                new_snippets.extend(result.get('snippets', []))
                costs['extraction'] += self._extract_cost(result.get('model_response', {}))

            all_snippets.extend(new_snippets)
            sources_pulled = batch_end

            logger.debug(f"[CLONE] Extracted {len(new_snippets)} snippets (total: {len(all_snippets)})")
            if all_snippets:
                avg_p = sum(s.get('p', 0.5) for s in all_snippets) / len(all_snippets)
                high_p = sum(1 for s in all_snippets if s.get('p', 0) >= 0.85)
                logger.debug(f"[CLONE] Quality: avg_p={avg_p:.2f}, high_quality={high_p}/{len(all_snippets)}")

            # Check stop condition
            if should_stop_iteration(all_snippets, strategy):
                logger.debug(f"[CLONE] Stop condition met ({strategy.get('stop_condition')})")
                break

            if sources_pulled >= len(ranked_sources):
                logger.debug(f"[CLONE] All sources exhausted")
                break

        # Step 5: Synthesis
        logger.debug(f"\n[CLONE] Step 5: Synthesis from {len(all_snippets)} snippets...")

        # Map strategy to old context for synthesis guidance (temporary until synthesis updated)
        context_map = {
            'targeted': 'low',
            'focused_deep': 'medium',
            'survey': 'medium',
            'comprehensive': 'high'
        }
        synthesis_context = context_map.get(strategy['name'], 'medium')

        synthesis_result = await self.unified_synthesizer.evaluate_and_synthesize(
            query=prompt,
            snippets=all_snippets,
            context=synthesis_context,
            iteration=1,
            is_last_iteration=True,
            schema=schema,
            model=models['synthesis'],
            search_terms=search_terms,
            debug_dir=debug_dir,
            soft_schema=True
        )

        costs['synthesis'] = self._extract_cost(synthesis_result.get('model_response', {}))

        # Build response
        total_time = (datetime.now() - start_time).total_seconds()
        total_cost = sum(costs.values())

        logger.info(f"\n[CLONE] Complete in {total_time:.1f}s, Cost: ${total_cost:.4f}")
        logger.debug(f"[CLONE] Snippets: {len(all_snippets)}, Citations: {len(synthesis_result.get('citations', []))}")

        return {
            "answer": synthesis_result.get('answer', {}),
            "citations": synthesis_result.get('citations', []),
            "synthesis_prompt": synthesis_result.get('synthesis_prompt', ''),
            "metadata": {
                "query": prompt,
                "strategy": strategy['name'],
                "breadth": breadth,
                "depth": depth,
                "search_terms": search_terms,
                "iterations": iteration,
                "total_snippets": len(all_snippets),
                "citations_count": len(synthesis_result.get('citations', [])),
                "sources_pulled": sources_pulled,
                "total_time_seconds": total_time,
                "total_cost": total_cost,
                "cost_breakdown": costs
            }
        }

    def _extract_cost(self, model_response: Dict) -> float:
        """Extract cost from model response."""
        enhanced = model_response.get('enhanced_data', {})
        costs = enhanced.get('costs', {}).get('actual', {})
        return costs.get('total_cost', 0.0)

    def _build_ranked_source_pool(
        self,
        search_results: List,
        ranked_lists: List[List[int]],
        search_terms: List[str]
    ) -> List[Dict]:
        """Build ranked source pool from triage results."""
        pool = []
        for search_idx, (search_result, ranked_indices) in enumerate(zip(search_results, ranked_lists)):
            if isinstance(search_result, Exception):
                continue

            results = search_result.get('results', [])
            for rank_position, source_idx in enumerate(ranked_indices):
                if 0 <= source_idx < len(results):
                    source = results[source_idx].copy()
                    source['_search_term'] = search_terms[search_idx]
                    source['_search_index'] = search_idx + 1
                    source['_rank_position'] = rank_position
                    pool.append(source)

        return pool

    def _build_direct_answer_response(self, prompt: str, initial_result: Dict, costs: Dict) -> Dict:
        """Build response for direct answer (no search)."""
        return {
            "answer": {},
            "citations": [],
            "metadata": {
                "query": prompt,
                "decision": "answer_directly",
                "iterations": 0,
                "total_cost": costs['initial'],
                "cost_breakdown": costs
            }
        }

    def _build_empty_response(self, prompt: str, search_terms: List[str], costs: Dict) -> Dict:
        """Build response when no sources found."""
        return {
            "answer": {},
            "citations": [],
            "metadata": {
                "query": prompt,
                "search_terms": search_terms,
                "total_snippets": 0,
                "total_cost": sum(costs.values()),
                "cost_breakdown": costs
            }
        }
