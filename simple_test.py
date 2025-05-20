"""
Simple test script to verify Lambda function works.
Place this in the same directory as lambda_function.py and schema_validator.py.
"""
import json
import os

# Set test mode to enable API key fallback
os.environ['TEST_MODE'] = 'true'

# Import after setting TEST_MODE
from lambda_function import lambda_handler

# Test event
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

def main():
    """Run the Lambda handler with test event."""
    print("Testing Lambda function...")
    
    # Invoke handler
    response = lambda_handler(test_event, {})
    
    # Print response
    print(f"\nStatus Code: {response['statusCode']}")
    if response['statusCode'] == 200:
        print("\nValidation results:")
        for key, result in response['body']['results'].items():
            print(f"\n{key}:")
            value, confidence, message = result
            print(f"  Value: {value}")
            print(f"  Confidence: {confidence}")
            print(f"  Message: {message}")
    else:
        print(f"Error: {response['body']}")
    
    print("\nTest complete!")

if __name__ == "__main__":
    main() 