"""
Handles the main background processing for validation tasks.
This is where the core orchestration happens for a validation run after
it has been triggered.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
import math
import io
from typing import Dict

import boto3

# Initialize AWS clients
s3_client = boto3.client('s3')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import DynamoDB functions at module level
# Define dummy functions first as fallback
def update_processing_metrics(*args, **kwargs): 
    logger.warning("DynamoDB not available - processing metrics not updated")
def track_email_delivery(*args, **kwargs): 
    logger.warning("DynamoDB not available - email delivery not tracked")
def track_user_request(*args, **kwargs): 
    logger.warning("DynamoDB not available - user request not tracked")
def update_run_status(**kwargs): 
    logger.warning("DynamoDB not available - run status not updated")

DYNAMODB_AVAILABLE = False

try:
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
    from dynamodb_schemas import update_processing_metrics, track_email_delivery, track_user_request, update_run_status
    DYNAMODB_AVAILABLE = True
    logger.info("DynamoDB functions imported successfully at module level")
except ImportError as e:
    logger.error(f"Failed to import dynamodb_schemas at module level: {e}")
    # Dummy functions are already defined above

# Global variable for the API Gateway Management client
api_gateway_management_client = None

def _get_api_gateway_management_client(context):
    """Initializes the API Gateway Management client."""
    global api_gateway_management_client
    if api_gateway_management_client is None:
        # The endpoint URL must be retrieved from the context of the WebSocket API request
        # For the background handler, it must be passed in via an environment variable.
        endpoint_url = os.environ.get('WEBSOCKET_API_URL')
        if not endpoint_url:
            logger.error("WEBSOCKET_API_URL environment variable not set.")
            return None
        
        # Convert WebSocket URL (wss://) to HTTPS endpoint for API Gateway Management
        if endpoint_url.startswith('wss://'):
            endpoint_url = endpoint_url.replace('wss://', 'https://')
            logger.info(f"Converted WebSocket URL to HTTPS endpoint: {endpoint_url}")
        
        # Ensure the endpoint URL includes the stage (prod)
        if not endpoint_url.endswith('/prod'):
            endpoint_url = endpoint_url.rstrip('/') + '/prod'
            logger.info(f"Added /prod stage to endpoint URL: {endpoint_url}")
        
        api_gateway_management_client = boto3.client('apigatewaymanagementapi', endpoint_url=endpoint_url)
    return api_gateway_management_client

def _send_balance_update(session_id: str, balance_data: dict):
    """Send balance update via WebSocket."""
    from dynamodb_schemas import get_connection_by_session, remove_websocket_connection
    
    connection_id = get_connection_by_session(session_id)
    if connection_id:
        try:
            client = _get_api_gateway_management_client(None)
            if client:
                client.post_to_connection(
                    ConnectionId=connection_id,
                    Data=json.dumps(balance_data).encode('utf-8')
                )
                logger.info(f"Balance update sent to WebSocket {connection_id}")
        except client.exceptions.GoneException:
            logger.warning(f"WebSocket connection {connection_id} is stale. Removing from DB.")
            remove_websocket_connection(connection_id)
        except Exception as e:
            logger.error(f"Failed to send balance update to WebSocket {connection_id}: {e}")

def _update_progress(session_id: str, status: str, processed_rows: int, verbose_status: str, percent_complete: int, total_rows: int = None, current_batch: int = None, total_batches: int = None):
    """Callback function to update DynamoDB and push WebSocket messages."""
    from dynamodb_schemas import update_run_status, get_connection_by_session, remove_websocket_connection
    
    # 1. Update DynamoDB
    update_run_status(
        session_id=session_id, status=status,
        processed_rows=processed_rows, verbose_status=verbose_status,
        percent_complete=percent_complete
    )

    # 2. Push update over WebSocket
    connection_id = get_connection_by_session(session_id)
    if connection_id:
        try:
            client = _get_api_gateway_management_client(None) # Context is not available here
            if client:
                payload = {
                    'status': status, 'processed_rows': processed_rows,
                    'verbose_status': verbose_status, 'percent_complete': percent_complete
                }
                # Include total_rows if provided (mainly for completion messages)
                if total_rows is not None:
                    payload['total_rows'] = total_rows
                # Include batch information if provided
                if current_batch is not None:
                    payload['current_batch'] = current_batch
                if total_batches is not None:
                    payload['total_batches'] = total_batches
                    
                client.post_to_connection(
                    ConnectionId=connection_id,
                    Data=json.dumps(payload).encode('utf-8')
                )
        except client.exceptions.GoneException:
            logger.warning(f"WebSocket connection {connection_id} is stale. Removing from DB.")
            remove_websocket_connection(connection_id)
        except Exception as e:
            logger.error(f"Failed to post to WebSocket connection {connection_id}: {e}")

# Environment variables will be needed here, or passed as arguments.
def get_unified_bucket():
    """Get the unified S3 bucket name from environment"""
    return os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')

S3_UNIFIED_BUCKET = get_unified_bucket()
S3_RESULTS_BUCKET = os.environ.get('S3_RESULTS_BUCKET', 'perplexity-results')
VALIDATOR_LAMBDA_NAME = os.environ.get('VALIDATOR_LAMBDA_NAME', 'perplexity-validator')

def handle(event, context):
    """Handle background processing for both normal and preview mode validation."""
    try:
        from ..core.validator_invoker import invoke_validator_lambda
        from ..reporting.zip_report import create_enhanced_result_zip
        from ..reporting.markdown_report import create_markdown_table_from_results
        
        try:
            from ..reporting.excel_report_new import create_enhanced_excel_with_validation, EXCEL_ENHANCEMENT_AVAILABLE
        except ImportError:
            EXCEL_ENHANCEMENT_AVAILABLE = False
            def create_enhanced_excel_with_validation(*args, **kwargs): return None
        
        try:
            from email_sender import send_validation_results_email
            EMAIL_SENDER_AVAILABLE = True
        except ImportError:
            EMAIL_SENDER_AVAILABLE = False

        logger.info("--- Background Handler Started ---")
        
        # Check if this is a config generation request
        if event.get('request_type') == 'config_generation':
            logger.info("Detected config generation request, forwarding to validation lambda")
            return handle_config_generation(event, context)
        
        # Extract parameters from event, ensuring correct types
        # Check both preview_mode and request_type for compatibility
        is_preview = event.get('preview_mode', False) or event.get('request_type') == 'preview'
        session_id = event['session_id']
        timestamp = event.get('timestamp')
        reference_pin = event.get('reference_pin', '000000')
        
        # If reference_pin is 'preview' or similar, extract it from clean_session_id
        if reference_pin == 'preview' or not reference_pin or reference_pin == '000000':
            # Extract reference pin from clean session ID
            if '_' in clean_session_id:
                reference_pin = clean_session_id.split('_')[-1]
            else:
                reference_pin = clean_session_id[:6]
        excel_s3_key = event['excel_s3_key']
        config_s3_key = event['config_s3_key']
        email = event.get('email', 'unknown@example.com')
        preview_email = event.get('preview_email', False)
        
        # Always use a clean session ID format: session_YYYY-MM-DDTHH_MM_SS_XXXXXX
        # Ensure session ID has proper prefix
        clean_session_id = session_id
        if not clean_session_id.startswith('session_'):
            clean_session_id = f"session_{clean_session_id}"
            
        logger.info(f"Background handler called for session {session_id}, clean_session_id={clean_session_id}, is_preview={is_preview}")
        
        try:
            max_rows_str = event.get('max_rows')
            max_rows = int(max_rows_str) if max_rows_str else 1000
            
            batch_size_str = event.get('batch_size')
            batch_size = int(batch_size_str) if batch_size_str else 10
        except (ValueError, TypeError):
            logger.warning("Invalid max_rows or batch_size, using defaults.")
            max_rows = 1000
            batch_size = 10

        email_folder = event.get('email_folder', 'default')
        email_address = event.get('email_address')
        
        # After a job starts
        update_run_status(session_id=session_id, status='PROCESSING')

        if is_preview:
            preview_max_rows = event.get('preview_max_rows', 5)
            sequential_call_num = event.get('sequential_call')
            logger.info(f"Background preview processing for session {session_id}")
            
            # Send initial WebSocket progress update
            _send_websocket_message_deduplicated(session_id, {
                'type': 'preview_progress',
                'progress': 5,
                'status': f'🚀 Starting preview validation for {preview_max_rows} rows...',
                'session_id': session_id,
                'preview_max_rows': preview_max_rows
            }, "preview_progress_start")
            
            # Initial status update for preview
            update_run_status(
                session_id=session_id, status='PROCESSING', 
                verbose_status=f"Starting preview for {preview_max_rows} rows...",
                percent_complete=10
            )

            # Send file retrieval progress update
            _send_websocket_message_deduplicated(session_id, {
                'type': 'preview_progress',
                'progress': 15,
                'status': '📁 Retrieving Excel file and configuration...',
                'session_id': session_id
            }, "preview_progress_files")
            
            # Use unified storage to get files for preview
            from ..core.unified_s3_manager import UnifiedS3Manager
            storage_manager = UnifiedS3Manager()
            
            # Get files from unified storage using clean session ID
            excel_content, actual_excel_s3_key = storage_manager.get_excel_file(email, clean_session_id)
            config_data, actual_config_s3_key = storage_manager.get_latest_config(email, clean_session_id)
            
            if not excel_content or not config_data:
                logger.error(f"Failed to retrieve files from unified storage for preview session {clean_session_id}")
                
                # Send error WebSocket update
                _send_websocket_message_deduplicated(session_id, {
                    'type': 'preview_failed',
                    'progress': 100,
                    'status': '❌ Failed to retrieve files for preview',
                    'session_id': session_id,
                    'error': 'Files not found'
                }, "preview_failed_files")
                
                update_run_status(
                    session_id=session_id, status='FAILED',
                    verbose_status="Failed to retrieve files for preview.",
                    percent_complete=100
                )
                return {'statusCode': 500, 'body': json.dumps({'status': 'failed', 'error': 'Files not found'})}
            
            # Send validation start progress update
            _send_websocket_message_deduplicated(session_id, {
                'type': 'preview_progress',
                'progress': 30,
                'status': f'🔍 Running AI validation on {preview_max_rows} sample rows...',
                'session_id': session_id
            }, "preview_progress_validation")
            
            validation_results = invoke_validator_lambda(
                actual_excel_s3_key, actual_config_s3_key, max_rows, batch_size, S3_UNIFIED_BUCKET, VALIDATOR_LAMBDA_NAME,
                preview_first_row=True, preview_max_rows=preview_max_rows, sequential_call=sequential_call_num
            )
            
            # Send validation completion progress update
            _send_websocket_message_deduplicated(session_id, {
                'type': 'preview_progress',
                'progress': 70,
                'status': '✅ AI validation completed, processing results...',
                'session_id': session_id
            }, "preview_progress_validation_complete")
            
            # Send results processing progress update
            _send_websocket_message_deduplicated(session_id, {
                'type': 'preview_progress',
                'progress': 80,
                'status': '📊 Analyzing results and generating estimates...',
                'session_id': session_id
            }, "preview_progress_analysis")
            
            # Final status update for preview
            if validation_results and validation_results.get('validation_results'):
                # Extract metadata first
                real_results = validation_results.get('validation_results', {})
                total_rows = validation_results.get('total_rows', 1)
                metadata = validation_results.get('metadata', {})
                token_usage = metadata.get('token_usage', {})
                # Get both costs from validation lambda
                eliyahu_cost = token_usage.get('total_cost', 0.0)  # What we actually paid for this preview run
                estimated_cost = token_usage.get('estimated_total_cost', eliyahu_cost)  # What this preview run would cost without caching
                total_tokens = token_usage.get('total_tokens', 0)
                total_api_calls = token_usage.get('api_calls', 0)
                total_cached_calls = token_usage.get('cached_calls', 0)
                total_rows_processed = validation_results.get('total_processed_rows', 1)
                validation_metrics = metadata.get('validation_metrics', {})
                
                # Initialize balance variables (preview doesn't charge)
                initial_balance = 0
                final_balance = 0
                multiplier = 1.0
                quoted_full_cost = math.ceil(estimated_cost)  # Will become full table quote after scaling and multiplier applied, rounded up
                charged_cost = 0.0  # Preview is free
                
                # Apply domain multiplier to estimated cost (what user pays)
                try:
                    import sys
                    import os
                    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
                    from dynamodb_schemas import get_domain_multiplier, track_preview_cost, track_api_usage_detailed, check_user_balance
                    from decimal import Decimal
                    
                    email_domain = email.split('@')[-1] if '@' in email else 'unknown'
                    multiplier = float(get_domain_multiplier(email_domain))
                    
                    # Calculate preview cost with multiplier (this will be used for scaling to full table)
                    preview_cost_with_multiplier = estimated_cost * multiplier
                    
                    logger.info(f"INTERFACE_COSTS: Processed {total_rows_processed} rows, Charged: ${charged_cost:.6f} (preview is free)")
                    logger.debug(f"COST_DEBUG: Domain={email_domain}, Estimated: ${estimated_cost:.6f}, Preview with multiplier: ${preview_cost_with_multiplier:.6f}")
                    
                    # Get account balance for tracking (no charges for preview) - moved to just before calculations
                    initial_balance = check_user_balance(email)
                    final_balance = initial_balance  # No change for preview
                    balance_error_occurred = False  # Preview doesn't charge
                    charged_amount = 0  # No charges for preview
                    
                    # Track preview cost (actual cost for your tracking, estimated cost for user display)
                    track_preview_cost(session_id, email, Decimal(str(estimated_cost)), Decimal(str(multiplier)), total_tokens)
                    
                    # Track detailed API usage for each provider
                    by_provider = token_usage.get('by_provider', {})
                    for provider, provider_usage in by_provider.items():
                        if provider_usage and isinstance(provider_usage, dict):
                            usage_data = {
                                'api_calls': provider_usage.get('api_calls', 0),
                                'cached_calls': provider_usage.get('cached_calls', 0),
                                'total_tokens': provider_usage.get('total_tokens', 0),
                                'cost': provider_usage.get('total_cost', 0.0) * multiplier,  # Apply multiplier to actual cost
                                'eliyahu_cost': provider_usage.get('total_cost', 0.0),  # Your actual expense
                                'multiplier_applied': multiplier
                            }
                            
                            # Add provider-specific token fields (AI client standardizes to input_tokens/output_tokens)
                            if provider == 'perplexity':
                                usage_data.update({
                                    'prompt_tokens': provider_usage.get('input_tokens', 0),  # AI client maps prompt_tokens to input_tokens
                                    'completion_tokens': provider_usage.get('output_tokens', 0)  # AI client maps completion_tokens to output_tokens
                                })
                            elif provider == 'anthropic':
                                usage_data.update({
                                    'input_tokens': provider_usage.get('input_tokens', 0),
                                    'output_tokens': provider_usage.get('output_tokens', 0),
                                    'cache_tokens': provider_usage.get('cache_creation_tokens', 0) + provider_usage.get('cache_read_tokens', 0)
                                })
                            
                            # Track detailed usage for this provider
                            
                    
                except Exception as e:
                    logger.error(f"Error applying domain multiplier in preview: {e}")
                    multiplier = 1.0
                    # Fallback if multiplier lookup fails
                    quoted_full_cost = math.ceil(estimated_cost)  # Will be recalculated with proper scaling, rounded up
                
                # --- Start of Complex Estimations Logic ---
                
                # Use batch timing info from the validator if available, otherwise fallback
                batch_timing = metadata.get('batch_timing', {})
                validator_processing_time = metadata.get('processing_time', 0.0)
                processing_time = 0.0
                time_per_batch = 20.0 # Default fallback
                time_per_row = 4.0 # Default fallback

                if batch_timing:
                    processing_time = batch_timing.get('total_batch_time_seconds', 0.0)
                    time_per_batch = batch_timing.get('average_batch_time_seconds', time_per_batch)
                    time_per_row = batch_timing.get('average_time_per_row_seconds', time_per_row)
                elif validator_processing_time > 0:
                    processing_time = validator_processing_time
                    if total_rows_processed > 0:
                        time_per_row = processing_time / total_rows_processed
                        time_per_batch = time_per_row * 5 # Assuming 5 rows per batch for estimation
                
                # Scale preview costs to full table estimates for user quotes
                # estimated_cost remains as preview run cost without caching
                # quoted_full_cost = scale to full table: (preview_cost / preview_rows) * total_rows * multiplier
                preview_with_multiplier = estimated_cost * multiplier  # Preview cost with multiplier applied
                per_row_cost = preview_with_multiplier / total_rows_processed if total_rows_processed > 0 else 0.02 * multiplier
                per_row_tokens = total_tokens / total_rows_processed if total_rows_processed > 0 else 200

                # Project to full table (this becomes quoted_full_cost)
                total_batches = math.ceil(total_rows / 5) # Assume batches of 5 for estimation
                estimated_total_time_seconds = total_batches * time_per_batch
                quoted_full_cost = math.ceil(per_row_cost * total_rows)  # Full table quote = per_row_cost * total_rows, rounded up to next dollar
                estimated_total_tokens = per_row_tokens * total_rows
                
                # --- End of Complex Estimations Logic ---

                # Get the most recent account balance right before calculating sufficient_balance
                # This ensures we capture any recent credit additions from the frontend
                logger.info(f"[BALANCE_CHECK] Refreshing balance for {email} before sufficient_balance calculation")
                current_balance = check_user_balance(email)
                logger.info(f"[BALANCE_CHECK] Current balance: {current_balance}, Quoted full cost: {quoted_full_cost}")

                # Create the markdown table for the response
                markdown_table = create_markdown_table_from_results(real_results, 3, actual_config_s3_key, S3_UNIFIED_BUCKET)
                
                preview_payload = {
                    "status": "COMPLETED", "session_id": session_id,
                    "markdown_table": markdown_table, "total_rows": total_rows,
                    "total_processed_rows": total_rows_processed,
                    "preview_processing_time": processing_time,
                    "estimated_total_processing_time": estimated_total_time_seconds,
                    "estimated_total_time_minutes": round(estimated_total_time_seconds / 60, 1),
                    "cost_estimates": {
                        "preview_cost": charged_cost,  # What user pays for preview (0)
                        "quoted_full_cost": quoted_full_cost,  # What user will pay for full validation
                        "preview_tokens": total_tokens,
                        "estimated_total_tokens": estimated_total_tokens,
                        "per_row_cost": per_row_cost,
                        "per_row_tokens": per_row_tokens,
                        "per_row_time": time_per_row
                    },
                    "token_usage": token_usage,
                    "validation_metrics": validation_metrics,
                    "account_info": {
                        "current_balance": float(current_balance) if current_balance else 0,
                        "sufficient_balance": float(current_balance) >= quoted_full_cost if current_balance else False,
                        "quoted_full_cost": quoted_full_cost,  # What user will be charged for full validation
                        "credits_needed": max(0, quoted_full_cost - (float(current_balance) if current_balance else 0)),
                        "domain_multiplier": float(multiplier),
                        "email_domain": email_domain
                    }
                }
                
                # Update DynamoDB with the complete preview payload
                update_run_status(
                    session_id=session_id, status='COMPLETED',
                    verbose_status="Preview complete. Results available.",
                    percent_complete=100,
                    processed_rows=len(validation_results['validation_results']),
                    preview_data=preview_payload
                )
                
                # Track enhanced user metrics for preview
                track_user_request(
                    email=email,
                    request_type='preview',
                    tokens_used=total_tokens,
                    cost_usd=charged_cost,  # Legacy field
                    perplexity_tokens=token_usage.get('by_provider', {}).get('perplexity', {}).get('total_tokens', 0),
                    perplexity_cost=token_usage.get('by_provider', {}).get('perplexity', {}).get('total_cost', 0),
                    anthropic_tokens=token_usage.get('by_provider', {}).get('anthropic', {}).get('total_tokens', 0),
                    anthropic_cost=token_usage.get('by_provider', {}).get('anthropic', {}).get('total_cost', 0),
                    # Enhanced metrics
                    rows_processed=total_rows_processed,
                    total_rows=validation_results.get('total_rows', 0),
                    columns_validated=validation_metrics.get('validated_columns_count', 0),
                    search_groups=validation_metrics.get('search_groups_count', 0),
                    high_context_search_groups=validation_metrics.get('high_context_search_groups_count', 0),
                    claude_calls=validation_metrics.get('claude_search_groups_count', 0),
                    eliyahu_cost=eliyahu_cost,
                    estimated_cost=estimated_cost,
                    quoted_full_cost=quoted_full_cost,  # This is the scaled full table quote
                    charged_cost=0.0,  # Preview doesn't charge
                    total_api_calls=total_api_calls,
                    total_cached_calls=total_cached_calls
                )
                
                # Send WebSocket notification with preview results
                from dynamodb_schemas import get_connection_by_session, remove_websocket_connection
                logger.info(f"Looking up WebSocket connection for session {session_id}")
                connection_id = get_connection_by_session(session_id)
                logger.info(f"Found WebSocket connection_id: {connection_id}")
                
                if connection_id:
                    try:
                        client = _get_api_gateway_management_client(context)
                        logger.info(f"API Gateway management client initialized: {client is not None}")
                        
                        if client:
                            websocket_payload = {
                                'status': 'COMPLETED',
                                'percent_complete': 100,
                                'verbose_status': 'Preview complete. Results available.',
                                'preview_data': preview_payload
                            }
                            logger.info(f"Sending WebSocket payload to connection {connection_id}: {len(json.dumps(websocket_payload))} bytes")
                            
                            client.post_to_connection(
                                ConnectionId=connection_id,
                                Data=json.dumps(websocket_payload).encode('utf-8')
                            )
                            logger.debug(f"Successfully sent preview completion notification to WebSocket {connection_id}")
                        else:
                            logger.error("API Gateway management client is None - cannot send WebSocket message")
                    except client.exceptions.GoneException:
                        logger.warning(f"WebSocket connection {connection_id} is stale. Removing from DB.")
                        remove_websocket_connection(connection_id)
                    except Exception as e:
                        logger.error(f"❌ Failed to post preview completion to WebSocket {connection_id}: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                else:
                    logger.warning(f"No WebSocket connection found for session {session_id} - cannot send notification")
                
                # Send preview email if requested
                logger.info(f"Preview email check: preview_email={preview_email}, EMAIL_SENDER_AVAILABLE={EMAIL_SENDER_AVAILABLE}, email_address={email_address}")
                if preview_email and EMAIL_SENDER_AVAILABLE and email_address:
                    # Send email preparation progress update
                    _send_websocket_message_deduplicated(session_id, {
                        'type': 'preview_progress',
                        'progress': 85,
                        'status': '📧 Preparing enhanced Excel email...',
                        'session_id': session_id
                    }, "preview_progress_email_prep")
                    
                    logger.info(f"Sending preview email for session {session_id}")
                    try:
                        # Get excel content and config for email
                        from ..core.unified_s3_manager import UnifiedS3Manager
                        storage_manager = UnifiedS3Manager()
                        excel_content, excel_s3_key = storage_manager.get_excel_file(email, clean_session_id)
                        config_data, config_s3_key = storage_manager.get_latest_config(email, clean_session_id)
                        
                        if excel_content and config_data:
                            input_filename = excel_s3_key.split('/')[-1]
                            
                            # Try to get the config lambda filename from metadata, fallback to S3 key
                            config_filename = config_s3_key.split('/')[-1] if config_s3_key else 'config.json'
                            if 'generation_metadata' in config_data:
                                # First try config_lambda_filename (set by interface lambda)
                                if 'config_lambda_filename' in config_data['generation_metadata']:
                                    config_filename = config_data['generation_metadata']['config_lambda_filename']
                                    logger.info(f"Using config lambda filename from metadata for preview: {config_filename}")
                                # Then try saved_filename (set by config lambda)
                                elif 'saved_filename' in config_data['generation_metadata']:
                                    config_filename = config_data['generation_metadata']['saved_filename']
                                    logger.info(f"Using saved filename from metadata for preview: {config_filename}")
                            
                            # Calculate summary data for the email
                            all_fields = set()
                            confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
                            for row_data in real_results.values():
                                for field_name, field_data in row_data.items():
                                    if isinstance(field_data, dict) and 'confidence_level' in field_data:
                                        all_fields.add(field_name)
                                        conf_level = field_data.get('confidence_level', 'UNKNOWN')
                                        if conf_level in confidence_counts:
                                            confidence_counts[conf_level] += 1
                            
                            summary_data = {
                                'total_rows': len(real_results),
                                'fields_validated': list(all_fields),
                                'confidence_distribution': confidence_counts
                            }
                            
                            # Create enhanced Excel if available
                            enhanced_excel_content = None
                            if EXCEL_ENHANCEMENT_AVAILABLE:
                                try:
                                    # Use shared_table_parser to get structured data
                                    from shared_table_parser import S3TableParser
                                    table_parser = S3TableParser()
                                    table_data = table_parser.parse_s3_table(S3_UNIFIED_BUCKET, excel_s3_key)
                                    
                                    validated_sheet = table_data.get('metadata', {}).get('sheet_name')
                                    excel_buffer = create_enhanced_excel_with_validation(
                                        table_data, real_results, config_data, session_id, validated_sheet_name=validated_sheet
                                    )
                                    if excel_buffer:
                                        enhanced_excel_content = excel_buffer.getvalue()
                                except Exception as e:
                                    logger.error(f"Error creating enhanced Excel for preview: {str(e)}")
                            
                            # Send the email
                            logger.info(f"Calling send_validation_results_email with: email_address={email_address}, "
                                      f"excel_content_len={len(excel_content) if excel_content else 0}, "
                                      f"config_content_len={len(json.dumps(config_data, indent=2).encode('utf-8'))}, "
                                      f"enhanced_excel_content_len={len(enhanced_excel_content) if enhanced_excel_content else 0}, "
                                      f"input_filename={input_filename}, config_filename={config_filename}, "
                                      f"session_id={session_id}, reference_pin={reference_pin}, preview_email=True")
                            
                            email_result = send_validation_results_email(
                                email_address=email_address, 
                                excel_content=excel_content, 
                                config_content=json.dumps(config_data, indent=2).encode('utf-8'),
                                enhanced_excel_content=enhanced_excel_content,
                                input_filename=input_filename, 
                                config_filename=config_filename,
                                enhanced_excel_filename=f"{os.path.splitext(input_filename)[0]}_Preview_Validated.xlsx",
                                session_id=session_id, 
                                summary_data=summary_data, 
                                processing_time=processing_time,
                                reference_pin=reference_pin, 
                                metadata=metadata, 
                                preview_email=True,
                                billing_info=None  # No charges for previews
                            )
                            
                            logger.info(f"Email result received: {email_result}")
                            
                            # Send email completion progress update
                            if email_result.get('success', False):
                                _send_websocket_message_deduplicated(session_id, {
                                    'type': 'preview_progress',
                                    'progress': 95,
                                    'status': '✅ Preview email sent successfully!',
                                    'session_id': session_id
                                }, "preview_progress_email_sent")
                            else:
                                _send_websocket_message_deduplicated(session_id, {
                                    'type': 'preview_progress',
                                    'progress': 95,
                                    'status': '⚠️ Preview completed (email may have failed)',
                                    'session_id': session_id
                                }, "preview_progress_email_failed")
                            
                            logger.info(f"Preview email sent: {email_result.get('success', False)}")
                        else:
                            logger.error("Could not retrieve files for preview email")
                    except Exception as e:
                        logger.error(f"Error sending preview email: {str(e)}")
                        import traceback
                        logger.error(f"Preview email error traceback: {traceback.format_exc()}")
                        # Log the email_result if available
                        if 'email_result' in locals():
                            logger.error(f"Email result details: {email_result}")
                
                # Store preview results in versioned results folder using unified storage
                config_version = 1
                try:
                    existing_config, latest_config_key = storage_manager.get_latest_config(email, clean_session_id)
                    if existing_config and existing_config.get('storage_metadata', {}).get('version'):
                        config_version = existing_config['storage_metadata']['version']
                except Exception as e:
                    logger.warning(f"Could not determine config version for preview: {e}")
                
                # Send final storage progress update
                _send_websocket_message_deduplicated(session_id, {
                    'type': 'preview_progress',
                    'progress': 98,
                    'status': '💾 Storing preview results...',
                    'session_id': session_id
                }, "preview_progress_storage")
                
                # Update session info with account data for preview
                account_info = {
                    'initial_balance': float(initial_balance) if initial_balance else 0,
                    'final_balance': float(final_balance) if final_balance else 0,
                    'amount_charged': 0,  # Previews are free
                    'domain_multiplier': float(multiplier),
                    'eliyahu_cost': float(eliyahu_cost),  # Your actual expense
                    'estimated_cost': float(estimated_cost),  # What it would cost without caching
                    'preview_abandoned': False,  # Completed successfully
                    'insufficient_balance_encountered': False,  # Previews don't charge
                    'processing_type': 'preview'
                }
                _update_session_info_with_account_data(email, clean_session_id, account_info)
                
                # Store preview results in unified storage
                result = storage_manager.store_results(
                    email, clean_session_id, config_version, preview_payload, 'preview'
                )
                
                if result['success']:
                    logger.info(f"Preview results stored in versioned folder: {result['s3_key']}")
                else:
                    logger.error(f"Failed to store preview results: {result.get('error')}")
                
                # Send final completion progress update
                _send_websocket_message_deduplicated(session_id, {
                    'type': 'preview_progress',
                    'progress': 100,
                    'status': '🎉 Preview completed successfully!',
                    'session_id': session_id
                }, "preview_progress_final")

                # No longer need to save a separate S3 object for previews
            else:
                # Send failure progress update
                _send_websocket_message_deduplicated(session_id, {
                    'type': 'preview_failed',
                    'progress': 100,
                    'status': '❌ Preview failed to generate results',
                    'session_id': session_id,
                    'error': 'No validation results returned'
                }, "preview_failed_no_results")
                
                # Update session info for failed preview
                try:
                    from dynamodb_schemas import check_user_balance, get_domain_multiplier
                    initial_balance = check_user_balance(email)
                    email_domain = email.split('@')[-1] if '@' in email else 'unknown'
                    multiplier = float(get_domain_multiplier(email_domain))
                    
                    account_info = {
                        'initial_balance': float(initial_balance) if initial_balance else 0,
                        'final_balance': float(initial_balance) if initial_balance else 0,
                        'amount_charged': 0,  # Previews are free
                        'domain_multiplier': float(multiplier),
                        'raw_cost': 0,  # No processing happened
                        'preview_abandoned': True,  # Failed to complete
                        'insufficient_balance_encountered': False,  # Previews don't charge
                        'processing_type': 'preview_failed'
                    }
                    _update_session_info_with_account_data(email, clean_session_id, account_info)
                except Exception as e:
                    logger.error(f"Failed to update session info for failed preview: {e}")
                
                update_run_status(
                    session_id=session_id, status='FAILED',
                    verbose_status="Preview failed to generate results.",
                    percent_complete=100
                )
            
            # Return early for preview mode to prevent fallthrough to normal processing
            return {'statusCode': 200, 'body': json.dumps({'status': 'preview_completed', 'session_id': session_id})}

        else:
            # Normal mode processing
            results_key = event['results_key']
            logger.info(f"Background normal processing for session {session_id}")
            
            # Use unified storage to get Excel and config files
            from ..core.unified_s3_manager import UnifiedS3Manager
            storage_manager = UnifiedS3Manager()
            
            # Get files from unified storage using clean session ID
            excel_content, actual_excel_s3_key = storage_manager.get_excel_file(email, clean_session_id)
            config_data, actual_config_s3_key = storage_manager.get_latest_config(email, clean_session_id)
            
            if not excel_content:
                logger.error(f"Failed to retrieve Excel file from unified storage for session {clean_session_id}")
                raise Exception(f"Excel file not found in unified storage for session {clean_session_id}")
            
            if not config_data:
                logger.error(f"Failed to retrieve config file from unified storage for session {clean_session_id}")
                raise Exception(f"Config file not found in unified storage for session {clean_session_id}")
            
            logger.info(f"Retrieved files from unified storage - Excel: {actual_excel_s3_key}, Config: {actual_config_s3_key}")
            
            # Use shared table parser to get row count (handles both CSV and Excel)
            from shared_table_parser import S3TableParser
            table_parser = S3TableParser()
            
            # Parse table to get structure and row count
            table_data = table_parser.parse_s3_table(storage_manager.bucket_name, actual_excel_s3_key)
            total_rows_in_file = len(table_data.get('rows', []))
            rows_to_process = min(max_rows, total_rows_in_file) if max_rows else total_rows_in_file

            # The actual batching loop
            all_validation_results = {}
            processed_rows_count = 0
            total_batches = (rows_to_process + batch_size - 1) // batch_size
            
            update_run_status(session_id=session_id, status='PROCESSING', verbose_status=f"Preparing to process {rows_to_process} rows in {total_batches} batches.")

            # We need the full rows data to iterate through, not just invoke the lambda
            # This is a conceptual simplification. The real invoker already does this.
            # We will simulate the batch processing here for the sake of status updates.
            
            for i in range(total_batches):
                start_row = i * batch_size
                end_row = min(start_row + batch_size, rows_to_process)
                
                # In a real scenario, you'd slice the data and send only the batch
                # Here, we'll just simulate the progress update
                
                # SIMULATE a call to a batch processor
                time.sleep(1) # Simulate work
                
                processed_rows_count = end_row
                percent_complete = int((processed_rows_count / rows_to_process) * 100)
                verbose_status = f"Processing batch {i + 1} of {total_batches} ({processed_rows_count}/{rows_to_process} rows)..."
                
                update_run_status(
                    session_id=session_id, 
                    status='PROCESSING',
                    processed_rows=processed_rows_count,
                    percent_complete=percent_complete,
                    verbose_status=verbose_status
                )
            
            # After the loop, we would have the final results.
            # For now, we will call the original invoker to get the final result in one go,
            # as refactoring it to return per-batch results is a larger change.
            validation_results = invoke_validator_lambda(
                excel_s3_key, config_s3_key, max_rows, batch_size, S3_UNIFIED_BUCKET, VALIDATOR_LAMBDA_NAME,
                preview_first_row=False,
                session_id=session_id,
                update_callback=_update_progress
            )
        
        # After invoke_validator_lambda returns
        if validation_results:
            processed_rows_count = len(validation_results.get('validation_results', {}))
            update_run_status(session_id=session_id, status='PROCESSING', processed_rows=processed_rows_count)

        has_results = (validation_results and 
                      'validation_results' in validation_results and 
                      validation_results['validation_results'] is not None)
        
        if has_results:
            real_results = validation_results['validation_results']
            total_rows = validation_results.get('total_rows', 1)
            metadata = validation_results.get('metadata', {})
            token_usage = metadata.get('token_usage', {})
            validation_metrics = metadata.get('validation_metrics', {})
            
            # Apply domain multiplier to raw costs and handle billing
            try:
                import sys
                import os
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
                from dynamodb_schemas import get_domain_multiplier, track_api_usage_detailed, deduct_from_balance, check_user_balance
                from decimal import Decimal
                
                email_domain = email.split('@')[-1] if '@' in email else 'unknown'
                multiplier = float(get_domain_multiplier(email_domain))
                
                # Get both costs from validation lambda
                eliyahu_cost = token_usage.get('total_cost', 0.0)  # What we actually paid for full validation
                estimated_cost = token_usage.get('estimated_total_cost', eliyahu_cost)  # What this full validation would cost without caching
                logger.debug(f"BILLING DEBUG: Raw costs from validation - eliyahu_cost={eliyahu_cost}, estimated_cost={estimated_cost}")
                
                # For full validation, use the quoted_full_cost from preview (what user was promised to pay)
                # This ensures users pay exactly what was quoted in preview, regardless of actual full validation costs
                charged_cost = estimated_cost * multiplier  # Fallback if preview cost not found
                logger.debug(f"BILLING DEBUG: Calculated fallback charged_cost = {estimated_cost} * {multiplier} = {charged_cost}")
                
                try:
                    # Try to get the quoted cost from preview results stored in S3
                    # Try multiple config versions since preview and full validation might use different versions
                    session_path = storage_manager.get_session_path(email, clean_session_id)
                    logger.debug(f"BILLING DEBUG: Using email='{email}', clean_session_id='{clean_session_id}' for preview lookup")
                    
                    preview_data = None
                    preview_results_key = None
                    
                    # Try to find the latest config version first
                    latest_version = 1
                    try:
                        existing_config, latest_config_key = storage_manager.get_latest_config(email, clean_session_id)
                        if existing_config and existing_config.get('storage_metadata', {}).get('version'):
                            latest_version = existing_config['storage_metadata']['version']
                            logger.debug(f"BILLING DEBUG: Found latest config version: {latest_version}")
                    except Exception as e:
                        logger.warning(f"Could not determine latest config version: {e}")
                    
                    # Try versions from latest down to v1
                    for version in range(latest_version, 0, -1):
                        preview_results_key = f"{session_path}v{version}_results/preview_results.json"
                        logger.debug(f"BILLING DEBUG: Trying preview results at s3://{storage_manager.bucket_name}/{preview_results_key}")
                        
                        try:
                            response = storage_manager.s3_client.get_object(
                                Bucket=storage_manager.bucket_name,
                                Key=preview_results_key
                            )
                            preview_data = json.loads(response['Body'].read().decode('utf-8'))
                            logger.debug(f"BILLING DEBUG: Found preview results at version {version}")
                            break
                        except storage_manager.s3_client.exceptions.NoSuchKey:
                            logger.debug(f"BILLING DEBUG: No preview results found at version {version}")
                            continue
                    
                    if not preview_data:
                        raise Exception("No preview results found in any config version")
                    
                    preview_quoted_cost = preview_data.get('account_info', {}).get('quoted_full_cost')
                    if preview_quoted_cost:
                        charged_cost = float(preview_quoted_cost)
                        logger.info(f"Using preview quoted cost for full validation: ${charged_cost:.6f}")
                    else:
                        logger.warning("Preview quoted cost not found in results, using calculated cost")
                        
                except Exception as e:
                    logger.warning(f"Failed to retrieve preview quoted cost: {e}, using calculated cost")
                
                logger.info(f"Full validation costs - Eliyahu: ${eliyahu_cost:.6f}, Estimated: ${estimated_cost:.6f}, Multiplier: {multiplier}x, User Charged: ${charged_cost:.6f}")
                logger.info(f"BILLING DEBUG: is_preview={is_preview}, charged_cost={charged_cost}, session_id={session_id}")
                
                # For full validation, deduct from account balance
                initial_balance = check_user_balance(email)
                final_balance = initial_balance
                balance_error_occurred = False
                charged_amount = 0
                
                if not is_preview and charged_cost > 0:
                    logger.info(f"BILLING: Proceeding with charge for {email}: ${charged_cost}")
                    # Check if user has sufficient balance
                    current_balance = check_user_balance(email)
                    if current_balance is not None and current_balance >= Decimal(str(charged_cost)):
                        # Deduct from balance
                        deduct_success = deduct_from_balance(
                            email=email,
                            amount=Decimal(str(charged_cost)),
                            session_id=session_id,
                            description=f"Full validation - {len(real_results)} rows processed",
                            raw_cost=Decimal(str(eliyahu_cost)),
                            multiplier=Decimal(str(multiplier))
                        )
                        if deduct_success:
                            final_balance = check_user_balance(email)
                            charged_amount = charged_cost
                            # Send balance update via WebSocket
                            _send_balance_update(session_id, {
                                'type': 'balance_update',
                                'new_balance': float(final_balance) if final_balance else 0,
                                'transaction': {
                                    'amount': -float(charged_cost),
                                    'description': f"Full validation - {len(real_results)} rows processed",
                                    'eliyahu_cost': float(eliyahu_cost),
                                    'multiplier': float(multiplier)
                                }
                            })
                        else:
                            logger.error(f"Failed to deduct ${charged_cost:.6f} from {email} balance")
                            balance_error_occurred = True
                    else:
                        logger.warning(f"Insufficient balance for {email}: {current_balance} < ${charged_cost:.6f}")
                        balance_error_occurred = True
                else:
                    logger.warning(f"BILLING: Skipping charge - is_preview={is_preview}, charged_cost={charged_cost}")
                
                # Track detailed API usage for each provider
                by_provider = token_usage.get('by_provider', {})
                for provider, provider_usage in by_provider.items():
                    if provider_usage and isinstance(provider_usage, dict):
                        usage_data = {
                            'api_calls': provider_usage.get('api_calls', 0),
                            'cached_calls': provider_usage.get('cached_calls', 0),
                            'total_tokens': provider_usage.get('total_tokens', 0),
                            'cost': provider_usage.get('total_cost', 0.0) * multiplier,  # Apply multiplier
                            'eliyahu_cost': provider_usage.get('total_cost', 0.0),  # Store eliyahu cost too
                            'multiplier_applied': multiplier
                        }
                        
                        # Add provider-specific token fields
                        if provider == 'perplexity':
                            usage_data.update({
                                'prompt_tokens': provider_usage.get('prompt_tokens', 0),
                                'completion_tokens': provider_usage.get('completion_tokens', 0)
                            })
                        elif provider == 'anthropic':
                            usage_data.update({
                                'input_tokens': provider_usage.get('input_tokens', 0),
                                'output_tokens': provider_usage.get('output_tokens', 0),
                                'cache_tokens': provider_usage.get('cache_tokens', 0)
                            })
                        
                        # Track detailed usage for this provider
                        
                
            except Exception as e:
                logger.error(f"Error applying domain multiplier in full validation: {e}")
                multiplier = 1.0
                charged_cost = eliyahu_cost
            
            if is_preview:
                logger.info(f"Got preview validation results for {session_id}, storing for polling.")
                
                # Extract metrics for this section  
                total_cost = charged_cost  # Use charged cost for display
                total_tokens = token_usage.get('total_tokens', 0)
                total_rows_processed = validation_results.get('total_processed_rows', len(real_results))
                
                # Create the markdown table for the response
                markdown_table = create_markdown_table_from_results(real_results, 3, actual_config_s3_key, S3_UNIFIED_BUCKET)
                
                # --- Start of Complex Estimations Logic ---
                
                # Use batch timing info from the validator if available, otherwise fallback
                batch_timing = metadata.get('batch_timing', {})
                validator_processing_time = metadata.get('processing_time', 0.0)
                processing_time = 0.0
                time_per_batch = 20.0 # Default fallback
                time_per_row = 4.0 # Default fallback

                if batch_timing:
                    processing_time = batch_timing.get('total_batch_time_seconds', 0.0)
                    time_per_batch = batch_timing.get('average_batch_time_seconds', time_per_batch)
                    time_per_row = batch_timing.get('average_time_per_row_seconds', time_per_row)
                elif validator_processing_time > 0:
                    processing_time = validator_processing_time
                    if total_rows_processed > 0:
                        time_per_row = processing_time / total_rows_processed
                        time_per_batch = time_per_row * 5 # Assuming 5 rows per batch for estimation
                
                # Use already calculated projection values from earlier (lines 383-394)
                # Scaling logic: (preview_run_estimated_cost * multiplier) / preview_rows * total_rows
                # Variables available: quoted_full_cost, estimated_total_tokens, estimated_total_time_seconds,
                # per_row_cost, per_row_tokens - all correctly scaled from preview run to full table quote
                
                # --- End of Complex Estimations Logic ---

                preview_payload = {
                    "status": "preview_completed",
                    "session_id": session_id,
                    "reference_pin": reference_pin,
                    "markdown_table": markdown_table,
                    "total_rows": total_rows,
                    "total_processed_rows": total_rows_processed,
                    "preview_processing_time": processing_time,
                    "estimated_total_processing_time": estimated_total_time_seconds,
                    "estimated_total_time_minutes": round(estimated_total_time_seconds / 60, 1),
                    "cost_estimates": {
                        "preview_cost": charged_cost,  # What user pays for preview (0)
                        "quoted_full_cost": quoted_full_cost,  # What user will pay for full validation
                        "preview_tokens": total_tokens,
                        "estimated_total_tokens": estimated_total_tokens,
                        "per_row_cost": per_row_cost,
                        "per_row_tokens": per_row_tokens,
                        "per_row_time": time_per_row
                    },
                    "token_usage": token_usage,
                    "validation_metrics": validation_metrics
                }


            else: # Full processing
                logger.info(f"Got full validation results for {session_id}, creating enhanced ZIP.")
                excel_response = s3_client.get_object(Bucket=storage_manager.bucket_name, Key=excel_s3_key)
                excel_content = excel_response['Body'].read()
                config_response = s3_client.get_object(Bucket=storage_manager.bucket_name, Key=config_s3_key)
                config_data = json.loads(config_response['Body'].read().decode('utf-8'))
                
                input_filename = excel_s3_key.split('/')[-1]
                
                # Try to get the config lambda filename from metadata, fallback to S3 key
                config_filename = config_s3_key.split('/')[-1]
                if 'generation_metadata' in config_data:
                    # First try config_lambda_filename (set by interface lambda)
                    if 'config_lambda_filename' in config_data['generation_metadata']:
                        config_filename = config_data['generation_metadata']['config_lambda_filename']
                        logger.info(f"Using config lambda filename from metadata: {config_filename}")
                    # Then try saved_filename (set by config lambda)
                    elif 'saved_filename' in config_data['generation_metadata']:
                        config_filename = config_data['generation_metadata']['saved_filename']
                        logger.info(f"Using saved filename from metadata: {config_filename}")

                # Get structured table data for enhanced Excel creation
                try:
                    from shared_table_parser import S3TableParser
                    table_parser = S3TableParser()
                    table_data = table_parser.parse_s3_table(storage_manager.bucket_name, excel_s3_key)
                    logger.info(f"Parsed table data for ZIP creation: {type(table_data)}")
                except Exception as e:
                    logger.error(f"Failed to parse table data for ZIP: {e}")
                    table_data = None

                enhanced_zip = create_enhanced_result_zip(
                    real_results, session_id, total_rows, excel_content, config_data,
                    reference_pin, input_filename, config_filename, metadata,
                    structured_excel_data=table_data
                )

                s3_client.put_object(Bucket=S3_RESULTS_BUCKET, Key=results_key, Body=enhanced_zip, ContentType='application/zip')
                logger.info(f"Enhanced results for {session_id} uploaded to {results_key}")
                
                # Determine config version for versioned storage
                config_version = 1
                try:
                    _, latest_config_key = storage_manager.get_latest_config(email, clean_session_id)
                    if latest_config_key:
                        config_filename = latest_config_key.split('/')[-1]
                        if config_filename.startswith('config_v') and '_' in config_filename:
                            version_part = config_filename.split('_')[1]  # config_v{N}_{source}.json
                            if version_part.startswith('v'):
                                config_version = int(version_part[1:])
                except Exception as e:
                    logger.warning(f"Could not determine config version for full results: {e}")
                
                # Store validation results in versioned folder
                validation_data = {
                    'validation_results': real_results,
                    'total_rows': total_rows,
                    'metadata': metadata,
                    'session_id': session_id,
                    'reference_pin': reference_pin
                }
                
                result = storage_manager.store_results(
                    email, clean_session_id, config_version, validation_data, 'validation'
                )
                
                # Update session info with account data for full validation
                account_info = {
                    'initial_balance': float(initial_balance) if initial_balance else 0,
                    'final_balance': float(final_balance) if final_balance else 0,
                    'amount_charged': float(charged_amount),
                    'domain_multiplier': float(multiplier),
                    'eliyahu_cost': float(eliyahu_cost),
                    'preview_abandoned': False,  # This is full validation
                    'insufficient_balance_encountered': balance_error_occurred,
                    'processing_type': 'full_validation'
                }
                _update_session_info_with_account_data(email, clean_session_id, account_info)
                
                if result['success']:
                    logger.info(f"Full validation results stored in versioned folder: {result['s3_key']}")
                else:
                    logger.error(f"Failed to store full validation results: {result.get('error')}")
                
                # Extract and store enhanced files from ZIP
                try:
                    import zipfile
                    import io
                    
                    enhanced_excel_content = None
                    summary_text = None
                    
                    with zipfile.ZipFile(io.BytesIO(enhanced_zip), 'r') as zip_file:
                        # Extract enhanced Excel
                        if 'validation_results_enhanced.xlsx' in zip_file.namelist():
                            enhanced_excel_content = zip_file.read('validation_results_enhanced.xlsx')
                            logger.info("Extracted enhanced Excel from ZIP")
                        
                        # Extract summary text
                        if 'SUMMARY.txt' in zip_file.namelist():
                            summary_text = zip_file.read('SUMMARY.txt').decode('utf-8')
                            logger.info("Extracted summary text from ZIP")
                    
                    # Store enhanced files in versioned folder
                    if enhanced_excel_content or summary_text:
                        enhanced_result = storage_manager.store_enhanced_files(
                            email, clean_session_id, config_version, 
                            enhanced_excel_content, summary_text
                        )
                        
                        if enhanced_result['success']:
                            logger.info(f"Stored enhanced files: {enhanced_result['stored_files']}")
                        else:
                            logger.error(f"Failed to store enhanced files: {enhanced_result.get('error')}")
                
                except Exception as e:
                    logger.error(f"Failed to extract enhanced files from ZIP: {e}")

                if EMAIL_SENDER_AVAILABLE and email_address:
                    # Calculate summary data for the email
                    all_fields = set()
                    confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
                    for row_data in real_results.values():
                        for field_name, field_data in row_data.items():
                            if isinstance(field_data, dict) and 'confidence_level' in field_data:
                                all_fields.add(field_name)
                                conf_level = field_data.get('confidence_level', 'UNKNOWN')
                                if conf_level in confidence_counts:
                                    confidence_counts[conf_level] += 1
                    
                    summary_data = {
                        'total_rows': len(real_results),
                        'fields_validated': list(all_fields),
                        'confidence_distribution': confidence_counts
                    }
                    
                    enhanced_excel_content = None
                    if EXCEL_ENHANCEMENT_AVAILABLE:
                        try:
                            # Use shared_table_parser to get structured data instead of raw bytes
                            from shared_table_parser import S3TableParser
                            table_parser = S3TableParser()
                            logger.info(f"Parsing S3 table: {S3_UNIFIED_BUCKET}/{excel_s3_key}")
                            table_data = table_parser.parse_s3_table(S3_UNIFIED_BUCKET, excel_s3_key)
                            logger.info(f"Table parser returned data type: {type(table_data)}")
                            if isinstance(table_data, dict):
                                logger.info(f"Table data keys: {list(table_data.keys())}")
                            else:
                                logger.warning(f"Table parser returned non-dict: {table_data}")
                            
                            # Pass structured data instead of raw file bytes
                            # Extract sheet name from table data metadata for consistency
                            validated_sheet = table_data.get('metadata', {}).get('sheet_name')
                            logger.info(f"Extracted validated sheet name from metadata: '{validated_sheet}'")
                            logger.info(f"Table data metadata: {table_data.get('metadata', {})}")
                            
                            excel_buffer = create_enhanced_excel_with_validation(
                                table_data, real_results, config_data, session_id, validated_sheet_name=validated_sheet
                            )
                            if excel_buffer:
                                enhanced_excel_content = excel_buffer.getvalue()
                        except Exception as e:
                            logger.error(f"Error creating enhanced Excel: {str(e)}")
                            enhanced_excel_content = None
                    
                    # Ensure enhanced_excel_content is bytes or None (not other types)
                    safe_enhanced_excel_content = enhanced_excel_content if isinstance(enhanced_excel_content, (bytes, type(None))) else None
                    
                    # Prepare billing information for receipt
                    billing_info = {
                        'amount_charged': charged_amount,
                        'eliyahu_cost': eliyahu_cost,
                        'multiplier': multiplier,
                        'initial_balance': float(initial_balance) if initial_balance else 0,
                        'final_balance': float(final_balance) if final_balance else 0
                    }
                    
                    email_result = send_validation_results_email(
                        email_address=email_address, excel_content=excel_content, 
                        config_content=json.dumps(config_data, indent=2).encode('utf-8'),
                        enhanced_excel_content=safe_enhanced_excel_content,
                        input_filename=input_filename, config_filename=config_filename,
                        enhanced_excel_filename=f"{os.path.splitext(input_filename)[0]}_Validated.xlsx",
                        session_id=session_id, summary_data=summary_data, 
                        processing_time=metadata.get('processing_time',0),
                        reference_pin=reference_pin, metadata=metadata, preview_email=preview_email,
                        billing_info=billing_info
                    )
                    # Send final completion notification with processed row count and total rows
                    processed_rows_count = len(validation_results.get('validation_results', {}))
                    total_rows_in_file = validation_results.get('total_rows', processed_rows_count)
                    _update_progress(session_id, 'COMPLETED', processed_rows_count, 'Validation complete. Results should be in your inbox shortly.', 100, total_rows_in_file)
                    update_run_status(session_id=session_id, status='COMPLETED', results_s3_key=results_key)
                    
                    # Track enhanced user metrics for full validation
                    track_user_request(
                        email=email,
                        request_type='full',
                        tokens_used=token_usage.get('total_tokens', 0),
                        cost_usd=charged_cost,  # Legacy field
                        perplexity_tokens=token_usage.get('by_provider', {}).get('perplexity', {}).get('total_tokens', 0),
                        perplexity_cost=token_usage.get('by_provider', {}).get('perplexity', {}).get('total_cost', 0),
                        anthropic_tokens=token_usage.get('by_provider', {}).get('anthropic', {}).get('total_tokens', 0),
                        anthropic_cost=token_usage.get('by_provider', {}).get('anthropic', {}).get('total_cost', 0),
                        # Enhanced metrics
                        rows_processed=processed_rows_count,
                        total_rows=total_rows_in_file,
                        columns_validated=validation_metrics.get('validated_columns_count', 0),
                        search_groups=validation_metrics.get('search_groups_count', 0),
                        high_context_search_groups=validation_metrics.get('high_context_search_groups_count', 0),
                        claude_calls=validation_metrics.get('claude_search_groups_count', 0),
                        eliyahu_cost=eliyahu_cost,
                        estimated_cost=estimated_cost,
                        quoted_full_cost=charged_cost,  # This is the quoted cost from preview (what we're charging)
                        charged_cost=charged_cost,  # Full validation charges user the preview quoted cost
                        total_api_calls=token_usage.get('api_calls', 0),
                        total_cached_calls=token_usage.get('cached_calls', 0)
                    )
        
        else: # No results
             logger.warning(f"No validation results returned from validator for session {session_id}")
             update_run_status(session_id=session_id, status='FAILED', error_message="No validation results returned", verbose_status="Failed to process results.", percent_complete=100)
             # Handle empty results case for preview if needed
             if is_preview:
                # Even for empty results, store in versioned folder
                config_version = 1
                try:
                    _, latest_config_key = storage_manager.get_latest_config(email, clean_session_id)
                    if latest_config_key:
                        config_filename = latest_config_key.split('/')[-1]
                        if config_filename.startswith('v') and '_' in config_filename:
                            config_version = int(config_filename.split('_')[0][1:])
                except:
                    pass
                
                result = storage_manager.store_results(
                    email, clean_session_id, config_version, 
                    {"status": "preview_completed", "note": "No results"}, 'preview'
                )
                
                if result['success']:
                    preview_results_key = result['s3_key']
                else:
                    # Fallback
                    preview_results_key = f"preview_results/{email_folder}/{session_id}.json"
                    s3_client.put_object(
                        Bucket=S3_RESULTS_BUCKET, Key=preview_results_key,
                        Body=json.dumps({"status": "preview_completed", "note": "No results"}),
                        ContentType='application/json'
                    )
            
        return {'statusCode': 200, 'body': json.dumps({'status': 'background_completed', 'session_id': session_id})}

    except Exception as e:
        logger.error(f"Critical error in background processing for session {event.get('session_id', 'unknown')}: {str(e)}")
        import traceback
        traceback.print_exc()
        if DYNAMODB_AVAILABLE:
            update_run_status(session_id=event.get('session_id'), status='FAILED', error_message=str(e))
        return {'statusCode': 500, 'body': json.dumps({'status': 'background_failed', 'error': str(e)})}

def handle_config_generation(event, context):
    """Handle config generation requests by forwarding to config lambda."""
    try:
        import time
        execution_id = f"{context.aws_request_id if context else 'no-context'}_{int(time.time() * 1000)}"
        logger.info(f"[CONFIG_GEN_START] {execution_id} - Handling config generation request for session {event.get('session_id')}")
        session_id = event.get('session_id')
        
        # Send initial progress update
        _send_websocket_message_deduplicated(session_id, {
            'type': 'config_generation_progress',
            'progress': 5,
            'status': '🚀 Starting AI configuration generation...',
            'session_id': session_id
        }, "config_progress_start")
        
        # Send analysis progress update
        _send_websocket_message_deduplicated(session_id, {
            'type': 'config_generation_progress', 
            'progress': 15,
            'status': '🔍 Analyzing table structure and data patterns...',
            'session_id': session_id
        }, "config_progress_analysis")
        
        # Invoke the config lambda directly
        _send_websocket_message_deduplicated(session_id, {
            'type': 'config_generation_progress',
            'progress': 30,
            'status': '🤖 Developing configuration with AI...',
            'session_id': session_id
        }, "config_progress_ai_invoke")
        
        response = invoke_config_lambda(event)
        
        logger.info(f"Config generation response: {response}")
        logger.info(f"Response keys: {list(response.keys()) if isinstance(response, dict) else 'Not a dict'}")
        
        # Send AI processing completion update
        _send_websocket_message_deduplicated(session_id, {
            'type': 'config_generation_progress',
            'progress': 70,
            'status': '✨ AI configuration generated successfully!',
            'session_id': session_id
        }, "config_progress_ai_complete")
        
        if response.get('success'):
            # Get the S3 key and create download URL
            config_s3_key = response.get('config_s3_key') or response.get('generated_config_s3_key')
            # Config lambda returns 'ai_summary'
            ai_summary = response.get('ai_summary', response.get('ai_response', ''))
            download_url = response.get('config_download_url', response.get('download_url', ''))
            
            logger.info(f"Extracted fields: config_s3_key={config_s3_key}, ai_summary_length={len(ai_summary) if ai_summary else 0}, download_url={download_url}")
            
            # Send storage progress update
            _send_websocket_message_deduplicated(session_id, {
                'type': 'config_generation_progress',
                'progress': 85,
                'status': '💾 Storing configuration in unified storage...',
                'session_id': session_id
            }, "config_progress_storage")
            
            # Use download URL from config lambda response, or create one if not provided
            if config_s3_key and not download_url:
                download_url = create_config_download_url(config_s3_key)
                logger.info(f"Created fallback download URL: {download_url}")
            elif download_url:
                logger.info(f"Using download URL from config lambda: {download_url}")
            
            # Send final completion progress
            _send_websocket_message_deduplicated(session_id, {
                'type': 'config_generation_progress',
                'progress': 100,
                'status': '🎉 Configuration generation complete!',
                'session_id': session_id
            }, "config_progress_complete")
            
            # Track config generation metrics
            config_cost = response.get('cost_info', {}).get('total_cost', 0.0)
            config_tokens = response.get('cost_info', {}).get('total_tokens', 0)
            
            track_user_request(
                email=event.get('email', ''),
                request_type='config',
                tokens_used=config_tokens,
                cost_usd=config_cost,  # Legacy field
                config_cost=config_cost,
                # Config generation typically uses Perplexity or Anthropic
                perplexity_tokens=response.get('cost_info', {}).get('perplexity_tokens', 0),
                perplexity_cost=response.get('cost_info', {}).get('perplexity_cost', 0.0),
                anthropic_tokens=response.get('cost_info', {}).get('anthropic_tokens', 0),
                anthropic_cost=response.get('cost_info', {}).get('anthropic_cost', 0.0),
                eliyahu_cost=config_cost,  # Config generation costs are our actual costs
                estimated_cost=config_cost,
                quoted_full_cost=0.0,  # Config generation is currently free
                charged_cost=0.0,  # Config generation is currently free
                total_api_calls=response.get('cost_info', {}).get('api_calls', 0),
                total_cached_calls=response.get('cost_info', {}).get('cached_calls', 0)
            )
            
            # Extract version from the actual config
            config_version = 1
            if response.get('updated_config'):
                config_version = response['updated_config'].get('generation_metadata', {}).get('version', 1)
                logger.info(f"Extracted config version {config_version} from generation_metadata")
            
            # Send success message via WebSocket
            websocket_message = {
                'type': 'config_generation_complete',
                'session_id': session_id,
                'success': True,
                'download_url': download_url,
                'ai_summary': ai_summary,
                'ai_response': ai_summary,  # For backward compatibility
                'config_s3_key': config_s3_key,
                'config_version': config_version,  # Explicit version from config
                'clarifying_questions': response.get('clarifying_questions', ''),
                'clarification_urgency': response.get('clarification_urgency', 0.0)
            }
            
            logger.info(f"WebSocket message to send: {json.dumps(websocket_message, indent=2)}")
            
            # Store the generated config in unified storage for future refinements
            try:
                from ..core.unified_s3_manager import UnifiedS3Manager
                
                storage_manager = UnifiedS3Manager()
                email = event.get('email')
                original_session_id = event.get('original_session_id') or session_id
                
                if email and original_session_id and response.get('updated_config'):
                    # Store config in unified storage using versioning system
                    from ..actions.generate_config_unified import store_config_with_versioning
                    storage_result = store_config_with_versioning(
                        email, original_session_id, response['updated_config'], 
                        source='ai_generated'
                    )
                    logger.info(f"Stored config in unified storage: {storage_result}")
                    
                    # If the config lambda didn't provide a working download URL, create one from unified storage
                    if not download_url and storage_result.get('success'):
                        try:
                            config_version = storage_result.get('version', 1)
                            unified_download_url = storage_manager.create_public_download_link(
                                response['updated_config'], f"config_v{config_version}_{original_session_id}.json"
                            )
                            if unified_download_url:
                                download_url = unified_download_url
                                websocket_message['download_url'] = download_url
                                logger.info(f"Created fallback download URL from unified storage: {download_url}")
                        except Exception as download_error:
                            logger.error(f"Failed to create download URL from unified storage: {download_error}")
                    
            except Exception as storage_error:
                logger.error(f"Failed to store config in unified storage: {storage_error}")
                # Don't fail the whole operation for this
            
            # Send via WebSocket with deduplication
            try:
                logger.info(f"[CONFIG_COMPLETION] About to send config_generation_complete for {session_id} with download_url: {websocket_message.get('download_url', 'None')}")
                _send_websocket_message_deduplicated(session_id, websocket_message, "config_generation_complete")
                logger.info(f"[CONFIG_COMPLETION] Sent config_generation_complete for {session_id}")
            except Exception as ws_error:
                logger.error(f"Failed to send WebSocket message: {ws_error}")
        else:
            # Send error message via WebSocket
            websocket_message = {
                'type': 'config_generation_failed',
                'session_id': session_id,
                'success': False,
                'error': response.get('error', 'Unknown error')
            }
            
            try:
                _send_websocket_message_deduplicated(session_id, websocket_message, "config_generation_failed")
            except Exception as ws_error:
                logger.error(f"Failed to send WebSocket error message: {ws_error}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'config_generation_completed',
                'session_id': session_id,
                'response': response
            })
        }
        
    except Exception as e:
        logger.error(f"Config generation error for session {event.get('session_id')}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Send error via WebSocket
        try:
            _send_websocket_message_deduplicated(event.get('session_id'), {
                'type': 'config_generation_failed',
                'session_id': event.get('session_id'),
                'success': False,
                'error': str(e)
            }, "config_generation_error")
        except:
            pass
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'config_generation_failed',
                'error': str(e),
                'session_id': event.get('session_id')
            })
        }

def invoke_config_lambda(event: Dict) -> Dict:
    """Invoke the config lambda function."""
    try:
        import boto3
        
        lambda_client = boto3.client('lambda')
        config_lambda_name = os.environ.get('CONFIG_LAMBDA_NAME', 'perplexity-validator-config')
        
        logger.info(f"Invoking config lambda: {config_lambda_name}")
        
        # Invoke the lambda
        response = lambda_client.invoke(
            FunctionName=config_lambda_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(event)
        )
        
        # Parse response
        payload = json.loads(response['Payload'].read())
        
        if response['StatusCode'] == 200:
            # Parse the body if it's a string
            if isinstance(payload, dict) and 'body' in payload:
                body = payload['body']
                if isinstance(body, str):
                    return json.loads(body)
                else:
                    return body
            else:
                return payload
        else:
            logger.error(f"Config lambda invocation failed: {payload}")
            return {'success': False, 'error': 'Config lambda invocation failed'}
            
    except Exception as e:
        logger.error(f"Failed to invoke config lambda: {str(e)}")
        return {'success': False, 'error': f'Failed to invoke config lambda: {str(e)}'}

def create_config_download_url(s3_key: str) -> str:
    """Create S3 download URL for the generated configuration."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = os.environ.get('S3_UNIFIED_BUCKET', 'perplexity-cache')
        
        # Generate presigned URL (valid for 1 hour)
        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': s3_key},
            ExpiresIn=3600
        )
        
        logger.info(f"Created download URL for S3 key: {s3_key}")
        return download_url
        
    except Exception as e:
        logger.error(f"Failed to create config download URL: {str(e)}")
        return ""

