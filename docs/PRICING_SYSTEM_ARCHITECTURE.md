# Pricing System Architecture - Deep Technical Overview

## Executive Summary

The Perplexity Validator implements a sophisticated **three-tier pricing system** designed to provide accurate cost tracking, transparent user billing, and comprehensive internal cost management. This document details the complete architecture, data flow, and business logic of the enhanced pricing system.

## Table of Contents

1. [Three-Tier Cost Model](#three-tier-cost-model)
2. [System Architecture](#system-architecture)
3. [Data Flow](#data-flow)
4. [Cost Calculation Pipeline](#cost-calculation-pipeline)
5. [Domain Multiplier System](#domain-multiplier-system)
6. [Model Configuration Pricing](#model-configuration-pricing)
7. [Database Schema](#database-schema)
8. [API Integration Points](#api-integration-points)
9. [Caching and Performance](#caching-and-performance)
10. [Audit and Validation](#audit-and-validation)
11. [Error Handling and Fallbacks](#error-handling-and-fallbacks)

## Three-Tier Cost Model with Preview vs Full Validation Semantics

### Overview
The system operates on a three-tier cost model that separates internal costs, raw estimates, and user charges, with **critical distinctions between preview and full validation operations**:

### Tier 1: Eliyahu Cost (Internal Actual)
- **Definition**: The actual cost paid to AI providers for the current operation
- **Preview Operations**: Cost of processing preview rows (e.g., 100 rows)
- **Full Validation Operations**: Cost of processing entire table (e.g., 10,000 rows)
- **Includes**: Caching benefits, discounts, and real provider charges
- **Purpose**: Internal cost tracking and profitability analysis
- **Field**: `eliyahu_cost`
- **Example**: 
  - Preview: $0.05 (actual cost for 100 rows)
  - Full Validation: $1.50 (actual cost for 10,000 rows)

### Tier 2: Estimated Full Validation Cost (Preview Projections)
- **Definition**: **ALWAYS** the estimated cost for a full validation, projected from preview
- **Preview Operations**: Stores the projection for what full validation would cost
- **Full Validation Operations**: **PRESERVES** the original preview estimate (never overwritten)
- **Purpose**: Cost projection, billing transparency, estimate accuracy tracking
- **Calculation**: Extrapolated from preview performance without caching benefits
- **Field**: `estimated_validation_eliyahu_cost`
- **Example**: 
  - After Preview: $3.80 (projected full table cost without cache)
  - After Full Validation: $3.80 (preserved original estimate for comparison)

### Tier 3: Quoted Validation Cost (User-Facing Charge)
- **Definition**: What users are charged for the current operation
- **Preview Operations**: Always $0.00 (previews are free to users)
- **Full Validation Operations**: Actual charge based on preview quote
- **Includes**: 
  - Domain-specific multipliers (1.0x - 100.0x)
  - $2.00 minimum charge
  - Rounded up to nearest dollar
- **Field**: `quoted_validation_cost`
- **Example**: 
  - Preview: $0.00 (free)
  - Full Validation: $12.00 (based on preview estimate × multiplier + rounding)

### Operation-Specific Business Logic Flow

#### Preview Flow:
```
Preview Actual Cost → Projected Full Cost (no cache) → Quoted Full Cost → User Quote (Preview = $0)
      $0.05         →        $3.80                   →      $12.00      →       $0.00
```

#### Full Validation Flow:
```
Full Actual Cost → Preserve Preview Estimate → Charge Preview Quote
     $1.50       →        $3.80             →      $12.00
```

### Critical Semantic Rules

1. **Preview Estimates Are Sacred**: Never overwrite `estimated_validation_eliyahu_cost` during full validation
2. **Billing Consistency**: Users pay exactly what was quoted during preview
3. **Cost Comparison**: Actual vs estimated costs enable accuracy tracking
4. **Operation Context**: All cost fields have different meanings for preview vs full validation

## System Architecture

### Core Components

#### 1. Centralized AI API Client (`src/shared/ai_api_client.py`)
- **Purpose**: Unified cost calculation across all services
- **Key Methods**:
  - `get_unified_cost_and_time_data()`: Main entry point
  - `calculate_token_costs()`: Core cost calculation with decimal precision
  - `load_pricing_data()`: Model pricing with DynamoDB integration
  - `_extract_token_usage()`: Normalized token extraction

#### 2. Background Handler (`src/lambdas/interface/handlers/background_handler.py`)
- **Purpose**: Cost orchestration for validation workflows
- **Enhancements**:
  - Three-tier cost validation and logging
  - Domain multiplier integration with audit trails
  - Preview-to-full cost scaling logic

#### 3. DynamoDB Schema (`src/shared/dynamodb_schemas.py`)
- **Purpose**: Validated storage with business rule enforcement
- **Features**:
  - Cost field validation and sanitization
  - Atomic transaction support
  - Audit trail integration

#### 4. Domain Multiplier System
- **Purpose**: Customer-specific pricing with comprehensive validation
- **Features**:
  - In-memory caching (5-minute TTL)
  - Retry logic with exponential backoff
  - Change history and audit trails

## Data Flow

### 1. Validation Request Flow
```
User Request → Process Excel → Validation Lambda → AI API Client → Cost Calculation → Background Handler → DynamoDB
```

### 2. Cost Calculation Flow
```
API Response → Token Extraction → Pricing Lookup → Cost Calculation → Three-Tier Assignment → Validation → Storage
```

### 3. Preview-to-Full Scaling Flow
```
Preview Results → Cache Analysis → Cost Projection → Domain Multiplier → Quoted Cost → Full Validation Estimate
```

## Cost Calculation Pipeline

### Step 1: Token Usage Extraction
- **Input**: Raw API responses from Anthropic/Perplexity
- **Process**: Normalize different response formats into unified structure
- **Output**: Standardized token usage with provider identification

```json
{
  "api_provider": "anthropic",
  "input_tokens": 1500,
  "output_tokens": 800,
  "cache_read_tokens": 500,
  "total_tokens": 2300,
  "model": "claude-sonnet-4-0"
}
```

### Step 2: Pricing Data Lookup
- **Source**: DynamoDB model configuration table with pattern matching
- **Fallback Chain**:
  1. Exact model match
  2. Pattern matching (e.g., `claude*` for Claude models)
  3. Provider defaults
  4. Hardcoded fallbacks

### Step 3: Cost Calculation
- **Method**: Decimal arithmetic to avoid floating-point precision issues
- **Formula**: `(input_tokens / 1,000,000) * input_rate + (output_tokens / 1,000,000) * output_rate`
- **Precision**: 6 decimal places for internal calculations

### Step 4: Three-Tier Assignment
1. **Eliyahu Cost**: Direct from calculation (includes caching benefits)
2. **Estimated Cost**: Calculated based on cache hit analysis
3. **Quoted Cost**: Applies domain multiplier + business rules

## Domain Multiplier System

### Architecture
- **Storage**: DynamoDB table with domain as primary key
- **Caching**: In-memory cache with 5-minute TTL
- **Validation**: Comprehensive domain format and multiplier value validation

### Validation Rules
- **Domain Format**: RFC-compliant domain names
- **Multiplier Range**: 0.1x to 100.0x (with warnings for extreme values)
- **Business Logic**: Config operations should have 0x user multiplier

### Lookup Logic
```python
def get_domain_multiplier(domain):
    1. Validate and normalize domain
    2. Check in-memory cache
    3. Query DynamoDB for domain-specific multiplier
    4. Fallback to global multiplier
    5. Final fallback to 5.0x default
```

### Audit Trail
- **Change History**: Last 10 changes per domain
- **Concurrent Modification Protection**: Conditional updates
- **Admin Tracking**: Full audit of who changed what when

## Model Configuration Pricing

### Data Structure
```json
{
  "model_pattern": "claude-sonnet-4*",
  "input_cost_per_million_tokens": 3.0,
  "output_cost_per_million_tokens": 15.0,
  "api_provider": "anthropic",
  "priority": 10
}
```

### Pattern Matching
- **Exact Match**: `claude-sonnet-4-0` matches exactly
- **Wildcard Match**: `claude*` matches all Claude models
- **Priority System**: Lower numbers = higher priority

## Database Schema

### Runs Table Cost Fields with Preview vs Full Validation Semantics
```sql
-- Three-tier cost tracking with operation-specific meanings
eliyahu_cost DECIMAL(10,6),                    -- Tier 1: Actual cost for current operation
                                               --   Preview: Cost of preview rows only
                                               --   Full: Cost of entire table validation
                                               
quoted_validation_cost DECIMAL(10,2),          -- Tier 3: User charge for current operation
                                               --   Preview: Always $0.00 (free)
                                               --   Full: Actual charge (based on preview quote)
                                               
estimated_validation_eliyahu_cost DECIMAL(10,6), -- Tier 2: ALWAYS full validation estimate
                                                 --   Preview: Projected full table cost (no cache)
                                                 --   Full: PRESERVED preview estimate (never overwritten)

-- Validation metadata
cost_validation_info MAP,                      -- Validation results and audit info
last_cost_update TIMESTAMP,                   -- Last cost field update time
run_type STRING,                              -- "Preview" or "Validation" for context
```

### Field Usage Examples by Operation Type

#### Preview Operation Record:
```sql
eliyahu_cost = 0.05                           -- Actual cost for 100 preview rows
quoted_validation_cost = 0.00                 -- User pays nothing for preview
estimated_validation_eliyahu_cost = 3.80      -- Projected cost for full 10,000 rows
run_type = "Preview"
```

#### Full Validation Operation Record:
```sql
eliyahu_cost = 1.50                           -- Actual cost for 10,000 full rows
quoted_validation_cost = 12.00                -- User charged based on preview quote
estimated_validation_eliyahu_cost = 3.80      -- PRESERVED preview estimate for comparison
run_type = "Validation"
```

### Domain Multipliers Table
```sql
domain STRING,                    -- Primary key: domain name
multiplier DECIMAL(5,2),         -- Multiplier value (0.01 - 100.00)
created_at TIMESTAMP,
updated_at TIMESTAMP,
created_by STRING,               -- Admin email
change_history LIST,             -- Last 10 changes
validation_info MAP              -- Validation metadata
```

## API Integration Points

### 1. Anthropic API Integration
- **Models**: Claude-4-Opus, Claude-Sonnet-4, Claude-Haiku
- **Token Tracking**: Input, output, cache creation, cache read tokens
- **Cost Calculation**: Based on official Anthropic pricing

### 2. Perplexity API Integration
- **Models**: Sonar-Pro, Sonar
- **Token Tracking**: Prompt tokens, completion tokens
- **Context Size**: Integration with search context size for pricing

## Caching and Performance

### Cost Calculation Caching
- **AI Client**: Pricing data cached per lambda execution
- **Domain Multipliers**: 5-minute in-memory cache
- **Token Usage**: Cached with API responses in S3

### Performance Optimizations
- **Decimal Arithmetic**: Precise cost calculations without floating-point errors
- **Batch Processing**: Efficient token aggregation across multiple API calls
- **Retry Logic**: Robust error handling with exponential backoff

## Audit and Validation

### Cost Field Validation
- **Negative Validation**: All costs must be non-negative
- **Range Validation**: Costs above $1000 trigger warnings
- **Relationship Validation**: Estimated ≥ Actual cost consistency checks
- **Business Rule Validation**: Config operations should be free to users

### Audit Trails
- **Cost Updates**: Full audit metadata with validation results
- **Domain Changes**: Complete change history with admin tracking
- **High-Value Transactions**: Special logging for costs > $10

### Validation Error Handling
- **Sanitization**: Invalid values sanitized to safe defaults
- **Warning System**: Business rule violations logged as warnings
- **Atomic Updates**: Cost field updates use DynamoDB transactions

## Error Handling and Fallbacks

### Pricing Data Fallbacks
1. **DynamoDB Model Config**: Primary source
2. **Provider Defaults**: Anthropic/Perplexity standard rates
3. **Hardcoded Fallbacks**: Emergency fallbacks for each provider
4. **Universal Fallback**: $3/$15 per million tokens (input/output)

### Domain Multiplier Fallbacks
1. **Domain-Specific**: User's specific domain multiplier
2. **Global Multiplier**: Organization-wide default
3. **Hardcoded Default**: 5.0x emergency fallback

### API Failure Handling
- **Retry Logic**: 3 attempts with exponential backoff
- **Circuit Breaker**: Temporary failure handling
- **Graceful Degradation**: System continues with warnings

## Cost Scaling Logic

### Preview to Full Validation Scaling
The system handles preview-to-full scaling through several mechanisms:

#### 1. Cache Analysis
- **Preview Analysis**: Determines cache hit rate from preview run
- **Projection**: Estimates full table cost assuming similar cache performance
- **Conservative Estimation**: Uses worst-case scenarios for safety

#### 2. Row-Based Scaling
```python
# Scale preview costs to full table
preview_cost_per_row = preview_eliyahu_cost / preview_rows_processed
estimated_full_cost = preview_cost_per_row * total_rows_in_table
```

#### 3. Token-Based Scaling
- **Token Density**: Calculates tokens per row from preview
- **Full Projection**: Scales to full table based on token density
- **Model Variation**: Accounts for different models in search groups

### Quoted Cost Generation
```python
def generate_quoted_cost(estimated_cost, domain):
    multiplier = get_domain_multiplier(domain)
    cost_with_multiplier = estimated_cost * multiplier
    quoted_cost = max(2.00, math.ceil(cost_with_multiplier))
    return quoted_cost
```

## Enhanced Provider-Specific Metrics System

### Overview
The system now tracks comprehensive provider-specific metrics with caching analysis and per-row calculations at the elemental call level in the AI API client.

### Enhanced AI API Client Tracking

#### New Method: get_enhanced_call_metrics()
```python
enhanced_metrics = ai_client.get_enhanced_call_metrics(
    response=api_response,
    model=model_name,
    processing_time=actual_time,
    search_context_size='medium',
    batch_info={'batch_size': 10, 'rows_processed': 10}
)
```

**Returns comprehensive metrics structure:**
- **call_info**: Model, provider, timestamp, context size
- **tokens**: Input, output, total, cache creation/read tokens
- **costs**: Actual (with cache), without cache, cache savings
- **timing**: Actual time, estimated without cache, time savings
- **caching**: Hit rates, coverage, efficiency scores
- **per_row**: Cost and time per row with/without cache
- **provider_metrics**: Aggregated data for provider breakdown

#### Provider Aggregation Methods
```python
# Aggregate metrics across multiple calls by provider
aggregated = AIAPIClient.aggregate_provider_metrics(call_metrics_list)

# Calculate full validation estimates from preview data
estimates = AIAPIClient.calculate_full_validation_estimates(
    aggregated_metrics=aggregated,
    total_rows_in_table=10000,
    preview_rows_processed=100
)
```

### Enhanced DynamoDB Schema

#### New Fields Added to Runs Table
```sql
-- Provider-specific detailed metrics
provider_metrics MAP,                           -- Nested provider data
total_provider_cost_actual DECIMAL(10,6),      -- Sum across providers
total_provider_cost_without_cache DECIMAL(10,6), -- Sum without cache benefits
total_provider_calls INT,                      -- Total API calls
total_provider_tokens INT,                     -- Total tokens processed
overall_cache_efficiency_percent DECIMAL(5,2)  -- Overall cache savings
```

#### Provider Metrics Structure
```json
{
  "anthropic": {
    "calls": 45,
    "tokens": 125000,
    "cost_actual": 0.75,
    "cost_without_cache": 1.20,
    "processing_time": 12.5,
    "cache_hit_tokens": 25000,
    "cost_per_row_actual": 0.0075,
    "cost_per_row_without_cache": 0.012,
    "time_per_row_actual": 0.125,
    "cache_efficiency_percent": 37.5
  },
  "perplexity": {
    "calls": 15,
    "tokens": 45000,
    "cost_actual": 0.15,
    "cost_without_cache": 0.18,
    "processing_time": 8.2,
    "cache_hit_tokens": 5000,
    "cost_per_row_actual": 0.0015,
    "cost_per_row_without_cache": 0.0018,
    "time_per_row_actual": 0.082,
    "cache_efficiency_percent": 16.7
  }
}
```

### Comprehensive Time and Cost Tracking

#### Time Estimation Features
- **Actual Processing Time**: Real time spent on API calls
- **Estimated Time Without Cache**: Projected time if no caching (8x multiplier)
- **Time Savings**: Absolute seconds and percentage saved through caching
- **Per-Row Time Metrics**: Time per row by provider with/without cache
- **Batch Time Estimates**: Projections for different batch sizes (10, 20, 50, 100)

#### Cost Analysis Features
- **Actual Costs**: Real costs paid to providers (with caching benefits)
- **Costs Without Cache**: Estimated costs if no caching were available
- **Cache Savings**: Absolute dollar savings and percentage efficiency
- **Per-Row Cost Metrics**: Cost per row by provider with/without cache
- **Provider Cost Breakdown**: Separate tracking for Anthropic vs Perplexity

### Preview Estimate Preservation & Accuracy Tracking

#### Critical Semantic Rules
1. **Preview Estimates Are Sacred**: `estimated_validation_eliyahu_cost` NEVER overwritten
2. **Time Estimates Preserved**: `estimated_validation_time_minutes` preserved from preview
3. **Provider Metrics Maintained**: Full provider breakdown preserved for comparison
4. **Billing Consistency**: Users pay exactly what was quoted during preview

#### Cost Comparison Logging
```python
# Enhanced comparison with provider breakdown
preview_estimate = float(existing_run['Item']['estimated_validation_eliyahu_cost'])
actual_full_cost_without_cache = estimated_cost_without_cache
estimate_accuracy = ((preview_estimate - actual_full_cost_without_cache) / preview_estimate * 100)

logger.info(f"[COST_COMPARISON] Preview estimated: ${preview_estimate:.6f} | "
           f"Actual full cost (no cache): ${actual_full_cost_without_cache:.6f} | "
           f"Estimate accuracy: {estimate_accuracy:.1f}% | User charged: ${charged_cost:.2f}")

# Provider-specific accuracy tracking
for provider, metrics in provider_metrics.items():
    logger.info(f"  {provider}: ${metrics['cost_without_cache']:.6f} estimated, "
               f"{metrics['cache_efficiency_percent']:.1f}% cache efficiency")
```

### Batch-Based Time Estimation
The system calculates full validation time estimates using:
1. **Per-Row Time Analysis**: Extract time per row from preview
2. **Batch Efficiency Modeling**: Account for batch processing overhead
3. **Provider-Specific Scaling**: Different time characteristics per provider
4. **Cache Efficiency Projection**: Maintain preview cache hit rate assumptions
5. **Batch Size Optimization**: Recommendations for optimal batch sizes

### Key Metrics Tracked
- **Provider Usage Distribution**: Anthropic vs Perplexity call patterns
- **Cache Effectiveness by Provider**: Hit rates and cost savings per provider
- **Per-Row Economics**: Unit costs and times by provider and operation type
- **Estimate Accuracy**: Preview vs actual cost and time accuracy
- **Batch Performance**: Optimal batch sizes for different table sizes
- **Time Scaling Precision**: How well preview timing predicts full validation

## Time Estimation Integration

### Current Implementation
- **Processing Time**: Tracked per API call and aggregated
- **Time Per Row**: Calculated for scaling estimates
- **Efficiency Metrics**: Tokens per second, cost per second

### Outstanding Time Enhancements
- **Predictive Modeling**: ML-based time prediction
- **Complexity Factors**: Account for search group complexity
- **Queue Time**: Include system wait times in estimates

---

*This document represents the current state of the pricing system architecture. For implementation details, see individual component documentation.*