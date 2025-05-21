"""
Module for loading prompt templates from YAML files.
"""
import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger()

DEFAULT_PROMPTS_PATH = Path(__file__).parent.parent / "prompts.yml"

def load_prompts(prompts_path: Path = None) -> Dict[str, Any]:
    """
    Load prompts from a YAML file.
    
    Args:
        prompts_path: Path to the prompts YAML file. If None, uses the default path.
        
    Returns:
        Dictionary containing the loaded prompts.
    """
    if prompts_path is None:
        prompts_path = DEFAULT_PROMPTS_PATH
    
    logger.info(f"Loading prompts from {prompts_path}")
    
    try:
        with open(prompts_path, 'r') as f:
            prompts = yaml.safe_load(f)
        logger.info(f"Successfully loaded {len(prompts)} prompts")
        return prompts
    except Exception as e:
        logger.error(f"Error loading prompts: {e}")
        # Return empty dict as fallback
        return {} 