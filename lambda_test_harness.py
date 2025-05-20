"""
AWS Lambda Test Harness

This script simulates the AWS Lambda environment for testing your Lambda function locally.
It provides a simple way to test your Lambda function with different test events.
"""
import json
import os
import sys
import argparse
from datetime import datetime

def configure_aws_env():
    """Configure environment variables to simulate AWS Lambda environment."""
    # Set AWS Lambda environment variables
    os.environ['AWS_LAMBDA_FUNCTION_NAME'] = 'perplexity-validator'
    os.environ['AWS_LAMBDA_FUNCTION_VERSION'] = '$LATEST'
    os.environ['AWS_LAMBDA_FUNCTION_MEMORY_SIZE'] = '256'
    os.environ['AWS_REGION'] = 'us-east-1'
    
    # Enable test mode for the Lambda function
    os.environ['TEST_MODE'] = 'true'

def create_lambda_context():
    """Create a simple Lambda context object."""
    class LambdaContext:
        def __init__(self):
            self.function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'test-function')
            self.function_version = os.environ.get('AWS_LAMBDA_FUNCTION_VERSION', '$LATEST')
            self.memory_limit_in_mb = int(os.environ.get('AWS_LAMBDA_FUNCTION_MEMORY_SIZE', '128'))
            self.aws_request_id = f"test-{datetime.now().timestamp()}"
            self.log_group_name = f"/aws/lambda/{self.function_name}"
            self.log_stream_name = f"{datetime.now().strftime('%Y/%m/%d')}/[$LATEST]{self.aws_request_id}"
            self.invoked_function_arn = f"arn:aws:lambda:us-east-1:123456789012:function:{self.function_name}"
            
            # Remaining time in milliseconds
            self._remaining_time_ms = 3000
        
        def get_remaining_time_in_millis(self):
            """Return remaining execution time in milliseconds."""
            return self._remaining_time_ms
    
    return LambdaContext()

def load_test_event(event_path=None):
    """Load a test event from a file or use a default event."""
    default_event = {
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
                    "description": "Validate name format"
                }
            ],
            "cache_ttl_days": 30
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
    
    if not event_path:
        print("Using default test event.")
        return default_event
    
    try:
        with open(event_path, 'r') as f:
            event = json.load(f)
            print(f"Loaded test event from: {event_path}")
            return event
    except Exception as e:
        print(f"Error loading test event: {str(e)}")
        print("Using default test event instead.")
        return default_event

def run_lambda(handler_path, handler_name, event, context):
    """Run a Lambda handler with the specified event and context."""
    # Add the handler's directory to Python path
    handler_dir = os.path.dirname(os.path.abspath(handler_path))
    sys.path.insert(0, handler_dir)
    
    # Load the handler
    try:
        # If handler_path is a .py file
        if handler_path.endswith('.py'):
            module_name = os.path.basename(handler_path).replace('.py', '')
            module = __import__(module_name)
        else:
            # If handler_path is a directory
            module_name = handler_path
            module = __import__(module_name)
        
        # Get the handler function
        if '.' in handler_name:
            # If handler_name is in the format 'module.function'
            parts = handler_name.split('.')
            handler_fn = getattr(module, parts[1])
        else:
            handler_fn = getattr(module, handler_name)
        
        # Run the handler
        print(f"Invoking {handler_name} with test event...")
        response = handler_fn(event, context)
        return response
    except Exception as e:
        print(f"Error running Lambda handler: {str(e)}")
        raise

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='AWS Lambda Test Harness')
    parser.add_argument('--handler', default='lambda_function.lambda_handler',
                      help='Lambda handler (format: file.function)')
    parser.add_argument('--event', help='Path to test event JSON file')
    args = parser.parse_args()
    
    # Parse handler
    if '.' in args.handler:
        handler_file, handler_function = args.handler.split('.', 1)
        handler_path = f"{handler_file}.py"
    else:
        handler_path = "lambda_function.py"
        handler_function = "lambda_handler"
    
    # Set up environment
    configure_aws_env()
    
    # Load test event
    event = load_test_event(args.event)
    
    # Create context
    context = create_lambda_context()
    
    # Run Lambda
    try:
        # Add path for importing the handler
        if not os.path.exists(handler_path):
            # If in the wrong directory, try to find in src directory
            src_handler_path = os.path.join("src", handler_path)
            if os.path.exists(src_handler_path):
                handler_path = src_handler_path
            else:
                raise FileNotFoundError(f"Cannot find Lambda handler: {handler_path}")
        
        # Add the directory containing the handler to sys.path
        sys.path.insert(0, os.path.dirname(os.path.abspath(handler_path)))
        
        # Import the handler module
        module_name = os.path.basename(handler_path).replace('.py', '')
        
        # Dynamically import the handler module
        sys.path.insert(0, '.')
        from src.lambda_function import lambda_handler
        
        # Run the handler
        print(f"Invoking {module_name}.{handler_function} with test event...")
        response = lambda_handler(event, context)
        
        # Print response
        print("\nLambda function response:")
        print(f"Status code: {response['statusCode']}")
        
        if response['statusCode'] == 200:
            print("\nValidation results:")
            results = response['body']['results']
            for column, result in results.items():
                value, confidence, message = result
                print(f"\n{column}:")
                print(f"  Value: {value}")
                print(f"  Confidence: {confidence}")
                print(f"  Message: {message}")
        else:
            print(f"Error: {response['body']}")
        
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 