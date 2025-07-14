"""
Handles HTTP requests from API Gateway.
"""
import base64
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(event, context):
    """
    Handle HTTP requests.
    This function parses the incoming event and routes it to the appropriate
    action handler, LAZILY loading only the code needed for the specific action.
    """
    from ..utils.helpers import create_response
    logger.info("--- HTTP Handler: Routing request ---")
    
    # Handle CORS preflight OPTIONS requests immediately
    if event.get('httpMethod') == 'OPTIONS':
        logger.info("Handling OPTIONS preflight request")
        return create_response(200, "")

    # Status check via GET request (lightweight)
    if event.get('httpMethod') == 'GET' and event.get('path', '').startswith('/status/'):
        from ..actions import status_check
        return status_check.handle_get_status(event, context)

    # All other actions are POST requests
    if event.get('httpMethod') == 'POST':
        headers = event.get('headers', {})
        content_type = headers.get('Content-Type') or headers.get('content-type', '')

        # Multipart form data for file uploads (heavyweight)
        if 'multipart/form-data' in content_type:
            from ..actions import process_excel
            return process_excel.handle_multipart_form(event, context)

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
                 from ..actions import process_excel
                 return process_excel.handle_json_request(event, context)
            elif action in email_actions:
                from ..actions import email_validation
                return email_validation.handle(request_data, context)
            elif action == 'getUserStats':
                from ..actions import user_stats
                return user_stats.handle(request_data, context)
            elif action == 'validateConfig':
                from ..actions import config_validation
                return config_validation.handle(request_data, context)
            elif action == 'checkStatus' or request_data.get('status_check'):
                from ..actions import status_check
                return status_check.handle_post_status(request_data, context)
            elif action == 'diagnostics':
                from ..actions import diagnostics
                return diagnostics.handle(request_data, context)
            else:
                logger.warning(f"Unknown action in JSON body: {action}")
                return create_response(400, {'error': f'Unknown or unsupported action: {action}'})
    
    # Fallback for unsupported methods
    logger.warning(f"Unsupported HTTP method: {event.get('httpMethod')}")
    return create_response(405, {'error': 'Method Not Allowed'}) 