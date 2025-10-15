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


async def handle_table_accept_and_validate(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate full table, create config, and run preview validation.

    Args:
        event_data: {
            'action': 'acceptTableAndValidate',
            'email': 'user@example.com',
            'session_id': 'session_20251013_123456',
            'conversation_id': 'table_conv_abc123',
            'row_count': 20  # Optional override
        }

    Returns:
        {
            'success': True,
            'table_csv_key': 's3://...',
            'validation_csv_key': 's3://...',  # Without column definitions
            'config_key': 's3://...',
            'config_version': 1,
            'preview_validation_results': {...}
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

        if not all([email, session_id, conversation_id]):
            return {
                'success': False,
                'error': 'Missing required parameters: email, session_id, or conversation_id'
            }

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

        # Get preview data from request or load from S3
        preview_data = event_data.get('table_config')

        if not preview_data:
            # Fallback: try loading from S3
            preview_key = f"{session_path}table_maker/preview_{conversation_id}.json"
            try:
                response = storage_manager.s3_client.get_object(
                    Bucket=storage_manager.bucket_name,
                    Key=preview_key
                )
                preview_data = json.loads(response['Body'].read().decode('utf-8'))
            except Exception as e:
                logger.error(f"No preview data in request and failed to load from S3: {e}")
                return {
                    'success': False,
                    'error': f'No preview data available. Please try generating the preview again.'
                }

        logger.info(f"Using preview data with {len(preview_data.get('columns', []))} columns")

        # Create run record for table generation
        try:
            run_key = create_run_record(
                session_id=session_id,
                email=email,
                total_rows=row_count,
                batch_size=1,
                run_type="Table Generation"
            )
            logger.info(f"Created run record with run_key: {run_key}")

            update_run_status(
                session_id=session_id,
                run_key=run_key,
                status='IN_PROGRESS',
                run_type="Table Generation",
                verbose_status="Generating full table from conversation...",
                percent_complete=10,
                processed_rows=0,
                total_rows=row_count
            )
        except Exception as e:
            logger.warning(f"Failed to create run record: {e}")
            run_key = None

        # Send progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_finalization_progress',
                    'session_id': session_id,
                    'progress': 5,
                    'status': f'Generating validation configuration...'
                })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

        # Extract columns and sample rows from preview for use in both parallel operations
        columns = preview_data.get('columns', [])
        sample_rows = preview_data.get('sample_rows', [])
        future_ids = preview_data.get('future_ids', [])

        logger.info(f"Preview data has {len(sample_rows)} sample rows and {len(columns)} columns")

        # CREATE EXCEL FILE FIRST (before parallel operations) using preview rows
        # This allows config generation to start immediately while table expansion continues
        try:
            import xlsxwriter
            # Use "excel_file.xlsx" which becomes "excel_file_input.xlsx" after store_excel_file adds suffix
            excel_filename = f"excel_file.xlsx"
            excel_path = f"/tmp/{excel_filename}"

            # Write preview rows to Excel
            workbook = xlsxwriter.Workbook(excel_path)
            worksheet = workbook.add_worksheet()

            # Write headers - use columns if sample_rows is empty
            if sample_rows:
                headers = list(sample_rows[0].keys())
            elif columns:
                headers = [col['name'] for col in columns]
            else:
                raise Exception("No sample rows or columns available to create Excel file")

            # Write header row
            for col_idx, header in enumerate(headers):
                worksheet.write(0, col_idx, header)

            # Write sample data rows (if any)
            if sample_rows:
                for row_idx, row_data in enumerate(sample_rows, start=1):
                    for col_idx, header in enumerate(headers):
                        worksheet.write(row_idx, col_idx, row_data.get(header, ''))

            workbook.close()

            # Store Excel file in S3 (config generation needs this)
            with open(excel_path, 'rb') as f:
                excel_content = f.read()

            storage_manager.store_excel_file(
                email=email,
                session_id=session_id,
                file_content=excel_content,
                filename=excel_filename
            )

            logger.info(f"Created initial Excel file with {len(sample_rows)} preview rows for config generation")
        except Exception as e:
            logger.error(f"Failed to create initial Excel file: {e}")
            raise Exception(f"Cannot proceed without Excel file for config generation: {e}")

        # Define parallel async functions
        async def generate_full_table():
            """Generate and store full table with all rows"""
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

                if additional_rows_needed > 0:
                    # Build expansion request based on future IDs and conversation context
                    research_purpose = ""
                    if conversation_state.get('messages'):
                        research_purpose = conversation_state['messages'][0].get('content', '')

                    # Fallback: use preview_data description if available
                    if not research_purpose and preview_data.get('metadata'):
                        research_purpose = preview_data['metadata'].get('description', 'Generate comprehensive research data')

                    # Create expansion request
                    expansion_request = f"""
Generate {additional_rows_needed} additional rows based on the research purpose: {research_purpose}

Use these future ID combinations as a guide:
{json.dumps(future_ids, indent=2)}

Ensure variety and relevance to the research domain.
"""

                    # Calculate batches for progress tracking
                    batch_size = 10
                    batches_needed = (additional_rows_needed + batch_size - 1) // batch_size

                    # Progress update
                    if websocket_client and session_id:
                        try:
                            websocket_client.send_to_session(session_id, {
                                'type': 'table_finalization_progress',
                                'session_id': session_id,
                                'progress': 20,
                                'status': f'Config generated! Expanding table to {row_count} rows ({batches_needed} batches)...'
                            })
                        except Exception as e:
                            logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

                    # Define progress callback for batch updates
                    def send_batch_progress(batch_num, total_batches, rows_generated):
                        """Send WebSocket progress update after each batch. Progress range: 20-80%"""
                        if websocket_client and session_id:
                            try:
                                # Linear progress from 20% to 80% across batches
                                batch_progress = 20 + int((batch_num / total_batches) * 60)
                                websocket_client.send_to_session(session_id, {
                                    'type': 'table_finalization_progress',
                                    'session_id': session_id,
                                    'progress': batch_progress,
                                    'status': f'Generated {rows_generated}/{additional_rows_needed} rows (batch {batch_num}/{total_batches})...'
                                })
                                logger.info(f"[TABLE_FINALIZE] Sent batch progress: {batch_progress}% (batch {batch_num}/{total_batches})")
                            except Exception as e:
                                logger.warning(f"[TABLE_FINALIZE] Failed to send batch progress: {e}")

                    # Expand rows iteratively
                    table_structure = {
                        'columns': columns,
                        'proposed_columns': columns
                    }

                    logger.info("[DEBUG] About to call expand_rows_iteratively...")
                    expansion_result = await row_expander.expand_rows_iteratively(
                        table_structure=table_structure,
                        existing_rows=sample_rows,
                        expansion_request=expansion_request,
                        total_rows_needed=additional_rows_needed,
                        batch_size=batch_size,
                        model="claude-sonnet-4-5",
                        progress_callback=send_batch_progress
                    )

                    logger.info("[DEBUG] expand_rows_iteratively returned, checking success...")

                    if not expansion_result['success']:
                        logger.error(f"Row expansion failed: {expansion_result.get('errors', [])}")
                        raise Exception(f"Failed to generate full table: {expansion_result.get('errors', ['Unknown error'])}")

                    logger.info(f"[DEBUG] Expansion successful, extending all_rows with {len(expansion_result['expanded_rows'])} rows...")
                    all_rows.extend(expansion_result['expanded_rows'])
                    logger.info(f"Generated {len(expansion_result['expanded_rows'])} additional rows")

                # Progress update
                if websocket_client and session_id:
                    try:
                        websocket_client.send_to_session(session_id, {
                            'type': 'table_finalization_progress',
                            'session_id': session_id,
                            'progress': 80,
                            'status': 'Row expansion complete! Creating CSV files...'
                        })
                    except Exception as e:
                        logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

                # Create CSV WITH column definitions (for user download)
                user_csv_filename = f"table_{session_id}.csv"
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
                validation_csv_filename = f"table_{session_id}_for_validation.csv"
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
                    excel_filename = f"excel_file.xlsx"
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
            """Generate validation configuration in parallel"""
            try:
                # Progress update
                if websocket_client and session_id:
                    try:
                        websocket_client.send_to_session(session_id, {
                            'type': 'table_finalization_progress',
                            'session_id': session_id,
                            'progress': 85,
                            'status': 'Generating validation configuration...'
                        })
                    except Exception as e:
                        logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

                # Extract identification columns
                identification_columns = [
                    col['name'] for col in columns if col.get('is_identification', False)
                ]

                # Build table_analysis structure for config generation
                # IMPORTANT: Use sample_rows (from preview) for sample_values since we're running in parallel
                table_analysis = {
                    'basic_info': {
                        'filename': f"table_{session_id}.csv",
                        'total_rows': len(sample_rows),  # Use sample_rows count for preview
                        'total_columns': len(columns),
                        'has_header': True
                    },
                    'column_analysis': {
                        col['name']: {
                            'name': col['name'],
                            'description': col.get('description', ''),
                            'data_type': col.get('format', 'String'),
                            'importance': col.get('importance', 'MEDIUM'),
                            'sample_values': [row.get(col['name'], '') for row in sample_rows[:3]],  # Use sample_rows
                            'is_identification': col.get('is_identification', False)
                        }
                        for col in columns
                    },
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
                        'context_research': conversation_state.get('context_research', {})
                    }
                }

                logger.info("Built enhanced table_analysis with conversation_context")

                # Progress update
                if websocket_client and session_id:
                    try:
                        websocket_client.send_to_session(session_id, {
                            'type': 'table_finalization_progress',
                            'session_id': session_id,
                            'progress': 90,
                            'status': 'Finalizing validation configuration...'
                        })
                    except Exception as e:
                        logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

                # Call existing handle_generate_config_unified() with enhanced payload
                config_generation_payload = {
                    'email': email,
                    'session_id': session_id,
                    'table_analysis': table_analysis,
                    'instructions': f"Generate optimal validation configuration for AI-generated research table. Research purpose: {table_analysis['conversation_context']['research_purpose'][:200]}...",
                    'existing_config': None  # No existing config for new table
                }

                config_result = await handle_generate_config_unified(
                    config_generation_payload
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

        # Run table generation and config generation in parallel
        table_result, config_result = await asyncio.gather(
            generate_full_table(),
            generate_config(),
            return_exceptions=True
        )

        # Handle results
        if isinstance(table_result, Exception):
            logger.error(f"Table generation failed: {table_result}")
            return {'success': False, 'error': f'Table generation failed: {str(table_result)}'}

        if isinstance(config_result, Exception):
            logger.error(f"Config generation failed: {config_result}")
            return {'success': False, 'error': f'Config generation failed: {str(config_result)}'}

        # Extract results
        all_rows = table_result['all_rows']
        user_csv_key = table_result['user_csv_key']
        validation_csv_key = table_result['validation_csv_key']
        user_csv_filename = table_result['user_csv_filename']

        config_version = config_result['config_version']
        config_s3_key = config_result['config_s3_key']

        # Progress update - Table generation complete
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_finalization_progress',
                    'session_id': session_id,
                    'progress': 100,
                    'status': 'Table generation complete! Ready for validation.'
                })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

        # Return comprehensive result
        result = {
            'success': True,
            'table_csv_key': user_csv_key,
            'validation_csv_key': validation_csv_key,
            'config_key': config_s3_key,
            'config_version': config_version,
            'row_count': len(all_rows),
            'column_count': len(columns),
            'download_url': storage_manager.generate_presigned_url(user_csv_key, expiration=86400),  # 24 hours
            'conversation_id': conversation_id
        }

        logger.info(f"Table finalization completed successfully: {len(all_rows)} rows, {len(columns)} columns")

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


