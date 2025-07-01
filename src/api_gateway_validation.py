"""
Simple API Gateway validation functions for the interface lambda.
"""

import json
from typing import Dict, Any, Tuple

def validate_api_request(request_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate API request data.
    Returns (is_valid, error_message)
    """
    if not request_data:
        return False, "Request body is empty"
    
    action = request_data.get('action')
    if not action:
        return False, "Missing 'action' field in request"
    
    # Validate based on action
    if action == 'validateConfig':
        if 'config' not in request_data:
            return False, "Missing 'config' field for validateConfig action"
    
    elif action == 'processExcel':
        # Validate file upload request
        files = request_data.get('files', {})
        form_data = request_data.get('form_data', {})
        
        if not files.get('excel_file'):
            return False, "Missing excel_file in upload"
        
        # Either config file or config JSON in form_data is required
        if not files.get('config_file') and not files.get('config'):
            return False, "Missing config file or config data"
    
    elif action == 'checkStatus':
        # These actions have their own validation logic
        pass
    
    else:
        return False, f"Unknown action: {action}"
    
    return True, ""

def create_validation_error_response(error_message: str, status_code: int = 400) -> Dict[str, Any]:
    """
    Create a standardized error response for validation failures.
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'error': error_message,
            'valid': False,
            'status': 'error'
        })
    } 