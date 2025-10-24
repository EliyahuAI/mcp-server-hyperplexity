# Table Maker Config Migration Guide

**Version:** 3.0 (Phase 1-3 Features)
**Date:** 2025-10-24

---

## Overview

This guide explains the changes to `table_maker_config.json` for the v3.0 redesign, which adds:
- **QC Strategy Selection**: Choose between traditional LLM-based QC, validator lambda QC, or both
- **Validator Lambda Integration**: Use validator lambda for quality checks with 2x1 hard/soft requirement weighting
- **QC Retrigger**: Allow QC to request additional discovery rounds with new subdomains

---

## What Changed in the Config

### New Settings in `qc_review` Section

The following settings have been added to the `qc_review` configuration block:

```json
{
  "qc_review": {
    // Existing settings (unchanged)
    "model": "claude-sonnet-4-5",
    "max_tokens": 8000,
    "min_qc_score": 0.5,
    "min_row_count": 4,
    "min_row_count_for_frontend": 4,
    "max_row_count": 50,
    "enable_qc": true,

    // NEW: QC Strategy Selection
    "qc_strategy": "traditional",        // Options: "traditional" | "validator" | "both"

    // NEW: Validator Lambda QC Configuration
    "validator_qc_model": "sonar",       // Model for validator lambda ("sonar" or "sonar-pro")
    "validator_qc_context": "low",       // Context size ("low", "medium", or "high")

    // NEW: Retrigger Configuration
    "allow_retrigger": true,             // Enable QC to request additional discovery
    "max_retriggers": 1                  // Maximum retrigger cycles (prevents loops)
  }
}
```

---

## What Each New Setting Does

### 1. `qc_strategy` (Default: "traditional")

Controls which QC method is used to review discovered rows.

**Options:**
- **"traditional"**: Use the existing LLM-based QC review
  - QC model (Claude Sonnet 4.5) analyzes rows and provides qualitative judgments
  - Uses `qc_review.md` prompt
  - Best for nuanced quality assessment

- **"validator"**: Use validator lambda for QC
  - Generates validator config with columns for each requirement
  - Uses existence check + requirement scoring (-2 to +2 scale)
  - Applies 2x1 weighting (hard requirements weighted double)
  - Best for consistent, objective scoring

- **"both"**: Run both traditional and validator QC, then merge results
  - Intersection of approved = approve
  - Union of approved = demote
  - Best for highest quality standards

**When to use:**
- Use "traditional" for most tables (default, well-tested)
- Use "validator" when you want consistent, repeatable scoring
- Use "both" for critical tables where quality is paramount

---

### 2. `validator_qc_model` (Default: "sonar")

Specifies which search model the validator lambda should use when `qc_strategy` is "validator" or "both".

**Options:**
- **"sonar"**: Standard Perplexity model
  - Faster, lower cost
  - Good for most use cases

- **"sonar-pro"**: Premium Perplexity model
  - Higher quality search results
  - Use for complex requirements or when accuracy is critical

**When to use:**
- Use "sonar" as default (good balance of speed and quality)
- Use "sonar-pro" for tables with complex requirements or when validator QC is giving inconsistent results

---

### 3. `validator_qc_context` (Default: "low")

Specifies the search context size for validator lambda when `qc_strategy` is "validator" or "both".

**Options:**
- **"low"**: Minimal context (fastest, cheapest)
- **"medium"**: Moderate context
- **"high"**: Maximum context (slowest, most thorough)

**When to use:**
- Use "low" as default (sufficient for most QC checks)
- Use "medium" or "high" if requirements need deeper research to verify

---

### 4. `allow_retrigger` (Default: true)

Enables QC to request an additional discovery round with completely new subdomains.

**Behavior:**
- When enabled, QC can analyze discovery results and request a retrigger if:
  - Results are insufficient in quantity or quality
  - Different search strategies might yield better results
  - Domain filtering or requirements need adjustment

- QC provides:
  - New subdomains (complete redesign, not modifications)
  - Optionally: updated requirements (relax/tighten)
  - Optionally: updated domain filters

- New discovery results are merged with existing results (deduplicated)

**When to use:**
- Keep `true` as default (allows system to self-correct)
- Set to `false` only if you want strict one-pass discovery (not recommended)

---

### 5. `max_retriggers` (Default: 1)

Maximum number of retrigger cycles to prevent infinite loops.

**Behavior:**
- After QC completes, if it requests a retrigger and `retry_count < max_retriggers`:
  - System runs new discovery with QC-specified subdomains
  - Runs QC again (with retrigger disabled to prevent loops)
  - Merges results

- Typically set to 1 (one additional chance to improve results)

