"""
Handles the getUserStats action.
"""
import logging
import json
from pathlib import Path

from src.lambdas.interface.utils.helpers import create_response
from src.shared.dynamodb_schemas import get_user_stats

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(request_data, context):
    """
    Handles the getUserStats action.
    """
    email = request_data.get('email', '').strip()
    if not email:
        return create_response(400, {'success': False, 'error': 'missing_email'})

    try:
        stats = get_user_stats(email)
        return create_response(200, {'success': True, 'stats': stats})
    except ImportError:
        logger.error("Failed to import dynamodb_schemas for user stats.")
        return create_response(500, {'success': False, 'error': 'server_configuration_error'})
    except Exception as e:
        logger.error(f"Error getting user stats for {email}: {e}")
        return create_response(500, {'success': False, 'error': 'internal_error'}) 