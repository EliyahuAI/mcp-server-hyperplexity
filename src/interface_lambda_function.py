"""
AWS Lambda handler for the perplexity-validator-interface function.

This is the main entry point for the Lambda function. It determines the event
source (API Gateway, SQS, etc.) and delegates to the appropriate handler module.
"""
import json
import logging
import os

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Runtime mode detection
IS_LIGHTWEIGHT_INTERFACE = os.environ.get('IS_LIGHTWEIGHT_INTERFACE', 'false').lower() == 'true'
IS_BACKGROUND_PROCESSOR = os.environ.get('IS_BACKGROUND_PROCESSOR', 'false').lower() == 'true'

if IS_LIGHTWEIGHT_INTERFACE:
    logger.info("[RUNTIME] LIGHTWEIGHT INTERFACE (API routing only)")
elif IS_BACKGROUND_PROCESSOR:
    logger.info("[RUNTIME] BACKGROUND PROCESSOR (SQS + heavy operations)")
else:
    logger.info("[RUNTIME] UNIFIED (legacy mode - all operations)")

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

    # Handle /health check IMMEDIATELY with zero imports (deployment verification)
    if event.get('path') == '/health' and event.get('httpMethod') == 'GET':
        logger.info("[HEALTH] Health check - returning immediately with no imports")
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'ok',
                'mode': 'lightweight' if IS_LIGHTWEIGHT_INTERFACE else ('background' if IS_BACKGROUND_PROCESSOR else 'unified')
            })
        }

    # Detect HTTP-like events regardless of payload format version.
    # HTTP API v2 (PayloadFormatVersion 2.0): version='2.0', routeKey present, no httpMethod
    # HTTP API v2 (PayloadFormatVersion 1.0): httpMethod present, version='1.0'
    # REST API v1: httpMethod present, no version field
    _is_http_event = (
        'httpMethod' in event           # REST API v1 or HTTP API v1.0 payload format
        or event.get('version') == '2.0'  # HTTP API v2.0 payload format
        or 'routeKey' in event          # HTTP API v2 always includes routeKey
    )

    # Lightweight mode: Only allow HTTP requests
    if IS_LIGHTWEIGHT_INTERFACE:
        if not _is_http_event:
            error_msg = "Lightweight interface Lambda can only process HTTP requests. SQS/background events must go to background Lambda."
            logger.error(f"{error_msg} event_keys={list(event.keys())[:10]}")
            return {
                'statusCode': 403,
                'body': json.dumps({'error': error_msg, 'mode': 'lightweight_interface'})
            }

        # Route to external API handler if request comes from the external API Gateway.
        # Detection strategy (in priority order):
        #   1. HTTP API v2 event signature (routeKey present / version=="2.0") — if the
        #      external API is ever upgraded to HTTP API v2, this picks it up automatically.
        #   2. apiId match against the configured env var (most precise for REST API v1).
        #      API_GATEWAY_EXTERNAL_API_ID is set at deploy time; may be blank on first deploy.
        #   3. Stage name fallback: external API always uses stage "v1"; web UI uses
        #      "dev"/"prod"/"staging"/"test" — so stage=="v1" uniquely identifies REST API
        #      external-API events when the env var is missing.
        ext_api_id = os.environ.get('API_GATEWAY_EXTERNAL_API_ID')
        _is_external_api = (
            'routeKey' in event or event.get('version') == '2.0'  # HTTP API v2 signature
            or (ext_api_id and event.get('requestContext', {}).get('apiId') == ext_api_id)
            or event.get('requestContext', {}).get('stage') == 'v1'  # REST API: external API uses /v1 stage
        )
        if _is_external_api:
            logger.info("Execution mode: EXTERNAL_API_GATEWAY (lightweight)")
            from interface_lambda.handlers import api_handler
            return api_handler.handle(event, context)

        logger.info("Execution mode: HTTP_API_GATEWAY (lightweight)")
        from interface_lambda.handlers import http_handler
        return http_handler.handle(event, context)

    # Background mode or unified mode: Allow all event types
    if 'Records' in event and event['Records'][0].get('eventSource') == 'aws:sqs':
        logger.info("Execution mode: SQS_PROCESSING")
        from interface_lambda.handlers import sqs_handler
        return sqs_handler.handle(event, context)

    elif event.get('background_processing'):
        logger.info("Execution mode: BACKGROUND_PROCESSING")
        from interface_lambda.handlers import background_handler
        return background_handler.handle(event, context)

    elif _is_http_event:
        # Route to external API handler if request comes from the external API Gateway.
        # See lightweight block above for full detection strategy notes.
        ext_api_id = os.environ.get('API_GATEWAY_EXTERNAL_API_ID')
        _is_external_api = (
            'routeKey' in event or event.get('version') == '2.0'
            or (ext_api_id and event.get('requestContext', {}).get('apiId') == ext_api_id)
            or event.get('requestContext', {}).get('stage') == 'v1'  # REST API: external API uses /v1 stage
        )
        if _is_external_api:
            logger.info("Execution mode: EXTERNAL_API_GATEWAY")
            from interface_lambda.handlers import api_handler
            return api_handler.handle(event, context)

        logger.info("Execution mode: HTTP_API_GATEWAY")
        from interface_lambda.handlers import http_handler
        return http_handler.handle(event, context)

    # Handle unknown event source
    logger.error(f"Unknown event source. Event keys: {list(event.keys())}")
    return {
        'statusCode': 400,
        'body': json.dumps({'error': 'Unknown or unsupported event source'})
    }