# Enhanced Cost and Time Estimation Features

## Overview
This update adds comprehensive cost and time tracking to the perplexity validator system, with enhanced preview functionality that provides accurate cost estimates even when using cached responses.

## New Features

### 1. Enhanced Cache Structure with Cost/Time Metadata

**What Changed:**
- Cache entries now store cost and time metadata alongside API responses
- Backward compatibility maintained with legacy cache format
- Processing time tracked for all API calls

**Technical Implementation:**
```json
{
  "api_response": { /* original API response */ },
  "cached_at": "2024-01-15T10:30:00Z",
  "model": "sonar-pro", 
  "search_context_size": "low",
  "token_usage": {
    "total_tokens": 150,
    "total_cost": 0.000234,
    "api_calls": 1,
    "cached_calls": 0
  },
  "processing_time": 2.34
}
```

**Benefits:**
- True cost/time estimates returned even for cached responses
- Cache hit/miss tracking for cost analysis
- Historical processing time data preserved

### 2. Preview Row Selection

**What Changed:**
- New `preview_row_number` parameter (1-5) for API requests
- Validation and graceful handling of invalid row numbers
- Defaults to row 1 if invalid or missing

**Usage:**
```
GET /api?preview_first_row=true&preview_row_number=3
```

**Benefits:**
- Test validation on different data rows without full processing
- Better preview capabilities for varied data sets
- Improved debugging and testing workflows

### 3. Enhanced Preview Response with Cost Data

**What Changed:**
- Preview responses now include detailed cost breakdowns
- Real token usage and processing time data
- Estimated costs for full dataset processing

**New Response Structure:**
```json
{
  "status": "preview_completed",
  "preview_row_number": 2,
  "preview_processing_time": 1.23,
  "cost_estimates": {
    "preview_cost": 0.000156,
    "estimated_total_cost": 0.015600,
    "preview_tokens": 120,
    "estimated_total_tokens": 12000,
    "api_calls": 1,
    "cached_calls": 0
  },
  "token_usage": {
    "total_tokens": 120,
    "total_cost": 0.000156,
    "by_provider": { /* detailed breakdown */ }
  }
}
```

**Benefits:**
- Accurate cost estimation before full processing
- Cache utilization visibility
- Better cost planning and budgeting

## API Changes

### New Parameters

1. **`preview_row_number`** (optional)
   - Type: Integer (1-5)
   - Default: 1
   - Used with: `preview_first_row=true`
   - Purpose: Select which row to preview

### Enhanced Response Fields

1. **Cost Estimates Object:**
   - `preview_cost`: Actual cost for preview row
   - `estimated_total_cost`: Projected cost for full dataset
   - `preview_tokens`: Tokens used for preview
   - `estimated_total_tokens`: Projected tokens for full dataset
   - `api_calls`: New API calls made
   - `cached_calls`: Responses served from cache

2. **Updated Field Names:**
   - `first_row_processing_time` → `preview_processing_time`
   - Added `preview_row_number` field

## Backward Compatibility

- Legacy cache entries continue to work
- Old field names still supported where possible
- Graceful degradation if cost data unavailable
- Default behavior unchanged (row 1 preview)

## Testing

A comprehensive test suite (`test_cost_time_features.py`) validates:

1. **Preview Row Selection:**
   - Tests rows 1-5
   - Invalid row number handling
   - Response consistency

2. **Cost Tracking:**
   - Cache hit/miss detection
   - Cost data accuracy
   - Performance measurement

3. **Error Handling:**
   - Invalid parameters
   - Missing data scenarios
   - Graceful degradation

## Implementation Files

### Core Lambda Function (`src/lambda_function.py`)
- Enhanced cache storage with metadata
- Processing time tracking
- Backward-compatible cache retrieval

### Interface Lambda (`src/interface_lambda_function.py` & `deployment/interface_package/interface_lambda_function.py`)
- Row selection parameter handling
- Enhanced preview response generation
- Cost estimate calculations

### Test Suite (`test_cost_time_features.py`)
- Comprehensive feature validation
- Performance benchmarking
- Error condition testing

## Usage Examples

### Basic Preview (Row 1)
```bash
curl -X POST "https://api.example.com/validate?preview_first_row=true" \
  -F "excel_file=@data.xlsx" \
  -F "config_file=@config.json"
```

### Preview Specific Row
```bash
curl -X POST "https://api.example.com/validate?preview_first_row=true&preview_row_number=3" \
  -F "excel_file=@data.xlsx" \
  -F "config_file=@config.json"
```

### Cost Analysis
The response will include:
- Exact cost for the previewed row
- Estimated total cost for full processing
- Cache utilization metrics
- Token usage breakdown by provider/model

## Benefits

1. **Cost Transparency:** Real-time cost tracking and estimation
2. **Flexible Testing:** Preview any row (1-5) for better data validation
3. **Cache Efficiency:** Visibility into cache utilization and savings
4. **Better Planning:** Accurate cost estimates before committing to full processing
5. **Performance Insights:** Processing time tracking for optimization

## Migration Notes

- No breaking changes to existing API contracts
- New features are opt-in via parameters
- Enhanced responses provide additional data without removing existing fields
- Legacy cache entries automatically upgraded on access

This implementation provides comprehensive cost and time tracking while maintaining full backward compatibility and adding powerful new preview capabilities. 