def handle_table_accept_and_validate_sync(event_data: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Synchronous wrapper for table finalization (for direct HTTP calls)
    DEPRECATED: Use handle_table_accept_and_validate_async instead to avoid timeouts.
    """
    from interface_lambda.utils.helpers import create_response

    try:
        logger.info(f"[TABLE_FINALIZE_SYNC] Starting sync wrapper with event_data: {event_data.keys()}")

        # Run the async function
        result = asyncio.run(handle_table_accept_and_validate(event_data))

        logger.info(f"[TABLE_FINALIZE_SYNC] Async function completed with success={result.get('success')}")

        if result.get('success'):
            return create_response(200, result)
        else:
            logger.error(f"[TABLE_FINALIZE_SYNC] Result indicated failure: {result.get('error')}")
            return create_response(500, result)

    except Exception as e:
        logger.error(f"[TABLE_FINALIZE_SYNC] Sync table finalization failed: {str(e)}")
        import traceback
        logger.error(f"[TABLE_FINALIZE_SYNC] Traceback: {traceback.format_exc()}")
        return create_response(500, {'success': False, 'error': str(e)})


# Main handler
def handle(request_data, context):
    """Main handler that routes table finalization requests"""
    action = request_data.get('action', 'acceptTableAndValidate')

    if action == 'acceptTableAndValidate':
        return handle_table_accept_and_validate_sync(request_data, context)
    else:
        from interface_lambda.utils.helpers import create_response
        return create_response(400, {'error': f'Unknown table finalization action: {action}'})
