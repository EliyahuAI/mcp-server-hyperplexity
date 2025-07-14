"""
Handles the validateConfig action.
"""
import logging
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(request_data, context):
    """
    Handles the validateConfig action.
    """
    from ..utils.helpers import create_response
    config_content = request_data.get('config', '')
    if not config_content:
        return create_response(400, {'error': 'Missing config content', 'valid': False})
    
    try:
        if isinstance(config_content, str):
            config_data = json.loads(config_content)
        else:
            config_data = config_content
        
        # Basic validation
        if 'validation_targets' in config_data and isinstance(config_data['validation_targets'], list):
            return create_response(200, {'valid': True, 'message': 'Configuration is valid'})
        else:
            return create_response(200, {'valid': False, 'message': 'Configuration must contain validation_targets array'})
    except json.JSONDecodeError as e:
        return create_response(200, {'valid': False, 'message': f'Invalid JSON: {str(e)}'}) 