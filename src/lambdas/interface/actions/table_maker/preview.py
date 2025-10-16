"""
Table Maker Preview Generation Handler.

Generates 3-row preview from conversation state using existing TableGenerator.
Creates transposed data structure for frontend display and future ID list.
"""

import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import boto3

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import shared utilities
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
try:
    from dynamodb_schemas import update_run_status
except ImportError as e:
    logger.error(f"Failed to import dynamodb_schemas: {e}")
    def update_run_status(**kwargs):
        logger.warning("update_run_status not available")

# Import core infrastructure
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.core.s3_manager import generate_presigned_url
from interface_lambda.utils.helpers import create_response


def handle_table_preview_generate(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Generate 3-row preview from conversation state.

    Input event body:
    {
        'action': 'generateTablePreview',
        'email': 'user@example.com',
        'session_id': 'session_20251013_123456',
        'conversation_id': 'table_conv_abc123'
    }

    Returns:
    {
        'success': True,
        'preview_data': {
            'columns': [...],
            'sample_rows_transposed': [...],
            'future_ids': [...]
        },
        'download_url': 'https://...'
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

        logger.info(f"[PREVIEW_GENERATE] Starting preview generation for conversation {conversation_id}")

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
        sample_row_count = config.get('preview_generation', {}).get('sample_row_count', 3)

        logger.info(f"[PREVIEW_GENERATE] Generating {sample_row_count} sample rows")

        # Generate preview using TableGenerator
        preview_result = _generate_preview_table(
            conversation_state=conversation_state,
            sample_row_count=sample_row_count,
            config=config
        )

        if not preview_result['success']:
            return create_response(500, {
                'error': f"Preview generation failed: {preview_result.get('error', 'Unknown error')}"
            })

        # Create transposed data structure for frontend
        transposed_data = _create_transposed_preview(
            columns=preview_result['columns'],
            rows=preview_result['rows']
        )

        # Generate future IDs list (20 rows worth)
        future_ids = _generate_future_ids(
            conversation_state=conversation_state,
            columns=preview_result['columns'],
            config=config
        )

        # Store preview CSV in S3 with column definitions
        preview_csv_result = _store_preview_csv(
            storage_manager=storage_manager,
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            columns=preview_result['columns'],
            rows=preview_result['rows'],
            include_metadata=True
        )

        if not preview_csv_result['success']:
            logger.warning(f"[PREVIEW_GENERATE] Failed to store CSV: {preview_csv_result['error']}")

        # Generate presigned download URL
        download_url = None
        if preview_csv_result.get('s3_key'):
            download_url = generate_presigned_url(
                storage_manager.bucket_name,
                preview_csv_result['s3_key'],
                expiration=3600
            )

        # Update conversation state with preview data
        conversation_state['status'] = 'preview_generated'
        conversation_state['preview_data'] = {
            'columns': preview_result['columns'],
            'rows': preview_result['rows'],
            'future_ids': future_ids,
            'generated_at': datetime.utcnow().isoformat() + 'Z'
        }
        _save_conversation_state(storage_manager, email, session_id, conversation_id, conversation_state)

        # Update runs database with preview status
        run_key = conversation_state.get('run_key')
        if run_key:
            update_run_status(
                session_id=session_id,
                run_key=run_key,
                status='COMPLETED',
                end_time=datetime.utcnow().isoformat() + 'Z',
                metadata={
                    'preview_rows': len(preview_result['rows']),
                    'preview_columns': len(preview_result['columns']),
                    'future_id_count': len(future_ids)
                }
            )

        # Prepare response with preview data
        response_data = {
            'success': True,
            'conversation_id': conversation_id,
            'preview_data': {
                'columns': preview_result['columns'],
                'sample_rows_transposed': transposed_data,
                'future_ids': future_ids
            }
        }

        if download_url:
            response_data['download_url'] = download_url

        logger.info(f"[PREVIEW_GENERATE] Preview generated successfully: {len(preview_result['rows'])} rows, {len(preview_result['columns'])} columns")

        return create_response(200, response_data)

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE] Error generating preview: {str(e)}")
        import traceback
        logger.error(f"[PREVIEW_GENERATE] Traceback: {traceback.format_exc()}")
        return create_response(500, {
            'error': f'Preview generation failed: {str(e)}'
        })


def handle_table_preview_generate_async(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Async wrapper for table preview generation - sends request to SQS and returns immediately.
    This prevents frontend timeouts for AI-powered table generation operations.
    """
    try:
        # Import SQS service
        from interface_lambda.core.sqs_service import send_table_finalization_request

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

        logger.info(f"[PREVIEW_GENERATE_ASYNC] Sending preview generation request to SQS for conversation {conversation_id}")

        # Send to SQS for background processing
        message_data = {
            'email': email,
            'session_id': session_id,
            'conversation_id': conversation_id,
            'action': 'generateTablePreview'
        }

        message_id = send_table_finalization_request(message_data)

        if not message_id:
            logger.error("[PREVIEW_GENERATE_ASYNC] Failed to send SQS message")
            return create_response(500, {
                'success': False,
                'error': 'Failed to queue preview generation request'
            })

        logger.info(f"[PREVIEW_GENERATE_ASYNC] Successfully queued preview generation: MessageId={message_id}")

        # Return immediately with processing status
        return create_response(200, {
            'success': True,
            'status': 'processing',
            'message': 'Preview generation started. You will receive updates via WebSocket.',
            'session_id': session_id,
            'conversation_id': conversation_id,
            'message_id': message_id
        })

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE_ASYNC] Async wrapper failed: {str(e)}")
        import traceback
        logger.error(f"[PREVIEW_GENERATE_ASYNC] Traceback: {traceback.format_exc()}")
        return create_response(500, {'success': False, 'error': str(e)})


def _load_conversation_state(storage_manager: UnifiedS3Manager, email: str,
                            session_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
    """Load conversation state from S3."""
    try:
        session_path = storage_manager.get_session_path(email, session_id)
        state_key = f"{session_path}table_maker/conversation_{conversation_id}.json"

        response = storage_manager.s3_client.get_object(
            Bucket=storage_manager.bucket_name,
            Key=state_key
        )

        state_data = json.loads(response['Body'].read().decode('utf-8'))
        logger.info(f"[PREVIEW_GENERATE] Loaded conversation state from {state_key}")
        return state_data

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE] Failed to load conversation state: {e}")
        return None


def _save_conversation_state(storage_manager: UnifiedS3Manager, email: str,
                            session_id: str, conversation_id: str,
                            state_data: Dict[str, Any]) -> bool:
    """Save conversation state to S3."""
    try:
        session_path = storage_manager.get_session_path(email, session_id)
        state_key = f"{session_path}table_maker/conversation_{conversation_id}.json"

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=state_key,
            Body=json.dumps(state_data, indent=2),
            ContentType='application/json'
        )

        logger.info(f"[PREVIEW_GENERATE] Saved conversation state to {state_key}")
        return True

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE] Failed to save conversation state: {e}")
        return False


def _load_table_maker_config() -> Dict[str, Any]:
    """Load table maker configuration."""
    try:
        # Try to load from packaged location
        config_path = Path(__file__).parent.parent.parent.parent.parent / 'table_maker' / 'table_maker_config.json'

        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                logger.info(f"[PREVIEW_GENERATE] Loaded config from {config_path}")
                return config
        else:
            logger.warning(f"[PREVIEW_GENERATE] Config not found at {config_path}, using defaults")
            return _get_default_config()

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE] Failed to load config: {e}")
        return _get_default_config()


def _get_default_config() -> Dict[str, Any]:
    """Get default configuration if config file not available."""
    return {
        'preview_generation': {
            'sample_row_count': 3,
            'model': 'claude-sonnet-4-5',
            'max_tokens': 12000
        },
        'full_table_generation': {
            'default_row_count': 20
        }
    }


def _generate_preview_table(conversation_state: Dict[str, Any],
                           sample_row_count: int,
                           config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate preview table using existing TableGenerator.

    Returns:
    {
        'success': bool,
        'columns': List[Dict],
        'rows': List[Dict],
        'error': Optional[str]
    }
    """
    try:
        # Import TableGenerator from table_maker standalone code
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'table_maker', 'src'))
        from table_generator import TableGenerator

        # Extract table structure from conversation state
        current_proposal = conversation_state.get('current_proposal', {})
        columns = current_proposal.get('columns', [])
        # IMPORTANT: current_proposal.rows contains the proposed_rows object from LLM schema
        # which has sample_rows and additional_rows inside it
        rows_data = current_proposal.get('rows', {})
        sample_rows = rows_data.get('sample_rows', [])

        if not columns:
            return {
                'success': False,
                'error': 'No column definitions found in conversation state'
            }

        # If we already have sample rows from conversation, use them
        if sample_rows and len(sample_rows) >= sample_row_count:
            logger.info(f"[PREVIEW_GENERATE] Using {len(sample_rows)} sample rows from conversation state")
            return {
                'success': True,
                'columns': columns,
                'rows': sample_rows[:sample_row_count]
            }

        # Otherwise, generate rows using AI (row_expander)
        logger.info(f"[PREVIEW_GENERATE] Generating {sample_row_count} rows using row_expander")
        rows = _generate_rows_with_ai(
            columns=columns,
            row_count=sample_row_count,
            conversation_state=conversation_state,
            config=config
        )

        return {
            'success': True,
            'columns': columns,
            'rows': rows
        }

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE] Error generating preview table: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def _generate_rows_with_ai(columns: List[Dict[str, Any]], row_count: int,
                          conversation_state: Dict[str, Any],
                          config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate rows using AI (row_expander)."""
    try:
        # Import row_expander
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'table_maker', 'src'))
        from row_expander import RowExpander
        from prompt_loader import PromptLoader

        # Initialize row expander
        prompt_loader = PromptLoader()
        row_expander = RowExpander(prompt_loader=prompt_loader)

        # Extract context from conversation
        research_purpose = conversation_state.get('messages', [{}])[0].get('content', '')
        context_research = conversation_state.get('context_research', {})

        # Generate rows
        result = row_expander.expand_rows(
            columns=columns,
            existing_rows=[],
            target_count=row_count,
            context={
                'research_purpose': research_purpose,
                'domain_insights': context_research.get('insights', '')
            }
        )

        if result['success']:
            return result['rows']
        else:
            logger.error(f"[PREVIEW_GENERATE] Row expansion failed: {result.get('error')}")
            return []

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE] Error generating rows with AI: {e}")
        return []


def _create_transposed_preview(columns: List[Dict[str, Any]],
                               rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Create transposed data structure for frontend display.

    Returns list where each item is a row with columns as keys.
    """
    transposed = []

    for row in rows:
        transposed_row = {}
        for col in columns:
            col_name = col['name']
            transposed_row[col_name] = row.get(col_name, '')
        transposed.append(transposed_row)

    return transposed


def _generate_future_ids(conversation_state: Dict[str, Any],
                        columns: List[Dict[str, Any]],
                        config: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Get future ID combinations from LLM response additional_rows.

    The LLM already provides these in the additional_rows field of proposed_rows.

    Returns list of dictionaries with ID column values.
    """
    try:
        # First, check if we already have additional_rows from the LLM response
        current_proposal = conversation_state.get('current_proposal', {})
        rows_data = current_proposal.get('rows', {})
        additional_rows = rows_data.get('additional_rows', [])

        if additional_rows:
            logger.info(f"[PREVIEW_GENERATE] Using {len(additional_rows)} additional rows from LLM response")
            return additional_rows

        # Fallback: Generate ID combinations using AI if not provided by LLM
        logger.info("[PREVIEW_GENERATE] No additional_rows from LLM, generating future IDs with AI")

        # Get identification columns
        id_columns = [col for col in columns if col.get('is_identification', False)]

        if not id_columns:
            logger.warning("[PREVIEW_GENERATE] No identification columns found")
            return []

        # Get target row count from config
        target_count = config.get('full_table_generation', {}).get('default_row_count', 20)

        # Generate ID combinations using AI
        future_ids = _generate_future_ids_with_ai(
            id_columns=id_columns,
            target_count=target_count,
            conversation_state=conversation_state,
            config=config
        )

        return future_ids

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE] Error generating future IDs: {e}")
        return []


def _generate_future_ids_with_ai(id_columns: List[Dict[str, Any]],
                                 target_count: int,
                                 conversation_state: Dict[str, Any],
                                 config: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generate future ID combinations using AI."""
    try:
        # Import AI client
        import anthropic

        # Get API key from environment
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            logger.error("[PREVIEW_GENERATE] ANTHROPIC_API_KEY not found")
            return []

        client = anthropic.Anthropic(api_key=api_key)

        # Build prompt for ID generation
        id_col_names = [col['name'] for col in id_columns]
        id_descriptions = '\n'.join([
            f"- {col['name']}: {col.get('description', 'No description')}"
            for col in id_columns
        ])

        research_purpose = conversation_state.get('messages', [{}])[0].get('content', '')

        prompt = f"""Generate {target_count} unique identification value combinations for a research table.

Research Purpose: {research_purpose}

Identification Columns:
{id_descriptions}

Generate {target_count} realistic and diverse ID combinations. Return ONLY a JSON array of objects, each containing these columns: {', '.join(id_col_names)}

Example format:
[
  {{{', '.join([f'"{col}": "value"' for col in id_col_names])}}},
  ...
]

Return only the JSON array, no other text."""

        # Call Claude
        model = config.get('models', {}).get('preview', 'claude-sonnet-4-5')
        max_tokens = config.get('preview_generation', {}).get('max_tokens', 12000)

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{'role': 'user', 'content': prompt}]
        )

        # Parse response
        response_text = response.content[0].text.strip()

        # Extract JSON from response
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        future_ids = json.loads(response_text)

        logger.info(f"[PREVIEW_GENERATE] Generated {len(future_ids)} future ID combinations")
        return future_ids[:target_count]

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE] Error generating future IDs with AI: {e}")
        return []


