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
def create_run_record(*args, **kwargs):
    logger.warning("DynamoDB not available - run record not created")

DYNAMODB_AVAILABLE = False

try:
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
    from dynamodb_schemas import update_processing_metrics, track_email_delivery, track_user_request, update_run_status, create_run_record
    DYNAMODB_AVAILABLE = True
    logger.debug("DynamoDB functions imported successfully at module level")
except ImportError as e:
    logger.error(f"Failed to import dynamodb_schemas at module level: {e}")
    # Dummy functions are already defined above

# Global variable for the API Gateway Management client
api_gateway_management_client = None

def _calculate_cost_estimated(token_usage: Dict, metadata: Dict) -> float:
    """
    Calculate estimated cost without caching benefits for projections.
    This estimates what the cost would be if no caching were available.
    
    Args:
        token_usage: Token usage data from validation lambda
        metadata: Additional metadata from validation results
        
    Returns:
        Estimated cost without caching benefits
    """
    try:
        # Extract actual cost and cached call information
        actual_cost = token_usage.get('total_cost', 0.0)
        total_calls = token_usage.get('api_calls', 0)
        cached_calls = token_usage.get('cached_calls', 0)
        
        # If no caching occurred, estimated cost equals actual cost
        if cached_calls == 0 or total_calls == 0:
            logger.debug(f"[COST_CALC] No caching detected - estimated cost equals actual: ${actual_cost:.6f}")
            return actual_cost
        
        # Calculate cache hit rate
        cache_hit_rate = cached_calls / max(1, total_calls)
        non_cached_calls = total_calls - cached_calls
        
        # Estimate cost per non-cached call
        if non_cached_calls > 0:
            cost_per_non_cached_call = actual_cost / non_cached_calls
            # Estimated cost if all calls were non-cached
            estimated_cost = cost_per_non_cached_call * total_calls
            
            logger.debug(f"[COST_CALC] Cache analysis - Hit rate: {cache_hit_rate:.2%}, "
                        f"Cost per call: ${cost_per_non_cached_call:.6f}, "
                        f"Estimated without cache: ${estimated_cost:.6f}")
            
            return estimated_cost
        else:
            # All calls were cached - use average cost estimation
            # This is a fallback case for when cached costs aren't tracked properly
            logger.warning(f"[COST_CALC] All {total_calls} calls were cached - using fallback estimation")
            
            # Fallback: assume average cost per call based on token usage
            total_tokens = token_usage.get('total_tokens', 0)
            if total_tokens > 0:
                # Use rough estimation based on tokens (typical cost per 1000 tokens)
                estimated_cost_per_1k_tokens = 0.003  # Conservative estimate
                estimated_cost = (total_tokens / 1000) * estimated_cost_per_1k_tokens
                return max(actual_cost, estimated_cost)  # Use higher of actual or estimated
            
            return actual_cost  # Final fallback
            
    except Exception as e:
        logger.error(f"[COST_CALC] Error calculating estimated cost without cache: {e}")
        # Fallback to actual cost with small buffer for safety
        return token_usage.get('total_cost', 0.0) * 1.2  # 20% buffer for estimation errors

def _apply_domain_multiplier_with_validation(email: str, base_cost: float, session_id: str = None) -> Dict[str, float]:
    """
    Apply domain multiplier with comprehensive validation and audit logging.
    
    Args:
        email: User email address
        base_cost: Base cost before multiplier
        session_id: Session ID for audit trail
        
    Returns:
        Dictionary with multiplier details and final quoted cost
    """
    try:
        from dynamodb_schemas import get_domain_multiplier
        from decimal import Decimal, ROUND_UP
        
        # Extract domain with validation
        if not email or '@' not in email:
            logger.error(f"[MULTIPLIER_ERROR] Invalid email format: {email}")
            return {
                'multiplier': 1.0,
                'domain': 'invalid',
                'base_cost': base_cost,
                'quoted_cost': max(2.0, math.ceil(base_cost)),  # $2 minimum, rounded up
                'error': 'invalid_email'
            }
        
        domain = email.split('@')[-1].lower().strip()
        if not domain:
            logger.error(f"[MULTIPLIER_ERROR] Empty domain extracted from email: {email}")
            domain = 'unknown'
        
        # Get multiplier with validation
        multiplier = float(get_domain_multiplier(domain))
        
        # Validate multiplier is reasonable
        if multiplier <= 0 or multiplier > 100:  # Sanity check
            logger.error(f"[MULTIPLIER_ERROR] Unreasonable multiplier {multiplier} for domain {domain}")
            multiplier = 5.0  # Default fallback
        
        # Calculate quoted cost with multiplier, rounding, and minimum
        cost_with_multiplier = base_cost * multiplier
        quoted_cost = max(2.0, math.ceil(cost_with_multiplier))  # $2 minimum, rounded up to nearest dollar
        
        # Audit logging
        logger.debug(f"[MULTIPLIER_AUDIT] Domain: {domain}, Base: ${base_cost:.6f}, "
                   f"Multiplier: {multiplier}x, With multiplier: ${cost_with_multiplier:.6f}, "
                   f"Final quoted: ${quoted_cost:.2f}, Session: {session_id}")
        
        return {
            'multiplier': multiplier,
            'domain': domain,
            'base_cost': base_cost,
            'cost_with_multiplier': cost_with_multiplier,
            'quoted_cost': quoted_cost,
            'minimum_applied': quoted_cost == 2.0,
            'rounding_applied': quoted_cost > cost_with_multiplier
        }
        
    except Exception as e:
        logger.error(f"[MULTIPLIER_ERROR] Failed to apply domain multiplier for {email}: {e}")
        # Safe fallback
        return {
            'multiplier': 5.0,  # Default multiplier
            'domain': 'error',
            'base_cost': base_cost,
            'quoted_cost': max(2.0, math.ceil(base_cost * 5.0)),
            'error': str(e)
        }

def _create_fallback_preview_excel(validation_results, config_data, input_filename, is_full=False):
    """Create a basic Excel file using openpyxl when xlsxwriter is not available."""
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill
        from openpyxl.utils import get_column_letter
        
        # Create a new workbook and worksheet
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Validation Results"
        
        # Header styles
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        
        # Get unique column names from validation results
        all_columns = set()
        for result in validation_results:
            all_columns.update(result.keys())
        
        # Sort columns for consistent ordering
        column_list = sorted(list(all_columns))
        
        # Write headers
        for col_idx, column in enumerate(column_list, 1):
            cell = ws.cell(row=1, column=col_idx, value=column)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        
        # Write data rows
        for row_idx, result in enumerate(validation_results, 2):
            for col_idx, column in enumerate(column_list, 1):
                value = result.get(column, "")
                # Handle complex objects by converting to string
                if isinstance(value, (dict, list)):
                    value = str(value)
                ws.cell(row=row_idx, column=col_idx, value=value)
        
        # Adjust column widths
        for col_idx in range(1, len(column_list) + 1):
            column_letter = get_column_letter(col_idx)
            ws.column_dimensions[column_letter].width = 15
        
        # Add metadata sheet
        meta_ws = wb.create_sheet("Metadata")
        meta_ws.append(["Key", "Value"])
        meta_ws.append(["Original File", input_filename])
        meta_ws.append(["Validation Type", "Full Validation" if is_full else "Preview"])
        meta_ws.append(["Timestamp", datetime.now().isoformat()])
        meta_ws.append(["Total Rows", len(validation_results) if validation_results else 0])
        meta_ws.append(["Total Columns", len(column_list)])
        
        if config_data:
            config_version = config_data.get('storage_metadata', {}).get('version', 1)
            meta_ws.append(["Config Version", config_version])
        
        # Save to bytes buffer
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Error creating fallback Excel: {str(e)}")
        return None

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
            logger.debug(f"Converted WebSocket URL to HTTPS endpoint: {endpoint_url}")
        
        # Ensure the endpoint URL includes the stage (prod)
        if not endpoint_url.endswith('/prod'):
            endpoint_url = endpoint_url.rstrip('/') + '/prod'
            logger.debug(f"Added /prod stage to endpoint URL: {endpoint_url}")
        
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
                logger.debug(f"Balance update sent to WebSocket {connection_id}")
        except client.exceptions.GoneException:
            logger.warning(f"WebSocket connection {connection_id} is stale. Removing from DB.")
            remove_websocket_connection(connection_id)
        except Exception as e:
            logger.error(f"Failed to send balance update to WebSocket {connection_id}: {e}")

