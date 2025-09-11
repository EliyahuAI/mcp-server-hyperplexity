"""
SQS service management for Perplexity Validator.

This module provides functions for creating SQS queues, sending messages with priorities,
and handling the message processing workflow.
"""

import boto3
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError
import os
from pathlib import Path

from interface_lambda.core.unified_s3_manager import UnifiedS3Manager

logger = logging.getLogger(__name__)
sqs = boto3.client('sqs', region_name=os.environ.get("AWS_REGION", "us-east-1"))

PREVIEW_QUEUE_URL = os.environ.get('PREVIEW_QUEUE_URL')
STANDARD_QUEUE_URL = os.environ.get('STANDARD_QUEUE_URL')

def send_preview_request(session_id, excel_s3_key, config_s3_key, email, reference_pin, preview_email=False, **kwargs):
    """Send a preview validation request to the priority SQS queue."""
    if not PREVIEW_QUEUE_URL:
        logger.error("Preview SQS queue URL is not configured.")
        return None
    message_body = {
        'request_type': 'preview',
        'session_id': session_id,
        'excel_s3_key': excel_s3_key,
        'config_s3_key': config_s3_key,
        'email': email,
        'reference_pin': reference_pin,
        'preview_email': preview_email,
        'created_at': datetime.now(timezone.utc).isoformat(),
        **kwargs
    }
    return _send_sqs_message(PREVIEW_QUEUE_URL, message_body, is_fifo=True)

def send_full_request(session_id, excel_s3_key, config_s3_key, email, reference_pin, results_key=None, max_rows=None, batch_size=None, email_folder=None, preview_email=False, run_key=None):
    """Send a full validation request to the standard SQS queue."""
    if not STANDARD_QUEUE_URL:
        logger.error("Standard SQS queue URL is not configured.")
        return None
    
    # Generate results_key if not provided, using unified storage format
    if not results_key:
        # Use unified storage format: results/{domain}/{email_prefix}/{session_id}/
        storage_manager = UnifiedS3Manager()
        session_path = storage_manager.get_session_path(email, session_id)
        results_key = f"{session_path.rstrip('/')}.zip"
        logger.info(f"Generated results_key using unified format: {results_key}")
    
    message_body = {
        'request_type': 'full',
        'session_id': session_id,
        'excel_s3_key': excel_s3_key,
        'config_s3_key': config_s3_key,
        'email': email,
        'reference_pin': reference_pin,
        'results_key': results_key,
        'max_rows': max_rows,
        'batch_size': batch_size,
        'email_folder': email_folder,  # Keep for backward compatibility
        'preview_email': preview_email,
        'run_key': run_key,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    # Clean out None values so they don't get serialized
    message_body_cleaned = {k: v for k, v in message_body.items() if v is not None}
    return _send_sqs_message(STANDARD_QUEUE_URL, message_body_cleaned)

def send_config_generation_request(message_data):
    """Send a config generation request to the standard SQS queue."""
    if not STANDARD_QUEUE_URL:
        logger.error("Standard SQS queue URL is not configured.")
        return None
    
    message_body = {
        'request_type': 'config_generation',
        'created_at': datetime.now(timezone.utc).isoformat(),
        **message_data
    }
    
    # Clean out None values so they don't get serialized
    message_body_cleaned = {k: v for k, v in message_body.items() if v is not None}
    return _send_sqs_message(STANDARD_QUEUE_URL, message_body_cleaned)

def _send_sqs_message(queue_url, message_body, is_fifo=False):
    """Helper function to send a message to a specified SQS queue."""
    try:
        params = {
            'QueueUrl': queue_url,
            'MessageBody': json.dumps(message_body)
        }
        if is_fifo:
            params['MessageGroupId'] = 'perplexity-validator'
            params['MessageDeduplicationId'] = f"{message_body['session_id']}-{message_body['created_at']}"
            
        response = sqs.send_message(**params)
        logger.info(f"Message sent to SQS queue {queue_url}. MessageId: {response['MessageId']}")
        return response['MessageId']
    except ClientError as e:
        logger.error(f"Failed to send message to SQS queue {queue_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending SQS message: {e}")
        return None

# The SQSManager and queue creation logic is better handled in the deployment script
# and not at runtime within the Lambda. Keeping this file focused on sending messages. 