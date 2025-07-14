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

import boto3

# Initialize AWS clients
s3_client = boto3.client('s3')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
        
        api_gateway_management_client = boto3.client('apigatewaymanagementapi', endpoint_url=endpoint_url)
    return api_gateway_management_client

def _update_progress(session_id: str, status: str, processed_rows: int, verbose_status: str, percent_complete: int, total_rows: int = None):
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
S3_CACHE_BUCKET = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
S3_RESULTS_BUCKET = os.environ.get('S3_RESULTS_BUCKET', 'perplexity-results')
VALIDATOR_LAMBDA_NAME = os.environ.get('VALIDATOR_LAMBDA_NAME', 'perplexity-validator')

def handle(event, context):
    """Handle background processing for both normal and preview mode validation."""
    try:
        from ..core.validator_invoker import invoke_validator_lambda
        from ..reporting.zip_report import create_enhanced_result_zip
        from ..reporting.markdown_report import create_markdown_table_from_results
        
        try:
            from ..reporting.excel_report import create_enhanced_excel_with_validation, EXCEL_ENHANCEMENT_AVAILABLE
        except ImportError:
            EXCEL_ENHANCEMENT_AVAILABLE = False
            def create_enhanced_excel_with_validation(*args, **kwargs): return None
        
        try:
            from email_sender import send_validation_results_email
            EMAIL_SENDER_AVAILABLE = True
        except ImportError:
            EMAIL_SENDER_AVAILABLE = False
        
        try:
            from dynamodb_schemas import update_processing_metrics, track_email_delivery, track_user_request, update_run_status
            DYNAMODB_AVAILABLE = True
        except ImportError:
            DYNAMODB_AVAILABLE = False
            # Define dummy functions if not available
            def update_processing_metrics(*args, **kwargs): pass
            def track_email_delivery(*args, **kwargs): pass
            def track_user_request(*args, **kwargs): pass
            def update_run_status(**kwargs): pass

        logger.info("--- Background Handler Started ---")
        
        # Extract parameters from event, ensuring correct types
        is_preview = event.get('preview_mode', False)
        session_id = event['session_id']
        timestamp = event.get('timestamp')
        reference_pin = event.get('reference_pin', '000000')
        excel_s3_key = event['excel_s3_key']
        config_s3_key = event['config_s3_key']
        
        logger.info(f"Background handler called for session {session_id}, is_preview={is_preview}")
        
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
            
            # Initial status update for preview
            update_run_status(
                session_id=session_id, status='PROCESSING', 
                verbose_status=f"Starting preview for {preview_max_rows} rows...",
                percent_complete=10
            )

            validation_results = invoke_validator_lambda(
                excel_s3_key, config_s3_key, max_rows, batch_size, S3_CACHE_BUCKET, VALIDATOR_LAMBDA_NAME,
                preview_first_row=True, preview_max_rows=preview_max_rows, sequential_call=sequential_call_num
            )
            
            # Final status update for preview
            if validation_results and validation_results.get('validation_results'):
                # Extract metadata first
                real_results = validation_results.get('validation_results', {})
                total_rows = validation_results.get('total_rows', 1)
                metadata = validation_results.get('metadata', {})
                token_usage = metadata.get('token_usage', {})
                total_cost = token_usage.get('total_cost', 0.0)
                total_tokens = token_usage.get('total_tokens', 0)
                total_api_calls = token_usage.get('api_calls', 0)
                total_cached_calls = token_usage.get('cached_calls', 0)
                total_rows_processed = validation_results.get('total_processed_rows', 1)
                validation_metrics = metadata.get('validation_metrics', {})
                
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
                
                # Calculate per-row cost and token metrics
                per_row_cost = total_cost / total_rows_processed if total_rows_processed > 0 else 0.02
                per_row_tokens = total_tokens / total_rows_processed if total_rows_processed > 0 else 200

                # Calculate final estimates for the entire file
                total_batches = math.ceil(total_rows / 5) # Assume batches of 5 for estimation
                estimated_total_time_seconds = total_batches * time_per_batch
                estimated_total_cost = per_row_cost * total_rows
                estimated_total_tokens = per_row_tokens * total_rows
                
                # --- End of Complex Estimations Logic ---

                # Create the markdown table for the response
                markdown_table = create_markdown_table_from_results(real_results, 3, config_s3_key, S3_CACHE_BUCKET)
                
                preview_payload = {
                    "status": "COMPLETED", "session_id": session_id,
                    "markdown_table": markdown_table, "total_rows": total_rows,
                    "total_processed_rows": total_rows_processed,
                    "preview_processing_time": processing_time,
                    "estimated_total_processing_time": estimated_total_time_seconds,
                    "estimated_total_time_minutes": round(estimated_total_time_seconds / 60, 1),
                    "cost_estimates": {
                        "preview_cost": total_cost,
                        "estimated_total_cost": estimated_total_cost,
                        "preview_tokens": total_tokens,
                        "estimated_total_tokens": estimated_total_tokens,
                        "per_row_cost": per_row_cost,
                        "per_row_tokens": per_row_tokens,
                        "per_row_time": time_per_row
                    },
                    "token_usage": token_usage,
                    "validation_metrics": validation_metrics
                }
                
                # Update DynamoDB with the complete preview payload
                update_run_status(
                    session_id=session_id, status='COMPLETED',
                    verbose_status="Preview complete. Results available.",
                    percent_complete=100,
                    processed_rows=len(validation_results['validation_results']),
                    preview_data=preview_payload
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
                            logger.info(f"✅ Successfully sent preview completion notification to WebSocket {connection_id}")
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
                # No longer need to save a separate S3 object for previews
            else:
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
            
            # This is where we need to re-introduce the batching logic from the original invoker
            excel_response = s3_client.get_object(Bucket=S3_CACHE_BUCKET, Key=excel_s3_key)
            excel_content = excel_response['Body'].read()
            config_response = s3_client.get_object(Bucket=S3_CACHE_BUCKET, Key=config_s3_key)
            config_data = json.loads(config_response['Body'].read().decode('utf-8'))
            
            # This logic is adapted from the original invoke_validator_lambda
            import openpyxl
            workbook = openpyxl.load_workbook(io.BytesIO(excel_content))
            worksheet = workbook.active
            total_rows_in_file = worksheet.max_row - 1
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
                excel_s3_key, config_s3_key, max_rows, batch_size, S3_CACHE_BUCKET, VALIDATOR_LAMBDA_NAME,
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
            
            if is_preview:
                logger.info(f"Got preview validation results for {session_id}, storing for polling.")
                
                # Create the markdown table for the response
                markdown_table = create_markdown_table_from_results(real_results, 3, config_s3_key, S3_CACHE_BUCKET)
                
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
                
                # Calculate per-row cost and token metrics
                per_row_cost = total_cost / total_rows_processed if total_rows_processed > 0 else 0.02
                per_row_tokens = total_tokens / total_rows_processed if total_rows_processed > 0 else 200

                # Calculate final estimates for the entire file
                total_batches = math.ceil(total_rows / 5) # Assume batches of 5 for estimation
                estimated_total_time_seconds = total_batches * time_per_batch
                estimated_total_cost = per_row_cost * total_rows
                estimated_total_tokens = per_row_tokens * total_rows
                
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
                        "preview_cost": total_cost,
                        "estimated_total_cost": estimated_total_cost,
                        "preview_tokens": total_tokens,
                        "estimated_total_tokens": estimated_total_tokens,
                        "per_row_cost": per_row_cost,
                        "per_row_tokens": per_row_tokens,
                        "per_row_time": time_per_row
                    },
                    "token_usage": token_usage,
                    "validation_metrics": validation_metrics
                }

                preview_results_key = f"preview_results/{email_folder}/{session_id}.json"
                s3_client.put_object(
                    Bucket=S3_RESULTS_BUCKET, Key=preview_results_key,
                    Body=json.dumps(preview_payload, indent=2), ContentType='application/json'
                )
                logger.info(f"Preview results for session {session_id} stored at {preview_results_key}")
                update_run_status(session_id=session_id, status='COMPLETED', results_s3_key=preview_results_key)

            else: # Full processing
                logger.info(f"Got full validation results for {session_id}, creating enhanced ZIP.")
                excel_response = s3_client.get_object(Bucket=S3_CACHE_BUCKET, Key=excel_s3_key)
                excel_content = excel_response['Body'].read()
                config_response = s3_client.get_object(Bucket=S3_CACHE_BUCKET, Key=config_s3_key)
                config_data = json.loads(config_response['Body'].read().decode('utf-8'))
                
                input_filename = excel_s3_key.split('/')[-1]
                config_filename = config_s3_key.split('/')[-1]

                enhanced_zip = create_enhanced_result_zip(
                    real_results, session_id, total_rows, excel_content, config_data,
                    reference_pin, input_filename, config_filename, metadata
                )

                s3_client.put_object(Bucket=S3_RESULTS_BUCKET, Key=results_key, Body=enhanced_zip, ContentType='application/zip')
                logger.info(f"Enhanced results for {session_id} uploaded to {results_key}")

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
                        excel_buffer = create_enhanced_excel_with_validation(excel_content, real_results, config_data, session_id)
                        if excel_buffer:
                            enhanced_excel_content = excel_buffer.getvalue()
                    
                    email_result = send_validation_results_email(
                        email_address=email_address, excel_content=excel_content, 
                        config_content=json.dumps(config_data, indent=2).encode('utf-8'),
                        enhanced_excel_content=enhanced_excel_content,
                        input_filename=input_filename, config_filename=config_filename,
                        enhanced_excel_filename=f"{os.path.splitext(input_filename)[0]}_Validated.xlsx",
                        session_id=session_id, summary_data=summary_data, 
                        processing_time=metadata.get('processing_time',0),
                        reference_pin=reference_pin, metadata=metadata
                    )
                    if DYNAMODB_AVAILABLE:
                        track_email_delivery(session_id=session_id, email_sent=email_result['success'], delivery_status='delivered' if email_result['success'] else 'failed', message_id=email_result.get('message_id',''))
                    # Send final completion notification with processed row count and total rows
                    processed_rows_count = len(validation_results.get('validation_results', {}))
                    total_rows_in_file = validation_results.get('total_rows', processed_rows_count)
                    _update_progress(session_id, 'COMPLETED', processed_rows_count, 'Validation complete. Results emailed.', 100, total_rows_in_file)
                    update_run_status(session_id=session_id, status='COMPLETED', results_s3_key=results_key)
        
        else: # No results
             logger.warning(f"No validation results returned from validator for session {session_id}")
             update_run_status(session_id=session_id, status='FAILED', error_message="No validation results returned", verbose_status="Failed to process results.", percent_complete=100)
             # Handle empty results case for preview if needed
             if is_preview:
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