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

# Lambda imports
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response
from interface_lambda.core.sqs_service import send_table_conversation_request
from dynamodb_schemas import create_run_record, update_run_status

# Table maker imports (packaged with lambda)
from .table_maker_lib.conversation_handler import TableConversationHandler
from .table_maker_lib.prompt_loader import PromptLoader
from .table_maker_lib.schema_validator import SchemaValidator
from .interview import TableInterviewHandler

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


def _send_interview_progress(session_id: str, conversation_id: str, turn_number: int) -> None:
    """
    Send dummy progress messages during interview phase to keep user engaged.

    These are purely cosmetic updates to show the system is working during the interview.
    They do NOT represent actual execution progress (which uses phase='execution').

    Progress messages:
    - Turn 1: "Understanding your table requirements..." (10%)
    - Turn 2: "Analyzing table structure..." (25%)
    - Turn 3: "Table concept ready. Approve to generate..." (40%)

    Args:
        session_id: Session identifier
        conversation_id: Conversation identifier
        turn_number: Current turn number (1, 2, 3, etc.)
    """
    if not websocket_client or not session_id:
        return

    # Only send progress for turns 1-3
    if turn_number not in [1, 2, 3]:
        return

    progress_messages = {
        1: {"message": "Understanding your table requirements...", "progress": 10},
        2: {"message": "Analyzing table structure...", "progress": 25},
        3: {"message": "Table concept ready. Approve to generate...", "progress": 40}
    }

    progress_info = progress_messages.get(turn_number)
    if not progress_info:
        return

    try:
        websocket_client.send_to_session(session_id, {
            'type': 'table_interview_progress',
            'conversation_id': conversation_id,
            'phase': 'interview',  # Distinguish from execution progress
            'status': progress_info['message'],
            'progress_percent': progress_info['progress'],
            'turn_number': turn_number
        })
        logger.info(f"[TABLE_MAKER] Sent interview progress for turn {turn_number}: {progress_info['message']}")
    except Exception as e:
        logger.warning(f"[TABLE_MAKER] Failed to send interview progress: {e}")


