"""
Row Discovery Handler for Lambda Environment.

This module handles the row discovery phase of table generation, using
parallel subdomain streams to find and score candidate rows.

Key differences from standalone:
1. Uses UnifiedS3Manager for conversation state storage
2. Creates runs database entries to track operations
3. Sends WebSocket updates for real-time feedback
4. Loads configuration from table_maker_config.json
5. Integrates with existing lambda infrastructure

Integration flow:
1. Load conversation state from S3 (contains column_definition)
2. Extract search_strategy and columns from column_definition
3. Initialize RowDiscovery orchestrator
4. Execute parallel row discovery with progress updates
5. Track EACH stream's API call in runs database
6. Save discovered rows to conversation state
7. Send final WebSocket update with results
"""

import logging
import json
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List

# Lambda imports
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response
from dynamodb_schemas import update_run_status

# Table maker imports
from .table_maker_lib.row_discovery import RowDiscovery
from .table_maker_lib.prompt_loader import PromptLoader
from .table_maker_lib.schema_validator import SchemaValidator

# Shared imports
from shared.ai_api_client import ai_client

# WebSocket client for real-time updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger = logging.getLogger()
    logger.warning("WebSocket client not available for row discovery")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _add_api_call_to_runs(
    session_id: str,
    run_key: Optional[str],
    api_response: Dict[str, Any],
    model: str,
    processing_time: float,
    call_type: str,
    status: str = 'IN_PROGRESS',
    verbose_status: str = None,
    percent_complete: int = None,
    stream_index: int = None,
    total_streams: int = None
) -> None:
    """
    Add a single API call's metrics to the runs database.

    This is used to track EACH stream's API call separately, since row discovery
    makes multiple parallel API calls (one per subdomain stream).

    Args:
        session_id: Session identifier
        run_key: Run tracking key
        api_response: API response dict from call_structured_api
        model: Model name used
        processing_time: Processing time in seconds
        call_type: Type of call (e.g., 'row_discovery_stream')
        status: Run status (default: IN_PROGRESS)
        verbose_status: Human-readable status
        percent_complete: Progress percentage (optional)
        stream_index: Index of this stream (for logging)
        total_streams: Total number of streams (for logging)
    """
    if not run_key:
        logger.warning("[ROW_DISCOVERY] No run_key provided, skipping metrics update")
        return

    try:
        from dynamodb_schemas import get_run_status

        # Step 1: READ existing run record
        existing_run = get_run_status(session_id, run_key)

        # Step 2: Extract existing call_metrics_list and models list
        existing_call_metrics = []
        existing_models_list = []

        if existing_run:
            if 'call_metrics_list' in existing_run:
                existing_call_metrics = existing_run.get('call_metrics_list', [])
                logger.info(f"[ROW_DISCOVERY] Found {len(existing_call_metrics)} existing API calls")
            if 'models' in existing_run and isinstance(existing_run['models'], list):
                existing_models_list = existing_run['models']

        # Step 3: Add NEW call metrics
        if 'enhanced_data' in api_response and api_response['enhanced_data']:
            new_call_metrics = api_response['enhanced_data']
        else:
            # Fallback: regenerate enhanced metrics
            # Use module-level singleton
            new_call_metrics = ai_client.get_enhanced_call_metrics(
                response=api_response.get('response', api_response),
                model=model,
                processing_time=processing_time,
                pre_extracted_token_usage=api_response.get('token_usage'),
                is_cached=api_response.get('is_cached')
            )

        # Tag with call type and stream info
        new_call_metrics['call_type'] = call_type
        if stream_index is not None:
            new_call_metrics['stream_index'] = stream_index
            new_call_metrics['total_streams'] = total_streams

        existing_call_metrics.append(new_call_metrics)

        # Extract max_web_searches from enhanced data
        max_web_searches_value = new_call_metrics.get('call_info', {}).get('max_web_searches', 0)

        # Build model entry
        model_entry = {
            'model': model,
            'call_type': call_type,
            'max_web_searches': max_web_searches_value,
            'is_cached': api_response.get('is_cached', False)
        }
        if stream_index is not None:
            model_entry['stream_index'] = stream_index
        existing_models_list.append(model_entry)

        logger.info(
            f"[ROW_DISCOVERY] Added {call_type} call metrics "
            f"(stream {stream_index + 1}/{total_streams} if applicable), "
            f"total calls: {len(existing_call_metrics)}"
        )

        # Step 4: Re-aggregate ALL calls
        aggregated = ai_client.aggregate_provider_metrics(existing_call_metrics)
        providers = aggregated.get('providers', {})
        totals = aggregated.get('totals', {})

        # Step 5: Build run_type with operation details
        call_type_names = {
            'interview': 'Interview',
            'preview': 'Preview Generation',
            'expansion': 'Expansion',
            'refinement': 'Refinement',
            'row_discovery_stream': 'Row Discovery Stream',
            'column_definition': 'Column Definition'
        }
        operation_sequence = ', '.join([
            call_type_names.get(c.get('call_type'), c.get('call_type', 'Unknown'))
            for c in existing_call_metrics
        ])
        run_type = f"Table Generation ({operation_sequence})" if operation_sequence else "Table Generation"

        # Step 6: WRITE back to database
        total_actual_cost = totals.get('total_cost_actual', 0.0)
        total_estimated_cost = totals.get('total_cost_estimated', 0.0)
        total_actual_time = totals.get('total_actual_processing_time', 0.0)
        total_calls = totals.get('total_calls', 0)

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
                'row_discovery_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'row_discovery_stream']),
                'column_definition_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'column_definition']),
                'total_calls': len(existing_call_metrics)
            }
        }

        if percent_complete is not None:
            update_params['percent_complete'] = percent_complete

        update_run_status(**update_params)

        logger.info(
            f"[ROW_DISCOVERY] Updated runs database: {total_calls} total calls, "
            f"${total_actual_cost:.6f} total cost"
        )

    except Exception as e:
        logger.error(f"[ROW_DISCOVERY] Failed to add API call to runs: {e}")
        import traceback
        logger.error(f"[ROW_DISCOVERY] Traceback: {traceback.format_exc()}")


