"""
Handles the generateConfig action for AI-powered configuration generation.
"""
import logging
import json
import os
import base64
import uuid
from datetime import datetime
import boto3
import time
import io
import asyncio

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_CACHE_BUCKET = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')

async def handle_generate_config(event_data, websocket_callback=None):
    """
    Generate configuration from uploaded table data using AI (unified approach)
    
    Args:
        event_data: {
            'excel_s3_key': 'path/to/uploaded.xlsx' | 'csv_s3_key' | 'table_data',
            'existing_config': {...} (optional - for iterative improvements),
            'instructions': 'string describing what to generate/modify',
            'email': 'user@example.com'
        }
        websocket_callback: Function to send progress updates via WebSocket
    
    Returns:
        {
            'success': True,
            'updated_config': {...},
            'clarifying_questions': 'string with 2-4 questions',
            'clarification_urgency': 0.0-1.0 (0=no clarification needed, 1=critical),
            'reasoning': 'explanation of changes',
            'config_s3_key': 'path/to/saved_config.json',
            'metadata': {...}
        }
    """
    from ..utils.helpers import create_response, create_email_folder_path
    from ..core.s3_manager import download_file_from_s3, upload_file_to_s3, s3_client, S3_RESULTS_BUCKET
    
    try:
        # Extract parameters  
        excel_s3_key = event_data.get('excel_s3_key')
        existing_config = event_data.get('existing_config')  # Optional
        instructions = event_data.get('instructions', 'Generate an optimal configuration for this data validation scenario')
        email = event_data.get('email', 'test@example.com')
        
        if not excel_s3_key:
            return {'success': False, 'error': 'Missing excel_s3_key'}
        
        # Send initial progress update
        if websocket_callback:
            await websocket_callback({
                'type': 'config_generation_progress',
                'progress': 10,
                'status': '📊 Analyzing Excel file structure...'
            })
        
        # Download Excel file from S3
        logger.info(f"Downloading Excel file from S3: {excel_s3_key}")
        excel_content = download_file_from_s3(S3_CACHE_BUCKET, excel_s3_key)
        if not excel_content:
            return {'success': False, 'error': 'Failed to download Excel file from S3'}
        
        # Progress update
        if websocket_callback:
            await websocket_callback({
                'type': 'config_generation_progress',
                'progress': 25,
                'status': '🧠 Detecting data domain and patterns...'
            })
        
        # Use consolidated table parser
        try:
            from shared_table_parser import s3_table_parser
            
        except ImportError as e:
            logger.error(f"Failed to import shared table parser: {e}")
            return {'success': False, 'error': 'Shared table parser not available'}
        
        # Analyze table structure using S3 parser
        logger.info("Analyzing table structure...")
        try:
            table_analysis = s3_table_parser.analyze_table_structure(S3_CACHE_BUCKET, excel_s3_key)
            
        except Exception as e:
            logger.error(f"Failed to analyze table structure: {e}")
            return {'success': False, 'error': f'Table analysis failed: {str(e)}'}
        
        # Progress update
        if websocket_callback:
            await websocket_callback({
                'type': 'config_generation_progress',
                'progress': 50,
                'status': '⚙️ Generating optimal configuration...'
            })
        
        # Progress update
        if websocket_callback:
            await websocket_callback({
                'type': 'config_generation_progress',
                'progress': 60,
                'status': '⚙️ Generating optimal configuration...'
            })
        
        # Send config generation request to SQS for async processing
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        session_id = f"config_gen_{timestamp}_{uuid.uuid4().hex[:8]}"
        
        logger.info("Sending config generation request to SQS for async processing...")
        try:
            from ..core.sqs_service import send_config_generation_request
            
            # Create email folder for organization
            def create_email_folder_path(email):
                """Create a safe folder path from email address."""
                return email.replace('@', '_at_').replace('.', '_').replace('+', '_plus_')
            
            email_folder = create_email_folder_path(email)
            
            # Prepare config generation request for SQS (unified approach)
            generation_request = {
                'session_id': session_id,
                'table_analysis': table_analysis,
                'existing_config': existing_config,
                'instructions': instructions,
                'email': email,
                'excel_s3_key': excel_s3_key,
                'email_folder': email_folder,
                'timestamp': timestamp
            }
            
            # Send to SQS for async processing
            message_id = send_config_generation_request(generation_request)
            
            if not message_id:
                return {'success': False, 'error': 'Failed to queue config generation request'}
            
            logger.info(f"Config generation request queued successfully: {message_id}")
            
            # Progress update
            if websocket_callback:
                await websocket_callback({
                    'type': 'config_generation_progress',
                    'progress': 25,
                    'status': '📋 Request queued for processing...'
                })
            
            # Return immediately with session info - results will come via WebSocket
            response = {
                'success': True,
                'status': 'queued',
                'session_id': session_id,
                'message_id': message_id,
                'ai_response': 'Configuration generation has been queued. You will receive both an updated configuration and clarifying questions via WebSocket.',
                'metadata': {
                    'table_analysis': table_analysis,
                    'instructions': instructions,
                    'has_existing_config': existing_config is not None,
                    'timestamp': timestamp,
                    'email': email
                }
            }
            
            logger.info(f"Config generation queued successfully: {session_id}")
            return response
                
        except Exception as e:
            logger.error(f"Config generation queueing failed: {e}")
            return {'success': False, 'error': f'Config generation queueing failed: {str(e)}'}
        
    except Exception as e:
        logger.error(f"Config generation failed: {e}")
        if websocket_callback:
            await websocket_callback({
                'type': 'config_generation_progress',
                'progress': 100,
                'status': f'❌ Generation failed: {str(e)}'
            })
        return {'success': False, 'error': str(e)}


