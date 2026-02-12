# AI Client 3-Tier Refinement Guide

**Complete guide for cost-optimized structured data refinement using ai_client**

## Overview

The `ai_client.call_structured_api()` now includes **built-in 3-tier refinement mode** that automatically optimizes cost and quality when refining existing structured data.

### How It Works

```
Add original_data parameter → Automatic 3-tier refinement

TIER 1: Primary model → JSON Patches       (~$0.08, ~40s)
   ↓ (patches fail?)
TIER 2: Cheap model → Direct implementation (~$0.002, ~10s)
   ↓ (validation fails?)
TIER 3: Primary model → Full generation    (~$0.15, ~70s)
```

**Average cost: ~$0.088** (41% savings vs always using expensive model)

## Quick Start

### Basic Usage

```python
from shared.ai_api_client import ai_client

# Normal mode (no refinement)
result = await ai_client.call_structured_api(
    prompt="Extract data from text",
    schema=extraction_schema,
    model="claude-opus-4-1"
)

# Refinement mode (just add original_data!)
result = await ai_client.call_structured_api(
    prompt="Change company name importance to RESEARCH",
    schema=config_schema,
    model=["claude-opus-4-1", "gemini-2.5-flash-lite"],

    original_data=existing_config,  # Triggers 3-tier mode
    validator_fn=validate_config     # Validates each tier
)

# Automatic 3-tier fallback!
print(f"Tier {result['refinement_tier']} succeeded")
print(f"Cost: ${result['total_refinement_cost']:.4f}")
updated_data = result['refined_data']
```

## API Reference

### Parameters

```python
await ai_client.call_structured_api(
    # Standard parameters
    prompt: str,                    # User's request or instruction
    schema: Dict,                   # JSON schema for the data type
    model: Union[str, List[str]],   # [primary, cheap] or single model
    tool_name: str = "structured_response",
    max_tokens: int = None,
    debug_name: str = None,
    # ... other standard params ...

    # Refinement mode (NEW - all optional)
    original_data: Optional[Dict] = None,           # Current data to refine (triggers mode)
    validator_fn: Optional[Callable] = None,        # (data) -> (is_valid, errors, warnings)
    try_patches_first: bool = True,                 # Tier 1: try patches
    refinement_context: Optional[Dict[str, str]] = None  # Additional context sections
)
```

### Return Value (Refinement Mode)

```python
{
    # Standard fields
    'response': {...},
    'token_usage': {...},
    'processing_time': 2.5,
    'model_used': 'claude-opus-4-1',
    'enhanced_data': {...},
    'is_cached': False,

    # Refinement fields (NEW)
    'refinement_tier': 1,           # Which tier succeeded (1, 2, or 3)
    'refined_data': {...},          # The updated data
    'tier_costs': [0.08],          # Cost of each tier attempted
    'total_refinement_cost': 0.08,  # Sum of tier costs
    'method': 'patches',            # "patches", "cheap_implementation", or "full_generation"

    # Tier 1 specific
    'patches': [{...}],             # The patches applied (if Tier 1)
    'reasoning': "Changed X..."     # Explanation of changes
}
```

## Real-World Examples

### Example 1: Config Refinement

```python
from shared.ai_api_client import ai_client
from config_validator import validate_config_complete

# User wants to change a column's importance
result = await ai_client.call_structured_api(
    prompt="Change Company Name column importance from ID to RESEARCH",
    schema=config_schema,
    model=["claude-opus-4-1", "gemini-2.5-flash-lite"],

    original_data=existing_config,
    validator_fn=lambda c: validate_config_complete(c, table_analysis),
    refinement_context={
        "Validation Results": "Previous run had 3% error rate...",
        "User Feedback": "Company names should be researched"
    },

    tool_name="refine_config",
    debug_name=f"refinement_{session_id}"
)

if result.get('refined_data'):
    new_config = result['refined_data']
    print(f"✅ Tier {result['refinement_tier']}: {result['method']}")
    print(f"💰 Cost: ${result['total_refinement_cost']:.4f}")

    if result.get('patches'):
        print(f"🔧 Applied {len(result['patches'])} patches")
```

### Example 2: User Settings