def _add_api_call_to_runs(
    session_id: str,
    run_key: Optional[str],
    api_response: Dict[str, Any],
    model: str,
    processing_time: float,
    call_type: str,
    status: str = 'IN_PROGRESS',
    verbose_status: str = None,
    percent_complete: int = None
) -> None:
    """
    Add a single API call's metrics to the runs database, aggregating with existing calls.

    This is the SINGLE function used by ALL table maker operations (interview, preview, etc.)
    to incrementally update runs metrics.

    Flow:
    1. READ existing run record
    2. Extract existing call_metrics_list and models list
    3. Add new call metrics (tagged with call_type)
    4. Build model entry (extracts max_web_searches from enhanced_data)
    5. Re-aggregate ALL calls
    6. WRITE back to database

    Args:
        session_id: Session identifier
        run_key: Run tracking key
        api_response: API response dict from call_structured_api with structure:
            {'response': <API response>, 'token_usage': {...}, 'processing_time': ...,
             'is_cached': ..., 'enhanced_data': {...}}
        model: Model name used
        processing_time: Processing time in seconds
        call_type: Type of call (e.g., 'interview', 'preview', 'expansion')
        status: Run status (default: IN_PROGRESS)
        verbose_status: Human-readable status
        percent_complete: Progress percentage (optional)
    """
    if not run_key:
        logger.warning("[TABLE_MAKER] No run_key provided, skipping metrics update")
        return

    try:
        from dynamodb_schemas import get_run_status

        # Step 1: READ existing run record
        existing_run = get_run_status(session_id, run_key)

        # Step 2: Extract existing call_metrics_list and models list (if any)
        existing_call_metrics = []
        existing_models_list = []
        logger.info(f"[TABLE_MAKER] Read existing run: exists={existing_run is not None}, keys={list(existing_run.keys()) if existing_run else 'None'}")
        if existing_run:
            logger.info(f"[TABLE_MAKER] Has call_metrics_list={'call_metrics_list' in existing_run}, Has models={'models' in existing_run}")
            if 'call_metrics_list' in existing_run:
                existing_call_metrics = existing_run.get('call_metrics_list', [])
                logger.info(f"[TABLE_MAKER] Found {len(existing_call_metrics)} existing API calls in runs database")
            else:
                logger.warning(f"[TABLE_MAKER] No call_metrics_list in existing run record")
            if 'models' in existing_run and isinstance(existing_run['models'], list):
                existing_models_list = existing_run['models']
        else:
            logger.warning(f"[TABLE_MAKER] No existing run found for session_id={session_id}, run_key={run_key}")

        # Step 3: Add NEW call metrics with call_type tag
        # Use enhanced_data directly from call_structured_api response (already computed)
        # If not available, regenerate it using get_enhanced_call_metrics
        if 'enhanced_data' in api_response and api_response['enhanced_data']:
            new_call_metrics = api_response['enhanced_data']
            logger.debug(f"[TABLE_MAKER] Using pre-computed enhanced_data from API response")
        else:
            # Fallback: regenerate enhanced metrics if not present
            logger.warning(f"[TABLE_MAKER] enhanced_data not found in api_response, regenerating...")
            ai_client = AIAPIClient()
            new_call_metrics = ai_client.get_enhanced_call_metrics(
                response=api_response.get('response', api_response),
                model=model,
                processing_time=processing_time,
                pre_extracted_token_usage=api_response.get('token_usage'),
                is_cached=api_response.get('is_cached')
            )

        # Tag with call type for tracking
        new_call_metrics['call_type'] = call_type
        existing_call_metrics.append(new_call_metrics)

        # Extract max_web_searches from enhanced data (automatically embedded by get_enhanced_call_metrics)
        max_web_searches_value = new_call_metrics.get('call_info', {}).get('max_web_searches', 0)

        # Build model entry with web search info
        model_entry = {
            'model': model,
            'call_type': call_type,
            'max_web_searches': max_web_searches_value,
            'is_cached': api_response.get('is_cached', False)
        }
        existing_models_list.append(model_entry)

        logger.info(f"[TABLE_MAKER] Added new {call_type} call metrics for {model}, total calls: {len(existing_call_metrics)}")

        # Step 4: Re-aggregate ALL calls
        aggregated = AIAPIClient.aggregate_provider_metrics(existing_call_metrics)
        providers = aggregated.get('providers', {})
        totals = aggregated.get('totals', {})

        # Step 5: WRITE back to database with aggregated metrics
        # Sum of actual costs across all providers and calls
        total_actual_cost = totals.get('total_cost_actual', 0.0)
        # Sum of estimated costs (no cache) across all providers and calls
        total_estimated_cost = totals.get('total_cost_estimated', 0.0)
        # Sum of actual processing times across all calls
        total_actual_time = totals.get('total_actual_processing_time', 0.0)
        # Total number of API calls made
        total_calls = totals.get('total_calls', 0)

        # Build run_type with operation details
        # Format: "Table Generation (Interview, Interview, Preview Generation)"
        call_type_names = {
            'interview': 'Interview',
            'preview': 'Preview Generation',
            'expansion': 'Expansion',
            'refinement': 'Refinement'
        }
        operation_sequence = ', '.join([call_type_names.get(c.get('call_type'), c.get('call_type', 'Unknown'))
                                       for c in existing_call_metrics])
        run_type = f"Table Generation ({operation_sequence})" if operation_sequence else "Table Generation"

        update_params = {
            'session_id': session_id,
            'run_key': run_key,
            'status': status,
            'run_type': run_type,  # Includes operation sequence
            'verbose_status': verbose_status or f"Completed {total_calls} API calls",
            'models': existing_models_list,  # List of model entries with web search info
            # Aggregate actual cost across all providers and calls (what we actually paid)
            'eliyahu_cost': total_actual_cost,
            'provider_metrics': providers,
            # Total actual cost paid (should equal eliyahu_cost)
            'total_provider_cost_actual': total_actual_cost,
            # Total estimated cost without caching benefits
            'total_provider_cost_estimated': total_estimated_cost,
            'total_provider_tokens': totals.get('total_tokens', 0),
            # Total number of API calls made
            'total_provider_calls': total_calls,
            # Overall cache efficiency percentage
            'overall_cache_efficiency_percent': totals.get('overall_cache_efficiency', 0.0),
            # Sum of actual processing times across all calls
            'actual_processing_time_seconds': total_actual_time,
            # Sum of actual run times (same as actual_processing_time_seconds)
            'run_time_s': total_actual_time,
            # Average time per call (not per row for table maker)
            'time_per_row_seconds': total_actual_time / max(total_calls, 1),
            # Store ALL enhanced data for debugging and analysis
            'call_metrics_list': existing_call_metrics,  # Full list with all call details
            'enhanced_metrics_aggregated': aggregated,  # Complete aggregated structure
            'table_maker_breakdown': {
                'interview_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'interview']),
                'preview_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'preview']),
                'expansion_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'expansion']),
                'total_calls': len(existing_call_metrics)
            }
        }

        if percent_complete is not None:
            update_params['percent_complete'] = percent_complete

        update_run_status(**update_params)

        logger.info(f"[TABLE_MAKER] Updated runs database: {totals.get('total_calls', 0)} total calls, ${totals.get('total_cost_actual', 0.0):.6f} total cost")
        logger.info(f"[TABLE_MAKER] Stored enhanced metrics: {len(existing_call_metrics)} call details, {len(providers)} providers")

    except Exception as e:
        logger.error(f"[TABLE_MAKER] Failed to add API call to runs: {e}")
        import traceback
        logger.error(f"[TABLE_MAKER] Traceback: {traceback.format_exc()}")


