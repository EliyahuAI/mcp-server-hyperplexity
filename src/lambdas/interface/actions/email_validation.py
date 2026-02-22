"""
Handles all email validation related actions.
"""
import logging
import json
from pathlib import Path

from interface_lambda.utils.helpers import create_response
from interface_lambda.utils.session_manager import create_session_token, revoke_all_user_tokens
from dynamodb_schemas import (
    create_email_validation_request,
    validate_email_code,
    is_email_validated,
    check_or_send_validation,
    is_new_user,
    add_to_balance,
    mark_welcome_credit_granted,
    WELCOME_CREDIT_AMOUNT
)
from decimal import Decimal

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

    # SECURITY: Extract IP address from request_data (added by http_handler) for rate limiting
    request_context = request_data.get('_requestContext', {})
    ip_address = request_context.get('identity', {}).get('sourceIp')

    try:
        if action == 'requestEmailValidation':
            result = create_email_validation_request(email)
        elif action == 'validateEmailCode':
            code = request_data.get('code', '').strip()
            if not code:
                return create_response(400, {'success': False, 'error': 'missing_code'})

            # Extract terms_version for server-side tracking
            terms_version = request_data.get('terms_version')

            # SECURITY: Pass IP address for rate limiting
            result = validate_email_code(email, code, ip_address=ip_address, terms_version=terms_version)

            # SECURITY: Issue session token after successful validation
            if result.get('success') and result.get('validated'):
                session_token = create_session_token(email)
                result['session_token'] = session_token
                result['terms_accepted_version'] = terms_version
                logger.info(f"[EMAIL_VALIDATION] Issued session token for {email}")

                # Grant welcome credit to first-time users
                if result.get('is_new_user'):
                    granted = add_to_balance(
                        email,
                        WELCOME_CREDIT_AMOUNT,
                        transaction_type='welcome_credit',
                        description='Welcome bonus — $20 free credits'
                    )
                    if granted:
                        result['welcome_credit_granted'] = True
                        result['welcome_credit_amount'] = float(WELCOME_CREDIT_AMOUNT)
                        result['new_balance'] = float(WELCOME_CREDIT_AMOUNT)
                        mark_welcome_credit_granted(email)
                        logger.info(f"[WELCOME_CREDIT] Granted ${WELCOME_CREDIT_AMOUNT} to new user {email}")

        elif action == 'checkEmailValidation':
            is_valid = is_email_validated(email)
            result = {'success': True, 'validated': is_valid}

            # SECURITY: Issue session token if email is validated
            if is_valid:
                session_token = create_session_token(email)
                result['session_token'] = session_token

        elif action == 'checkOrSendValidation':
            # Support force_reverify parameter (e.g., after logout)
            force_reverify = request_data.get('force_reverify', False)
            result = check_or_send_validation(email, force_reverify=force_reverify)

            # SECURITY: Issue session token if email is validated
            if result.get('success') and result.get('validated'):
                session_token = create_session_token(email)
                result['session_token'] = session_token
                logger.info(f"[EMAIL_VALIDATION] Issued session token for {email}")
            # New user detection removed for performance - no longer needed
            # if result.get('success') and result.get('validated'):
            #     result['is_new_user'] = is_new_user(email)

        elif action == 'logout':
            # SECURITY: Logout user on all devices (revoke all tokens)
            revoked_count = revoke_all_user_tokens(email, reason='user_logout')
            logger.info(f"[AUTH] User logout: {email} - Revoked {revoked_count} sessions")

            result = {
                'success': True,
                'message': 'Logged out successfully on all devices',
                'revoked_count': revoked_count
            }

        else:
            return create_response(400, {'error': f'Unknown email action: {action}'})

        return create_response(200, result)

    except Exception as e:
        logger.error(f"Error handling email action '{action}' for {email}: {e}")
        return create_response(500, {'success': False, 'error': 'internal_error'}) 