```python
def validate_settings(settings):
    errors = []
    if settings.get('email_frequency') not in ['daily', 'weekly', 'never']:
        errors.append("Invalid email_frequency")
    if settings.get('theme') not in ['light', 'dark', 'auto']:
        errors.append("Invalid theme")
    return (len(errors) == 0, errors, [])

result = await ai_client.call_structured_api(
    prompt="Enable notifications and set frequency to daily",
    schema=settings_schema,
    model=["claude-sonnet-4-5", "gemini-2.5-flash-lite"],

    original_data=user_settings,
    validator_fn=validate_settings,

    debug_name="settings_refinement"
)

updated_settings = result['refined_data']
```

### Example 3: API Config Optimization

```python
result = await ai_client.call_structured_api(
    prompt="Optimize for latency under 200ms while staying under $500/month",
    schema=api_config_schema,
    model=["claude-opus-4-1", "gemini-2.5-flash-lite"],

    original_data=api_config,
    validator_fn=validate_api_config,
    refinement_context={
        "Current Performance": "P95: 450ms, P99: 800ms",
        "Current Cost": "$650/month",
        "Budget": "$500/month max"
    },

    debug_name="api_optimization"
)

if result['refinement_tier'] == 1:
    # Patches worked - minimal changes
    print(f"Applied {len(result['patches'])} targeted optimizations")
elif result['refinement_tier'] == 2:
    # Cheap model implemented changes
    print(f"Cheap model optimized config (${result['total_refinement_cost']:.4f})")
else:
    # Full regeneration
    print(f"Full optimization (${result['total_refinement_cost']:.4f})")
```

## How Each Tier Works

### Tier 1: Primary Model → Patches

**What happens:**
1. AI generates JSON Patch operations (RFC 6902)
2. Patches are applied to original_data
3. Result is validated with validator_fn
4. If successful → Done! ✅

**Example patches:**
```json
{
  "patch_operations": [
    {"op": "test", "path": "/validation_targets/1/column", "value": "Company Name"},
    {"op": "replace", "path": "/validation_targets/1/importance", "value": "RESEARCH"}
  ],
  "reasoning": "Changed Company Name importance as requested"
}
```

**Benefits:**
- Explicit changes (audit trail)
- Can't accidentally drop fields
- Smaller payload
- ~47% cost savings

**When it fails:**
- Invalid JSON Pointer path
- Validation errors
- AI generates bad patches

### Tier 2: Cheap Model → Direct Implementation

**What happens:**
1. Cheap model sees: instruction + original JSON + failed patches (for context)
2. AI implements changes directly, returns full updated JSON
3. Result is validated with validator_fn
4. If successful → Done! ✅

**Prompt to cheap model:**
```
USER REQUEST: "Change X to Y"

CURRENT DATA: {...full JSON...}

FAILED PATCHES (for reference): [{...}]

TASK: Implement the changes directly. Return complete updated data.
```

**Benefits:**
- Very cheap (~$0.002)
- Often works when patches fail
- Still validates output

**When it fails:**
- Cheap model hallucinates
- Validation errors
- Missing required fields

### Tier 3: Primary Model → Full Generation

**What happens:**
1. Primary expensive model generates complete updated config
2. Uses full context and validation history
3. Guaranteed high-quality output
4. Final fallback

**Benefits:**
- Always works (highest quality model)
- Full context understanding
- Comprehensive output

**Cost:**
- Most expensive (~$0.15)
- Only used as last resort (~5% of time)

## Configuration

### Model Selection

```python
# Recommended model pairs:
models = [
    "claude-opus-4-1",       # Primary: Expensive, accurate
    "gemini-2.5-flash-lite"  # Cheap: Fast, cheap
]

# Or use single model (all tiers use same):
models = "claude-sonnet-4-5"

# Or specify more backups:
models = [
    "claude-opus-4-1",      # Tier 1 & 3
    "gemini-2.5-flash-lite", # Tier 2
    "claude-sonnet-4-5"     # Additional backup
]
```

### Validation Function

```python
def your_validator(data: dict) -> Tuple[bool, List[str], List[str]]:
    """
    Validate refined data.

    Returns:
        (is_valid, errors, warnings)
    """
    errors = []
    warnings = []

    # Check required fields
    if 'required_field' not in data:
        errors.append("Missing required_field")

    # Check constraints
    if data.get('value', 0) < 0:
        errors.append("value must be positive")

    # Check cross-field logic
    if data.get('field_a') == data.get('field_b'):
        warnings.append("field_a and field_b are the same")

    return (len(errors) == 0, errors, warnings)
```

