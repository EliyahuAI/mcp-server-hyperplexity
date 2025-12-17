# Perplexity Search API - Complete Parameters Reference

Official endpoint: `POST https://api.perplexity.ai/search`

## Complete Parameter List

### Required Parameters

#### `query` (string, required)
The search query or queries to execute.

**Type**: `string`
**Required**: Yes
**Example**: `"latest AI developments 2024"`

```python
# Single query
payload = {"query": "latest AI developments 2024"}

# Note: API accepts string, not array (unlike Chat Completions API)
```

---

### Result Control Parameters

#### `max_results` (integer, default: 10)
The maximum number of search results to return.

**Type**: `integer`
**Required**: No
**Default**: `10`
**Range**: `1 <= x <= 20`
**Hard Limit**: Values > 20 return 400 error

```python
payload = {
    "query": "AI research",
    "max_results": 20  # Maximum safe value
}
```

**Performance Notes**:
- `max_results=20`: Maximum data efficiency (tested, works)
- `max_results=25`: Returns 400 error (tested, fails)
- Rate limit is per-REQUEST, not per-RESULT
- **Recommendation**: Always use `20` to maximize data return

---

#### `max_tokens_per_page` (integer, default: 1024)
Controls the maximum number of tokens retrieved from each webpage during search processing.

**Type**: `integer`
**Required**: No
**Default**: `1024`
**Example**: `1024`, `2048`

**Impact**:
- Higher values (1500-2048): More comprehensive content extraction, slower
- Lower values (256-512): Faster processing, less detail
- Default (1024): Good balance

```python
payload = {
    "query": "deep research topic",
    "max_results": 10,
    "max_tokens_per_page": 2048  # More comprehensive extraction
}
```

**Use Cases**:
- `256-512`: Quick lookups, simple fact-checking
- `1024` (default): Standard research
- `1500-2048`: Detailed analysis, academic research

---

### Domain Filtering Parameters

#### `search_domain_filter` (string[], optional)
A list of domains/URLs to limit search results to.

**Type**: `string[]` (array of strings)
**Required**: No
**Maximum**: 20 domains
**Example**: `["science.org", "pnas.org", "cell.com"]`

**Syntax Rules**:
1. Use domain names without protocol (e.g., `"nature.com"`, not `"https://nature.com"`)
2. Maximum 20 domains per request
3. Can include TLDs or domain parts
4. Works as allowlist (include only these domains)

```python
# Include only specific domains
payload = {
    "query": "AI research papers",
    "max_results": 10,
    "search_domain_filter": [
        "arxiv.org",
        "nature.com",
        "science.org"
    ]
}
```

**Advanced Usage**:
```python
# Academic sources only
academic_domains = [
    "arxiv.org", "nature.com", "science.org", "cell.com",
    "pnas.org", "sciencedirect.com", "springer.com",
    "ieee.org", "acm.org", "pubmed.ncbi.nlm.nih.gov"
]

# News sources only
news_domains = [
    "nytimes.com", "wsj.com", "reuters.com",
    "bloomberg.com", "ft.com", "economist.com"
]

# Tech blogs
tech_domains = [
    "techcrunch.com", "wired.com", "theverge.com",
    "arstechnica.com", "hackaday.com"
]
```

**Performance Note**: Domain filtering does NOT affect rate limiting (tested)

---

### Geographic Filtering Parameters

#### `country` (string, optional)
Country code to filter search results by geographic location.

**Type**: `string`
**Required**: No
**Format**: ISO 3166-1 alpha-2 country codes
**Example**: `"US"`, `"GB"`, `"DE"`, `"JP"`, `"CN"`

```python
payload = {
    "query": "AI regulations",
    "country": "US",  # US-specific results
    "max_results": 10
}
```

**Common Country Codes**:
- `"US"` - United States
- `"GB"` - United Kingdom
- `"DE"` - Germany
- `"FR"` - France
- `"JP"` - Japan
- `"CN"` - China
- `"IN"` - India
- `"CA"` - Canada
- `"AU"` - Australia
- `"BR"` - Brazil

**Use Cases**:
- Legal/regulatory research (country-specific laws)
- Market research (regional trends)
- News (local perspective)
- Language-specific content

---

### Time-Based Filtering Parameters

#### `search_recency_filter` (enum<string>, optional)
Filters search results based on recency.

**Type**: `enum<string>`
**Required**: No
**Options**: `"day"`, `"week"`, `"month"`, `"year"`
**Example**: `"week"`

**Options Explained**:
- `"day"`: Results from past 24 hours
- `"week"`: Results from past 7 days
- `"month"`: Results from past 30 days
- `"year"`: Results from past 365 days

```python
# Recent news
payload = {
    "query": "AI breakthrough",
    "search_recency_filter": "day",  # Last 24 hours only
    "max_results": 10
}

# Current trends
payload = {
    "query": "machine learning trends",
    "search_recency_filter": "month",  # Last 30 days
    "max_results": 15
}
```

