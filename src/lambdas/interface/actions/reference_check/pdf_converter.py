"""
PDF to Markdown Converter - Async Pattern

Handles PDF file uploads and conversion using the SQS + WebSocket pattern:
1. Lightweight handler: Upload PDF to S3, queue to SQS, return immediately
2. Background processor: Convert PDF to markdown, send via WebSocket
"""

import tempfile
import os
import uuid
from datetime import datetime, timezone
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
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.core.sqs_service import _send_sqs_message, STANDARD_QUEUE_URL
from websocket_client import WebSocketClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Max file size: 10MB
MAX_PDF_SIZE = 10 * 1024 * 1024


def handle_pdf_multipart(files: Dict[str, Any], form_data: Dict[str, str], context: Any) -> Dict[str, Any]:
    """
    Lightweight PDF upload handler (synchronous - returns immediately).

    Uploads PDF to S3, queues conversion to SQS, returns 200.
    Results sent via WebSocket when ready.

    Args:
        files: Dictionary of uploaded files from multipart parser
        form_data: Dictionary of form fields (email, session_id)
        context: Lambda context

    Returns:
        Response dict with success and pdf_id for tracking
    """
    try:
        # Check if pymupdf4llm is available
        if not PYMUPDF_AVAILABLE:
            logger.error("[PDF_UPLOAD] pymupdf4llm not available")
            return create_response(
                400,
                {
                    'success': False,
                    'error': 'dependency_missing',
                    'message': 'PDF conversion not available - pymupdf4llm not installed'
                }
            )

        # Extract required fields
        email = form_data.get('email', '').strip().lower()
        session_id = form_data.get('session_id', '').strip()
        pdf_file = files.get('pdf_file')

        if not email:
            return create_response(400, {
                'success': False,
                'error': 'missing_email',
                'message': 'Email address is required'
            })

        if not session_id:
            return create_response(400, {
                'success': False,
                'error': 'missing_session',
                'message': 'Session ID is required'
            })

        if not pdf_file:
            logger.error("[PDF_UPLOAD] No PDF file in upload")
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
            logger.error("[PDF_UPLOAD] PDF file has no content")
            return create_response(
                400,
                {
                    'success': False,
                    'error': 'empty_file',
                    'message': 'PDF file is empty'
                }
            )

        # Check file size
        file_size = len(pdf_content)
        if file_size > MAX_PDF_SIZE:
            logger.warning(f"[PDF_UPLOAD] File too large: {file_size} bytes")
            return create_response(
                400,
                {
                    'success': False,
                    'error': 'file_too_large',
                    'message': f'PDF file too large. Maximum size is {MAX_PDF_SIZE / 1024 / 1024}MB'
                }
            )

        logger.info(f"[PDF_UPLOAD] Processing file: {filename} ({file_size} bytes) for session {session_id}")

        # Generate PDF ID
        pdf_id = f"pdf_{uuid.uuid4().hex[:12]}"

        # Upload PDF to S3
        storage_manager = UnifiedS3Manager()
        domain = email.split('@')[1] if '@' in email else 'unknown'
        email_prefix = email.split('@')[0] if '@' in email else email

        # Store in session folder
        s3_key = f"results/{domain}/{email_prefix}/{session_id}/pdfs/{pdf_id}_{filename}"

        try:
            storage_manager.s3_client.put_object(
                Bucket=storage_manager.bucket_name,
                Key=s3_key,
                Body=pdf_content,
                ContentType='application/pdf',
                Metadata={
                    'original_filename': filename,
                    'email': email,
                    'session_id': session_id,
                    'pdf_id': pdf_id,
                    'uploaded_at': datetime.now(timezone.utc).isoformat()
                }
            )
            logger.info(f"[PDF_UPLOAD] Uploaded to S3: {s3_key}")
        except Exception as e:
            logger.error(f"[PDF_UPLOAD] S3 upload failed: {str(e)}")
            return create_response(500, {
                'success': False,
                'error': 's3_upload_failed',
                'message': 'Failed to upload PDF to storage'
            })

        # Prepare SQS message for background processing
        conversion_request = {
            'request_type': 'pdf_conversion',
            'action': 'convertPdfToMarkdown',
            'email': email,
            'session_id': session_id,
            'pdf_id': pdf_id,
            's3_key': s3_key,
            'filename': filename,
            'file_size': file_size,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'deployment_environment': os.environ.get('DEPLOYMENT_ENVIRONMENT', 'prod')
        }

        # Send to SQS queue
        try:
            if not STANDARD_QUEUE_URL:
                raise Exception("STANDARD_QUEUE_URL not configured")

            message_id = _send_sqs_message(STANDARD_QUEUE_URL, conversion_request)
            logger.info(f"[PDF_UPLOAD] Queued conversion: {pdf_id}, SQS message: {message_id}")
        except Exception as e:
            logger.error(f"[PDF_UPLOAD] Failed to queue conversion: {str(e)}")
            return create_response(500, {
                'success': False,
                'error': 'queue_failed',
                'message': 'Failed to start PDF conversion. Please try again.'
            })

        # Return immediate success response
        return create_response(200, {
            'success': True,
            'status': 'processing',
            'pdf_id': pdf_id,
            'filename': filename,
            'file_size': file_size,
            'message': f'{filename} uploaded successfully. Converting to markdown...'
        })

    except Exception as e:
        logger.error(f"[PDF_UPLOAD] Unexpected error: {str(e)}", exc_info=True)
        return create_response(
            500,
            {
                'success': False,
                'error': 'unexpected_error',
                'message': f'An unexpected error occurred: {str(e)}'
            }
        )


