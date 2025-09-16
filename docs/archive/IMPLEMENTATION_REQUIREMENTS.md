# Implementation Requirements for Enhanced Pricing System Integration

## Current Status Summary

The enhanced provider-specific metrics system has been implemented at the core level with:
- ✅ **AI API Client Enhanced**: `get_enhanced_call_metrics()` with comprehensive provider-specific tracking
- ✅ **DynamoDB Schema Extended**: Added `provider_metrics` and related fields to runs table
- ✅ **Cost Field Semantics Fixed**: Preview estimates preserved during full validation
- ✅ **Aggregation Methods**: Provider metrics aggregation and full validation estimation

## Outstanding Implementation Items

### 1. Frontend WebSocket Integration for Enhanced Estimates

**Problem**: The frontend expects `quoted_validation_cost` and `estimated_validation_time_minutes` from preview data to display full validation estimates, but the enhanced metrics may not be flowing correctly through the WebSocket.

**Current Frontend Expectation** (`frontend/perplexity_validator_interface2.html`):
```javascript
// Lines 1941-1942: Frontend expects these fields from preview data
const estimatedCost = previewData.cost_estimates.quoted_validation_cost || previewData.cost_estimates.quoted_full_cost || 0;
const estimatedTime = previewData.estimated_total_processing_time || 0;
```

**Required Implementation**:
- **File**: `src/lambdas/interface/handlers/background_handler.py`
- **Location**: Preview completion WebSocket message construction
- **Action**: Ensure the preview WebSocket message includes:
  ```python
  {
    'cost_estimates': {
      'quoted_validation_cost': quoted_full_cost,  # What user will pay for full validation
      'estimated_validation_eliyahu_cost': estimated_cost_without_cache,  # Internal estimate
      'estimated_validation_time_minutes': estimated_time_minutes  # Time estimate for full validation
    },
    'estimated_total_processing_time': estimated_time_minutes * 60  # In seconds for compatibility
  }
  ```

**Context**: The frontend shows users the cost and time estimates for full validation during the preview phase. These must be preserved and not overwritten during the actual full validation.

### 2. DynamoDB Runs Table Call Consistency and run_key Usage

**Problem**: Not all calls to `update_run_status()` may be properly formed with correct `run_key` values, and the enhanced `provider_metrics` parameter may not be used consistently.

**Required Implementation**:

#### A. Preview Operations
- **File**: `src/lambdas/interface/handlers/background_handler.py` 
- **Context**: Preview validation completion
- **Action**: Ensure all preview completions call:
  ```python
  # Extract provider metrics from enhanced call tracking
  provider_metrics_for_db = extract_provider_metrics_for_storage(aggregated_metrics)
  
  update_run_status(
      session_id=session_id,
      run_key=run_key,  # Must be properly formed
      status='COMPLETED',
      run_type='Preview',
      processed_rows=preview_rows_processed,
      total_rows=total_rows_in_table,
      eliyahu_cost=aggregated_metrics['totals']['total_cost_actual'],
      quoted_validation_cost=0.0,  # Previews are free to users
      estimated_validation_eliyahu_cost=estimates['total_estimates']['estimated_total_cost_without_cache'],
      estimated_validation_time_minutes=estimates['total_estimates']['estimated_total_processing_time'] / 60,
      provider_metrics=provider_metrics_for_db  # NEW: Enhanced provider metrics
  )
  ```

#### B. Full Validation Operations  
- **File**: `src/lambdas/interface/handlers/background_handler.py`
- **Context**: Full validation completion
- **Action**: Ensure full validations preserve preview estimates:
  ```python
  update_run_status(
      session_id=session_id,
      run_key=run_key,  # Must be properly formed
      status='COMPLETED', 
      run_type='Validation',
      processed_rows=total_rows_processed,
      eliyahu_cost=actual_full_validation_cost,  # What we actually paid
      quoted_validation_cost=charged_cost,  # What user was charged
      # Do NOT overwrite estimated_validation_eliyahu_cost - preserve preview estimate
      # Do NOT overwrite estimated_validation_time_minutes - preserve preview estimate  
      provider_metrics=actual_provider_metrics_for_db
  )
  ```

