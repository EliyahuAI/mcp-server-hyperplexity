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
from the_clone.snippet_schemas import (
    get_snippet_extraction_schema,
    get_snippet_extraction_code_schema,
    get_snippet_extraction_batch_code_schema,
    convert_p_string_to_number
)
from the_clone.text_labeler import TextLabeler
from the_clone.code_resolver import CodeResolver
from the_clone.code_extraction_debug import CodeExtractionDebugger
from the_clone.strategy_loader import get_model_with_backups
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SnippetExtractorStreamlined:
    """
    Streamlined extractor - returns only essential quotes.
    No topics, no relevance, no metadata - just quotes.
    """

    def __init__(self, ai_client: AIAPIClient = None, enable_debug: bool = True):
        """Initialize the streamlined extractor.

        Args:
            ai_client: AIAPIClient instance
            enable_debug: Enable debug logging for code extraction (default True)
        """
        self.ai_client = ai_client or AIAPIClient()
        self.text_labeler = TextLabeler()
        self.debugger = CodeExtractionDebugger() if enable_debug else None

    def _generate_verbal_handle(self, search_term: str, snippet_index: int, snippet_id: str = None, existing_snippets: list = None) -> str:
        """
        Generate unique semantic handle for a snippet.
        If handle already used, append _2, _3, etc.

        Args:
            search_term: The search term this snippet relates to
            snippet_index: Index of this snippet
            snippet_id: Full snippet ID (optional)
            existing_snippets: List of existing snippets to check for handle collisions

        Returns:
            Unique handle (e.g., "intermittent_fasting_weight", "intermittent_fasting_weight_2")
        """
        # Clean and create slug from search term
        handle = search_term.lower()
        # Remove common words
        for word in ['what', 'is', 'the', 'how', 'does', 'compare', 'to', 'in', 'for', 'a', 'an', 'of', 'and', 'or']:
            handle = handle.replace(f' {word} ', ' ')
        # Take first 2-3 meaningful words, create slug
        words = [w for w in handle.split() if len(w) > 2][:3]
        base_handle = '_'.join(words) if words else 'snippet'
        base_handle = base_handle[:28]  # Leave room for _XX suffix

        # Check for collisions and increment if needed
        if existing_snippets:
            used_handles = {s.get('verbal_handle') for s in existing_snippets if s.get('verbal_handle')}
            final_handle = base_handle
            counter = 2
            while final_handle in used_handles:
                final_handle = f"{base_handle}_{counter}"
                counter += 1
            return final_handle

        return base_handle

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
        max_snippets_per_source: int = 5,
        use_code_extraction: bool = False,
        clone_logger: Any = None,
        log_prompt_collapsed: bool = False,
        provider: str = None
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
            use_code_extraction: If True, use code-based extraction (more token-efficient)

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
        # Get current date for staleness assessment
        from datetime import datetime
        current_date = datetime.now().strftime('%Y-%m-%d')

        logger.debug(f"[EXTRACTOR] Extracting from: {source_title[:60]}...")
        logger.debug(f"[EXTRACTOR] Source _search_term: '{source_search_term}'")

        # Code-based extraction: label the source text first
        labeled_text = None
        text_structure = None
        if use_code_extraction:
            labeled_text, text_structure = self.text_labeler.label_text(source_text)
            logger.debug(f"[EXTRACTOR] Labeled source text: {len(text_structure.get('sections', []))} sections")

        # Build extraction prompt with all search terms
        extraction_prompt = self._build_prompt(
            query=query,
            source_title=source_title,
            source_url=source_url,
            source_text=labeled_text if use_code_extraction else source_text,
            source_reliability=source_reliability,
            source_date=source_date,
            current_date=current_date,
            all_search_terms=all_search_terms,
            primary_search_index=primary_search_index,
            extraction_mode=extraction_mode,
            max_snippets=max_snippets_per_source,
            use_code_extraction=use_code_extraction
        )

        if clone_logger:
            clone_logger.log_section(f"Extraction Prompt ({snippet_id_prefix})", extraction_prompt, level=4, collapse=True)

        try:
            # Call extraction model with appropriate schema
            schema = get_snippet_extraction_code_schema() if use_code_extraction else get_snippet_extraction_schema()

            # Get model with backups to override ai_client defaults
            model_chain = get_model_with_backups(model, provider)

            response = await self.ai_client.call_structured_api(
                prompt=extraction_prompt,
                schema=schema,
                model=model_chain,
                use_cache=False,
                max_web_searches=0,
                context=f"extract_{snippet_id_prefix}",
                soft_schema=soft_schema
            )

            # Log model attempts if backups were used
            if clone_logger and response.get('attempted_models'):
                clone_logger.log_model_attempts(response['attempted_models'], f"Extraction {snippet_id_prefix}")

            # Extract quotes using centralized parsing
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            if clone_logger:
                 clone_logger.log_section(f"Extraction Result ({snippet_id_prefix})", data, level=4, collapse=True)

            quotes_by_search = data.get('quotes_by_search', {})

            # Initialize code resolver if using code extraction
            resolver = None
            if use_code_extraction and text_structure:
                resolver = CodeResolver(text_structure, labeled_text, source_text)

            # Assign snippet IDs to each quote, organized by search term
            # Quotes now come as objects with {text, p, reason} or {c, p, r} for code-based
            snippets = []
            total_quotes = 0

            for search_num_str, quotes in quotes_by_search.items():
                search_num = int(search_num_str)

                # Check if any quote uses §* (pass-all) - if so, skip snippet extraction
                has_pass_all = False
                if isinstance(quotes, list):
                    for q in quotes:
                        if isinstance(q, list) and len(q) > 0:
                            code = q[0]
                            if code == '§*' or code == '*':
                                has_pass_all = True
                                logger.debug(f"[EXTRACTOR] Found §* pass-all code, using entire source instead of snippets")
                                break

                # Merge consecutive table row codes into ranges (if using code extraction)
                if use_code_extraction and resolver and not has_pass_all and isinstance(quotes, list):
                    quotes = self._merge_consecutive_codes(quotes, resolver)

                # If pass-all detected, create single snippet with entire source
                if has_pass_all:
                    snippet_id = f"{snippet_id_prefix}.{total_quotes}-p0.95"
                    snippet_search_term = all_search_terms[search_num - 1] if search_num <= len(all_search_terms) else source_search_term
                    verbal_handle = self._generate_verbal_handle(snippet_search_term, total_quotes, snippet_id, snippets)

                    snippet = {
                        "id": snippet_id,
                        "verbal_handle": verbal_handle,
                        "text": source_text,  # Entire original source
                        "p": 0.95,
                        "validation_reason": "PASS_ALL",
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
                    continue  # Skip individual quote processing

                for i, quote_obj in enumerate(quotes):
                    # Handle multiple formats: string, array, object
                    if isinstance(quote_obj, str):
                        # Old format - assign default validation
                        quote_text = quote_obj
                        p_score = 0.50
                        reason = "OK"
                    elif isinstance(quote_obj, list):
                        # Array format: [code, p, reason_abbrev] or [code, p, reason_abbrev, verbal_handle]
                        if len(quote_obj) >= 3:
                            code = quote_obj[0]
                            p_score = quote_obj[1]
                            reason_abbrev = quote_obj[2]
                            # Verbal handle is optional (4th element)
                            extracted_handle = quote_obj[3] if len(quote_obj) >= 4 else None

                            # Expand abbreviated reason
                            reason_map = {
                                "P": "PRIMARY", "D": "DOCUMENTED", "A": "ATTRIBUTED",
                                "O": "OK",
                                "C": "CONTRADICTED", "U": "UNSOURCED", "N": "ANONYMOUS",
                                "PR": "PROMOTIONAL", "S": "STALE", "SL": "SLOP", "IR": "INDIRECT"
                            }
                            reason = reason_map.get(reason_abbrev, reason_abbrev)

                            # Resolve code to text if using code extraction
                            if use_code_extraction and resolver:
                                quote_text = resolver.resolve(code)
                                logger.debug(f"[EXTRACTOR] Resolved code '{code}' → {len(quote_text)} chars: {quote_text[:50]}...")
                                if not quote_text:
                                    logger.warning(f"[EXTRACTOR] Failed to resolve code '{code}', skipping")
                                    continue
                            else:
                                # Not using code extraction, treat as literal
                                quote_text = code
                        else:
                            logger.warning(f"[EXTRACTOR] Invalid array format (len={len(quote_obj)}), skipping")
                            continue
                    elif use_code_extraction and 'c' in quote_obj:
                        # Code-based object format with {c, p, r}
                        code = quote_obj.get('c', '')
                        p_score = quote_obj.get('p', 0.50)
                        reason = quote_obj.get('r', 'OK')

                        # Resolve code to text
                        if resolver:
                            quote_text = resolver.resolve(code)
                            logger.debug(f"[EXTRACTOR] Resolved code '{code}' → {len(quote_text)} chars: {quote_text[:50]}...")
                            if not quote_text:
                                logger.warning(f"[EXTRACTOR] Failed to resolve code '{code}', skipping")
                                continue
                        else:
                            logger.warning(f"[EXTRACTOR] No resolver available for code '{code}', skipping")
                            continue
                    else:
                        # Text-based object format with {text, p, reason}
                        quote_text = quote_obj.get('text', '')
                        p_score = quote_obj.get('p', 0.50)
                        reason = quote_obj.get('reason', 'OK')

                    # Filter by quality threshold
                    if p_score < min_quality_threshold:
                        logger.debug(f"[EXTRACTOR] Filtered quote (p={p_score:.2f} < {min_quality_threshold}): {quote_text[:50]}...")
                        continue

                    # Use p-score in snippet ID instead of source reliability
                    snippet_id = f"{snippet_id_prefix}.{total_quotes}-p{p_score:.2f}"

                    # Get search term for this snippet
                    snippet_search_term = all_search_terms[search_num - 1] if search_num <= len(all_search_terms) else source_search_term

                    # Use extracted verbal handle if provided, otherwise generate (check existing for uniqueness)
                    if 'extracted_handle' in locals() and extracted_handle:
                        verbal_handle = extracted_handle
                    else:
                        verbal_handle = self._generate_verbal_handle(snippet_search_term, total_quotes, snippet_id, snippets)

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
                        "verbal_handle": verbal_handle,
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

            logger.debug(f"[EXTRACTOR] {snippet_id_prefix}: {len(snippets)} quotes across {len(quotes_by_search)} search terms (threshold: {min_quality_threshold})")

            # Log resolved snippets if using code extraction
            if clone_logger and use_code_extraction and snippets:
                resolved_snippet_texts = [{'id': s['id'], 'text': s['text']} for s in snippets]
                clone_logger.log_section(
                    f"Resolved Snippets ({snippet_id_prefix})",
                    resolved_snippet_texts,
                    level=4,
                    collapse=True
                )

            # Calculate validation stats
            if snippets:
                avg_p = sum(s["p"] for s in snippets) / len(snippets)
                high_q = sum(1 for s in snippets if s["p"] >= 0.85)
                low_q = sum(1 for s in snippets if s["p"] <= 0.15)

                # Calculate mode p-score (most common)
                from collections import Counter
                p_scores = [s["p"] for s in snippets]
                mode_p = Counter(p_scores).most_common(1)[0][0] if p_scores else 0.5

                logger.debug(f"[EXTRACTOR] Quality: avg_p={avg_p:.2f}, mode_p={mode_p:.2f}, high={high_q}, low={low_q}")

                # Add source quality (mode p-score) to all snippets
                for snippet in snippets:
                    snippet["_source_quality"] = mode_p

                # Optimization: If >50% of source words extracted, use entire source instead
                # OR if extraction_mode='structured', force full extraction for any results
                if use_code_extraction and text_structure:
                    # Calculate word coverage, not sentence coverage
                    total_words = len(source_text.split())
                    extracted_words = sum(len(s['text'].split()) for s in snippets)
                    coverage = extracted_words / total_words if total_words > 0 else 0

                    # Force full extraction for structured/table extraction mode
                    force_full_extraction = (extraction_mode == "structured" and len(snippets) > 0)

                    if coverage > 0.5 or force_full_extraction:
                        # Calculate median p-score and most common reason
                        p_scores = sorted([s["p"] for s in snippets])
                        median_p = p_scores[len(p_scores) // 2]

                        # Get most common reason
                        from collections import Counter
                        reason_counts = Counter(s["validation_reason"] for s in snippets)
                        most_common_reason = reason_counts.most_common(1)[0][0]

                        if force_full_extraction:
                            logger.debug(f"[EXTRACTOR] EXTRACTION MODE - forcing full source content (p={median_p}, {len(snippets)} snippets found)")
                        else:
                            logger.debug(f"[EXTRACTOR] Coverage {coverage:.1%} >50% - using entire source (median_p={median_p}, reason={most_common_reason})")

                        # Replace all individual snippets with single consolidated snippet
                        snippet_id = f"{snippet_id_prefix}.0-p{median_p:.2f}"

                        # Generate unique verbal handle for consolidated snippet
                        consolidated_search_term = all_search_terms[0] if all_search_terms else source_search_term
                        consolidated_handle = self._generate_verbal_handle(consolidated_search_term, 0, snippet_id, [])
                        snippets = [{
                            "id": snippet_id,
                            "verbal_handle": consolidated_handle,
                            "text": source_text,
                            "p": median_p,
                            "validation_reason": most_common_reason,
                            "search_ref": 1,
                            "_source_title": source_title,
                            "_source_url": source_url,
                            "_source_date": source_date,
                            "_source_reliability": source_reliability,
                            "_search_term": source_search_term,
                            "_primary_search": primary_search_index,
                            "_is_off_topic": False,
                            "_optimized_from_coverage": coverage
                        }]

            # Debug logging for code extraction
            if use_code_extraction and self.debugger and text_structure:
                issues = self.debugger.detect_issues(
                    labeled_text=labeled_text,
                    structure=text_structure,
                    ai_response=data,
                    resolved_snippets=snippets
                )

                self.debugger.log_extraction(
                    source_id=snippet_id_prefix,
                    original_text=source_text,
                    labeled_text=labeled_text,
                    structure=text_structure,
                    ai_response=data,
                    resolved_snippets=snippets,
                    issues=issues,
                    query=query
                )

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

    async def extract_from_sources_batch(
        self,
        sources: List[Dict[str, Any]],
        query: str,
        snippet_id_prefix: str,
        all_search_terms: List[str],
        model: str = "gemini-2.0-flash",
        soft_schema: bool = False,
        min_quality_threshold: float = 0.0,
        extraction_mode: str = "simple_facts",
        max_snippets_per_source: int = 3,
        clone_logger: Any = None,
        provider: str = None,
        start_source_index: int = 1,
        accept_all_quality_levels: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Extract quotes from multiple sources in a single API call (batch mode).
        Used for shallow strategies to reduce overhead.

        Args:
            sources: List of search result dicts
            query: User's query
            snippet_id_prefix: Prefix for snippet IDs
            all_search_terms: List of ALL search terms
            model: Model to use for extraction
            soft_schema: Whether to use soft schema mode
            min_quality_threshold: Minimum p score to keep snippets
            extraction_mode: "simple_facts" or "nuanced"
            max_snippets_per_source: Max snippets per source
            clone_logger: Optional logger
            provider: Provider name
            start_source_index: Starting index for source numbering (default 1)

        Returns:
            List of extraction results, one per source
        """
        from datetime import datetime
        current_date = datetime.now().strftime('%Y-%m-%d')

        logger.debug(f"[BATCH EXTRACTOR] Processing {len(sources)} sources in single call (starting index {start_source_index})")

        # Label all sources with source-prefixed codes
        labeled_sources = []
        for i, source in enumerate(sources, start=start_source_index):
            source_text = source.get('snippet', '')
            source_url = source.get('url', 'Unknown URL')
            source_title = source.get('title', 'Unknown')
            source_date = source.get('date') or source.get('last_updated', '')
            source_reliability = source.get('reliability', 'MEDIUM')
            search_ref = source.get('_search_ref', 1)
            search_term = source.get('_search_term', '')

            # Label the text
            labeled_text, text_structure = self.text_labeler.label_text(source_text)

            # Add source prefix to all codes for display (e.g., §1.1 -> §S1:1.1)
            source_id = f"S{i}"
            labeled_text_with_prefix = re.sub(r'§(\d+\.\d+)', f'§{source_id}:\\1', labeled_text)

            # Create resolver with ORIGINAL labeled_text (without source prefix)
            # Model will return codes WITH prefix (S1:1.1), we'll strip before resolving
            labeled_sources.append({
                'source_id': source_id,
                'source_num': i,
                'url': source_url,
                'title': source_title,
                'date': source_date,
                'reliability': source_reliability,
                'search_ref': search_ref,
                'search_term': search_term,
                'original_text': source_text,
                'labeled_text': labeled_text,  # Original for resolver
                'labeled_text_display': labeled_text_with_prefix,  # Prefixed for prompt display
                'structure': text_structure,
                'resolver': CodeResolver(text_structure, labeled_text, source_text)
            })

        # Build batch extraction prompt
        batch_prompt = self._build_batch_prompt(
            query=query,
            labeled_sources=labeled_sources,
            all_search_terms=all_search_terms,
            extraction_mode=extraction_mode,
            max_snippets=max_snippets_per_source,
            current_date=current_date
        )

        if clone_logger:
            clone_logger.log_section(f"Batch Extraction Prompt ({len(sources)} sources)", batch_prompt, level=4, collapse=True)

        try:
            # Call extraction model with batch schema
            schema = get_snippet_extraction_batch_code_schema()
            model_chain = get_model_with_backups(model, provider)

            response = await self.ai_client.call_structured_api(
                prompt=batch_prompt,
                schema=schema,
                model=model_chain,
                use_cache=False,
                max_web_searches=0,
                context=f"batch_extract_{snippet_id_prefix}",
                soft_schema=soft_schema
            )

            # Log model attempts if backups were used
            if clone_logger and response.get('attempted_models'):
                clone_logger.log_model_attempts(response['attempted_models'], f"Batch Extraction {snippet_id_prefix}")

            # Extract quotes
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            if clone_logger:
                clone_logger.log_section(f"Batch Extraction Result ({len(sources)} sources)", data, level=4, collapse=True)

            quotes_by_source = data.get('quotes_by_source', {})

            # 1. Calculate dynamic threshold based on available quality (Top 2 Levels)
            all_p_scores = set()
            for src_id, src_data in quotes_by_source.items():
                if src_data.get('quotes_by_search'):
                    # Convert p from string format (p05, p15, etc.) to number (0.05, 0.15, etc.)
                    p_value = convert_p_string_to_number(src_data.get('p', 0.50))
                    all_p_scores.add(p_value)

            sorted_p = sorted(list(all_p_scores), reverse=True)

            # For findall mode (accept_all_quality_levels=True), allow ALL levels
            if accept_all_quality_levels:
                allowed_levels = sorted_p  # All levels allowed
                dynamic_threshold = 0.0
                effective_threshold = 0.0
                logger.debug(f"[BATCH EXTRACTOR] FINDALL mode: Accepting ALL quality levels (Available levels: {sorted_p}, Warning threshold: {min_quality_threshold})")
            else:
                # Use top 2 levels if available, otherwise just the top 1
                allowed_levels = sorted_p[:2]
                dynamic_threshold = allowed_levels[-1] if allowed_levels else 0.0

                # Effective threshold is dynamic but never below 0.15 (absolute junk)
                effective_threshold = max(dynamic_threshold, 0.15)

                logger.debug(f"[BATCH EXTRACTOR] Dynamic threshold: p >= {effective_threshold} (Available levels: {sorted_p}, Strategy min: {min_quality_threshold})")

            # Process each source's quotes
            results = []
            for labeled_src in labeled_sources:
                source_id = labeled_src['source_id']
                source_num = labeled_src['source_num']
                resolver = labeled_src['resolver']

                # Get source data (new format with source-level assessment)
                source_data = quotes_by_source.get(source_id, {})

                # Extract source-level metadata
                source_handle = source_data.get('source_handle', f'source{source_num}')
                source_c = source_data.get('c', 'M/O')  # Classification (e.g., H/P, M/A/O)
                # Convert p from string format (p05, p15, etc.) to number (0.05, 0.15, etc.)
                source_p = convert_p_string_to_number(source_data.get('p', 0.50))
                source_quotes_by_search = source_data.get('quotes_by_search', {})

                snippets = []
                snippet_counter = 0
                dropped_count = 0
                
                # Check if this source is considered "lower quality" relative to original strict requirements
                is_lower_quality = source_p < min_quality_threshold

                # Process quotes organized by search term
                for search_num_str, quotes in source_quotes_by_search.items():
                    search_num = int(search_num_str)

                    # Check for pass-all flag (NEW FORMAT: [detail_limitation, code])
                    has_pass_all = False
                    if isinstance(quotes, list):
                        for q in quotes:
                            if isinstance(q, list) and len(q) >= 2:
                                code = q[1]  # Code is now position [1], handle is [0]
                                if code == f'§{source_id}:*' or code == '§*':
                                    has_pass_all = True
                                    logger.debug(f"[BATCH EXTRACTOR] Found pass-all code for {source_id}, using entire source")
                                    break

                    # If pass-all, create single snippet with entire source
                    if has_pass_all:
                        # Only check effective threshold for pass-all
                        if source_p < effective_threshold:
                            dropped_count += 1
                            continue

                        snippet_id = f"{snippet_id_prefix}.{labeled_src['search_ref']}.{source_num}.{snippet_counter}-p{source_p:.2f}"
                        # Full verbal handle = source_handle + detail_limitation
                        verbal_handle = f"{source_handle}_entire-source_pass-all"

                        snippet = {
                            "id": snippet_id,
                            "verbal_handle": verbal_handle,
                            "text": labeled_src['original_text'],
                            "p": source_p,
                            "c": source_c,
                            "validation_reason": "PASS_ALL",
                            "search_ref": search_num,
                            "_source_title": labeled_src['title'],
                            "_source_url": labeled_src['url'],
                            "_source_date": labeled_src['date'],
                            "_source_reliability": labeled_src['reliability'],
                            "_search_term": labeled_src['search_term'],
                            "_source_handle": source_handle,
                            "_is_lower_quality": is_lower_quality
                        }
                        snippets.append(snippet)
                        snippet_counter += 1
                        continue

                    # Process individual quotes (NEW FORMAT: [detail_limitation, code])
                    for quote_array in quotes:
                        if not isinstance(quote_array, list) or len(quote_array) < 2:
                            continue

                        detail_limitation = quote_array[0]  # Handle components (detail_limitation)
                        code = quote_array[1]  # Location code

                        # Strip source prefix from code before resolving (e.g., §S1:1.1 -> §1.1)
                        code_without_prefix = code
                        if ':' in code:
                            # Extract the part after the colon
                            code_without_prefix = '§' + code.split(':', 1)[1].lstrip('§')

                        # Resolve code to text
                        quote_text = resolver.resolve(code_without_prefix)
                        if not quote_text:
                            logger.warning(f"[BATCH EXTRACTOR] Failed to resolve code '{code}' (stripped: '{code_without_prefix}') from {source_id}, skipping")
                            continue

                        # Filter by dynamic effective threshold
                        if source_p < effective_threshold:
                            dropped_count += 1
                            continue

                        # Create snippet with source-level p in ID
                        snippet_id = f"{snippet_id_prefix}.{labeled_src['search_ref']}.{source_num}.{snippet_counter}-p{source_p:.2f}"

                        # Assemble full verbal handle: source_handle + detail_limitation
                        verbal_handle = f"{source_handle}_{detail_limitation}"

                        snippet = {
                            "id": snippet_id,
                            "verbal_handle": verbal_handle,
                            "text": quote_text,
                            "p": source_p,
                            "c": source_c,
                            "search_ref": search_num,
                            "_source_title": labeled_src['title'],
                            "_source_url": labeled_src['url'],
                            "_source_date": labeled_src['date'],
                            "_source_reliability": labeled_src['reliability'],
                            "_search_term": labeled_src['search_term'],
                            "_source_handle": source_handle,
                            "_detail_limitation": detail_limitation,
                            "_code": code,
                            "_is_lower_quality": is_lower_quality
                        }
                        snippets.append(snippet)
                        snippet_counter += 1

                # All snippets from this source have same source-level p (already set above)
                logger.debug(f"[BATCH EXTRACTOR] {source_id} ({source_handle}): {len(snippets)} quotes extracted (dropped {dropped_count} low quality), p={source_p}, c={source_c}")

                # Add result for this source
                results.append({
                    "snippets": snippets,
                    "source_info": {
                        "title": labeled_src['title'],
                        "url": labeled_src['url'],
                        "reliability": labeled_src['reliability']
                    },
                    "model_response": response  # Share same response for all sources
                })

            return results

        except Exception as e:
            logger.error(f"[BATCH EXTRACTOR] Batch extraction failed: {e}")
            # Return empty results for all sources
            return [{
                "snippets": [],
                "source_info": {
                    "title": src.get('title', 'Unknown'),
                    "url": src.get('url', 'Unknown'),
                    "reliability": src.get('reliability', 'MEDIUM')
                },
                "error": str(e)
            } for src in sources]

    def _build_batch_prompt(
        self,
        query: str,
        labeled_sources: List[Dict],
        all_search_terms: List[str],
        extraction_mode: str,
        max_snippets: int,
        current_date: str
    ) -> str:
        """Build batch extraction prompt with multiple labeled sources."""
        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__),
            'prompts',
            'snippet_extraction_batch.md'
        )

        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # Format all search terms
        formatted_terms = '\n'.join([f"{i}. {term}" for i, term in enumerate(all_search_terms, 1)])

        # Format labeled sources
        formatted_sources = self._format_labeled_sources_for_batch(labeled_sources)

        # Mode guidance
        mode_guidance = {
            "simple_facts": "Extract ONLY concrete atomic facts (numbers, dates, entities). Prefer brevity.",
            "nuanced": "Extract facts with context, explanations, and methodology when relevant."
        }.get(extraction_mode, "Extract essential quotes.")

        prompt = template.format(
            current_date=current_date,
            all_search_terms_formatted=formatted_terms,
            formatted_sources=formatted_sources,
            extraction_mode_guidance=mode_guidance,
            max_snippets=max_snippets
        )

        return prompt

    def _format_labeled_sources_for_batch(self, labeled_sources: List[Dict]) -> str:
        """Format multiple labeled sources for batch prompt."""
        if not labeled_sources:
            return "(No sources)"

        formatted = []
        for src in labeled_sources:
            source_id = src['source_id']

            # Source header
            source_line = f"\n### {source_id}: {src['title']}"
            if src['url']:
                source_line += f"\nURL: {src['url']}"
            if src['date']:
                source_line += f"\nDate: {src['date']}"

            formatted.append(source_line)
            formatted.append("\nLabeled text:\n")

            # Labeled text (use display version with source prefixes)
            formatted.append(src['labeled_text_display'])
            formatted.append("\n")

        return '\n'.join(formatted)

    def _merge_consecutive_codes(self, quotes: List, resolver: 'CodeResolver') -> List:
        """
        Merge consecutive table row codes into ranges to avoid duplicate header prepending.

        E.g., [["H8.3", 0.9, "P"], ["H8.4", 0.9, "P"], ["H8.5", 0.9, "P"]]
        becomes [["H8.3-H8.5", 0.9, "P"]]

        Only merges if:
        1. Codes are consecutive (H8.3, H8.4, H8.5)
        2. All are from the same table (same table_header_id)
        3. Have same p-score and reason
        """
        if not quotes or len(quotes) <= 1:
            return quotes

        import re
        merged = []
        i = 0

        while i < len(quotes):
            quote = quotes[i]

            # Only process array format codes
            if not isinstance(quote, list) or len(quote) < 3:
                merged.append(quote)
                i += 1
                continue

            code = quote[0]
            p_score = quote[1]
            reason = quote[2]

            # Check if this is a sentence code (H1.2 or 1.2 format)
            match = re.match(r'§?(H?\d+)\.(\d+)$', code)
            if not match:
                merged.append(quote)
                i += 1
                continue

            section = match.group(1)
            sent_num = int(match.group(2))

            # Check if this is a table row using the resolver
            section_id = f"H{section}" if not section.startswith('H') else section
            sent_id = f"{section_id}.{sent_num}"

            # Get sentence metadata from resolver
            section_data = resolver.sections.get(section_id)
            if not section_data:
                merged.append(quote)
                i += 1
                continue

            sent_data = section_data['sentences'].get(sent_id)
            if not sent_data or not sent_data.get('is_table_row'):
                # Not a table row, keep as-is
                merged.append(quote)
                i += 1
                continue

            # This is a table row - look ahead for consecutive rows from same table
            table_header_id = sent_data.get('table_header_id')
            consecutive_end = sent_num
            j = i + 1

            while j < len(quotes):
                next_quote = quotes[j]

                # Must be same format and same p/reason to merge
                if not isinstance(next_quote, list) or len(next_quote) < 3:
                    break

                next_code = next_quote[0]
                next_p = next_quote[1]
                next_reason = next_quote[2]

                # Must have same p-score and reason
                if next_p != p_score or next_reason != reason:
                    break

                # Must be consecutive sentence from same section
                next_match = re.match(r'§?(H?\d+)\.(\d+)$', next_code)
                if not next_match:
                    break

                next_section = next_match.group(1)
                next_sent_num = int(next_match.group(2))

                if next_section != section or next_sent_num != consecutive_end + 1:
                    break

                # Check if same table
                next_sent_id = f"{section_id}.{next_sent_num}"
                next_sent_data = section_data['sentences'].get(next_sent_id)

                if not next_sent_data or not next_sent_data.get('is_table_row'):
                    break

                if next_sent_data.get('table_header_id') != table_header_id:
                    break

                # This is consecutive, extend range
                consecutive_end = next_sent_num
                j += 1

            # If we found consecutive rows, create a range
            if consecutive_end > sent_num:
                # Create range code (strip § if present)
                code_clean = code[1:] if code.startswith('§') else code
                range_code = f"§{code_clean}-{consecutive_end}"
                logger.debug(f"[EXTRACTOR] Merged {consecutive_end - sent_num + 1} consecutive table rows into range {range_code}")
                merged.append([range_code, p_score, reason])
                i = j  # Skip all merged quotes
            else:
                # No consecutive rows, keep as-is
                merged.append(quote)
                i += 1

        return merged

    def _build_prompt(
        self,
        query: str,
        source_title: str,
        source_url: str,
        source_text: str,
        source_reliability: str,
        source_date: str,
        current_date: str,
        all_search_terms: List[str],
        primary_search_index: int,
        extraction_mode: str = "simple_facts",
        max_snippets: int = 5,
        use_code_extraction: bool = False
    ) -> str:
        """Build extraction prompt with all search terms."""
        template_file = 'snippet_extraction_code_compressed.md' if use_code_extraction else 'snippet_extraction_streamlined.md'
        template_path = os.path.join(
            os.path.dirname(__file__),
            'prompts',
            template_file
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

        # Get primary search term (primary_search_index is 1-indexed)
        primary_search_term = all_search_terms[primary_search_index - 1] if primary_search_index <= len(all_search_terms) else query

        prompt = template.format(
            primary_search_term=primary_search_term,
            source_title=source_title,
            source_url=source_url,
            source_date=source_date or "Unknown",
            current_date=current_date,
            primary_search_num=primary_search_index,
            all_search_terms_formatted=all_search_terms_formatted,
            source_full_text=source_text,
            extraction_mode_guidance=mode_guidance,
            max_snippets=max_snippets
        )

        return prompt
