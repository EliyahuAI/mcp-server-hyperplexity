#!/usr/bin/env python3
"""
The Clone 2 - Refined Architecture.
Implements intelligent triage, diversity-focused source selection, and iterative evaluation.

Refined Flow:
1. Generate search terms (1-5 based on complexity)
2. Execute searches (10 results per term)
3. Parallel triage (select 0-3 best diverse sources per search)
4. If no sources selected → straight to synthesis
5. Extract snippets from selected sources (parallel)
6. Evaluate sufficiency (skip on last iteration or LOW context)
7. If can answer OR last iteration → synthesis
8. Else → next iteration
"""

import sys
import os
import asyncio
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
    The Clone 2 - Refined architecture with intelligent triage and evaluation.

    Key features:
    - Parallel triage per search term (select 0-3 best diverse sources)
    - Early exit if no new sources found
    - Iterative evaluation (skip on last iteration)
    - Context-based iteration limits (1/2/3)
    - Configuration-driven
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
        Execute query with refined triage and evaluation architecture.

        Args:
            prompt: User's query
            search_context: Context level (low/medium/high)
            schema: Optional schema for synthesis

        Returns:
            Dict containing answer, citations, and metadata
        """
        start_time = datetime.now()

        logger.info("=" * 80)
        logger.info(f"[CLONE 2 REFINED] Starting query: {prompt[:100]}...")
        logger.info(f"[CLONE 2 REFINED] Context: {search_context}")
        logger.info("=" * 80)

        # Load models and limits
        models = get_default_models()
        global_limits = get_global_limits()

        logger.info(f"[CLONE 2 REFINED] Using DeepSeek V3.2 for all stages")

        # Save debug info if debug_dir provided
        if debug_dir:
            try:
                with open(os.path.join(debug_dir, '00_config.json'), 'w', encoding='utf-8') as f:
                    json.dump({
                        'query': prompt,
                        'models': models,
                        'global_limits': global_limits,
                        'schema_provided': schema is not None
                    }, f, indent=2)
            except:
                pass

        # Step 0: Initial Decision - Answer or Search?
        logger.info(f"\n[CLONE 2 REFINED] Step 0: Initial decision (Answer or Search?)...")
        initial_start = datetime.now()

        initial_result = await self.initial_decision.make_decision(
            query=prompt,
            model=models['initial_decision'],
            soft_schema=True,  # Always use soft schema for DeepSeek
            debug_dir=debug_dir
        )

        decision = initial_result.get('decision', 'need_search')
        initial_time = (datetime.now() - initial_start).total_seconds()

        logger.info(f"[CLONE 2 REFINED] Initial decision in {initial_time:.1f}s: {decision}")

        # If can answer directly, return immediately
        if decision == "answer_directly":
            answer = initial_result.get('answer', {})
            logger.info(f"[CLONE 2 REFINED] Answered from model knowledge - no search needed!")

            end_time = datetime.now()
            total_time = (end_time - start_time).total_seconds()

            # Extract initial decision cost
            initial_enhanced = initial_result.get('model_response', {}).get('enhanced_data', {})
            initial_costs = initial_enhanced.get('costs', {}).get('actual', {})
            initial_cost = initial_costs.get('total_cost', 0.0)

            return {
                "answer": answer,
                "citations": [],  # No citations for direct answer
                "synthesis_input": {
                    "snippets": [],
                    "snippet_count": 0
                },
                "metadata": {
                    "query": prompt,
                    "search_context": search_context,
                    "iterations": 0,
                    "total_snippets": 0,
                    "snippets_used": 0,
                    "citations_count": 0,
                    "sources_selected": 0,
                    "total_time_seconds": total_time,
                    "total_cost": initial_cost,
                    "cost_breakdown": {"initial_decision": initial_cost},
                    "architecture": "direct_answer_no_search",
                    "decision": "answer_directly",
                    "confidence": initial_result.get('confidence', 'medium')
                }
            }

        # Get breadth/depth and determine strategy
        breadth = initial_result.get('breadth', 'narrow')
        depth = initial_result.get('depth', 'shallow')
        strategy = get_strategy(breadth, depth)

        logger.info(f"[CLONE 2 REFINED] Strategy: {strategy['name']} (breadth={breadth}, depth={depth})")
        logger.info(f"[CLONE 2 REFINED] Batch size: {strategy['sources_per_batch']}, Mode: {strategy['extraction_mode']}, Min p: {strategy['min_p_threshold']}")

        # Get search terms from initial decision
        initial_search_terms = initial_result.get('search_terms', [])
        logger.info(f"[CLONE 2 REFINED] Need search - using {len(initial_search_terms)} initial terms")
        logger.info(f"[CLONE 2 REFINED] Initial search terms: {initial_search_terms}")

        # Initialize tracking
        all_snippets = []  # List of snippets with IDs
        snippets_used = []  # Track snippets used in answer
        citations = []  # Citations list
        answer = {}  # Answer dict
        synthesis_prompt = ""  # Synthesis prompt
        iteration = 0
        all_search_terms = []  # Track all search terms used across iterations

        # Initialize cost tracking
        cost_tracker = {
            'initial_decision': 0.0,
            'triage': 0.0,
            'extraction': 0.0,
            'synthesis': 0.0,
            'search': 0.0
        }

        # Extract initial decision cost
        initial_enhanced = initial_result.get('model_response', {}).get('enhanced_data', {})
        initial_costs = initial_enhanced.get('costs', {}).get('actual', {})
        cost_tracker['initial_decision'] = initial_costs.get('total_cost', 0.0)

        # Iteration loop
        for iteration in range(1, max_iterations + 1):
            logger.info(f"\n{'='*80}")
            logger.info(f"[CLONE 2 REFINED] Iteration {iteration}/{max_iterations}")
            logger.info(f"{'='*80}")

            # Step 1: Get search terms (use initial terms on iter 1, generate new on iter 2+)
            if iteration == 1:
                logger.info(f"[CLONE 2 REFINED] Step 1: Using initial search terms")
                search_terms = initial_search_terms
                all_search_terms.extend(search_terms)  # Track all terms
                search_settings = {'max_results': max_results}
                step1_time = 0  # Already counted in initial decision
            else:
                logger.info(f"[CLONE 2 REFINED] Step 1: Generating new search terms...")
                step_start = datetime.now()
                optimization_guidance = get_optimization_guidance(search_context)

                # Generate new search terms based on missing aspects
                search_result = await self.search_manager.generate_search_terms(
                    prompt=prompt,
                    model=triage_model,
                    optimization_notes=optimization_guidance
                )

                search_terms = search_result.get('search_terms', [])
                all_search_terms.extend(search_terms)  # Track all terms
                search_settings = search_result.get('search_settings', {})
                search_settings['max_results'] = max_results

                step1_time = (datetime.now() - step_start).total_seconds()
                logger.info(f"[CLONE 2 REFINED] Generated {len(search_terms)} search terms in {step1_time:.1f}s")

            # Step 2: Execute searches
            logger.info(f"[CLONE 2 REFINED] Step 2: Executing searches...")
            step_start = datetime.now()
            search_results = await self.search_manager.execute_searches(
                search_terms=search_terms,
                search_settings=search_settings
            )
            step2_time = (datetime.now() - step_start).total_seconds()
            logger.info(f"[CLONE 2 REFINED] Searches completed in {step2_time:.1f}s")

            # Track search cost (Perplexity charges per search)
            cost_tracker['search'] += len(search_terms) * 0.005

            # Step 3: Parallel Triage (NEW!)
            logger.info(f"[CLONE 2 REFINED] Step 3: Parallel triage (0-{sources_per_search_max} per search)...")
            step_start = datetime.now()

            selected_indices_per_search, triage_results = await self.source_triage.triage_all_searches(
                search_results=search_results,
                search_terms=search_terms,
                query=prompt,
                existing_snippets=all_snippets,
                model=triage_model,
                max_sources_per_search=sources_per_search_max,  # Use max from range
                soft_schema=use_soft_schema
            )

            # Extract triage costs
            for triage_result in triage_results:
                if isinstance(triage_result, Exception):
                    continue
                model_resp = triage_result.get('model_response', {})
                enhanced = model_resp.get('enhanced_data', {})
                costs = enhanced.get('costs', {}).get('actual', {})
                cost_tracker['triage'] += costs.get('total_cost', 0.0)

            # Build list of selected sources
            selected_sources = []
            for search_idx, (search_result, indices) in enumerate(zip(search_results, selected_indices_per_search)):
                if isinstance(search_result, Exception):
                    continue

                results = search_result.get('results', [])
                for source_idx in indices:
                    if 0 <= source_idx < len(results):
                        source = results[source_idx]
                        source['_search_term'] = search_terms[search_idx]
                        source['_search_index'] = search_idx + 1
                        source['_source_index_in_search'] = source_idx
                        selected_sources.append(source)

            # Sort by date (most recent first)
            def get_date_for_sort(source):
                date_str = source.get('date') or source.get('last_updated', '')
                if not date_str:
                    return '0000-00-00'  # Put undated sources at end
                return date_str

            selected_sources.sort(key=get_date_for_sort, reverse=True)

            # Reassign source indices after sorting (most recent = 0, next = 1, etc.)
            for new_idx, source in enumerate(selected_sources):
                source['_sorted_index'] = new_idx

            step3_time = (datetime.now() - step_start).total_seconds()
            logger.info(f"[CLONE 2 REFINED] Triage selected {len(selected_sources)} sources from {len(search_terms)} searches in {step3_time:.1f}s (sorted by date)")

            # Early exit if no new sources
            if len(selected_sources) == 0:
                logger.info(f"[CLONE 2 REFINED] No new sources selected - proceeding to synthesis")
                break

            # Step 4: Extract quotes with snippet IDs (parallel)
            logger.info(f"[CLONE 2 REFINED] Step 4: Extracting quotes from {len(selected_sources)} sources (parallel)...")
            step_start = datetime.now()

            extraction_tasks = []
            for source in selected_sources:
                search_idx = source.get('_search_index', 1)
                # Use sorted index (most recent = 0) instead of original position
                source_idx = source.get('_sorted_index', 0)
                snippet_id_prefix = f"S{iteration}.{search_idx}.{source_idx}"

                task = self.snippet_extractor.extract_from_source(
                    source=source,
                    query=prompt,
                    snippet_id_prefix=snippet_id_prefix,
                    all_search_terms=search_terms,  # Pass all search terms
                    primary_search_index=search_idx,  # Which search found this
                    model=extraction_model,
                    soft_schema=use_soft_schema
                )
                extraction_tasks.append(task)

            # Extract all in parallel
            extraction_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

            # Accumulate snippets and extract costs
            new_snippets = []
            for result in extraction_results:
                if isinstance(result, Exception):
                    logger.error(f"[CLONE 2 REFINED] Extraction failed: {result}")
                    continue

                snippets = result.get('snippets', [])
                new_snippets.extend(snippets)

                # Extract cost from this extraction
                model_resp = result.get('model_response', {})
                enhanced = model_resp.get('enhanced_data', {})
                costs = enhanced.get('costs', {}).get('actual', {})
                cost_tracker['extraction'] += costs.get('total_cost', 0.0)

            all_snippets.extend(new_snippets)

            step4_time = (datetime.now() - step_start).total_seconds()
            logger.info(f"[CLONE 2 REFINED] Extracted {len(new_snippets)} quotes in {step4_time:.1f}s, Total: {len(all_snippets)}")
            if len(selected_sources) > 0:
                logger.info(f"[CLONE 2 REFINED] Average extraction time: {step4_time / len(selected_sources):.1f}s per source")

            # Step 5/6: Unified Evaluation + Synthesis
            is_last_iteration = (iteration >= max_iterations)

            if is_last_iteration:
                logger.info(f"[CLONE 2 REFINED] Step 5: Synthesis (last iteration)...")
            else:
                logger.info(f"[CLONE 2 REFINED] Step 5: Evaluation + Synthesis (if sufficient)...")

            step_start = datetime.now()

            unified_result = await self.unified_synthesizer.evaluate_and_synthesize(
                query=prompt,
                snippets=all_snippets,
                context=determined_context,  # Use determined context
                iteration=iteration,
                is_last_iteration=is_last_iteration,
                schema=schema,
                model=determined_synthesis_model,  # Use determined model tier
                search_terms=search_terms,  # Pass search terms for proper formatting
                debug_dir=debug_dir,  # Pass debug directory
                soft_schema=use_soft_schema
            )

            can_answer = unified_result.get('can_answer', False)
            confidence = unified_result.get('confidence', 'low')
            answer = unified_result.get('answer', {})
            citations = unified_result.get('citations', [])
            snippets_used = unified_result.get('snippets_used', [])
            synthesis_prompt = unified_result.get('synthesis_prompt', '')

            # Extract synthesis cost
            synth_resp = unified_result.get('model_response', {})
            synth_enhanced = synth_resp.get('enhanced_data', {})
            synth_costs = synth_enhanced.get('costs', {}).get('actual', {})
            cost_tracker['synthesis'] += synth_costs.get('total_cost', 0.0)

            step5_time = (datetime.now() - step_start).total_seconds()

            if is_last_iteration:
                logger.info(f"[CLONE 2 REFINED] Synthesis complete in {step5_time:.1f}s")
                break
            else:
                logger.info(f"[CLONE 2 REFINED] Eval+Synthesis complete in {step5_time:.1f}s - Can answer: {can_answer}, Confidence: {confidence}")

                if can_answer:
                    logger.info(f"[CLONE 2 REFINED] Answer provided - stopping")
                    break
                else:
                    missing = unified_result.get('missing_aspects', [])
                    logger.info(f"[CLONE 2 REFINED] Insufficient - missing: {', '.join(missing[:3])}")
                    logger.info(f"[CLONE 2 REFINED] Continuing to iteration {iteration + 1}")

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        # Calculate total cost
        total_cost = sum(cost_tracker.values())

        logger.info(f"\n[CLONE 2 REFINED] Complete!")
        logger.info(f"[CLONE 2 REFINED] Total time: {total_time:.1f}s")
        logger.info(f"[CLONE 2 REFINED] Iterations: {iteration}")
        logger.info(f"[CLONE 2 REFINED] Snippets: {len(snippets_used)}/{len(all_snippets)}")
        logger.info(f"[CLONE 2 REFINED] Citations: {len(citations)}")
        logger.info(f"[CLONE 2 REFINED] Total cost: ${total_cost:.4f}")
        logger.info(f"\n[CLONE 2 REFINED] COST BREAKDOWN:")
        for component, cost in cost_tracker.items():
            if cost > 0:
                pct = (cost / total_cost * 100) if total_cost > 0 else 0
                logger.info(f"  {component:20s}: ${cost:.4f} ({pct:.1f}%)")

        logger.info(f"[CLONE DEBUG] About to return - synthesis_tier={synthesis_tier}, all_search_terms={all_search_terms[:50] if all_search_terms else None}")

        return {
            "answer": answer,
            "citations": citations,
            "synthesis_input": {
                "snippets": all_snippets,
                "snippet_count": len(all_snippets)
            },
            "synthesis_prompt": synthesis_prompt,  # Actual prompt sent to synthesis model
            "metadata": {
                "query": prompt,
                "decision": "need_search",
                "search_context": search_context,
                "synthesis_model_tier": synthesis_tier,
                "search_terms": all_search_terms,  # All search queries used across iterations
                "iterations": iteration,
                "total_snippets": len(all_snippets),
                "snippets_used": len(snippets_used),
                "citations_count": len(citations),
                "sources_selected": len(selected_sources) * iteration,
                "total_time_seconds": total_time,
                "total_cost": total_cost,
                "cost_breakdown": cost_tracker,
                "architecture": "streamlined_v3_smart_routing"
            }
        }


async def main():
    """Test The Clone 2 Refined."""
    clone2 = TheClone2Refined()

    query = "Compare Claude Opus 4 and GPT-4.5 architecture"

    result = await clone2.query(
        prompt=query,
        search_context="medium"
    )

    print("\n" + "="*80)
    print("ANSWER:")
    print("="*80)
    print(json.dumps(result['answer'], indent=2))

    print("\n" + "="*80)
    print("METADATA:")
    print("="*80)
    print(json.dumps(result['metadata'], indent=2))


if __name__ == "__main__":
    import json
    asyncio.run(main())