def _load_table_maker_config() -> Dict[str, Any]:
    """
    Load table maker configuration from table_maker_config.json.

    Returns:
        Configuration dictionary with row_discovery settings
    """
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'table_maker_config.json')

        if not os.path.exists(config_path):
            logger.warning(f"Table maker config not found at {config_path}, using defaults")
            return _get_default_row_discovery_config()

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        logger.info("Loaded table maker configuration successfully")
        return config

    except Exception as e:
        logger.error(f"Error loading table maker config: {e}, using defaults")
        return _get_default_row_discovery_config()


def _get_default_row_discovery_config() -> Dict[str, Any]:
    """
    Get default row discovery configuration as fallback.

    Returns:
        Default configuration dictionary
    """
    return {
        "row_discovery": {
            "target_row_count": 20,
            "min_match_score": 0.6,
            "max_parallel_streams": 5,
            "web_searches_per_stream": 3,
            "model": "claude-sonnet-4-5",
            "max_tokens": 8000
        }
    }


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
        logger.info(f"[ROW_DISCOVERY] Loaded conversation state from S3: {s3_key}")
        return conversation_state

    except storage_manager.s3_client.exceptions.NoSuchKey:
        logger.error(f"[ROW_DISCOVERY] Conversation state not found: {conversation_id}")
        return None
    except Exception as e:
        logger.error(f"[ROW_DISCOVERY] Error loading conversation state: {e}")
        return None


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
        session_path = storage_manager.get_session_path(email, session_id)
        s3_key = f"{session_path}table_maker/conversation_{conversation_id}.json"

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key,
            Body=json.dumps(conversation_state, indent=2, ensure_ascii=False),
            ContentType='application/json'
        )

        logger.info(f"[ROW_DISCOVERY] Saved conversation state to S3: {s3_key}")
        return {'success': True, 's3_key': s3_key, 'error': None}

    except Exception as e:
        error_msg = f"Error saving conversation state to S3: {e}"
        logger.error(f"[ROW_DISCOVERY] {error_msg}")
        return {'success': False, 's3_key': None, 'error': error_msg}


