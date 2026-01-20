# Citation-Aware Memory System - Implementation Plan

## Overview

Store citations alongside memory so we can return pre-extracted citations instead of re-extracting. This avoids redundant extraction work while maintaining the ability to extract fresh when needed.

## Core Concept

**Single recall rule**: Match **required keywords** against the stored **query + citation (quote + context) + hit_keywords**. Return citations on match, extract on miss.

No special handling for different source types. All sources accumulate citations over time.

**Important distinctions:**
- **Only required/mandatory keywords** are used for matching and stored as hit_keywords
- **Matching searches across**: stored query/search_term + citation quote + citation context + hit_keywords
- **hit_keywords**: Only the required keywords that were actually found in the citation

---

## How It Works

### Example: Table-Wide Source Accumulation

**First Validation: Wyoming Population**
```
Query keywords: ["Wyoming", "population"]
Source: census.gov (table-wide)
Extract → Citation: "Wyoming: 576,851"
Store with hit_keywords: ["Wyoming", "population"]
```

**Second Validation: Montana Population**
```
Query keywords: ["Montana", "population"]
Check census.gov citations → hit_keywords are ["Wyoming", "population"]
No match for "Montana" → Return source for extraction
Extract → Citation: "Montana: 1,084,225"
Store with hit_keywords: ["Montana", "population"]
```

**Third Validation: Wyoming Population (again)**
```
Query keywords: ["Wyoming", "population"]
Check census.gov citations → hit_keywords include ["Wyoming", "population"]
MATCH → Return stored citation directly (no extraction)
```

### Accumulated Result

Over time, a source accumulates citations for different entities:

```json
{
  "url": "https://census.gov/population",
  "content": "Full table...",

  "citations": [
    {
      "quote": "Wyoming: 576,851",
      "hit_keywords": ["Wyoming", "population"]
    },
    {
      "quote": "Montana: 1,084,225",
      "hit_keywords": ["Montana", "population"]
    }
  ]
}
```

---

## Data Structure

```json
{
  "sources": {
    "source_abc123": {
      "url": "https://tokchart.com/bella-poarch",
      "title": "TokChart - Bella Poarch",
      "content": "Full text for extraction fallback...",
      "source_type": "search",
      "search_term": "Bella Poarch TikTok followers 2026",

      "citations": [
        {
          "quote": "Bella Poarch has 93,695,680 followers",
          "p_score": 0.92,
          "context": "TikTok analytics dashboard",
          "hit_keywords": ["Bella Poarch", "followers"],
          "extracted_at": "2026-01-20T10:30:00Z"
        }
      ]
    },

    "source_def456": {
      "url": "https://census.gov/population-by-state",
      "title": "US Population by State",
      "content": "| State | 2020 |...",
      "source_type": "table_extraction",
      "search_term": "US state population 2020 census",

      "citations": [
        {
          "quote": "Wyoming: 576,851",
          "hit_keywords": ["Wyoming", "population", "2020"],
          "extracted_at": "2026-01-20T11:00:00Z"
        },
        {
          "quote": "Montana: 1,084,225",
          "hit_keywords": ["Montana", "population", "2020"],
          "extracted_at": "2026-01-20T11:30:00Z"
        }
      ]
    }
  },

  "indexes": {
    "by_url": {
      "https://tokchart.com/bella-poarch": "source_abc123",
      "https://census.gov/population-by-state": "source_def456"
    }
  }
}
```

### Key Fields

| Field | Meaning | Used For |
|-------|---------|----------|
| `content` | Full source text | Fallback extraction |
| `citations` | Pre-extracted quotes with context | Direct return on match |
| `hit_keywords` | **Required** keywords actually found in citation | Recall matching |
| `source_type` | Origin (search, url_fetch, table_extraction) | Debugging/provenance |
| `search_term` | Original query/search term | Recall matching (searched alongside citation) |

---

## Recall Logic

### Single Function: `recall(url=None, keywords=None)`

