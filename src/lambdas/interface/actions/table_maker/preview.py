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


async def handle_table_preview_generate(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
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
        preview_result = await _generate_preview_table(
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

        # Get future IDs - use additional_rows from preview if available, otherwise generate
        if preview_result.get('additional_rows'):
            logger.info(f"[PREVIEW_GENERATE] Using {len(preview_result['additional_rows'])} additional rows from conversation handler")
            future_ids = preview_result['additional_rows']
        else:
            logger.info(f"[PREVIEW_GENERATE] No additional_rows from handler, generating future IDs")
            future_ids = _generate_future_ids(
                conversation_state=conversation_state,
                columns=preview_result['columns'],
                config=config
            )

        # Combine sample rows with future ID rows for CSV
        # Sample rows have all columns filled, future ID rows have only ID columns filled (rest empty)
        all_rows_for_csv = preview_result['rows'].copy()

        # Add future_ids as rows with only ID columns populated, other columns empty
        for future_id in future_ids:
            partial_row = {}
            # Set all columns to empty string
            for col in preview_result['columns']:
                partial_row[col['name']] = ''
            # Fill in the ID column values from future_ids
            for id_col, id_val in future_id.items():
                partial_row[id_col] = id_val
            all_rows_for_csv.append(partial_row)

        logger.info(f"[PREVIEW_GENERATE] Storing CSV with {len(preview_result['rows'])} complete rows + {len(future_ids)} ID-only rows = {len(all_rows_for_csv)} total rows")

        # Store preview CSV in S3 with column definitions
        preview_csv_result = _store_preview_csv(
            storage_manager=storage_manager,
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            columns=preview_result['columns'],
            rows=all_rows_for_csv,
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

        # Extract tablewide_research from preview result
        tablewide_research = preview_result.get('tablewide_research', '')

        # Update conversation state with preview data
        conversation_state['status'] = 'preview_generated'
        conversation_state['preview_data'] = {
            'columns': preview_result['columns'],
            'rows': preview_result['rows'],
            'future_ids': future_ids,
            'generated_at': datetime.utcnow().isoformat() + 'Z'
        }

        # Store tablewide_research for config generation
        if tablewide_research:
            conversation_state['tablewide_research'] = tablewide_research
            logger.info(f"[PREVIEW_GENERATE] Stored tablewide_research in conversation state")

        # Store the current_proposal so refinement can access it
        conversation_state['current_proposal'] = {
            'columns': preview_result['columns'],
            'rows': {
                'sample_rows': preview_result['rows'],
                'additional_rows': future_ids
            }
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
                    'preview_sample_rows': len(preview_result['rows']),
                    'preview_id_rows': len(future_ids),
                    'preview_total_rows': len(all_rows_for_csv),
                    'preview_columns': len(preview_result['columns'])
                }
            )

        # Get interview context for display
        interview_context = conversation_state.get('interview_context', {})

        # Prepare response with preview data
        response_data = {
            'success': True,
            'conversation_id': conversation_id,
            'preview_data': {
                'columns': preview_result['columns'],
                'sample_rows_transposed': transposed_data,
                'future_ids': future_ids
            },
            # Include the follow-up question/table proposal from interview
            'follow_up_question': interview_context.get('follow_up_question', ''),
            'table_name': interview_context.get('table_name', ''),
            # Include API response for metrics aggregation
            'api_response': preview_result.get('api_response'),
            'model': preview_result.get('model'),
            'processing_time': preview_result.get('processing_time', 0.0)
        }

        if download_url:
            response_data['download_url'] = download_url

        logger.info(f"[PREVIEW_GENERATE] Preview generated successfully: {len(all_rows_for_csv)} total rows ({len(preview_result['rows'])} complete + {len(future_ids)} ID-only), {len(preview_result['columns'])} columns")

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
            'model': 'claude-sonnet-4-6',
            'max_tokens': 12000
        },
        'full_table_generation': {
            'default_row_count': 20
        }
    }