async def handle_pdf_conversion(request_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Background PDF conversion processor (runs via SQS).

    Converts PDF to markdown and sends result via WebSocket.

    Args:
        request_data: SQS message payload with s3_key, session_id, etc.
        context: Lambda context

    Returns:
        Result dict with status
    """
    try:
        # Extract fields
        email = request_data['email']
        session_id = request_data['session_id']
        pdf_id = request_data['pdf_id']
        s3_key = request_data['s3_key']
        filename = request_data['filename']

        logger.info(f"[PDF_CONVERT] Starting conversion for {pdf_id}: {filename}")

        # Initialize WebSocket client
        websocket_client = WebSocketClient()

        # Send progress update
        websocket_client.send_to_session(session_id, {
            'type': 'pdf_conversion_progress',
            'pdf_id': pdf_id,
            'status': 'converting',
            'message': f'Reading {filename}...'
        })

        # Download PDF from S3
        storage_manager = UnifiedS3Manager()
        try:
            response = storage_manager.s3_client.get_object(
                Bucket=storage_manager.bucket_name,
                Key=s3_key
            )
            pdf_content = response['Body'].read()
            logger.info(f"[PDF_CONVERT] Downloaded from S3: {len(pdf_content)} bytes")
        except Exception as e:
            logger.error(f"[PDF_CONVERT] S3 download failed: {str(e)}")
            websocket_client.send_to_session(session_id, {
                'type': 'pdf_conversion_error',
                'pdf_id': pdf_id,
                'error': 'download_failed',
                'message': 'Failed to download PDF from storage'
            })
            return {'status': 'error', 'error': 'download_failed'}

        # Write to temporary file (required by pymupdf4llm)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            temp_pdf.write(pdf_content)
            temp_pdf_path = temp_pdf.name

        try:
            # Convert PDF to markdown using pymupdf4llm
            logger.info(f"[PDF_CONVERT] Converting {filename} to markdown")

            markdown_text = pymupdf4llm.to_markdown(temp_pdf_path)

            # Get page count
            doc = fitz.open(temp_pdf_path)
            page_count = len(doc)
            doc.close()

            logger.info(f"[PDF_CONVERT] Successfully converted {page_count} pages ({len(markdown_text)} chars)")

            # Send success via WebSocket
            websocket_client.send_to_session(session_id, {
                'type': 'pdf_conversion_complete',
                'pdf_id': pdf_id,
                'status': 'complete',
                'filename': filename,
                'page_count': page_count,
                'markdown_text': markdown_text,
                'message': f'Successfully converted {page_count} pages'
            })

            return {'status': 'success', 'pdf_id': pdf_id, 'page_count': page_count}

        except Exception as e:
            logger.error(f"[PDF_CONVERT] Conversion failed: {str(e)}", exc_info=True)
            websocket_client.send_to_session(session_id, {
                'type': 'pdf_conversion_error',
                'pdf_id': pdf_id,
                'error': 'conversion_failed',
                'message': f'Failed to convert PDF: {str(e)}'
            })
            return {'status': 'error', 'error': 'conversion_failed'}

        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_pdf_path)
            except Exception as e:
                logger.warning(f"[PDF_CONVERT] Failed to delete temp file: {str(e)}")

    except Exception as e:
        logger.error(f"[PDF_CONVERT] Unexpected error: {str(e)}", exc_info=True)
        try:
            websocket_client.send_to_session(request_data.get('session_id', ''), {
                'type': 'pdf_conversion_error',
                'pdf_id': request_data.get('pdf_id', ''),
                'error': 'unexpected_error',
                'message': f'An unexpected error occurred: {str(e)}'
            })
        except:
            pass
        return {'status': 'error', 'error': 'unexpected_error'}
