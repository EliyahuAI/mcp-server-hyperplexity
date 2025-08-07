"""
Handles SQS messages for background processing.
"""
import json
import logging
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
            
            # Transform SQS message to the format expected by the background handler
            request_type = message_body.get('request_type', '')
            is_preview = (request_type == 'preview') or message_body.get('preview_mode', False)
            
            # Handle config generation requests differently
            if request_type == 'config_generation':
                logger.info(f"Processing config generation request for session {message_body.get('session_id')}")
                # Pass the entire message body for config generation
                background_event = {
                    "background_processing": True,
                    "request_type": "config_generation",
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
                    "preview_email": message_body.get('preview_email', False)
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