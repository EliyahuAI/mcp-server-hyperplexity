"""
Message Replay API Handler

Provides endpoints for retrieving persisted websocket messages for replay
after page refresh or reconnection.

Actions:
- getMessagesForCard: Get messages for a specific card since a sequence number
- getMessagesSince: Get all messages for a session since a sequence number
"""

import logging
from typing import Dict, Any

from interface_lambda.utils.helpers import create_response

logger = logging.getLogger(__name__)


def handle_get_messages_for_card(request_data: dict, context) -> dict:
    """
    Get messages for a specific card since a given sequence number.

    Request:
    {
        "action": "getMessagesForCard",
        "session_id": "sess_abc123",
        "card_id": "card-4",
        "since_seq": 5,
        "limit": 100
    }

    Response:
    {
        "success": true,
        "messages": [...],
        "last_seq": 10,
        "has_more": false
    }
    """
    try:
        session_id = request_data.get('session_id')
        card_id = request_data.get('card_id')
        since_seq = request_data.get('since_seq', 0)
        limit = request_data.get('limit', 100)

        if not session_id:
            return create_response(400, {'error': 'session_id is required'})

        if not card_id:
            return create_response(400, {'error': 'card_id is required'})

        # Import here to avoid circular imports
        from dynamodb_schemas import get_messages_for_card

        result = get_messages_for_card(session_id, card_id, since_seq, limit)

        logger.info(f"[MESSAGE_REPLAY] Retrieved {len(result['messages'])} messages for card {card_id} in session {session_id}")

        return create_response(200, {
            'success': True,
            'messages': result['messages'],
            'last_seq': result['last_seq'],
            'has_more': result['has_more']
        })

    except Exception as e:
        logger.error(f"[MESSAGE_REPLAY] Error getting messages for card: {e}")
        import traceback
        logger.error(f"[MESSAGE_REPLAY] Traceback: {traceback.format_exc()}")
        return create_response(500, {'error': f'Failed to get messages: {str(e)}'})


def handle_get_messages_since(request_data: dict, context) -> dict:
    """
    Get all messages for a session since a given sequence number.

    Request:
    {
        "action": "getMessagesSince",
        "session_id": "sess_abc123",
        "since_seq": 5,
        "limit": 50
    }

    Response:
    {
        "success": true,
        "messages": [...],
        "last_seq": 10,
        "has_more": false
    }
    """
    try:
        session_id = request_data.get('session_id')
        since_seq = request_data.get('since_seq', 0)
        limit = request_data.get('limit', 50)

        if not session_id:
            return create_response(400, {'error': 'session_id is required'})

        # Import here to avoid circular imports
        from dynamodb_schemas import get_messages_since

        result = get_messages_since(session_id, since_seq, limit)

        logger.info(f"[MESSAGE_REPLAY] Retrieved {len(result['messages'])} messages for session {session_id}")

        return create_response(200, {
            'success': True,
            'messages': result['messages'],
            'last_seq': result['last_seq'],
            'has_more': result['has_more']
        })

    except Exception as e:
        logger.error(f"[MESSAGE_REPLAY] Error getting messages: {e}")
        import traceback
        logger.error(f"[MESSAGE_REPLAY] Traceback: {traceback.format_exc()}")
        return create_response(500, {'error': f'Failed to get messages: {str(e)}'})


def handle(request_data: dict, context) -> dict:
    """Route message replay requests to appropriate handler."""
    action = request_data.get('action')

    if action == 'getMessagesForCard':
        return handle_get_messages_for_card(request_data, context)
    elif action == 'getMessagesSince':
        return handle_get_messages_since(request_data, context)
    else:
        return create_response(400, {'error': f'Unknown message replay action: {action}'})
