import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import os

from lambda_function import lambda_handler

# Sample configuration and data
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
        }
    ]
}

SAMPLE_DATA = {
    "rows": [
        {
            "id": 1,
            "name": "John Doe"
        }
    ]
}

@pytest.fixture
def mock_env():
    """Set up test environment variables."""
    os.environ['PERPLEXITY_API_KEY'] = 'test-api-key'
    yield
    del os.environ['PERPLEXITY_API_KEY']

@pytest.fixture
def mock_aws_services():
    """Mock AWS services."""
    with patch('boto3.resource') as mock_s3_resource, \
         patch('boto3.client') as mock_ssm_client:
        
        # Mock S3 bucket
        mock_bucket = MagicMock()
        mock_s3_resource.return_value.Bucket.return_value = mock_bucket
        
        # Mock SSM client
        mock_ssm_client.return_value.get_parameter.return_value = {
            'Parameter': {'Value': 'test-api-key'}
        }
        
        yield {
            's3_resource': mock_s3_resource,
            'ssm_client': mock_ssm_client,
            'bucket': mock_bucket
        }

@pytest.fixture
def mock_perplexity_api():
    """Mock Perplexity API responses."""
    mock_response = {
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
    
    with patch('lambda_function.validate_with_perplexity', return_value=mock_response) as mock:
        yield mock

def test_lambda_handler_success(mock_env, mock_aws_services, mock_perplexity_api):
    """Test successful Lambda execution."""
    test_event = {
        "config": SAMPLE_CONFIG,
        "validation_data": SAMPLE_DATA,
        "bucket_name": "test-validation-bucket"
    }
    
    response = lambda_handler(test_event, None)
    
    assert response['statusCode'] == 200
    assert 'results' in response['body']
    assert 'name' in response['body']['results']

def test_lambda_handler_cache_hit(mock_env, mock_aws_services, mock_perplexity_api):
    """Test cache hit scenario."""
    # Mock cached data
    cached_data = {
        'results': {
            'name': ('John Doe', 0.95, 'Name is valid')
        },
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    
    mock_aws_services['bucket'].Object().get.return_value = {
        'Body': MagicMock(read=lambda: json.dumps(cached_data).encode())
    }
    
    test_event = {
        "config": SAMPLE_CONFIG,
        "validation_data": SAMPLE_DATA,
        "bucket_name": "test-validation-bucket"
    }
    
    response = lambda_handler(test_event, None)
    
    assert response['statusCode'] == 200
    assert response['body'] == cached_data['results']
    mock_perplexity_api.assert_not_called()

def test_lambda_handler_cache_expired(mock_env, mock_aws_services, mock_perplexity_api):
    """Test expired cache scenario."""
    # Mock expired cached data
    expired_time = datetime.now(timezone.utc) - timedelta(days=31)
    cached_data = {
        'results': {
            'name': ('John Doe', 0.95, 'Name is valid')
        },
        'timestamp': expired_time.isoformat()
    }
    
    mock_aws_services['bucket'].Object().get.return_value = {
        'Body': MagicMock(read=lambda: json.dumps(cached_data).encode())
    }
    
    test_event = {
        "config": SAMPLE_CONFIG,
        "validation_data": SAMPLE_DATA,
        "bucket_name": "test-validation-bucket"
    }
    
    response = lambda_handler(test_event, None)
    
    assert response['statusCode'] == 200
    assert 'results' in response['body']
    mock_perplexity_api.assert_called()

def test_lambda_handler_error(mock_env, mock_aws_services):
    """Test error handling."""
    # Mock Perplexity API error
    with patch('lambda_function.validate_with_perplexity', side_effect=Exception("API Error")):
        test_event = {
            "config": SAMPLE_CONFIG,
            "validation_data": SAMPLE_DATA,
            "bucket_name": "test-validation-bucket"
        }
        
        response = lambda_handler(test_event, None)
        
        assert response['statusCode'] == 500
        assert 'error' in json.loads(response['body']) 