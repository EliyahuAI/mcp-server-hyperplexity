"""
Lightweight preview starter - sends preview request to SQS without heavy multipart processing.

This replaces the multipart form path for previews when files are already uploaded to S3.
The full multipart path (process_excel_unified) does double multipart parsing, S3 lookups,
DynamoDB writes, and config searches before delegating to SQS. On a 128MB Lambda with cold
start, this can exceed the 29-second API Gateway timeout.

This handler does the minimum needed: look up S3 keys from session_info and send to SQS.
"""
import logging
import os
import sys

from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle_start_preview(request_data, context=None):
    """
    Start a preview validation via SQS.

    Expects:
        request_data: {
            '_verified_email': 'user@example.com',  # Set by http_handler token verification
            'session_id': 'session_20260210_...',
            'preview_max_rows': 3
        }

    Returns:
        200 with status: 'processing' on success
    """
    email = request_data.get('_verified_email') or request_data.get('email')
    session_id = request_data.get('session_id')
    preview_max_rows = int(request_data.get('preview_max_rows', 3))

    if not email or not session_id:
        return create_response(400, {
            'success': False,
            'error': 'Missing required parameters: email, session_id'
        })

    # Clean session ID
    base_session_id = session_id
    if base_session_id.endswith('_preview'):
        base_session_id = base_session_id[:-8]
    if not base_session_id.startswith('session_'):
        base_session_id = f"session_{base_session_id}"

    try:
        from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
        storage_manager = UnifiedS3Manager()

        # Look up stored files from session_info (single S3 read)
        session_info = storage_manager.load_session_info(email, base_session_id)
        excel_s3_key = session_info.get('table_path')

        if not excel_s3_key:
            # Fallback: try direct S3 lookup
            _, excel_s3_key = storage_manager.get_excel_file(email, base_session_id)

        if not excel_s3_key:
            return create_response(400, {
                'success': False,
                'error': 'No Excel file found for this session. Please upload a file first.'
            })

        # Get latest config
        existing_config, config_s3_key = storage_manager.get_latest_config(email, base_session_id)
        if not config_s3_key:
            return create_response(400, {
                'success': False,
                'error': 'No configuration found. Please generate or upload a config first.'
            })

        # Create run record for tracking
        try:
            sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
            from dynamodb_schemas import create_run_record, track_validation_call
            run_key = create_run_record(
                session_id=base_session_id, email=email,
                total_rows=-1, batch_size=None, run_type="Preview"
            )
            reference_pin = base_session_id.split('_')[-1] if '_' in base_session_id else base_session_id[:6]
            track_validation_call(
                email=email, session_id=base_session_id,
                reference_pin=reference_pin, request_type='preview',
                excel_s3_key=excel_s3_key, config_s3_key=config_s3_key
            )
        except Exception as e:
            logger.warning(f"Failed to create tracking records: {e}")
            run_key = None
            reference_pin = base_session_id.split('_')[-1] if '_' in base_session_id else base_session_id[:6]

        # Send to SQS for background processing
        from interface_lambda.core.sqs_service import send_preview_request
        message_id = send_preview_request(
            session_id=base_session_id,
            excel_s3_key=excel_s3_key,
            config_s3_key=config_s3_key,
            email=email,
            reference_pin=reference_pin,
            preview_max_rows=preview_max_rows,
            run_key=run_key
        )

        logger.info(f"[START_PREVIEW] Sent preview to SQS for {base_session_id}, MessageId: {message_id}")

        return create_response(200, {
            'status': 'processing',
            'session_id': base_session_id,
            'reference_pin': reference_pin,
            'storage_path': storage_manager.get_session_path(email, base_session_id)
        })

    except Exception as e:
        logger.error(f"[START_PREVIEW] Error: {e}")
        return create_response(500, {
            'success': False,
            'error': f'Failed to start preview: {str(e)}'
        })
