"""
Script to test the Lambda function locally.
"""
import json
import os
import sys
from pathlib import Path
import boto3
from datetime import datetime
import logging

# Add src directory to Python path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'src'))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Import the Lambda handler
from src.lambda_function import lambda_handler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Run a test of the Lambda function."""
    # Set TEST_MODE to enable fallback API key
    os.environ['TEST_MODE'] = 'true'
    
    # Load the test event
    test_event_path = os.path.join(os.path.dirname(__file__), 'test_events', 'basic_test_event.json')
    
    try:
        with open(test_event_path, 'r') as f:
            test_event = json.load(f)
    except FileNotFoundError:
        print(f"Test event file not found: {test_event_path}")
        print("Using built-in test event instead.")
        test_event = {
            "bucket_name": "perplexity-temp-bucket--use1-az6--x-s3",
            "config": {
                "primary_key": ["id"],
                "validation_targets": [
                    {
                        "column": "name",
                        "validation_type": "string",
                        "rules": {
                            "min_length": 2,
                            "max_length": 100
                        },
                        "description": "Validate name length and format"
                    }
                ]
            },
            "validation_data": {
                "rows": [
                    {
                        "id": "123",
                        "name": "John Doe"
                    }
                ]
            }
        }
    
    print("Running Lambda function with test event...")
    print(f"Test event: {json.dumps(test_event, indent=2)}\n")
    
    # Run the Lambda handler
    response = lambda_handler(test_event, {})
    
    print("\nLambda function response:")
    print(f"Status code: {response['statusCode']}")
    print("Body:")
    try:
        if isinstance(response['body'], str):
            body = json.loads(response['body'])
            print(json.dumps(body, indent=2))
        else:
            print(json.dumps(response['body'], indent=2))
    except (json.JSONDecodeError, TypeError):
        print(response['body'])
    
    print("\nTest completed!")

def test_lambda():
    """Test the Lambda function with the enhanced test event."""
    try:
        # Load test event
        with open('test_events/enhanced_test_event.json', 'r') as f:
            test_event = json.load(f)
        
        # Initialize Lambda client
        lambda_client = boto3.client('lambda')
        
        # Get function name from environment or use default
        function_name = os.environ.get('LAMBDA_FUNCTION_NAME', 'perplexity-validator')
        
        logger.info(f"Invoking Lambda function: {function_name}")
        
        # Invoke Lambda function
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(test_event)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read())
        
        if response_payload.get('statusCode') == 200:
            results = response_payload['body']
            logger.info("Validation completed successfully!")
            logger.info(f"Cache stats: {results['cache_stats']}")
            
            # Print validation results
            for row_idx, row_results in results['validation_results'].items():
                logger.info(f"\nRow {row_idx} Results:")
                for target, result in row_results.items():
                    if target not in ['next_check', 'reasons']:
                        logger.info(f"  {target}:")
                        logger.info(f"    Value: {result['value']}")
                        logger.info(f"    Confidence: {result['confidence']} ({result['confidence_level']})")
                        logger.info(f"    Sources: {result['sources']}")
                        if result['quote']:
                            logger.info(f"    Quote: {result['quote']}")
                
                logger.info(f"  Next Check: {row_results['next_check']}")
                logger.info(f"  Reasons: {row_results['reasons']}")
        else:
            logger.error(f"Error in Lambda execution: {response_payload.get('body', {}).get('error')}")
        
    except Exception as e:
        logger.error(f"Error testing Lambda: {str(e)}")
        raise

if __name__ == "__main__":
    main()
    test_lambda() 