# WebSocket message deduplication cache
_websocket_message_cache = {}
# Special cache for config generation completion messages
_config_completion_cache = {}

def _send_websocket_message_deduplicated(session_id: str, message: Dict, message_type: str = None):
    """Send a WebSocket message to a session with deduplication."""
    import hashlib
    import time
    
    try:
        current_time = time.time()
        
        # Special deduplication for config generation completion messages
        if message_type in ['config_generation_complete', 'config_generation_failed']:
            completion_key = f"{session_id}:{message_type}"
            if completion_key in _config_completion_cache:
                last_completion = _config_completion_cache[completion_key]
                if current_time - last_completion < 60:  # 60 second window for completion messages
                    logger.info(f"🚫 DEDUPLICATED config completion message for {session_id} (type: {message_type}) - last sent {current_time - last_completion:.1f}s ago")
                    return
            _config_completion_cache[completion_key] = current_time
            logger.info(f"[DEDUP_CACHE] Cached config completion for {session_id}:{message_type}")
            
            # Clean old completion cache entries
            expired_completion_keys = [k for k, v in _config_completion_cache.items() if current_time - v > 120]
            for key in expired_completion_keys:
                del _config_completion_cache[key]
        
        # Create message fingerprint for general deduplication
        message_content = json.dumps(message, sort_keys=True)
        message_hash = hashlib.md5(f"{session_id}:{message_content}".encode()).hexdigest()
        
        # Check if this exact message was sent recently 
        # Use longer deduplication window for completion messages
        dedup_window = 30 if message_type in ['config_generation_complete', 'config_generation_failed'] else 5
        cache_key = f"{session_id}:{message_hash}"
        
        if cache_key in _websocket_message_cache:
            last_sent = _websocket_message_cache[cache_key]
            if current_time - last_sent < dedup_window:
                logger.info(f"🚫 DEDUPLICATED WebSocket message for {session_id} (type: {message_type}, window: {dedup_window}s)")
                return
        
        # Clean old cache entries (older than 60 seconds)
        expired_keys = [k for k, v in _websocket_message_cache.items() if current_time - v > 60]
        for key in expired_keys:
            del _websocket_message_cache[key]
        
        from dynamodb_schemas import get_connections_for_session
        
        connections = get_connections_for_session(session_id)
        if not connections:
            logger.warning(f"No WebSocket connections found for session {session_id}")
            return
        
        # Get API Gateway Management client
        client = _get_api_gateway_management_client(None)
        if not client:
            logger.error("Failed to get API Gateway Management client")
            return
        
        # Send to all connections
        sent_count = 0
        for connection_id in connections:
            try:
                client.post_to_connection(
                    ConnectionId=connection_id,
                    Data=json.dumps(message)
                )
                sent_count += 1
                # Reduce individual connection logging - already logged in summary
            except Exception as e:
                logger.error(f"Failed to send to connection {connection_id}: {e}")
                # Remove stale connection
                try:
                    from dynamodb_schemas import remove_websocket_connection
                    remove_websocket_connection(connection_id)
                except:
                    pass
        
        # Cache this message to prevent duplicates
        _websocket_message_cache[cache_key] = current_time
        # Only log WebSocket messages for important events or when multiple connections
        if sent_count > 1 or message_type in ['preview_progress_final', 'validation_complete', 'error']:
            logger.info(f"📤 WebSocket message sent to {sent_count} connections for {session_id} (type: {message_type})")
                    
    except Exception as e:
        logger.error(f"Failed to send WebSocket message: {e}")
        raise

