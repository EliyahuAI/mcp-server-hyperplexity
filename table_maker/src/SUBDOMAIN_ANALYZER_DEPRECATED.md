# Subdomain Analyzer - Deprecation Notice

**Component:** `subdomain_analyzer.py`
**Status:** DEPRECATED
**Date Deprecated:** October 20, 2025
**Deprecated By:** Architecture revision for integrated row discovery

---

## Why Deprecated

The subdomain analyzer component is no longer needed because **subdomains are now defined directly in the column definition step**, eliminating the need for a separate AI call.

### Old Architecture (Deprecated)

```
Column Definition → search_strategy (description + hints) →
  Subdomain Analysis (separate AI call) → subdomains (2-5) →
    Row Discovery
```

**Problems:**
- Extra AI call (adds ~3-5 seconds and ~$0.01-0.02 per table)
- Subdomains designed without full column context
- Two-step process when one would suffice

### New Architecture (Current)

```
Column Definition → columns + search_strategy + subdomains →
  Row Discovery (uses subdomains directly)
```

**Benefits:**
- One fewer AI call (faster, cheaper)
- Subdomains designed with full column context
- More coherent, integrated search strategy

---

## What Replaced It

### New Schema: `column_definition_response.json`

Subdomains are now part of the `search_strategy` object:

```json
{
  "columns": [...],
  "search_strategy": {
    "description": "Find AI companies actively hiring across multiple sectors",
    "subdomains": [
      {
        "name": "AI Research Companies",
        "focus": "Academic and research-focused AI organizations",
        "search_queries": [
          "top AI research labs hiring 2024",
          "machine learning research companies with job openings"
        ],
        "target_rows": 7
      },
      {
        "name": "Healthcare AI",
        "focus": "AI companies in healthcare and biotech",
        "search_queries": [
          "healthcare AI companies hiring",
          "medical AI startups recruiting"
        ],
        "target_rows": 7
      },
      {
        "name": "Enterprise AI",
        "focus": "B2B AI solutions and platforms",
        "search_queries": [
          "enterprise AI software companies hiring",
          "B2B AI automation platforms"
        ],
        "target_rows": 6
      }
    ]
  },
  "table_name": "AI Companies Hiring Status"
}
```

### Key Changes

1. **Subdomains Array** (2-5 subdomains):
   - `name`: Short descriptive name
   - `focus`: Detailed description of subdomain scope
   - `search_queries`: List of focused queries for this subdomain
   - `target_rows`: How many rows to discover for this subdomain

2. **Target Row Distribution**:
   - Total `target_rows` across subdomains = `target_row_count × discovery_multiplier`
   - Example: For 20 final rows with 1.5x multiplier → find 30 total (10+10+10 across 3 subdomains)

3. **Query Prioritization**:
   - Multi-row queries preferred (lists, directories, comparisons)
   - Single-entity queries used sparingly

---

## Migration Guide

### Before (Deprecated)

```python
from subdomain_analyzer import SubdomainAnalyzer

# Step 1: Define columns
column_result = await column_handler.define_columns(conversation_context)

# Step 2: Analyze subdomains (SEPARATE CALL)
subdomain_analyzer = SubdomainAnalyzer(ai_client, prompt_loader, schema_validator)
subdomain_result = await subdomain_analyzer.analyze(
    search_strategy=column_result['search_strategy']
)

# Step 3: Row discovery
discovery_result = await row_discovery.discover_rows(
    search_strategy=column_result['search_strategy'],
    subdomains=subdomain_result['subdomains'],  # From separate call
    columns=column_result['columns'],
    target_row_count=20
)
```

### After (Current)

```python
# Step 1: Define columns (now includes subdomains)
column_result = await column_handler.define_columns(conversation_context)

# Subdomains are already in column_result['search_strategy']['subdomains']

# Step 2: Row discovery (uses subdomains from column_result)
discovery_result = await row_discovery.discover_rows(
    search_strategy=column_result['search_strategy'],  # Contains subdomains
    columns=column_result['columns'],
    target_row_count=20
)
```

**Difference:** No separate subdomain analysis call needed!

---

## Code Reference

The deprecated code is kept in `subdomain_analyzer.py` for reference. Key components:

- **`SubdomainAnalyzer.analyze()`**: Main method that analyzed search strategies
- **Subdomain schema**: `schemas/subdomain_analysis_response.json`
- **Prompt template**: `prompts/subdomain_analysis.md`

### When You Might Need It

This component could be useful in the future if:

1. **Manual subdomain splitting** is needed outside column definition
2. **Re-splitting** existing search strategies into finer granularity
3. **Debugging** subdomain quality for existing strategies

However, for the standard table generation flow, it is no longer used.

---

## Test Changes

### Deprecated Tests

**File:** `tests/test_subdomain_analyzer.py`

All tests are marked with:
```python
@pytest.mark.skip(reason="Component deprecated - subdomains now in column_definition")
```

Tests are kept for reference but will not run in the standard test suite.

### Updated Tests

The following tests have been updated for the new architecture:

1. **`test_column_definition_handler.py`**:
   - Added tests for subdomain output in search_strategy
   - Validates subdomain count (2-5)
   - Tests target_rows distribution

2. **`test_row_discovery.py`**:
   - Updated to use subdomains from search_strategy
   - Removed subdomain analyzer mock setup
   - Tests sequential and parallel modes

3. **`test_integration_row_discovery.py`**:
   - Removed subdomain analysis step from flow
   - Updated to use integrated subdomains

---

## Performance Impact

### Before (Deprecated Architecture)

- **Column Definition:** ~25-30s
- **Subdomain Analysis:** ~3-5s
- **Row Discovery:** ~60-90s
- **Total:** ~90-125s

### After (New Architecture)

- **Column Definition (with subdomains):** ~28-32s
- **Row Discovery:** ~60-90s
- **Total:** ~90-120s

**Net Savings:** ~3-5 seconds per table, ~$0.01-0.02 in API costs

---

## Related Documentation

- **Architecture Document:** `docs/REVISED_ARCHITECTURE_ROW_DISCOVERY.md`
- **Column Definition Schema:** `schemas/column_definition_response.json`
- **Row Discovery:** `src/row_discovery.py`

---

## Questions?

If you have questions about this deprecation or need to use subdomain analysis for a special case, consult:

1. The revised architecture document
2. The column definition handler implementation
3. The integration tests showing the new flow

The deprecated code remains available in `subdomain_analyzer.py` for reference.
