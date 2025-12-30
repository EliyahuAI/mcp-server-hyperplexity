# Table Extractor Cost Tracking & Metadata

## Overview

The table extractor currently executes multiple strategies (Jina, Search API + Gemini, HTML, etc.) but doesn't aggregate costs or return detailed metadata like the_clone does.

This document outlines the implementation plan for comprehensive cost tracking and metadata reporting.

---

## Reference: the_clone Metadata Format

**What the_clone returns:**

```python
{
    'answer': {...},  # Extracted data
    'citations': [...],  # Source citations
    'metadata': {
        'total_cost': 0.0534,
        'processing_time': 96.6,
        'snippets_extracted': 12,

        # Cost by provider
        'cost_by_provider': {
            'perplexity': {'cost': 0.015, 'calls': 3},
            'vertex': {'cost': 0.038, 'calls': 6},
            'gemini': {'cost': 0.0003, 'calls': 1},
            'anthropic': {'cost': 0.0, 'calls': 0}
        },

        # Cost by stage
        'cost_breakdown': {
            'initial': 0.001,
            'search': 0.015,
            'triage': 0.005,
            'extraction': 0.020,
            'synthesis': 0.012
        },

        # Additional metadata
        'strategy_used': 'extraction',
        'breadth': 'narrow',
        'depth': 'extraction',
        'synthesis_tier': 'tier2',
        'model_used': 'gemini-2.5-flash'
    }
}
```

---

## Required: Table Extractor Metadata Format

**What table_extractor should return:**

```python
{
    'success': True,
    'url': 'https://fortune.com/ranking/fortune500/',
    'table_name': 'Fortune 500',
    'rows': [...],  # Extracted table rows
    'rows_extracted': 255,
    'extraction_complete': True,
    'confidence': 'HIGH',
    'citations': [...],

    # NEW: Comprehensive metadata
    'metadata': {
        # Overall metrics
        'total_cost': 0.0450,
        'processing_time': 45.2,
        'strategy_used': 'search_api_gemini',
        'iterations_used': 1,

        # Strategy execution chain (what was tried)
        'strategies_attempted': [
            {'name': 'jina_reader', 'success': False, 'error': 'HTTP 451'},
            {'name': 'search_api_gemini', 'success': True, 'rows': 255}
        ],

        # Cost by provider
        'cost_by_provider': {
            'perplexity': {'cost': 0.015, 'calls': 1},  # Search API
            'gemini': {'cost': 0.030, 'calls': 10},      # Parallel extractions
            'anthropic': {'cost': 0.0, 'calls': 0},
            'vertex': {'cost': 0.0, 'calls': 0}
        },

        # Cost by stage (table extractor specific)
        'cost_breakdown': {
            'jina_fetch': 0.0,          # Free
            'search_api': 0.015,        # Perplexity Search API
            'parallel_extraction': 0.030, # 10 × Gemini calls
            'iteration': 0.0,           # No iteration needed
            'synthesis': 0.0            # N/A for this strategy
        },

        # Extraction details
        'extraction_details': {
            'search_api_calls': 1,
            'search_results_found': 10,
            'sources_processed': 10,
            'parallel_gemini_calls': 10,
            'rows_before_dedup': 270,
            'rows_after_dedup': 255,
            'duplicates_removed': 15
        },

        # Performance metrics
        'performance': {
            'time_by_stage': {
                'jina': 0.5,
                'search_api': 3.2,
                'parallel_extraction': 38.5,
                'deduplication': 0.3
            },
            'tokens_by_provider': {
                'gemini': {'input': 45000, 'output': 12000}
            }
        }
    }
}
```

---

## Implementation Requirements

### 1. **Cost Tracking Per Strategy**

Each strategy method should track its own costs:

```python
async def _try_jina_extraction(self, ...) -> Dict[str, Any]:
    result = {
        'success': False,
        'rows': [],
        'metadata': {
            'cost': 0.0,  # Jina is free
            'processing_time': 0.0,
            'api_calls': 0
        }
    }
    # ... extraction logic
    return result
```

### 2. **Aggregate Costs Across Strategies**

In the main `extract_table()` method:

```python
async def extract_table(self, ...):
    total_cost = 0.0
    cost_by_provider = {}
    strategies_attempted = []

    # Try Strategy 1: Jina
    jina_result = await self._try_jina_extraction(...)
    strategies_attempted.append({
        'name': 'jina_reader',
        'success': jina_result['success'],
        'cost': jina_result['metadata']['cost'],
        'time': jina_result['metadata']['processing_time']
    })

    if jina_result['success']:
        # Build final metadata
        return {
            'success': True,
            'rows': jina_result['rows'],
            'metadata': self._build_metadata(
                strategies_attempted,
                total_cost,
                cost_by_provider
            )
        }

    # Try Strategy 2: Search API + Gemini
    # ... (accumulate costs)
```

### 3. **Extract Costs from API Responses**

```python
def _extract_cost_from_response(self, api_response: Dict) -> Dict:
    """Extract cost and provider info from API response."""
    enhanced_data = api_response.get('enhanced_data', {})
    call_info = enhanced_data.get('call_info', {})

    return {
        'cost': call_info.get('cost', 0.0),
        'provider': call_info.get('api_provider', 'unknown'),
        'model': api_response.get('model_used', 'unknown'),
        'tokens': api_response.get('token_usage', {})
    }
```

### 4. **Build Final Metadata**

