# URL Validation Feature

## Overview

The **URL validation** feature automatically validates all URLs in AI API responses against citations, ensuring that LLM-generated URLs are grounded in actual search results.

## Problem It Solves

LLMs sometimes:
- **Hallucinate URLs** - Generate plausible-looking but non-existent URLs
- **Modify URLs slightly** - Change query params, paths, or IDs
- **Use different URL formats** - Different protocol, subdomain variations

URL validation ensures all URLs in responses are traceable to actual search results.

## How It Works

### 1. Automatic Post-Processing

URL validation runs **automatically** on ALL API responses (both soft and hard schema):

```python
# Happens after every call_structured_api call
result = await client.call_structured_api(...)

# System automatically:
# 1. Extracts citations from response
# 2. Finds all URLs in response content
# 3. Validates each URL against citations
# 4. Replaces with canonical URL or adds warning
```

### 2. Validation Strategy

**Three-tier matching approach:**

#### Tier 1: Exact Match (Normalized)
```python
# URLs are normalized for comparison:
"https://careers.abbvie.com/job/123"
→ "careers.abbvie.com/job/123"  # Remove protocol, www, trailing /

# If normalized URLs match exactly → Use canonical citation URL
```

#### Tier 2: Fuzzy Match (Same Domain)
```python
# Same domain, similar path:
LLM URL:       "careers.abbvie.com/job/12345"
Citation URL:  "careers.abbvie.com/en/job/director-of-ai/jid-12714"

# Scoring:
# - Same domain: +0.5 base score
# - Path similarity: +0.0 to +0.5
# - Total: 0.5 to 1.0

# If score ≥ 0.6 → Use canonical citation URL
```

#### Tier 3: Not Found
```python
# URL not in citations or similarity < 0.6
→ Add warning: "https://... (Warning: Not in citations!)"
```

### 3. Recursive Validation

Validates URLs **anywhere** in the response structure:

```python
{
  "candidates": [
    {
      "id_values": {
        "Company Name": "Acme",
        "Website": "https://acme.com"  # ← Validated
      },
      "source_urls": [
        "https://jobs.acme.com/123",    # ← Validated
        "https://crunchbase.com/acme"  # ← Validated
      ]
    }
  ]
}
```

## Matching Examples

### Exact Match
```python
LLM URL:      "https://jobs.takeda.com/job/boston/director-generative-ai/1113/86259978896"
Citation:     "https://jobs.takeda.com/job/boston/director-generative-ai/1113/86259978896"
Result:       ✓ Exact match (silent - no logging)
```

### Fuzzy Match
```python
LLM URL:      "https://jobs.takeda.com/job/boston/director/123"
Citation:     "https://jobs.takeda.com/job/boston/director-generative-ai/1113/86259978896"
Result:       ✓ Fuzzy match (similarity: 0.72)
Replacement:  Use full citation URL
Log:          [URL_VALIDATION] Fuzzy match: ... → ... (similarity: 0.72)
```

### Not Found
```python
LLM URL:      "https://linkedin.com/company/abbvie"
Citations:    ["https://careers.abbvie.com/...", "https://jobs.takeda.com/..."]
Result:       ✗ Not in citations
Replacement:  "https://linkedin.com/company/abbvie (Warning: Not in citations!)"
Log:          [URL_VALIDATION] URL not in citations: https://linkedin.com/...
```

## URL Normalization

URLs are normalized before comparison to handle common variations:

### Normalization Steps:
1. **Remove protocol:** `https://` → ``
2. **Remove www:** `www.example.com` → `example.com`
3. **Remove trailing slash:** `/path/` → `/path`
4. **Remove query params:** `?param=value` → ``
5. **Remove fragments:** `#section` → ``
6. **Convert to lowercase**

### Examples:
```python
"HTTPS://WWW.Example.Com/Path/?query=1#section"
→ "example.com/path"

"http://example.com/path/"
→ "example.com/path"
```

## Domain-Aware Scoring

For URLs on the same domain, scoring prioritizes domain match:

```python
def calculate_similarity(url, citation):
    if same_domain(url, citation):
        # Base score for same domain
        score = 0.5

        # Add path similarity (0.0 to 0.5)
        path_score = calculate_path_similarity(url_path, citation_path)
        score += path_score * 0.5

        # Final: 0.5 to 1.0
        return score
    else:
        # Different domains - full URL comparison
        return full_url_similarity(url, citation)
```

**Threshold:** ≥ 0.6 for match acceptance

