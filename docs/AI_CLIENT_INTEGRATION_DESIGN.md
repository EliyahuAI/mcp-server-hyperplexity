# Integrating 3-Tier Refinement into call_structured_api

## Current Architecture

`call_structured_api` already has:
- ✅ Model fallback: `model=['primary', 'backup1', 'backup2']`
- ✅ Hard/soft schema modes
- ✅ Retry logic
- ✅ Cache handling
- ✅ Error recovery

## Proposed Integration

### Option 1: Add Refinement Parameters (RECOMMENDED)

Extend `call_structured_api` with optional refinement parameters:

```python
async def call_structured_api(
    self,
    prompt: str,
    schema: Dict,
    model: Union[str, List[str]] = "claude-sonnet-4-5",
    tool_name: str = "structured_response",

    # ... existing parameters ...

    # NEW: Refinement mode parameters
    original_data: Optional[Dict] = None,  # If provided, enables refinement mode
    validator_fn: Optional[Callable] = None,  # For validating refined data
    try_patches_first: bool = True,  # Tier 1: try patches before full
    cheap_implementation_model: Optional[str] = None,  # Tier 2: cheap model for direct implementation

    **kwargs
) -> Dict:
```

### How It Works

**Normal mode** (original_data=None):
```python
# Standard structured API call - works as before
result = await ai_client.call_structured_api(
    prompt="Extract data from this text",
    schema=extraction_schema,
    model="claude-opus-4-1"
)
```

**Refinement mode** (original_data provided):
```python
# 3-tier refinement automatically activated
result = await ai_client.call_structured_api(
    prompt="Change company name to research",  # User instruction
    schema=config_schema,  # Full config schema
    model=["claude-opus-4-1", "gemini-2.0-flash-exp"],  # [expensive, cheap]

    # Refinement mode
    original_data=existing_config,  # Triggers refinement
    validator_fn=validate_config,  # Validates each attempt
    try_patches_first=True  # Tier 1: patches
)
```

### Internal Flow

```python
if original_data is not None:
    # REFINEMENT MODE - 3 Tiers

    # TIER 1: Primary model generates patches
    if try_patches_first:
        patch_schema = create_patch_schema(schema)
        patch_prompt = build_patch_prompt(prompt, original_data)

        result = await self._try_with_model(
            prompt=patch_prompt,
            schema=patch_schema,
            model=models_to_try[0],  # Primary model
            tool_name=f"{tool_name}_patches"
        )

        if result:
            # Try to apply patches
            patched_data = apply_patches(original_data, result['patches'])

            if validator_fn and validator_fn(patched_data):
                # SUCCESS - Tier 1
                return {
                    **result,
                    'refinement_tier': 1,
                    'refined_data': patched_data,
                    'method': 'patches'
                }

    # TIER 2: Cheap model with direct implementation
    if cheap_implementation_model or len(models_to_try) > 1:
        cheap_model = cheap_implementation_model or models_to_try[1]

        # Show failed patches + original JSON
        tier2_prompt = build_tier2_prompt(
            prompt,
            original_data,
            failed_patches=result.get('patches') if result else None
        )

        result = await self._try_with_model(
            prompt=tier2_prompt,
            schema=schema,  # Full schema
            model=cheap_model,
            tool_name=f"{tool_name}_implementation"
        )

        if result:
            refined_data = result['structured_data']

            if validator_fn and validator_fn(refined_data):
                # SUCCESS - Tier 2
                return {
                    **result,
                    'refinement_tier': 2,
                    'refined_data': refined_data,
                    'method': 'cheap_implementation'
                }

    # TIER 3: Primary model with full generation (fallback)
    # Use existing model fallback logic
    tier3_prompt = build_full_generation_prompt(prompt, original_data)

    # Continue with normal flow using tier3_prompt
    prompt = tier3_prompt
    # Fall through to normal execution...

# NORMAL MODE - Standard structured API call
# ... existing code ...
```

## Implementation Details

### 1. Prompt Builders

```python
def build_patch_prompt(instruction: str, original_data: Dict) -> str:
    """Build prompt for Tier 1 (patches)"""
    return f"""
# USER REQUEST
{instruction}

# CURRENT DATA
```json
{json.dumps(original_data, indent=2)}
```

# TASK
Generate JSON Patch operations (RFC 6902) to implement the requested changes.
Use minimal patches - only change what's requested.
"""

def build_tier2_prompt(instruction: str, original_data: Dict, failed_patches: List = None) -> str:
    """Build prompt for Tier 2 (cheap implementation)"""
    context = ""
    if failed_patches:
        context = f"""
# FAILED PATCHES (for reference)
These patches didn't work:
```json
{json.dumps(failed_patches, indent=2)}
```
"""

    return f"""
# USER REQUEST
{instruction}

# CURRENT DATA
```json
{json.dumps(original_data, indent=2)}
```

{context}

# TASK
Implement the requested changes directly. Return the complete updated data.
Make ONLY the changes requested, keep everything else as-is.
"""

def build_full_generation_prompt(instruction: str, original_data: Dict) -> str:
    """Build prompt for Tier 3 (full generation)"""
    return f"""
# USER REQUEST
{instruction}

# CURRENT DATA (for context)
```json
{json.dumps(original_data, indent=2)}
```

# TASK
Generate the complete updated data with the requested changes.
Ensure all required fields are present and valid.
"""
```

