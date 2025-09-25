"""
Updated processExcel action using unified storage system.
Files are stored once per session and reused across preview/validation/config generation.
"""
import logging
import json
import os
import base64
import uuid
from datetime import datetime
import boto3
import time
import math
import io
from pathlib import Path

from interface_lambda.utils.parsing import parse_multipart_form_data
from interface_lambda.utils.helpers import create_response
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager

# Optional imports - will be handled conditionally in functions
try:
    from shared_table_parser import s3_table_parser
except ImportError:
    s3_table_parser = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def _calculate_intelligent_cost_estimate(email: str, session_id: str, storage_manager, multiplier: float) -> float:
    """
    Calculate intelligent cost estimate based on available preview data or table analysis.
    
    Args:
        email: User email address
        session_id: Current session ID
        storage_manager: Unified storage manager instance
        multiplier: Domain multiplier for cost calculation
        
    Returns:
        Estimated minimum cost in USD (Decimal precision)
    """
    try:
        from decimal import Decimal
        
        # Ensure multiplier is a float (DynamoDB may return Decimal)
        multiplier = float(multiplier) if multiplier is not None else 1.0
        
        # Try to get cost estimate from existing preview results
        try:
            # Look for existing preview results in this session
            session_path = storage_manager.get_session_path(email, session_id)
            
            # Try to find preview results in different config versions
            for version in range(5, 0, -1):  # Check versions 5 down to 1
                try:
                    preview_key = f"{session_path}/results/v{version}/preview_results.json"
                    response = storage_manager.s3_client.get_object(
                        Bucket=storage_manager.bucket_name,
                        Key=preview_key
                    )
                    preview_data = json.loads(response['Body'].read().decode('utf-8'))
                    
                    # Extract cost estimates from preview
                    cost_estimates = preview_data.get('cost_estimates', {})
                    preview_quoted_cost = cost_estimates.get('quoted_validation_cost', 0.0)
                    
                    if preview_quoted_cost > 0:
                        logger.info(f"[COST_ESTIMATE] Using preview quoted cost: ${preview_quoted_cost:.2f} from v{version}")
                        return Decimal(str(preview_quoted_cost))
                        
                except Exception:
                    continue  # Try next version
                    
        except Exception as preview_error:
            logger.debug(f"[COST_ESTIMATE] No preview data found: {preview_error}")
        
        # Fallback: Try to estimate based on Excel file analysis
        try:
            excel_keys = storage_manager.list_session_files(email, session_id, 'excel/')
            if excel_keys:
                # Get the most recent Excel file
                latest_excel_key = sorted(excel_keys)[-1]
                
                # Estimate cost based on file size as rough approximation
                try:
                    head_response = storage_manager.s3_client.head_object(
                        Bucket=storage_manager.bucket_name,
                        Key=latest_excel_key
                    )
                    file_size = head_response.get('ContentLength', 0)
                    
                    # Rough estimation: $0.10 per MB of Excel file with multiplier
                    # This is a conservative estimate that accounts for processing complexity
                    size_mb = file_size / (1024 * 1024) if file_size > 0 else 0.1
                    base_estimate = max(0.02, size_mb * 0.10)  # At least $0.02, $0.10 per MB
                    estimated_with_multiplier = base_estimate * multiplier
                    final_estimate = max(2.0, math.ceil(estimated_with_multiplier))  # $2 minimum, rounded up
                    
                    logger.info(f"[COST_ESTIMATE] File size estimation: {size_mb:.2f}MB -> "
                               f"Base: ${base_estimate:.2f}, With {multiplier}x: ${estimated_with_multiplier:.2f}, "
                               f"Final: ${final_estimate:.2f}")
                    
                    return Decimal(str(final_estimate))
                    
                except Exception as size_error:
                    logger.warning(f"[COST_ESTIMATE] File size estimation failed: {size_error}")
                    
        except Exception as excel_error:
            logger.debug(f"[COST_ESTIMATE] Excel analysis failed: {excel_error}")
        
        # Final fallback: Conservative default estimate
        default_estimate = max(2.0, 0.05 * multiplier)  # $2 minimum or 5 cents * multiplier
        logger.warning(f"[COST_ESTIMATE] Using fallback estimate: ${default_estimate:.2f} "
                      f"(multiplier: {multiplier}x)")
        
        return Decimal(str(default_estimate))
        
    except Exception as e:
        logger.error(f"[COST_ESTIMATE] Error calculating cost estimate: {e}")
        # Emergency fallback
        return Decimal('2.00')  # $2 minimum

