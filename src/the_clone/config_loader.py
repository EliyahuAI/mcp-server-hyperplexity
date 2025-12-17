#!/usr/bin/env python3
"""
Configuration loader for The Clone.
Loads and manages configuration from config.json.
"""

import os
import json
from typing import Dict, Any


def load_config() -> Dict[str, Any]:
    """
    Load The Clone configuration from config.json.

    Returns:
        Configuration dictionary with 'common' and 'contexts' sections
    """
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')

    with open(config_path, 'r') as f:
        config = json.load(f)

    return config


def get_context_config(context: str = "medium", variant: str = "common") -> Dict[str, Any]:
    """
    Get merged configuration for a specific context level.
    Combines common/variant settings with context-specific overrides.

    Args:
        context: Context level (low/medium/high)
        variant: Config variant (common/deepseek_variant/deepseek_synthesis_variant)

    Returns:
        Merged configuration dict with all settings for this context
    """
    config = load_config()
    base = config.get(variant, config.get('common', {}))
    context_specific = config.get('contexts', {}).get(context, {})

    # Merge base and context-specific
    merged = {**base, **context_specific}

    # Override model_tiers if variant uses DeepSeek for synthesis
    if variant in ["deepseek_synthesis_variant", "deepseek_variant"]:
        merged['model_tiers'] = config.get('model_tiers_deepseek', {})

    return merged


def get_max_iterations(context: str) -> int:
    """Get max iterations for context level."""
    context_config = get_context_config(context)
    return context_config.get('max_iterations', 2)


def get_sources_per_search(context: str) -> int:
    """Get sources per search term for context level."""
    context_config = get_context_config(context)
    return context_config.get('sources_per_search', 3)


def get_decision_model(context: str) -> str:
    """Get decision model (for triage and evaluation)."""
    context_config = get_context_config(context)
    return context_config.get('decision_model', 'claude-haiku-4-5')


def get_extraction_model(context: str) -> str:
    """Get extraction model."""
    context_config = get_context_config(context)
    return context_config.get('extraction_model', 'claude-haiku-4-5')


def get_synthesis_model(context: str) -> str:
    """Get synthesis model."""
    context_config = get_context_config(context)
    return context_config.get('synthesis_model', 'claude-sonnet-4-5')


def should_skip_evaluation(context: str, current_iteration: int, max_iterations: int) -> bool:
    """
    Determine if evaluation should be skipped.

    Args:
        context: Context level
        current_iteration: Current iteration number (1-indexed)
        max_iterations: Maximum iterations for this context

    Returns:
        True if evaluation should be skipped
    """
    context_config = get_context_config(context)

    # LOW context: Always skip evaluation (straight to synthesis)
    if context == 'low' or context_config.get('skip_evaluation', False):
        return True

    # On last iteration: Skip evaluation (go straight to synthesis)
    if current_iteration >= max_iterations:
        return True

    return False
