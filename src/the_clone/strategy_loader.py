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
        ('broad', 'shallow'): 'survey',
        ('broad', 'deep'): 'comprehensive'
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


def get_models_for_tier(provider: str, synthesis_tier: str) -> Dict[str, str]:
    """
    Get models for specified provider and synthesis tier.

    Args:
        provider: Provider name ("deepseek", "claude", or "baseten")
        synthesis_tier: Tier name ("tier1", "tier2", "tier3", or "tier4")

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

    return {
        'initial_decision': extraction_model,
        'triage': extraction_model,
        'extraction': extraction_model,
        'synthesis': tier_config['synthesis']
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


def get_model_with_backups(model: str, provider: str = None) -> list:
    """
    Get model with appropriate backup chain for The Clone.

    Rules:
    - Gemini 2.0 Flash first line of defense for extraction
    - Provider-specific backups (Baseten uses Baseten, others skip it)
    - Creates robust cross-provider safety net

    Args:
        model: Primary model name
        provider: Clone provider context ("baseten", "deepseek", or "claude")

    Returns:
        List of models [primary, backup1, backup2, ...]
    """
    # Gemini 2.0 Flash (extraction model) → Context-aware backups
    if model == 'gemini-2.0-flash':
        if provider == 'baseten':
            # Baseten context: use Baseten in backup chain
            return ['gemini-2.0-flash', 'deepseek-v3.2-baseten', 'deepseek-v3.2', 'claude-haiku-4-5']
        else:
            # Regular/Claude context: skip Baseten, go straight to Vertex DeepSeek
            return ['gemini-2.0-flash', 'deepseek-v3.2', 'claude-haiku-4-5']

    # Other Gemini models
    if model.startswith('gemini-'):
        return [model, 'gemini-2.0-flash', 'claude-haiku-4-5']

    # DeepSeek Baseten → DeepSeek → Claude Sonnet
    if model == 'deepseek-v3.2-baseten':
        return ['deepseek-v3.2-baseten', 'deepseek-v3.2', 'claude-sonnet-4-5']

    # DeepSeek Vertex → Claude Sonnet
    if model == 'deepseek-v3.2':
        return ['deepseek-v3.2', 'claude-sonnet-4-5']

    # DeepSeek Exp (same as v3.2) → DeepSeek → Claude Sonnet
    if model == 'deepseek-v3.2-exp':
        return ['deepseek-v3.2-exp', 'deepseek-v3.2', 'claude-sonnet-4-5']

    # Claude Opus → Sonnet → DeepSeek
    if model == 'claude-opus-4-5':
        return ['claude-opus-4-5', 'claude-sonnet-4-5', 'deepseek-v3.2']

    # Claude Sonnet → Opus → DeepSeek
    if model == 'claude-sonnet-4-5':
        return ['claude-sonnet-4-5', 'claude-opus-4-5', 'deepseek-v3.2']

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

    if stop_condition == "1_reliable_snippet":
        # Stop if we have at least 1 snippet with p >= min threshold
        min_p = strategy.get('min_p_threshold', 0.85)
        reliable_count = sum(1 for s in snippets if s.get('p', 0) >= min_p)
        return reliable_count >= 1

    # Unknown stop condition - don't stop
    return False
