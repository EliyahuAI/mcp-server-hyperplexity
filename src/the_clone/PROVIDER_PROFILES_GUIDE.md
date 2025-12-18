# Provider Profiles & Tier System

## Overview

The Clone now uses a **provider profiles** system with **4 synthesis tiers** for clean model selection.

## Usage

### Selecting a Provider

```python
# Default: DeepSeek provider (cost-optimized)
result = await clone.query("your question")

# Claude provider (all-Claude for maximum reliability)
result = await clone.query("your question", provider="claude")

# Baseten provider (DeepSeek via Baseten for lower latency)
result = await clone.query("your question", provider="baseten")

# Backwards compatibility
result = await clone.query("your question", use_baseten=True)  # Same as provider="baseten"
```

## Model Mappings

The `initial_decision` model automatically selects a synthesis tier (tier1-4) based on complexity. The tier then maps to models based on the provider:

| Tier | DeepSeek Provider | Claude Provider | Baseten Provider |
|------|-------------------|-----------------|------------------|
| **tier1** (Simple facts) | deepseek-v3.2 | haiku-4-5 | deepseek-v3.2-baseten |
| **tier2** (Master's-level) | deepseek-v3.2 | sonnet-4-5 | deepseek-v3.2-baseten |
| **tier3** (PhD-level) | sonnet-4-5 | sonnet-4-5 | sonnet-4-5 |
| **tier4** (PhD + Grant) | opus-4-5 | opus-4-5 | opus-4-5 |

## Tier Selection (Automatic)

The system automatically selects tiers based on **synthesis complexity only**:

- **tier1**: Simple factual lookups (no synthesis needed)
- **tier2**: Standard synthesis - organizing multiple aspects (DEFAULT)
- **tier3**: Complex technical synthesis with conflicting sources
- **tier4**: Maximum complexity - multi-layered cross-domain synthesis

## Examples

```python
# Most queries use provider="deepseek" (default) and get tier2 automatically
result = await clone.query("Explain transformer architecture")
# Uses: deepseek-v3.2 for all stages

# Complex analysis might trigger tier3
result = await clone.query("Synthesize conflicting research on X's effectiveness")
# Uses: deepseek-v3.2 for extraction, sonnet-4-5 for synthesis

# Using Claude provider for maximum reliability
result = await clone.query("Compare GPT-4 vs Claude", provider="claude")
# Uses: haiku-4-5 for extraction, sonnet-4-5 for synthesis (tier2)

# Baseten for lower latency
result = await clone.query("What is DeepSeek V3?", provider="baseten")
# Uses: deepseek-v3.2-baseten for all stages
```