```python
def recall(url: str = None, required_keywords: list = None) -> dict:
    """
    Unified recall - same logic for URL-based and keyword-based.

    Args:
        url: Optional URL to look up directly
        required_keywords: Mandatory keywords that must match

    Returns:
        - needs_extraction: False + citations (if required keywords match)
        - needs_extraction: True + source (if no match but have source)
        - found: False (if nothing relevant)
    """

    # Find candidate sources
    if url:
        # URL-based: look up specific source
        source_id = indexes["by_url"].get(url)
        candidates = [sources[source_id]] if source_id else []
    else:
        # Keyword-based: find sources with content matching keywords
        candidates = keyword_filter_sources(required_keywords)

    if not candidates:
        return {"found": False}

    # Check each candidate for citation match against required keywords
    for source in candidates:
        matching_citations = find_matching_citations(
            citations=source.get("citations", []),
            query_data=source,  # Contains search_term
            required_keywords=required_keywords
        )

        if matching_citations:
            return {
                "found": True,
                "needs_extraction": False,
                "citations": matching_citations,
                "source_url": source["url"],
                "source_title": source["title"]
            }

    # Have source(s) but no matching citations - need extraction
    return {
        "found": True,
        "needs_extraction": True,
        "sources": [
            {
                "url": s["url"],
                "title": s["title"],
                "content": s["content"]
            }
            for s in candidates
        ]
    }


def find_matching_citations(citations: list, query_data: dict, required_keywords: list) -> list:
    """
    Find citations where required keywords match stored query + citation content.

    Match criteria: All required keywords appear somewhere in:
    - stored query/search_term
    - citation quote
    - citation context
    - hit_keywords

    Args:
        citations: List of stored citations
        query_data: Stored query data (contains search_term)
        required_keywords: Current query's required/mandatory keywords
    """
    matching = []

    for citation in citations:
        # Build searchable text from query + citation
        searchable = " ".join([
            query_data.get("search_term", ""),
            citation.get("quote", ""),
            citation.get("context", ""),
            " ".join(citation.get("hit_keywords", []))
        ]).lower()

        # All required keywords must appear somewhere in searchable text
        if all(kw.lower() in searchable for kw in required_keywords):
            matching.append(citation)

    return matching
```

---

## Storage Logic

### Function: `store_citations()`

```python
def store_citations(
    url: str,
    content: str,
    title: str,
    search_term: str,  # Original query for recall matching
    citations: list,   # With hit_keywords already computed (required keywords only)
    source_type: str = "search"
):
    """
    Store or update source with new citations.

    Citations accumulate - new extractions add to existing.
    search_term is stored for recall matching (searched alongside citation content).
    """
    source_id = indexes["by_url"].get(url)

    if source_id and source_id in sources:
        # Existing source - append new citations
        existing = sources[source_id]
        existing["citations"].extend(citations)
        # Dedupe by quote text
        existing["citations"] = dedupe_citations(existing["citations"])
    else:
        # New source
        source_id = generate_source_id(url)
        sources[source_id] = {
            "url": url,
            "title": title,
            "content": content,
            "search_term": search_term,
            "source_type": source_type,
            "citations": citations
        }
        indexes["by_url"][url] = source_id


def dedupe_citations(citations: list) -> list:
    """Remove duplicate citations by quote text."""
    seen = set()
    unique = []
    for c in citations:
        quote_hash = hash(c["quote"].strip().lower())
        if quote_hash not in seen:
            seen.add(quote_hash)
            unique.append(c)
    return unique
```

### Computing Hit Keywords

```python
def compute_hit_keywords(citation: dict, required_keywords: list) -> list:
    """
    Determine which REQUIRED keywords actually appear in this citation.

    Only stores required/mandatory keywords that are actually found.
    This is what we match against during recall.

    Args:
        citation: The extracted citation with quote and context
        required_keywords: Only the mandatory keywords from the query
    """
    citation_text = f"{citation.get('quote', '')} {citation.get('context', '')}".lower()

    hit = []
    for kw in required_keywords:
        # Check keyword and common variants
        variants = get_keyword_variants(kw)  # e.g., "Wyoming" -> ["wyoming", "wy"]
        if any(v.lower() in citation_text for v in variants):
            hit.append(kw)

    return hit
```

