#!/usr/bin/env python3
"""
Web Search Rate Limiter

Manages Anthropic web search rate limiting (20 searches/second) across multiple
concurrent validation sessions to prevent rate limit violations.
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class WebSearchCall:
    """Represents a pending web search call."""
    timestamp: float
    session_id: str
    model: str
    max_searches: int


class WebSearchRateLimiter:
    """
    Manages web search rate limiting for Anthropic API calls.
    
    Key Features:
    - 20 searches/second limit enforcement
    - Call staggering to optimize throughput
    - Session-aware tracking
    - Collision avoidance for multiple users
    """
    
    def __init__(self, max_searches_per_second: int = 20):
        """
        Initialize the rate limiter.
        
        Args:
            max_searches_per_second: Maximum web searches allowed per second (default: 20)
        """
        self.max_searches_per_second = max_searches_per_second
        self.search_history = deque()  # Track recent search calls
        self.pending_calls = deque()   # Queue of pending calls
        self.session_stats = {}        # Per-session statistics
        self.lock = asyncio.Lock()     # Thread safety
        
        # Configuration
        self.window_seconds = 1.0      # Rolling window for rate limiting
        self.min_delay_ms = 50         # Minimum delay between calls (milliseconds)
        self.max_delay_ms = 500        # Maximum delay for staggering
        
        logger.info(f"🔧 WebSearchRateLimiter initialized: {max_searches_per_second}/second limit")
    
    async def should_delay_call(self, session_id: str, model: str, max_searches: int = 10) -> float:
        """
        Determine if a call should be delayed and by how much.
        
        Args:
            session_id: Validation session ID
            model: Model being used
            max_searches: Maximum searches for this call
            
        Returns:
            Delay in seconds (0.0 if no delay needed)
        """
        async with self.lock:
            current_time = time.time()
            
            # Clean old entries from history
            self._clean_old_entries(current_time)
            
            # Calculate current usage in the last second
            recent_searches = sum(call.max_searches for call in self.search_history)
            
            # Projected usage if we add this call
            projected_usage = recent_searches + max_searches
            
            # If we're under the limit, no delay needed
            if projected_usage <= self.max_searches_per_second:
                self._record_call(current_time, session_id, model, max_searches)
                return 0.0
            
            # Calculate minimum delay to stay under limit
            excess_searches = projected_usage - self.max_searches_per_second
            base_delay = excess_searches / self.max_searches_per_second
            
            # Add staggering for better distribution
            stagger_delay = self._calculate_stagger_delay(session_id)
            
            total_delay = max(base_delay, stagger_delay)
            total_delay = min(total_delay, self.max_delay_ms / 1000.0)  # Cap at max delay
            
            logger.info(f"🕐 Web search delay: {total_delay:.3f}s (session: {session_id}, "
                       f"recent: {recent_searches}, projected: {projected_usage})")
            
            return total_delay
    
    def _clean_old_entries(self, current_time: float):
        """Remove entries older than the window."""
        cutoff = current_time - self.window_seconds
        while self.search_history and self.search_history[0].timestamp < cutoff:
            self.search_history.popleft()
    
    def _record_call(self, timestamp: float, session_id: str, model: str, max_searches: int):
        """Record a new call in the history."""
        call = WebSearchCall(timestamp, session_id, model, max_searches)
        self.search_history.append(call)
        
        # Update session statistics
        if session_id not in self.session_stats:
            self.session_stats[session_id] = {
                'total_calls': 0,
                'total_searches': 0,
                'first_call': timestamp,
                'last_call': timestamp,
                'models_used': set()
            }
        
        stats = self.session_stats[session_id]
        stats['total_calls'] += 1
        stats['total_searches'] += max_searches
        stats['last_call'] = timestamp
        stats['models_used'].add(model)
    
    def _calculate_stagger_delay(self, session_id: str) -> float:
        """Calculate staggering delay to distribute calls evenly."""
        # Simple hash-based staggering to avoid collisions
        session_hash = hash(session_id) % 1000
        stagger_ms = (session_hash * self.min_delay_ms) / 1000.0
        return min(stagger_ms / 1000.0, self.max_delay_ms / 1000.0)
    
    async def wait_if_needed(self, session_id: str, model: str, max_searches: int = 10):
        """
        Wait if necessary before making a web search call.
        
        Args:
            session_id: Validation session ID
            model: Model being used
            max_searches: Maximum searches for this call
        """
        delay = await self.should_delay_call(session_id, model, max_searches)
        
        if delay > 0:
            logger.info(f"⏳ Delaying web search call by {delay:.3f}s to respect rate limits")
            await asyncio.sleep(delay)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current rate limiter statistics."""
        current_time = time.time()
        self._clean_old_entries(current_time)
        
        recent_searches = sum(call.max_searches for call in self.search_history)
        recent_calls = len(self.search_history)
        
        return {
            'current_usage': {
                'searches_in_last_second': recent_searches,
                'calls_in_last_second': recent_calls,
                'utilization_percent': (recent_searches / self.max_searches_per_second) * 100
            },
            'configuration': {
                'max_searches_per_second': self.max_searches_per_second,
                'window_seconds': self.window_seconds,
                'min_delay_ms': self.min_delay_ms,
                'max_delay_ms': self.max_delay_ms
            },
            'session_count': len(self.session_stats),
            'total_sessions_tracked': len(self.session_stats)
        }
    
    def get_session_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific session."""
        if session_id not in self.session_stats:
            return None
        
        stats = self.session_stats[session_id].copy()
        stats['models_used'] = list(stats['models_used'])  # Convert set to list
        stats['duration_seconds'] = stats['last_call'] - stats['first_call']
        stats['average_searches_per_call'] = stats['total_searches'] / max(1, stats['total_calls'])
        
        return stats


# Global rate limiter instance
_global_rate_limiter = None


def get_rate_limiter() -> WebSearchRateLimiter:
    """Get the global web search rate limiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = WebSearchRateLimiter()
    return _global_rate_limiter


