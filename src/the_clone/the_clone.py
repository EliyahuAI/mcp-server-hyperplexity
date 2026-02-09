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
from the_clone.search_memory import SearchMemory, extract_urls_from_text

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
        use_code_extraction: bool = True,
        disable_keyword_scoring: bool = False,
        findall: bool = False,
        findall_iterations: int = 1,
        extraction: bool = False,
        session_id: Optional[str] = None,
        email: Optional[str] = None,
        s3_manager = None,
        use_memory: bool = True,
        row_context: dict = None
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

        logger.debug("=" * 80)
        logger.debug(f"[CLONE] Query: {prompt[:100]}...")
        logger.debug("=" * 80)

        # Handle backwards compatibility: use_baseten=True → provider="baseten"
        if use_baseten:
            provider = "baseten"
            logger.debug(f"[CLONE] use_baseten=True (backwards compat), setting provider='baseten'")

        # Load configuration
        if model_override:
            models = {
                'initial_decision': model_override if 'claude' in model_override else 'claude-sonnet-4-5',
                'triage': model_override,
                'extraction': model_override,
                'synthesis': model_override
            }
            logger.debug(f"[CLONE] Model override: {model_override}")
        else:
            models = get_default_models(provider)

        global_limits = get_global_limits()

        logger.debug(f"[CLONE] Provider: {provider}")

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
        costs = {'initial': 0.0, 'recall': 0.0, 'search': 0.0, 'triage': 0.0, 'extraction': 0.0, 'synthesis': 0.0}
        
        # Stats tracking
        stats = {'schema_repairs': 0}

        # Cost tracking by provider (for proper DynamoDB attribution)
        costs_by_provider = {
            'perplexity': 0.0,
            'vertex': 0.0,
            'baseten': 0.0,
            'anthropic': 0.0,
            'gemini': 0.0
        }
        calls_by_provider = {
            'perplexity': 0,
            'vertex': 0,
            'baseten': 0,
            'anthropic': 0,
            'gemini': 0
        }

        # Step 1: Initial Decision
        logger.debug("\n[CLONE] Step 1: Initial Decision...")
        step_start_phase = time.time()
        if clone_logger:
            clone_logger.start_step("Initial Decision")
            
        initial_result = await self.initial_decision.make_decision(
            query=prompt,
            model=models['initial_decision'],
            soft_schema=True,
            debug_dir=debug_dir,
            custom_schema=schema,
            clone_logger=clone_logger,
            findall_mode=findall
        )

        decision = initial_result.get('decision', 'need_search')
        model_resp = initial_result.get('model_response', {})

        # Debug: check model_response structure
        if model_resp:
            enhanced = model_resp.get('enhanced_data', {})
            if enhanced:
                call_info = enhanced.get('call_info', {})
                logger.debug(f"Initial decision - call_info keys: {list(call_info.keys()) if call_info else 'NO call_info'}")
                logger.debug(f"Initial decision - api_provider: {call_info.get('api_provider', 'NOT FOUND')}")
            else:
                logger.debug(f"No enhanced_data in model_response")
        else:
            logger.debug(f"No model_response in initial_result")

        initial_cost, initial_provider = self._extract_cost_and_provider(model_resp, clone_logger, stats)
        logger.debug(f"Extracted provider: {initial_provider}")
        costs['initial'] = initial_cost
        costs_by_provider[initial_provider] = costs_by_provider.get(initial_provider, 0.0) + initial_cost
        calls_by_provider[initial_provider] = calls_by_provider.get(initial_provider, 0) + 1
        
        step_time_phase = time.time() - step_start_phase
        if clone_logger:
            used_model = model_resp.get('model_used', models['initial_decision'])
            if model_resp.get('used_backup_model'): used_model += " (Backup)"
            clone_logger.record_step_metric("Initial Decision", initial_provider, used_model, initial_cost, step_time_phase, f"Decision: {decision}")
            clone_logger.end_step("Initial Decision")

        if decision == "answer_directly" and not initial_result.get('skip_to_synthesis'):
            logger.debug("[CLONE] Answering directly from model knowledge")
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

        # Skip-to-synthesis path: Direct answer failed, skip search and go straight to synthesis
        # with URL sources from memory (if any)
        if initial_result.get('skip_to_synthesis'):
            logger.debug("[CLONE] Skip-to-synthesis: Direct answer failed, attempting synthesis with URL sources")

            if clone_logger:
                clone_logger.start_step("Skip-to-Synthesis")

            # Extract URLs from query and fetch from memory or live
            url_snippets = []
            query_urls = extract_urls_from_text(prompt)

            # Get required_keywords for URL validation (from initial decision)
            skip_required_keywords = initial_result.get('required_keywords', [])

            if query_urls and use_memory and session_id and email and s3_manager:
                logger.debug(f"[CLONE] Skip-to-synthesis: Found {len(query_urls)} URLs in query")

                # Use MemoryCache for shared memory access (loads from S3 if not cached)
                from the_clone.search_memory_cache import MemoryCache
                memory = MemoryCache.get(session_id, email, s3_manager, self.ai_client)

                # Look up URLs in memory with keyword validation
                url_lookup_result = memory.recall_by_urls(
                    query_urls,
                    required_keywords=skip_required_keywords
                )
                url_sources = url_lookup_result['found']
                urls_not_in_memory = url_lookup_result['not_found']
                urls_need_fetch = url_lookup_result.get('needs_fetch', [])  # URLs that failed keyword validation
                fetched_count = 0

                if url_sources:
                    logger.debug(f"[CLONE] Skip-to-synthesis: {len(url_sources)} URLs found in memory (passing keywords)")

                if urls_need_fetch:
                    logger.debug(f"[CLONE] Skip-to-synthesis: {len(urls_need_fetch)} URLs need fresh fetch (failed keyword validation)")

                # Combine URLs that need fetching: not in memory + failed keyword validation
                urls_to_fetch = list(set(urls_not_in_memory + urls_need_fetch))

                # Fetch URLs via Jina
                if urls_to_fetch:
                    logger.debug(f"[CLONE] Skip-to-synthesis: Fetching {len(urls_to_fetch)} URLs...")
                    fetched_sources = await memory.fetch_url_content(urls_to_fetch)
                    if fetched_sources:
                        url_sources.extend(fetched_sources)
                        fetched_count = len(fetched_sources)
                        logger.debug(f"[CLONE] Skip-to-synthesis: {fetched_count} URLs fetched live")

                # Convert URL sources to snippets format
                for i, source in enumerate(url_sources):
                    # Use 'snippet' field (memory format) or 'text'/'content' (live fetch format)
                    raw_content = source.get('snippet', source.get('text', source.get('content', '')))

                    # Full content sources (table extractions) get higher limit to preserve table data
                    # Regular sources truncated at 8000 chars to fit in context
                    if source.get('_is_full_content'):
                        text_content = raw_content[:32000]  # 32K for table extractions
                    else:
                        text_content = raw_content[:8000]

                    # Higher p-score for full content (table extractions)
                    p_score = 0.95 if source.get('_is_full_content') else 0.85

                    snippet = {
                        'id': f'U1.{i+1}.0.0',
                        'search_ref': 1,
                        '_source_url': source.get('url', ''),
                        '_source_date': source.get('date', ''),
                        'verbal_handle': source.get('title', source.get('url', '')),
                        'text': text_content,
                        'p': p_score,
                        'c': 'H/P',  # High reliability, primary source
                        'validation_reason': 'URL from query',
                        '_is_lower_quality': False,
                        '_is_full_content': source.get('_is_full_content', False),
                        '_source_type': source.get('_source_type', 'url_lookup')
                    }
                    url_snippets.append(snippet)

                if clone_logger:
                    clone_logger.log_section("Skip-to-Synthesis URL Sources", {
                        "URLs in Query": query_urls,
                        "Found in Memory (passing)": len(url_lookup_result['found']),
                        "Needs Fetch (failed keywords)": len(urls_need_fetch),
                        "Not in Memory": len(urls_not_in_memory),
                        "Fetched Live": fetched_count,
                        "Total Snippets": len(url_snippets),
                        "Full Content Snippets": sum(1 for s in url_snippets if s.get('_is_full_content'))
                    }, level=3)

            # Call synthesis with URL snippets (or empty if no URLs found)
            synthesis_tier = initial_result.get('synthesis_tier', 'tier2')
            if model_override:
                models = {
                    'initial_decision': model_override if 'claude' in model_override else 'claude-sonnet-4-5',
                    'triage': model_override,
                    'extraction': model_override,
                    'synthesis': model_override
                }
            else:
                models = get_models_for_tier(provider, synthesis_tier)

            step_start_phase = time.time()
            synthesis_result = await self.unified_synthesizer.evaluate_and_synthesize(
                query=prompt,
                snippets=url_snippets,
                context='medium',
                iteration=1,
                is_last_iteration=True,
                schema=schema,
                model=models['synthesis'],
                search_terms=[prompt],  # Use query as search term
                debug_dir=debug_dir,
                soft_schema=False,
                clone_logger=clone_logger,
                initial_decision=decision,  # Pass initial decision
                sources_examined=[]  # No sources examined for answer_directly
            )

            synth_cost, synth_provider = self._extract_cost_and_provider(
                synthesis_result.get('model_response', {}), clone_logger, stats
            )
            costs['synthesis'] = synth_cost
            costs_by_provider[synth_provider] = costs_by_provider.get(synth_provider, 0.0) + synth_cost
            calls_by_provider[synth_provider] = calls_by_provider.get(synth_provider, 0) + 1

            step_time_phase = time.time() - step_start_phase
            if clone_logger:
                clone_logger.record_step_metric(
                    "Skip-to-Synthesis", synth_provider, models['synthesis'],
                    synth_cost, step_time_phase,
                    f"URL sources: {len(url_snippets)}, Citations: {len(synthesis_result.get('citations', []))}"
                )
                clone_logger.end_step("Skip-to-Synthesis")

            # Build final result
            total_time = time.time() - call_start_time
            total_cost = sum(costs.values())

            final_answer_data = synthesis_result.get('answer', {})
            final_citations = synthesis_result.get('citations', [])

            metadata = {
                "query": prompt,
                "strategy": "skip_to_synthesis",
                "breadth": initial_result.get('breadth', 'narrow'),
                "depth": initial_result.get('depth', 'shallow'),
                "synthesis_tier": synthesis_tier,
                "iterations": 1,
                "total_snippets": len(url_snippets),
                "citations_count": len(final_citations),
                "sources_pulled": len(url_snippets),
                "total_time_seconds": total_time,
                "total_cost": total_cost,
                "cost_breakdown": costs,
                "cost_by_provider": {p: {'cost': c, 'calls': calls_by_provider[p]} for p, c in costs_by_provider.items() if c > 0},
                "schema_repairs": stats['schema_repairs'],
                "provider": provider,
                "model_override": model_override,
                "schema_provided": bool(schema),
                "use_code_extraction": use_code_extraction,
                "academic": academic,
                "url_sources_used": len(url_snippets)
            }

            if clone_logger:
                clone_logger.finalize(metadata, final_answer_data, final_citations)

            return {
                "answer": final_answer_data,
                "citations": final_citations,
                "synthesis_prompt": synthesis_result.get('synthesis_prompt', ''),
                "metadata": {**metadata, "debug_log": clone_logger.get_log_content()}
            }

        # Get strategy and models
        breadth = initial_result.get('breadth', 'narrow')
        depth = initial_result.get('depth', 'shallow')
        synthesis_tier = initial_result.get('synthesis_tier', 'tier2')

        # Force extraction strategy if extraction=True
        if extraction:
            strategy = get_strategy('narrow', 'extraction')
            logger.debug(f"[CLONE] EXTRACTION mode enabled: 8K tokens/page, parallel, Gemini synthesis")
        else:
            strategy = get_strategy(breadth, depth)

        search_terms = initial_result.get('search_terms', [prompt])
        required_keywords = initial_result.get('required_keywords', [])
        positive_keywords = initial_result.get('positive_keywords', [])
        negative_keywords = initial_result.get('negative_keywords', [])

        # Extract significant words from search terms and add to positive keywords
        # This ensures memory recall matches on actual search content, not unrelated context
        stopwords = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                     'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                     'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
                     'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
                     'from', 'as', 'into', 'through', 'during', 'before', 'after',
                     'above', 'below', 'between', 'under', 'again', 'further', 'then',
                     'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all',
                     'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
                     'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just',
                     'and', 'but', 'if', 'or', 'because', 'until', 'while', 'although',
                     'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those',
                     'am', 'it', 'its', 'they', 'their', 'them', 'we', 'us', 'our',
                     'you', 'your', 'he', 'him', 'his', 'she', 'her', 'hers', 'i', 'me', 'my'}
        search_term_words = set()
        for term in search_terms:
            words = term.lower().split()
            for word in words:
                # Keep words 3+ chars that aren't stopwords
                clean_word = ''.join(c for c in word if c.isalnum())
                if len(clean_word) >= 3 and clean_word not in stopwords:
                    search_term_words.add(clean_word)

        # Merge with existing positive keywords (avoid duplicates)
        existing_lower = {kw.lower() for kw in positive_keywords}
        new_keywords = [w for w in search_term_words if w not in existing_lower]
        if new_keywords:
            positive_keywords = positive_keywords + new_keywords
            logger.debug(f"[CLONE] Added {len(new_keywords)} keywords from search terms: {new_keywords}")

        # Allow disabling keyword scoring for comparison tests
        if disable_keyword_scoring:
            logger.debug("[CLONE] Keyword scoring DISABLED for comparison test")
            required_keywords = []
            positive_keywords = []
            negative_keywords = []
        else:
            logger.debug(f"[CLONE] Keywords generated: {len(required_keywords)} required, {len(positive_keywords)} positive, {len(negative_keywords)} negative")
            if required_keywords:
                logger.debug(f"[CLONE] Required keywords: {required_keywords}")
            if positive_keywords:
                logger.debug(f"[CLONE] Positive keywords: {positive_keywords}")
            if negative_keywords:
                logger.debug(f"[CLONE] Negative keywords: {negative_keywords}")

        # Get models for synthesis tier (unless overridden)
        if not model_override:
            models = get_models_for_tier(provider, synthesis_tier, strategy=strategy)

        # Override global limits for findall mode
        if strategy.get('bypass_global_source_limit'):
            max_per_search = strategy.get('max_results_per_search', 10)
            global_limits['max_sources_total'] = max_per_search * len(search_terms)
            logger.debug(f"[CLONE] FINDALL mode: Overriding max_sources_total to {global_limits['max_sources_total']}")

            # FINDALL mode: Use specific model chain for synthesis (faster for entity enumeration)
            # Only use models with 65K+ output limit for synthesis
            if not model_override:
                models['synthesis'] = ['gemini-2.5-flash', 'deepseek-v3.2', 'claude-sonnet-4-5']
                logger.debug(f"[CLONE] FINDALL mode: Using model chain {models['synthesis']} for synthesis")

        logger.debug(f"[CLONE] Strategy: {strategy['name']} (breadth={breadth}, depth={depth})")
        logger.debug(f"[CLONE] Synthesis tier: {synthesis_tier} (model: {models['synthesis']})")
        logger.debug(f"[CLONE] Params: batch={strategy['sources_per_batch']}, mode={strategy['extraction_mode']}, max_snippets={strategy['max_snippets_per_source']}, min_p={strategy['min_p_threshold']}")
        logger.debug(f"[CLONE] Search terms: {search_terms}")
        
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
            logger.debug(f"[CLONE] Academic mode (backdoor) - using {len(search_include_domains)} academic domains")
        elif academic:
            from the_clone.academic_domains import get_academic_domains
            search_include_domains = get_academic_domains()
            logger.debug(f"[CLONE] Academic mode - using {len(search_include_domains)} academic domains")
        elif include_domains:
            search_include_domains = include_domains
            logger.debug(f"[CLONE] Using {len(search_include_domains)} included domains")
        elif exclude_domains:
            search_exclude_domains = exclude_domains
            logger.debug(f"[CLONE] Using {len(search_exclude_domains)} excluded domains")

        # Step 1.5: Memory Recall
        memory_sources = []
        memory_snippets = []  # NEW: Snippets extracted from memory (before search decision)
        recall_result = None
        memory = None  # Initialize memory variable
        search_decision = {'action': 'full_search', 'search_terms': search_terms, 'reasoning': 'Memory not enabled'}

        # Debug memory availability
        logger.debug(f"[MEMORY_CHECK] use_memory={use_memory}, session_id={session_id}, email={email}, s3_manager={type(s3_manager).__name__ if s3_manager else None}")

        if use_memory and session_id and email and s3_manager:
            logger.debug("\n[CLONE] Step 1.5: Checking memory...")
            step_start_phase = time.time()
            if clone_logger:
                clone_logger.start_step("Memory Recall")

            try:
                # Use MemoryCache for shared memory access (single S3 load, shared across agents)
                from the_clone.search_memory_cache import MemoryCache
                memory = MemoryCache.get(session_id, email, s3_manager, self.ai_client)

                # Log memory statistics
                mem_stats = memory.get_stats()
                if clone_logger:
                    clone_logger.log_section("Memory Statistics", {
                        "Total Queries in Memory": mem_stats['total_queries'],
                        "Total Sources": mem_stats['total_sources'],
                        "Unique URLs": mem_stats['unique_urls'],
                        "Last Updated": mem_stats.get('last_updated', 'N/A')
                    }, level=4, collapse=True)

                # Skip expensive recall if memory is empty
                if mem_stats['total_queries'] == 0:
                    logger.debug("[CLONE] Memory is empty, skipping recall (no Gemini cost)")
                    if clone_logger:
                        clone_logger.log_section("Memory Recall Skipped", "No queries in memory - proceeding directly to search", level=3)
                        step_time_phase = time.time() - step_start_phase
                        clone_logger.record_step_metric("Memory Recall", "skipped", "N/A", 0.0, step_time_phase, "Empty memory")
                        clone_logger.end_step("Memory Recall")
                    # Fall through to search with default search_decision
                    raise Exception("SKIP_MEMORY")  # Use exception to jump to search

                # URL-based recall: Look up any URLs mentioned in the original query
                # Pass required_keywords so memory can validate if stored content is sufficient
                url_matched_sources = []
                query_urls = extract_urls_from_text(prompt)
                if query_urls:
                    logger.debug(f"[CLONE] Found {len(query_urls)} URLs in query, checking memory...")
                    url_lookup_result = memory.recall_by_urls(
                        query_urls,
                        required_keywords=required_keywords
                    )
                    url_matched_sources = url_lookup_result['found']
                    urls_not_in_memory = url_lookup_result['not_found']
                    urls_need_fetch = url_lookup_result.get('needs_fetch', [])  # URLs that failed keyword validation

                    if url_matched_sources:
                        logger.debug(f"[CLONE] URL lookup: {len(url_matched_sources)} sources found in memory (passing keywords)")

                    if urls_need_fetch:
                        logger.debug(f"[CLONE] URL lookup: {len(urls_need_fetch)} URLs need fresh fetch (failed keyword validation)")

                    # Combine URLs that need fetching: not in memory + failed keyword validation
                    urls_to_fetch = list(set(urls_not_in_memory + urls_need_fetch))

                    # Fetch URLs via Jina
                    if urls_to_fetch:
                        logger.debug(f"[CLONE] Fetching {len(urls_to_fetch)} URLs...")
                        fetched_sources = await memory.fetch_url_content(urls_to_fetch)
                        if fetched_sources:
                            url_matched_sources.extend(fetched_sources)
                            logger.debug(f"[CLONE] Live fetch: {len(fetched_sources)} URLs fetched via Jina")

                    if url_matched_sources and clone_logger:
                        clone_logger.log_section("URL Memory Lookup", {
                            "URLs in Query": query_urls,
                            "Found in Memory (passing)": len(url_lookup_result['found']),
                            "Needs Fetch (failed keywords)": len(urls_need_fetch),
                            "Not in Memory": len(urls_not_in_memory),
                            "Fetched Live": len(fetched_sources) if 'fetched_sources' in dir() else 0,
                            "Total URL Sources": len(url_matched_sources),
                            "Matched URLs": [s['url'] for s in url_matched_sources],
                            "Full Content Sources": sum(1 for s in url_matched_sources if s.get('_is_full_content'))
                        }, level=4, collapse=True)

                # Recall relevant memories (keyword-based + URL sources)
                # URL sources are passed to Gemini for selection and always included in verification
                # Required keywords: entities that MUST appear in sources (ANY match, case-insensitive)
                # search_terms passed for per-term confidence assessment
                if clone_logger:
                    clone_logger.log_section("Starting Recall", {
                        "Search Terms": search_terms,
                        "Required Keywords": required_keywords,
                        "Positive Keywords": positive_keywords[:5] if positive_keywords else [],  # Truncate for readability
                        "Breadth": breadth,
                        "Depth": depth,
                        "URL Sources Found": len(url_matched_sources)
                    }, level=4, collapse=True)
                recall_result = await memory.recall(
                    query=prompt,
                    keywords={
                        'required': required_keywords,
                        'positive': positive_keywords,
                        'negative': negative_keywords
                    },
                    max_results=10,
                    confidence_threshold=0.8,
                    breadth=breadth,
                    depth=depth,
                    url_sources=url_matched_sources,  # Pass URL sources for Gemini consideration
                    search_terms=search_terms,  # Pass for per-term confidence assessment
                    skip_verification=True,  # NEW: Extract first, then verify based on snippets
                    row_identifiers=row_context  # Filter by row to prevent cross-contamination
                )

                memory_sources = recall_result['memories']
                recall_meta = recall_result['recall_metadata']

                logger.debug(
                    f"[CLONE] Memory recall: {len(memory_sources)} sources "
                    f"(url_sources={recall_meta.get('url_sources_count', 0)}), "
                    f"verification_skipped=True, cost=${recall_meta['recall_cost']:.4f}"
                )

                # Extract from memory sources BEFORE assessing confidence
                # But first, check if we have pre-extracted citations (citation-aware memory)
                memory_snippets = []
                memory_extract_cost = 0.0  # Track extraction cost separately
                memory_extract_provider = None
                citation_recall_count = 0  # Track how many sources used citation recall

                if memory_sources:
                    logger.debug(f"[CLONE] Processing {len(memory_sources)} memory sources...")
                    extract_start = time.time()

                    # Citation-aware recall: Check for pre-extracted citations
                    # This avoids redundant extraction when we already have good citations
                    sources_needing_extraction = []
                    from the_clone.search_memory_cache import MemoryCache

                    # Track citation recall results for debug logging
                    citation_recall_details = []

                    for source in memory_sources:
                        source_url = source.get('url')
                        if source_url:
                            try:
                                # Check if we have matching citations for this source
                                citation_result = MemoryCache.recall_citations(
                                    session_id=session_id,
                                    url=source_url,
                                    required_keywords=required_keywords
                                )

                                if citation_result.get('found') and not citation_result.get('needs_extraction'):
                                    # We have pre-extracted citations - convert to snippet format
                                    recalled_citations = citation_result.get('citations', [])
                                    for i, citation in enumerate(recalled_citations):
                                        p_score = citation.get('p_score', 0.8)
                                        snippet = {
                                            'id': f'SC.{citation_recall_count + 1}.{i + 1}-p{p_score:.2f}',  # SC = Snippet from Citation
                                            'text': citation.get('quote', ''),
                                            'p': p_score,
                                            'c': 'H/S',  # High reliability, stored citation
                                            'verbal_handle': citation.get('context', source.get('title', '')),
                                            'validation_reason': f"Recalled from citation store (keywords: {citation.get('hit_keywords', [])})",
                                            'search_ref': 1,
                                            '_source_title': source.get('title', ''),
                                            '_source_url': source_url,
                                            '_source_date': source.get('date', ''),
                                            '_search_term': source.get('_original_query', ''),
                                            '_from_citation_recall': True,
                                            '_from_memory': True  # Track as memory source for logging
                                        }
                                        memory_snippets.append(snippet)
                                    citation_recall_count += 1
                                    logger.debug(f"[CLONE] Citation recall HIT: {len(recalled_citations)} citations for {source_url[:50]}...")

                                    # Record for debug log
                                    citation_recall_details.append({
                                        "status": "USED",
                                        "url": source_url[:80],
                                        "title": source.get('title', 'Unknown')[:50],
                                        "citations_returned": len(recalled_citations),
                                        "hit_keywords": [c.get('hit_keywords', []) for c in recalled_citations[:3]],  # First 3
                                        "quotes_preview": [c.get('quote', '')[:60] + '...' for c in recalled_citations[:2]]
                                    })
                                elif citation_result.get('found'):
                                    # Source exists but no matching citations - need extraction
                                    sources_needing_extraction.append(source)

                                    # Record for debug log - citations exist but didn't match
                                    available_sources = citation_result.get('sources', [])
                                    citation_recall_details.append({
                                        "status": "MISS_NO_MATCH",
                                        "url": source_url[:80],
                                        "title": source.get('title', 'Unknown')[:50],
                                        "reason": "Source has citations but none match required keywords",
                                        "required_keywords": required_keywords,
                                        "available_sources": len(available_sources)
                                    })
                                else:
                                    # No source found at all
                                    sources_needing_extraction.append(source)
                                    citation_recall_details.append({
                                        "status": "MISS_NO_SOURCE",
                                        "url": source_url[:80],
                                        "title": source.get('title', 'Unknown')[:50],
                                        "reason": "No citations stored for this URL"
                                    })
                            except Exception as e:
                                # Citation recall failed - fall back to extraction
                                logger.warning(f"[CLONE] Citation recall failed for {source_url[:50]}: {e}")
                                sources_needing_extraction.append(source)
                                citation_recall_details.append({
                                    "status": "ERROR",
                                    "url": source_url[:80],
                                    "error": str(e)[:100]
                                })
                        else:
                            sources_needing_extraction.append(source)

                    # Log citation recall details to debug file
                    if clone_logger and citation_recall_details:
                        used_count = sum(1 for d in citation_recall_details if d['status'] == 'USED')
                        miss_no_match = sum(1 for d in citation_recall_details if d['status'] == 'MISS_NO_MATCH')
                        miss_no_source = sum(1 for d in citation_recall_details if d['status'] == 'MISS_NO_SOURCE')

                        clone_logger.log_section("Citation-Aware Memory Recall", {
                            "Summary": {
                                "Total Sources Checked": len(memory_sources),
                                "Citations USED (skipped extraction)": used_count,
                                "MISS - No Matching Citations": miss_no_match,
                                "MISS - No Source Stored": miss_no_source,
                                "Required Keywords": required_keywords
                            },
                            "Per-Source Details": citation_recall_details
                        }, level=4, collapse=False)

                    if citation_recall_count > 0:
                        logger.debug(f"[CLONE] Citation recall: {citation_recall_count} sources used cached citations, {len(sources_needing_extraction)} need extraction")

                    # Extract from remaining sources that don't have cached citations
                    if sources_needing_extraction:
                        if clone_logger:
                            clone_logger.log_section("Memory Extraction Starting", {
                                "Sources to Extract": len(sources_needing_extraction),
                                "Extraction Model": models['extraction'],
                                "Snippet ID Prefix": "SM (Snippet from Memory)"
                            }, level=4, collapse=True)

                        # Prepare memory sources for extraction (add metadata extraction expects)
                        for rank_idx, source in enumerate(sources_needing_extraction):
                            source['_search_term'] = source.get('_original_query', 'Memory')
                            source['_search_index'] = 1
                            source['_search_ref'] = 1
                            source['_rank_position'] = rank_idx

                        # Extract using batch extraction
                        batch_result = await self.snippet_extractor.extract_from_sources_batch(
                            sources=sources_needing_extraction,
                            query=prompt,
                            snippet_id_prefix="SM",  # SM = Snippet from Memory
                            all_search_terms=search_terms,
                            model=models['extraction'],
                            soft_schema=False,
                            min_quality_threshold=strategy['min_p_threshold'],
                            extraction_mode=strategy['extraction_mode'],
                            max_snippets_per_source=strategy['max_snippets_per_source'],
                            clone_logger=clone_logger,
                            provider=provider,
                            start_source_index=1,
                            accept_all_quality_levels=strategy.get('accept_all_quality_levels', False)
                        )

                        # Collect extracted snippets and mark as from memory
                        for source_result in batch_result:
                            snippets = source_result.get('snippets', [])
                            for snippet in snippets:
                                snippet['_from_memory'] = True  # Track as memory source
                            memory_snippets.extend(snippets)

                        # Track cost
                        if batch_result and len(batch_result) > 0:
                            model_response = batch_result[0].get('model_response', {})
                            memory_extract_cost, memory_extract_provider = self._extract_cost_and_provider(model_response, clone_logger, stats)
                            costs['extraction'] = costs.get('extraction', 0.0) + memory_extract_cost
                            costs_by_provider[memory_extract_provider] = costs_by_provider.get(memory_extract_provider, 0.0) + memory_extract_cost
                            calls_by_provider[memory_extract_provider] = calls_by_provider.get(memory_extract_provider, 0) + 1

                    extract_time = time.time() - extract_start
                    logger.debug(
                        f"[CLONE] Memory processing: {len(memory_snippets)} snippets "
                        f"({citation_recall_count} from cache, {len(sources_needing_extraction)} extracted) "
                        f"({extract_time:.2f}s, ${memory_extract_cost:.4f})"
                    )

                    # Log memory extraction results
                    if clone_logger:
                        # Summarize extracted snippets
                        snippet_summary = []
                        for i, snippet in enumerate(memory_snippets[:10]):  # First 10
                            p_score = snippet.get('p', 0)
                            text_preview = snippet.get('text', '')[:100]
                            source_type = "CACHE" if snippet.get('_from_citation_recall') else "EXTRACT"
                            snippet_summary.append(f"[{snippet.get('id', i)}] ({source_type}) p={p_score:.2f}: {text_preview}...")

                        clone_logger.log_section("Memory Processing Results", {
                            "Total Sources": len(memory_sources),
                            "Sources with Cached Citations": citation_recall_count,
                            "Sources Extracted": len(sources_needing_extraction),
                            "Total Snippets": len(memory_snippets),
                            "From Citation Cache": sum(1 for s in memory_snippets if s.get('_from_citation_recall')),
                            "From Extraction": sum(1 for s in memory_snippets if not s.get('_from_citation_recall')),
                            "Processing Time": f"{extract_time:.2f}s",
                            "Extraction Cost": f"${memory_extract_cost:.4f}",
                            "Provider": memory_extract_provider or "N/A (used cache)",
                            "Avg Quality": f"{sum(s.get('p', 0) for s in memory_snippets) / len(memory_snippets):.2f}" if memory_snippets else "N/A",
                            "High Quality (p>=0.85)": sum(1 for s in memory_snippets if s.get('p', 0) >= 0.85),
                            "Snippet Preview": snippet_summary if snippet_summary else "No snippets"
                        }, level=4, collapse=False)

                    # Store newly extracted snippets as citations for future recall
                    newly_extracted = [s for s in memory_snippets if not s.get('_from_citation_recall')]
                    if newly_extracted and session_id:
                        self._store_snippets_as_citations(
                            snippets=newly_extracted,
                            session_id=session_id,
                            all_keywords=required_keywords + positive_keywords,
                            source_type="memory_extraction"
                        )

                # Assess confidence based on ACTUAL extracted snippets
                # (runs even if memory_sources was empty - will return 0 confidence)
                from the_clone.snippet_confidence import assess_snippet_confidence

                confidence_assessment = await assess_snippet_confidence(
                    snippets=memory_snippets,
                    search_terms=search_terms,
                    breadth=breadth,
                    depth=depth,
                    ai_client=self.ai_client
                )

                confidence = confidence_assessment['overall_confidence']
                confidence_vector = confidence_assessment['confidence_vector']
                snippet_counts = confidence_assessment['snippet_counts']
                recommended_searches = confidence_assessment['recommended_searches']

                logger.debug(
                    f"[CLONE] Snippet-based confidence: {confidence:.2f} "
                    f"(counts={snippet_counts}, vector={confidence_vector})"
                )

                # Log snippet-based confidence assessment
                if clone_logger:
                    conf_info = {
                        "Overall Confidence": f"{confidence:.2f}",
                        "Assessment Method": "Snippet-based (extract-then-verify)",
                        "Snippets Assessed": len(memory_snippets),
                    }
                    # Per-term breakdown
                    for i, term in enumerate(search_terms):
                        term_conf = confidence_vector[i] if i < len(confidence_vector) else 0.0
                        term_count = snippet_counts[i] if i < len(snippet_counts) else 0
                        conf_info[f"Term {i+1}: \"{term[:40]}\""] = f"conf={term_conf:.2f}, snippets={term_count}"

                    if recommended_searches:
                        conf_info["Recommended Searches"] = recommended_searches
                    else:
                        conf_info["Recommended Searches"] = "None (all terms covered)"

                    clone_logger.log_section("Snippet-Based Confidence", conf_info, level=4, collapse=False)

                # Update recall_result with snippet-based confidence
                recall_result['confidence'] = confidence
                recall_result['confidence_vector'] = confidence_vector
                recall_result['recommended_searches'] = recommended_searches
                recall_result['search_term_confidence'] = {
                    term: confidence_vector[i] if i < len(confidence_vector) else 0.0
                    for i, term in enumerate(search_terms)
                }

                logger.debug(
                    f"[CLONE] Updated confidence after extraction: {confidence:.2f}, "
                    f"recommended_searches={recommended_searches}"
                )

                # Log recall details
                if clone_logger:
                    recall_info = {
                        "Total Queries Searched": recall_meta['total_queries'],
                        "Queries After Keyword Filter": recall_meta['filtered_queries'],
                        "Sources Selected": recall_meta['sources_selected'],
                        "URL Sources (from query)": recall_meta.get('url_sources_count', 0),
                        "Overall Confidence": f"{confidence:.2f}",
                        "Recall Time": f"{recall_meta['recall_time_ms']:.0f}ms",
                        "Recall Cost": f"${recall_meta['recall_cost']:.4f}",
                        "Verification Run": recall_meta.get('verification_run', False)
                    }

                    # Always show per-term confidence if available
                    per_term_conf = recall_result.get('search_term_confidence', {})
                    if per_term_conf:
                        recall_info["Per-Term Confidence"] = per_term_conf

                    # Show recommended searches (terms that need fresh search)
                    recommended = recall_result.get('recommended_searches', [])
                    if recommended:
                        recall_info["Terms Needing Search"] = recommended
                    else:
                        recall_info["Terms Needing Search"] = "None (all covered by memory)"

                    # Add verification info if it ran
                    if recall_meta.get('verification_run'):
                        recall_info["Verification Note"] = "Full snippet verification completed"

                    # Add confidence interpretation
                    if confidence >= 0.85:
                        recall_info["Confidence Level"] = "HIGH (>=0.85) - Can skip search"
                    elif confidence >= 0.6:
                        recall_info["Confidence Level"] = "MEDIUM (0.6-0.85) - Supplement search recommended"
                    else:
                        recall_info["Confidence Level"] = "LOW (<0.6) - Full search needed"

                    clone_logger.log_section("Recall Results", recall_info, level=4, collapse=False)

                # Track recall cost
                recall_cost = recall_meta['recall_cost']
                costs['recall'] = recall_cost  # Add to stage breakdown
                costs_by_provider['gemini'] = costs_by_provider.get('gemini', 0.0) + recall_cost
                calls_by_provider['gemini'] = calls_by_provider.get('gemini', 0) + 1

                # Decide search strategy based on memory
                # Per-search-term confidence filtering: only low confidence terms get fresh searches
                search_decision = self._decide_search_strategy(
                    recall_result, prompt, search_terms, force_min_searches=0
                )

                logger.debug(f"[CLONE] Search decision: {search_decision['action']} - {search_decision['reasoning']}")

                # Log search decision
                if clone_logger:
                    decision_info = {
                        "Action": search_decision['action'].upper(),
                        "Reasoning": search_decision['reasoning'],
                        "Original Search Terms Count": len(initial_result.get('search_terms', [])),
                        "Final Search Terms Count": len(search_decision['search_terms'])
                    }
                    # Show actual search terms that will be executed
                    if search_decision['search_terms']:
                        decision_info["Search Terms to Execute"] = search_decision['search_terms']
                    else:
                        decision_info["Search Terms to Execute"] = "NONE (using memory only)"

                    # Add cost savings info for skip/supplement
                    if search_decision['action'] == 'skip':
                        decision_info["Cost Savings"] = "~$0.005 (search skipped)"
                    elif search_decision['action'] == 'supplement':
                        original_count = len(initial_result.get('search_terms', []))
                        final_count = len(search_decision['search_terms'])
                        savings = (original_count - final_count) * 0.005
                        if savings > 0:
                            decision_info["Cost Savings"] = f"~${savings:.3f} ({original_count - final_count} searches avoided)"

                    clone_logger.log_section("Search Decision", decision_info, level=4, collapse=False)

                # Log memory sources
                if clone_logger and memory_sources:
                    sources_preview = []
                    for i, src in enumerate(memory_sources[:5], 1):  # Show first 5
                        snippet_preview = src.get('snippet', '')[:80] if src.get('snippet') else '[EMPTY]'
                        title = src.get('title', 'Unknown')[:60]
                        url = src.get('url', 'Unknown')
                        original_query = src.get('_original_query', '[Live Fetch]')
                        age_days = src.get('_memory_age_days', 0)
                        freshness = src.get('_freshness_indicator', 'live')
                        relevance = src.get('_memory_relevance', 0.0)
                        sources_preview.append(
                            f"{i}. **{title}...**\n"
                            f"   - URL: {url}\n"
                            f"   - Original Query: \"{original_query}\"\n"
                            f"   - Age: {age_days} days ({freshness})\n"
                            f"   - Relevance: {relevance:.1f}\n"
                            f"   - Snippet: {snippet_preview}"
                        )
                    if len(memory_sources) > 5:
                        sources_preview.append(f"\n... and {len(memory_sources) - 5} more sources")

                    clone_logger.log_section(
                        f"Memory Sources Retrieved ({len(memory_sources)} total)",
                        "\n\n".join(sources_preview),
                        level=4,
                        collapse=True
                    )

                # Update search_terms based on decision
                search_terms = search_decision['search_terms']

                step_time_phase = time.time() - step_start_phase
                if clone_logger:
                    # Calculate total memory cost (recall + extraction)
                    total_memory_cost = recall_cost + memory_extract_cost
                    # Build provider string (recall is always gemini, extraction may differ)
                    if memory_extract_provider and memory_extract_provider != 'gemini':
                        provider_str = f"gemini+{memory_extract_provider}"
                    else:
                        provider_str = "gemini"
                    clone_logger.record_step_metric(
                        "Memory Recall", provider_str, "gemini-2.5-flash-lite",
                        total_memory_cost, step_time_phase,
                        f"{len(memory_sources)} sources, {len(memory_snippets)} snippets, confidence={confidence:.2f}"
                    )
                    clone_logger.end_step("Memory Recall")

            except Exception as e:
                step_time_phase = time.time() - step_start_phase
                if str(e) == "SKIP_MEMORY":
                    # Intentional skip - memory was empty, no warning needed
                    search_decision = {'action': 'full_search', 'search_terms': search_terms, 'reasoning': 'Memory empty - skipped'}
                    # Note: end_step already called in the empty memory check above
                else:
                    logger.warning(f"[CLONE] Memory recall failed, continuing with full search: {e}")
                    search_decision = {'action': 'full_search', 'search_terms': search_terms, 'reasoning': f'Memory error: {str(e)}'}
                    # Log the error and close the step
                    if clone_logger:
                        clone_logger.log_section("Memory Recall Error", {
                            "Error": str(e),
                            "Error Type": type(e).__name__,
                            "Action": "Proceeding with full search"
                        }, level=4, collapse=False)
                        clone_logger.record_step_metric(
                            "Memory Recall", "error", "N/A",
                            0.0, step_time_phase,
                            f"Error: {type(e).__name__}"
                        )
                        clone_logger.end_step("Memory Recall")
        else:
            # Memory not available - log why
            reason = None
            if not use_memory:
                reason = "Memory disabled (use_memory=False)"
                logger.debug("[CLONE] Memory disabled (use_memory=False)")
            elif not session_id or not email or not s3_manager:
                missing = []
                if not session_id:
                    missing.append("session_id")
                if not email:
                    missing.append("email")
                if not s3_manager:
                    missing.append("s3_manager")
                reason = f"Missing required parameters: {', '.join(missing)}"
                logger.debug(f"[CLONE] Memory not available ({reason})")

            if clone_logger and reason:
                clone_logger.log_section("Memory Status", {
                    "Status": "NOT AVAILABLE",
                    "Reason": reason,
                    "Action": "Proceeding with full search"
                }, level=4, collapse=True)

        # Build search settings (needed even if skipping, for memory storage)
        search_settings = {
            'max_results': strategy.get('max_results_per_search', 10)
        }
        if 'max_tokens_per_page' in strategy:
            search_settings['max_tokens_per_page'] = strategy['max_tokens_per_page']

        # Step 2: Search
        if search_terms:
            logger.debug(f"\n[CLONE] Step 2: Executing {len(search_terms)} searches...")
            step_start_phase = time.time()
            if clone_logger:
                clone_logger.start_step("Search Execution")

            search_results = await self.search_manager.execute_searches(
                search_terms=search_terms,
                search_settings=search_settings,
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
                clone_logger.record_step_metric("Search", "perplexity", "Search API", search_cost, step_time_phase, f"{len(search_terms)} queries, {total_results} results")
                clone_logger.end_step("Search Execution")

            # Store search results in memory (RAM only, flushed at batch end)
            if use_memory and session_id and email and s3_manager:
                try:
                    from the_clone.search_memory_cache import MemoryCache
                    stored_count = 0
                    total_urls_indexed = 0
                    for term, result in zip(search_terms, search_results):
                        if not isinstance(result, Exception):
                            MemoryCache.store_search(
                                session_id=session_id,
                                search_term=term,
                                results=result,
                                parameters=search_settings,
                                strategy=strategy['name'],
                                row_context=row_context
                            )
                            stored_count += 1
                            total_urls_indexed += len(result.get('results', []))
                    # Log for MEMORY_URL_STORAGE_ISSUE debugging
                    logger.info(f"[CLONE_MEMORY_DEBUG] Stored {stored_count} searches with {total_urls_indexed} URLs to memory (RAM cache)")
                except Exception as e:
                    logger.warning(f"[MEMORY] Failed to store searches: {e}")
        else:
            logger.debug(f"\n[CLONE] Step 2: Skipping search (using memory only)")
            search_results = []

        # Step 2.5: Deduplicate memory snippets vs search results (by URL)
        original_memory_count = len(memory_sources)
        original_search_count = len(search_terms) if search_terms else 0

        if memory_snippets and search_results:
            # Get URLs already covered by memory snippets
            memory_urls = {s.get('_source_url') for s in memory_snippets if s.get('_source_url')}

            # Remove duplicate URLs from search results (memory already has them)
            total_deduped = 0
            for result in search_results:
                if not isinstance(result, Exception):
                    original_len = len(result.get('results', []))
                    result['results'] = [r for r in result.get('results', []) if r.get('url') not in memory_urls]
                    total_deduped += original_len - len(result.get('results', []))

            if total_deduped > 0:
                logger.debug(f"[CLONE] Deduped {total_deduped} search results (URLs already in memory snippets)")

        # Step 3: Triage SEARCH RESULTS ONLY (memory already extracted)
        # Pass memory_snippets as existing_snippets so triage knows what we have
        memory_only = (search_decision.get('action') == 'skip' and len(search_results) == 0)

        if memory_only:
            logger.debug(f"\n[CLONE] Step 3: Skipping triage (no search results, using memory snippets only)")
            # Memory snippets already extracted - nothing more to triage/extract
            ranked_sources = []

            if clone_logger:
                clone_logger.log_section("Triage Skipped", f"No search results to triage - using {len(memory_snippets)} memory snippets", level=3, collapse=False)
        else:
            logger.debug(f"\n[CLONE] Step 3: Ranking sources...")
            step_start_phase = time.time()
            if clone_logger:
                clone_logger.start_step("Source Triage")

            ranked_lists, triage_results = await self.source_triage.triage_all_searches(
                search_results=search_results,
                search_terms=search_terms,
                query=prompt,
                existing_snippets=memory_snippets,  # Triage sees what memory already covers
                positive_keywords=positive_keywords,
                negative_keywords=negative_keywords,
                model=models['triage'],
                soft_schema=False,
                clone_logger=clone_logger,
                provider=provider
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

        # Filter out sources with empty snippets (can't extract from nothing)
        original_count = len(ranked_sources)
        ranked_sources = [s for s in ranked_sources if s.get('snippet', '').strip()]
        if original_count != len(ranked_sources):
            logger.warning(f"[CLONE] Filtered {original_count - len(ranked_sources)} sources with empty snippets")
            if clone_logger:
                clone_logger.log_section("Empty Snippet Filter", f"Removed {original_count - len(ranked_sources)} sources with empty snippets (cannot extract from empty content)", level=3)

        logger.debug(f"[CLONE] Ranked {len(ranked_sources)} search sources to extract")

        if len(ranked_sources) == 0:
            logger.debug("[CLONE] No relevant sources found from triage - proceeding to synthesis for self-correction")
            if clone_logger:
                clone_logger.log_section("Triage Result", "No relevant sources passed triage - synthesis will attempt answer from model knowledge and may suggest new search terms", level=3)

        # Step 4: Iterative Extraction
        # Start with memory snippets (already extracted in memory phase)
        all_snippets = list(memory_snippets)  # Copy to avoid mutation issues
        if memory_snippets:
            logger.debug(f"[CLONE] Starting extraction with {len(memory_snippets)} memory snippets")
            if clone_logger:
                clone_logger.log_section("Memory Snippets Merged", f"Starting with {len(memory_snippets)} snippets from memory extraction", level=3)
        sources_examined = []  # Track sources for synthesis (in case of 0 snippets)
        sources_pulled = 0
        first_extraction_prompt_logged = False
        iteration = 0

        # Skip extraction if no search sources (memory snippets already extracted)
        if len(ranked_sources) == 0:
            if memory_snippets:
                logger.debug(f"\n[CLONE] Step 4: Skipping search extraction (using {len(memory_snippets)} memory snippets)")
                if clone_logger:
                    clone_logger.log_section("Search Extraction Skipped", f"No search sources to extract - proceeding with {len(memory_snippets)} memory snippets", level=3)
            else:
                logger.debug(f"\n[CLONE] Step 4: Skipping extraction (no sources) - will proceed to synthesis")
                if clone_logger:
                    clone_logger.log_section("Extraction Skipped", "No sources to extract from - synthesis will use model knowledge", level=3)
        else:
            logger.debug(f"\n[CLONE] Step 4: Iterative extraction (max {global_limits['max_iterations']} iterations)...")
            step_start_phase = time.time()
            if clone_logger:
                clone_logger.start_step("Extraction")

            # FINDALL MODE: Process sources grouped by search in PARALLEL (one batch per search)
            if strategy.get('bypass_global_source_limit') and strategy.get('batch_extraction'):
                logger.debug(f"[CLONE] FINDALL mode: Processing sources grouped by search in PARALLEL")

                # Group sources by search index
                sources_by_search = {}
                for source in ranked_sources:
                    search_idx = source.get('_search_index', 1)
                    if search_idx not in sources_by_search:
                        sources_by_search[search_idx] = []
                    sources_by_search[search_idx].append(source)

                logger.debug(f"[CLONE] FINDALL: Found {len(sources_by_search)} searches with sources")

                # Track sources examined
                sources_examined.extend(ranked_sources)

                # Create extraction tasks for each search (run in PARALLEL)
                extraction_tasks = []
                for search_idx in sorted(sources_by_search.keys()):
                    search_sources = sources_by_search[search_idx]
                    snippet_id_prefix = f"S{search_idx}"

                    logger.debug(f"[CLONE] FINDALL Search {search_idx}: Queueing {len(search_sources)} sources for batch extraction")

                    task = self.snippet_extractor.extract_from_sources_batch(
                        sources=search_sources,  # All sources for this search in one batch
                        query=prompt,
                        snippet_id_prefix=snippet_id_prefix,
                        all_search_terms=search_terms,
                        model=models['extraction'],
                        soft_schema=False,
                        min_quality_threshold=strategy['min_p_threshold'],
                        extraction_mode=strategy['extraction_mode'],
                        max_snippets_per_source=strategy['max_snippets_per_source'],
                        clone_logger=clone_logger if search_idx == 1 else None,  # Log first only
                        provider=provider,
                        start_source_index=1,
                        accept_all_quality_levels=strategy.get('accept_all_quality_levels', False)
                    )
                    extraction_tasks.append((search_idx, task))

                logger.debug(f"[CLONE] FINDALL: Executing {len(extraction_tasks)} batch extractions IN PARALLEL")

                # Run all search extractions in PARALLEL
                results = await asyncio.gather(*[task for _, task in extraction_tasks], return_exceptions=True)

                # Collect snippets and costs
                iteration_cost = 0.0
                extract_providers = set()

                for (search_idx, _), result in zip(extraction_tasks, results):
                    if isinstance(result, Exception):
                        logger.error(f"[CLONE] FINDALL Search {search_idx} extraction error: {result}")
                        continue

                    # Extract snippets from batch result
                    for source_result in result:
                        snippets = source_result.get('snippets', [])
                        all_snippets.extend(snippets)
                        logger.debug(f"[CLONE] FINDALL Search {search_idx}: Extracted {len(snippets)} snippets")

                    # Extract cost ONCE per batch (not per source - model_response is shared)
                    if result and len(result) > 0:
                        model_response = result[0].get('model_response', {})
                        extract_cost, extract_provider = self._extract_cost_and_provider(model_response, clone_logger, stats)
                        costs['extraction'] += extract_cost
                        iteration_cost += extract_cost
                        costs_by_provider[extract_provider] = costs_by_provider.get(extract_provider, 0.0) + extract_cost
                        calls_by_provider[extract_provider] = calls_by_provider.get(extract_provider, 0) + 1
                        extract_providers.add(extract_provider)

                sources_pulled = len(ranked_sources)
                iteration = len(sources_by_search)

                logger.debug(f"[CLONE] FINDALL: Extracted total of {len(all_snippets)} snippets from {sources_pulled} sources")

            else:
                # EXISTING iteration logic for non-findall strategies
                for iteration_idx in range(1, global_limits['max_iterations'] + 1):
                    iteration = iteration_idx
                    # Log at INFO for iteration > 1 to show progress
                    if iteration > 1:
                        logger.info(f"\n[CLONE] Iteration {iteration}/{global_limits['max_iterations']}")
                    else:
                        logger.debug(f"\n[CLONE] Iteration {iteration}/{global_limits['max_iterations']}")
                    if clone_logger:
                        clone_logger.log_section(f"Iteration {iteration}", f"Pulling sources from index {sources_pulled}", level=3)

                    # Determine batch (restrict to same search term)
                    batch_size = strategy['sources_per_batch']
                    current_search_index = ranked_sources[sources_pulled].get('_search_index')

                    # Find end of batch, stopping if search index changes
                    batch_end = sources_pulled
                    for i in range(sources_pulled, min(sources_pulled + batch_size, len(ranked_sources))):
                        if ranked_sources[i].get('_search_index') != current_search_index:
                            break
                        batch_end = i + 1

                    sources_this_batch = ranked_sources[sources_pulled:batch_end]

                    if len(sources_this_batch) == 0:
                        logger.debug("[CLONE] No more sources to pull")
                        break

                    logger.debug(f"[CLONE] Pulling sources {sources_pulled}-{batch_end-1} ({len(sources_this_batch)} sources)")

                    # Track sources examined (for synthesis visibility when 0 snippets)
                    sources_examined.extend(sources_this_batch)

                    # For code extraction, decide between batch (shallow) or parallel individual (deep)
                    use_batch_single_call = strategy.get('batch_extraction', False) and use_code_extraction

                    if use_batch_single_call:
                        # Batch extraction: ALL sources in SINGLE API call (shallow strategies)
                        logger.debug(f"[CLONE] Using batch extraction (single call) for {len(sources_this_batch)} sources")
                        snippet_id_prefix = f"S{iteration}"

                        batch_result = await self.snippet_extractor.extract_from_sources_batch(
                            sources=sources_this_batch,
                            query=prompt,
                            snippet_id_prefix=snippet_id_prefix,
                            all_search_terms=search_terms,
                            model=models['extraction'],
                            soft_schema=False,
                            min_quality_threshold=strategy['min_p_threshold'],
                            extraction_mode=strategy['extraction_mode'],
                            max_snippets_per_source=strategy['max_snippets_per_source'],
                            clone_logger=clone_logger,
                            provider=provider,
                            start_source_index=sources_pulled + 1,
                            accept_all_quality_levels=strategy.get('accept_all_quality_levels', False)
                        )
                        results = batch_result

                        if not first_extraction_prompt_logged: first_extraction_prompt_logged = True
                    elif use_code_extraction:
                        # Parallel individual extraction: Each source in SEPARATE call (deep strategies)
                        # Still uses batch pathway (for source-level assessment) but one source per call
                        logger.debug(f"[CLONE] Using parallel individual extraction ({len(sources_this_batch)} calls) for deep strategy")
                        extraction_tasks = []
                        for idx, source in enumerate(sources_this_batch):
                            snippet_id_prefix = f"S{iteration}"
                            # Call batch extractor with single source
                            task = self.snippet_extractor.extract_from_sources_batch(
                                sources=[source],  # Single source wrapped in list
                                query=prompt,
                                snippet_id_prefix=snippet_id_prefix,
                                all_search_terms=search_terms,
                                model=models['extraction'],
                                soft_schema=False,
                                min_quality_threshold=strategy['min_p_threshold'],
                                extraction_mode=strategy['extraction_mode'],
                                max_snippets_per_source=strategy['max_snippets_per_source'],
                                clone_logger=clone_logger if idx == 0 else None,  # Only log first
                                provider=provider,
                                start_source_index=sources_pulled + idx + 1,
                                accept_all_quality_levels=strategy.get('accept_all_quality_levels', False)
                            )
                            extraction_tasks.append(task)

                        if not first_extraction_prompt_logged: first_extraction_prompt_logged = True

                        # Run all extractions in parallel
                        batch_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)
                        # Flatten results (each batch_result is a list with 1 item)
                        results = [r[0] for r in batch_results if isinstance(r, list) and len(r) > 0]
                    else:
                        # Legacy non-code extraction (shouldn't happen)
                        logger.debug(f"[CLONE] Using legacy individual extraction for {len(sources_this_batch)} sources")
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
                                soft_schema=False,
                                min_quality_threshold=strategy['min_p_threshold'],
                                extraction_mode=strategy['extraction_mode'],
                                max_snippets_per_source=strategy['max_snippets_per_source'],
                                use_code_extraction=use_code_extraction,
                                clone_logger=clone_logger,
                                log_prompt_collapsed=(first_extraction_prompt_logged),
                                provider=provider
                            )
                            extraction_tasks.append(task)

                        if not first_extraction_prompt_logged: first_extraction_prompt_logged = True

                        results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

                    # Collect snippets and costs by provider
                    new_snippets = []
                    iteration_cost = 0.0
                    extract_providers = set()
                    seen_responses = set()  # Track response objects to avoid double-counting

                    for result in results:
                        if isinstance(result, Exception):
                            logger.error(f"[CLONE] Extraction error: {result}")
                            continue
                        new_snippets.extend(result.get('snippets', []))

                        # Extract cost, but avoid double-counting shared responses
                        model_response = result.get('model_response', {})
                        response_id = id(model_response)  # Use object ID to detect duplicates

                        if response_id not in seen_responses:
                            extract_cost, extract_provider = self._extract_cost_and_provider(model_response, clone_logger, stats)
                            costs['extraction'] += extract_cost
                            iteration_cost += extract_cost
                            costs_by_provider[extract_provider] = costs_by_provider.get(extract_provider, 0.0) + extract_cost
                            calls_by_provider[extract_provider] = calls_by_provider.get(extract_provider, 0) + 1
                            extract_providers.add(extract_provider)
                            seen_responses.add(response_id)

                    all_snippets.extend(new_snippets)
                    sources_pulled = batch_end

                    logger.debug(f"[CLONE] Extracted {len(new_snippets)} snippets (total: {len(all_snippets)})")
                    if all_snippets:
                        avg_p = sum(s.get('p', 0.5) for s in all_snippets) / len(all_snippets)
                        high_p = sum(1 for s in all_snippets if s.get('p', 0) >= 0.85)
                        logger.debug(f"[CLONE] Quality: avg_p={avg_p:.2f}, high_quality={high_p}/{len(all_snippets)}")

                    # Store extracted snippets as citations for future recall
                    if new_snippets and use_memory and session_id:
                        self._store_snippets_as_citations(
                            snippets=new_snippets,
                            session_id=session_id,
                            all_keywords=required_keywords + positive_keywords,
                            source_type="search_extraction"
                        )

                    # Check stop condition
                    if should_stop_iteration(all_snippets, strategy):
                        logger.debug(f"[CLONE] Stop condition met ({strategy.get('stop_condition')})")
                        break

                    if sources_pulled >= len(ranked_sources):
                        logger.debug("[CLONE] All sources exhausted")
                        break

            step_time_phase = time.time() - step_start_phase
            if clone_logger:
                provider_display = list(extract_providers)[0] if len(extract_providers) == 1 else f"mixed:{','.join(sorted(list(extract_providers)))}"
                extract_model = models['extraction']
                # For simplicity, we just list the configured model. Backup models are logged at the individual call level in log_section.
                clone_logger.record_step_metric("Extraction", provider_display, extract_model, costs['extraction'], step_time_phase, f"Extracted {len(all_snippets)} snippets")
                clone_logger.end_step("Extraction")

        # Deduplicate verbal handles across all snippets
        used_handles = {}
        for snippet in all_snippets:
            handle = snippet.get('verbal_handle')
            if handle:
                if handle in used_handles:
                    # Handle collision - append counter
                    used_handles[handle] += 1
                    new_handle = f"{handle}_{used_handles[handle]}"
                    snippet['verbal_handle'] = new_handle
                else:
                    used_handles[handle] = 1

        # Step 5: Synthesis
        logger.debug(f"\n[CLONE] Step 5: Synthesis from {len(all_snippets)} snippets...")
        step_start_phase = time.time()
        if clone_logger:
            clone_logger.start_step("Synthesis")

        # Map strategy to synthesis context
        context_map = {
            'targeted': 'low',
            'focused_deep': 'medium',
            'survey': 'medium',
            'comprehensive': 'high',
            'findall_breadth': 'findall'  # Entity identification mode
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
            soft_schema=False,
            clone_logger=clone_logger,
            initial_decision=decision,  # Pass initial decision to detect source mismatches
            sources_examined=sources_examined  # Pass sources for visibility when 0 snippets
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
        # self_assessment is now extracted in unified_synthesizer before transform loses it
        self_assessment = synthesis_result.get('self_assessment', 'A')
        suggested_search_terms = synthesis_result.get('suggested_search_terms', [])
        request_upgrade = synthesis_result.get('request_capability_upgrade', False)
        note_to_self = synthesis_result.get('note_to_self')
        original_note_to_self = note_to_self  # Preserve original before prefix is added
        previous_answer = synthesis_result.get('answer', {})  # Capture for passing to next iteration
        upgraded = False

        # Track all search terms used across iterations (for deduplication)
        all_search_terms_used = set(search_terms or [])

        # Determine max self-correction iterations (findall mode can do more)
        max_self_corrections = findall_iterations if findall else 1
        self_correction_count = 0

        # Self-correction loop: runs up to max_self_corrections times while we have search terms
        while (self_assessment not in ['A+', 'A']
               and suggested_search_terms
               and self_correction_count < max_self_corrections):

            self_correction_count += 1
            logger.info(f"\n[CLONE] Self-correction {self_correction_count}/{max_self_corrections}: Grade {self_assessment}")

            # Filter out already-used search terms and limit to 2
            suggested_search_terms = [t for t in suggested_search_terms if t not in all_search_terms_used][:2]
            if not suggested_search_terms:
                logger.debug(f"[CLONE] No new search terms to try, stopping self-correction")
                break

            all_search_terms_used.update(suggested_search_terms)
            iteration += 1
            logger.debug(f"[CLONE] Suggested search terms: {suggested_search_terms}")
            if clone_logger:
                clone_logger.log_section("Self-Correction Search", f"Iteration {self_correction_count}: Grade {self_assessment}. Executing: {suggested_search_terms}", level=2)

            # Prepend system message to note_to_self
            prefix = "Providing additional search results that you requested"
            if note_to_self:
                note_to_self = f"{prefix}: {note_to_self}"
            else:
                note_to_self = f"{prefix}."

            # Search
            new_search_results = await self.search_manager.execute_searches(
                search_terms=suggested_search_terms,
                search_settings=search_settings,
                include_domains=search_include_domains,
                exclude_domains=search_exclude_domains,
                clone_logger=clone_logger
            )
            search_cost = len(suggested_search_terms) * 0.005
            costs['search'] += search_cost
            costs_by_provider['perplexity'] += search_cost
            calls_by_provider['perplexity'] += len(suggested_search_terms)
            search_results.extend(new_search_results)

            if clone_logger:
                clone_logger.record_step_metric(
                    "Self-Correction Search",
                    "perplexity",
                    "Search API",
                    search_cost,
                    0.0,
                    f"{len(suggested_search_terms)} queries"
                )

            # Triage
            start_time_corr = time.time()
            correction_triage_cost = 0.0
            new_ranked_lists, new_triage_results = await self.source_triage.triage_all_searches(
                search_results=new_search_results,
                search_terms=suggested_search_terms,
                query=prompt,
                existing_snippets=all_snippets,
                positive_keywords=positive_keywords,
                negative_keywords=negative_keywords,
                model=models['triage'],
                soft_schema=False,
                clone_logger=clone_logger,
                provider=provider
            )
            for result in new_triage_results:
                if not isinstance(result, Exception):
                    triage_cost, triage_provider = self._extract_cost_and_provider(result.get('model_response', {}), clone_logger, stats)
                    correction_triage_cost += triage_cost
                    costs['triage'] += triage_cost
                    costs_by_provider[triage_provider] = costs_by_provider.get(triage_provider, 0.0) + triage_cost
                    calls_by_provider[triage_provider] = calls_by_provider.get(triage_provider, 0) + 1

            if clone_logger:
                clone_logger.record_step_metric(
                    "Self-Correction Triage",
                    provider,
                    models['triage'],
                    correction_triage_cost,
                    time.time() - start_time_corr,
                    f"Ranked {len(new_ranked_lists)} groups"
                )

            # Build pool
            new_ranked_sources = self._build_ranked_source_pool(new_search_results, new_ranked_lists, suggested_search_terms)
            ranked_sources.extend(new_ranked_sources)

            # Extraction
            if new_ranked_sources:
                logger.debug(f"[CLONE] Extracting from {len(new_ranked_sources)} new sources (Parallel)...")

                new_sources_pulled = 0
                total_new_snippets = 0
                extraction_tasks = []

                # Prepare tasks
                current_global_index = sources_pulled + 1  # Start index for continuous numbering

                while new_sources_pulled < len(new_ranked_sources):
                    # Determine batch (restrict to same search term)
                    batch_size = strategy['sources_per_batch']
                    current_search_index = new_ranked_sources[new_sources_pulled].get('_search_index')

                    batch_end = new_sources_pulled
                    for i in range(new_sources_pulled, min(new_sources_pulled + batch_size, len(new_ranked_sources))):
                        if new_ranked_sources[i].get('_search_index') != current_search_index:
                            break
                        batch_end = i + 1

                    sources_this_batch = new_ranked_sources[new_sources_pulled:batch_end]

                    # Add task
                    task = self.snippet_extractor.extract_from_sources_batch(
                        sources=sources_this_batch,
                        query=prompt,
                        snippet_id_prefix=f"S{iteration}",  # Use iteration-specific prefix to avoid ID collisions
                        all_search_terms=list(all_search_terms_used),
                        model=models['extraction'],
                        soft_schema=False,
                        min_quality_threshold=strategy['min_p_threshold'],
                        extraction_mode=strategy['extraction_mode'],
                        max_snippets_per_source=strategy['max_snippets_per_source'],
                        clone_logger=clone_logger,
                        provider=provider,
                        start_source_index=current_global_index,
                        accept_all_quality_levels=strategy.get('accept_all_quality_levels', False)
                    )
                    extraction_tasks.append(task)

                    # Update counters for next batch
                    new_sources_pulled += len(sources_this_batch)
                    current_global_index += len(sources_this_batch)

                # Execute all extraction tasks in parallel
                start_time_corr = time.time()
                correction_extraction_cost = 0.0
                batch_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

                # Process results
                for i, batch_result in enumerate(batch_results):
                    if isinstance(batch_result, Exception):
                        logger.error(f"[CLONE] Extraction batch {i} failed: {batch_result}")
                        continue

                    # Collect snippets from all sources in this batch
                    new_snippets = []
                    for source_result in batch_result:
                        new_snippets.extend(source_result.get('snippets', []))

                    all_snippets.extend(new_snippets)
                    total_new_snippets += len(new_snippets)

                    # Extract cost ONCE per batch (model_response is shared across sources in batch)
                    if batch_result and len(batch_result) > 0:
                        model_response = batch_result[0].get('model_response', {})
                        extract_cost, extract_provider = self._extract_cost_and_provider(model_response, clone_logger, stats)
                        correction_extraction_cost += extract_cost
                        costs['extraction'] += extract_cost
                        costs_by_provider[extract_provider] = costs_by_provider.get(extract_provider, 0.0) + extract_cost
                        calls_by_provider[extract_provider] = calls_by_provider.get(extract_provider, 0) + 1

                # Update global source counter
                sources_pulled += len(new_ranked_sources)

                if clone_logger:
                    clone_logger.record_step_metric(
                        "Self-Correction Extraction",
                        provider,
                        models['extraction'],
                        correction_extraction_cost,
                        time.time() - start_time_corr,
                        f"Extracted {total_new_snippets} new snippets (Parallel)"
                    )

                logger.debug(f"[CLONE] Added {total_new_snippets} new snippets")

            # 2. Determine model for re-synthesis
            target_model = models['synthesis']
            target_soft_schema = False

            if request_upgrade and synthesis_tier != 'tier4':
                logger.debug(f"[CLONE] Upgrading to tier4 (PhD+ capability) as requested")
                tier4_models = get_models_for_tier(provider, 'tier4', strategy=strategy)
                target_model = tier4_models['synthesis']
                # ai_client will handle soft_schema automatically for DeepSeek/Baseten
                target_soft_schema = False
                synthesis_tier = 'tier4'
                models['synthesis'] = target_model # Update current model state
                upgraded = True
                action_name = "Tier 4 Upgrade & Re-Synthesis"
            else:
                logger.debug(f"[CLONE] Re-synthesizing with current model ({target_model})")
                action_name = "Re-Synthesis (Current Model)"

            step_start_phase = time.time()
            if clone_logger:
                clone_logger.start_step(action_name)
                clone_logger.log_section(action_name, f"Self-assessment: {self_assessment}. Re-running synthesis.", level=2)

            logger.debug(f"[CLONE] Retrying synthesis with {target_model}")

            # Build previous iteration data to pass to synthesis
            previous_iteration_data = {
                'iteration': self_correction_count,  # Track actual iteration number
                'grade': self_assessment,
                'response': previous_answer,
                'note_to_self': original_note_to_self or '',  # Original note before prefix was added
                'search_terms': list(all_search_terms_used)  # All search terms used across iterations
            }

            synthesis_result = await self.unified_synthesizer.evaluate_and_synthesize(
                query=prompt,
                snippets=all_snippets,
                context=synthesis_context,
                iteration=iteration,
                is_last_iteration=True,
                schema=schema,
                model=target_model,
                search_terms=list(all_search_terms_used),
                debug_dir=debug_dir,
                soft_schema=target_soft_schema,
                clone_logger=clone_logger,
                note_to_self=note_to_self,
                initial_decision=decision,  # Pass initial decision
                sources_examined=sources_examined,  # Pass examined sources
                previous_iteration_data=previous_iteration_data  # Pass previous iteration data
            )

            tier4_cost, tier4_provider = self._extract_cost_and_provider(synthesis_result.get('model_response', {}), clone_logger, stats)
            costs['synthesis'] += tier4_cost
            costs_by_provider[tier4_provider] = costs_by_provider.get(tier4_provider, 0.0) + tier4_cost
            calls_by_provider[tier4_provider] = calls_by_provider.get(tier4_provider, 0) + 1

            step_time_phase = time.time() - step_start_phase
            if clone_logger:
                model_resp = synthesis_result.get('model_response', {})
                used_model = model_resp.get('model_used', target_model)
                if model_resp.get('used_backup_model'): used_model += " (Backup)"
                clone_logger.record_step_metric(action_name, tier4_provider, used_model, tier4_cost, step_time_phase, "Re-synthesized")
                clone_logger.end_step(action_name)

            # Extract values for next iteration (if loop continues)
            answer_data = synthesis_result.get('answer', {})
            self_assessment = answer_data.get('self_assessment', 'A') if isinstance(answer_data, dict) else 'A'
            suggested_search_terms = synthesis_result.get('suggested_search_terms', [])
            previous_answer = synthesis_result.get('answer', {})
            logger.debug(f"[CLONE] Self-correction {self_correction_count} complete: grade={self_assessment}, new_terms={len(suggested_search_terms)}")

        # Handle tier4 upgrade request if loop didn't run (no search terms but upgrade requested)
        if (self_correction_count == 0
            and self_assessment not in ['A+', 'A']
            and request_upgrade
            and synthesis_tier != 'tier4'):

            logger.info(f"[CLONE] Grade {self_assessment} with upgrade request (no search terms). Upgrading to tier4.")
            tier4_models = get_models_for_tier(provider, 'tier4', strategy=strategy)
            target_model = tier4_models['synthesis']
            synthesis_tier = 'tier4'
            models['synthesis'] = target_model
            upgraded = True

            step_start_phase = time.time()
            if clone_logger:
                clone_logger.start_step("Tier 4 Upgrade (No Search)")
                clone_logger.log_section("Tier 4 Upgrade", f"Grade {self_assessment}. Upgrading model without new searches.", level=2)

            synthesis_result = await self.unified_synthesizer.evaluate_and_synthesize(
                query=prompt,
                snippets=all_snippets,
                context=synthesis_context,
                iteration=iteration,
                is_last_iteration=True,
                schema=schema,
                model=target_model,
                search_terms=list(all_search_terms_used),
                debug_dir=debug_dir,
                soft_schema=False,
                clone_logger=clone_logger,
                note_to_self=note_to_self,
                initial_decision=decision,
                sources_examined=sources_examined,
                previous_iteration_data={
                    'iteration': 1,
                    'grade': self_assessment,
                    'response': previous_answer,
                    'note_to_self': original_note_to_self or '',
                    'search_terms': list(all_search_terms_used)
                }
            )

            upgrade_cost, upgrade_provider = self._extract_cost_and_provider(synthesis_result.get('model_response', {}), clone_logger, stats)
            costs['synthesis'] += upgrade_cost
            costs_by_provider[upgrade_provider] = costs_by_provider.get(upgrade_provider, 0.0) + upgrade_cost
            calls_by_provider[upgrade_provider] = calls_by_provider.get(upgrade_provider, 0) + 1

            step_time_phase = time.time() - step_start_phase
            if clone_logger:
                model_resp = synthesis_result.get('model_response', {})
                used_model = model_resp.get('model_used', target_model)
                if model_resp.get('used_backup_model'): used_model += " (Backup)"
                clone_logger.record_step_metric("Tier 4 Upgrade (No Search)", upgrade_provider, used_model, upgrade_cost, step_time_phase, "Upgraded")
                clone_logger.end_step("Tier 4 Upgrade (No Search)")

            answer_data = synthesis_result.get('answer', {})
            self_assessment = answer_data.get('self_assessment', 'A') if isinstance(answer_data, dict) else 'A'

        # Warn if low grade but no self-correction was possible
        elif self_correction_count == 0 and self_assessment not in ['A+', 'A']:
            logger.warning(f"[CLONE] Low self-assessment ({self_assessment}) but no search terms suggested. Returning best effort.")

        # Build response
        total_time = time.time() - call_start_time # Use overall start time
        total_cost = sum(costs.values())
        total_cost_by_provider = sum(costs_by_provider.values())

        # Sanity check: both totals should match
        if abs(total_cost - total_cost_by_provider) > 0.0001:
            logger.warning(f"[CLONE] Cost mismatch! By-stage: ${total_cost:.4f}, By-provider: ${total_cost_by_provider:.4f}")

        logger.info(f"\n[CLONE] Complete in {total_time:.1f}s, Cost: ${total_cost:.4f}")
        logger.debug(f"[CLONE] Cost by provider: " + ", ".join(f"{p}=${c:.4f}" for p, c in costs_by_provider.items() if c > 0))
        logger.debug(f"[CLONE] Snippets: {len(all_snippets)}, Citations: {len(synthesis_result.get('citations', []))}")

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

        # Add memory stats if memory was used
        if recall_result:
            recall_meta = recall_result['recall_metadata']
            # Count memory sources in final citations
            memory_sources_used = sum(1 for c in final_citations if c.get('_from_memory', False))

            metadata['memory_stats'] = {
                'memory_enabled': True,
                'sources_recalled': original_memory_count,  # Before deduplication
                'sources_from_memory_after_dedup': len([s for s in memory_sources if s.get('_from_memory')]) if memory_sources else 0,
                'sources_from_search': original_search_count,
                'memory_confidence': recall_result['confidence'],
                'search_decision': search_decision['action'],
                'search_decision_reasoning': search_decision['reasoning'],
                'recall_cost': recall_meta['recall_cost'],
                'memory_sources_cited': memory_sources_used
            }
        else:
            metadata['memory_stats'] = {'memory_enabled': False}

        if clone_logger:
            clone_logger.finalize(metadata, final_answer_data, final_citations)

        # Log citation URLs for memory debugging (MEMORY_URL_STORAGE_ISSUE)
        if final_citations:
            citation_urls = [c.get('url', 'no-url') for c in final_citations]
            # Check both _from_memory and _from_citation_recall (cached citations)
            from_memory = [c.get('url', 'no-url') for c in final_citations if c.get('_from_memory') or c.get('_from_citation_recall')]
            from_search = [c.get('url', 'no-url') for c in final_citations if not c.get('_from_memory') and not c.get('_from_citation_recall') and not c.get('_from_live_fetch')]
            from_jina = [c.get('url', 'no-url') for c in final_citations if c.get('_from_live_fetch')]
            logger.info(f"[CLONE_MEMORY_DEBUG] Citations: {len(final_citations)} total, {len(from_memory)} from memory/cache, {len(from_search)} from search, {len(from_jina)} from Jina")
            if from_jina:
                logger.info(f"[CLONE_MEMORY_DEBUG] Jina-fetched URLs: {from_jina[:5]}{'...' if len(from_jina) > 5 else ''}")

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

    def _decide_search_strategy(
        self,
        recall_result: Dict[str, Any],
        query: str,
        search_terms: List[str],
        force_min_searches: int = 0
    ) -> Dict[str, Any]:
        """
        Decide which search terms need fresh searches based on memory recall.

        Memory recall returns per-search-term confidence:
        - recommended_searches: Terms needing fresh search (refined if verification ran, else original)
        - search_term_confidence: Per-term confidence dict for logging

        Decision logic:
        - If recommended_searches has all terms -> 'full_search'
        - If recommended_searches has some terms -> 'supplement' (search only those)
        - If recommended_searches is empty -> 'skip' (use memory sources only)

        Args:
            recall_result: Result from memory.recall()
            query: Current user query
            search_terms: Original search terms from initial decision
            force_min_searches: Deprecated, kept for compatibility

        Returns:
            {'action': 'skip' | 'supplement' | 'full_search', 'search_terms': [...], 'reasoning': str}
        """
        overall_confidence = recall_result['confidence']
        num_memories = len(recall_result['memories'])
        # recommended_searches now contains the terms to search (refined or original for low-conf)
        terms_to_search = recall_result.get('recommended_searches', [])
        search_term_confidence = recall_result.get('search_term_confidence', {})

        # CRITICAL: If no memories returned, always do full search regardless of confidence
        if num_memories == 0:
            return {
                'action': 'full_search',
                'search_terms': search_terms,
                'reasoning': f"No memory sources available (0 memories despite confidence {overall_confidence:.2f})"
            }

        # If verification provided specific terms to search, use them
        if terms_to_search:
            if len(terms_to_search) == len(search_terms):
                return {
                    'action': 'full_search',
                    'search_terms': terms_to_search,
                    'reasoning': f"All {len(search_terms)} terms have low memory confidence"
                }
            else:
                return {
                    'action': 'supplement',
                    'search_terms': terms_to_search,
                    'reasoning': f"{len(terms_to_search)}/{len(search_terms)} terms need fresh search"
                }

        # No terms to search - all have high confidence
        if search_term_confidence:
            return {
                'action': 'skip',
                'search_terms': [],
                'reasoning': f"All {len(search_terms)} terms have high memory confidence"
            }

        # Fallback: No per-term data, use overall confidence
        if overall_confidence >= 0.85:
            return {
                'action': 'skip',
                'search_terms': [],
                'reasoning': f"High overall confidence ({overall_confidence:.2f})"
            }
        elif overall_confidence >= 0.6:
            return {
                'action': 'supplement',
                'search_terms': search_terms[:2],
                'reasoning': f"Medium confidence ({overall_confidence:.2f}), no per-term data"
            }
        else:
            return {
                'action': 'full_search',
                'search_terms': search_terms,
                'reasoning': f"Low overall confidence ({overall_confidence:.2f})"
            }

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
                    source['_search_ref'] = search_idx + 1
                    source['_rank_position'] = rank_position
                    pool.append(source)

        return pool

    def _store_snippets_as_citations(
        self,
        snippets: List[Dict[str, Any]],
        session_id: str,
        all_keywords: List[str],
        source_type: str = "search"
    ):
        """
        Store extracted snippets as citations for future recall.

        This enables citation-aware memory: on future queries with matching
        required keywords, we can return pre-extracted citations instead of
        re-extracting from raw source content.

        Args:
            snippets: List of extracted snippets with _source_url, text, p, etc.
            session_id: Session identifier for MemoryCache
            all_keywords: All keywords to check for hits (required + positive combined)
            source_type: Origin type (memory_extraction, search_extraction, etc.)
        """
        from the_clone.search_memory_cache import MemoryCache
        from the_clone.search_memory import SearchMemory

        # Group snippets by source URL
        snippets_by_url = {}
        for snippet in snippets:
            url = snippet.get('_source_url')
            if not url:
                continue
            if url not in snippets_by_url:
                snippets_by_url[url] = {
                    'snippets': [],
                    'title': snippet.get('_source_title', 'Unknown'),
                    'search_term': snippet.get('_search_term', ''),
                    'content': ''  # We don't store full content here (it's in existing memory)
                }
            snippets_by_url[url]['snippets'].append(snippet)

        # Store citations for each source
        stored_count = 0
        for url, source_data in snippets_by_url.items():
            citations = []
            for snippet in source_data['snippets']:
                # Convert snippet to citation format
                # Store ALL keywords that hit (required + positive) for rich metadata
                citation = {
                    'quote': snippet.get('text', ''),
                    'p_score': snippet.get('p', 0.5),
                    'context': snippet.get('verbal_handle', ''),
                    'hit_keywords': SearchMemory.compute_hit_keywords(
                        {'quote': snippet.get('text', ''), 'context': snippet.get('verbal_handle', '')},
                        all_keywords
                    ),
                    'extracted_at': datetime.now().isoformat(),
                    'snippet_id': snippet.get('id', ''),
                    'validation_reason': snippet.get('validation_reason', '')
                }
                citations.append(citation)

            if citations:
                try:
                    MemoryCache.store_citations(
                        session_id=session_id,
                        url=url,
                        content='',  # Content already in existing memory
                        title=source_data['title'],
                        search_term=source_data['search_term'],
                        citations=citations,
                        source_type=source_type
                    )
                    stored_count += len(citations)
                except Exception as e:
                    logger.warning(f"[CLONE] Failed to store citations for {url[:50]}: {e}")

        if stored_count > 0:
            logger.info(f"[CLONE_MEMORY_DEBUG] Stored {stored_count} citations from {len(snippets_by_url)} sources to sources dict (type: {source_type})")