"""
QC Cost Tracker

Handles cost tracking and metrics specifically for QC operations.
Integrates with existing cost tracking infrastructure.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class QCCostTracker:
    """
    Tracks costs and metrics for QC operations.
    Integrates with existing provider_metrics and DynamoDB tracking.
    """

    def __init__(self):
        """Initialize QC cost tracker."""
        self.qc_metrics = {
            'total_qc_calls': 0,
            'total_qc_tokens': 0,
            'total_qc_cost': 0.0,  # Actual cost paid (with cache benefits)
            'total_qc_estimated_cost': 0.0,  # Estimated cost without cache
            'total_qc_time_actual': 0.0,  # Actual time spent (with cache benefits)
            'total_qc_time_estimated': 0.0,  # Estimated time without cache
            'total_fields_reviewed': 0,
            'total_fields_modified': 0,
            'confidence_lowered_count': 0,
            'values_replaced_count': 0,
            'revision_percentages_by_column': {},
            'qc_models_used': set(),
            'qc_provider_metrics': {},
            # Per-column QC tracking for fail rate analysis
            'qc_by_column': {}  # column -> {reviewed: int, modified: int, confidence_lowered: int, values_replaced: int}
        }

    def track_qc_call(
        self,
        qc_response: Dict[str, Any],
        qc_results: List[Dict],
        qc_metrics: Dict[str, Any],
        model_used: str,
        api_provider: str
    ):
        """
        Track a single QC API call and its results.

        Args:
            qc_response: Response from QC API call
            qc_results: Parsed QC results
            qc_metrics: QC-specific metrics from QC module
            model_used: Model used for QC
            api_provider: API provider used
        """
        # Extract cost, token, and timing information from enhanced_data
        enhanced_data = qc_response.get('enhanced_data', {})
        usage = enhanced_data.get('token_usage', {}) or qc_response.get('usage', {})
        cost_info = enhanced_data.get('costs', {})
        timing_info = enhanced_data.get('timing', {})

        # Update totals
        self.qc_metrics['total_qc_calls'] += 1
        self.qc_metrics['total_qc_tokens'] += usage.get('total_tokens', 0)

        # Get actual vs estimated costs (following DYNAMODB_TABLES.md pattern)
        actual_cost = cost_info.get('actual', {}).get('total_cost', 0.0)
        estimated_cost = cost_info.get('estimated', {}).get('total_cost', 0.0)

        self.qc_metrics['total_qc_cost'] += actual_cost  # What we actually paid (with cache benefits)
        self.qc_metrics['total_qc_estimated_cost'] += estimated_cost  # What it would cost without cache

        # Track actual vs estimated timing (following DYNAMODB_TABLES.md pattern)
        actual_time = timing_info.get('time_actual_seconds', 0.0)
        estimated_time = timing_info.get('time_estimated_seconds', 0.0)

        self.qc_metrics['total_qc_time_actual'] += actual_time  # Actual time with cache benefits
        self.qc_metrics['total_qc_time_estimated'] += estimated_time  # Time without cache

        # Update field-level metrics
        self.qc_metrics['total_fields_reviewed'] += qc_metrics.get('qc_fields_reviewed', 0)
        self.qc_metrics['total_fields_modified'] += qc_metrics.get('qc_fields_modified', 0)
        self.qc_metrics['confidence_lowered_count'] += qc_metrics.get('qc_confidence_lowered', 0)
        self.qc_metrics['values_replaced_count'] += qc_metrics.get('qc_values_replaced', 0)

        # Track models used
        self.qc_metrics['qc_models_used'].add(model_used)

        # Update provider metrics
        if api_provider not in self.qc_metrics['qc_provider_metrics']:
            self.qc_metrics['qc_provider_metrics'][api_provider] = {
                'calls': 0,
                'tokens': 0,
                'cost_actual': 0.0,
                'cost_estimated': 0.0,
                'time_actual': 0.0,
                'time_estimated': 0.0,
                'models_used': set()
            }

        provider_metrics = self.qc_metrics['qc_provider_metrics'][api_provider]
        provider_metrics['calls'] += 1
        provider_metrics['tokens'] += usage.get('total_tokens', 0)
        provider_metrics['cost_actual'] = provider_metrics.get('cost_actual', 0.0) + actual_cost
        provider_metrics['cost_estimated'] = provider_metrics.get('cost_estimated', 0.0) + estimated_cost
        provider_metrics['time_actual'] = provider_metrics.get('time_actual', 0.0) + actual_time
        provider_metrics['time_estimated'] = provider_metrics.get('time_estimated', 0.0) + estimated_time
        provider_metrics['models_used'].add(model_used)

        # Calculate cache efficiency if we have both actual and estimated
        cache_efficiency = 0.0
        if estimated_cost > 0:
            cache_efficiency = ((estimated_cost - actual_cost) / estimated_cost) * 100.0

        logger.info(f"QC call tracked: {len(qc_results)} field modifications, "
                   f"${actual_cost:.6f} actual cost (${estimated_cost:.6f} estimated), "
                   f"{usage.get('total_tokens', 0)} tokens, {cache_efficiency:.1f}% cache efficiency")

        # Track per-column QC actions for fail rate analysis
        self.track_column_qc_actions(qc_results, qc_metrics)

    def track_column_qc_actions(self, qc_results: List[Dict], qc_metrics: Dict[str, Any]):
        """
        Track QC actions per column for fail rate analysis.

        Args:
            qc_results: List of QC results
            qc_metrics: QC metrics from QC module
        """
        # Get fields reviewed from QC metrics
        fields_reviewed = qc_metrics.get('qc_fields_reviewed', 0)
        if fields_reviewed == 0:
            return  # No fields to track

        # Track all fields that were reviewed (whether modified or not)
        # We'll need to get the column list from somewhere - for now track only modified fields
        for qc_result in qc_results:
            column = qc_result.get('column', '')
            if not column:
                continue

            # Initialize column tracking if not exists
            if column not in self.qc_metrics['qc_by_column']:
                self.qc_metrics['qc_by_column'][column] = {
                    'reviewed': 0,
                    'modified': 0,
                    'confidence_lowered': 0,
                    'values_replaced': 0
                }

            column_stats = self.qc_metrics['qc_by_column'][column]
            column_stats['reviewed'] += 1  # This field was reviewed

            # Since QC is now comprehensive, determine modifications by comparing values/confidence
            # Get original validation values from qc_metrics if available
            original_value = ''
            original_confidence = ''
            updated_value = ''
            updated_confidence = ''

            if qc_metrics and column in qc_metrics:
                field_data = qc_metrics[column]
                original_value = str(field_data.get('original_value', ''))
                original_confidence = str(field_data.get('original_confidence', ''))
                updated_value = str(field_data.get('updated_entry', ''))
                updated_confidence = str(field_data.get('updated_confidence', ''))

            # Get QC values
            qc_value = str(qc_result.get('answer', ''))
            qc_confidence = str(qc_result.get('confidence', ''))
            qc_original_confidence = str(qc_result.get('original_confidence', ''))
            qc_updated_confidence = str(qc_result.get('updated_confidence', ''))

            # Determine if QC made modifications
            value_changed = qc_value != updated_value
            confidence_changed = qc_confidence != updated_confidence
            original_confidence_changed = qc_original_confidence != original_confidence
            updated_confidence_changed = qc_updated_confidence != updated_confidence

            if value_changed:
                column_stats['values_replaced'] += 1
                column_stats['modified'] += 1
            elif confidence_changed or original_confidence_changed or updated_confidence_changed:
                column_stats['confidence_lowered'] += 1  # Generic confidence change tracking
                column_stats['modified'] += 1

    def get_qc_fail_rates_by_column(self) -> Dict[str, Dict[str, float]]:
        """
        Calculate QC fail rates by column.

        Returns:
            Dictionary mapping column names to fail rate statistics
        """
        fail_rates = {}

        for column, stats in self.qc_metrics['qc_by_column'].items():
            reviewed = stats['reviewed']
            modified = stats['modified']
            confidence_lowered = stats['confidence_lowered']
            values_replaced = stats['values_replaced']

            if reviewed > 0:
                fail_rates[column] = {
                    'total_reviewed': reviewed,
                    'total_modified': modified,
                    'overall_fail_rate': (modified / reviewed) * 100.0,
                    'confidence_fail_rate': (confidence_lowered / reviewed) * 100.0,
                    'value_fail_rate': (values_replaced / reviewed) * 100.0,
                    'confidence_lowered_count': confidence_lowered,
                    'values_replaced_count': values_replaced
                }
            else:
                fail_rates[column] = {
                    'total_reviewed': 0,
                    'total_modified': 0,
                    'overall_fail_rate': 0.0,
                    'confidence_fail_rate': 0.0,
                    'value_fail_rate': 0.0,
                    'confidence_lowered_count': 0,
                    'values_replaced_count': 0
                }

        return fail_rates

    def track_all_reviewed_fields(self, multiplex_results: List[Dict], qc_results: List[Dict]):
        """
        Track all fields that were reviewed by QC (both modified and unmodified).

        Args:
            multiplex_results: All multiplex results that were sent to QC
            qc_results: QC results (only contains modified fields)
        """
        # Create set of modified columns from QC results
        modified_columns = {qc_result.get('column', '') for qc_result in qc_results if qc_result.get('column')}

        # Track all fields from multiplex results
        for multiplex_result in multiplex_results:
            column = multiplex_result.get('column', '')
            if not column:
                continue

            # Initialize column tracking if not exists
            if column not in self.qc_metrics['qc_by_column']:
                self.qc_metrics['qc_by_column'][column] = {
                    'reviewed': 0,
                    'modified': 0,
                    'confidence_lowered': 0,
                    'values_replaced': 0
                }

            column_stats = self.qc_metrics['qc_by_column'][column]

            # Only increment reviewed count if we haven't already counted this field
            # (avoid double counting when both track_column_qc_actions and track_all_reviewed_fields are called)
            if column not in modified_columns:
                column_stats['reviewed'] += 1  # This field was reviewed but not modified

    def log_qc_fail_rate_summary(self):
        """Log a summary of QC fail rates by column."""
        fail_rates = self.get_qc_fail_rates_by_column()

        if not fail_rates:
            logger.info("No QC fail rate data available")
            return

        # Sort columns by overall fail rate (highest first)
        sorted_columns = sorted(fail_rates.items(), key=lambda x: x[1]['overall_fail_rate'], reverse=True)

        logger.info("QC Fail Rate Summary by Column:")
        for column, stats in sorted_columns:
            if stats['total_reviewed'] > 0:
                logger.info(f"  {column}: {stats['overall_fail_rate']:.1f}% fail rate "
                           f"({stats['total_modified']}/{stats['total_reviewed']} reviewed)")

    def update_revision_percentages(self, column_revision_data: Dict[str, Dict[str, Any]]):
        """
        Update revision percentages for columns based on QC results.

        Args:
            column_revision_data: Dictionary mapping column names to revision data
                Format: {column: {'total_rows': int, 'revised_rows': int}}
        """
        for column, revision_data in column_revision_data.items():
            total_rows = revision_data.get('total_rows', 0)
            revised_rows = revision_data.get('revised_rows', 0)

            if total_rows > 0:
                revision_percentage = (revised_rows / total_rows) * 100.0
            else:
                revision_percentage = 0.0

            self.qc_metrics['revision_percentages_by_column'][column] = {
                'percentage': round(revision_percentage, 2),
                'revised_rows': revised_rows,
                'total_rows': total_rows
            }

    def get_qc_metrics_for_aggregation(self) -> Dict[str, Any]:
        """
        Get QC metrics in format suitable for aggregation with existing metrics.

        Returns:
            Dictionary of QC metrics for integration with provider_metrics
        """
        # Convert sets to lists for JSON serialization
        qc_models_used = list(self.qc_metrics['qc_models_used'])

        provider_metrics = {}
        for provider, metrics in self.qc_metrics['qc_provider_metrics'].items():
            provider_metrics[provider] = {
                'calls': metrics['calls'],
                'tokens': metrics['tokens'],
                'cost': metrics['cost'],
                'models_used': list(metrics['models_used'])
            }

        return {
            'qc_totals': {
                'total_qc_calls': self.qc_metrics['total_qc_calls'],
                'total_qc_tokens': self.qc_metrics['total_qc_tokens'],
                'total_qc_cost': round(self.qc_metrics['total_qc_cost'], 6),
                'total_fields_reviewed': self.qc_metrics['total_fields_reviewed'],
                'total_fields_modified': self.qc_metrics['total_fields_modified'],
                'confidence_lowered_count': self.qc_metrics['confidence_lowered_count'],
                'values_replaced_count': self.qc_metrics['values_replaced_count'],
                'qc_models_used': qc_models_used
            },
            'qc_provider_metrics': provider_metrics,
            'qc_revision_percentages': self.qc_metrics['revision_percentages_by_column']
        }

    def merge_with_existing_metrics(
        self,
        existing_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge QC metrics with existing validation metrics.

        Args:
            existing_metrics: Existing metrics dictionary

        Returns:
            Merged metrics dictionary with QC data included
        """
        qc_metrics = self.get_qc_metrics_for_aggregation()

        # Create merged metrics
        merged_metrics = existing_metrics.copy()

        # Add QC metrics at top level
        merged_metrics['qc_metrics'] = qc_metrics

        # Update totals to include QC
        if 'totals' in merged_metrics:
            totals = merged_metrics['totals']
            qc_totals = qc_metrics['qc_totals']

            # Add QC costs to overall totals
            totals['total_cost_actual'] = totals.get('total_cost_actual', 0.0) + qc_totals['total_qc_cost']
            totals['total_cost_estimated'] = totals.get('total_cost_estimated', 0.0) + qc_totals['total_qc_cost']
            totals['total_tokens'] = totals.get('total_tokens', 0) + qc_totals['total_qc_tokens']
            totals['total_calls'] = totals.get('total_calls', 0) + qc_totals['total_qc_calls']

        # Merge QC provider metrics with existing provider metrics
        if 'providers' in merged_metrics:
            providers = merged_metrics['providers']
            qc_providers = qc_metrics['qc_provider_metrics']

            for provider_name, qc_provider_data in qc_providers.items():
                if provider_name not in providers:
                    providers[provider_name] = {
                        'calls': 0,
                        'tokens': 0,
                        'cost_actual': 0.0,
                        'cost_estimated': 0.0
                    }

                # Add QC metrics to provider totals
                providers[provider_name]['calls'] += qc_provider_data['calls']
                providers[provider_name]['tokens'] += qc_provider_data['tokens']
                providers[provider_name]['cost_actual'] += qc_provider_data['cost']
                providers[provider_name]['cost_estimated'] += qc_provider_data['cost']

                # Track QC models separately
                providers[provider_name]['qc_models_used'] = qc_provider_data['models_used']

        return merged_metrics

    def get_qc_summary_for_logging(self) -> str:
        """
        Get a summary string of QC metrics for logging.

        Returns:
            Formatted summary string
        """
        total_cost = self.qc_metrics['total_qc_cost']
        total_calls = self.qc_metrics['total_qc_calls']
        total_fields_reviewed = self.qc_metrics['total_fields_reviewed']
        total_fields_modified = self.qc_metrics['total_fields_modified']

        if total_fields_reviewed > 0:
            modification_rate = (total_fields_modified / total_fields_reviewed) * 100
        else:
            modification_rate = 0.0

        return (f"QC Summary: {total_calls} calls, {total_fields_reviewed} fields reviewed, "
               f"{total_fields_modified} modified ({modification_rate:.1f}%), "
               f"${total_cost:.6f} total cost")

    def prepare_qc_metrics_for_dynamodb(
        self,
        session_id: str,
        run_key: str
    ) -> Dict[str, Any]:
        """
        Prepare QC metrics for storage in DynamoDB runs table.

        Args:
            session_id: Session identifier
            run_key: Run key for DynamoDB

        Returns:
            Dictionary formatted for DynamoDB storage
        """
        qc_metrics = self.get_qc_metrics_for_aggregation()

        return {
            'session_id': session_id,
            'run_key': run_key,
            'qc_enabled': True,
            'qc_summary': qc_metrics['qc_totals'],
            'qc_provider_breakdown': qc_metrics['qc_provider_metrics'],
            'qc_revision_percentages': qc_metrics['qc_revision_percentages'],
            'qc_timestamp': datetime.now(timezone.utc).isoformat()
        }


def create_qc_cost_tracker() -> QCCostTracker:
    """
    Factory function to create QC cost tracker instance.

    Returns:
        QCCostTracker instance
    """
    return QCCostTracker()


def calculate_qc_revision_percentage(
    total_fields_reviewed: int,
    total_fields_modified: int
) -> float:
    """
    Calculate QC revision percentage.

    Args:
        total_fields_reviewed: Total number of fields reviewed by QC
        total_fields_modified: Total number of fields modified by QC

    Returns:
        Revision percentage (0-100)
    """
    if total_fields_reviewed <= 0:
        return 0.0

    return (total_fields_modified / total_fields_reviewed) * 100.0