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

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()
        session_path = storage_manager.get_session_path(email, session_id)

        # Send initial progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                'type': 'table_finalization_progress',
                'progress': 5,
                'status': 'Loading conversation state...'
            })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

        # Load conversation state from S3
        conversation_key = f"{session_path}table_maker/conversation_{conversation_id}.json"
        try:
            response = storage_manager.s3_client.get_object(
                Bucket=storage_manager.bucket_name,
                Key=conversation_key
            )
            conversation_state = json.loads(response['Body'].read().decode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to load conversation state: {e}")
            return {
                'success': False,
                'error': f'Failed to load conversation state: {str(e)}'
            }

        # Load preview data from S3
        preview_key = f"{session_path}table_maker/preview_{conversation_id}.json"
        try:
            response = storage_manager.s3_client.get_object(
                Bucket=storage_manager.bucket_name,
                Key=preview_key
            )
            preview_data = json.loads(response['Body'].read().decode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to load preview data: {e}")
            return {
                'success': False,
                'error': f'Failed to load preview data: {str(e)}'
            }

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
                'progress': 15,
                'status': f'Generating {row_count} rows for full table...'
            })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

        # Generate full table using TableGenerator
        try:
            from table_maker.src.table_generator import TableGenerator
            from table_maker.src.row_expander import RowExpander
            from table_maker.src.prompt_loader import PromptLoader
            from table_maker.src.schema_validator import SchemaValidator
            from shared.ai_api_client import AIAPIClient

            # Initialize components
            table_generator = TableGenerator()
            ai_client = AIAPIClient()
            prompt_loader = PromptLoader()
            schema_validator = SchemaValidator()
            row_expander = RowExpander(ai_client, prompt_loader, schema_validator)

            # Get table structure from preview
            columns = preview_data.get('columns', [])
            sample_rows = preview_data.get('sample_rows', [])
            future_ids = preview_data.get('future_ids', [])

            # Calculate how many additional rows we need
            existing_row_count = len(sample_rows)
            additional_rows_needed = max(0, row_count - existing_row_count)

            logger.info(f"Existing rows: {existing_row_count}, Additional needed: {additional_rows_needed}")

            all_rows = list(sample_rows)  # Start with preview rows

            if additional_rows_needed > 0:
                # Build expansion request based on future IDs and conversation context
                research_purpose = conversation_state.get('messages', [{}])[0].get('content', '')

                # Create expansion request
                expansion_request = f"""
Generate {additional_rows_needed} additional rows based on the research purpose: {research_purpose}

Use these future ID combinations as a guide:
{json.dumps(future_ids, indent=2)}

Ensure variety and relevance to the research domain.
"""

                # Progress update
                if websocket_client and session_id:
                    try:
                websocket_client.send_to_session(session_id, {
                        'type': 'table_finalization_progress',
                        'progress': 30,
                        'status': f'Expanding table to {row_count} rows...'
                    })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

                # Expand rows iteratively
                table_structure = {
                    'columns': columns,
                    'proposed_columns': columns
                }

                expansion_result = await row_expander.expand_rows_iteratively(
                    table_structure=table_structure,
                    existing_rows=sample_rows,
                    expansion_request=expansion_request,
                    total_rows_needed=additional_rows_needed,
                    batch_size=10,
                    model="claude-sonnet-4-5"
                )

                if not expansion_result['success']:
                    logger.error(f"Row expansion failed: {expansion_result.get('errors', [])}")
                    return {
                        'success': False,
                        'error': f"Failed to generate full table: {expansion_result.get('errors', ['Unknown error'])}"
                    }

                all_rows.extend(expansion_result['expanded_rows'])
                logger.info(f"Generated {len(expansion_result['expanded_rows'])} additional rows")

            # Progress update
            if websocket_client and session_id:
                try:
                websocket_client.send_to_session(session_id, {
                    'type': 'table_finalization_progress',
                    'progress': 50,
                    'status': 'Creating CSV files...'
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
                return {
                    'success': False,
                    'error': f"Failed to generate user CSV: {generation_result.get('error')}"
                }

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
                return {
                    'success': False,
                    'error': f"Failed to generate validation CSV: {validation_result.get('error')}"
                }

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
            return {
                'success': False,
                'error': f'Failed to generate full table: {str(e)}'
            }

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

        # Progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                'type': 'table_finalization_progress',
                'progress': 60,
                'status': 'Generating validation configuration...'
            })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

        # Build enhanced table_analysis with conversation_context
        try:
            # Extract identification columns
            identification_columns = [
                col['name'] for col in columns if col.get('is_identification', False)
            ]

            # Build table_analysis structure for config generation
            table_analysis = {
                'basic_info': {
                    'filename': user_csv_filename,
                    'total_rows': len(all_rows),
                    'total_columns': len(columns),
                    'has_header': True
                },
                'column_analysis': {
                    col['name']: {
                        'name': col['name'],
                        'description': col.get('description', ''),
                        'data_type': col.get('format', 'String'),
                        'importance': col.get('importance', 'MEDIUM'),
                        'sample_values': [row.get(col['name'], '') for row in all_rows[:3]],
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

        except Exception as e:
            logger.error(f"Failed to build table_analysis: {e}")
            return {
                'success': False,
                'error': f'Failed to build table_analysis: {str(e)}'
            }

        # Progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                'type': 'table_finalization_progress',
                'progress': 70,
                'status': 'Calling config generation lambda...'
            })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

        # Call existing handle_generate_config_unified() with enhanced payload
        try:
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
                return {
                    'success': False,
                    'error': f'Failed to generate validation config: {error_msg}'
                }

            config_version = config_result.get('config_version', 1)
            config_s3_key = config_result.get('config_s3_key', '')

            logger.info(f"Config generated successfully: version {config_version}, key {config_s3_key}")

        except Exception as e:
            logger.error(f"Failed to generate config: {e}")
            return {
                'success': False,
                'error': f'Failed to generate validation config: {str(e)}'
            }

        # Progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                'type': 'table_finalization_progress',
                'progress': 85,
                'status': 'Launching preview validation...'
            })
            except Exception as e:
                logger.warning(f"[TABLE_FINALIZE] Failed to send WebSocket update: {e}")

        # Launch preview validation using existing flow
        try:
            from interface_lambda.core.validator_invoker import invoke_validator_lambda

            # Invoke preview validation
            preview_validation_result = await invoke_validator_lambda(
                email=email,
                session_id=session_id,
                validation_type='preview'
            )

            if not preview_validation_result.get('success'):
                logger.warning(f"Preview validation failed: {preview_validation_result.get('error')}")
                # Don't fail the entire operation if preview validation fails
                preview_validation_results = {
                    'status': 'failed',
                    'error': preview_validation_result.get('error')
                }
            else:
                preview_validation_results = preview_validation_result
                logger.info("Preview validation completed successfully")

        except Exception as e:
            logger.error(f"Failed to launch preview validation: {e}")
            preview_validation_results = {
                'status': 'failed',
                'error': str(e)
            }

        # Progress update
        if websocket_client and session_id:
            try:
                websocket_client.send_to_session(session_id, {
                'type': 'table_finalization_progress',
                'progress': 100,
                'status': 'Table generation and validation complete!'
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
            'preview_validation_results': preview_validation_results,
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


def handle_table_accept_and_validate_sync(event_data: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Synchronous wrapper for table finalization (for direct HTTP calls)
    """
    from interface_lambda.utils.helpers import create_response

    try:
        # Run the async function
        result = asyncio.run(handle_table_accept_and_validate(event_data))

        if result['success']:
            return create_response(200, result)
        else:
            return create_response(500, result)

    except Exception as e:
        logger.error(f"Sync table finalization failed: {str(e)}")
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