def _enhance_cost_aggregation(validation_results: dict, processing_time: float) -> dict:
    """
    Enhance cost aggregation with three-tier cost system and time estimation improvements.
    
    Args:
        validation_results: Raw validation results from lambda
        processing_time: Processing time in seconds
        
    Returns:
        Enhanced cost data with three-tier system applied
    """
    try:
        if not validation_results or not isinstance(validation_results, dict):
            logger.warning("[COST_AGGREGATION] Invalid validation results")
            return {
                'eliyahu_cost': 0.0,
                'cost_estimated': 0.0,
                'total_cost': 0.0,
                'processing_time': processing_time,
                'cost_per_second': 0.0,
                'error': 'invalid_results'
            }
        
        metadata = validation_results.get('metadata', {})
        token_usage = metadata.get('token_usage', {})
        
        # Extract actual cost (with caching benefits)
        eliyahu_cost = float(token_usage.get('total_cost', 0.0))
        
        # Calculate estimated cost without cache benefits
        total_calls = token_usage.get('api_calls', 0)
        cached_calls = token_usage.get('cached_calls', 0)
        
        if cached_calls > 0 and total_calls > cached_calls:
            # Estimate cost if no caching were available
            non_cached_calls = total_calls - cached_calls
            cost_per_non_cached_call = eliyahu_cost / max(1, non_cached_calls)
            cost_estimated = cost_per_non_cached_call * total_calls
        else:
            cost_estimated = eliyahu_cost
        
        # Calculate processing efficiency metrics
        cost_per_second = eliyahu_cost / max(0.001, processing_time)  # Avoid division by zero
        total_tokens = token_usage.get('total_tokens', 0)
        tokens_per_second = total_tokens / max(0.001, processing_time)
        cost_per_token = eliyahu_cost / max(1, total_tokens)
        
        # Validate calculations
        if eliyahu_cost < 0 or cost_estimated < 0:
            logger.error(f"[COST_AGGREGATION] Negative costs detected - Actual: ${eliyahu_cost:.6f}, "
                        f"Estimated: ${cost_estimated:.6f}")
            eliyahu_cost = max(0.0, eliyahu_cost)
            cost_estimated = max(0.0, cost_estimated)
        
        enhanced_data = {
            'eliyahu_cost': eliyahu_cost,
            'cost_estimated': cost_estimated,
            'total_cost': eliyahu_cost,  # For backwards compatibility
            'processing_time': processing_time,
            'cost_per_second': cost_per_second,
            'cost_per_token': cost_per_token,
            'tokens_per_second': tokens_per_second,
            'cache_hit_rate': cached_calls / max(1, total_calls),
            'cost_savings_from_cache': cost_estimated - eliyahu_cost,
            'efficiency_metrics': {
                'total_calls': total_calls,
                'cached_calls': cached_calls,
                'non_cached_calls': max(0, total_calls - cached_calls),
                'total_tokens': total_tokens,
                'processing_efficiency_score': tokens_per_second / max(0.001, cost_per_second)  # Tokens per dollar per second
            }
        }
        
        logger.info(f"[COST_AGGREGATION] Enhanced cost data - Actual: ${eliyahu_cost:.6f}, "
                   f"Estimated: ${cost_estimated:.6f}, "
                   f"Cache savings: ${enhanced_data['cost_savings_from_cache']:.6f}, "
                   f"Efficiency: {enhanced_data['efficiency_metrics']['processing_efficiency_score']:.2f}")
        
        return enhanced_data
        
    except Exception as e:
        logger.error(f"[COST_AGGREGATION] Error enhancing cost data: {e}")
        return {
            'eliyahu_cost': 0.0,
            'cost_estimated': 0.0,
            'total_cost': 0.0,
            'processing_time': processing_time,
            'cost_per_second': 0.0,
            'error': str(e)
        }

def handle_multipart_form(event, context):
    """Handles multipart/form-data requests for Excel processing with unified storage."""
    
    headers = event.get('headers', {})
    content_type = headers.get('Content-Type') or headers.get('content-type', '')
    body = event.get('body', '')
    is_base64_encoded = event.get('isBase64Encoded', False)
    
    files, form_data = parse_multipart_form_data(body, content_type, is_base64_encoded)
    
    email_address = form_data.get('email', 'test@example.com')
    session_id = form_data.get('session_id', '')  # Should be provided from email validation
    excel_file = files.get('excel_file')
    config_file_content_str = form_data.get('config_file', '')
    
    if not email_address:
        return create_response(400, {'error': 'Missing email address'})
    
    # For new Excel uploads without session_id, we'll generate one
    # For other operations, session_id is required
    if not session_id and not excel_file:
        return create_response(400, {'error': 'Missing session_id - please upload an Excel file first'})
    
    # Don't require files if we have a valid session - unified storage may have them
    # The actual check for stored files happens in _process_files_unified

    config_file = None
    if config_file_content_str:
        config_file = {'filename': 'config.json', 'content': config_file_content_str.encode('utf-8')}

    return _process_files_unified(excel_file, config_file, email_address, session_id, 
                                event.get('queryStringParameters') or {}, context)

