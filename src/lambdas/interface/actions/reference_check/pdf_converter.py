"""
PDF to Markdown Converter - Async Pattern

Handles PDF file uploads and conversion using the SQS + WebSocket pattern:
1. Lightweight handler: Upload PDF to S3, queue to SQS, return immediately
2. Background processor: Convert PDF to markdown, send via WebSocket
"""

import tempfile
import os
import uuid
import json
from datetime import datetime, timezone
from typing import Dict, Any
from pathlib import Path
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

# Max file size: 6MB (to account for multipart encoding overhead)
# API Gateway has 10MB total payload limit; 6MB PDF + encoding = ~8MB
MAX_PDF_SIZE = 6 * 1024 * 1024


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

        # Generate session ID if not provided or is 'null' string (same as text submission)
        if not session_id or session_id == 'null':
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            random_hex = uuid.uuid4().hex[:8]
            session_id = f"session_{timestamp}_{random_hex}"
            logger.info(f"[PDF_UPLOAD] Generated new session ID: {session_id}")

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

        # Upload PDF to S3 (results folder for easy access with results)
        storage_manager = UnifiedS3Manager()
        domain = email.split('@')[1] if '@' in email else 'unknown'
        email_prefix = email.split('@')[0] if '@' in email else email

        # Store original PDF in results folder (not pdfs subfolder)
        pdf_s3_key = f"results/{domain}/{email_prefix}/{session_id}/{pdf_id}_{filename}"

        try:
            storage_manager.s3_client.put_object(
                Bucket=storage_manager.bucket_name,
                Key=pdf_s3_key,
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
            logger.info(f"[PDF_UPLOAD] Uploaded PDF to S3: {pdf_s3_key}")
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
            's3_key': pdf_s3_key,
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
            'session_id': session_id,
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

        # Send initial progress update
        websocket_client.send_to_session(session_id, {
            'type': 'pdf_conversion_progress',
            'pdf_id': pdf_id,
            'status': 'downloading',
            'progress': 5,
            'message': f'Downloading {filename}...'
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
            # Get page count first to show in progress message
            doc = fitz.open(temp_pdf_path)
            page_count = len(doc)
            doc.close()

            # Send conversion start progress
            websocket_client.send_to_session(session_id, {
                'type': 'pdf_conversion_progress',
                'pdf_id': pdf_id,
                'status': 'converting',
                'progress': 10,
                'message': f'Converting {page_count} pages to text...'
            })

            # Convert PDF to plain text using PyMuPDF (fast - 20x faster than pymupdf4llm)
            # For reference checking, we don't need fancy markdown formatting
            logger.info(f"[PDF_CONVERT] Converting {filename} to text ({page_count} pages)")

            doc = fitz.open(temp_pdf_path)
            markdown_text = ''
            for page in doc:
                markdown_text += page.get_text()
            doc.close()

            logger.info(f"[PDF_CONVERT] Successfully converted {page_count} pages ({len(markdown_text)} chars)")

            # Send conversion complete progress
            websocket_client.send_to_session(session_id, {
                'type': 'pdf_conversion_progress',
                'pdf_id': pdf_id,
                'status': 'validating',
                'progress': 15,
                'message': f'Conversion complete. Validating text size...'
            })

            # Load config for text limits
            config_path = Path(__file__).parent / 'reference_check_config.json'
            with open(config_path, 'r') as f:
                config = json.load(f)

            # Validate markdown size using config limits
            max_tokens = config['text_limits']['max_tokens']
            tokens_per_word = config['text_limits']['tokens_per_word']

            # Calculate max words from tokens (3 words = 4 tokens)
            max_words = int(max_tokens / tokens_per_word)

            word_count = len(markdown_text.split())
            estimated_tokens = int(word_count * tokens_per_word)

            if estimated_tokens > max_tokens:
                logger.warning(f"[PDF_CONVERT] Markdown too large: {word_count} words, ~{estimated_tokens} tokens (max: {max_tokens} tokens)")
                websocket_client.send_to_session(session_id, {
                    'type': 'pdf_conversion_error',
                    'pdf_id': pdf_id,
                    'error': 'file_too_large',
                    'message': f'PDF converted to ~{estimated_tokens} tokens (max {max_tokens}). Please use a smaller PDF.'
                })
                return {'status': 'error', 'error': 'file_too_large', 'estimated_tokens': estimated_tokens}

            logger.info(f"[PDF_CONVERT] Size validation passed: {word_count} words, ~{estimated_tokens} tokens (max {max_tokens})")

            # Save markdown to S3 (results folder, not pdfs subfolder)
            domain = email.split('@')[1] if '@' in email else 'unknown'
            email_prefix = email.split('@')[0] if '@' in email else email
            markdown_filename = f"{pdf_id}_markdown.txt"
            markdown_s3_key = f"results/{domain}/{email_prefix}/{session_id}/{markdown_filename}"

            try:
                storage_manager.s3_client.put_object(
                    Bucket=storage_manager.bucket_name,
                    Key=markdown_s3_key,
                    Body=markdown_text.encode('utf-8'),
                    ContentType='text/plain; charset=utf-8',
                    Metadata={
                        'original_pdf': filename,
                        'pdf_id': pdf_id,
                        'page_count': str(page_count),
                        'converted_at': datetime.now(timezone.utc).isoformat()
                    }
                )
                logger.info(f"[PDF_CONVERT] Saved markdown to S3: {markdown_s3_key}")
            except Exception as e:
                logger.error(f"[PDF_CONVERT] Failed to save markdown to S3: {str(e)}")
                websocket_client.send_to_session(session_id, {
                    'type': 'pdf_conversion_error',
                    'pdf_id': pdf_id,
                    'error': 's3_save_failed',
                    'message': 'Failed to save converted markdown'
                })
                return {'status': 'error', 'error': 's3_save_failed'}

            # Automatically start reference check with the markdown text
            logger.info(f"[PDF_CONVERT] Starting reference check with converted markdown")

            # Generate conversation ID for reference check
            conversation_id = f"refcheck_{uuid.uuid4().hex[:12]}"

            # Queue reference check to SQS
            from interface_lambda.core.sqs_service import _send_sqs_message, STANDARD_QUEUE_URL

            reference_check_request = {
                'request_type': 'reference_check',
                'action': 'startReferenceCheck',
                'email': email,
                'session_id': session_id,
                'conversation_id': conversation_id,
                'submitted_text': markdown_text,
                'pdf_source': {
                    'pdf_id': pdf_id,
                    'filename': filename,
                    'page_count': page_count
                },
                'created_at': datetime.now(timezone.utc).isoformat(),
                'deployment_environment': os.environ.get('DEPLOYMENT_ENVIRONMENT', 'prod')
            }

            try:
                message_id = _send_sqs_message(STANDARD_QUEUE_URL, reference_check_request)
                logger.info(f"[PDF_CONVERT] Queued reference check: {conversation_id}, SQS message: {message_id}")

                # Send completion notification via WebSocket
                websocket_client.send_to_session(session_id, {
                    'type': 'pdf_conversion_complete',
                    'pdf_id': pdf_id,
                    'status': 'complete',
                    'filename': filename,
                    'page_count': page_count,
                    'conversation_id': conversation_id,
                    'message': f'Successfully converted {page_count} pages. Starting reference check...'
                })

                return {'status': 'success', 'pdf_id': pdf_id, 'page_count': page_count, 'conversation_id': conversation_id}

            except Exception as e:
                logger.error(f"[PDF_CONVERT] Failed to queue reference check: {str(e)}")
                websocket_client.send_to_session(session_id, {
                    'type': 'pdf_conversion_error',
                    'pdf_id': pdf_id,
                    'error': 'reference_check_failed',
                    'message': 'PDF converted but failed to start reference check'
                })
                return {'status': 'error', 'error': 'reference_check_failed'}

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


def fetch_pdf_markdown(request_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Fetch converted markdown from S3 (synchronous handler).

    Args:
        request_data: Request with markdown_s3_key

    Returns:
        Response dict with markdown_text
    """
    try:
        markdown_s3_key = request_data.get('markdown_s3_key')

        if not markdown_s3_key:
            return create_response(400, {
                'success': False,
                'error': 'missing_key',
                'message': 'markdown_s3_key is required'
            })

        logger.info(f"[PDF_FETCH] Fetching markdown from S3: {markdown_s3_key}")

        # Download markdown from S3
        storage_manager = UnifiedS3Manager()
        try:
            response = storage_manager.s3_client.get_object(
                Bucket=storage_manager.bucket_name,
                Key=markdown_s3_key
            )
            markdown_text = response['Body'].read().decode('utf-8')
            logger.info(f"[PDF_FETCH] Retrieved markdown ({len(markdown_text)} chars)")

            return create_response(200, {
                'success': True,
                'markdown_text': markdown_text
            })

        except Exception as e:
            logger.error(f"[PDF_FETCH] S3 download failed: {str(e)}")
            return create_response(500, {
                'success': False,
                'error': 'download_failed',
                'message': 'Failed to download markdown from storage'
            })

    except Exception as e:
        logger.error(f"[PDF_FETCH] Unexpected error: {str(e)}", exc_info=True)
        return create_response(500, {
            'success': False,
            'error': 'unexpected_error',
            'message': f'An unexpected error occurred: {str(e)}'
        })


def extract_text_from_s3(s3_key: str) -> str:
    """
    Download a file from S3 and extract its plain text content.

    Supports:
    - PDF  (.pdf)  — uses PyMuPDF (fitz) page-by-page text extraction
    - ODF  (.odf, .odt) — ODF is a ZIP; extract content.xml and strip XML tags

    Args:
        s3_key: S3 key of the uploaded file (in the main storage bucket).

    Returns:
        Extracted plain text as a string.

    Raises:
        ValueError: If the file type is unsupported.
        Exception:  On download or extraction failures.
    """
    import io
    import re as _re
    import zipfile

    storage_manager = UnifiedS3Manager()
    logger.info(f"[EXTRACT_TEXT] Downloading {s3_key}")

    response = storage_manager.s3_client.get_object(
        Bucket=storage_manager.bucket_name,
        Key=s3_key,
    )
    file_bytes = response["Body"].read()
    key_lower = s3_key.lower()

    if key_lower.endswith(".pdf"):
        # PDF extraction via PyMuPDF
        if not PYMUPDF_AVAILABLE:
            raise RuntimeError("PyMuPDF (fitz) is not installed — cannot extract PDF text")
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc]
        text = "\n\n".join(pages)
        logger.info(f"[EXTRACT_TEXT] Extracted {len(text)} chars from PDF ({len(pages)} pages)")
        return text

    if key_lower.endswith(".odf") or key_lower.endswith(".odt"):
        # ODF/ODT is a ZIP archive containing content.xml
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                with zf.open("content.xml") as xml_file:
                    xml_content = xml_file.read().decode("utf-8", errors="replace")
        except KeyError:
            raise ValueError("content.xml not found inside ODF/ODT archive")

        # Strip XML tags and decode XML entities
        text = _re.sub(r"<[^>]+>", " ", xml_content)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&apos;", "'")
        # Collapse whitespace
        text = " ".join(text.split())
        logger.info(f"[EXTRACT_TEXT] Extracted {len(text)} chars from ODF/ODT")
        return text

    raise ValueError(f"Unsupported file type for text extraction: {s3_key}")
