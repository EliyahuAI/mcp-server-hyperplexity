"""
QC Excel Formatter

Extensions to Excel reporting functionality to handle QC results.
This module provides functions to format QC results for Excel output.
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

def get_qc_enhanced_detail_headers(id_fields: List[str]) -> List[str]:
    """
    Get enhanced detail headers that include QC columns.

    Args:
        id_fields: List of ID field names

    Returns:
        List of header names for the Details sheet with QC support
    """
    headers = ["Row Key", "Identifier"]

    # Add ID field columns
    headers.extend(id_fields)

    # Add enhanced columns with QC support
    headers.extend([
        "Column",
        "Original Value",
        "Updated Value",
        "QC Value",
        "QC Applied",
        "QC Action",
        "QC Reasoning",
        "Final Confidence",
        "Original Confidence",
        "Quote",
        "Sources",
        "Explanation",
        "Update Required",
        "Substantially Different",
        "Consistent with Model",
        "Model",
        "Timestamp",
        "New"
    ])

    return headers

def format_qc_result_for_excel(
    merged_qc_result: Dict[str, Any],
    field_name: str,
    original_value: str = ""
) -> Dict[str, Any]:
    """
    Format a merged QC result for Excel output.

    Args:
        merged_qc_result: Merged result from QC module
        field_name: Name of the field
        original_value: Original value from the data

    Returns:
        Dictionary with formatted values for Excel columns
    """
    # Determine final values based on QC application
    qc_applied = merged_qc_result.get('qc_applied', False)

    if qc_applied:
        final_value = merged_qc_result.get('qc_entry', '')
        final_confidence = merged_qc_result.get('qc_confidence', '')
        sources = merged_qc_result.get('all_sources', [])
    else:
        final_value = merged_qc_result.get('updated_entry', '')
        final_confidence = merged_qc_result.get('updated_confidence', '')
        sources = merged_qc_result.get('updated_sources', [])

    return {
        'column': field_name,
        'original_value': original_value,
        'updated_value': merged_qc_result.get('updated_entry', ''),
        'qc_value': merged_qc_result.get('qc_entry', ''),
        'qc_applied': 'Yes' if qc_applied else 'No',
        'qc_action': 'Comprehensive QC',  # Since all fields now get full QC
        'qc_reasoning': merged_qc_result.get('qc_reasoning', ''),
        'final_confidence': final_confidence,
        'original_confidence': merged_qc_result.get('original_confidence', ''),
        'quote': merged_qc_result.get('updated_reasoning', ''),
        'sources': ', '.join(sources) if sources else '',
        'explanation': merged_qc_result.get('updated_reasoning', ''),
        'update_required': 'Yes' if merged_qc_result.get('updated_entry', '') != original_value else 'No',
        'substantially_different': 'Yes' if qc_applied else 'No',
        'consistent_with_model': 'Yes',  # Placeholder
        'final_value_for_results_sheet': final_value
    }

def get_qc_enhanced_column_widths() -> List[int]:
    """
    Get column widths for QC-enhanced Details sheet.

    Returns:
        List of column widths
    """
    return [
        15,  # Row Key
        30,  # Identifier
        # ID fields would be inserted here (20 each)
        25,  # Column
        30,  # Original Value
        30,  # Updated Value
        30,  # QC Value
        12,  # QC Applied
        20,  # QC Action
        50,  # QC Reasoning
        15,  # Final Confidence
        15,  # Original Confidence
        50,  # Quote
        40,  # Sources
        60,  # Explanation
        15,  # Update Required
        20,  # Substantially Different
        25,  # Consistent with Model
        25,  # Model
        20,  # Timestamp
        10   # New
    ]

def determine_cell_format(qc_applied: bool, is_results_sheet: bool = False):
    """
    Determine the cell format based on QC application.

    Args:
        qc_applied: Whether QC was applied to this field
        is_results_sheet: Whether this is for the Results sheet

    Returns:
        Format specification for the cell
    """
    if is_results_sheet and qc_applied:
        # QC-applied cells should be in italics in Results/Original/Updated sheets
        return {'italic': True}

    return {}

def write_qc_enhanced_detail_row(
    worksheet: Any,
    row_num: int,
    row_key: str,
    identifier: str,
    id_field_values: List[str],
    formatted_result: Dict[str, Any],
    model_name: str,
    timestamp: str,
    formats: Dict[str, Any]
):
    """
    Write a QC-enhanced detail row to the worksheet.

    Args:
        worksheet: xlsxwriter worksheet object
        row_num: Row number to write to
        row_key: Row key identifier
        identifier: Row identifier string
        id_field_values: Values for ID fields
        formatted_result: Formatted QC result dictionary
        model_name: Name of the model used
        timestamp: Timestamp string
        formats: Dictionary of xlsxwriter formats
    """
    col_idx = 0

    # Row Key and Identifier
    worksheet.write(row_num, col_idx, row_key)
    col_idx += 1
    worksheet.write(row_num, col_idx, identifier)
    col_idx += 1

    # ID field values
    for id_value in id_field_values:
        worksheet.write(row_num, col_idx, str(id_value))
        col_idx += 1

    # QC-enhanced columns
    qc_applied = formatted_result.get('qc_applied', 'No') == 'Yes'
    cell_format = formats.get('italic_format') if qc_applied else None

    worksheet.write(row_num, col_idx, formatted_result.get('column', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('original_value', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('updated_value', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('qc_value', ''), cell_format)
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('qc_applied', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('qc_action', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('qc_reasoning', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('final_confidence', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('original_confidence', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('quote', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('sources', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('explanation', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('update_required', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('substantially_different', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, formatted_result.get('consistent_with_model', ''))
    col_idx += 1
    worksheet.write(row_num, col_idx, model_name)
    col_idx += 1
    worksheet.write(row_num, col_idx, timestamp)
    col_idx += 1
    worksheet.write(row_num, col_idx, 'Yes')  # New

def create_qc_formats(workbook: Any) -> Dict[str, Any]:
    """
    Create xlsxwriter formats for QC-enhanced sheets.

    Args:
        workbook: xlsxwriter workbook object

    Returns:
        Dictionary of format objects
    """
    return {
        'header_format': workbook.add_format({
            'bold': True, 'text_wrap': True, 'valign': 'top',
            'fg_color': '#4472C4', 'font_color': 'white', 'border': 1
        }),
        'italic_format': workbook.add_format({
            'italic': True
        }),
        'qc_applied_format': workbook.add_format({
            'italic': True,
            'fg_color': '#E6F3FF'  # Light blue background for QC-applied cells
        })
    }