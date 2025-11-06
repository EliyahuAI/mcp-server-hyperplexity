"""
Reference Check Conversation Management

Handles the conversation flow for reference checking.
Includes upfront text size validation and async/sync split pattern.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
import re

# Import shared services
from interface_lambda.core.sqs_service import _send_sqs_message
import os
from interface_lambda.services.user_service import validate_email_and_get_session_data
from interface_lambda.services.dynamodb_service import create_run_record, update_run_status
from interface_lambda.services.websocket_client import WebSocketClient
from interface_lambda.services.s3_service import UnifiedS3Manager

# Logger
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


# Load configuration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'reference_check_config.json')
with open(CONFIG_PATH, 'r') as f:
    CONFIG = json.load(f)


def _validate_text_size(text: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate that submitted text is within token limits.

    Uses conservative estimate: 1.33 tokens per word (4 tokens per 3 words)
    Max: 32,000 tokens (~24,000 words)

    Args:
        text: The submitted text to validate

    Returns:
        Tuple of (is_valid, details_dict)
        details_dict contains: word_count, estimated_tokens, max_words, max_tokens
    """
    # Get limits from config
    max_tokens = CONFIG['text_limits']['max_tokens']
    max_words = CONFIG['text_limits']['max_words']
    tokens_per_word = CONFIG['text_limits']['tokens_per_word']

    # Count words (simple whitespace split)
    word_count = len(text.split())

    # Estimate tokens
    estimated_tokens = int(word_count * tokens_per_word)

    # Check if within limits
    is_valid = word_count <= max_words and estimated_tokens <= max_tokens

    details = {
        'word_count': word_count,
        'estimated_tokens': estimated_tokens,
        'max_words': max_words,
        'max_tokens': max_tokens,
        'is_valid': is_valid
    }

    return is_valid, details


