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
        model: str = "claude-sonnet-4-6"
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

            # Count ID vs research columns from the config
            id_count = sum(1 for t in config.get('validation_targets', []) if t.get('importance') == 'ID')
            research_count = len(config.get('validation_targets', [])) - id_count

            logger.info(
                f"Successfully generated config with "
                f"{len(config['validation_targets'])} validation targets "
                f"({id_count} ID columns + {research_count} research columns) and "
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
        identification_columns = [col for col in columns if col.get('importance', '').upper() == 'ID']
        research_columns = [col for col in columns if col.get('importance', '').upper() != 'ID']

        logger.info(
            f"Building config: {len(identification_columns)} ID columns, "
            f"{len(research_columns)} research columns"
        )

        # Check for researchable ID columns that should be validated
        researchable_id_columns = []
        non_researchable_id_columns = []

        for col in identification_columns:
            if self._is_researchable_id_column(col):
                researchable_id_columns.append(col)
            else:
                non_researchable_id_columns.append(col)

        logger.info(
            f"ID column analysis: {len(researchable_id_columns)} researchable, "
            f"{len(non_researchable_id_columns)} non-researchable"
        )

        # Add researchable ID columns to research columns for validation
        # This allows them to be included in search groups and validated
        research_columns_with_ids = research_columns + researchable_id_columns

        # Group research columns (including researchable IDs) by importance for search groups
        search_groups = self._create_search_groups(research_columns_with_ids)

        # Create validation targets for ALL columns (including ID columns for row key generation)
        # ID columns need to be in validation_targets with importance='ID' for row key generation
        validation_targets = []

        # First, add non-researchable identification columns with importance='ID'
        for col in non_researchable_id_columns:
            validation_targets.append({
                'column': col['name'],
                'description': col.get('description', ''),
                'importance': 'ID',  # Critical: This marks it as an ID field for row key generation
                'format': col.get('format', 'String'),
                'search_group': 0,  # ID columns don't need validation, just marking
                'notes': f"Identification column: {col['name']}",
                'is_identification': True  # Extra flag for clarity
            })
            logger.info(f"Added non-researchable ID column to validation_targets: {col['name']}")

        # Then add research columns for actual validation
        # Pass ALL columns (ID + research) so we can build relationship context
        all_columns = identification_columns + research_columns
        research_targets = self._create_validation_targets(
            research_columns,
            search_groups,
            all_columns
        )
        validation_targets.extend(research_targets)

        # Add researchable ID columns as CRITICAL validation targets
        for col in researchable_id_columns:
            # Find the CRITICAL search group (group_id=1 typically)
            critical_group_id = next(
                (g['group_id'] for g in search_groups if 'Critical' in g.get('group_name', '')),
                1  # Fallback to group 1 if no Critical group found
            )

            validation_targets.append({
                'column': col['name'],
                'description': col.get('description', ''),
                'importance': 'RESEARCH',  # Mark as RESEARCH for validation
                'format': col.get('format', 'String'),
                'search_group': critical_group_id,
                'notes': f"Researchable ID column - verify accuracy: {col.get('description', col['name'])}",
                'is_identification': True,  # Still mark as ID for row key generation
                'preferred_model': 'claude-sonnet-4-6',
                'search_context_size': 'high'
            })
            logger.info(f"Added researchable ID column as CRITICAL validation target: {col['name']}")

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
                'researchable_id_columns': [col['name'] for col in researchable_id_columns],
                'total_research_columns': len(research_columns) + len(researchable_id_columns)
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
            'RESEARCH': [],
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
        if importance_groups['RESEARCH']:
            search_groups.append({
                'group_id': group_id,
                'group_name': 'Critical Validation',
                'description': 'Critical fields requiring highest accuracy',
                'model': 'claude-sonnet-4-6',
                'search_context': 'high',
                'column_count': len(importance_groups['RESEARCH'])
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
        search_groups: List[Dict[str, Any]],
        all_columns: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Create validation targets for research columns.

        Args:
            research_columns: List of research column definitions
            search_groups: List of search groups
            all_columns: All columns (ID + research) for relationship context

        Returns:
            List of validation target definitions
        """
        # Extract ID columns for relationship context
        id_columns = [col for col in all_columns if col.get('importance', '').upper() == 'ID']

        # Map importance to search group ID
        importance_to_group = {}
        for group in search_groups:
            group_name = group['group_name']
            if 'Critical' in group_name:
                importance_to_group['RESEARCH'] = group['group_id']
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
                'notes': self._generate_enhanced_notes(col, id_columns, all_columns),
                'examples': self._extract_examples_from_description(col)
            }

            # Add specific model override for CRITICAL fields
            if importance == 'RESEARCH':
                target['preferred_model'] = 'claude-sonnet-4-6'
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

    def _generate_enhanced_notes(
        self,
        column: Dict[str, Any],
        id_columns: List[Dict[str, Any]],
        all_columns: List[Dict[str, Any]]
    ) -> str:
        """
        Generate enhanced notes with explicit relationship context and scope warnings.

        Args:
            column: Column to generate notes for
            id_columns: List of ID columns (provide entity context)
            all_columns: All columns in the table

        Returns:
            Enhanced notes string with relationship context
        """
        col_name = column.get('name', '').lower()
        col_desc = column.get('description', '').lower()
        combined_text = f"{col_name} {col_desc}"

        # Start with base description
        base_notes = column.get('description', f"Validate {column['name']}")

        # Build ID column context reference
        id_context = ""
        if id_columns:
            id_names = [col['name'] for col in id_columns]
            if len(id_names) == 1:
                id_context = f"for THIS {id_names[0].upper()}"
            elif len(id_names) == 2:
                id_context = f"for THIS {id_names[0].upper()} and THIS {id_names[1].upper()}"
            else:
                id_context = f"for the SPECIFIC entity identified by {', '.join(id_names)}"

        # Detect patterns and add specific scope warnings
        scope_warnings = []

        # Pattern: News/Updates columns
        if any(pattern in combined_text for pattern in ['news', 'update', 'announcement', 'press release', 'article']):
            # Check if there are company and product columns
            company_cols = [col['name'] for col in all_columns if any(
                p in col.get('name', '').lower() for p in ['company', 'organization', 'firm', 'developer']
            )]
            product_cols = [col['name'] for col in all_columns if any(
                p in col.get('name', '').lower() for p in ['product', 'candidate', 'drug', 'therapy', 'project']
            )]

            if company_cols and product_cols:
                scope_warnings.append(
                    f"Find news specifically about THIS PRODUCT (as identified by {', '.join(product_cols)}), "
                    f"not general company news. The news must explicitly mention the product by name, not just "
                    f"the company ({', '.join(company_cols)})."
                )
            elif product_cols:
                scope_warnings.append(
                    f"Find news specifically about THIS PRODUCT ({', '.join(product_cols)}), not general information."
                )
            elif company_cols:
                scope_warnings.append(
                    f"Find news specifically about THIS COMPANY ({', '.join(company_cols)})."
                )
            else:
                scope_warnings.append("Find news specifically about the entity identified by the row context.")

        # Pattern: Company/Organization relationship validation
        if any(pattern in combined_text for pattern in ['company', 'organization', 'developer', 'manufacturer']):
            product_cols = [col['name'] for col in all_columns if any(
                p in col.get('name', '').lower() for p in ['product', 'candidate', 'drug', 'therapy', 'project']
            )]
            if product_cols:
                scope_warnings.append(
                    f"Verify that this company OWNS/DEVELOPS the specific {', '.join(product_cols)} in this row, "
                    f"not just that the company exists."
                )

        # Pattern: Clinical trial / Study data
        if any(pattern in combined_text for pattern in ['trial', 'study', 'clinical', 'phase', 'enrollment']):
            product_cols = [col['name'] for col in all_columns if any(
                p in col.get('name', '').lower() for p in ['product', 'candidate', 'drug', 'therapy']
            )]
            if product_cols:
                scope_warnings.append(
                    f"Validate trial/study data specifically for THIS product ({', '.join(product_cols)}), "
                    f"not other products from the same company."
                )

        # Pattern: Timeline/Date validation
        if any(pattern in combined_text for pattern in ['date', 'timeline', 'launch', 'approval', 'filing']):
            scope_warnings.append(
                "Verify temporal alignment - the date must be contemporary with the entity's existence, "
                "not before it was created/announced."
            )

        # Pattern: Status/Stage validation
        if any(pattern in combined_text for pattern in ['status', 'stage', 'phase', 'progress']):
            scope_warnings.append(
                "Validate the CURRENT status/stage for this specific entity, not historical or projected status."
            )

        # Pattern: URL/Website validation
        if any(pattern in combined_text for pattern in ['url', 'website', 'link', 'homepage']):
            scope_warnings.append(
                "Verify the URL is the OFFICIAL website for this specific entity, not a general company website "
                "or third-party reference."
            )

        # Build final notes
        notes_parts = [base_notes]

        # Add scope constraint if we have ID context
        if id_context:
            notes_parts.append(f"Validate specifically {id_context}, not general information.")

        # Add pattern-specific warnings
        if scope_warnings:
            notes_parts.extend(scope_warnings)

        # Add general scope reminder
        notes_parts.append(
            "SCOPE: All validation results must explicitly mention the identifying information from the row context. "
            "When in doubt about entity match, mark confidence as MEDIUM or LOW."
        )

        return " ".join(notes_parts)

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

Identification Column Handling:
- Researchable ID columns (URLs, company names, person names, etc.) are marked as CRITICAL
  and will be validated to ensure row generation quality.
- Non-researchable ID columns (generic IDs, dates, etc.) are included with importance='ID'
  for row key generation but are not actively validated.
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

            # Check that search_group references valid group (0 is valid for ID columns)
            group_id = target.get('search_group')
            valid_groups = [g['group_id'] for g in config.get('search_groups', [])]
            # Group 0 is valid for ID columns that don't need validation
            if group_id != 0 and group_id not in valid_groups:
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

    def _is_researchable_id_column(self, column: Dict[str, Any]) -> bool:
        """
        Determine if an ID column can be researched on the web.

        Researchable ID columns should be validated to ensure row generation quality.

        Args:
            column: Column definition with name, format, description, etc.

        Returns:
            True if the column can be researched, False otherwise
        """
        column_name = column.get('name', '').lower()
        column_format = column.get('format', '').lower()
        column_description = column.get('description', '').lower()

        # Combine all text fields for pattern matching
        combined_text = f"{column_name} {column_format} {column_description}"

        # Researchable patterns - URLs, companies, organizations, people, etc.
        researchable_patterns = [
            # URL/Website columns
            'url', 'website', 'link', 'homepage', 'site',
            # Company/Organization columns
            'company', 'organization', 'organisation', 'firm', 'business',
            'corporation', 'enterprise', 'startup', 'vendor', 'supplier',
            # People columns
            'person', 'researcher', 'author', 'founder', 'ceo', 'contact',
            'name', 'scientist', 'professor', 'director', 'manager',
            # Location columns (can be verified)
            'location', 'address', 'city', 'country', 'region',
            # Product/Project names (can be verified)
            'product', 'project', 'program', 'application', 'app',
            # Email/Contact (can be verified)
            'email', 'contact'
        ]

        # Check if any researchable pattern is found
        for pattern in researchable_patterns:
            if pattern in combined_text:
                logger.info(
                    f"Column '{column['name']}' identified as researchable "
                    f"(matched pattern: '{pattern}')"
                )
                return True

        # Non-researchable patterns - generic IDs, dates, numbers
        non_researchable_patterns = [
            'id', 'uuid', 'guid', 'key', 'index', 'number', '#',
            'date', 'time', 'timestamp', 'created', 'updated',
            'code', 'serial', 'reference'
        ]

        # If it matches non-researchable pattern and no researchable pattern, it's not researchable
        for pattern in non_researchable_patterns:
            if pattern in combined_text:
                logger.info(
                    f"Column '{column['name']}' identified as non-researchable "
                    f"(matched pattern: '{pattern}')"
                )
                return False

        # Default: if no pattern matched, consider it non-researchable
        logger.info(
            f"Column '{column['name']}' defaulted to non-researchable "
            f"(no pattern match)"
        )
        return False

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
