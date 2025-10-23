# Soft Schema Feature

## Overview

The **soft_schema** feature provides flexible JSON schema validation for AI API responses, allowing LLMs to return more comprehensive results while maintaining structured output quality.

## Problem It Solves

### Hard Schema Limitation

When using strict JSON schema enforcement via API parameters (`response_format` for Perplexity, `tools` for Anthropic), LLMs become overly conservative:

**Example Test Results:**
- ✗ Hard schema (Perplexity): **0 candidates** found
- ✓ Soft schema (Perplexity): **20 candidates** found
- **20x improvement** in result quality

The hard schema causes the LLM to:
- Be overly strict about matching criteria
- Return empty results when uncertain
- Provide minimal output to ensure perfect schema compliance

### Soft Schema Solution

Soft schema requests JSON structure via **prompt instructions only** (not API enforcement), then:
1. Cleans and extracts JSON from responses
2. Validates structure with flexible matching
3. Normalizes types and field names
4. Logs warnings instead of failing
5. Automatically falls back to hard schema if soft schema fails

## Usage

### In Row Discovery (Already Enabled)

Row discovery uses `soft_schema=True` by default for maximum result quality:

```python
# src/lambdas/interface/actions/table_maker/table_maker_lib/row_discovery_stream.py
result = await self.ai_client.call_structured_api(
    prompt=prompt,
    schema=schema,
    model=scoring_model,
    soft_schema=True  # ← Enabled for row discovery
)
```

### In Other Components (Hard Schema)

QC reviewer and subdomain analyzer use hard schema (`soft_schema=False`, the default):
- QC reviewer: Needs strict validation for quality control
- Subdomain analyzer: Returns structured metadata, not search results

### Manual Usage

To use soft schema in your own code:

```python
from ai_api_client import AIAPIClient

client = AIAPIClient()

result = await client.call_structured_api(
    prompt="Find biotech companies...",
    schema=your_json_schema,
    model="sonar-pro",  # Works with Perplexity or Anthropic
    soft_schema=True,   # ← Enable soft schema
    use_cache=False
)
```

## How It Works

### 1. Response Cleaning

**Perplexity:**
```python
# Handles responses like:
"Here are the results:\n```json\n{...}\n```"

# Becomes:
"{...}"
```

**Anthropic:**
```python
# Extracts from content blocks:
[{"type": "text", "text": "Here's the JSON:\n{...}"}]

# Becomes:
"{...}"
```

**Cleaning Steps:**
1. Strip markdown code fences (````json ... ````)
2. Extract JSON from prose using regex (`\{.*\}`)
3. Parse and validate JSON structure

### 2. Flexible Validation

#### A. Fuzzy Key Matching

Handles field name variations:

```python
# LLM returns:
{"company_name": "Acme Corp"}

# Schema expects:
{"Company Name": "..."}

# System fuzzy-matches (80% threshold):
"company_name" → "Company Name" (similarity: 0.85)
```

**Supported Variations:**
- Case: `Company`, `company`, `COMPANY`
- Separators: `company_name`, `company-name`, `company name`
- Combined: `CompanyName`, `companyName`, `COMPANY_NAME`

#### B. Type Coercion

Automatically converts types:

```python
# String → Number
"0.95" → 0.95

# String → Integer
"42.0" → 42

# String → Boolean
"true" → true
"yes" → true
"1" → true

# Non-array → Array
"single_value" → ["single_value"]
```

#### C. Recursive Validation

Validates nested structures:

```python
{
  "candidates": [  # Array validation
    {
      "id_values": {  # Nested object validation
        "company_name": "Acme"  # Fuzzy match + type coerce
      },
      "score_breakdown": {  # Nested object validation
        "relevancy": "0.95"  # Type coercion
      }
    }
  ]
}
```

### 3. Error Handling

**Warnings (Not Failures):**
- Missing optional fields → logged as warnings
- Extra fields → accepted (allowed with soft schema)
- Type mismatches → attempt coercion, warn if fails
- Fuzzy key matches → logged for transparency

**Failures Saved to Debug Folder:**
```python
# All failures saved to S3 debug folder:
- JSON decode errors
- Schema validation issues
- Cleaning/extraction errors

# Debug files include:
- Original response
- Cleaned content
- Schema used
- Error details
```

### 4. Automatic Fallback

