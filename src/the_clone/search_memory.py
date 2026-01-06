#!/usr/bin/env python3
"""
Search Memory for Perplexity Search API.
Session-scoped memory with volatile RAM + S3 persistence.
"""

import asyncio
import json
import logging
import re
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from collections import defaultdict


# URL extraction pattern - matches http/https URLs
URL_PATTERN = re.compile(
    r'https?://[^\s<>"\')\]\}]+',
    re.IGNORECASE
)


def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract URLs from text.

    Args:
        text: Text that may contain URLs

    Returns:
        List of unique URLs found (preserves order)
    """
    if not text:
        return []

    matches = URL_PATTERN.findall(text)

    # Clean trailing punctuation that might have been captured
    cleaned = []
    for url in matches:
        # Remove trailing punctuation that's likely not part of URL
        url = url.rstrip('.,;:!?')
        if url and url not in cleaned:
            cleaned.append(url)

    return cleaned

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SearchMemory:
    """
    Session-scoped memory for Perplexity Search API.

    Architecture:
    - Volatile RAM storage during lambda execution (fast access)
    - S3 backup/restore for persistence
    - Optimistic concurrency for parallel lambda writes

    Deduplication Rules:
    - Only dedupe within same query (not across queries)
    - Keep both if different max_tokens (preserve richer data)
    """

    def __init__(
        self,
        session_id: str,
        email: str,
        s3_manager,
        ai_client=None
    ):
        """
        Initialize SearchMemory.

        Args:
            session_id: Session identifier
            email: User email
            s3_manager: UnifiedS3Manager instance
            ai_client: AIAPIClient instance (for recall)
        """
        self.session_id = session_id
        self.email = email
        self.s3_manager = s3_manager
        self.ai_client = ai_client

        # Session path
        self.session_path = s3_manager.get_session_path(email, session_id)
        self.memory_key = f"{self.session_path}agent_memory.json"

        # In-memory storage (lazy loaded)
        self._memory = None

        # Constants
        self.MAX_RETRIES = 3
        self.RETRY_BASE_DELAY = 2.0

    # === INITIALIZATION & PERSISTENCE ===

    @classmethod
    async def restore(
        cls,
        session_id: str,
        email: str,
        s3_manager,
        ai_client=None
    ) -> 'SearchMemory':
        """
        Restore memory from S3 into RAM.
        Creates empty memory if not exists.

        Args:
            session_id: Session identifier
            email: User email
            s3_manager: UnifiedS3Manager instance
            ai_client: AIAPIClient instance

        Returns:
            SearchMemory instance with loaded/initialized memory
        """
        instance = cls(session_id, email, s3_manager, ai_client)

        try:
            await instance._load_from_s3()
            logger.debug(f"[MEMORY] Restored {len(instance._memory['queries'])} queries from S3")
        except Exception as e:
            logger.debug(f"[MEMORY] No existing memory found, initializing empty: {e}")
            instance._initialize_empty_memory()

        return instance

    def _initialize_empty_memory(self):
        """Initialize empty in-memory structure."""
        self._memory = {
            "session_id": self.session_id,
            "email": self.email,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "queries": {},  # {query_id: query_data}
            "indexes": {
                "by_time": [],  # [query_id, ...] newest first
                "by_url": defaultdict(list)  # {url: [query_id, ...]}
            }
        }

    async def _load_from_s3(self):
        """Load memory from S3."""
        try:
            response = await asyncio.to_thread(
                self.s3_manager.s3_client.get_object,
                Bucket=self.s3_manager.bucket_name,
                Key=self.memory_key
            )

            memory_json = response['Body'].read().decode('utf-8')
            self._memory = json.loads(memory_json)

            # Convert by_url dict back from JSON (was converted to list for serialization)
            if isinstance(self._memory['indexes'].get('by_url'), dict):
                self._memory['indexes']['by_url'] = defaultdict(
                    list,
                    self._memory['indexes']['by_url']
                )

        except self.s3_manager.s3_client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"Memory file not found: {self.memory_key}")

    async def backup(self):
        """
        Save current memory state to S3 with optimistic concurrency.
        Retries on conflict with exponential backoff.
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                # Update timestamp
                self._memory['last_updated'] = datetime.now(timezone.utc).isoformat()

                # Prepare for JSON serialization (convert defaultdict to dict)
                memory_to_save = self._memory.copy()
                memory_to_save['indexes'] = {
                    'by_time': self._memory['indexes']['by_time'],
                    'by_url': dict(self._memory['indexes']['by_url'])
                }

                # Save to S3
                await asyncio.to_thread(
                    self.s3_manager.s3_client.put_object,
                    Bucket=self.s3_manager.bucket_name,
                    Key=self.memory_key,
                    Body=json.dumps(memory_to_save, indent=2),
                    ContentType='application/json'
                )

                logger.debug(f"[MEMORY] Backed up to S3 (attempt {attempt + 1})")
                return

            except Exception as e:
                if attempt == self.MAX_RETRIES - 1:
                    logger.error(f"[MEMORY] Failed to backup after {self.MAX_RETRIES} attempts: {e}")
                    raise

                # Exponential backoff
                wait_time = self.RETRY_BASE_DELAY ** attempt
                logger.warning(f"[MEMORY] Backup failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)

    # === STORAGE ===

    async def store_search(
        self,
        search_term: str,
        results: Dict[str, Any],
        parameters: Dict[str, Any],
        strategy: str = "unknown"
    ) -> str:
        """
        Store search results in memory and backup to S3.

        Deduplication rules:
        - Only dedupe within same search_term (not across terms)
        - Keep both if different max_tokens (preserve richer data)

        Args:
            search_term: Specific search term used
            results: Perplexity API response {"results": [...]}
            parameters: Search parameters (max_results, max_tokens_per_page, etc.)
            strategy: Strategy name used

        Returns:
            query_id: Unique identifier for stored query
        """
        # Ensure memory is loaded
        if self._memory is None:
            self._initialize_empty_memory()

        # Generate query ID
        query_id = self._generate_query_id(search_term)

        # Check if this exact query+search_term already exists
        existing_query = self._memory['queries'].get(query_id)

        if existing_query:
            # Same query exists - check max_tokens
            existing_max_tokens = existing_query['parameters'].get('max_tokens_per_page', 0)
            new_max_tokens = parameters.get('max_tokens_per_page', 0)

            if new_max_tokens <= existing_max_tokens:
                # Don't overwrite richer data with poorer data
                logger.info(
                    f"[MEMORY] Skipping storage - existing result has higher max_tokens "
                    f"({existing_max_tokens} vs {new_max_tokens})"
                )
                return query_id
            else:
                logger.info(
                    f"[MEMORY] Updating with richer data "
                    f"(max_tokens: {existing_max_tokens} → {new_max_tokens})"
                )

        # Store query data
        query_data = {
            "query_text": search_term,
            "search_term": search_term,
            "query_time": datetime.now(timezone.utc).isoformat(),
            "parameters": parameters,
            "results": results.get('results', []),
            "metadata": {
                "cost": 0.005,  # Perplexity Search API flat rate
                "num_results": len(results.get('results', [])),
                "strategy": strategy
            }
        }

        # Add to queries
        self._memory['queries'][query_id] = query_data

        # Update time index (add to front if new, move to front if updating)
        if query_id in self._memory['indexes']['by_time']:
            self._memory['indexes']['by_time'].remove(query_id)
        self._memory['indexes']['by_time'].insert(0, query_id)

        # Update URL index (for deduplication tracking)
        for result in results.get('results', []):
            url = result.get('url')
            if url and query_id not in self._memory['indexes']['by_url'][url]:
                self._memory['indexes']['by_url'][url].append(query_id)

        # Backup to S3
        try:
            await self.backup()
        except Exception as e:
            logger.error(f"[MEMORY] Failed to backup, continuing anyway: {e}")

        logger.info(
            f"[MEMORY] Stored query '{search_term}' with {len(results.get('results', []))} results"
        )

        return query_id

    def _generate_query_id(self, search_term: str) -> str:
        """
        Generate stable query ID based on search_term.
        Same term = same ID (enables deduplication).
        """
        # Create hash of search_term
        content = search_term.lower().strip()
        hash_hex = hashlib.md5(content.encode()).hexdigest()[:12]
        return f"query_{hash_hex}"

    # === RECALL ===

    async def recall(
        self,
        query: str,
        keywords: Optional[Dict[str, List[str]]] = None,
        max_results: int = 10,
        confidence_threshold: float = 0.6,
        breadth: str = "narrow",
        depth: str = "shallow",
        url_sources: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Recall relevant memories using iterative Gemini approach.

        Strategy:
        1. Keyword pre-filter on queries (fast, free)
        2. Gemini selects relevant sources from filtered queries
           - URL sources (from query) shown at TOP with note
        3. Verification with full snippets (URL sources always included)

        Args:
            query: Current user query
            keywords: {'positive': [...], 'negative': [...]}
            max_results: Max sources to return
            confidence_threshold: Minimum confidence to trust recall
            url_sources: Sources from URLs mentioned in query (always included)

        Returns:
            {
                'memories': List[dict],  # Search API format with _from_memory metadata
                'confidence': float,
                'should_search': bool,
                'recall_metadata': {...}
            }
        """
        start_time = time.time()
        url_sources = url_sources or []

        # Ensure memory is loaded
        if self._memory is None:
            self._initialize_empty_memory()

        # If no queries in memory and no URL sources, return empty
        if not self._memory['queries'] and not url_sources:
            return self._empty_recall_result()

        # Extract keywords
        positive_keywords = keywords.get('positive', []) if keywords else []
        negative_keywords = keywords.get('negative', []) if keywords else []

        # Stage 1: Keyword pre-filter on queries
        filtered_queries = self._filter_queries_by_keywords(
            query=query,
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords
        )

        # Log URL sources if present
        if url_sources:
            logger.info(f"[MEMORY] {len(url_sources)} URL sources from query will be prioritized")

        if not filtered_queries and not url_sources:
            logger.debug("[MEMORY] No relevant queries found after keyword filter")
            return self._empty_recall_result()

        logger.info(
            f"[MEMORY] Keyword filter: {len(self._memory['queries'])} → "
            f"{len(filtered_queries)} candidate queries"
        )

        # Stage 2: Gemini selects sources from filtered queries
        # URL sources are shown at top with special note
        if self.ai_client is None:
            logger.warning("[MEMORY] No AI client provided, using keyword-only recall")
            selected_sources = self._keyword_only_recall(filtered_queries, max_results)
            llm_cost = 0.0
            confidence = self._calculate_confidence(selected_sources, query)
        else:
            selected_sources, selection_cost = await self._gemini_select_sources(
                query=query,
                filtered_queries=filtered_queries,
                max_select=max_results,
                url_sources=url_sources
            )

            # Get initial confidence from Gemini selection
            confidence = self._calculate_confidence(selected_sources, query)

            # Stage 3: Verify with full snippet text
            # Run if: high confidence OR url_sources present (always verify URL sources)
            recommended_searches = []
            should_verify = (confidence >= 0.75 and len(selected_sources) > 0) or len(url_sources) > 0

            if should_verify:
                logger.debug(f"[MEMORY] Running verification (confidence={confidence:.2f}, url_sources={len(url_sources)})...")
                verified_confidence, verification_cost, recommended_searches, ranked_source_indices = await self._verify_with_full_snippets(
                    query=query,
                    selected_sources=selected_sources,
                    breadth=breadth,
                    depth=depth,
                    url_sources=url_sources
                )

                # Reorder sources based on Gemini's ranking
                if ranked_source_indices:
                    selected_sources = [selected_sources[i] for i in ranked_source_indices if i < len(selected_sources)]
                llm_cost = selection_cost + verification_cost
                confidence = verified_confidence
                logger.debug(f"[MEMORY] Verification complete: confidence {confidence:.2f}, recommended_searches={recommended_searches} (cost: ${verification_cost:.4f})")
            else:
                llm_cost = selection_cost
                recommended_searches = []

        # Convert to search API format
        memory_results = self._convert_to_search_format(selected_sources)

        # Always include URL sources in final results (even if Gemini didn't select them)
        # They go to synthesis regardless
        if url_sources:
            existing_urls = {m['url'] for m in memory_results}
            for url_src in url_sources:
                if url_src.get('url') not in existing_urls:
                    memory_results.append(url_src)
                    existing_urls.add(url_src.get('url'))
            logger.info(f"[MEMORY] Ensured {len(url_sources)} URL sources included in results")

        recall_time = (time.time() - start_time) * 1000

        return {
            'memories': memory_results,
            'confidence': confidence,
            'should_search': confidence < confidence_threshold,
            'recommended_searches': recommended_searches,
            'recall_metadata': {
                'total_queries': len(self._memory['queries']),
                'filtered_queries': len(filtered_queries),
                'sources_selected': len(selected_sources),
                'url_sources_count': len(url_sources),
                'recall_cost': llm_cost,
                'recall_time_ms': recall_time,
                'verification_run': should_verify
            }
        }

    def _filter_queries_by_keywords(
        self,
        query: str,
        positive_keywords: List[str],
        negative_keywords: List[str],
        top_k: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Filter queries by keyword match and query similarity.
        Keywords are matched against FULL TEXT (snippets), not just queries.

        Returns:
            List of {query_id, query_data, relevance_score}
        """
        scored_queries = []
        query_tokens = set(query.lower().split())

        for query_id, query_data in self._memory['queries'].items():
            # Build searchable text from query AND all snippets
            past_query = query_data['query_text'].lower()
            search_term = query_data['search_term'].lower()

            # Include ALL snippet text for keyword matching
            all_snippets = " ".join(
                result.get('snippet', '') + " " + result.get('title', '')
                for result in query_data['results']
            ).lower()

            # Calculate query overlap (Jaccard similarity)
            past_tokens = set(past_query.split()) | set(search_term.split())
            intersection = len(query_tokens & past_tokens)
            union = len(query_tokens | past_tokens)
            query_overlap = intersection / union if union > 0 else 0

            # Keyword scoring in FULL TEXT (query + snippets)
            searchable_text = f"{past_query} {search_term} {all_snippets}"
            pos_matches = sum(1 for kw in positive_keywords if kw.lower() in searchable_text)
            neg_matches = sum(1 for kw in negative_keywords if kw.lower() in searchable_text)

            # Combined score (removed recency - doesn't always matter)
            relevance_score = (
                query_overlap * 10.0 +  # Query match most important
                pos_matches * 1.0 -     # Positive keyword matches
                neg_matches * 5.0       # Strong penalty for negative keywords
            )

            # Only keep positive scores
            if relevance_score > 0:
                scored_queries.append({
                    'query_id': query_id,
                    'query_data': query_data,
                    'relevance_score': relevance_score,
                    'query_overlap': query_overlap
                })

        # Sort by score and return top k
        scored_queries.sort(key=lambda x: x['relevance_score'], reverse=True)
        return scored_queries[:top_k]

    async def _gemini_select_sources(
        self,
        query: str,
        filtered_queries: List[Dict[str, Any]],
        max_select: int,
        url_sources: Optional[List[Dict[str, Any]]] = None
    ) -> tuple[List[Dict[str, Any]], float]:
        """
        Use Gemini (via ai_client) to select most relevant sources.
        Also assesses confidence that sources can provide complete, accurate answer.
        URL sources from query are shown at top with special note.

        Returns:
            (selected_sources, cost)
        """
        url_sources = url_sources or []

        # Build prompt with filtered queries and their sources
        prompt = self._build_recall_prompt(query, filtered_queries, max_select, url_sources)

        # Schema for structured output
        schema = {
            "type": "object",
            "properties": {
                "selected_sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "query_index": {"type": "integer"},
                            "source_index": {"type": "integer"}
                        },
                        "required": ["query_index", "source_index"]
                    },
                    "description": f"Up to {max_select} most relevant sources (query_index, source_index pairs)"
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Probability (0.0-1.0) that selected sources can provide a factually accurate, up-to-date, and complete answer to the query"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation of selection and confidence assessment"
                }
            },
            "required": ["selected_sources", "confidence"]
        }

        try:
            # Call Gemini via ai_client with structured outputs
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model="gemini-2.0-flash",
                use_cache=False,
                context="memory_recall",
                soft_schema=True
            )

            # Extract structured response
            from shared.ai_client.utils import extract_structured_response
            data = extract_structured_response(response.get('response', response))

            # Extract cost
            cost = self._extract_cost_from_response(response)

            # Extract Gemini's confidence assessment
            gemini_confidence = data.get('confidence', 0.5)

            # Map selected indices to actual sources
            selected_sources = []
            url_sources_selected = 0
            for selection in data.get('selected_sources', [])[:max_select]:
                query_idx = selection.get('query_index')
                source_idx = selection.get('source_index')

                # Handle URL sources (query_index=-1)
                if query_idx == -1 and url_sources:
                    if source_idx < len(url_sources):
                        source = url_sources[source_idx].copy()
                        source['_gemini_confidence'] = gemini_confidence
                        source['_gemini_selected'] = True
                        selected_sources.append(source)
                        url_sources_selected += 1
                elif query_idx >= 0 and query_idx < len(filtered_queries):
                    query_info = filtered_queries[query_idx]
                    query_data = query_info['query_data']

                    if source_idx < len(query_data['results']):
                        source = query_data['results'][source_idx].copy()
                        source['_query_id'] = query_info['query_id']
                        source['_query_text'] = query_data['query_text']
                        source['_query_time'] = query_data['query_time']
                        source['_relevance_score'] = query_info['relevance_score']
                        source['_gemini_confidence'] = gemini_confidence
                        selected_sources.append(source)

            logger.debug(f"[MEMORY] Gemini selected {len(selected_sources)} sources ({url_sources_selected} URL), confidence={gemini_confidence:.2f} (cost: ${cost:.4f})")

            return selected_sources, cost

        except Exception as e:
            logger.error(f"[MEMORY] Gemini selection failed, using keyword fallback: {e}")
            # Fallback to keyword-only
            selected = self._keyword_only_recall(filtered_queries, max_select)
            return selected, 0.0

    async def _verify_with_full_snippets(
        self,
        query: str,
        selected_sources: List[Dict[str, Any]],
        breadth: str = "narrow",
        depth: str = "shallow",
        url_sources: Optional[List[Dict[str, Any]]] = None
    ) -> tuple[float, float, List[str], List[int]]:
        """
        Verify that selected sources can actually answer the query.
        Provides full snippet text to Gemini for assessment.
        Considers breadth/depth requirements.
        Returns ranked source indices (replaces triage when using memory only).

        URL sources are always included (user explicitly mentioned them).

        Returns:
            (verified_confidence, cost, recommended_searches, ranked_source_indices)
        """
        from datetime import datetime

        url_sources = url_sources or []

        # Get today's date
        today = datetime.now().strftime("%Y-%m-%d")

        # Combine URL sources with selected sources for verification
        # URL sources go first, marked as user-referenced
        all_sources = []
        url_source_count = len(url_sources)

        # Add URL sources first (user explicitly mentioned these)
        for source in url_sources:
            source_copy = source.copy()
            source_copy['_user_referenced'] = True
            all_sources.append(source_copy)

        # Add selected sources (dedupe by URL)
        existing_urls = {s.get('url') for s in url_sources}
        for source in selected_sources:
            if source.get('url') not in existing_urls:
                all_sources.append(source)
                existing_urls.add(source.get('url'))

        # Build verification prompt with full snippets
        snippets_text = []
        for i, source in enumerate(all_sources, 1):
            # Mark user-referenced sources
            user_ref_note = " [USER REFERENCED THIS URL]" if source.get('_user_referenced') else ""
            snippets_text.append(f"**Source {i}:{user_ref_note}** {source.get('title', 'No title')}")
            snippets_text.append(f"URL: {source.get('url', 'No URL')}")
            snippets_text.append(f"Date: {source.get('date', 'No date')}")
            snippets_text.append(f"\nContent:\n{source.get('snippet', 'No content')[:2000]}...")
            snippets_text.append("\n" + "="*80 + "\n")

        # Define answer requirements based on breadth/depth
        requirements_map = {
            "narrow": "focused on a specific aspect or single question",
            "broad": "comprehensive, covering multiple aspects and perspectives"
        }
        depth_map = {
            "shallow": "factual, concise (lists, definitions, quick facts)",
            "deep": "detailed with context, explanations, methodology, trade-offs, and examples"
        }

        answer_requirements = f"{requirements_map.get(breadth, 'focused')} and {depth_map.get(depth, 'concise')}"

        # Note about user-referenced sources if any
        url_note = ""
        if url_source_count > 0:
            url_note = f"\n**Note:** Sources 1-{url_source_count} are URLs the user explicitly mentioned in their query. Give these priority consideration.\n"

        prompt = f"""# Memory Verification Task

**Today's Date:** {today}

**Query:** {query}

**Answer Requirements:**
- Breadth: {breadth.upper()} - {requirements_map.get(breadth, 'focused')}
- Depth: {depth.upper()} - {depth_map.get(depth, 'concise')}
{url_note}
**Available Sources ({len(all_sources)}):**

{chr(10).join(snippets_text)}

**Tasks:**
1. Assess the probability (0.0-1.0) that you can provide a **{answer_requirements}** answer using ONLY these sources
2. Rank the sources by usefulness (return indices from best to worst)
3. If sources are incomplete for the required breadth/depth, recommend 1-3 specific search terms to fill the gaps

**Assessment Guidelines:**
- **0.9-1.0**: Can definitely provide complete, accurate, up-to-date answer
- **0.7-0.9**: Can likely provide good answer, may have minor gaps
- **0.5-0.7**: Can provide partial answer, missing important information
- **0.3-0.5**: Sources tangentially related, significant gaps exist
- **0.0-0.3**: Insufficient to answer properly

**Consider:**
- Completeness: Do sources cover all aspects of the query?
- Accuracy: Are sources authoritative and reliable?
- Recency: If query requires current info, are sources up-to-date?
- Depth: Is there enough detail to provide a substantive answer?

**Source Selection & Ranking:**
- Select ONLY the sources that are useful for answering this query
- Rank selected sources by usefulness (best first)
- Return indices of USEFUL sources only (0-indexed), skip irrelevant sources
- Example: If only Sources 3, 1, 5 are useful (in that order) → [2, 0, 4]
- This selection replaces triage when using memory-only

**Recommended Searches:**
- If confidence < 0.85, identify specific gaps and recommend targeted search terms
- Example: Sources cover syntax but miss performance → ["Python 3.12 performance benchmarks"]
- Return empty array [] if sources are complete

Return JSON:
{{
  "confidence": 0.85,
  "can_answer": true,
  "ranked_source_indices": [2, 0, 1, 3],
  "recommended_searches": ["specific search term 1"],
  "reasoning": "Brief explanation of confidence, ranking, and any gaps"
}}
"""

        schema = {
            "type": "object",
            "properties": {
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Probability that sources provide complete, accurate answer for required breadth/depth"
                },
                "can_answer": {
                    "type": "boolean",
                    "description": "True if confident sources can answer the query"
                },
                "ranked_source_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": f"Indices of USEFUL sources only (0-{len(all_sources)-1}), ranked best first. Skip irrelevant sources. Replaces triage for memory-only queries.",
                    "minItems": 0
                },
                "recommended_searches": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1-3 specific search terms to fill identified gaps (empty if sources are complete)",
                    "maxItems": 3
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation of confidence level, source ranking, and any gaps"
                }
            },
            "required": ["confidence", "can_answer", "ranked_source_indices", "recommended_searches"]
        }

        try:
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model="gemini-2.0-flash",
                use_cache=False,
                context="memory_verification",
                soft_schema=True
            )

            from shared.ai_client.utils import extract_structured_response
            data = extract_structured_response(response.get('response', response))
            cost = self._extract_cost_from_response(response)

            verified_confidence = data.get('confidence', 0.5)
            recommended_searches = data.get('recommended_searches', [])
            ranked_source_indices = data.get('ranked_source_indices', list(range(len(all_sources))))

            logger.info(
                f"[MEMORY] Verification: confidence={verified_confidence:.2f}, "
                f"can_answer={data.get('can_answer', False)}, "
                f"ranked_sources={len(ranked_source_indices)}, "
                f"url_sources={url_source_count}, "
                f"recommended_searches={len(recommended_searches)}"
            )

            return verified_confidence, cost, recommended_searches, ranked_source_indices

        except Exception as e:
            logger.error(f"[MEMORY] Verification failed: {e}")
            # Return original confidence on error, no reordering
            return self._calculate_confidence(all_sources, query), 0.0, [], []

    def _keyword_only_recall(
        self,
        filtered_queries: List[Dict[str, Any]],
        max_select: int
    ) -> List[Dict[str, Any]]:
        """
        Fallback: Select top sources from filtered queries without LLM.
        """
        all_sources = []

        for query_info in filtered_queries:
            query_data = query_info['query_data']
            for idx, source in enumerate(query_data['results']):
                source_copy = source.copy()
                source_copy['_query_id'] = query_info['query_id']
                source_copy['_query_text'] = query_data['query_text']
                source_copy['_query_time'] = query_data['query_time']
                source_copy['_relevance_score'] = query_info['relevance_score']
                source_copy['_source_rank'] = idx
                all_sources.append(source_copy)

        # Sort by query relevance and source rank
        all_sources.sort(
            key=lambda x: (x['_relevance_score'], -x['_source_rank']),
            reverse=True
        )

        return all_sources[:max_select]

    def _build_recall_prompt(
        self,
        query: str,
        filtered_queries: List[Dict[str, Any]],
        max_select: int,
        url_sources: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Build prompt for Gemini source selection with confidence assessment."""
        from datetime import datetime

        url_sources = url_sources or []

        # Get today's date
        today = datetime.now().strftime("%Y-%m-%d")

        # Format URL sources at the TOP (user explicitly referenced these)
        url_section = ""
        if url_sources:
            url_lines = []
            url_lines.append("## USER-REFERENCED URLs (PRIORITY)")
            url_lines.append("**The user explicitly mentioned these URLs in their query.**")
            url_lines.append("**Use query_index=-1 to select these sources.**")
            url_lines.append("")
            for src_idx, source in enumerate(url_sources):
                title = source.get('title', 'No title')[:60]
                url = source.get('url', 'No URL')
                date = source.get('date', 'No date')
                snippet_preview = source.get('snippet', '')[:150]
                original_query = source.get('_original_query', 'Unknown')
                url_lines.append(f"  [{src_idx}] {title}")
                url_lines.append(f"      URL: {url}")
                url_lines.append(f"      Date: {date}")
                url_lines.append(f"      Originally found via: \"{original_query}\"")
                url_lines.append(f"      Preview: {snippet_preview}...")
                url_lines.append("")
            url_section = chr(10).join(url_lines) + chr(10)

        # Format queries with their sources
        formatted_queries = []
        for idx, query_info in enumerate(filtered_queries[:10]):  # Limit to top 10 queries
            query_data = query_info['query_data']
            score = query_info['relevance_score']

            formatted_queries.append(f"Query {idx} (score: {score:.1f}):")
            formatted_queries.append(f"  Original: \"{query_data['query_text']}\"")
            formatted_queries.append(f"  Search: \"{query_data['search_term']}\"")
            formatted_queries.append(f"  Time: {query_data['query_time'][:10]}")
            formatted_queries.append(f"  Sources:")

            for src_idx, source in enumerate(query_data['results'][:5]):  # Top 5 sources per query
                title = source.get('title', 'No title')[:60]
                date = source.get('date', 'No date')
                snippet_preview = source.get('snippet', '')[:100]
                formatted_queries.append(f"    [{src_idx}] {title} ({date})")
                formatted_queries.append(f"        Preview: {snippet_preview}...")

            formatted_queries.append("")

        # Build selection instructions based on whether URL sources exist
        url_instruction = ""
        if url_sources:
            url_instruction = f"""
**URL Source Selection:**
- For USER-REFERENCED URLs above, use: {{"query_index": -1, "source_index": <index>}}
- These are high-priority as the user explicitly mentioned them
"""

        return f"""# Memory Recall Task

**Today's Date:** {today}

**Current Query:** {query}

{url_section}**Past Queries ({len(filtered_queries)} candidates):**

{chr(10).join(formatted_queries)}

**Task:**
1. Select up to {max_select} most relevant sources that would help answer the current query
2. Assess the probability (0.0-1.0) that these selected sources can provide a **factually accurate, up-to-date, and complete** answer to the current query
{url_instruction}
**Selection Criteria:**
- **Relevance**: Does the source contain information directly relevant to the query?
- **Completeness**: Do the sources together provide a comprehensive answer?
- **Accuracy**: Are the sources from reliable, authoritative sources?
- **Recency** (when applicable): For time-sensitive queries (e.g., "latest", "new", "current", specific years), prioritize recent sources
- **Diversity**: Avoid redundant sources covering the same information

**Confidence Assessment Guidelines:**
- **0.9-1.0**: Sources definitely provide complete, accurate, up-to-date answer
- **0.7-0.9**: Sources likely provide good answer, may have minor gaps
- **0.5-0.7**: Sources provide partial answer, missing some important information
- **0.3-0.5**: Sources tangentially related, significant gaps exist
- **0.0-0.3**: Sources insufficient to answer query properly

Consider:
- Does the query require current information? Check source dates against today's date ({today})
- Are the sources comprehensive enough to fully address all aspects of the query?
- Are there any obvious gaps in coverage that would require new search?

Return JSON:
{{
  "selected_sources": [
    {{"query_index": -1, "source_index": 0}},
    {{"query_index": 0, "source_index": 2}},
    ...
  ],
  "confidence": 0.85,
  "reasoning": "Brief explanation of selection and why this confidence level"
}}
"""

    def _convert_to_search_format(
        self,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert memory sources to search API format with metadata.
        """
        results = []

        for source in sources:
            result = {
                # Standard search API fields
                "url": source.get('url'),
                "title": source.get('title'),
                "snippet": source.get('snippet'),
                "date": source.get('date'),
                "last_updated": source.get('last_updated'),

                # Memory-specific metadata
                "_from_memory": True,
                "_original_query": source.get('_query_text'),
                "_query_date": source.get('_query_time'),
                "_memory_age_days": self._calculate_age_days(source.get('_query_time')),
                "_original_rank": source.get('_source_rank', 0),
                "_memory_relevance": source.get('_relevance_score', 0),
                "_freshness_indicator": self._get_freshness_indicator(source.get('_query_time'))
            }

            results.append(result)

        return results

    def _calculate_confidence(
        self,
        selected_sources: List[Dict[str, Any]],
        query: str
    ) -> float:
        """
        Get confidence from Gemini's assessment.
        If Gemini didn't provide confidence (keyword fallback), use simple heuristic.
        """
        if not selected_sources:
            return 0.0

        # Check if Gemini provided confidence (stored in sources)
        gemini_confidences = [s.get('_gemini_confidence') for s in selected_sources if '_gemini_confidence' in s]

        if gemini_confidences:
            # Use Gemini's confidence (same for all sources from same Gemini call)
            return gemini_confidences[0]

        # Fallback: Simple heuristic based on count and query overlap
        # This only happens when keyword-only recall is used
        count_score = min(len(selected_sources) / 7.0, 1.0)

        # Calculate average query overlap
        query_tokens = set(query.lower().split())
        avg_overlap = 0.0
        for source in selected_sources:
            original_query = source.get('_query_text', '')
            original_tokens = set(original_query.lower().split())
            intersection = len(query_tokens & original_tokens)
            union = len(query_tokens | original_tokens)
            overlap = intersection / union if union > 0 else 0
            avg_overlap += overlap
        avg_overlap /= len(selected_sources)

        # Simple formula for fallback (count + overlap only)
        confidence = (count_score * 0.4) + (avg_overlap * 0.6)

        return min(confidence, 1.0)

    # === HELPER METHODS ===

    def _recency_score(self, timestamp: str) -> float:
        """Calculate recency score (0-5 range)."""
        try:
            query_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            age_days = (datetime.now(timezone.utc) - query_time).days

            # Scoring: 5 (today) → 4 (week) → 3 (month) → 2 (3 months) → 1 (6 months) → 0 (year+)
            if age_days < 1:
                return 5.0
            elif age_days < 7:
                return 4.0
            elif age_days < 30:
                return 3.0
            elif age_days < 90:
                return 2.0
            elif age_days < 180:
                return 1.0
            else:
                return 0.0
        except:
            return 0.0

    def _calculate_age_days(self, timestamp: str) -> int:
        """Calculate age in days."""
        try:
            query_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return (datetime.now(timezone.utc) - query_time).days
        except:
            return 999

    def _get_freshness_indicator(self, timestamp: str) -> str:
        """Get human-readable freshness indicator."""
        age_days = self._calculate_age_days(timestamp)

        if age_days < 1:
            return "today"
        elif age_days < 7:
            return "this_week"
        elif age_days < 30:
            return "this_month"
        elif age_days < 90:
            return "recent"
        else:
            return "older"

    def _extract_cost_from_response(self, response: Dict[str, Any]) -> float:
        """Extract cost from AI client response (same method as the_clone.py)."""
        try:
            enhanced = response.get('enhanced_data', {})
            costs = enhanced.get('costs', {}).get('actual', {})
            cost = costs.get('total_cost', 0.0)
            return cost
        except:
            return 0.0

    def _empty_recall_result(self) -> Dict[str, Any]:
        """Return empty recall result."""
        return {
            'memories': [],
            'confidence': 0.0,
            'should_search': True,
            'recall_metadata': {
                'total_queries': len(self._memory['queries']) if self._memory else 0,
                'filtered_queries': 0,
                'sources_selected': 0,
                'recall_cost': 0.0,
                'recall_time_ms': 0.0
            }
        }

    # === URL-BASED RECALL ===

    def recall_by_urls(self, urls: List[str]) -> Dict[str, Any]:
        """
        Look up sources by exact URL match in memory.

        This is used when the user's query contains URLs that we've
        previously searched and stored in memory. Unlike keyword-based
        recall, this is a direct lookup - no AI selection needed.

        Args:
            urls: List of URLs to look up

        Returns:
            Dict with:
            - 'found': List of sources in search API format with _from_memory metadata
            - 'not_found': List of URLs not in memory (can be fetched live)
        """
        result = {'found': [], 'not_found': []}

        if self._memory is None:
            result['not_found'] = list(urls) if urls else []
            return result

        if not urls:
            return result

        by_url_index = self._memory['indexes'].get('by_url', {})
        queries = self._memory['queries']
        found_sources = []
        seen_urls = set()
        found_target_urls = set()

        for target_url in urls:
            # Normalize URL for lookup (remove trailing slash)
            normalized_url = target_url.rstrip('/')

            # Check both with and without trailing slash
            query_ids = by_url_index.get(target_url, []) or by_url_index.get(normalized_url, [])

            if not query_ids:
                # Try partial match (URL might have been stored with different query params)
                base_url = target_url.split('?')[0].rstrip('/')
                for stored_url, qids in by_url_index.items():
                    if stored_url.split('?')[0].rstrip('/') == base_url:
                        query_ids = qids
                        break

            if not query_ids:
                logger.debug(f"[MEMORY] URL not found in memory: {target_url}")
                continue

            # Get the most recent query that has this URL
            url_found = False
            for query_id in query_ids:
                query_data = queries.get(query_id)
                if not query_data:
                    continue

                # Find the source with this URL in the query results
                for idx, res in enumerate(query_data.get('results', [])):
                    result_url = res.get('url', '')

                    # Match by URL (exact or base URL match)
                    if result_url == target_url or result_url.rstrip('/') == normalized_url:
                        if result_url in seen_urls:
                            continue  # Skip duplicates

                        seen_urls.add(result_url)
                        found_target_urls.add(target_url)
                        url_found = True

                        # Build source with metadata (same format as _convert_to_search_format)
                        source = {
                            "url": res.get('url'),
                            "title": res.get('title'),
                            "snippet": res.get('snippet'),
                            "date": res.get('date'),
                            "last_updated": res.get('last_updated'),

                            # Memory-specific metadata
                            "_from_memory": True,
                            "_from_url_lookup": True,  # Mark as direct URL lookup
                            "_original_query": query_data.get('search_term'),
                            "_query_date": query_data.get('query_time'),
                            "_memory_age_days": self._calculate_age_days(query_data.get('query_time')),
                            "_original_rank": idx,
                            "_memory_relevance": 10.0,  # High relevance for direct URL match
                            "_freshness_indicator": self._get_freshness_indicator(query_data.get('query_time'))
                        }

                        found_sources.append(source)
                        logger.info(f"[MEMORY] Found URL in memory: {target_url} (from query: {query_data.get('search_term', 'unknown')})")
                        break  # Found this URL, move to next target

                if url_found:
                    break  # Already found, no need to check other queries

        # Track URLs not found in memory
        not_found = [url for url in urls if url not in found_target_urls]

        logger.info(f"[MEMORY] URL lookup: {len(urls)} URLs -> {len(found_sources)} found, {len(not_found)} not found")
        return {'found': found_sources, 'not_found': not_found}

    async def fetch_url_content(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch content from URLs not in memory using Jina AI Reader.

        This is used when URLs mentioned in the query aren't in memory.
        Jina handles JS-rendered content and returns clean markdown.

        Args:
            urls: List of URLs to fetch

        Returns:
            List of sources in search API format with _from_live_fetch metadata
        """
        if not urls:
            return []

        from shared.html_table_parser import HTMLTableParser

        html_parser = HTMLTableParser(timeout=30)
        fetched_sources = []

        for url in urls:
            try:
                logger.info(f"[MEMORY] Fetching URL content via Jina: {url}")
                jina_result = await html_parser.fetch_via_jina(url)

                if jina_result['success']:
                    markdown = jina_result.get('markdown', '')
                    title = jina_result.get('title', 'Unknown Title')

                    # Truncate markdown to reasonable size for synthesis (first 8000 chars)
                    snippet = markdown[:8000] if len(markdown) > 8000 else markdown

                    source = {
                        "url": url,
                        "title": title,
                        "snippet": snippet,
                        "date": None,
                        "last_updated": None,

                        # Live fetch metadata
                        "_from_memory": False,
                        "_from_live_fetch": True,
                        "_from_url_lookup": True,
                        "_fetch_method": "jina_reader",
                        "_memory_relevance": 10.0,  # High relevance - user explicitly mentioned
                        "_content_length": len(markdown)
                    }

                    fetched_sources.append(source)
                    logger.info(f"[MEMORY] Fetched URL: {url} ({len(markdown)} chars, title: {title[:50]})")
                else:
                    logger.warning(f"[MEMORY] Failed to fetch URL: {url} - {jina_result.get('error', 'Unknown error')}")

            except Exception as e:
                logger.error(f"[MEMORY] Error fetching URL {url}: {str(e)}")

        logger.info(f"[MEMORY] Live URL fetch: {len(urls)} URLs -> {len(fetched_sources)} fetched")
        return fetched_sources

    # === STATS ===

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        if self._memory is None:
            return {'error': 'Memory not loaded'}

        total_sources = sum(
            len(q['results'])
            for q in self._memory['queries'].values()
        )

        return {
            'session_id': self.session_id,
            'total_queries': len(self._memory['queries']),
            'total_sources': total_sources,
            'unique_urls': len(self._memory['indexes']['by_url']),
            'created_at': self._memory.get('created_at'),
            'last_updated': self._memory.get('last_updated')
        }
