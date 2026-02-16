# AI Client Refinement Mode Proposal

## Overview

Add a **3-tier refinement mode** to `ai_client` as a reusable pattern for cost-optimized structured data refinement.

## Why Bake Into ai_client?

✅ **Reusable** - Any code can use 3-tier refinement
✅ **Consistent** - Same logic everywhere
✅ **Cost optimization** - Automatic tier fallback
✅ **Simple API** - Single method call
✅ **Centralized** - Easy to tune/improve

## Proposed API

```python
from shared.ai_api_client import ai_client

result = await ai_client.refine_structured_data(
    original_data=my_config,
    instructions="Change company name to research",
    schema=my_schema,
    validator_fn=my_validator,

    # 3-Tier configuration
    tier1_model="claude-opus-4-1",  # Original model for patches
    tier2_model="gemini-2.0-flash-exp",  # Cheap model for full implementation
    tier3_model="claude-opus-4-1",  # Original model for full generation (fallback)

    # Optional
    context={},
    max_tokens=16000,
    debug_name="my_refinement"
)

if result.success:
    updated_data = result.data
    print(f"Tier used: {result.tier}")  # 1, 2, or 3
    print(f"Total cost: ${result.total_cost}")
```

## Implementation in ai_client

Add to `src/shared/ai_client/core.py`:

```python
async def refine_structured_data(
    self,
    original_data: Dict,
    instructions: str,
    schema: Dict,
    validator_fn: Optional[Callable] = None,

    # 3-Tier models
    tier1_model: str = "claude-opus-4-1",
    tier2_model: str = "gemini-2.0-flash-exp",
    tier3_model: Optional[str] = None,  # Defaults to tier1_model

    # Optional
    context: Optional[Dict] = None,
    examples: Optional[List] = None,
    max_tokens: int = 16000,
    debug_name: str = "refinement"
) -> RefinementResult:
    """
    3-Tier cost-optimized refinement of structured data.

    Tier 1: tier1_model generates JSON Patch operations
    Tier 2: If patches fail, tier2_model implements changes directly (full output)
    Tier 3: If tier2 fails, tier3_model generates full output (fallback)

    Args:
        original_data: Current data to refine
        instructions: User's refinement request
        schema: JSON schema for the data type
        validator_fn: Optional validation function (data) -> (is_valid, errors, warnings)
        tier1_model: Model for patch generation (usually expensive/accurate)
        tier2_model: Model for direct implementation (usually cheap/fast)
        tier3_model: Model for final fallback (defaults to tier1_model)
        context: Additional context for prompts
        examples: Example patches for tier 1
        max_tokens: Max tokens for responses
        debug_name: Name for logging/debugging

    Returns:
        RefinementResult with:
            - success: bool
            - data: Updated data if successful
            - tier: Which tier succeeded (1, 2, or 3)
            - total_cost: Combined cost across all tiers
            - tier_costs: Breakdown by tier
            - method: "patches", "direct_implementation", or "full_generation"

    Example:
        >>> result = await ai_client.refine_structured_data(
        ...     original_data=config,
        ...     instructions="Change model to claude-opus-4-6",
        ...     schema=config_schema,
        ...     validator_fn=validate_config
        ... )
        >>> if result.success:
        ...     new_config = result.data
        ...     print(f"Used tier {result.tier}, cost ${result.total_cost:.4f}")
    """

    tier3_model = tier3_model or tier1_model
    tier_costs = {'tier1': 0.0, 'tier2': 0.0, 'tier3': 0.0}

    logger.info(f"🎯 Starting 3-tier refinement: {debug_name}")
    logger.info(f"   Tier 1: {tier1_model} (patches)")
    logger.info(f"   Tier 2: {tier2_model} (direct)")
    logger.info(f"   Tier 3: {tier3_model} (full)")

    # TIER 1: Generate patches with tier1_model
    try:
        logger.info("📍 TIER 1: Generating patches...")

        patch_result = await self._tier1_generate_patches(
            original_data=original_data,
            instructions=instructions,
            schema=schema,
            validator_fn=validator_fn,
            model=tier1_model,
            context=context,
            examples=examples,
            max_tokens=max_tokens,
            debug_name=f"{debug_name}_tier1"
        )

        tier_costs['tier1'] = patch_result.cost

        if patch_result.success:
            logger.info(f"✅ TIER 1 SUCCESS: ${patch_result.cost:.4f}")
            return RefinementResult(
                success=True,
                data=patch_result.data,
                tier=1,
                method="patches",
                total_cost=tier_costs['tier1'],
                tier_costs=tier_costs,
                patches=patch_result.patches,
                reasoning=patch_result.reasoning
            )

        # Tier 1 failed, try tier 2
        logger.warning(f"⚠️ TIER 1 FAILED: {patch_result.error}")

    except Exception as e:
        logger.error(f"❌ TIER 1 EXCEPTION: {e}")

    # TIER 2: Direct implementation with cheap model
    try:
        logger.info("📍 TIER 2: Cheap model direct implementation...")

        tier2_result = await self._tier2_direct_implementation(
            original_data=original_data,
            instructions=instructions,
            schema=schema,
            validator_fn=validator_fn,
            failed_patches=patch_result.patches if 'patch_result' in locals() else None,
            model=tier2_model,
            context=context,
            max_tokens=max_tokens,
            debug_name=f"{debug_name}_tier2"
        )

        tier_costs['tier2'] = tier2_result.cost

        if tier2_result.success:
            logger.info(f"✅ TIER 2 SUCCESS: ${tier2_result.cost:.4f}")
            total = tier_costs['tier1'] + tier_costs['tier2']
            return RefinementResult(
                success=True,
                data=tier2_result.data,
                tier=2,
                method="direct_implementation",
                total_cost=total,
                tier_costs=tier_costs,
                reasoning=tier2_result.reasoning
            )

        # Tier 2 failed, try tier 3
        logger.warning(f"⚠️ TIER 2 FAILED: {tier2_result.error}")

    except Exception as e:
        logger.error(f"❌ TIER 2 EXCEPTION: {e}")

    # TIER 3: Full generation with original model
    logger.info("📍 TIER 3: Original model full generation...")

    tier3_result = await self._tier3_full_generation(
        original_data=original_data,
        instructions=instructions,
        schema=schema,
        validator_fn=validator_fn,
        model=tier3_model,
        context=context,
        max_tokens=max_tokens,
        debug_name=f"{debug_name}_tier3"
    )

    tier_costs['tier3'] = tier3_result.cost
    total = sum(tier_costs.values())

    if tier3_result.success:
        logger.info(f"✅ TIER 3 SUCCESS: ${tier3_result.cost:.4f}")
        return RefinementResult(
            success=True,
            data=tier3_result.data,
            tier=3,
            method="full_generation",
            total_cost=total,
            tier_costs=tier_costs,
            reasoning=tier3_result.reasoning
        )

    # All tiers failed
    logger.error(f"❌ ALL TIERS FAILED")
    return RefinementResult(
        success=False,
        error="All 3 tiers failed",
        tier=None,
        total_cost=total,
        tier_costs=tier_costs
    )
```

