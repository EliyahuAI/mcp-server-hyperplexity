#!/usr/bin/env python3
"""
Prompt loader utility for Perplexity Clone.
Loads prompts from markdown files and configuration from JSON.
"""

import os
import json
from typing import Dict, Any


class PromptLoader:
    """Loads prompts from .md files and configuration from JSON."""

    def __init__(self, base_dir: str = None):
        """
        Initialize prompt loader.

        Args:
            base_dir: Base directory for perplexity_clone module
        """
        if base_dir is None:
            base_dir = os.path.dirname(__file__)

        self.base_dir = base_dir
        self.prompts_dir = os.path.join(base_dir, 'prompts')
        self.config_file = os.path.join(base_dir, 'configuration.json')
        self._config_cache = None
        self._prompt_cache = {}

    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from JSON file.

        Returns:
            Configuration dictionary
        """
        if self._config_cache is not None:
            return self._config_cache

        with open(self.config_file, 'r') as f:
            self._config_cache = json.load(f)

        return self._config_cache

    def load_prompt(self, prompt_name: str, **kwargs) -> str:
        """
        Load and format a prompt from markdown file.

        Args:
            prompt_name: Name of the prompt (without .md extension)
            **kwargs: Variables to substitute in the prompt

        Returns:
            Formatted prompt string
        """
        # Check cache
        if prompt_name in self._prompt_cache:
            template = self._prompt_cache[prompt_name]
        else:
            # Load from file
            prompt_file = os.path.join(self.prompts_dir, f"{prompt_name}.md")
            with open(prompt_file, 'r') as f:
                template = f.read()
            self._prompt_cache[prompt_name] = template

        # Format with provided variables
        try:
            formatted = template.format(**kwargs)
            return formatted
        except KeyError as e:
            raise ValueError(f"Missing required variable for prompt '{prompt_name}': {e}")

    def get_prompt_path(self, prompt_name: str) -> str:
        """Get the file path for a prompt."""
        return os.path.join(self.prompts_dir, f"{prompt_name}.md")

    def reload_prompts(self):
        """Clear prompt cache to force reload from files."""
        self._prompt_cache = {}

    def reload_config(self):
        """Clear config cache to force reload from file."""
        self._config_cache = None