async def handle_row_discovery(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Discover rows using parallel subdomain streams.

    This is the main handler for row discovery, called after column definition is complete.
    It loads the column definition from S3, initializes the RowDiscovery orchestrator,
    executes parallel streams, tracks all API calls in the runs database, and saves
    the discovered rows back to S3.

    Input event body:
    {
        'email': 'user@example.com',
        'session_id': 'session_xxx',
        'conversation_id': 'table_conv_xxx'
    }

    Returns:
        {
            'success': bool,
            'conversation_id': str,
            'rows_discovered': int,
            'match_score_avg': float,
            'stats': Dict - Discovery statistics,
            'error': Optional[str]
        }
    """
    result = {
        'success': False,
        'conversation_id': None,
        'rows_discovered': 0,
        'match_score_avg': 0.0,
        'stats': {},
        'error': None
    }

    try:
        # Extract parameters
        email = event.get('email')
        session_id = event.get('session_id')
        conversation_id = event.get('conversation_id')

        if not email or not session_id or not conversation_id:
            result['error'] = 'Missing email, session_id, or conversation_id'
            return create_response(400, result)

        result['conversation_id'] = conversation_id

        logger.info(f"[ROW_DISCOVERY] Starting row discovery for conversation {conversation_id}")

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
            result['error'] = f'Conversation {conversation_id} not found in S3'
            logger.error(f"[ROW_DISCOVERY] {result['error']}")
            return create_response(404, result)

        # Get run_key for tracking
        run_key = conversation_state.get('run_key')

        # Extract column_definition from conversation state
        column_definition = conversation_state.get('column_definition')
        if not column_definition:
            result['error'] = 'No column_definition found in conversation state'
            logger.error(f"[ROW_DISCOVERY] {result['error']}")
            return create_response(400, result)

        # Extract search_strategy and columns
        search_strategy = column_definition.get('search_strategy')
        columns = column_definition.get('columns')

        if not search_strategy or not columns:
            result['error'] = 'Invalid column_definition: missing search_strategy or columns'
            logger.error(f"[ROW_DISCOVERY] {result['error']}")
            return create_response(400, result)

        logger.info(
            f"[ROW_DISCOVERY] Loaded column definition: {len(columns)} columns, "
            f"search strategy: {search_strategy.get('description', 'N/A')[:60]}..."
        )

        # Load configuration
        config = _load_table_maker_config()
        row_discovery_config = config.get('row_discovery', {})

        # Extract parameters from config
        target_row_count = row_discovery_config.get('target_row_count', 20)
        min_match_score = row_discovery_config.get('min_match_score', 0.6)
        max_parallel_streams = row_discovery_config.get('max_parallel_streams', 5)
        web_searches_per_stream = row_discovery_config.get('web_searches_per_stream', 3)
        model = row_discovery_config.get('model', 'claude-sonnet-4-5')
        max_tokens = row_discovery_config.get('max_tokens', 8000)

        logger.info(
            f"[ROW_DISCOVERY] Configuration: target_rows={target_row_count}, "
            f"min_score={min_match_score}, max_streams={max_parallel_streams}, "
            f"searches_per_stream={web_searches_per_stream}"
        )

        # Send initial WebSocket update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_execution_update',
                    'conversation_id': conversation_id,
                    'status': 'Discovering matching entities',
                    'current_step': 2,
                    'total_steps': 4,
                    'progress_percent': 30
                })
            except Exception as e:
                logger.warning(f"[ROW_DISCOVERY] Failed to send WebSocket update: {e}")

        # Initialize components
        prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
        schemas_dir = os.path.join(os.path.dirname(__file__), 'schemas')

        # Use module-level singleton
        prompt_loader = PromptLoader(prompts_dir)
        schema_validator = SchemaValidator(schemas_dir)

        # Initialize RowDiscovery orchestrator
        row_discovery = RowDiscovery(
            ai_client=ai_client,
            prompt_loader=prompt_loader,
            schema_validator=schema_validator
        )

        logger.info("[ROW_DISCOVERY] Initialized RowDiscovery orchestrator")

        # Execute row discovery
        discovery_result = await row_discovery.discover_rows(
            search_strategy=search_strategy,
            columns=columns,
            target_row_count=target_row_count,
            min_match_score=min_match_score,
            web_searches_per_stream=web_searches_per_stream,
            max_parallel_streams=max_parallel_streams
        )

        if not discovery_result.get('success'):
            error_msg = discovery_result.get('error', 'Row discovery failed')
            logger.error(f"[ROW_DISCOVERY] {error_msg}")
            result['error'] = error_msg

            # Update runs database with failure
            if run_key:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='FAILED',
                    run_type="Table Generation",
                    verbose_status="Row discovery failed",
                    error_message=error_msg
                )

            return create_response(500, result)

        # Extract results
        final_rows = discovery_result.get('final_rows', [])
        stats = discovery_result.get('stats', {})

        logger.info(
            f"[ROW_DISCOVERY] Discovery complete: {len(final_rows)} rows found, "
            f"processing_time={discovery_result.get('processing_time', 0)}s"
        )

        # Calculate average match score
        if final_rows:
            match_scores = [row.get('match_score', 0) for row in final_rows]
            avg_match_score = sum(match_scores) / len(match_scores)
        else:
            avg_match_score = 0.0

        # Update conversation state with discovered rows
        conversation_state['row_discovery'] = {
            'final_rows': final_rows,
            'stats': stats,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'config': {
                'target_row_count': target_row_count,
                'min_match_score': min_match_score,
                'max_parallel_streams': max_parallel_streams,
                'web_searches_per_stream': web_searches_per_stream
            }
        }
        conversation_state['status'] = 'row_discovery_complete'
        conversation_state['last_updated'] = datetime.utcnow().isoformat() + 'Z'

        # Save updated conversation state
        save_result = _save_conversation_state_to_s3(
            storage_manager=storage_manager,
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            conversation_state=conversation_state
        )

        if not save_result['success']:
            logger.error(
                f"[ROW_DISCOVERY] CRITICAL: Failed to save updated conversation state: "
                f"{save_result['error']}"
            )

        # Send final WebSocket update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_execution_update',
                    'conversation_id': conversation_id,
                    'status': 'Row discovery complete',
                    'current_step': 2,
                    'total_steps': 4,
                    'progress_percent': 50,
                    'rows_discovered': len(final_rows),
                    'match_score_avg': round(avg_match_score, 2)
                })
            except Exception as e:
                logger.warning(f"[ROW_DISCOVERY] Failed to send final WebSocket update: {e}")

        # Build success result
        result['success'] = True
        result['rows_discovered'] = len(final_rows)
        result['match_score_avg'] = round(avg_match_score, 2)
        result['stats'] = stats

        logger.info(
            f"[ROW_DISCOVERY] Row discovery handler complete: {len(final_rows)} rows, "
            f"avg_score={avg_match_score:.2f}"
        )

        return create_response(200, result)

    except Exception as e:
        error_msg = f"Error in row discovery handler: {str(e)}"
        logger.error(f"[ROW_DISCOVERY] {error_msg}")
        import traceback
        logger.error(f"[ROW_DISCOVERY] Traceback: {traceback.format_exc()}")
        result['error'] = error_msg
        return create_response(500, result)
