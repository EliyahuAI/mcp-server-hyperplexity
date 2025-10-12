"""
QC-Enhanced Excel Dual Generator

Generates BOTH full (with Details sheet) and customer (without Details sheet) versions
of enhanced Excel files in a single efficient pass.

This solves the openpyxl/xlsxwriter compatibility issue where loading an xlsxwriter-generated
file with openpyxl and re-saving it causes data corruption.
"""

import io
import logging
from typing import Dict, Any, Optional, Tuple

from qc_enhanced_excel_report import create_qc_enhanced_excel_with_validation

logger = logging.getLogger()


def create_both_excel_versions(
    excel_file_content: bytes,
    validation_results: Dict[str, Any],
    qc_results: Optional[Dict[str, Dict[str, Any]]] = None,
    config_data: Dict[str, Any] = None,
    session_id: str = ""
) -> Tuple[bytes, bytes]:
    """
    Generate BOTH full and customer versions of enhanced Excel by calling the generator twice.

    Strategy: Call create_qc_enhanced_excel_with_validation twice - once with Details sheet,
    once without. Both are generated fresh using xlsxwriter, avoiding the openpyxl corruption
    issue that would occur if we tried to strip the Details sheet post-generation.

    Args:
        excel_file_content: Original Excel file content
        validation_results: Validation results from the validator
        qc_results: QC results merged with validation results
        config_data: Configuration data
        session_id: Session ID for tracking

    Returns:
        Tuple of (full_version_bytes, customer_version_bytes)
        - full_version_bytes: Complete Excel with Results, Details, and Reasons sheets (for S3)
        - customer_version_bytes: Excel with Results and Reasons only (for email/download)
    """
    logger.info(f"[DUAL_EXCEL_GEN] Generating both full and customer versions for session {session_id}")

    try:
        # Generate full version FIRST (with Details sheet) - this is the authoritative version
        logger.info("[DUAL_EXCEL_GEN] Generating full version (with Details sheet)...")
        full_version = create_qc_enhanced_excel_with_validation(
            excel_file_content=excel_file_content,
            validation_results=validation_results,
            qc_results=qc_results,
            config_data=config_data,
            session_id=session_id,
            skip_history=False,
            include_details_sheet=True  # Full version includes Details
        )

        logger.info(f"[DUAL_EXCEL_GEN] Full version generated: {len(full_version):,} bytes")

        # Generate customer version (without Details sheet)
        logger.info("[DUAL_EXCEL_GEN] Generating customer version (no Details sheet)...")
        customer_version = create_qc_enhanced_excel_with_validation(
            excel_file_content=excel_file_content,
            validation_results=validation_results,
            qc_results=qc_results,
            config_data=config_data,
            session_id=session_id,
            skip_history=False,
            include_details_sheet=False  # Customer version excludes Details
        )

        logger.info(f"[DUAL_EXCEL_GEN] Customer version generated: {len(customer_version):,} bytes")
        logger.info(f"[DUAL_EXCEL_GEN] Both versions generated successfully")

        return (full_version, customer_version)

    except Exception as e:
        logger.error(f"[DUAL_EXCEL_GEN] Failed to generate both versions: {e}")
        raise Exception(f"Dual Excel generation failed: {str(e)}") from e