If soft schema fails, automatically retries with hard schema:

```python
try:
    # Try soft schema first
    result = call_api(soft_schema=True)
except:
    logger.warning("[SOFT_SCHEMA_FALLBACK] Retrying with hard schema")
    result = call_api(soft_schema=False)  # Fallback
```

**Fallback Behavior:**
- Only attempts on first model (not backup models)
- Logs fallback attempts
- Marks result with `soft_schema_fallback: true`
- Preserves all error context in debug folder

## Performance Comparison

### Test Results: Row Discovery for Biotech GenAI Jobs

| Configuration | Schema Type | Candidates | Output Tokens | Processing |
|---------------|-------------|------------|---------------|------------|
| Hard Schema   | API enforced | **0** | 266 | 8.2s |
| Soft Schema   | Prompt only  | **20** | 3,505 | Similar |

**Key Findings:**
- **20x more results** with soft schema
- **13x more output tokens** (more comprehensive)
- Similar processing time
- Same cost per token

### Specific Example

**Query:** "Find midsized biotech companies hiring for GenAI leadership roles"

**Hard Schema Result:**
```json
{
  "subdomain": "Company Career Pages",
  "no_matches_reason": "No specific job postings found...",
  "candidates": []
}
```

**Soft Schema Result:**
```json
{
  "subdomain": "Company Career Pages",
  "candidates": [
    {"id_values": {"Company Name": "AbbVie", ...}, ...},
    {"id_values": {"Company Name": "Eli Lilly", ...}, ...},
    {"id_values": {"Company Name": "Gilead Sciences", ...}, ...},
    // ... 17 more candidates
  ]
}
```

## Validation Features

### 1. Extra Fields Allowed

```python
# LLM adds helpful extra fields:
{
  "subdomain": "...",
  "candidates": [...],
  "search_strategy_used": "...",  # ← Extra field
  "confidence_level": "high"       # ← Extra field
}

# Result: Accepted with soft schema ✓
```

### 2. Type Flexibility

```python
# LLM returns mixed types:
{
  "score_breakdown": {
    "relevancy": "0.95",    # String
    "reliability": 1.0,      # Number
    "recency": 0.9          # Number
  }
}

# Result: All coerced to float ✓
```

### 3. Key Variations

```python
# LLM uses different casing:
{
  "id_values": {
    "job_posting_url": "...",  # lowercase
    "Company Name": "...",      # Title Case
    "JOB_TITLE": "..."         # UPPERCASE
  }
}

# Result: All fuzzy-matched to schema keys ✓
```

## Debugging

### Log Messages

**Soft Schema Active:**
```
INFO:[SOFT_SCHEMA] Using soft schema - JSON requested in prompt only, no API enforcement
INFO:[SOFT_SCHEMA] Successfully cleaned and validated response JSON
```

**Fuzzy Matching:**
```
INFO:[FUZZY_MATCH] Matched 'company_name' → 'Company Name' (similarity: 0.85)
```

**Type Coercion:**
```
INFO:[TYPE_COERCE] Coerced 'relevancy': "0.95" (str) → 0.95 (number)
```

**Validation Warnings:**
```
WARNING:[SOFT_SCHEMA] Schema validation warnings: ['Missing required field: source_urls']
```

**Fallback:**
```
WARNING:[SOFT_SCHEMA_FALLBACK] Soft schema failed, retrying with hard schema
INFO:[SOFT_SCHEMA_FALLBACK] Hard schema succeeded
```

### Debug Files

All failures saved to S3 debug folder with context:

**JSON Decode Failures:**
```
s3://bucket/debug/perplexity/json_decode_error/YYYY-MM-DD/...json
```
Contains:
- `raw_content`: Original response
- `cleaned_content`: After fence stripping
- Error details

**Schema Validation Warnings:**
```
s3://bucket/debug/perplexity/schema_validation_warnings/YYYY-MM-DD/...json
```
Contains:
- `original`: Pre-normalization JSON
- `normalized`: Post-normalization JSON
- `warnings`: List of validation issues
- `schema`: Expected schema

**Cleaning Errors:**
```
s3://bucket/debug/perplexity/cleaning_error/YYYY-MM-DD/...json
```
Contains:
- `response`: Full API response
- Error stack trace
- Context

## When to Use Soft Schema

