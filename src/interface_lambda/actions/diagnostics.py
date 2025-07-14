"""
Handles the diagnostics action.
"""
import logging
import json
import os
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(request_data, context):
    """
    Handles the diagnostics action.
    """
    from ..utils.helpers import create_response
    # These would be read from the environment in a real Lambda context
    S3_CACHE_BUCKET = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
    S3_RESULTS_BUCKET = os.environ.get('S3_RESULTS_BUCKET', 'perplexity-results')
    VALIDATOR_LAMBDA_NAME = os.environ.get('VALIDATOR_LAMBDA_NAME', 'perplexity-validator')

    # Check for SQS integration availability
    try:
        from ..core.sqs_service import send_preview_request
        SQS_INTEGRATION_AVAILABLE = True
        SQS_IMPORT_ERROR = None
    except ImportError as e:
        SQS_INTEGRATION_AVAILABLE = False
        SQS_IMPORT_ERROR = str(e)

    diagnostics = {
        'sqs_integration_available': SQS_INTEGRATION_AVAILABLE,
        'sqs_import_error': SQS_IMPORT_ERROR,
        'environment': {
            'S3_CACHE_BUCKET': S3_CACHE_BUCKET,
            'S3_RESULTS_BUCKET': S3_RESULTS_BUCKET,
            'VALIDATOR_LAMBDA_NAME': VALIDATOR_LAMBDA_NAME
        },
        'boto3_version': boto3.__version__,
        'python_version': os.sys.version,
        'lambda_function_version': context.function_version if hasattr(context, 'function_version') else 'N/A',
        'memory_limit': context.memory_limit_in_mb if hasattr(context, 'memory_limit_in_mb') else 'N/A'
    }
    
    return create_response(200, diagnostics) 