def handle_multipart_form(event, context):
    """Handles multipart/form-data requests for config generation."""
    from ..utils.parsing import parse_multipart_form_data
    from ..utils.helpers import create_response
    
    headers = event.get('headers', {})
    content_type = headers.get('Content-Type') or headers.get('content-type', '')
    body = event.get('body', '')
    is_base64_encoded = event.get('isBase64Encoded', False)
    
    files, form_data = parse_multipart_form_data(body, content_type, is_base64_encoded)
    
    email_address = form_data.get('email', 'test@example.com')
    excel_file = files.get('excel_file')
    existing_config_str = form_data.get('existing_config')  # JSON string if provided
    instructions = form_data.get('instructions', 'Generate an optimal configuration for this data validation scenario')
    
    # Parse existing config if provided
    existing_config = None
    if existing_config_str:
        try:
            existing_config = json.loads(existing_config_str)
        except json.JSONDecodeError:
            logger.warning("Invalid existing_config JSON provided, ignoring")
    
    if not excel_file:
        return create_response(400, {'error': 'Missing excel_file'})

    return _process_config_generation(
        excel_file, email_address, existing_config, instructions, context
    )


def handle_json_request(event, context):
    """Handles application/json requests for config generation."""
    from ..utils.helpers import create_response
    
    body = event.get('body', '{}')
    if event.get('isBase64Encoded'):
        body = base64.b64decode(body).decode('utf-8')
    request_data = json.loads(body)
    
    email_address = request_data.get('email', 'test@example.com')
    excel_base64 = request_data.get('excel_file', '')
    existing_config = request_data.get('existing_config')  # Already a dict if provided
    instructions = request_data.get('instructions', 'Generate an optimal configuration for this data validation scenario')

    if not excel_base64:
        return create_response(400, {'error': 'Missing excel_file'})

    excel_file = {
        'filename': 'input.xlsx', 
        'content': base64.b64decode(excel_base64)
    }

    return _process_config_generation(
        excel_file, email_address, existing_config, instructions, context
    )


def _process_config_generation(excel_file, email_address, existing_config, 
                              instructions, context):
    """Shared logic to process config generation request synchronously."""
    from ..utils.helpers import create_response, create_email_folder_path
    from ..core.s3_manager import upload_file_to_s3
    
    try:
        from dynamodb_schemas import is_email_validated
    except ImportError:
        def is_email_validated(email): return True

    if not is_email_validated(email_address):
        return create_response(403, {'error': 'email_not_validated'})
    
    # Upload Excel file to S3
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    session_id = f"config_gen_{timestamp}_{uuid.uuid4().hex[:8]}"
    email_folder = create_email_folder_path(email_address)
    excel_s3_key = f"uploads/{email_folder}/{session_id}_excel_{excel_file['filename']}"
    
    if not upload_file_to_s3(excel_file['content'], S3_CACHE_BUCKET, excel_s3_key):
        return create_response(500, {'error': 'Failed to upload Excel file to S3'})
    
    # Process config generation synchronously
    try:
        event_data = {
            'excel_s3_key': excel_s3_key,
            'existing_config': existing_config,
            'instructions': instructions,
            'email': email_address
        }
        
        # Process synchronously (remove async for simplicity)
        import asyncio
        result = asyncio.run(handle_generate_config(event_data))
        
        if result.get('success'):
            response_body = {
                "status": "generation_completed", 
                "session_id": session_id,
                "updated_config": result.get('updated_config'),
                "clarifying_questions": result.get('clarifying_questions'),
                "clarification_urgency": result.get('clarification_urgency'),
                "reasoning": result.get('reasoning'),
                "config_s3_key": result.get('config_s3_key'),
                **result
            }
            return create_response(200, response_body)
        else:
            return create_response(500, {'error': result.get('error', 'Config generation failed')})
            
    except Exception as e:
        logger.error(f"Config generation failed: {e}")
        return create_response(500, {'error': f'Config generation failed: {str(e)}'})

