"""
Handles HTTP requests from API Gateway.
"""
import base64
import json
import logging
import sys
from pathlib import Path

from interface_lambda.utils.helpers import create_response
from interface_lambda.actions import status_check, generate_config_unified, email_validation, user_stats, config_validation, find_matching_config, copy_config, diagnostics
from interface_lambda.utils.parsing import parse_multipart_form_data
from interface_lambda.actions import process_excel_unified

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(event, context):
    """
    Handle HTTP requests.
    This function parses the incoming event and routes it to the appropriate
    action handler, LAZILY loading only the code needed for the specific action.
    """
    logger.info("--- HTTP Handler: Routing request ---")
    
    # Handle CORS preflight OPTIONS requests immediately
    if event.get('httpMethod') == 'OPTIONS':
        logger.info("Handling OPTIONS preflight request")
        return create_response(200, "")

    # Handle dedicated health check
    if event.get('path', '') == '/health':
        logger.info("Handling /health check")
        return create_response(200, {'status': 'ok'})

    # Status check via GET request (lightweight)
    if event.get('httpMethod') == 'GET' and event.get('path', '').startswith('/status/'):
        return status_check.handle_get_status(event, context)

    # All other actions are POST requests
    if event.get('httpMethod') == 'POST':
        headers = event.get('headers', {})
        content_type = headers.get('Content-Type') or headers.get('content-type', '')
        logger.info(f"POST request with Content-Type: {content_type}")

        # Multipart form data for file uploads (heavyweight)
        if 'multipart/form-data' in content_type:
            # Check if this is a config generation request based on form fields
            try:
                files, form_data = parse_multipart_form_data(
                    event.get('body', ''), content_type, event.get('isBase64Encoded', False)
                )
                
                # If generation_mode is present, route to config generation
                if 'generation_mode' in form_data:
                    return generate_config_unified.handle_generate_config_sync(form_data, context)
            except Exception:
                pass  # Fall through to default Excel processing
            
            # Default to Excel processing with unified storage
            return process_excel_unified.handle_multipart_form(event, context)

        # JSON body for API-style actions
        elif 'application/json' in content_type:
            body = event.get('body', '{}')
            if event.get('isBase64Encoded'):
                body = base64.b64decode(body).decode('utf-8')
            
            try:
                request_data = json.loads(body)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in request body: {e}")
                return create_response(400, {'error': 'Invalid JSON format'})

            # Route to action based on 'action' field in JSON body
            action = request_data.get('action')
            
            email_actions = [
                'requestEmailValidation', 
                'validateEmailCode', 
                'checkEmailValidation', 
                'checkOrSendValidation'
            ]

            if action == 'processExcel':
                 return process_excel_unified.handle_json_request(event, context)
            elif action == 'generateConfig':
                # Check for async parameter in query string
                query_params = event.get('queryStringParameters') or {}
                is_async = query_params.get('async', 'false').lower() == 'true'
                
                logger.info(f"generateConfig: query_params={query_params}, is_async={is_async}")
                
                if is_async:
                    logger.info("Using ASYNC config generation path")
                    return generate_config_unified.handle_generate_config_async(request_data, context)
                else:
                    logger.info("Using SYNC config generation path")
                    return generate_config_unified.handle_generate_config_sync(request_data, context)
            elif action == 'submitInterviewResponses':
                return generate_config_unified.handle_generate_config_sync(request_data, context)
            elif action == 'modifyConfig':
                # Check for async parameter in query string
                query_params = event.get('queryStringParameters') or {}
                is_async = query_params.get('async', 'false').lower() == 'true'
                
                logger.info(f"=== MODIFY CONFIG REQUEST ===")
                logger.info(f"Query params: {query_params}")
                logger.info(f"Is async: {is_async}")
                logger.info(f"Request data keys: {list(request_data.keys())}")
                
                if is_async:
                    logger.info("✅ USING ASYNC CONFIG MODIFICATION - WebSocket only response")
                    return generate_config_unified.handle_generate_config_async(request_data, context)
                else:
                    logger.info("✅ USING SYNC CONFIG MODIFICATION - HTTP response with full data")
                    return generate_config_unified.handle_modify_config(request_data, context)
            elif action in email_actions:
                return email_validation.handle(request_data, context)
            elif action == 'getUserStats':
                return user_stats.handle(request_data, context)
            elif action == 'validateConfig':
                return config_validation.handle(request_data, context)
            elif action == 'checkStatus' or request_data.get('status_check'):
                return status_check.handle_post_status(request_data, context)
            elif action == 'diagnostics':
                return diagnostics.handle(request_data, context)
            elif action == 'findMatchingConfig':
                return find_matching_config.handle_find_matching_config(request_data, context)
            elif action == 'copyConfig':
                return copy_config.handle_copy_config(request_data, context)
            else:
                logger.warning(f"Unknown action in JSON body: {action}")
                return create_response(400, {'error': f'Unknown or unsupported action: {action}'})
        
        # Fallback for POST requests without proper Content-Type
        else:
            logger.warning(f"POST request without recognized Content-Type: {content_type}")
            # Try to parse as JSON anyway
            try:
                body = event.get('body', '{}')
                if event.get('isBase64Encoded'):
                    body = base64.b64decode(body).decode('utf-8')
                request_data = json.loads(body)
                action = request_data.get('action')
                
                if action == 'submitInterviewResponses':
                    return generate_config_unified.handle_generate_config_sync(request_data, context)
                elif action == 'modifyConfig':
                    return generate_config_unified.handle_modify_config(request_data, context)
                else:
                    logger.warning(f"Unknown action in fallback: {action}")
                    return create_response(400, {'error': f'Unknown or unsupported action: {action}'})
            except Exception as e:
                logger.error(f"Failed to parse POST body as JSON: {e}")
                return create_response(400, {'error': 'Invalid request format'})
    
    # Fallback for unsupported methods
    logger.warning(f"Unsupported HTTP method: {event.get('httpMethod')}")
    return create_response(405, {'error': 'Method Not Allowed'}) 