"""
Handles all status check related actions.
"""
import json
import logging
import boto3
import os
from pathlib import Path

from interface_lambda.utils.helpers import create_email_folder_path, create_response
from dynamodb_schemas import get_run_status, find_run_key_by_type, find_existing_run_key
from interface_lambda.core.s3_manager import generate_presigned_url, S3_RESULTS_BUCKET

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

def handle_get_status(event, context):
    """Handle GET requests to check processing status."""
    try:
        path_parts = event.get('path', '').split('/')
        if len(path_parts) < 3:
            return create_response(400, {'error': 'Invalid status request path'})
        
        session_id = path_parts[2]
        query_params = event.get('queryStringParameters') or {}
        is_preview = query_params.get('preview', 'false').lower() == 'true'
        email_param = query_params.get('email', '')
        
        return _check_status(session_id, is_preview, email_param)
        
    except Exception as e:
        logger.error(f"Error in GET status handler: {str(e)}")
        return create_response(500, {'error': 'Internal server error'})

def handle_post_status(request_data, context):
    """Handle status check requests via JSON POST body"""
    try:
        session_id = request_data.get('session_id')
        is_preview = request_data.get('preview_mode', False)
        email_param = request_data.get('email', '')
        
        return _check_status(session_id, is_preview, email_param)

    except Exception as e:
        logger.error(f"Error in POST status handler: {str(e)}")
        return create_response(500, {'error': 'Internal server error'})

def _check_status(session_id, is_preview, email_param):
    """Shared logic to check the status of a validation job by querying DynamoDB."""
    # Use the same session ID for both preview and full validation
    lookup_session_id = session_id
    
    # Determine expected run type based on is_preview flag
    expected_run_type = "Preview" if is_preview else "Validation"
    
    # Find run_key for this session and run type
    run_key = find_run_key_by_type(lookup_session_id, expected_run_type)
    if not run_key:
        # Fallback to any existing run_key
        run_key = find_existing_run_key(lookup_session_id)
    
    if not run_key:
        return create_response(200, {'session_id': session_id, 'status': 'PROCESSING', 'message': 'Status record not yet available. The job is likely still being queued.'})
    
    status_record = get_run_status(lookup_session_id, run_key)
    
    if not status_record:
        # If no record is found, it's either still processing or an invalid ID
        return create_response(200, {'session_id': session_id, 'status': 'PROCESSING', 'message': 'Status record not yet available. The job is likely still being queued.'})

    # If this is a completed preview, the preview data is nested in the record
    if is_preview and status_record.get('status') == 'COMPLETED' and 'preview_data' in status_record:
        preview_data = status_record['preview_data']
        # Check if there's a preview results S3 key for download
        if status_record.get('preview_results_s3_key'):
            preview_data['download_url'] = generate_presigned_url(S3_RESULTS_BUCKET, status_record['preview_results_s3_key'])
        return create_response(200, preview_data)
        
    # If this is a completed full run, generate a download URL
    if not is_preview and status_record.get('status') == 'COMPLETED' and status_record.get('results_s3_key'):
        status_record['download_url'] = generate_presigned_url(S3_RESULTS_BUCKET, status_record['results_s3_key'])
    
    # For all other cases (e.g., still processing), return the raw status record
    return create_response(200, status_record) 