**When to use:**
- Use 1 as default (one retrigger is usually sufficient)
- Increase to 2 only for experimental scenarios (risk of diminishing returns)
- Never set to 0 (use `allow_retrigger: false` instead)

---

## Configuration Scenarios

### Scenario 1: Traditional QC Only (Default)

**Use case:** Standard table generation, well-understood requirements

```json
{
  "qc_review": {
    "qc_strategy": "traditional",
    "allow_retrigger": true,
    "max_retriggers": 1
  }
}
```

**Behavior:**
- Uses LLM-based QC review
- QC can request retrigger if needed
- Validator settings ignored

---

### Scenario 2: Validator Lambda QC Only

**Use case:** Tables where consistent, objective scoring is preferred

```json
{
  "qc_review": {
    "qc_strategy": "validator",
    "validator_qc_model": "sonar",
    "validator_qc_context": "low",
    "allow_retrigger": true,
    "max_retriggers": 1
  }
}
```

**Behavior:**
- Uses validator lambda for QC
- Generates config with existence + requirement columns
- Applies 2x1 hard/soft weighting
- QC can request retrigger if needed

---

### Scenario 3: Both QC Methods (Highest Quality)

**Use case:** Critical tables where you want maximum quality assurance

```json
{
  "qc_review": {
    "qc_strategy": "both",
    "validator_qc_model": "sonar-pro",
    "validator_qc_context": "medium",
    "allow_retrigger": true,
    "max_retriggers": 1
  }
}
```

**Behavior:**
- Runs both traditional and validator QC
- Rows approved by both = approve
- Rows approved by one = demote
- Uses premium model and medium context for validator
- QC can request retrigger if needed

---

### Scenario 4: No Retrigger (Strict One-Pass)

**Use case:** Time-constrained scenarios or when retrigger not desired

```json
{
  "qc_review": {
    "qc_strategy": "traditional",
    "allow_retrigger": false,
    "max_retriggers": 0
  }
}
```

**Behavior:**
- Uses LLM-based QC review
- QC cannot request retrigger
- Results are final after first QC pass

---

### Scenario 5: Validator QC with Premium Settings

**Use case:** Complex requirements that need thorough verification

```json
{
  "qc_review": {
    "qc_strategy": "validator",
    "validator_qc_model": "sonar-pro",
    "validator_qc_context": "high",
    "allow_retrigger": true,
    "max_retriggers": 1
  }
}
```

**Behavior:**
- Uses validator lambda with premium search model
- High context for thorough requirement verification
- QC can request retrigger if needed

---

## Migration Checklist

If you have an existing `table_maker_config.json` file, follow these steps:

1. **Backup your current config**
   ```bash
   cp table_maker_config.json table_maker_config.json.backup
   ```

2. **Add new settings to `qc_review` section**
   - Add `"qc_strategy": "traditional"` (keeps current behavior)
   - Add `"validator_qc_model": "sonar"`
   - Add `"validator_qc_context": "low"`
   - Add `"allow_retrigger": true`
   - Add `"max_retriggers": 1`

3. **Review existing settings**
   - Verify `min_row_count` and `min_row_count_for_frontend` are present (added in previous update)
   - Verify all other existing settings are unchanged

4. **Optional: Add inline comments**
   - Use `_comment_*` fields to document settings
   - See updated config for examples

5. **Test configuration**
   - Run a test table generation
   - Verify QC behaves as expected
   - Check logs for any configuration errors

---

## Backward Compatibility

**Good news:** The new settings have sensible defaults that maintain existing behavior.

- If `qc_strategy` is missing, system defaults to "traditional"
- If `allow_retrigger` is missing, system defaults to `false` (safe default)
- If `validator_qc_model` or `validator_qc_context` are missing, system uses "sonar" and "low"

**However:** It's strongly recommended to explicitly set these values in your config for clarity.

---

## Related Documentation

- **TABLE_MAKER_REDESIGN_REQUIREMENTS.md**: Full Phase 1-3 requirements
- **TABLE_MAKER_GUIDE.md**: Overall table maker system guide
- **Validator Lambda QC**: See Phase 3 in requirements doc for 2x1 weighting formula
- **QC Retrigger**: See Phase 2 in requirements doc for retrigger behavior

---

## Questions?

If you're unsure which configuration to use:

1. **Start with defaults** (traditional QC, allow retrigger)
2. **Monitor QC quality** over several table generations
3. **Switch to validator** if you notice inconsistent quality judgments
4. **Use both** if quality is critical and cost is less important

The traditional QC strategy is well-tested and works well for most tables. The validator strategy is newer but provides more consistent scoring for tables with clear, measurable requirements.
