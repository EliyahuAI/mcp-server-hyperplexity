"""
Module for loading prompt templates from YAML files.
"""
import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import re

logger = logging.getLogger()

# Update path to look in the src directory instead of the parent directory
DEFAULT_PROMPTS_PATH = Path(__file__).parent / "prompts.yml"

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

def format_prompt(template: str, context: Dict[str, Any]) -> str:
    """
    Format a prompt template with the given context.
    
    Args:
        template: The prompt template string
        context: Dictionary of values to insert into the template
        
    Returns:
        Formatted prompt string
    """
    if not template:
        return ""
    
    # Make a copy of the template to avoid modifying the original
    formatted = template
    
    # Extract variable names from the template using regex
    var_pattern = r'{([^}]+)}'
    variables = re.findall(var_pattern, template)
    
    # Replace each variable with its value from context
    for var_name in variables:
        placeholder = '{' + var_name + '}'
        if var_name not in context or context[var_name] is None:
            # Replace missing values with empty string
            formatted = formatted.replace(placeholder, "")
        else:
            value = context[var_name]
            # If value is a list or dict, pretty format it
            if isinstance(value, (list, dict)):
                import json
                value_str = json.dumps(value, indent=2)
            else:
                value_str = str(value)
                
            # Replace the placeholder with the value
            formatted = formatted.replace(placeholder, value_str)
    
    return formatted 