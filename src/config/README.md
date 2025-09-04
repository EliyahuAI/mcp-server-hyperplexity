# Enhanced Batch Size Management System

## Overview

The Enhanced Batch Size Management System provides configuration-driven, audit-logged batch size management with hierarchical model pattern matching and comprehensive tracking.

## Key Features

✅ **CSV Configuration**: Define batch size limits per model pattern  
✅ **Hierarchical Pattern Matching**: Use wildcards to match model families  
✅ **Automatic Model Registration**: New models are configured automatically  
✅ **Weight-Based Adjustments**: Different models can have different aggressiveness  
✅ **DynamoDB Audit Logging**: Track all batch size changes over time  
✅ **Drop-in Replacement**: Compatible with existing code  
✅ **Management Commands**: CLI tools for monitoring and administration  

## Configuration File Format

The `model_batch_config.csv` file defines batch size parameters for different model patterns:

```csv
model_pattern,min_batch_size,max_batch_size,initial_batch_size,priority,weight,rate_limit_factor,success_threshold,failure_threshold,enabled,notes
claude-4*,5,200,100,1,1.5,0.5,5,2,true,Latest Claude models with high rate limits
claude-3.5*,10,150,80,2,1.3,0.6,5,2,true,Claude 3.5 family with good performance
llama-3.1-sonar-large*,8,120,60,1,1.4,0.7,5,2,true,Large Perplexity models
*,25,50,30,999,1.0,0.9,3,2,true,Default for unmatched models
```

### Column Definitions

| Column | Type | Description |
|--------|------|-------------|
| `model_pattern` | String | Glob pattern to match model names (use * for wildcards) |
| `min_batch_size` | Integer | Minimum allowed batch size for this model |
| `max_batch_size` | Integer | Maximum allowed batch size for this model |
| `initial_batch_size` | Integer | Starting batch size when model is first registered |
| `priority` | Integer | Pattern matching priority (lower = higher priority) |
| `weight` | Float | Adjustment factor for success increases (1.0 = normal, >1.0 = more aggressive) |
| `rate_limit_factor` | Float | Reduction factor when rate limit hit (0.5 = reduce by 50%) |
| `success_threshold` | Integer | Consecutive successes needed before increasing batch size |
| `failure_threshold` | Integer | Consecutive failures needed before decreasing batch size |
| `enabled` | Boolean | Whether this configuration is active |
| `notes` | String | Human-readable description |

## Pattern Matching Examples

| Model Name | Matched Pattern | Priority | Batch Size |
|------------|-----------------|----------|------------|
| `claude-4-opus` | `claude-4*` | 1 | 100 |
| `claude-3.5-sonnet-20241022` | `claude-3.5*` | 2 | 80 |
| `claude-3-haiku` | `claude-3*` | 3 | 50 |
| `llama-3.1-sonar-large-128k` | `llama-3.1-sonar-large*` | 1 | 60 |
| `gpt-4-turbo` | `*` | 999 | 30 |

## Integration

### Simple Integration

Replace your existing `DynamicBatchSizeManager` creation:

```python
# BEFORE
batch_manager = DynamicBatchSizeManager(initial_batch_size=50, ...)

# AFTER
from integration_example import create_enhanced_batch_manager
batch_manager = create_enhanced_batch_manager(
    session_id=session_id,
    enable_audit_logging=True
)
```

### Manual Integration

```python
from shared.enhanced_batch_manager import EnhancedDynamicBatchSizeManager

batch_manager = EnhancedDynamicBatchSizeManager(
    config_file_path="path/to/model_batch_config.csv",  # Optional
    session_id="your_session_id",  # Optional
    enable_audit_logging=True  # Optional
)
```

## Audit Logging

All batch size changes are logged to the `perplexity-validator-batch-audit` DynamoDB table with:

- **Timestamp**: When the change occurred
- **Model**: Which model was affected  
- **Old/New Sizes**: Before and after batch sizes
- **Change Reason**: Why the change happened (rate_limit, success_streak, failure_streak, etc.)
- **Session ID**: Which validation session triggered the change
- **Additional Context**: Success/failure counts, adjustment factors, etc.

### Audit Log Schema

```json
{
  "audit_id": "uuid-string",
  "timestamp": "2025-01-01T12:00:00.000Z", 
  "model": "claude-3.5-sonnet-20241022",
  "old_batch_size": 80,
  "new_batch_size": 60,
  "change_amount": -20,
  "change_percent": -25.0,
  "change_reason": "rate_limit",
  "session_id": "session_20250101_120000_abcdef12",
  "additional_context": "{\"rate_limit_count\": 1, \"rate_limit_factor\": 0.6}",
  "ttl": 1735689600
}
```

## Management Commands

### View Batch History for Specific Model
```bash
python manage_dynamodb_tables.py batch-history claude-3.5-sonnet-20241022 50
```

### View Recent Batch Changes (All Models)
```bash
python manage_dynamodb_tables.py recent-batch-changes 24 100  # Last 24 hours, max 100 records
```

### Create Batch Audit Table
```bash
python manage_dynamodb_tables.py create-batch-audit-table
```

### Test Model Configuration
```bash
python src/config/model_config_loader.py
```

## Weight-Based Adjustments

The `weight` parameter controls how aggressively batch sizes are increased after success streaks:

- **Weight 1.0**: Standard 10% increase
- **Weight 1.5**: ~12.5% increase (more aggressive for high-performance models)
- **Weight 0.8**: ~9% increase (more conservative for unreliable models)

Formula: `increase_factor = 1.1 + ((weight - 1.0) * 0.05)`

## Performance Benefits

### Before: Provider-Level Tracking
- Claude models share one batch size
- Perplexity models share one batch size  
- New models require code changes

### After: Per-Model Tracking  
- Each model has independent batch size optimization
- Models auto-register with appropriate configuration
- Higher-tier models can use larger batches
- Fine-grained rate limit handling

### Example Performance Impact

```
Model: claude-4-opus (weight: 1.5, range: 5-200)
├─ Starts at: 100 batch size
├─ Can scale up to: 200 (vs 100 in old system)  
├─ More aggressive increases: 12.5% vs 10%
└─ Independent of other Claude models

Model: claude-3-haiku (weight: 1.0, range: 15-100)  
├─ Starts at: 50 batch size
├─ Conservative increases: 10%
└─ Won't be throttled by claude-4 rate limits
```

## Backwards Compatibility

The enhanced system is a drop-in replacement:

- ✅ All existing method calls work unchanged
- ✅ Falls back to original implementation if enhanced version fails
- ✅ Existing statistics and logging continue to work
- ✅ No breaking changes to lambda function interface

## Files Added

```
src/config/
├── model_batch_config.csv          # Model configuration file
├── model_config_loader.py           # Configuration loader
└── README.md                        # This documentation

src/shared/
├── enhanced_batch_manager.py        # Enhanced batch manager
└── batch_audit_logger.py            # DynamoDB audit logging

src/
└── integration_example.py           # Integration guide and testing
```

## Monitoring and Alerting

The audit logs can be used to:

1. **Detect Rate Limiting Patterns**: Models frequently hitting rate limits
2. **Performance Monitoring**: Track batch size optimization over time  
3. **Cost Analysis**: Correlate batch sizes with processing costs
4. **Model Comparison**: Compare performance across different models
5. **System Health**: Alert on excessive batch size reductions

Example CloudWatch queries can be built on the audit data for operational insights.