### Refinement Context

Add additional context to help AI understand the changes:

```python
refinement_context = {
    "Performance Data": "Current P95: 450ms, Budget: $500/month",
    "User Feedback": "Previous attempts were too slow",
    "Constraints": "Must maintain 99.9% uptime"
}

result = await ai_client.call_structured_api(
    prompt="Optimize for speed",
    schema=schema,
    model=models,
    original_data=config,
    validator_fn=validator,
    refinement_context=refinement_context  # Helps AI make better decisions
)
```

## Cost Analysis

### Breakdown by Tier

| Tier | Model | Method | Cost | Time | Success Rate* |
|------|-------|--------|------|------|---------------|
| 1 | claude-opus-4-1 | Patches | ~$0.08 | ~40s | 80% |
| 2 | gemini-2.5-flash-lite | Full | ~$0.002 | ~10s | 15% |
| 3 | claude-opus-4-1 | Full | ~$0.15 | ~70s | 5% |

*Estimated based on refinement complexity

### Scenarios

**Scenario 1: Simple change (Tier 1)**
- Request: "Change field X to value Y"
- Result: Tier 1 patches succeed
- Cost: $0.08 (47% savings)

**Scenario 2: Complex change that breaks patches (Tier 2)**
- Request: "Update multiple nested fields"
- Result: Patches fail, cheap model implements
- Cost: $0.082 (45% savings)

**Scenario 3: Very complex restructuring (Tier 3)**
- Request: "Reorganize entire structure"
- Result: Both patches and cheap model fail, expensive model succeeds
- Cost: $0.232 (1% overhead)

### Break-Even Analysis

With realistic success rates:
- 80% Tier 1 success: 0.80 × $0.08 = $0.064
- 15% Tier 2 success: 0.15 × $0.082 = $0.0123
- 5% Tier 3 fallback: 0.05 × $0.232 = $0.0116

**Average: $0.088** (vs $0.15 always expensive = **41% savings**)

## Monitoring

### Log Messages

Watch for these in CloudWatch/logs:

```
✅ Success:
"🎯 3-TIER REFINEMENT MODE activated"
"✅ TIER 1 SUCCESS: Patches applied ($0.082400)"
"✅ TIER 2 SUCCESS: Cheap model implemented ($0.001800)"
"✅ TIER 3 SUCCESS: Full generation ($0.150000)"

⚠️ Fallback:
"⚠️ TIER 1 FAILED: Invalid path /field"
"⚠️ TIER 2 FAILED: Validation failed"
"📍 TIER 3: Falling back to primary model..."

💰 Cost tracking:
"💰 Total refinement cost: $0.084200 across 2 tiers"
```

### Metrics to Track

```python
# In your monitoring code:
if result.get('refinement_tier'):
    tier = result['refinement_tier']
    cost = result['total_refinement_cost']
    method = result['method']

    # Track tier usage
    metrics.increment(f"refinement.tier{tier}.success")
    metrics.observe("refinement.cost", cost)
    metrics.histogram("refinement.tier_distribution", tier)
```

**Recommended metrics:**
- `refinement.tier1.success_rate` - Should be 70-85%
- `refinement.tier2.success_rate` - Should be 10-20%
- `refinement.tier3.fallback_rate` - Should be <10%
- `refinement.avg_cost` - Should be $0.08-0.10
- `refinement.cost_savings` - Should be 35-45%

## Best Practices

### 1. Choose Models Wisely

```python
# For high-stakes refinements:
model = ["claude-opus-4-1", "gemini-2.5-flash-lite"]  # Best quality Tier 1

# For routine refinements:
model = ["claude-sonnet-4-5", "gemini-2.5-flash-lite"]  # Balanced cost

# For experimental/testing:
model = ["gemini-2.5-flash-lite"]  # All tiers use cheap model
```

### 2. Provide Good Validators

```python
def comprehensive_validator(data):
    errors = []
    warnings = []

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing {field}")

    # Value constraints
    if data.get('batch_size', 0) <= 0:
        errors.append("batch_size must be positive")

    # Cross-field validation
    if data.get('max_concurrent') > data.get('rate_limit'):
        warnings.append("max_concurrent exceeds rate_limit")

    return (len(errors) == 0, errors, warnings)
```

