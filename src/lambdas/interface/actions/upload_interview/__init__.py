"""
Upload Interview action handlers for conversational table upload configuration.

This module provides the routing and handlers for the upload interview feature,
which allows users to engage in a brief conversation after uploading a table
to clarify validation requirements before generating a config.
"""
import asyncio
import inspect
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get paths for prompts and schemas
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(CURRENT_DIR, 'prompts')
SCHEMAS_DIR = os.path.join(CURRENT_DIR, 'schemas')

# Import the interview handler
from .interview import UploadInterviewHandler
from ..utils.helpers import create_response


async def handle_upload_interview_start_async(request_data, context):
    """
    Start upload interview - async wrapper for HTTP requests.

    This is called directly from HTTP request and immediately returns,
    with actual processing happening in background via SQS.
    """
    try:
        from ..core.sqs_service import send_upload_interview_request

        # Extract request data
        session_id = request_data.get('session_id')
        email = request_data.get('email')
        conversation_id = request_data.get('conversation_id', f"upload_interview_{session_id}")
        user_message = request_data.get('user_message', '')

        if not session_id or not email:
            return create_response(400, {'error': 'Missing required fields: session_id, email'})

        logger.info(f"[UPLOAD_INTERVIEW] Starting interview for session {session_id}")

        # Send to SQS for background processing
        sqs_result = await send_upload_interview_request(
            session_id=session_id,
            email=email,
            conversation_id=conversation_id,
            user_message=user_message,
            action='startUploadInterview'
        )

        if not sqs_result.get('success'):
            return create_response(500, {'error': f"Failed to queue interview request: {sqs_result.get('error')}"})

        return create_response(200, {
            'success': True,
            'message': 'Upload interview started',
            'conversation_id': conversation_id
        })

    except Exception as e:
        logger.error(f"[UPLOAD_INTERVIEW] Error starting interview: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_response(500, {'error': f'Failed to start upload interview: {str(e)}'})


async def handle_upload_interview_continue_async(request_data, context):
    """
    Continue upload interview - async wrapper for HTTP requests.

    This is called when user responds to interview questions.
    """
    try:
        from ..core.sqs_service import send_upload_interview_request

        # Extract request data
        session_id = request_data.get('session_id')
        email = request_data.get('email')
        conversation_id = request_data.get('conversation_id')
        user_message = request_data.get('user_message', '')

        if not session_id or not email or not conversation_id:
            return create_response(400, {'error': 'Missing required fields: session_id, email, conversation_id'})

        logger.info(f"[UPLOAD_INTERVIEW] Continuing interview for conversation {conversation_id}")

        # Send to SQS for background processing
        sqs_result = await send_upload_interview_request(
            session_id=session_id,
            email=email,
            conversation_id=conversation_id,
            user_message=user_message,
            action='continueUploadInterview'
        )

        if not sqs_result.get('success'):
            return create_response(500, {'error': f"Failed to queue interview continuation: {sqs_result.get('error')}"})

        return create_response(200, {
            'success': True,
            'message': 'Upload interview continued',
            'conversation_id': conversation_id
        })

    except Exception as e:
        logger.error(f"[UPLOAD_INTERVIEW] Error continuing interview: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_response(500, {'error': f'Failed to continue upload interview: {str(e)}'})


# Action routing dictionary
UPLOAD_INTERVIEW_ACTIONS = {
    'startUploadInterview': handle_upload_interview_start_async,
    'continueUploadInterview': handle_upload_interview_continue_async,
}


def route_upload_interview_action(action, request_data, context):
    """
    Route upload interview actions to appropriate handlers.

    Args:
        action: Action name (e.g., 'startUploadInterview')
        request_data: Request data dictionary
        context: Lambda context

    Returns:
        Handler response
    """
    handler = UPLOAD_INTERVIEW_ACTIONS.get(action)

    if not handler:
        logger.error(f"Unknown upload interview action: {action}")
        return create_response(400, {'error': f'Unknown upload interview action: {action}'})

    logger.info(f"Routing upload interview action: {action}")

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
        return handler(request_data, context)


from .processing import handle_upload_interview_start, handle_upload_interview_continue

__all__ = [
    'route_upload_interview_action',
    'handle_upload_interview_start_async',
    'handle_upload_interview_continue_async',
    'handle_upload_interview_start',
    'handle_upload_interview_continue',
    'UploadInterviewHandler',
    'PROMPTS_DIR',
    'SCHEMAS_DIR',
]
