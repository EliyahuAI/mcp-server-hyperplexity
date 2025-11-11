"""
QC Integration Interface

Provides a clean integration interface for the QC module with the validation lambda.
This keeps QC functionality separate while providing a simple integration point.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
import json

# Import QC modules
from qc_module import QCModule, create_qc_module
from qc_cost_tracker import QCCostTracker, create_qc_cost_tracker
from qc_excel_formatter import format_qc_result_for_excel

logger = logging.getLogger(__name__)

class QCIntegrationManager:
    """
    Manages QC integration with the validation lambda.
    Provides a clean interface that minimizes changes to the main validation logic.
    """

    def __init__(self, config: Dict[str, Any], prompts_file: str = "prompts.yml"):
        """
        Initialize QC integration manager.

        Args:
            config: Configuration dictionary
            prompts_file: Path to prompts YAML file
        """
        self.config = config
        self.qc_module = create_qc_module(config, prompts_file)
        self.cost_tracker = create_qc_cost_tracker()
        self.enabled = self.qc_module.is_enabled()

        logger.info(f"QC Integration Manager initialized: enabled={self.enabled}")

    def is_qc_enabled(self) -> bool:
        """Check if QC is enabled."""
        return self.enabled

    async def process_complete_row_qc(
        self,
        session: Any,
        row: Dict[str, Any],
        all_group_results: Dict[str, List[Dict]],
        validation_targets: List[Any],
        context: str = "",
        general_notes: str = "",
        group_metadata: Dict[str, Dict[str, Any]] = None,
        validation_history: Dict[str, Any] = None
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """
        Process QC for a complete row after ALL field groups have been processed.

        Args:
            session: aiohttp session
            row: Row data
            all_group_results: Dictionary mapping group names to their multiplex validation results
            validation_targets: Validation targets
            context: Context information
            general_notes: General guidance notes
            group_metadata: Dictionary mapping group names to metadata (description, model, etc.)
            validation_history: Validation history for this row (dict mapping column to history data)

        Returns:
            Tuple of (merged_results_by_column, qc_metrics)
        """
        if not self.enabled:
            # QC disabled - return all multiplex results as-is
            # Note: When QC is disabled, original_confidence should be the validation's confidence
            # (not the pre-validation original_confidence from the cell)
            merged_results = {}
            for group_name, group_results in all_group_results.items():
                for result in group_results:
                    column = result.get('column', '')
                    if column:
                        validation_confidence = result.get('confidence', '')
                        merged_results[column] = {
                            'updated_entry': result.get('answer', ''),
                            'updated_confidence': validation_confidence,
                            'original_confidence': validation_confidence,  # Use validation confidence as original when no QC
                            'updated_reasoning': result.get('reasoning', ''),
                            'updated_sources': result.get('sources', []),
                            'qc_applied': False,
                            'qc_entry': result.get('answer', ''),
                            'qc_confidence': validation_confidence,
                            'qc_reasoning': '',
                            'qc_sources': [],
                            'all_sources': result.get('sources', []),
                            'group_name': group_name
                        }
            return merged_results, {}

        # Flatten all multiplex results for total count
        all_multiplex_results = []
        for group_results in all_group_results.values():
            all_multiplex_results.extend(group_results)

        # Run QC processing on complete row
        qc_results, qc_metrics = await self.qc_module.process_qc_for_complete_row(
            session=session,
            row=row,
            all_group_results=all_group_results,
            validation_targets=validation_targets,
            context=context,
            general_notes=general_notes,
            group_metadata=group_metadata,
            validation_history=validation_history
        )

        # Merge multiplex and QC results first to get proper validation data
        merged_results = self.qc_module.merge_multiplex_and_qc_results(
            multiplex_results=all_multiplex_results,
            qc_results=qc_results,
            original_row_data=row
        )

        # Track QC costs and metrics using merged results for proper comparison
        if qc_results or qc_metrics:
            model_used = qc_metrics.get('qc_model_used', 'claude-sonnet-4-5')
            if isinstance(model_used, list):
                model_used = model_used[0] if model_used else 'claude-sonnet-4-5'

            api_provider = 'anthropic'  # QC uses Claude models

            # Get the real QC response with proper enhanced_data from original qc_metrics
            qc_response_data = qc_metrics.get('qc_response_data', {})

            # Use a hybrid approach: pass original qc_metrics but add merged results to it for comparison
            enhanced_qc_metrics = qc_metrics.copy()
            enhanced_qc_metrics['validation_comparison_data'] = merged_results

            self.cost_tracker.track_qc_call(
                qc_response=qc_response_data,
                qc_results=qc_results,
                qc_metrics=enhanced_qc_metrics,
                model_used=model_used,
                api_provider=api_provider
            )

            # Update QC metrics with actual modification counts from cost tracker
            qc_metrics['confidence_lowered_count'] = sum(
                stats.get('confidence_lowered', 0)
                for stats in self.cost_tracker.qc_metrics['qc_by_column'].values()
            )
            qc_metrics['values_replaced_count'] = sum(
                stats.get('values_replaced', 0)
                for stats in self.cost_tracker.qc_metrics['qc_by_column'].values()
            )

            # Track all reviewed fields for accurate fail rate calculation
            self.cost_tracker.track_all_reviewed_fields(all_multiplex_results, qc_results)

        # Add group information to merged results
        for group_name, group_results in all_group_results.items():
            for result in group_results:
                column = result.get('column', '')
                if column in merged_results:
                    merged_results[column]['group_name'] = group_name

        return merged_results, qc_metrics

    async def process_row_qc(
        self,
        session: Any,
        row: Dict[str, Any],
        multiplex_results: List[Dict],
        validation_targets: List[Any],
        context: str = "",
        general_notes: str = "",
        group_name: str = "",
        group_description: str = ""
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """
        Process QC for a single row.

        Args:
            session: aiohttp session
            row: Row data
            multiplex_results: Multiplex validation results
            validation_targets: Validation targets
            context: Context information
            general_notes: General guidance notes
            group_name: Group name
            group_description: Group description

        Returns:
            Tuple of (merged_results_by_column, qc_metrics)
        """
        if not self.enabled:
            # QC disabled - return multiplex results as-is
            # Note: When QC is disabled, original_confidence should be the validation's confidence
            # (not the pre-validation original_confidence from the cell)
            merged_results = {}
            for result in multiplex_results:
                column = result.get('column', '')
                if column:
                    validation_confidence = result.get('confidence', '')
                    merged_results[column] = {
                        'updated_entry': result.get('answer', ''),
                        'updated_confidence': validation_confidence,
                        'original_confidence': validation_confidence,  # Use validation confidence as original when no QC
                        'updated_reasoning': result.get('reasoning', ''),
                        'updated_sources': result.get('sources', []),
                        'qc_applied': False,
                        'qc_entry': result.get('answer', ''),
                        'qc_confidence': validation_confidence,
                        'qc_reasoning': '',
                        'qc_sources': [],
                        'all_sources': result.get('sources', [])
                    }
            return merged_results, {}

        # Run QC processing
        qc_results, qc_metrics = await self.qc_module.process_qc_for_row(
            session=session,
            row=row,
            multiplex_results=multiplex_results,
            validation_targets=validation_targets,
            context=context,
            general_notes=general_notes,
            group_name=group_name,
            group_description=group_description
        )

        # Merge multiplex and QC results first to get proper validation data
        merged_results = self.qc_module.merge_multiplex_and_qc_results(
            multiplex_results=multiplex_results,
            qc_results=qc_results,
            original_row_data=row
        )

        # Track QC costs and metrics using merged results for proper comparison
        if qc_results or qc_metrics:
            model_used = qc_metrics.get('qc_model_used', 'claude-sonnet-4-5')
            if isinstance(model_used, list):
                model_used = model_used[0] if model_used else 'claude-sonnet-4-5'

            api_provider = 'anthropic'  # QC uses Claude models

            # Get the real QC response with proper enhanced_data from original qc_metrics
            qc_response_data = qc_metrics.get('qc_response_data', {})

            # Use a hybrid approach: pass original qc_metrics but add merged results to it for comparison
            enhanced_qc_metrics = qc_metrics.copy()
            enhanced_qc_metrics['validation_comparison_data'] = merged_results

            self.cost_tracker.track_qc_call(
                qc_response=qc_response_data,
                qc_results=qc_results,
                qc_metrics=enhanced_qc_metrics,
                model_used=model_used,
                api_provider=api_provider
            )

            # Update QC metrics with actual modification counts from cost tracker
            qc_metrics['confidence_lowered_count'] = sum(
                stats.get('confidence_lowered', 0)
                for stats in self.cost_tracker.qc_metrics['qc_by_column'].values()
            )
            qc_metrics['values_replaced_count'] = sum(
                stats.get('values_replaced', 0)
                for stats in self.cost_tracker.qc_metrics['qc_by_column'].values()
            )

            # Track all reviewed fields for accurate fail rate calculation
            self.cost_tracker.track_all_reviewed_fields(multiplex_results, qc_results)

        return merged_results, qc_metrics

    def get_qc_metrics(self) -> Dict[str, Any]:
        """
        Get QC metrics for provider tracking.

        Returns:
            Dictionary containing QC metrics for provider tracking
        """
        if not self.enabled:
            return {}

        return self.cost_tracker.qc_metrics

    def get_aggregated_qc_metrics(self) -> Dict[str, Any]:
        """
        Get aggregated QC metrics for the entire validation run.

        Returns:
            Dictionary of aggregated QC metrics
        """
        return self.cost_tracker.get_qc_metrics_for_aggregation()

    def merge_qc_with_validation_metrics(self, validation_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge QC metrics with existing validation metrics.

        Args:
            validation_metrics: Existing validation metrics

        Returns:
            Merged metrics including QC data
        """
        return self.cost_tracker.merge_with_existing_metrics(validation_metrics)

    def update_revision_percentages(self, column_revision_data: Dict[str, Dict[str, Any]]):
        """
        Update QC revision percentages by column.

        Args:
            column_revision_data: Revision data by column
        """
        self.cost_tracker.update_revision_percentages(column_revision_data)

    def format_qc_results_for_excel(
        self,
        merged_results: Dict[str, Dict[str, Any]],
        original_row_data: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Format QC results for Excel output.

        Args:
            merged_results: Merged QC results by column
            original_row_data: Original row data

        Returns:
            List of formatted results for Excel
        """
        formatted_results = []

        for column, merged_result in merged_results.items():
            original_value = original_row_data.get(column, '')
            formatted_result = format_qc_result_for_excel(
                merged_qc_result=merged_result,
                field_name=column,
                original_value=original_value
            )
            formatted_results.append(formatted_result)

        return formatted_results

    def get_qc_summary_for_logging(self) -> str:
        """
        Get QC summary for logging.

        Returns:
            Summary string
        """
        return self.cost_tracker.get_qc_summary_for_logging()

    def prepare_qc_data_for_interface_lambda(
        self,
        merged_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Prepare QC data for interface lambda according to requirements.

        Args:
            merged_results: Merged QC results

        Returns:
            Data structure for interface lambda with Original + QC values
        """
        interface_data = {}

        for column, merged_result in merged_results.items():
            qc_applied = merged_result.get('qc_applied', False)

            # Prepare data showing Original and QC values
            interface_data[column] = {
                'original_value': merged_result.get('original_value', ''),  # Original Entry
                'qc_value': merged_result.get('qc_entry', ''),  # QC Entry (final)
                'qc_applied': qc_applied,
                'qc_action': 'Comprehensive QC',  # All fields now get full QC
                'qc_reasoning': merged_result.get('qc_reasoning', ''),
                'final_confidence': merged_result.get('qc_confidence', merged_result.get('updated_confidence', '')),
                'all_sources': merged_result.get('all_sources', [])
            }

        return interface_data


def create_qc_integration_manager(
    config: Dict[str, Any],
    prompts_file: str = "prompts.yml"
) -> QCIntegrationManager:
    """
    Factory function to create QC integration manager.

    Args:
        config: Configuration dictionary
        prompts_file: Path to prompts YAML file

    Returns:
        QCIntegrationManager instance
    """
    return QCIntegrationManager(config, prompts_file)


def extract_original_values_from_row(
    row_data: Dict[str, Any],
    validation_targets: List[Any]
) -> Dict[str, str]:
    """
    Extract original values from row data for QC processing.

    Args:
        row_data: Row data dictionary
        validation_targets: Validation targets

    Returns:
        Dictionary mapping column names to original values
    """
    original_values = {}

    for target in validation_targets:
        column_name = getattr(target, 'column', '') or getattr(target, 'name', '')
        if column_name and column_name in row_data:
            original_values[column_name] = str(row_data[column_name]) if row_data[column_name] is not None else ''

    return original_values