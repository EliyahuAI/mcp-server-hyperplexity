"""
Table Maker Execution Orchestrator for Lambda Environment.

This is the MAIN coordinator that runs the entire Phase 2 pipeline after user approval.
It orchestrates all 4 steps of the execution phase in sequence and parallel where possible.

Pipeline Flow:
  Step 1: Column Definition (~30s)
  Step 2a & 2b (PARALLEL): Row Discovery (~90s) + Config Generation (~90s)
  Step 3: Table Population (~90s)
  Step 4: Validation (~10s)

Total Duration: ~3-4 minutes

Key Integration Points:
1. Called by conversation.py when trigger_execution=true
2. Calls column_definition.py (Step 1)
3. Calls row_discovery_handler.py (Step 2a, parallel)
4. Calls config_bridge.py (Step 2b, parallel)
5. Calls finalize.py (Step 3) - modified to accept row_ids
6. Calls validation (Step 4) - if exists
7. Updates runs database at each step
8. Sends WebSocket updates throughout
9. Saves S3 state after each major step
"""

import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

# Lambda imports
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response
from dynamodb_schemas import create_run_record, update_run_status

# Table maker imports
from .column_definition import handle_column_definition
from .row_discovery_handler import handle_row_discovery
from .config_bridge import build_table_analysis_from_conversation
# Note: finalize.py will be modified to accept row_ids parameter
# For now, we'll import it and adapt the call

# WebSocket client for real-time updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger = logging.getLogger()
    logger.warning("WebSocket client not available for table maker execution")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def send_execution_progress(
    session_id: str,
    conversation_id: str,
    current_step: int,
    total_steps: int,
    status: str,
    progress_percent: int,
    **kwargs
) -> None:
    """
    Send execution progress update via WebSocket.

    Args:
        session_id: Session identifier
        conversation_id: Conversation identifier
        current_step: Current step number (1-4)
        total_steps: Total number of steps (4)
        status: Human-readable status message
        progress_percent: Progress percentage (0-100)
        **kwargs: Additional fields to include in message
    """
    if not websocket_client or not session_id:
        return

    try:
        message = {
            'type': 'table_execution_update',
            'conversation_id': conversation_id,
            'current_step': current_step,
            'total_steps': total_steps,
            'status': status,
            'progress_percent': progress_percent,
            **kwargs
        }
        websocket_client.send_to_session(session_id, message)
        logger.info(
            f"[EXECUTION] Progress {progress_percent}% (Step {current_step}/{total_steps}): {status}"
        )
    except Exception as e:
        logger.warning(f"[EXECUTION] Failed to send WebSocket update: {e}")


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
        session_path = storage_manager.get_session_path(email, session_id)
        s3_key = f"{session_path}table_maker/conversation_{conversation_id}.json"

        response = storage_manager.s3_client.get_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key
        )

        conversation_state = json.loads(response['Body'].read().decode('utf-8'))
        logger.info(f"[EXECUTION] Loaded conversation state from S3: {s3_key}")
        return conversation_state

    except storage_manager.s3_client.exceptions.NoSuchKey:
        logger.error(f"[EXECUTION] Conversation state not found: {conversation_id}")
        return None
    except Exception as e:
        logger.error(f"[EXECUTION] Error loading conversation state: {e}")
        import traceback
        logger.error(f"[EXECUTION] Traceback: {traceback.format_exc()}")
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
        session_path = storage_manager.get_session_path(email, session_id)
        s3_key = f"{session_path}table_maker/conversation_{conversation_id}.json"

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key,
            Body=json.dumps(conversation_state, indent=2, ensure_ascii=False),
            ContentType='application/json'
        )

        logger.info(f"[EXECUTION] Saved conversation state to S3: {s3_key}")
        return True

    except Exception as e:
        logger.error(f"[EXECUTION] Error saving conversation state: {e}")
        import traceback
        logger.error(f"[EXECUTION] Traceback: {traceback.format_exc()}")
        return False