### 2. Schema Management

```python
# Tier 1: Patch schema
patch_schema = {
    "type": "object",
    "properties": {
        "patch_operations": {"type": "array", "items": {...}},
        "reasoning": {"type": "string"}
    }
}

# Tier 2 & 3: Full schema (original schema passed in)
```

### 3. Validation Integration

```python
if validator_fn:
    is_valid, errors, warnings = validator_fn(refined_data)

    if not is_valid:
        logger.warning(f"Validation failed: {errors}")
        # Try next tier
        continue
```

## Usage Examples

### Config Refinement

```python
result = await ai_client.call_structured_api(
    prompt="Change company name importance to RESEARCH",
    schema=config_schema,
    model=["claude-opus-4-1", "gemini-2.0-flash-exp"],

    # Refinement mode
    original_data=existing_config,
    validator_fn=validate_config_complete,
    try_patches_first=True,

    # Standard params
    tool_name="refine_config",
    debug_name="config_refinement_session123"
)

# Result includes:
# - refinement_tier: 1, 2, or 3
# - refined_data: The updated config
# - method: "patches", "cheap_implementation", or "full_generation"
# - All standard fields: cost, tokens, time, etc.
```

### User Settings

```python
result = await ai_client.call_structured_api(
    prompt="Enable notifications",
    schema=settings_schema,
    model=["claude-sonnet-4-5", "gemini-2.0-flash-exp"],

    original_data=user_settings,
    validator_fn=validate_settings,

    debug_name="settings_refinement"
)
```

## Advantages

### ✅ Leverages Existing Features

- Uses existing model fallback list
- Uses existing cache system
- Uses existing error handling
- Uses existing hard/soft schema logic

### ✅ Clean API

```python
# No refinement (normal mode)
result = await call_structured_api(prompt, schema, model)

# With refinement (auto 3-tier)
result = await call_structured_api(
    prompt, schema, model,
    original_data=data,  # Just add this!
    validator_fn=validator
)
```

### ✅ Backwards Compatible

- Existing calls work unchanged
- New parameters are optional
- No breaking changes

### ✅ Unified Metrics

- All tiers tracked in same place
- Cost aggregation automatic
- Token usage consistent

## Alternative: Layer on Top

Could also create `refine_structured_data()` that wraps `call_structured_api`:

```python
async def refine_structured_data(self, original_data, instruction, schema, models, validator_fn):
    # Tier 1: Patches
    result = await self.call_structured_api(
        prompt=build_patch_prompt(instruction, original_data),
        schema=patch_schema,
        model=models[0]
    )
    # ... etc
```

**Pros:**
- Cleaner separation
- Easier to understand
- Less complexity in call_structured_api

**Cons:**
- Duplicate logic (caching, retries, etc.)
- More code to maintain
- Can't leverage model fallback as easily

## Recommendation

**Integrate directly into `call_structured_api`** with optional parameters:

1. Minimal API surface (`original_data` triggers refinement mode)
2. Leverages all existing infrastructure
3. Single source of truth for metrics
4. Easy to add Tier 0 (code interpretation) later
5. Works with all existing features (cache, soft schema, etc.)

## Migration Path

1. Add parameters to `call_structured_api` signature
2. Add refinement mode logic before normal execution
3. Update config generation to use new parameters:
   ```python
   # Before:
   result = await generate_config_with_patches(...)
   if not result.success:
       result = await try_cheap_model_implementation(...)
       if not result.success:
           result = await generate_full_config(...)

   # After:
   result = await ai_client.call_structured_api(
       prompt=instructions,
       schema=config_schema,
       model=["claude-opus-4-1", "gemini-2.0-flash-exp"],
       original_data=existing_config,
       validator_fn=validate_config_complete
   )
   ```
4. Add metrics dashboard for tier success rates
5. Tune based on production data

## Next Steps

1. **Prototype** the integration in core.py
2. **Test** with existing config generation
3. **Measure** tier success rates and cost savings
4. **Document** the new parameters
5. **Evangelize** for other use cases

---

**Status**: Design Proposal
**Decision Needed**: Integrate directly vs layer on top
**Recommendation**: Integrate directly (better leverage of existing features)