## Benefits

### For Config Generation

```python
# Before (current code)
patch_result = await generate_config_with_patches(...)
if not patch_result.success:
    tier2_result = await try_cheap_model_implementation(...)
    if not tier2_result.success:
        # Fallback to full generation...

# After (with ai_client mode)
result = await ai_client.refine_structured_data(
    original_data=existing_config,
    instructions=instructions,
    schema=config_schema,
    validator_fn=validate_config_complete,
    tier1_model="claude-opus-4-1",
    tier2_model="gemini-2.0-flash-exp"
)
# Done! Automatic tier fallback
```

### For Other Use Cases

```python
# User settings refinement
result = await ai_client.refine_structured_data(
    original_data=user_settings,
    instructions="Enable notifications",
    schema=settings_schema,
    tier1_model="claude-sonnet-4-5",
    tier2_model="gemini-flash-2.5"
)

# API config optimization
result = await ai_client.refine_structured_data(
    original_data=api_config,
    instructions="Optimize for latency",
    schema=api_schema,
    tier1_model="claude-opus-4-1",
    tier2_model="gemini-flash-2.5"
)
```

## Cost Savings

| Scenario | Tier 1 (Patches) | Tier 2 (Cheap Direct) | Tier 3 (Expensive Full) | Total |
|----------|-----------------|---------------------|----------------------|-------|
| Success Tier 1 | $0.08 | - | - | $0.08 |
| Success Tier 2 | $0.08 | $0.002 | - | $0.082 |
| Success Tier 3 | $0.08 | $0.002 | $0.15 | $0.232 |
| **vs Always Tier 3** | - | - | $0.15 | $0.15 |

With 80% Tier 1 success rate:
- Average cost: **$0.088** (41% savings)
- With 15% Tier 2 success: **$0.080** (47% savings)

## Implementation Plan

1. **Phase 1**: Add `refine_structured_data()` to ai_client
2. **Phase 2**: Implement internal `_tier1_generate_patches()`, `_tier2_direct_implementation()`, `_tier3_full_generation()`
3. **Phase 3**: Update config generation to use new mode
4. **Phase 4**: Document and evangelize for other use cases

## Open Questions

1. Should tier models be configurable per-project?
2. Should we add a Tier 0 (code-based interpretation)?
3. Should we track tier success rates in metrics?
4. Should we allow skipping tiers? (e.g., skip tier 2)

## Next Steps

**Immediate**:
- Get feedback on API design
- Decide on implementation location in ai_client

**Soon**:
- Implement in ai_client
- Migrate config generation to use it
- Add metrics tracking

---

**Status**: Proposal
**Owner**: TBD
**Priority**: High (cost optimization)
