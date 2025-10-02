"""
Handles the processExcel action, for both multipart and JSON requests.
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
from interface_lambda.utils.helpers import create_response, generate_reference_pin, create_email_folder_path
from interface_lambda.core.s3_manager import s3_client, S3_RESULTS_BUCKET, upload_file_to_s3
from dynamodb_schemas import is_email_validated, track_validation_call, create_run_record
from interface_lambda.core.sqs_service import send_preview_request, send_full_request
from interface_lambda.core.validator_invoker import invoke_validator_lambda
from interface_lambda.reporting.markdown_report import create_markdown_table_from_results
from shared.shared_table_parser import S3TableParser

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_CACHE_BUCKET = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')

def handle_multipart_form(event, context):
    """Handles multipart/form-data requests for Excel processing."""
    
    headers = event.get('headers', {})
    content_type = headers.get('Content-Type') or headers.get('content-type', '')
    body = event.get('body', '')
    is_base64_encoded = event.get('isBase64Encoded', False)
    
    files, form_data = parse_multipart_form_data(body, content_type, is_base64_encoded)
    
    email_address = form_data.get('email', 'test@example.com')
    excel_file = files.get('excel_file')
    config_file_content_str = form_data.get('config_file', '')
    
    if not excel_file or not config_file_content_str:
        return create_response(400, {'error': 'Missing excel_file or config_file'})

    config_file = {'filename': 'config.json', 'content': config_file_content_str.encode('utf-8')}

    return _process_files(excel_file, config_file, email_address, event.get('queryStringParameters', {}), context)


def handle_json_request(event, context):
    """Handles application/json requests for Excel processing."""
    body = event.get('body', '{}')
    if event.get('isBase64Encoded'):
        body = base64.b64decode(body).decode('utf-8')
    request_data = json.loads(body)
    
    email_address = request_data.get('email', 'test@example.com')
    excel_base64 = request_data.get('excel_file', '')
    config_base64 = request_data.get('config_file', '')

    if not excel_base64 or not config_base64:
        return create_response(400, {'error': 'Missing excel_file or config_file'})

    excel_file = {'filename': 'input.xlsx', 'content': base64.b64decode(excel_base64)}
    config_file = {'filename': 'config.json', 'content': base64.b64decode(config_base64)}

    return _process_files(excel_file, config_file, email_address, request_data, context)


def _clear_previous_previews(email_folder):
    """Deletes all previous preview result files for a given user."""
    logger.info(f"Clearing previous preview results in s3://{S3_RESULTS_BUCKET}/preview_results/{email_folder}/")
    try:
        response = s3_client.list_objects_v2(
            Bucket=S3_RESULTS_BUCKET,
            Prefix=f"preview_results/{email_folder}/"
        )
        if 'Contents' in response:
            objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
            if objects_to_delete:
                s3_client.delete_objects(
                    Bucket=S3_RESULTS_BUCKET,
                    Delete={'Objects': objects_to_delete}
                )
                logger.info(f"Deleted {len(objects_to_delete)} previous preview files.")
    except Exception as e:
        logger.error(f"Failed to clear previous preview results: {e}")

def _process_files(excel_file, config_file, email_address, params, context):
    """Shared logic to process files, upload to S3, and trigger validation."""
    
    try:
        SQS_AVAILABLE = True
    except ImportError:
        SQS_AVAILABLE = False

    if not is_email_validated(email_address):
        return create_response(403, {'error': 'email_not_validated'})
        
    preview = params.get('preview_first_row', 'false').lower() == 'true'
    async_mode = params.get('async', 'false').lower() == 'true'
    email_folder = create_email_folder_path(email_address)
    
    logger.info(f"Processing request: preview={preview}, async_mode={async_mode}, SQS_AVAILABLE={SQS_AVAILABLE}")

    # If this is a new preview request, clear out old preview results first.
    if preview:
        _clear_previous_previews(email_folder)

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    reference_pin = generate_reference_pin()
    session_id = f"{timestamp}_{reference_pin}"
    
    excel_s3_key = f"uploads/{email_folder}/{session_id}_excel_{excel_file['filename']}"
    config_s3_key = f"uploads/{email_folder}/{session_id}_config_{config_file['filename']}"

    if not upload_file_to_s3(excel_file['content'], S3_CACHE_BUCKET, excel_s3_key) or \
       not upload_file_to_s3(config_file['content'], S3_CACHE_BUCKET, config_s3_key):
        return create_response(500, {'error': 'Failed to upload files to S3'})

    # Extract max_rows and batch_size from parameters, ensuring they are integers
    try:
        max_rows_str = params.get('max_rows')
        max_rows = int(max_rows_str) if max_rows_str else None
        
        # Let enhanced batch manager determine optimal batch size if not explicitly provided
        batch_size_str = params.get('batch_size')
        batch_size = int(batch_size_str) if batch_size_str else None
        
        preview_max_rows_str = params.get('preview_max_rows')
        preview_max_rows = int(preview_max_rows_str) if preview_max_rows_str else 3

    except (ValueError, TypeError):
        return create_response(400, {'error': 'max_rows, batch_size, and preview_max_rows must be valid integers'})

    # After uploading files to S3 and before triggering the job

    # Calculate total rows for the record using shared_table_parser (robust empty row handling)
    try:
        logger.info(f"Using shared_table_parser to get accurate row count from s3://{S3_CACHE_BUCKET}/{excel_s3_key}")
        table_parser = S3TableParser()
        parsed_data = table_parser.parse_s3_table(S3_CACHE_BUCKET, excel_s3_key)
        total_rows = parsed_data['total_rows']
        logger.info(f"Accurate row count from shared_table_parser: {total_rows}")
    except Exception as e:
        logger.error(f"Failed to get row count from shared_table_parser: {e}")
        total_rows = -1 # Indicate that we couldn't determine the row count
    
    # Create the initial run record in DynamoDB
    # Make each preview session unique to avoid conflicts
    if preview:
        timestamp = datetime.utcnow().strftime('%H%M%S')
        preview_session_id = f"{session_id}_preview_{timestamp}"
        create_run_record(session_id=preview_session_id, email=email_address, total_rows=total_rows, batch_size=batch_size)
    else:
        create_run_record(session_id=session_id, email=email_address, total_rows=total_rows, batch_size=batch_size)

    if preview:
        
        
        if async_mode and SQS_AVAILABLE:
            logger.info(f"Sending preview request to SQS for session {preview_session_id}")
            message_id = send_preview_request(
                session_id=preview_session_id, excel_s3_key=excel_s3_key, 
                config_s3_key=config_s3_key, email=email_address, 
                reference_pin=reference_pin, preview_max_rows=preview_max_rows
            )
            logger.info(f"SQS preview request sent with MessageId: {message_id}")
            response_body = {"status": "processing", "session_id": preview_session_id, "reference_pin": reference_pin}
            return create_response(200, response_body)
        else:
            # Synchronous preview logic
            start_time = time.time()
            validation_results = invoke_validator_lambda(
                excel_s3_key, config_s3_key, 
                max_rows=preview_max_rows, 
                batch_size=preview_max_rows, # For sync preview, batch size is same as max rows
                S3_CACHE_BUCKET=S3_CACHE_BUCKET, 
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
                total_cost = token_usage.get('total_cost', 0.0)
                total_processed_rows = validation_results.get('total_processed_rows', 1)

                markdown_table = create_markdown_table_from_results(real_results, 3, config_s3_key, S3_CACHE_BUCKET, None)
                
                estimated_total_cost = (total_cost / total_processed_rows) * total_rows if total_processed_rows > 0 else 0
                estimated_total_time = processing_time * math.ceil(total_rows / (batch_size or 10))

                response_body = {
                    "status": "preview_completed",
                    "session_id": preview_session_id,
                    "reference_pin": reference_pin,
                    "markdown_table": markdown_table,
                    "total_rows": total_rows,
                    "estimated_total_cost": estimated_total_cost,
                    "estimated_total_time_seconds": estimated_total_time,
                }
            else:
                 response_body = {"status": "preview_failed", "message": "Failed to get validation results."}

            return create_response(200, response_body)
    else: # Full validation
        results_key = f"results/{email_folder}/{session_id}.zip"
        
        
        if SQS_AVAILABLE:
            send_full_request(
                session_id=session_id, excel_s3_key=excel_s3_key, config_s3_key=config_s3_key, 
                email=email_address, reference_pin=reference_pin, results_key=results_key,
                max_rows=max_rows, batch_size=batch_size, email_folder=email_folder
            )
        else: # Fallback to direct background invocation
            lambda_client = boto3.client('lambda')
            payload = {
                "background_processing": True, "preview_mode": False, "session_id": session_id,
                "timestamp": timestamp, "reference_pin": reference_pin, "excel_s3_key": excel_s3_key,
                "config_s3_key": config_s3_key, "results_key": results_key,
                "email_folder": email_folder, "email_address": email_address,
                "max_rows": max_rows, "batch_size": batch_size
            }
            lambda_client.invoke(FunctionName=context.function_name, InvocationType='Event', Payload=json.dumps(payload))

        response_body = {"status": "processing_started", "session_id": session_id, "reference_pin": reference_pin}
        return create_response(200, response_body) 