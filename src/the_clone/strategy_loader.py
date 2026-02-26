#!/usr/bin/env python3
"""
Strategy configuration loader for The Clone.
Manages breadth/depth-based search strategies.
"""

import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def load_strategy_config() -> Dict[str, Any]:
    """Load strategy configuration from JSON file."""
    config_path = os.path.join(os.path.dirname(__file__), 'strategy_config.json')

    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_strategy(breadth: str, depth: str) -> Dict[str, Any]:
    """
    Get strategy configuration based on breadth and depth.

    Args:
        breadth: "narrow" or "broad"
        depth: "shallow" or "deep"

    Returns:
        Strategy configuration dict
    """
    config = load_strategy_config()
    strategies = config['strategies']

    # Map breadth/depth to strategy
    strategy_map = {
        ('narrow', 'shallow'): 'targeted',
        ('narrow', 'deep'): 'focused_deep',
        ('narrow', 'extraction'): 'extraction',  # NEW: Extraction mode
        ('broad', 'shallow'): 'survey',
        ('broad', 'deep'): 'comprehensive',
        ('findall', 'shallow'): 'findall_breadth'
    }

    strategy_name = strategy_map.get((breadth, depth), 'targeted')
    strategy = strategies[strategy_name].copy()
    strategy['name'] = strategy_name

    return strategy


def get_global_limits() -> Dict[str, int]:
    """Get global iteration and source limits."""
    config = load_strategy_config()
    return config['global_limits']


def get_provider_config(provider: str = "deepseek") -> Dict[str, Any]:
    """
    Get provider configuration.

    Args:
        provider: Provider name ("deepseek", "claude", or "baseten")

    Returns:
        Provider configuration dict
    """
    config = load_strategy_config()
    if provider not in config['providers']:
        logger.warning(f"Provider '{provider}' not found, falling back to 'deepseek'")
        provider = 'deepseek'
    return config['providers'][provider]


def get_models_for_tier(provider: str, synthesis_tier: str, strategy: Dict = None) -> Dict[str, str]:
    """
    Get models for specified provider and synthesis tier.

    Args:
        provider: Provider name ("deepseek", "claude", or "baseten")
        synthesis_tier: Tier name ("tier1", "tier2", "tier3", or "tier4")
        strategy: Optional strategy config (can override synthesis model)

    Returns:
        Dict with model configuration for all stages
    """
    provider_config = get_provider_config(provider)

    # Validate tier
    if synthesis_tier not in provider_config['tiers']:
        logger.warning(f"Tier '{synthesis_tier}' not found for provider '{provider}', falling back to 'tier2'")
        synthesis_tier = 'tier2'

    tier_config = provider_config['tiers'][synthesis_tier]
    extraction_model = provider_config['default_extraction_model']

    # Use Gemini 3 Flash Preview for initial decision (medium thinking, best reasoning at low cost)
    routing_model = 'gemini-3-flash-preview'

    # Check if strategy overrides synthesis model (for extraction mode)
    synthesis_model = tier_config['synthesis']
    if strategy and 'synthesis_model' in strategy:
        synthesis_model = strategy['synthesis_model']
        logger.debug(f"[STRATEGY] Using strategy-specific synthesis model: {synthesis_model}")

    return {
        'initial_decision': routing_model,
        'triage': extraction_model,
        'extraction': extraction_model,
        'synthesis': synthesis_model
    }


def get_default_models(provider: str = "deepseek") -> Dict[str, str]:
    """
    Get default model configuration for a provider (tier2 - balanced).

    Args:
        provider: Provider name ("deepseek", "claude", or "baseten")

    Returns:
        Model configuration dict
    """
    return get_models_for_tier(provider, 'tier2')