```python
def _build_metadata(
    self,
    strategies_attempted: List[Dict],
    total_cost: float,
    cost_by_provider: Dict,
    extraction_details: Dict = None
) -> Dict:
    """Build comprehensive metadata for table extraction result."""

    successful_strategy = next(
        (s for s in strategies_attempted if s['success']),
        strategies_attempted[-1]
    )

    return {
        'total_cost': total_cost,
        'processing_time': sum(s['time'] for s in strategies_attempted),
        'strategy_used': successful_strategy['name'],
        'strategies_attempted': strategies_attempted,
        'cost_by_provider': cost_by_provider,
        'extraction_details': extraction_details or {}
    }
```

---

## Implementation Plan

### Phase 1: Basic Cost Tracking

**Files to modify:**
- `src/shared/table_extractor.py` - Add cost tracking to each strategy method

**Changes needed:**
1. Track API response metadata in each strategy
2. Extract cost/provider from enhanced_data
3. Accumulate costs across strategies
4. Return basic metadata dict

**Estimated effort:** 2-3 hours

---

### Phase 2: Detailed Breakdown

**Additional tracking:**
- Cost by stage (jina, search_api, extraction, iteration)
- Token usage by provider
- Timing breakdown by stage
- Extraction details (sources processed, dedup stats)

**Estimated effort:** 1-2 hours

---

### Phase 3: Integration

**Update table_maker to use metadata:**
- Log costs to DynamoDB
- Include in Excel reports
- Track extraction efficiency metrics

**Estimated effort:** 1-2 hours

---

## Example Usage

### Current (no metadata):

```python
result = await extractor.extract_table(
    url='https://fortune.com/ranking/fortune500/',
    table_name='Fortune 500',
    expected_columns=['Rank', 'Company', 'Revenue'],
    estimated_rows=100
)

print(f"Rows: {result['rows_extracted']}")
# No cost information available!
```

### After implementation:

```python
result = await extractor.extract_table(
    url='https://fortune.com/ranking/fortune500/',
    table_name='Fortune 500',
    expected_columns=['Rank', 'Company', 'Revenue'],
    estimated_rows=100
)

print(f"Rows: {result['rows_extracted']}")
print(f"Cost: ${result['metadata']['total_cost']:.4f}")
print(f"Strategy: {result['metadata']['strategy_used']}")
print(f"Providers: {list(result['metadata']['cost_by_provider'].keys())}")

# Detailed breakdown
for provider, info in result['metadata']['cost_by_provider'].items():
    print(f"  {provider}: ${info['cost']:.4f} ({info['calls']} calls)")
```

---

## Cost Estimation Examples

### Search API + Gemini (Parallel) - Typical Run

**Fortune 500 extraction (255 rows):**
```
Search API: 1 call × $0.005 = $0.015
Gemini 2.0 Flash: 10 parallel calls × $0.003 = $0.030
Total: $0.045

Time: ~40s (parallel processing)
Efficiency: 5.7 rows per cent
```

### the_clone Extraction - Typical Run

**Fortune 500 extraction (68 rows):**
```
Perplexity Search: 1 call × $0.005 = $0.015
DeepSeek Synthesis: 1 call × $0.020 = $0.020
Gemini Extraction: 5 calls × $0.0005 = $0.0025
Total: $0.038

Time: ~60s
Efficiency: 1.8 rows per cent
```

### HTML Direct - Best Case

**S&P 500 extraction (503 rows):**
```
HTML fetch: Free
BeautifulSoup parsing: Free
Total: $0.000

Time: ~2s
Efficiency: ∞ rows per cent (free!)
```

---

## Metrics to Track

### Essential Metrics:

1. **Total cost** - Sum of all API calls
2. **Cost by provider** - Perplexity, Gemini, Vertex, Anthropic
3. **Strategy used** - Which strategy succeeded
4. **Processing time** - Total time elapsed
5. **Rows extracted** - Final row count

### Advanced Metrics:

6. **Cost per row** - Efficiency metric
7. **Strategies attempted** - Full fallback chain
8. **Parallel extraction details** - Sources processed, dedup stats
9. **Token usage** - Input/output tokens by provider
10. **Cache hits** - Cost savings from caching

---

## Next Steps

1. Implement cost tracking in each strategy method
2. Aggregate costs in main extract_table() method
3. Build metadata dict with comprehensive breakdowns
4. Add cost logging to table_maker
5. Update Excel reports to show extraction costs
6. Create cost analysis dashboard

---

## Expected Benefits

**For users:**
- Understand extraction costs per table
- Compare strategy efficiency
- Optimize for cost vs completeness

**For developers:**
- Debug expensive extractions
- Identify optimization opportunities
- Track cost trends over time

**For business:**
- Budget planning
- Cost attribution
- ROI analysis

---

## File Structure

```
src/shared/table_extractor.py
├── extract_table() - Main method, aggregates all costs
├── _try_jina_extraction() - Tracks Jina costs (free)
├── _try_search_api_extraction() - Tracks Search API + Gemini costs
├── _try_html_extraction() - Tracks HTML costs (free)
├── _try_ai_extraction() - Tracks Gemini direct costs
├── _extract_iteratively() - Tracks iteration costs
├── _try_search_extraction() - Tracks the_clone extraction costs
└── _build_metadata() - NEW: Aggregates all metadata
```

---

**Ready to implement!** This will give table_maker the same detailed cost visibility that the_clone provides.
