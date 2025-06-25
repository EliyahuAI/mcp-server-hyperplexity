import os
import sys
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import re

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the original SchemaValidator
sys.path.append(str(Path(__file__).parent))
from schema_validator import SchemaValidator, ValidationTarget, format_prompt, normalize_sources

class EnhancedSchemaValidator(SchemaValidator):
    """Enhanced version of SchemaValidator that properly handles examples and supports JSON configs"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with config and create a column lookup for faster access"""
        super().__init__(config)
        
        # Create a column lookup dictionary from validation_targets
        self.column_lookup = {}
        for target in self.validation_targets:
            self.column_lookup[target.column] = {
                'description': target.description,
                'validation_type': target.validation_type,
                'importance': target.importance,
                'search_group': target.search_group,
                'rules': target.rules
            }
            
            # Look for examples in the original config targets
            for target_config in self.config.get('validation_targets', []):
                if target_config['column'] == target.column:
                    if 'examples' in target_config:
                        self.column_lookup[target.column]['examples'] = target_config['examples']
                    if 'notes' in target_config:
                        self.column_lookup[target.column]['notes'] = target_config['notes']
                    if 'format' in target_config:
                        self.column_lookup[target.column]['format'] = target_config['format']
    
    def _format_examples(self, column: str) -> str:
        """Format examples for a column with improved formatting."""
        examples = self.column_lookup.get(column, {}).get('examples', [])
        if not examples:
            logger.info(f"No examples found for column: {column}")
            return ""
        
        # Better formatting for examples
        logger.info(f"Formatting {len(examples)} examples for column: {column}")
        formatted = ""
        for example in examples:
            formatted += f"- {example}\n"
        return formatted
    
    def generate_multiplex_prompt(self, row: Dict[str, Any], targets: List[ValidationTarget], previous_results: Dict[str, Dict[str, Any]] = None) -> str:
        """
        Generate a prompt for validating multiple columns in a single API call.
        
        Args:
            row: The row data to validate
            targets: List of validation targets to include in the prompt
            previous_results: Optional dictionary of previous validation results
            
        Returns:
            The formatted prompt string
        """
        # Load multiplex template
        multiplex_template = self.prompts.get('multiplex_validation', '')
        if not multiplex_template:
            return self._generate_multiplex_prompt_fallback(row, targets, previous_results)
        
        # Get general notes
        general_notes = self.config.get('general_notes', '')
        
        # Get context from ID fields
        context_lines = []
        all_id_fields = self._get_id_fields(self.validation_targets)
        if all_id_fields:
            for id_field in all_id_fields:
                context_lines.append(f"{id_field.column}: {row.get(id_field.column, '')}")
        context = "\n".join(context_lines)
        
        # Format previous validation results
        previous_results_lines = []
        if previous_results and len(previous_results) > 0:
            for col, result in previous_results.items():
                confidence_level = result.get('confidence_level', 'UNKNOWN')
                value = result.get('value', '')
                previous_results_lines.append(f"{col}: {value} (Confidence: {confidence_level})")
        previous_results_text = "\n".join(previous_results_lines)
        
        # Format fields to validate with clear separation
        fields_to_validate = []
        for i, target in enumerate(targets, 1):
            column_info = self.column_lookup.get(target.column, {})
            description = column_info.get('description', target.description)
            format_info = column_info.get('format', '')
            notes = column_info.get('notes', '')
            
            field_parts = []
            field_parts.append(f"----- FIELD {i}: {target.column} -----")
            field_parts.append(f"Current Value: {row.get(target.column, '')}")
            field_parts.append(f"Description: {description}")
            
            if format_info:
                field_parts.append(f"Format: {format_info}")
                
            field_parts.append(f"Importance: {target.importance}")
            
            if notes:
                field_parts.append(f"Notes: {notes}")
            
            # Always include examples section, even if it's empty
            examples = self._format_examples(target.column)
            if examples and examples.strip():
                field_parts.append("Examples:")
                field_parts.append(examples)
            
            fields_to_validate.append("\n".join(field_parts))
        
        columns_to_validate = "\n\n".join(fields_to_validate)
        
        # Format the prompt using the template
        prompt_context = {
            'general_notes': general_notes,
            'context': context,
            'previous_results': previous_results_text,
            'columns_to_validate': columns_to_validate
        }
        
        # Use the format_prompt function to fill in the template
        prompt = format_prompt(multiplex_template, prompt_context)
        
        # Clean up any instances of multiple consecutive newlines
        while "\n\n\n" in prompt:
            prompt = prompt.replace("\n\n\n", "\n\n")
            
        return prompt

def load_config_file(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from either a JSON or YAML file.
    
    Args:
        config_path: Path to the config file (either .json or .yml/.yaml)
        
    Returns:
        Configuration dictionary with validation_targets list
    """
    try:
        file_extension = Path(config_path).suffix.lower()
        
        with open(config_path, 'r', encoding='utf-8') as f:
            if file_extension == '.json':
                config = json.load(f)
            elif file_extension in ['.yml', '.yaml']:
                config = yaml.safe_load(f)
            else:
                logger.warning(f"Unknown file extension {file_extension}, trying to parse as JSON")
                config = json.load(f)
        
        # Handle backward compatibility with old format using 'columns' map
        if 'columns' in config and 'validation_targets' not in config:
            logger.info("Converting legacy 'columns' format to 'validation_targets' format")
            validation_targets = []
            
            for column_name, column_data in config['columns'].items():
                # Create a validation target entry for each column
                target = {
                    'column': column_name,
                    'validation_type': column_data.get('validation_type', 'string'),
                    'description': column_data.get('description', ''),
                    'importance': column_data.get('importance', 'MEDIUM'),
                    'format': column_data.get('format', ''),
                    'notes': column_data.get('notes', ''),
                    'rules': column_data.get('rules', {}),
                    'search_group': column_data.get('search_group', 0)
                }
                
                # Copy examples if available
                if 'examples' in column_data:
                    target['examples'] = column_data['examples']
                
                validation_targets.append(target)
            
            # Replace columns with validation_targets
            config['validation_targets'] = validation_targets
            del config['columns']
        
        return config
    except Exception as e:
        logger.error(f"Failed to load config file {config_path}: {str(e)}")
        raise

def create_validator(config_path_or_dict: Any) -> EnhancedSchemaValidator:
    """
    Create an enhanced schema validator from either a file path or config dict.
    
    Args:
        config_path_or_dict: Either a path to a config file or a configuration dictionary
        
    Returns:
        EnhancedSchemaValidator instance
    """
    if isinstance(config_path_or_dict, str):
        config = load_config_file(config_path_or_dict)
    else:
        config = config_path_or_dict
        
    return EnhancedSchemaValidator(config) 