def handle_json_request(event, context):
    """Handles application/json requests for Excel processing with unified storage."""
    body = event.get('body', '{}')
    if event.get('isBase64Encoded'):
        body = base64.b64decode(body).decode('utf-8')
    request_data = json.loads(body)
    
    email_address = request_data.get('email', 'test@example.com')
    session_id = request_data.get('session_id', '')
    excel_base64 = request_data.get('excel_file', '')
    config_base64 = request_data.get('config_file', '')

    if not email_address:
        return create_response(400, {'error': 'Missing email address'})
    
    # For new Excel uploads without session_id, we'll generate one
    # For other operations, session_id is required  
    if not session_id and not excel_base64:
        return create_response(400, {'error': 'Missing session_id - please upload an Excel file first'})

    excel_file = None
    config_file = None
    
    if excel_base64:
        excel_file = {'filename': 'input.xlsx', 'content': base64.b64decode(excel_base64)}
    
    if config_base64:
        config_file = {'filename': 'config.json', 'content': base64.b64decode(config_base64)}
    
    # Don't require files if we have a valid session - unified storage may have them
    # The actual check for stored files happens in _process_files_unified

    return _process_files_unified(excel_file, config_file, email_address, session_id, 
                                request_data, context)

def _process_files_unified(excel_file, config_file, email_address, session_id, params, context):
    """Process files using unified storage - store once, use throughout session lifecycle."""
    
    # Always use a clean session ID format: session_YYYY-MM-DDTHH_MM_SS_XXXXXX
    # Remove _preview suffix if present, ensure session_ prefix
    base_session_id = session_id
    if base_session_id.endswith('_preview'):
        base_session_id = base_session_id[:-8]  # Remove '_preview' suffix
        
    if not base_session_id.startswith('session_'):
        base_session_id = f"session_{base_session_id}"
        
    logger.info(f"Using clean session ID for file storage/lookup: {base_session_id}")
    
    # Use base_session_id for file operations, keep original session_id for tracking
    
    try:
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
        from dynamodb_schemas import is_email_validated, track_validation_call, create_run_record
    except ImportError as e:
        logger.error(f"Failed to import dynamodb_schemas: {e}")
        def is_email_validated(email): return True
        def track_validation_call(email, session_id, reference_pin, request_type, excel_s3_key=None, config_s3_key=None): 
            logger.warning("dynamodb_schemas not available - tracking disabled")
        def create_run_record(**kwargs): 
            logger.warning("dynamodb_schemas not available - run record creation disabled")

    try:
        from ..core.sqs_service import send_preview_request, send_full_request
        SQS_AVAILABLE = True
        logger.info("✅ SQS service is available - will use async processing")
    except ImportError as e:
        SQS_AVAILABLE = False
        logger.warning(f"❌ SQS service not available - will use sync processing: {e}")
    except Exception as e:
        SQS_AVAILABLE = False
        logger.error(f"❌ Failed to load SQS service - will use sync processing: {e}")

    # Validate email
    if not is_email_validated(email_address):
        return create_response(403, {'error': 'email_not_validated'})
        
    # Initialize unified storage
    storage_manager = UnifiedS3Manager()
    
    # Parse request parameters
    preview = params.get('preview_first_row', 'false').lower() == 'true'
    async_mode = params.get('async', 'false').lower() == 'true'
    preview_email = params.get('preview_email', 'false').lower() == 'true'
    
    logger.info(f"Processing unified request: email={email_address}, session={session_id}, "
                f"preview={preview}, async_mode={async_mode}, preview_email={preview_email}, SQS_AVAILABLE={SQS_AVAILABLE}")

    # Store files in unified storage if provided
    excel_s3_key = None
    config_s3_key = None
    
    try:
        # Store Excel file if provided
        if excel_file:
            logger.info(f"Storing Excel file: {excel_file['filename']}")
            
            # Only generate new session ID if none was provided (new upload)
            if not session_id:
                logger.info("No session_id provided - generating new session ID for new table upload")
                import hashlib
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                hash_input = f"{email_address}_{timestamp}".encode()
                short_hash = hashlib.md5(hash_input).hexdigest()[:8]
                new_session_id = f"session_{timestamp}_{short_hash}"
                base_session_id = new_session_id
                logger.info(f"Generated new session ID for Excel upload: {base_session_id}")
            else:
                logger.info(f"Using existing session_id for Excel storage: {base_session_id}")
            
            # Get table name from filename for session info
            table_name = excel_file['filename'].rsplit('.', 1)[0] if '.' in excel_file['filename'] else excel_file['filename']
            
            excel_result = storage_manager.store_excel_file(
                email_address, base_session_id, excel_file['content'], excel_file['filename']
            )
            if not excel_result['success']:
                return create_response(500, {'error': f"Failed to store Excel file: {excel_result['error']}"})
            excel_s3_key = excel_result['s3_key']
            
            # Initialize session info with Excel path (clean structure)
            session_info = storage_manager.load_session_info(email_address, base_session_id)
            session_info.update({
                'table_name': table_name,
                'table_path': excel_s3_key,
                'current_version': 0,  # No config uploaded yet
                'last_updated': datetime.now().isoformat()
            })
            
            session_info_saved = storage_manager.save_session_info(email_address, base_session_id, session_info)
            if session_info_saved:
                logger.info(f"Session info initialized with Excel path: {excel_s3_key}")
            else:
                logger.warning("Failed to save session info with Excel path")
            
            # Update session_id to match base_session_id for consistency
            session_id = base_session_id
        else:
            # Try to get existing Excel file from storage
            logger.info("No new Excel file provided, looking for existing file")
            excel_content, excel_s3_key = storage_manager.get_excel_file(email_address, base_session_id)
            if not excel_s3_key:
                return create_response(400, {'error': 'No Excel file found for this session. Please upload an Excel file first.'})
        
        # Store config file if provided (optional for testing)
        if config_file:
            logger.info(f"Config file provided for testing - storing new config file: {config_file['filename']}")
            try:
                config_data = json.loads(config_file['content'].decode('utf-8'))
            except json.JSONDecodeError as e:
                return create_response(400, {'error': f'Invalid JSON in config file: {str(e)}'})
            
            # Get current version number (increment from existing configs)
            existing_config, _ = storage_manager.get_latest_config(email_address, base_session_id)
            version = 1
            if existing_config and existing_config.get('storage_metadata', {}).get('version'):
                version = existing_config['storage_metadata']['version'] + 1
            
            config_result = storage_manager.store_config_file(
                email_address, base_session_id, config_data, version=version, source='upload'
            )
            if not config_result['success']:
                return create_response(500, {'error': f"Failed to store config file: {config_result['error']}"})
            config_s3_key = config_result['s3_key']
        else:
            # Normal operation: get existing config file from unified storage
            logger.info("No config file provided - retrieving existing config from unified storage")
            existing_config, config_s3_key = storage_manager.get_latest_config(email_address, base_session_id)
            if not config_s3_key:
                # Check if this is validation/preview request (requires config) vs file upload (doesn't require config)
                is_validation_request = params.get('preview_first_row') or params.get('async')
                
                if is_validation_request:
                    # This is a validation/preview request but no config found
                    logger.error(f"Validation/preview request but no config found for session {base_session_id}")
                    return create_response(400, {'error': 'No config file found for this session. Please upload a config file or generate one using AI first.'})
                elif excel_file:
                    # This is just an Excel file upload (for config generation) - store and search for matching configs
                    logger.info("Excel file uploaded for config generation - searching for matching configs")
                    
                    # Automatically search for matching configs
                    try:
                        from .find_matching_config import find_matching_configs
                        matching_configs = find_matching_configs(email_address, base_session_id, limit=3)
                        logger.info(f"Found {len(matching_configs.get('matches', []))} matching configs")
                        
                        # Don't auto-copy configs - let user explicitly select them
                        # This prevents premature version increments (configs should only be copied when user chooses to use them)
                        
                    except Exception as e:
                        logger.error(f"Error searching for matching configs: {e}")
                        matching_configs = {'success': False, 'matches': []}
                    
                    return create_response(200, {
                        'success': True,
                        'message': 'Excel file uploaded successfully for config generation',
                        'session_id': session_id,
                        'excel_s3_key': excel_s3_key,
                        'storage_path': storage_manager.get_session_path(email_address, base_session_id),
                        'matching_configs': matching_configs
                    })
                else:
                    # No Excel file and no config - invalid state
                    return create_response(400, {'error': 'No files provided. Please upload an Excel file or config file.'})
            else:
                # Config found - check if this is a new Excel file upload for config generation
                if excel_file and not params.get('preview_first_row') and not params.get('async'):
                    # New Excel file uploaded even though config exists - this is for config generation
                    logger.info("New Excel file uploaded to session with existing config - treating as config generation request")

                    # Search for matching configs for the new file
                    try:
                        from .find_matching_config import find_matching_configs
                        matching_configs = find_matching_configs(email_address, base_session_id, limit=3)
                        logger.info(f"Found {len(matching_configs.get('matches', []))} matching configs")

                    except Exception as e:
                        logger.error(f"Error searching for matching configs: {e}")
                        matching_configs = {'success': False, 'matches': []}

                    return create_response(200, {
                        'success': True,
                        'message': 'Excel file uploaded successfully for config generation',
                        'session_id': session_id,
                        'excel_s3_key': excel_s3_key,
                        'storage_path': storage_manager.get_session_path(email_address, base_session_id),
                        'matching_configs': matching_configs
                    })

                # Config found and this is validation/preview request - log details
                config_source = existing_config.get('storage_metadata', {}).get('source', 'unknown')
                config_version = existing_config.get('storage_metadata', {}).get('version', 'unknown')
                logger.info(f"Using existing config from unified storage: {config_s3_key} (source: {config_source}, version: {config_version})")

        # Parse validation parameters
        try:
            max_rows_str = params.get('max_rows')
            max_rows = int(max_rows_str) if max_rows_str else None
            
            batch_size_str = params.get('batch_size')
            batch_size = int(batch_size_str) if batch_size_str else None  # Let enhanced batch manager determine optimal size
            
            preview_max_rows_str = params.get('preview_max_rows')
            preview_max_rows = int(preview_max_rows_str) if preview_max_rows_str else 3

        except (ValueError, TypeError):
            return create_response(400, {'error': 'max_rows, batch_size, and preview_max_rows must be valid integers'})

        # Calculate total rows for tracking using shared table parser
        total_rows = -1
        try:
            if excel_s3_key and s3_table_parser:
                table_data = s3_table_parser.analyze_table_structure(storage_manager.bucket_name, excel_s3_key)
                if table_data and 'basic_info' in table_data:
                    total_rows = table_data['basic_info'].get('total_rows', -1)
                logger.info(f"Calculated total rows using shared parser: {total_rows}")
        except Exception as e:
            logger.warning(f"Could not calculate total rows: {e}")
            total_rows = -1

        # Create tracking records
        run_type = "Preview" if preview else "Validation"
        run_key = create_run_record(session_id=session_id, email=email_address, total_rows=total_rows, batch_size=batch_size, run_type=run_type)
        reference_pin = session_id.split('_')[-1] if '_' in session_id else session_id[:6]
        track_validation_call(
            email=email_address,
            session_id=session_id,
            reference_pin=reference_pin,
            request_type='preview' if preview else 'full', 
            excel_s3_key=excel_s3_key, 
            config_s3_key=config_s3_key
        )

        # Process the validation request
        if preview:
            return _handle_preview_request(
                storage_manager, email_address, session_id, excel_s3_key, config_s3_key,
                preview_max_rows, async_mode, SQS_AVAILABLE, preview_email, run_key
            )
        else:
            return _handle_full_validation_request(
                storage_manager, email_address, session_id, excel_s3_key, config_s3_key,
                max_rows, batch_size, async_mode, SQS_AVAILABLE, preview_email, run_key
            )

    except Exception as e:
        logger.error(f"Error in unified file processing: {str(e)}")
        return create_response(500, {'error': f'File processing failed: {str(e)}'})