#### C. Configuration Generation Operations
- **File**: `src/lambdas/interface/actions/generate_config_unified.py`
- **Context**: Config generation completion
- **Action**: Ensure config operations use provider metrics:
  ```python
  update_run_status(
      session_id=session_id,
      run_key=run_key,  # Must be properly formed as 'config_' + timestamp
      status='COMPLETED',
      run_type='Config Generation',
      eliyahu_cost=config_generation_cost,
      quoted_validation_cost=0.0,  # Config generation is free to users
      provider_metrics=config_provider_metrics
  )
  ```

#### D. Configuration Refinement Operations
- **File**: `src/lambdas/config/config_lambda_function.py` (if exists) or related refinement handlers
- **Context**: Config refinement operations  
- **Action**: Ensure refinement operations are tracked:
  ```python
  update_run_status(
      session_id=session_id,
      run_key=f"refinement_{refinement_id}",  # Properly formed run_key
      status='COMPLETED',
      run_type='Config Refinement', 
      eliyahu_cost=refinement_cost,
      quoted_validation_cost=0.0,  # Refinement is free to users
      provider_metrics=refinement_provider_metrics
  )
  ```

### 3. Enhanced manage_dynamodb_tables.py Query and Display

**Problem**: The management script may not be pulling the new provider-specific fields or ordering results optimally for analysis.

**Required Implementation**:
- **File**: `src/manage_dynamodb_tables.py`
- **Action**: Update query and display methods to include:

#### A. Enhanced Query Fields
```python
# Add new fields to queries
ENHANCED_FIELDS_TO_RETRIEVE = [
    # Existing fields
    'session_id', 'run_key', 'status', 'run_type', 'processed_rows', 'total_rows',
    'eliyahu_cost', 'quoted_validation_cost', 'estimated_validation_eliyahu_cost',
    'time_per_row_seconds', 'estimated_validation_time_minutes', 'run_time_s',
    
    # NEW: Enhanced provider-specific fields
    'provider_metrics', 'total_provider_cost_actual', 'total_provider_cost_without_cache',
    'total_provider_calls', 'total_provider_tokens', 'overall_cache_efficiency_percent',
    
    # Timing and metadata
    'start_time', 'end_time', 'last_update', 'email_status', 'batch_size'
]
```

#### B. Enhanced Display Formatting
```python
def display_enhanced_run_info(run_item):
    """Display comprehensive run information including provider metrics."""
    
    # Basic run info
    print(f"Session: {run_item.get('session_id')}")
    print(f"Run Key: {run_item.get('run_key')}")
    print(f"Type: {run_item.get('run_type')} | Status: {run_item.get('status')}")
    print(f"Rows: {run_item.get('processed_rows', 0):,} / {run_item.get('total_rows', 0):,}")
    
    # Cost breakdown
    eliyahu_cost = float(run_item.get('eliyahu_cost', 0))
    quoted_cost = float(run_item.get('quoted_validation_cost', 0))
    estimated_cost = float(run_item.get('estimated_validation_eliyahu_cost', 0))
    
    print(f"Costs: ${eliyahu_cost:.6f} (actual) | ${estimated_cost:.6f} (estimated) | ${quoted_cost:.2f} (quoted)")
    
    # Provider-specific breakdown
    provider_metrics = run_item.get('provider_metrics', {})
    if provider_metrics:
        print("Provider Breakdown:")
        for provider, metrics in provider_metrics.items():
            cost_actual = float(metrics.get('cost_actual', 0))
            cost_no_cache = float(metrics.get('cost_without_cache', 0))
            calls = metrics.get('calls', 0)
            tokens = metrics.get('tokens', 0)
            cache_eff = float(metrics.get('cache_efficiency_percent', 0))
            
            print(f"  {provider}: ${cost_actual:.6f} (${cost_no_cache:.6f} no cache) | "
                  f"{calls} calls | {tokens:,} tokens | {cache_eff:.1f}% cache efficiency")
    
    # Timing information
    time_per_row = float(run_item.get('time_per_row_seconds', 0))
    estimated_time = float(run_item.get('estimated_validation_time_minutes', 0))
    run_time = float(run_item.get('run_time_s', 0))
    
    print(f"Timing: {time_per_row:.3f}s/row | {estimated_time:.1f}min estimated | {run_time:.1f}s actual")
    
    # Cache efficiency summary
    cache_efficiency = float(run_item.get('overall_cache_efficiency_percent', 0))
    if cache_efficiency > 0:
        print(f"Overall Cache Efficiency: {cache_efficiency:.1f}%")
```