def handle_interview_responses(request_data, context):
    """Handle interview response submission."""
    from ..utils.helpers import create_response
    
    try:
        logger.info("Handling interview responses submission")
        
        # Extract required fields
        interview_id = request_data.get('interview_id')
        responses = request_data.get('responses', {})
        
        if not interview_id:
            return create_response(400, {'error': 'Missing interview_id'})
        
        if not responses:
            return create_response(400, {'error': 'Missing responses'})
        
        # Import the conversational system
        try:
            from ..config_generator_conversational import ConversationalConfigSystem
        except ImportError:
            # Fallback to ai_config_generator directory
            import sys
            import os
            sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ai_config_generator'))
            from config_generator_conversational import ConversationalConfigSystem
        
        # Process the interview responses
        logger.info(f"Processing interview {interview_id} with {len(responses)} responses")
        
        # Create conversational system
        system = ConversationalConfigSystem()
        
        # Format responses as a user message
        response_text = "Here are my responses to the interview questions:\n\n"
        for question, answer in responses.items():
            response_text += f"Q: {question}\nA: {answer}\n\n"
        
        # Continue the conversation with the responses
        import asyncio
        result = asyncio.run(system.continue_conversation(interview_id, response_text))
        
        if result:
            return create_response(200, {
                'success': True,
                'interview_id': interview_id,
                'status': 'completed',
                'config_generated': True,
                'ai_response': result.get('conversation_response', ''),
                'message': 'Interview responses processed successfully'
            })
        else:
            return create_response(500, {'error': 'Failed to process interview responses'})
        
    except Exception as e:
        logger.error(f"Interview response handling failed: {e}")
        import traceback
        traceback.print_exc()
        return create_response(500, {'error': f'Interview response handling failed: {str(e)}'})

def handle_config_modification(request_data, context):
    """Handle configuration modification requests."""
    from ..utils.helpers import create_response
    
    try:
        logger.info("Handling config modification request")
        
        # Extract required fields
        email = request_data.get('email')
        existing_config = request_data.get('existing_config')
        modification_notes = request_data.get('modification_notes')
        session_id = request_data.get('session_id')
        
        if not email:
            return create_response(400, {'error': 'Missing email'})
        
        if not existing_config:
            return create_response(400, {'error': 'Missing existing_config'})
        
        if not modification_notes:
            return create_response(400, {'error': 'Missing modification_notes'})
        
        # Import the conversational system
        try:
            from ..config_generator_conversational import ConversationalConfigSystem
        except ImportError:
            # Fallback to ai_config_generator directory
            import sys
            import os
            sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ai_config_generator'))
            from config_generator_conversational import ConversationalConfigSystem
        try:
            from ..config_generator_step1 import TableAnalyzer
        except ImportError:
            from config_generator_step1 import TableAnalyzer
        
        logger.info(f"Processing config modification for session {session_id}")
        logger.info(f"Modification notes: {modification_notes}")
        
        # Create conversational system
        system = ConversationalConfigSystem()
        
        # Create a temporary config file for the conversation
        import tempfile
        import json
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_config:
            json.dump(existing_config, tmp_config, indent=2)
            tmp_config_path = tmp_config.name
        
        try:
            # Create a basic table analysis for the conversation
            # In a real implementation, this would come from the original table analysis
            table_analysis = {
                'basic_info': {
                    'filename': 'existing_config.json',
                    'shape': [0, 0],
                    'column_names': []
                },
                'column_analysis': {},
                'domain_info': {'inferred_domain': 'general'}
            }
            
            # Start a conversation with the modification request
            import asyncio
            conversation_id = asyncio.run(system.start_conversation(
                tmp_config_path, 
                table_analysis,
                modification_notes
            ))
            
            if conversation_id:
                # Save the updated config
                updated_config_path = f"modified_config_{session_id}.json"
                system.save_updated_config(conversation_id, updated_config_path)
                
                # Read the updated config
                if os.path.exists(updated_config_path):
                    with open(updated_config_path, 'r') as f:
                        updated_config = json.load(f)
                    
                    # Clean up temporary files
                    os.unlink(tmp_config_path)
                    os.unlink(updated_config_path)
                    
                    result = {
                        'success': True,
                        'session_id': session_id,
                        'conversation_id': conversation_id,
                        'status': 'modification_completed',
                        'message': 'Configuration modification processed successfully',
                        'modifications_applied': True,
                        'updated_config': updated_config
                    }
                    
                    return create_response(200, result)
                else:
                    return create_response(500, {'error': 'Failed to save updated config'})
            else:
                return create_response(500, {'error': 'Failed to start modification conversation'})
                
        finally:
            # Clean up temporary config file
            if os.path.exists(tmp_config_path):
                os.unlink(tmp_config_path)
        
    except Exception as e:
        logger.error(f"Config modification failed: {e}")
        import traceback
        traceback.print_exc()
        return create_response(500, {'error': f'Config modification failed: {str(e)}'})