def _handle_preview_request(storage_manager, email_address, session_id, excel_s3_key, 
                          config_s3_key, preview_max_rows, async_mode, SQS_AVAILABLE, preview_email=False, run_key=None):
    """Handle preview request using unified storage"""
    from ..utils.helpers import create_response
    
    # IMPORTANT: Use unique preview_session_id for WebSocket but keep storage folder consistent
    # This allows multiple previews from same session without conflicts
    
    if async_mode and SQS_AVAILABLE:
        logger.info(f"Sending preview request to SQS for session {session_id}")
        from ..core.sqs_service import send_preview_request
        
        message_id = send_preview_request(
            session_id=session_id, excel_s3_key=excel_s3_key, 
            config_s3_key=config_s3_key, email=email_address, 
            reference_pin=session_id.split('_')[-1] if '_' in session_id else session_id[:6],
            preview_max_rows=preview_max_rows, preview_email=preview_email,
            run_key=run_key
        )
        logger.info(f"SQS preview request sent with MessageId: {message_id}")
        
        response_body = {
            "status": "processing", 
            "session_id": session_id, 
            "reference_pin": session_id.split('_')[-1] if '_' in session_id else session_id[:6],
            "storage_path": storage_manager.get_session_path(email_address, session_id)
        }
        return create_response(200, response_body)
    else:
        # Synchronous preview processing
        return _process_preview_sync(
            storage_manager, email_address, session_id, excel_s3_key, config_s3_key, preview_max_rows
        )

