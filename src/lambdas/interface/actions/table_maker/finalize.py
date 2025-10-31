"""
Table Maker Finalization Handler
Handles table acceptance and full table generation with validation launch.

This module:
1. Generates full table from conversation and preview data
2. Creates CSV with column definitions (user download)
3. Creates CSV without column definitions (validation)
4. Stores both in S3 using UnifiedS3Manager
5. Calls existing handle_generate_config_unified() with enhanced payload
6. Stores config with versioning
7. Launches preview validation using existing flow
8. Sends WebSocket updates throughout process
9. Updates runs database with completion status
"""

import json
import logging
import asyncio
import io
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import sys

# Add table_maker to path if running in lambda
if '/var/task/table_maker' not in sys.path:
    sys.path.insert(0, '/var/task/table_maker')

logger = logging.getLogger(__name__)

# WebSocket client for real-time updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger.warning("WebSocket client not available for table maker finalization")


def title_to_snake_case(title: str) -> str:
    """
    Convert title case to snake_case for file naming.

    Examples:
        'Research Applications for Internal Programs' -> 'Research_Applications_for_Internal_Programs'
        'New Clients with GenAI Job Postings' -> 'New_Clients_with_GenAI_Job_Postings'
    """
    import re
    # Replace spaces with underscores
    snake = title.replace(' ', '_')
    # Remove any characters that aren't alphanumeric or underscore
    snake = re.sub(r'[^a-zA-Z0-9_]', '', snake)
    # Remove consecutive underscores
    snake = re.sub(r'_+', '_', snake)
    # Remove leading/trailing underscores
    snake = snake.strip('_')
    return snake