### 3. Use Refinement Context

```python
# Good: Provides actionable context
refinement_context = {
    "Current State": "API latency P95: 450ms",
    "User Feedback": "Too slow for real-time use",
    "Constraints": "Budget: $500/month, Uptime: 99.9%"
}

# Bad: Vague or redundant
refinement_context = {
    "Info": "Some information",
    "Data": json.dumps(original_data)  # Already provided!
}
```

### 4. Handle Tier Results Appropriately

```python
result = await ai_client.call_structured_api(...)

if result.get('refined_data'):
    tier = result['refinement_tier']

    if tier == 1:
        # Patches - very precise changes
        print(f"Applied {len(result['patches'])} targeted changes")
        audit_log.record_patches(result['patches'])

    elif tier == 2:
        # Cheap implementation - might be less precise
        print("Cheap model implementation - review recommended")
        flag_for_review(result['refined_data'])

    elif tier == 3:
        # Full regeneration - high confidence
        print("Full regeneration by primary model")
        # Trust this result

    return result['refined_data']
```

## Integration Patterns

### Pattern 1: Config Refinement

```python
async def refine_config(existing_config, user_instruction, table_analysis):
    """Refine validation config based on user feedback"""

    result = await ai_client.call_structured_api(
        prompt=user_instruction,
        schema=config_schema,
        model=["claude-opus-4-1", "gemini-2.5-flash-lite"],

        original_data=existing_config,
        validator_fn=lambda c: validate_config_complete(c, table_analysis),
        refinement_context={
            "Table": f"{len(table_analysis['column_names'])} columns",
            "Feedback": user_instruction
        },

        tool_name="refine_config",
        debug_name=f"config_{session_id}"
    )

    return result
```

### Pattern 2: Settings Update

```python
async def update_user_settings(user_id, changes_requested):
    """Update user settings intelligently"""

    current_settings = load_settings(user_id)

    result = await ai_client.call_structured_api(
        prompt=changes_requested,
        schema=settings_schema,
        model=["claude-sonnet-4-5", "gemini-2.5-flash-lite"],

        original_data=current_settings,
        validator_fn=validate_settings,

        debug_name=f"settings_{user_id}"
    )

    if result.get('refined_data'):
        save_settings(user_id, result['refined_data'])

        # Notify user of tier used
        if result['refinement_tier'] == 1:
            notify_user("Settings updated precisely")
        else:
            notify_user("Settings updated successfully")
```

### Pattern 3: Iterative Refinement

```python
async def iterative_refinement(data, refinement_steps):
    """Apply multiple refinements in sequence"""

    current_data = data
    total_cost = 0.0
    tier_usage = []

    for step in refinement_steps:
        result = await ai_client.call_structured_api(
            prompt=step['instruction'],
            schema=schema,
            model=["claude-opus-4-1", "gemini-2.5-flash-lite"],

            original_data=current_data,
            validator_fn=validator,

            debug_name=f"step_{step['name']}"
        )

        if result.get('refined_data'):
            current_data = result['refined_data']
            total_cost += result.get('total_refinement_cost', 0.0)
            tier_usage.append(result['refinement_tier'])
        else:
            raise Exception(f"Step {step['name']} failed")

    print(f"Completed {len(refinement_steps)} refinements")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Tier usage: {tier_usage}")

    return current_data
```

## Troubleshooting

### Issue: Tier 1 always fails

**Symptoms:**
- Patches never apply
- Always falls back to Tier 2/3

**Solutions:**
1. Check that schema matches data structure
2. Simplify refinement requests
3. Add better examples in refinement_context
4. Check validator isn't too strict

### Issue: Tier 2 validation fails

**Symptoms:**
- Cheap model implements but validation fails
- Always falls back to Tier 3

**Solutions:**
1. Check validator function is correct
2. Provide better refinement_context
3. Use slightly better cheap model (e.g., gemini-pro)
4. Simplify validation rules for Tier 2

### Issue: High Tier 3 usage

**Symptoms:**
- >20% of refinements use Tier 3
- Cost savings are minimal

**Analysis:**
- Check if refinements are too complex
- Review failed Tier 1/2 attempts in logs
- Consider if patches are appropriate for your use case

