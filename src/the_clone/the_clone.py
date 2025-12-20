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
import time
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
from the_clone.clone_logger import CloneLogger

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
        call_start_time = time.time()
        
        # Initialize Consolidated Logger (works in memory even if debug_dir is None)
        clone_logger = CloneLogger(debug_dir)
        
        clone_logger.log_section("Initial Query", prompt, level=1)

        logger.info("=" * 80)
        logger.info(f"[CLONE] Query: {prompt[:100]}...")
        logger.info("=" * 80)

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

        # Log initial settings
        if clone_logger:
            clone_logger.log_section("Clone Configuration & Initial Settings", {
                "Provider": provider,
                "Model Override": model_override,
                "Schema Provided": bool(schema),
                "Use Code Extraction": use_code_extraction,
                "Academic Mode": academic,
                "Models": models,
                "Global Limits": global_limits
            }, level=2, collapse=False)

        # Cost tracking by stage
        costs = {'initial': 0.0, 'search': 0.0, 'triage': 0.0, 'extraction': 0.0, 'synthesis': 0.0}
        
        # Stats tracking
        stats = {'schema_repairs': 0}

        # Cost tracking by provider (for proper DynamoDB attribution)
        costs_by_provider = {
            'perplexity': 0.0,
            'vertex': 0.0,
            'baseten': 0.0,
            'anthropic': 0.0
        }
        calls_by_provider = {
            'perplexity': 0,
            'vertex': 0,
            'baseten': 0,
            'anthropic': 0
        }

        # Step 1: Initial Decision
        logger.info("\n[CLONE] Step 1: Initial Decision...")
        step_start_phase = time.time()
        if clone_logger:
            clone_logger.start_step("Initial Decision")
            
        initial_result = await self.initial_decision.make_decision(
            query=prompt,
            model=models['initial_decision'],
            soft_schema=True,
            debug_dir=debug_dir,
            custom_schema=schema,
            clone_logger=clone_logger
        )

        decision = initial_result.get('decision', 'need_search')
        model_resp = initial_result.get('model_response', {})

        # Debug: check model_response structure
        if model_resp:
            enhanced = model_resp.get('enhanced_data', {})
            if enhanced:
                call_info = enhanced.get('call_info', {})
                logger.info(f"[DEBUG] Initial decision - call_info keys: {list(call_info.keys()) if call_info else 'NO call_info'}")
                logger.info(f"[DEBUG] Initial decision - api_provider: {call_info.get('api_provider', 'NOT FOUND')}")
            else:
                logger.warning(f"[DEBUG] No enhanced_data in model_response")
        else:
            logger.warning(f"[DEBUG] No model_response in initial_result")

        initial_cost, initial_provider = self._extract_cost_and_provider(model_resp, clone_logger, stats)
        logger.info(f"[DEBUG] Extracted provider: {initial_provider}")
        costs['initial'] = initial_cost
        costs_by_provider[initial_provider] = costs_by_provider.get(initial_provider, 0.0) + initial_cost
        calls_by_provider[initial_provider] = calls_by_provider.get(initial_provider, 0) + 1
        
        step_time_phase = time.time() - step_start_phase
        if clone_logger:
            used_model = model_resp.get('model_used', models['initial_decision'])
            if model_resp.get('used_backup_model'): used_model += " (Backup)"
            clone_logger.record_step_metric("Initial Decision", initial_provider, used_model, initial_cost, step_time_phase, f"Decision: {decision}")
            clone_logger.end_step("Initial Decision")

        if decision == "answer_directly":
            logger.info("[CLONE] Answering directly from model knowledge")
            direct_answer = initial_result.get('direct_answer', {})

            total_time = time.time() - call_start_time
            total_cost = sum(costs.values())
            
            final_citations = [] # No citations for direct answers
            final_answer_data = direct_answer

            metadata = {
                "query": prompt,
                "strategy": "direct_answer",
                "breadth": initial_result.get('breadth', 'narrow'),
                "depth": initial_result.get('depth', 'shallow'),
                "synthesis_tier": initial_result.get('synthesis_tier', 'tier1'),
                "iterations": 0,
                "total_snippets": 0,
                "citations_count": 0,
                "sources_pulled": 0,
                "total_time_seconds": total_time,
                "total_cost": total_cost,
                "cost_breakdown": costs,
                "cost_by_provider": {p: {'cost': c, 'calls': calls_by_provider[p]} for p, c in costs_by_provider.items() if c > 0},
                "schema_repairs": stats['schema_repairs'],
                "provider": provider, # Add top-level provider for settings summary
                "model_override": model_override,
                "schema_provided": bool(schema),
                "use_code_extraction": use_code_extraction,
                "academic": academic
            }
            if clone_logger:
                clone_logger.finalize(metadata, final_answer_data, final_citations)

            return {
                "answer": final_answer_data,
                "citations": final_citations,
                "synthesis_prompt": "",
                "metadata": {**metadata, "debug_log": clone_logger.get_log_content()}
            }

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
        
        if clone_logger:
            clone_logger.log_section("Strategy Selected", {
                'name': strategy['name'], 
                'breadth': breadth, 
                'depth': depth,
                'synthesis_tier': synthesis_tier,
                'search_terms': search_terms
            }, level=2, collapse=True)

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
        step_start_phase = time.time()
        if clone_logger:
            clone_logger.start_step("Search Execution")

        search_results = await self.search_manager.execute_searches(
            search_terms=search_terms,
            search_settings={'max_results': 10},
            include_domains=search_include_domains,
            exclude_domains=search_exclude_domains,
            clone_logger=clone_logger
        )
        search_cost = len(search_terms) * 0.005  # Perplexity search API cost
        costs['search'] = search_cost
        costs_by_provider['perplexity'] += search_cost
        calls_by_provider['perplexity'] += len(search_terms)
        
        step_time_phase = time.time() - step_start_phase
        if clone_logger:
            total_results = sum(len(r.get('results', [])) for r in search_results if not isinstance(r, Exception))
            clone_logger.record_step_metric("Search", "perplexity", "sonar-pro", search_cost, step_time_phase, f"{len(search_terms)} queries, {total_results} results")
            clone_logger.end_step("Search Execution")

        # Step 3: Triage (rank ALL sources)
        logger.info(f"\n[CLONE] Step 3: Ranking sources...")
        step_start_phase = time.time()
        if clone_logger:
            clone_logger.start_step("Source Triage")

        ranked_lists, triage_results = await self.source_triage.triage_all_searches(
            search_results=search_results,
            search_terms=search_terms,
            query=prompt,
            existing_snippets=[],
            model=models['triage'],
            soft_schema=use_soft_schema,
            clone_logger=clone_logger
        )

        # Extract triage costs by provider
        triage_providers = set()
        for i, result in enumerate(triage_results):
            if not isinstance(result, Exception):
                triage_cost, triage_provider = self._extract_cost_and_provider(result.get('model_response', {}), clone_logger, stats)
                costs['triage'] += triage_cost
                costs_by_provider[triage_provider] = costs_by_provider.get(triage_provider, 0.0) + triage_cost
                calls_by_provider[triage_provider] = calls_by_provider.get(triage_provider, 0) + 1
                triage_providers.add(triage_provider)

            if clone_logger and i == 0: # Log first prompt uncollapsed
                if not isinstance(result, Exception) and result.get('triage_prompt'):
                    clone_logger.log_section(f"Triage Prompt (Search {i+1})", result['triage_prompt'], level=3, collapse=False)

        step_time_phase = time.time() - step_start_phase
        if clone_logger:
            provider_display = list(triage_providers)[0] if len(triage_providers) == 1 else f"mixed:{','.join(sorted(list(triage_providers)))}"
            triage_model = models['triage']
            # Check for backup usage in any result
            backup_triggered = any(
                r.get('model_response', {}).get('used_backup_model') 
                for r in triage_results if not isinstance(r, Exception)
            )
            if backup_triggered: triage_model += " (Backup)"
                
            clone_logger.record_step_metric("Triage", provider_display, triage_model, costs['triage'], step_time_phase, f"Ranked {len(ranked_lists)} search groups")
            clone_logger.end_step("Source Triage")

        # Build ranked source pool
        ranked_sources = self._build_ranked_source_pool(search_results, ranked_lists, search_terms)
        logger.info(f"[CLONE] Ranked {len(ranked_sources)} relevant sources")

        if len(ranked_sources) == 0:
            logger.info("[CLONE] No relevant sources found")
            total_time = time.time() - call_start_time
            metadata = {
                "query": prompt,
                "strategy": strategy['name'],
                "breadth": breadth,
                "depth": depth,
                "synthesis_tier": synthesis_tier,
                "synthesis_model": models['synthesis'],
                "upgraded_to_deepest": False,
                "self_assessment": "No sources found",
                "search_terms": search_terms,
                "iterations": 0,
                "total_snippets": 0,
                "citations_count": 0,
                "sources_pulled": 0,
                "total_time_seconds": total_time,
                "total_cost": sum(costs.values()),
                "cost_breakdown": costs,
                "cost_by_provider": {p: {'cost': c, 'calls': calls_by_provider[p]} for p, c in costs_by_provider.items() if c > 0},
                "schema_repairs": stats['schema_repairs'],
                "provider": provider,
                "model_override": model_override,
                "schema_provided": bool(schema),
                "use_code_extraction": use_code_extraction,
                "academic": academic
            }
            if clone_logger: 
                clone_logger.finalize(metadata, {}, []) # No answer or citations
            return {
                "answer": {},
                "citations": [],
                "synthesis_prompt": "",
                "metadata": {**metadata, "debug_log": clone_logger.get_log_content()}
            }

        # Step 4: Iterative Extraction
        logger.info(f"\n[CLONE] Step 4: Iterative extraction (max {global_limits['max_iterations']} iterations)...")
        step_start_phase = time.time()
        if clone_logger:
            clone_logger.start_step("Extraction")

        all_snippets = []
        sources_pulled = 0
        first_extraction_prompt_logged = False

        for iteration in range(1, global_limits['max_iterations'] + 1):
            logger.info(f"\n[CLONE] Iteration {iteration}/{global_limits['max_iterations']}")
            if clone_logger:
                clone_logger.log_section(f"Iteration {iteration}", f"Pulling sources from index {sources_pulled}", level=3)

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
                    use_code_extraction=use_code_extraction,
                    clone_logger=clone_logger,
                    log_prompt_collapsed=(first_extraction_prompt_logged)
                )
                extraction_tasks.append(task)
            
            if not first_extraction_prompt_logged: first_extraction_prompt_logged = True

            results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

            # Collect snippets and costs by provider
            new_snippets = []
            iteration_cost = 0.0
            extract_providers = set()
            
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"[CLONE] Extraction error: {result}")
                    continue
                new_snippets.extend(result.get('snippets', []))
                extract_cost, extract_provider = self._extract_cost_and_provider(result.get('model_response', {}), clone_logger, stats)
                costs['extraction'] += extract_cost
                iteration_cost += extract_cost
                costs_by_provider[extract_provider] = costs_by_provider.get(extract_provider, 0.0) + extract_cost
                calls_by_provider[extract_provider] = calls_by_provider.get(extract_provider, 0) + 1
                extract_providers.add(extract_provider)

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
        
        step_time_phase = time.time() - step_start_phase
        if clone_logger:
            provider_display = list(extract_providers)[0] if len(extract_providers) == 1 else f"mixed:{','.join(sorted(list(extract_providers)))}"
            extract_model = models['extraction']
            # For simplicity, we just list the configured model. Backup models are logged at the individual call level in log_section.
            clone_logger.record_step_metric("Extraction", provider_display, extract_model, costs['extraction'], step_time_phase, f"Extracted {len(all_snippets)} snippets")
            clone_logger.end_step("Extraction")

        # Step 5: Synthesis
        logger.info(f"\n[CLONE] Step 5: Synthesis from {len(all_snippets)} snippets...")
        step_start_phase = time.time()
        if clone_logger:
            clone_logger.start_step("Synthesis")

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
            soft_schema=use_soft_schema,
            clone_logger=clone_logger
        )

        synth_cost, synth_provider = self._extract_cost_and_provider(synthesis_result.get('model_response', {}), clone_logger, stats)
        costs['synthesis'] = synth_cost
        costs_by_provider[synth_provider] = costs_by_provider.get(synth_provider, 0.0) + synth_cost
        calls_by_provider[synth_provider] = calls_by_provider.get(synth_provider, 0) + 1
        
        step_time_phase = time.time() - step_start_phase
        if clone_logger:
            model_resp = synthesis_result.get('model_response', {})
            used_model = model_resp.get('model_used', models['synthesis'])
            if model_resp.get('used_backup_model'): used_model += " (Backup)"
            clone_logger.record_step_metric("Synthesis", synth_provider, used_model, synth_cost, step_time_phase, f"Generated {len(synthesis_result.get('citations', []))} citations")
            clone_logger.end_step("Synthesis")

        # Check self-assessment and upgrade to tier4 if needed
        answer_data = synthesis_result.get('answer', {})
        self_assessment = answer_data.get('self_assessment', 'A') if isinstance(answer_data, dict) else 'A'
        upgraded = False

        if self_assessment not in ['A+', 'A'] and synthesis_tier != 'tier4':
            logger.info(f"\n[CLONE] Self-assessment: {self_assessment} - Upgrading to tier4 (deepest)")
            step_start_phase = time.time()
            if clone_logger:
                clone_logger.start_step("Tier 4 Upgrade")
                clone_logger.log_section("Tier 4 Upgrade", f"Self-assessment: {self_assessment}. Upgrading to tier4.", level=2)

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
                soft_schema=tier4_soft_schema,
                clone_logger=clone_logger
            )

            tier4_cost, tier4_provider = self._extract_cost_and_provider(synthesis_result.get('model_response', {}), clone_logger, stats)
            costs['synthesis'] += tier4_cost
            costs_by_provider[tier4_provider] = costs_by_provider.get(tier4_provider, 0.0) + tier4_cost
            calls_by_provider[tier4_provider] = calls_by_provider.get(tier4_provider, 0) + 1
            synthesis_tier = 'tier4'
            models['synthesis'] = tier4_synthesis_model
            upgraded = True
            
            step_time_phase = time.time() - step_start_phase
            if clone_logger:
                model_resp = synthesis_result.get('model_response', {})
                used_model = model_resp.get('model_used', tier4_synthesis_model)
                if model_resp.get('used_backup_model'): used_model += " (Backup)"
                clone_logger.record_step_metric("Tier 4 Synthesis", tier4_provider, used_model, tier4_cost, step_time_phase, "Re-synthesized with deepest model")
                clone_logger.end_step("Tier 4 Upgrade")

            # Get new self-assessment
            answer_data = synthesis_result.get('answer', {})
            self_assessment = answer_data.get('self_assessment', 'A') if isinstance(answer_data, dict) else 'A'
            logger.info(f"[CLONE] Tier4 self-assessment: {self_assessment}")

        # Build response
        total_time = time.time() - call_start_time # Use overall start time
        total_cost = sum(costs.values())
        total_cost_by_provider = sum(costs_by_provider.values())

        # Sanity check: both totals should match
        if abs(total_cost - total_cost_by_provider) > 0.0001:
            logger.warning(f"[CLONE] Cost mismatch! By-stage: ${total_cost:.4f}, By-provider: ${total_cost_by_provider:.4f}")

        logger.info(f"\n[CLONE] Complete in {total_time:.1f}s, Cost: ${total_cost:.4f}")
        logger.info(f"[CLONE] Cost by provider: " + ", ".join(f"{p}=${c:.4f}" for p, c in costs_by_provider.items() if c > 0))
        logger.info(f"[CLONE] Snippets: {len(all_snippets)}, Citations: {len(synthesis_result.get('citations', []))}")

        # Build provider-level cost structure for DynamoDB
        provider_costs = {}
        for p, cost in costs_by_provider.items():
            if cost > 0 or calls_by_provider.get(p, 0) > 0:
                provider_costs[p] = {
                    'cost': cost,
                    'calls': calls_by_provider.get(p, 0)
                }
        
        final_answer_data = synthesis_result.get('answer', {})
        final_citations = synthesis_result.get('citations', [])

        metadata = {
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
            "citations_count": len(final_citations),
            "sources_pulled": sources_pulled,
            "total_time_seconds": total_time,
            "total_cost": total_cost,
            "cost_breakdown": costs,  # By-stage breakdown (for debugging)
            "cost_by_provider": provider_costs,  # By-provider breakdown (for DynamoDB)
            "schema_repairs": stats['schema_repairs'],
            "provider": provider, # Add top-level provider for settings summary
            "model_override": model_override,
            "schema_provided": bool(schema),
            "use_code_extraction": use_code_extraction,
            "academic": academic
        }

        if clone_logger:
            clone_logger.finalize(metadata, final_answer_data, final_citations)

        return {
            "answer": final_answer_data,
            "citations": final_citations,
            "synthesis_prompt": synthesis_result.get('synthesis_prompt', ''),
            "metadata": {**metadata, "debug_log": clone_logger.get_log_content() if clone_logger else ""}
        }

    def _extract_cost_and_provider(self, model_response: Dict, clone_logger=None, stats: Dict = None) -> tuple[float, str]:
        """Extract cost and provider from model response."""
        enhanced = model_response.get('enhanced_data', {})
        costs = enhanced.get('costs', {}).get('actual', {})
        cost = costs.get('total_cost', 0.0)
        provider = enhanced.get('call_info', {}).get('api_provider', 'unknown')

        # Debug unknown provider
        if provider == 'unknown' and enhanced:
            logger.warning(f"[DEBUG] Provider unknown - enhanced_data keys: {list(enhanced.keys())}")
            if 'call_info' in enhanced:
                logger.warning(f"[DEBUG] call_info keys: {list(enhanced['call_info'].keys())}")

        # Track schema repairs if stats provided
        if stats and 'schema_repairs' in stats:
            # Check if this response used Haiku repair
            if 'haiku_repair' in str(model_response):
                stats['schema_repairs'] += 1

        return cost, provider

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