def _store_preview_csv(storage_manager: UnifiedS3Manager, email: str,
                      session_id: str, conversation_id: str,
                      columns: List[Dict[str, Any]], rows: List[Dict[str, Any]],
                      include_metadata: bool = True) -> Dict[str, Any]:
    """
    Store preview CSV in S3 with column definitions.

    Returns:
    {
        'success': bool,
        's3_key': str,
        'error': Optional[str]
    }
    """
    try:
        # Import TableGenerator
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'table_maker', 'src'))
        from table_generator import TableGenerator

        # Create temporary file for CSV
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
            tmp_path = tmp_file.name

        # Generate CSV using TableGenerator
        generator = TableGenerator()
        result = generator.generate_csv(
            columns=columns,
            rows=rows,
            output_path=tmp_path,
            include_metadata=include_metadata
        )

        if not result['success']:
            return {
                'success': False,
                'error': result.get('error', 'CSV generation failed')
            }

        # Upload to S3
        session_path = storage_manager.get_session_path(email, session_id)
        s3_key = f"{session_path}table_maker/preview_{conversation_id}.csv"

        with open(tmp_path, 'rb') as f:
            csv_content = f.read()

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key,
            Body=csv_content,
            ContentType='text/csv'
        )

        logger.info(f"[PREVIEW_GENERATE] Stored preview CSV: {s3_key}")

        # Clean up temp file
        os.unlink(tmp_path)

        return {
            'success': True,
            's3_key': s3_key
        }

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE] Error storing preview CSV: {e}")
        return {
            'success': False,
            'error': str(e)
        }
