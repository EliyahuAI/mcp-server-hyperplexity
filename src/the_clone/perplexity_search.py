#!/usr/bin/env python3
"""
Perplexity Search API - Raw search results without LLM synthesis
Uses the /search endpoint (not /chat/completions)
"""

import asyncio
import aiohttp
import json
import os
import time
import random
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)

# Global semaphore to limit concurrent Perplexity API requests
# Prevents rate limit saturation when multiple clones run in parallel
# 15 concurrent ≈ 3-5 completing/sec, staying under 3 QPS limit
PERPLEXITY_SEARCH_SEMAPHORE = asyncio.Semaphore(15)

# Threshold for high 429 rate alerting (429s per second)
HIGH_429_RATE_THRESHOLD = 0.5


class RateMetrics:
    """Thread-safe rate metrics tracker for calls/sec and 429s/sec."""

    def __init__(self, window_seconds: int = 10):
        self.window_seconds = window_seconds
        self._calls: deque = deque()
        self._rate_limits: deque = deque()
        self._lock = Lock()

    def record_call(self):
        """Record a successful API call."""
        now = time.time()
        with self._lock:
            self._calls.append(now)
            self._cleanup(now)

    def record_rate_limit(self):
        """Record a 429 rate limit response and log if rate is high."""
        now = time.time()
        with self._lock:
            self._rate_limits.append(now)
            self._cleanup(now)
            # Check if 429 rate is high and log at INFO level
            rate_limits_per_sec = len(self._rate_limits) / self.window_seconds
            if rate_limits_per_sec >= HIGH_429_RATE_THRESHOLD:
                calls_per_sec = len(self._calls) / self.window_seconds
                logger.info(f"[PERPLEXITY_HIGH_429] 429s/sec: {rate_limits_per_sec:.2f} (threshold: {HIGH_429_RATE_THRESHOLD}), calls/sec: {calls_per_sec:.2f}")

    def _cleanup(self, now: float):
        """Remove entries older than window."""
        cutoff = now - self.window_seconds
        while self._calls and self._calls[0] < cutoff:
            self._calls.popleft()
        while self._rate_limits and self._rate_limits[0] < cutoff:
            self._rate_limits.popleft()

    def get_rates(self) -> Dict[str, float]:
        """Get current calls/sec and 429s/sec."""
        now = time.time()
        with self._lock:
            self._cleanup(now)
            calls_per_sec = len(self._calls) / self.window_seconds
            rate_limits_per_sec = len(self._rate_limits) / self.window_seconds
        return {
            'calls_per_sec': round(calls_per_sec, 2),
            'rate_limits_per_sec': round(rate_limits_per_sec, 2),
            'window_seconds': self.window_seconds
        }

    def log_rates(self, prefix: str = "[PERPLEXITY_RATE]"):
        """Log current rates."""
        rates = self.get_rates()
        logger.info(f"{prefix} calls/sec: {rates['calls_per_sec']:.2f}, 429s/sec: {rates['rate_limits_per_sec']:.2f}")
        return rates


# Global rate metrics instance
RATE_METRICS = RateMetrics(window_seconds=10)


