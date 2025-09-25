"""
Handles all email validation related actions.
"""
import logging
import json
from pathlib import Path

from interface_lambda.utils.helpers import create_response
from dynamodb_schemas import (
    create_email_validation_request,
    validate_email_code,
    is_email_validated,
    check_or_send_validation,
    is_new_user
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(request_data, context):
    """
    Handles email validation actions by routing to the correct sub-handler.
    """
    action = request_data.get('action')
    email = request_data.get('email', '').strip()
    
    if not email:
        return create_response(400, {'success': False, 'error': 'missing_email'})

    try:
        if action == 'requestEmailValidation':
            result = create_email_validation_request(email)
        elif action == 'validateEmailCode':
            code = request_data.get('code', '').strip()
            if not code:
                return create_response(400, {'success': False, 'error': 'missing_code'})
            result = validate_email_code(email, code)
        elif action == 'checkEmailValidation':
            is_valid = is_email_validated(email)
            result = {'success': True, 'validated': is_valid}
        elif action == 'checkOrSendValidation':
            result = check_or_send_validation(email)
            # Add new user detection for demo functionality
            if result.get('success') and result.get('validated'):
                result['is_new_user'] = is_new_user(email)
        else:
            return create_response(400, {'error': f'Unknown email action: {action}'})

        return create_response(200, result)

    except Exception as e:
        logger.error(f"Error handling email action '{action}' for {email}: {e}")
        return create_response(500, {'success': False, 'error': 'internal_error'}) 