## Logging

### What Gets Logged:

**Fuzzy Matches (INFO):**
```
INFO:[URL_VALIDATION] Fuzzy match: https://jobs.company.com/123 → https://jobs.company.com/job/director/123456 (similarity: 0.72)
```

**Not in Citations (WARNING):**
```
WARNING:[URL_VALIDATION] URL not in citations: https://linkedin.com/company/acme
```

**Errors (ERROR):**
```
ERROR:[URL_VALIDATION] Error during validation: <error_details>
ERROR:[URL_VALIDATION] Traceback: <stack_trace>
```

### What Doesn't Get Logged:

- ✗ **Exact matches** - Expected behavior, no noise
- ✗ **Skipped validation** - When no citations available (DEBUG level only)

## Configuration

### Similarity Threshold

Default: **0.6 (60%)**

To adjust, modify `_fuzzy_match_url_to_citations`:

```python
# Accept fuzzy matches above 0.6 threshold
if best_score >= 0.6:  # ← Change this value
    return (True, best_match)
```

**Recommendations:**
- `0.5` - Very loose (may match unrelated URLs on same domain)
- `0.6` - Balanced (default)
- `0.7` - Stricter (requires more path similarity)
- `0.8` - Very strict (almost exact match required)

### Domain Score Weight

Default: **0.5 base + 0.5 path**

Same-domain URLs get:
- Base score: 0.5 (for domain match)
- Path similarity: 0.0 to 0.5
- Total: 0.5 to 1.0

To adjust weights, modify the `domain_score` in `_fuzzy_match_url_to_citations`.

## When It Runs

### Always Runs For:
- ✅ Perplexity API calls (always have citations from web search)
- ✅ Anthropic calls with web search enabled
- ✅ Both soft_schema and hard schema modes

### Skipped For:
- ⏭️ Anthropic calls without web search (no citations)
- ⏭️ Responses with no citations
- ⏭️ Responses with non-JSON content

## Use Cases

### 1. Job Posting URLs

**Scenario:** LLM finds job on aggregator but provides company career page URL

```python
LLM URL:      "https://careers.abbvie.com/job/ai-director"
Citations:    ["https://www.indeed.com/viewjob?jk=12345"]
Result:       ✗ Not in citations (Warning added)
```

**Why:** The LLM inferred the company URL but search results only had Indeed link.

### 2. Normalized Company URLs

**Scenario:** LLM provides simplified URL, citation has full path

```python
LLM URL:      "https://takeda.com"
Citation:     "https://jobs.takeda.com/job/boston/director-generative-ai/1113/86259978896"
Result:       ✗ Different domains (takeda.com vs jobs.takeda.com)
```

### 3. Job Board Variations

**Scenario:** Same job on different paths

```python
LLM URL:      "https://jobs.company.com/role/123"
Citation:     "https://jobs.company.com/en-us/job/role-director-ai-123"
Result:       ✓ Fuzzy match (same domain, similar path)
```

## Implementation Details

### Location

All URL validation code is in:
```
src/shared/ai_api_client.py
```

**Key Methods:**
- `_validate_urls_in_response()` - Main recursive validator
- `_fuzzy_match_url_to_citations()` - Matching logic
- `_normalize_url_for_comparison()` - URL normalization
- `_is_url()` - URL detection

### Processing Flow

```
API Response
    ↓
Extract citations
    ↓
Parse JSON content
    ↓
Recursively walk data structure
    ↓
For each URL found:
    ↓
Normalize URL
    ↓
Try exact match
    ↓
Try fuzzy match (if same domain)
    ↓
If match found: Replace with canonical
If not found: Add warning
    ↓
Update response content
    ↓
Return validated response
```

### Data Structure Handling

**Validates in:**
- Dictionary values
- List items
- Nested objects
- Nested arrays
- String fields

**Example:**
```python
{
  "field": "https://url1.com",              # ← Validated
  "nested": {
    "url": "https://url2.com"               # ← Validated
  },
  "urls": [
    "https://url3.com",                     # ← Validated
    {"link": "https://url4.com"}            # ← Validated
  ]
}
```

## Monitoring

### Log Analysis

**Count validation events:**
```bash
# Fuzzy matches
grep "URL_VALIDATION.*Fuzzy match" lambda.log | wc -l

# Warnings
grep "URL_VALIDATION.*not in citations" lambda.log | wc -l
```

**Find problematic URLs:**
```bash
# URLs not in citations
grep "Warning: Not in citations!" lambda.log
```