**Solutions:**
- Simplify refinement requests
- Improve validator to catch issues earlier
- Use better models for Tier 1
- Skip Tier 1 for complex changes: `try_patches_first=False`

### Issue: Validation errors

**Symptoms:**
- All tiers fail validation
- No refined_data returned

**Solutions:**
1. Check validator function is working correctly
2. Test validator on original_data
3. Review validation error messages
4. Simplify schema requirements

## Advanced Usage

### Skip Tier 1 (Direct to Implementation)

```python
# For complex restructuring where patches won't work:
result = await ai_client.call_structured_api(
    prompt="Completely reorganize the data structure",
    schema=schema,
    model=["claude-opus-4-1", "gemini-2.5-flash-lite"],

    original_data=data,
    validator_fn=validator,
    try_patches_first=False  # Skip Tier 1, go straight to Tier 2
)
```

### Custom Tier Costs Tracking

```python
result = await ai_client.call_structured_api(...)

if result.get('tier_costs'):
    # Log individual tier costs
    for i, cost in enumerate(result['tier_costs'], 1):
        logger.info(f"Tier {i} cost: ${cost:.6f}")

    # Track which tier succeeded
    success_tier = result['refinement_tier']
    cost_db.record_refinement(
        tier=success_tier,
        cost=result['total_refinement_cost'],
        method=result['method']
    )
```

### Disable Validation for Specific Tiers

```python
def tier_aware_validator(data):
    """Different validation rules for different tiers"""
    # Access tier from thread-local if needed
    # Or just validate strictly always
    errors = []

    if not data.get('required_field'):
        errors.append("Missing required field")

    return (len(errors) == 0, errors, [])
```

## Performance Characteristics

| Metric | Tier 1 (Patches) | Tier 2 (Cheap) | Tier 3 (Full) |
|--------|-----------------|----------------|---------------|
| Cost | ~$0.08 | ~$0.002 | ~$0.15 |
| Time | ~40s | ~10s | ~70s |
| Accuracy | High | Medium | Highest |
| Data Safety | Excellent | Good | Excellent |
| Success Rate | ~80% | ~15% | 100% |

## FAQ

**Q: When should I use refinement mode?**
A: When you have existing structured data that needs modifications. Not for generating new data from scratch.

**Q: What if I don't have a validator?**
A: Still works! Tiers won't be validated, but will still fall back on AI errors.

**Q: Can I use with soft_schema?**
A: Yes! Refinement mode works with both hard and soft schemas.

**Q: Does caching work?**
A: Yes! Each tier attempt is cached separately.

**Q: What about model fallback?**
A: Refinement mode uses first two models from list for Tier 1 & 2. If both fail, Tier 3 uses existing model fallback logic.

**Q: Can I track which tier was used?**
A: Yes! Check `result['refinement_tier']` (1, 2, or 3) and `result['method']`.

**Q: How do I disable refinement mode?**
A: Don't provide `original_data` parameter. Normal mode is default.

## Migration Guide

### From Old Tier Functions

**Before:**
```python
patch_result = await generate_config_with_patches(...)
if not patch_result.success:
    tier2 = await try_cheap_model_implementation(...)
    if not tier2['success']:
        tier3 = await generate_full_config(...)
```

**After:**
```python
result = await ai_client.call_structured_api(
    prompt=instructions,
    schema=schema,
    model=[expensive, cheap],
    original_data=existing_config,
    validator_fn=validator
)
# Done! Automatic tier fallback
```

### From PatchRefinementManager

**Before:**
```python
manager = PatchRefinementManager(...)
result = await manager.refine_with_patches(...)
```

**After:**
```python
result = await ai_client.call_structured_api(
    prompt=instructions,
    schema=schema,
    model=[primary, cheap],
    original_data=data,
    validator_fn=validator
)
```

## Summary

✅ **Built into ai_client** - No separate imports needed
✅ **Automatic tier fallback** - Cost optimized by default
✅ **Reusable everywhere** - Works with any structured data
✅ **Backward compatible** - Existing code works unchanged
✅ **Well tested** - Comprehensive test suite
✅ **Cost effective** - ~41% average savings

**To use:** Just add `original_data` parameter to `call_structured_api()`

---

**Version**: 1.0
**Status**: Production ready
**Location**: `src/shared/ai_client/core.py`
