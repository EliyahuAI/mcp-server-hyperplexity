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
from interface_lambda.core.sqs_service import _send_sqs_message, STANDARD_QUEUE_URL
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response
from dynamodb_schemas import create_run_record, update_run_status
from websocket_client import WebSocketClient

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
    Max tokens specified in config, max words calculated.

    Args:
        text: The submitted text to validate

    Returns:
        Tuple of (is_valid, details_dict)
        details_dict contains: word_count, estimated_tokens, max_tokens
    """
    # Get limits from config
    max_tokens = CONFIG['text_limits']['max_tokens']
    tokens_per_word = CONFIG['text_limits']['tokens_per_word']

    # Calculate max words from tokens (3 words = 4 tokens)
    max_words = int(max_tokens / tokens_per_word)

    # Count words (simple whitespace split)
    word_count = len(text.split())

    # Estimate tokens
    estimated_tokens = int(word_count * tokens_per_word)

    # Check if within limits (token-based validation)
    is_valid = estimated_tokens <= max_tokens

    details = {
        'word_count': word_count,
        'estimated_tokens': estimated_tokens,
        'max_tokens': max_tokens,
        'max_words': max_words,
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
        email = (request_data.get('email') or '').strip().lower()
        session_id = (request_data.get('session_id') or '').strip()
        submitted_text = (request_data.get('submitted_text') or '').strip()

        # Validate required fields
        if not email or not submitted_text:
            return create_response(400, {
                'success': False,
                'error': 'missing_fields',
                'message': 'Email and submitted_text are required'
            })

        # Generate session ID if not provided (like table_maker does)
        if not session_id:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            random_hex = uuid.uuid4().hex[:8]
            session_id = f"session_{timestamp}_{random_hex}"
            logger.info(f"[REFERENCE_CHECK] Generated new session ID: {session_id}")

        # Note: Email validation is assumed to be done by frontend before this action
        # Same pattern as table_maker - just use the email/session provided

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

            return create_response(400, {
                'success': False,
                'error': 'text_too_large',
                'message': error_message,
                'details': size_details
            })

        # Text size is valid, proceed with processing
        logger.info(
            f"Text size valid for session {session_id}: "
            f"{size_details['word_count']} words, "
            f"~{size_details['estimated_tokens']} tokens"
        )

        # Generate conversation ID
        conversation_id = f"refcheck_{uuid.uuid4().hex[:12]}"

        # Read optional auto_approve flag
        auto_approve = bool(request_data.get('auto_approve', False))

        # Prepare message for SQS
        conversation_request = {
            'request_type': 'reference_check',  # Important: Different from table_conversation
            'action': 'startReferenceCheck',
            'email': email,
            'session_id': session_id,
            'conversation_id': conversation_id,
            'submitted_text': submitted_text,
            'text_stats': size_details,
            'auto_approve': auto_approve,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'deployment_environment': os.environ.get('DEPLOYMENT_ENVIRONMENT', 'prod')
        }

        # Send to SQS queue
        try:
            # Check queue URL is configured
            if not STANDARD_QUEUE_URL:
                raise Exception("STANDARD_QUEUE_URL not configured")

            # Clean out None values
            message_body_cleaned = {k: v for k, v in conversation_request.items() if v is not None}

            # Send to SQS
            message_id = _send_sqs_message(STANDARD_QUEUE_URL, message_body_cleaned)
            logger.info(
                f"Reference check queued: {conversation_id}, "
                f"SQS message: {message_id}"
            )
        except Exception as e:
            logger.error(f"Failed to queue reference check: {str(e)}")
            return create_response(500, {
                'success': False,
                'error': 'queue_failed',
                'message': 'Failed to start reference check. Please try again.'
            })

        # Return immediate success response
        return create_response(200, {
            'success': True,
            'status': 'processing',
            'conversation_id': conversation_id,
            'session_id': session_id,
            'message': 'Reference check started. Results will be sent via WebSocket.',
            'text_stats': {
                'word_count': size_details['word_count'],
                'estimated_tokens': size_details['estimated_tokens']
            }
        })

    except Exception as e:
        logger.error(f"Error in handle_reference_check_start_async: {str(e)}", exc_info=True)
        return create_response(500, {
            'success': False,
            'error': 'internal_error',
            'message': f'An unexpected error occurred: {str(e)}'
        })


async def handle_reference_check_start(request_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Background processor - Phase 1 (extraction only).

    Creates run record, saves conversation state, runs phase 1 (claim extraction).
    If auto_approve=True and balance is sufficient, immediately queues phase 2.
    """
    try:
        # Extract fields
        email = request_data['email']
        session_id = request_data['session_id']
        conversation_id = request_data['conversation_id']
        submitted_text = request_data['submitted_text']
        text_stats = request_data.get('text_stats', {})
        auto_approve = bool(request_data.get('auto_approve', False))

        logger.info(
            f"[REFERENCE CHECK START] conversation_id={conversation_id}, "
            f"session={session_id}, email={email}, "
            f"text_length={len(submitted_text)} chars, auto_approve={auto_approve}"
        )

        # Create run record for Phase 1
        run_key = create_run_record(
            session_id=session_id,
            email=email,
            total_rows=0,
            run_type="Reference Check Preview"
        )

        update_run_status(
            session_id=session_id,
            run_key=run_key,
            status='IN_PROGRESS',
            run_type="Reference Check Preview",
            verbose_status="Extracting claims...",
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
            'auto_approve': auto_approve,
            'extraction_result': None,
            'validation_results': None,
            'csv_s3_key': None
        }

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

        # Run Phase 1 (extraction only)
        from .execution import execute_reference_check_phase1
        result = await execute_reference_check_phase1(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            run_key=run_key
        )

        logger.info(f"[REFERENCE CHECK PHASE1 COMPLETE] conversation_id={conversation_id}, success={result.get('success')}")

        # If auto_approve, queue the standard validator immediately (same path as approve_validation)
        if result.get('success') and auto_approve:
            logger.info(f"[REFERENCE CHECK] auto_approve=True, queuing standard validator for {conversation_id}")
            try:
                from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
                from dynamodb_schemas import create_run_record, track_validation_call
                from interface_lambda.core.sqs_service import send_full_request
                storage_manager = UnifiedS3Manager()
                si = storage_manager.load_session_info(email, session_id)
                excel_s3_key = si.get('table_path')
                _, config_s3_key = storage_manager.get_latest_config(email, session_id)
                if excel_s3_key and config_s3_key:
                    reference_pin = session_id.split('_')[-1] if '_' in session_id else session_id[:6]
                    run_key = create_run_record(
                        session_id=session_id, email=email,
                        total_rows=-1, batch_size=None, run_type="Validation"
                    )
                    track_validation_call(
                        email=email, session_id=session_id,
                        reference_pin=reference_pin, request_type='full',
                        excel_s3_key=excel_s3_key, config_s3_key=config_s3_key
                    )
                    send_full_request(
                        session_id=session_id,
                        excel_s3_key=excel_s3_key,
                        config_s3_key=config_s3_key,
                        email=email,
                        reference_pin=reference_pin,
                        run_key=run_key,
                    )
                    logger.info(f"[REFERENCE CHECK] Standard validator queued for {conversation_id}, run_key={run_key}")
                else:
                    logger.error(f"[REFERENCE CHECK] auto_approve: CSV or config missing, cannot queue validator")
            except Exception as e:
                logger.error(f"[REFERENCE CHECK] Failed to queue standard validator: {e}", exc_info=True)

        return result

    except Exception as e:
        logger.error(f"Error in handle_reference_check_start: {str(e)}", exc_info=True)

        if 'run_key' in locals():
            update_run_status(
                session_id=session_id,
                run_key=run_key,
                status='FAILED',
                run_type="Reference Check Preview",
                verbose_status=f"Error: {str(e)}",
                percent_complete=0
            )

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
        State dict or None if not found
    """
    s3_key = f"reference_checks/{email}/{session_id}/{conversation_id}/conversation_state.json"

    try:
        response = storage_manager.s3_client.get_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key
        )

        state = json.loads(response['Body'].read())
        logger.info(f"Loaded conversation state from S3: {s3_key}")
        return state

    except storage_manager.s3_client.exceptions.NoSuchKey:
        logger.error(f"Conversation state not found: {s3_key}")
        return None
    except Exception as e:
        logger.error(f"Error loading conversation state from {s3_key}: {e}", exc_info=True)
        return None