async def handle_reference_check_start_async(request_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    HTTP endpoint handler - validates and queues reference check to SQS.

    This is the async wrapper that:
    1. Validates email/session
    2. Validates text size (UPFRONT CHECK)
    3. Returns error immediately if text too large
    4. Generates conversation_id
    5. Queues to SQS
    6. Returns 200 immediately

    Results will be sent via WebSocket.

    Args:
        request_data: Request payload with email, session_id, submitted_text
        context: Lambda context

    Returns:
        Response dict with status 200 (queued) or 400 (validation error)
    """
    try:
        # Extract required fields
        email = request_data.get('email', '').strip().lower()
        session_id = request_data.get('session_id', '').strip()
        submitted_text = request_data.get('submitted_text', '').strip()

        # Validate required fields
        if not email or not submitted_text:
            return {
                'statusCode': 400,
                'body': {
                    'status': 'error',
                    'error': 'missing_fields',
                    'message': 'Email and submitted_text are required'
                }
            }

        # Generate session ID if not provided (like table_maker does)
        if not session_id:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            random_hex = uuid.uuid4().hex[:8]
            session_id = f"session_{timestamp}_{random_hex}"
            logger.info(f"[REFERENCE_CHECK] Generated new session ID: {session_id}")

        # Validate email and get/create session
        try:
            session_info = validate_email_and_get_session_data(email, session_id)
            session_id = session_info.get('session_id')
        except Exception as e:
            logger.error(f"Email validation failed: {str(e)}")
            return {
                'statusCode': 400,
                'body': {
                    'status': 'error',
                    'error': 'invalid_email',
                    'message': 'Email validation failed'
                }
            }

        # ===== UPFRONT TEXT SIZE VALIDATION =====
        is_valid, size_details = _validate_text_size(submitted_text)

        if not is_valid:
            error_message = CONFIG['text_limits']['error_message'].format(
                max_words=size_details['max_words']
            )

            logger.warning(
                f"Text too large for session {session_id}: "
                f"{size_details['word_count']} words, "
                f"~{size_details['estimated_tokens']} tokens"
            )

            return {
                'statusCode': 400,
                'body': {
                    'status': 'error',
                    'error': 'text_too_large',
                    'message': error_message,
                    'details': size_details
                }
            }

        # Text size is valid, proceed with processing
        logger.info(
            f"Text size valid for session {session_id}: "
            f"{size_details['word_count']} words, "
            f"~{size_details['estimated_tokens']} tokens"
        )

        # Generate conversation ID
        conversation_id = f"refcheck_{uuid.uuid4().hex[:12]}"

        # Prepare message for SQS
        conversation_request = {
            'request_type': 'reference_check',  # Important: Different from table_conversation
            'action': 'startReferenceCheck',
            'email': email,
            'session_id': session_id,
            'conversation_id': conversation_id,
            'submitted_text': submitted_text,
            'text_stats': size_details,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'deployment_environment': os.environ.get('DEPLOYMENT_ENVIRONMENT', 'prod')
        }

        # Send to SQS queue
        try:
            # Get queue URL
            queue_url = os.environ.get('SQS_STANDARD_QUEUE_URL')
            if not queue_url:
                raise Exception("SQS_STANDARD_QUEUE_URL not configured")

            # Clean out None values
            message_body_cleaned = {k: v for k, v in conversation_request.items() if v is not None}

            # Send to SQS
            message_id = _send_sqs_message(queue_url, message_body_cleaned)
            logger.info(
                f"Reference check queued: {conversation_id}, "
                f"SQS message: {message_id}"
            )
        except Exception as e:
            logger.error(f"Failed to queue reference check: {str(e)}")
            return {
                'statusCode': 500,
                'body': {
                    'status': 'error',
                    'error': 'queue_failed',
                    'message': 'Failed to start reference check. Please try again.'
                }
            }

        # Return immediate success response
        return {
            'statusCode': 200,
            'body': {
                'success': True,
                'status': 'processing',
                'conversation_id': conversation_id,
                'session_id': session_id,
                'message': 'Reference check started. Results will be sent via WebSocket.',
                'text_stats': {
                    'word_count': size_details['word_count'],
                    'estimated_tokens': size_details['estimated_tokens']
                }
            }
        }

    except Exception as e:
        logger.error(f"Error in handle_reference_check_start_async: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {
                'status': 'error',
                'error': 'internal_error',
                'message': 'An unexpected error occurred'
            }
        }


async def handle_reference_check_start(request_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Background processor - executes the reference check pipeline.

    This is the sync handler that runs in the background after being queued from SQS.
    It:
    1. Creates run record in DynamoDB
    2. Initializes conversation state
    3. Saves state to S3
    4. Triggers execution pipeline
    5. Sends progress updates via WebSocket

    Args:
        request_data: SQS message payload
        context: Lambda context

    Returns:
        Result dict with status
    """
    try:
        # Extract fields
        email = request_data['email']
        session_id = request_data['session_id']
        conversation_id = request_data['conversation_id']
        submitted_text = request_data['submitted_text']
        text_stats = request_data.get('text_stats', {})

        logger.info(
            f"[REFERENCE CHECK START] conversation_id={conversation_id}, "
            f"session={session_id}, email={email}, "
            f"text_length={len(submitted_text)} chars"
        )

        # Create run record in DynamoDB
        run_key = create_run_record(
            session_id=session_id,
            email=email,
            total_rows=0,  # Not applicable for reference check
            run_type="Reference Check"
        )

        # Update run status
        update_run_status(
            session_id=session_id,
            run_key=run_key,
            status='IN_PROGRESS',
            run_type="Reference Check",
            verbose_status="Starting reference validation...",
            percent_complete=5
        )

        # Initialize conversation state
        conversation_state = {
            'conversation_id': conversation_id,
            'session_id': session_id,
            'email': email,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'status': 'analyzing',
            'run_key': run_key,
            'submitted_text': submitted_text,
            'text_length': len(submitted_text),
            'text_stats': text_stats,
            'extraction_result': None,
            'validation_results': None,
            'csv_s3_key': None
        }

        # Save conversation state to S3
        storage_manager = UnifiedS3Manager()
        _save_conversation_state(storage_manager, email, session_id, conversation_id, conversation_state)

        # Send initial WebSocket update
        ws_client = WebSocketClient()
        ws_client.send_to_session(session_id, {
            'type': 'reference_check_progress',
            'conversation_id': conversation_id,
            'current_step': 0,
            'total_steps': 2,
            'status': 'Analyzing text and extracting claims...',
            'progress_percent': 10,
            'phase': 'extraction',
            'text_stats': text_stats
        })

        # Import and trigger execution pipeline
        from .execution import execute_reference_check

        result = await execute_reference_check(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            run_key=run_key
        )

        logger.info(f"[REFERENCE CHECK COMPLETE] conversation_id={conversation_id}, status={result.get('status')}")

        return result

    except Exception as e:
        logger.error(f"Error in handle_reference_check_start: {str(e)}", exc_info=True)

        # Update run status to failed
        if 'run_key' in locals():
            update_run_status(
                session_id=session_id,
                run_key=run_key,
                status='FAILED',
                run_type="Reference Check",
                verbose_status=f"Error: {str(e)}",
                percent_complete=0
            )

        # Send error via WebSocket
        if 'session_id' in locals() and 'conversation_id' in locals():
            ws_client = WebSocketClient()
            ws_client.send_to_session(session_id, {
                'type': 'reference_check_error',
                'conversation_id': conversation_id,
                'status': 'error',
                'message': 'An error occurred during reference check. Please try again.'
            })

        return {
            'status': 'error',
            'message': str(e)
        }


def _save_conversation_state(storage_manager: UnifiedS3Manager, email: str, session_id: str,
                             conversation_id: str, state: Dict[str, Any]) -> None:
    """
    Save conversation state to S3.

    Args:
        storage_manager: S3 manager instance
        email: User email
        session_id: Session ID
        conversation_id: Conversation ID
        state: State dict to save
    """
    s3_key = f"reference_checks/{email}/{session_id}/{conversation_id}/conversation_state.json"

    storage_manager.s3_client.put_object(
        Bucket=storage_manager.bucket_name,
        Key=s3_key,
        Body=json.dumps(state, indent=2),
        ContentType='application/json'
    )

    logger.info(f"Saved conversation state to S3: {s3_key}")


def _load_conversation_state(storage_manager: UnifiedS3Manager, email: str, session_id: str,
                             conversation_id: str) -> Dict[str, Any]:
    """
    Load conversation state from S3.

    Args:
        storage_manager: S3 manager instance
        email: User email
        session_id: Session ID
        conversation_id: Conversation ID

    Returns:
        State dict
    """
    s3_key = f"reference_checks/{email}/{session_id}/{conversation_id}/conversation_state.json"

    response = storage_manager.s3_client.get_object(
        Bucket=storage_manager.bucket_name,
        Key=s3_key
    )

    state = json.loads(response['Body'].read())
    logger.info(f"Loaded conversation state from S3: {s3_key}")

    return state
