"""
Interface QC Excel Integration

Provides QC-enhanced Excel creation that can be used as a drop-in replacement
for the standard Excel creation in the interface lambda.

This module simply imports the working function from excel_report_qc_unified.py
"""

import io
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger()

def create_qc_enhanced_excel_for_interface(
    table_data: Any,
    validation_results: Dict[str, Any],
    config_data: Dict[str, Any],
    session_id: str,
    validated_sheet_name: Optional[str] = None,
    config_s3_key: Optional[str] = None,
    run_key: Optional[str] = None
) -> Optional[io.BytesIO]:
    """
    Create QC-enhanced Excel for interface lambda with Details sheet stripping.

    This wraps the working function from excel_report_qc_unified.py and adds
    Details sheet stripping for customer-facing downloads.

    Args:
        table_data: Table data from parser
        validation_results: Validation results from lambda (full response with body)
        config_data: Configuration data
        session_id: Session ID
        validated_sheet_name: Name of validated sheet
        config_s3_key: Optional S3 key for config
        run_key: DynamoDB run key (e.g., #Preview_34t345345346346)

    Returns:
        BytesIO buffer with customer version (no Details sheet),
        with .full_version and .customer_version attributes
    """
    try:
        # Import the WORKING function from excel_report_qc_unified.py
        from excel_report_qc_unified import create_qc_enhanced_excel_for_interface as create_qc_excel_unified

        # Create the full Excel (with Details sheet) using the working function
        full_excel_buffer = create_qc_excel_unified(
            table_data=table_data,
            validation_results=validation_results,
            config_data=config_data,
            session_id=session_id,
            validated_sheet_name=validated_sheet_name,
            config_s3_key=config_s3_key,
            run_key=run_key
        )

        if not full_excel_buffer:
            logger.error("QC-enhanced Excel creation returned None")
            return None

        full_excel_content = full_excel_buffer.getvalue()
        logger.info(f"[INTERFACE_QC] Full Excel generated: {len(full_excel_content):,} bytes (with Details sheet)")

        # Strip Details sheet for customer version
        from qc_enhanced_excel_report import strip_details_sheet_for_customer
        customer_excel_content = strip_details_sheet_for_customer(full_excel_content)
        logger.info(f"[INTERFACE_QC] Customer Excel created: {len(customer_excel_content):,} bytes (no Details sheet)")

        # Return BytesIO with BOTH versions as attributes
        # - customer version in buffer (for backward compatibility with .getvalue())
        # - full version as .full_version attribute (for S3 storage)
        # - customer version as .customer_version attribute (for downloads/email)
        excel_buffer = io.BytesIO(customer_excel_content)
        excel_buffer.full_version = full_excel_content
        excel_buffer.customer_version = customer_excel_content
        logger.info(f"[INTERFACE_QC] Created dual-version Excel for session {session_id}")
        return excel_buffer

    except Exception as e:
        logger.error(f"Error creating QC-enhanced Excel with details stripping: {str(e)}", exc_info=True)
        return None

def get_qc_summary_for_interface(validation_results: Dict[str, Any], config_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get QC summary for interface display.

    Args:
        validation_results: Validation results
        config_data: Configuration data

    Returns:
        QC summary for interface
    """
    try:
        from ..handlers.interface_qc_handler import create_interface_qc_handler

        qc_handler = create_interface_qc_handler()
        enhanced_response = qc_handler.process_validation_response_with_qc(
            validation_results, config_data
        )

        return qc_handler.get_qc_status_summary(enhanced_response)

    except Exception as e:
        logger.error(f"Error getting QC summary for interface: {str(e)}")
        return {
            'qc_enabled': False,
            'error': str(e)
        }

def format_qc_status_message(validation_results: Dict[str, Any], config_data: Dict[str, Any]) -> str:
    """
    Format QC status message for user display.

    Args:
        validation_results: Validation results
        config_data: Configuration data

    Returns:
        Formatted QC status message
    """
    try:
        qc_summary = get_qc_summary_for_interface(validation_results, config_data)

        if not qc_summary.get('qc_enabled', False):
            return "QC: Disabled"

        fields_reviewed = qc_summary.get('fields_reviewed', 0)
        fields_modified = qc_summary.get('fields_modified', 0)
        modification_rate = qc_summary.get('modification_rate', 0.0)
        qc_cost = qc_summary.get('qc_cost', 0.0)

        return (f"QC: {fields_reviewed} fields reviewed, {fields_modified} modified "
               f"({modification_rate}%), ${qc_cost:.4f} cost")

    except Exception as e:
        logger.error(f"Error formatting QC status message: {str(e)}")
        return "QC: Status unavailable"

# For backward compatibility, provide the same function name as the original
def create_enhanced_excel_with_validation_qc(
    table_data: Any,
    validation_results: Dict[str, Any],
    config_data: Dict[str, Any],
    session_id: str,
    validated_sheet_name: Optional[str] = None,
    config_s3_key: Optional[str] = None
) -> Optional[io.BytesIO]:
    """
    QC-enhanced version of create_enhanced_excel_with_validation.

    This function can be used as a drop-in replacement for the original
    create_enhanced_excel_with_validation function.
    """
    return create_qc_enhanced_excel_for_interface(
        table_data, validation_results, config_data, session_id, validated_sheet_name, config_s3_key
    )