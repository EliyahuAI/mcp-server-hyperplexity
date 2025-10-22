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
    api_result: Dict[str, Any],
    call_description: str
) -> None:
    """
    Add API call metrics to runs database.

    Args:
        session_id: Session identifier
        run_key: Run tracking key
        api_result: Result dict from handler with enhanced_data
        call_description: Description of the call
    """
    if not run_key:
        logger.warning("[EXECUTION] No run_key, skipping metrics update")
        return

    try:
        from dynamodb_schemas import get_run_status, create_or_update_run_with_aggregated_metrics

        # Extract enhanced_data from result
        enhanced_data = api_result.get('enhanced_data', {})
        model_used = api_result.get('model_used', 'unknown')
        cost = api_result.get('cost', 0.0)

        # Read existing run
        existing_run = get_run_status(session_id, run_key)
        if not existing_run:
            logger.warning(f"[EXECUTION] Run not found: {session_id}/{run_key}")
            return

        # Extract existing metrics
        existing_calls = existing_run.get('call_metrics_list', [])

        # Build new call entry
        new_call = {
            'call_description': call_description,
            'model': model_used,
            'enhanced_data': enhanced_data,
            'timestamp': datetime.now().isoformat(),
            'cost': cost
        }

        # Append to calls list
        updated_calls = existing_calls + [new_call]

        # Re-aggregate all calls
        create_or_update_run_with_aggregated_metrics(
            session_id=session_id,
            run_key=run_key,
            call_metrics_list=updated_calls,
            status='IN_PROGRESS'
        )

        logger.info(f"[EXECUTION] Added API call to runs: {call_description} (${cost:.4f})")

    except Exception as e:
        logger.error(f"[EXECUTION] Failed to add API call to runs: {e}")


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
                session_id, run_key, column_result,
                'Column Definition - Defining columns and search strategy'
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

                    _add_api_call_to_runs(
                        session_id, run_key, round_data,
                        f"Row Discovery - {subdomain_name} - Round {round_num} ({model}-{context})"
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

        try:
            # Get config for QC review
            qc_config = config.get('qc_review', {})
            qc_model = qc_config.get('model', 'claude-sonnet-4-5')
            qc_max_tokens = qc_config.get('max_tokens', 16000)
            min_qc_score = qc_config.get('min_qc_score', 0.5)

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
                max_rows=999  # No artificial cutoff
            )

            if not qc_result.get('success'):
                logger.warning(f"[EXECUTION] QC review failed: {qc_result.get('error')}")
                # Use original rows if QC fails
                approved_rows = final_rows
            else:
                approved_rows = qc_result.get('approved_rows', final_rows)

                # Track API call
                _add_api_call_to_runs(
                    session_id, run_key, qc_result,
                    'QC Review - Filtering and prioritizing rows'
                )

                # Save to S3
                _save_to_s3(
                    storage_manager, email, session_id, conversation_id,
                    'qc_result.json', qc_result
                )

            result['approved_rows'] = approved_rows
            result['row_count'] = len(approved_rows)

            logger.info(f"[EXECUTION] Step 4 complete: {len(approved_rows)} approved rows")

            # Send progress update with approved_row_count
            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=4,
                total_steps=4,
                status='Finalizing validation configuration...',
                progress_percent=80,
                approved_row_count=len(approved_rows)
            )

        except Exception as e:
            logger.error(f"[EXECUTION] QC review error: {e}", exc_info=True)
            # Continue with discovered rows if QC fails
            approved_rows = final_rows
            result['approved_rows'] = approved_rows
            result['row_count'] = len(approved_rows)

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
