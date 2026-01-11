"""
Upload Interview Processing Handler for Lambda Environment.

This module handles the background processing of upload interview requests,
managing conversation state in S3 and sending WebSocket updates.
"""

import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError

# Lambda imports
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response

# Upload interview imports
from .interview import UploadInterviewHandler
from . import PROMPTS_DIR, SCHEMAS_DIR

# WebSocket client for real-time updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger = logging.getLogger()
    logger.warning("WebSocket client not available for upload interview")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


async def handle_upload_interview_start(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process upload interview start request from SQS.

    This is called when a user uploads a table and we need to start the interview.

    Args:
        event: SQS event containing session_id, email, conversation_id, user_message
        context: Lambda context

    Returns:
        Response dictionary
    """
    try:
        session_id = event.get('session_id')
        email = event.get('email')
        conversation_id = event.get('conversation_id')
        user_message = event.get('user_message', '')

        if not session_id or not email or not conversation_id:
            logger.error("[UPLOAD_INTERVIEW] Missing required fields")
            return create_response(400, {'error': 'Missing required fields: session_id, email, conversation_id'})

        logger.info(f"[UPLOAD_INTERVIEW] Starting interview for session {session_id}")

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Load table analysis from session info
        session_info = storage_manager.load_session_info(email, session_id)
        table_analysis = session_info.get('table_analysis', {})

        if not table_analysis:
            # Try to extract table analysis if not available
            logger.warning("[UPLOAD_INTERVIEW] No table analysis in session info, attempting to extract")
            try:
                from shared_table_parser import S3TableParser
                if S3TableParser:
                    excel_content, excel_s3_key = storage_manager.get_excel_file(email, session_id)
                    if excel_s3_key:
                        parser = S3TableParser(enable_cleaning_log=False)
                        sample = parser.get_table_sample(storage_manager.bucket_name, excel_s3_key, max_rows=3)
                        table_analysis = {
                            'columns': sample.get('column_names', []),
                            'row_count': sample.get('total_rows', 0),
                            'sample_rows': sample.get('sample_data', [])
                        }
            except Exception as e:
                logger.error(f"[UPLOAD_INTERVIEW] Failed to extract table analysis: {e}")
                table_analysis = {}

        # Initialize interview handler
        interview_handler = UploadInterviewHandler(PROMPTS_DIR, SCHEMAS_DIR)

        # Load existing conversation state if available
        conversation_state = _load_conversation_state(storage_manager, email, session_id, conversation_id)
        if conversation_state:
            # Restore conversation history
            interview_handler.messages = conversation_state.get('messages', [])
            interview_handler.interview_context = conversation_state.get('interview_context', {})
            logger.info(f"[UPLOAD_INTERVIEW] Restored conversation state with {len(interview_handler.messages)} messages")

        # Start interview
        result = await interview_handler.start_interview(
            table_analysis=table_analysis,
            user_message=user_message
        )

        if not result['success']:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"[UPLOAD_INTERVIEW] Interview failed: {error_msg}")

            # Send error via WebSocket
            if websocket_client:
                websocket_client.send_to_session(session_id, {
                    'type': 'upload_interview_error',
                    'conversation_id': conversation_id,
                    'error': error_msg
                })

            return create_response(500, {'error': error_msg})

        # Save conversation state
        conversation_state = {
            'conversation_id': conversation_id,
            'session_id': session_id,
            'email': email,
            'created_at': conversation_state.get('created_at', datetime.utcnow().isoformat() + 'Z') if conversation_state else datetime.utcnow().isoformat() + 'Z',
            'updated_at': datetime.utcnow().isoformat() + 'Z',
            'status': 'awaiting_approval' if result['mode'] == 2 else 'in_progress',
            'turn_count': len(interview_handler.messages),
            'messages': interview_handler.messages,
            'interview_context': interview_handler.interview_context,
            'table_analysis': table_analysis,
            'mode': result['mode'],
            'trigger_config_generation': result['trigger_config_generation']
        }

        # Add confirmation response and config instructions if available
        if result.get('confirmation_response'):
            conversation_state['confirmation_response'] = result['confirmation_response']
        if result.get('config_instructions'):
            conversation_state['config_instructions'] = result['config_instructions']

        _save_conversation_state(storage_manager, email, session_id, conversation_id, conversation_state)

        # Send response via WebSocket
        if websocket_client:
            websocket_message = {
                'type': 'upload_interview_update',
                'conversation_id': conversation_id,
                'mode': result['mode'],
                'ai_message': result['ai_message'],
                'inferred_context': result.get('inferred_context', {}),
                'trigger_config_generation': result['trigger_config_generation']
            }

            # Include confirmation_response for mode 2 (so frontend can use it on button press)
            if result['mode'] == 2 and result.get('confirmation_response'):
                websocket_message['confirmation_response'] = result['confirmation_response']

            websocket_client.send_to_session(session_id, websocket_message)
            logger.info(f"[UPLOAD_INTERVIEW] Sent WebSocket update for mode {result['mode']}")

        # If trigger_config_generation is true, start config generation
        if result['trigger_config_generation']:
            await _trigger_config_generation(
                storage_manager=storage_manager,
                session_id=session_id,
                email=email,
                conversation_id=conversation_id,
                config_instructions=result.get('config_instructions', ''),
                inferred_context=result.get('inferred_context', {}),
                conversation_messages=interview_handler.messages
            )

        return create_response(200, {
            'success': True,
            'conversation_id': conversation_id,
            'mode': result['mode']
        })

    except Exception as e:
        logger.error(f"[UPLOAD_INTERVIEW] Error starting interview: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # Send error via WebSocket
        if websocket_client and session_id:
            websocket_client.send_to_session(session_id, {
                'type': 'upload_interview_error',
                'conversation_id': conversation_id,
                'error': str(e)
            })

        return create_response(500, {'error': str(e)})


async def handle_upload_interview_continue(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process upload interview continuation request from SQS.

    This is called when a user responds to interview questions or confirms the plan.

    Args:
        event: SQS event containing session_id, email, conversation_id, user_message
        context: Lambda context

    Returns:
        Response dictionary
    """
    try:
        session_id = event.get('session_id')
        email = event.get('email')
        conversation_id = event.get('conversation_id')
        user_message = event.get('user_message', '')

        if not session_id or not email or not conversation_id:
            logger.error("[UPLOAD_INTERVIEW] Missing required fields")
            return create_response(400, {'error': 'Missing required fields: session_id, email, conversation_id'})

        logger.info(f"[UPLOAD_INTERVIEW] Continuing interview for conversation {conversation_id}")

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Load conversation state
        conversation_state = _load_conversation_state(storage_manager, email, session_id, conversation_id)

        if not conversation_state:
            logger.error(f"[UPLOAD_INTERVIEW] No conversation state found for {conversation_id}")
            return create_response(400, {'error': 'Conversation not found'})

        # Check if user is confirming (empty message or "yes" variants) and we have a pre-generated confirmation
        is_confirmation = (
            not user_message.strip() or
            user_message.strip().lower() in ['yes', 'go', 'go ahead', 'looks good', 'perfect', 'ok', 'okay']
        )

        if is_confirmation and conversation_state.get('mode') == 2 and conversation_state.get('confirmation_response'):
            # Use pre-generated confirmation response (skip redundant AI call)
            logger.info("[UPLOAD_INTERVIEW] Using pre-generated confirmation response")

            confirmation_response = conversation_state['confirmation_response']

            result = {
                'success': True,
                'mode': 3,
                'trigger_config_generation': True,
                'ai_message': confirmation_response['ai_message'],
                'config_instructions': confirmation_response['config_instructions'],
                'inferred_context': conversation_state.get('interview_context', {}),
                'confirmation_response': None
            }

            # Update conversation state messages
            interview_handler = UploadInterviewHandler(PROMPTS_DIR, SCHEMAS_DIR)
            interview_handler.messages = conversation_state.get('messages', [])
            interview_handler.interview_context = conversation_state.get('interview_context', {})

            # Add user confirmation message
            interview_handler.messages.append({
                'role': 'user',
                'content': user_message if user_message else '(Confirmed by button press)',
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })

            # Add assistant confirmation
            interview_handler.messages.append({
                'role': 'assistant',
                'content': result,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
        else:
            # Initialize interview handler and restore state
            interview_handler = UploadInterviewHandler(PROMPTS_DIR, SCHEMAS_DIR)
            interview_handler.messages = conversation_state.get('messages', [])
            interview_handler.interview_context = conversation_state.get('interview_context', {})

            # Continue interview
            result = await interview_handler.continue_interview(user_message)

            if not result['success']:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"[UPLOAD_INTERVIEW] Interview continuation failed: {error_msg}")

                # Send error via WebSocket
                if websocket_client:
                    websocket_client.send_to_session(session_id, {
                        'type': 'upload_interview_error',
                        'conversation_id': conversation_id,
                        'error': error_msg
                    })

                return create_response(500, {'error': error_msg})

        # Save updated conversation state
        conversation_state.update({
            'updated_at': datetime.utcnow().isoformat() + 'Z',
            'status': 'awaiting_approval' if result['mode'] == 2 else 'approved' if result['mode'] == 3 else 'in_progress',
            'turn_count': len(interview_handler.messages),
            'messages': interview_handler.messages,
            'interview_context': interview_handler.interview_context,
            'mode': result['mode'],
            'trigger_config_generation': result['trigger_config_generation']
        })

        # Add confirmation response and config instructions if available
        if result.get('confirmation_response'):
            conversation_state['confirmation_response'] = result['confirmation_response']
        if result.get('config_instructions'):
            conversation_state['config_instructions'] = result['config_instructions']

        _save_conversation_state(storage_manager, email, session_id, conversation_id, conversation_state)

        # Send response via WebSocket
        if websocket_client:
            websocket_message = {
                'type': 'upload_interview_update',
                'conversation_id': conversation_id,
                'mode': result['mode'],
                'ai_message': result['ai_message'],
                'inferred_context': result.get('inferred_context', {}),
                'trigger_config_generation': result['trigger_config_generation']
            }

            # Include confirmation_response for mode 2
            if result['mode'] == 2 and result.get('confirmation_response'):
                websocket_message['confirmation_response'] = result['confirmation_response']

            websocket_client.send_to_session(session_id, websocket_message)
            logger.info(f"[UPLOAD_INTERVIEW] Sent WebSocket update for mode {result['mode']}")

        # If trigger_config_generation is true, start config generation
        if result['trigger_config_generation']:
            await _trigger_config_generation(
                storage_manager=storage_manager,
                session_id=session_id,
                email=email,
                conversation_id=conversation_id,
                config_instructions=result.get('config_instructions', ''),
                inferred_context=result.get('inferred_context', {}),
                conversation_messages=interview_handler.messages
            )

        return create_response(200, {
            'success': True,
            'conversation_id': conversation_id,
            'mode': result['mode']
        })

    except Exception as e:
        logger.error(f"[UPLOAD_INTERVIEW] Error continuing interview: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # Send error via WebSocket
        if websocket_client and session_id:
            websocket_client.send_to_session(session_id, {
                'type': 'upload_interview_error',
                'conversation_id': conversation_id,
                'error': str(e)
            })

        return create_response(500, {'error': str(e)})


def _load_conversation_state(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str
) -> Optional[Dict[str, Any]]:
    """Load conversation state from S3."""
    try:
        # Path: results/{domain}/{email_prefix}/{session_id}/upload_interview/{conversation_id}/state.json
        s3_key = storage_manager.get_table_maker_path(email, session_id, conversation_id, 'state.json')
        s3_key = s3_key.replace('/table_maker/', '/upload_interview/')

        logger.info(f"[UPLOAD_INTERVIEW] Loading conversation state from {s3_key}")

        try:
            response = storage_manager.s3_client.get_object(
                Bucket=storage_manager.bucket_name,
                Key=s3_key
            )
            state_data = json.loads(response['Body'].read().decode('utf-8'))
            return state_data
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info(f"[UPLOAD_INTERVIEW] No existing conversation state found")
                return None
            raise
    except Exception as e:
        logger.error(f"[UPLOAD_INTERVIEW] Failed to load conversation state: {e}")
        return None


def _save_conversation_state(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str,
    state_data: Dict[str, Any]
) -> bool:
    """Save conversation state to S3."""
    try:
        # Path: results/{domain}/{email_prefix}/{session_id}/upload_interview/{conversation_id}/state.json
        s3_key = storage_manager.get_table_maker_path(email, session_id, conversation_id, 'state.json')
        s3_key = s3_key.replace('/table_maker/', '/upload_interview/')

        logger.info(f"[UPLOAD_INTERVIEW] Saving conversation state to {s3_key}")

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key,
            Body=json.dumps(state_data, indent=2).encode('utf-8'),
            ContentType='application/json'
        )

        return True
    except Exception as e:
        logger.error(f"[UPLOAD_INTERVIEW] Failed to save conversation state: {e}")
        return False


async def _trigger_config_generation(
    storage_manager: UnifiedS3Manager,
    session_id: str,
    email: str,
    conversation_id: str,
    config_instructions: str,
    inferred_context: Dict[str, Any],
    conversation_messages: list = None
):
    """
    Trigger config generation after interview approval.

    Args:
        storage_manager: S3 storage manager
        session_id: Session ID
        email: User email
        conversation_id: Conversation ID
        config_instructions: Detailed instructions for config generation
        inferred_context: Inferred context from interview
        conversation_messages: List of interview conversation messages to log in config
    """
    try:
        logger.info(f"[UPLOAD_INTERVIEW] Triggering config generation for session {session_id}")

        # Send WebSocket update that config generation is starting
        if websocket_client:
            websocket_client.send_to_session(session_id, {
                'type': 'config_generation_start',
                'conversation_id': conversation_id,
                'message': 'Generating validation configuration...'
            })

        # Convert upload interview message format to config generation format
        conversation_history = []
        if conversation_messages:
            for msg in conversation_messages:
                if msg.get('role') == 'user':
                    conversation_history.append({
                        'entry_type': 'user_input',
                        'user_instructions': msg.get('content', ''),
                        'timestamp': msg.get('timestamp', datetime.utcnow().isoformat() + 'Z'),
                        'source': 'upload_interview'
                    })
                elif msg.get('role') == 'assistant':
                    # Extract AI message from structured response if present
                    content = msg.get('content', {})
                    ai_message = content.get('ai_message', str(content)) if isinstance(content, dict) else str(content)
                    conversation_history.append({
                        'entry_type': 'ai_response',
                        'instructions': ai_message,
                        'timestamp': msg.get('timestamp', datetime.utcnow().isoformat() + 'Z'),
                        'source': 'upload_interview'
                    })
            logger.info(f"[UPLOAD_INTERVIEW] Converted {len(conversation_messages)} messages to config history format")

        # Send config generation request to SQS
        from interface_lambda.core.sqs_service import send_config_generation_request

        config_request = {
            'session_id': session_id,
            'email': email,
            'instructions': config_instructions,
            'interview_context': inferred_context,
            'conversation_history': conversation_history,
            'source': 'upload_interview',
            'conversation_id': conversation_id
        }

        message_id = send_config_generation_request(config_request)

        if message_id:
            logger.info(f"[UPLOAD_INTERVIEW] Config generation queued: {message_id}")
        else:
            logger.error("[UPLOAD_INTERVIEW] Failed to queue config generation")

            if websocket_client:
                websocket_client.send_to_session(session_id, {
                    'type': 'upload_interview_error',
                    'conversation_id': conversation_id,
                    'error': 'Failed to start config generation'
                })

    except Exception as e:
        logger.error(f"[UPLOAD_INTERVIEW] Error triggering config generation: {e}")
        import traceback
        logger.error(traceback.format_exc())
