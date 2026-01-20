#!/usr/bin/env python3
"""
In-Process Memory Cache for Parallel Agent Access.

Enables massive parallelization within a single Lambda:
- Single S3 read at batch start (or on-demand if needed)
- All agents share same RAM (zero latency)
- Single S3 write at batch end

Architecture:
- Module-level singleton (_MEMORY_CACHE)
- Thread-safe access via locks
- Automatic fallback: loads from S3 if not cached
- Dirty tracking: only flush sessions with new data
"""

import logging
from threading import Lock
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Module-level singleton - shared across all async tasks in this Lambda
_MEMORY_CACHE: Dict[str, Any] = {}  # {session_id: SearchMemory}
_CACHE_LOCK = Lock()
_DIRTY_SESSIONS: set = set()  # Track which sessions have pending writes


class MemoryCache:
    """
    In-process memory cache for parallel agent access.

    Usage:
    ```python
    # Get shared memory (loads from S3 if needed)
    memory = MemoryCache.get(session_id, email, s3_manager, ai_client)

    # Store search (RAM only, no S3)
    MemoryCache.store_search(session_id, search_term, results, params)

    # At batch end: flush to S3
    await MemoryCache.flush(session_id)
    ```
    """

    @classmethod
    def get(
        cls,
        session_id: str,
        email: str,
        s3_manager,
        ai_client=None
    ):
        """
        Get or load shared memory for this session.

        Backup check: If not in cache, loads from S3 automatically.
        This handles cases where memory was copied but not loaded,
        or where an agent needs memory that wasn't pre-loaded.

        Args:
            session_id: Session identifier
            email: User email
            s3_manager: UnifiedS3Manager instance
            ai_client: AIAPIClient instance (optional)

        Returns:
            SearchMemory instance (shared across all agents)
        """
        with _CACHE_LOCK:
            if session_id not in _MEMORY_CACHE:
                # Import here to avoid circular dependency
                from the_clone.search_memory import SearchMemory

                logger.info(f"[MEMORY_CACHE] Loading memory for session {session_id}")
                memory = SearchMemory(session_id, email, s3_manager, ai_client)

                # Synchronous load from S3 (backup check)
                try:
                    memory._load_from_s3_sync()
                    query_count = len(memory._memory.get('queries', {}))
                    logger.info(f"[MEMORY_CACHE] Loaded {query_count} queries from S3")
                except FileNotFoundError:
                    memory._initialize_empty_memory()
                    logger.info(f"[MEMORY_CACHE] No existing memory, initialized empty")
                except Exception as e:
                    logger.warning(f"[MEMORY_CACHE] Failed to load memory, initializing empty: {e}")
                    memory._initialize_empty_memory()

                _MEMORY_CACHE[session_id] = memory

            return _MEMORY_CACHE[session_id]

    @classmethod
    def load_from_copy(
        cls,
        target_session_id: str,
        source_session_id: str,
        email: str,
        s3_manager,
        ai_client=None
    ):
        """
        Load memory from a copied config into RAM cache.

        Call this AFTER copying agent_memory.json from source to target session.
        Ensures the copied memory is immediately available to all agents.

        Args:
            target_session_id: New session that received the copy
            source_session_id: Original session (for logging)
            email: User email
            s3_manager: UnifiedS3Manager instance
            ai_client: AIAPIClient instance (optional)

        Returns:
            SearchMemory instance loaded from copied file
        """
        with _CACHE_LOCK:
            logger.info(f"[MEMORY_CACHE] Loading copied memory: {source_session_id} -> {target_session_id}")

            # Remove any stale cache entry
            if target_session_id in _MEMORY_CACHE:
                logger.debug(f"[MEMORY_CACHE] Replacing stale cache entry for {target_session_id}")
                del _MEMORY_CACHE[target_session_id]

            # Import here to avoid circular dependency
            from the_clone.search_memory import SearchMemory

            # Load the copied memory file
            memory = SearchMemory(target_session_id, email, s3_manager, ai_client)
            try:
                memory._load_from_s3_sync()
                query_count = len(memory._memory.get('queries', {}))
                logger.info(f"[MEMORY_CACHE] Loaded {query_count} queries from copied memory")
            except FileNotFoundError:
                memory._initialize_empty_memory()
                logger.warning(f"[MEMORY_CACHE] Copied memory file not found, initializing empty")
            except Exception as e:
                logger.warning(f"[MEMORY_CACHE] Failed to load copied memory, initializing empty: {e}")
                memory._initialize_empty_memory()

            _MEMORY_CACHE[target_session_id] = memory
            return memory

    @classmethod
    def store_search(
        cls,
        session_id: str,
        search_term: str,
        results: Dict[str, Any],
        parameters: Dict[str, Any],
        strategy: str = "unknown"
    ) -> str:
        """
        Store search in RAM cache. NO S3 WRITE.

        Args:
            session_id: Session identifier
            search_term: Search term used
            results: Perplexity API response
            parameters: Search parameters
            strategy: Strategy name

        Returns:
            query_id: Unique identifier for stored query

        Raises:
            ValueError: If session not in cache (must call get() first)
        """
        with _CACHE_LOCK:
            if session_id not in _MEMORY_CACHE:
                raise ValueError(
                    f"Session {session_id} not in cache. Call MemoryCache.get() first."
                )

            memory = _MEMORY_CACHE[session_id]
            query_id = memory._store_search_no_backup(search_term, results, parameters, strategy)
            _DIRTY_SESSIONS.add(session_id)

            logger.debug(f"[MEMORY_CACHE] Stored search '{search_term[:50]}...' (RAM only, no S3)")
            return query_id

    @classmethod
    def store_url_content(
        cls,
        session_id: str,
        url: str,
        content: str,
        title: str = None,
        source_type: str = "table_extraction",
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Store URL content in RAM cache. NO S3 WRITE.

        Args:
            session_id: Session identifier
            url: Source URL
            content: Full content (markdown, text, etc.)
            title: Display title
            source_type: Content type identifier
            metadata: Optional extraction metadata

        Returns:
            query_id: Unique identifier for stored content

        Raises:
            ValueError: If session not in cache (must call get() first)
        """
        with _CACHE_LOCK:
            if session_id not in _MEMORY_CACHE:
                raise ValueError(
                    f"Session {session_id} not in cache. Call MemoryCache.get() first."
                )

            memory = _MEMORY_CACHE[session_id]
            query_id = memory._store_url_content_no_backup(url, content, title, source_type, metadata)
            _DIRTY_SESSIONS.add(session_id)

            logger.debug(f"[MEMORY_CACHE] Stored URL content '{url[:50]}...' (RAM only, no S3)")
            return query_id

    @classmethod
    async def flush(cls, session_id: str):
        """
        Write session memory to S3. Call at END of batch.

        Only writes if session is dirty (has new data).

        Args:
            session_id: Session identifier to flush
        """
        # Get memory reference and mark as flushing (prevents concurrent modifications)
        with _CACHE_LOCK:
            if session_id not in _MEMORY_CACHE:
                logger.debug(f"[MEMORY_CACHE] Session {session_id} not in cache, nothing to flush")
                return

            if session_id not in _DIRTY_SESSIONS:
                logger.debug(f"[MEMORY_CACHE] Session {session_id} not dirty, skipping flush")
                return

            memory = _MEMORY_CACHE[session_id]
            query_count = len(memory._memory.get('queries', {}))
            url_count = len(memory._memory.get('indexes', {}).get('by_url', {}))

            # Mark as clean BEFORE write to prevent double-flush
            # If write fails, we'll log error but won't retry
            _DIRTY_SESSIONS.discard(session_id)

        # Lock is held throughout backup to prevent race conditions during serialization
        # Log for MEMORY_URL_STORAGE_ISSUE debugging
        logger.info(f"[MEMORY_CACHE] Flushing {query_count} queries, {url_count} unique URLs to S3 for session {session_id}")
        start_time = __import__('time').time()

        try:
            await memory.backup()
            elapsed = __import__('time').time() - start_time
            logger.info(f"[MEMORY_CACHE] Flush complete for session {session_id} ({elapsed:.2f}s)")

        except Exception as e:
            logger.error(f"[MEMORY_CACHE] Flush failed for session {session_id}: {e}")
            # Re-mark as dirty so it can be retried
            with _CACHE_LOCK:
                _DIRTY_SESSIONS.add(session_id)
            raise

    @classmethod
    def flush_sync(cls, session_id: str):
        """
        Write session memory to S3 synchronously. For use in sync contexts.

        Only writes if session is dirty (has new data).

        Args:
            session_id: Session identifier to flush
        """
        # Get memory reference and mark as flushing
        with _CACHE_LOCK:
            if session_id not in _MEMORY_CACHE:
                logger.debug(f"[MEMORY_CACHE] Session {session_id} not in cache, nothing to flush")
                return

            if session_id not in _DIRTY_SESSIONS:
                logger.debug(f"[MEMORY_CACHE] Session {session_id} not dirty, skipping flush")
                return

            memory = _MEMORY_CACHE[session_id]
            query_count = len(memory._memory.get('queries', {}))
            sources_count = len(memory._memory.get('sources', {}))
            total_citations = sum(len(s.get('citations', [])) for s in memory._memory.get('sources', {}).values())

            # Mark as clean BEFORE write to prevent double-flush
            _DIRTY_SESSIONS.discard(session_id)

        logger.info(f"[MEMORY_CACHE] Flushing {query_count} queries, {sources_count} sources ({total_citations} citations) to S3 for session {session_id} (sync)")
        start_time = __import__('time').time()

        try:
            # Synchronous backup
            memory._backup_sync()
            elapsed = __import__('time').time() - start_time
            logger.info(f"[MEMORY_CACHE] Flush complete for session {session_id} ({elapsed:.2f}s)")

        except Exception as e:
            logger.error(f"[MEMORY_CACHE] Flush failed for session {session_id}: {e}")
            # Re-mark as dirty so it can be retried
            with _CACHE_LOCK:
                _DIRTY_SESSIONS.add(session_id)
            raise

    @classmethod
    async def flush_all(cls):
        """
        Flush ALL dirty sessions. Call at end of Lambda.

        Writes all dirty sessions in sequence (to avoid S3 rate limits).
        """
        with _CACHE_LOCK:
            dirty = list(_DIRTY_SESSIONS)

        if not dirty:
            logger.debug("[MEMORY_CACHE] No dirty sessions to flush")
            return

        logger.info(f"[MEMORY_CACHE] Flushing {len(dirty)} dirty sessions")

        for session_id in dirty:
            await cls.flush(session_id)

        logger.info(f"[MEMORY_CACHE] All sessions flushed")

    @classmethod
    def is_cached(cls, session_id: str) -> bool:
        """Check if session is in cache."""
        with _CACHE_LOCK:
            return session_id in _MEMORY_CACHE

    @classmethod
    def is_dirty(cls, session_id: str) -> bool:
        """Check if session has pending writes."""
        with _CACHE_LOCK:
            return session_id in _DIRTY_SESSIONS

    @classmethod
    def get_stats(cls, session_id: str) -> Dict[str, Any]:
        """
        Get cache stats for debugging.

        Returns:
            Dict with cache status, query count, etc.
        """
        with _CACHE_LOCK:
            if session_id not in _MEMORY_CACHE:
                return {
                    "cached": False,
                    "dirty": False,
                    "queries": 0,
                    "unique_urls": 0
                }

            memory = _MEMORY_CACHE[session_id]
            return {
                "cached": True,
                "dirty": session_id in _DIRTY_SESSIONS,
                "queries": len(memory._memory.get('queries', {})),
                "unique_urls": len(memory._memory.get('indexes', {}).get('by_url', {}))
            }

    @classmethod
    def clear(cls, session_id: str = None):
        """
        Clear cache (for testing or Lambda cleanup).

        Args:
            session_id: Specific session to clear, or None to clear all
        """
        with _CACHE_LOCK:
            if session_id:
                _MEMORY_CACHE.pop(session_id, None)
                _DIRTY_SESSIONS.discard(session_id)
                logger.debug(f"[MEMORY_CACHE] Cleared cache for session {session_id}")
            else:
                count = len(_MEMORY_CACHE)
                _MEMORY_CACHE.clear()
                _DIRTY_SESSIONS.clear()
                logger.debug(f"[MEMORY_CACHE] Cleared all cache ({count} sessions)")

    @classmethod
    def get_all_cached_sessions(cls) -> list:
        """Get list of all cached session IDs (for debugging)."""
        with _CACHE_LOCK:
            return list(_MEMORY_CACHE.keys())

    @classmethod
    def get_all_dirty_sessions(cls) -> list:
        """Get list of all dirty session IDs (for debugging)."""
        with _CACHE_LOCK:
            return list(_DIRTY_SESSIONS)

    # === CITATION-AWARE MEMORY METHODS ===

    @classmethod
    def recall_citations(
        cls,
        session_id: str,
        url: str = None,
        required_keywords: list = None
    ) -> Dict[str, Any]:
        """
        Recall pre-extracted citations from memory.

        Args:
            session_id: Session identifier
            url: Optional URL to look up directly
            required_keywords: Mandatory keywords that must match

        Returns:
            Dict with found, needs_extraction, citations/sources

        Raises:
            ValueError: If session not in cache (must call get() first)
        """
        with _CACHE_LOCK:
            if session_id not in _MEMORY_CACHE:
                raise ValueError(
                    f"Session {session_id} not in cache. Call MemoryCache.get() first."
                )

            memory = _MEMORY_CACHE[session_id]
            return memory.recall_citations(url=url, required_keywords=required_keywords)

    @classmethod
    def store_citations(
        cls,
        session_id: str,
        url: str,
        content: str,
        title: str,
        search_term: str,
        citations: list,
        source_type: str = "search"
    ):
        """
        Store citations in RAM cache. NO S3 WRITE.

        Citations accumulate - new extractions add to existing.

        Args:
            session_id: Session identifier
            url: Source URL
            content: Full source content
            title: Source title
            search_term: Original query for recall matching
            citations: List of citations with hit_keywords computed
            source_type: Origin type (search, url_fetch, table_extraction)

        Raises:
            ValueError: If session not in cache (must call get() first)
        """
        with _CACHE_LOCK:
            if session_id not in _MEMORY_CACHE:
                raise ValueError(
                    f"Session {session_id} not in cache. Call MemoryCache.get() first."
                )

            memory = _MEMORY_CACHE[session_id]
            memory._store_citations_no_backup(
                url=url,
                content=content,
                title=title,
                search_term=search_term,
                citations=citations,
                source_type=source_type
            )
            _DIRTY_SESSIONS.add(session_id)

            logger.info(
                f"[MEMORY_CACHE] Stored {len(citations)} citations for "
                f"'{url[:50]}...' (RAM only, no S3)"
            )

    @classmethod
    def get_citation_stats(cls, session_id: str) -> Dict[str, Any]:
        """
        Get citation statistics for a session.

        Args:
            session_id: Session identifier

        Returns:
            Dict with citation stats or empty dict if not cached
        """
        with _CACHE_LOCK:
            if session_id not in _MEMORY_CACHE:
                return {
                    "cached": False,
                    "total_sources": 0,
                    "total_citations": 0
                }

            memory = _MEMORY_CACHE[session_id]
            stats = memory.get_citation_stats()
            stats["cached"] = True
            return stats