# ============================================================================
# ASYNC WRAPPERS - Queue to SQS and return immediately
# ============================================================================

def handle_table_conversation_start_async(request_data, context):
    """
    Async wrapper for starting table conversation - queues to SQS and returns immediately.
    Results will be sent via WebSocket.
    """
    try:
        email = request_data.get('email')
        session_id = request_data.get('session_id')
        user_message = request_data.get('user_message', '')

        if not email:
            return create_response(400, {'error': 'Missing email'})

        # Generate session ID if not provided
        if not session_id:
            import uuid
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            random_hex = uuid.uuid4().hex[:8]
            session_id = f"session_{timestamp}_{random_hex}"
            logger.info(f"[TABLE_MAKER] Generated new session ID: {session_id}")

        if not user_message.strip():
            return create_response(400, {'error': 'Missing user_message'})

        # Generate conversation ID
        conversation_id = f"table_conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{session_id[-6:]}"

        # Send to SQS for background processing
        conversation_request = {
            'action': 'startTableConversation',
            'email': email,
            'session_id': session_id,
            'user_message': user_message,
            'conversation_id': conversation_id,
            'timestamp': datetime.now().isoformat()
        }

        logger.info(f"Queueing table conversation start request: {conversation_id}")
        message_id = send_table_conversation_request(conversation_request)

        if not message_id:
            return create_response(500, {'error': 'Failed to queue table conversation request'})

        logger.info(f"Table conversation request queued successfully: {message_id}")

        # Return immediately - results will come via WebSocket
        response_body = {
            'success': True,
            'status': 'processing',
            'conversation_id': conversation_id,
            'session_id': session_id  # Return session_id for frontend tracking
        }

        logger.info(f"✅ ASYNC TABLE CONVERSATION RESPONSE (WebSocket-only): {response_body}")
        return create_response(200, response_body)

    except Exception as e:
        logger.error(f"Async table conversation start failed: {str(e)}")
        return create_response(500, {'success': False, 'error': str(e)})