class PerplexitySearchClient:
    """
    Client for Perplexity Search API with retry logic and rate limiting.

    Rate Limit: 3 requests per second (sustained)
    Pricing: $5 per 1,000 requests (flat, no token costs)

    Features:
    - Global semaphore (15 concurrent) prevents rate limit saturation
    - Jittered exponential backoff prevents convoy effect
    - Fast retries (0.5s base) for quick recovery
    - Rate metrics logging (calls/sec, 429s/sec)
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the search client."""
        if api_key:
            self.api_key = api_key
        else:
            # Try environment variable first, then SSM Parameter Store
            self.api_key = os.environ.get('PERPLEXITY_API_KEY')
            if not self.api_key:
                try:
                    # Import here to avoid circular dependency
                    from shared.ai_client.config import get_perplexity_api_key
                    self.api_key = get_perplexity_api_key()
                except Exception as e:
                    raise ValueError(f"PERPLEXITY_API_KEY not set and failed to load from SSM: {e}")

        self.base_url = "https://api.perplexity.ai"

    async def search(
        self,
        query: Union[str, List[str]],
        max_results: int = 10,
        search_recency_filter: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        max_tokens_per_page: Optional[int] = None,
        max_retries: int = 5,
        base_delay: float = 0.5
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Execute a search query with automatic retry logic.
        Supports single query or multi-query (up to 5 queries per call).

        Uses global semaphore to prevent rate limit saturation.
        Uses jittered exponential backoff to prevent convoy effect.

        Args:
            query: Single search query string OR array of up to 5 queries
            max_results: Maximum number of results to return (default: 10)
            search_recency_filter: Filter by recency - "day", "week", "month", "year", or None
            include_domains: Whitelist of domains to search (prefer over exclude if both given)
            exclude_domains: Blacklist of domains to exclude
            max_tokens_per_page: Control content extraction size (512=faster/shallow, 2048=comprehensive/deep)
            max_retries: Maximum retry attempts for rate limits (default: 5)
            base_delay: Base delay in seconds for exponential backoff (default: 0.5s)

        Returns:
            Single query: Dict with structure {"results": [...]}
            Multi-query: List of dicts, one per query [{"results": [...]}, ...]
        """

        # Build request payload
        payload = {
            "query": query,
            "max_results": max_results
        }

        if search_recency_filter:
            payload["search_recency_filter"] = search_recency_filter

        # Domain filtering - prefer include_domains if both given
        if include_domains:
            payload["search_domain_filter"] = include_domains
        elif exclude_domains:
            payload["search_domain_filter"] = exclude_domains

        if max_tokens_per_page:
            payload["max_tokens_per_page"] = max_tokens_per_page

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        url = f"{self.base_url}/search"

        last_error = None

        # Use global semaphore to limit concurrent requests
        async with PERPLEXITY_SEARCH_SEMAPHORE:
            for attempt in range(max_retries + 1):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                            response_text = await response.text()

                            # Success
                            if response.status == 200:
                                result = json.loads(response_text)
                                RATE_METRICS.record_call()
                                return result

                            # Rate limit hit
                            elif response.status == 429:
                                RATE_METRICS.record_rate_limit()
                                if attempt < max_retries:
                                    # Jittered exponential backoff: base * 2^attempt + random(0, 1)
                                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                                    logger.warning(f"[PERPLEXITY] Rate limit 429, retry {attempt + 1}/{max_retries + 1} in {delay:.1f}s")
                                    # Log rates every few retries
                                    if attempt % 2 == 0:
                                        RATE_METRICS.log_rates()
                                    await asyncio.sleep(delay)
                                    continue
                                else:
                                    RATE_METRICS.log_rates("[PERPLEXITY_EXHAUSTED]")
                                    raise Exception(f"Rate limit exceeded after {max_retries + 1} attempts: {response_text}")

                            # Server errors
                            elif response.status in [502, 503, 529]:
                                if attempt < max_retries:
                                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                                    logger.warning(f"[PERPLEXITY] Server error {response.status}, retry {attempt + 1}/{max_retries + 1} in {delay:.1f}s")
                                    await asyncio.sleep(delay)
                                    continue
                                else:
                                    raise Exception(f"Server error ({response.status}) after {max_retries + 1} attempts")

                            # Other errors
                            else:
                                raise Exception(f"API error ({response.status}): {response_text}")

                except aiohttp.ClientError as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                        logger.warning(f"[PERPLEXITY] Network error: {str(e)}, retry {attempt + 1}/{max_retries + 1} in {delay:.1f}s")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise Exception(f"Network error after {max_retries + 1} attempts: {str(e)}")

            if last_error:
                raise last_error
            raise Exception("All retry attempts failed")

    async def batch_search(
        self,
        queries: List[str],
        max_results: int = 10,
        search_recency_filter: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        max_tokens_per_page: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple searches with automatic rate limiting.

        NOTE: Perplexity documents a multi-query feature (up to 5 queries per call)
        but it has a critical bug - only returns results for the first query.
        Therefore, we make separate API calls for each query (confirmed working).

        Uses global semaphore (15 concurrent) to prevent rate limit saturation.

        Args:
            queries: List of search queries
            max_results: Max results per query
            search_recency_filter: Recency filter
            include_domains: Whitelist of domains
            exclude_domains: Blacklist of domains
            max_tokens_per_page: Control content extraction size

        Returns:
            List of search result dicts, one per query
        """
        start_time = time.time()
        logger.info(f"[PERPLEXITY] Starting batch of {len(queries)} searches (semaphore limit: 15)")

        tasks = []
        for query in queries:
            task = self.search(query, max_results, search_recency_filter, include_domains, exclude_domains, max_tokens_per_page)
            tasks.append(task)

        # Run with semaphore limiting concurrent requests
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - success_count

        logger.info(f"[PERPLEXITY] Batch complete: {success_count}/{len(queries)} success, {error_count} errors in {elapsed:.1f}s")
        RATE_METRICS.log_rates("[PERPLEXITY_BATCH_END]")

        return results


def get_semaphore_status() -> Dict[str, Any]:
    """Get current semaphore and rate metrics status for debugging."""
    # Note: asyncio.Semaphore doesn't expose current count directly
    # We can only check if it's locked
    return {
        'semaphore_limit': 15,
        'rate_metrics': RATE_METRICS.get_rates()
    }


def get_rate_metrics() -> Dict[str, float]:
    """Get current rate metrics (calls/sec, 429s/sec)."""
    return RATE_METRICS.get_rates()


async def test_single_search():
    """Test a single search query."""

    print("\n" + "="*80)
    print("TEST 1: Single Search Query")
    print("="*80)

    client = PerplexitySearchClient()

    query = "latest AI developments 2024"
    print(f"\n[INFO] Query: '{query}'")
    print(f"[INFO] Max results: 10")
    print(f"[INFO] Recency filter: week")

    start_time = time.time()

    try:
        result = await client.search(
            query=query,
            max_results=10,
            search_recency_filter="week"
        )

        elapsed = time.time() - start_time

        print(f"\n[SUCCESS] Search completed in {elapsed:.2f}s")

        results = result.get('results', [])
        print(f"[INFO] Found {len(results)} results")

        print("\n" + "-"*80)
        print("Results:")
        print("-"*80)

        for i, item in enumerate(results[:5], 1):  # Show first 5
            print(f"\n{i}. {item.get('title', 'No title')}")
            print(f"   URL: {item.get('url', 'N/A')}")
            print(f"   Snippet: {item.get('snippet', 'N/A')[:150]}...")
            if 'date' in item:
                print(f"   Date: {item.get('date')}")

        # Save full result
        output_file = "/tmp/perplexity_search_single.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n[INFO] Full results saved to: {output_file}")

    except Exception as e:
        print(f"\n[ERROR] Search failed: {str(e)}")
        raise

    print("\n" + "="*80 + "\n")


