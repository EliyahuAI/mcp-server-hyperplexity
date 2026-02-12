# 3-Tier Refinement Implementation Summary

## What We Built

A **3-tier cost-optimized refinement system** for config generation with automatic fallback:

```
TIER 1: Original Model → Patches       (Try patches with good model)
   ↓ (if patches fail)
TIER 2: Cheap Model → Full Implementation (Show failed patches + JSON, ask cheap model to implement)
   ↓ (if cheap model fails)
TIER 3: Original Model → Full Generation  (Fallback to expensive full generation)
```

## Current Status

### ✅ Implemented

1. **JSON Patch utilities** (`src/shared/ai_patch_utils.py`)
   - `PatchRefinementManager` - High-level manager
   - `apply_patches_with_validation()` - Safe patch application
   - `create_patch_schema()` - Schema factory
   - Full dataclasses and error handling

2. **Config Generation Integration** (`src/lambdas/interface/actions/config_generation/__init__.py`)
   - **Tier 1**: `generate_config_with_patches()` - Uses original model for patches
   - **Tier 2**: `try_cheap_model_implementation()` - Uses gemini-flash for direct implementation
   - **Tier 3**: Falls back to `generate_config_unified()` - Uses original model for full generation

3. **Tests**
   - `test_patch_refinement.py` - Basic patch tests ✅
   - `test_patch_mock_ai.py` - Mock AI tests ✅
   - `test_two_tier_models.py` - Two-tier tests ✅

4. **Documentation**
   - `docs/AI_PATCH_UTILS_GUIDE.md` - Complete API guide
   - `docs/PATCH_REFINEMENT_IMPLEMENTATION.md` - Implementation details
   - `docs/AI_CLIENT_REFINEMENT_MODE.md` - Proposal for ai_client integration

### 🎯 How It Works Now

**For Config Refinement:**

```python
# User requests: "Change Company Name to RESEARCH"

# Tier 1: Original model generates patches
patches = [
    {"op": "replace", "path": "/validation_targets/1/importance", "value": "RESEARCH"}
]
# Try to apply → If succeeds: Done! ✅

# Tier 2: If patches fail (bad path, etc.)
# Call gemini-flash-2.5:
# "These patches failed: [...], here's the JSON: {...}, implement the changes"
# → Returns full config with changes
# → Validate → If succeeds: Done! ✅

# Tier 3: If cheap model fails
# Call original model:
# "Generate full config with these changes"
# → Returns full config
# → Done! ✅
```

### 💰 Cost Analysis

| Tier | Model | Method | Cost | Time | Success Rate* |
|------|-------|--------|------|------|--------------|
| 1 | claude-opus-4-1 | Patches | ~$0.08 | ~40s | ~80% |
| 2 | gemini-flash-2.5 | Full | ~$0.002 | ~10s | ~15% |
| 3 | claude-opus-4-1 | Full | ~$0.15 | ~70s | 100% |

*Estimated

**Average cost with 80% Tier 1 success:**
- Tier 1 success: 0.80 × $0.08 = $0.064
- Tier 2 success: 0.15 × ($0.08 + $0.002) = $0.0123
- Tier 3 fallback: 0.05 × ($0.08 + $0.002 + $0.15) = $0.0116
- **Total average: $0.088** (vs $0.15 always → **41% savings**)

## Next Steps

### Option A: Keep Current Implementation

**Pros:**
- Works now
- Specific to config generation
- Easy to tune for this use case

**Cons:**
- Not reusable for other data types
- Duplicated logic if we need it elsewhere
- Harder to maintain tier logic

### Option B: Bake Into ai_client ⭐ **RECOMMENDED**

**Pros:**
- ✅ Reusable everywhere
- ✅ Consistent API
- ✅ Centralized tuning
- ✅ Easy to add Tier 0 (code interpretation)
- ✅ Metrics tracking in one place

**Implementation:**
```python
# In ai_client
result = await ai_client.refine_structured_data(
    original_data=my_data,
    instructions="change X to Y",
    schema=my_schema,
    validator_fn=my_validator,
    tier1_model="claude-opus-4-1",
    tier2_model="gemini-2.0-flash-exp"
)

# Automatic 3-tier fallback!
# Returns: result.tier (1, 2, or 3), result.data, result.total_cost
```

**Migration:**
```python
# Config generation becomes:
result = await ai_client.refine_structured_data(
    original_data=existing_config,
    instructions=instructions,
    schema=config_schema,
    validator_fn=validate_config_complete,
    context={
        "table_analysis": table_analysis,
        "validation_results": latest_validation_results
    }
)

if result.success:
    return format_result(result)
```

## Immediate Actions Needed

1. **Decision**: Keep current implementation or migrate to ai_client?

2. **If ai_client approach**:
   - [ ] Design `refine_structured_data()` API in ai_client
   - [ ] Implement tier logic in ai_client
   - [ ] Migrate config generation to use it
   - [ ] Add metrics tracking

3. **If current approach**:
   - [ ] Add Tier 0 (code interpretation) if needed
   - [ ] Tune tier models based on production data
   - [ ] Add metrics tracking for tier success rates

4. **Testing**:
   - [ ] Deploy to dev environment
   - [ ] Test with real config refinements
   - [ ] Monitor tier success rates
   - [ ] Measure cost savings

## Files Changed

**New:**
- `src/shared/ai_patch_utils.py` - Reusable patch utilities
- `src/shared/code_interpreter.py` - Code-based interpretation (Tier 0 candidate)
- `test_patch_refinement.py` - Basic tests
- `test_patch_mock_ai.py` - Mock AI tests
- `test_two_tier_models.py` - Two-tier tests
- `test_three_tier_models.py` - Three-tier tests (TODO)
- `docs/AI_PATCH_UTILS_GUIDE.md` - API guide
- `docs/PATCH_REFINEMENT_IMPLEMENTATION.md` - Implementation details
- `docs/AI_CLIENT_REFINEMENT_MODE.md` - Proposal for ai_client

**Modified:**
- `src/lambdas/interface/actions/config_generation/__init__.py` - Added 3-tier logic
- `deployment/requirements-interface-lambda.txt` - Added jsonpatch
- `deployment/requirements-lambda.txt` - Added jsonpatch

## Questions for Discussion

1. **Model Selection**:
   - Should Tier 2 use gemini-flash-2.5 or gemini-flash-2.0?
   - Should we allow per-project tier configuration?

2. **Tier 0**:
   - Should we add code-based interpretation (no LLM)?
   - What patterns are common enough to parse?

3. **Metrics**:
   - Track tier success rates?
   - Track cost savings?
   - Alert if Tier 1 success rate drops?

4. **API Design**:
   - Bake into ai_client? (Recommended)
   - Keep as separate utility?
   - Hybrid approach?

## Recommendation

**Bake into ai_client** for maximum reusability and maintainability:

```python
# One API for all structured data refinement
result = await ai_client.refine_structured_data(
    original_data=data,
    instructions=instructions,
    schema=schema,
    validator_fn=validator,
    tier1_model="expensive-accurate",
    tier2_model="cheap-fast",
    # Optional Tier 0
    try_code_interpretation=True
)

# Works for:
# - Config generation
# - User settings
# - API configurations
# - Any structured data
```

---

**Status**: Implemented (ready for testing)
**Next**: Decide on ai_client integration
**Priority**: High (cost optimization)