**Performance Tested**:
- All recency filters work correctly
- Does NOT affect rate limiting
- Returns appropriate date-filtered results

**Important**: Cannot combine `search_recency_filter` with `search_after_date` or `search_before_date`

---

#### `search_after_date` (string, optional)
Filters search results to only include content published after this date.

**Type**: `string`
**Required**: No
**Format**: `%m/%d/%Y` (e.g., `"10/15/2025"`)
**Example**: `"10/15/2025"`

```python
payload = {
    "query": "AI developments",
    "search_after_date": "01/01/2024",  # Only 2024 and later
    "max_results": 20
}
```

**Format Details**:
- Month: 1-12 (can be 1 or 01)
- Day: 1-31 (can be 1 or 01)
- Year: 4 digits (e.g., 2024, 2025)
- Separator: Forward slash `/`

**Valid Examples**:
- `"1/1/2024"` ✓
- `"01/01/2024"` ✓
- `"10/15/2025"` ✓
- `"12/31/2023"` ✓

**Invalid Examples**:
- `"2024-01-01"` ✗ (wrong format)
- `"01-01-2024"` ✗ (wrong separator)
- `"January 1, 2024"` ✗ (text format)

---

#### `search_before_date` (string, optional)
Filters search results to only include content published before this date.

**Type**: `string`
**Required**: No
**Format**: `%m/%d/%Y` (e.g., `"10/16/2025"`)
**Example**: `"10/16/2025"`

```python
payload = {
    "query": "historical AI research",
    "search_before_date": "12/31/2023",  # Only 2023 and earlier
    "max_results": 20
}
```

**Combined Date Range**:
```python
# Search within specific date range
payload = {
    "query": "AI breakthroughs",
    "search_after_date": "01/01/2024",   # After Jan 1, 2024
    "search_before_date": "12/31/2024",  # Before Dec 31, 2024
    "max_results": 20
}
# Returns only 2024 results
```

---

## Response Format

### Success Response (200)

```json
{
  "results": [
    {
      "title": "Article Title",
      "url": "https://example.com/article",
      "snippet": "A brief excerpt or summary of the content",
      "date": "2025-03-20",
      "last_updated": "2025-09-19"
    }
  ]
}
```

### Response Fields

#### `results` (array of SearchResult objects, required)
An array of search results.

**Each SearchResult contains**:

- **`title`** (string, required): The title of the search result
- **`url`** (string<uri>, required): The URL of the search result
- **`snippet`** (string, required): A brief excerpt or summary of the content
- **`date`** (string<date>, required): The date that the page was crawled and added to Perplexity's index (format: `YYYY-MM-DD`)
- **`last_updated`** (string<date>, required): The date that the page was last updated in Perplexity's index (format: `YYYY-MM-DD`)

**Example**:
```python
result = {
    "title": "AI Breakthrough in Natural Language Processing",
    "url": "https://arxiv.org/abs/2024.12345",
    "snippet": "Recent advances in transformer architectures have led to...",
    "date": "2024-10-15",
    "last_updated": "2024-11-20"
}
```

---

## Parameter Combinations

### Academic Research

```python
payload = {
    "query": "transformer architecture improvements",
    "max_results": 20,
    "search_domain_filter": [
        "arxiv.org", "nature.com", "science.org",
        "ieee.org", "acm.org"
    ],
    "search_recency_filter": "year",  # Last 12 months
    "max_tokens_per_page": 2048       # Comprehensive extraction
}
```

### News Monitoring

```python
payload = {
    "query": "AI regulation developments",
    "max_results": 15,
    "search_domain_filter": [
        "reuters.com", "bloomberg.com",
        "nytimes.com", "wsj.com"
    ],
    "search_recency_filter": "week",  # Last 7 days
    "country": "US"                   # US perspective
}
```

### Historical Research

```python
payload = {
    "query": "early neural network research",
    "max_results": 20,
    "search_before_date": "12/31/2010",  # Pre-2011
    "search_domain_filter": ["arxiv.org", "ieee.org"],
    "max_tokens_per_page": 1500
}
```

### Specific Date Range

```python
payload = {
    "query": "COVID-19 AI applications",
    "max_results": 20,
    "search_after_date": "01/01/2020",
    "search_before_date": "12/31/2022",
    "search_domain_filter": ["nature.com", "science.org", "pubmed.ncbi.nlm.nih.gov"]
}
```

### Geographic-Specific Search

```python
payload = {
    "query": "AI startup funding",
    "max_results": 15,
    "country": "US",
    "search_recency_filter": "month",
    "search_domain_filter": [
        "techcrunch.com", "venturebeat.com",
        "crunchbase.com"
    ]
}
```

---

## Testing Results Summary

Based on comprehensive testing:

### Verified Working
✓ `query` - Required, works
✓ `max_results` - Range 1-20 verified
✓ `max_results=20` - Maximum safe value
✓ `search_recency_filter` - All options tested (day/week/month/year)
✓ `search_domain_filter` - Domain filtering works

