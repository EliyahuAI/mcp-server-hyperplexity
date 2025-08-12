"""
Updated generateConfig action using unified storage system.
Generates AI configs that are stored in the unified session storage.
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
from botocore.exceptions import ClientError
from pathlib import Path

from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response
from shared_table_parser import s3_table_parser
from interface_lambda.core.sqs_service import send_config_generation_request
from dynamodb_schemas import update_run_status, get_connection_by_session, remove_websocket_connection
from interface_lambda.core.validator_invoker import invoke_validator_lambda
from interface_lambda.reporting.zip_report import create_enhanced_result_zip
from interface_lambda.reporting.markdown_report import create_markdown_table_from_results
from interface_lambda.reporting.excel_report_new import create_enhanced_excel_with_validation, EXCEL_ENHANCEMENT_AVAILABLE
from email_sender import send_validation_results_email
from dynamodb_schemas import update_processing_metrics, track_email_delivery, track_user_request, update_run_status

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_next_config_version(email: str, session_id: str) -> int:
    """Get the next version number for config files"""
    import re
    
    try:
        storage_manager = UnifiedS3Manager()
        session_path = storage_manager.get_session_path(email, session_id)
        
        # List all objects in session path
        response = storage_manager.s3_client.list_objects_v2(
            Bucket=storage_manager.bucket_name,
            Prefix=session_path
        )
        
        if 'Contents' not in response:
            return 1
        
        # Extract version numbers and get max
        versions = []
        for obj in response['Contents']:
            filename = obj['Key'].split('/')[-1]
            if filename.startswith('config_v') and filename.endswith('.json'):
                match = re.search(r'config_v(\d+)_', filename)
                if match:
                    versions.append(int(match.group(1)))
        
        return max(versions, default=0) + 1
    except Exception as e:
        logger.warning(f"Could not determine next version: {e}")
        return 1

def store_config_with_versioning(email: str, session_id: str, config_data: dict, 
                                source: str = 'refined') -> dict:
    """Store config with automatic version increment"""
    from ..core.unified_s3_manager import UnifiedS3Manager
    
    storage_manager = UnifiedS3Manager()
    next_version = get_next_config_version(email, session_id)
    
    # Store with incremented version
    result = storage_manager.store_config_file(
        email=email,
        session_id=session_id, 
        config_data=config_data,
        version=next_version,
        source=source
    )
    
    # Add version to result for caller
    result['version'] = next_version
    
    return result

def find_latest_config_in_session(s3_client, bucket_name, session_path):
    """Find the highest version config file in a session folder"""
    try:
        # List all objects in session path
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=session_path
        )

        if 'Contents' not in response:
            logger.info(f"No contents found in session path: {session_path}")
            return None

        # Find config files and extract versions
        config_files = []
        for obj in response['Contents']:
            filename = obj['Key'].split('/')[-1]
            if filename.startswith('config_v') and filename.endswith('.json'):
                try:
                    # Extract version: config_v1.json -> 1, config_v01_source.json -> 1
                    version_part = filename[8:].split('.')[0].split('_')[0]
                    version = int(version_part.lstrip('0') or '1')
                    config_files.append({
                        'key': obj['Key'],
                        'version': version,
                        'last_modified': obj['LastModified']
                    })
                    logger.debug(f"Found config file: {filename} -> version {version}")
                except (ValueError, IndexError) as e:
                    logger.debug(f"Could not parse version from {filename}: {e}")
                    continue

        if not config_files:
            logger.info(f"No config files found in session path: {session_path}")
            return None

        # Sort by version (highest first), then by modification time
        config_files.sort(key=lambda x: (x['version'], x['last_modified']), reverse=True)
        latest_config_file = config_files[0]

        # Download and parse the latest config
        config_response = s3_client.get_object(
            Bucket=bucket_name,
            Key=latest_config_file['key']
        )
        config_data = json.loads(config_response['Body'].read().decode('utf-8'))

        logger.info(f"Found latest config: {latest_config_file['key']} (version {latest_config_file['version']})")
        return config_data

    except ClientError as e:
        logger.error(f"S3 access error finding latest config: {e}")
        return None
    except Exception as e:
        logger.error(f"Error finding latest config: {e}")
        return None

async def handle_generate_config_unified(event_data, websocket_callback=None):
    """
    Generate configuration from uploaded table data using AI with unified storage
    
    Args:
        event_data: {
            'email': 'user@example.com',
            'session_id': 'session_identifier',
            'existing_config': {...} (optional - for iterative improvements),
            'instructions': 'string describing what to generate/modify'
        }
        websocket_callback: Function to send progress updates via WebSocket
    
    Returns:
        {
            'success': True,
            'updated_config': {...},
            'clarifying_questions': 'string with 2-4 questions',
            'clarification_urgency': 0.0-1.0 (0=no clarification needed, 1=critical),
            'reasoning': 'explanation of changes',
            'ai_summary': 'AI summary of changes made',
            'config_s3_key': 'path/to/saved_config.json',
            'config_version': 2,
            'storage_path': 'email/domain/session_id/'
        }
    """
    from ..utils.helpers import create_response
    from ..core.unified_s3_manager import UnifiedS3Manager
    
    try:
        # Extract parameters  
        email = event_data.get('email')
        session_id = event_data.get('session_id')
        existing_config = event_data.get('existing_config')  # Optional
        instructions = event_data.get('instructions', 'Generate an optimal configuration for this data validation scenario')
        
        if not email or not session_id:
            return {'success': False, 'error': 'Missing email or session_id'}
        
        # Initialize unified storage
        storage_manager = UnifiedS3Manager()
        
        # Send initial progress update
        if websocket_callback:
            await websocket_callback({
                'type': 'config_generation_progress',
                'progress': 10,
                'status': '📊 Analyzing Excel file from unified storage...'
            })
        
        # Get Excel file from unified storage
        logger.info(f"Getting Excel file from unified storage: {email}/{session_id}")
        excel_content, excel_s3_key = storage_manager.get_excel_file(email, session_id)
        if not excel_content:
            return {'success': False, 'error': 'No Excel file found in unified storage for this session'}
        
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
            
            # Analyze table structure directly from S3
            table_analysis = s3_table_parser.analyze_table_structure(storage_manager.bucket_name, excel_s3_key)
            
            if not table_analysis:
                return {'success': False, 'error': 'Failed to analyze table structure'}
            
            logger.info(f"Table analysis completed: {table_analysis.get('basic_info', {}).get('filename', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Table analysis failed: {str(e)}")
            return {'success': False, 'error': f'Table analysis failed: {str(e)}'}
        
        # Progress update
        if websocket_callback:
            await websocket_callback({
                'type': 'config_generation_progress',
                'progress': 50,
                'status': '🤖 Generating AI configuration...'
            })
        
        # Get existing config from unified storage if not provided
        if not existing_config:
            logger.info("No existing config provided, checking unified storage for latest version")
            existing_config = find_latest_config_in_session(storage_manager.s3_client, storage_manager.bucket_name, storage_manager.get_session_path(email, session_id))
            if existing_config:
                logger.info(f"Found existing config version {existing_config.get('storage_metadata', {}).get('version', 'unknown')}")
        
        # Call config lambda with unified architecture
        try:
            lambda_client = boto3.client('lambda')
            config_lambda_name = os.environ.get('CONFIG_LAMBDA_NAME', 'perplexity-validator-config')
            
            # Prepare payload for config lambda
            # Ensure conversation history is preserved by including current conversation log
            conversation_history = []
            if existing_config and existing_config.get('config_change_log'):
                conversation_history = existing_config['config_change_log']
                logger.info(f"Preserving {len(conversation_history)} existing conversation entries")
                
                # Debug: log current version info being passed
                generation_metadata = existing_config.get('generation_metadata', {})
                current_version = generation_metadata.get('version', 'unknown')
                logger.info(f"Passing existing config to lambda - Version: {current_version}")
                
                # Log recent entries for debugging
                if conversation_history:
                    logger.info("Recent conversation entries being passed:")
                    for i, entry in enumerate(conversation_history[-2:], 1):
                        logger.info(f"  Entry {len(conversation_history)-2+i}: v{entry.get('version', 'unknown')} - {entry.get('instructions', 'No instructions')[:30]}...")
            else:
                logger.info("No existing conversation history found to preserve")
            
            payload = {
                'table_analysis': table_analysis,
                'existing_config': existing_config,
                'instructions': instructions,
                'session_id': session_id,
                'email': email,  # Include email for context
                'preserve_conversation_history': True,  # Signal to config lambda to preserve history
                'conversation_history': conversation_history  # Pass existing conversation for preservation
            }
            
            # Progress update
            if websocket_callback:
                await websocket_callback({
                    'type': 'config_generation_progress',
                    'progress': 75,
                    'status': '⚙️ Processing AI configuration generation...'
                })
            
            # Invoke config lambda
            response = lambda_client.invoke(
                FunctionName=config_lambda_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            # Parse response
            result = json.loads(response['Payload'].read())
            
            if response['StatusCode'] != 200:
                return {'success': False, 'error': f'Config lambda failed with status {response["StatusCode"]}'}
            
            body = json.loads(result['body']) if isinstance(result.get('body'), str) else result.get('body', {})
            
            if not body.get('success'):
                error_response = {
                    'success': False, 
                    'error': body.get('error', 'Unknown error'),
                    'error_type': body.get('error_type', 'unknown')
                }
                
                # Add retry suggestions for specific error types
                if body.get('error_type') == 'format_error':
                    error_response['retry_suggestion'] = body.get('retry_suggestion', 
                        'Try simplifying your instructions or breaking them into smaller steps.')
                elif body.get('error_type') == 'api_overloaded':
                    error_response['retry_suggestion'] = 'Please wait a moment and try again.'
                
                # Include error details for debugging if available
                if body.get('error_details'):
                    logger.error(f"Config generation error details: {body.get('error_details')}")
                
                return error_response
            
            # Extract generated config
            updated_config = body.get('updated_config')
            if not updated_config:
                return {'success': False, 'error': 'No config returned from AI generation'}
            
            # Progress update
            if websocket_callback:
                await websocket_callback({
                    'type': 'config_generation_progress',
                    'progress': 90,
                    'status': '💾 Storing generated configuration...'
                })
            
            # Use the version already set by config lambda, or calculate if missing
            config_version = updated_config.get('generation_metadata', {}).get('version')
            if config_version:
                logger.info(f"Using version {config_version} set by config lambda")
                # Store config directly with the version set by config lambda
                from ..core.unified_s3_manager import UnifiedS3Manager
                storage_manager = UnifiedS3Manager()
                storage_result = storage_manager.store_config_file(
                    email=email,
                    session_id=session_id,
                    config_data=updated_config,
                    version=config_version,
                    source='ai_generated'
                )
                storage_result['version'] = config_version
                version = config_version
            else:
                logger.warning("Config lambda didn't set version, falling back to interface lambda versioning")
                # Fallback to interface lambda versioning system
                storage_result = store_config_with_versioning(
                    email, session_id, updated_config, source='ai_generated'
                )
                version = storage_result.get('version', 1)
            
            if not storage_result['success']:
                return {'success': False, 'error': f'Failed to store generated config: {storage_result["error"]}'}
            
            # Update session info with new config version
            try:
                # Get table name from session or use default
                table_name = f"table_{session_id.split('_')[-1]}"
                session_info_result = storage_manager.create_session_info(
                    email, session_id, table_name, current_config_version=version,
                    config_source='ai_generated'
                )
                if session_info_result['success']:
                    logger.info(f"Session info updated with config version {version}")
            except Exception as e:
                logger.warning(f"Failed to update session info: {e}")
            
            # Create download link for the config (separate bucket)
            download_url = storage_manager.create_public_download_link(updated_config, f"config_v{version}_{session_id}.json")
            
            # Progress update
            if websocket_callback:
                await websocket_callback({
                    'type': 'config_generation_progress',
                    'progress': 100,
                    'status': '✅ Configuration generated and stored successfully!'
                })
            
            logger.info(f"Config generation completed successfully for session {session_id}")
            
            # Get config filename from the config lambda response
            config_filename = body.get('config_filename')
            if config_filename:
                # Store the config lambda filename in the updated config's metadata
                if 'generation_metadata' not in updated_config:
                    updated_config['generation_metadata'] = {}
                updated_config['generation_metadata']['config_lambda_filename'] = config_filename
                logger.info(f"Config lambda filename: {config_filename}")
            
            return {
                'success': True,
                'updated_config': updated_config,
                'clarifying_questions': body.get('clarifying_questions', ''),
                'clarification_urgency': body.get('clarification_urgency', 0.0),
                'reasoning': body.get('reasoning', ''),
                'ai_summary': body.get('ai_summary', ''),
                'config_s3_key': storage_result['s3_key'],
                'config_version': version,
                'config_filename': config_filename,  # Include config lambda filename
                'storage_path': storage_result['session_path'],
                'download_url': download_url,
                'session_id': session_id
            }
            
        except Exception as e:
            logger.error(f"Config lambda invocation failed: {str(e)}")
            return {'success': False, 'error': f'Config generation failed: {str(e)}'}
        
    except Exception as e:
        logger.error(f"Config generation error: {str(e)}")
        return {'success': False, 'error': f'Config generation failed: {str(e)}'}

def handle_generate_config_sync(request_data, context):
    """
    Synchronous wrapper for config generation (for direct HTTP calls)
    """
    from ..utils.helpers import create_response
    
    try:
        # Run the async function
        result = asyncio.run(handle_generate_config_unified(request_data))
        
        if result['success']:
            return create_response(200, result)
        else:
            return create_response(500, result)
            
    except Exception as e:
        logger.error(f"Sync config generation failed: {str(e)}")
        return create_response(500, {'success': False, 'error': str(e)})

def handle_generate_config_async(request_data, context):
    """
    Async wrapper for config generation - returns immediately and uses SQS + WebSocket
    """
    from ..utils.helpers import create_response
    from ..core.unified_s3_manager import UnifiedS3Manager
    
    try:
        email = request_data.get('email')
        session_id = request_data.get('session_id')
        instructions = request_data.get('instructions', 'Generate an optimal configuration for this data validation scenario')
        existing_config = request_data.get('existing_config')
        
        if not email or not session_id:
            return create_response(400, {'error': 'Missing email or session_id'})
        
        # Initialize unified storage to verify Excel file exists
        storage_manager = UnifiedS3Manager()
        excel_content, excel_s3_key = storage_manager.get_excel_file(email, session_id)
        if not excel_s3_key:
            return create_response(400, {'error': 'No Excel file found for this session. Please upload an Excel file first.'})
        
        # Auto-discover existing config if not provided (for modifyConfig requests)
        if not existing_config:
            logger.info("Auto-discovering existing config for modification request")
            existing_config = find_latest_config_in_session(
                storage_manager.s3_client, 
                storage_manager.bucket_name, 
                storage_manager.get_session_path(email, session_id)
            )
            if existing_config:
                logger.info(f"Found existing config version {existing_config.get('storage_metadata', {}).get('version', 'unknown')} for modification")
            else:
                logger.warning("No existing configuration found for modification request")
        
        # Send config generation request to SQS for async processing
        try:
            from ..core.sqs_service import send_config_generation_request
            
            # Use the original session_id directly - no need for separate config session
            # Prepare config generation request for SQS
            generation_request = {
                'session_id': session_id,
                'email': email,
                'excel_s3_key': excel_s3_key,
                'existing_config': existing_config,
                'instructions': instructions,
                'storage_path': storage_manager.get_session_path(email, session_id),
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"Sending config generation request to SQS: {generation_request}")
            
            # Send to SQS for async processing
            message_id = send_config_generation_request(generation_request)
            
            logger.info(f"SQS send result: message_id={message_id}")
            
            if not message_id:
                return create_response(500, {'error': 'Failed to queue config generation request'})
            
            logger.info(f"Config generation request queued successfully: {message_id}")
            
            # Return immediately with session info - results will come via WebSocket
            # NO ai_summary field to prevent sync processing on frontend
            response_body = {
                'success': True,
                'status': 'processing',
                'session_id': session_id
                # Explicitly NOT including message_id, ai_summary, clarifying_questions, or download_url
                # These will be sent via WebSocket only
            }
            
            logger.info(f"✅ ASYNC CONFIG RESPONSE (WebSocket-only): {response_body}")
            return create_response(200, response_body)
                
        except Exception as e:
            logger.error(f"Config generation queueing failed: {e}")
            return create_response(500, {'success': False, 'error': f'Config generation queueing failed: {str(e)}'})
        
    except Exception as e:
        logger.error(f"Async config generation failed: {str(e)}")
        return create_response(500, {'success': False, 'error': str(e)})

def handle_modify_config(request_data, context):
    """
    Handle config modification requests using unified storage
    """
    from ..utils.helpers import create_response
    from ..core.unified_s3_manager import UnifiedS3Manager
    
    try:
        email = request_data.get('email')
        session_id = request_data.get('session_id')
        instructions = request_data.get('instructions', 'Modify the configuration')
        
        if not email or not session_id:
            return create_response(400, {'error': 'Missing email or session_id'})
        
        # Initialize unified storage
        storage_manager = UnifiedS3Manager()
        
        # Auto-discover existing config using enhanced logic
        existing_config = find_latest_config_in_session(
            storage_manager.s3_client, 
            storage_manager.bucket_name, 
            storage_manager.get_session_path(email, session_id)
        )
        if not existing_config:
            return create_response(404, {
                'error': 'No existing configuration found for refinement. Please create a configuration first.',
                'suggestion': 'Use generateConfig action to create an initial configuration'
            })
        
        # Prepare request for config generation
        modify_request = {
            'email': email,
            'session_id': session_id,
            'existing_config': existing_config,
            'instructions': instructions
        }
        
        # Generate modified config using versioning
        result = asyncio.run(handle_generate_config_unified(modify_request))
        
        if result['success']:
            return create_response(200, result)
        else:
            return create_response(500, result)
            
    except Exception as e:
        logger.error(f"Config modification failed: {str(e)}")
        return create_response(500, {'success': False, 'error': str(e)})

# Main handlers
def handle(request_data, context):
    """Main handler that routes to appropriate config generation method"""
    action = request_data.get('action', 'generate')
    
    if action == 'generate':
        return handle_generate_config_sync(request_data, context)
    elif action == 'modify':
        return handle_modify_config(request_data, context)
    else:
        from ..utils.helpers import create_response
        return create_response(400, {'error': f'Unknown config action: {action}'})