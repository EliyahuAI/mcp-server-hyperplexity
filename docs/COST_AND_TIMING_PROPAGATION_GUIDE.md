# Cost and Timing Propagation Guide

## Overview

This document provides a comprehensive guide to how cost and timing data flows from the AI API Client through the validation system to final cost calculations and storage. This guide serves as a complete reference for understanding, debugging, and maintaining the cost tracking system.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Enhanced Data Generation](#enhanced-data-generation)
3. [Data Flow Through Validation Lambda](#data-flow-through-validation-lambda)
4. [Enhanced Data Aggregation](#enhanced-data-aggregation)
5. [Three-Tier Cost System](#three-tier-cost-system)
6. [Storage and Persistence](#storage-and-persistence)
7. [Key Functions and Variables Reference](#key-functions-and-variables-reference)
8. [Troubleshooting Common Issues](#troubleshooting-common-issues)

## System Architecture

The cost and timing system operates on a three-tier architecture:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   AI API Calls  │───▶│   Aggregation   │───▶│  Business Logic │
│  (Per Request)  │    │  (Per Session)  │    │ (Final Pricing) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
     enhanced_data         aggregated_data       three_cost_tiers
```

### Three Cost Tiers:
1. **cost_actual**: What was actually paid (with caching benefits)
2. **cost_estimated**: Raw cost estimate without caching benefits
3. **cost_quoted**: What the user pays (estimated × multiplier + business rules)

## Enhanced Data Generation

### Location
**File**: `/src/shared/ai_api_client.py`
**Primary Function**: `get_enhanced_call_metrics()` (lines 722-845)

### Purpose
Every AI API call generates comprehensive metrics including costs, timing, tokens, and caching efficiency.

### Enhanced Data Structure

```python
enhanced_metrics = {
    # Basic call information
    'call_info': {
        'model': str,                    # Model used (e.g., "claude-3-5-sonnet-20241022")
        'api_provider': str,             # "anthropic" or "perplexity"
        'timestamp': str,                # ISO format timestamp
        'search_context_size': str       # For Perplexity: "low", "medium", "high"
    },
    
    # Token usage breakdown
    'tokens': {
        'input_tokens': int,             # Input tokens used
        'output_tokens': int,            # Output tokens generated
        'total_tokens': int,             # Sum of input + output tokens
        'cache_creation_tokens': int,    # Tokens used for cache creation (Anthropic)
        'cache_read_tokens': int         # Tokens read from cache (Anthropic)
    },
    
    # Cost breakdown with caching analysis
    'costs': {
        # TIER 1: Actual costs (with caching benefits)
        'actual': {
            'input_cost': float,         # Actual input cost paid
            'output_cost': float,        # Actual output cost paid
            'total_cost': float,         # TIER 1: cost_actual
            'pricing_source': str        # Source of pricing data
        },
        
        # TIER 2: Estimated costs without caching benefits
        'estimated': {
            'input_cost': float,         # Input cost without cache
            'output_cost': float,        # Output cost without cache
            'total_cost': float          # TIER 2: cost_estimated
        },
        
        # Cost efficiency from caching
        'cache_savings': {
            'absolute_savings': float,   # Dollars saved from caching
            'percentage_savings': float  # Percentage saved from caching
        }
    },
    
    # Timing breakdown
    'timing': {
        'time_actual_seconds': float,    # Actual processing time
        'time_estimated_seconds': float, # Estimated time without cache
        'time_savings_seconds': float,   # Time saved from caching
        'time_savings_percent': float    # Percentage time saved
    },
    
    # Caching efficiency metrics
    'caching': {
        'cache_hit': bool,               # Whether cache was hit
        'cache_efficiency': float,       # Cache effectiveness score
        'cache_tokens_ratio': float      # Ratio of cache tokens to total
    },
    
    # Per-row calculations (when batch_info provided)
    'per_row': {
        'cost_actual_per_row': float,    # Actual cost divided by rows
        'cost_estimated_per_row': float, # Estimated cost divided by rows
        'time_per_row_seconds': float    # Processing time per row
    },
    
    # Provider-specific metrics for aggregation
    'provider_metrics': {
        api_provider: {                  # "anthropic" or "perplexity"
            'calls': int,                # Number of calls (always 1 per enhanced_data)
            'tokens': int,               # Total tokens used
            'cost_actual': float,        # TIER 1: Actual cost paid
            'cost_estimated': float,     # TIER 2: Estimated cost without cache
            'time_estimated_seconds': float,  # Time without cache (for scaling)
            'time_actual_seconds': float,     # Actual time with cache benefits
            'cache_hit_tokens': int      # Tokens from cache hits
        }
    }
}
```

### Key Generation Functions

#### `get_enhanced_call_metrics()`
**Parameters**:
- `response`: Dict - API response dictionary
- `model`: str - Model name used
- `processing_time`: float - Actual processing time in seconds
- `search_context_size`: str (optional) - Context size for Perplexity
- `batch_info`: Dict (optional) - Batch size information
- `pre_extracted_token_usage`: Dict (optional) - For cached responses

**Returns**: Complete enhanced_metrics dictionary

#### Helper Functions:
- `_extract_token_usage()`: Extracts token usage from API response
- `calculate_token_costs()`: Calculates actual costs with caching benefits
- `_calculate_cost_without_caching_benefits()`: Calculates estimated costs
- `_extract_caching_metrics()`: Analyzes cache efficiency
- `_calculate_comprehensive_timing_metrics()`: Calculates timing metrics

## Data Flow Through Validation Lambda

### Location
**File**: `/src/lambdas/validation/lambda_function.py`
**Primary Function**: `process_multiplex_group()` (lines 2469+)

### Collection Points

#### 1. API Call Response Collection
```python
# Lines 2602, 2627, 2714, 2732: Enhanced data extraction
enhanced_data = shared_client_result.get('enhanced_data', {})
```

#### 2. Raw Response Storage
```python
# Lines 2647-2660: Raw response with enhanced_data
row_results['_raw_responses'][response_id] = {
    'prompt': str,
    'response': dict,              # API response
    'is_cached': bool,
    'fields': list,               # Validation targets
    'model': str,
    'token_usage': dict,
    'processing_time': float,
    'citations': list,
    'enhanced_data': dict         # Complete enhanced metrics
}
```

#### 3. Enhanced Data Context Addition
```python
# Lines 2867-2885: Add context to enhanced data
enhanced_data_with_context = {
    **enhanced_data,              # Original enhanced metrics
    'context': {
        'row_idx': int,           # Row being processed
        'batch_number': int,      # Batch within row
        'search_group': list      # Fields processed together
    }
}
all_enhanced_call_data.append(enhanced_data_with_context)
```

### Variables Tracking Enhanced Data:
- `enhanced_data`: Per-call enhanced metrics from ai_api_client
- `all_enhanced_call_data`: List of all enhanced_data with context
- `row_results['_raw_responses']`: Raw responses with embedded enhanced_data

## Enhanced Data Aggregation

### Location
**File**: `/src/shared/ai_api_client.py`
**Primary Function**: `aggregate_provider_metrics()` (lines 1021-1155)

### Purpose
Aggregates all individual enhanced_data entries into session-level totals and per-provider breakdowns.

### Aggregation Structure
```python
aggregated_metrics = {
    # Overall totals across all providers
    'totals': {
        'total_calls': int,                    # Total API calls made
        'total_tokens': int,                   # Total tokens across all calls
        'total_cost_actual': float,            # TIER 1: Sum of all actual costs
        'total_cost_estimated': float,         # TIER 2: Sum of all estimated costs
        'total_cache_savings': float,          # Total savings from caching
        'total_time_actual_seconds': float,    # Total actual processing time
        'total_time_estimated_seconds': float, # Total estimated time without cache
        'cache_efficiency_overall': float      # Overall cache efficiency percentage
    },
    
    # Per-provider breakdowns
    'providers': {
        'anthropic': {
            'calls': int,
            'tokens': int,
            'cost_actual': float,              # TIER 1: Anthropic actual costs
            'cost_estimated': float,           # TIER 2: Anthropic estimated costs
            'cache_hit_tokens': int,
            'time_actual_seconds': float,
            'time_estimated_seconds': float,
            'cache_savings': float,
            'cache_efficiency': float
        },
        'perplexity': {
            # Same structure as anthropic
        }
    },
    
    # Per-model breakdowns
    'models': {
        'claude-3-5-sonnet-20241022': {
            # Same metrics as providers
        },
        'sonar-pro': {
            # Same metrics as providers
        }
    },
    
    # Raw enhanced data for detailed analysis
    'raw_enhanced_data': [...]               # All individual enhanced_data entries
}
```

### Key Aggregation Logic
```python
# Lines 1063-1089: Core aggregation loop
for enhanced_data in all_enhanced_call_data:
    provider_metrics = enhanced_data.get('provider_metrics', {})
    
    for provider, metrics in provider_metrics.items():
        # Aggregate TIER 1 costs (actual)
        totals['total_cost_actual'] += metrics.get('cost_actual', 0.0)
        
        # Aggregate TIER 2 costs (estimated)  
        totals['total_cost_estimated'] += metrics.get('cost_estimated', 0.0)
        
        # Provider-specific aggregation
        providers[provider]['cost_actual'] += metrics.get('cost_actual', 0.0)
        providers[provider]['cost_estimated'] += metrics.get('cost_estimated', 0.0)
```

## Three-Tier Cost System

### Location
**File**: `/src/lambdas/interface/handlers/background_handler.py`
**Function**: `lambda_handler()` (lines 585-707)

### Tier Definitions

#### TIER 1: cost_actual (eliyahu_cost)
```python
# Line 590: Extract from aggregated totals
eliyahu_cost = totals.get('total_cost_actual', 0.0)
```
- **Definition**: What was actually paid to AI providers
- **Includes**: Caching benefits (lower cost)
- **Source**: Sum of all `enhanced_data.costs.actual.total_cost`
- **Use Case**: Internal cost tracking, profit calculation

#### TIER 2: cost_estimated (estimated_validation_eliyahu_cost)
```python
# Line 589: Extract from aggregated totals  
cost_estimated = totals.get('total_cost_estimated', 0.0)
```
- **Definition**: Raw cost estimate without caching benefits
- **Excludes**: Caching savings
- **Source**: Sum of all `enhanced_data.costs.estimated.total_cost`
- **Use Case**: Full validation cost projections, capacity planning

#### TIER 3: cost_quoted (quoted_validation_cost)
```python
# Lines 693-707: Apply business rules
multiplier_result = _apply_domain_multiplier_with_validation(email, cost_estimated, session_id)
quoted_full_cost = max(2.0, math.ceil(cost_estimated * multiplier * scaling_factor))
```
- **Definition**: What the user pays
- **Calculation**: `max($2.00, ceiling(cost_estimated × domain_multiplier × scaling_factor))`
- **Source**: Business logic applied to TIER 2
- **Use Case**: User billing, revenue calculation

### Domain Multiplier Logic
```python
# Lines 646-690: Domain-specific pricing
DOMAIN_MULTIPLIERS = {
    '@gmail.com': 4.0,          # Consumer pricing
    '@company.com': 2.5,        # Business pricing
    # Default: 3.0
}

scaling_factor = 1.1            # 10% markup
minimum_charge = 2.0            # $2 minimum
```

## Storage and Persistence

### Location
**File**: `/src/shared/dynamodb_schemas.py`
**Function**: `validate_and_convert_session_result()` (lines 2904-2911)

### DynamoDB Storage Fields
```python
{
    # TIER 1: Actual cost paid
    'eliyahu_cost': float,                              # From totals.total_cost_actual
    
    # TIER 2: Cost without caching benefits
    'estimated_validation_eliyahu_cost': float,         # From totals.total_cost_estimated
    
    # TIER 3: User-facing cost with business rules
    'quoted_validation_cost': float,                    # From background_handler calculation
    
    # Enhanced metrics storage
    'enhanced_token_usage_summary': dict,               # Aggregated metrics summary
    'detailed_cost_breakdown': dict,                    # Per-provider cost breakdown
    
    # Timing metrics
    'total_processing_time': float,                     # Actual processing time
    'estimated_processing_time': float,                 # Estimated time without cache
    'cache_efficiency_percentage': float                # Cache effectiveness
}
```

### Validation Rules
```python
# Lines 2904-2911: Cost validation
if not isinstance(eliyahu_cost, (int, float)) or eliyahu_cost < 0:
    raise ValueError("eliyahu_cost must be non-negative number")

if not isinstance(cost_estimated, (int, float)) or cost_estimated < 0:
    raise ValueError("estimated_validation_eliyahu_cost must be non-negative")

if not isinstance(quoted_cost, (int, float)) or quoted_cost < 2.0:
    raise ValueError("quoted_validation_cost must be >= $2.00")
```

## Key Functions and Variables Reference

### AI API Client (`/src/shared/ai_api_client.py`)

#### Core Enhanced Data Functions:
- **`get_enhanced_call_metrics(response, model, processing_time, ...)`**
  - **Purpose**: Generate comprehensive per-call metrics
  - **Returns**: Complete enhanced_data dictionary
  - **Key Variables**: `enhanced_metrics`, `cost_data`, `cost_estimated`

- **`aggregate_provider_metrics(all_enhanced_call_data)`**
  - **Purpose**: Aggregate all enhanced_data into session totals
  - **Returns**: `aggregated_metrics` with totals and provider breakdowns
  - **Key Variables**: `totals`, `providers`, `models`

- **`calculate_token_costs(token_usage)`**
  - **Purpose**: Calculate actual costs with caching benefits
  - **Returns**: Cost breakdown with TIER 1 costs
  - **Key Variables**: `input_cost`, `output_cost`, `total_cost`

- **`_calculate_cost_without_caching_benefits(token_usage, actual_cost_data)`**
  - **Purpose**: Calculate estimated costs without caching
  - **Returns**: Cost breakdown with TIER 2 costs
  - **Key Variables**: `estimated_input_cost`, `estimated_output_cost`

#### Key Variables:
- **`enhanced_metrics`**: Complete per-call metrics dictionary
- **`cost_data`**: Actual costs with caching benefits (TIER 1)
- **`cost_estimated`**: Estimated costs without caching (TIER 2)
- **`aggregated_metrics`**: Session-level aggregated data
- **`all_enhanced_call_data`**: List of all enhanced_data with context

### Validation Lambda (`/src/lambdas/validation/lambda_function.py`)

#### Key Functions:
- **`process_multiplex_group(session, row, row_results, targets, ...)`**
  - **Purpose**: Process validation requests and collect enhanced_data
  - **Key Variables**: `enhanced_data`, `shared_client_result`

#### Key Variables:
- **`enhanced_data`**: Per-call enhanced metrics from ai_api_client
- **`all_enhanced_call_data`**: Collected enhanced data with context
- **`row_results['_raw_responses']`**: Raw responses with embedded enhanced_data
- **`shared_client_result`**: Complete ai_api_client response including enhanced_data

### Background Handler (`/src/lambdas/interface/handlers/background_handler.py`)

#### Key Functions:
- **`_apply_domain_multiplier_with_validation(email, cost_estimated, session_id)`**
  - **Purpose**: Apply business rules to create TIER 3 pricing
  - **Returns**: Domain multiplier and validation results

#### Key Variables:
- **`eliyahu_cost`**: TIER 1 cost (actual cost paid)
- **`cost_estimated`**: TIER 2 cost (estimated without cache)
- **`quoted_full_cost`**: TIER 3 cost (user-facing price)
- **`totals`**: Aggregated metrics from ai_api_client
- **`multiplier`**: Domain-specific pricing multiplier

### DynamoDB Schemas (`/src/shared/dynamodb_schemas.py`)

#### Key Functions:
- **`validate_and_convert_session_result(result_data)`**
  - **Purpose**: Validate and store all three cost tiers
  - **Key Variables**: Cost validation and storage fields

## Troubleshooting Common Issues

### Problem: $0.00 Costs in Enhanced Data
**Symptoms**: Enhanced metrics show zero costs despite successful API calls
**Likely Causes**:
1. Missing enhanced_data in ai_api_client responses
2. Caching layer bypassing enhanced_data generation
3. Cost calculation errors in `calculate_token_costs()`

**Investigation Steps**:
```python
# Check if enhanced_data is being generated
logger.info(f"Enhanced data keys: {list(shared_client_result.keys())}")
logger.info(f"Enhanced data costs: {shared_client_result.get('enhanced_data', {}).get('costs', {})}")

# Verify cost calculation inputs
token_usage = shared_client_result.get('token_usage', {})
logger.info(f"Token usage for costs: {token_usage}")
```

### Problem: Missing Enhanced Data in Aggregation
**Symptoms**: `all_enhanced_call_data` list is empty or incomplete
**Likely Causes**:
1. Enhanced data not being collected from API responses
2. Context addition step being skipped
3. Exception during enhanced data processing

**Investigation Steps**:
```python
# Verify collection
logger.info(f"Enhanced call data count: {len(all_enhanced_call_data)}")
for i, data in enumerate(all_enhanced_call_data):
    logger.info(f"Enhanced data {i}: {list(data.keys())}")
```

### Problem: Incorrect Three-Tier Cost Calculations
**Symptoms**: Wrong cost relationships between tiers
**Expected Relationships**:
- `cost_actual <= cost_estimated` (caching reduces actual costs)
- `cost_quoted >= cost_estimated` (business markup increases quoted costs)
- `cost_quoted >= 2.00` (minimum charge applies)

**Investigation Steps**:
```python
# Verify tier relationships
logger.info(f"Tier 1 (actual): ${eliyahu_cost:.6f}")
logger.info(f"Tier 2 (estimated): ${cost_estimated:.6f}")
logger.info(f"Tier 3 (quoted): ${quoted_full_cost:.2f}")
logger.info(f"Domain multiplier: {multiplier}")
```

### Problem: Cache Savings Not Reflected
**Symptoms**: Actual and estimated costs are identical
**Status**: ✅ **RESOLVED** - Fixed in `get_enhanced_call_metrics()` with `pre_extracted_token_usage` detection
**Solution**: Modified cost calculation logic to set actual cost = $0 for cached responses

**Investigation Steps**:
```python
# Check cache utilization
logger.info(f"[CACHE_COST_DEBUG] messages should show actual=$0, estimated=original_cost")
```

### Problem: Aggregated Totals Show Zero Despite Enhanced Data
**Symptoms**: 
- `total_provider_cost_estimated = 0`
- `total_provider_calls = 0`
- Individual enhanced calls show data, but aggregation fails

**Likely Causes**:
1. Enhanced metrics not reaching aggregation in background_handler
2. Aggregation logic not being called or failing
3. `totals.get('total_cost_estimated')` returning 0 despite enhanced data

**Investigation Steps**:
```python
# In background_handler.py around line 585
logger.info(f"[ENHANCED_DEBUG] enhanced_metrics available: {bool(enhanced_metrics)}")
logger.info(f"[ENHANCED_DEBUG] aggregated_metrics: {bool(enhanced_metrics.get('aggregated_metrics'))}")
totals = enhanced_metrics.get('aggregated_metrics', {}).get('totals', {})
logger.info(f"[ENHANCED_DEBUG] totals keys: {list(totals.keys())}")
logger.info(f"[ENHANCED_DEBUG] total_cost_estimated: {totals.get('total_cost_estimated', 'NOT_FOUND')}")
```

### Problem: Timing Metrics Inconsistencies
**Symptoms**: Timing data doesn't align with actual processing times
**Likely Causes**:
1. Processing time measurement errors
2. Cache timing calculations incorrect
3. Timing context not preserved through aggregation

**Investigation Steps**:
```python
# Verify timing tracking
timing_metrics = enhanced_data.get('timing', {})
logger.info(f"Actual time: {timing_metrics.get('time_actual_seconds', 0):.3f}s")
logger.info(f"Estimated time: {timing_metrics.get('time_estimated_seconds', 0):.3f}s") 
logger.info(f"Time savings: {timing_metrics.get('time_savings_percent', 0):.1f}%")
```

### Problem: Quoted Validation Cost Incorrect
**Symptoms**: `quoted_validation_cost = 4` when it should be `ceil(3.64889 × 3) = 11`
**Root Cause**: Domain multiplier calculation or business logic error

**Investigation Steps**:
```python
# Check multiplier calculation in background_handler.py around line 693
logger.info(f"[MULTIPLIER_AUDIT] Domain: {domain}, Base: ${base_cost:.6f}, "
           f"Multiplier: {multiplier}x, With multiplier: ${cost_with_multiplier:.6f}, "
           f"Final quoted: ${quoted_cost:.2f}")
```

**Expected Flow**:
1. `estimated_validation_eliyahu_cost = 3.64889` (base cost without multiplier)
2. `domain_multiplier = 3` (from `account_domain_multiplier`)  
3. `quoted_validation_cost = max(2.0, ceil(3.64889 × 3)) = ceil(10.94667) = 11`

### Problem: Time Estimates Always Zero
**Symptoms**: `estimated_validation_time_minutes = 0` despite cached calls having timing data
**Root Cause**: `estimated_total_time_seconds = 0` in background_handler

**Investigation Steps**:
```python
# In background_handler.py around line 654
logger.info(f"[TIME_DEBUG] total_estimates: {total_estimates}")
logger.info(f"[TIME_DEBUG] estimated_total_processing_time: {total_estimates.get('estimated_total_processing_time', 'NOT_FOUND')}")
```

**Expected Flow**:
1. Enhanced metrics should contain timing data from cached responses
2. `full_validation_estimates` should project total time based on cache timing
3. `estimated_validation_time_minutes = round(estimated_total_time_seconds / 60, 1)`

### Problem: Provider Metrics in DynamoDB All Zero
**Symptoms**: `provider_metrics` shows all zeros despite aggregation working in logs
**Root Cause**: Enhanced aggregated data not reaching DynamoDB storage conversion

**Investigation Steps**:
```python
# Check if aggregated data reaches DynamoDB conversion
logger.info(f"[PROVIDER_METRICS_DEBUG] provider_metrics before DB: {provider_metrics}")
logger.info(f"[PROVIDER_METRICS_DEBUG] enhanced_metrics structure: {enhanced_metrics.keys()}")
```

---

## Summary

The cost and timing propagation system provides comprehensive tracking from individual AI API calls through to final user billing. The three-tier cost system enables:

1. **Internal Cost Tracking**: Actual costs paid with caching benefits
2. **Capacity Planning**: Full cost estimates without caching assumptions
3. **User Billing**: Business rule-applied pricing with domain multipliers

Understanding this flow is essential for debugging cost-related issues, optimizing caching efficiency, and maintaining accurate financial tracking throughout the validation system.