"""
Quality Control (QC) Module for Validation Results

This module provides QC functionality that reviews and potentially overrides
multiplex validation outputs on a per-row basis.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import yaml
import copy
from pathlib import Path

# Import shared modules
from ai_api_client import ai_client
from perplexity_schema import get_qc_response_format_schema, MULTIPLEX_RESPONSE_SCHEMA, ADDITIONAL_QC_FIELDS

logger = logging.getLogger(__name__)

class QCModule:
    """
    Quality Control module for reviewing and overriding validation results.

    Operates per-row after multiplex validation groups have completed.
    Uses the same structured API calls as validation but with QC-specific prompts.
    """

    def __init__(self, config: Dict[str, Any], prompts: Dict[str, str]):
        """
        Initialize QC module with configuration and prompts.

        Args:
            config: Configuration dictionary containing QC settings
            prompts: Dictionary containing prompt templates
        """
        self.config = config
        self.prompts = prompts
        self.qc_settings = config.get('qc_settings', {})
        self.enabled = self.qc_settings.get('enable_qc', True)

        # QC-specific configuration - ensure model is a string, not a list
        default_model = config.get('model', ['claude-sonnet-4-0'])
        if isinstance(default_model, list):
            default_model = default_model[0] if default_model else 'claude-sonnet-4-0'

        qc_model_setting = self.qc_settings.get('model', default_model)
        if isinstance(qc_model_setting, list):
            self.qc_model = qc_model_setting[0] if qc_model_setting else 'claude-sonnet-4-0'
        else:
            self.qc_model = qc_model_setting
        self.qc_max_tokens = self.qc_settings.get('max_tokens_default', 8000)
        self.qc_tokens_per_column = self.qc_settings.get('tokens_per_validated_column_default', 4000)
        self.qc_max_web_searches = self.qc_settings.get('anthropic_max_web_searches', 0)

        logger.info(f"QC Module initialized: enabled={self.enabled}, model={self.qc_model}")

    def is_enabled(self) -> bool:
        """Check if QC is enabled."""
        return self.enabled

    def scrub_encrypted_content(self, data: Any) -> Any:
        """
        Remove encrypted_content from citations before QC processing.

        Args:
            data: Data structure to scrub

        Returns:
            Scrubbed data with encrypted_content removed
        """
        if isinstance(data, dict):
            scrubbed = {}
            for key, value in data.items():
                if key == 'encrypted_content':
                    continue  # Skip encrypted content
                scrubbed[key] = self.scrub_encrypted_content(value)
            return scrubbed
        elif isinstance(data, list):
            return [self.scrub_encrypted_content(item) for item in data]
        else:
            return data

    def aggregate_citations(self, multiplex_results: List[Dict], qc_results: List[Dict]) -> Dict[str, List[str]]:
        """
        Aggregate citations between multiplex and QC results.

        Args:
            multiplex_results: Original multiplex validation results
            qc_results: QC override results

        Returns:
            Dictionary mapping column names to aggregated source lists
        """
        aggregated_sources = {}

        # First, collect all multiplex sources
        for result in multiplex_results:
            column = result.get('column', '')
            sources = result.get('sources', [])
            if column:
                aggregated_sources[column] = list(sources)

        # Then, add QC sources
        for qc_result in qc_results:
            column = qc_result.get('column', '')
            qc_sources = qc_result.get('sources', [])
            if column:
                if column not in aggregated_sources:
                    aggregated_sources[column] = []
                # Add QC sources, avoiding duplicates
                for source in qc_sources:
                    if source not in aggregated_sources[column]:
                        aggregated_sources[column].append(source)

        return aggregated_sources

    def format_all_multiplex_outputs_for_qc(self, all_group_results: Dict[str, List[Dict]], original_row: Dict[str, Any] = None, validation_targets: List[Any] = None, group_metadata: Dict[str, Dict[str, Any]] = None) -> str:
        """
        Format ALL multiplex validation outputs across all field groups for inclusion in QC prompt.
        Enhanced formatting to provide complete context for QC review.

        Args:
            all_group_results: Dictionary mapping group names to their multiplex validation results
            original_row: Original row data for extracting original values
            validation_targets: List of validation target objects for field guidance
            group_metadata: Dictionary mapping group names to metadata (description, model, etc.)

        Returns:
            Formatted string for QC prompt showing all field groups with complete context
        """
        if not all_group_results:
            return "No multiplex validation outputs to review."

        # Create mapping of column names to validation targets for quick lookup
        targets_by_column = {}
        if validation_targets:
            for target in validation_targets:
                targets_by_column[target.column] = target

        formatted_groups = []

        for group_name, group_results in all_group_results.items():
            if not group_results:
                continue

            # Filter out ID fields from QC review
            non_id_results = []
            for result in group_results:
                column = result.get('column', 'Unknown')
                if column in targets_by_column:
                    target = targets_by_column[column]
                    # Skip ID fields - they are for context only
                    if hasattr(target, 'importance') and target.importance == 'ID':
                        continue
                non_id_results.append(result)

            if not non_id_results:
                continue  # Skip this group if only ID fields

            # Enhanced group header with description and model info if available
            group_section = [f"### FIELD GROUP: {group_name}"]

            # Add group metadata if available
            if group_metadata and group_name in group_metadata:
                metadata = group_metadata[group_name]

                # Add group description
                if 'description' in metadata and metadata['description']:
                    group_section.append(f"**Description**: {metadata['description']}")

                # Add model used for this group
                if 'model' in metadata and metadata['model']:
                    group_section.append(f"**Model Used**: {metadata['model']}")

                # Add search context level if available
                if 'search_context_level' in metadata:
                    group_section.append(f"**Search Context**: {metadata['search_context_level']}")

                # Add max web searches if available
                if 'max_web_searches' in metadata:
                    group_section.append(f"**Max Web Searches**: {metadata['max_web_searches']}")

            group_section.append("")

            for result in non_id_results:
                column = result.get('column', 'Unknown')

                # Get original value from row data if available, otherwise from result
                if original_row and column in original_row:
                    original_value = original_row[column]
                else:
                    original_value = result.get('original_value', '[Original value not available]')

                answer = result.get('answer', '')
                confidence = result.get('confidence', '')
                original_confidence = result.get('original_confidence', '')
                reasoning = result.get('reasoning', '')
                sources = result.get('sources', [])
                explanation = result.get('explanation', '')

                # Enhanced field formatting with original and updated values
                field_output = [
                    f"**FIELD: {column}**",
                    ""
                ]

                # Add field-specific guidance if available
                if column in targets_by_column:
                    target = targets_by_column[column]
                    if hasattr(target, 'description') and target.description:
                        field_output.append(f"* Description: {target.description}")
                    if hasattr(target, 'format') and target.format:
                        field_output.append(f"* Format: {target.format}")
                    if hasattr(target, 'notes') and target.notes:
                        field_output.append(f"* Notes: {target.notes}")
                    if hasattr(target, 'examples') and target.examples:
                        field_output.append("* Examples:")
                        for example in target.examples:
                            field_output.append(f"  - {example}")
                    field_output.append("")

                field_output.extend([
                    f"* Original Entry: {original_value}",
                    f"* Updated Entry: {answer}",
                    f"* Confidence: {confidence}",
                    f"* Original Confidence: {original_confidence}",
                    f"* Reasoning: {reasoning}",
                    f"* Sources: {', '.join(sources) if sources else 'None'}",
                    f"* Citations: {', '.join(sources) if sources else 'None'}"
                ])

                if explanation:
                    field_output.append(f"* Explanation: {explanation}")

                field_output.append("")
                field_output.append("---")
                field_output.append("")

                group_section.extend(field_output)

            formatted_groups.append('\n'.join(group_section))

        return '\n\n'.join(formatted_groups)

    def format_id_fields_for_context(self, validation_targets: List[Any], row: Dict[str, Any]) -> str:
        """
        Format ID fields from validation targets to provide context for QC.
        ID fields are not QC'd but provide important context.

        Args:
            validation_targets: List of validation target objects
            row: Row data for extracting ID field values

        Returns:
            Formatted string with ID fields for context
        """
        if not validation_targets or not row:
            logger.warning("QC ID context: No validation targets or row data provided")
            return ""

        id_fields = []
        logger.info(f"QC checking {len(validation_targets)} validation targets for ID fields")

        for target in validation_targets:
            # Check if this is an ID field
            logger.debug(f"QC target: {target.column}, importance: {getattr(target, 'importance', 'NONE')}")
            if hasattr(target, 'importance') and target.importance == 'ID':
                column = target.column
                value = row.get(column, '')
                description = getattr(target, 'description', '')

                field_info = f"**{column}**: {value}"
                if description:
                    field_info += f" ({description})"

                id_fields.append(field_info)
                logger.info(f"QC added ID field: {field_info}")

        if not id_fields:
            logger.warning("QC: No ID fields found in validation targets")
            return "No ID fields available for context."

        result = '\n'.join(id_fields)
        logger.info(f"QC final ID context: '{result}'")
        return result


    def calculate_qc_tokens(self, num_fields: int) -> int:
        """
        Calculate token limit for QC based on number of fields.

        Args:
            num_fields: Number of fields being reviewed

        Returns:
            Token limit for QC call
        """
        return self.qc_max_tokens + (num_fields * self.qc_tokens_per_column)

    async def process_qc_for_complete_row(
        self,
        session: Any,
        row: Dict[str, Any],
        all_group_results: Dict[str, List[Dict]],
        validation_targets: List[Any],
        context: str = "",
        general_notes: str = "",
        group_metadata: Dict[str, Dict[str, Any]] = None
    ) -> Tuple[List[Dict], Dict[str, Any]]:
        """
        Process QC for a complete row after ALL field groups have been processed.

        Args:
            session: aiohttp session for API calls
            row: The data row being processed
            all_group_results: Dictionary mapping group names to their multiplex validation results
            validation_targets: List of validation target objects
            context: Context information for validation
            general_notes: General guidance notes
            group_metadata: Dictionary mapping group names to metadata (description, model, etc.)

        Returns:
            Tuple of (qc_results_list, qc_metrics_dict)
        """
        if not self.is_enabled():
            logger.info("QC is disabled, skipping QC processing")
            return [], {}

        if not all_group_results:
            logger.info("No multiplex results to QC, skipping")
            return [], {}

        # Flatten all results to get total field count
        all_multiplex_results = []
        for group_results in all_group_results.values():
            all_multiplex_results.extend(group_results)

        # Scrub encrypted content from all multiplex results
        scrubbed_all_group_results = {}
        for group_name, group_results in all_group_results.items():
            scrubbed_all_group_results[group_name] = self.scrub_encrypted_content(group_results)

        # Prepare QC prompt
        qc_prompt_template = self.prompts.get('qc_validation', '')
        if not qc_prompt_template:
            logger.error("QC validation prompt not found in prompts")
            return [], {}

        # Format ALL multiplex outputs for QC review
        all_multiplex_outputs_formatted = self.format_all_multiplex_outputs_for_qc(
            scrubbed_all_group_results, row, validation_targets, group_metadata
        )

        # Get QC schema
        qc_schema_response = get_qc_response_format_schema()
        array_schema = qc_schema_response['json_schema']['schema']
        json_schema_example = json.dumps(array_schema, indent=2)

        # Wrap the array schema in an object for tool calling (Anthropic requires type: object)
        tool_schema = {
            "type": "object",
            "properties": {
                "qc_results": array_schema
            },
            "required": ["qc_results"]
        }

        # Generate ID fields context
        logger.info(f"QC: About to generate ID context with {len(validation_targets) if validation_targets else 0} validation targets")
        id_context = self.format_id_fields_for_context(validation_targets, row)
        logger.info(f"QC: Generated ID context: '{id_context}'")
        enhanced_context = f"{context}\n\n{id_context}" if context else id_context
        logger.info(f"QC: Enhanced context: '{enhanced_context}'")

        # Build QC prompt with all field groups
        qc_prompt = qc_prompt_template.format(
            general_notes=general_notes,
            context=enhanced_context,
            all_multiplex_outputs=all_multiplex_outputs_formatted,
            json_schema_example=json_schema_example
        )

        # Calculate token limit based on non-ID fields across all groups
        non_id_fields = 0
        for group_results in all_group_results.values():
            for result in group_results:
                column = result.get('column', 'Unknown')
                if validation_targets:
                    target = next((t for t in validation_targets if t.column == column), None)
                    if target and hasattr(target, 'importance') and target.importance == 'ID':
                        continue  # Skip ID fields
                non_id_fields += 1

        token_limit = self.calculate_qc_tokens(non_id_fields)

        logger.info(f"Running QC for complete row with {non_id_fields} non-ID fields across {len(all_group_results)} groups, token limit {token_limit}")
        logger.info(f"QC context being used: '{enhanced_context}'")

        try:
            # Make QC API call using ai_api_client
            qc_response = await ai_client.call_structured_api(
                prompt=qc_prompt,
                model=self.qc_model,
                schema=tool_schema,
                max_tokens=token_limit,
                max_web_searches=self.qc_max_web_searches,
                tool_name="qc_validation"
            )

            # Parse QC results
            qc_results = []

            # Extract timing and cost data from enhanced_data
            enhanced_data = qc_response.get('enhanced_data', {})
            timing_data = enhanced_data.get('timing', {})
            costs_data = enhanced_data.get('costs', {})
            token_usage = enhanced_data.get('token_usage', {})

            qc_metrics = {
                'qc_fields_reviewed': non_id_fields,
                'qc_fields_modified': 0,
                'qc_confidence_lowered': 0,
                'qc_values_replaced': 0,
                'qc_model_used': self.qc_model,
                'qc_tokens_used': token_usage.get('total_tokens', 0),
                'qc_groups_processed': len(all_group_results),
                # Add timing data for aggregation (actual vs estimated per DYNAMODB_TABLES.md)
                'qc_time_actual_seconds': timing_data.get('time_actual_seconds', 0.0),  # What we actually spent (with cache benefits)
                'qc_time_estimated_seconds': timing_data.get('time_estimated_seconds', 0.0),  # What it would take without cache
                'qc_time_savings_seconds': timing_data.get('time_savings_seconds', 0.0),
                'qc_cost_actual': costs_data.get('actual', {}).get('total_cost', 0.0),  # What we actually paid (with cache benefits)
                'qc_cost_estimated': costs_data.get('estimated', {}).get('total_cost', 0.0),  # What it would cost without cache
                'qc_cache_hit_tokens': token_usage.get('cache_read_tokens', 0),
                # Include raw response data for proper cost tracking
                'qc_response_data': qc_response
            }

            # Extract structured response using ai_client method
            try:
                structured_data = ai_client.extract_structured_response(qc_response['response'], "qc_validation")
                qc_results = structured_data.get('qc_results', []) if isinstance(structured_data, dict) else []
                logger.info(f"QC returned {len(qc_results)} field modifications across all groups")

                # Debug QC API response
                logger.info(f"QC API structured extraction successful: found {len(qc_results)} QC modifications")

                # Update metrics based on QC actions
                qc_metrics['qc_fields_modified'] = len(qc_results)
                for qc_result in qc_results:
                    action = qc_result.get('qc_action_taken', '')
                    if action == 'confidence_lowered':
                        qc_metrics['qc_confidence_lowered'] += 1
                    elif action == 'value_replaced':
                        qc_metrics['qc_values_replaced'] += 1

            except Exception as e:
                logger.warning(f"QC API structured response extraction failed: {str(e)}")
                qc_results = []

            return qc_results, qc_metrics

        except Exception as e:
            logger.error(f"Error during QC processing: {str(e)}")
            return [], {}

    async def process_qc_for_row(
        self,
        session: Any,
        row: Dict[str, Any],
        multiplex_results: List[Dict],
        validation_targets: List[Any],
        context: str = "",
        general_notes: str = "",
        group_name: str = "",
        group_description: str = ""
    ) -> Tuple[List[Dict], Dict[str, Any]]:
        """
        Process QC for a single row's multiplex validation results.

        Args:
            session: aiohttp session for API calls
            row: The data row being processed
            multiplex_results: List of multiplex validation results for this row
            validation_targets: List of validation target objects
            context: Context information for validation
            general_notes: General guidance notes
            group_name: Name of the validation group
            group_description: Description of the validation group

        Returns:
            Tuple of (qc_results_list, qc_metrics_dict)
        """
        if not self.is_enabled():
            logger.info("QC is disabled, skipping QC processing")
            return [], {}

        if not multiplex_results:
            logger.info("No multiplex results to QC, skipping")
            return [], {}

        # Scrub encrypted content from multiplex results
        scrubbed_multiplex_results = self.scrub_encrypted_content(multiplex_results)

        # Prepare QC prompt
        qc_prompt_template = self.prompts.get('qc_validation', '')
        if not qc_prompt_template:
            logger.error("QC validation prompt not found in prompts")
            return [], {}

        # Format multiplex outputs for QC review
        multiplex_outputs_formatted = self.format_multiplex_outputs_for_qc(scrubbed_multiplex_results, validation_targets)

        # Get QC schema
        qc_schema_response = get_qc_response_format_schema()
        array_schema = qc_schema_response['json_schema']['schema']
        json_schema_example = json.dumps(array_schema, indent=2)

        # Wrap the array schema in an object for tool calling (Anthropic requires type: object)
        tool_schema = {
            "type": "object",
            "properties": {
                "qc_results": array_schema
            },
            "required": ["qc_results"]
        }

        # Generate ID fields context
        id_context = self.format_id_fields_for_context(validation_targets, row)
        enhanced_context = f"{context}\n\n{id_context}" if context else id_context

        # Build QC prompt
        qc_prompt = qc_prompt_template.format(
            general_notes=general_notes,
            context=enhanced_context,
            group_name=group_name,
            group_description=group_description,
            multiplex_outputs=multiplex_outputs_formatted,
            json_schema_example=json_schema_example
        )

        # Calculate token limit
        num_fields = len(scrubbed_multiplex_results)
        token_limit = self.calculate_qc_tokens(num_fields)

        logger.info(f"Running QC for {num_fields} fields with token limit {token_limit}")

        try:
            # Make QC API call using ai_api_client
            qc_response = await ai_client.call_structured_api(
                prompt=qc_prompt,
                model=self.qc_model,
                schema=tool_schema,
                max_tokens=token_limit,
                max_web_searches=self.qc_max_web_searches,
                tool_name="qc_validation"
            )

            # Parse QC results
            qc_results = []

            # Extract timing and cost data from enhanced_data
            enhanced_data = qc_response.get('enhanced_data', {})
            timing_data = enhanced_data.get('timing', {})
            costs_data = enhanced_data.get('costs', {})
            token_usage = enhanced_data.get('token_usage', {})

            qc_metrics = {
                'qc_fields_reviewed': num_fields,
                'qc_fields_modified': 0,
                'qc_confidence_lowered': 0,
                'qc_values_replaced': 0,
                'qc_model_used': self.qc_model,
                'qc_tokens_used': token_usage.get('total_tokens', 0),
                # Add timing data for aggregation (actual vs estimated per DYNAMODB_TABLES.md)
                'qc_time_actual_seconds': timing_data.get('time_actual_seconds', 0.0),  # What we actually spent (with cache benefits)
                'qc_time_estimated_seconds': timing_data.get('time_estimated_seconds', 0.0),  # What it would take without cache
                'qc_time_savings_seconds': timing_data.get('time_savings_seconds', 0.0),
                'qc_cost_actual': costs_data.get('actual', {}).get('total_cost', 0.0),  # What we actually paid (with cache benefits)
                'qc_cost_estimated': costs_data.get('estimated', {}).get('total_cost', 0.0),  # What it would cost without cache
                'qc_cache_hit_tokens': token_usage.get('cache_read_tokens', 0)
            }

            # Extract structured response using ai_client method
            try:
                structured_data = ai_client.extract_structured_response(qc_response['response'], "qc_validation")
                qc_results = structured_data.get('qc_results', []) if isinstance(structured_data, dict) else []
                logger.info(f"QC returned {len(qc_results)} field modifications")

                # Debug QC API response
                logger.info(f"QC API structured extraction successful: found {len(qc_results)} QC modifications")

                # Update metrics based on QC actions
                qc_metrics['qc_fields_modified'] = len(qc_results)
                for qc_result in qc_results:
                    action = qc_result.get('qc_action_taken', '')
                    if action == 'confidence_lowered':
                        qc_metrics['qc_confidence_lowered'] += 1
                    elif action == 'value_replaced':
                        qc_metrics['qc_values_replaced'] += 1

            except Exception as e:
                logger.warning(f"QC API structured response extraction failed: {str(e)}")
                qc_results = []

            return qc_results, qc_metrics

        except Exception as e:
            logger.error(f"Error during QC processing: {str(e)}")
            return [], {}

    def merge_multiplex_and_qc_results(
        self,
        multiplex_results: List[Dict],
        qc_results: List[Dict]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Merge multiplex and QC results to create final entries with Original, Updated, and QC values.

        Args:
            multiplex_results: Original multiplex validation results
            qc_results: QC override results

        Returns:
            Dictionary mapping column names to merged result dictionaries containing:
            - original_entry: Original value from the data
            - updated_entry: Updated value from multiplex validation
            - qc_entry: Final value after QC (may be same as updated_entry)
            - qc_applied: Boolean indicating if QC made changes
            - qc_action_taken: Type of QC action
            - qc_reasoning: Reasoning for QC changes
        """
        merged_results = {}

        # Create QC results lookup
        qc_lookup = {result.get('column', ''): result for result in qc_results}

        # Aggregate citations
        aggregated_citations = self.aggregate_citations(multiplex_results, qc_results)

        # Process each multiplex result
        for multiplex_result in multiplex_results:
            column = multiplex_result.get('column', '')
            if not column:
                continue

            # Check if QC made changes to this field
            qc_result = qc_lookup.get(column)
            qc_applied = qc_result is not None

            # Build merged result
            merged_result = {
                # Original multiplex data (this represents the "Updated Entry")
                'updated_entry': multiplex_result.get('answer', ''),
                'updated_confidence': multiplex_result.get('confidence', ''),
                'original_confidence': multiplex_result.get('original_confidence', ''),
                'updated_reasoning': multiplex_result.get('reasoning', ''),
                'updated_sources': multiplex_result.get('sources', []),

                # QC data
                'qc_applied': qc_applied,
                'qc_entry': '',
                'qc_confidence': '',
                'qc_action_taken': 'no_change',
                'qc_reasoning': '',
                'qc_sources': [],

                # Aggregated sources
                'all_sources': aggregated_citations.get(column, [])
            }

            if qc_applied:
                # QC made changes - use QC values as final
                merged_result.update({
                    'qc_entry': qc_result.get('answer', merged_result['updated_entry']),
                    'qc_confidence': qc_result.get('confidence', merged_result['updated_confidence']),
                    'qc_action_taken': qc_result.get('qc_action_taken', 'no_change'),
                    'qc_reasoning': qc_result.get('qc_reasoning', ''),
                    'qc_sources': qc_result.get('sources', [])
                })
            else:
                # No QC changes - QC entry same as updated entry
                merged_result.update({
                    'qc_entry': merged_result['updated_entry'],
                    'qc_confidence': merged_result['updated_confidence']
                })

            merged_results[column] = merged_result

        return merged_results

    def calculate_revision_percentages(self, merged_results: Dict[str, Dict]) -> Dict[str, float]:
        """
        Calculate the percentage of rows revised by QC for each validated column.

        Args:
            merged_results: Dictionary of merged results by column

        Returns:
            Dictionary mapping column names to revision percentages
        """
        revision_percentages = {}

        for column, result in merged_results.items():
            qc_applied = result.get('qc_applied', False)
            # For now, we calculate per-row. In practice, this would be aggregated across all rows
            revision_percentages[column] = 100.0 if qc_applied else 0.0

        return revision_percentages


def load_prompts_from_file(prompts_file: str = "prompts.yml") -> Dict[str, str]:
    """
    Load prompts from YAML file.

    Args:
        prompts_file: Path to prompts YAML file

    Returns:
        Dictionary of prompt templates
    """
    try:
        # Use proper path resolution for Lambda environment
        if prompts_file == "prompts.yml":
            prompts_path = Path(__file__).parent / "prompts.yml"
        else:
            prompts_path = Path(prompts_file)

        with open(prompts_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error loading prompts from {prompts_path}: {e}")
        return {}


def create_qc_module(config: Dict[str, Any], prompts_file: str = "prompts.yml") -> QCModule:
    """
    Factory function to create QC module instance.

    Args:
        config: Configuration dictionary
        prompts_file: Path to prompts YAML file

    Returns:
        QCModule instance
    """
    prompts = load_prompts_from_file(prompts_file)
    return QCModule(config, prompts)