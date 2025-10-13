#!/usr/bin/env python3
"""
Prompt loader for table generation system.
Loads markdown prompt templates and replaces {{VARIABLE}} placeholders.
"""

import logging
import os
import re
from typing import Dict, Optional
from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)


class PromptLoader:
    """Load and process markdown prompt templates with variable replacement."""

    def __init__(self, prompts_dir: str):
        """
        Initialize prompt loader.

        Args:
            prompts_dir: Path to directory containing prompt markdown files
        """
        self.prompts_dir = Path(prompts_dir)
        if not self.prompts_dir.exists():
            raise ValueError(f"Prompts directory does not exist: {prompts_dir}")

        logger.info(f"Initialized PromptLoader with directory: {prompts_dir}")

        # Cache loaded prompts to avoid repeated file I/O
        self._prompt_cache: Dict[str, str] = {}

    def load_prompt(self, template_name: str, variables: Optional[Dict[str, str]] = None) -> str:
        """
        Load a markdown prompt template and replace variables.

        Args:
            template_name: Name of the prompt file (without .md extension)
            variables: Dictionary of variable names to values for replacement

        Returns:
            Processed prompt string with variables replaced

        Raises:
            FileNotFoundError: If template file doesn't exist
            ValueError: If required variables are missing
        """
        # Load template from file or cache
        template = self._load_template(template_name)

        # If no variables provided, return template as-is
        if not variables:
            return template

        # Replace variables in template
        processed_prompt = self.replace_variables(template, variables)

        logger.debug(f"Loaded and processed prompt template: {template_name}")
        return processed_prompt

    def _load_template(self, template_name: str) -> str:
        """
        Load template from file or cache.

        Args:
            template_name: Name of the template file

        Returns:
            Template content as string

        Raises:
            FileNotFoundError: If template file doesn't exist
        """
        # Check cache first
        if template_name in self._prompt_cache:
            logger.debug(f"Using cached template: {template_name}")
            return self._prompt_cache[template_name]

        # Construct file path
        if not template_name.endswith('.md'):
            template_name = f"{template_name}.md"

        template_path = self.prompts_dir / template_name

        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        # Read template file
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()

            # Cache the template
            self._prompt_cache[template_name] = template
            logger.info(f"Loaded prompt template: {template_name}")
            return template

        except Exception as e:
            logger.error(f"Error reading prompt template {template_path}: {e}")
            raise

    def replace_variables(self, template: str, variables: Dict[str, str]) -> str:
        """
        Replace {{VARIABLE}} placeholders with actual values.

        Args:
            template: Template string containing {{VARIABLE}} placeholders
            variables: Dictionary mapping variable names to replacement values

        Returns:
            Template with variables replaced

        Raises:
            ValueError: If template contains undefined variables
        """
        if not variables:
            variables = {}

        # Find all {{VARIABLE}} patterns in template
        pattern = r'\{\{([A-Z_]+)\}\}'
        matches = re.finditer(pattern, template)

        # Check for undefined variables
        undefined_vars = set()
        for match in matches:
            var_name = match.group(1)
            if var_name not in variables:
                undefined_vars.add(var_name)

        if undefined_vars:
            logger.warning(
                f"Template contains undefined variables: {', '.join(sorted(undefined_vars))}"
            )

        # Replace all variables
        processed = template
        for var_name, var_value in variables.items():
            placeholder = f"{{{{{var_name}}}}}"
            if placeholder in processed:
                processed = processed.replace(placeholder, str(var_value))
                logger.debug(f"Replaced variable {var_name}")

        return processed

    def get_template_variables(self, template_name: str) -> set:
        """
        Extract all variable names from a template.

        Args:
            template_name: Name of the template file

        Returns:
            Set of variable names found in template
        """
        template = self._load_template(template_name)
        pattern = r'\{\{([A-Z_]+)\}\}'
        matches = re.findall(pattern, template)
        return set(matches)

    def validate_variables(self, template_name: str, variables: Dict[str, str]) -> tuple:
        """
        Validate that all required variables are provided for a template.

        Args:
            template_name: Name of the template file
            variables: Variables to validate

        Returns:
            Tuple of (is_valid: bool, missing_vars: set, extra_vars: set)
        """
        required_vars = self.get_template_variables(template_name)
        provided_vars = set(variables.keys()) if variables else set()

        missing_vars = required_vars - provided_vars
        extra_vars = provided_vars - required_vars

        is_valid = len(missing_vars) == 0

        if not is_valid:
            logger.warning(
                f"Template {template_name} validation failed. "
                f"Missing: {missing_vars}, Extra: {extra_vars}"
            )

        return is_valid, missing_vars, extra_vars

    def clear_cache(self):
        """Clear the prompt cache."""
        self._prompt_cache.clear()
        logger.info("Cleared prompt cache")
