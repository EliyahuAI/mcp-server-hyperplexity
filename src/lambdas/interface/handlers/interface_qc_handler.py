"""
Interface Lambda QC Handler

Handles QC integration for the interface lambda, processing QC results and
integrating them into the validation response pipeline.
"""

import json
import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class InterfaceQCHandler:
    """
    Handles QC data processing for the interface lambda.
    Integrates QC results with validation results for response generation.
    """

    def __init__(self):
        """Initialize the QC handler."""
        self.qc_enabled = True  # Will be set based on config
        logger.info("Interface QC Handler initialized")

    def process_validation_response_with_qc(
        self,
        validation_response: Dict[str, Any],
        config_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process validation response and integrate QC data if present.

        Args:
            validation_response: Response from validation lambda
            config_data: Configuration data

        Returns:
            Enhanced response with QC data integrated
        """
        try:
            # Check if QC is enabled in config
            qc_settings = config_data.get('qc_settings', {})
            self.qc_enabled = qc_settings.get('enable_qc', True)

            if not self.qc_enabled:
                logger.info("QC disabled, returning validation response as-is")
                return validation_response

            # Extract QC data from validation response
            qc_metrics = validation_response.get('qc_metrics', {})
            qc_results = validation_response.get('qc_results', {})

            if not qc_results:
                logger.info("No QC results found in validation response")
                # Still add QC summary indicating no QC data
                enhanced_response = validation_response.copy()
                enhanced_response['qc_summary'] = {
                    'qc_enabled': True,
                    'total_fields_reviewed': 0,
                    'total_fields_modified': 0,
                    'modification_rate': 0.0,
                    'total_qc_cost': 0.0,
                    'qc_models_used': []
                }
                return enhanced_response

            # Process QC data
            enhanced_response = self._integrate_qc_data(validation_response, qc_results, qc_metrics)

            logger.info(f"QC integration complete: {len(qc_results)} rows with QC data")
            return enhanced_response

        except Exception as e:
            logger.error(f"Error processing QC data in interface: {str(e)}")
            # Return original response if QC processing fails
            return validation_response

    def _integrate_qc_data(
        self,
        validation_response: Dict[str, Any],
        qc_results: Dict[str, Any],
        qc_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Integrate QC data into the validation response.

        Args:
            validation_response: Original validation response
            qc_results: QC results by row
            qc_metrics: QC metrics and cost data

        Returns:
            Enhanced response with QC data
        """
        enhanced_response = validation_response.copy()

        # Add QC summary to response
        qc_totals = qc_metrics.get('qc_totals', {})
        enhanced_response['qc_summary'] = {
            'qc_enabled': True,
            'total_fields_reviewed': qc_totals.get('total_fields_reviewed', 0),
            'total_fields_modified': qc_totals.get('total_fields_modified', 0),
            'modification_rate': self._calculate_modification_rate(qc_totals),
            'total_qc_cost': qc_totals.get('total_qc_cost', 0.0),
            'qc_models_used': qc_totals.get('qc_models_used', [])
        }

        # Add QC revision percentages to response
        qc_revision_percentages = qc_metrics.get('qc_revision_percentages', {})
        enhanced_response['qc_revision_percentages'] = qc_revision_percentages

        # Store QC results for Excel generation
        enhanced_response['qc_results'] = qc_results

        # Update cost totals to include QC
        if 'total_cost' in enhanced_response:
            enhanced_response['total_cost'] += qc_totals.get('total_qc_cost', 0.0)

        return enhanced_response

    def _calculate_modification_rate(self, qc_totals: Dict[str, Any]) -> float:
        """Calculate QC modification rate as percentage."""
        total_reviewed = qc_totals.get('total_fields_reviewed', 0)
        total_modified = qc_totals.get('total_fields_modified', 0)

        if total_reviewed == 0:
            return 0.0

        return round((total_modified / total_reviewed) * 100, 2)

    def prepare_qc_excel_data(
        self,
        validation_results: Dict[str, Any],
        qc_results: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Prepare validation and QC data for Excel generation.

        Args:
            validation_results: Validation results by row
            qc_results: QC results by row

        Returns:
            Tuple of (validation_results, formatted_qc_results)
        """
        try:
            # Format QC results for Excel integration
            formatted_qc_results = {}

            for row_key, row_qc_data in qc_results.items():
                formatted_row = {}

                for field_name, field_qc_data in row_qc_data.items():
                    if isinstance(field_qc_data, dict):
                        # Ensure QC data is properly formatted for Excel
                        formatted_field = {
                            'qc_applied': field_qc_data.get('qc_applied', False),
                            'qc_entry': field_qc_data.get('qc_entry', ''),
                            'qc_confidence': field_qc_data.get('qc_confidence', ''),
                            'qc_action_taken': field_qc_data.get('qc_action_taken', 'no_change'),
                            'qc_reasoning': field_qc_data.get('qc_reasoning', ''),
                            'updated_entry': field_qc_data.get('updated_entry', ''),
                            'updated_confidence': field_qc_data.get('updated_confidence', ''),
                            'original_confidence': field_qc_data.get('original_confidence', ''),
                            'all_sources': field_qc_data.get('all_sources', [])
                        }
                        formatted_row[field_name] = formatted_field

                if formatted_row:
                    formatted_qc_results[row_key] = formatted_row

            logger.info(f"Prepared QC Excel data for {len(formatted_qc_results)} rows")
            return validation_results, formatted_qc_results

        except Exception as e:
            logger.error(f"Error preparing QC Excel data: {str(e)}")
            return validation_results, {}

    def create_qc_enhanced_response(
        self,
        validation_response: Dict[str, Any],
        session_id: str,
        config_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create QC-enhanced response for the interface.

        Args:
            validation_response: Response from validation lambda
            session_id: Session ID
            config_data: Configuration data

        Returns:
            QC-enhanced response ready for interface
        """
        try:
            # Process QC data
            enhanced_response = self.process_validation_response_with_qc(
                validation_response, config_data
            )

            # Add session tracking
            enhanced_response['session_id'] = session_id
            enhanced_response['qc_enabled'] = self.qc_enabled

            # Prepare interface-specific data
            if self.qc_enabled and 'qc_results' in enhanced_response:
                qc_results = enhanced_response['qc_results']
                validation_results = enhanced_response.get('validation_results', {})

                # Prepare data for Excel generation
                validation_data, qc_data = self.prepare_qc_excel_data(
                    validation_results, qc_results
                )

                enhanced_response['excel_validation_data'] = validation_data
                enhanced_response['excel_qc_data'] = qc_data

            return enhanced_response

        except Exception as e:
            logger.error(f"Error creating QC-enhanced response: {str(e)}")
            return validation_response

    def get_qc_status_summary(self, enhanced_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get QC status summary for interface display.

        Args:
            enhanced_response: QC-enhanced response

        Returns:
            QC status summary
        """
        if not self.qc_enabled:
            return {
                'qc_enabled': False,
                'message': 'QC is disabled'
            }

        qc_summary = enhanced_response.get('qc_summary', {})
        qc_revision_percentages = enhanced_response.get('qc_revision_percentages', {})

        return {
            'qc_enabled': True,
            'fields_reviewed': qc_summary.get('total_fields_reviewed', 0),
            'fields_modified': qc_summary.get('total_fields_modified', 0),
            'modification_rate': qc_summary.get('modification_rate', 0.0),
            'qc_cost': qc_summary.get('total_qc_cost', 0.0),
            'models_used': qc_summary.get('qc_models_used', []),
            'revision_by_column': qc_revision_percentages
        }


def create_interface_qc_handler() -> InterfaceQCHandler:
    """
    Factory function to create interface QC handler.

    Returns:
        InterfaceQCHandler instance
    """
    return InterfaceQCHandler()


def format_qc_summary_for_display(qc_status: Dict[str, Any]) -> str:
    """
    Format QC status for user display.

    Args:
        qc_status: QC status summary

    Returns:
        Formatted string for display
    """
    if not qc_status.get('qc_enabled', False):
        return "QC: Disabled"

    fields_reviewed = qc_status.get('fields_reviewed', 0)
    fields_modified = qc_status.get('fields_modified', 0)
    modification_rate = qc_status.get('modification_rate', 0.0)
    qc_cost = qc_status.get('qc_cost', 0.0)

    return (f"QC: {fields_reviewed} fields reviewed, {fields_modified} modified "
           f"({modification_rate}%), ${qc_cost:.4f} cost")