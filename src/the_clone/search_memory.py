#!/usr/bin/env python3
"""
Search Memory for Perplexity Search API.
Session-scoped memory with volatile RAM + S3 persistence.
"""

import asyncio
import json
import logging
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from collections import defaultdict

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
        query: str,
        search_term: str,
        results: Dict[str, Any],
        parameters: Dict[str, Any],
        strategy: str = "unknown"
    ) -> str:
        """
        Store search results in memory and backup to S3.

        Deduplication rules:
        - Only dedupe within same query (not across queries)
        - Keep both if different max_tokens (preserve richer data)

        Args:
            query: Original user query
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
        query_id = self._generate_query_id(query, search_term)

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
            "query_text": query,
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

    def _generate_query_id(self, query: str, search_term: str) -> str:
        """
        Generate stable query ID based on query + search_term.
        Same query+term = same ID (enables deduplication).
        """
        # Create hash of query + search_term
        content = f"{query}|{search_term}".lower().strip()
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
        depth: str = "shallow"
    ) -> Dict[str, Any]:
        """
        Recall relevant memories using iterative Gemini approach.

        Strategy:
        1. Keyword pre-filter on queries (fast, free)
        2. Gemini selects relevant sources from filtered queries

        Args:
            query: Current user query
            keywords: {'positive': [...], 'negative': [...]}
            max_results: Max sources to return
            confidence_threshold: Minimum confidence to trust recall

        Returns:
            {
                'memories': List[dict],  # Search API format with _from_memory metadata
                'confidence': float,
                'should_search': bool,
                'recall_metadata': {...}
            }
        """
        start_time = time.time()

        # Ensure memory is loaded
        if self._memory is None:
            self._initialize_empty_memory()

        # If no queries in memory, return empty
        if not self._memory['queries']:
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

        if not filtered_queries:
            logger.debug("[MEMORY] No relevant queries found after keyword filter")
            return self._empty_recall_result()

        logger.info(
            f"[MEMORY] Keyword filter: {len(self._memory['queries'])} → "
            f"{len(filtered_queries)} candidate queries"
        )

        # Stage 2: Gemini selects sources from filtered queries
        if self.ai_client is None:
            logger.warning("[MEMORY] No AI client provided, using keyword-only recall")
            selected_sources = self._keyword_only_recall(filtered_queries, max_results)
            llm_cost = 0.0
            confidence = self._calculate_confidence(selected_sources, query)
        else:
            selected_sources, selection_cost = await self._gemini_select_sources(
                query=query,
                filtered_queries=filtered_queries,
                max_select=max_results
            )

            # Get initial confidence from Gemini selection
            confidence = self._calculate_confidence(selected_sources, query)

            # Stage 3: If high confidence, verify with full snippet text
            recommended_searches = []
            if confidence >= 0.75 and len(selected_sources) > 0:
                logger.debug(f"[MEMORY] High confidence ({confidence:.2f}), running verification with full snippets...")
                verified_confidence, verification_cost, recommended_searches, ranked_source_indices = await self._verify_with_full_snippets(
                    query=query,
                    selected_sources=selected_sources,
                    breadth=breadth,
                    depth=depth
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
                'recall_cost': llm_cost,
                'recall_time_ms': recall_time,
                'verification_run': confidence >= 0.75
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
        max_select: int
    ) -> tuple[List[Dict[str, Any]], float]:
        """
        Use Gemini (via ai_client) to select most relevant sources.
        Also assesses confidence that sources can provide complete, accurate answer.

        Returns:
            (selected_sources, cost)
        """
        # Build prompt with filtered queries and their sources
        prompt = self._build_recall_prompt(query, filtered_queries, max_select)

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
            for selection in data.get('selected_sources', [])[:max_select]:
                query_idx = selection.get('query_index')
                source_idx = selection.get('source_index')

                if query_idx < len(filtered_queries):
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

            logger.debug(f"[MEMORY] Gemini selected {len(selected_sources)} sources, confidence={gemini_confidence:.2f} (cost: ${cost:.4f})")

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
        depth: str = "shallow"
    ) -> tuple[float, float, List[str], List[int]]:
        """
        Verify that selected sources can actually answer the query.
        Provides full snippet text to Gemini for assessment.
        Considers breadth/depth requirements.
        Returns ranked source indices (replaces triage when using memory only).

        Returns:
            (verified_confidence, cost, recommended_searches, ranked_source_indices)
        """
        from datetime import datetime

        # Get today's date
        today = datetime.now().strftime("%Y-%m-%d")

        # Build verification prompt with full snippets
        snippets_text = []
        for i, source in enumerate(selected_sources, 1):
            snippets_text.append(f"**Source {i}:** {source.get('title', 'No title')}")
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

        prompt = f"""# Memory Verification Task

**Today's Date:** {today}

**Query:** {query}

**Answer Requirements:**
- Breadth: {breadth.upper()} - {requirements_map.get(breadth, 'focused')}
- Depth: {depth.upper()} - {depth_map.get(depth, 'concise')}

**Available Sources ({len(selected_sources)}):**

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
                    "description": f"Indices of USEFUL sources only (0-{len(selected_sources)-1}), ranked best first. Skip irrelevant sources. Replaces triage for memory-only queries.",
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
            ranked_source_indices = data.get('ranked_source_indices', list(range(len(selected_sources))))

            logger.info(
                f"[MEMORY] Verification: confidence={verified_confidence:.2f}, "
                f"can_answer={data.get('can_answer', False)}, "
                f"ranked_sources={len(ranked_source_indices)}, "
                f"recommended_searches={len(recommended_searches)}"
            )

            return verified_confidence, cost, recommended_searches, ranked_source_indices

        except Exception as e:
            logger.error(f"[MEMORY] Verification failed: {e}")
            # Return original confidence on error, no reordering
            return self._calculate_confidence(selected_sources, query), 0.0, [], []

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
        max_select: int
    ) -> str:
        """Build prompt for Gemini source selection with confidence assessment."""
        from datetime import datetime

        # Get today's date
        today = datetime.now().strftime("%Y-%m-%d")

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

        return f"""# Memory Recall Task

**Today's Date:** {today}

**Current Query:** {query}

**Past Queries ({len(filtered_queries)} candidates):**

{chr(10).join(formatted_queries)}

**Task:**
1. Select up to {max_select} most relevant sources that would help answer the current query
2. Assess the probability (0.0-1.0) that these selected sources can provide a **factually accurate, up-to-date, and complete** answer to the current query

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