async def apply_web_search_rate_limiting(session_id: str, model: str, max_searches: int = 10):
    """
    Apply web search rate limiting before making an API call.
    
    Args:
        session_id: Validation session ID
        model: Model being used (for statistics)
        max_searches: Maximum searches this call will make
    """
    limiter = get_rate_limiter()
    await limiter.wait_if_needed(session_id, model, max_searches)


def optimize_web_search_settings(current_load: int, target_throughput: int) -> Dict[str, int]:
    """
    Recommend optimal web search settings based on current load.
    
    Args:
        current_load: Current number of concurrent users
        target_throughput: Target requests per minute
        
    Returns:
        Dictionary with recommended settings
    """
    # Calculate optimal max_searches per call
    base_searches = 10
    
    if current_load <= 1:
        # Single user - can use full search capability
        recommended_searches = 10
        expected_delay = 0.0
    elif current_load <= 2:
        # Two users - reduce slightly to avoid collisions
        recommended_searches = 8
        expected_delay = 0.1
    else:
        # Multiple users - more conservative
        recommended_searches = 6
        expected_delay = 0.2
    
    # Calculate expected throughput
    searches_per_minute = target_throughput * recommended_searches
    web_search_capacity = 20 * 60  # 20/second = 1200/minute
    
    utilization = (searches_per_minute / web_search_capacity) * 100
    
    return {
        'recommended_max_searches': recommended_searches,
        'expected_delay_seconds': expected_delay,
        'estimated_throughput_rpm': min(target_throughput, int(web_search_capacity / recommended_searches)),
        'web_search_utilization_percent': min(100, utilization),
        'bottleneck': 'web_search' if utilization > 80 else 'other'
    }


if __name__ == "__main__":
    # Test the rate limiter
    import asyncio
    
    async def test_rate_limiter():
        """Test the web search rate limiter."""
        limiter = WebSearchRateLimiter(max_searches_per_second=20)
        
        print("Testing web search rate limiter...")
        
        # Simulate multiple rapid calls
        tasks = []
        for i in range(5):
            session_id = f"test_session_{i}"
            model = "claude-4-sonnet"
            task = limiter.wait_if_needed(session_id, model, 10)
            tasks.append(task)
        
        start_time = time.time()
        await asyncio.gather(*tasks)
        end_time = time.time()
        
        print(f"All calls completed in {end_time - start_time:.3f} seconds")
        print(f"Rate limiter stats: {limiter.get_stats()}")
        
        # Test optimization recommendations
        recommendations = optimize_web_search_settings(current_load=2, target_throughput=100)
        print(f"Optimization recommendations: {recommendations}")
    
    asyncio.run(test_rate_limiter())