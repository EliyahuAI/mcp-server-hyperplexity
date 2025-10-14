"""
Table Maker Conversation Handler for Lambda Environment.

This module adapts the standalone TableConversationHandler for lambda integration,
using S3 storage and WebSocket updates instead of local files.

Key differences from standalone:
1. Uses UnifiedS3Manager for conversation state storage (not local files)
2. Creates runs database entries to track operations
3. Sends WebSocket updates for real-time feedback
4. Loads configuration from table_maker/table_maker_config.json
5. Integrates with existing lambda infrastructure (not standalone)

REUSES existing patterns:
- TableConversationHandler from table_maker/src/conversation_handler.py
- config_change_log pattern from generate_config_unified.py
- instructions field for user messages
- ai_summary, clarifying_questions, reasoning for AI responses
"""

import logging
import json
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

# Lambda imports
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response
from dynamodb_schemas import create_run_record, update_run_status

# Table maker imports (packaged with lambda)
from table_maker.src.conversation_handler import TableConversationHandler
from table_maker.src.prompt_loader import PromptLoader
from table_maker.src.schema_validator import SchemaValidator

# Shared imports
from ai_api_client import AIAPIClient

# WebSocket client for real-time updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger = logging.getLogger()
    logger.warning("WebSocket client not available for table maker")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _load_table_maker_config() -> Dict[str, Any]:
    """
    Load table maker configuration from table_maker/table_maker_config.json.

    Returns:
        Configuration dictionary with conversation, preview, and feature settings
    """
    try:
        # Path is relative to lambda package root
        config_path = Path(__file__).parent.parent.parent.parent / "table_maker" / "table_maker_config.json"

        if not config_path.exists():
            logger.warning(f"Table maker config not found at {config_path}, using defaults")
            return _get_default_config()

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        logger.info("Loaded table maker configuration successfully")
        return config

    except Exception as e:
        logger.error(f"Error loading table maker config: {e}, using defaults")
        return _get_default_config()


def _get_default_config() -> Dict[str, Any]:
    """
    Get default table maker configuration as fallback.

    Returns:
        Default configuration dictionary
    """
    return {
        "conversation": {
            "model": "claude-sonnet-4-5",
            "max_turns_before_preview": 3,
            "min_turns_before_preview": 1,
            "readiness_threshold": 0.75,
            "max_tokens": 8000,
            "use_web_search_for_context": True,
            "context_web_searches": 3
        },
        "preview_generation": {
            "sample_row_count": 3,
            "model": "claude-sonnet-4-5",
            "max_tokens": 12000,
            "search_context": "high"
        },
        "full_table_generation": {
            "default_row_count": 20,
            "model": "claude-sonnet-4-5",
            "max_tokens": 16000,
            "batch_size": 10
        },
        "models": {
            "conversation": "claude-sonnet-4-5",
            "preview": "claude-sonnet-4-5",
            "expansion": "claude-sonnet-4-5"
        },
        "features": {
            "enable_column_definitions_in_csv": True,
            "remove_definitions_for_validation": True,
            "enable_context_research": True,
            "show_id_columns_in_blue_circles": True
        }
    }


def _generate_conversation_id() -> str:
    """
    Generate unique conversation ID for table maker session.

    Returns:
        Conversation ID string
    """
    import uuid
    return f"table_conv_{uuid.uuid4().hex[:12]}"


