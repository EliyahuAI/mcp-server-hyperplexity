"""
Interface QC Excel Integration

Provides QC-enhanced Excel creation that can be used as a drop-in replacement
for the standard Excel creation in the interface lambda.
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
    validated_sheet_name: Optional[str] = None
) -> Optional[io.BytesIO]:
    """
    Create QC-enhanced Excel for interface lambda.
    This is a drop-in replacement for create_enhanced_excel_with_validation
    that includes QC data.

    Args:
        table_data: Table data from parser
        validation_results: Validation results from lambda
        config_data: Configuration data
        session_id: Session ID
        validated_sheet_name: Name of validated sheet

    Returns:
        BytesIO buffer with Excel content, or None if creation failed
    """
    try:
        # Import QC modules
        from interface_qc_handler import create_interface_qc_handler
        from qc_enhanced_excel_report import create_qc_enhanced_excel_with_validation

        # Extract QC data from validation results
        qc_handler = create_interface_qc_handler()

        # Process validation response to extract QC data
        enhanced_response = qc_handler.process_validation_response_with_qc(
            validation_results, config_data
        )

        # Get QC results if available
        qc_results = enhanced_response.get('qc_results', {})

        # Get original Excel file content from table_data
        excel_file_content = None
        if hasattr(table_data, 'get'):
            # If table_data is a dict with file content
            excel_file_content = table_data.get('file_content')
        elif hasattr(table_data, 'file_content'):
            # If table_data has file_content attribute
            excel_file_content = table_data.file_content
        elif isinstance(table_data, bytes):
            # If table_data is the file content directly
            excel_file_content = table_data

        if not excel_file_content:
            logger.error("No Excel file content found in table_data for QC Excel creation")
            return None

        # Create QC-enhanced Excel
        enhanced_excel_content = create_qc_enhanced_excel_with_validation(
            excel_file_content=excel_file_content,
            validation_results=validation_results,
            qc_results=qc_results,
            config_data=config_data,
            session_id=session_id
        )

        if enhanced_excel_content:
            # Return as BytesIO for compatibility
            excel_buffer = io.BytesIO(enhanced_excel_content)
            logger.info(f"Created QC-enhanced Excel for session {session_id}")
            return excel_buffer
        else:
            logger.error("QC-enhanced Excel creation returned None")
            return None

    except Exception as e:
        logger.error(f"Error creating QC-enhanced Excel for interface: {str(e)}")

        # Fallback to standard Excel creation
        try:
            from excel_report_new import create_enhanced_excel_with_validation

            # Get original Excel file content
            excel_file_content = None
            if hasattr(table_data, 'get'):
                excel_file_content = table_data.get('file_content')
            elif hasattr(table_data, 'file_content'):
                excel_file_content = table_data.file_content
            elif isinstance(table_data, bytes):
                excel_file_content = table_data

            if excel_file_content:
                return create_enhanced_excel_with_validation(
                    table_data, validation_results, config_data, session_id, validated_sheet_name
                )
            else:
                logger.error("No Excel file content available for fallback Excel creation")
                return None

        except Exception as fallback_error:
            logger.error(f"Fallback Excel creation also failed: {str(fallback_error)}")
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
        from interface_qc_handler import create_interface_qc_handler

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
    validated_sheet_name: Optional[str] = None
) -> Optional[io.BytesIO]:
    """
    QC-enhanced version of create_enhanced_excel_with_validation.

    This function can be used as a drop-in replacement for the original
    create_enhanced_excel_with_validation function.
    """
    return create_qc_enhanced_excel_for_interface(
        table_data, validation_results, config_data, session_id, validated_sheet_name
    )