async def execute_full_table_generation(
    email: str,
    session_id: str,
    conversation_id: str,
    run_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute complete table generation pipeline (Phase 2).

    Pipeline:
    1. Column Definition (~30s)
    2. PARALLEL:
       - Row Discovery (~90s)
       - Config Generation (~90s)
    3. Table Population (~90s)
    4. Validation (~10s)

    Args:
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        run_key: Run tracking key (optional)

    Returns:
        {
            'success': bool,
            'conversation_id': str,
            'table_data': Dict,  # Complete validated table
            'validation_summary': Dict,
            'error': Optional[str],
            'failed_at_step': Optional[int]
        }
    """
    result = {
        'success': False,
        'conversation_id': conversation_id,
        'table_data': None,
        'validation_summary': None,
        'error': None,
        'failed_at_step': None
    }

    storage_manager = None

    try:
        logger.info(
            f"[EXECUTION] Starting full table generation pipeline for {conversation_id}"
        )

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Load conversation state
        conversation_state = _load_conversation_state(
            storage_manager, email, session_id, conversation_id
        )

        if not conversation_state:
            result['error'] = f'Conversation {conversation_id} not found'
            result['failed_at_step'] = 0
            logger.error(f"[EXECUTION] {result['error']}")
            return result

        # Get or create run_key
        if not run_key:
            run_key = conversation_state.get('run_key')
            if not run_key:
                logger.warning("[EXECUTION] No run_key available, metrics tracking disabled")

        # Send initial progress
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=0,
            total_steps=4,
            status='Execution starting',
            progress_percent=0
        )

        # Update runs database
        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='IN_PROGRESS',
                    run_type='Table Generation (Execution)',
                    verbose_status='Starting execution pipeline',
                    percent_complete=0
                )
            except Exception as e:
                logger.warning(f"[EXECUTION] Failed to update run status: {e}")

        # ======================================================================
        # STEP 1: Column Definition (~30s)
        # ======================================================================
        logger.info("[EXECUTION] Step 1/4: Starting column definition")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=1,
            total_steps=4,
            status='Step 1/4: Defining columns and search strategy...',
            progress_percent=5
        )

        try:
            # Build event for column definition handler
            column_def_event = {
                'body': json.dumps({
                    'email': email,
                    'session_id': session_id,
                    'conversation_id': conversation_id
                })
            }

            column_result = await handle_column_definition(column_def_event, None)

            # Parse result
            if isinstance(column_result.get('body'), str):
                column_result_body = json.loads(column_result['body'])
            else:
                column_result_body = column_result.get('body', {})

            if not column_result_body.get('success'):
                error_msg = column_result_body.get('error', 'Column definition failed')
                raise Exception(error_msg)

            logger.info(
                f"[EXECUTION] Step 1/4 complete: {len(column_result_body.get('columns', []))} columns defined"
            )

            # Reload conversation state to get updated column_definition
            conversation_state = _load_conversation_state(
                storage_manager, email, session_id, conversation_id
            )

        except Exception as e:
            error_msg = f"Step 1 failed (Column Definition): {str(e)}"
            logger.error(f"[EXECUTION] {error_msg}")
            import traceback
            logger.error(f"[EXECUTION] Traceback: {traceback.format_exc()}")

            result['error'] = error_msg
            result['failed_at_step'] = 1

            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=1,
                total_steps=4,
                status=f'Failed at step 1: {str(e)}',
                progress_percent=25,
                error=error_msg
            )

            if run_key:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='FAILED',
                    run_type='Table Generation (Execution)',
                    verbose_status=error_msg,
                    error_message=error_msg
                )

            return result

        # Update progress after step 1
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=1,
            total_steps=4,
            status='Step 1/4 complete: Columns and search strategy defined',
            progress_percent=25
        )

        # ======================================================================
        # STEP 2: PARALLEL - Row Discovery + Config Generation (~90s each)
        # ======================================================================
        logger.info("[EXECUTION] Step 2/4: Starting parallel row discovery and config generation")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=2,
            total_steps=4,
            status='Step 2/4: Discovering rows and generating config (parallel)...',
            progress_percent=30
        )

        try:
            # Build events for both handlers
            row_discovery_event = {
                'email': email,
                'session_id': session_id,
                'conversation_id': conversation_id
            }

            # Create parallel tasks
            row_task = asyncio.create_task(
                handle_row_discovery(row_discovery_event, None)
            )

            # Config generation using config_bridge
            # Note: Config generation will be done after row discovery for now
            # since it needs the complete table data
            config_task = asyncio.create_task(
                _generate_config_placeholder(
                    email, session_id, conversation_id, conversation_state
                )
            )

            # Wait for both to complete
            row_result, config_result = await asyncio.gather(row_task, config_task)

            # Parse row discovery result
            if isinstance(row_result.get('body'), str):
                row_result_body = json.loads(row_result['body'])
            else:
                row_result_body = row_result.get('body', {})

            if not row_result_body.get('success'):
                error_msg = row_result_body.get('error', 'Row discovery failed')
                raise Exception(error_msg)

            # Check config result
            if not config_result.get('success'):
                error_msg = config_result.get('error', 'Config generation failed')
                logger.warning(f"[EXECUTION] Config generation failed: {error_msg}")
                # Not fatal - we can continue without config

            logger.info(
                f"[EXECUTION] Step 2/4 complete: "
                f"{row_result_body.get('rows_discovered', 0)} rows discovered, "
                f"config generated: {config_result.get('success', False)}"
            )

            # Reload conversation state to get updated row_discovery
            conversation_state = _load_conversation_state(
                storage_manager, email, session_id, conversation_id
            )

        except Exception as e:
            error_msg = f"Step 2 failed (Row Discovery/Config): {str(e)}"
            logger.error(f"[EXECUTION] {error_msg}")
            import traceback
            logger.error(f"[EXECUTION] Traceback: {traceback.format_exc()}")

            result['error'] = error_msg
            result['failed_at_step'] = 2

            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=2,
                total_steps=4,
                status=f'Failed at step 2: {str(e)}',
                progress_percent=50,
                error=error_msg
            )

            if run_key:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='FAILED',
                    run_type='Table Generation (Execution)',
                    verbose_status=error_msg,
                    error_message=error_msg
                )

            return result

        # Update progress after step 2
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=2,
            total_steps=4,
            status='Step 2/4 complete: Rows discovered and config generated',
            progress_percent=50
        )

        # ======================================================================
        # STEP 3: Table Population (~90s)
        # ======================================================================
        logger.info("[EXECUTION] Step 3/4: Starting table population")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=3,
            total_steps=4,
            status='Step 3/4: Populating table with discovered rows...',
            progress_percent=55
        )

        try:
            # Get discovered rows from conversation state
            row_discovery = conversation_state.get('row_discovery', {})
            final_rows = row_discovery.get('final_rows', [])

            if not final_rows:
                raise Exception("No rows discovered in step 2")

            # Call table population handler (finalize.py)
            # Note: This will need to be modified to accept final_row_ids parameter
            # For now, we'll use the existing handle_table_accept_and_validate
            # but pass the discovered rows in the conversation state

            table_result = await _populate_table_with_rows(
                email=email,
                session_id=session_id,
                conversation_id=conversation_id,
                final_rows=final_rows,
                conversation_state=conversation_state,
                run_key=run_key
            )

            if not table_result.get('success'):
                error_msg = table_result.get('error', 'Table population failed')
                raise Exception(error_msg)

            logger.info(
                f"[EXECUTION] Step 3/4 complete: Table populated with {len(final_rows)} rows"
            )

            # Update conversation state with table data
            conversation_state['table_data'] = table_result.get('table_data', {})
            conversation_state['status'] = 'table_populated'
            conversation_state['last_updated'] = datetime.utcnow().isoformat() + 'Z'

            _save_conversation_state(
                storage_manager, email, session_id, conversation_id, conversation_state
            )

        except Exception as e:
            error_msg = f"Step 3 failed (Table Population): {str(e)}"
            logger.error(f"[EXECUTION] {error_msg}")
            import traceback
            logger.error(f"[EXECUTION] Traceback: {traceback.format_exc()}")

            result['error'] = error_msg
            result['failed_at_step'] = 3

            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=3,
                total_steps=4,
                status=f'Failed at step 3: {str(e)}',
                progress_percent=75,
                error=error_msg
            )

            if run_key:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='FAILED',
                    run_type='Table Generation (Execution)',
                    verbose_status=error_msg,
                    error_message=error_msg
                )

            return result

        # Update progress after step 3
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=3,
            total_steps=4,
            status='Step 3/4 complete: Table populated',
            progress_percent=75
        )

        # ======================================================================
        # STEP 4: Validation (~10s)
        # ======================================================================
        logger.info("[EXECUTION] Step 4/4: Starting validation")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=4,
            total_steps=4,
            status='Step 4/4: Validating table...',
            progress_percent=80
        )

        try:
            validation_result = await _validate_complete_table(
                email=email,
                session_id=session_id,
                conversation_id=conversation_id,
                table_data=conversation_state.get('table_data', {}),
                config=conversation_state.get('config', {})
            )

            if not validation_result.get('success'):
                logger.warning(
                    f"[EXECUTION] Validation failed: {validation_result.get('error', 'Unknown')}"
                )
                # Not fatal - mark table as unvalidated
                validation_summary = {
                    'status': 'unvalidated',
                    'error': validation_result.get('error', 'Validation failed')
                }
            else:
                validation_summary = validation_result.get('validation_summary', {})

            logger.info("[EXECUTION] Step 4/4 complete: Validation finished")

            # Update conversation state with validation
            conversation_state['validation'] = validation_summary
            conversation_state['status'] = 'execution_complete'
            conversation_state['last_updated'] = datetime.utcnow().isoformat() + 'Z'

            _save_conversation_state(
                storage_manager, email, session_id, conversation_id, conversation_state
            )

        except Exception as e:
            error_msg = f"Step 4 failed (Validation): {str(e)}"
            logger.warning(f"[EXECUTION] {error_msg} (non-fatal)")

            # Validation failure is not fatal - continue
            validation_summary = {
                'status': 'validation_skipped',
                'error': str(e)
            }

        # Update progress to 100%
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=4,
            total_steps=4,
            status='Execution complete! Table is ready.',
            progress_percent=100
        )

        # Update runs database to COMPLETED
        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='COMPLETED',
                    run_type='Table Generation (Execution)',
                    verbose_status='Table generation pipeline complete',
                    percent_complete=100
                )
            except Exception as e:
                logger.warning(f"[EXECUTION] Failed to update run status: {e}")

        # Build success result
        result['success'] = True
        result['table_data'] = conversation_state.get('table_data', {})
        result['validation_summary'] = validation_summary

        logger.info(
            f"[EXECUTION] Full table generation pipeline complete for {conversation_id}"
        )

        return result

    except Exception as e:
        error_msg = f"Execution pipeline failed: {str(e)}"
        logger.error(f"[EXECUTION] {error_msg}")
        import traceback
        logger.error(f"[EXECUTION] Traceback: {traceback.format_exc()}")

        result['error'] = error_msg

        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='FAILED',
                    run_type='Table Generation (Execution)',
                    verbose_status=error_msg,
                    error_message=error_msg
                )
            except Exception as update_error:
                logger.error(f"[EXECUTION] Failed to update run status: {update_error}")

        return result


async def _generate_config_placeholder(
    email: str,
    session_id: str,
    conversation_id: str,
    conversation_state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate configuration using config_bridge.

    This is a placeholder that will use config_bridge.py to generate
    a validation config from the conversation context.

    Args:
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        conversation_state: Complete conversation state

    Returns:
        {
            'success': bool,
            'config': Dict,
            'error': Optional[str]
        }
    """
    try:
        logger.info("[EXECUTION] Config generation placeholder called (will be implemented)")

        # For now, return a minimal config
        # TODO: Implement actual config generation using config_bridge.py
        # and handle_generate_config_unified

        minimal_config = {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'source': 'table_maker_execution',
            'conversation_id': conversation_id
        }

        return {
            'success': True,
            'config': minimal_config,
            'error': None
        }

    except Exception as e:
        logger.error(f"[EXECUTION] Config generation failed: {e}")
        return {
            'success': False,
            'config': {},
            'error': str(e)
        }


async def _populate_table_with_rows(
    email: str,
    session_id: str,
    conversation_id: str,
    final_rows: list,
    conversation_state: Dict[str, Any],
    run_key: Optional[str]
) -> Dict[str, Any]:
    """
    Populate table with discovered rows.

    This function will eventually call a modified version of finalize.py
    that accepts final_row_ids as input instead of generating them internally.

    For now, this is a placeholder that simulates table population.

    Args:
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        final_rows: List of discovered rows with id_values
        conversation_state: Complete conversation state
        run_key: Run tracking key

    Returns:
        {
            'success': bool,
            'table_data': Dict,
            'error': Optional[str]
        }
    """
    try:
        logger.info(
            f"[EXECUTION] Populating table with {len(final_rows)} discovered rows"
        )

        # Get column definitions
        column_definition = conversation_state.get('column_definition', {})
        columns = column_definition.get('columns', [])

        # Build table data structure
        table_data = {
            'columns': columns,
            'rows': [],
            'row_count': len(final_rows),
            'populated_at': datetime.utcnow().isoformat() + 'Z'
        }

        # Convert final_rows to table rows
        # Each final_row has: {id_values, match_score, match_rationale, source_urls}
        for row in final_rows:
            table_row = {}
            # Start with ID values
            id_values = row.get('id_values', {})
            for col in columns:
                col_name = col['name']
                if col.get('is_identification', False):
                    # Use ID value from discovery
                    table_row[col_name] = id_values.get(col_name, '')
                else:
                    # Data columns will be populated later by expansion
                    # For now, leave empty (will be filled in actual implementation)
                    table_row[col_name] = ''

            # Add metadata
            table_row['_match_score'] = row.get('match_score', 0)
            table_row['_match_rationale'] = row.get('match_rationale', '')
            table_row['_source_urls'] = row.get('source_urls', [])

            table_data['rows'].append(table_row)

        logger.info(
            f"[EXECUTION] Table populated with {len(table_data['rows'])} rows "
            f"({len(columns)} columns)"
        )

        # TODO: Call actual row expansion handler to populate data columns
        # For now, this is a placeholder

        return {
            'success': True,
            'table_data': table_data,
            'error': None
        }

    except Exception as e:
        logger.error(f"[EXECUTION] Table population failed: {e}")
        import traceback
        logger.error(f"[EXECUTION] Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'table_data': {},
            'error': str(e)
        }


async def _validate_complete_table(
    email: str,
    session_id: str,
    conversation_id: str,
    table_data: Dict[str, Any],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate complete table.

    This is a placeholder for table validation. In the full implementation,
    this would call the validation lambda to validate the complete table.

    Args:
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        table_data: Complete table data
        config: Validation configuration

    Returns:
        {
            'success': bool,
            'validation_summary': Dict,
            'error': Optional[str]
        }
    """
    try:
        logger.info("[EXECUTION] Validating complete table (placeholder)")

        # TODO: Implement actual validation
        # For now, return a placeholder validation summary

        validation_summary = {
            'status': 'validated',
            'total_cells': len(table_data.get('rows', [])) * len(table_data.get('columns', [])),
            'validated_cells': 0,
            'confidence_avg': 0.0,
            'validated_at': datetime.utcnow().isoformat() + 'Z'
        }

        return {
            'success': True,
            'validation_summary': validation_summary,
            'error': None
        }

    except Exception as e:
        logger.error(f"[EXECUTION] Validation failed: {e}")
        return {
            'success': False,
            'validation_summary': {},
            'error': str(e)
        }


# ============================================================================
# HTTP Handler - Called by API Gateway or SQS
# ============================================================================

async def handle_execute_full_table(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    HTTP handler for full table execution.

    This handler is called when trigger_execution=true from conversation.py
    or directly via API Gateway.

    Input event body:
    {
        'email': 'user@example.com',
        'session_id': 'session_xxx',
        'conversation_id': 'table_conv_xxx',
        'run_key': 'optional_run_key'
    }

    Returns:
        HTTP response with execution results
    """
    try:
        # Parse request body
        body = event.get('body', '{}')
        if isinstance(body, str):
            body = json.loads(body)

        email = body.get('email')
        session_id = body.get('session_id')
        conversation_id = body.get('conversation_id')
        run_key = body.get('run_key')

        # Validate required parameters
        if not email or not session_id or not conversation_id:
            return create_response(400, {
                'success': False,
                'error': 'Missing required parameters: email, session_id, conversation_id'
            })

        logger.info(
            f"[EXECUTION] HTTP handler called for conversation {conversation_id}"
        )

        # Execute pipeline
        result = await execute_full_table_generation(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            run_key=run_key
        )

        # Return result
        status_code = 200 if result['success'] else 500
        return create_response(status_code, result)

    except Exception as e:
        logger.error(f"[EXECUTION] HTTP handler error: {str(e)}")
        import traceback
        logger.error(f"[EXECUTION] Traceback: {traceback.format_exc()}")

        return create_response(500, {
            'success': False,
            'error': f'Execution handler failed: {str(e)}'
        })