def handle_table_conversation_continue_async(request_data, context):
    """
    Async wrapper for continuing table conversation - queues to SQS and returns immediately.
    Results will be sent via WebSocket.
    """
    try:
        email = request_data.get('email')
        session_id = request_data.get('session_id')
        conversation_id = request_data.get('conversation_id')
        user_message = request_data.get('user_message', '')

        if not email:
            return create_response(400, {'error': 'Missing email'})

        # Generate session ID if not provided (shouldn't happen for continue, but safety check)
        if not session_id:
            import uuid
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            random_hex = uuid.uuid4().hex[:8]
            session_id = f"session_{timestamp}_{random_hex}"
            logger.warning(f"[TABLE_MAKER] Had to generate session ID for continue: {session_id}")

        if not conversation_id:
            return create_response(400, {'error': 'Missing conversation_id'})

        if not user_message.strip():
            return create_response(400, {'error': 'Missing user_message'})

        # Send to SQS for background processing
        conversation_request = {
            'action': 'continueTableConversation',
            'email': email,
            'session_id': session_id,
            'conversation_id': conversation_id,
            'user_message': user_message,
            'timestamp': datetime.now().isoformat()
        }

        logger.info(f"Queueing table conversation continue request: {conversation_id}")
        message_id = send_table_conversation_request(conversation_request)

        if not message_id:
            return create_response(500, {'error': 'Failed to queue table conversation request'})

        logger.info(f"Table conversation continue request queued successfully: {message_id}")

        # Return immediately - results will come via WebSocket
        response_body = {
            'success': True,
            'status': 'processing',
            'conversation_id': conversation_id
        }

        logger.info(f"✅ ASYNC TABLE CONVERSATION CONTINUE RESPONSE (WebSocket-only): {response_body}")
        return create_response(200, response_body)

    except Exception as e:
        logger.error(f"Async table conversation continue failed: {str(e)}")
        return create_response(500, {'success': False, 'error': str(e)})


# ============================================================================
# SYNC HANDLERS - Do the actual work (called by background processor)
# ============================================================================

def _load_table_maker_config() -> Dict[str, Any]:
    """
    Load table maker configuration from table_maker/table_maker_config.json.

    Returns:
        Configuration dictionary with conversation, preview, and feature settings
    """
    try:
        # Use local config file
        config_path = os.path.join(os.path.dirname(__file__), 'table_maker_config.json')

        if not os.path.exists(config_path):
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
        # Use get_table_maker_path for consistency with execution.py
        s3_key = storage_manager.get_table_maker_path(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            file_name='conversation_state.json'
        )

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
        # Use get_table_maker_path for consistency
        s3_key = storage_manager.get_table_maker_path(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            file_name='conversation_state.json'
        )

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


