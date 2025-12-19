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

# Lazy import for AIAPIClient to avoid circular dependency
# from shared.ai_api_client import AIAPIClient 

from the_clone.perplexity_search import PerplexitySearchClient
from the_clone.search_manager import SearchManager
from the_clone.strategy_loader import get_strategy, get_global_limits, get_default_models, get_models_for_tier, should_stop_iteration
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
    """

    def __init__(
        self,
        ai_client=None,
        search_client: PerplexitySearchClient = None
    ):
        """Initialize The Clone 2 Refined."""
        if ai_client is None:
            from shared.ai_api_client import AIAPIClient
            self.ai_client = AIAPIClient()
        else:
            self.ai_client = ai_client
            
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
        debug_dir: Optional[str] = None,
        model_override: Optional[str] = None,
        academic: bool = False,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        provider: str = "deepseek",
        use_baseten: bool = False,
        use_code_extraction: bool = True
    ) -> Dict[str, Any]:
        """
        Execute query with strategy-based architecture.

        Args:
            prompt: User's query
            schema: Optional schema for synthesis
            debug_dir: Optional directory for debug output
            model_override: Override all models (e.g., "claude-haiku-4-5")

        Returns:
            Dict containing answer, citations, and metadata
        """
        start_time = datetime.now()

        logger.info("=" * 80)
        logger.info(f"[CLONE] Query: {prompt[:100]}...")
        logger.info("=" * 80)
        logger.info(f"[CLONE] use_code_extraction: {use_code_extraction}")

        # Handle backwards compatibility: use_baseten=True → provider="baseten"
        if use_baseten:
            provider = "baseten"
            logger.info(f"[CLONE] use_baseten=True (backwards compat), setting provider='baseten'")

        # Load configuration
        if model_override:
            models = {
                'initial_decision': model_override if 'claude' in model_override else 'claude-sonnet-4-5',
                'triage': model_override,
                'extraction': model_override,
                'synthesis': model_override
            }
            use_soft_schema = 'deepseek' in model_override
            logger.info(f"[CLONE] Model override: {model_override}")
        else:
            models = get_default_models(provider)
            use_soft_schema = True

        global_limits = get_global_limits()

        logger.info(f"[CLONE] Provider: {provider}")

        # Save debug config
        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, '00_config.json'), 'w') as f:
                json.dump({'query': prompt, 'models': models, 'limits': global_limits}, f, indent=2)

        # Cost tracking
        costs = {'initial': 0.0, 'search': 0.0, 'triage': 0.0, 'extraction': 0.0, 'synthesis': 0.0}

        # Step 1: Initial Decision
        logger.info("\n[CLONE] Step 1: Initial Decision...")
        initial_result = await self.initial_decision.make_decision(
            query=prompt,
            model=models['initial_decision'],
            soft_schema=True,
            debug_dir=debug_dir
        )

        decision = initial_result.get('decision', 'need_search')
        costs['initial'] = self._extract_cost(initial_result.get('model_response', {}))

        if decision == "answer_directly":
            logger.warning("[CLONE] Direct answer not implemented - forcing search instead")
            # Direct answer path is incomplete, always use search
            decision = "need_search"
            # Fall through to search path

        # Get strategy and models
        breadth = initial_result.get('breadth', 'narrow')
        depth = initial_result.get('depth', 'shallow')
        synthesis_tier = initial_result.get('synthesis_tier', 'tier2')
        strategy = get_strategy(breadth, depth)
        search_terms = initial_result.get('search_terms', [prompt])

        # Get models for synthesis tier (unless overridden)
        if not model_override:
            models = get_models_for_tier(provider, synthesis_tier)
            use_soft_schema = 'deepseek' in models['synthesis'] or 'baseten' in models['synthesis']

        logger.info(f"[CLONE] Strategy: {strategy['name']} (breadth={breadth}, depth={depth})")
        logger.info(f"[CLONE] Synthesis tier: {synthesis_tier} (model: {models['synthesis']})")
        logger.info(f"[CLONE] Params: batch={strategy['sources_per_batch']}, mode={strategy['extraction_mode']}, max_snippets={strategy['max_snippets_per_source']}, min_p={strategy['min_p_threshold']}")
        logger.info(f"[CLONE] Search terms: {search_terms}")

        # Determine domain filters
        search_include_domains: Optional[List[str]] = None
        search_exclude_domains: Optional[List[str]] = None

        # Backdoor: include_domains=["academic"] triggers academic mode
        if include_domains and include_domains == ["academic"]:
            from the_clone.academic_domains import get_academic_domains
            search_include_domains = get_academic_domains()
            logger.info(f"[CLONE] Academic mode (backdoor) - using {len(search_include_domains)} academic domains")
        elif academic:
            from the_clone.academic_domains import get_academic_domains
            search_include_domains = get_academic_domains()
            logger.info(f"[CLONE] Academic mode - using {len(search_include_domains)} academic domains")
        elif include_domains:
            search_include_domains = include_domains
            logger.info(f"[CLONE] Using {len(search_include_domains)} included domains")
        elif exclude_domains:
            search_exclude_domains = exclude_domains
            logger.info(f"[CLONE] Using {len(search_exclude_domains)} excluded domains")

        # Step 2: Search
        logger.info(f"\n[CLONE] Step 2: Executing {len(search_terms)} searches...")
        search_results = await self.search_manager.execute_searches(
            search_terms=search_terms,
            search_settings={'max_results': 10},
            include_domains=search_include_domains,
            exclude_domains=search_exclude_domains
        )
        costs['search'] = len(search_terms) * 0.005  # Perplexity cost per search

        # Step 3: Triage (rank ALL sources)
        logger.info(f"\n[CLONE] Step 3: Ranking sources...")
        ranked_lists, triage_results = await self.source_triage.triage_all_searches(
            search_results=search_results,
            search_terms=search_terms,
            query=prompt,
            existing_snippets=[],
            model=models['triage'],
            soft_schema=use_soft_schema
        )

        # Extract triage costs
        for result in triage_results:
            if not isinstance(result, Exception):
                costs['triage'] += self._extract_cost(result.get('model_response', {}))

        # Build ranked source pool
        ranked_sources = self._build_ranked_source_pool(search_results, ranked_lists, search_terms)
        logger.info(f"[CLONE] Ranked {len(ranked_sources)} relevant sources")

        if len(ranked_sources) == 0:
            logger.info("[CLONE] No relevant sources found")
            return self._build_empty_response(prompt, search_terms, costs)

        # Step 4: Iterative Extraction
        logger.info(f"\n[CLONE] Step 4: Iterative extraction (max {global_limits['max_iterations']} iterations)...")
        all_snippets = []
        sources_pulled = 0

        for iteration in range(1, global_limits['max_iterations'] + 1):
            logger.info(f"\n[CLONE] Iteration {iteration}/{global_limits['max_iterations']}")

            # Determine batch
            batch_size = strategy['sources_per_batch']
            batch_end = min(sources_pulled + batch_size, len(ranked_sources))
            sources_this_batch = ranked_sources[sources_pulled:batch_end]

            if len(sources_this_batch) == 0:
                logger.info("[CLONE] No more sources to pull")
                break

            logger.info(f"[CLONE] Pulling sources {sources_pulled}-{batch_end-1} ({len(sources_this_batch)} sources)")

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
                    soft_schema=use_soft_schema,
                    min_quality_threshold=strategy['min_p_threshold'],
                    extraction_mode=strategy['extraction_mode'],
                    max_snippets_per_source=strategy['max_snippets_per_source'],
                    use_code_extraction=use_code_extraction
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

            logger.info(f"[CLONE] Extracted {len(new_snippets)} snippets (total: {len(all_snippets)})")
            if all_snippets:
                avg_p = sum(s.get('p', 0.5) for s in all_snippets) / len(all_snippets)
                high_p = sum(1 for s in all_snippets if s.get('p', 0) >= 0.85)
                logger.info(f"[CLONE] Quality: avg_p={avg_p:.2f}, high_quality={high_p}/{len(all_snippets)}")

            # Check stop condition
            if should_stop_iteration(all_snippets, strategy):
                logger.info(f"[CLONE] Stop condition met ({strategy.get('stop_condition')})")
                break

            if sources_pulled >= len(ranked_sources):
                logger.info(f"[CLONE] All sources exhausted")
                break

        # Step 5: Synthesis
        logger.info(f"\n[CLONE] Step 5: Synthesis from {len(all_snippets)} snippets...")

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
            soft_schema=use_soft_schema
        )

        costs['synthesis'] = self._extract_cost(synthesis_result.get('model_response', {}))

        # Check self-assessment and upgrade to tier4 if needed
        answer_data = synthesis_result.get('answer', {})
        self_assessment = answer_data.get('self_assessment', 'A')
        upgraded = False

        if self_assessment not in ['A+', 'A'] and synthesis_tier != 'tier4':
            logger.info(f"\n[CLONE] Self-assessment: {self_assessment} - Upgrading to tier4 (deepest)")

            # Get tier4 models
            tier4_models = get_models_for_tier(provider, 'tier4')
            tier4_synthesis_model = tier4_models['synthesis']
            tier4_soft_schema = 'deepseek' in tier4_synthesis_model or 'baseten' in tier4_synthesis_model

            logger.info(f"[CLONE] Retrying synthesis with {tier4_synthesis_model}")

            # Re-run synthesis with tier4
            synthesis_result = await self.unified_synthesizer.evaluate_and_synthesize(
                query=prompt,
                snippets=all_snippets,
                context=synthesis_context,
                iteration=1,
                is_last_iteration=True,
                schema=schema,
                model=tier4_synthesis_model,
                search_terms=search_terms,
                debug_dir=debug_dir,
                soft_schema=tier4_soft_schema
            )

            costs['synthesis'] += self._extract_cost(synthesis_result.get('model_response', {}))
            synthesis_tier = 'tier4'
            models['synthesis'] = tier4_synthesis_model
            upgraded = True

            # Get new self-assessment
            answer_data = synthesis_result.get('answer', {})
            self_assessment = answer_data.get('self_assessment', 'A')
            logger.info(f"[CLONE] Tier4 self-assessment: {self_assessment}")

        # Build response
        total_time = (datetime.now() - start_time).total_seconds()
        total_cost = sum(costs.values())

        logger.info(f"\n[CLONE] Complete in {total_time:.1f}s, Cost: ${total_cost:.4f}")
        logger.info(f"[CLONE] Snippets: {len(all_snippets)}, Citations: {len(synthesis_result.get('citations', []))}")

        return {
            "answer": synthesis_result.get('answer', {}),
            "citations": synthesis_result.get('citations', []),
            "synthesis_prompt": synthesis_result.get('synthesis_prompt', ''),
            "metadata": {
                "query": prompt,
                "strategy": strategy['name'],
                "breadth": breadth,
                "depth": depth,
                "synthesis_tier": synthesis_tier,
                "synthesis_model": models['synthesis'],
                "upgraded_to_deepest": upgraded,
                "self_assessment": self_assessment,
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
                "total_snippets": 0,
                "citations_count": 0,
                "sources_pulled": 0,
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
                "citations_count": 0,
                "sources_pulled": 0,
                "iterations": 0,
                "total_cost": sum(costs.values()),
                "cost_breakdown": costs
            }
        }
