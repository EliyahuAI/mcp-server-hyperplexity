import sys
import os
import json
from datetime import datetime, timezone
import asyncio
from unittest.mock import patch, MagicMock

# Add src directory to Python path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from lambda_function import lambda_handler

# Sample configuration
SAMPLE_CONFIG = {
    "primary_key": ["id"],
    "cache_ttl_days": 30,
    "validation_targets": [
        {
            "column": "name",
            "validation_type": "string",
            "rules": {
                "min_length": 2,
                "max_length": 100
            },
            "description": "Validate name length"
        },
        {
            "column": "age",
            "validation_type": "number",
            "rules": {
                "min": 0,
                "max": 120
            },
            "description": "Validate age range"
        }
    ]
}

# Sample validation data
SAMPLE_DATA = {
    "rows": [
        {
            "id": 1,
            "name": "John Doe",
            "age": 30
        },
        {
            "id": 2,
            "name": "Jane Smith",
            "age": 25
        }
    ]
}

# Mock Perplexity API response
MOCK_API_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps({
                    "validated_value": "John Doe",
                    "confidence": 0.95,
                    "message": "Name is valid"
                })
            }
        }
    ]
}

async def mock_validate_with_perplexity(*args, **kwargs):
    """Mock function to simulate Perplexity API response."""
    return MOCK_API_RESPONSE

def main():
    # Set up test environment
    os.environ['PERPLEXITY_API_KEY'] = 'test-api-key'
    
    # Create test event
    test_event = {
        "config": SAMPLE_CONFIG,
        "validation_data": SAMPLE_DATA,
        "bucket_name": "test-validation-bucket"
    }
    
    # Mock AWS services
    with patch('boto3.resource') as mock_s3_resource, \
         patch('boto3.client') as mock_ssm_client, \
         patch('lambda_function.validate_with_perplexity', side_effect=mock_validate_with_perplexity):
        
        # Mock S3 bucket
        mock_bucket = MagicMock()
        mock_s3_resource.return_value.Bucket.return_value = mock_bucket
        
        # Mock SSM client
        mock_ssm_client.return_value.get_parameter.return_value = {
            'Parameter': {'Value': 'test-api-key'}
        }
        
        # Run the Lambda handler
        response = lambda_handler(test_event, None)
        
        # Print results
        print("\nLambda Response:")
        print(json.dumps(response, indent=2))
        
        # Print validation results
        if response['statusCode'] == 200:
            results = response['body']
            print("\nValidation Results:")
            for column, (value, confidence, message) in results['results'].items():
                print(f"\n{column}:")
                print(f"  Value: {value}")
                print(f"  Confidence: {confidence}")
                print(f"  Message: {message}")

if __name__ == "__main__":
    main() 