async def _trigger_execution(
    email: str,
    session_id: str,
    conversation_id: str,
    conversation_state: Dict[str, Any],
    run_key: Optional[str]
) -> None:
    """
    Trigger Independent Row Discovery pipeline when interview is complete.

    This is the entry point to Phase 2 of the two-phase workflow.
    Once the user approves the table concept during the interview, this function
    executes the complete 4-step pipeline (1-3 minutes):
    1. Column Definition - Define columns and search strategy with subdomains
    2. Row Discovery - Progressive escalation (sonar -> sonar-pro) across subdomains
    3. Consolidation - Deduplicate and score discovered rows
    4. QC Review - Final quality control and prioritization

    Since we're already running in the background processor, we can call
    execution directly without queueing to SQS again.

    Args:
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        conversation_state: Complete conversation state with interview_context
        run_key: Run tracking key (optional)
    """
    logger.info(f"[TABLE_MAKER] Triggering Independent Row Discovery for {conversation_id}")

    # Import execution orchestrator
    from .execution import execute_full_table_generation

    # Send initial execution start message via WebSocket
    if websocket_client and session_id:
        try:
            websocket_client.send_to_session(session_id, {
                'type': 'table_execution_update',
                'conversation_id': conversation_id,
                'status': 'Starting Independent Row Discovery pipeline (1-3 minutes)...',
                'estimated_duration_seconds': 120,
                'current_step': 0,
                'total_steps': 4,
                'progress_percent': 0,
                'steps': [
                    'Column Definition',
                    'Row Discovery (Progressive Escalation)',
                    'Consolidation',
                    'QC Review'
                ]
            })
            logger.info(f"[TABLE_MAKER] Sent execution start message via WebSocket")
        except Exception as e:
            logger.warning(f"[TABLE_MAKER] Failed to send execution start message: {e}")

    # Execute full table generation pipeline
    try:
        execution_result = await execute_full_table_generation(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            run_key=run_key
        )

        logger.info(f"[TABLE_MAKER] Execution pipeline complete. Success: {execution_result.get('success')}")

        # Send completion message via WebSocket
        if execution_result['success']:
            if websocket_client and session_id:
                try:
                    completion_message = {
                        'type': 'table_execution_complete',
                        'conversation_id': conversation_id,
                        'status': 'Independent Row Discovery complete',
                        'table_name': execution_result.get('table_name'),
                        'row_count': execution_result.get('row_count', 0),
                        'approved_rows': execution_result.get('approved_rows', [])
                    }
                    websocket_client.send_to_session(session_id, completion_message)
                    logger.info(f"[TABLE_MAKER] Sent execution completion message via WebSocket")
                except Exception as ws_error:
                    logger.error(f"[TABLE_MAKER] Failed to send execution completion via WebSocket: {ws_error}")
                    import traceback
                    logger.error(f"[TABLE_MAKER] WebSocket error traceback: {traceback.format_exc()}")
        else:
            # Execution failed - send error message
            error_msg = execution_result.get('error', 'Unknown execution error')
            logger.error(f"[TABLE_MAKER] Execution failed: {error_msg}")

            if websocket_client and session_id:
                try:
                    websocket_client.send_to_session(session_id, {
                        'type': 'table_execution_error',
                        'conversation_id': conversation_id,
                        'status': 'Execution failed',
                        'error': error_msg,
                        'failed_at_step': execution_result.get('failed_at_step')
                    })
                except Exception as ws_error:
                    logger.warning(f"[TABLE_MAKER] Failed to send error message: {ws_error}")

            # Update runs database with failure
            if run_key:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='FAILED',
                    run_type="Table Generation (Execution)",
                    verbose_status=f"Execution failed: {error_msg}",
                    error_message=error_msg
                )

    except Exception as e:
        error_msg = f"Execution pipeline exception: {str(e)}"
        logger.error(f"[TABLE_MAKER] {error_msg}")
        import traceback
        logger.error(f"[TABLE_MAKER] Traceback: {traceback.format_exc()}")

        # Send error message via WebSocket
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_execution_error',
                    'conversation_id': conversation_id,
                    'status': 'Execution failed',
                    'error': error_msg
                })
            except Exception as ws_error:
                logger.warning(f"[TABLE_MAKER] Failed to send error message: {ws_error}")

        # Update runs database with failure
        if run_key:
            update_run_status(
                session_id=session_id,
                run_key=run_key,
                status='FAILED',
                run_type="Table Generation (Execution)",
                verbose_status=error_msg,
                error_message=error_msg
            )


