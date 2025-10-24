"""
Independent Row Discovery Execution Handler for Lambda.

This module orchestrates the 4-step pipeline using LOCAL components directly:
1. Column Definition
2. Row Discovery (with progressive escalation)
3. Consolidation (built into row_discovery)
4. QC Review

The LOCAL components (from table_maker/src/) are the SOURCE OF TRUTH.
This file just adds Lambda infrastructure wrappers (S3, WebSocket, runs DB).
"""

import logging
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Lambda infrastructure imports
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response
from dynamodb_schemas import update_run_status

# WebSocket client for real-time updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger = logging.getLogger()
    logger.warning("WebSocket client not available")

# Import LOCAL components (no modifications)
from .table_maker_lib.column_definition_handler import ColumnDefinitionHandler
from .table_maker_lib.row_discovery import RowDiscovery
from .table_maker_lib.qc_reviewer import QCReviewer
from .table_maker_lib.prompt_loader import PromptLoader
from .table_maker_lib.schema_validator import SchemaValidator
from ai_api_client import AIAPIClient

# Import config generation
from .config_bridge import build_table_analysis_from_conversation
from ..generate_config_unified import handle_generate_config_unified
from .table_maker_lib.config_generator import ConfigGenerator

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
            'phase': 'execution',
            **kwargs
        }
        websocket_client.send_to_session(session_id, message)
        logger.info(
            f"[EXECUTION] Progress {progress_percent}% (Step {current_step}/{total_steps}): {status}"
        )
    except Exception as e:
        logger.warning(f"[EXECUTION] Failed to send WebSocket update: {e}")


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

    This uses the SAME pattern as conversation.py to ensure consistent metrics tracking.

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
        api_response: API response dict from handler with structure:
            {'enhanced_data': {...}, 'model_used': str, 'processing_time': float, ...}
        model: Model name used
        processing_time: Processing time in seconds
        call_type: Type of call (e.g., 'column_definition', 'row_discovery', 'qc_review')
        status: Run status (default: IN_PROGRESS)
        verbose_status: Human-readable status
        percent_complete: Progress percentage (optional)
    """
    if not run_key:
        logger.warning("[EXECUTION] No run_key provided, skipping metrics update")
        return

    try:
        from dynamodb_schemas import get_run_status

        # Step 1: READ existing run record
        existing_run = get_run_status(session_id, run_key)

        # Step 2: Extract existing call_metrics_list and models list (if any)
        existing_call_metrics = []
        existing_models_list = []
        logger.info(f"[EXECUTION] Read existing run: exists={existing_run is not None}")
        if existing_run:
            if 'call_metrics_list' in existing_run:
                existing_call_metrics = existing_run.get('call_metrics_list', [])
                logger.info(f"[EXECUTION] Found {len(existing_call_metrics)} existing API calls in runs database")
            if 'models' in existing_run and isinstance(existing_run['models'], list):
                existing_models_list = existing_run['models']
        else:
            logger.warning(f"[EXECUTION] No existing run found for session_id={session_id}, run_key={run_key}")

        # Step 3: Add NEW call metrics with call_type tag
        # Use enhanced_data directly from API response (already computed by handlers)
        if 'enhanced_data' in api_response and api_response['enhanced_data']:
            new_call_metrics = api_response['enhanced_data']
            logger.debug(f"[EXECUTION] Using pre-computed enhanced_data from API response")
        else:
            # Fallback: regenerate enhanced metrics if not present
            logger.warning(f"[EXECUTION] enhanced_data not found in api_response, regenerating...")
            new_call_metrics = AIAPIClient().get_enhanced_call_metrics(
                response=api_response.get('response', api_response),
                model=model,
                processing_time=processing_time,
                pre_extracted_token_usage=api_response.get('token_usage'),
                is_cached=api_response.get('is_cached', False)
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

        logger.info(f"[EXECUTION] Added new {call_type} call metrics for {model}, total calls: {len(existing_call_metrics)}")

        # Step 4: Re-aggregate ALL calls
        aggregated = AIAPIClient.aggregate_provider_metrics(existing_call_metrics)
        providers = aggregated.get('providers', {})
        totals = aggregated.get('totals', {})

        # Step 5: WRITE back to database with aggregated metrics
        total_actual_cost = totals.get('total_cost_actual', 0.0)
        total_estimated_cost = totals.get('total_cost_estimated', 0.0)
        total_actual_time = totals.get('total_actual_processing_time', 0.0)
        total_calls = totals.get('total_calls', 0)

        # Build run_type with operation details
        call_type_names = {
            'column_definition': 'Column Definition',
            'row_discovery': 'Row Discovery',
            'qc_review': 'QC Review',
            'config_generation': 'Config Generation'
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
                'column_definition_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'column_definition']),
                'row_discovery_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'row_discovery']),
                'qc_review_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'qc_review']),
                'config_generation_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'config_generation']),
                'total_calls': len(existing_call_metrics)
            }
        }

        if percent_complete is not None:
            update_params['percent_complete'] = percent_complete

        update_run_status(**update_params)

        logger.info(f"[EXECUTION] Updated runs database: {total_calls} total calls, ${total_actual_cost:.6f} total cost")
        logger.info(f"[EXECUTION] Stored enhanced metrics: {len(existing_call_metrics)} call details, {len(providers)} providers")

    except Exception as e:
        logger.error(f"[EXECUTION] Failed to add API call to runs: {e}")
        import traceback
        logger.error(f"[EXECUTION] Traceback: {traceback.format_exc()}")


def _load_conversation_state(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str
) -> Optional[Dict]:
    """Load conversation state from S3."""
    try:
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
        logger.info(f"[EXECUTION] Loaded conversation state from S3: {s3_key}")
        return conversation_state

    except Exception as e:
        logger.error(f"[EXECUTION] Error loading conversation state: {e}")
        return None


def _save_to_s3(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str,
    file_name: str,
    data: Dict
) -> None:
    """Save data to S3."""
    try:
        s3_key = storage_manager.get_table_maker_path(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            file_name=file_name
        )

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key,
            Body=json.dumps(data, indent=2),
            ContentType='application/json'
        )

        logger.info(f"[EXECUTION] Saved to S3: {s3_key}")

    except Exception as e:
        logger.error(f"[EXECUTION] Failed to save to S3: {e}")


def _load_config() -> Dict:
    """Load table_maker_config.json."""
    try:
        # Config is in the same directory as this file
        config_path = Path(__file__).parent / 'table_maker_config.json'
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[EXECUTION] Failed to load config: {e}")
        return {}


async def _generate_validation_config(
    email: str,
    session_id: str,
    conversation_id: str,
    conversation_state: Dict,
    columns: list,
    table_name: str
) -> Dict[str, Any]:
    """
    Generate validation config in parallel with row discovery.

    Args:
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        conversation_state: Conversation state
        columns: Column definitions from column_definition step
        table_name: Table name

    Returns:
        {
            'success': bool,
            'config': Dict (if successful),
            'error': str (if failed)
        }
    """
    try:
        logger.info(f"[CONFIG_GEN] Starting validation config generation for {conversation_id}")

        # Build preview_data structure for config_bridge
        preview_data = {
            'columns': columns,
            'sample_rows': [],  # No rows yet - config is based on columns
            'table_name': table_name
        }

        # Build table_analysis using config_bridge
        table_analysis = build_table_analysis_from_conversation(
            conversation_state=conversation_state,
            preview_data=preview_data,
            table_rows=None  # No rows yet
        )

        logger.info(f"[CONFIG_GEN] Built table_analysis with {len(columns)} columns")

        # Call config generation handler
        config_event = {
            'email': email,
            'session_id': session_id,
            'table_analysis': table_analysis,
            'instructions': f'Generate validation configuration for table: {table_name}'
        }

        config_result = await handle_generate_config_unified(
            config_event,
            websocket_callback=None,
            table_maker_mode=True  # Use Table Maker mode - skip CSV parsing
        )

        if config_result.get('success'):
            logger.info(f"[CONFIG_GEN] Config generation succeeded")
            return {
                'success': True,
                'config': config_result.get('updated_config'),
                'config_s3_key': config_result.get('config_s3_key'),
                'config_version': config_result.get('config_version')
            }
        else:
            error_msg = config_result.get('error', 'Unknown config generation error')
            logger.warning(f"[CONFIG_GEN] Config generation failed: {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }

    except Exception as e:
        logger.error(f"[CONFIG_GEN] Config generation error: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


async def execute_full_table_generation(
    email: str,
    session_id: str,
    conversation_id: str,
    run_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute the complete Independent Row Discovery pipeline with parallel config generation.

    This function uses LOCAL components (from table_maker/src/) directly.
    It only adds Lambda infrastructure wrappers (S3, WebSocket, runs DB).

    Pipeline Flow:
        Step 1: Column Definition (~10-40s)
            ↓
        Step 2: Row Discovery + Config Generation START IN PARALLEL
            ├─→ Row Discovery (60-120s) - progressive escalation
            └─→ Config Generation (20-40s) - runs in background
            ↓
        [Row Discovery completes]
            ↓
        Step 3: QC Review starts immediately (~8-15s) - doesn't wait for config
            ↓
        [QC Review completes]
            ↓
        MUTUAL COMPLETION: Wait for Config Generation to finish
            ↓
        Generate CSV: ID columns filled, other columns empty
            ↓
        Complete

    Total Duration: ~1-3 minutes (config runs in parallel, QC doesn't wait)
    Total Cost: ~$0.05-0.20 (includes config generation)

    Args:
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        run_key: Run tracking key (optional)

    Returns:
        {
            'success': bool,
            'conversation_id': str,
            'table_name': str,
            'row_count': int,
            'approved_rows': List[Dict],
            'config_generated': bool,
            'config_s3_key': str (if config succeeded),
            'config_version': int (if config succeeded),
            'csv_s3_key': str,
            'csv_filename': str,
            'error': Optional[str]
        }
    """
    result = {
        'success': False,
        'conversation_id': conversation_id,
        'table_name': None,
        'row_count': 0,
        'approved_rows': [],
        'error': None
    }

    try:
        logger.info(f"[EXECUTION] Starting Independent Row Discovery pipeline for {conversation_id}")

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Load conversation state from S3
        conversation_state = _load_conversation_state(
            storage_manager, email, session_id, conversation_id
        )

        if not conversation_state:
            result['error'] = f'Conversation {conversation_id} not found'
            logger.error(f"[EXECUTION] {result['error']}")
            return result

        # Get or create run_key
        if not run_key:
            run_key = conversation_state.get('run_key')
            if not run_key:
                logger.warning("[EXECUTION] No run_key available, metrics tracking disabled")

        # Load config
        config = _load_config()

        # Initialize LOCAL components (same as local test)
        ai_client = AIAPIClient()

        # Prompts and schemas are in subdirectories
        prompts_dir = str(Path(__file__).parent / 'prompts')
        schemas_dir = str(Path(__file__).parent / 'schemas')

        prompt_loader = PromptLoader(prompts_dir)
        schema_validator = SchemaValidator(schemas_dir)

        column_handler = ColumnDefinitionHandler(ai_client, prompt_loader, schema_validator)
        row_discovery = RowDiscovery(ai_client, prompt_loader, schema_validator)
        qc_reviewer = QCReviewer(ai_client, prompt_loader, schema_validator)

        # Send initial progress
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=0,
            total_steps=4,
            status='Starting Independent Row Discovery pipeline',
            progress_percent=0
        )

        # Update runs database
        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='IN_PROGRESS',
                    run_type='Table Generation (Independent Row Discovery)',
                    verbose_status='Starting 4-step pipeline',
                    percent_complete=0
                )
            except Exception as e:
                logger.warning(f"[EXECUTION] Failed to update run status: {e}")

        # ======================================================================
        # STEP 1: Column Definition
        # ======================================================================
        logger.info("[EXECUTION] Step 1/4: Column Definition")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=1,
            total_steps=4,
            status='Step 1/4: Defining columns and search strategy',
            progress_percent=5
        )

        try:
            # Get config for column definition
            col_config = config.get('column_definition', {})
            col_model = col_config.get('model', 'claude-haiku-4-5')
            col_max_tokens = col_config.get('max_tokens', 12000)

            # Call column definition handler (same as local test)
            column_result = await column_handler.define_columns(
                conversation_context=conversation_state,
                context_web_research=conversation_state.get('context_web_research', []),
                model=col_model,
                max_tokens=col_max_tokens
            )

            if not column_result.get('success'):
                result['error'] = f"Column definition failed: {column_result.get('error')}"
                logger.error(f"[EXECUTION] {result['error']}")
                return result

            columns = column_result['columns']
            search_strategy = column_result['search_strategy']
            table_name = column_result.get('table_name', 'Unknown Table')

            result['table_name'] = table_name

            # Track API call
            _add_api_call_to_runs(
                session_id=session_id,
                run_key=run_key,
                api_response=column_result,
                model=column_result.get('model_used', col_model),
                processing_time=column_result.get('processing_time', 0.0),
                call_type='column_definition',
                status='IN_PROGRESS',
                verbose_status='Column definition complete',
                percent_complete=20
            )

            # Save to S3
            _save_to_s3(
                storage_manager, email, session_id, conversation_id,
                'column_definition_result.json', column_result
            )

            logger.info(f"[EXECUTION] Step 1 complete: {len(columns)} columns, table: {table_name}")

            # Add tablewide_research to conversation_state for config generation
            conversation_state['tablewide_research'] = column_result.get('tablewide_research', '')
            if conversation_state.get('tablewide_research'):
                logger.info(f"[EXECUTION] Stored tablewide_research in conversation_state for config generation")

            # Create minimal CSV with column headers for config generation
            import csv
            import io
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer, quoting=csv.QUOTE_ALL)  # Quote all fields to handle commas

            # Write column headers
            column_names = [col['name'] for col in columns]
            csv_writer.writerow(column_names)

            csv_content = csv_buffer.getvalue()

            # Save minimal CSV directly in session folder so config generation can find it
            # Session path already includes results/{domain}/{email}/{session_id}/
            csv_filename = f"{table_name.replace(' ', '_')}_template.csv"
            session_path = storage_manager.get_session_path(email, session_id)
            csv_s3_key = f"{session_path}{csv_filename}"

            storage_manager.s3_client.put_object(
                Bucket=storage_manager.bucket_name,
                Key=csv_s3_key,
                Body=csv_content,
                ContentType='text/csv'
            )
            logger.info(f"[EXECUTION] Created minimal CSV for config generation: {csv_s3_key}")

            # Send progress update with columns and table_name
            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=1,
                total_steps=4,
                status=f'Column definition complete: {table_name}',
                progress_percent=20,
                columns=columns,
                table_name=table_name
            )

        except Exception as e:
            result['error'] = f"Column definition error: {str(e)}"
            logger.error(f"[EXECUTION] {result['error']}", exc_info=True)
            return result

        # ======================================================================
        # STEP 2: Row Discovery + Config Generation (PARALLEL)
        # ======================================================================
        logger.info("[EXECUTION] Step 2/4: Row Discovery + Config Generation (parallel)")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=2,
            total_steps=4,
            status='Step 2/4: Discovering rows and generating validation config (parallel)',
            progress_percent=25
        )

        # Start config generation as background task (runs in parallel)
        config_generation_task = None
        try:
            # Get config for row discovery
            discovery_config = config.get('row_discovery', {})
            escalation_strategy = discovery_config.get('escalation_strategy', [])
            min_match_score = discovery_config.get('min_match_score', 0.6)
            check_targets_between_subdomains = discovery_config.get('check_targets_between_subdomains', False)
            early_stop_threshold_percentage = discovery_config.get('early_stop_threshold_percentage', 120)
            config_max_parallel = discovery_config.get('max_parallel_streams')

            # Calculate dynamic max_parallel_streams
            num_subdomains = len(search_strategy.get('subdomains', []))
            if config_max_parallel is None:
                max_parallel_streams = min(num_subdomains, 5)
                logger.info(
                    f"[EXECUTION] Dynamic max_parallel_streams: {max_parallel_streams} "
                    f"(min of {num_subdomains} subdomains and 5)"
                )
            else:
                max_parallel_streams = config_max_parallel
                logger.info(
                    f"[EXECUTION] Using config max_parallel_streams: {max_parallel_streams}"
                )

            # Create WebSocket callback for row discovery
            def websocket_callback(**kwargs):
                """Wrapper to send row discovery progress updates via WebSocket."""
                # Extract required positional args from kwargs
                progress_percent = kwargs.pop('progress_percent', 25)
                status = kwargs.pop('status', 'Discovering rows...')

                send_execution_progress(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    current_step=2,
                    total_steps=4,
                    status=status,
                    progress_percent=progress_percent,
                    **kwargs  # Now kwargs doesn't have 'status' or 'progress_percent'
                )

            # Start config generation in background (don't wait for it)
            logger.info("[EXECUTION] Starting config generation in background")
            config_generation_task = asyncio.create_task(
                _generate_validation_config(
                    email=email,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    conversation_state=conversation_state,
                    columns=columns,
                    table_name=table_name
                )
            )

            # Run row discovery (wait for completion before starting QC)
            logger.info("[EXECUTION] Starting row discovery")
            discovery_result = await row_discovery.discover_rows(
                search_strategy=search_strategy,
                columns=columns,
                target_row_count=conversation_state.get('target_row_count', 15),
                discovery_multiplier=1.5,
                min_match_score=min_match_score,
                max_parallel_streams=max_parallel_streams,
                escalation_strategy=escalation_strategy,
                check_targets_between_subdomains=check_targets_between_subdomains,
                early_stop_threshold_percentage=early_stop_threshold_percentage,
                websocket_callback=websocket_callback
            )

            # Check if row discovery succeeded (critical)
            if not discovery_result.get('success'):
                result['error'] = f"Row discovery failed: {discovery_result.get('error')}"
                logger.error(f"[EXECUTION] {result['error']}")
                return result

            final_rows = discovery_result.get('final_rows', [])
            stream_results = discovery_result.get('stream_results', [])

            # Track each subdomain's API calls
            for stream_result in stream_results:
                subdomain_name = stream_result.get('subdomain', 'Unknown')
                all_rounds = stream_result.get('all_rounds', [])

                for round_data in all_rounds:
                    round_num = round_data.get('round', '?')
                    model = round_data.get('model', 'unknown')
                    context = round_data.get('context', 'unknown')
                    processing_time = round_data.get('processing_time', 0.0)

                    _add_api_call_to_runs(
                        session_id=session_id,
                        run_key=run_key,
                        api_response=round_data,
                        model=model,
                        processing_time=processing_time,
                        call_type='row_discovery',
                        status='IN_PROGRESS',
                        verbose_status=f'Row discovery: {subdomain_name} round {round_num}'
                    )

            # Save discovery results to S3
            _save_to_s3(
                storage_manager, email, session_id, conversation_id,
                'discovery_result.json', discovery_result
            )

            logger.info(f"[EXECUTION] Step 2 complete: {len(final_rows)} consolidated rows")
            logger.info(f"[EXECUTION] Config generation still running in background...")

            # Send progress update with discovered_rows
            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=2,
                total_steps=4,
                status='Reviewing and prioritizing rows by relevance, reliability, and recency...',
                progress_percent=55,
                discovered_rows=final_rows
            )

        except Exception as e:
            result['error'] = f"Row discovery error: {str(e)}"
            logger.error(f"[EXECUTION] {result['error']}", exc_info=True)
            return result

        # ======================================================================
        # STEP 3: Consolidation (already done in row_discovery)
        # ======================================================================
        # Consolidation is built into row_discovery.discover_rows()
        # final_rows are already deduplicated, scored, and filtered

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=3,
            total_steps=4,
            status=f'Step 3/4: Row discovery complete, starting QC review ({len(final_rows)} rows)',
            progress_percent=60
        )

        # ======================================================================
        # STEP 4: QC Review (starts immediately, doesn't wait for config)
        # ======================================================================
        logger.info("[EXECUTION] Step 4/4: QC Review (config still running in background)")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=4,
            total_steps=4,
            status=f'Step 4/4: Quality control review of {len(final_rows)} rows',
            progress_percent=75
        )

        # Initialize retry tracking for QC retriggers
        retry_count = 0
        max_retriggers = 1
        # TODO: Pass retrigger_allowed to QC reviewer when parameter is supported
        # This flag will be used to disable retrigger after first attempt (prevent loops)
        retrigger_allowed = True

        # QC Review Loop (supports up to 1 retrigger)
        while True:
            try:
                # Get config for QC review
                qc_config = config.get('qc_review', {})
                qc_model = qc_config.get('model', 'claude-sonnet-4-5')
                qc_max_tokens = qc_config.get('max_tokens', 16000)
                min_qc_score = qc_config.get('min_qc_score', 0.5)
                min_row_count = qc_config.get('min_row_count', 4)
                min_row_count_for_frontend = qc_config.get('min_row_count_for_frontend', 4)

                # Call QC reviewer (same as local test)
                qc_result = await qc_reviewer.review_rows(
                    discovered_rows=final_rows,
                    columns=columns,
                    user_context=conversation_state.get('user_request', ''),
                    table_name=table_name,
                    table_purpose=search_strategy.get('table_purpose', ''),
                    tablewide_research=search_strategy.get('tablewide_research', ''),
                    model=qc_model,
                    max_tokens=qc_max_tokens,
                    min_qc_score=min_qc_score,
                    max_rows=999,  # No artificial cutoff
                    min_row_count=min_row_count,
                    search_strategy=search_strategy,
                    discovery_result=discovery_result,
                    retrigger_allowed=retrigger_allowed
                )

                if not qc_result.get('success'):
                    logger.warning(f"[EXECUTION] QC review failed: {qc_result.get('error')}")
                    # Use original rows if QC fails
                    approved_rows = final_rows
                    break
                else:
                    approved_rows = qc_result.get('approved_rows', final_rows)

                    # Track API call
                    _add_api_call_to_runs(
                        session_id=session_id,
                        run_key=run_key,
                        api_response=qc_result,
                        model=qc_model,
                        processing_time=qc_result.get('processing_time', 0.0),
                        call_type='qc_review',
                        status='IN_PROGRESS',
                        verbose_status=f'QC review complete: {len(approved_rows)} rows approved',
                        percent_complete=80
                    )

                    # Save to S3
                    _save_to_s3(
                        storage_manager, email, session_id, conversation_id,
                        'qc_result.json', qc_result
                    )

                # ======================================================================
                # Phase 1, Item 5: Check for insufficient rows
                # ======================================================================
                insufficient_rows_flag = qc_result.get('qc_summary', {}).get('insufficient_rows', False)
                if insufficient_rows_flag and len(approved_rows) < min_row_count_for_frontend:
                    logger.warning(
                        f"[INSUFFICIENT_ROWS] Only {len(approved_rows)} approved rows (< {min_row_count_for_frontend}). "
                        "Frontend will show restart button with recommendations."
                    )

                    # Include insufficient rows info in result for WebSocket message
                    result['insufficient_rows'] = True
                    result['insufficient_rows_statement'] = qc_result.get('insufficient_rows_statement', '')
                    result['insufficient_rows_recommendations'] = qc_result.get('insufficient_rows_recommendations', [])

                # ======================================================================
                # Phase 2, Item 6: Check for QC retrigger request
                # ======================================================================
                retrigger_data = qc_result.get('retrigger_discovery', {})
                should_retrigger = retrigger_data.get('should_retrigger', False)

                if should_retrigger and retry_count < max_retriggers:
                    retry_count += 1
                    retrigger_reason = retrigger_data.get('reason', 'No reason provided')

                    logger.info(f"[RETRIGGER] QC requested retrigger (attempt {retry_count}/{max_retriggers}): {retrigger_reason}")

                    # Send progress update about retrigger
                    send_execution_progress(
                        session_id=session_id,
                        conversation_id=conversation_id,
                        current_step=4,
                        total_steps=4,
                        status=f'QC requested additional discovery: {retrigger_reason}',
                        progress_percent=82
                    )

                    # Extract existing approved/demoted row IDs for exclusion
                    exclusion_list = []
                    for row in approved_rows:
                        id_values = row.get('id_values', {})
                        if id_values:
                            exclusion_list.append(id_values)

                    logger.info(f"[RETRIGGER] Created exclusion list with {len(exclusion_list)} existing rows")

                    # Update search_strategy with new subdomains
                    new_subdomains = retrigger_data.get('new_subdomains', [])
                    if new_subdomains:
                        logger.info(f"[RETRIGGER] Replacing {len(search_strategy.get('subdomains', []))} old subdomains with {len(new_subdomains)} new subdomains")
                        search_strategy['subdomains'] = new_subdomains

                    # Update requirements if provided
                    updated_requirements = retrigger_data.get('updated_requirements')
                    if updated_requirements:
                        logger.info(f"[RETRIGGER] Updating requirements: {len(updated_requirements)} requirements")
                        search_strategy['requirements'] = updated_requirements

                    # Update domain filters if provided
                    updated_default_domains = retrigger_data.get('updated_default_domains')
                    if updated_default_domains:
                        if 'included_domains' in updated_default_domains:
                            search_strategy['default_included_domains'] = updated_default_domains['included_domains']
                            logger.info(f"[RETRIGGER] Updated default_included_domains: {updated_default_domains['included_domains']}")
                        if 'excluded_domains' in updated_default_domains:
                            search_strategy['default_excluded_domains'] = updated_default_domains['excluded_domains']
                            logger.info(f"[RETRIGGER] Updated default_excluded_domains: {updated_default_domains['excluded_domains']}")

                    # Save updated column_definition_result
                    updated_column_result = {
                        'columns': columns,
                        'search_strategy': search_strategy,
                        'table_name': table_name,
                        'tablewide_research': column_result.get('tablewide_research', '')
                    }
                    _save_to_s3(
                        storage_manager, email, session_id, conversation_id,
                        'column_definition_result_retrigger.json', updated_column_result
                    )

                    # Re-run row discovery with updated strategy and exclusion list
                    logger.info("[RETRIGGER] Re-running row discovery with updated strategy")
                    send_execution_progress(
                        session_id=session_id,
                        conversation_id=conversation_id,
                        current_step=4,
                        total_steps=4,
                        status='Re-discovering rows with updated search strategy...',
                        progress_percent=85
                    )

                    # Calculate dynamic max_parallel_streams for retrigger
                    num_subdomains = len(search_strategy.get('subdomains', []))
                    max_parallel_streams_retrigger = min(num_subdomains, 5)

                    # TODO: Pass exclusion_list when row_discovery.py is updated to support it
                    # For now, the new subdomains and updated requirements will help avoid duplicates
                    retrigger_discovery_result = await row_discovery.discover_rows(
                        search_strategy=search_strategy,
                        columns=columns,
                        target_row_count=conversation_state.get('target_row_count', 15),
                        discovery_multiplier=1.5,
                        min_match_score=min_match_score,
                        max_parallel_streams=max_parallel_streams_retrigger,
                        escalation_strategy=escalation_strategy,
                        check_targets_between_subdomains=check_targets_between_subdomains,
                        early_stop_threshold_percentage=early_stop_threshold_percentage,
                        # exclusion_list=exclusion_list,  # TODO: Add when parameter is supported
                        websocket_callback=websocket_callback
                    )

                    if not retrigger_discovery_result.get('success'):
                        logger.error(f"[RETRIGGER] Re-discovery failed: {retrigger_discovery_result.get('error')}")
                        # Keep original rows and break
                        break

                    new_rows = retrigger_discovery_result.get('final_rows', [])
                    logger.info(f"[RETRIGGER] Re-discovery found {len(new_rows)} new rows")

                    # Track retrigger discovery API calls
                    retrigger_stream_results = retrigger_discovery_result.get('stream_results', [])
                    for stream_result in retrigger_stream_results:
                        subdomain_name = stream_result.get('subdomain', 'Unknown')
                        all_rounds = stream_result.get('all_rounds', [])

                        for round_data in all_rounds:
                            round_num = round_data.get('round', '?')
                            model = round_data.get('model', 'unknown')
                            processing_time = round_data.get('processing_time', 0.0)

                            _add_api_call_to_runs(
                                session_id=session_id,
                                run_key=run_key,
                                api_response=round_data,
                                model=model,
                                processing_time=processing_time,
                                call_type='row_discovery_retrigger',
                                status='IN_PROGRESS',
                                verbose_status=f'Retrigger discovery: {subdomain_name} round {round_num}'
                            )

                    # Merge new rows with existing approved rows (deduplicate by ID values)
                    existing_ids = set()
                    for row in approved_rows:
                        id_values = row.get('id_values', {})
                        if id_values:
                            # Create a hashable key from ID values
                            id_key = tuple(sorted(id_values.items()))
                            existing_ids.add(id_key)

                    # Add new rows that don't duplicate existing
                    merged_count = 0
                    for new_row in new_rows:
                        id_values = new_row.get('id_values', {})
                        if id_values:
                            id_key = tuple(sorted(id_values.items()))
                            if id_key not in existing_ids:
                                final_rows.append(new_row)
                                merged_count += 1
                                existing_ids.add(id_key)

                    logger.info(f"[RETRIGGER] Merged {merged_count} new unique rows, total now: {len(final_rows)}")

                    # Save merged discovery results
                    merged_discovery_result = {
                        'success': True,
                        'final_rows': final_rows,
                        'original_discovery': discovery_result,
                        'retrigger_discovery': retrigger_discovery_result,
                        'retrigger_count': retry_count
                    }
                    _save_to_s3(
                        storage_manager, email, session_id, conversation_id,
                        'discovery_result_merged.json', merged_discovery_result
                    )

                    # Update discovery_result to merged result for next QC iteration
                    discovery_result = merged_discovery_result

                    # Disable retrigger for next QC iteration
                    retrigger_allowed = False

                    # Continue to re-run QC with merged results
                    logger.info("[RETRIGGER] Re-running QC with merged results (retrigger disabled)")
                    continue

                else:
                    # No retrigger or max retriggers reached
                    if should_retrigger and retry_count >= max_retriggers:
                        logger.warning(f"[RETRIGGER] QC requested retrigger but max_retriggers ({max_retriggers}) reached")

                    # Break out of QC loop
                    break

            except Exception as e:
                logger.error(f"[EXECUTION] QC review error: {e}", exc_info=True)
                # Continue with discovered rows if QC fails
                approved_rows = final_rows
                break

        # Store final approved rows
        result['approved_rows'] = approved_rows
        result['row_count'] = len(approved_rows)

        logger.info(f"[EXECUTION] Step 4 complete: {len(approved_rows)} approved rows (after {retry_count} retrigger(s))")

        # Build progress message
        progress_message_parts = []
        if result.get('insufficient_rows'):
            progress_message_parts.append(f"Only {len(approved_rows)} rows found")
        else:
            progress_message_parts.append('Finalizing validation configuration...')

        progress_message = ' | '.join(progress_message_parts) if progress_message_parts else 'Finalizing validation configuration...'

        # Send progress update with approved_rows data (top 10 for display)
        progress_data = {
            'session_id': session_id,
            'conversation_id': conversation_id,
            'current_step': 4,
            'total_steps': 4,
            'status': progress_message,
            'progress_percent': 80,
            'approved_rows': approved_rows[:10],  # Send top 10 for frontend display
            'approved_row_count': len(approved_rows),
            'total_discovered': len(final_rows)  # Total before QC filtering
        }

        # Add insufficient rows info if applicable
        if result.get('insufficient_rows'):
            progress_data['insufficient_rows'] = True
            progress_data['insufficient_rows_statement'] = result.get('insufficient_rows_statement', '')
            progress_data['insufficient_rows_recommendations'] = result.get('insufficient_rows_recommendations', [])

        send_execution_progress(**progress_data)

        # ======================================================================
        # MUTUAL COMPLETION: Wait for Config Generation
        # ======================================================================
        logger.info("[EXECUTION] Waiting for config generation to complete...")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=4,
            total_steps=4,
            status='Waiting for config generation to complete...',
            progress_percent=85
        )

        # Wait for config generation to finish
        if config_generation_task:
            try:
                config_result = await config_generation_task

                if isinstance(config_result, Exception):
                    logger.warning(f"[EXECUTION] Config generation failed with exception: {config_result}")
                    result['config_generated'] = False
                elif config_result.get('success'):
                    logger.info(f"[EXECUTION] Config generation succeeded: {config_result.get('config_s3_key')}")
                    result['config_generated'] = True
                    result['config_s3_key'] = config_result.get('config_s3_key')
                    result['config_version'] = config_result.get('config_version')
                else:
                    logger.warning(f"[EXECUTION] Config generation failed: {config_result.get('error')}")
                    result['config_generated'] = False
            except Exception as e:
                logger.error(f"[EXECUTION] Error waiting for config generation: {e}", exc_info=True)
                result['config_generated'] = False
        else:
            logger.warning("[EXECUTION] Config generation task was not created")
            result['config_generated'] = False

        # ======================================================================
        # GENERATE CSV with ID columns filled, other columns empty
        # ======================================================================
        logger.info("[EXECUTION] Generating CSV file with ID columns filled...")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=4,
            total_steps=4,
            status='Generating CSV file...',
            progress_percent=90
        )

        try:
            # Create CSV with ID columns filled, other columns empty
            import csv
            import io

            csv_buffer = io.StringIO()

            # Get ID columns and all column names
            id_columns = [col['name'] for col in columns if col.get('is_identification')]
            all_column_names = [col['name'] for col in columns]

            writer = csv.DictWriter(csv_buffer, fieldnames=all_column_names)
            writer.writeheader()

            # Write rows with only ID columns filled
            for row in approved_rows:
                csv_row = {}
                for col_name in all_column_names:
                    if col_name in id_columns:
                        # Fill ID columns from approved_rows
                        csv_row[col_name] = row.get('id_values', {}).get(col_name, '')
                    else:
                        # Leave other columns empty
                        csv_row[col_name] = ''
                writer.writerow(csv_row)

            csv_content = csv_buffer.getvalue()

            # Save CSV to S3
            csv_filename = f"{table_name.replace(' ', '_')}_template.csv"
            csv_s3_key = storage_manager.get_table_maker_path(
                email=email,
                session_id=session_id,
                conversation_id=conversation_id,
                file_name=csv_filename
            )

            storage_manager.s3_client.put_object(
                Bucket=storage_manager.bucket_name,
                Key=csv_s3_key,
                Body=csv_content,
                ContentType='text/csv'
            )

            result['csv_s3_key'] = csv_s3_key
            result['csv_filename'] = csv_filename

            logger.info(f"[EXECUTION] CSV generated with {len(approved_rows)} rows, {len(id_columns)} ID columns filled")

            # Update session_info.json with table_path
            try:
                session_info = storage_manager.load_session_info(email, session_id)
                session_info['table_path'] = csv_s3_key
                session_info['table_name'] = table_name
                session_info['last_updated'] = datetime.now().isoformat()
                storage_manager.save_session_info(email, session_id, session_info)
                logger.info(f"[EXECUTION] Updated session_info.json with table_path: {csv_s3_key}")
            except Exception as e_session:
                logger.warning(f"[EXECUTION] Failed to update session_info with table_path: {e_session}")

        except Exception as e:
            logger.error(f"[EXECUTION] Failed to generate CSV: {e}", exc_info=True)
            result['csv_generation_error'] = str(e)

        # ======================================================================
        # COMPLETE
        # ======================================================================

        # Update conversation state with approved rows
        conversation_state['approved_rows'] = approved_rows
        conversation_state['columns'] = columns
        conversation_state['table_name'] = table_name
        conversation_state['csv_s3_key'] = result.get('csv_s3_key')
        _save_to_s3(
            storage_manager, email, session_id, conversation_id,
            'conversation_state.json', conversation_state
        )

        # Send final progress
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=4,
            total_steps=4,
            status='Table ready for validation!',
            progress_percent=100
        )

        # Update runs database
        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='COMPLETE',
                    verbose_status=f'Completed: {len(approved_rows)} rows, CSV generated',
                    percent_complete=100
                )
            except Exception as e:
                logger.warning(f"[EXECUTION] Failed to update run status: {e}")

        result['success'] = True
        logger.info(f"[EXECUTION] Pipeline complete: {len(approved_rows)} rows")

        return result

    except Exception as e:
        result['error'] = f"Execution pipeline error: {str(e)}"
        logger.error(f"[EXECUTION] {result['error']}", exc_info=True)
        return result