#### C. Reasonable Ordering and Filtering
```python
def list_runs_with_enhanced_sorting():
    """List runs with intelligent sorting and filtering."""
    
    # Default ordering: Most recent first, then by cost (highest first)
    # Secondary sort by run_type priority: Validation > Preview > Config
    
    def sort_key(run):
        # Primary: Most recent first (by last_update)
        last_update = run.get('last_update', '1970-01-01T00:00:00')
        
        # Secondary: Run type priority (Validation=1, Preview=2, Config=3)
        run_type = run.get('run_type', 'Unknown')
        type_priority = {'Validation': 1, 'Preview': 2, 'Config Generation': 3, 'Config Refinement': 4}.get(run_type, 5)
        
        # Tertiary: Cost (highest first)
        cost = float(run.get('quoted_validation_cost', 0))
        
        return (-last_update, type_priority, -cost)
    
    # Apply sorting and filtering logic
    runs = get_all_runs()  # Your existing method
    
    # Filter options
    filter_by_type = input("Filter by run type (Validation/Preview/Config/All): ").strip()
    filter_by_status = input("Filter by status (COMPLETED/FAILED/IN_PROGRESS/All): ").strip() 
    
    if filter_by_type.lower() not in ['all', '']:
        runs = [r for r in runs if filter_by_type.lower() in r.get('run_type', '').lower()]
    
    if filter_by_status.upper() not in ['ALL', '']:
        runs = [r for r in runs if r.get('status', '').upper() == filter_by_status.upper()]
    
    # Sort and display
    sorted_runs = sorted(runs, key=sort_key)
    
    for run in sorted_runs:
        display_enhanced_run_info(run)
        print("-" * 80)
```

## Integration Points and Dependencies

### Critical Files to Modify:
1. **`src/lambdas/interface/handlers/background_handler.py`** - Main handler for preview/full validation WebSocket and DynamoDB integration
2. **`src/lambdas/interface/actions/generate_config_unified.py`** - Config generation DynamoDB integration
3. **`src/lambdas/config/config_lambda_function.py`** - Config refinement operations (if applicable)
4. **`src/manage_dynamodb_tables.py`** - Enhanced querying and display
5. **Frontend WebSocket message construction** - Ensure proper data flow to UI

### Key Data Flow:
```
AI API Call → get_enhanced_call_metrics() → aggregate_provider_metrics() → 
calculate_full_validation_estimates() → update_run_status(provider_metrics=...) → 
WebSocket message → Frontend display
```

### Testing Considerations:
- **Preview Operations**: Verify `quoted_validation_cost` and `estimated_validation_time_minutes` reach frontend
- **Full Validations**: Confirm preview estimates are preserved, not overwritten  
- **Provider Metrics**: Ensure all operation types store provider breakdown
- **Run Keys**: Verify all operations use properly formed run_key values
- **Management Script**: Test enhanced display with real provider metrics data

## Success Criteria:
1. ✅ Frontend shows accurate full validation cost and time estimates from preview
2. ✅ All DynamoDB operations use proper run_key format and provider_metrics parameter  
3. ✅ Preview estimates are never overwritten during full validation
4. ✅ Management script displays rich provider-specific information with logical ordering
5. ✅ Provider metrics enable analysis of Anthropic vs Perplexity usage patterns
6. ✅ Cache efficiency tracking enables system optimization insights