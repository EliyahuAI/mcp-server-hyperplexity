"""
AWS Lambda handler for the perplexity-validator-interface function.

This is the main entry point for the Lambda function. It determines the event
source (API Gateway, SQS, etc.) and delegates to the appropriate handler module.
"""
import json
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Conditional imports for handlers
# We import them here and not globally inside the functions to avoid circular dependencies
# and still allow for some level of lazy loading.
# A more advanced approach could use importlib within the handler.

def lambda_handler(event, context):
    """
    Main Lambda handler.

    Determines the event source and routes the event to the appropriate handler.
    """
    logger.info("=== Perplexity Validator Interface Lambda - Main Handler ===")

    # Determine the execution mode based on the event structure
    if 'Records' in event and event['Records'][0].get('eventSource') == 'aws:sqs':
        mode = "SQS_PROCESSING"
        from interface_lambda.handlers import sqs_handler
        return sqs_handler.handle(event, context)

    elif event.get('background_processing'):
        mode = "BACKGROUND_PROCESSING"
        from interface_lambda.handlers import background_handler
        return background_handler.handle(event, context)

    elif 'httpMethod' in event:
        mode = "HTTP_API_GATEWAY"
        from interface_lambda.handlers import http_handler
        return http_handler.handle(event, context)

    # The stray 'else' block was here and has been removed.
    # We now correctly handle the case where the event source is unknown.
    logger.error(f"Unknown event source. Event keys: {list(event.keys())}")
    return {
        'statusCode': 400,
        'body': json.dumps({'error': 'Unknown or unsupported event source'})
    }

    logger.info(f"Execution mode: {mode}")