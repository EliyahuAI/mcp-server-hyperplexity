#!/usr/bin/env python3
"""
Config generator for table generation system.
Generates AI validation configs from finalized table structures.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class ConfigGenerator:
    """Generate AI validation configurations from table structures."""

    def __init__(self, ai_client):
        """
        Initialize config generator.

        Args:
            ai_client: AI API client instance
        """
        self.ai_client = ai_client
        logger.info("Initialized ConfigGenerator")

    async def generate_config_from_table(
        self,
        table_structure: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
        model: str = "claude-sonnet-4-5"
    ) -> Dict[str, Any]:
        """
        Generate AI validation config from final table structure.

        Args:
            table_structure: Finalized table structure with columns and rows
            conversation_history: Full conversation log
            model: AI model to use

        Returns:
            Dictionary with generated config:
            {
                'success': bool,
                'config': Dict,  # The generated validation config
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'config': None,
            'error': None
        }

        try:
            logger.info("Generating validation config from table structure")

            # Extract columns from table structure
            columns = table_structure.get('columns', [])
            if not columns:
                columns = table_structure.get('proposed_columns', [])

            if not columns:
                raise ValueError("No columns found in table structure")

            # Build the config structure
            config = self._build_config_structure(
                columns=columns,
                table_structure=table_structure,
                conversation_history=conversation_history
            )

            # Validate the generated config
            validation_errors = self._validate_config(config)
            if validation_errors:
                logger.warning(
                    f"Generated config has validation warnings: {len(validation_errors)}"
                )
                # Include warnings but don't fail
                result['validation_warnings'] = validation_errors

            result['config'] = config
            result['success'] = True

            logger.info(
                f"Successfully generated config with "
                f"{len(config['validation_targets'])} validation targets and "
                f"{len(config.get('search_groups', []))} search groups"
            )

        except Exception as e:
            error_msg = f"Error generating config: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result

    def _build_config_structure(
        self,
        columns: List[Dict[str, Any]],
        table_structure: Dict[str, Any],
        conversation_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Build the configuration structure from columns.

        Args:
            columns: List of column definitions
            table_structure: Complete table structure
            conversation_history: Conversation history for context

        Returns:
            Complete configuration dictionary
        """
        # Separate identification vs research columns
        identification_columns = [col for col in columns if col.get('is_identification', False)]
        research_columns = [col for col in columns if not col.get('is_identification', False)]

        logger.info(
            f"Building config: {len(identification_columns)} ID columns, "
            f"{len(research_columns)} research columns"
        )

        # Group research columns by importance for search groups
        search_groups = self._create_search_groups(research_columns)

        # Create validation targets for ALL columns (including ID columns for row key generation)
        # ID columns need to be in validation_targets with importance='ID' for row key generation
        validation_targets = []

        # First, add identification columns with importance='ID'
        for col in identification_columns:
            validation_targets.append({
                'column': col['name'],
                'description': col.get('description', ''),
                'importance': 'ID',  # Critical: This marks it as an ID field for row key generation
                'format': col.get('format', 'String'),
                'search_group': 0,  # ID columns don't need validation, just marking
                'notes': f"Identification column: {col['name']}",
                'is_identification': True  # Extra flag for clarity
            })

        # Then add research columns for actual validation
        research_targets = self._create_validation_targets(
            research_columns,
            search_groups
        )
        validation_targets.extend(research_targets)

        # Build complete config
        config = {
            'general_notes': self._generate_general_notes(
                table_structure,
                conversation_history
            ),
            'default_model': 'sonar-pro',
            'default_search_context_size': 'medium',
            'search_groups': search_groups,
            'validation_targets': validation_targets,
            'generation_metadata': {
                'generated_at': datetime.utcnow().isoformat() + 'Z',
                'generated_from': 'table_generation_system',
                'conversation_id': table_structure.get('metadata', {}).get('conversation_id', 'unknown'),
                'version': 1,
                'identification_columns': [col['name'] for col in identification_columns],
                'total_research_columns': len(research_columns)
            }
        }

        return config

    def _create_search_groups(self, research_columns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create search groups based on column importance and characteristics.

        Args:
            research_columns: List of research column definitions

        Returns:
            List of search group definitions
        """
        # Group columns by importance level
        importance_groups = {
            'CRITICAL': [],
            'HIGH': [],
            'MEDIUM': [],
            'LOW': []
        }

        for col in research_columns:
            importance = col.get('importance', 'MEDIUM')
            importance_groups[importance].append(col)

        search_groups = []
        group_id = 1

        # Create search group for CRITICAL columns (use Claude for better accuracy)
        if importance_groups['CRITICAL']:
            search_groups.append({
                'group_id': group_id,
                'group_name': 'Critical Validation',
                'description': 'Critical fields requiring highest accuracy',
                'model': 'claude-sonnet-4-5',
                'search_context': 'high',
                'column_count': len(importance_groups['CRITICAL'])
            })
            group_id += 1

        # Create search group for HIGH importance
        if importance_groups['HIGH']:
            search_groups.append({
                'group_id': group_id,
                'group_name': 'High Priority Validation',
                'description': 'Important fields requiring detailed verification',
                'model': 'sonar-pro',
                'search_context': 'medium',
                'column_count': len(importance_groups['HIGH'])
            })
            group_id += 1

        # Create search group for MEDIUM importance
        if importance_groups['MEDIUM']:
            search_groups.append({
                'group_id': group_id,
                'group_name': 'Standard Validation',
                'description': 'Standard verification fields',
                'model': 'sonar-pro',
                'search_context': 'medium',
                'column_count': len(importance_groups['MEDIUM'])
            })
            group_id += 1

        # Create search group for LOW importance
        if importance_groups['LOW']:
            search_groups.append({
                'group_id': group_id,
                'group_name': 'Basic Validation',
                'description': 'Basic verification with minimal context',
                'model': 'sonar-pro',
                'search_context': 'low',
                'column_count': len(importance_groups['LOW'])
            })

        logger.info(f"Created {len(search_groups)} search groups")
        return search_groups

    def _create_validation_targets(
        self,
        research_columns: List[Dict[str, Any]],
        search_groups: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Create validation targets for research columns.

        Args:
            research_columns: List of research column definitions
            search_groups: List of search groups

        Returns:
            List of validation target definitions
        """
        # Map importance to search group ID
        importance_to_group = {}
        for group in search_groups:
            group_name = group['group_name']
            if 'Critical' in group_name:
                importance_to_group['CRITICAL'] = group['group_id']
            elif 'High Priority' in group_name:
                importance_to_group['HIGH'] = group['group_id']
            elif 'Standard' in group_name:
                importance_to_group['MEDIUM'] = group['group_id']
            elif 'Basic' in group_name:
                importance_to_group['LOW'] = group['group_id']

        validation_targets = []

        for col in research_columns:
            importance = col.get('importance', 'MEDIUM')
            search_group_id = importance_to_group.get(importance, 1)

            target = {
                'column': col['name'],
                'description': col.get('description', ''),
                'importance': importance,
                'format': col.get('format', 'String'),
                'search_group': search_group_id,
                'notes': f"Validation for {col['name']}: {col.get('description', '')}",
                'examples': self._extract_examples_from_description(col)
            }

            # Add specific model override for CRITICAL fields
            if importance == 'CRITICAL':
                target['preferred_model'] = 'claude-sonnet-4-5'
                target['search_context_size'] = 'high'

            validation_targets.append(target)

        logger.info(f"Created {len(validation_targets)} validation targets")
        return validation_targets

    def _extract_examples_from_description(self, column: Dict[str, Any]) -> List[str]:
        """
        Extract or generate example values for a column.

        Args:
            column: Column definition

        Returns:
            List of example values
        """
        # If examples are provided in column definition, use them
        if 'examples' in column and column['examples']:
            return column['examples']

        # Generate placeholder examples based on format
        format_type = column.get('format', 'String').lower()

        if 'url' in format_type or 'link' in format_type:
            return ['https://example.com']
        elif 'date' in format_type:
            return ['2024-01-01']
        elif 'number' in format_type or 'integer' in format_type:
            return ['42']
        elif 'boolean' in format_type:
            return ['true', 'false']
        elif 'email' in format_type:
            return ['example@example.com']
        else:
            return ['Sample value']

    def _generate_general_notes(
        self,
        table_structure: Dict[str, Any],
        conversation_history: List[Dict[str, Any]]
    ) -> str:
        """
        Generate general notes for the configuration.

        Args:
            table_structure: Table structure
            conversation_history: Conversation history

        Returns:
            General notes string
        """
        metadata = table_structure.get('metadata', {})
        description = metadata.get('description', 'Research table validation')

        notes = f"""Configuration generated from conversational table design system.

Research Purpose: {description}

This configuration was automatically generated from a table structure created through
an interactive conversation. The validation targets and search groups are organized
based on the importance levels and data types specified during table design.

Identification columns are not included in validation targets as they represent
the core data being researched, not fields to be validated.
"""

        return notes.strip()

    def _validate_config(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate generated configuration structure.

        Args:
            config: Configuration to validate

        Returns:
            List of validation error/warning messages
        """
        errors = []

        # Check required fields
        if 'validation_targets' not in config or not config['validation_targets']:
            errors.append("Configuration must have validation_targets")

        if 'search_groups' not in config or not config['search_groups']:
            errors.append("Configuration must have search_groups")

        # Validate validation targets
        for idx, target in enumerate(config.get('validation_targets', [])):
            if 'column' not in target:
                errors.append(f"Validation target {idx} missing 'column' field")

            if 'search_group' not in target:
                errors.append(f"Validation target {idx} missing 'search_group' field")

            # Check that search_group references valid group
            group_id = target.get('search_group')
            valid_groups = [g['group_id'] for g in config.get('search_groups', [])]
            if group_id not in valid_groups:
                errors.append(
                    f"Validation target '{target.get('column')}' references "
                    f"invalid search_group {group_id}"
                )

        # Validate search groups
        group_ids = set()
        for group in config.get('search_groups', []):
            if 'group_id' not in group:
                errors.append(f"Search group missing 'group_id'")
            else:
                group_id = group['group_id']
                if group_id in group_ids:
                    errors.append(f"Duplicate search group ID: {group_id}")
                group_ids.add(group_id)

        return errors

    def export_config_to_file(
        self,
        config: Dict[str, Any],
        output_path: str
    ) -> Dict[str, Any]:
        """
        Export configuration to JSON file.

        Args:
            config: Configuration to export
            output_path: Path for output file

        Returns:
            Dictionary with export results
        """
        result = {
            'success': False,
            'output_path': output_path,
            'error': None
        }

        try:
            from pathlib import Path

            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            result['success'] = True
            logger.info(f"Exported config to: {output_path}")

        except Exception as e:
            error_msg = f"Error exporting config: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result
