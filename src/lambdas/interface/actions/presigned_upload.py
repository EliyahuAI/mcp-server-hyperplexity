"""
Unified Presigned URL Upload Handler

Provides S3 presigned URLs for direct browser-to-S3 uploads, bypassing API Gateway
and Lambda payload limits. Supports both PDF and Excel file uploads.

Flow:
1. Frontend requests presigned URL (small JSON request, no file)
2. Lambda generates presigned URL for S3 upload
3. Frontend uploads file directly to S3 using presigned URL
4. Frontend notifies backend that upload is complete
5. Backend queues processing to SQS (PDF conversion or Excel processing)

Advantages:
- No API Gateway 10MB limit
- No Lambda 6MB payload limit
- Faster uploads (direct to S3)
- Lower Lambda costs (no payload processing)
"""

import uuid
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any

from interface_lambda.utils.helpers import create_response
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.core.sqs_service import _send_sqs_message, STANDARD_QUEUE_URL

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File type configurations
FILE_CONFIGS = {
    'pdf': {
        'max_size': 50 * 1024 * 1024,  # 50 MB for PDFs (no longer limited by API Gateway)
        'allowed_extensions': ['.pdf'],
        'error_message': 'Invalid PDF file'
    },
    'excel': {
        'max_size': 50 * 1024 * 1024,  # 50 MB for Excel files
        'allowed_extensions': ['.xlsx', '.xls'],
        'error_message': 'Invalid Excel file'
    }
}

# Content type mappings by file extension
CONTENT_TYPE_MAP = {
    '.pdf': 'application/pdf',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls': 'application/vnd.ms-excel'
}

def get_content_type(filename: str) -> str:
    """Get the correct MIME type based on file extension."""
    file_ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
    return CONTENT_TYPE_MAP.get(file_ext, 'application/octet-stream')


