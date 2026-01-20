# Memory URL Storage Issue

## Date
2026-01-20

## Issue Summary
URLs cited in validation output don't appear in `agent_memory.json`, causing subsequent validation runs to re-fetch the same URLs via Jina instead of recalling from memory.

## Observed Behavior
1. First validation run completes with citations (e.g., `tokchart.com/dashboard/artists/bella-poarch_1008`)
2. Follow-up validation shows "URL Memory Lookup" with those URLs as "Not in Memory"
3. Jina fetches the URLs fresh instead of recalling from memory
4. Memory shows 72 queries stored, so the memory system IS working for search queries

## Investigation Summary

### What We Know
1. **Search queries ARE being stored** - 72 queries in memory after validation
2. **URL indexing works** - `store_search()` indexes URLs from search results in `by_url` index
3. **URL recall works** - `recall_by_urls()` can find URLs that are in the index

### The Gap
URLs that appear in **citations** but weren't in **Perplexity Search results** won't be in memory.

Flow:
1. Clone does Perplexity Search → results stored (with URLs indexed)
2. Source triage → selects relevant sources
3. Synthesis → generates answer with citations
4. Citations may reference URLs that weren't in search results

### Fix Applied
Added storage of Jina-fetched URLs to memory in `search_memory.py:fetch_url_content()` (lines 1987-2002):
```python
# Store fetched content to memory for future recall
try:
    await self.store_url_content(
        url=url,
        content=snippet,
        title=title,
        source_type="jina_live_fetch",
        metadata={...}
    )
except Exception as store_err:
    logger.warning(f"[MEMORY] Failed to store live-fetched URL (non-fatal): {store_err}")
```

This ensures that URLs fetched via Jina are stored for future recall.

## Open Question

**Why would Jina be called in the first validation run at all?**

For Jina to be called, there must be URLs in the query that aren't in memory. But on the first run:
- No prior memory exists
- Validation queries typically don't contain URLs

Possible explanations (none fully satisfying):
1. ~~First validation used different model/path~~ - Ruled out by user
2. URL was in search results with empty snippet, filtered out during triage, but AI cited it anyway based on other sources
3. AI inferred/hallucinated the URL from data in other sources

**This remains unexplained.** Need more logging to understand the flow.

## Logging Added
Added logging to track sources/queries in validation for debugging:
- Log count of search results stored to memory
- Log count of URLs indexed
- Log citations returned vs URLs in memory

## Files Modified
- `src/the_clone/search_memory.py` - Added storage of Jina-fetched URLs

## Related Documentation
- `docs/SEARCH_MEMORY_SYSTEM.md` - Memory system architecture
- `src/the_clone/ARCHITECTURE.md` - Clone system overview