async def handle_table_conversation_start(request_data, context):
    """
    Start a new table design interview (Phase 1: Quick context gathering).

    This handler:
    1. Creates a new conversation_id
    2. Loads table_maker_config.json
    3. Creates runs database entry for tracking
    4. Initializes TableInterviewHandler with user's initial message
    5. Stores interview state in S3
    6. Returns interview response via WebSocket
    7. If trigger_execution is true, automatically starts execution pipeline

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
            'trigger_execution': bool,
            'follow_up_question': str,
            'context_web_research': list,
            'processing_steps': list,
            'table_name': str,
            'turn_count': 1,
            'error': None
        }
    """
    result = {
        'success': False,
        'conversation_id': None,
        'trigger_execution': False,
        'follow_up_question': '',
        'context_web_research': [],
        'processing_steps': [],
        'table_name': '',
        'turn_count': 0,
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

        # Use conversation ID from request if provided (from HTTP endpoint), otherwise generate new one
        conversation_id = request_data.get('conversation_id') or _generate_conversation_id()
        result['conversation_id'] = conversation_id
        logger.info(f"[TABLE_MAKER] Using conversation ID: {conversation_id}")

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Create runs database entry for table generation tracking
        logger.info(f"[TABLE_MAKER] Creating run record for table conversation")
        try:
            run_key = create_run_record(
                session_id=session_id,
                email=email,
                total_rows=0,
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
                input_table_name=f"table_{conversation_id}"
                # models, eliyahu_cost, run_time_s will be set by _add_api_call_to_runs
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

        # Use local table_maker prompts and schemas
        prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
        schemas_dir = os.path.join(os.path.dirname(__file__), 'schemas')

        # Initialize interview handler (Phase 1: Quick context gathering)
        interview_handler = TableInterviewHandler(
            prompts_dir=prompts_dir,
            schemas_dir=schemas_dir
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

        # Start interview with user message
        interview_config = config.get('interview', {})
        model = interview_config.get('model', 'claude-sonnet-4-5')
        max_tokens = interview_config.get('max_tokens', 8000)
        logger.info(f"[TABLE_MAKER] Starting interview with model: {model}")

        interview_result = await interview_handler.start_interview(
            user_message=user_message,
            model=model,
            max_tokens=max_tokens
        )

        if not interview_result['success']:
            result['error'] = interview_result.get('error', 'Interview initialization failed')
            logger.error(f"[TABLE_MAKER] Interview start failed: {result['error']}")

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

        # Extract interview response (using new schema)
        result['success'] = True
        result['mode'] = interview_result.get('mode', 0)
        result['trigger_execution'] = interview_result.get('trigger_execution', False)
        result['show_structure'] = interview_result.get('show_structure', False)
        result['ai_message'] = interview_result.get('ai_message', '')
        result['context_web_research'] = interview_result.get('context_web_research', [])
        result['processing_steps'] = interview_result.get('processing_steps', [])
        result['table_name'] = interview_result.get('table_name', '')
        result['turn_count'] = 1

        # Build conversation state for S3 storage (following config_change_log pattern)
        conversation_state = {
            'conversation_id': conversation_id,
            'session_id': session_id,
            'email': email,
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'status': 'execution_ready' if result['trigger_execution'] else 'in_progress',
            'turn_count': 1,
            'run_key': run_key,
            'config': config,  # Store config for reference
            'messages': interview_handler.get_interview_history(),
            'interview_context': interview_handler.get_interview_context(),
            'trigger_execution': result['trigger_execution']
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
            logger.error(f"[TABLE_MAKER] CRITICAL: Failed to save conversation state: {save_result['error']}")
            logger.error(f"[TABLE_MAKER] This will prevent conversation continuation!")
        else:
            logger.info(f"[TABLE_MAKER] Successfully saved conversation state to {save_result['s3_key']}")

        # Send progress update with interview results
        if websocket_client and session_id:
            try:
                interview_message = {
                    'type': 'table_conversation_update',
                    'conversation_id': conversation_id,
                    'progress': 100,
                    'status': 'Interview turn 1 complete',
                    'mode': result['mode'],
                    'trigger_execution': result['trigger_execution'],
                    'show_structure': result['show_structure'],
                    'ai_message': result['ai_message'],
                    'context_web_research': result['context_web_research'],
                    'processing_steps': result['processing_steps'],
                    'table_name': result['table_name'],
                    'turn_count': result['turn_count']
                }
                websocket_client.send_to_session(session_id, interview_message)
                logger.info(f"[TABLE_MAKER] Sent interview results via WebSocket: mode={result['mode']}, trigger_execution={result['trigger_execution']}, show_structure={result['show_structure']}, ai_message length={len(result['ai_message'])}")
            except Exception as e:
                logger.warning(f"[TABLE_MAKER] Failed to send WebSocket update: {e}")

        # Send dummy interview progress message (cosmetic, to keep user engaged)
        _send_interview_progress(session_id, conversation_id, turn_number=1)

        # Update runs database with interview API call metrics (using enhanced aggregation)
        if run_key:
            try:
                # The interview returns the full API response from call_structured_api
                api_response = interview_result.get('api_metadata', {})  # This is the full response from interview.py
                processing_time = api_response.get('processing_time', 0.0)

                _add_api_call_to_runs(
                    session_id=session_id,
                    run_key=run_key,
                    api_response=api_response,
                    model=model,
                    processing_time=processing_time,
                    call_type='interview',
                    status='IN_PROGRESS',
                    verbose_status="Interview turn 1 complete",
                    percent_complete=20
                )
            except Exception as e:
                logger.error(f"[TABLE_MAKER] Failed to update run status: {e}")

        # If trigger_execution is true, start execution pipeline after brief delay
        if result['trigger_execution']:
            logger.info(f"[TABLE_MAKER] Interview approved, waiting 2s before execution")

            # Give frontend time to display interview results (2 seconds)
            await asyncio.sleep(2)

            logger.info(f"[TABLE_MAKER] Starting execution pipeline now")

            # Now trigger execution
            await _trigger_execution(
                email=email,
                session_id=session_id,
                conversation_id=conversation_id,
                conversation_state=conversation_state,
                run_key=run_key
            )

        logger.info(f"[TABLE_MAKER] Interview started successfully: {conversation_id}")
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
    Continue an existing table design interview.

    This handler:
    1. Loads conversation state from S3
    2. Continues interview with user's new message
    3. Stores updated interview state in S3
    4. Returns interview response via WebSocket
    5. If trigger_execution is true, automatically starts execution pipeline

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
            'trigger_execution': bool,
            'follow_up_question': str,
            'context_web_research': list,
            'processing_steps': list,
            'table_name': str,
            'turn_count': 2,
            'error': None
        }
    """
    result = {
        'success': False,
        'conversation_id': None,
        'trigger_execution': False,
        'follow_up_question': '',
        'context_web_research': [],
        'processing_steps': [],
        'table_name': '',
        'turn_count': 0,
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

        # Use local table_maker prompts and schemas
        prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
        schemas_dir = os.path.join(os.path.dirname(__file__), 'schemas')

        # Initialize interview handler and restore state
        interview_handler = TableInterviewHandler(
            prompts_dir=prompts_dir,
            schemas_dir=schemas_dir
        )

        # Restore interview state
        interview_handler.messages = conversation_state['messages']
        interview_handler.interview_context = conversation_state.get('interview_context', {})

        logger.info(f"[TABLE_MAKER] Restored interview with {len(interview_handler.messages)} messages")

        # If there's preview data from a previous generation, inject it into the user message
        # so the LLM can see the complete table structure when refining
        preview_data = conversation_state.get('preview_data')
        if preview_data:
            columns = preview_data.get('columns', [])
            rows = preview_data.get('rows', [])
            future_ids = preview_data.get('future_ids', [])

            # Build a comprehensive table context
            table_context = "\n\n--- CURRENT TABLE STRUCTURE (for reference) ---\n"
            table_context += f"\nCOLUMNS ({len(columns)} total):\n"
            for col in columns:
                col_type = "ID" if col.get('is_identification') else "DATA"
                table_context += f"  [{col_type}] {col['name']}: {col.get('description', 'No description')}\n"

            table_context += f"\nSAMPLE ROWS ({len(rows)} complete rows):\n"
            for i, row in enumerate(rows[:3], 1):  # Show first 3 sample rows
                table_context += f"  Row {i}: {json.dumps(row, indent=4)}\n"

            if future_ids:
                table_context += f"\nADDITIONAL ROW IDs ({len(future_ids)} rows):\n"
                for i, id_row in enumerate(future_ids[:5], 1):  # Show first 5 ID rows
                    table_context += f"  ID {i}: {json.dumps(id_row)}\n"
                if len(future_ids) > 5:
                    table_context += f"  ... and {len(future_ids) - 5} more\n"

            table_context += "\n--- END OF CURRENT TABLE ---\n\n"

            # Prepend the table context AND highlight the latest user request
            user_message = table_context + f"=== USER'S LATEST REQUEST (address this in the ongoing conversation) ===\n{user_message}\n=== END OF LATEST REQUEST ===\n"
            logger.info(f"[TABLE_MAKER] Added preview table context to refinement request ({len(columns)} columns, {len(rows)} sample rows, {len(future_ids)} additional IDs)")

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

        # Continue interview with user message
        config = conversation_state.get('config', _load_table_maker_config())
        interview_config = config.get('interview', {})
        model = interview_config.get('model', 'claude-sonnet-4-5')
        max_tokens = interview_config.get('max_tokens', 8000)

        logger.info(f"[TABLE_MAKER] Continuing interview with model: {model}")

        interview_result = await interview_handler.continue_interview(
            user_message=user_message,
            model=model,
            max_tokens=max_tokens
        )

        if not interview_result['success']:
            result['error'] = interview_result.get('error', 'Interview continuation failed')
            logger.error(f"[TABLE_MAKER] Interview continue failed: {result['error']}")

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

        # Extract interview response (using new schema)
        result['success'] = True
        result['mode'] = interview_result.get('mode', 0)
        result['trigger_execution'] = interview_result.get('trigger_execution', False)
        result['show_structure'] = interview_result.get('show_structure', False)
        result['ai_message'] = interview_result.get('ai_message', '')
        result['context_web_research'] = interview_result.get('context_web_research', [])
        result['processing_steps'] = interview_result.get('processing_steps', [])
        result['table_name'] = interview_result.get('table_name', '')
        result['turn_count'] = conversation_state['turn_count'] + 1

        # Update conversation state
        conversation_state['last_updated'] = datetime.utcnow().isoformat() + 'Z'
        conversation_state['status'] = 'execution_ready' if result['trigger_execution'] else 'in_progress'
        conversation_state['turn_count'] = result['turn_count']
        conversation_state['messages'] = interview_handler.get_interview_history()
        conversation_state['interview_context'] = interview_handler.get_interview_context()
        conversation_state['trigger_execution'] = result['trigger_execution']

        # Save updated conversation state to S3
        save_result = _save_conversation_state_to_s3(
            storage_manager=storage_manager,
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            conversation_state=conversation_state
        )

        if not save_result['success']:
            logger.error(f"[TABLE_MAKER] CRITICAL: Failed to save updated conversation state: {save_result['error']}")
            logger.error(f"[TABLE_MAKER] This will prevent further conversation continuation!")
        else:
            logger.info(f"[TABLE_MAKER] Successfully saved updated conversation state to {save_result['s3_key']}")

        # Send progress update with interview results
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_conversation_update',
                    'conversation_id': conversation_id,
                    'progress': 100,
                    'status': f'Interview turn {result["turn_count"]} complete',
                    'mode': result['mode'],
                    'trigger_execution': result['trigger_execution'],
                    'show_structure': result['show_structure'],
                    'ai_message': result['ai_message'],
                    'context_web_research': result['context_web_research'],
                    'processing_steps': result['processing_steps'],
                    'table_name': result['table_name'],
                    'turn_count': result['turn_count']
                })
            except Exception as e:
                logger.warning(f"[TABLE_MAKER] Failed to send WebSocket update: {e}")

        # Send dummy interview progress message (cosmetic, to keep user engaged)
        _send_interview_progress(session_id, conversation_id, turn_number=result['turn_count'])

        # Update runs database with interview API call metrics (using enhanced aggregation)
        if run_key:
            try:
                api_response = interview_result.get('api_metadata', {})
                status_msg = "Ready for execution" if result['trigger_execution'] else f"Interview turn {result['turn_count']} complete"

                _add_api_call_to_runs(
                    session_id=session_id,
                    run_key=run_key,
                    api_response=api_response,
                    model=model,
                    processing_time=api_response.get('processing_time', 0.0),
                    call_type='interview',
                    status='IN_PROGRESS',
                    verbose_status=status_msg,
                    percent_complete=20 + (result['turn_count'] * 10)
                )
            except Exception as e:
                logger.error(f"[TABLE_MAKER] Failed to update run status: {e}")

        # If trigger_execution is true, start execution pipeline after brief delay
        if result['trigger_execution']:
            logger.info(f"[TABLE_MAKER] Interview approved, waiting 2s before execution")

            # Give frontend time to display interview results (2 seconds)
            await asyncio.sleep(2)

            logger.info(f"[TABLE_MAKER] Starting execution pipeline now")

            # Now trigger execution
            await _trigger_execution(
                email=email,
                session_id=session_id,
                conversation_id=conversation_id,
                conversation_state=conversation_state,
                run_key=run_key
            )

        logger.info(f"[TABLE_MAKER] Interview continued successfully: {conversation_id}, turn {result['turn_count']}")
        return create_response(200, result)

    except Exception as e:
        error_msg = f"Error continuing table conversation: {str(e)}"
        logger.error(f"[TABLE_MAKER] {error_msg}")
        import traceback
        logger.error(f"[TABLE_MAKER] Traceback: {traceback.format_exc()}")
        result['error'] = error_msg
        return create_response(500, result)
