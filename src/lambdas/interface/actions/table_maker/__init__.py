"""
Table Maker action handlers for conversational table generation.

This module provides the routing and handlers for the table maker feature,
which allows users to create research tables through natural language conversation.
"""
import asyncio
import inspect
import logging

from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import action handlers
from .conversation import (
    handle_table_conversation_start_async,
    handle_table_conversation_continue_async,
    handle_table_conversation_start,
    handle_table_conversation_continue
)
from .preview import handle_table_preview_generate, handle_table_preview_generate_async
from .finalize import handle_table_accept_and_validate_async, handle_table_accept_and_validate
from .context_research import perform_context_research
from .config_bridge import build_table_analysis_from_conversation
from .download import handle_table_download_url

# Action routing dictionary - uses ASYNC wrappers for HTTP requests to prevent timeouts
TABLE_MAKER_ACTIONS = {
    'startTableConversation': handle_table_conversation_start_async,
    'continueTableConversation': handle_table_conversation_continue_async,
    'generateTablePreview': handle_table_preview_generate_async,  # Use async wrapper to prevent timeouts
    'acceptTableAndValidate': handle_table_accept_and_validate_async,  # Use async wrapper to prevent timeouts
    'getTableDownloadUrl': handle_table_download_url,  # Get presigned download URL for unvalidated table
}

def route_table_maker_action(action, request_data, context):
    """
    Route table maker actions to appropriate handlers.

    Handles both async and sync handlers by detecting function type
    and using asyncio.run() for async functions.

    Args:
        action: Action name (e.g., 'startTableConversation')
        request_data: Request data dictionary
        context: Lambda context

    Returns:
        Handler response with CORS headers
    """
    handler = TABLE_MAKER_ACTIONS.get(action)

    if not handler:
        logger.error(f"Unknown table maker action: {action}")
        return create_response(400, {'error': f'Unknown table maker action: {action}'})

    logger.info(f"Routing table maker action: {action}")

    # Check if handler is async
    if inspect.iscoroutinefunction(handler):
        logger.info(f"Handler {action} is async, using asyncio.run()")
        try:
            result = asyncio.run(handler(request_data, context))
            return result
        except Exception as e:
            logger.error(f"Error running async handler {action}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return create_response(500, {'error': f'Handler execution failed: {str(e)}'})
    else:
        logger.info(f"Handler {action} is sync, calling directly")
        try:
            return handler(request_data, context)
        except Exception as e:
            logger.error(f"Error running sync handler {action}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return create_response(500, {'error': f'Handler execution failed: {str(e)}'})

__all__ = [
    'route_table_maker_action',
    'handle_table_conversation_start',
    'handle_table_conversation_continue',
    'handle_table_preview_generate',
    'handle_table_accept_and_validate',
    'handle_table_download_url',
    'perform_context_research',
    'build_table_analysis_from_conversation',
]
