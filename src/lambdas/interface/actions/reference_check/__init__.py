"""
Reference Check Action Router

Routes reference check actions to their appropriate handlers.
Modeled after table_maker action routing.
"""

import asyncio
import inspect
from typing import Dict, Any, Callable
from .conversation import (
    handle_reference_check_start_async,
    # handle_reference_check_continue_async,  # Future: iterative refinement
)


# Action routing dictionary
REFERENCE_CHECK_ACTIONS: Dict[str, Callable] = {
    'startReferenceCheck': handle_reference_check_start_async,
    # 'continueReferenceCheck': handle_reference_check_continue_async,  # Future
    # 'getReferenceCheckResults': handle_reference_check_results,  # Future
}


def route_reference_check_action(action: str, request_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Route reference check actions to appropriate handlers.

    Args:
        action: The action name (e.g., 'startReferenceCheck')
        request_data: The request payload
        context: Lambda context

    Returns:
        Response dictionary

    Raises:
        ValueError: If action is not recognized
    """
    handler = REFERENCE_CHECK_ACTIONS.get(action)

    if not handler:
        return {
            'statusCode': 400,
            'body': {
                'status': 'error',
                'error': 'invalid_action',
                'message': f'Unknown reference check action: {action}',
                'valid_actions': list(REFERENCE_CHECK_ACTIONS.keys())
            }
        }

    # Check if handler is async
    if inspect.iscoroutinefunction(handler):
        # Run async handler
        result = asyncio.run(handler(request_data, context))
    else:
        # Run sync handler
        result = handler(request_data, context)

    return result
