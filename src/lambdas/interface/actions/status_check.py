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

def handle_get_results(request_data, context=None):
    """
    Get download URL for a completed validation job.

    Called by api_handler for GET /v1/jobs/{job_id}/results.

    Expects:
        request_data: {
            '_api_email': 'user@example.com',
            'job_id': 'session_xxx',
        }

    Returns standard create_response dict.
    Returns 404 if job is not yet complete.
    """
    job_id = request_data.get('job_id') or request_data.get('session_id')
    email = request_data.get('_api_email') or request_data.get('_verified_email') or request_data.get('email', '')

    if not job_id:
        return create_response(400, {'success': False, 'error': 'job_id is required'})

    base_session_id = job_id
    if not base_session_id.startswith('session_'):
        base_session_id = f"session_{base_session_id}"

    try:
        from dynamodb_schemas import find_run_key_by_type, get_run_status

        run_key = find_run_key_by_type(base_session_id, "Validation")
        if not run_key:
            return create_response(404, {
                'success': False,
                'error': 'job_not_found',
                'message': 'No full validation job found. Submit a preview and approve it first.'
            })

        status_record = get_run_status(base_session_id, run_key)
        if not status_record:
            return create_response(404, {
                'success': False,
                'error': 'job_not_found',
                'message': 'Job status record not found.'
            })

        current_status = status_record.get('status', '').upper()

        if current_status != 'COMPLETED':
            return create_response(404, {
                'success': False,
                'error': 'results_not_ready',
                'message': 'Validation results are not yet available.',
                'details': {
                    'current_status': current_status.lower(),
                    'progress_percent': status_record.get('progress_percent', 0),
                    'status_url': f'/v1/jobs/{job_id}'
                }
            })

        results_s3_key = status_record.get('results_s3_key')
        download_url = None
        if results_s3_key:
            download_url = generate_presigned_url(S3_RESULTS_BUCKET, results_s3_key)

        return create_response(200, {
            'success': True,
            'job_id': job_id,
            'status': 'completed',
            'results': {
                'download_url': download_url,
                'download_expires_at': None,
                'file_format': 'zip' if results_s3_key and results_s3_key.endswith('.zip') else 'unknown',
            },
            'summary': {
                'rows_processed': int(status_record.get('total_rows') or 0),
                'columns_validated': int(status_record.get('columns_validated') or 0),
                'valid_count': int(status_record.get('valid_count') or 0),
                'invalid_count': int(status_record.get('invalid_count') or 0),
                'run_time_seconds': float(status_record.get('run_time_s') or status_record.get('run_time_seconds') or 0),
                'cost_usd': float(status_record.get('quoted_validation_cost') or 0),
            }
        })

    except Exception as e:
        logger.error(f"[GET_RESULTS] Error: {e}")
        return create_response(500, {
            'success': False,
            'error': 'server_error',
            'message': f'Failed to get results: {str(e)}'
        })
