"""
Script to test the Lambda function locally.
"""
import json
import os
import sys
from pathlib import Path

# Add src directory to Python path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'src'))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Import the Lambda handler
from src.lambda_function import lambda_handler

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

if __name__ == "__main__":
    main() 