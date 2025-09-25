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
from dynamodb_schemas import update_run_status, get_connection_by_session, remove_websocket_connection, create_run_record
from interface_lambda.core.validator_invoker import invoke_validator_lambda
from interface_lambda.reporting.zip_report import create_enhanced_result_zip
from interface_lambda.reporting.markdown_report import create_markdown_table_from_results
from interface_lambda.reporting.excel_report_new import create_enhanced_excel_with_validation, EXCEL_ENHANCEMENT_AVAILABLE
from email_sender import send_validation_results_email
from dynamodb_schemas import update_processing_metrics, track_email_delivery, track_user_request, update_run_status

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def _enhance_config_generation_costs(eliyahu_cost: float, token_usage: dict, processing_time: float, is_cached: bool) -> dict:
    """
    Enhance config generation cost tracking with three-tier cost analysis.
    
    Args:
        eliyahu_cost: Actual cost paid for config generation
        token_usage: Token usage data from config lambda
        processing_time: Processing time in seconds
        is_cached: Whether the response was cached
        
    Returns:
        Enhanced cost data with efficiency metrics
    """
    try:
        # Calculate estimated cost without cache benefit
        if is_cached:
            # For config generation, if cached, estimate what non-cached cost would be
            # Use token-based estimation for cached responses
            total_tokens = token_usage.get('total_tokens', 0)
            if total_tokens > 0:
                # Conservative estimate: $3 per million input tokens, $15 per million output tokens
                input_tokens = token_usage.get('input_tokens', total_tokens // 2)
                output_tokens = token_usage.get('output_tokens', total_tokens - input_tokens)
                cost_estimated = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)
            else:
                # Fallback: assume cached saved 80% of cost
                cost_estimated = eliyahu_cost / 0.2 if eliyahu_cost > 0 else 0.01
        else:
            # If not cached, estimated cost equals actual cost
            cost_estimated = eliyahu_cost
        
        # Config generation is typically free to users, but track internal costs
        internal_cost = eliyahu_cost
        user_cost = 0.0  # Config generation is free
        
        # Calculate efficiency metrics
        total_tokens = token_usage.get('total_tokens', 0)
        cost_per_token = internal_cost / max(1, total_tokens)
        tokens_per_second = total_tokens / max(0.001, processing_time)
        cost_per_second = internal_cost / max(0.001, processing_time)
        
        # Config generation efficiency score (tokens per dollar per second)
        efficiency_score = tokens_per_second / max(0.001, cost_per_second)
        
        # Calculate cache savings if applicable
        cache_savings = cost_estimated - eliyahu_cost if is_cached else 0.0
        
        enhanced_data = {
            'eliyahu_cost': internal_cost,  # What we paid
            'cost_estimated': cost_estimated,  # Estimated without caching
            'user_cost': user_cost,  # What user pays (free for config)
            'cache_savings': cache_savings,
            'is_cached': is_cached,
            'processing_time': processing_time,
            'efficiency_metrics': {
                'total_tokens': total_tokens,
                'cost_per_token': cost_per_token,
                'tokens_per_second': tokens_per_second,
                'cost_per_second': cost_per_second,
                'efficiency_score': efficiency_score
            },
            'operation_type': 'config_generation'
        }
        
        # Validation
        if internal_cost < 0 or cost_estimated < 0:
            logger.error(f"[CONFIG_COST_ERROR] Negative costs detected - Internal: ${internal_cost:.6f}, "
                        f"Estimated: ${cost_estimated:.6f}")
            enhanced_data['eliyahu_cost'] = max(0.0, internal_cost)
            enhanced_data['cost_estimated'] = max(0.0, cost_estimated)
        
        logger.info(f"[CONFIG_COST_ANALYSIS] Enhanced config cost data - "
                   f"Internal: ${internal_cost:.6f}, Estimated: ${cost_estimated:.6f}, "
                   f"Cache savings: ${cache_savings:.6f}, Efficiency: {efficiency_score:.2f}")
        
        return enhanced_data
        
    except Exception as e:
        logger.error(f"[CONFIG_COST_ERROR] Error enhancing config generation costs: {e}")
        return {
            'eliyahu_cost': eliyahu_cost,
            'cost_estimated': eliyahu_cost,
            'user_cost': 0.0,
            'cache_savings': 0.0,
            'is_cached': is_cached,
            'processing_time': processing_time,
            'efficiency_metrics': {
                'total_tokens': 0,
                'cost_per_token': 0.0,
                'tokens_per_second': 0.0,
                'cost_per_second': 0.0,
                'efficiency_score': 0.0
            },
            'operation_type': 'config_generation',
            'error': str(e)
        }

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
        
        # Extract version numbers from ALL .json files using multiple patterns
        versions = []
        for obj in response['Contents']:
            filename = obj['Key'].split('/')[-1]
            if filename.endswith('.json'):
                # Multiple patterns for version detection
                patterns = [
                    r'config_v(\d+)_',      # config_v5_ai_generated.json
                    r'_v(\d+)_',            # session_20250916_v5_something.json
                    r'_v(\d+)\.json$',      # filename_v5.json
                    r'config_v(\d+)\.json$', # config_v5.json
                    r'session_\w+_v(\d+)_', # session_20250916_123456_v5_config.json
                    r'session_\w+_v(\d+)\.json$' # session_20250916_123456_v5.json
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, filename)
                    if match:
                        try:
                            version = int(match.group(1))
                            versions.append(version)
                            logger.debug(f"Found version {version} in {filename}")
                            break  # Stop at first match
                        except ValueError:
                            continue
        
        next_version = max(versions, default=0) + 1
        logger.info(f"Detected versions: {sorted(set(versions))}, next version: {next_version}")
        return next_version
    except Exception as e:
        logger.warning(f"Could not determine next version: {e}")
        return 1