def request_presigned_url(request_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Generate a presigned URL for direct S3 upload.

    Request body:
        {
            "file_type": "pdf" or "excel",
            "filename": "document.pdf",
            "file_size": 5242880,
            "email": "user@example.com",
            "session_id": "session_20251112_123456_abc123"  (optional)
        }

    Response:
        {
            "success": true,
            "presigned_url": "https://s3.amazonaws.com/...",
            "upload_id": "upload_abc123...",
            "s3_key": "results/example.com/user/session_123/upload_abc_document.pdf",
            "session_id": "session_20251112_123456_abc123",
            "expires_in": 300
        }
    """
    try:
        # Extract and validate required fields
        file_type = request_data.get('file_type', '').lower()
        filename = request_data.get('filename', '')
        file_size = request_data.get('file_size', 0)
        email = request_data.get('email', '').strip().lower()
        session_id = request_data.get('session_id', '').strip()

        if not file_type or file_type not in FILE_CONFIGS:
            return create_response(400, {
                'success': False,
                'error': 'invalid_file_type',
                'message': f'file_type must be one of: {", ".join(FILE_CONFIGS.keys())}'
            })

        if not filename:
            return create_response(400, {
                'success': False,
                'error': 'missing_filename',
                'message': 'filename is required'
            })

        if not email:
            return create_response(400, {
                'success': False,
                'error': 'missing_email',
                'message': 'email is required'
            })

        # Validate file extension
        config = FILE_CONFIGS[file_type]
        file_ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        if file_ext not in config['allowed_extensions']:
            return create_response(400, {
                'success': False,
                'error': 'invalid_extension',
                'message': f'{config["error_message"]}. Allowed extensions: {", ".join(config["allowed_extensions"])}'
            })

        # Validate file size
        if file_size <= 0 or file_size > config['max_size']:
            max_mb = config['max_size'] / 1024 / 1024
            return create_response(400, {
                'success': False,
                'error': 'invalid_file_size',
                'message': f'File size must be between 1 byte and {max_mb}MB'
            })

        # Generate session ID if not provided
        if not session_id or session_id == 'null':
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            random_hex = uuid.uuid4().hex[:8]
            session_id = f"session_{timestamp}_{random_hex}"
            logger.info(f"[PRESIGNED_URL] Generated new session ID: {session_id}")

        # Generate upload ID
        upload_id = f"upload_{uuid.uuid4().hex[:12]}"

        # Construct S3 key
        storage_manager = UnifiedS3Manager()
        domain = email.split('@')[1] if '@' in email else 'unknown'
        email_prefix = email.split('@')[0] if '@' in email else email

        # Sanitize filename
        safe_filename = filename.replace(' ', '_').replace('/', '_')
        s3_key = f"results/{domain}/{email_prefix}/{session_id}/{upload_id}_{safe_filename}"

        # Get correct content type for file extension
        content_type = get_content_type(filename)

        # Generate presigned URL for PUT operation
        presigned_url = storage_manager.s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': storage_manager.bucket_name,
                'Key': s3_key,
                'ContentType': content_type,
                'Metadata': {
                    'upload_id': upload_id,
                    'original_filename': filename,
                    'email': email,
                    'session_id': session_id,
                    'file_type': file_type,
                    'file_size': str(file_size),
                    'uploaded_at': datetime.now(timezone.utc).isoformat()
                }
            },
            ExpiresIn=300  # 5 minutes
        )

        logger.info(f"[PRESIGNED_URL] Generated URL for {file_type}: {upload_id}, session: {session_id}, content_type: {content_type}")

        return create_response(200, {
            'success': True,
            'presigned_url': presigned_url,
            'upload_id': upload_id,
            's3_key': s3_key,
            'session_id': session_id,
            'file_type': file_type,
            'content_type': content_type,  # Return to frontend so it knows what header to use
            'expires_in': 300
        })

    except Exception as e:
        logger.error(f"[PRESIGNED_URL] Error generating presigned URL: {str(e)}", exc_info=True)
        return create_response(500, {
            'success': False,
            'error': 'server_error',
            'message': f'Failed to generate upload URL: {str(e)}'
        })


def confirm_upload_complete(request_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Confirm that file was uploaded to S3 and queue processing.

    Request body:
        {
            "upload_id": "upload_abc123...",
            "s3_key": "results/example.com/user/session_123/upload_abc_document.pdf",
            "session_id": "session_20251112_123456_abc123",
            "file_type": "pdf" or "excel",
            "email": "user@example.com"
        }

    Response:
        {
            "success": true,
            "status": "processing",
            "message": "File uploaded successfully. Processing started."
        }
    """
    try:
        # Extract required fields
        upload_id = request_data.get('upload_id', '')
        s3_key = request_data.get('s3_key', '')
        session_id = request_data.get('session_id', '')
        file_type = request_data.get('file_type', '').lower()
        email = request_data.get('email', '').strip().lower()

        if not all([upload_id, s3_key, session_id, file_type, email]):
            return create_response(400, {
                'success': False,
                'error': 'missing_fields',
                'message': 'upload_id, s3_key, session_id, file_type, and email are required'
            })

        if file_type not in FILE_CONFIGS:
            return create_response(400, {
                'success': False,
                'error': 'invalid_file_type',
                'message': f'file_type must be one of: {", ".join(FILE_CONFIGS.keys())}'
            })

        # Verify file exists in S3
        storage_manager = UnifiedS3Manager()
        try:
            response = storage_manager.s3_client.head_object(
                Bucket=storage_manager.bucket_name,
                Key=s3_key
            )
            file_size = response['ContentLength']
            logger.info(f"[UPLOAD_CONFIRM] Verified file in S3: {s3_key} ({file_size} bytes)")
        except Exception as e:
            logger.error(f"[UPLOAD_CONFIRM] File not found in S3: {s3_key}")
            return create_response(400, {
                'success': False,
                'error': 'file_not_found',
                'message': 'File was not successfully uploaded to S3'
            })

        # Extract original filename from request
        filename = request_data.get('filename', s3_key.split('/')[-1])

        # Queue processing based on file type
        if file_type == 'pdf':
            # Queue PDF conversion (compatible with pdf_converter.handle_pdf_conversion)
            conversion_request = {
                'request_type': 'pdf_conversion',
                'action': 'convertPdfToMarkdown',
                'email': email,
                'session_id': session_id,
                'pdf_id': upload_id,  # pdf_converter expects 'pdf_id'
                's3_key': s3_key,
                'filename': filename,  # Original filename for display
                'file_size': file_size,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'deployment_environment': os.environ.get('DEPLOYMENT_ENVIRONMENT', 'prod')
            }

            if not STANDARD_QUEUE_URL:
                raise Exception("STANDARD_QUEUE_URL not configured")

            message_id = _send_sqs_message(STANDARD_QUEUE_URL, conversion_request)
            logger.info(f"[UPLOAD_CONFIRM] Queued PDF conversion: {upload_id}, SQS: {message_id}")

            return create_response(200, {
                'success': True,
                'status': 'processing',
                'upload_id': upload_id,
                'session_id': session_id,
                'message': 'PDF uploaded successfully. Converting to text...'
            })

        elif file_type == 'excel':
            # For Excel files, analyze table structure and find matching configs
            logger.info(f"[UPLOAD_CONFIRM] Excel file uploaded: {upload_id}, analyzing structure...")

            try:
                # Import Excel analysis functions
                from interface_lambda.actions.process_excel_unified import _find_matching_configs

                # Download and analyze Excel file from S3
                response = storage_manager.s3_client.get_object(
                    Bucket=storage_manager.bucket_name,
                    Key=s3_key
                )
                excel_content = response['Body'].read()

                # Find matching configs based on Excel structure
                try:
                    matching_configs = _find_matching_configs(excel_content, email)
                    logger.info(f"[UPLOAD_CONFIRM] Found {len(matching_configs.get('matches', [])) if matching_configs.get('success') else 0} matching configs")
                except Exception as e:
                    logger.warning(f"[UPLOAD_CONFIRM] Error finding matching configs: {str(e)}")
                    matching_configs = {'success': False, 'matches': []}

                # Construct storage path (matches old format)
                domain = email.split('@')[1] if '@' in email else 'unknown'
                email_prefix = email.split('@')[0] if '@' in email else email
                storage_path = f"{domain}/{email_prefix}/{session_id}"

                # Extract and store clean table name in session_info
                from interface_lambda.utils.helpers import clean_table_name
                display_name = clean_table_name(filename, for_display=True)
                filename_base = clean_table_name(filename, for_display=False)

                try:
                    session_info = storage_manager.load_session_info(email, session_id)
                    session_info['original_filename'] = filename
                    session_info['clean_table_name'] = display_name
                    session_info['table_name_base'] = filename_base  # For use in output filenames
                    session_info['input_file'] = {
                        's3_key': s3_key,
                        'upload_id': upload_id,
                        'uploaded_at': datetime.now(timezone.utc).isoformat()
                    }
                    storage_manager.save_session_info(email, session_id, session_info)
                    logger.info(f"[UPLOAD_CONFIRM] Saved clean_table_name='{display_name}' to session_info")
                except Exception as e:
                    logger.warning(f"[UPLOAD_CONFIRM] Failed to save session_info: {e}")

                logger.info(f"[UPLOAD_CONFIRM] Excel analysis complete: {upload_id}")

                return create_response(200, {
                    'success': True,
                    'status': 'uploaded',
                    'upload_id': upload_id,
                    's3_key': s3_key,
                    'session_id': session_id,
                    'storage_path': storage_path,
                    'matching_configs': matching_configs,
                    'message': 'Excel file uploaded and analyzed successfully'
                })

            except Exception as e:
                logger.error(f"[UPLOAD_CONFIRM] Error analyzing Excel file: {str(e)}", exc_info=True)
                # Return success for upload but indicate analysis failed
                return create_response(200, {
                    'success': True,
                    'status': 'uploaded',
                    'upload_id': upload_id,
                    's3_key': s3_key,
                    'session_id': session_id,
                    'storage_path': f"{email.split('@')[1] if '@' in email else 'unknown'}/{email.split('@')[0] if '@' in email else email}/{session_id}",
                    'matching_configs': {'success': False, 'matches': []},
                    'message': f'Excel file uploaded but analysis failed: {str(e)}'
                })

    except Exception as e:
        logger.error(f"[UPLOAD_CONFIRM] Error confirming upload: {str(e)}", exc_info=True)
        return create_response(500, {
            'success': False,
            'error': 'server_error',
            'message': f'Failed to process upload confirmation: {str(e)}'
        })
