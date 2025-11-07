"""
PDF to Markdown Converter

Handles PDF file conversion to markdown using pymupdf4llm.
Designed for lightweight, LLM-optimized conversion.
Follows the Excel upload pattern for multipart form data.
"""

import tempfile
import os
from typing import Dict, Any
import logging

# Use pymupdf4llm for LLM-optimized markdown conversion
try:
    import pymupdf4llm
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logging.warning("pymupdf4llm not installed - PDF conversion will not be available")

from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle_pdf_multipart(files: Dict[str, Any], form_data: Dict[str, str], context: Any) -> Dict[str, Any]:
    """
    Convert PDF file to markdown text (synchronous multipart handler).

    Follows the Excel upload pattern - receives parsed multipart data.

    Args:
        files: Dictionary of uploaded files from multipart parser
        form_data: Dictionary of form fields
        context: Lambda context

    Returns:
        Response dict with:
            - success: True/False
            - markdown_text: Converted markdown content
            - page_count: Number of pages processed
            - filename: Original filename
    """
    try:
        # Check if pymupdf4llm is available
        if not PYMUPDF_AVAILABLE:
            logger.error("[PDF_CONVERT] pymupdf4llm not available")
            return create_response(
                400,
                {
                    'success': False,
                    'error': 'dependency_missing',
                    'message': 'PDF conversion not available - pymupdf4llm not installed'
                }
            )

        # Extract PDF file from files dict
        pdf_file = files.get('pdf_file')

        if not pdf_file:
            logger.error("[PDF_CONVERT] No PDF file in upload")
            return create_response(
                400,
                {
                    'success': False,
                    'error': 'missing_file',
                    'message': 'No PDF file provided'
                }
            )

        # Get filename and content
        filename = pdf_file.get('filename', 'uploaded.pdf')
        pdf_content = pdf_file.get('content', b'')

        if not pdf_content:
            logger.error("[PDF_CONVERT] PDF file has no content")
            return create_response(
                400,
                {
                    'success': False,
                    'error': 'empty_file',
                    'message': 'PDF file is empty'
                }
            )

        logger.info(f"[PDF_CONVERT] Processing file: {filename} ({len(pdf_content)} bytes)")

        # Write to temporary file (required by pymupdf4llm)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            temp_pdf.write(pdf_content)
            temp_pdf_path = temp_pdf.name

        try:
            # Convert PDF to markdown using pymupdf4llm
            logger.info(f"[PDF_CONVERT] Converting PDF to markdown")

            # pymupdf4llm.to_markdown returns markdown text directly
            markdown_text = pymupdf4llm.to_markdown(temp_pdf_path)

            # Get page count for reporting
            doc = fitz.open(temp_pdf_path)
            page_count = len(doc)
            doc.close()

            logger.info(f"[PDF_CONVERT] Successfully converted {page_count} pages to markdown ({len(markdown_text)} chars)")

            # Return markdown text
            return create_response(
                200,
                {
                    'success': True,
                    'markdown_text': markdown_text,
                    'page_count': page_count,
                    'filename': filename,
                    'message': f'Successfully converted {page_count} pages to markdown'
                }
            )

        except Exception as e:
            logger.error(f"[PDF_CONVERT] Conversion failed: {str(e)}", exc_info=True)
            return create_response(
                500,
                {
                    'success': False,
                    'error': 'conversion_failed',
                    'message': f'Failed to convert PDF to markdown: {str(e)}'
                }
            )

        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_pdf_path)
            except Exception as e:
                logger.warning(f"[PDF_CONVERT] Failed to delete temp file: {str(e)}")

    except Exception as e:
        logger.error(f"[PDF_CONVERT] Unexpected error: {str(e)}", exc_info=True)
        return create_response(
            500,
            {
                'success': False,
                'error': 'unexpected_error',
                'message': f'An unexpected error occurred: {str(e)}'
            }
        )
