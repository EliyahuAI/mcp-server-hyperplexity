"""
Table Maker Column Definition Handler for Lambda Environment.

This module defines precise column specifications and search strategy from approved
conversation context, preparing for the row discovery phase.

Key Integration Points:
1. Loads conversation state from S3 (UnifiedS3Manager)
2. Uses ColumnDefinitionHandler from table_maker_lib
3. Sends WebSocket updates for progress
4. Tracks metrics in runs database
5. Saves results to S3 conversation state for row discovery
"""

import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

# Lambda imports
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response
from dynamodb_schemas import create_run_record, update_run_status

# Table maker imports (packaged with lambda)
from .table_maker_lib.column_definition_handler import ColumnDefinitionHandler
from .table_maker_lib.prompt_loader import PromptLoader
from .table_maker_lib.schema_validator import SchemaValidator

# Shared imports
from ai_api_client import AIAPIClient

# WebSocket client for real-time updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger = logging.getLogger()
    logger.warning("WebSocket client not available for table maker column definition")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _add_api_call_to_runs(
    session_id: str,
    run_key: Optional[str],
    api_response: Dict[str, Any],
    model: str,
    processing_time: float,
    call_type: str = 'column_definition',
    status: str = 'IN_PROGRESS',
    verbose_status: str = None,
    percent_complete: int = None
) -> None:
    """
    Add column definition API call metrics to runs database.

    Follows the same pattern as conversation.py _add_api_call_to_runs.

    Args:
        session_id: Session identifier
        run_key: Run tracking key
        api_response: API response dict from call_structured_api
        model: Model name used
        processing_time: Processing time in seconds
        call_type: Type of call (default: 'column_definition')
        status: Run status (default: IN_PROGRESS)
        verbose_status: Human-readable status
        percent_complete: Progress percentage (optional)
    """
    if not run_key:
        logger.warning("[COLUMN_DEF] No run_key provided, skipping metrics update")
        return

    try:
        from dynamodb_schemas import get_run_status

        # Step 1: READ existing run record
        existing_run = get_run_status(session_id, run_key)

        # Step 2: Extract existing call_metrics_list and models list
        existing_call_metrics = []
        existing_models_list = []

        if existing_run:
            logger.info(f"[COLUMN_DEF] Read existing run with keys: {list(existing_run.keys())}")
            if 'call_metrics_list' in existing_run:
                existing_call_metrics = existing_run.get('call_metrics_list', [])
                logger.info(f"[COLUMN_DEF] Found {len(existing_call_metrics)} existing API calls")
            if 'models' in existing_run and isinstance(existing_run['models'], list):
                existing_models_list = existing_run['models']

        # Step 3: Add NEW call metrics with call_type tag
        if 'enhanced_data' in api_response and api_response['enhanced_data']:
            new_call_metrics = api_response['enhanced_data']
            logger.debug(f"[COLUMN_DEF] Using pre-computed enhanced_data from API response")
        else:
            # Fallback: regenerate enhanced metrics if not present
            logger.warning(f"[COLUMN_DEF] enhanced_data not found, regenerating...")
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

        # Extract max_web_searches from enhanced data
        max_web_searches_value = new_call_metrics.get('call_info', {}).get('max_web_searches', 0)

        # Build model entry with web search info
        model_entry = {
            'model': model,
            'call_type': call_type,
            'max_web_searches': max_web_searches_value,
            'is_cached': api_response.get('is_cached', False)
        }
        existing_models_list.append(model_entry)

        logger.info(f"[COLUMN_DEF] Added {call_type} call metrics for {model}, total calls: {len(existing_call_metrics)}")

        # Step 4: Re-aggregate ALL calls
        aggregated = AIAPIClient().aggregate_provider_metrics(existing_call_metrics)
        providers = aggregated.get('providers', {})
        totals = aggregated.get('totals', {})

        # Step 5: WRITE back to database with aggregated metrics
        total_actual_cost = totals.get('total_cost_actual', 0.0)
        total_estimated_cost = totals.get('total_cost_estimated', 0.0)
        total_actual_time = totals.get('total_actual_processing_time', 0.0)
        total_calls = totals.get('total_calls', 0)

        # Build run_type with operation details
        call_type_names = {
            'interview': 'Interview',
            'preview': 'Preview Generation',
            'expansion': 'Expansion',
            'refinement': 'Refinement',
            'column_definition': 'Column Definition'
        }
        operation_sequence = ', '.join([call_type_names.get(c.get('call_type'), c.get('call_type', 'Unknown'))
                                       for c in existing_call_metrics])
        run_type = f"Table Generation ({operation_sequence})" if operation_sequence else "Table Generation"

        update_params = {
            'session_id': session_id,
            'run_key': run_key,
            'status': status,
            'run_type': run_type,
            'verbose_status': verbose_status or f"Completed {total_calls} API calls",
            'models': existing_models_list,
            'eliyahu_cost': total_actual_cost,
            'provider_metrics': providers,
            'total_provider_cost_actual': total_actual_cost,
            'total_provider_cost_estimated': total_estimated_cost,
            'total_provider_tokens': totals.get('total_tokens', 0),
            'total_provider_calls': total_calls,
            'overall_cache_efficiency_percent': totals.get('overall_cache_efficiency', 0.0),
            'actual_processing_time_seconds': total_actual_time,
            'run_time_s': total_actual_time,
            'time_per_row_seconds': total_actual_time / max(total_calls, 1),
            'call_metrics_list': existing_call_metrics,
            'enhanced_metrics_aggregated': aggregated,
            'table_maker_breakdown': {
                'interview_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'interview']),
                'preview_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'preview']),
                'expansion_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'expansion']),
                'column_definition_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'column_definition']),
                'total_calls': len(existing_call_metrics)
            }
        }

        if percent_complete is not None:
            update_params['percent_complete'] = percent_complete

        update_run_status(**update_params)

        logger.info(f"[COLUMN_DEF] Updated runs database: {total_calls} total calls, ${total_actual_cost:.6f} total cost")

    except Exception as e:
        logger.error(f"[COLUMN_DEF] Failed to add API call to runs: {e}")
        import traceback
        logger.error(f"[COLUMN_DEF] Traceback: {traceback.format_exc()}")