def _handle_full_validation_request(storage_manager, email_address, session_id, excel_s3_key, 
                                  config_s3_key, max_rows, batch_size, async_mode, SQS_AVAILABLE, preview_email=False, run_key=None):
    """Handle full validation request using unified storage"""
    from ..utils.helpers import create_response
    
    # Check account balance before processing full validation
    try:
        from dynamodb_schemas import check_user_balance, get_domain_multiplier
        from decimal import Decimal
        
        current_balance = check_user_balance(email_address)
        if current_balance is None:
            return create_response(400, {
                'error': 'Account not found. Please contact support to set up your account.',
                'error_type': 'account_not_found'
            })
        
        # ========== HARDENED COST ESTIMATION SYSTEM ==========
        # Get domain multiplier with validation
        email_domain = email_address.split('@')[-1] if '@' in email_address else 'unknown'
        multiplier = get_domain_multiplier(email_domain)
        
        # Validate multiplier
        if multiplier <= 0 or multiplier > 100:
            logger.error(f"[COST_ERROR] Invalid multiplier {multiplier} for domain {email_domain}")
            multiplier = 5.0  # Safe fallback
        
        # Intelligent cost estimation based on available preview data
        min_estimated_cost = _calculate_intelligent_cost_estimate(
            email_address, session_id, storage_manager, multiplier
        )
        
        if current_balance < min_estimated_cost:
            logger.warning(f"Insufficient balance for {email_address}: ${current_balance} < ${min_estimated_cost}")
            return create_response(402, {  # Payment Required
                'error': 'Insufficient account balance for full validation',
                'error_type': 'insufficient_balance',
                'current_balance': float(current_balance),
                'domain_multiplier': float(multiplier),
                'estimated_minimum_cost': float(min_estimated_cost),
                'message': f'Your account balance (${float(current_balance):.4f}) is insufficient for validation. Please add credits to continue.'
            })
        
        logger.info(f"Balance check passed for {email_address}: ${current_balance} available, multiplier: {multiplier}x")
        
    except Exception as e:
        logger.error(f"Error checking account balance: {e}")
        return create_response(500, {
            'error': 'Failed to verify account balance',
            'error_type': 'balance_check_failed'
        })
    
    if async_mode and SQS_AVAILABLE:
        logger.info(f"🚀 USING ASYNC PROCESSING: Sending full validation request to SQS for session {session_id} (preview_email={preview_email})")
        from ..core.sqs_service import send_full_request
        
        message_id = send_full_request(
            session_id=session_id, excel_s3_key=excel_s3_key, 
            config_s3_key=config_s3_key, email=email_address, 
            reference_pin=session_id.split('_')[-1] if '_' in session_id else session_id[:6],
            max_rows=max_rows, batch_size=batch_size, preview_email=preview_email,
            run_key=run_key
        )
        logger.info(f"SQS full validation request sent with MessageId: {message_id}")
        
        response_body = {
            "status": "processing", 
            "session_id": session_id, 
            "reference_pin": session_id.split('_')[-1] if '_' in session_id else session_id[:6],
            "storage_path": storage_manager.get_session_path(email_address, session_id)
        }
        return create_response(200, response_body)
    else:
        # Synchronous full validation processing
        logger.warning(f"⚠️ USING SYNC PROCESSING: async_mode={async_mode}, SQS_AVAILABLE={SQS_AVAILABLE}, batch_size={batch_size}")
        return _process_validation_sync(
            storage_manager, email_address, session_id, excel_s3_key, config_s3_key, max_rows, batch_size
        )