---

## Integration Flow

### After Extraction (Clone)

```python
# In the_clone.py after extraction completes

for source in extracted_sources:
    # Compute hit_keywords for each citation using REQUIRED keywords only
    citations_with_hits = []
    for citation in source["citations"]:
        citation["hit_keywords"] = compute_hit_keywords(citation, required_keywords)
        citations_with_hits.append(citation)

    # Store with search_term for recall matching
    MemoryCache.store_citations(
        session_id=session_id,
        url=source["url"],
        content=source["content"],
        title=source["title"],
        search_term=search_term,  # Stored for recall matching
        citations=citations_with_hits,
        source_type=source.get("source_type", "search")
    )
```

### During Recall (Clone)

```python
# In the_clone.py during memory recall

# URL-based (URLs in query)
for url in query_urls:
    result = memory.recall(url=url, required_keywords=required_keywords)

    if result["found"] and not result["needs_extraction"]:
        ready_citations.extend(result["citations"])
    elif result["found"]:
        sources_to_extract.append(result["sources"][0])
    else:
        urls_to_fetch.append(url)  # Jina

# Keyword-based (no URLs)
if not query_urls:
    result = memory.recall(required_keywords=required_keywords)

    if result["found"] and not result["needs_extraction"]:
        ready_citations.extend(result["citations"])
    elif result["found"]:
        sources_to_extract.extend(result["sources"])
```

---

## Scenario Summary

| Scenario | What Happens |
|----------|--------------|
| URL + required keywords found in (query + citation + hit_keywords) | Return stored citations |
| URL + required keywords NOT found | Return source for extraction, store new citations after |
| Keyword search + required keywords found | Return stored citations |
| Keyword search + no match | Return sources for extraction |
| Nothing found | Jina fetch (URL) or search (keywords) |

**Matching logic**: All required keywords must appear somewhere in the combined text of:
- Stored `search_term`
- Citation `quote`
- Citation `context`
- Citation `hit_keywords`

---

## Migration Path

### Phase 1: Schema Update

1. Update `search_memory.py` with new schema structure
2. Add `citations` field with `hit_keywords` to source entries
3. Update indexes structure

### Phase 2: Storage Updates

1. Add `store_citations()` method that accumulates citations
2. Add `compute_hit_keywords()` function
3. Add `dedupe_citations()` helper

### Phase 3: Recall Updates

1. Implement unified `recall(url, keywords)` function
2. Implement `find_matching_citations()` with hit_keywords matching
3. Return `needs_extraction` flag appropriately

### Phase 4: Clone Integration

1. After extraction: compute hit_keywords and call `store_citations()`
2. During recall: check for matching citations before extraction
3. Skip extraction when citations returned
4. Pass keywords through Jina fetch flow

### Phase 5: Testing

1. Test citation accumulation for same source
2. Test keyword matching returns correct citations
3. Test no-match triggers extraction
4. Test Jina fetches store with context
5. Verify cross-entity queries work (Wyoming then Montana)

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/the_clone/search_memory.py` | New `recall()`, `store_citations()`, hit_keywords logic |
| `src/the_clone/search_memory_cache.py` | Expose new methods via MemoryCache |
| `src/the_clone/the_clone.py` | Integrate citation storage after extraction, recall before extraction |
| `src/lambdas/interface/actions/table_maker/execution.py` | Use `store_citations()` with `source_type="table_extraction"` |
| `docs/SEARCH_MEMORY_SYSTEM.md` | Update documentation |

---

## Related Documentation

- `docs/SEARCH_MEMORY_SYSTEM.md` - Current memory system architecture
- `docs/MEMORY_URL_STORAGE_ISSUE.md` - Issue that led to this design