def _save_conversation_state_to_s3(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str,
    conversation_state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Save conversation state to S3 unified storage.

    Args:
        storage_manager: UnifiedS3Manager instance
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        conversation_state: Complete conversation state dictionary

    Returns:
        Dictionary with save results: {'success': bool, 's3_key': str, 'error': str}
    """
    try:
        # Store in table_maker subfolder: email/domain/session_id/table_maker/conversation_{conv_id}.json
        session_path = storage_manager.get_session_path(email, session_id)
        s3_key = f"{session_path}table_maker/conversation_{conversation_id}.json"

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key,
            Body=json.dumps(conversation_state, indent=2, ensure_ascii=False),
            ContentType='application/json'
        )

        logger.info(f"Saved conversation state to S3: {s3_key}")
        return {'success': True, 's3_key': s3_key, 'error': None}

    except Exception as e:
        error_msg = f"Error saving conversation state to S3: {e}"
        logger.error(error_msg)
        return {'success': False, 's3_key': None, 'error': error_msg}


def _load_conversation_state_from_s3(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str
) -> Optional[Dict[str, Any]]:
    """
    Load conversation state from S3 unified storage.

    Args:
        storage_manager: UnifiedS3Manager instance
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier

    Returns:
        Conversation state dictionary or None if not found
    """
    try:
        session_path = storage_manager.get_session_path(email, session_id)
        s3_key = f"{session_path}table_maker/conversation_{conversation_id}.json"

        response = storage_manager.s3_client.get_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key
        )

        conversation_state = json.loads(response['Body'].read().decode('utf-8'))
        logger.info(f"Loaded conversation state from S3: {s3_key}")
        return conversation_state

    except storage_manager.s3_client.exceptions.NoSuchKey:
        logger.warning(f"Conversation state not found in S3: {conversation_id}")
        return None
    except Exception as e:
        logger.error(f"Error loading conversation state from S3: {e}")
        return None


async def handle_table_conversation_start(request_data, context):
    """
    Start a new table design conversation.

    This handler:
    1. Creates a new conversation_id
    2. Loads table_maker_config.json
    3. Creates runs database entry for tracking
    4. Initializes TableConversationHandler with user's initial message
    5. Stores conversation state in S3
    6. Returns AI response via WebSocket

    Args:
        request_data: {
            'action': 'startTableConversation',
            'email': 'user@example.com',
            'session_id': 'session_20251013_123456',
            'user_message': 'Create a table to track AI research papers...'
        }
        context: Lambda context

    Returns:
        {
            'success': True,
            'conversation_id': 'table_conv_abc123',
            'ai_message': 'I'll help you create...',
            'clarifying_questions': '...',
            'reasoning': 'AI explanation of approach',
            'ready_to_generate': False,
            'turn_count': 1,
            'proposed_table': {...},
            'error': None
        }
    """
    result = {
        'success': False,
        'conversation_id': None,
        'ai_message': '',
        'clarifying_questions': '',
        'reasoning': '',
        'ready_to_generate': False,
        'turn_count': 0,
        'proposed_table': None,
        'error': None
    }

    try:
        # Extract parameters
        email = request_data.get('email')
        session_id = request_data.get('session_id')
        user_message = request_data.get('user_message', '')

        if not email or not session_id:
            result['error'] = 'Missing email or session_id'
            return create_response(400, result)

        if not user_message.strip():
            result['error'] = 'Missing user_message'
            return create_response(400, result)

        logger.info(f"[TABLE_MAKER] Starting conversation for session {session_id}: '{user_message[:50]}...'")

        # Load table maker configuration
        config = _load_table_maker_config()
        conversation_config = config.get('conversation', {})

        # Generate conversation ID
        conversation_id = _generate_conversation_id()
        result['conversation_id'] = conversation_id

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Create runs database entry for table generation tracking
        logger.info(f"[TABLE_MAKER] Creating run record for table conversation")
        try:
            run_key = create_run_record(
                session_id=session_id,
                email=email,
                total_rows=0,  # Preview will have 3 rows
                batch_size=1,
                run_type="Table Generation"
            )
            logger.info(f"[TABLE_MAKER] Created run record with run_key: {run_key}")

            update_run_status(
                session_id=session_id,
                run_key=run_key,
                status='IN_PROGRESS',
                run_type="Table Generation",
                verbose_status="Table conversation starting...",
                percent_complete=5,
                processed_rows=0,
                total_rows=0,
                input_table_name=f"table_{conversation_id}",
                account_current_balance=0,
                account_sufficient_balance="n/a",
                account_credits_needed="n/a",
                account_domain_multiplier=1.0,
                models="TBD",
                batch_size=1,
                eliyahu_cost=0.0,
                time_per_row_seconds=0.0
            )
        except Exception as e:
            logger.warning(f"[TABLE_MAKER] Failed to create run record: {e}")
            run_key = None

        # Send initial progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_conversation_update',
                    'conversation_id': conversation_id,
                    'progress': 10,
                    'status': 'Starting conversation...'
                })
            except Exception as e:
                logger.warning(f"[TABLE_MAKER] Failed to send WebSocket update: {e}")

        # Initialize AI client, prompt loader, and schema validator
        ai_client = AIAPIClient()

        # Paths are relative to lambda package root
        base_path = Path(__file__).parent.parent.parent.parent / "table_maker"
        prompt_loader = PromptLoader(str(base_path / "prompts"))
        schema_validator = SchemaValidator(str(base_path / "schemas"))

        # Initialize conversation handler (REUSE existing class)
        conversation_handler = TableConversationHandler(
            ai_client=ai_client,
            prompt_loader=prompt_loader,
            schema_validator=schema_validator
        )

        # Send progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_conversation_update',
                    'conversation_id': conversation_id,
                    'progress': 30,
                    'status': 'Analyzing your request...'
                })
            except Exception as e:
                logger.warning(f"[TABLE_MAKER] Failed to send WebSocket update: {e}")

        # Start conversation with user message
        model = conversation_config.get('model', 'claude-sonnet-4-5')
        logger.info(f"[TABLE_MAKER] Calling conversation handler with model: {model}")

        conversation_result = await conversation_handler.start_conversation(
            user_message=user_message,
            model=model,
            conversation_id=conversation_id
        )

        if not conversation_result['success']:
            result['error'] = conversation_result.get('error', 'Conversation initialization failed')
            logger.error(f"[TABLE_MAKER] Conversation start failed: {result['error']}")

            # Update runs database with failure
            if run_key:
                try:
                    update_run_status(
                        session_id=session_id,
                        run_key=run_key,
                        status='FAILED',
                        run_type="Table Generation",
                        verbose_status="Conversation start failed",
                        percent_complete=0,
                        error_message=result['error']
                    )
                except Exception as e:
                    logger.error(f"[TABLE_MAKER] Failed to update run status: {e}")

            return create_response(500, result)

        # Extract AI response
        ai_response = conversation_result.get('ai_response', {})
        result['success'] = True
        result['ai_message'] = ai_response.get('ai_message', '')
        result['clarifying_questions'] = ai_response.get('clarifying_questions', '')
        result['reasoning'] = ai_response.get('reasoning', '')
        result['ready_to_generate'] = conversation_result.get('ready_to_generate', False)
        result['turn_count'] = 1
        result['proposed_table'] = conversation_result.get('proposed_table')

        # Build conversation state for S3 storage (following config_change_log pattern)
        conversation_state = {
            'conversation_id': conversation_id,
            'session_id': session_id,
            'email': email,
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'status': 'preview_ready' if result['ready_to_generate'] else 'in_progress',
            'turn_count': 1,
            'run_key': run_key,
            'config': config,  # Store config for reference
            'messages': conversation_handler.get_conversation_history(),
            'current_proposal': result['proposed_table'],
            'ready_to_generate': result['ready_to_generate']
        }

        # Save conversation state to S3
        save_result = _save_conversation_state_to_s3(
            storage_manager=storage_manager,
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            conversation_state=conversation_state
        )

        if not save_result['success']:
            logger.warning(f"[TABLE_MAKER] Failed to save conversation state: {save_result['error']}")

        # Send progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_conversation_update',
                    'conversation_id': conversation_id,
                    'progress': 100,
                    'status': 'Conversation started successfully',
                    'ai_message': result['ai_message'],
                    'clarifying_questions': result['clarifying_questions'],
                    'reasoning': result['reasoning'],
                    'ready_to_generate': result['ready_to_generate'],
                    'turn_count': result['turn_count'],
                    'proposed_table': result['proposed_table']
                })
            except Exception as e:
                logger.warning(f"[TABLE_MAKER] Failed to send WebSocket update: {e}")

        # Update runs database with progress
        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='IN_PROGRESS',
                    run_type="Table Generation",
                    verbose_status="Conversation turn 1 complete",
                    percent_complete=20,
                    models=model
                )
            except Exception as e:
                logger.error(f"[TABLE_MAKER] Failed to update run status: {e}")

        logger.info(f"[TABLE_MAKER] Conversation started successfully: {conversation_id}")
        return create_response(200, result)

    except Exception as e:
        error_msg = f"Error starting table conversation: {str(e)}"
        logger.error(f"[TABLE_MAKER] {error_msg}")
        import traceback
        logger.error(f"[TABLE_MAKER] Traceback: {traceback.format_exc()}")
        result['error'] = error_msg
        return create_response(500, result)


async def handle_table_conversation_continue(request_data, context):
    """
    Continue an existing table design conversation.

    This handler:
    1. Loads conversation state from S3
    2. Continues conversation with user's new message
    3. Checks readiness threshold for preview generation
    4. Stores updated conversation state in S3
    5. Returns AI response via WebSocket

    Args:
        request_data: {
            'action': 'continueTableConversation',
            'email': 'user@example.com',
            'session_id': 'session_20251013_123456',
            'conversation_id': 'table_conv_abc123',
            'user_message': 'Focus on NLP papers with citations...'
        }
        context: Lambda context

    Returns:
        {
            'success': True,
            'conversation_id': 'table_conv_abc123',
            'ai_message': '...',
            'clarifying_questions': '...',
            'reasoning': '...',
            'ready_to_generate': True,
            'turn_count': 2,
            'proposed_table': {...},
            'error': None
        }
    """
    result = {
        'success': False,
        'conversation_id': None,
        'ai_message': '',
        'clarifying_questions': '',
        'reasoning': '',
        'ready_to_generate': False,
        'turn_count': 0,
        'proposed_table': None,
        'error': None
    }

    try:
        # Extract parameters
        email = request_data.get('email')
        session_id = request_data.get('session_id')
        conversation_id = request_data.get('conversation_id')
        user_message = request_data.get('user_message', '')

        if not email or not session_id or not conversation_id:
            result['error'] = 'Missing email, session_id, or conversation_id'
            return create_response(400, result)

        if not user_message.strip():
            result['error'] = 'Missing user_message'
            return create_response(400, result)

        result['conversation_id'] = conversation_id

        logger.info(f"[TABLE_MAKER] Continuing conversation {conversation_id}: '{user_message[:50]}...'")

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Load conversation state from S3
        conversation_state = _load_conversation_state_from_s3(
            storage_manager=storage_manager,
            email=email,
            session_id=session_id,
            conversation_id=conversation_id
        )

        if not conversation_state:
            result['error'] = f'Conversation {conversation_id} not found'
            logger.error(f"[TABLE_MAKER] {result['error']}")
            return create_response(404, result)

        # Get run_key for database tracking
        run_key = conversation_state.get('run_key')

        # Send initial progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_conversation_update',
                    'conversation_id': conversation_id,
                    'progress': 10,
                    'status': 'Continuing conversation...'
                })
            except Exception as e:
                logger.warning(f"[TABLE_MAKER] Failed to send WebSocket update: {e}")

        # Initialize AI client, prompt loader, and schema validator
        ai_client = AIAPIClient()
        base_path = Path(__file__).parent.parent.parent.parent / "table_maker"
        prompt_loader = PromptLoader(str(base_path / "prompts"))
        schema_validator = SchemaValidator(str(base_path / "schemas"))

        # Initialize conversation handler and restore state (REUSE existing class)
        conversation_handler = TableConversationHandler(
            ai_client=ai_client,
            prompt_loader=prompt_loader,
            schema_validator=schema_validator
        )

        # Restore conversation state
        conversation_handler.conversation_id = conversation_state['conversation_id']
        conversation_handler.conversation_log = conversation_state['messages']
        conversation_handler.current_proposal = conversation_state['current_proposal']
        conversation_handler.is_initialized = True

        logger.info(f"[TABLE_MAKER] Restored conversation with {len(conversation_handler.conversation_log)} messages")

        # Send progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_conversation_update',
                    'conversation_id': conversation_id,
                    'progress': 30,
                    'status': 'Analyzing your feedback...'
                })
            except Exception as e:
                logger.warning(f"[TABLE_MAKER] Failed to send WebSocket update: {e}")

        # Continue conversation with user message
        config = conversation_state.get('config', _load_table_maker_config())
        conversation_config = config.get('conversation', {})
        model = conversation_config.get('model', 'claude-sonnet-4-5')

        logger.info(f"[TABLE_MAKER] Calling conversation handler to continue with model: {model}")

        conversation_result = await conversation_handler.continue_conversation(
            user_message=user_message,
            model=model
        )

        if not conversation_result['success']:
            result['error'] = conversation_result.get('error', 'Conversation continuation failed')
            logger.error(f"[TABLE_MAKER] Conversation continue failed: {result['error']}")

            # Update runs database with failure
            if run_key:
                try:
                    update_run_status(
                        session_id=session_id,
                        run_key=run_key,
                        status='FAILED',
                        run_type="Table Generation",
                        verbose_status="Conversation continuation failed",
                        percent_complete=0,
                        error_message=result['error']
                    )
                except Exception as e:
                    logger.error(f"[TABLE_MAKER] Failed to update run status: {e}")

            return create_response(500, result)

        # Extract AI response
        ai_response = conversation_result.get('ai_response', {})
        result['success'] = True
        result['ai_message'] = ai_response.get('ai_message', '')
        result['clarifying_questions'] = ai_response.get('clarifying_questions', '')
        result['reasoning'] = ai_response.get('reasoning', '')
        result['ready_to_generate'] = conversation_result.get('ready_to_generate', False)
        result['turn_count'] = conversation_state['turn_count'] + 1
        result['proposed_table'] = conversation_result.get('proposed_table')

        # Update conversation state
        conversation_state['last_updated'] = datetime.utcnow().isoformat() + 'Z'
        conversation_state['status'] = 'preview_ready' if result['ready_to_generate'] else 'in_progress'
        conversation_state['turn_count'] = result['turn_count']
        conversation_state['messages'] = conversation_handler.get_conversation_history()
        conversation_state['current_proposal'] = result['proposed_table']
        conversation_state['ready_to_generate'] = result['ready_to_generate']

        # Save updated conversation state to S3
        save_result = _save_conversation_state_to_s3(
            storage_manager=storage_manager,
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            conversation_state=conversation_state
        )

        if not save_result['success']:
            logger.warning(f"[TABLE_MAKER] Failed to save updated conversation state: {save_result['error']}")

        # Send progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_conversation_update',
                    'conversation_id': conversation_id,
                    'progress': 100,
                    'status': f'Turn {result["turn_count"]} complete',
                    'ai_message': result['ai_message'],
                    'clarifying_questions': result['clarifying_questions'],
                    'reasoning': result['reasoning'],
                    'ready_to_generate': result['ready_to_generate'],
                    'turn_count': result['turn_count'],
                    'proposed_table': result['proposed_table']
                })
            except Exception as e:
                logger.warning(f"[TABLE_MAKER] Failed to send WebSocket update: {e}")

        # Update runs database with progress
        if run_key:
            try:
                status_msg = "Ready for preview generation" if result['ready_to_generate'] else f"Conversation turn {result['turn_count']} complete"
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='IN_PROGRESS',
                    run_type="Table Generation",
                    verbose_status=status_msg,
                    percent_complete=20 + (result['turn_count'] * 10),
                    models=model
                )
            except Exception as e:
                logger.error(f"[TABLE_MAKER] Failed to update run status: {e}")

        logger.info(f"[TABLE_MAKER] Conversation continued successfully: {conversation_id}, turn {result['turn_count']}")
        return create_response(200, result)

    except Exception as e:
        error_msg = f"Error continuing table conversation: {str(e)}"
        logger.error(f"[TABLE_MAKER] {error_msg}")
        import traceback
        logger.error(f"[TABLE_MAKER] Traceback: {traceback.format_exc()}")
        result['error'] = error_msg
        return create_response(500, result)
