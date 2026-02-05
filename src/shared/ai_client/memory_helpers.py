"""Helper functions for storing AI client results to memory."""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def serialize_validation_response(response_data: Dict, max_length: int = 200) -> str:
    """
    Serialize validation response into a compact search term.

    Args:
        response_data: Parsed validation response (field values, etc.)
        max_length: Maximum length for the search term

    Returns:
        Compact string like "[validation] Apple Inc: CEO=Tim Cook, Founded=1976"
    """
    try:
        parts = []

        # Extract field/value pairs from response
        for key, value in response_data.items():
            # Skip metadata fields
            if key.startswith('_') or key in ('confidence', 'reasoning', 'sources', 'citations'):
                continue
            # Include strings, numbers (including 0), and booleans
            if isinstance(value, (str, int, float, bool)):
                # Skip empty strings but keep 0, False, etc.
                if isinstance(value, str) and not value.strip():
                    continue
                # Truncate long values
                val_str = str(value)[:50]
                parts.append(f"{key}={val_str}")

        if not parts:
            return "[validation] Query unavailable - serialized response"

        # Join and truncate
        content = ", ".join(parts)
        if len(content) > max_length - 15:  # Leave room for prefix
            content = content[:max_length - 18] + "..."

        return f"[validation] {content}"

    except Exception:
        return "[validation] Query unavailable - serialized response"


def store_perplexity_citations_to_memory(
    session_id: str,
    email: str,
    s3_manager,
    ai_client,
    citations: List[Dict],
    response_data: Dict = None,
    search_term: str = None,
    source_type: str = "validation"
) -> bool:
    """
    Store Perplexity citations to memory for future recall.

    Args:
        session_id: Session identifier
        email: User email
        s3_manager: UnifiedS3Manager instance
        ai_client: AIAPIClient instance (for memory initialization)
        citations: List of citation dicts from Perplexity response
        response_data: Parsed validation response (used to generate search_term if not provided)
        search_term: Override search term (optional - generated from response_data if not provided)
        source_type: Strategy name for tracking

    Returns:
        True if stored successfully, False otherwise
    """
    if not session_id or not email or not s3_manager or not citations:
        return False

    try:
        from the_clone.search_memory_cache import MemoryCache

        # Ensure memory is loaded for this session
        MemoryCache.get(session_id, email, s3_manager, ai_client)

        # Generate search term from response if not provided
        if not search_term:
            if response_data:
                search_term = serialize_validation_response(response_data)
            else:
                search_term = "[validation] Query unavailable - serialized response"

        # Convert citations to memory format
        # Citations have: url, title, cited_text, date, last_updated, p
        # Memory expects: url, title, snippet, date, p
        results = {
            "results": [
                {
                    "url": c.get('url', ''),
                    "title": c.get('title', ''),
                    "snippet": c.get('cited_text', ''),
                    "date": c.get('date', ''),
                    "last_updated": c.get('last_updated', ''),
                    "p": c.get('p', '')
                }
                for c in citations if c.get('url')
            ]
        }

        if not results["results"]:
            return False

        # Store to memory (RAM only, flushed at batch end)
        MemoryCache.store_search(
            session_id=session_id,
            search_term=search_term,
            results=results,
            parameters={"source": "perplexity_validation", "source_type": source_type},
            strategy=source_type
        )

        logger.debug(f"[MEMORY] Stored {len(results['results'])} citations for: {search_term[:50]}...")
        return True

    except Exception as e:
        logger.debug(f"[MEMORY] Failed to store citations: {e}")
        return False