def _process_preview_sync(storage_manager, email_address, session_id, excel_s3_key, 
                        config_s3_key, preview_max_rows):
    """Process preview synchronously and store results in unified storage"""
    from ..utils.helpers import create_response
    from ..core.validator_invoker import invoke_validator_lambda
    from ..reporting.markdown_report import create_markdown_table_from_results
    
    
    try:
        start_time = time.time()
        validation_results = invoke_validator_lambda(
            excel_s3_key, config_s3_key, 
            max_rows=preview_max_rows, 
            batch_size=preview_max_rows,
            S3_CACHE_BUCKET=storage_manager.bucket_name,
            VALIDATOR_LAMBDA_NAME=os.environ.get('VALIDATOR_LAMBDA_NAME'), 
            preview_first_row=True, 
            preview_max_rows=preview_max_rows
        )
        processing_time = time.time() - start_time
        
        if validation_results and 'validation_results' in validation_results and validation_results['validation_results']:
            real_results = validation_results['validation_results']
            total_rows = validation_results.get('total_rows', 1)
            metadata = validation_results.get('metadata', {})
            token_usage = metadata.get('token_usage', {})
            total_processed_rows = validation_results.get('total_processed_rows', 1)

            # ========== ENHANCED COST AGGREGATION ==========
            # Apply hardened cost aggregation with three-tier system
            enhanced_cost_data = _enhance_cost_aggregation(validation_results, processing_time)
            
            # Extract costs for backwards compatibility
            total_cost = enhanced_cost_data.get('total_cost', 0.0)
            eliyahu_cost = enhanced_cost_data.get('eliyahu_cost', 0.0)
            cost_estimated = enhanced_cost_data.get('cost_estimated', 0.0)

            markdown_table = create_markdown_table_from_results(real_results, 3, config_s3_key, storage_manager.bucket_name, None)
            
            # Prepare enhanced preview results for storage with three-tier cost data
            preview_data = {
                'session_id': session_id,
                'results': real_results,
                'markdown_table': markdown_table,
                'metadata': {
                    'total_rows': total_rows,
                    'total_processed_rows': total_processed_rows,
                    'processing_time': processing_time,
                    'token_usage': token_usage,
                    'total_cost': total_cost,  # Backwards compatibility
                    'enhanced_cost_data': enhanced_cost_data  # Full cost analysis
                },
                'excel_s3_key': excel_s3_key,
                'config_s3_key': config_s3_key
            }
            
            # Store preview results in unified storage using versioned results structure
            # Get config version from config_s3_key or default to 1
            config_version = 1
            config_id = ""
            try:
                existing_config, _ = storage_manager.get_latest_config(email_address, session_id)
                if existing_config and existing_config.get('storage_metadata', {}):
                    config_version = existing_config['storage_metadata'].get('version', 1)
                    config_id = existing_config['storage_metadata'].get('config_id', '')
            except:
                pass
            
            result = storage_manager.store_results(email_address, session_id, config_version, preview_data, 'preview')
            if result['success']:
                logger.info(f"Preview results stored: {result['s3_key']}")
                
                # Update session tracking with minimal lookup info and file paths
                try:
                    logger.error(f"🔥 PROCESS_EXCEL_PREVIEW: About to call update_session_results for preview")
                    logger.error(f"🔥 PROCESS_EXCEL_PREVIEW: Parameters - email={email_address}, session_id={session_id}, config_id={config_id}, version={config_version}, run_key={run_key}")
                    
                    success = storage_manager.update_session_results(
                        email=email_address,
                        session_id=session_id,
                        operation_type="preview",
                        config_id=config_id,
                        version=config_version,
                        run_key=run_key,
                        results_path=result['s3_key']  # Path to preview results JSON
                    )
                    logger.error(f"🔥 PROCESS_EXCEL_PREVIEW: update_session_results returned: {success}")
                    
                    if success:
                        logger.info(f"✅ Updated session_info.json with preview completion")
                    else:
                        logger.error(f"❌ Failed to update session_info.json with preview completion")
                except Exception as e:
                    logger.error(f"💥 EXCEPTION in process_excel preview session tracking: {e}")
                    import traceback
                    logger.error(f"💥 TRACEBACK: {traceback.format_exc()}")
            
            # ========== ENHANCED RESPONSE WITH THREE-TIER COST DATA ==========
            response_body = {
                'success': True,
                'session_id': session_id,
                'results': real_results,
                'markdown_table': markdown_table,
                'total_rows': total_rows,
                'total_processed_rows': total_processed_rows,
                'processing_time': processing_time,
                'token_usage': token_usage,
                'total_cost': total_cost,  # Backwards compatibility
                'enhanced_cost_data': enhanced_cost_data,  # Full three-tier cost analysis
                'cost_summary': {
                    'eliyahu_cost': eliyahu_cost,
                    'cost_estimated': cost_estimated,
                    'cache_savings': enhanced_cost_data.get('cost_savings_from_cache', 0.0),
                    'efficiency_score': enhanced_cost_data.get('efficiency_metrics', {}).get('processing_efficiency_score', 0.0)
                },
                'storage_path': storage_manager.get_session_path(email_address, session_id)
            }
            return create_response(200, response_body)
        else:
            logger.error("Preview validation failed or returned empty results")
            return create_response(500, {'error': 'Preview validation failed'})
            
    except Exception as e:
        logger.error(f"Preview processing error: {str(e)}")
        return create_response(500, {'error': f'Preview processing failed: {str(e)}'})