async def _generate_preview_table(conversation_state: Dict[str, Any],
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
        # Import TableGenerator from packaged table_maker_lib
        from .table_maker_lib.table_generator import TableGenerator

        # Check if we're using new interview schema or old conversation schema
        interview_context = conversation_state.get('interview_context', {})
        current_proposal = conversation_state.get('current_proposal', {})

        # If we have interview context but no current_proposal,
        # use the original TableConversationHandler to generate everything
        if interview_context and not current_proposal:
            logger.info(f"[PREVIEW_GENERATE] Using interview conversation to generate full table structure")
            logger.info(f"[PREVIEW_GENERATE]   - table_name: {interview_context.get('table_name', 'N/A')}")
            logger.info(f"[PREVIEW_GENERATE]   - context_web_research: {interview_context.get('context_web_research', [])}")

            # Use the original conversation handler to generate columns + rows
            full_table = await _generate_table_from_conversation(
                conversation_state=conversation_state,
                config=config
            )

            if not full_table['success']:
                return {
                    'success': False,
                    'error': f"Failed to generate table: {full_table.get('error', 'Unknown error')}"
                }

            # Return complete result including API metadata for metrics tracking
            return {
                'success': True,
                'columns': full_table['columns'],
                'rows': full_table['rows'],
                'additional_rows': full_table.get('additional_rows', []),
                'tablewide_research': full_table.get('tablewide_research', ''),
                'api_response': full_table.get('api_response'),
                'model': full_table.get('model'),
                'processing_time': full_table.get('processing_time', 0.0)
            }

        # If we have a current_proposal from refinement, use it
        if current_proposal:
            logger.info(f"[PREVIEW_GENERATE] Using existing proposal from conversation (refinement flow)")
            columns = current_proposal.get('columns', [])
            # IMPORTANT: current_proposal.rows contains the proposed_rows object from LLM schema
            # which has sample_rows and additional_rows inside it
            rows_data = current_proposal.get('rows', {})
            sample_rows = rows_data.get('sample_rows', [])
        else:
            columns = []
            sample_rows = []

        if not columns:
            return {
                'success': False,
                'error': 'No column definitions found in conversation state'
            }

        # If we already have sample rows from conversation, use them
        # NOTE: This shouldn't happen for interview-based flow, but handle it for refinement
        if sample_rows and len(sample_rows) >= sample_row_count:
            logger.warning(f"[PREVIEW_GENERATE] Using {len(sample_rows)} sample rows from conversation state (no new API call)")
            # No api_response available since we're reusing existing data
            return {
                'success': True,
                'columns': columns,
                'rows': sample_rows[:sample_row_count],
                'api_response': None,  # Explicitly None - no new API call made
                'model': None,
                'processing_time': 0.0
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


async def _generate_table_from_conversation(
    conversation_state: Dict[str, Any],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate full table structure using the original TableConversationHandler.

    Takes the interview conversation and feeds it into the existing handler
    that already knows how to generate columns, rows, and everything else.

    Args:
        conversation_state: Full conversation state including interview messages
        config: Table maker configuration

    Returns:
        {
            'success': bool,
            'columns': List[Dict],
            'rows': List[Dict],
            'error': Optional[str]
        }
    """
    try:
        # Import the original conversation handler (same imports as conversation.py)
        from .table_maker_lib.conversation_handler import TableConversationHandler
        from .table_maker_lib.prompt_loader import PromptLoader
        from .table_maker_lib.schema_validator import SchemaValidator
        from shared.ai_api_client import ai_client

        # Initialize handler
        prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
        schemas_dir = os.path.join(os.path.dirname(__file__), 'schemas')

        # Use module-level singleton
        prompt_loader = PromptLoader(prompts_dir)
        schema_validator = SchemaValidator(schemas_dir)

        conversation_handler = TableConversationHandler(
            ai_client=ai_client,
            prompt_loader=prompt_loader,
            schema_validator=schema_validator
        )

        # Build a comprehensive message from the interview conversation
        messages = conversation_state.get('messages', [])
        interview_context = conversation_state.get('interview_context', {})

        # Build context from full conversation (both user and assistant)
        conversation_context = "\n\n".join([
            f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')}"
            for msg in messages
        ])

        # The follow_up_question contains the table proposal in markdown
        table_proposal = interview_context.get('follow_up_question', '')
        context_research_queries = interview_context.get('context_web_research', [])

        # Synthesize a comprehensive message that includes:
        # 1. The full conversation context
        # 2. The final table proposal
        # 3. Context research queries (the handler will research these)
        if context_research_queries:
            research_section = f"""
CONTEXT TO RESEARCH (use web search to find current information about these specific items):
{chr(10).join([f"- {q}" for q in context_research_queries])}

Research these items and embed the findings into your table configuration and column descriptions."""
        else:
            research_section = ""

        synthesized_message = f"""Based on our interview conversation, I need to build this research table:

INTERVIEW CONVERSATION:
{conversation_context}

TABLE PROPOSAL:
{table_proposal}
{research_section}

Please generate the complete table structure with columns and sample rows."""

        logger.info(f"[PREVIEW_GENERATE] Generating table with original handler from interview context")

        # Use the conversation config settings for this generation
        conversation_config = config.get('conversation', {})
        model = conversation_config.get('model', 'claude-sonnet-4-6')

        logger.info(f"[PREVIEW_GENERATE] Generating table with original handler (web search enabled by default)")

        # Call the original handler to generate everything at once
        # The handler's call_structured_api has max_web_searches=3 by default
        # It will research the context items and generate the table in ONE call
        result = await conversation_handler.start_conversation(
            user_message=synthesized_message,
            model=model,
            conversation_id=conversation_state.get('conversation_id', 'preview_gen')
        )

        if not result.get('success'):
            return {
                'success': False,
                'error': result.get('error', 'Table generation failed')
            }

        # Extract the proposed table structure
        proposed_table = result.get('proposed_table', {})
        columns = proposed_table.get('columns', [])
        rows_data = proposed_table.get('rows', {})
        sample_rows = rows_data.get('sample_rows', [])
        additional_rows = rows_data.get('additional_rows', [])

        # Extract tablewide_research from the LLM's response
        tablewide_research = proposed_table.get('tablewide_research', '')

        if not columns or not sample_rows:
            return {
                'success': False,
                'error': 'Handler did not return valid table structure'
            }

        logger.info(f"[PREVIEW_GENERATE] Generated {len(columns)} columns, {len(sample_rows)} sample rows, {len(additional_rows)} additional rows")
        if tablewide_research:
            logger.info(f"[PREVIEW_GENERATE] Tablewide research extracted: {tablewide_research[:100]}...")

        # Return table structure AND API metadata for metrics aggregation
        return {
            'success': True,
            'columns': columns,
            'rows': sample_rows,
            'additional_rows': additional_rows,
            'tablewide_research': tablewide_research,  # Pass through for storage
            'api_response': result.get('api_response', {}),  # Full API response
            'model': model,
            'processing_time': result.get('api_metadata', {}).get('processing_time', 0.0)
        }

    except Exception as e:
        logger.error(f"[PREVIEW_GENERATE] Error generating table from conversation: {e}")
        import traceback
        logger.error(f"[PREVIEW_GENERATE] Traceback: {traceback.format_exc()}")
        return {
            'success': False,
            'error': str(e)
        }


def _generate_rows_with_ai(columns: List[Dict[str, Any]], row_count: int,
                          conversation_state: Dict[str, Any],
                          config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate rows using AI (row_expander)."""
    try:
        # Import row_expander from packaged table_maker_lib
        from .table_maker_lib.row_expander import RowExpander
        from .table_maker_lib.prompt_loader import PromptLoader

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
        id_columns = [col for col in columns if col.get('importance', '').upper() == 'ID']

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
        model = config.get('models', {}).get('preview', 'claude-sonnet-4-6')
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
        # Import TableGenerator from packaged table_maker_lib
        from .table_maker_lib.table_generator import TableGenerator

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