### ✅ **Use Soft Schema When:**
- **Search/discovery tasks** - Finding entities, companies, jobs, etc.
- **Exploratory queries** - Open-ended research questions
- **High result count needed** - Target: 20-40+ items
- **Perplexity models** - Particularly benefits from soft schema

### ❌ **Use Hard Schema When:**
- **Quality control** - Strict validation required
- **Metadata generation** - Structured config/settings
- **Financial/critical data** - No tolerance for fuzzy matching
- **Small result sets** - Single item or 2-3 items

## Configuration

### Current Settings (by Component)

| Component | soft_schema | Rationale |
|-----------|-------------|-----------|
| **row_discovery_stream** | `True` | Search task, needs comprehensive results |
| **subdomain_analyzer** | `False` | Metadata generation, needs strict structure |
| **qc_reviewer** | `False` | Quality control, needs strict validation |

### Override Settings

To change soft_schema for a component, modify the `call_structured_api` call:

```python
result = await self.ai_client.call_structured_api(
    prompt=prompt,
    schema=schema,
    model=model,
    soft_schema=True,  # ← Change this
    # ... other params
)
```

## Advanced Features

### Recursive Normalization

Validates and normalizes nested structures:

```python
# Input:
{
  "candidates": [
    {
      "id_values": {
        "company_name": "Acme",  # ← Will fuzzy match
        "role": "Director"
      },
      "score_breakdown": {
        "relevancy": "0.95"  # ← Will coerce to float
      }
    }
  ]
}

# After normalization:
{
  "candidates": [
    {
      "id_values": {
        "Company Name": "Acme",  # ← Fuzzy matched
        "Role": "Director"
      },
      "score_breakdown": {
        "relevancy": 0.95  # ← Coerced to float
      }
    }
  ]
}
```

### Similarity Threshold

Default fuzzy matching threshold is **0.8 (80%)**. To adjust:

```python
def _fuzzy_match_keys(self, data: Dict, schema_properties: Dict, threshold: float = 0.8):
    # Change threshold here ↑
```

**Examples of matches:**
- `0.9+`: `"company_name"` ↔ `"Company Name"`
- `0.8-0.9`: `"job_title"` ↔ `"Job Title"`
- `<0.8`: No match, keeps original key

## Implementation Details

### Location

All soft schema code is in:
```
src/shared/ai_api_client.py
```

**Key Methods:**
- `call_structured_api()` - Main entry point, accepts `soft_schema` param
- `_make_single_perplexity_structured_call()` - Handles Perplexity soft schema
- `_make_single_anthropic_call()` - Handles Anthropic soft schema
- `_clean_soft_schema_response()` - Cleans Perplexity responses
- `_clean_anthropic_soft_schema_response()` - Cleans Anthropic responses
- `_validate_and_normalize_soft_schema()` - Validates/normalizes JSON
- `_fuzzy_match_keys()` - Fuzzy key matching
- `_coerce_value_to_type()` - Type coercion

### API Differences

**Perplexity (with soft_schema=True):**
```python
# API request does NOT include:
"response_format": {
    "type": "json_schema",
    "json_schema": {...}
}

# Just sends:
"messages": [{"role": "user", "content": prompt}]
```

**Anthropic (with soft_schema=True):**
```python
# API request does NOT include:
"tools": [...],
"tool_choice": {...}

# Just sends:
"messages": [{"role": "user", "content": prompt + "\n\nIMPORTANT: Return valid JSON only"}]
```

## Testing

### Test Scripts

**Basic Integration Test:**
```bash
python3 test_soft_schema_integration.py
```

**Comprehensive Test (Both Providers):**
```bash
python3 test_soft_schema_complete.py
```

**Full Comparison (Hard vs Soft):**
```bash
python3 test_schema_in_prompt.py
```

### Expected Output

```
[INFO] Starting comprehensive soft_schema tests
================================================================================
TEST 1: Perplexity with Soft Schema
================================================================================
[RESULT] Found 3 candidates
================================================================================
TEST 2: Anthropic (Claude) with Soft Schema
================================================================================
[RESULT] Found 3 candidates
================================================================================
TEST SUMMARY
================================================================================
Perplexity Soft Schema: PASS
Anthropic Soft Schema:  PASS
================================================================================
[SUCCESS] All tests passed!
```

## Monitoring

### Log Levels

