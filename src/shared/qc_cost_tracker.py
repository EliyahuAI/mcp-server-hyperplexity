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
            'total_qc_cost': 0.0,
            'total_fields_reviewed': 0,
            'total_fields_modified': 0,
            'confidence_lowered_count': 0,
            'values_replaced_count': 0,
            'revision_percentages_by_column': {},
            'qc_models_used': set(),
            'qc_provider_metrics': {}
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
        # Extract cost and token information from response
        usage = qc_response.get('usage', {})
        cost_info = qc_response.get('enhanced_data', {}).get('costs', {})

        # Update totals
        self.qc_metrics['total_qc_calls'] += 1
        self.qc_metrics['total_qc_tokens'] += usage.get('total_tokens', 0)

        # Get actual cost from enhanced data if available
        actual_cost = cost_info.get('actual', {}).get('total_cost', 0.0)
        if actual_cost > 0:
            self.qc_metrics['total_qc_cost'] += actual_cost
        else:
            # Fallback to response cost
            self.qc_metrics['total_qc_cost'] += qc_response.get('cost', 0.0)

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
                'cost': 0.0,
                'models_used': set()
            }

        provider_metrics = self.qc_metrics['qc_provider_metrics'][api_provider]
        provider_metrics['calls'] += 1
        provider_metrics['tokens'] += usage.get('total_tokens', 0)
        provider_metrics['cost'] += actual_cost if actual_cost > 0 else qc_response.get('cost', 0.0)
        provider_metrics['models_used'].add(model_used)

        logger.info(f"QC call tracked: {len(qc_results)} field modifications, "
                   f"${actual_cost:.6f} cost, {usage.get('total_tokens', 0)} tokens")

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