async def test_batch_search():
    """Test multiple concurrent searches with rate limiting."""

    print("\n" + "="*80)
    print("TEST 2: Batch Search (Rate Limit Test)")
    print("="*80)

    client = PerplexitySearchClient()

    queries = [
        "DeepSeek V3 capabilities",
        "Claude 4 Opus features",
        "OpenAI GPT-5 news",
        "Anthropic constitutional AI",
        "Google Gemini 2.0 updates"
    ]

    print(f"\n[INFO] Running {len(queries)} searches concurrently")
    print("[INFO] Rate limit: 3 QPS (requests will be throttled)")

    for i, q in enumerate(queries, 1):
        print(f"  {i}. {q}")

    start_time = time.time()

    try:
        results = await client.batch_search(
            queries=queries,
            max_results=5,
            search_recency_filter="month"
        )

        elapsed = time.time() - start_time

        print(f"\n[SUCCESS] All searches completed in {elapsed:.2f}s")
        print(f"[INFO] Average: {elapsed/len(queries):.2f}s per query")
        print(f"[INFO] Effective QPS: {len(queries)/elapsed:.2f}")

        # Count successes
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = sum(1 for r in results if isinstance(r, Exception))

        print(f"\n[RESULTS] Success: {success_count}/{len(queries)}, Errors: {error_count}/{len(queries)}")

        # Show sample results
        print("\n" + "-"*80)
        print("Sample Results:")
        print("-"*80)

        for i, (query, result) in enumerate(zip(queries, results), 1):
            if isinstance(result, Exception):
                print(f"\n{i}. '{query}' - [ERROR] {str(result)[:100]}")
            else:
                items = result.get('results', [])
                print(f"\n{i}. '{query}' - Found {len(items)} results")
                if items:
                    first = items[0]
                    print(f"   Top result: {first.get('title', 'N/A')}")
                    print(f"   URL: {first.get('url', 'N/A')}")

        # Save results
        output_file = "/tmp/perplexity_search_batch.json"
        with open(output_file, 'w') as f:
            # Convert exceptions to strings for JSON serialization
            serializable_results = []
            for r in results:
                if isinstance(r, Exception):
                    serializable_results.append({"error": str(r)})
                else:
                    serializable_results.append(r)
            json.dump(serializable_results, f, indent=2)
        print(f"\n[INFO] Full results saved to: {output_file}")

    except Exception as e:
        print(f"\n[ERROR] Batch search failed: {str(e)}")
        raise

    print("\n" + "="*80 + "\n")