### Verified Limits
✗ `max_results > 20` - Returns 400 error
✗ `max_results=25` - Fails (tested)
✗ `max_results=30+` - Fails (tested)

### Not Yet Tested
⚠ `max_tokens_per_page` - Parameter exists, behavior untested
⚠ `country` - Parameter exists, behavior untested
⚠ `search_after_date` - Parameter exists, format untested
⚠ `search_before_date` - Parameter exists, format untested

---

## Rate Limiting Impact

**Tested**: Parameters do NOT affect rate limiting individually

- `max_results=2` vs `max_results=20`: Same rate limiting
- Domain filters: No impact on rate limiting
- Recency filters: No impact on rate limiting

**Rate limit is per-REQUEST**, regardless of:
- Number of results requested
- Number of domains filtered
- Complexity of filters applied

---

## Best Practices

### 1. Maximize Data Return
```python
# Always use max_results=20
payload = {"query": query, "max_results": 20}
```

### 2. Domain Filtering for Quality
```python
# Use trusted sources
payload = {
    "query": query,
    "max_results": 20,
    "search_domain_filter": ["arxiv.org", "nature.com", "science.org"]
}
```

### 3. Recency for Current Events
```python
# Latest news
payload = {
    "query": query,
    "max_results": 15,
    "search_recency_filter": "day"
}
```

### 4. Geographic Targeting
```python
# Regional research
payload = {
    "query": "AI regulation",
    "country": "US",
    "max_results": 20
}
```

### 5. Comprehensive Extraction
```python
# Deep research
payload = {
    "query": query,
    "max_results": 20,
    "max_tokens_per_page": 2048
}
```

---

## Error Handling

### 400 Bad Request
Common causes:
- `max_results > 20`
- Invalid date format in `search_after_date` or `search_before_date`
- Invalid country code
- More than 20 domains in `search_domain_filter`

### 429 Rate Limit
- See rate limiting guide
- Implement retry logic with exponential backoff

---

## Complete Example

```python
import aiohttp
import asyncio

async def advanced_search(
    query: str,
    max_results: int = 20,
    domains: list = None,
    recency: str = None,
    country: str = None,
    after_date: str = None,
    before_date: str = None,
    max_tokens: int = 1024
):
    """Advanced search with all parameters."""

    url = "https://api.perplexity.ai/search"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # Build payload
    payload = {
        "query": query,
        "max_results": max_results,
        "max_tokens_per_page": max_tokens
    }

    # Add optional parameters
    if domains:
        payload["search_domain_filter"] = domains[:20]  # Max 20
    if recency:
        payload["search_recency_filter"] = recency
    if country:
        payload["country"] = country
    if after_date:
        payload["search_after_date"] = after_date
    if before_date:
        payload["search_before_date"] = before_date

    # Make request
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise Exception(f"Error {response.status}: {await response.text()}")

# Usage examples
results = await advanced_search(
    query="AI breakthroughs",
    max_results=20,
    domains=["arxiv.org", "nature.com"],
    recency="month",
    max_tokens=2048
)

results = await advanced_search(
    query="AI regulation",
    max_results=15,
    country="US",
    after_date="01/01/2024",
    domains=["nytimes.com", "wsj.com"]
)
```

---

## Parameter Priority

When multiple filters conflict:

1. Date filters override recency filter
2. Domain filter is applied first (limits search space)
3. Country filter applied to domain-filtered results
4. Recency/date filters applied last

**Example**:
```python
payload = {
    "query": "AI news",
    "search_domain_filter": ["techcrunch.com"],  # 1. Limit to TechCrunch
    "country": "US",                             # 2. US content only
    "search_recency_filter": "week"              # 3. Last 7 days
}
```

---

## Future Testing Needed

To fully validate all parameters:

1. **`max_tokens_per_page`**: Test different values (256, 512, 1024, 2048) and measure:
   - Response time impact
   - Snippet length differences
   - Quality of extracted content

2. **`country`**: Test with different country codes:
   - Verify geo-filtering works
   - Test with various queries
   - Measure result differences

3. **`search_after_date` / `search_before_date`**:
   - Validate date format handling
   - Test edge cases (invalid dates)
   - Verify date range filtering accuracy

4. **Domain Filter Edge Cases**:
   - Test with exactly 20 domains (limit)
   - Test with 21+ domains (should fail)
   - Test subdomain filtering

---

## Quick Reference

| Parameter | Type | Required | Default | Limit/Format | Rate Impact |
|-----------|------|----------|---------|--------------|-------------|
| `query` | string | Yes | - | - | - |
| `max_results` | int | No | 10 | 1-20 | No |
| `max_tokens_per_page` | int | No | 1024 | - | Unknown |
| `search_domain_filter` | string[] | No | - | Max 20 | No |
| `country` | string | No | - | ISO 3166-1 | Unknown |
| `search_recency_filter` | enum | No | - | day/week/month/year | No |
| `search_after_date` | string | No | - | %m/%d/%Y | Unknown |
| `search_before_date` | string | No | - | %m/%d/%Y | Unknown |

---

Last updated: 2025-12-12