def get_model_with_backups(model, provider: str = None) -> list:
    """
    Get model with appropriate backup chain for The Clone.

    Rules:
    - Gemini models chain to each other first (separate rate limit quotas)
    - Each Gemini variant (2.5-flash-lite, 2.0-flash, 2.5-flash) has own semaphore
    - Only 2 retries before moving to next model in chain
    - Final fallback to DeepSeek/Claude for cross-provider safety

    Args:
        model: Primary model name (str) or pre-defined model chain (list)
        provider: Clone provider context ("baseten", "deepseek", or "claude")

    Returns:
        List of models [primary, backup1, backup2, ...]
    """
    # If already a list, return as-is (pre-defined chain)
    if isinstance(model, list):
        return model

    # Gemini 3 Flash Preview HIGH thinking (conversation / config-gen / table-maker)
    # → OpenRouter fallback → Kimi K2.5 (no Gemini 2.5 — they have different capabilities)
    if model == 'gemini-3-flash-preview-high':
        return ['gemini-3-flash-preview-high', 'openrouter/gemini-3-flash-preview-high', 'moonshotai/kimi-k2.5']

    # Gemini 3 Flash Preview MEDIUM thinking (initial decision / routing)
    # → OpenRouter fallback → Kimi K2.5
    if model == 'gemini-3-flash-preview':
        return ['gemini-3-flash-preview', 'openrouter/gemini-3-flash-preview', 'moonshotai/kimi-k2.5']

    # Gemini 3 Flash Preview LOW thinking → OpenRouter mirror → different provider (Kimi)
    if model == 'gemini-3-flash-preview-low':
        return ['gemini-3-flash-preview-low', 'openrouter/gemini-3-flash-preview-low', 'moonshotai/kimi-k2.5']

    # Gemini 3 Flash Preview MIN thinking (no budget) → OpenRouter mirror → different provider (Kimi)
    if model == 'gemini-3-flash-preview-min':
        return ['gemini-3-flash-preview-min', 'openrouter/gemini-3-flash-preview-min', 'moonshotai/kimi-k2.5']

    # Gemini 2.5 Flash (redirected to Gemini 3 — superseded for all synthesis tasks)
    if model == 'gemini-2.5-flash':
        return ['gemini-3-flash-preview', 'openrouter/gemini-3-flash-preview']

    # Gemini 2.5 Flash Lite (primary extraction model) → OpenRouter fallback → MiniMax → Haiku
    # Keeps gemini-2.5-flash-lite as primary; Gemini 3 is too expensive for bulk extraction.
    if model == 'gemini-2.5-flash-lite':
        return ['gemini-2.5-flash-lite', 'openrouter/gemini-2.5-flash-lite', 'minimax/minimax-m2.5', 'claude-haiku-4-5']

    # Other Gemini models → Gemini 3 chain (catch-all for any other gemini-* variants)
    if model.startswith('gemini-'):
        return [model, 'gemini-3-flash-preview', 'openrouter/gemini-3-flash-preview', 'claude-sonnet-4-6']

    # DeepSeek Baseten → DeepSeek → Claude Sonnet
    if model == 'deepseek-v3.2-baseten':
        return ['deepseek-v3.2-baseten', 'deepseek-v3.2', 'claude-sonnet-4-6']

    # DeepSeek Vertex → Claude Sonnet
    if model == 'deepseek-v3.2':
        return ['deepseek-v3.2', 'claude-sonnet-4-6']

    # Kimi K2.5 (OpenRouter) → Claude Sonnet
    if model == 'moonshotai/kimi-k2.5':
        return ['moonshotai/kimi-k2.5', 'claude-sonnet-4-6']

    # DeepSeek Exp (same as v3.2) → DeepSeek → Claude Sonnet
    if model == 'deepseek-v3.2-exp':
        return ['deepseek-v3.2-exp', 'deepseek-v3.2', 'claude-sonnet-4-6']

    # Claude Opus → Sonnet → DeepSeek
    if model == 'claude-opus-4-6':
        return ['claude-opus-4-6', 'claude-sonnet-4-6', 'deepseek-v3.2']

    # Claude Sonnet → Opus → DeepSeek
    if model == 'claude-sonnet-4-6':
        return ['claude-sonnet-4-6', 'claude-opus-4-6', 'deepseek-v3.2']

    # Claude Haiku → DeepSeek
    if model == 'claude-haiku-4-5':
        return ['claude-haiku-4-5', 'deepseek-v3.2']

    # Perplexity models
    if model == 'sonar-pro':
        return ['sonar-pro', 'sonar']

    if model == 'sonar':
        return ['sonar']

    # Clone models - these have internal retry logic, no backups
    if model.startswith('the-clone'):
        return [model]

    # Unknown model - return as-is
    logger.warning(f"Unknown model '{model}' - no backup chain defined")
    return [model]


def should_stop_iteration(snippets: list, strategy: Dict[str, Any]) -> bool:
    """
    Check if we should stop iterating based on strategy stop condition.

    Args:
        snippets: List of all snippets collected so far
        strategy: Strategy configuration

    Returns:
        True if stop condition met, False otherwise
    """
    stop_condition = strategy.get('stop_condition')

    if stop_condition is None:
        # No early stopping - continue until max iterations
        return False

    if stop_condition in ["reliable_answer_found", "1_reliable_snippet"]:
        # Stop if we found at least 1 reliable answer to the EXACT query (p≥0.85)
        # Check snippets for primary search term (search_ref=1) with high confidence
        # Used for targeted queries where we're looking for a specific fact
        min_p = strategy.get('min_p_threshold', 0.85)

        # Count reliable snippets for primary search term only (search_ref=1)
        primary_reliable = sum(1 for s in snippets
                              if s.get('p', 0) >= min_p and s.get('search_ref') == 1)

        if primary_reliable >= 1:
            logger.debug(f"[STRATEGY] Reliable answer to exact query found: {primary_reliable} snippet(s) with p≥{min_p} for primary search term")
            return True

        logger.debug(f"[STRATEGY] No reliable answer yet (found {len([s for s in snippets if s.get('p', 0) >= min_p])} high-p snippets, but {primary_reliable} for primary query)")
        return False

    # Unknown stop condition - don't stop
    return False