def _process_validation_sync(storage_manager, email_address, session_id, excel_s3_key, 
                           config_s3_key, max_rows, batch_size):
    """Process full validation synchronously and store results in unified storage"""
    from ..utils.helpers import create_response
    from ..core.validator_invoker import invoke_validator_lambda
    # ZIP report functionality disabled to avoid import errors
    # from ..reporting.zip_report import create_zip_report
    
    try:
        start_time = time.time()
        validation_results = invoke_validator_lambda(
            excel_s3_key, config_s3_key, 
            max_rows=max_rows, 
            batch_size=batch_size,
            S3_CACHE_BUCKET=storage_manager.bucket_name,
            VALIDATOR_LAMBDA_NAME=os.environ.get('VALIDATOR_LAMBDA_NAME'), 
            preview_first_row=False
        )
        processing_time = time.time() - start_time
        
        if validation_results and 'validation_results' in validation_results:
            # ZIP report functionality disabled - just store JSON results
            import json
            results_json = json.dumps(validation_results, indent=2).encode('utf-8')
            
            # Store validation results in unified storage using versioned results structure
            # Get config version from config_s3_key or default to 1
            config_version = 1
            config_id = ""
            try:
                existing_config, _ = storage_manager.get_latest_config(email_address, session_id)
                if existing_config and existing_config.get('storage_metadata', {}):
                    config_version = existing_config['storage_metadata'].get('version', 1)
                    config_id = existing_config['storage_metadata'].get('config_id', '')
            except:
                pass
            
            result = storage_manager.store_results(email_address, session_id, config_version, validation_results, 'validation')
            if result['success']:
                logger.info(f"Validation results stored: {result['s3_key']}")
                
                # Update session tracking with minimal lookup info and file paths
                try:
                    logger.error(f"🔥 PROCESS_EXCEL_VALIDATION: About to call update_session_results for validation")
                    logger.error(f"🔥 PROCESS_EXCEL_VALIDATION: Parameters - email={email_address}, session_id={session_id}, config_id={config_id}, version={config_version}, run_key={run_key}")
                    
                    success = storage_manager.update_session_results(
                        email=email_address,
                        session_id=session_id,
                        operation_type="validation",
                        config_id=config_id,
                        version=config_version,
                        run_key=run_key,
                        results_path=result['s3_key']  # Path to validation results JSON
                    )
                    logger.error(f"🔥 PROCESS_EXCEL_VALIDATION: update_session_results returned: {success}")
                    
                    if success:
                        logger.info(f"✅ Updated session_info.json with validation completion")
                    else:
                        logger.error(f"❌ Failed to update session_info.json with validation completion")
                except Exception as e:
                    logger.error(f"💥 EXCEPTION in process_excel validation session tracking: {e}")
                    import traceback
                    logger.error(f"💥 TRACEBACK: {traceback.format_exc()}")
            
            # Email the results (since we have unified storage, email final config with results)
            try:
                from email_sender import send_validation_results_email as send_results_email
                send_results_email(email_address, session_id, result['s3_key'], validation_results.get('metadata', {}))
            except Exception as e:
                logger.warning(f"Failed to send results email: {e}")
            
            response_body = {
                'success': True,
                'session_id': session_id,
                'message': 'Validation completed and results emailed',
                'storage_path': storage_manager.get_session_path(email_address, session_id),
                'processing_time': processing_time
            }
            return create_response(200, response_body)
        else:
            logger.error("Full validation failed or returned empty results")
            return create_response(500, {'error': 'Full validation failed'})
            
    except Exception as e:
        logger.error(f"Full validation processing error: {str(e)}")
        return create_response(500, {'error': f'Full validation processing failed: {str(e)}'})

# Handlers for backward compatibility
def handle(request_data, context):
    """Main handler that routes to appropriate processing method"""
    content_type = request_data.get('headers', {}).get('Content-Type', '')
    
    if 'multipart/form-data' in content_type:
        return handle_multipart_form(request_data, context)
    else:
        return handle_json_request(request_data, context)