async def handle_column_definition(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Generate column definitions and search strategy from conversation context.

    This is Step 1 of the execution phase - defines precise specifications for what
    data to collect and how to find matching entities.

    Input event body:
    {
        'email': 'user@example.com',
        'session_id': 'session_xxx',
        'conversation_id': 'table_conv_xxx'
    }

    Returns:
    {
        'success': True,
        'columns': [...],  # Column definitions with validation strategies
        'search_strategy': {...},  # Search strategy with subdomain hints
        'table_name': str,
        'tablewide_research': str
    }
    """
    try:
        # Parse request body
        body = event.get('body', '{}')
        if isinstance(body, str):
            body = json.loads(body)

        email = body.get('email')
        session_id = body.get('session_id')
        conversation_id = body.get('conversation_id')

        # Validate required parameters
        if not email or not session_id or not conversation_id:
            return create_response(400, {
                'error': 'Missing required parameters: email, session_id, conversation_id'
            })

        logger.info(f"[COLUMN_DEF] Starting column definition for conversation {conversation_id}")

        # Send initial WebSocket update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_execution_update',
                    'conversation_id': conversation_id,
                    'status': 'Defining columns and search strategy',
                    'current_step': 1,
                    'total_steps': 4,
                    'progress_percent': 10
                })
            except Exception as ws_error:
                logger.warning(f"[COLUMN_DEF] WebSocket update failed: {ws_error}")

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Load conversation state from S3
        conversation_state = _load_conversation_state(storage_manager, email, session_id, conversation_id)
        if not conversation_state:
            return create_response(404, {
                'error': f'Conversation state not found: {conversation_id}'
            })

        # Load table maker config
        config = _load_table_maker_config()
        column_def_config = config.get('column_definition', {})
        model = column_def_config.get('model', 'claude-sonnet-4-5')
        max_tokens = column_def_config.get('max_tokens', 8000)

        # Initialize components
        base_dir = os.path.dirname(__file__)
        prompt_loader = PromptLoader(prompts_dir=os.path.join(base_dir, 'prompts'))
        schema_validator = SchemaValidator(schemas_dir=os.path.join(base_dir, 'schemas'))
        ai_client = AIAPIClient()

        # Initialize column definition handler
        column_handler = ColumnDefinitionHandler(
            ai_client=ai_client,
            prompt_loader=prompt_loader,
            schema_validator=schema_validator
        )

        # Generate column definitions
        logger.info(f"[COLUMN_DEF] Calling column definition handler with model: {model}")
        result = await column_handler.define_columns(
            conversation_context=conversation_state,
            model=model,
            max_tokens=max_tokens
        )

        if not result['success']:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"[COLUMN_DEF] Column definition failed: {error_msg}")

            # Send error WebSocket update
            if websocket_client and session_id:
                try:
                    websocket_client.send_to_session(session_id, {
                        'type': 'table_execution_update',
                        'conversation_id': conversation_id,
                        'status': 'Column definition failed',
                        'error': error_msg
                    })
                except Exception as ws_error:
                    logger.warning(f"[COLUMN_DEF] WebSocket error update failed: {ws_error}")

            return create_response(500, {
                'error': f"Column definition failed: {error_msg}"
            })

        # Track metrics in runs database
        run_key = conversation_state.get('run_key')
        if run_key and result.get('api_response'):
            _add_api_call_to_runs(
                session_id=session_id,
                run_key=run_key,
                api_response=result['api_response'],
                model=model,
                processing_time=result['processing_time'],
                call_type='column_definition',
                status='IN_PROGRESS',
                verbose_status='Column definition complete',
                percent_complete=25
            )

        # Save results to conversation state for row discovery
        conversation_state['column_definition'] = {
            'columns': result['columns'],
            'search_strategy': result['search_strategy'],
            'table_name': result['table_name'],
            'tablewide_research': result['tablewide_research'],
            'generated_at': datetime.utcnow().isoformat() + 'Z'
        }
        conversation_state['status'] = 'column_definition_complete'

        _save_conversation_state(storage_manager, email, session_id, conversation_id, conversation_state)

        # Send completion WebSocket update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_execution_update',
                    'conversation_id': conversation_id,
                    'status': 'Column definition complete',
                    'current_step': 1,
                    'total_steps': 4,
                    'progress_percent': 25,
                    'columns_count': len(result['columns']),
                    'search_strategy_subdomains': len(result['search_strategy'].get('subdomain_hints', []))
                })
            except Exception as ws_error:
                logger.warning(f"[COLUMN_DEF] WebSocket completion update failed: {ws_error}")

        # Prepare response
        response_data = {
            'success': True,
            'conversation_id': conversation_id,
            'columns': result['columns'],
            'search_strategy': result['search_strategy'],
            'table_name': result['table_name'],
            'tablewide_research': result['tablewide_research'],
            'processing_time': result['processing_time']
        }

        logger.info(
            f"[COLUMN_DEF] Column definition completed successfully: "
            f"{len(result['columns'])} columns, "
            f"{len(result['search_strategy'].get('subdomain_hints', []))} subdomains"
        )

        return create_response(200, response_data)

    except Exception as e:
        logger.error(f"[COLUMN_DEF] Error in column definition: {str(e)}")
        import traceback
        logger.error(f"[COLUMN_DEF] Traceback: {traceback.format_exc()}")

        # Send error WebSocket update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_execution_update',
                    'conversation_id': conversation_id,
                    'status': 'Column definition failed',
                    'error': str(e)
                })
            except Exception as ws_error:
                logger.warning(f"[COLUMN_DEF] WebSocket error update failed: {ws_error}")

        return create_response(500, {
            'error': f'Column definition failed: {str(e)}'
        })


def _load_conversation_state(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str
) -> Optional[Dict[str, Any]]:
    """
    Load conversation state from S3.

    Args:
        storage_manager: UnifiedS3Manager instance
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier

    Returns:
        Conversation state dictionary or None if not found
    """
    try:
        # S3 key pattern: table_conversations/{email}/{session_id}/{conversation_id}/state.json
        s3_key = f"table_conversations/{email}/{session_id}/{conversation_id}/state.json"

        logger.info(f"[COLUMN_DEF] Loading conversation state from S3: {s3_key}")
        conversation_state = storage_manager.load_json(s3_key)

        if not conversation_state:
            logger.error(f"[COLUMN_DEF] Conversation state not found: {s3_key}")
            return None

        logger.info(f"[COLUMN_DEF] Loaded conversation state with keys: {list(conversation_state.keys())}")
        return conversation_state

    except Exception as e:
        logger.error(f"[COLUMN_DEF] Error loading conversation state: {e}")
        import traceback
        logger.error(f"[COLUMN_DEF] Traceback: {traceback.format_exc()}")
        return None


def _save_conversation_state(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str,
    conversation_state: Dict[str, Any]
) -> bool:
    """
    Save conversation state to S3.

    Args:
        storage_manager: UnifiedS3Manager instance
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        conversation_state: Conversation state dictionary

    Returns:
        True if successful, False otherwise
    """
    try:
        # S3 key pattern: table_conversations/{email}/{session_id}/{conversation_id}/state.json
        s3_key = f"table_conversations/{email}/{session_id}/{conversation_id}/state.json"

        logger.info(f"[COLUMN_DEF] Saving conversation state to S3: {s3_key}")
        storage_manager.save_json(s3_key, conversation_state)

        logger.info(f"[COLUMN_DEF] Saved conversation state successfully")
        return True

    except Exception as e:
        logger.error(f"[COLUMN_DEF] Error saving conversation state: {e}")
        import traceback
        logger.error(f"[COLUMN_DEF] Traceback: {traceback.format_exc()}")
        return False


def _load_table_maker_config() -> Dict[str, Any]:
    """
    Load table maker configuration from table_maker_config.json.

    Returns:
        Configuration dictionary with column_definition settings
    """
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'table_maker_config.json')

        if not os.path.exists(config_path):
            logger.warning(f"[COLUMN_DEF] Config not found at {config_path}, using defaults")
            return _get_default_config()

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        logger.info("[COLUMN_DEF] Loaded table maker configuration successfully")
        return config

    except Exception as e:
        logger.error(f"[COLUMN_DEF] Error loading config: {e}, using defaults")
        return _get_default_config()


def _get_default_config() -> Dict[str, Any]:
    """
    Get default table maker configuration.

    Returns:
        Default configuration dictionary
    """
    return {
        'column_definition': {
            'model': 'claude-sonnet-4-5',
            'max_tokens': 8000,
            'use_web_search': True,
            'web_searches': 3
        }
    }