async def handle_table_accept_and_validate(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate validation configuration and optionally populate table with discovered row IDs.

    NEW BEHAVIOR: If final_row_ids is provided, uses pre-discovered rows from row discovery system.
    LEGACY BEHAVIOR: If final_row_ids not provided, uses future_ids from preview data.

    Args:
        event_data: {
            'action': 'acceptTableAndValidate',
            'email': 'user@example.com',
            'session_id': 'session_20251013_123456',
            'conversation_id': 'table_conv_abc123',
            'row_count': 20,  # Optional override
            'final_row_ids': [  # NEW: Pre-discovered rows from row discovery
                {
                    'id_values': {'Company Name': 'Anthropic', 'Website': 'anthropic.com'},
                    'match_score': 0.95,
                    'match_rationale': '...',
                    'source_urls': [...]
                },
                ...
            ]
        }

    Returns:
        {
            'success': True,
            'config_key': 's3://...',
            'config_version': 1
        }
    """
    from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
    from ..generate_config_unified import handle_generate_config_unified
    from dynamodb_schemas import create_run_record, update_run_status

    try:
        # Extract parameters
        email = event_data.get('email')
        session_id = event_data.get('session_id')
        conversation_id = event_data.get('conversation_id')
        row_count = event_data.get('row_count', 20)

        # NEW: Extract pre-discovered row IDs from row discovery system
        final_row_ids = event_data.get('final_row_ids', None)

        # Determine if we're using new row discovery system or legacy future_ids
        using_row_discovery = final_row_ids is not None and len(final_row_ids) > 0

        if not all([email, session_id, conversation_id]):
            return {
                'success': False,
                'error': 'Missing required parameters: email, session_id, or conversation_id'
            }

        # Validate final_row_ids structure if provided
        if using_row_discovery:
            logger.info(f"Using row discovery system with {len(final_row_ids)} pre-discovered rows")
            # Validate structure of first row ID
            if not isinstance(final_row_ids, list) or len(final_row_ids) == 0:
                return {
                    'success': False,
                    'error': 'final_row_ids must be a non-empty list'
                }
            # Check first row has required structure
            first_row = final_row_ids[0]
            if 'id_values' not in first_row:
                return {
                    'success': False,
                    'error': 'Each final_row_id must have id_values dictionary'
                }
        else:
            logger.info("Using legacy future_ids system from preview data")

        logger.info(f"Starting table acceptance and validation for conversation {conversation_id}")
        logger.info(f"[TABLE_FINALIZE] WebSocket client available: {websocket_client is not None}")
        logger.info(f"[TABLE_FINALIZE] Session ID: {session_id}")

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()
        session_path = storage_manager.get_session_path(email, session_id)

        # Send initial progress update
        if websocket_client and session_id:
            try:
                logger.info(f"[TABLE_FINALIZE] Sending initial WebSocket progress (3%)")
                websocket_client.send_to_session(session_id, {
                    'type': 'table_finalization_progress',
                    'session_id': session_id,
                    'progress': 3,
                    'status': 'Loading conversation state...'
                })
                logger.info(f"[TABLE_FINALIZE] Successfully sent initial WebSocket progress")
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")
        else:
            logger.warning(f"[TABLE_FINALIZE] Skipping WebSocket update - client: {websocket_client is not None}, session_id: {bool(session_id)}")

        # Load conversation state from S3 (optional - used for context)
        conversation_state = {}
        conversation_key = f"{session_path}table_maker/conversation_{conversation_id}.json"
        try:
            response = storage_manager.s3_client.get_object(
                Bucket=storage_manager.bucket_name,
                Key=conversation_key
            )
            conversation_state = json.loads(response['Body'].read().decode('utf-8'))
            logger.info(f"Loaded conversation state from S3")
        except Exception as e:
            logger.warning(f"Could not load conversation state (will use preview data for context): {e}")
            # Not fatal - we can work with just the preview data

        # Always load preview data from conversation state (not from request)
        # The conversation state has the proper structure with all the data
        if not conversation_state.get('preview_data'):
            logger.error(f"No preview data in conversation state")
            return {
                'success': False,
                'error': f'No preview data available. Please try generating the preview again.'
            }

        preview_data = conversation_state['preview_data']
        logger.info(f"Loaded preview data from conversation state with {len(preview_data.get('columns', []))} columns")

        # Extract table name from interview context
        interview_context = conversation_state.get('interview_context', {})
        table_name_title = interview_context.get('table_name', '')

        # Convert to snake_case for file naming, fallback to session_id if not available
        if table_name_title:
            table_name_snake = title_to_snake_case(table_name_title)
            logger.info(f"Using table name: '{table_name_title}' -> '{table_name_snake}'")
        else:
            table_name_snake = f"table_{session_id}"
            logger.warning(f"No table name found in conversation state, using default: {table_name_snake}")

        # Reuse existing run_key from conversation (don't create a new one)
        run_key = conversation_state.get('run_key')
        if run_key:
            logger.info(f"Reusing existing run_key from conversation: {run_key}")
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='IN_PROGRESS',
                    verbose_status="Generating full table from conversation...",
                    percent_complete=10,
                    total_rows=row_count
                )
            except Exception as e:
                logger.warning(f"Failed to update run status: {e}")
        else:
            logger.warning("No run_key found in conversation_state, metrics will not be tracked")
            run_key = None

        # Send progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_finalization_progress',
                    'session_id': session_id,
                    'progress': 5,
                    'status': f'Starting configuration generation...'
                })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

        # Extract columns and sample rows from preview for use in both parallel operations
        columns = preview_data.get('columns', [])
        # NOTE: preview_data stores rows as 'rows', not 'sample_rows'
        sample_rows = preview_data.get('rows', preview_data.get('sample_rows', []))
        future_ids = preview_data.get('future_ids', [])

        # IMPORTANT: If sample_rows is empty, try to get it from conversation_state.current_proposal
        if not sample_rows and conversation_state.get('current_proposal'):
            sample_rows = conversation_state['current_proposal'].get('sample_rows', [])
            logger.info(f"Retrieved {len(sample_rows)} sample rows from conversation_state.current_proposal")

        logger.info(f"Preview data has {len(sample_rows)} sample rows and {len(columns)} columns")

        # CREATE clean CSV from preview data (WITHOUT column definitions for config generation)
        # The preview CSV has column definitions which confuse the config lambda
        try:
            from .table_maker_lib.table_generator import TableGenerator
            import csv

            # Destination: {table_name_snake}_input.csv in main session folder
            dest_csv_filename = f"{table_name_snake}_input.csv"
            dest_csv_key = f"{session_path}{dest_csv_filename}"
            tmp_csv_path = f"/tmp/{dest_csv_filename}"

            logger.info(f"Creating clean CSV (without definitions) at {tmp_csv_path}")

            # Get all rows (sample rows + ID rows from either system)
            all_rows = list(sample_rows)

            # NEW PATH: Use pre-discovered rows from row discovery
            if using_row_discovery:
                logger.info(f"Adding {len(final_row_ids)} rows from row discovery system")
                for discovered_row in final_row_ids:
                    partial_row = {}
                    id_values = discovered_row.get('id_values', {})
                    for col in columns:
                        col_name = col['name']
                        if col.get('is_identification', False) and col_name in id_values:
                            partial_row[col_name] = id_values[col_name]
                        else:
                            partial_row[col_name] = ''
                    all_rows.append(partial_row)
                logger.info(f"Writing CSV with {len(all_rows)} rows ({len(sample_rows)} complete + {len(final_row_ids)} from row discovery)")

            # LEGACY PATH: Use future_ids from preview data
            elif future_ids:
                logger.info(f"Adding {len(future_ids)} rows from legacy future_ids system")
                for future_id in future_ids:
                    partial_row = {}
                    for col in columns:
                        col_name = col['name']
                        if col.get('is_identification', False) and col_name in future_id:
                            partial_row[col_name] = future_id[col_name]
                        else:
                            partial_row[col_name] = ''
                    all_rows.append(partial_row)
                logger.info(f"Writing CSV with {len(all_rows)} rows ({len(sample_rows)} complete + {len(future_ids)} ID-only)")

            # Write clean CSV without column definitions
            with open(tmp_csv_path, 'w', newline='', encoding='utf-8') as f:
                if all_rows:
                    fieldnames = [col['name'] for col in columns]
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_rows)

            # Upload to S3
            with open(tmp_csv_path, 'rb') as f:
                csv_content = f.read()

            storage_manager.s3_client.put_object(
                Bucket=storage_manager.bucket_name,
                Key=dest_csv_key,
                Body=csv_content,
                ContentType='text/csv',
                Metadata={
                    'session-id': session_id,
                    'email': email,
                    'conversation-id': conversation_id,
                    'source': 'table_maker_preview',
                    'row-count': str(len(all_rows)),
                    'column-count': str(len(columns)),
                    'is-clean': 'true',  # Tell parsers this is already clean
                    'skip-table-cleaning': 'true'  # Don't apply table cleaning to this file
                }
            )

            logger.info(f"Successfully created clean CSV at {dest_csv_key} for config generation")
            logger.info(f"File: {dest_csv_filename}, Rows: {len(all_rows)}, Columns: {len(columns)}")

            # Clean up temp file
            os.unlink(tmp_csv_path)

        except Exception as e:
            logger.error(f"Failed to create clean CSV: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Cannot proceed without clean CSV: {e}")

        # Define parallel async functions
        async def generate_full_table():
            """
            Generate and store full table with all rows.

            NEW BEHAVIOR: If using row discovery, creates rows from final_row_ids.
            LEGACY BEHAVIOR: If using future_ids, creates placeholder rows.
            """
            try:
                from .table_maker_lib.table_generator import TableGenerator
                from .table_maker_lib.row_expander import RowExpander
                from .table_maker_lib.prompt_loader import PromptLoader
                from .table_maker_lib.schema_validator import SchemaValidator
                from ai_api_client import AIAPIClient

                # Initialize components
                import os
                prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
                schemas_dir = os.path.join(os.path.dirname(__file__), 'schemas')

                table_generator = TableGenerator()
                ai_client = AIAPIClient()
                prompt_loader = PromptLoader(prompts_dir)
                schema_validator = SchemaValidator(schemas_dir)
                row_expander = RowExpander(ai_client, prompt_loader, schema_validator)

                # Calculate how many additional rows we need
                existing_row_count = len(sample_rows)
                additional_rows_needed = max(0, row_count - existing_row_count)

                logger.info(f"Existing rows: {existing_row_count}, Additional needed: {additional_rows_needed}")

                all_rows = list(sample_rows)  # Start with preview rows

                # NEW PATH: Use pre-discovered rows from row discovery system
                if using_row_discovery:
                    logger.info(f"Using {len(final_row_ids)} pre-discovered rows from row discovery system")
                    for discovered_row in final_row_ids:
                        # Create a row with ID columns filled in from discovered row
                        placeholder_row = {}
                        id_values = discovered_row.get('id_values', {})
                        for col in columns:
                            col_name = col['name']
                            if col.get('is_identification', False) and col_name in id_values:
                                placeholder_row[col_name] = id_values[col_name]
                            else:
                                # Leave research columns empty for population
                                placeholder_row[col_name] = ''
                        all_rows.append(placeholder_row)
                    logger.info(f"Added {len(final_row_ids)} rows from row discovery. Total rows: {len(all_rows)}")

                # LEGACY PATH: Append empty rows with future_ids for validator to fill in
                elif additional_rows_needed > 0 and future_ids:
                    logger.info(f"Appending {min(additional_rows_needed, len(future_ids))} placeholder rows with legacy future IDs")
                    for i, future_id_set in enumerate(future_ids[:additional_rows_needed]):
                        # Create a row with ID columns filled in, other columns empty
                        placeholder_row = {}
                        for col in columns:
                            col_name = col['name']
                            # If this is an ID column and we have a future ID value, use it
                            if col.get('is_identification', False) and col_name in future_id_set:
                                placeholder_row[col_name] = future_id_set[col_name]
                            else:
                                # Leave other columns empty for validator to fill
                                placeholder_row[col_name] = ''
                        all_rows.append(placeholder_row)
                    logger.info(f"Added {len(future_ids[:additional_rows_needed])} placeholder rows. Total rows: {len(all_rows)}")

                # Progress update
                if websocket_client and session_id:
                    try:
                        websocket_client.send_to_session(session_id, {
                            'type': 'table_finalization_progress',
                            'session_id': session_id,
                            'progress': 80,
                            'status': 'Created table with placeholder rows. Creating CSV files...'
                        })
                    except Exception as e:
                        logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

                # Create CSV WITH column definitions (for user download)
                user_csv_filename = f"{table_name_snake}.csv"
                user_csv_path = f"/tmp/{user_csv_filename}"

                generation_result = table_generator.generate_csv(
                    columns=columns,
                    rows=all_rows,
                    output_path=user_csv_path,
                    include_metadata=True  # Include column definitions
                )

                if not generation_result['success']:
                    raise Exception(f"Failed to generate user CSV: {generation_result.get('error')}")

                # Store user CSV in S3
                with open(user_csv_path, 'rb') as f:
                    user_csv_content = f.read()

                user_csv_key = f"{session_path}{user_csv_filename}"
                storage_manager.s3_client.put_object(
                    Bucket=storage_manager.bucket_name,
                    Key=user_csv_key,
                    Body=user_csv_content,
                    ContentType='text/csv',
                    Metadata={
                        'session_id': session_id,
                        'email': email,
                        'conversation_id': conversation_id,
                        'row_count': str(len(all_rows)),
                        'includes_definitions': 'true'
                    }
                )

                logger.info(f"Stored user CSV with definitions: {user_csv_key}")

                # Create CSV WITHOUT column definitions (for validation)
                validation_csv_filename = f"{table_name_snake}_for_validation.csv"
                validation_csv_path = f"/tmp/{validation_csv_filename}"

                validation_result = table_generator.generate_csv(
                    columns=columns,
                    rows=all_rows,
                    output_path=validation_csv_path,
                    include_metadata=False  # NO column definitions for validation
                )

                if not validation_result['success']:
                    raise Exception(f"Failed to generate validation CSV: {validation_result.get('error')}")

                # Store validation CSV in S3
                with open(validation_csv_path, 'rb') as f:
                    validation_csv_content = f.read()

                validation_csv_key = f"{session_path}{validation_csv_filename}"
                storage_manager.s3_client.put_object(
                    Bucket=storage_manager.bucket_name,
                    Key=validation_csv_key,
                    Body=validation_csv_content,
                    ContentType='text/csv',
                    Metadata={
                        'session_id': session_id,
                        'email': email,
                        'conversation_id': conversation_id,
                        'row_count': str(len(all_rows)),
                        'includes_definitions': 'false'
                    }
                )

                logger.info(f"Stored validation CSV without definitions: {validation_csv_key}")

                # UPDATE Excel file with all expanded rows (initial version was created with preview rows)
                try:
                    excel_filename = f"{table_name_snake}.xlsx"
                    excel_path = f"/tmp/{excel_filename}_full"

                    # Write to Excel using xlsxwriter
                    workbook = xlsxwriter.Workbook(excel_path)
                    worksheet = workbook.add_worksheet()

                    # Write headers
                    if all_rows:
                        headers = list(all_rows[0].keys())
                        for col_idx, header in enumerate(headers):
                            worksheet.write(0, col_idx, header)

                        # Write all data rows (preview + expanded)
                        for row_idx, row_data in enumerate(all_rows, start=1):
                            for col_idx, header in enumerate(headers):
                                worksheet.write(row_idx, col_idx, row_data.get(header, ''))

                    workbook.close()

                    # Update Excel file in S3 with full data
                    with open(excel_path, 'rb') as f:
                        excel_content = f.read()

                    storage_manager.store_excel_file(
                        email=email,
                        session_id=session_id,
                        file_content=excel_content,
                        filename=excel_filename
                    )

                    logger.info(f"Updated Excel file with all {len(all_rows)} rows: {excel_filename}")
                except Exception as e:
                    logger.warning(f"Failed to update Excel file with full data: {e}")
                    # Don't fail the entire operation if Excel update fails

                # Update run status for table generation completion
                if run_key:
                    update_run_status(
                        session_id=session_id,
                        run_key=run_key,
                        status='COMPLETED',
                        run_type="Table Generation",
                        verbose_status=f"Generated table with {len(all_rows)} rows",
                        percent_complete=100,
                        processed_rows=len(all_rows),
                        total_rows=row_count
                    )

                # Return results
                return {
                    'all_rows': all_rows,
                    'user_csv_key': user_csv_key,
                    'validation_csv_key': validation_csv_key,
                    'user_csv_filename': user_csv_filename
                }

            except Exception as e:
                logger.error(f"Failed to generate full table: {e}")
                if run_key:
                    update_run_status(
                        session_id=session_id,
                        run_key=run_key,
                        status='FAILED',
                        run_type="Table Generation",
                        verbose_status="Failed to generate full table",
                        percent_complete=0,
                        error_message=str(e)
                    )
                raise

        async def generate_config():
            """Generate validation configuration"""
            try:
                logger.info(f"[TABLE_FINALIZE] Starting config generation with WebSocket updates")

                # Create websocket callback for config generation (must be async)
                async def config_websocket_callback(message):
                    """Send WebSocket updates from config generation"""
                    if websocket_client and session_id:
                        try:
                            websocket_client.send_to_session(session_id, message)
                            logger.info(f"[TABLE_FINALIZE] Config generation sent WebSocket: {message.get('status', 'no status')}")
                        except Exception as e:
                            logger.warning(f"[TABLE_FINALIZE] Failed to send config WebSocket update: {e}")

                # Extract identification columns and ensure at least 1 remains
                # (Match logic from config_bridge.py to keep first ID column + non-researchable ones)
                from .config_bridge import _is_researchable_id_column

                id_columns_list = [col for col in columns if col.get('importance', '').upper() == 'ID']
                columns_to_keep_as_id = set()

                if id_columns_list:
                    # Always keep first ID column as ID
                    first_id_col = id_columns_list[0]
                    columns_to_keep_as_id.add(first_id_col['name'])

                    # Keep non-researchable ones as ID too
                    for col in id_columns_list[1:]:
                        if not _is_researchable_id_column(col):
                            columns_to_keep_as_id.add(col['name'])

                    logger.info(
                        f"[TABLE_FINALIZE] Found {len(id_columns_list)} ID columns. "
                        f"Keeping {len(columns_to_keep_as_id)} as ID (first: '{first_id_col['name']}'). "
                        f"Converting {len(id_columns_list) - len(columns_to_keep_as_id)} to RESEARCH."
                    )

                # Build column_analysis with adjusted importance
                column_analysis = {}
                for col in columns:
                    col_name = col['name']
                    importance = col.get('importance', 'MEDIUM')

                    # Convert researchable ID columns to RESEARCH (except those in keep set)
                    if importance.upper() == 'ID':
                        if col_name not in columns_to_keep_as_id and _is_researchable_id_column(col):
                            importance = 'RESEARCH'
                            logger.info(f"[TABLE_FINALIZE] Converting '{col_name}' from ID to RESEARCH for validation")

                    column_analysis[col_name] = {
                        'name': col_name,
                        'description': col.get('description', ''),
                        'data_type': col.get('format', 'String'),
                        'importance': importance,
                        'sample_values': [row.get(col_name, '') for row in sample_rows[:3]]
                    }

                # Extract final identification columns after conversion
                identification_columns = [
                    name for name, info in column_analysis.items()
                    if info['importance'].upper() == 'ID'
                ]

                logger.info(f"[TABLE_FINALIZE] Final ID columns for config: {identification_columns}")

                # Build table_analysis structure for config generation
                table_analysis = {
                    'basic_info': {
                        'filename': f"{table_name_snake}.csv",
                        'total_rows': len(sample_rows),  # Use sample_rows count for preview
                        'total_columns': len(columns),
                        'has_header': True
                    },
                    'column_analysis': column_analysis,
                    'domain_info': {
                        'domain': conversation_state.get('context_research', {}).get('domain', 'research'),
                        'insights': conversation_state.get('context_research', {}).get('insights', '')
                    },
                    'metadata': {
                        'file_type': 'csv',
                        'generated_by': 'table_maker',
                        'conversation_id': conversation_id
                    },
                    'conversation_context': {
                        'research_purpose': conversation_state.get('messages', [{}])[0].get('content', ''),
                        'ai_reasoning': conversation_state.get('messages', [{}])[-1].get('content', '') if len(conversation_state.get('messages', [])) > 1 else '',
                        'column_details': columns,
                        'identification_columns': identification_columns,
                        'conversation_history': conversation_state.get('messages', []),
                        'context_research': conversation_state.get('context_research', {}),
                        'tablewide_research': conversation_state.get('tablewide_research', '')  # Add tablewide_research
                    }
                }

                logger.info("Built enhanced table_analysis with conversation_context")

                # NO WEBSOCKET UPDATE - avoid race condition with table generation

                # Extract tablewide_research for embedding in configuration
                tablewide_research = table_analysis['conversation_context'].get('tablewide_research', '')

                # Build instructions with tablewide research context
                instructions = f"Generate optimal validation configuration for AI-generated research table. Research purpose: {table_analysis['conversation_context']['research_purpose'][:200]}..."

                if tablewide_research:
                    instructions += f"\n\nHere is tablewide concise research to embed in the general/column notes: {tablewide_research}"
                    logger.info(f"[TABLE_FINALIZE] Including tablewide_research in config generation instructions")

                # Call existing handle_generate_config_unified() with enhanced payload and websocket callback
                config_generation_payload = {
                    'email': email,
                    'session_id': session_id,
                    'table_analysis': table_analysis,
                    'instructions': instructions,
                    'existing_config': None  # No existing config for new table
                }

                # The function signature expects positional args
                # Pass table_maker_mode=True to skip CSV parsing
                config_result = await handle_generate_config_unified(
                    config_generation_payload,
                    config_websocket_callback,  # Pass as second positional arg, not keyword
                    table_maker_mode=True  # Enable Table Maker mode to skip CSV parsing
                )

                if not config_result.get('success'):
                    error_msg = config_result.get('error', 'Unknown error')
                    logger.error(f"Config generation failed: {error_msg}")
                    raise Exception(f'Failed to generate validation config: {error_msg}')

                config_version = config_result.get('config_version', 1)
                config_s3_key = config_result.get('config_s3_key', '')

                logger.info(f"Config generated successfully: version {config_version}, key {config_s3_key}")

                # Return results
                return {
                    'config_version': config_version,
                    'config_s3_key': config_s3_key
                }

            except Exception as e:
                logger.error(f"Failed to generate config: {e}")
                raise

        # Only run config generation (no table generation)
        try:
            config_result = await generate_config()
        except Exception as config_error:
            logger.error(f"Config generation failed: {config_error}")
            return {'success': False, 'error': f'Config generation failed: {str(config_error)}'}

        # Extract config results
        config_version = config_result['config_version']
        config_s3_key = config_result['config_s3_key']

        # FINAL COMPLETION - Config generation is complete
        logger.info(f"[TABLE_FINALIZE] Config generation complete - sending final WebSocket update")
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_finalization_progress',
                    'session_id': session_id,
                    'progress': 100,
                    'status': 'Table generation complete! Ready for validation.',  # Use standard message
                    'table_filename': f'{table_name_snake}_input.csv'  # Tell frontend the table filename
                })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send final WebSocket update: {e}")

        # Return simplified result (no table CSVs)
        result = {
            'success': True,
            'config_key': config_s3_key,
            'config_version': config_version,
            'conversation_id': conversation_id
        }

        logger.info(f"Config generation completed successfully for conversation {conversation_id}")

        return result

    except Exception as e:
        logger.error(f"Table finalization failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'error': f'Table finalization failed: {str(e)}'
        }


def handle_table_accept_and_validate_async(event_data: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Async wrapper for table finalization - sends request to SQS and returns immediately.
    This prevents frontend timeouts for long-running table generation operations.
    """
    from interface_lambda.utils.helpers import create_response
    from interface_lambda.core.sqs_service import send_table_finalization_request

    try:
        logger.info(f"[TABLE_FINALIZE_ASYNC] Sending table finalization request to SQS: {event_data.keys()}")

        # Extract key parameters
        email = event_data.get('email')
        session_id = event_data.get('session_id')
        conversation_id = event_data.get('conversation_id')

        if not all([email, session_id, conversation_id]):
            return create_response(400, {
                'success': False,
                'error': 'Missing required parameters: email, session_id, or conversation_id'
            })

        # Send to SQS for background processing
        message_data = {
            'email': email,
            'session_id': session_id,
            'conversation_id': conversation_id,
            'row_count': event_data.get('row_count', 20),
            'table_config': event_data.get('table_config'),  # Include preview data if present
            'final_row_ids': event_data.get('final_row_ids'),  # NEW: Include pre-discovered rows
            'action': 'acceptTableAndValidate'
        }

        message_id = send_table_finalization_request(message_data)

        if not message_id:
            logger.error("[TABLE_FINALIZE_ASYNC] Failed to send SQS message")
            return create_response(500, {
                'success': False,
                'error': 'Failed to queue table finalization request'
            })

        logger.info(f"[TABLE_FINALIZE_ASYNC] Successfully queued table finalization: MessageId={message_id}")

        # Send initial WebSocket progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_finalization_progress',
                    'session_id': session_id,
                    'progress': 0,
                    'status': 'Table finalization queued for processing...'
                })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE_ASYNC] Failed to send WebSocket update: {e}")

        # Return immediately with processing status
        return create_response(200, {
            'success': True,
            'status': 'processing',
            'message': 'Table finalization started. You will receive updates via WebSocket.',
            'session_id': session_id,
            'conversation_id': conversation_id,
            'message_id': message_id
        })

    except Exception as e:
        logger.error(f"[TABLE_FINALIZE_ASYNC] Async wrapper failed: {str(e)}")
        import traceback
        logger.error(f"[TABLE_FINALIZE_ASYNC] Traceback: {traceback.format_exc()}")
        return create_response(500, {'success': False, 'error': str(e)})


# Main handler
def handle(request_data, context):
    """Main handler that routes table finalization requests"""
    from interface_lambda.utils.helpers import create_response

    action = request_data.get('action', 'acceptTableAndValidate')

    if action == 'acceptTableAndValidate':
        # Use async wrapper to avoid timeouts
        return handle_table_accept_and_validate_async(request_data, context)
    else:
        return create_response(400, {'error': f'Unknown table finalization action: {action}'})