def store_config_with_versioning(email: str, session_id: str, config_data: dict, 
                                source: str = 'refined', run_key: str = None) -> dict:
    """Store config with automatic version increment and session tracking"""
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
    
    # Update session tracking if storage was successful
    if result.get('success'):
        try:
            config_description = config_data.get('general_notes', f'{source.replace("_", " ").title()} configuration')
            update_success = storage_manager.update_session_config(
                email=email,
                session_id=session_id,
                config_data=config_data,
                config_key=result['s3_key'],
                config_id=result.get('config_id'),
                version=next_version,
                source=source,
                description=config_description,
                run_key=run_key
            )
            result['session_tracking_updated'] = update_success
            logger.info(f"Session tracking updated for {source} config v{next_version}: {update_success}")
        except Exception as e:
            logger.warning(f"Failed to update session tracking for {source} config: {e}")
            result['session_tracking_updated'] = False
    
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
        
        # Get input table name early for runs table tracking
        input_table_name = f"table_{session_id}"
        try:
            # Try to get the actual Excel filename from unified storage
            storage_manager_temp = UnifiedS3Manager()
            excel_content, excel_s3_key = storage_manager_temp.get_excel_file(email, session_id)
            if excel_s3_key:
                input_table_name = excel_s3_key.split('/')[-1]  # Get filename from S3 key
        except Exception as e:
            logger.warning(f"Could not get Excel filename for runs table: {e}")
            
        # Determine run type based on whether existing config is provided
        is_refinement = existing_config is not None and existing_config.get('config_change_log')
        run_type = "Config Refinement" if is_refinement else "Config Generation"
        
        # Create runs table record for config generation/refinement tracking
        logger.info(f"[CONFIG_RUN_TRACKING] Creating {run_type.lower()} run record for session {session_id}")
        try:
            run_key = create_run_record(session_id=session_id, email=email, total_rows=0, batch_size=1, run_type=run_type)
            logger.info(f"[CONFIG_RUN_TRACKING] Created run record with run_key: {run_key}")
            update_run_status(
                session_id=session_id,
                run_key=run_key,
                status='IN_PROGRESS',
                run_type=run_type,
                verbose_status=f"{run_type} starting with AI analysis...",
                percent_complete=5,
                processed_rows=0,
                total_rows=0,  # Config generation doesn't process data rows
                input_table_name=input_table_name,
                account_current_balance=0,  # Will be updated later
                account_sufficient_balance="n/a",
                account_credits_needed="n/a", 
                account_domain_multiplier=1.0,  # Config generation typically doesn't use domain multiplier
                models="TBD",  # Will be updated after AI processing
                batch_size=1,  # Config generation batch size
                eliyahu_cost=0.0,  # Will be updated after completion
                time_per_row_seconds=0.0  # Will be updated after completion
            )
        except Exception as e:
            logger.warning(f"[CONFIG_RUN_TRACKING] Failed to create run record: {e}")
        
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
        
        # Use consolidated table parser with formula extraction
        try:
            from shared_table_parser import s3_table_parser

            # First, analyze table structure with formula extraction for config generation
            table_analysis = s3_table_parser.analyze_table_structure(storage_manager.bucket_name, excel_s3_key, extract_formulas=True)

            if not table_analysis:
                return {'success': False, 'error': 'Failed to analyze table structure'}

            logger.info(f"Table analysis completed: {table_analysis.get('basic_info', {}).get('filename', 'Unknown')}")

            # For Excel files, also extract formulas to enhance config generation
            formula_data = None
            if table_analysis.get('metadata', {}).get('file_type') == 'excel':
                try:
                    logger.info("Extracting formulas from Excel file for enhanced config generation...")
                    full_table_data = s3_table_parser.parse_s3_table(
                        storage_manager.bucket_name,
                        excel_s3_key,
                        extract_formulas=True
                    )

                    if full_table_data.get('formulas'):
                        formula_data = full_table_data['formulas']
                        formula_count = full_table_data['metadata'].get('formula_count', 0)
                        logger.info(f"[SUCCESS] Extracted {formula_count} formulas from Excel file")

                        # Add formula information to table analysis
                        table_analysis['formula_data'] = formula_data
                        table_analysis['metadata']['has_formulas'] = True
                        table_analysis['metadata']['formula_count'] = formula_count
                    else:
                        logger.info("No formulas found in Excel file")

                except Exception as formula_error:
                    logger.warning(f"Formula extraction failed (non-critical): {formula_error}")
                    # Continue without formulas - this shouldn't break config generation
            
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
            from botocore.config import Config
            
            # Configure longer timeouts for Opus processing
            config = Config(
                read_timeout=900,  # 15 minutes read timeout  
                connect_timeout=60,  # 1 minute connect timeout
                retries={'max_attempts': 1}  # Don't retry on timeout
            )
            
            lambda_client = boto3.client('lambda', config=config)
            config_lambda_name = os.environ.get('CONFIG_LAMBDA_NAME', 'perplexity-validator-config')
            
            # Prepare payload for config lambda
            # Ensure conversation history is preserved by including current conversation log
            conversation_history = []
            if existing_config and existing_config.get('config_change_log'):
                conversation_history = existing_config['config_change_log'].copy()
                logger.info(f"Preserving {len(conversation_history)} existing conversation entries")

                # For refinements with user instructions, add the user message to conversation history
                if instructions and instructions.strip():
                    user_entry = {
                        'timestamp': datetime.now().isoformat(),
                        'action': 'user_message',
                        'session_id': session_id,
                        'user_instructions': instructions,
                        'entry_type': 'user_input'
                    }
                    conversation_history.append(user_entry)
                    logger.info(f"Added user message to conversation history for refinement")
                
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
            
            # Get latest validation or preview results for context
            # This helps determine if we should treat this as a refinement even without existing_config
            latest_validation_results = None
            try:
                logger.info(f"🔍 RESULTS_RETRIEVAL: Getting latest results for config context")

                # Use circular-dependency-free method for getting results during config generation
                latest_validation_results = storage_manager.get_latest_results_for_context(email, session_id)
                if latest_validation_results:
                    logger.info(f"✅ SUCCESS: Retrieved results for config context (existing_config={bool(existing_config)})")
                else:
                    logger.info("❌ No validation or preview results found for context")

            except Exception as e:
                logger.error(f"DEBUG_CONFIG_UNIFIED: EXCEPTION - Could not retrieve results for context: {e}")
                import traceback
                logger.error(f"DEBUG_CONFIG_UNIFIED: Traceback: {traceback.format_exc()}")
                latest_validation_results = None
            
            # Strip generation_metadata from existing_config to prevent cache pollution
            clean_existing_config = None
            if existing_config:
                clean_existing_config = existing_config.copy()
                if 'generation_metadata' in clean_existing_config:
                    logger.info("Stripping generation_metadata from existing_config for config lambda to prevent cache issues")
                    del clean_existing_config['generation_metadata']

            payload = {
                'table_analysis': table_analysis,
                'existing_config': clean_existing_config,
                'instructions': instructions,
                'session_id': session_id,
                'email': email,  # Include email for context
                'preserve_conversation_history': True,  # Signal to config lambda to preserve history
                'conversation_history': conversation_history,  # Pass updated conversation including user message
                'latest_validation_results': latest_validation_results  # Add validation results context
            }
            
            # Debug the payload being sent to config lambda
            logger.info(f"DEBUG_CONFIG_UNIFIED: Payload being sent to config lambda:")
            logger.info(f"DEBUG_CONFIG_UNIFIED: - has table_analysis: {bool(payload.get('table_analysis'))}")
            logger.info(f"DEBUG_CONFIG_UNIFIED: - has existing_config: {bool(payload.get('existing_config'))}")
            logger.info(f"DEBUG_CONFIG_UNIFIED: - instructions: {payload.get('instructions', '')[:50]}...")
            logger.info(f"DEBUG_CONFIG_UNIFIED: - session_id: {payload.get('session_id')}")
            logger.info(f"DEBUG_CONFIG_UNIFIED: - latest_validation_results is None: {payload.get('latest_validation_results') is None}")
            if payload.get('latest_validation_results'):
                vr = payload.get('latest_validation_results')
                logger.info(f"DEBUG_CONFIG_UNIFIED: - latest_validation_results type: {type(vr)}")
                logger.info(f"DEBUG_CONFIG_UNIFIED: - latest_validation_results keys: {list(vr.keys()) if isinstance(vr, dict) else 'N/A'}")
            else:
                logger.info(f"DEBUG_CONFIG_UNIFIED: - latest_validation_results is None or empty")
            
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
                error_message = body.get('error', 'Unknown error')
                error_response = {
                    'success': False, 
                    'error': error_message,
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
                
                # Update runs table with config lambda failure
                try:
                    logger.info(f"[CONFIG_RUN_TRACKING] Updating {run_type.lower()} run record with config lambda failure")
                    update_run_status(
                        session_id=session_id,
                        run_key=run_key,
                        status='FAILED',
                        run_type=run_type,
                        verbose_status=f"{run_type} failed in config lambda",
                        percent_complete=0,
                        error_message=error_message
                    )
                    logger.info(f"[CONFIG_RUN_TRACKING] Successfully updated config generation run record with config lambda failure")
                except Exception as run_error:
                    logger.error(f"[CONFIG_RUN_TRACKING] Failed to update run record with config lambda failure: {run_error}")
                
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
                    email, session_id, updated_config, source='ai_generated', run_key=run_key
                )
                version = storage_result.get('version', 1)
                config_version = version  # Ensure config_version is always set
            
            if not storage_result['success']:
                return {'success': False, 'error': f'Failed to store generated config: {storage_result["error"]}'}
            
            # Update comprehensive session tracking
            try:
                # Update session config tracking with comprehensive data
                config_description = updated_config.get('general_notes', 'AI generated configuration')
                update_success = storage_manager.update_session_config(
                    email=email,
                    session_id=session_id,
                    config_data=updated_config,
                    config_key=storage_result['s3_key'],
                    config_id=storage_result.get('config_id'),
                    version=version,
                    source='ai_generated',
                    description=config_description
                )
                
                if update_success:
                    logger.info(f"Updated session_info.json with AI generated config v{version}")
                else:
                    logger.warning(f"Failed to update session_info.json (will fall back to legacy tracking)")
                    
            except Exception as e:
                logger.warning(f"Failed to update session_info.json: {e}")
            
            # Legacy session info update (fallback)
            try:
                # Get table name from session or use default
                table_name = f"table_{session_id.split('_')[-1]}"
                session_info_result = storage_manager.create_session_info(
                    email, session_id, table_name, current_config_version=version,
                    config_source='ai_generated'
                )
                if session_info_result['success']:
                    logger.info(f"Legacy session info updated with config version {version}")
            except Exception as e:
                logger.warning(f"Failed to update legacy session info: {e}")
            
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
            
            # ========== ENHANCED CONFIG GENERATION COST INTEGRATION ==========
            # Extract cost and usage data from config lambda response (now uses centralized ai_api_client)
            eliyahu_cost = body.get('eliyahu_cost', 0.0)  # Actual cost paid
            token_usage = body.get('token_usage', {})
            processing_time = body.get('processing_time', 0.0)
            model_used = body.get('model_used', 'unknown')
            is_cached = body.get('is_cached', False)
            
            # Calculate enhanced cost metrics for config generation
            enhanced_config_cost_data = _enhance_config_generation_costs(
                eliyahu_cost, token_usage, processing_time, is_cached
            )
            
            # Update runs table with completion data
            logger.info(f"[CONFIG_RUN_TRACKING] Updating {run_type.lower()} run record with completion data")
            try:
                # Determine which AI models were used - with call counts for config operation
                models_text = f"{model_used} X 1"
                if is_cached:
                    models_text += " (cached)"
                
                # Use the input table name we got earlier (no need to fetch again)
                
                # ========== ENHANCED PREVIEW DATA WITH THREE-TIER COSTS ==========
                # Build enhanced token usage summary for preview_data
                preview_data = {
                    "token_usage": {
                        "total_tokens": token_usage.get('total_tokens', 0),
                        "by_provider": {
                            "anthropic" if 'claude' in model_used.lower() else "perplexity": {
                                "prompt_tokens": token_usage.get('input_tokens', 0),
                                "completion_tokens": token_usage.get('output_tokens', 0),
                                "total_cost": eliyahu_cost,
                                "calls": 1
                            }
                        }
                    },
                    "enhanced_cost_data": enhanced_config_cost_data,  # Full cost analysis
                    "cost_summary": {
                        "internal_cost": enhanced_config_cost_data.get('eliyahu_cost', 0.0),
                        "cost_estimated": enhanced_config_cost_data.get('cost_estimated', 0.0),
                        "user_cost": enhanced_config_cost_data.get('user_cost', 0.0),
                        "cache_savings": enhanced_config_cost_data.get('cache_savings', 0.0),
                        "efficiency_score": enhanced_config_cost_data.get('efficiency_metrics', {}).get('efficiency_score', 0.0)
                    }
                }
                
                # Calculate timing metrics for config operation
                time_per_config = processing_time  # For config operation, it's time per config
                
                # Convert config token_usage data to enhanced provider metrics format
                provider_metrics_for_db = {}
                provider_name = "anthropic" if 'claude' in model_used.lower() else "perplexity"
                
                if eliyahu_cost > 0 or token_usage.get('total_tokens', 0) > 0:
                    # Estimate cost without cache for config operations
                    cache_multiplier = 1.2 if is_cached else 1.0  # Modest increase for cached configs
                    cost_estimated = eliyahu_cost * cache_multiplier
                    
                    provider_metrics_for_db[provider_name] = {
                        'calls': 1,
                        'tokens': token_usage.get('total_tokens', 0),
                        'cost_actual': eliyahu_cost,
                        'cost_estimated': cost_estimated,
                        'processing_time': processing_time,
                        'cache_hit_tokens': token_usage.get('total_tokens', 0) if is_cached else 0,
                        'cost_per_row_actual': eliyahu_cost,  # For config, "per row" is per config
                        'cost_per_row_estimated': cost_estimated,
                        'time_per_row_actual': processing_time,
                        'cache_efficiency_percent': ((cost_estimated - eliyahu_cost) / max(cost_estimated, 0.000001)) * 100 if is_cached else 0
                    }
                
                # Update runs table with completion
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='COMPLETED',
                    run_type=run_type,
                    verbose_status=f"{run_type} completed successfully",
                    percent_complete=100,
                    processed_rows=1,  # One config generated
                    total_rows=0,  # No validation rows processed
                    input_table_name=input_table_name,
                    models=models_text,
                    preview_data=preview_data,
                    # ========== THREE-TIER COST TRACKING FOR CONFIG OPERATIONS ==========
                    eliyahu_cost=enhanced_config_cost_data.get('eliyahu_cost', 0.0),  # Actual internal cost paid
                    quoted_validation_cost=enhanced_config_cost_data.get('user_cost', 0.0),  # What user pays (free for config)
                    estimated_validation_eliyahu_cost=enhanced_config_cost_data.get('cost_estimated', 0.0),  # Estimated cost without caching
                    time_per_row_seconds=None,  # Not applicable for config operations
                    estimated_validation_time_minutes=None,  # Not applicable for config operations
                    run_time_s=processing_time,  # Actual config operation time in seconds
                    provider_metrics=provider_metrics_for_db  # Enhanced provider-specific metrics
                )
                logger.info(f"[CONFIG_RUN_TRACKING] Successfully updated {run_type.lower()} run record")
                
            except Exception as e:
                logger.error(f"[CONFIG_RUN_TRACKING] Failed to update run record with completion: {e}")
            
            # Get config filename from the config lambda response
            config_filename = body.get('config_filename')
            if config_filename:
                # Store the config lambda filename in the updated config's metadata
                if 'generation_metadata' not in updated_config:
                    updated_config['generation_metadata'] = {}
                updated_config['generation_metadata']['config_lambda_filename'] = config_filename
                logger.info(f"Config lambda filename: {config_filename}")
                
                # Also store actual filename in config_change_log entries
                if 'config_change_log' in updated_config:
                    for entry in updated_config['config_change_log']:
                        if 'config_filename' not in entry:
                            entry['config_filename'] = config_filename
            
            # DEBUG: Log clarifying questions from config lambda
            config_clarifying_questions = body.get('clarifying_questions', '')
            clarification_urgency = body.get('clarification_urgency', 0.0)
            print(f"🔍 INTERFACE_DEBUG: Config lambda clarifying_questions: {bool(config_clarifying_questions)}")
            if config_clarifying_questions:
                print(f"🔍 INTERFACE_DEBUG: Questions length: {len(config_clarifying_questions)}")
                print(f"🔍 INTERFACE_DEBUG: Questions preview: {config_clarifying_questions[:200]}...")
            else:
                print(f"🔍 INTERFACE_DEBUG: No clarifying questions from config lambda")

            # CRITICAL: Add clarifying questions to the config before storing
            if config_clarifying_questions:
                updated_config['clarifying_questions'] = config_clarifying_questions
                updated_config['clarification_urgency'] = clarification_urgency
                print(f"🔍 INTERFACE_DEBUG: Added clarifying questions to config before storage")
            else:
                print(f"🔍 INTERFACE_DEBUG: No clarifying questions to add to config")

            # ========== ENHANCED RESPONSE WITH COST ANALYSIS ==========
            return {
                'success': True,
                'updated_config': updated_config,
                'clarifying_questions': config_clarifying_questions,
                'clarification_urgency': body.get('clarification_urgency', 0.0),
                'reasoning': body.get('reasoning', ''),
                'ai_summary': body.get('ai_summary', ''),
                'technical_ai_summary': body.get('technical_ai_summary', ''),
                'config_s3_key': storage_result['s3_key'],
                'config_version': version,
                'config_filename': config_filename,  # Include config lambda filename
                'storage_path': storage_result['session_path'],
                'download_url': download_url,
                'session_id': session_id,
                # Enhanced cost tracking for config generation
                'cost_analysis': {
                    'internal_cost': enhanced_config_cost_data.get('eliyahu_cost', 0.0),
                    'cost_estimated': enhanced_config_cost_data.get('cost_estimated', 0.0),
                    'user_cost': enhanced_config_cost_data.get('user_cost', 0.0),
                    'cache_savings': enhanced_config_cost_data.get('cache_savings', 0.0),
                    'is_cached': is_cached,
                    'processing_time': processing_time,
                    'efficiency_score': enhanced_config_cost_data.get('efficiency_metrics', {}).get('efficiency_score', 0.0),
                    'operation_type': 'config_generation'
                }
            }
            
        except Exception as e:
            logger.error(f"Config lambda invocation failed: {str(e)}")
            # Update runs table with failure
            try:
                logger.info(f"[CONFIG_RUN_TRACKING] Updating {run_type.lower()} run record with failure")
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='FAILED',
                    run_type=run_type,
                    verbose_status=f"{run_type} failed",
                    percent_complete=0,
                    error_message=str(e)
                )
                logger.info(f"[CONFIG_RUN_TRACKING] Successfully updated {run_type.lower()} run record with failure")
            except Exception as run_error:
                logger.error(f"[CONFIG_RUN_TRACKING] Failed to update run record with failure: {run_error}")
            
            return {'success': False, 'error': f'Config generation failed: {str(e)}'}
        
    except Exception as e:
        logger.error(f"Config generation error: {str(e)}")
        # Update runs table with exception failure (use default run_type if not set)
        try:
            # Use session_id and existing_config to determine run_type if not already set
            if 'run_type' not in locals():
                is_refinement = existing_config is not None and existing_config.get('config_change_log')
                run_type = "Config Refinement" if is_refinement else "Config Generation"
            
            logger.info(f"[CONFIG_RUN_TRACKING] Updating {run_type.lower()} run record with exception failure")
            # Use run_key if available for composite key
            update_run_status(
                session_id=session_id,
                run_key=run_key if 'run_key' in locals() else None,
                status='FAILED',
                run_type=run_type,
                verbose_status=f"{run_type} failed with exception",
                percent_complete=0,
                error_message=str(e)
            )
            logger.info(f"[CONFIG_RUN_TRACKING] Successfully updated {run_type.lower()} run record with exception failure")
        except Exception as run_error:
            logger.error(f"[CONFIG_RUN_TRACKING] Failed to update run record with exception failure: {run_error}")
        
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