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

    Recall Flow:
    1. Keyword pre-filter: Filter stored queries by required/positive/negative keywords
    2. Gemini selection: Select sources + per-search-term confidence vector
       - If ALL confidence < threshold: Skip verification, search all terms
       - If ANY confidence >= threshold: Run verification
    3. Snippet verification: Full snippet review, returns refined search terms for low-conf domains
    4. URL sources: Always included at top of results regardless of selection

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
        """Load memory from S3 (async)."""
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

    def _load_from_s3_sync(self):
        """
        Load memory from S3 (synchronous - for use within locks).

        Used by MemoryCache to load memory while holding a lock.
        """
        try:
            response = self.s3_manager.s3_client.get_object(
                Bucket=self.s3_manager.bucket_name,
                Key=self.memory_key
            )

            memory_json = response['Body'].read().decode('utf-8')
            self._memory = json.loads(memory_json)

            # Convert by_url dict back from JSON
            if isinstance(self._memory['indexes'].get('by_url'), dict):
                self._memory['indexes']['by_url'] = defaultdict(
                    list,
                    self._memory['indexes']['by_url']
                )

        except self.s3_manager.s3_client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"Memory file not found: {self.memory_key}")

    def _prepare_memory_for_save(self) -> dict:
        """
        Prepare memory for S3 save with deep copy to prevent race conditions.

        Returns:
            Deep copy of memory safe for serialization
        """
        import copy

        # Update timestamp
        self._memory['last_updated'] = datetime.now(timezone.utc).isoformat()

        # Deep copy to prevent concurrent modifications during serialization
        memory_to_save = copy.deepcopy(self._memory)

        # Convert defaultdict to regular dict for JSON serialization
        if isinstance(memory_to_save['indexes'].get('by_url'), defaultdict):
            memory_to_save['indexes']['by_url'] = dict(memory_to_save['indexes']['by_url'])

        return memory_to_save

    def _backup_sync(self):
        """
        Synchronous backup to S3 (for use in sync contexts).
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                memory_to_save = self._prepare_memory_for_save()

                # Save to S3 (synchronous)
                self.s3_manager.s3_client.put_object(
                    Bucket=self.s3_manager.bucket_name,
                    Key=self.memory_key,
                    Body=json.dumps(memory_to_save),  # No indent - 30-40% smaller, faster
                    ContentType='application/json'
                )

                logger.debug(f"[MEMORY] Backed up to S3 sync (attempt {attempt + 1})")
                return

            except Exception as e:
                if attempt == self.MAX_RETRIES - 1:
                    logger.error(f"[MEMORY] Failed to backup after {self.MAX_RETRIES} attempts: {e}")
                    raise

                # Exponential backoff
                wait_time = self.RETRY_BASE_DELAY ** attempt
                logger.warning(f"[MEMORY] Backup failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                time.sleep(wait_time)

    async def backup(self):
        """
        Save current memory state to S3 with optimistic concurrency.
        Retries on conflict with exponential backoff.
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                memory_to_save = self._prepare_memory_for_save()

                # Save to S3 (async)
                await asyncio.to_thread(
                    self.s3_manager.s3_client.put_object,
                    Bucket=self.s3_manager.bucket_name,
                    Key=self.memory_key,
                    Body=json.dumps(memory_to_save),  # No indent - 30-40% smaller, faster
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

    def _store_search_no_backup(
        self,
        search_term: str,
        results: Dict[str, Any],
        parameters: Dict[str, Any],
        strategy: str = "unknown"
    ) -> str:
        """
        Store search results in memory WITHOUT backup to S3.

        Used by MemoryCache for batch operations.
        Identical to store_search() but skips the backup() call.

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
                logger.debug(
                    f"[MEMORY] Skipping storage - existing result has higher max_tokens "
                    f"({existing_max_tokens} vs {new_max_tokens})"
                )
                return query_id
            else:
                logger.debug(
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

        logger.debug(
            f"[MEMORY] Stored query '{search_term}' with {len(results.get('results', []))} results (no backup)"
        )

        return query_id

    def _store_url_content_no_backup(
        self,
        url: str,
        content: str,
        title: str = None,
        source_type: str = "table_extraction",
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Store URL content in memory WITHOUT backup to S3.

        Used by MemoryCache for batch operations.
        Identical to store_url_content() but skips the backup() call.

        Returns:
            query_id: Unique identifier for stored content
        """
        # Ensure memory is loaded
        if self._memory is None:
            self._initialize_empty_memory()

        # Generate query ID based on URL (not search term)
        query_id = self._generate_url_content_id(url, source_type)

        # Check if we already have content for this URL
        existing_query = self._memory['queries'].get(query_id)

        if existing_query:
            # Compare content length - keep richer data
            existing_content_len = len(existing_query.get('results', [{}])[0].get('snippet', ''))
            new_content_len = len(content)

            if new_content_len <= existing_content_len:
                logger.debug(
                    f"[MEMORY] Skipping URL content storage - existing content is richer "
                    f"({existing_content_len} vs {new_content_len} chars)"
                )
                return query_id
            else:
                logger.debug(
                    f"[MEMORY] Updating URL content with richer data "
                    f"({existing_content_len} -> {new_content_len} chars)"
                )

        # Build result in search API format
        result_entry = {
            "url": url,
            "title": title or f"Extracted content from {url}",
            "snippet": content,
            "date": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "_source_type": source_type,
            "_is_full_content": True,  # Flag that this is complete content, not truncated
        }

        # Add any additional metadata
        if metadata:
            result_entry["_extraction_metadata"] = metadata

        # Store as query data (compatible with existing recall system)
        query_data = {
            "query_text": f"[URL_CONTENT] {url}",
            "search_term": f"[URL_CONTENT] {url}",
            "query_time": datetime.now(timezone.utc).isoformat(),
            "parameters": {
                "source_type": source_type,
                "content_length": len(content),
                "is_url_content": True
            },
            "results": [result_entry],
            "metadata": {
                "cost": 0.0,  # No API cost for stored content
                "num_results": 1,
                "strategy": source_type,
                "is_url_content": True
            }
        }

        # Add to queries
        self._memory['queries'][query_id] = query_data

        # Update time index
        if query_id in self._memory['indexes']['by_time']:
            self._memory['indexes']['by_time'].remove(query_id)
        self._memory['indexes']['by_time'].insert(0, query_id)

        # Update URL index - this is critical for recall_by_urls
        if query_id not in self._memory['indexes']['by_url'][url]:
            self._memory['indexes']['by_url'][url].append(query_id)

        logger.debug(
            f"[MEMORY] Stored URL content: {url} ({len(content)} chars, type={source_type}, no backup)"
        )

        return query_id

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
                logger.debug(
                    f"[MEMORY] Skipping storage - existing result has higher max_tokens "
                    f"({existing_max_tokens} vs {new_max_tokens})"
                )
                return query_id
            else:
                logger.debug(
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

        logger.debug(
            f"[MEMORY] Stored query '{search_term}' with {len(results.get('results', []))} results"
        )

        return query_id

    async def store_url_content(
        self,
        url: str,
        content: str,
        title: str = None,
        source_type: str = "table_extraction",
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Store directly fetched/extracted URL content in memory.

        This is used for Table Maker extractions where we have full table
        content that should be available for future validation lookups.
        Unlike store_search(), this stores content for a SPECIFIC URL
        with potentially richer/more complete data than search snippets.

        Args:
            url: The source URL
            content: Full content (e.g., markdown table, extracted text)
            title: Optional title for the content
            source_type: Type of content (table_extraction, background_research, etc.)
            metadata: Optional additional metadata (columns_found, rows_count, etc.)

        Returns:
            query_id: Unique identifier for stored content
        """
        # Ensure memory is loaded
        if self._memory is None:
            self._initialize_empty_memory()

        # Generate query ID based on URL (not search term)
        query_id = self._generate_url_content_id(url, source_type)

        # Check if we already have content for this URL
        existing_query = self._memory['queries'].get(query_id)

        if existing_query:
            # Compare content length - keep richer data
            existing_content_len = len(existing_query.get('results', [{}])[0].get('snippet', ''))
            new_content_len = len(content)

            if new_content_len <= existing_content_len:
                logger.debug(
                    f"[MEMORY] Skipping URL content storage - existing content is richer "
                    f"({existing_content_len} vs {new_content_len} chars)"
                )
                return query_id
            else:
                logger.debug(
                    f"[MEMORY] Updating URL content with richer data "
                    f"({existing_content_len} -> {new_content_len} chars)"
                )

        # Build result in search API format
        result_entry = {
            "url": url,
            "title": title or f"Extracted content from {url}",
            "snippet": content,
            "date": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "_source_type": source_type,
            "_is_full_content": True,  # Flag that this is complete content, not truncated
        }

        # Add any additional metadata
        if metadata:
            result_entry["_extraction_metadata"] = metadata

        # Store as query data (compatible with existing recall system)
        query_data = {
            "query_text": f"[URL_CONTENT] {url}",
            "search_term": f"[URL_CONTENT] {url}",
            "query_time": datetime.now(timezone.utc).isoformat(),
            "parameters": {
                "source_type": source_type,
                "content_length": len(content),
                "is_url_content": True
            },
            "results": [result_entry],
            "metadata": {
                "cost": 0.0,  # No API cost for stored content
                "num_results": 1,
                "strategy": source_type,
                "is_url_content": True
            }
        }

        # Add to queries
        self._memory['queries'][query_id] = query_data

        # Update time index
        if query_id in self._memory['indexes']['by_time']:
            self._memory['indexes']['by_time'].remove(query_id)
        self._memory['indexes']['by_time'].insert(0, query_id)

        # Update URL index - this is critical for recall_by_urls
        if query_id not in self._memory['indexes']['by_url'][url]:
            self._memory['indexes']['by_url'][url].append(query_id)

        # Backup to S3
        try:
            await self.backup()
        except Exception as e:
            logger.error(f"[MEMORY] Failed to backup URL content, continuing anyway: {e}")

        logger.debug(
            f"[MEMORY] Stored URL content: {url} ({len(content)} chars, type={source_type})"
        )

        return query_id

    def _generate_url_content_id(self, url: str, source_type: str) -> str:
        """
        Generate stable ID for URL content storage.
        Different source_types for same URL get different IDs (allows multiple snippets).
        """
        content = f"{url}|{source_type}".lower().strip()
        hash_hex = hashlib.md5(content.encode()).hexdigest()[:12]
        return f"url_content_{hash_hex}"

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
        url_sources: Optional[List[Dict[str, Any]]] = None,
        search_terms: Optional[List[str]] = None,
        skip_verification: bool = False
    ) -> Dict[str, Any]:
        """
        Recall relevant memories with per-search-term confidence assessment.

        Flow (skip_verification=False, default):
        1. Keyword pre-filter: Filter stored queries by required/positive/negative keywords
           - Required keywords use | for OR variants, AND between groups
           - Example: ["Apple|AAPL", "stock|shares"] = (Apple OR AAPL) AND (stock OR shares)
        2. Gemini selection: Select sources + per-search-term confidence vector
           - If ALL confidence < threshold: Skip verification, return all search terms for fresh search
           - If ANY confidence >= threshold: Run verification for refined terms
        3. Snippet verification (if any high conf): Full snippet review
           - Returns refined search terms for low-confidence domains
        4. URL sources: Always included at top of results regardless of selection

        Flow (skip_verification=True, for extract-then-verify):
        1. Keyword pre-filter
        2. Gemini selection (titles/previews only)
        3. Return sources WITHOUT confidence assessment
        4. Caller extracts snippets then assesses confidence based on actual quotes

        Args:
            query: Current user query
            keywords: {'required': [...], 'positive': [...], 'negative': [...]}
                - required: Entity identifiers with | for variants (AND between groups)
                - positive: Terms that boost relevance
                - negative: Terms that penalize relevance
            max_results: Max sources to return
            confidence_threshold: Minimum confidence (default 0.6) - terms below trigger fresh search
            url_sources: Sources from URLs mentioned in query (always included at top)
            search_terms: List of search terms for per-term confidence assessment

        Returns:
            {
                'memories': List[dict],           # Sources in search API format
                'confidence': float,              # Overall confidence (mean of vector)
                'confidence_vector': List[float], # Per-search-term confidence
                'should_search': bool,            # True if any terms need fresh search
                'recommended_searches': List[str],# Terms needing search (refined or original)
                'search_term_confidence': dict,   # {term: confidence} for logging
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
            return self._empty_recall_result(search_terms)

        # Extract keywords
        required_keywords = keywords.get('required', []) if keywords else []
        positive_keywords = keywords.get('positive', []) if keywords else []
        negative_keywords = keywords.get('negative', []) if keywords else []

        # Stage 1: Keyword pre-filter on queries
        filtered_queries = self._filter_queries_by_keywords(
            query=query,
            required_keywords=required_keywords,
            positive_keywords=positive_keywords,
            negative_keywords=negative_keywords
        )

        # Log URL sources if present
        if url_sources:
            logger.debug(f"[MEMORY] {len(url_sources)} URL sources from query will be prioritized")

        if not filtered_queries and not url_sources:
            logger.debug("[MEMORY] No relevant queries found after keyword filter")
            return self._empty_recall_result(search_terms)

        logger.debug(
            f"[MEMORY] Keyword filter: {len(self._memory['queries'])} → "
            f"{len(filtered_queries)} candidate queries"
        )

        # Stage 2: Gemini selects sources + per-term confidence
        search_terms_list = search_terms or []
        num_terms = len(search_terms_list)
        verification_run = False

        if self.ai_client is None:
            logger.warning("[MEMORY] No AI client provided, using keyword-only recall")
            selected_sources = self._keyword_only_recall(filtered_queries, max_results)
            llm_cost = 0.0
            confidence_vector = [0.0] * num_terms  # No confidence without AI
            search_term_confidence = {term: 0.0 for term in search_terms_list}
            recommended_searches = search_terms_list[:]  # Search all terms
        else:
            selected_sources, confidence_vector, selection_cost = await self._gemini_select_sources(
                query=query,
                filtered_queries=filtered_queries,
                max_select=max_results,
                url_sources=url_sources,
                search_terms=search_terms_list
            )

            # Build per-term confidence dict
            search_term_confidence = {}
            for i, term in enumerate(search_terms_list):
                search_term_confidence[term] = confidence_vector[i] if i < len(confidence_vector) else 0.0

            # Skip verification if requested (for extract-then-verify pattern)
            if skip_verification:
                logger.debug(f"[MEMORY] Skipping verification (extract-then-verify pattern)")
                llm_cost = selection_cost
                # Don't set confidence - caller will assess after extraction
                confidence_vector = None
                recommended_searches = None  # Caller will determine after extraction
                verification_run = False
            else:
                # Check if ALL confidences are low -> skip verification, go straight to search
                all_low = all(c < confidence_threshold for c in confidence_vector) if confidence_vector else True
                any_high = any(c >= confidence_threshold for c in confidence_vector) if confidence_vector else False

                if all_low:
                    # ALL terms have low confidence -> skip verification, search all terms
                    # URL sources will still be included in final results regardless
                    logger.debug(f"[MEMORY] All {num_terms} terms have low confidence, skipping verification")
                    llm_cost = selection_cost
                    recommended_searches = search_terms_list[:]  # Search all terms
                else:
                    # ANY term has high confidence -> run verification for refined terms
                    verification_run = True
                    logger.debug(f"[MEMORY] Running verification (any_high={any_high}, search_terms={num_terms})...")
                    verified_sources, verification_cost, recommended_searches, verified_confidence_vector = await self._verify_with_full_snippets(
                        query=query,
                        selected_sources=selected_sources,
                        breadth=breadth,
                        depth=depth,
                        url_sources=url_sources,
                        search_terms=search_terms_list
                    )

                    # Update with verified results
                    selected_sources = verified_sources
                    llm_cost = selection_cost + verification_cost

                    # Update per-term confidence with verified values
                    if verified_confidence_vector:
                        confidence_vector = verified_confidence_vector
                        for i, term in enumerate(search_terms_list):
                            search_term_confidence[term] = confidence_vector[i] if i < len(confidence_vector) else 0.0

                    logger.debug(f"[MEMORY] Verification complete: conf_vector={confidence_vector}, recommended_searches={recommended_searches} (cost: ${verification_cost:.4f})")

        # Calculate overall confidence from vector (None if verification skipped)
        if confidence_vector is not None:
            confidence = sum(confidence_vector) / len(confidence_vector) if confidence_vector else 0.0
        else:
            confidence = None  # No confidence assessment yet (extract-then-verify pattern)
            confidence_vector = []  # Empty vector

        # Post-selection filter: Validate individual sources match required keywords
        # This catches sources that slipped through query-level filter (e.g., Amazon source in MSFT query)
        if required_keywords:
            selected_sources = self._filter_sources_by_required_keywords(selected_sources, required_keywords)

        # Convert to search API format
        memory_results = self._convert_to_search_format(selected_sources)

        # URL sources ALWAYS included (independent of ranking/selection)
        if url_sources:
            existing_urls = {m.get('url') for m in memory_results}
            for url_src in url_sources:
                if url_src.get('url') not in existing_urls:
                    # Add at the BEGINNING (high priority)
                    memory_results.insert(0, url_src)
                    existing_urls.add(url_src.get('url'))
            logger.debug(f"[MEMORY] URL sources always included: {len(url_sources)} sources")

        recall_time = (time.time() - start_time) * 1000

        # Handle recommended_searches when verification skipped
        if recommended_searches is None:
            recommended_searches = []  # Caller will determine after extraction

        return {
            'memories': memory_results,
            'confidence': confidence,  # None if verification skipped
            'confidence_vector': confidence_vector,  # [] if verification skipped
            'should_search': len(recommended_searches) > 0 if recommended_searches else None,
            'recommended_searches': recommended_searches,
            'search_term_confidence': search_term_confidence,
            'recall_metadata': {
                'total_queries': len(self._memory['queries']),
                'filtered_queries': len(filtered_queries),
                'sources_selected': len(selected_sources),
                'url_sources_count': len(url_sources),
                'recall_cost': llm_cost,
                'recall_time_ms': recall_time,
                'verification_run': verification_run,
                'verification_skipped': skip_verification
            }
        }

    def _filter_queries_by_keywords(
        self,
        query: str,
        required_keywords: List[str],
        positive_keywords: List[str],
        negative_keywords: List[str],
        top_k: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Filter queries by keyword match and query similarity.
        Keywords are matched against FULL TEXT (snippets), not just queries.

        Required keywords: Source must contain AT LEAST ONE (case-insensitive substring).
        This is "ANY" logic because keywords are entity variants (e.g., "Apple", "AAPL").

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

            # Full searchable text for keyword matching
            searchable_text = f"{past_query} {search_term} {all_snippets}"

            # REQUIRED KEYWORD CHECK: ALL keyword groups must match (AND logic)
            # Each group can have variants separated by | (OR within group)
            # Format: ["Apple|AAPL", "stock|shares"] = (Apple OR AAPL) AND (stock OR shares)
            # If required_keywords is empty, all sources pass this check
            if required_keywords:
                all_groups_match = True
                for keyword_group in required_keywords:
                    # Split by | for variants within this group
                    variants = [v.strip().lower() for v in keyword_group.split('|')]
                    # Check if ANY variant in this group matches (OR logic within group)
                    group_matches = any(variant in searchable_text for variant in variants)
                    if not group_matches:
                        all_groups_match = False
                        break

                if not all_groups_match:
                    # Skip this query - doesn't match all required keyword groups
                    logger.debug(
                        f"[MEMORY] Skipping query '{query_data['search_term']}' - "
                        f"required keywords not matched (needed: {required_keywords})"
                    )
                    continue

            # Calculate query overlap (Jaccard similarity)
            past_tokens = set(past_query.split()) | set(search_term.split())
            intersection = len(query_tokens & past_tokens)
            union = len(query_tokens | past_tokens)
            query_overlap = intersection / union if union > 0 else 0

            # Keyword scoring in FULL TEXT (query + snippets)
            pos_matches = sum(1 for kw in positive_keywords if kw.lower() in searchable_text)
            neg_matches = sum(1 for kw in negative_keywords if kw.lower() in searchable_text)

            # Count required keyword group matches (for relevance boost)
            # Each group counts as 1 if any variant matches
            req_matches = 0
            if required_keywords:
                for keyword_group in required_keywords:
                    variants = [v.strip().lower() for v in keyword_group.split('|')]
                    if any(variant in searchable_text for variant in variants):
                        req_matches += 1

            # Calculate recency score - more recent memories get priority
            # This is important for dynamic content (stock prices, weather, news)
            query_time = query_data.get('query_time', '')
            recency_score = self._recency_score(query_time)

            # Combined score with recency priority
            # Recency acts as a tiebreaker and slight boost for fresher data
            relevance_score = (
                query_overlap * 10.0 +  # Query match most important
                req_matches * 3.0 +     # Required keyword matches get strong boost
                pos_matches * 1.0 +     # Positive keyword matches
                recency_score * 0.5 -   # Recent memories get priority bonus (0-2.5 points)
                neg_matches * 5.0       # Strong penalty for negative keywords
            )

            # Only keep positive scores
            if relevance_score > 0:
                scored_queries.append({
                    'query_id': query_id,
                    'query_data': query_data,
                    'relevance_score': relevance_score,
                    'query_overlap': query_overlap,
                    'recency_score': recency_score,
                    'query_time': query_time
                })

        # Sort by score and return top k
        scored_queries.sort(key=lambda x: x['relevance_score'], reverse=True)
        return scored_queries[:top_k]

    def _filter_sources_by_required_keywords(
        self,
        sources: List[Dict[str, Any]],
        required_keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Post-selection filter: Validate individual sources match required keywords.

        The query-level filter lets through queries where ANY source matches keywords.
        This filter ensures each INDIVIDUAL source matches all required keyword groups.

        Args:
            sources: List of source dicts with 'snippet' and 'title'
            required_keywords: List of keyword groups with | for OR variants
                Example: ["MSFT|Microsoft", "analyst"] = (MSFT OR Microsoft) AND analyst

        Returns:
            Filtered list of sources where each source matches all keyword groups
        """
        if not required_keywords:
            return sources

        filtered = []
        for source in sources:
            # Build searchable text for this individual source
            searchable = f"{source.get('title', '')} {source.get('snippet', '')}".lower()

            # Check all keyword groups (AND logic between groups)
            all_groups_match = True
            for keyword_group in required_keywords:
                # Split by | for variants (OR within group)
                variants = [v.strip().lower() for v in keyword_group.split('|')]
                if not any(variant in searchable for variant in variants):
                    all_groups_match = False
                    break

            if all_groups_match:
                filtered.append(source)
            else:
                logger.debug(
                    f"[MEMORY] Source-level filter removed: {source.get('title', 'No title')[:50]}... "
                    f"(missing required keywords: {required_keywords})"
                )

        if len(filtered) < len(sources):
            logger.debug(
                f"[MEMORY] Source-level keyword filter: {len(sources)} -> {len(filtered)} sources"
            )

        return filtered

    async def _gemini_select_sources(
        self,
        query: str,
        filtered_queries: List[Dict[str, Any]],
        max_select: int,
        url_sources: Optional[List[Dict[str, Any]]] = None,
        search_terms: Optional[List[str]] = None
    ) -> tuple[List[Dict[str, Any]], List[float], float]:
        """
        Use Gemini (via ai_client) to select most relevant sources.
        Assesses per-search-term confidence for granular search decisions.
        URL sources from query are shown at top with special note.

        Returns:
            (selected_sources, confidence_vector, cost)
            - confidence_vector: Per-search-term confidence matched to search_terms order
        """
        url_sources = url_sources or []
        search_terms = search_terms or []
        num_terms = len(search_terms)

        # Build prompt with filtered queries and their sources
        prompt = self._build_recall_prompt(query, filtered_queries, max_select, url_sources, search_terms)

        # Schema for structured output - now with per-term confidence
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
                "confidence_vector": {
                    "type": "array",
                    "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "description": f"Confidence per search term (length={num_terms}), matched to search term order. 0.9+=complete, 0.7-0.9=good, 0.5-0.7=partial, <0.5=insufficient"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation of selection and confidence assessment"
                }
            },
            "required": ["selected_sources", "confidence_vector"]
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

            # Extract per-term confidence vector
            confidence_vector = data.get('confidence_vector', [])
            # Pad with 0.0 if vector is shorter than search_terms
            while len(confidence_vector) < num_terms:
                confidence_vector.append(0.0)
            # Calculate overall for logging
            overall_confidence = sum(confidence_vector) / len(confidence_vector) if confidence_vector else 0.5

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
                        selected_sources.append(source)

            logger.debug(f"[MEMORY] Gemini selected {len(selected_sources)} sources ({url_sources_selected} URL), conf_vector={confidence_vector}, overall={overall_confidence:.2f} (cost: ${cost:.4f})")

            return selected_sources, confidence_vector, cost

        except Exception as e:
            logger.error(f"[MEMORY] Gemini selection failed, using keyword fallback: {e}")
            # Fallback to keyword-only with zero confidence
            selected = self._keyword_only_recall(filtered_queries, max_select)
            return selected, [0.0] * num_terms, 0.0

    async def _verify_with_full_snippets(
        self,
        query: str,
        selected_sources: List[Dict[str, Any]],
        breadth: str = "narrow",
        depth: str = "shallow",
        url_sources: Optional[List[Dict[str, Any]]] = None,
        search_terms: Optional[List[str]] = None
    ) -> tuple[List[Dict[str, Any]], float, List[str], List[float]]:
        """
        Verify that selected sources can actually answer the query.
        Provides full snippet text to Gemini for assessment.
        Returns ranked sources directly (not indices) and updated confidence.

        Returns:
            (verified_sources, cost, recommended_searches, confidence_vector)
            - verified_sources: Sources reordered by Gemini's ranking
            - cost: LLM cost
            - recommended_searches: Refined terms for low-confidence domains
            - confidence_vector: Updated per-term confidence
        """
        from datetime import datetime

        url_sources = url_sources or []
        search_terms_list = search_terms or []
        num_terms = len(search_terms_list)

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
        # FIX: Use 0-indexed display to match schema (was 1-indexed causing off-by-one)
        snippets_text = []
        for i, source in enumerate(all_sources):
            # Mark user-referenced sources
            user_ref_note = " [USER REFERENCED]" if source.get('_user_referenced') else ""
            # Calculate relative time for memory age
            query_time = source.get('_query_time', '')
            relative_time = self._get_relative_time(query_time) if query_time else "unknown age"
            snippets_text.append(f"**[{i}]{user_ref_note}** {source.get('title', 'No title')}")
            snippets_text.append(f"URL: {source.get('url', 'No URL')}")
            snippets_text.append(f"Content Date: {source.get('date', 'No date')} | Memory Age: {relative_time}")
            snippets_text.append(f"Content: {source.get('snippet', 'No content')[:2000]}...")
            snippets_text.append("---")

        # Build search terms section
        search_terms_section = ""
        if search_terms_list:
            numbered_terms = [f'{i}. "{term}"' for i, term in enumerate(search_terms_list)]
            search_terms_section = f"""
**Search Terms ({num_terms}, indexed 0-{num_terms-1}):**
{chr(10).join(numbered_terms)}
"""

        prompt = f"""# Memory Verification

**Date:** {today}
**Query:** {query}
**Requirements:** {breadth}/{depth}
{search_terms_section}

**IMPORTANT - Data Freshness Warning:**
These sources are from MEMORY (previous searches). Check "Memory Age" for each source.
For DYNAMIC content (stock prices, weather, news, sports scores, current events):
- Sources older than 1 day may be STALE - reduce confidence accordingly
- Prefer recent sources over older ones for time-sensitive queries
- If query needs current data and sources are old, recommend fresh search

**Sources ({len(all_sources)}, indexed 0-{len(all_sources)-1}):**

{chr(10).join(snippets_text)}

**Task:** For each search term, ask: "Could I write a complete answer to '[search term]' using ONLY these sources?"
Consider data freshness - old memories about dynamic topics should lower confidence.

**Output (arrays matched to search term order):**
- `confidence_vector`: [{num_terms} floats] confidence per term. 0.9+=yes fully, 0.7-0.9=mostly yes, 0.5-0.7=partially, <0.5=no
- `refined_terms`: [{num_terms} strings] refined search term or "" to keep original
- `ranked_source_indices`: [ints] source indices (0-{len(all_sources)-1}) ranked by usefulness, best first. Prefer recent sources.
"""

        schema = {
            "type": "object",
            "properties": {
                "confidence_vector": {
                    "type": "array",
                    "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "description": f"Confidence per search term, length={num_terms}"
                },
                "refined_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"Refined terms, length={num_terms}. '' to keep original."
                },
                "ranked_source_indices": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "description": f"Source indices 0-{len(all_sources)-1}, best first"
                }
            },
            "required": ["confidence_vector", "refined_terms", "ranked_source_indices"]
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

            confidence_vector = data.get('confidence_vector', [])
            refined_terms = data.get('refined_terms', [])
            ranked_source_indices = data.get('ranked_source_indices', list(range(len(all_sources))))

            # Pad confidence_vector if shorter than num_terms
            while len(confidence_vector) < num_terms:
                confidence_vector.append(0.0)

            # FIX: Reorder all_sources based on ranking, returning actual sources (not indices)
            verified_sources = []
            seen_indices = set()
            for idx in ranked_source_indices:
                if 0 <= idx < len(all_sources) and idx not in seen_indices:
                    verified_sources.append(all_sources[idx])
                    seen_indices.add(idx)
            # Add any sources not included in ranking
            for idx, source in enumerate(all_sources):
                if idx not in seen_indices:
                    verified_sources.append(source)

            # Determine which terms need fresh search (confidence < 0.8)
            terms_to_search = []
            for i, term in enumerate(search_terms_list):
                conf = confidence_vector[i] if i < len(confidence_vector) else 0.0
                if conf < 0.8:
                    # Use refined term if provided, else original
                    refined = refined_terms[i] if i < len(refined_terms) and refined_terms[i] else term
                    terms_to_search.append(refined)

            low_conf_count = len(terms_to_search)
            overall = sum(confidence_vector) / len(confidence_vector) if confidence_vector else 0.0

            logger.debug(
                f"[MEMORY] Verification: overall={overall:.2f}, "
                f"low_conf={low_conf_count}/{num_terms}, "
                f"sources={len(verified_sources)}"
            )
            logger.debug(f"[MEMORY] conf_vector={confidence_vector}, terms_to_search={terms_to_search}")

            return verified_sources, cost, terms_to_search, confidence_vector

        except Exception as e:
            logger.error(f"[MEMORY] Verification failed: {e}")
            # Return sources unchanged on error
            return all_sources, 0.0, search_terms_list, [0.0] * num_terms

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
        url_sources: Optional[List[Dict[str, Any]]] = None,
        search_terms: Optional[List[str]] = None
    ) -> str:
        """Build prompt for Gemini source selection with per-term confidence assessment."""
        from datetime import datetime

        url_sources = url_sources or []
        search_terms = search_terms or []
        num_terms = len(search_terms)

        # Get today's date
        today = datetime.now().strftime("%Y-%m-%d")

        # Build search terms section
        search_terms_section = ""
        if search_terms:
            numbered_terms = [f'{i}. "{term}"' for i, term in enumerate(search_terms)]
            search_terms_section = f"""**Search Terms ({num_terms} total, indexed 0-{num_terms-1}):**
{chr(10).join(numbered_terms)}

"""

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

{search_terms_section}{url_section}**Past Queries ({len(filtered_queries)} candidates):**

{chr(10).join(formatted_queries)}

**Task:**
1. Select up to {max_select} most relevant sources that would help answer the current query
2. Assess confidence **per search term** - how well do selected sources cover each search term?
{url_instruction}
**Selection Criteria:**
- **Relevance**: Does the source contain information directly relevant to the query?
- **Completeness**: Do the sources together provide a comprehensive answer?
- **Accuracy**: Are the sources from reliable, authoritative sources?
- **Recency** (when applicable): For time-sensitive queries (e.g., "latest", "new", "current", specific years), prioritize recent sources
- **Diversity**: Avoid redundant sources covering the same information

**Per-Term Confidence Guidelines:**
Ask yourself: "Could I write a complete answer to '[search term]' using ONLY these sources?"
- **0.9-1.0**: Yes, sources contain enough information to fully answer this search term
- **0.7-0.9**: Mostly yes, could write a good answer with minor gaps
- **0.5-0.7**: Partially, could write a partial answer but missing key information
- **0.3-0.5**: Barely, sources only tangentially help with this search term
- **0.0-0.3**: No, cannot write a meaningful answer using these sources

Return JSON:
{{
  "selected_sources": [
    {{"query_index": -1, "source_index": 0}},
    {{"query_index": 0, "source_index": 2}},
    ...
  ],
  "confidence_vector": [0.85, 0.45, 0.92],
  "reasoning": "Brief explanation"
}}

**confidence_vector must have exactly {num_terms} values, one per search term in order.**
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
                "_query_time": source.get('_query_time'),  # When this memory was stored
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

    def _get_relative_time(self, timestamp: str) -> str:
        """Convert timestamp to human-readable relative time (e.g., '2 days ago')."""
        if not timestamp:
            return "unknown"
        try:
            query_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = now - query_time

            seconds = delta.total_seconds()
            minutes = seconds / 60
            hours = minutes / 60
            days = delta.days

            if seconds < 60:
                return "just now"
            elif minutes < 60:
                m = int(minutes)
                return f"{m} minute{'s' if m != 1 else ''} ago"
            elif hours < 24:
                h = int(hours)
                return f"{h} hour{'s' if h != 1 else ''} ago"
            elif days == 1:
                return "1 day ago"
            elif days < 7:
                return f"{days} days ago"
            elif days < 14:
                return "1 week ago"
            elif days < 30:
                w = days // 7
                return f"{w} weeks ago"
            elif days < 60:
                return "1 month ago"
            elif days < 365:
                m = days // 30
                return f"{m} months ago"
            else:
                y = days // 365
                return f"{y} year{'s' if y != 1 else ''} ago"
        except:
            return "unknown"

    def _extract_cost_from_response(self, response: Dict[str, Any]) -> float:
        """Extract cost from AI client response (same method as the_clone.py)."""
        try:
            enhanced = response.get('enhanced_data', {})
            costs = enhanced.get('costs', {}).get('actual', {})
            cost = costs.get('total_cost', 0.0)
            return cost
        except:
            return 0.0

    def _empty_recall_result(self, search_terms: List[str] = None) -> Dict[str, Any]:
        """Return empty recall result."""
        search_terms = search_terms or []
        return {
            'memories': [],
            'confidence': 0.0,
            'confidence_vector': [0.0] * len(search_terms),
            'should_search': True,
            'recommended_searches': search_terms[:],  # Search all terms
            'search_term_confidence': {term: 0.0 for term in search_terms},
            'recall_metadata': {
                'total_queries': len(self._memory['queries']) if self._memory else 0,
                'filtered_queries': 0,
                'sources_selected': 0,
                'url_sources_count': 0,
                'recall_cost': 0.0,
                'recall_time_ms': 0.0,
                'verification_run': False
            }
        }

    # === URL-BASED RECALL ===

    def recall_by_urls(
        self,
        urls: List[str],
        required_keywords: List[str] = None
    ) -> Dict[str, Any]:
        """
        Look up sources by exact URL match in memory with keyword validation.

        This is used when the user's query contains URLs that we've
        previously searched and stored in memory. Returns ALL snippets
        for each URL (not just the first), with keyword validation to
        determine if stored content is sufficient or needs live fetch.

        Args:
            urls: List of URLs to look up
            required_keywords: Optional list of keyword groups for validation.
                Each group can have variants separated by '|' (OR logic).
                ALL groups must match (AND logic between groups).
                If provided and content doesn't match, URL goes to needs_fetch.

        Returns:
            Dict with:
            - 'found': List of sources that pass keyword validation (or no keywords specified)
            - 'not_found': List of URLs not in memory at all
            - 'needs_fetch': List of URLs found but failed keyword validation (should fetch fresh)
            - 'all_snippets': Dict mapping URL -> list of all snippets (for debugging/extraction)
        """
        result = {
            'found': [],
            'not_found': [],
            'needs_fetch': [],
            'all_snippets': {}
        }

        if self._memory is None:
            result['not_found'] = list(urls) if urls else []
            return result

        if not urls:
            return result

        by_url_index = self._memory['indexes'].get('by_url', {})
        queries = self._memory['queries']
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
                result['not_found'].append(target_url)
                continue

            # Collect ALL snippets for this URL from ALL queries
            url_snippets = []
            seen_snippet_hashes = set()

            for query_id in query_ids:
                query_data = queries.get(query_id)
                if not query_data:
                    continue

                # Find ALL results with this URL in the query
                for idx, res in enumerate(query_data.get('results', [])):
                    result_url = res.get('url', '')

                    # Match by URL (exact or base URL match)
                    if result_url == target_url or result_url.rstrip('/') == normalized_url:
                        snippet_text = res.get('snippet', '')

                        # Dedupe by snippet content hash
                        snippet_hash = hashlib.md5(snippet_text.encode()).hexdigest()[:16]
                        if snippet_hash in seen_snippet_hashes:
                            continue
                        seen_snippet_hashes.add(snippet_hash)

                        # Check if this is full content (from store_url_content)
                        is_full_content = res.get('_is_full_content', False)
                        source_type = res.get('_source_type', 'search_result')

                        # Build source with metadata
                        source = {
                            "url": res.get('url'),
                            "title": res.get('title'),
                            "snippet": snippet_text,
                            "date": res.get('date'),
                            "last_updated": res.get('last_updated'),

                            # Memory-specific metadata
                            "_from_memory": True,
                            "_from_url_lookup": True,
                            "_original_query": query_data.get('search_term'),
                            "_query_date": query_data.get('query_time'),
                            "_memory_age_days": self._calculate_age_days(query_data.get('query_time')),
                            "_original_rank": idx,
                            "_memory_relevance": 10.0,
                            "_freshness_indicator": self._get_freshness_indicator(query_data.get('query_time')),
                            "_is_full_content": is_full_content,
                            "_source_type": source_type,
                            "_snippet_length": len(snippet_text)
                        }

                        # Add extraction metadata if present
                        if '_extraction_metadata' in res:
                            source['_extraction_metadata'] = res['_extraction_metadata']

                        url_snippets.append(source)

            if not url_snippets:
                logger.debug(f"[MEMORY] URL in index but no snippets found: {target_url}")
                result['not_found'].append(target_url)
                continue

            found_target_urls.add(target_url)
            result['all_snippets'][target_url] = url_snippets

            # Sort snippets: full_content first (table extractions), then by length (longer = richer)
            url_snippets.sort(
                key=lambda s: (
                    not s.get('_is_full_content', False),  # Full content first (False sorts before True)
                    -s.get('_snippet_length', 0)  # Longer snippets first
                )
            )

            # Keyword validation: check if ANY snippet passes all required keywords
            if required_keywords:
                passes_validation = False
                passing_snippets = []

                for source in url_snippets:
                    if self._snippet_matches_keywords(source.get('snippet', ''), source.get('title', ''), required_keywords):
                        passes_validation = True
                        passing_snippets.append(source)

                if passes_validation:
                    # Use ALL passing snippets (for extraction to pull from)
                    result['found'].extend(passing_snippets)
                    logger.debug(
                        f"[MEMORY] URL passes keyword validation: {target_url} "
                        f"({len(passing_snippets)}/{len(url_snippets)} snippets match)"
                    )
                else:
                    # No snippets pass - need to fetch fresh content
                    result['needs_fetch'].append(target_url)
                    logger.debug(
                        f"[MEMORY] URL found but FAILS keyword validation: {target_url} "
                        f"(keywords: {required_keywords}, snippets checked: {len(url_snippets)})"
                    )
            else:
                # No keyword validation - use all snippets (prefer full content)
                result['found'].extend(url_snippets)
                logger.debug(
                    f"[MEMORY] Found URL in memory: {target_url} "
                    f"({len(url_snippets)} snippets, full_content: {any(s.get('_is_full_content') for s in url_snippets)})"
                )

        logger.debug(
            f"[MEMORY] URL lookup: {len(urls)} URLs -> "
            f"{len(result['found'])} found (passing), "
            f"{len(result['needs_fetch'])} needs_fetch (failed keywords), "
            f"{len(result['not_found'])} not_found"
        )
        return result

    def _snippet_matches_keywords(
        self,
        snippet: str,
        title: str,
        required_keywords: List[str]
    ) -> bool:
        """
        Check if snippet/title contains all required keyword groups.

        Args:
            snippet: The snippet text to check
            title: The title to check
            required_keywords: List of keyword groups. Each group can have
                variants separated by '|'. ALL groups must match.

        Returns:
            True if all keyword groups are found, False otherwise
        """
        if not required_keywords:
            return True

        searchable = (snippet + ' ' + title).lower()

        for keyword_group in required_keywords:
            # Split group into variants (OR logic within group)
            variants = [v.strip().lower() for v in keyword_group.split('|')]

            # Check if ANY variant is found
            if not any(variant in searchable for variant in variants):
                return False  # This required group not found

        return True  # All groups matched

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
                logger.debug(f"[MEMORY] Fetching URL content via Jina: {url}")
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
                    logger.debug(f"[MEMORY] Fetched URL: {url} ({len(markdown)} chars, title: {title[:50]})")
                else:
                    logger.warning(f"[MEMORY] Failed to fetch URL: {url} - {jina_result.get('error', 'Unknown error')}")

            except Exception as e:
                logger.error(f"[MEMORY] Error fetching URL {url}: {str(e)}")

        logger.debug(f"[MEMORY] Live URL fetch: {len(urls)} URLs -> {len(fetched_sources)} fetched")
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