def _send_websocket_message(session_id: str, message: Dict):
    """Legacy WebSocket sender - delegates to deduplicated version."""
    _send_websocket_message_deduplicated(session_id, message, "legacy")

def _update_session_info_with_account_data(email: str, session_id: str, account_info: Dict):
    """Update session_info.json with comprehensive account information."""
    try:
        from ..core.unified_s3_manager import UnifiedS3Manager
        
        storage_manager = UnifiedS3Manager()
        session_path = storage_manager.get_session_path(email, session_id)
        session_info_key = f"{session_path}session_info.json"
        
        # Get existing session info
        try:
            existing_response = storage_manager.s3_client.get_object(
                Bucket=storage_manager.bucket_name,
                Key=session_info_key
            )
            session_info = json.loads(existing_response['Body'].read())
        except:
            # Create basic session info if doesn't exist
            session_info = {
                'session_id': session_id,
                'created': datetime.now().isoformat(),
                'email': email,
                'last_updated': datetime.now().isoformat()
            }
        
        # Update with account information
        session_info['account_info'] = account_info
        session_info['last_updated'] = datetime.now().isoformat()
        
        # Store updated session info
        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=session_info_key,
            Body=json.dumps(session_info, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Updated session_info.json with account data for {session_id}")
        
    except Exception as e:
        logger.error(f"Failed to update session_info with account data: {e}")