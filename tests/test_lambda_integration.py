import json
import os
import sys
from pathlib import Path
import pytest
from datetime import datetime, timezone
import hashlib

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from lambda_function import lambda_handler

# Sample test data
SAMPLE_CONFIG = {
    "primary_key": ["id"],
    "validation_targets": [
        {
            "column": "name",
            "validation_type": "string",
            "rules": {
                "min_length": 2,
                "max_length": 100
            },
            "description": "Must be a valid name with no special characters"
        },
        {
            "column": "email",
            "validation_type": "email",
            "rules": {
                "format": "email"
            },
            "description": "Must be a valid email address"
        }
    ],
    "cache_ttl_days": 30
}

SAMPLE_VALIDATION_DATA = {
    "rows": [
        {
            "id": "123",
            "name": "John Doe",
            "email": "john@example.com",
            "type": "customer"
        },
        {
            "id": "124",
            "name": "Jane Smith",
            "email": "jane@example.com",
            "type": "customer"
        }
    ]
}

# Set S3 bucket name to the one that worked previously
BUCKET_NAME = 'perplexity-temp-bucket--use1-az6--x-s3'

# Prepare test environment - use if you need to run tests before running pytest
def setup_test_environment():
    """Setup API key and other environment variables for testing."""
    # Set test mode to enable API key fallback
    os.environ['TEST_MODE'] = 'true'
    
    # For Perplexity API key, use existing environment variable if available
    if not os.environ.get('PERPLEXITY_API_KEY'):
        # Try to load from .env file if no environment variable exists
        try:
            with open(os.path.join(os.path.dirname(__file__), '..', '.env'), 'r') as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        key, value = line.strip().split('=', 1)
                        os.environ[key] = value
        except FileNotFoundError:
            print("No .env file found. Using TEST_MODE fallback.")
            
    # Print confirmation that we're using the environment API key or test mode
    if os.environ.get('PERPLEXITY_API_KEY'):
        print(f"Using Perplexity API key from environment (ends with: ...{os.environ.get('PERPLEXITY_API_KEY', '')[-4:]})")
    else:
        print("Using TEST_MODE fallback for API key")
    
    print(f"Using S3 bucket: {os.environ.get('TEST_BUCKET_NAME', BUCKET_NAME)}")

def get_cache_key(data):
    """Generate a cache key for testing to check if items are cached."""
    # Include model name in the cache key
    cache_data = {
        **data,
        "model": "sonar-pro"  # Add model to ensure different models don't share cache
    }
    data_bytes = json.dumps(cache_data, sort_keys=True).encode()
    return hashlib.sha256(data_bytes).hexdigest()

# Integration Test 1: Basic Validation
@pytest.mark.integration
def test_lambda_handler_integration():
    """Test Lambda handler with real Perplexity API and S3 bucket."""
    setup_test_environment()
    
    # Use the working bucket name
    bucket_name = os.environ.get('TEST_BUCKET_NAME', BUCKET_NAME)
    
    event = {
        'bucket_name': bucket_name,
        'config': SAMPLE_CONFIG,
        'validation_data': SAMPLE_VALIDATION_DATA
    }
    
    response = lambda_handler(event, {})
    
    assert response['statusCode'] == 200
    assert 'results' in response['body']
    assert 'cache_key' in response['body']
    
    # Check validation results
    results = response['body']['results']
    for column, result in results.items():
        if not column.endswith('_next_check'):
            value, confidence, message = result
            assert value is not None
            assert 0 <= confidence <= 1
            assert isinstance(message, str)

# Integration Test 2: Caching
@pytest.mark.integration
def test_lambda_handler_caching_integration():
    """Test caching with real S3 bucket."""
    setup_test_environment()
    
    # Use the working bucket name
    bucket_name = os.environ.get('TEST_BUCKET_NAME', BUCKET_NAME)
    
    event = {
        'bucket_name': bucket_name,
        'config': SAMPLE_CONFIG,
        'validation_data': SAMPLE_VALIDATION_DATA
    }
    
    # First call - should perform validation
    response1 = lambda_handler(event, {})
    
    # Second call - should use cache
    response2 = lambda_handler(event, {})
    
    assert response1['statusCode'] == 200
    assert response2['statusCode'] == 200
    
    # Either the responses should match exactly, or the second one should indicate it used cache
    results1 = response1['body']
    results2 = response2['body']
    
    # Compare key validation results
    for key in SAMPLE_VALIDATION_DATA['rows'][0].keys():
        if key in results1['results'] and key in results2['results']:
            assert results1['results'][key][0] == results2['results'][key][0]  # validated value
            assert results1['results'][key][2] == results2['results'][key][2]  # message

# Integration Test 3: Next Check Date Logic
@pytest.mark.integration
def test_next_check_date_integration():
    """Test that next check dates are calculated correctly."""
    setup_test_environment()
    
    # Use the working bucket name
    bucket_name = os.environ.get('TEST_BUCKET_NAME', BUCKET_NAME)
    
    event = {
        'bucket_name': bucket_name,
        'config': SAMPLE_CONFIG,
        'validation_data': SAMPLE_VALIDATION_DATA
    }
    
    response = lambda_handler(event, {})
    
    assert response['statusCode'] == 200
    
    # Check for next_check dates
    results = response['body']['results']
    check_counts = 0
    
    # Get current time in UTC for comparison
    now = datetime.now(timezone.utc)
    
    for key in results:
        if key.endswith('_next_check'):
            check_counts += 1
            date_str, confidence, reasons = results[key]
            # Try to parse the date to ensure it's a valid ISO format
            try:
                date_obj = datetime.fromisoformat(date_str)
                # Make sure the date is timezone-aware for comparison
                if date_obj.tzinfo is None:
                    date_obj = date_obj.replace(tzinfo=timezone.utc)
                assert date_obj > now
            except ValueError:
                assert False, f"Invalid date format: {date_str}"
            
            assert confidence > 0
            assert len(reasons) > 0
    
    # Make sure we have a next check date for each row
    assert check_counts == len(SAMPLE_VALIDATION_DATA['rows'])

if __name__ == '__main__':
    # This allows running the tests directly without pytest
    setup_test_environment()
    print("Running integration test 1: Basic validation")
    test_lambda_handler_integration()
    print("Running integration test 2: Caching")
    test_lambda_handler_caching_integration()
    print("Running integration test 3: Next check date logic")
    test_next_check_date_integration()
    print("All integration tests passed!") 