**INFO:** Normal operation
```
INFO:[SOFT_SCHEMA] Using soft schema - JSON requested in prompt only
INFO:[SOFT_SCHEMA] Successfully cleaned and validated response JSON
INFO:[FUZZY_MATCH] Matched 'company_name' → 'Company Name' (similarity: 0.85)
INFO:[TYPE_COERCE] Coerced 'relevancy': "0.95" (str) → 0.95 (number)
```

**WARNING:** Issues handled gracefully
```
WARNING:[SOFT_SCHEMA] Schema validation warnings: ['Missing required field: X']
WARNING:[SOFT_SCHEMA_FALLBACK] Soft schema failed, retrying with hard schema
```

**ERROR:** Critical failures (saved to debug folder)
```
ERROR:[SOFT_SCHEMA] Response content is not valid JSON after cleaning
ERROR:[SOFT_SCHEMA] Error cleaning response: ...
```

### Debug Folder Structure

```
s3://bucket/debug/
├── perplexity/
│   ├── json_decode_error/
│   │   └── YYYY-MM-DD/
│   │       └── timestamp_model.json
│   ├── schema_validation_warnings/
│   │   └── YYYY-MM-DD/
│   │       └── timestamp_model.json
│   └── cleaning_error/
│       └── YYYY-MM-DD/
│           └── timestamp_model.json
└── anthropic/
    ├── json_decode_error/
    ├── schema_validation_warnings/
    └── cleaning_error/
```

## Best Practices

### 1. Use for Search Tasks

```python
# Good: Search/discovery tasks
result = await client.call_structured_api(
    prompt="Find companies hiring for AI roles",
    schema=row_discovery_schema,
    soft_schema=True  # ✓ Recommended
)
```

### 2. Use Hard Schema for Critical Data

```python
# Good: Quality control, validation, critical metadata
result = await client.call_structured_api(
    prompt="Review this data for quality issues",
    schema=qc_schema,
    soft_schema=False  # ✓ Recommended (default)
)
```

### 3. Monitor Debug Folder

Regularly check debug folder for:
- Repeated JSON decode errors → prompt needs improvement
- Frequent fuzzy matches → consider standardizing field names
- Validation warnings → schema may be too strict

### 4. Test Both Modes

When implementing new features, test both:
```python
# Test hard schema
result_hard = await call_api(soft_schema=False)

# Test soft schema
result_soft = await call_api(soft_schema=True)

# Compare result quality
```

## Troubleshooting

### Issue: Empty Results with Soft Schema

**Check:**
1. Review debug folder for JSON decode errors
2. Check logs for fuzzy match/type coerce messages
3. Verify prompt includes JSON format instructions

**Solution:**
```python
# Ensure prompt has clear JSON format example:
prompt = """
...
Return JSON in this format:
```json
{
  "subdomain": "...",
  "candidates": [...]
}
```
"""
```

### Issue: Soft Schema Always Falls Back to Hard

**Check:**
1. Debug folder for parsing errors
2. Log for specific error messages
3. Response format (prose vs JSON)

**Solution:**
- May need to improve prompt clarity
- Check if LLM is returning valid JSON
- Review JSON extraction regex

### Issue: Fuzzy Matches Incorrect

**Check:**
1. Log messages showing match scores
2. Debug folder for validation warnings

**Solution:**
```python
# Adjust similarity threshold in _fuzzy_match_keys:
def _fuzzy_match_keys(self, data, schema_properties, threshold=0.85):
    # Increase threshold ↑ for stricter matching
```

## Future Enhancements

Potential improvements (not yet implemented):

1. **Configurable fuzzy threshold** - Pass as parameter
2. **Custom type coercers** - Register custom type conversions
3. **Schema learning** - Auto-detect common variations
4. **Validation metrics** - Track fuzzy match/coercion rates
5. **Pydantic integration** - Use Pydantic models for validation

## Related Documentation

- **Table Maker Guide:** `docs/TABLE_MAKER_GUIDE.md`
- **AI API Client:** `src/shared/ai_api_client.py`
- **Row Discovery:** `src/lambdas/interface/actions/table_maker/table_maker_lib/row_discovery_stream.py`

## Version History

- **2025-10-23:** Initial implementation
  - Soft schema for Perplexity and Anthropic
  - Fuzzy key matching
  - Type coercion
  - Automatic fallback
  - Debug folder integration
