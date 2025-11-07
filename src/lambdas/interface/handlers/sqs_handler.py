"""
Handles SQS messages for background processing.
"""
import json
import logging
import os
from datetime import datetime

from interface_lambda.handlers import background_handler

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(event, context):
    """
    Handle SQS events.

    This function iterates through SQS records, parses the message body,
    and triggers the background processing handler for each message.
    """
    logger.info("--- SQS Handler ---")
    
    for record in event['Records']:
        try:
            message_body = json.loads(record['body'])
            
            # Environment filtering: only process messages from our deployment environment
            message_environment = message_body.get('deployment_environment', 'prod')
            current_environment = os.environ.get('DEPLOYMENT_ENVIRONMENT', 'prod')
            
            if message_environment != current_environment:
                logger.info(f"Skipping message from {message_environment} environment (current: {current_environment})")
                continue
            
            # Check message type to determine routing
            message_type = message_body.get('message_type', '')
            request_type = message_body.get('request_type', '')
            is_preview = (request_type == 'preview') or message_body.get('preview_mode', False)

            # Handle async completion messages from validation lambda
            # Check for both message types and async_completion flag for compatibility
            if (message_type == 'ASYNC_COMPLETION_REQUEST' or
                message_type == 'ASYNC_VALIDATION_COMPLETE' or
                message_body.get('async_completion', False)):
                logger.info(f"Processing async completion for session {message_body.get('session_id')} (message_type={message_type}, async_completion={message_body.get('async_completion', False)})")
                # Route directly to background handler with the completion data
                background_event = message_body  # Pass entire message for async completion

            # Handle config generation requests
            elif request_type == 'config_generation':
                logger.info(f"Processing config generation request for session {message_body.get('session_id')}")
                # Pass the entire message body for config generation
                background_event = {
                    "background_processing": True,
                    "request_type": "config_generation",
                    **message_body
                }

            # Handle table conversation requests
            elif request_type == 'table_conversation':
                logger.info(f"Processing table conversation request for session {message_body.get('session_id')}")
                # Pass the entire message body for table conversation
                background_event = {
                    "background_processing": True,
                    "request_type": "table_conversation",
                    **message_body
                }

            # Handle table finalization requests (preview generation + accept and validate)
            elif request_type == 'table_finalization':
                logger.info(f"Processing table finalization request for session {message_body.get('session_id')}")
                # Pass the entire message body for table finalization
                background_event = {
                    "background_processing": True,
                    "request_type": "table_finalization",
                    **message_body
                }

            # Handle reference check requests
            elif request_type == 'reference_check':
                logger.info(f"Processing reference check request for session {message_body.get('session_id')}")
                # Pass the entire message body for reference check
                background_event = {
                    "background_processing": True,
                    "request_type": "reference_check",
                    **message_body
                }

            # Handle PDF conversion requests
            elif request_type == 'pdf_conversion':
                logger.info(f"Processing PDF conversion request for session {message_body.get('session_id')}, pdf_id: {message_body.get('pdf_id')}")
                # Pass the entire message body for PDF conversion
                background_event = {
                    "background_processing": True,
                    "request_type": "pdf_conversion",
                    **message_body
                }

            else:
                # Handle regular validation requests
                background_event = {
                    "background_processing": True,
                    "preview_mode": is_preview,
                    "session_id": message_body.get('session_id'),
                    "timestamp": message_body.get('timestamp', datetime.utcnow().strftime('%Y%m%d_%H%M%S')),
                    "reference_pin": message_body.get('reference_pin'),
                    "excel_s3_key": message_body.get('excel_s3_key'),
                    "config_s3_key": message_body.get('config_s3_key'),
                    "results_key": message_body.get('results_key'),
                    "preview_max_rows": message_body.get('preview_max_rows', 5),
                    "email_folder": message_body.get('email_folder'),
                    "max_rows": message_body.get('max_rows', 1000),
                    "batch_size": message_body.get('batch_size', 10),
                    "sequential_call": message_body.get('sequential_call'),
                    "email": message_body.get('email'),
                    "email_address": message_body.get('email'),  # For compatibility
                    "preview_email": message_body.get('preview_email', False),
                    "run_key": message_body.get('run_key')
                }
            
            # Process using the background handler
            background_handler.handle(background_event, context)
            
        except Exception as e:
            logger.error(f"Error processing SQS message: {str(e)}")
            # Depending on the SQS configuration, re-raising the exception
            # might cause the message to be re-processed.
            # For now, we log and continue to prevent a poison-pill scenario.
            import traceback
            logger.error(traceback.format_exc())
            continue # Process next record

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'SQS messages processed successfully'})
    } 