async def test_recency_filters():
    """Test different recency filter options."""

    print("\n" + "="*80)
    print("TEST 3: Recency Filters")
    print("="*80)

    client = PerplexitySearchClient()

    query = "AI breakthrough"
    filters = ["day", "week", "month", None]

    print(f"\n[INFO] Query: '{query}'")
    print(f"[INFO] Testing filters: {filters}")

    for filter_value in filters:
        filter_name = filter_value or "none"
        print(f"\n[INFO] Testing filter: {filter_name}")

        try:
            result = await client.search(
                query=query,
                max_results=3,
                search_recency_filter=filter_value
            )

            results = result.get('results', [])
            print(f"[SUCCESS] Filter '{filter_name}': {len(results)} results")

            if results:
                first = results[0]
                print(f"  Top: {first.get('title', 'N/A')[:60]}...")
                if 'date' in first:
                    print(f"  Date: {first.get('date')}")

        except Exception as e:
            print(f"[ERROR] Filter '{filter_name}' failed: {str(e)}")

    print("\n" + "="*80 + "\n")


async def test_retry_logic():
    """Test retry logic by making rapid requests."""

    print("\n" + "="*80)
    print("TEST 4: Retry Logic (Rapid Requests)")
    print("="*80)

    client = PerplexitySearchClient()

    print("\n[INFO] Making 10 rapid requests to test retry logic")
    print("[INFO] Rate limiter should throttle to ~3 QPS")

    queries = [f"AI topic {i}" for i in range(10)]

    start_time = time.time()

    try:
        results = await client.batch_search(queries, max_results=2)

        elapsed = time.time() - start_time
        actual_qps = len(queries) / elapsed

        print(f"\n[SUCCESS] Completed {len(queries)} requests in {elapsed:.2f}s")
        print(f"[INFO] Actual QPS: {actual_qps:.2f} (target: ~3.0)")
        print(f"[INFO] Rate limiting is {'WORKING' if actual_qps <= 3.5 else 'NOT EFFECTIVE'}")

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        print(f"[INFO] Successful requests: {success_count}/{len(queries)}")

    except Exception as e:
        print(f"\n[ERROR] Retry test failed: {str(e)}")
        raise

    print("\n" + "="*80 + "\n")


async def main():
    """Run all tests."""

    # Check API key
    if not os.environ.get('PERPLEXITY_API_KEY'):
        print("\n[ERROR] PERPLEXITY_API_KEY not set!")
        return

    print("\n" + "="*80)
    print("PERPLEXITY SEARCH API - COMPREHENSIVE TESTS")
    print("="*80)
    print("\n[INFO] API Key: SET")
    print("[INFO] Endpoint: https://api.perplexity.ai/search")
    print("[INFO] Rate Limit: 3 QPS")
    print("[INFO] Pricing: $5 per 1,000 requests")

    try:
        await test_single_search()
        await test_batch_search()
        await test_recency_filters()
        await test_retry_logic()

        print("\n" + "="*80)
        print("ALL TESTS COMPLETED SUCCESSFULLY")
        print("="*80 + "\n")

    except KeyboardInterrupt:
        print("\n\n[INFO] Tests interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Tests failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