def _update_progress(session_id: str, status: str, processed_rows: int, verbose_status: str, percent_complete: int, total_rows: int = None, current_batch: int = None, total_batches: int = None):
    """Callback function to update DynamoDB and push WebSocket messages."""
    from dynamodb_schemas import update_run_status, get_connection_by_session, remove_websocket_connection, find_existing_run_key
    
    
    # 1. Update DynamoDB
    run_key = find_existing_run_key(session_id)
    if run_key:
        update_run_status(session_id=session_id, run_key=run_key, status=status,
            processed_rows=processed_rows, verbose_status=verbose_status,
            percent_complete=percent_complete)

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
            from excel_report_qc_unified import create_qc_enhanced_excel_for_interface
            EXCEL_ENHANCEMENT_AVAILABLE = True
        except ImportError:
            try:
                from ..reporting.excel_report_new import create_enhanced_excel_with_validation, EXCEL_ENHANCEMENT_AVAILABLE
                # Fallback function that maps to QC interface
                def create_qc_enhanced_excel_for_interface(table_data, validation_results, config_data, session_id, validated_sheet_name=None):
                    return create_enhanced_excel_with_validation(table_data, validation_results, config_data, session_id, validated_sheet_name)
            except ImportError:
                EXCEL_ENHANCEMENT_AVAILABLE = False
                def create_qc_enhanced_excel_for_interface(*args, **kwargs): return None
        
        try:
            from email_sender import send_validation_results_email
            EMAIL_SENDER_AVAILABLE = True
        except ImportError:
            EMAIL_SENDER_AVAILABLE = False

        logger.info("--- Background Handler Started ---")
        
        # Record when background handler actually starts processing
        background_start_time = datetime.now(timezone.utc).isoformat()
        
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
        email = event.get('email', 'unknown@example.com').lower().strip()
        preview_email = event.get('preview_email', False)
        # Extract parameters early before using them
        try:
            max_rows_str = event.get('max_rows')
            max_rows = int(max_rows_str) if max_rows_str else 1000
            
            batch_size_str = event.get('batch_size')
            batch_size = int(batch_size_str) if batch_size_str else None  # Let enhanced batch manager determine optimal size
        except (ValueError, TypeError):
            logger.warning("Invalid max_rows or batch_size, using defaults.")
            max_rows = 1000
            batch_size = None  # Let enhanced batch manager determine optimal size

        run_key = event.get('run_key')  # Extract run_key from SQS message
        
        # Handle case where run_key is missing (backward compatibility)
        if not run_key:
            logger.warning(f"No run_key found in SQS message for session {session_id}, attempting to find existing run")
            # Try to find existing run record first to avoid duplicates
            try:
                from dynamodb_schemas import find_existing_run_key
                run_key = find_existing_run_key(session_id)
                
                if run_key:
                    logger.debug(f"Found existing run_key for session {session_id}: {run_key}")
                else:
                    # Only create new run record if none exists
                    run_type_initial = "Preview" if is_preview else "Validation"
                    run_key = create_run_record(session_id=session_id, email=email, total_rows=0, batch_size=batch_size or 10, run_type=run_type_initial)
                    logger.debug(f"Created new run_key for backward compatibility: {run_key}")
            except Exception as e:
                logger.error(f"Failed to find/create run_key for backward compatibility: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                run_key = None
        
        # Always use a clean session ID format: session_YYYY-MM-DDTHH_MM_SS_XXXXXX
        # Ensure session ID has proper prefix
        clean_session_id = session_id
        if not clean_session_id.startswith('session_'):
            clean_session_id = f"session_{clean_session_id}"
            
        logger.debug(f"Background handler called for session {session_id}, clean_session_id={clean_session_id}, is_preview={is_preview}")

        email_folder = event.get('email_folder', 'default')
        email_address = event.get('email_address')
        if email_address:
            email_address = email_address.lower().strip()
        
        # Initialize processing_time early to prevent "referenced before assignment" error
        processing_time = 0.0
        
        # Create a wrapper function for run status updates with this session's run_key
        def update_run_status_for_session(**kwargs):
            if run_key:
                try:
                    return update_run_status(session_id=session_id, run_key=run_key, **kwargs)
                except Exception as e:
                    logger.error(f"Failed to update run status for session {session_id}, run_key {run_key}: {e}")
                    logger.error(f"Status update kwargs: {kwargs}")
                    return None
            else:
                logger.warning(f"Skipping run status update due to missing run_key for session {session_id}: {kwargs}")
                return None
        
        # After a job starts
        run_type_initial = "Preview" if is_preview else "Validation"
        update_run_status_for_session(status='PROCESSING', run_type=run_type_initial)

        if is_preview:
            preview_max_rows = event.get('preview_max_rows', 5)
            sequential_call_num = event.get('sequential_call')
            logger.debug(f"Background preview processing for session {session_id}")
            
            # Send initial WebSocket progress update - interface setup range 0-5%
            _send_websocket_message_deduplicated(session_id, {
                'type': 'preview_progress',
                'progress': 1,  # Interface setup: 0-5% range
                'status': f'🚀 Starting preview validation for {preview_max_rows} rows...',
                'session_id': session_id,
                'preview_max_rows': preview_max_rows
            }, "preview_progress_start")
            
            # Initial status update for preview - use 0-5% range for interface setup
            update_run_status_for_session(
                status='PROCESSING', 
                run_type="Preview",
                verbose_status=f"Starting preview for {preview_max_rows} rows...",
                percent_complete=2,  # Interface setup: 0-5% range
                batch_size=preview_max_rows
            )

            # Send file retrieval progress update - interface setup range 0-5%
            _send_websocket_message_deduplicated(session_id, {
                'type': 'preview_progress',
                'progress': 3,  # Interface setup: 0-5% range
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
                
                update_run_status_for_session(
                    status='FAILED',
                    run_type="Preview",
                    verbose_status="Failed to retrieve files for preview.",
                    percent_complete=100,
                    processed_rows=0,
                    batch_size=10,
                    eliyahu_cost=0.0,
                    quoted_validation_cost=0.0,
                    estimated_validation_eliyahu_cost=0.0,
                    time_per_row_seconds=0.0
                )
                return {'statusCode': 500, 'body': json.dumps({'status': 'failed', 'error': 'Files not found'})}
            
            # Send validation start progress update - interface setup complete, AI work begins (5-90% reserved for validation lambda)
            _send_websocket_message_deduplicated(session_id, {
                'type': 'preview_progress',
                'progress': 5,  # Interface setup complete: hand off to validation lambda for 5-90%
                'status': f'🔍 Running AI validation on {preview_max_rows} sample rows...',
                'session_id': session_id
            }, "preview_progress_validation")
            
            # Update start_time to when background handler actually begins validation processing
            if run_key:
                update_run_status_for_session(
                    status='IN_PROGRESS',
                    run_type="Preview",
                    verbose_status=f"Running AI validation on {preview_max_rows} sample rows...",
                    start_time=background_start_time,  # Use background handler start time
                    percent_complete=5
                )
            
            validation_results = invoke_validator_lambda(
                actual_excel_s3_key, actual_config_s3_key, max_rows, batch_size, S3_UNIFIED_BUCKET, VALIDATOR_LAMBDA_NAME,
                preview_first_row=True, preview_max_rows=preview_max_rows, sequential_call=sequential_call_num,
                session_id=session_id
            )
            
            # Send validation completion progress update - interface final processing begins (90-100% range)
            _send_websocket_message_deduplicated(session_id, {
                'type': 'preview_progress',
                'progress': 90,  # Interface final processing: 90-100% range
                'status': '✅ AI validation completed, processing results...',
                'session_id': session_id
            }, "preview_progress_validation_complete")
            
            # Send results processing progress update - interface final processing (90-100% range)
            _send_websocket_message_deduplicated(session_id, {
                'type': 'preview_progress',
                'progress': 92,  # Interface final processing: 90-100% range
                'status': '📊 Analyzing results and generating estimates...',
                'session_id': session_id
            }, "preview_progress_analysis")
            
            # Final status update for preview
            if validation_results and validation_results.get('validation_results'):
                # Extract metadata first
                real_results = validation_results.get('validation_results', {})

                # Extract QC data if present (it's at the top level of validation_results, not in metadata)
                qc_results = validation_results.get('qc_results', {})
                qc_metrics_data = validation_results.get('qc_metrics', {})
                logger.info(f"[QC_DEBUG] Extracted QC data - results: {len(qc_results)} rows, metrics: {qc_metrics_data.get('total_fields_reviewed', 0)} fields reviewed")

                # Merge QC data into real_results for display purposes (QC values take precedence)
                if qc_results:
                    logger.info(f"[QC_MERGE] Merging QC data into preview results for display")
                    logger.info(f"[QC_MERGE_DEBUG] QC results structure: {list(qc_results.keys())[:3]}")
                    logger.info(f"[QC_MERGE_DEBUG] real_results keys sample: {list(real_results.keys())[:3]}")

                    # Create mapping from hash keys (QC) to numeric keys (validation results)
                    # QC uses hash keys, validation results use numeric string keys
                    qc_hash_keys = list(qc_results.keys())
                    validation_numeric_keys = list(real_results.keys())

                    # Map QC hash keys to validation numeric keys by position
                    for i, qc_hash_key in enumerate(qc_hash_keys):
                        if i < len(validation_numeric_keys):
                            validation_key = validation_numeric_keys[i]
                            row_qc_data = qc_results[qc_hash_key]

                            logger.info(f"[QC_MERGE_DEBUG] Mapping QC hash key {qc_hash_key} -> validation key {validation_key}")

                            if validation_key in real_results:
                                logger.info(f"[QC_MERGE_DEBUG] Row {validation_key}: QC fields = {list(row_qc_data.keys())}")
                                for field_name, field_qc_data in row_qc_data.items():
                                    logger.info(f"[QC_MERGE_DEBUG] Field {field_name}: QC data keys = {list(field_qc_data.keys()) if isinstance(field_qc_data, dict) else 'not dict'}")
                                    logger.info(f"[QC_MERGE_DEBUG] Field {field_name}: qc_applied = {field_qc_data.get('qc_applied') if isinstance(field_qc_data, dict) else 'N/A'}")

                                    if isinstance(field_qc_data, dict) and (field_qc_data.get('qc_applied') is True or field_qc_data.get('qc_applied') == 'Yes'):
                                        # Since QC is now comprehensive, always use QC values when available
                                        qc_entry = field_qc_data.get('qc_entry', '')
                                        qc_confidence = field_qc_data.get('qc_confidence', '')
                                        logger.info(f"[QC_MERGE_DEBUG] Field {field_name}: has qc_entry = {bool(qc_entry)}, has qc_confidence = {bool(qc_confidence)}")

                                        # Always use QC entry and confidence when available (comprehensive QC)
                                        if qc_entry and str(qc_entry).strip():
                                            real_results[validation_key][field_name]['value'] = qc_entry
                                            logger.debug(f"[QC_MERGE] {field_name}: Using QC entry value: {qc_entry}")

                                        if qc_confidence and str(qc_confidence).strip():
                                            real_results[validation_key][field_name]['confidence_level'] = qc_confidence
                                            logger.debug(f"[QC_MERGE] {field_name}: Using QC confidence: {qc_confidence}")
                logger.debug(f"[EXCEL_DEBUG] validation_results keys: {list(validation_results.keys())}")
                logger.debug(f"[EXCEL_DEBUG] real_results type: {type(real_results)}, keys: {list(real_results.keys()) if isinstance(real_results, dict) else 'N/A'}")
                if isinstance(real_results, dict) and real_results:
                    sample_key = list(real_results.keys())[0]
                    sample_value = real_results[sample_key]
                    logger.debug(f"[EXCEL_DEBUG] Sample validation entry - Key: {sample_key}, Value type: {type(sample_value)}")
                    if isinstance(sample_value, dict):
                        logger.debug(f"[EXCEL_DEBUG] Sample validation entry - Value keys: {list(sample_value.keys())}")
                        for field_name, field_data in sample_value.items():
                            if isinstance(field_data, dict):
                                logger.debug(f"[EXCEL_DEBUG] Field '{field_name}' - keys: {list(field_data.keys())}")
                                confidence = field_data.get('confidence') or field_data.get('confidence_level')
                                logger.debug(f"[EXCEL_DEBUG] Field '{field_name}' - confidence: {confidence}")
                            break  # Just show one field sample
                total_rows = validation_results.get('total_rows', 1)
                metadata = validation_results.get('metadata', {})
                total_rows_processed = validation_results.get('total_processed_rows', 1)
                token_usage = metadata.get('token_usage', {})
                # Initialize variables early to avoid scope issues
                quoted_full_cost = None
                eliyahu_cost = 0.0
                cost_estimated = 0.0
                multiplier = 1.0
                estimated_time_per_row = 0.0
                total_estimated_processing_time = 0.0
                estimated_total_time_seconds = None
                time_per_row = 0.0
                email_domain = email.split('@')[-1] if '@' in email else 'unknown'
                # ========== ENHANCED AI_API_CLIENT INTEGRATION ==========
                # Extract enhanced cost/time data from validation lambda's ai_client aggregation
                enhanced_metrics = metadata.get('enhanced_metrics', {})
                # validation_metrics is nested inside enhanced_metrics
                validation_metrics = enhanced_metrics.get('validation_metrics', {})
                logger.info(f"[METADATA_DEBUG] enhanced_metrics keys: {list(enhanced_metrics.keys()) if enhanced_metrics else 'None'}")
                logger.info(f"[METADATA_DEBUG] validation_metrics extracted: {validation_metrics}")

                # Log what background handler received from validation lambda (CALL COUNTS DEBUGGING)
                validation_calls_received = {}
                qc_calls_received = 0
                if enhanced_metrics and enhanced_metrics.get('aggregated_metrics'):
                    providers = enhanced_metrics['aggregated_metrics'].get('providers', {})
                    for provider, data in providers.items():
                        if not data.get('is_metadata_only', False):  # Exclude metadata-only providers
                            validation_calls_received[provider] = data.get('calls', 0)
                        else:
                            logger.info(f"[BACKGROUND_HANDLER_RECEIVED] Excluding metadata-only provider '{provider}' with {data.get('calls', 0)} calls")

                if qc_metrics_data:
                    qc_calls_received = qc_metrics_data.get('total_qc_calls', 0)

                logger.info(f"[BACKGROUND_HANDLER_RECEIVED] Received call counts from validation lambda:")
                logger.info(f"[BACKGROUND_HANDLER_RECEIVED]   Validation calls by provider: {validation_calls_received}")
                logger.info(f"[BACKGROUND_HANDLER_RECEIVED]   QC calls total: {qc_calls_received}")
                logger.info(f"[BACKGROUND_HANDLER_RECEIVED]   Grand total calls: {sum(validation_calls_received.values()) + qc_calls_received}")

                # Extract enhanced models parameter from validation response (it's inside enhanced_metrics)
                logger.info(f"[MODELS_DEBUG] metadata keys available: {list(metadata.keys()) if metadata else 'No metadata'}")
                if enhanced_metrics:
                    logger.info(f"[MODELS_DEBUG] enhanced_metrics keys available: {list(enhanced_metrics.keys())}")
                    enhanced_models_parameter = enhanced_metrics.get('enhanced_models_parameter', {})
                else:
                    enhanced_models_parameter = {}
                logger.info(f"[MODELS_DEBUG] enhanced_models_parameter from enhanced_metrics: {list(enhanced_models_parameter.keys()) if enhanced_models_parameter else 'EMPTY'}")
                if enhanced_models_parameter:
                    logger.info(f"[MODELS_DEBUG] enhanced_models_parameter has {len(enhanced_models_parameter)} search groups")

                # DEBUG: Log the exact structure of the received enhanced_metrics
                logger.debug(f"[DATA_FLOW_DEBUG] Received enhanced_metrics structure: {json.dumps(enhanced_metrics, indent=2)}")
                
                # DEBUG: Log what we received from validation lambda
                logger.debug(f"[ENHANCED_DEBUG] enhanced_metrics available: {bool(enhanced_metrics)}")
                if enhanced_metrics:
                    logger.debug(f"[ENHANCED_DEBUG] enhanced_metrics keys: {list(enhanced_metrics.keys())}")
                    logger.debug(f"[ENHANCED_DEBUG] aggregated_metrics available: {bool(enhanced_metrics.get('aggregated_metrics'))}")
                    if enhanced_metrics.get('aggregated_metrics'):
                        aggregated_data = enhanced_metrics['aggregated_metrics']
                        logger.debug(f"[ENHANCED_DEBUG] aggregated_data keys: {list(aggregated_data.keys())}")
                        totals = aggregated_data.get('totals', {})
                        logger.debug(f"[ENHANCED_DEBUG] totals keys: {list(totals.keys())}")
                        logger.debug(f"[ENHANCED_DEBUG] total_cost_actual: {totals.get('total_cost_actual', 'NOT_FOUND')}")
                        logger.debug(f"[ENHANCED_DEBUG] total_cost_estimated: {totals.get('total_cost_estimated', 'NOT_FOUND')}")
                        providers = aggregated_data.get('providers', {})
                        logger.debug(f"[ENHANCED_DEBUG] providers: {list(providers.keys())}")
                else:
                    logger.warning(f"[ENHANCED_DEBUG] No enhanced_metrics found in metadata. Metadata keys: {list(metadata.keys())}")
                
                if enhanced_metrics and enhanced_metrics.get('aggregated_metrics'):
                    # Extract three-tier cost data from enhanced aggregation
                    aggregated_data = enhanced_metrics['aggregated_metrics']
                    totals = aggregated_data.get('totals', {})
                    
                    # Tier 1: Eliyahu Cost (actual cost paid with caching benefits)
                    eliyahu_cost = totals.get('total_cost_actual', 0.0)

                    # Tier 2: Estimated cost without cache (for full validation projections)
                    cost_estimated = totals.get('total_cost_estimated', 0.0)

                    # Extract provider-specific measures
                    providers = aggregated_data.get('providers', {})
                    perplexity_eliyahu_cost = providers.get('perplexity', {}).get('cost_actual', 0.0)
                    anthropic_eliyahu_cost = providers.get('anthropic', {}).get('cost_actual', 0.0)
                    
                    # Use provider sum as fallback if total is wrong (ensures consistency)
                    provider_cost_sum = perplexity_eliyahu_cost + anthropic_eliyahu_cost
                    logger.debug(f"[COST_DEBUG] eliyahu_cost=${eliyahu_cost:.6f}, provider_sum=${provider_cost_sum:.6f}, perplexity=${perplexity_eliyahu_cost:.6f}, anthropic=${anthropic_eliyahu_cost:.6f}")
                    
                    # Use provider sum if it's different from the total (handles both 0 and other mismatches)
                    if provider_cost_sum > 0 and abs(eliyahu_cost - provider_cost_sum) > 0.000001:
                        logger.info(f"[COST_CORRECTION] Using provider sum ${provider_cost_sum:.6f} instead of total ${eliyahu_cost:.6f}")
                        eliyahu_cost = provider_cost_sum
                    
                    # Extract API call counts
                    perplexity_calls = providers.get('perplexity', {}).get('calls', 0)
                    anthropic_calls = providers.get('anthropic', {}).get('calls', 0)
                    
                    # Extract token counts
                    perplexity_tokens = providers.get('perplexity', {}).get('tokens', 0)
                    anthropic_tokens = providers.get('anthropic', {}).get('tokens', 0)
                    
                    # Extract both actual and estimated time data
                    # Actual time (with caching benefits) for reporting what actually happened
                    total_processing_time = totals.get('total_actual_processing_time', 0.0)
                    # Estimated time (without caching) for projecting onto non-cached rows
                    # Use direct calculation over all rows if available, otherwise divide total by rows
                    if 'avg_estimated_row_processing_time' in totals:
                        estimated_time_per_row = totals.get('avg_estimated_row_processing_time')
                        time_calculation_method = "direct calculation over all rows"
                    else:
                        estimated_time_per_row = totals.get('total_estimated_processing_time', 0.0) / max(1, total_rows_processed)
                        time_calculation_method = "total time divided by rows (fallback)"
                    total_estimated_time_seconds = totals.get('total_estimated_processing_time', 0.0)
                    
                    logger.info(f"[ENHANCED_COSTS] Using ai_client aggregated data - Actual: ${eliyahu_cost:.6f}, No cache: ${cost_estimated:.6f}")
                    logger.info(f"[ENHANCED_PROVIDERS] Perplexity: ${perplexity_eliyahu_cost:.6f} ({perplexity_calls} calls), Anthropic: ${anthropic_eliyahu_cost:.6f} ({anthropic_calls} calls)")
                    logger.info(f"[ENHANCED_TIME] Actual time: {total_processing_time:.3f}s, Estimated time per row: {estimated_time_per_row:.3f}s ({time_calculation_method}), Total estimated: {total_estimated_time_seconds:.3f}s")
                    
                    # Debug timing extraction from totals
                    logger.debug(f"[TIME_DEBUG] totals timing keys: {[k for k in totals.keys() if 'time' in k.lower()]}")
                    logger.debug(f"[TIME_DEBUG] total_actual_processing_time from totals: {totals.get('total_actual_processing_time', 'NOT_FOUND')}")
                    logger.debug(f"[TIME_DEBUG] total_estimated_processing_time from totals: {totals.get('total_estimated_processing_time', 'NOT_FOUND')}")
                else:
                    # Fallback to legacy token_usage for backward compatibility
                    eliyahu_cost = token_usage.get('total_cost', 0.0)
                    cost_estimated = _calculate_cost_estimated(token_usage, metadata)
                    
                    # Extract legacy provider-specific data
                    by_provider = token_usage.get('by_provider', {})
                    perplexity_data = by_provider.get('perplexity', {})
                    anthropic_data = by_provider.get('anthropic', {})
                    
                    perplexity_eliyahu_cost = perplexity_data.get('total_cost', 0.0)
                    anthropic_eliyahu_cost = anthropic_data.get('total_cost', 0.0)
                    perplexity_calls = perplexity_data.get('api_calls', 0)
                    anthropic_calls = anthropic_data.get('api_calls', 0) 
                    perplexity_tokens = perplexity_data.get('total_tokens', 0)
                    anthropic_tokens = anthropic_data.get('total_tokens', 0)
                    
                    # Legacy time calculation - assume processing_time is actual time with cache benefits
                    total_processing_time = metadata.get('processing_time', 0.0)  # Actual time
                    total_estimated_time_seconds = total_processing_time * 1.2  # Rough estimate: 20% slower without cache
                    estimated_time_per_row = total_estimated_time_seconds / max(1, total_rows_processed)
                    
                    logger.warning(f"[ENHANCED_COSTS] Falling back to legacy token_usage - enhanced_metrics not available")
                
                # ========== ENHANCED VALIDATION ESTIMATES ==========
                # For both preview and validation operations, use enhanced estimates from ai_api_client
                logger.info(f"[ESTIMATES_CHECK] is_preview: {is_preview}, enhanced_metrics available: {bool(enhanced_metrics)}")
                if enhanced_metrics:
                    logger.info(f"[ESTIMATES_CHECK] enhanced_metrics keys: {list(enhanced_metrics.keys())}")
                    logger.info(f"[ESTIMATES_CHECK] full_validation_estimates available: {bool(enhanced_metrics.get('full_validation_estimates'))}")
                
                if enhanced_metrics and enhanced_metrics.get('full_validation_estimates'):
                    estimates = enhanced_metrics['full_validation_estimates']
                    total_estimates = estimates.get('total_estimates', {})

                    # DEBUG: Log the entire estimates object to see what we're working with
                    logger.debug(f"[ESTIMATES_DEBUG] Full validation estimates object: {json.dumps(estimates, indent=2)}")
                    
                    # Extract batch timing analysis for proper time scaling
                    batch_timing = estimates.get('batch_timing_analysis', {})
                    timing_estimates = estimates.get('timing_estimates', {})
                    per_provider_estimates = estimates.get('per_provider_estimates', {})
                    
                    # Use properly scaled estimates from validation lambda calculations
                    # estimated_validation_eliyahu_cost: Raw eliyahu cost for full table (no multiplier, no cache)
                    # This comes from the validation lambda's scaling: preview_cost * (total_rows / preview_rows)
                    estimated_total_cost_raw = total_estimates.get('estimated_total_cost_estimated', cost_estimated * total_rows / max(1, total_rows_processed))
                    
                    # estimated_validation_time: Use batch-based scaling for accurate time projection
                    # The validation lambda calculates this using proper batch architecture
                    logger.info(f"[TIME_DEBUG] timing_estimates: {timing_estimates}")
                    logger.info(f"[TIME_DEBUG] batch_timing.estimated_total_time_for_full_validation: {batch_timing.get('estimated_total_time_for_full_validation')}")
                    logger.info(f"[TIME_DEBUG] total_estimates.estimated_total_processing_time: {total_estimates.get('estimated_total_processing_time')}")
                    estimated_total_time_seconds = (timing_estimates.get('total_estimated_time_seconds') or
                                                   batch_timing.get('estimated_total_time_for_full_validation') or
                                                   total_estimates.get('estimated_total_processing_time', 0.0))

                    logger.info(f"[TIME_DEBUG] estimated_total_time_seconds: {estimated_total_time_seconds}")
                    logger.info(f"[TIME_DEBUG] Converting to minutes: {estimated_total_time_seconds / 60:.1f} minutes")
                    logger.info(f"[TIME_DEBUG] timing_estimates.total_estimated_time_seconds: {timing_estimates.get('total_estimated_time_seconds', 'NOT_SET')}")
                    logger.info(f"[TIME_DEBUG] batch_timing.estimated_total_time_for_full_validation: {batch_timing.get('estimated_total_time_for_full_validation', 'NOT_SET')}")
                    logger.info(f"[TIME_DEBUG] total_estimates.estimated_total_processing_time: {total_estimates.get('estimated_total_processing_time', 'NOT_SET')}")
                    
                    # Extract per-provider costs from new structure if available
                    if per_provider_estimates:
                        logger.info(f"[ENHANCED_PROVIDER_DATA] Found per-provider estimates: {list(per_provider_estimates.keys())}")
                        
                        # Override provider costs with enhanced data
                        perplexity_data = per_provider_estimates.get('perplexity', {})
                        anthropic_data = per_provider_estimates.get('anthropic', {})
                        
                        if perplexity_data:
                            perplexity_per_row_estimated_cost = perplexity_data.get('per_row_estimated_cost', 0)
                            perplexity_total_actual_cost = perplexity_data.get('total_cost_actual', 0)
                        
                        if anthropic_data:
                            anthropic_per_row_estimated_cost = anthropic_data.get('per_row_estimated_cost', 0)
                            anthropic_total_actual_cost = anthropic_data.get('total_cost_actual', 0)
                    
                    # Debug: Log what we actually received
                    logger.debug(f"[ENHANCED_ESTIMATES_DEBUG] batch_timing keys: {list(batch_timing.keys())}")
                    logger.debug(f"[ENHANCED_ESTIMATES_DEBUG] total_estimates keys: {list(total_estimates.keys())}")
                    logger.debug(f"[ENHANCED_ESTIMATES_DEBUG] estimated_total_time_for_full_validation: {batch_timing.get('estimated_total_time_for_full_validation', 'NOT_FOUND')}")
                    logger.debug(f"[ENHANCED_ESTIMATES_DEBUG] estimated_total_cost_estimated: {total_estimates.get('estimated_total_cost_estimated', 'NOT_FOUND')}")
                    
                    logger.info(f"[ENHANCED_ESTIMATES] ✅ Using ai_client full validation estimates:")
                    logger.info(f"  - Eliyahu cost (no cache, scaled): ${estimated_total_cost_raw:.6f}")
                    logger.info(f"  - Validation time (batch-based): {estimated_total_time_seconds:.3f}s ({estimated_total_time_seconds/60:.1f} minutes)")
                    logger.info(f"  - Batch analysis: {batch_timing.get('estimated_batches_for_full_table', 0)} estimated batches")
                    logger.info(f"  - Preview batch size: {batch_timing.get('preview_average_batch_size', 'N/A')}")
                    logger.info(f"  - Target batch size: {batch_timing.get('target_full_validation_batch_size', 'N/A')}")
                    logger.info(f"  - Avg batch time: {batch_timing.get('estimated_time_per_batch', 0):.3f}s")
                else:
                    # Fallback to manual scaling calculations for non-preview or legacy data
                    estimated_total_cost_raw = None  # Will be calculated later in manual scaling section
                    estimated_total_time_seconds = None  # Will be calculated later in manual scaling section
                    logger.info(f"[ENHANCED_ESTIMATES] ❌ No enhanced estimates available - will use manual scaling")

                # Validate cost calculations
                if eliyahu_cost < 0 or cost_estimated < 0:
                    logger.error(f"[COST_ERROR] Invalid negative costs - Actual: ${eliyahu_cost:.6f}, Estimated: ${cost_estimated:.6f}")
                    eliyahu_cost = max(0.0, eliyahu_cost)
                    cost_estimated = max(0.0, cost_estimated)
                
                if eliyahu_cost > cost_estimated:
                    logger.warning(f"[COST_WARNING] Actual cost ${eliyahu_cost:.6f} > estimated ${cost_estimated:.6f} - possible pricing issue")
                
                logger.debug(f"[COST_DEBUG] Three-tier costs - Actual: ${eliyahu_cost:.6f}, Estimated: ${cost_estimated:.6f}")
                total_tokens = token_usage.get('total_tokens', 0)
                total_api_calls = token_usage.get('api_calls', 0)
                total_cached_calls = token_usage.get('cached_calls', 0)
                logger.info(f"[METADATA_DEBUG] metadata keys: {list(metadata.keys()) if metadata else 'None'}")
                logger.info(f"[METADATA_DEBUG] Looking for validation_metrics in metadata")
                
                # Initialize balance variables (preview doesn't charge)
                initial_balance = 0
                final_balance = 0
                multiplier = 1.0
                charged_cost = 0.0  # Preview is free
                
                # ========== HARDENED DOMAIN MULTIPLIER SYSTEM ==========
                # Apply domain multiplier with comprehensive validation and audit trail
                try:
                    import sys
                    import os
                    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
                    from dynamodb_schemas import track_preview_cost, track_api_usage_detailed, check_user_balance
                    from decimal import Decimal
                    
                    # Use scaled eliyahu cost for multiplier calculation if available, otherwise preview cost
                    cost_for_multiplier = estimated_total_cost_raw if estimated_total_cost_raw is not None else cost_estimated
                    
                    logger.debug(f"[MULTIPLIER_DEBUG] Calling _apply_domain_multiplier_with_validation with cost: ${cost_for_multiplier:.6f}")
                    logger.debug(f"[MULTIPLIER_DEBUG] - Using {'scaled eliyahu cost' if estimated_total_cost_raw is not None else 'preview cost'}")
                    multiplier_result = _apply_domain_multiplier_with_validation(email, cost_for_multiplier, session_id)
                    multiplier = multiplier_result['multiplier']
                    domain = multiplier_result['domain']
                    
                    # Cost with multiplier and business logic applied (what user will pay)
                    cost_with_multiplier = multiplier_result['cost_with_multiplier']
                    quoted_full_cost = multiplier_result['quoted_cost']
                    
                    logger.debug(f"[MULTIPLIER_DEBUG] Domain multiplier result: domain={domain}, multiplier={multiplier}, "
                              f"cost_with_multiplier=${cost_with_multiplier:.6f}, quoted_cost=${quoted_full_cost:.2f}")
                    
                    # Validation and audit logging
                    if 'error' in multiplier_result:
                        logger.error(f"[MULTIPLIER_ERROR] Preview domain multiplier error: {multiplier_result['error']}")
                    
                    logger.debug(f"[COST_AUDIT] Preview processed {total_rows_processed} rows - "
                               f"Preview actual: ${eliyahu_cost:.6f}, Preview estimated: ${cost_estimated:.6f}, "
                               f"Scaled eliyahu cost: ${cost_for_multiplier:.6f}, "
                               f"Domain: {domain}, Multiplier: {multiplier}x, Quoted: ${quoted_full_cost:.2f}")
                    
                    # Get account balance for tracking (no charges for preview)
                    initial_balance = check_user_balance(email)
                    final_balance = initial_balance  # No change for preview
                    balance_error_occurred = False  # Preview doesn't charge
                    charged_amount = 0  # No charges for preview
                    
                    # Track preview cost (actual cost for your tracking, estimated cost for user display)
                    track_preview_cost(session_id, email, Decimal(str(cost_estimated)), Decimal(str(multiplier)), total_tokens)
                    
                    # Provider tracking now handled by enhanced metrics from ai_client
                    logger.info(f"[ENHANCED_METRICS] Preview provider metrics tracked in enhanced data structure")
                            
                    
                except Exception as e:
                    logger.error(f"Error applying domain multiplier in preview: {e}")
                    multiplier = 1.0
                    # Fallback if multiplier lookup fails - apply default multiplier properly
                    fallback_cost_with_multiplier = cost_estimated * multiplier
                    quoted_full_cost = max(2.0, math.ceil(fallback_cost_with_multiplier))
                    logger.warning(f"[MULTIPLIER_FALLBACK] Using fallback multiplier {multiplier} -> quoted_cost: ${quoted_full_cost:.2f}")
                
                # ========== SIMPLIFIED TIME/BATCH CALCULATIONS ==========
                # Extract simple batch/timing info for backward compatibility
                # All cost calculations now come from enhanced ai_client data
                
                # Get basic processing time for backward compatibility
                processing_time = total_estimated_processing_time if total_estimated_processing_time > 0 else metadata.get('processing_time', 0.0)
                
                # Simple batch size extraction for display purposes
                effective_batch_size = batch_size or 50  # Use configured or default
                per_model_batch_stats = metadata.get('per_model_batch_stats', {})
                if per_model_batch_stats:
                    actual_batch_sizes = per_model_batch_stats.get('model_batch_sizes', {})
                    if actual_batch_sizes:
                        effective_batch_size = min(actual_batch_sizes.values())
                
                # Simple fallback time estimates if enhanced data not available
                if estimated_total_time_seconds is None:
                    # Use simple per-row calculation
                    time_per_row_fallback = processing_time / max(1, total_rows_processed)
                    estimated_total_time_seconds = time_per_row_fallback * total_rows
                
                # Calculate time per row for full validation (time_per_row_seconds field)
                # First try to get from enhanced timing estimates, then fall back to calculation
                logger.info(f"[TIME_DEBUG_FINAL] Final estimated_total_time_seconds before payload: {estimated_total_time_seconds}")
                if estimated_total_time_seconds:
                    logger.info(f"[TIME_DEBUG_FINAL] Will be converted to minutes: {estimated_total_time_seconds / 60:.1f}")
                else:
                    logger.info(f"[TIME_DEBUG_FINAL] Will be converted to minutes: None")
                if enhanced_metrics and enhanced_metrics.get('full_validation_estimates'):
                    timing_estimates = enhanced_metrics['full_validation_estimates'].get('timing_estimates', {})
                    time_per_row = timing_estimates.get('time_per_row_seconds', 0.0)
                    if time_per_row == 0.0:
                        time_per_row = estimated_total_time_seconds / max(1, total_rows) if estimated_total_time_seconds and total_rows else 0.0
                else:
                    time_per_row = estimated_total_time_seconds / max(1, total_rows) if estimated_total_time_seconds and total_rows else 0.0
                
                # Simple batch count for display
                total_batches = math.ceil(total_rows / effective_batch_size) if effective_batch_size > 0 else 1
                
                logger.info(f"[SIMPLIFIED_TIMING] Processing time: {processing_time:.3f}s, Est. total: {estimated_total_time_seconds:.3f}s")
                logger.info(f"[SIMPLIFIED_BATCH] Batch size: {effective_batch_size}, Total batches: {total_batches}")
                
                # All cost/time calculations now come from enhanced estimates - no manual scaling
                if estimated_total_cost_raw is None:
                    logger.warning(f"[ENHANCED_DATA] Missing estimated_total_cost_raw from enhanced estimates - using fallback")
                    scaling_factor = total_rows / max(1, total_rows_processed)
                    estimated_total_cost_raw = cost_estimated * scaling_factor
                    logger.debug(f"[SCALING_DEBUG] Manual scaling: ${cost_estimated:.6f} × ({total_rows}/{total_rows_processed}) = ${estimated_total_cost_raw:.6f}")
                
                # Quoted cost comes from enhanced estimates with business logic applied
                if quoted_full_cost is None:
                    logger.warning(f"[ENHANCED_DATA] Missing quoted_full_cost from enhanced estimates - applying business logic")
                    raw_quoted_cost = cost_estimated * multiplier * (total_rows / max(1, total_rows_processed))
                    quoted_full_cost = max(2.0, math.ceil(raw_quoted_cost))  # Add $2 minimum charge, rounded up
                    logger.info(f"[ENHANCED_DATA] Calculated fallback quoted_full_cost: ${quoted_full_cost:.2f} (base: ${cost_estimated:.6f}, multiplier: {multiplier}, scaling: {total_rows}/{total_rows_processed})")
                
                estimated_total_tokens = total_tokens * (total_rows / max(1, total_rows_processed))
                
                # DEBUG: Log enhanced cost data
                logger.info(f"[ENHANCED_COST] Final estimates:")
                logger.info(f"[ENHANCED_COST]   eliyahu_cost: ${eliyahu_cost:.6f}")
                logger.info(f"[ENHANCED_COST]   estimated_total_cost_raw: ${estimated_total_cost_raw:.6f}")
                logger.info(f"[ENHANCED_COST]   quoted_full_cost (with business logic): ${quoted_full_cost:.2f}")
                logger.info(f"[ENHANCED_COST]   estimated_total_time_seconds: {estimated_total_time_seconds:.3f}s")

                # Get the most recent account balance right before calculating sufficient_balance
                # This ensures we capture any recent credit additions from the frontend
                logger.info(f"[BALANCE_CHECK] Refreshing balance for {email} before sufficient_balance calculation")
                current_balance = check_user_balance(email)
                logger.info(f"[BALANCE_CHECK] Current balance: {current_balance}, Quoted full cost: {quoted_full_cost}")

                # Create the markdown table for the response
                markdown_table = create_markdown_table_from_results(real_results, 3, actual_config_s3_key, S3_UNIFIED_BUCKET, qc_results)
                
                preview_payload = {
                    "status": "COMPLETED", "session_id": session_id,
                    "markdown_table": markdown_table, "total_rows": total_rows,
                    "total_processed_rows": total_rows_processed,
                    "preview_processing_time": processing_time,
                    "estimated_total_processing_time": estimated_total_time_seconds,
                    "estimated_validation_time_minutes": round(estimated_total_time_seconds / 60, 1),
                    "actual_batch_size": effective_batch_size,
                    "estimated_validation_batches": total_batches,
                    "cost_estimates": {
                        "preview_cost": charged_cost,  # What user pays for preview (0)
                        "preview_tokens": total_tokens,
                        "estimated_total_tokens": estimated_total_tokens,
                        "per_row_time": time_per_row
                    },
                    "token_usage": token_usage,
                    "validation_metrics": validation_metrics,
                    "account_info": {
                        "current_balance": float(current_balance) if current_balance else 0,
                        "sufficient_balance": float(current_balance) >= quoted_full_cost if current_balance else False,
                        "credits_needed": max(0, quoted_full_cost - (float(current_balance) if current_balance else 0)),
                        "domain_multiplier": float(multiplier),
                        "email_domain": email_domain
                    }
                }
                
                # Extract provider costs and totals: per-row estimated costs and total run actual costs
                perplexity_per_row_estimated_cost = 0
                anthropic_per_row_estimated_cost = 0
                perplexity_total_actual_cost = 0
                anthropic_total_actual_cost = 0
                totals = {}  # Initialize totals for use later
                
                if enhanced_metrics and enhanced_metrics.get('aggregated_metrics'):
                    providers = enhanced_metrics['aggregated_metrics'].get('providers', {})
                    totals = enhanced_metrics['aggregated_metrics'].get('totals', {})  # Extract totals here
                    
                    # Extract per-row ESTIMATED costs (what it would cost per row without caching)
                    if total_rows_processed > 0:
                        perplexity_per_row_estimated_cost = providers.get('perplexity', {}).get('cost_estimated', 0) / total_rows_processed
                        anthropic_per_row_estimated_cost = providers.get('anthropic', {}).get('cost_estimated', 0) / total_rows_processed
                    
                    # Extract total run ACTUAL costs (what was actually paid for the entire run)
                    perplexity_total_actual_cost = providers.get('perplexity', {}).get('cost_actual', 0)
                    anthropic_total_actual_cost = providers.get('anthropic', {}).get('cost_actual', 0)
                else:
                    # Fallback to legacy token_usage if enhanced data not available
                    by_provider = token_usage.get('by_provider', {})
                    perplexity_data = by_provider.get('perplexity', {})
                    anthropic_data = by_provider.get('anthropic', {})
                    
                    # Legacy calculation
                    perplexity_total_actual_cost = float(perplexity_data.get('total_cost', 0))
                    anthropic_total_actual_cost = float(anthropic_data.get('total_cost', 0))
                    perplexity_per_row_estimated_cost = perplexity_total_actual_cost / total_rows_processed if total_rows_processed > 0 else 0
                    anthropic_per_row_estimated_cost = anthropic_total_actual_cost / total_rows_processed if total_rows_processed > 0 else 0
                    
                    # Create fallback totals for legacy path
                    totals = {
                        'total_cost_estimated': perplexity_total_actual_cost + anthropic_total_actual_cost,
                        'total_calls': perplexity_data.get('calls', 0) + anthropic_data.get('calls', 0)
                    }
                
                # Add provider costs to cost_estimates
                preview_payload['cost_estimates']['perplexity_per_row_estimated_cost'] = perplexity_per_row_estimated_cost  # Per-row cost without caching
                preview_payload['cost_estimates']['anthropic_per_row_estimated_cost'] = anthropic_per_row_estimated_cost  # Per-row cost without caching
                preview_payload['cost_estimates']['perplexity_total_actual_cost'] = perplexity_total_actual_cost  # Total actual cost paid for entire run
                preview_payload['cost_estimates']['anthropic_total_actual_cost'] = anthropic_total_actual_cost  # Total actual cost paid for entire run
                
                # Add enhanced timing data if available
                if enhanced_metrics and enhanced_metrics.get('full_validation_estimates'):
                    timing_estimates = enhanced_metrics['full_validation_estimates'].get('timing_estimates', {})
                    
                    # Add timing fields to cost_estimates for frontend
                    preview_payload['cost_estimates']['actual_processing_time_seconds'] = timing_estimates.get('actual_processing_time_seconds', 0.0)
                    preview_payload['cost_estimates']['actual_time_per_batch_seconds'] = timing_estimates.get('actual_time_per_batch_seconds', 0.0)
                    
                    logger.info(f"[ENHANCED_TIMING] Added timing data - processing: {timing_estimates.get('actual_processing_time_seconds', 0):.3f}s, "
                               f"per batch: {timing_estimates.get('actual_time_per_batch_seconds', 0):.3f}s")
                
                # Add key frontend-expected fields to cost_estimates object (frontend looks for them here)
                preview_payload['cost_estimates'].update({
                    "quoted_validation_cost": quoted_full_cost,  # What user will pay for full validation (rounded up)
                    "estimated_validation_eliyahu_cost": estimated_total_cost_raw,  # Raw eliyahu cost estimate for full table (no multiplier)
                    "estimated_total_processing_time": estimated_total_time_seconds,  # Keep for backward compatibility
                    "estimated_validation_time": estimated_total_time_seconds, # Explicitly pass the full validation time estimate
                    "total_provider_cost_estimated": totals.get('total_cost_estimated', 0.0),  # Total estimated cost across all providers
                    "total_provider_calls": totals.get('total_calls', 0) + qc_metrics_data.get('total_qc_calls', 0) if qc_metrics_data else totals.get('total_calls', 0)  # Total calls including QC
                })
                
                # Add fields at top level for backward compatibility and easy access
                preview_payload.update({
                    "quoted_validation_cost": quoted_full_cost,  # What user will pay for full validation (rounded up)
                    "estimated_validation_eliyahu_cost": estimated_total_cost_raw  # Raw eliyahu cost estimate for full table (no multiplier)
                })
                
                # Generate enhanced Excel download link and add to preview payload
                enhanced_download_url = None
                logger.info("Generating enhanced Excel for preview mode")
                
                try:
                    # Get excel content and config for enhanced Excel generation
                    from ..core.unified_s3_manager import UnifiedS3Manager
                    storage_manager = UnifiedS3Manager()
                    excel_content, excel_s3_key = storage_manager.get_excel_file(email, clean_session_id)
                    config_data, config_s3_key = storage_manager.get_latest_config(email, clean_session_id)
                    
                    if excel_content and config_data:
                        input_filename = excel_s3_key.split('/')[-1]
                        
                        # Calculate summary data for potential email
                        all_fields = set()
                        confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
                        original_confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
                        
                        for row_data in real_results.values():
                            for field_name, field_data in row_data.items():
                                if isinstance(field_data, dict):
                                    all_fields.add(field_name)
                                    
                                    # Count updated confidence levels
                                    if 'confidence_level' in field_data:
                                        conf_level = field_data.get('confidence_level', 'UNKNOWN')
                                        if conf_level in confidence_counts:
                                            confidence_counts[conf_level] += 1
                                    
                                    # Count original confidence levels
                                    if 'original_confidence' in field_data:
                                        original_conf = field_data.get('original_confidence')
                                        if original_conf and str(original_conf).upper() in original_confidence_counts:
                                            original_confidence_counts[str(original_conf).upper()] += 1
                        
                        # Create enhanced Excel if available
                        enhanced_excel_content = None
                        
                        if EXCEL_ENHANCEMENT_AVAILABLE:
                            try:
                                # Use shared_table_parser to get structured data
                                from shared_table_parser import S3TableParser
                                table_parser = S3TableParser()
                                table_data = table_parser.parse_s3_table(S3_UNIFIED_BUCKET, excel_s3_key)
                                validated_sheet = table_data.get('metadata', {}).get('sheet_name') if isinstance(table_data, dict) else None
                                
                                excel_buffer = create_qc_enhanced_excel_for_interface(
                                    table_data, validation_results, config_data, session_id, validated_sheet_name=validated_sheet
                                )
                                
                                if excel_buffer:
                                    enhanced_excel_content = excel_buffer.getvalue()
                                else:
                                    logger.error("Enhanced Excel creation failed - excel_buffer is None")
                            except Exception as e:
                                logger.error(f"Error creating enhanced Excel for preview: {str(e)}")
                                import traceback
                                logger.error(traceback.format_exc())
                        else:
                            # Fallback: Create basic Excel using openpyxl when xlsxwriter is not available
                            try:
                                logger.debug("[DEBUG] xlsxwriter not available, creating fallback Excel using openpyxl")
                                enhanced_excel_content = _create_fallback_preview_excel(real_results, config_data, input_filename)
                                logger.debug(f"[DEBUG] Fallback Excel created. Size: {len(enhanced_excel_content) if enhanced_excel_content else 0} bytes")
                            except Exception as e:
                                logger.error(f"Error creating fallback Excel for preview: {str(e)}")
                                import traceback
                                logger.error(traceback.format_exc())
                        
                        # Store enhanced Excel in versioned results folder and create download link
                        logger.debug(f"[DEBUG] About to store enhanced Excel. enhanced_excel_content size: {len(enhanced_excel_content) if enhanced_excel_content else 0}")
                        if enhanced_excel_content:
                            try:
                                # Get version from config
                                config_version = config_data.get('storage_metadata', {}).get('version', 1)
                                enhanced_filename = f"{os.path.splitext(input_filename)[0]}_v{config_version}_preview_enhanced.xlsx"
                                logger.debug(f"[DEBUG] Storing enhanced Excel with filename: {enhanced_filename}")
                                
                                # Store enhanced Excel in versioned results folder
                                enhanced_result = storage_manager.store_enhanced_files(
                                    email, clean_session_id, config_version, 
                                    enhanced_excel_content, None
                                )
                                
                                if enhanced_result['success']:
                                    logger.debug(f"[DEBUG] Enhanced Excel stored in results folder: {enhanced_result['stored_files']}")
                                    
                                    # Also create public download link for immediate download
                                    enhanced_download_url = storage_manager.create_public_download_link(
                                        enhanced_excel_content, 
                                        enhanced_filename,
                                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                                    )
                                    logger.debug(f"[DEBUG] Enhanced Excel download link created successfully: {enhanced_download_url}")
                                else:
                                    logger.error(f"[DEBUG] Failed to store enhanced Excel in results folder: {enhanced_result.get('error')}")
                                    enhanced_download_url = None
                                    
                            except Exception as e:
                                logger.error(f"Failed to store enhanced Excel: {e}")
                                import traceback
                                logger.error(traceback.format_exc())
                        else:
                            logger.error("[DEBUG] No enhanced Excel content available - cannot store or create download link")
                except Exception as e:
                    logger.error(f"Error during enhanced Excel generation for preview: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

                # Add enhanced Excel download URL to preview payload
                preview_payload["enhanced_download_url"] = enhanced_download_url
                logger.debug(f"[DEBUG] Added enhanced_download_url to preview_payload: {enhanced_download_url}")
                
                # Get account balance and multiplier for preview tracking
                try:
                    import sys
                    import os
                    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
                    from dynamodb_schemas import check_user_balance, get_domain_multiplier
                    
                    current_balance = check_user_balance(email)
                    email_domain = email.split('@')[-1] if '@' in email else 'unknown'
                    multiplier = float(get_domain_multiplier(email_domain))
                except Exception as e:
                    logger.warning(f"Could not get account info for preview: {e}")
                    current_balance = None
                    multiplier = 1.0
                
                # Create search group models tracking string for preview - one entry per search group with validated columns count
                search_groups_models = []
                search_groups_count = validation_metrics.get('search_groups_count', 0)
                enhanced_context_groups = validation_metrics.get('high_context_search_groups_count', 0)
                claude_groups = validation_metrics.get('claude_search_groups_count', 0)
                regular_perplexity_groups = search_groups_count - enhanced_context_groups - claude_groups
                validated_columns_count = validation_metrics.get('validated_columns_count', 0)
                
                # Count actual validation targets per search group from config
                validation_targets = config_data.get('validation_targets', [])
                columns_per_search_group = {}
                
                # Count validation targets assigned to each search group (excluding ID and IGNORED)
                for target in validation_targets:
                    importance = target.get('importance', '').upper()
                    if importance not in ["ID", "IGNORED"]:
                        search_group_id = target.get('search_group', 0)
                        columns_per_search_group[search_group_id] = columns_per_search_group.get(search_group_id, 0) + 1
                
                # Build search group models by iterating through actual search groups in config
                search_groups_list = config_data.get('search_groups', [])
                anthropic_default_web_searches = config_data.get('anthropic_max_web_searches_default', 3)
                
                # Iterate through each search group to get exact models and settings
                for search_group in search_groups_list:
                    # Process ALL search groups defined in config, not just those with validation targets
                    # This ensures we capture models like claude-sonnet-4-0 even if they're in groups without validation targets
                    
                    search_group_id = search_group.get('group_id', 0)
                    columns_for_this_group = columns_per_search_group.get(search_group_id, 0)
                    model = search_group.get('model', 'sonar-pro')
                    search_context = search_group.get('search_context', 'low')
                    
                    # Build model display name
                    if 'claude' in model.lower() or 'anthropic' in model.lower():
                        # Get anthropic_max_web_searches from this specific search group, or fall back to default
                        max_web_searches = search_group.get('anthropic_max_web_searches', anthropic_default_web_searches)
                        if search_context == 'high':
                            model_display = f"{model} ({max_web_searches}) (high context) X {columns_for_this_group}"
                        else:
                            model_display = f"{model} ({max_web_searches}) X {columns_for_this_group}"
                    else:
                        # Perplexity models
                        if search_context == 'high':
                            model_display = f"{model} (high context) X {columns_for_this_group}"
                        else:
                            model_display = f"{model} X {columns_for_this_group}"
                    
                    search_groups_models.append(model_display)
                
                # Get configuration ID for tracking
                configuration_id = config_data.get('storage_metadata', {}).get('config_id', 'unknown')
                if not configuration_id or configuration_id == 'unknown':
                    # Fallback to generation metadata
                    configuration_id = config_data.get('generation_metadata', {}).get('config_id', 'unknown')
                
                # Extract consolidated fields from preview payload
                logger.info(f"[TIME_SAVE_DEBUG] preview_payload keys: {list(preview_payload.keys())}")
                logger.info(f"[TIME_SAVE_DEBUG] estimated_validation_time_minutes in preview_payload: {preview_payload.get('estimated_validation_time_minutes', 'NOT_FOUND')}")

                eliyahu_cost = preview_payload.get('cost_estimates', {}).get('preview_cost', 0.0)  # Actual cost incurred
                quoted_validation_cost_value = preview_payload.get('cost_estimates', {}).get('quoted_validation_cost', 0.0)  # What user will pay for full
                estimated_validation_eliyahu_cost_value = preview_payload.get('cost_estimates', {}).get('estimated_validation_eliyahu_cost', 0.0)  # Raw eliyahu cost estimate
                time_per_row = preview_payload.get('cost_estimates', {}).get('per_row_time', 0.0)  # Time per row estimate
                estimated_time_minutes = preview_payload.get('estimated_validation_time_minutes', 0.0)  # Total estimated time in minutes

                logger.info(f"[TIME_SAVE_DEBUG] extracted estimated_time_minutes: {estimated_time_minutes}")
                logger.info(f"[TIME_SAVE_DEBUG] Conversion check: {estimated_time_minutes} minutes = {estimated_time_minutes * 60:.1f} seconds")
                logger.info(f"[TIME_SAVE_DEBUG] Source estimated_total_time_seconds was: {preview_payload.get('estimated_total_processing_time', 'NOT_IN_PAYLOAD')}")

                # Debug total_provider_calls calculation
                total_validation_calls = 0
                total_qc_calls = 0
                if enhanced_metrics and enhanced_metrics.get('aggregated_metrics'):
                    providers = enhanced_metrics['aggregated_metrics'].get('providers', {})
                    for provider, data in providers.items():
                        # QC is tracked separately in qc_metrics_data, exclude QC_Costs provider
                        if provider != 'QC_Costs':
                            total_validation_calls += data.get('calls', 0)
                    logger.info(f"[PROVIDER_CALLS_DEBUG] From enhanced_metrics - validation_calls: {total_validation_calls}")
                else:
                    # Fallback to token_usage
                    for provider in ['perplexity', 'anthropic']:
                        provider_data = token_usage.get('by_provider', {}).get(provider, {})
                        total_validation_calls += provider_data.get('api_calls', 0)
                    logger.info(f"[PROVIDER_CALLS_DEBUG] From token_usage - validation_calls: {total_validation_calls}")

                # Add QC calls from qc_metrics_data
                if qc_metrics_data:
                    qc_calls_from_metrics = qc_metrics_data.get('total_qc_calls', 0)
                    logger.info(f"[PROVIDER_CALLS_DEBUG] QC calls from qc_metrics_data: {qc_calls_from_metrics}")
                    total_qc_calls = max(total_qc_calls, qc_calls_from_metrics)  # Use max to avoid double-counting

                # Calculate grand total (QC calls now included in validation_calls via anthropic provider)
                total_provider_calls_override = total_validation_calls
                logger.info(f"[PROVIDER_CALLS_DEBUG] TOTAL calls (QC included in validation): {total_provider_calls_override}, QC calls (debug): {total_qc_calls}")
                batch_size_used = preview_payload.get('actual_batch_size', 10)  # Actual batch size used for preview
                
                # Use enhanced provider metrics from ai_client aggregation if available
                provider_metrics_for_db = {}
                total_rows_processed = len(validation_results.get('validation_results', {})) if validation_results else 1
                
                if enhanced_metrics and enhanced_metrics.get('aggregated_metrics'):
                    # Use properly aggregated enhanced metrics from validation lambda
                    providers = enhanced_metrics['aggregated_metrics'].get('providers', {})

                    for provider, provider_data in providers.items():
                        # Skip QC_Costs as it's now in separate qc_metrics field
                        if provider == 'QC_Costs':
                            continue
                        provider_metrics_for_db[provider] = {
                            'calls': provider_data.get('calls', 0),
                            'tokens': provider_data.get('tokens', 0),
                            'cost_actual': provider_data.get('cost_actual', 0.0),
                            'cost_estimated': provider_data.get('cost_estimated', 0.0),
                            'processing_time': provider_data.get('time_actual', 0.0),
                            'cache_hit_tokens': provider_data.get('cache_hit_tokens', 0),
                            'cost_per_row_actual': provider_data.get('cost_actual', 0.0) / total_rows_processed if total_rows_processed > 0 else 0,
                            'cost_per_row_estimated': provider_data.get('cost_estimated', 0.0) / total_rows_processed if total_rows_processed > 0 else 0,
                            'time_per_row_actual': provider_data.get('time_actual', 0.0) / total_rows_processed if total_rows_processed > 0 else 0,
                            'time_per_row_estimated': provider_data.get('time_estimated', 0.0) / total_rows_processed if total_rows_processed > 0 else 0,
                            'cache_efficiency_percent': provider_data.get('cache_efficiency_percent', 0.0)
                        }
                    
                    logger.info(f"[PROVIDER_METRICS] Using enhanced aggregated metrics for provider_metrics_for_db")

                # Create separate QC metrics for database (not mixed with providers)
                qc_metrics_for_db = {}
                if qc_metrics_data:
                    # Calculate per-row QC metrics similar to provider metrics
                    qc_rows_processed = qc_metrics_data.get('total_rows_processed', total_rows_processed)
                    qc_cost_actual = qc_metrics_data.get('total_qc_cost', 0.0)
                    qc_cost_estimated = qc_metrics_data.get('total_qc_cost_estimated', 0.0)
                    qc_time_actual = qc_metrics_data.get('total_qc_time_actual', 0.0)
                    qc_time_estimated = qc_metrics_data.get('total_qc_time_estimated', 0.0)

                    qc_metrics_for_db = {
                        'enabled': True,
                        'total_fields_reviewed': qc_metrics_data.get('total_fields_reviewed', 0),
                        'total_fields_modified': qc_metrics_data.get('total_fields_modified', 0),
                        'total_qc_cost': qc_cost_actual,
                        'total_qc_cost_estimated': qc_cost_estimated,
                        'total_qc_calls': qc_metrics_data.get('total_qc_calls', 0),
                        'total_qc_tokens': qc_metrics_data.get('total_qc_tokens', 0),
                        'qc_models_used': qc_metrics_data.get('qc_models_used', []),
                        'confidence_lowered_count': qc_metrics_data.get('confidence_lowered_count', 0),
                        'values_replaced_count': qc_metrics_data.get('values_replaced_count', 0),
                        # Add per-row metrics
                        'cost_per_row_actual': qc_cost_actual / qc_rows_processed if qc_rows_processed > 0 else 0.0,
                        'cost_per_row_estimated': qc_cost_estimated / qc_rows_processed if qc_rows_processed > 0 else 0.0,
                        'time_actual': qc_time_actual,
                        'time_estimated': qc_time_estimated,
                        'time_per_row_actual': qc_time_actual / qc_rows_processed if qc_rows_processed > 0 else 0.0,
                        'time_per_row_estimated': qc_time_estimated / qc_rows_processed if qc_rows_processed > 0 else 0.0,
                        # Add qc_by_column if available
                        'qc_by_column': qc_metrics_data.get('qc_by_column', {})
                    }
                    logger.info(f"[QC_METRICS] Created QC metrics for DB with qc_by_column: {len(qc_metrics_for_db.get('qc_by_column', {}))} columns")

                # The models field already contains all validation model info via enhanced_models_parameter
                # QC model info is in qc_metrics_for_db['qc_models_used']
                logger.info(f"[MODELS_SUMMARY] Validation models in enhanced_models_parameter: {len(enhanced_models_parameter)} search groups")
                if qc_metrics_for_db:
                    logger.info(f"[QC_MODELS] QC models used: {qc_metrics_for_db.get('qc_models_used', [])}")
                else:
                    # Fallback to legacy token_usage conversion
                    by_provider = token_usage.get('by_provider', {})
                    
                    for provider, provider_usage in by_provider.items():
                        if provider_usage and isinstance(provider_usage, dict):
                            # Extract metrics from existing token_usage structure
                            actual_cost = provider_usage.get('total_cost', 0.0)
                            total_tokens = provider_usage.get('total_tokens', 0)
                            api_calls = provider_usage.get('api_calls', 0)
                            cached_calls = provider_usage.get('cached_calls', 0)
                            
                            # Estimate cost without cache benefits (approximate 8x multiplier for time, varies for cost)
                            cache_efficiency = cached_calls / max(api_calls, 1) if api_calls > 0 else 0
                            cost_estimated = actual_cost * (1 + (cache_efficiency * 1.5))  # Conservative estimate
                            
                            provider_metrics_for_db[provider] = {
                                'calls': api_calls,
                                'tokens': total_tokens,
                                'cost_actual': actual_cost,
                                'cost_estimated': cost_estimated,
                                'processing_time': processing_time * (api_calls / max(sum(p.get('api_calls', 0) for p in by_provider.values()), 1)),
                                'cache_hit_tokens': cached_calls * (total_tokens / max(api_calls, 1)) if api_calls > 0 else 0,
                                'cost_per_row_actual': actual_cost / total_rows_processed if total_rows_processed > 0 else 0,
                                'cost_per_row_estimated': cost_estimated / total_rows_processed if total_rows_processed > 0 else 0,
                                'time_per_row_actual': (processing_time * (api_calls / max(sum(p.get('api_calls', 0) for p in by_provider.values()), 1))) / total_rows_processed if total_rows_processed > 0 else 0,
                                'cache_efficiency_percent': (1 - (actual_cost / max(cost_estimated, 0.000001))) * 100
                            }
                    
                    logger.warning(f"[PROVIDER_METRICS] Falling back to legacy token_usage conversion for provider_metrics_for_db")
                
                # Record completion time for background handler
                background_end_time = datetime.now(timezone.utc).isoformat()
                
                # Calculate actual background handler processing time
                start_time = datetime.fromisoformat(background_start_time.replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(background_end_time.replace('Z', '+00:00'))
                background_processing_time_seconds = (end_time - start_time).total_seconds()
                logger.info(f"[PREVIEW_TIMING] Background handler processing time: {background_processing_time_seconds:.3f}s")
                
                # Debug QC search groups calculation
                base_claude_groups = validation_metrics.get('claude_search_groups_count', 0)
                qc_has_calls = qc_metrics_data and qc_metrics_data.get('total_qc_calls', 0) > 0
                qc_calls_count = qc_metrics_data.get('total_qc_calls', 0) if qc_metrics_data else 0
                corrected_claude_groups = base_claude_groups + (1 if qc_has_calls else 0)
                logger.info(f"[QC_SEARCH_GROUPS_DEBUG] base_claude_groups: {base_claude_groups}, qc_has_calls: {qc_has_calls}, qc_calls_count: {qc_calls_count}, corrected: {corrected_claude_groups}")

                # Preserve original validation metrics for database storage BEFORE modifying for frontend
                original_validation_metrics = validation_metrics.copy()

                # Update preview_payload validation_metrics for WebSocket logging
                # Frontend expects: perplexityGroups = searchGroups - claudeGroups, so adjust accordingly
                total_search_groups = validation_metrics.get('search_groups_count', 0)  # 4 total validation groups
                perplexity_only_groups = total_search_groups - base_claude_groups  # 4 - 1 = 3 perplexity groups
                claude_groups_for_frontend = base_claude_groups + (1 if qc_has_calls else 0)  # Include QC as fake Claude group (1 + 1 = 2)
                # Add fake group to total so frontend math works: perplexity = total - claude = 5 - 2 = 3
                total_groups_for_frontend = total_search_groups + (1 if qc_has_calls else 0)  # Add fake QC group to total

                if 'validation_metrics' not in preview_payload:
                    preview_payload['validation_metrics'] = {}
                preview_payload['validation_metrics'].update({
                    "validated_columns_count": validation_metrics.get('validated_columns_count', 0),
                    "search_groups_count": total_groups_for_frontend,  # Total groups so frontend math works
                    "claude_search_groups_count": claude_groups_for_frontend  # Claude + QC groups
                })

                # Create minimal frontend payload with only consumed fields
                frontend_payload = {
                    "markdown_table": preview_payload.get("markdown_table", ""),
                    "enhanced_download_url": preview_payload.get("enhanced_download_url"),
                    "total_rows": preview_payload.get("total_rows", 0),
                    "cost_estimates": {
                        "quoted_validation_cost": quoted_full_cost,
                        "estimated_validation_time": estimated_total_time_seconds
                    },
                    "validation_metrics": {
                        "validated_columns_count": validation_metrics.get('validated_columns_count', 0),
                        "search_groups_count": total_groups_for_frontend,  # Total groups so frontend math works
                        "claude_search_groups_count": claude_groups_for_frontend  # Claude + QC groups
                    },
                    "account_info": {
                        "current_balance": float(current_balance) if current_balance else 0,
                        "sufficient_balance": float(current_balance) >= quoted_full_cost if current_balance else False,
                        "credits_needed": max(0, quoted_full_cost - (float(current_balance) if current_balance else 0))
                    }
                }
                
                # Update DynamoDB with the minimal frontend payload
                update_run_status_for_session(status='COMPLETED',
                    run_type="Preview",
                    verbose_status="Preview complete. Results available.",
                    percent_complete=100,
                    processed_rows=len(validation_results.get('validation_results', {})) if validation_results else 0,
                    total_rows=total_rows,  # Actual total rows in the table
                    preview_data=frontend_payload,  # Send minimal frontend payload
                    account_current_balance=float(current_balance) if current_balance else 0,
                    account_sufficient_balance="n/a",
                    account_credits_needed="n/a",
                    account_domain_multiplier=float(multiplier),
                    models=json.dumps(enhanced_models_parameter) if enhanced_models_parameter else json.dumps({}),
                    input_table_name=input_filename,
                    configuration_id=configuration_id,
                    batch_size=batch_size_used,
                    eliyahu_cost=eliyahu_cost,  # Actual cost paid (with caching benefits)
                    quoted_validation_cost=quoted_full_cost,  # What user will pay for full validation (with multiplier, rounding, $2 min)
                    estimated_validation_eliyahu_cost=estimated_total_cost_raw,  # Raw cost estimate for full table without caching benefit
                    time_per_row_seconds=time_per_row,
                    estimated_validation_time_minutes=estimated_time_minutes,
                    end_time=background_end_time,  # Use background handler completion time
                    run_time_s=background_processing_time_seconds,  # Actual background handler processing time
                    provider_metrics=provider_metrics_for_db,  # Enhanced provider-specific metrics
                    qc_metrics=qc_metrics_for_db if qc_metrics_for_db else None,  # Separate QC metrics (not mixed with providers)
                    total_provider_calls=total_provider_calls_override  # Override with correct total including QC
                )

                # Log what we're saving to database
                logger.info(f"[DB_SAVE_DEBUG] Saving to database:")
                logger.info(f"[DB_SAVE_DEBUG]   estimated_validation_time_minutes: {estimated_time_minutes}")
                logger.info(f"[DB_SAVE_DEBUG]   total_provider_calls: {total_provider_calls_override}")
                logger.info(f"[DB_SAVE_DEBUG]   qc_metrics: {qc_metrics_for_db}")
                if qc_metrics_for_db and 'qc_by_column' in qc_metrics_for_db:
                    logger.info(f"[DB_SAVE_DEBUG]   qc_by_column columns: {list(qc_metrics_for_db['qc_by_column'].keys())}")
                    logger.info(f"[DB_SAVE_DEBUG]   qc_by_column data: {qc_metrics_for_db['qc_by_column']}")
                logger.info(f"[DB_SAVE_DEBUG]   provider_metrics keys: {list(provider_metrics_for_db.keys()) if provider_metrics_for_db else 'None'}")
                
                # Track enhanced user metrics for preview
                logger.info(f"[USER_TRACKING] Tracking preview request for email: {email}")
                logger.info(f"[VALIDATION_METRICS_DEBUG] validation_metrics: {validation_metrics}")
                logger.info(f"[VALIDATION_METRICS_DEBUG] validated_columns_count: {validation_metrics.get('validated_columns_count', 'KEY_NOT_FOUND')}")
                try:
                    track_result = track_user_request(
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
                    columns_validated=original_validation_metrics.get('validated_columns_count', 0),
                    search_groups=original_validation_metrics.get('search_groups_count', 0),
                    high_context_search_groups=original_validation_metrics.get('enhanced_context_search_groups_count', 0),
                    claude_calls=original_validation_metrics.get('claude_search_groups_count', 0),
                    eliyahu_cost=eliyahu_cost,  # Actual cost paid
                    estimated_cost=cost_estimated,  # Raw cost estimate without caching
                    quoted_validation_cost=quoted_full_cost,  # This is the scaled full table quote
                    charged_cost=0.0,  # Preview doesn't charge
                    total_api_calls=total_api_calls,
                    total_cached_calls=total_cached_calls
                    )
                    logger.info(f"[USER_TRACKING] Preview tracking result: {track_result}")
                except Exception as e:
                    logger.error(f"[USER_TRACKING] Failed to track preview request: {e}")
                    import traceback
                    logger.error(f"[USER_TRACKING] Traceback: {traceback.format_exc()}")
                
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
                            
                            # DEBUG: Log the cost estimates being sent to frontend
                            cost_estimates = preview_payload.get('cost_estimates', {})
                            logger.debug(f"[COST_DEBUG] WebSocket payload cost_estimates: {cost_estimates}")
                            logger.debug(f"[COST_DEBUG] quoted_validation_cost: {cost_estimates.get('quoted_validation_cost')}")

                            # Log call counts being sent to frontend (CALL COUNTS DEBUGGING)
                            total_provider_calls_ws = cost_estimates.get('total_provider_calls', 0)
                            validation_metrics_ws = preview_payload.get('validation_metrics', {})
                            search_groups_count_ws = validation_metrics_ws.get('search_groups_count', 0)
                            claude_search_groups_count_ws = validation_metrics_ws.get('claude_search_groups_count', 0)
                            calculated_perplexity_groups = search_groups_count_ws - claude_search_groups_count_ws

                            logger.info(f"[WEBSOCKET_SENDING] Sending call counts to frontend:")
                            logger.info(f"[WEBSOCKET_SENDING]   total_provider_calls: {total_provider_calls_ws}")
                            logger.info(f"[WEBSOCKET_SENDING]   search_groups_count (total): {search_groups_count_ws}")
                            logger.info(f"[WEBSOCKET_SENDING]   claude_search_groups_count: {claude_search_groups_count_ws}")
                            logger.info(f"[WEBSOCKET_SENDING]   frontend will calculate perplexity_groups: {calculated_perplexity_groups}")
                            logger.info(f"[WEBSOCKET_SENDING]   payload contains preview_data with {len(preview_payload)} top-level fields")

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
                
                # Enhanced Excel generation has been moved earlier in the function (before WebSocket message)
                # to ensure enhanced_download_url is available in the preview payload
                
                # Store preview results in versioned results folder using unified storage
                config_version = 1
                config_id = "unknown"
                try:
                    existing_config, latest_config_key = storage_manager.get_latest_config(email, clean_session_id)
                    if existing_config and existing_config.get('storage_metadata', {}):
                        config_version = existing_config['storage_metadata'].get('version', 1)
                        config_id = existing_config['storage_metadata'].get('config_id', 'unknown')
                except Exception as e:
                    logger.warning(f"Could not determine config version for preview: {e}")
                
                # Send final storage progress update - interface final processing (90-100% range)
                _send_websocket_message_deduplicated(session_id, {
                    'type': 'preview_progress',
                    'progress': 98,  # Interface final processing: 90-100% range
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
                    'estimated_cost': float(cost_estimated),  # What it would cost without caching
                    # Removed preview_abandoned and insufficient_balance_encountered - unnecessary fields
                    'processing_type': 'preview'
                }
                _update_session_info_with_account_data(email, clean_session_id, account_info)
                
                # Frontend payload already created above for DynamoDB
                
                # Store preview results in unified storage (full payload for processing)
                result = storage_manager.store_results(
                    email, clean_session_id, config_version, preview_payload, 'preview'
                )
                
                if result['success']:
                    logger.info(f"Preview results stored in versioned folder: {result['s3_key']}")
                    
                    # Update session tracking with minimal frontend payload for UX analysis
                    try:
                        success = storage_manager.update_session_results(
                            email=email,
                            session_id=clean_session_id,
                            operation_type="preview",
                            config_id=config_id,
                            version=config_version,
                            run_key=run_key,
                            results_path=result['s3_key'],  # Path to preview results JSON
                            frontend_payload=frontend_payload  # Minimal frontend payload for UX tracking
                        )
                        
                        if success:
                            logger.info(f"✅ Updated session_info.json with preview completion")
                        else:
                            logger.error(f"❌ Failed to update session_info.json with preview completion")
                    except Exception as e:
                        logger.error(f"Failed to update preview session tracking: {e}")
                else:
                    logger.error(f"Failed to store preview results: {result.get('error')}")
                
                # Send final completion progress update - interface final processing complete (100%)
                _send_websocket_message_deduplicated(session_id, {
                    'type': 'preview_progress',
                    'progress': 100,  # Interface final processing complete: 100%
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
                        # Removed preview_abandoned and insufficient_balance_encountered - unnecessary fields
                        'processing_type': 'preview_failed'
                    }
                    _update_session_info_with_account_data(email, clean_session_id, account_info)
                except Exception as e:
                    logger.error(f"Failed to update session info for failed preview: {e}")
                
                update_run_status_for_session(status='FAILED',
                    run_type="Preview",
                    verbose_status="Preview failed to generate results.",
                    percent_complete=100,
                    processed_rows=0,
                    batch_size=10,  # Default batch size
                    eliyahu_cost=0.0,
                    time_per_row_seconds=0.0)
            
            # Return early for preview mode to prevent fallthrough to normal processing
            return {'statusCode': 200, 'body': json.dumps({'status': 'preview_completed', 'session_id': session_id})}

        else:
            # Normal mode processing
            results_key = event['results_key']
            logger.debug(f"Background normal processing for session {session_id}")
            
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
            
            update_run_status_for_session( status='PROCESSING', run_type="Validation", verbose_status=f"Validation preparing to process {rows_to_process} rows in {total_batches} batches.", batch_size=batch_size)

            # DISABLED: Fake simulation replaced with real validation lambda invocation
            logger.debug(f"[DEBUG] Fake batch processing loop DISABLED for session {session_id}")
            logger.debug(f"[DEBUG] Should invoke validation lambda with {rows_to_process} rows in {total_batches} batches")
            
            # TODO: Replace with actual validation lambda invocation
            # This simulation was creating fake "first batch -> final batch" jumps
            
            # Interface setup for full validation - use 0-5% range  
            # Update start_time to when background handler actually begins validation processing
            update_run_status_for_session(status='PROCESSING',
                processed_rows=0,
                percent_complete=2,  # Interface setup: 0-5% range
                verbose_status=f"Validation starting full processing for {rows_to_process} rows...",
                start_time=background_start_time,  # Use background handler start time
                run_type="Validation")
            
            # The real processing should happen via validation lambda invocation
            # which will send proper WebSocket progress updates
            
            # Original simulation loop commented out:
            """
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
                
                update_run_status_for_session(status='PROCESSING',
                    processed_rows=processed_rows_count,
                    percent_complete=percent_complete,
                    verbose_status=verbose_status)
            """
            
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
            run_type_processing = "Preview" if is_preview else "Validation"
            update_run_status_for_session( status='PROCESSING', run_type=run_type_processing, processed_rows=processed_rows_count)

        has_results = (validation_results and 
                      'validation_results' in validation_results and 
                      validation_results['validation_results'] is not None)
        if has_results:
            real_results = validation_results['validation_results']
            total_rows = validation_results.get('total_rows', 1)
            metadata = validation_results.get('metadata', {})
            token_usage = metadata.get('token_usage', {})

            # Extract QC data for full validation
            qc_results = validation_results.get('qc_results', {})
            if qc_results:
                logger.info(f"[QC_MERGE_FULL] Merging QC data into full validation results for display")
                logger.info(f"[QC_MERGE_FULL_DEBUG] QC results structure: {list(qc_results.keys())[:3]}")
                logger.info(f"[QC_MERGE_FULL_DEBUG] real_results keys sample: {list(real_results.keys())[:3]}")

                # Create mapping from hash keys (QC) to numeric keys (validation results)
                qc_hash_keys = list(qc_results.keys())
                validation_numeric_keys = list(real_results.keys())

                # Map QC hash keys to validation numeric keys by position
                for i, qc_hash_key in enumerate(qc_hash_keys):
                    if i < len(validation_numeric_keys):
                        validation_key = validation_numeric_keys[i]
                        row_qc_data = qc_results[qc_hash_key]

                        logger.info(f"[QC_MERGE_FULL_DEBUG] Mapping QC hash key {qc_hash_key} -> validation key {validation_key}")

                        if validation_key in real_results:
                            logger.info(f"[QC_MERGE_FULL_DEBUG] Row {validation_key}: QC fields = {list(row_qc_data.keys())}")
                            for field_name, field_qc_data in row_qc_data.items():
                                logger.info(f"[QC_MERGE_FULL_DEBUG] Field {field_name}: QC data keys = {list(field_qc_data.keys()) if isinstance(field_qc_data, dict) else 'not dict'}")
                                logger.info(f"[QC_MERGE_FULL_DEBUG] Field {field_name}: qc_applied = {field_qc_data.get('qc_applied') if isinstance(field_qc_data, dict) else 'N/A'}")

                                if isinstance(field_qc_data, dict) and (field_qc_data.get('qc_applied') is True or field_qc_data.get('qc_applied') == 'Yes'):
                                    # Since QC is now comprehensive, always use QC values when available
                                    qc_entry = field_qc_data.get('qc_entry', '')
                                    qc_confidence = field_qc_data.get('qc_confidence', '')
                                    logger.info(f"[QC_MERGE_FULL_DEBUG] Field {field_name}: has qc_entry = {bool(qc_entry)}, has qc_confidence = {bool(qc_confidence)}")

                                    # Always use QC entry and confidence when available (comprehensive QC)
                                    if qc_entry and str(qc_entry).strip():
                                        real_results[validation_key][field_name]['value'] = qc_entry
                                        logger.debug(f"[QC_MERGE_FULL] {field_name}: Using QC entry value: {qc_entry}")

                                    if qc_confidence and str(qc_confidence).strip():
                                        real_results[validation_key][field_name]['confidence_level'] = qc_confidence
                                        logger.debug(f"[QC_MERGE_FULL] {field_name}: Using QC confidence: {qc_confidence}")
            # Extract enhanced metrics from validation response
            enhanced_metrics = metadata.get('enhanced_metrics', {})
            # validation_metrics is nested inside enhanced_metrics
            validation_metrics = enhanced_metrics.get('validation_metrics', {})

            # Extract enhanced models parameter from enhanced_metrics (not top-level metadata)
            enhanced_models_parameter = enhanced_metrics.get('enhanced_models_parameter', {}) if enhanced_metrics else {}
            
            # Apply domain multiplier to raw costs and handle billing
            try:
                import sys
                import os
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
                from dynamodb_schemas import get_domain_multiplier, track_api_usage_detailed, deduct_from_balance, check_user_balance
                from decimal import Decimal
                
                email_domain = email.split('@')[-1] if '@' in email else 'unknown'
                multiplier = float(get_domain_multiplier(email_domain))
                
                # ========== HARDENED THREE-TIER COST SYSTEM (FULL VALIDATION) ==========
                # Extract cost data from validation lambda's centralized cost calculation
                eliyahu_cost = token_usage.get('total_cost', 0.0)  # Actual cost paid (includes caching benefits)
                
                # Calculate estimated cost without caching benefit for consistency
                cost_estimated = _calculate_cost_estimated(token_usage, metadata)
                
                # Validate cost calculations
                if eliyahu_cost < 0 or cost_estimated < 0:
                    logger.error(f"[COST_ERROR] Full validation invalid negative costs - Actual: ${eliyahu_cost:.6f}, Estimated: ${cost_estimated:.6f}")
                    eliyahu_cost = max(0.0, eliyahu_cost)
                    cost_estimated = max(0.0, cost_estimated)
                
                if eliyahu_cost > cost_estimated:
                    logger.warning(f"[COST_WARNING] Full validation actual cost ${eliyahu_cost:.6f} > estimated ${cost_estimated:.6f}")
                
                # Apply hardened domain multiplier for fallback calculation
                multiplier_result = _apply_domain_multiplier_with_validation(email, cost_estimated, session_id)
                multiplier = multiplier_result['multiplier']
                
                # For full validation, use the quoted_full_cost from preview (what user was promised to pay)
                # This ensures users pay exactly what was quoted in preview, regardless of actual full validation costs
                charged_cost = multiplier_result['quoted_cost']  # Fallback if preview cost not found
                logger.debug(f"[COST_AUDIT] Full validation fallback - Actual: ${eliyahu_cost:.6f}, "
                           f"Estimated: ${cost_estimated:.6f}, Quoted fallback: ${charged_cost:.2f}")
                logger.warning(f"[BILLING_PATH] Using FALLBACK calculation instead of preview quoted cost!")
                
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
                    
                    # Try both locations for preview quoted cost
                    preview_quoted_cost = None
                    if preview_data:
                        # First try account_info (nested location)
                        preview_quoted_cost = preview_data.get('account_info', {}).get('quoted_validation_cost')
                        
                        # If not found, try top level (direct location)  
                        if not preview_quoted_cost:
                            preview_quoted_cost = preview_data.get('quoted_validation_cost')
                    
                    if preview_quoted_cost:
                        charged_cost = float(preview_quoted_cost)
                        logger.info(f"[BILLING_PATH] ✅ Using preview quoted cost for full validation: ${charged_cost:.6f}")
                    else:
                        logger.warning(f"[BILLING_PATH] ❌ Preview quoted cost not found in results - preview_data keys: {list(preview_data.keys()) if preview_data else 'None'}")
                        if preview_data and 'account_info' in preview_data:
                            logger.warning(f"[BILLING_PATH] account_info keys: {list(preview_data['account_info'].keys())}")
                        logger.warning("[BILLING_PATH] Using calculated fallback cost")
                        
                except Exception as e:
                    logger.warning(f"Failed to retrieve preview quoted cost: {e}, using calculated cost")
                
                logger.info(f"[BILLING_SUMMARY] Full validation costs:")
                logger.info(f"  - Eliyahu (actual): ${eliyahu_cost:.6f}")
                logger.info(f"  - Estimated (current): ${cost_estimated:.6f}")
                logger.info(f"  - Multiplier: {multiplier}x")
                logger.info(f"  - User Charged: ${charged_cost:.6f}")
                logger.info(f"  - Fallback would be: ${multiplier_result['quoted_cost']:.2f}")
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
                            description=f"Full validation - {len(real_results) if real_results else 0} rows processed",
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
                                    'description': f"Full validation - {len(real_results) if real_results else 0} rows processed",
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
                total_rows_processed = validation_results.get('total_processed_rows', len(real_results) if real_results else 0)
                
                # Create the markdown table for the response
                markdown_table = create_markdown_table_from_results(real_results, 3, actual_config_s3_key, S3_UNIFIED_BUCKET, qc_results)
                
                # --- Start of Complex Estimations Logic ---
                
                # Get actual batch size used during validation (same logic as preview)
                per_model_batch_stats = metadata.get('per_model_batch_stats', {})
                effective_batch_size = 50  # Default fallback (reasonable default from enhanced batch manager)
                
                if per_model_batch_stats:
                    actual_batch_sizes = per_model_batch_stats.get('model_batch_sizes', {})
                    if actual_batch_sizes:
                        # Use minimum batch size (what the validator actually used)
                        effective_batch_size = min(actual_batch_sizes.values())
                        logger.info(f"📊 Using actual batch size from full validation: {effective_batch_size} (from models: {actual_batch_sizes})")
                    else:
                        logger.warning(f"📊 per_model_batch_stats available but no model_batch_sizes found")
                elif batch_size and batch_size > 0:
                    effective_batch_size = batch_size
                    logger.info(f"📊 Using configured batch size for full validation: {effective_batch_size}")
                else:
                    logger.warning(f"📊 No batch size data available for full validation, using default: {effective_batch_size}")
                
                # Use batch timing info from the validator if available, otherwise fallback
                batch_timing = metadata.get('batch_timing', {})
                validator_processing_time = metadata.get('processing_time', 0.0)
                time_per_batch = 20.0 # Default fallback
                time_per_row = 4.0 # Default fallback

                # Extract timing data from enhanced metrics or use fallback
                processing_time = 0.0  # Initialize
                
                logger.debug(f"[TIMING_DEBUG] batch_timing available: {bool(batch_timing)}, validator_processing_time: {validator_processing_time}")
                if batch_timing:
                    logger.debug(f"[TIMING_DEBUG] batch_timing keys: {list(batch_timing.keys())}")
                
                if batch_timing and batch_timing.get('total_batch_time_seconds', 0.0) > 0:
                    processing_time = batch_timing.get('total_batch_time_seconds', 0.0)
                    time_per_batch = batch_timing.get('average_batch_time_seconds', time_per_batch)
                    time_per_row = batch_timing.get('average_time_per_row_seconds', time_per_row)
                    logger.debug(f"[TIMING_DEBUG] Using batch_timing: processing_time={processing_time:.3f}s")
                elif validator_processing_time > 0:
                    processing_time = validator_processing_time
                    if total_rows_processed > 0:
                        time_per_row = processing_time / total_rows_processed
                        time_per_batch = time_per_row * effective_batch_size
                    logger.debug(f"[TIMING_DEBUG] Using validator_processing_time: processing_time={processing_time:.3f}s")
                else:
                    # Additional fallback - calculate from start/end times if available
                    start_time_str = validation_results.get('start_time')
                    end_time_str = validation_results.get('end_time') 
                    if start_time_str and end_time_str:
                        try:
                            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                            processing_time = (end_time - start_time).total_seconds()
                            if total_rows_processed > 0:
                                time_per_row = processing_time / total_rows_processed
                                time_per_batch = time_per_row * effective_batch_size
                            logger.debug(f"[TIMING_DEBUG] Calculated from start/end times: processing_time={processing_time:.3f}s")
                        except Exception as e:
                            logger.warning(f"[TIMING_DEBUG] Failed to calculate from start/end times: {e}")
                            processing_time = 0.0
                    else:
                        logger.warning(f"[TIMING_DEBUG] No valid timing data found - processing_time will be 0")
                        processing_time = 0.0
                
                # Extract per-row cost from enhanced data (not manual calculation)
                per_row_cost_full = eliyahu_cost / total_rows_processed if total_rows_processed > 0 else eliyahu_cost
                
                # Simple batch count for display
                total_batches = math.ceil(total_rows / effective_batch_size) if total_rows > 0 else 0

                preview_payload = {
                    "status": "preview_completed",
                    "session_id": session_id,
                    "reference_pin": reference_pin,
                    "markdown_table": markdown_table,
                    "total_rows": total_rows,
                    "total_processed_rows": total_rows_processed,
                    "preview_processing_time": processing_time,
                    "estimated_total_processing_time": estimated_total_time_seconds,
                    "estimated_validation_time_minutes": round(estimated_total_time_seconds / 60, 1),
                    "actual_batch_size": effective_batch_size,
                    "estimated_validation_batches": total_batches,
                    "enhanced_download_url": enhanced_download_url,  # Download link for enhanced Excel
                    "cost_estimates": {
                        "preview_cost": charged_cost,  # What user pays for preview (0)
                        "preview_tokens": total_tokens,
                        "estimated_total_tokens": estimated_total_tokens,
                        "per_row_time": time_per_row
                    },
                    "token_usage": token_usage,
                    "validation_metrics": validation_metrics
                }


            else: # Full processing
                logger.info(f"Got full validation results for {session_id}, creating enhanced ZIP.")
                
                # Send post-validation progress update - processing results (90-95% range)
                _send_websocket_message_deduplicated(session_id, {
                    'type': 'progress_update',
                    'progress': 92,
                    'message': '📊 Processing validation results and generating files...',
                    'status': 'Processing validation results and generating files...',
                    'session_id': session_id
                }, "full_validation_processing")
                
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
                
                # Determine config version and ID for versioned storage
                config_version = 1
                config_id = "unknown"
                try:
                    existing_config, latest_config_key = storage_manager.get_latest_config(email, clean_session_id)
                    if existing_config and existing_config.get('storage_metadata', {}):
                        config_version = existing_config['storage_metadata'].get('version', 1)
                        config_id = existing_config['storage_metadata'].get('config_id', 'unknown')
                    elif latest_config_key:
                        # Fallback: try to extract version from filename
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
                    # Removed preview_abandoned and insufficient_balance_encountered - unnecessary fields
                    'processing_type': 'full_validation'
                }
                _update_session_info_with_account_data(email, clean_session_id, account_info)
                
                if result['success']:
                    logger.info(f"Full validation results stored in versioned folder: {result['s3_key']}")
                    validation_results_path = result['s3_key']
                else:
                    logger.error(f"Failed to store full validation results: {result.get('error')}")
                    validation_results_path = None
                
                # Extract and store enhanced files from ZIP
                enhanced_excel_path = None
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
                            # Extract enhanced Excel path if available
                            if enhanced_result.get('stored_files'):
                                for file_path in enhanced_result['stored_files']:
                                    if 'enhanced.xlsx' in file_path:
                                        enhanced_excel_path = file_path
                                        break
                        else:
                            logger.error(f"Failed to store enhanced files: {enhanced_result.get('error')}")
                
                except Exception as e:
                    logger.error(f"Failed to extract enhanced files from ZIP: {e}")
                
                # Update session tracking with validation results and enhanced Excel paths
                if validation_results_path:
                    try:
                        success = storage_manager.update_session_results(
                            email=email,
                            session_id=clean_session_id,
                            operation_type="validation",
                            config_id=config_id,
                            version=config_version,
                            run_key=run_key,
                            results_path=validation_results_path,
                            enhanced_excel_path=enhanced_excel_path
                        )
                        
                        if success:
                            logger.info(f"✅ Updated session_info.json with validation completion")
                        else:
                            logger.error(f"❌ Failed to update session_info.json with validation completion")
                    except Exception as e:
                        logger.error(f"Failed to update validation session tracking: {e}")
                else:
                    logger.warning(f"No validation results path available, skipping session tracking")

                if EMAIL_SENDER_AVAILABLE and email_address:
                    # Calculate summary data for the email
                    # First, determine which fields are ID fields (should not be counted as "validated")
                    id_fields = set()
                    if config_data and 'validation_targets' in config_data:
                        for target in config_data['validation_targets']:
                            if target.get('importance', '').upper() in ['ID', 'IGNORED']:
                                id_fields.add(target.get('column'))
                    
                    validated_fields = set()  # Only count fields that were actually validated
                    confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
                    original_confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
                    
                    for row_data in real_results.values():
                        for field_name, field_data in row_data.items():
                            if isinstance(field_data, dict):
                                # Only count as validated if it's not an ID/IGNORED field
                                if field_name not in id_fields:
                                    validated_fields.add(field_name)
                                
                                # Count updated confidence levels (only for validated fields)
                                if 'confidence_level' in field_data and field_name not in id_fields:
                                    conf_level = field_data.get('confidence_level', 'UNKNOWN')
                                    if conf_level in confidence_counts:
                                        confidence_counts[conf_level] += 1
                                
                                # Count original confidence levels (only for validated fields)
                                if 'original_confidence' in field_data and field_name not in id_fields:
                                    original_conf = field_data.get('original_confidence')
                                    if original_conf and str(original_conf).upper() in original_confidence_counts:
                                        original_confidence_counts[str(original_conf).upper()] += 1
                    
                    summary_data = {
                        'total_rows': len(real_results) if real_results else 0,
                        'fields_validated': list(validated_fields),  # Only count actually validated fields (exclude ID/IGNORED)
                        'confidence_distribution': confidence_counts,
                        'original_confidence_distribution': original_confidence_counts
                    }
                    
                    logger.info(f"Email summary: {len(validated_fields)} validated fields (excluding {len(id_fields)} ID/ignored fields): {sorted(validated_fields)}")
                    
                    enhanced_excel_content = None
                    logger.info(f"EXCEL_ENHANCEMENT_AVAILABLE: {EXCEL_ENHANCEMENT_AVAILABLE}")
                    
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
                            
                            excel_buffer = create_qc_enhanced_excel_for_interface(
                                table_data, validation_results, config_data, session_id, validated_sheet_name=validated_sheet
                            )
                            if excel_buffer:
                                enhanced_excel_content = excel_buffer.getvalue()
                                logger.info("Created enhanced Excel using xlsxwriter")
                        except Exception as e:
                            logger.error(f"Error creating enhanced Excel: {str(e)}")
                            enhanced_excel_content = None
                    else:
                        # Fallback: Create basic Excel using openpyxl when xlsxwriter is not available
                        try:
                            logger.info("Creating fallback Excel using openpyxl")
                            enhanced_excel_content = _create_fallback_preview_excel(real_results, config_data, input_filename, is_full=True)
                            logger.info("Created fallback Excel successfully")
                        except Exception as e:
                            logger.error(f"Error creating fallback Excel: {str(e)}")
                            enhanced_excel_content = None
                    
                    # Ensure enhanced_excel_content is bytes or None (not other types)
                    safe_enhanced_excel_content = enhanced_excel_content if isinstance(enhanced_excel_content, (bytes, type(None))) else None
                    
                    # Extract API call counts from token usage for receipt
                    by_provider = token_usage.get('by_provider', {})
                    perplexity_calls = by_provider.get('perplexity', {}).get('calls', 0)
                    anthropic_calls = by_provider.get('anthropic', {}).get('calls', 0)

                    # Extract QC call counts from validation results (if available)
                    qc_calls = 0
                    if validation_results:
                        qc_metrics_data = validation_results.get('qc_metrics', {})
                        qc_calls = qc_metrics_data.get('total_qc_calls', 0) if qc_metrics_data else 0
                        logger.info(f"[RECEIPT_QC_CALLS] Extracted QC calls for receipt: {qc_calls}")
                    
                    # Extract original table name (remove _input suffix if present)
                    original_table_name = input_filename
                    if input_filename and '_input' in input_filename:
                        original_table_name = input_filename.replace('_input', '').rsplit('.', 1)[0]
                        if '.' in original_table_name:  # Add extension back if it had one
                            original_table_name += '.xlsx'
                    elif input_filename:
                        original_table_name = input_filename.rsplit('.', 1)[0] + '.xlsx'
                    
                    # Extract config_id from config metadata (will be added later after config_id is calculated)
                    # This is a placeholder - config_id will be added to billing_info after line 1404
                    
                    # Prepare billing information for receipt
                    billing_info = {
                        'amount_charged': charged_amount,
                        'eliyahu_cost': eliyahu_cost,
                        'actual_cost': eliyahu_cost,  # Add actual cost from DynamoDB
                        'multiplier': multiplier,
                        'initial_balance': float(initial_balance) if initial_balance else 0,
                        'final_balance': float(final_balance) if final_balance else 0,
                        # Add receipt-specific data
                        'perplexity_api_calls': perplexity_calls,
                        'anthropic_api_calls': anthropic_calls,
                        'qc_api_calls': qc_calls,  # Add QC calls for receipt
                        'rows_processed': processed_rows_count,
                        'table_name': original_table_name,
                        'columns_validated_count': len(summary_data.get('fields_validated', []))
                    }
                    
                    # Store enhanced Excel in versioned results folder and create download link
                    enhanced_download_url = None
                    if safe_enhanced_excel_content:
                        try:
                            # Get version from config
                            config_version = config_data.get('storage_metadata', {}).get('version', 1)
                            enhanced_filename = f"{os.path.splitext(input_filename)[0]}_v{config_version}_full_enhanced.xlsx"
                            
                            # Store enhanced Excel in versioned results folder
                            enhanced_result = storage_manager.store_enhanced_files(
                                email, clean_session_id, config_version, 
                                safe_enhanced_excel_content, None
                            )
                            
                            if enhanced_result['success']:
                                logger.info(f"Enhanced Excel stored in results folder for full validation: {enhanced_result['stored_files']}")
                                
                                # Also create public download link for immediate download
                                enhanced_download_url = storage_manager.create_public_download_link(
                                    safe_enhanced_excel_content, 
                                    enhanced_filename,
                                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                                )
                                logger.info(f"Created enhanced Excel download link for full results: {enhanced_download_url}")
                            else:
                                logger.error(f"Failed to store enhanced Excel in results folder for full validation: {enhanced_result.get('error')}")
                                
                        except Exception as e:
                            logger.error(f"Failed to store enhanced Excel for full validation: {e}")
                    
                    # Extract config_id from config metadata
                    config_id = config_data.get('storage_metadata', {}).get('config_id', 'N/A')
                    
                    # Add config_id to billing_info for receipt
                    billing_info['config_id'] = config_id
                    
                    # Get actual processing time from DynamoDB run record instead of metadata
                    actual_processing_time = 0
                    try:
                        from dynamodb_schemas import get_run_status
                        run_status = get_run_status(session_id, run_key)
                        if run_status:
                            # Use actual processing time if available, otherwise calculate from start/end times
                            if 'actual_processing_time_seconds' in run_status:
                                actual_processing_time = float(run_status['actual_processing_time_seconds'])
                            elif 'start_time' in run_status and 'end_time' in run_status:
                                start_time = datetime.fromisoformat(run_status['start_time'].replace('Z', '+00:00'))
                                end_time = datetime.fromisoformat(run_status['end_time'].replace('Z', '+00:00'))
                                actual_processing_time = (end_time - start_time).total_seconds()
                        logger.info(f"Using actual processing time for email: {actual_processing_time:.2f} seconds")
                    except Exception as e:
                        logger.warning(f"Could not get actual processing time for email, using metadata fallback: {e}")
                        actual_processing_time = metadata.get('processing_time', 0)
                    
                    # Send email progress update - sending results (95-98% range)
                    _send_websocket_message_deduplicated(session_id, {
                        'type': 'progress_update',
                        'progress': 96,
                        'message': '📧 Sending validation results to your email...',
                        'status': 'Sending validation results to your email...',
                        'session_id': session_id
                    }, "full_validation_email")
                    
                    email_result = send_validation_results_email(
                        email_address=email_address, excel_content=excel_content, 
                        config_content=json.dumps(config_data, indent=2).encode('utf-8'),
                        enhanced_excel_content=safe_enhanced_excel_content,
                        input_filename=input_filename, config_filename=config_filename,
                        enhanced_excel_filename=f"{os.path.splitext(input_filename)[0].replace('_input', '')}_Validated.xlsx",
                        session_id=session_id, summary_data=summary_data, 
                        processing_time=actual_processing_time,
                        reference_pin=reference_pin, metadata=metadata, preview_email=preview_email,
                        billing_info=billing_info,
                        config_id=config_id
                    )
                    
                    # Send final processing progress update - finalizing (98-100% range)
                    _send_websocket_message_deduplicated(session_id, {
                        'type': 'progress_update',
                        'progress': 99,
                        'message': '✅ Finalizing download links and completion...',
                        'status': 'Finalizing download links and completion...',
                        'session_id': session_id
                    }, "full_validation_finalizing")
                    
                    # Send final completion notification with download URLs
                    processed_rows_count = len(validation_results.get('validation_results', {}))
                    total_rows_in_file = validation_results.get('total_rows', processed_rows_count)
                    
                    # Create ZIP download URL from results_key
                    zip_download_url = None
                    if results_key:
                        try:
                            zip_download_url = s3_client.generate_presigned_url(
                                'get_object',
                                Params={'Bucket': S3_RESULTS_BUCKET, 'Key': results_key},
                                ExpiresIn=7200  # 2 hours
                            )
                            logger.info(f"Created ZIP download link: {zip_download_url}")
                        except Exception as e:
                            logger.error(f"Failed to create ZIP download URL: {e}")
                            zip_download_url = None
                    
                    # Send completion with download URLs (consistent with preview completion)
                    completion_payload = {
                        'status': 'COMPLETED',
                        'processed_rows': processed_rows_count,
                        'total_rows': total_rows_in_file,
                        'verbose_status': 'Validation complete. Results should be in your inbox shortly.',
                        'percent_complete': 100  # Interface final processing complete: 100%
                    }
                    
                    # Add download URLs if available
                    if enhanced_download_url:
                        completion_payload['enhanced_download_url'] = enhanced_download_url
                    if zip_download_url:
                        completion_payload['download_url'] = zip_download_url
                    
                    logger.info(f"Sending completion WebSocket message with download URLs: enhanced={bool(enhanced_download_url)}, zip={bool(zip_download_url)}")
                    _send_websocket_message(session_id, completion_payload)
                    
                    # Get enhanced results S3 key (points to enhanced validation results directory)
                    enhanced_results_s3_key = results_key  # Default to ZIP file if enhanced path not found
                    try:
                        # Try to get the enhanced results directory path instead of ZIP file
                        config_version = config_data.get('storage_metadata', {}).get('version', 1)
                        session_path = storage_manager.get_session_path(email, clean_session_id)
                        enhanced_results_s3_key = f"{session_path}v{config_version}_results/validation_results_enhanced.xlsx"
                        logger.info(f"Using enhanced results S3 key: {enhanced_results_s3_key}")
                    except Exception as e:
                        logger.warning(f"Could not determine enhanced results path, using ZIP path: {e}")
                    
                    # Update status with both ZIP file and enhanced Excel download URLs
                    status_update_data = {
                        'session_id': session_id,
                        'run_key': run_key,
                        'status': 'COMPLETED', 
                        'results_s3_key': enhanced_results_s3_key  # Points to enhanced validation results directory
                    }
                    if enhanced_download_url:
                        status_update_data['enhanced_download_url'] = enhanced_download_url
                    if zip_download_url:
                        status_update_data['download_url'] = zip_download_url
                    
                    # Get and add the actual batch size used during validation
                    per_model_batch_stats = metadata.get('per_model_batch_stats', {})
                    effective_batch_size = 50  # Default fallback
                    
                    if per_model_batch_stats:
                        actual_batch_sizes = per_model_batch_stats.get('model_batch_sizes', {})
                        if actual_batch_sizes:
                            effective_batch_size = min(actual_batch_sizes.values())
                            logger.info(f"📊 Final status update batch size from validation: {effective_batch_size}")
                    elif batch_size and batch_size > 0:
                        effective_batch_size = batch_size
                    
                    if effective_batch_size:
                        status_update_data['batch_size'] = effective_batch_size
                    
                    # Add token/cost data to runs table for full runs (similar to preview runs)
                    # This ensures CSV exports have complete token metrics for both preview and full runs
                    full_run_data = {
                        "actual_batch_size": effective_batch_size,
                        "estimated_validation_batches": math.ceil(total_rows_in_file / effective_batch_size) if effective_batch_size > 0 else 0,
                        "cost_estimates": {
                            "preview_cost": 0  # Full runs don't have preview cost
                        },
                        "token_usage": {
                            "total_tokens": token_usage.get('total_tokens', 0),
                            "by_provider": token_usage.get('by_provider', {}),
                            "api_calls": token_usage.get('api_calls', 0),
                            "cached_calls": token_usage.get('cached_calls', 0),
                            "total_cost": eliyahu_cost
                        },
                        "validation_metrics": validation_metrics
                    }
                    status_update_data['preview_data'] = full_run_data
                    
                    # Add account tracking fields
                    status_update_data['account_current_balance'] = float(final_balance) if final_balance else 0
                    status_update_data['account_sufficient_balance'] = "n/a"
                    status_update_data['account_credits_needed'] = "n/a" 
                    status_update_data['account_domain_multiplier'] = float(multiplier)
                    
                    # Create search group models tracking string - one entry per search group with validated columns count
                    search_groups_models = []
                    # validation_metrics should already be defined from metadata.get('validation_metrics', {})
                    search_groups_count = validation_metrics.get('search_groups_count', 0)
                    enhanced_context_groups = validation_metrics.get('high_context_search_groups_count', 0)
                    claude_groups = validation_metrics.get('claude_search_groups_count', 0)
                    regular_perplexity_groups = search_groups_count - enhanced_context_groups - claude_groups
                    validated_columns_count = validation_metrics.get('validated_columns_count', 0)
                    
                    # Count actual validation targets per search group from config
                    validation_targets = config_data.get('validation_targets', [])
                    columns_per_search_group = {}
                    
                    # Count validation targets assigned to each search group (excluding ID and IGNORED)
                    for target in validation_targets:
                        importance = target.get('importance', '').upper()
                        if importance not in ["ID", "IGNORED"]:
                            search_group_id = target.get('search_group', 0)
                            columns_per_search_group[search_group_id] = columns_per_search_group.get(search_group_id, 0) + 1
                    
                    # Build search group models by iterating through actual search groups in config
                    search_groups_list = config_data.get('search_groups', [])
                    anthropic_default_web_searches = config_data.get('anthropic_max_web_searches_default', 3)
                    
                    # Iterate through each search group to get exact models and settings
                    for search_group in search_groups_list:
                        search_group_id = search_group.get('group_id', 0)
                        columns_for_this_group = columns_per_search_group.get(search_group_id, 0)
                        model = search_group.get('model', 'sonar-pro')
                        search_context = search_group.get('search_context', 'low')
                        
                        # Build model display name
                        if 'claude' in model.lower() or 'anthropic' in model.lower():
                            # Get anthropic_max_web_searches from this specific search group, or fall back to default
                            max_web_searches = search_group.get('anthropic_max_web_searches', anthropic_default_web_searches)
                            if search_context == 'high':
                                model_display = f"{model} ({max_web_searches}) (high context) X {columns_for_this_group}"
                            else:
                                model_display = f"{model} ({max_web_searches}) X {columns_for_this_group}"
                        else:
                            # Perplexity models
                            if search_context == 'high':
                                model_display = f"{model} (high context) X {columns_for_this_group}"
                            else:
                                model_display = f"{model} X {columns_for_this_group}"
                        
                        search_groups_models.append(model_display)
                    
                    status_update_data['models'] = json.dumps(enhanced_models_parameter) if enhanced_models_parameter else json.dumps({})
                    
                    # Add input table name and configuration ID
                    status_update_data['input_table_name'] = input_filename
                    
                    # Get configuration ID for tracking
                    configuration_id = config_data.get('storage_metadata', {}).get('config_id', 'unknown')
                    if not configuration_id or configuration_id == 'unknown':
                        # Fallback to generation metadata
                        configuration_id = config_data.get('generation_metadata', {}).get('config_id', 'unknown')
                    
                    # If still no config ID, generate one from session and version info
                    if not configuration_id or configuration_id == 'unknown':
                        version = config_data.get('storage_metadata', {}).get('version') or config_data.get('generation_metadata', {}).get('version', 'v1')
                        configuration_id = f"{session_id}_{version}_config"
                        logger.info(f"[CONFIG_ID] Generated configuration_id: {configuration_id}")
                    
                    status_update_data['configuration_id'] = configuration_id
                    
                    # Add total rows count
                    status_update_data['total_rows'] = total_rows_in_file
                    
                    # Update verbose status to start with 'Validation' for full validations
                    status_update_data['verbose_status'] = "Validation complete. Results should be in your inbox shortly."
                    
                    # Add consolidated fields according to new schema
                    status_update_data['run_type'] = "Validation"
                    # ========== HARDENED THREE-TIER COST FIELDS ==========
                    status_update_data['eliyahu_cost'] = eliyahu_cost  # Actual cost paid for full validation (includes caching benefits)
                    status_update_data['quoted_validation_cost'] = charged_cost  # What user was charged for full validation (with multiplier, rounding, $2 min)
                    
                    # NOTE: Do NOT overwrite estimated_validation_eliyahu_cost for full validations
                    # This field should preserve the preview estimate for accuracy comparison
                    # Log the comparison between preview estimate and actual full validation cost
                    try:
                        # Try to retrieve the preview estimate from the existing run record
                        run_table = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1')).Table('perplexity-validator-runs')
                        existing_run = run_table.get_item(Key={'session_id': session_id, 'run_key': run_key})
                        
                        if 'Item' in existing_run and 'estimated_validation_eliyahu_cost' in existing_run['Item']:
                            preview_estimate = float(existing_run['Item']['estimated_validation_eliyahu_cost'])
                            actual_full_cost_estimated = cost_estimated
                            estimate_accuracy = ((preview_estimate - actual_full_cost_estimated) / preview_estimate * 100) if preview_estimate > 0 else 0
                            
                            logger.info(f"[COST_COMPARISON] Preview estimated: ${preview_estimate:.6f} | "
                                      f"Actual full cost (no cache): ${actual_full_cost_estimated:.6f} | "
                                      f"Estimate accuracy: {estimate_accuracy:.1f}% | User charged: ${charged_cost:.2f}")
                        else:
                            logger.info(f"[COST_COMPARISON] No preview estimate found | "
                                      f"Actual full cost (no cache): ${cost_estimated:.6f} | "
                                      f"User charged: ${charged_cost:.2f}")
                    except Exception as e:
                        logger.warning(f"[COST_COMPARISON] Could not retrieve preview estimate for comparison: {e}")
                        logger.info(f"[COST_COMPARISON] Actual full cost (no cache): ${cost_estimated:.6f} | "
                                  f"User charged: ${charged_cost:.2f}")
                    
                    # Calculate actual validation processing time from DynamoDB record times
                    validation_processing_time = 0.0
                    
                    # Get the current run's start time from DynamoDB
                    try:
                        from dynamodb_schemas import get_run_status
                        current_run = get_run_status(session_id, run_key)
                        if current_run and 'start_time' in current_run:
                            start_time_str = current_run['start_time']
                            end_time_str = datetime.now(timezone.utc).isoformat()  # Current time as end time
                            
                            logger.debug(f"[VALIDATION_TIMING_DEBUG] DynamoDB start_time: {start_time_str}, end_time: {end_time_str}")
                            
                            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                            validation_processing_time = (end_time - start_time).total_seconds()
                            logger.debug(f"[VALIDATION_TIMING_DEBUG] Calculated from DynamoDB times: validation_processing_time={validation_processing_time:.3f}s")
                        else:
                            logger.warning(f"[VALIDATION_TIMING_DEBUG] Could not get start_time from DynamoDB run record")
                    except Exception as db_error:
                        logger.warning(f"[VALIDATION_TIMING_DEBUG] Failed to get timing from DynamoDB: {db_error}")
                        
                        # Fallback to validation_results times if available
                        start_time_str = validation_results.get('start_time')
                        end_time_str = validation_results.get('end_time') 
                        
                        logger.debug(f"[VALIDATION_TIMING_DEBUG] Fallback start_time: {start_time_str}, end_time: {end_time_str}")
                        
                        if start_time_str and end_time_str:
                            try:
                                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                                end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                                validation_processing_time = (end_time - start_time).total_seconds()
                                logger.debug(f"[VALIDATION_TIMING_DEBUG] Calculated from start/end times: validation_processing_time={validation_processing_time:.3f}s")
                            except Exception as e:
                                logger.warning(f"[VALIDATION_TIMING_DEBUG] Failed to calculate from start/end times: {e}")
                                # Fallback to other timing sources only if start/end calculation fails
                                batch_timing = metadata.get('batch_timing', {})
                                validator_processing_time = metadata.get('processing_time', 0.0)
                                
                                if batch_timing and batch_timing.get('total_batch_time_seconds', 0.0) > 0:
                                    validation_processing_time = batch_timing.get('total_batch_time_seconds', 0.0)
                                    logger.debug(f"[VALIDATION_TIMING_DEBUG] Fallback to batch_timing: validation_processing_time={validation_processing_time:.3f}s")
                                elif validator_processing_time > 0:
                                    validation_processing_time = validator_processing_time
                                    logger.debug(f"[VALIDATION_TIMING_DEBUG] Fallback to validator_processing_time: validation_processing_time={validation_processing_time:.3f}s")
                                else:
                                    logger.warning(f"[VALIDATION_TIMING_DEBUG] No valid timing data found - validation_processing_time will be 0")
                                    validation_processing_time = 0.0
                        else:
                            logger.warning(f"[VALIDATION_TIMING_DEBUG] No start/end times available - using fallback timing sources")
                            # Fallback when start/end times are missing
                            batch_timing = metadata.get('batch_timing', {})
                            validator_processing_time = metadata.get('processing_time', 0.0)
                            
                            if batch_timing and batch_timing.get('total_batch_time_seconds', 0.0) > 0:
                                validation_processing_time = batch_timing.get('total_batch_time_seconds', 0.0)
                                logger.debug(f"[VALIDATION_TIMING_DEBUG] Fallback to batch_timing: validation_processing_time={validation_processing_time:.3f}s")
                            elif validator_processing_time > 0:
                                validation_processing_time = validator_processing_time
                                logger.debug(f"[VALIDATION_TIMING_DEBUG] Fallback to validator_processing_time: validation_processing_time={validation_processing_time:.3f}s")
                            else:
                                logger.warning(f"[VALIDATION_TIMING_DEBUG] No valid timing data found - validation_processing_time will be 0")
                                validation_processing_time = 0.0
                    
                    # Do NOT update estimated_validation_eliyahu_cost - preserve the preview estimate
                    status_update_data['time_per_row_seconds'] = validation_processing_time / processed_rows_count if processed_rows_count > 0 else 0.0  # Actual time per row
                    status_update_data['run_time_s'] = validation_processing_time  # Actual validation run time in seconds
                    status_update_data['actual_processing_time_seconds'] = validation_processing_time  # Same as run_time_s for compatibility
                    status_update_data['actual_time_per_batch_seconds'] = validation_processing_time  # For single batch validation, same as total time
                    logger.debug(f"[TIMING_DEBUG] Set actual_processing_time_seconds={validation_processing_time:.3f}, actual_time_per_batch_seconds={validation_processing_time:.3f}")
                    status_update_data['percent_complete'] = 100  # Mark validation as 100% complete
                    # estimated_validation_time_minutes will be calculated from actual processing time automatically in update_run_status
                    
                    # Use enhanced provider metrics from ai_client aggregation if available, otherwise fallback to token_usage
                    provider_metrics_for_db = {}
                    
                    if enhanced_metrics and enhanced_metrics.get('aggregated_metrics'):
                        # Use properly aggregated enhanced metrics from validation lambda
                        providers = enhanced_metrics['aggregated_metrics'].get('providers', {})

                        for provider, provider_data in providers.items():
                            # Skip QC_Costs as it's now in separate qc_metrics field
                            if provider == 'QC_Costs':
                                continue
                            provider_metrics_for_db[provider] = {
                                'calls': provider_data.get('calls', 0),
                                'tokens': provider_data.get('tokens', 0),
                                'cost_actual': provider_data.get('cost_actual', 0.0),
                                'cost_estimated': provider_data.get('cost_estimated', 0.0),
                                'processing_time': provider_data.get('time_actual', 0.0),
                                'cache_hit_tokens': provider_data.get('cache_hit_tokens', 0),
                                'cost_per_row_actual': provider_data.get('cost_actual', 0.0) / processed_rows_count if processed_rows_count > 0 else 0,
                                'cost_per_row_estimated': provider_data.get('cost_estimated', 0.0) / processed_rows_count if processed_rows_count > 0 else 0,
                                'time_per_row_actual': provider_data.get('time_actual', 0.0) / processed_rows_count if processed_rows_count > 0 else 0,
                                'time_per_row_estimated': provider_data.get('time_estimated', 0.0) / processed_rows_count if processed_rows_count > 0 else 0,
                                'cache_efficiency_percent': provider_data.get('cache_efficiency_percent', 0.0)
                            }
                        
                        logger.info(f"[VALIDATION_PROVIDER_METRICS] Using enhanced aggregated metrics for provider_metrics_for_db")
                    else:
                        # Fallback to legacy token_usage conversion
                        by_provider = token_usage.get('by_provider', {})
                        
                        for provider, provider_usage in by_provider.items():
                            if provider_usage and isinstance(provider_usage, dict):
                                # Extract metrics from existing token_usage structure
                                actual_cost = provider_usage.get('total_cost', 0.0)
                                total_tokens = provider_usage.get('total_tokens', 0)
                                api_calls = provider_usage.get('api_calls', 0)
                                cached_calls = provider_usage.get('cached_calls', 0)
                                
                                # Estimate cost without cache benefits (approximate based on cache efficiency)
                                cache_efficiency = cached_calls / max(api_calls, 1) if api_calls > 0 else 0
                                cost_estimated = actual_cost * (1 + (cache_efficiency * 1.5))  # Conservative estimate
                                
                                provider_time = processing_time * (api_calls / max(sum(p.get('api_calls', 0) for p in by_provider.values()), 1))
                                provider_metrics_for_db[provider] = {
                                    'calls': api_calls,
                                    'tokens': total_tokens,
                                    'cost_actual': actual_cost,
                                    'cost_estimated': cost_estimated,
                                    'processing_time': provider_time,
                                    'cache_hit_tokens': cached_calls * (total_tokens / max(api_calls, 1)) if api_calls > 0 else 0,
                                    'cost_per_row_actual': actual_cost / processed_rows_count if processed_rows_count > 0 else 0,
                                    'cost_per_row_estimated': cost_estimated / processed_rows_count if processed_rows_count > 0 else 0,
                                    'time_per_row_actual': provider_time / processed_rows_count if processed_rows_count > 0 else 0,
                                    'time_per_row_estimated': provider_time / processed_rows_count if processed_rows_count > 0 else 0,  # In fallback, use same as actual
                                    'cache_efficiency_percent': (1 - (actual_cost / max(cost_estimated, 0.000001))) * 100
                                }
                        
                        logger.warning(f"[VALIDATION_PROVIDER_METRICS] Falling back to legacy token_usage conversion for provider_metrics_for_db")
                    
                    status_update_data['provider_metrics'] = provider_metrics_for_db

                    # Extract QC metrics from validation results if available
                    qc_metrics_data = validation_results.get('qc_metrics', {})
                    if qc_metrics_data:
                        logger.info(f"[QC_DB_STORAGE] Found QC metrics in validation results: {list(qc_metrics_data.keys())}")
                        status_update_data['qc_metrics'] = qc_metrics_data
                    else:
                        logger.info(f"[QC_DB_STORAGE] No QC metrics found in validation results")

                    # Calculate total_provider_calls from all providers (QC calls now included in anthropic provider)
                    total_provider_calls_override = sum(
                        provider_data.get('calls', 0)
                        for provider_name, provider_data in provider_metrics_for_db.items()
                        if not provider_data.get('is_metadata_only', False)  # Exclude QC_Costs metadata-only provider
                    )
                    status_update_data['total_provider_calls'] = total_provider_calls_override

                    # Debug logging to verify call counting
                    anthropic_calls = provider_metrics_for_db.get('anthropic', {}).get('calls', 0)
                    perplexity_calls = provider_metrics_for_db.get('perplexity', {}).get('calls', 0)
                    qc_calls_debug = qc_metrics_data.get('total_qc_calls', 0) if qc_metrics_data else 0
                    logger.info(f"[FULL_VALIDATION_CALLS] Anthropic calls (incl QC): {anthropic_calls}, Perplexity calls: {perplexity_calls}, QC calls (debug): {qc_calls_debug}, Total: {total_provider_calls_override}")

                    # Record completion time for background handler
                    background_end_time = datetime.now(timezone.utc).isoformat()
                    
                    # Calculate actual background handler processing time
                    start_time = datetime.fromisoformat(background_start_time.replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(background_end_time.replace('Z', '+00:00'))
                    background_processing_time_seconds = (end_time - start_time).total_seconds()
                    logger.info(f"[VALIDATION_TIMING] Background handler processing time: {background_processing_time_seconds:.3f}s")
                    
                    # Override timing with actual background handler processing time
                    status_update_data['end_time'] = background_end_time  # Use background handler completion time
                    status_update_data['run_time_s'] = background_processing_time_seconds  # Actual background handler processing time
                    status_update_data['actual_processing_time_seconds'] = background_processing_time_seconds  # Override with background handler time
                    status_update_data['actual_time_per_batch_seconds'] = background_processing_time_seconds  # Override with background handler time
                    logger.info(f"[TIMING_OVERRIDE] Override timing fields with background handler time: {background_processing_time_seconds:.3f}s")
                    
                    update_run_status(**status_update_data)
                    
                    # Track enhanced user metrics for full validation
                    logger.info(f"[USER_TRACKING] Tracking full validation request for email: {email}")
                    try:
                        track_result = track_user_request(
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
                        high_context_search_groups=validation_metrics.get('enhanced_context_search_groups_count', 0),
                        claude_calls=validation_metrics.get('claude_search_groups_count', 0),
                        eliyahu_cost=eliyahu_cost,  # Actual cost paid
                        estimated_cost=cost_estimated,  # Raw cost estimate without caching
                        quoted_validation_cost=charged_cost,  # This is the quoted cost from preview (what we're charging)
                        charged_cost=charged_cost,  # Full validation charges user the preview quoted cost
                        total_api_calls=token_usage.get('api_calls', 0),
                        total_cached_calls=token_usage.get('cached_calls', 0)
                        )
                        logger.info(f"[USER_TRACKING] Full validation tracking result: {track_result}")
                    except Exception as e:
                        logger.error(f"[USER_TRACKING] Failed to track full validation request: {e}")
                        import traceback
                        logger.error(f"[USER_TRACKING] Traceback: {traceback.format_exc()}")
        
        else: # No results
             logger.error(f"[DEBUG] No validation results returned from validator for session {session_id}")
             logger.error(f"[DEBUG] is_preview = {is_preview}")
             run_type_for_failed = "Preview" if is_preview else "Validation"
             logger.error(f"[DEBUG] About to update run status to FAILED for {run_type_for_failed}")
             update_run_status_for_session(status='FAILED', 
                run_type=run_type_for_failed,
                error_message="No validation results returned", 
                verbose_status="Failed to process results.", 
                percent_complete=100,
                processed_rows=0,
                batch_size=10,  # Default batch size
                eliyahu_cost=0.0,
                time_per_row_seconds=0.0)
             logger.error(f"[DEBUG] Completed run status update to FAILED")
             # Handle empty results case for preview if needed
             logger.error(f"[DEBUG] Checking if is_preview: {is_preview}")
             if is_preview:
                logger.error(f"[DEBUG] Entering preview handling for empty results")
                # Even for empty results, store in versioned folder
                config_version = 1
                try:
                    logger.debug(f"[DEBUG] Getting latest config for email={email}, session={clean_session_id}")
                    _, latest_config_key = storage_manager.get_latest_config(email, clean_session_id)
                    logger.debug(f"[DEBUG] Got latest_config_key: {latest_config_key}")
                    if latest_config_key:
                        config_filename = latest_config_key.split('/')[-1]
                        if config_filename.startswith('v') and '_' in config_filename:
                            config_version = int(config_filename.split('_')[0][1:])
                    logger.debug(f"[DEBUG] Determined config_version: {config_version}")
                except Exception as e:
                    logger.warning(f"[DEBUG] Exception getting config version: {e}")
                    pass
                
                logger.debug(f"[DEBUG] About to store preview results with config_version={config_version}")
                result = storage_manager.store_results(
                    email, clean_session_id, config_version, 
                    {"status": "preview_completed", "note": "No results"}, 'preview'
                )
                logger.debug(f"[DEBUG] Store results completed: {result}")
                
                if result['success']:
                    preview_results_key = result['s3_key']
                    logger.debug(f"[DEBUG] Store results successful, s3_key: {preview_results_key}")
                else:
                    logger.warning(f"[DEBUG] Store results failed, using fallback")
                    # Fallback
                    preview_results_key = f"preview_results/{email_folder}/{session_id}.json"
                    s3_client.put_object(
                        Bucket=S3_RESULTS_BUCKET, Key=preview_results_key,
                        Body=json.dumps({"status": "preview_completed", "note": "No results"}),
                        ContentType='application/json'
                    )
                logger.debug(f"[DEBUG] About to return preview_completed response for session {session_id}")
                return {'statusCode': 200, 'body': json.dumps({'status': 'preview_completed', 'session_id': session_id})}
             else:
                # Return error response for non-preview failures
                logger.debug(f"[DEBUG] About to return background_failed response for non-preview session {session_id}")
                return {'statusCode': 500, 'body': json.dumps({
                    'status': 'background_failed', 
                    'error': 'No validation results returned',
                    'session_id': session_id
                })}
            
        return {'statusCode': 200, 'body': json.dumps({'status': 'background_completed', 'session_id': session_id})}

    except Exception as e:
        logger.error(f"Critical error in background processing for session {event.get('session_id', 'unknown')}: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        traceback.print_exc()
        if DYNAMODB_AVAILABLE:
            # Determine run type from event or default to unknown
            is_preview = event.get('preview_mode', False) or event.get('request_type') == 'preview'
            is_config = event.get('request_type') == 'config_generation'
            run_type_for_error = "Config Generation" if is_config else ("Preview" if is_preview else "Validation")
            # Try to get run_key from event, if not available create one for error tracking
            session_id_for_error = event.get('session_id')
            run_key_for_error = event.get('run_key')
            
            if not run_key_for_error and session_id_for_error:
                try:
                    # Create a new run record for this error if one doesn't exist
                    run_key_for_error = create_run_record(
                        session_id=session_id_for_error, 
                        email=event.get('email', 'unknown'), 
                        total_rows=0, 
                        batch_size=1, 
                        run_type=run_type_for_error
                    )
                    logger.info(f"Created run_key for error tracking: {run_key_for_error}")
                except Exception as create_error:
                    logger.error(f"Failed to create run_key for error tracking: {create_error}")
                    run_key_for_error = None
            
            if run_key_for_error:
                update_run_status(
                    session_id=session_id_for_error,
                    run_key=run_key_for_error,
                    status='FAILED',
                    run_type=run_type_for_error,
                    error_message=str(e),
                    processed_rows=0,
                    batch_size=1 if is_config else 10,
                    eliyahu_cost=0.0,
                    time_per_row_seconds=0.0
                )
            else:
                logger.warning(f"Cannot update run status for failed session {session_id_for_error} - no run_key available")

            # Send error notification to frontend via WebSocket
            if session_id_for_error:
                try:
                    if is_config:
                        error_message = {
                            'type': 'config_generation_failed',
                            'session_id': session_id_for_error,
                            'success': False,
                            'error': str(e),
                            'progress': 100
                        }
                    else:
                        error_message = {
                            'type': 'validation_failed' if not is_preview else 'preview_failed',
                            'session_id': session_id_for_error,
                            'progress': 100,
                            'status': f'❌ {run_type_for_error} failed: {str(e)[:100]}{"..." if len(str(e)) > 100 else ""}',
                            'error': str(e)
                        }

                    _send_websocket_message_deduplicated(session_id_for_error, error_message)
                    logger.info(f"Sent error notification via WebSocket for session {session_id_for_error}")
                except Exception as ws_error:
                    logger.error(f"Failed to send error notification via WebSocket: {ws_error}")
        return {'statusCode': 500, 'body': json.dumps({'status': 'background_failed', 'error': str(e)})}

def handle_config_generation(event, context):
    """Handle config generation requests by forwarding to config lambda."""
    try:
        import time
        execution_id = f"{context.aws_request_id if context else 'no-context'}_{int(time.time() * 1000)}"
        logger.info(f"[CONFIG_GEN_START] {execution_id} - Handling config generation request for session {event.get('session_id')}")
        session_id = event.get('session_id')
        config_email = event.get('email', '').lower().strip()
        
        # Record when background handler actually starts processing
        background_start_time = datetime.now(timezone.utc).isoformat()
        
        # Create initial config generation run record
        if DYNAMODB_AVAILABLE and config_email and session_id:
            try:
                # Get input table name from event
                input_table_name = "unknown_table"
                if event.get('excel_s3_key'):
                    input_table_name = event['excel_s3_key'].split('/')[-1]
                elif event.get('table_name'):
                    input_table_name = event.get('table_name')
                
                # Get total rows if available
                total_rows = event.get('total_rows', 0)
                
                logger.info(f"[CONFIG_RUN_TRACKING] Creating config generation run record for session {session_id}")
                run_key = create_run_record(session_id, config_email, total_rows, 1, "Config Generation")  # batch_size=1 for config generation
                logger.info(f"[CONFIG_RUN_TRACKING] Config generation run_key: {run_key}")
                
                # Update start_time to when background handler actually begins processing
                update_run_status(session_id=session_id, run_key=run_key, status='IN_PROGRESS',
                    run_type="Config Generation",
                    verbose_status="Configuration generation starting with AI analysis...",
                    percent_complete=5,
                    processed_rows=0,
                    total_rows=total_rows,
                    input_table_name=input_table_name,
                    account_current_balance=0,  # Will be updated later
                    account_sufficient_balance="n/a",
                    start_time=background_start_time,  # Use background handler start time
                    account_credits_needed="n/a",
                    account_domain_multiplier=1.0,  # Config generation typically doesn't use domain multiplier
                    models="TBD",  # Will be updated after AI processing
                    batch_size=1,  # Config generation batch size
                    eliyahu_cost=0.0,  # Will be updated after completion
                    time_per_row_seconds=0.0  # Will be updated after completion
                )
            except Exception as e:
                logger.error(f"[CONFIG_RUN_TRACKING] Failed to create config run record: {e}")
        
        # Send initial progress update - interface setup (0-5% range)
        _send_websocket_message_deduplicated(session_id, {
            'type': 'config_generation_progress',
            'progress': 1,  # Interface setup: 0-5% range
            'status': '🚀 Starting AI configuration generation...',
            'session_id': session_id
        }, "config_progress_start")
        
        # Send analysis progress update - interface setup (0-5% range)
        _send_websocket_message_deduplicated(session_id, {
            'type': 'config_generation_progress', 
            'progress': 3,  # Interface setup: 0-5% range
            'status': '🔍 Analyzing table structure and data patterns...',
            'session_id': session_id
        }, "config_progress_analysis")
        
        # Invoke the config lambda directly - interface setup complete (5% handoff to config lambda for 5-90%)
        _send_websocket_message_deduplicated(session_id, {
            'type': 'config_generation_progress',
            'progress': 5,  # Interface setup complete: hand off to config lambda for 5-90%
            'status': '🤖 Developing configuration with AI...',
            'session_id': session_id
        }, "config_progress_ai_invoke")
        
        response = invoke_config_lambda(event)
        
        logger.info(f"Config generation response: {response}")
        logger.info(f"Response keys: {list(response.keys()) if isinstance(response, dict) else 'Not a dict'}")
        
        # Send AI processing completion update - interface final processing begins (90-100% range)
        _send_websocket_message_deduplicated(session_id, {
            'type': 'config_generation_progress',
            'progress': 90,  # Interface final processing: 90-100% range
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
            
            # Send storage progress update - interface final processing (90-100% range)
            _send_websocket_message_deduplicated(session_id, {
                'type': 'config_generation_progress',
                'progress': 95,  # Interface final processing: 90-100% range
                'status': '💾 Storing configuration in unified storage...',
                'session_id': session_id
            }, "config_progress_storage")
            
            # Use download URL from config lambda response, or create one if not provided
            if config_s3_key and not download_url:
                download_url = create_config_download_url(config_s3_key)
                logger.info(f"Created fallback download URL: {download_url}")
            elif download_url:
                logger.info(f"Using download URL from config lambda: {download_url}")
            
            # Send final completion progress - interface final processing complete (100%)
            _send_websocket_message_deduplicated(session_id, {
                'type': 'config_generation_progress',
                'progress': 100,  # Interface final processing complete: 100%
                'status': '🎉 Configuration generation complete!',
                'session_id': session_id
            }, "config_progress_complete")
            
            # Track config generation metrics
            config_cost = response.get('cost_info', {}).get('total_cost', 0.0)
            config_tokens = response.get('cost_info', {}).get('total_tokens', 0)
            
            # Get and normalize email for tracking
            config_email = event.get('email', '').lower().strip()
            if config_email:  # Only track if email is not empty
                logger.info(f"[USER_TRACKING] Tracking config generation for email: {config_email}")
                try:
                    track_result = track_user_request(
                    email=config_email,
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
                quoted_validation_cost=0.0,  # Config generation is currently free
                charged_cost=0.0,  # Config generation is currently free
                total_api_calls=response.get('cost_info', {}).get('api_calls', 0),
                total_cached_calls=response.get('cost_info', {}).get('cached_calls', 0)
                    )
                    logger.info(f"[USER_TRACKING] Config tracking result: {track_result}")
                except Exception as e:
                    logger.error(f"[USER_TRACKING] Failed to track config generation: {e}")
                    import traceback
                    logger.error(f"[USER_TRACKING] Traceback: {traceback.format_exc()}")
            else:
                logger.warning("Config generation completed but no email provided for user tracking")
            
            # Update config generation run record with completion data
            if DYNAMODB_AVAILABLE and config_email and session_id:
                try:
                    logger.info(f"[CONFIG_RUN_TRACKING] Updating config generation run record with completion data")
                    
                    # Get the actual model used from config lambda response
                    models = response.get('model_used', 'unknown')
                    
                    # Get configuration ID  
                    configuration_id = "unknown"
                    if response.get('updated_config'):
                        configuration_id = response['updated_config'].get('generation_metadata', {}).get('config_id', 'unknown')
                    
                    # Extract config version from response
                    config_version = 1
                    if response.get('updated_config'):
                        config_version = response['updated_config'].get('generation_metadata', {}).get('version', 1)
                        logger.info(f"Extracted config version {config_version} from generation_metadata")
                    
                    # Extract cost_info from response
                    cost_info = response.get('cost_info', {})
                    
                    # Build preview_data for config generation
                    config_data = {
                        "config_type": "ai_generated",
                        "ai_models_used": models,
                        "processing_time_seconds": response.get('processing_time', 0),
                        "cost_estimates": {
                            "total_cost": config_cost,
                            "per_generation_cost": config_cost
                        },
                        "token_usage": {
                            "total_tokens": config_tokens,
                            "by_provider": {
                                "perplexity": {
                                    "total_tokens": cost_info.get('perplexity_tokens', 0),
                                    "total_cost": cost_info.get('perplexity_cost', 0.0),
                                    "calls": cost_info.get('perplexity_calls', 0)
                                },
                                "anthropic": {
                                    "total_tokens": cost_info.get('anthropic_tokens', 0),
                                    "total_cost": cost_info.get('anthropic_cost', 0.0), 
                                    "calls": cost_info.get('anthropic_calls', 0)
                                }
                            }
                        },
                        "generation_metadata": {
                            "config_version": config_version,
                            "config_s3_key": config_s3_key,
                            "download_url": download_url,
                            "ai_summary_length": len(ai_summary) if ai_summary else 0,
                            "clarifying_questions_count": len(response.get('clarifying_questions', '').split('\n')) if response.get('clarifying_questions') else 0
                        }
                    }
                    
                    # Record completion time for background handler
                    background_end_time = datetime.now(timezone.utc).isoformat()
                    
                    # Calculate timing metrics for config generation from background handler processing time
                    start_time = datetime.fromisoformat(background_start_time.replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(background_end_time.replace('Z', '+00:00'))
                    processing_time_seconds = (end_time - start_time).total_seconds()
                    logger.info(f"[CONFIG_TIMING] Background handler processing time: {processing_time_seconds:.3f}s")
                    
                    time_per_config = processing_time_seconds  # For config generation, it's time per config
                    processing_time_minutes = processing_time_seconds / 60.0
                    
                    # Use enhanced data from config lambda if available, otherwise fallback to token_usage
                    provider_metrics_for_db = {}
                    config_enhanced_data = response.get('enhanced_data', {})
                    
                    # Get actual costs from config response (more reliable than enhanced_data for config)
                    config_cost_actual = response.get('eliyahu_cost', 0.0)
                    config_cost_estimated = response.get('estimated_cost', config_cost_actual)
                    
                    if config_enhanced_data and config_enhanced_data.get('provider_metrics'):
                        # Use enhanced data from config lambda (single call structure)
                        for provider, provider_data in config_enhanced_data['provider_metrics'].items():
                            provider_metrics_for_db[provider] = {
                                'calls': provider_data.get('calls', 1),
                                'tokens': provider_data.get('tokens', 0),
                                'cost_actual': config_cost_actual,  # Use actual cost from response
                                'cost_estimated': config_cost_estimated,  # Use estimated cost from response
                                'processing_time': processing_time_seconds,  # Use actual processing time
                                'cache_hit_tokens': provider_data.get('cache_hit_tokens', 0),
                                'cost_per_row_actual': config_cost_actual,  # For config, "per row" is per config
                                'cost_per_row_estimated': config_cost_estimated,
                                'time_per_row_actual': processing_time_seconds,  # Use actual processing time
                                'cache_efficiency_percent': provider_data.get('cache_efficiency_percent', 0.0)
                            }
                        
                        logger.info(f"[CONFIG_PROVIDER_METRICS] Using enhanced data from config lambda")
                    else:
                        # Fallback to legacy token_usage conversion
                        token_usage_data = config_data.get('token_usage', {}).get('by_provider', {})
                        
                        for provider, provider_usage in token_usage_data.items():
                            if provider_usage and isinstance(provider_usage, dict):
                                # Extract metrics from config token_usage structure
                                actual_cost = provider_usage.get('total_cost', 0.0)
                                total_tokens = provider_usage.get('total_tokens', 0)
                                api_calls = provider_usage.get('calls', 0)
                                
                                # For config generation, assume minimal caching benefit (conservative estimate)
                                cache_multiplier = 1.1  # 10% increase for non-cached config operations
                                cost_estimated = actual_cost * cache_multiplier
                                
                                provider_metrics_for_db[provider] = {
                                    'calls': api_calls,
                                    'tokens': total_tokens,
                                    'cost_actual': actual_cost,
                                    'cost_estimated': cost_estimated,
                                    'processing_time': processing_time_seconds * (api_calls / max(sum(p.get('calls', 0) for p in token_usage_data.values()), 1)) if api_calls > 0 else 0,
                                    'cache_hit_tokens': 0,  # Config generation typically doesn't benefit from significant caching
                                    'cost_per_row_actual': actual_cost,  # For config, "per row" is per config
                                    'cost_per_row_estimated': cost_estimated,
                                    'time_per_row_actual': processing_time_seconds * (api_calls / max(sum(p.get('calls', 0) for p in token_usage_data.values()), 1)) if api_calls > 0 else processing_time_seconds,
                                    'cache_efficiency_percent': ((cost_estimated - actual_cost) / max(cost_estimated, 0.000001)) * 100
                                }
                        
                        logger.warning(f"[CONFIG_PROVIDER_METRICS] Falling back to legacy token_usage conversion")
                    
                    update_run_status(session_id=session_id, run_key=run_key, status='COMPLETED',
                        run_type="Config Generation",
                        verbose_status="Configuration generation completed successfully.",
                        percent_complete=100,
                        processed_rows=1,  # One config generated
                        preview_data=config_data,
                        models=models,
                        configuration_id=configuration_id,
                        results_s3_key=config_s3_key,  # Points to generated config file
                        account_current_balance=0,  # Config generation is free
                        account_sufficient_balance="n/a",
                        account_credits_needed="n/a",
                        end_time=background_end_time,  # Use background handler completion time
                        account_domain_multiplier=1.0,
                        batch_size=1,  # Config generation batch size
                        eliyahu_cost=config_cost,  # Actual cost for config generation
                        quoted_validation_cost=0.0,  # Config generation is free to users
                        estimated_validation_eliyahu_cost=None,  # Config generation doesn't use validation cost estimates
                        time_per_row_seconds=None,  # Config generation doesn't use validation timing fields
                        estimated_validation_time_minutes=None,  # Config generation doesn't use validation timing fields
                        run_time_s=processing_time_seconds,  # Actual config generation time in seconds
                        provider_metrics=provider_metrics_for_db  # Enhanced provider-specific metrics
                    )
                    logger.info(f"[CONFIG_RUN_TRACKING] Successfully updated config generation run record")
                except Exception as e:
                    logger.error(f"[CONFIG_RUN_TRACKING] Failed to update config run record: {e}")
                    import traceback
                    logger.error(f"[CONFIG_RUN_TRACKING] Traceback: {traceback.format_exc()}")
            
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
                email = event.get('email', '').lower().strip() if event.get('email') else ''
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
            # Update config generation run record with failure
            if DYNAMODB_AVAILABLE and config_email and session_id:
                try:
                    logger.info(f"[CONFIG_RUN_TRACKING] Updating config generation run record with failure")
                    update_run_status(session_id=session_id, run_key=run_key, status='FAILED',
                        run_type="Config Generation",
                        verbose_status=f"Configuration generation failed: {response.get('error', 'Unknown error')}",
                        percent_complete=0,
                        processed_rows=0,
                        error_message=response.get('error', 'Config generation failed'),
                        account_current_balance=0,
                        account_sufficient_balance="n/a",
                        account_credits_needed="n/a",
                        account_domain_multiplier=1.0,
                        models="Config generation failed",
                        batch_size=1,
                        eliyahu_cost=0.0,
                        estimated_validation_eliyahu_cost=0.0,
                        time_per_row_seconds=0.0
                    )
                    logger.info(f"[CONFIG_RUN_TRACKING] Successfully updated config generation run record with failure")
                except Exception as e:
                    logger.error(f"[CONFIG_RUN_TRACKING] Failed to update config run record with failure: {e}")
            
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
        
        # Update config generation run record with exception failure
        session_id = event.get('session_id')
        config_email = event.get('email', '').lower().strip()
        if DYNAMODB_AVAILABLE and config_email and session_id:
            try:
                logger.info(f"[CONFIG_RUN_TRACKING] Updating config generation run record with exception failure")
                update_run_status(session_id=session_id, run_key=run_key, status='FAILED',
                    run_type="Config Generation",
                    verbose_status=f"Configuration generation failed with exception: {str(e)}",
                    percent_complete=0,
                    processed_rows=0,
                    error_message=str(e),
                    account_current_balance=0,
                    account_sufficient_balance="n/a",
                    account_credits_needed="n/a",
                    account_domain_multiplier=1.0,
                    models="Config generation exception",
                    batch_size=1,
                    eliyahu_cost=0.0,
                    quoted_validation_cost=0.0,
                    estimated_validation_eliyahu_cost=0.0,
                    time_per_row_seconds=0.0
                )
                logger.info(f"[CONFIG_RUN_TRACKING] Successfully updated config generation run record with exception failure")
            except Exception as update_error:
                logger.error(f"[CONFIG_RUN_TRACKING] Failed to update config run record with exception: {update_error}")
        
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
        from botocore.config import Config
        
        # Configure longer timeouts for Opus processing
        config = Config(
            read_timeout=900,  # 15 minutes read timeout  
            connect_timeout=60,  # 1 minute connect timeout
            retries={'max_attempts': 1}  # Don't retry on timeout
        )
        
        lambda_client = boto3.client('lambda', config=config)
        config_lambda_name = os.environ.get('CONFIG_LAMBDA_NAME', 'perplexity-validator-config')
        
        logger.info(f"Invoking config lambda: {config_lambda_name}")
        
        # Always try to retrieve existing config and validation results for config generation
        if event.get('email') and event.get('session_id'):
            try:
                logger.info(f"BACKGROUND_HANDLER: Retrieving existing config and validation results for {event.get('email')}/{event.get('session_id')}")

                # Import and use UnifiedS3Manager to get both config and validation results
                from ..core.unified_s3_manager import UnifiedS3Manager
                storage_manager = UnifiedS3Manager()

                # Try to get existing configuration
                if not event.get('existing_config'):
                    logger.info("BACKGROUND_HANDLER: No existing_config in event, trying to retrieve from storage")
                    try:
                        existing_config = storage_manager.get_latest_config(
                            email=event.get('email'),
                            session_id=event.get('session_id')
                        )
                        if existing_config:
                            event['existing_config'] = existing_config
                            logger.info(f"BACKGROUND_HANDLER: Successfully retrieved existing config!")
                            logger.info(f"Config keys: {list(existing_config.keys())}")
                        else:
                            logger.info(f"BACKGROUND_HANDLER: No existing config found")
                    except Exception as config_error:
                        logger.warning(f"BACKGROUND_HANDLER: Exception retrieving existing config: {config_error}")

                # Try to get validation results
                if not event.get('latest_validation_results'):
                    logger.info("BACKGROUND_HANDLER: No validation results in event, trying to retrieve from storage")
                    latest_validation_results = storage_manager.get_latest_validation_results(
                        email=event.get('email'),
                        session_id=event.get('session_id')
                    )

                    if latest_validation_results:
                        event['latest_validation_results'] = latest_validation_results
                        logger.info(f"BACKGROUND_HANDLER: Successfully added validation results to config lambda payload!")
                        logger.info(f"Validation results keys: {list(latest_validation_results.keys())}")
                        if 'markdown_table' in latest_validation_results:
                            logger.info(f"markdown_table size: {len(latest_validation_results['markdown_table'])}")
                    else:
                        logger.info(f"BACKGROUND_HANDLER: No validation results found")

            except Exception as e:
                logger.warning(f"BACKGROUND_HANDLER: Exception retrieving config/validation data: {e}")
                import traceback
                logger.warning(f"Traceback: {traceback.format_exc()}")
        
        # Debug what we're sending to config lambda
        logger.info(f"CONFIG_LAMBDA_PAYLOAD_DEBUG: Event keys being sent: {list(event.keys())}")
        logger.info(f"CONFIG_LAMBDA_PAYLOAD_DEBUG: Has existing_config: {bool(event.get('existing_config'))}")
        logger.info(f"CONFIG_LAMBDA_PAYLOAD_DEBUG: Has latest_validation_results: {bool(event.get('latest_validation_results'))}")
        if 'email' in event and 'session_id' in event:
            logger.info(f"CONFIG_LAMBDA_PAYLOAD_DEBUG: email={event.get('email')}, session_id={event.get('session_id')}")
        
        # Check payload size for potential issues
        try:
            payload_json = json.dumps(event)
            payload_size_mb = len(payload_json.encode('utf-8')) / (1024 * 1024)
            logger.info(f"CONFIG_LAMBDA_PAYLOAD_SIZE: {payload_size_mb:.2f} MB")
            if payload_size_mb > 5.5:
                logger.warning(f"CONFIG_LAMBDA_PAYLOAD_SIZE: Large payload detected! Size: {payload_size_mb:.2f} MB (limit is 6MB)")
                # Log size breakdown if payload is large
                if event.get('latest_validation_results'):
                    vr_size = len(json.dumps(event['latest_validation_results']).encode('utf-8')) / (1024 * 1024)
                    logger.info(f"latest_validation_results contributes: {vr_size:.2f} MB")
        except Exception as size_check_error:
            logger.warning(f"Could not check payload size: {size_check_error}")
        
        # Construct proper payload for config lambda (extract only the fields it expects)
        config_lambda_payload = {
            'table_analysis': event.get('table_analysis'),
            'existing_config': event.get('existing_config'),
            'instructions': event.get('instructions', 'Generate an optimal configuration for this data validation scenario'),
            'session_id': event.get('session_id', 'unknown'),
            'latest_validation_results': event.get('latest_validation_results'),
            'conversation_history': event.get('conversation_history', []),
            # Add table data sources that config lambda can use if table_analysis is missing
            'excel_s3_key': event.get('excel_s3_key'),
            'csv_s3_key': event.get('csv_s3_key'),
            'table_data': event.get('table_data')
        }

        logger.info(f"BACKGROUND_HANDLER: Constructed config lambda payload with keys: {list(config_lambda_payload.keys())}")
        logger.info(f"BACKGROUND_HANDLER: existing_config in payload: {bool(config_lambda_payload.get('existing_config'))}")
        logger.info(f"BACKGROUND_HANDLER: table_analysis in payload: {bool(config_lambda_payload.get('table_analysis'))}")
        logger.info(f"BACKGROUND_HANDLER: excel_s3_key in payload: {bool(config_lambda_payload.get('excel_s3_key'))}")
        logger.info(f"BACKGROUND_HANDLER: csv_s3_key in payload: {bool(config_lambda_payload.get('csv_s3_key'))}")
        logger.info(f"BACKGROUND_HANDLER: table_data in payload: {bool(config_lambda_payload.get('table_data'))}")

        # Invoke the lambda
        response = lambda_client.invoke(
            FunctionName=config_lambda_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(config_lambda_payload)
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
    """Update session_info.json with account information using unified session management."""
    try:
        from ..core.unified_s3_manager import UnifiedS3Manager
        
        storage_manager = UnifiedS3Manager()
        
        # Use unified session management to preserve version tracking data
        session_info = storage_manager.load_session_info(email, session_id)
        
        # Update with account information (preserves all existing data)
        session_info['account_info'] = account_info
        session_info['last_updated'] = datetime.now().isoformat()
        
        # Save using unified session management to preserve structure
        success = storage_manager.save_session_info(email, session_id, session_info)
        
        if success:
            logger.info(f"Updated session_info.json with account data for {session_id} (preserving version tracking)")
        else:
            logger.error(f"Failed to save session_info.json with account data for {session_id}")
        
    except Exception as e:
        logger.error(f"Failed to update session_info with account data: {e}")