### Success Metrics

**Good Validation Rate:** > 90% of URLs validated (exact or fuzzy)

**High Warning Rate:** > 10% warnings may indicate:
- LLMs inferring URLs beyond search results
- Citations not comprehensive enough
- Threshold too strict (increase from 0.6)

## Troubleshooting

### Issue: Too Many Warnings

**Symptom:**
```
WARNING:[URL_VALIDATION] URL not in citations: https://...
WARNING:[URL_VALIDATION] URL not in citations: https://...
```

**Solutions:**
1. **Lower threshold** - Change from 0.6 to 0.5 for looser matching
2. **Check citations** - Ensure web search is enabled and working
3. **Review URLs** - LLMs may be adding value by finding company sites

### Issue: Wrong URL Matches

**Symptom:**
```
INFO:[URL_VALIDATION] Fuzzy match: https://jobs.companyA.com/123 → https://jobs.companyB.com/456 (similarity: 0.62)
```

**Solution:**
- **Increase threshold** - Change from 0.6 to 0.7
- **Review domain logic** - May need stricter domain validation

### Issue: Valid URLs Getting Warnings

**Symptom:** URLs that should match are marked as "not in citations"

**Debug:**
```python
# Add debug logging to see normalized URLs:
logger.debug(f"URL normalized: {url_normalized}")
logger.debug(f"Citation normalized: {citation_normalized}")
```

**Common Causes:**
- Subdomain differences: `www.site.com` vs `site.com`
- Path variations: `/en/job` vs `/job`
- Query params removed during normalization

## Best Practices

### 1. Review Warnings

Periodically review URLs marked with warnings:
```python
# In your code after getting results:
for candidate in candidates:
    for key, value in candidate.get('id_values', {}).items():
        if "(Warning: Not in citations!)" in str(value):
            print(f"Unvalidated URL in {key}: {value}")
```

### 2. Use with Web Search

URL validation is most effective when citations are comprehensive:
```python
# Good: Web search enabled
result = await client.call_structured_api(
    prompt=prompt,
    model="sonar-pro",           # Perplexity with web search
    search_context_size="high"   # More citations
)

# Less effective: No web search
result = await client.call_structured_api(
    prompt=prompt,
    model="claude-sonnet-4-5",   # Claude without web search
    max_web_searches=0           # No citations
)
```

### 3. Handle Warnings Appropriately

Warnings don't mean the URL is invalid, just unverified:

```python
url = "https://careers.company.com/job/123 (Warning: Not in citations!)"

# Option 1: Remove warning for display
clean_url = url.replace(" (Warning: Not in citations!)", "")

# Option 2: Flag for manual review
needs_review = "(Warning: Not in citations!)" in url

# Option 3: Accept as-is (LLM may have found it via reasoning)
```

## Performance Impact

**Minimal overhead:**
- Runs only when citations exist
- Fast string operations (normalization, matching)
- No API calls
- No blocking I/O

**Typical timing:**
- 10 URLs: < 1ms
- 100 URLs: < 10ms
- 1000 URLs: < 100ms

## Integration with Other Features

### Works With Soft Schema

```python
result = await client.call_structured_api(
    prompt=prompt,
    schema=schema,
    soft_schema=True  # ← Soft schema enabled
)

# URL validation still runs:
# 1. Soft schema allows more results
# 2. URL validation ensures quality
# 3. Best of both worlds
```

### Works With Hard Schema

```python
result = await client.call_structured_api(
    prompt=prompt,
    schema=schema,
    soft_schema=False  # ← Hard schema (default)
)

# URL validation still runs:
# 1. Hard schema ensures structure
# 2. URL validation ensures citation grounding
# 3. Double verification
```

### Works With All Models

- ✅ Perplexity (sonar, sonar-pro) - Always has citations
- ✅ Anthropic with web search - Has citations from search tool
- ⏭️ Anthropic without web search - Skipped (no citations)

## Example Output

### Before URL Validation

```json
{
  "candidates": [
    {
      "id_values": {
        "Company Name": "Takeda",
        "Website": "https://jobs.takeda.com/job/123"
      },
      "source_urls": [
        "https://takeda.com",
        "https://linkedin.com/company/takeda"
      ]
    }
  ]
}
```

### After URL Validation

