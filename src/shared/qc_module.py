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
import difflib
import re

# Import shared modules
from ai_api_client import ai_client
from perplexity_schema import get_qc_response_format_schema, MULTIPLEX_RESPONSE_SCHEMA, ADDITIONAL_QC_FIELDS

logger = logging.getLogger(__name__)

def find_similar_columns(expected_columns: List[str], actual_columns: List[str], similarity_threshold: float = 0.8) -> Dict[str, str]:
    """
    Find column mappings between expected and actual columns using string similarity.
    Enhanced to handle parentheses by trying matches with and without them.

    Args:
        expected_columns: List of expected column names
        actual_columns: List of actual column names from API response
        similarity_threshold: Minimum similarity ratio (0.0 to 1.0) for a match

    Returns:
        Dictionary mapping actual column names to expected column names
        Only includes mappings above the similarity threshold
    """
    def strip_parentheses(text: str) -> str:
        """Remove parentheses and their contents from text."""
        return re.sub(r'\s*\([^)]*\)', '', text).strip()

    column_mappings = {}
    used_actual_columns = set()

    for expected_col in expected_columns:
        best_match = None
        best_ratio = 0.0

        # Try matching with original names
        for actual_col in actual_columns:
            if actual_col in used_actual_columns:
                continue

            # Calculate similarity ratio using difflib
            ratio = difflib.SequenceMatcher(None, expected_col.lower(), actual_col.lower()).ratio()

            if ratio > best_ratio and ratio >= similarity_threshold:
                best_match = actual_col
                best_ratio = ratio

        # If no match found, try matching without parentheses
        if not best_match:
            expected_stripped = strip_parentheses(expected_col)
            for actual_col in actual_columns:
                if actual_col in used_actual_columns:
                    continue

                actual_stripped = strip_parentheses(actual_col)

                # Calculate similarity ratio without parentheses
                ratio = difflib.SequenceMatcher(None, expected_stripped.lower(), actual_stripped.lower()).ratio()

                if ratio > best_ratio and ratio >= similarity_threshold:
                    best_match = actual_col
                    best_ratio = ratio

            if best_match:
                logger.info(f"[QC_FLEXIBLE_MATCH] Matched '{best_match}' to '{expected_col}' after stripping parentheses (ratio: {best_ratio:.2f})")

        if best_match:
            column_mappings[best_match] = expected_col
            used_actual_columns.add(best_match)

    return column_mappings

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

        # QC-specific configuration - ensure model is a string or list for fallback
        default_model = config.get('model', ['deepseek-v3.2', 'claude-sonnet-4-5'])
        if isinstance(default_model, list):
            default_model = default_model if default_model else ['deepseek-v3.2', 'claude-sonnet-4-5']
        else:
            # Convert single model to list with backup
            default_model = [default_model, 'claude-sonnet-4-5']

        qc_model_setting = self.qc_settings.get('model', default_model)
        # Keep as list for automatic fallback, or convert to list if single string
        if isinstance(qc_model_setting, list):
            self.qc_model = qc_model_setting if qc_model_setting else ['deepseek-v3.2', 'claude-sonnet-4-5']
        else:
            # Convert single model to list with backup
            self.qc_model = [qc_model_setting, 'claude-sonnet-4-5']
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

    def format_all_multiplex_outputs_for_qc(self, all_group_results: Dict[str, List[Dict]], original_row: Dict[str, Any] = None, validation_targets: List[Any] = None, group_metadata: Dict[str, Dict[str, Any]] = None, validation_history: Dict[str, Any] = None) -> str:
        """
        Format ALL multiplex validation outputs across all field groups for inclusion in QC prompt.
        Enhanced formatting to provide complete context for QC review.

        Args:
            all_group_results: Dictionary mapping group names to their multiplex validation results
            original_row: Original row data for extracting original values
            validation_targets: List of validation target objects for field guidance
            group_metadata: Dictionary mapping group names to metadata (description, model, etc.)
            validation_history: Validation history for this row (dict mapping column to history data)

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

            # Enhanced group header with descriptive name if available, fall back to group_name
            display_name = group_name
            if group_metadata and group_name in group_metadata:
                metadata = group_metadata[group_name]
                if metadata.get('group_name'):
                    display_name = metadata['group_name']
                    logger.debug(f"[QC_GROUP_DEBUG] Using descriptive name '{display_name}' for group key '{group_name}'")
                else:
                    logger.debug(f"[QC_GROUP_DEBUG] No group_name in metadata for '{group_name}', using key as display name")
            else:
                logger.debug(f"[QC_GROUP_DEBUG] No metadata found for group '{group_name}', using key as display name")

            group_section = [f"### FIELD GROUP: {display_name}"]

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
                original_confidence = result.get('original_confidence')  # Preserve None/null
                reasoning = result.get('reasoning', '')
                sources = result.get('sources', [])
                citations = result.get('citations', [])  # Full structured citation data
                explanation = result.get('explanation', '')

                # Debug logging for citations
                logger.debug(f"[QC_CITATIONS_DEBUG] {column}: Found {len(citations)} citations")
                if citations and len(citations) > 0:
                    # Log type of first citation for debugging
                    first_citation = citations[0]
                    if isinstance(first_citation, dict):
                        logger.debug(f"[QC_CITATIONS_DEBUG] {column}: First citation is dict with keys: {list(first_citation.keys())}")
                    else:
                        logger.debug(f"[QC_CITATIONS_DEBUG] {column}: First citation is string, length: {len(str(first_citation))}")

                # Enhanced field formatting with validation history context
                field_output = [
                    f"**FIELD: {column}**",
                    "",
                    "### Field Configuration"
                ]

                # Add field-specific guidance if available
                if column in targets_by_column:
                    target = targets_by_column[column]
                    if hasattr(target, 'description') and target.description:
                        field_output.append(f"* **Description:** {target.description}")
                    if hasattr(target, 'format') and target.format:
                        field_output.append(f"* **Format:** {target.format}")
                    if hasattr(target, 'notes') and target.notes:
                        field_output.append(f"* **Notes:** {target.notes}")
                    if hasattr(target, 'examples') and target.examples:
                        field_output.append("* **Examples:**")
                        for example in target.examples:
                            field_output.append(f"  - {example}")
                    field_output.append("")

                # Add validation history if available
                if validation_history and column in validation_history:
                    field_history = validation_history[column]

                    # Prior Value (the value from a previous validation run)
                    if field_history.get('prior_value'):
                        prior_ts = field_history.get('prior_timestamp', '')

                        # Use "previously" if no timestamp available (avoids cache break from S3 LastModified)
                        if prior_ts:
                            # We have an explicit prior timestamp from Validation Record
                            field_output.append(f"### Prior Value: `{field_history['prior_value']}` (from validation on {prior_ts})")
                        else:
                            # No timestamp available - say "previously"
                            field_output.append(f"### Prior Value: `{field_history['prior_value']}` (from previous validation)")

                        # Prior value only shows the confidence from that validation, no context
                        if field_history.get('prior_confidence'):
                            field_output.append(f"* **Prior Confidence:** {field_history['prior_confidence']}")
                        field_output.append("")

                # Original/Current Value (the INPUT - what's in the cell now)
                # This is from the most recent validation (has validation context in cell comments)
                original_ts = ''
                if validation_history and column in validation_history:
                    original_ts = validation_history[column].get('original_timestamp', '')

                # Use "previously" if no timestamp available (avoids cache break from S3 LastModified)
                if original_ts:
                    field_output.append(f"### Original/Current Value: `{original_value}` (validated on {original_ts})")
                else:
                    field_output.append(f"### Original/Current Value: `{original_value}` (from previous validation)")

                # Format original_confidence for display (show 'null' for None)
                original_conf_display = 'null' if original_confidence is None else original_confidence
                field_output.append(f"* **Original Confidence (Proposed):** {original_conf_display}")

                # Add validation context from cell comments for the current value
                if validation_history and column in validation_history:
                    field_history = validation_history[column]

                    # The validation context belongs to the Original/Current value
                    # Show the key citation
                    if field_history.get('original_key_citation'):
                        field_output.append(f"* **Key Citation:** {field_history['original_key_citation']}")

                    # Show full source citations if available, otherwise fall back to URLs
                    if field_history.get('original_sources_full'):
                        field_output.append(f"* **Sources:**")
                        for source in field_history['original_sources_full']:
                            field_output.append(f"  - {source}")
                    elif field_history.get('original_sources'):
                        # Fallback to just URLs if full citations not available
                        field_output.append(f"* **Sources:** {', '.join(field_history['original_sources'])}")

                    # Show the even older value from Original Values sheet if available
                    if field_history.get('original_value'):
                        field_output.append(f"* **Original Values sheet entry:** `{field_history['original_value']}`")
                field_output.append("")

                # Updated Value (Proposed) - show the actual validated value
                field_output.append(f"### Updated Value (Proposed): `{answer}`")
                field_output.append(f"* **Updated Confidence (Proposed):** {confidence}")

                # Show explanation (AI's reasoning for the answer)
                if explanation:
                    field_output.append(f"* **Explanation:** {explanation}")

                # Show citations with full text from structured citation data
                if citations and any(citations):  # Check if citations exist and are not empty
                    field_output.append(f"* **Citations:**")
                    for i, citation in enumerate(citations, 1):
                        # Handle both structured citation objects and plain strings
                        if isinstance(citation, dict):
                            # Format structured citation with title and snippet
                            title = citation.get('title', 'Untitled')
                            url = citation.get('url', '')
                            cited_text = citation.get('cited_text', '')

                            # Format: [{#}] {Title}: "{quote}" (URL)
                            if cited_text:
                                citation_text = f"[{i}] {title}: \"{cited_text}\" ({url})"
                            else:
                                citation_text = f"[{i}] {title} ({url})"
                            field_output.append(f"  - {citation_text}")
                        else:
                            # Plain string citation (fallback)
                            field_output.append(f"  - [{i}] {citation}")
                elif sources:  # If no citations but we have source URLs, format them
                    field_output.append(f"* **Citations:** (URLs only)")
                    for i, source in enumerate(sources, 1):
                        field_output.append(f"  - [{i}] {source}")
                else:
                    field_output.append(f"* **Citations:** None")

                # Also show just the source URLs separately for quick reference if we have full citations
                # Only show this if we had actual citations (to avoid duplication)
                if citations and any(citations) and sources:
                    field_output.append(f"* **Source URLs:** {', '.join(sources)}")

                # Show supporting quotes if available (provides context when citation snippets not available)
                supporting_quotes = result.get('supporting_quotes', '')
                if supporting_quotes and supporting_quotes.strip():
                    field_output.append(f"* **Supporting Quotes:** {supporting_quotes}")
                field_output.append(f"* **Substantially Different from Original:** {'Yes' if str(answer).strip() != str(original_value).strip() else 'No'}")

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

    def _format_citations_for_qc(self, citations: List[str]) -> str:
        """
        Format citations for QC prompt to provide full citation text rather than just URLs.

        Args:
            citations: List of citation strings (full citation text with titles and snippets)

        Returns:
            Formatted citation string for QC prompt
        """
        if not citations:
            return 'None'

        # Format all citations with numbers for QC reference
        formatted_citations = []
        for i, citation in enumerate(citations, 1):
            formatted_citations.append(f"[{i}] {citation}")
        return '\n'.join(formatted_citations)


    async def process_qc_for_complete_row(
        self,
        session: Any,
        row: Dict[str, Any],
        all_group_results: Dict[str, List[Dict]],
        validation_targets: List[Any],
        context: str = "",
        general_notes: str = "",
        group_metadata: Dict[str, Dict[str, Any]] = None,
        validation_history: Dict[str, Any] = None
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
            validation_history: Validation history for this row (dict mapping column to history data)

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
            scrubbed_all_group_results, row, validation_targets, group_metadata, validation_history
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
                'qc_response_data': qc_response,

                # Add fields expected by validation lambda for aggregation
                'qc_cost': costs_data.get('actual', {}).get('total_cost', 0.0),  # Alias for qc_cost_actual
                'qc_calls': 1,  # This QC call count
                'confidence_lowered_count': 0,  # Will be updated by cost tracker
                'values_replaced_count': 0  # Will be updated by cost tracker
            }

            # Extract structured response using ai_client method
            try:
                structured_data = ai_client.extract_structured_response(qc_response['response'], "qc_validation")
                qc_results = structured_data.get('qc_results', []) if isinstance(structured_data, dict) else []
                logger.info(f"QC returned {len(qc_results)} field modifications across all groups")

                # Apply flexible column matching to QC results
                if qc_results and validation_targets:
                    # Get expected column names from non-ID validation targets
                    expected_columns = [t.column for t in validation_targets if hasattr(t, 'importance') and t.importance.upper() not in ['ID', 'IGNORED']]
                    actual_columns = [result.get('column', '') for result in qc_results if result.get('column')]

                    # Check for missing columns
                    exact_missing = set(expected_columns) - set(actual_columns)

                    if exact_missing:
                        logger.warning(f"[QC_COLUMN_CHECK] QC response missing columns: {list(exact_missing)}")
                        logger.info(f"[QC_COLUMN_CHECK] Attempting flexible column matching for QC results")

                        # Apply flexible matching
                        column_mappings = find_similar_columns(expected_columns, actual_columns, similarity_threshold=0.8)

                        # Create a lookup for quick access
                        qc_results_by_column = {result.get('column', ''): result for result in qc_results}

                        # Apply corrections
                        corrected_qc_results = []
                        for expected_col in expected_columns:
                            matched = False
                            for actual_col, mapped_expected_col in column_mappings.items():
                                if mapped_expected_col == expected_col and actual_col in qc_results_by_column:
                                    result = qc_results_by_column[actual_col].copy()
                                    result['column'] = expected_col  # Correct the column name
                                    corrected_qc_results.append(result)
                                    logger.warning(f"[QC_COLUMN_CORRECTION] '{actual_col}' -> '{expected_col}' (similarity matching)")
                                    matched = True
                                    break

                            # If exact match exists, use it
                            if not matched and expected_col in qc_results_by_column:
                                corrected_qc_results.append(qc_results_by_column[expected_col])
                                matched = True

                            # If still no match, create error placeholder
                            if not matched:
                                logger.error(f"[QC_MISSING_COLUMN] QC response missing column '{expected_col}' even after flexible matching")
                                corrected_qc_results.append({
                                    'column': expected_col,
                                    'answer': '[ERROR: QC did not return this field]',
                                    'confidence': 'LOW',
                                    'original_confidence': 'LOW',
                                    'qc_reasoning': f"QC response did not include field '{expected_col}'. Received columns: {', '.join(actual_columns)}",
                                    'qc_citations': '[ERROR] QC field missing',
                                    'update_importance': '0'
                                })

                        qc_results = corrected_qc_results
                        logger.info(f"[QC_FLEXIBLE_MATCH] After flexible matching: {len(qc_results)} QC results aligned with expected columns")

                # Debug QC API response
                logger.info(f"QC API structured extraction successful: found {len(qc_results)} QC responses (comprehensive)")

                # ENFORCE: Blank cells must have null confidence (don't rely on AI)
                for qc_result in qc_results:
                    column = qc_result.get('column', '')
                    if column:
                        # ENFORCE 1: If QC answer is blank, force confidence to null
                        qc_answer = qc_result.get('answer')
                        if qc_answer is None or str(qc_answer).strip() == '':
                            if qc_result.get('confidence') is not None:
                                logger.info(f"[QC_NULL_ENFORCE] {column}: QC answer is blank, forcing confidence to null (was: {qc_result.get('confidence')})")
                                qc_result['confidence'] = None

                        # ENFORCE 2: Check original row data - if it was blank, force null original_confidence
                        original_row_value = row.get(column) if row else None
                        if original_row_value is None or str(original_row_value).strip() == '':
                            if qc_result.get('original_confidence') is not None:
                                logger.info(f"[QC_NULL_ENFORCE] {column}: Original row value was blank, forcing original_confidence to null (was: {qc_result.get('original_confidence')})")
                                qc_result['original_confidence'] = None

                        # ENFORCE 3: Double-check validation also had null (backup check)
                        for group_results in all_group_results.values():
                            for validation_result in group_results:
                                if validation_result.get('column') == column:
                                    validation_original_conf = validation_result.get('original_confidence')
                                    if validation_original_conf is None:
                                        # Validation had null - enforce QC keeps it null
                                        if qc_result.get('original_confidence') is not None:
                                            logger.info(f"[QC_NULL_ENFORCE] {column}: Validation had null original_confidence, forcing QC to preserve null (was: {qc_result.get('original_confidence')})")
                                            qc_result['original_confidence'] = None
                                    break

                # Update metrics - count actual modifications, not just QC responses
                # With comprehensive QC, len(qc_results) equals all fields processed
                # But we only want to count actual modifications for meaningful metrics
                # Cost tracker will provide accurate modification counts based on value comparison
                qc_metrics['qc_fields_modified'] = 0  # Will be updated by cost tracker
                qc_metrics['qc_values_replaced'] = 0  # Will be updated by cost tracker

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
                'qc_cache_hit_tokens': token_usage.get('cache_read_tokens', 0),

                # Add fields expected by validation lambda for aggregation
                'qc_cost': costs_data.get('actual', {}).get('total_cost', 0.0),  # Alias for qc_cost_actual
                'qc_calls': 1,  # This QC call count
                'confidence_lowered_count': 0,  # Will be updated by cost tracker
                'values_replaced_count': 0  # Will be updated by cost tracker
            }

            # Extract structured response using ai_client method
            try:
                structured_data = ai_client.extract_structured_response(qc_response['response'], "qc_validation")
                qc_results = structured_data.get('qc_results', []) if isinstance(structured_data, dict) else []
                logger.info(f"QC returned {len(qc_results)} field modifications")

                # Apply flexible column matching to QC results
                if qc_results and validation_targets:
                    # Get expected column names from non-ID validation targets
                    expected_columns = [t.column for t in validation_targets if hasattr(t, 'importance') and t.importance.upper() not in ['ID', 'IGNORED']]
                    actual_columns = [result.get('column', '') for result in qc_results if result.get('column')]

                    # Check for missing columns
                    exact_missing = set(expected_columns) - set(actual_columns)

                    if exact_missing:
                        logger.warning(f"[QC_COLUMN_CHECK] QC response missing columns: {list(exact_missing)}")
                        logger.info(f"[QC_COLUMN_CHECK] Attempting flexible column matching for QC results")

                        # Apply flexible matching
                        column_mappings = find_similar_columns(expected_columns, actual_columns, similarity_threshold=0.8)

                        # Create a lookup for quick access
                        qc_results_by_column = {result.get('column', ''): result for result in qc_results}

                        # Apply corrections
                        corrected_qc_results = []
                        for expected_col in expected_columns:
                            matched = False
                            for actual_col, mapped_expected_col in column_mappings.items():
                                if mapped_expected_col == expected_col and actual_col in qc_results_by_column:
                                    result = qc_results_by_column[actual_col].copy()
                                    result['column'] = expected_col  # Correct the column name
                                    corrected_qc_results.append(result)
                                    logger.warning(f"[QC_COLUMN_CORRECTION] '{actual_col}' -> '{expected_col}' (similarity matching)")
                                    matched = True
                                    break

                            # If exact match exists, use it
                            if not matched and expected_col in qc_results_by_column:
                                corrected_qc_results.append(qc_results_by_column[expected_col])
                                matched = True

                            # If still no match, create error placeholder
                            if not matched:
                                logger.error(f"[QC_MISSING_COLUMN] QC response missing column '{expected_col}' even after flexible matching")
                                corrected_qc_results.append({
                                    'column': expected_col,
                                    'answer': '[ERROR: QC did not return this field]',
                                    'confidence': 'LOW',
                                    'original_confidence': 'LOW',
                                    'qc_reasoning': f"QC response did not include field '{expected_col}'. Received columns: {', '.join(actual_columns)}",
                                    'qc_citations': '[ERROR] QC field missing',
                                    'qc_sources': [],
                                    'update_importance': '0'
                                })

                        qc_results = corrected_qc_results
                        logger.info(f"[QC_FLEXIBLE_MATCH] After flexible matching: {len(qc_results)} QC results aligned with expected columns")

                # Extract QC sources from AI API response metadata (like validation does)
                qc_api_citations = qc_response.get('citations', [])
                # Scrub encrypted content from citations before processing
                scrubbed_qc_citations = self.scrub_encrypted_content(qc_api_citations)
                qc_sources_from_metadata = [c.get('url', '') for c in scrubbed_qc_citations if c.get('url')]
                logger.info(f"[QC_SOURCES_DEBUG] Extracted {len(qc_sources_from_metadata)} source URLs from QC API response metadata (encrypted content scrubbed)")

                # Add metadata sources to all QC results (since all fields benefit from the QC web search)
                for qc_result in qc_results:
                    column = qc_result.get('column', '')

                    # qc_citations comes from AI's JSON response (already included by AI)
                    # qc_sources comes from API metadata (like validation does)
                    if 'qc_sources' not in qc_result:
                        qc_result['qc_sources'] = qc_sources_from_metadata

                    logger.info(f"[QC_SOURCES_DEBUG] {column}: Added {len(qc_result.get('qc_sources', []))} metadata sources")

                # Debug QC API response
                logger.info(f"QC API structured extraction successful: found {len(qc_results)} QC responses (comprehensive)")

                # Update metrics - count actual modifications, not just QC responses
                # With comprehensive QC, len(qc_results) equals all fields processed
                # But we only want to count actual modifications for meaningful metrics
                # Cost tracker will provide accurate modification counts based on value comparison
                qc_metrics['qc_fields_modified'] = 0  # Will be updated by cost tracker
                qc_metrics['qc_values_replaced'] = 0  # Will be updated by cost tracker

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
        qc_results: List[Dict],
        original_row_data: Dict[str, Any] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Merge multiplex and QC results to create final entries with Original, Updated, and QC values.

        Args:
            multiplex_results: Original multiplex validation results
            qc_results: QC override results
            original_row_data: Original row data (needed for soft comparison with original values)

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
            # IMPORTANT: Preserve None/null values for confidences (don't default to empty string)
            merged_result = {
                # Original multiplex data (this represents the "Updated Entry")
                'updated_entry': multiplex_result.get('answer', ''),
                'updated_confidence': multiplex_result.get('confidence', ''),
                'original_confidence': multiplex_result.get('original_confidence'),  # Preserve None/null
                'updated_reasoning': multiplex_result.get('reasoning', ''),
                'updated_sources': multiplex_result.get('sources', []),

                # QC data (defaults will be overridden if QC was applied)
                'qc_applied': qc_applied,
                'qc_entry': '',
                'qc_confidence': '',
                'qc_reasoning': '',
                'qc_sources': [],
                'qc_citations': '',
                'qc_original_confidence': None,  # Default to None, not empty string
                'qc_updated_confidence': None,   # Default to None, not empty string

                # Aggregated sources
                'all_sources': aggregated_citations.get(column, [])
            }

            if qc_applied:
                # QC made changes - extract QC-specific fields only
                # Since QC is now comprehensive, we always have QC values
                qc_reasoning = qc_result.get('qc_reasoning', '')

                # Extract QC fields (now all mandatory)
                qc_entry = qc_result.get('answer', merged_result['updated_entry'])
                qc_confidence = qc_result.get('confidence', merged_result['updated_confidence'])

                # Extract QC-revised confidence levels (preserve None/null, don't convert to empty string)
                qc_original_confidence = qc_result.get('original_confidence')  # Can be None/null
                qc_updated_confidence = qc_result.get('updated_confidence')    # Can be None/null

                # Parse update_importance FIRST (format: "N - Explanation text")
                update_importance_raw = qc_result.get('update_importance', '0')
                update_importance_level = 0
                update_importance_explanation = ''

                try:
                    if ' - ' in str(update_importance_raw):
                        parts = str(update_importance_raw).split(' - ', 1)
                        update_importance_level = int(parts[0].strip())
                        update_importance_explanation = parts[1].strip()
                    else:
                        # If no explanation, just parse the number
                        update_importance_level = int(str(update_importance_raw).strip())
                except (ValueError, AttributeError):
                    logger.warning(f"Could not parse update_importance: {update_importance_raw}")
                    update_importance_level = 0

                # Check if QC entry is the same as original value (normalized comparison)
                # If same, OR if update_importance is 0 or 1, enforce original_confidence == qc_confidence
                # Get original value from row data if available, otherwise from multiplex result
                original_value_from_row = ''
                if original_row_data and column in original_row_data:
                    original_value_from_row = original_row_data[column]
                else:
                    original_value_from_row = multiplex_result.get('original_value', '')

                def normalize_for_comparison(value):
                    """Normalize value for comparison: strip whitespace, lowercase, remove punctuation"""
                    import string
                    if value is None:
                        return ''
                    value_str = str(value).strip().lower()
                    # Remove punctuation
                    value_str = value_str.translate(str.maketrans('', '', string.punctuation))
                    return value_str

                enforce_equal_confidence = False
                enforcement_reason = ""

                # Check condition 1: QC entry equals original value
                if normalize_for_comparison(qc_entry) == normalize_for_comparison(original_value_from_row):
                    enforce_equal_confidence = True
                    enforcement_reason = "QC entry matches original value"

                # Check condition 2: Update importance is 0 or 1
                if update_importance_level in [0, 1]:
                    enforce_equal_confidence = True
                    if enforcement_reason:
                        enforcement_reason += f" AND update_importance={update_importance_level}"
                    else:
                        enforcement_reason = f"update_importance={update_importance_level}"

                if enforce_equal_confidence:
                    # No meaningful change - enforce original confidence == qc confidence
                    logger.info(f"[QC_CONFIDENCE_ENFORCEMENT] {column}: {enforcement_reason}, enforcing original_confidence == qc_confidence ({qc_confidence})")
                    qc_original_confidence = qc_confidence  # Override to match QC confidence

                # Update confidence levels if QC provided revisions (check is not None, not truthiness)
                # This preserves None/null values instead of skipping them
                if qc_original_confidence is not None:
                    merged_result['qc_original_confidence'] = qc_original_confidence
                    merged_result['original_confidence'] = qc_original_confidence  # Update in place
                if qc_updated_confidence is not None:
                    merged_result['qc_updated_confidence'] = qc_updated_confidence
                    merged_result['updated_confidence'] = qc_updated_confidence  # Update in place

                # Debug logging to see what QC actually returned
                logger.debug(f"[QC_MERGE_DEBUG] {column}: QC returned entry='{qc_entry}', confidence='{qc_confidence}'")
                logger.debug(f"[QC_MERGE_DEBUG] {column}: Original='{multiplex_result.get('original_value', 'N/A')}', Validated='{merged_result['updated_entry']}', QC='{qc_entry}'")
                logger.debug(f"[QC_MERGE_DEBUG] {column}: Final merged QC fields - qc_applied=True, qc_entry='{qc_entry}', qc_confidence='{qc_confidence}'")

                merged_result.update({
                    'qc_entry': qc_entry,
                    'qc_confidence': qc_confidence,
                    'qc_reasoning': qc_reasoning,
                    'qc_sources': qc_result.get('qc_sources', []),  # QC sources from AI API client
                    'qc_citations': qc_result.get('qc_citations', ''),  # QC citations for cell comments
                    'qc_original_confidence': merged_result.get('qc_original_confidence', ''),  # QC-revised original confidence
                    'qc_updated_confidence': merged_result.get('qc_updated_confidence', ''),     # QC-revised updated confidence
                    'update_importance': update_importance_raw,  # Full string with explanation
                    'update_importance_level': update_importance_level,  # Numeric level 0-5
                    'update_importance_explanation': update_importance_explanation  # Just the explanation text
                })
            else:
                # No QC changes - QC entry same as updated entry
                merged_result.update({
                    'qc_entry': merged_result['updated_entry'],
                    'qc_confidence': merged_result['updated_confidence'],
                    'update_importance': '0',  # No update importance when QC not applied
                    'update_importance_level': 0,
                    'update_importance_explanation': ''
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
    Load prompts from markdown files.

    Args:
        prompts_file: Path to prompts directory or legacy YAML file (for backward compatibility)

    Returns:
        Dictionary of prompt templates
    """
    try:
        # Use proper path resolution for Lambda environment
        prompts_dir = Path(__file__).parent / "prompts"

        # Load QC validation prompt from markdown
        qc_validation_path = prompts_dir / "qc_validation.md"

        prompts = {}

        if qc_validation_path.exists():
            with open(qc_validation_path, 'r', encoding='utf-8') as f:
                prompts['qc_validation'] = f.read()
            logger.info(f"Loaded qc_validation prompt from {qc_validation_path}")
        else:
            logger.error(f"QC validation prompt not found at {qc_validation_path}")

        return prompts

    except Exception as e:
        logger.error(f"Error loading prompts from markdown files: {e}")
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