```json
{
  "candidates": [
    {
      "id_values": {
        "Company Name": "Takeda",
        "Website": "https://jobs.takeda.com/job/boston/director-generative-ai/1113/86259978896"
      },
      "source_urls": [
        "https://takeda.com (Warning: Not in citations!)",
        "https://linkedin.com/company/takeda (Warning: Not in citations!)"
      ]
    }
  ]
}
```

**What happened:**
- ✅ Website URL: Fuzzy matched to full citation URL
- ⚠️ Company homepage: Not in citations (LLM inferred it)
- ⚠️ LinkedIn: Not in citations (LLM inferred it)

## Log Messages Reference

### Normal Operation

**Skipped (No Citations):**
```
DEBUG:[URL_VALIDATION] Skipped - no citations (citations=0)
```

**Skipped (Non-JSON Content):**
```
DEBUG:[URL_VALIDATION] Skipped - content is not JSON: <content>
```

**Completed Successfully:**
```
DEBUG:[URL_VALIDATION] Completed URL validation against 8 citations
```

### Interesting Events

**Fuzzy Match:**
```
INFO:[URL_VALIDATION] Fuzzy match: https://jobs.company.com/123 → https://jobs.company.com/job/director/123456 (similarity: 0.72)
```
*Action:* URL was corrected to canonical citation URL

**Not in Citations:**
```
WARNING:[URL_VALIDATION] URL not in citations: https://linkedin.com/company/acme
```
*Action:* Warning appended to URL

### Errors

**Validation Failed:**
```
ERROR:[URL_VALIDATION] Error during validation: <error>
ERROR:[URL_VALIDATION] Traceback: <stack_trace>
```
*Action:* Original response preserved, validation skipped

## Testing

### Test Script

```bash
cd /mnt/c/Users/ellio/OneDrive\ -\ Eliyahu.AI/Desktop/src/perplexityValidator
python3 test_url_validation.py
```

**Expected output:**
```
[INFO] Response includes 10 citations
[RESULT] Found 3 candidates

Total URLs checked: 3
Exact matches:      2
Fuzzy matches:      1
Not in citations:   0

Validation rate:    100.0%
[SUCCESS] All URLs validated against citations!
```

### Mock Data Test

```bash
python3 test_url_warning.py
```

Tests specific scenarios:
- Exact matches
- Fuzzy matches
- Unvalidated URLs

## Advanced Configuration

### Custom URL Detection

To detect additional URL patterns, modify `_is_url()`:

```python
def _is_url(self, value: str) -> bool:
    if not isinstance(value, str):
        return False
    # Add custom patterns
    return (value.startswith('http://') or
            value.startswith('https://') or
            value.startswith('www.') or
            value.startswith('ftp://'))  # ← Add custom protocol
```

### Custom Normalization

To preserve query params or other URL components:

```python
def _normalize_url_for_comparison(self, url: str) -> str:
    # ... existing code ...

    # REMOVE this line to keep query params:
    # normalized = re.sub(r'[?#].*$', '', normalized)

    return normalized
```

### Disable for Specific Fields

To skip validation for certain fields:

```python
def _validate_urls_in_response(self, data: any, citations: list, skip_keys: set = None) -> any:
    skip_keys = skip_keys or set()

    if isinstance(data, dict):
        validated = {}
        for key, value in data.items():
            if key in skip_keys:
                validated[key] = value  # Skip validation
            else:
                # ... existing validation logic
```

## Related Features

- **Soft Schema** - `docs/SOFT_SCHEMA_FEATURE.md`
- **Citations** - `docs/CITATIONS.md`
- **AI API Client** - `src/shared/ai_api_client.py`

## FAQ

**Q: What if the LLM finds a better URL than what's in citations?**

A: The warning is informational. You can:
- Accept the URL as valid (LLM reasoning may be correct)
- Manually verify the URL
- Filter out URLs with warnings in post-processing

**Q: Does this slow down API calls?**

A: No. URL validation runs after the API call completes, with minimal overhead (< 10ms for typical responses).

**Q: What about URLs in different formats (shortened URLs, redirects)?**

A: The system validates against what's in citations. If citations have shortened URLs, those will match. Redirects are not followed.

**Q: Can I disable URL validation?**

A: Currently no. It's a lightweight post-processing step with graceful error handling. If needed, you could modify the code to add a flag.

## Version History

- **2025-10-23:** Initial implementation
  - Automatic URL validation against citations
  - Fuzzy matching with domain-aware scoring
  - Recursive validation through data structures
  - Warning annotations for unvalidated URLs
  - Silent exact matches (no log noise)
