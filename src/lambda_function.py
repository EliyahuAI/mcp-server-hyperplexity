import json
import boto3
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import pandas as pd
from botocore.exceptions import NoCredentialsError
import asyncio
import aiohttp
import logging
import os
from schema_validator import SchemaValidator, ValidationTarget

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_perplexity_api_key():
    """Get Perplexity API key from environment variable or SSM, with fallback for testing."""
    # Try environment variable first
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if api_key:
        return api_key
    
    # Try AWS SSM Parameter Store
    try:
        ssm_client = boto3.client('ssm')
        parameter_name = '/Perplexity_API_Key'
        response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
        return response['Parameter']['Value']
    except Exception as e:
        logger.warning(f"Could not retrieve API key from SSM: {str(e)}")
        
        # TESTING ONLY: If running integration tests and no key is available, use a default
        # In production, this should be properly configured through environment or SSM
        if 'TEST_MODE' in os.environ:
            logger.warning("USING TEST API KEY - THIS SHOULD NOT HAPPEN IN PRODUCTION")
            # For testing integration, insert your API key here TEMPORARILY
            return "pp-..." # Replace with actual API key for testing
        
        # In production, we should fail if the key isn't available
        raise ValueError("No Perplexity API key found. Set PERPLEXITY_API_KEY environment variable or configure SSM parameter.")

async def validate_with_perplexity(session: aiohttp.ClientSession, prompt: str, api_key: str) -> Dict:
    """Validate a single prompt using Perplexity API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "sonar-pro",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000
    }
    
    async with session.post(
        "https://api.perplexity.ai/chat/completions",
        headers=headers,
        json=data
    ) as response:
        if response.status == 200:
            result = await response.json()
            return result
        else:
            error_text = await response.text()
            raise Exception(f"Perplexity API error: {error_text}")

def get_cache_key(data: Dict) -> str:
    """Generate a unique cache key for the validation request."""
    # Include model name in the cache key
    cache_data = {
        **data,
        "model": "sonar-pro"  # Add model to ensure different models don't share cache
    }
    data_bytes = json.dumps(cache_data, sort_keys=True).encode()
    return hashlib.sha256(data_bytes).hexdigest()

async def process_validation_batch(
    session: aiohttp.ClientSession,
    batch: List[Dict],
    api_key: str,
    s3_bucket: str,
    cache_key: str,
    validator: SchemaValidator
) -> Dict:
    """Process a batch of validations in parallel."""
    tasks = []
    for item in batch:
        row = item['row']
        target = item['target']
        prompt = validator.generate_validation_prompt(row, target)
        tasks.append(validate_with_perplexity(session, prompt, api_key))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results and handle any errors
    processed_results = {}
    for idx, (item, result) in enumerate(zip(batch, results)):
        target = item['target']
        if isinstance(result, Exception):
            processed_results[target.column] = (None, 0.0, f"Error: {str(result)}")
        else:
            validated_value, confidence, message = validator.parse_validation_result(result, target)
            processed_results[target.column] = (validated_value, confidence, message)
    
    return {
        "results": processed_results,
        "cache_key": cache_key
    }

def lambda_handler(event, context):
    """Main Lambda handler function."""
    try:
        # Initialize AWS clients
        s3 = boto3.resource('s3')
        bucket_name = event.get('bucket_name', 'validation-cache-bucket')
        bucket = s3.Bucket(bucket_name)
        
        # Get API key from SSM
        api_key = get_perplexity_api_key()
        
        # Parse input data and initialize validator
        config = event.get('config', {})
        validator = SchemaValidator(config)
        
        # Prepare validation data
        validation_data = event.get('validation_data', {})
        rows = validation_data.get('rows', [])
        
        # Generate cache key
        cache_key = get_cache_key(validation_data)
        cache_path = f"validation_results/{cache_key}.json"
        
        # Check cache first
        try:
            cache_obj = bucket.Object(cache_path).get()
            body_content = cache_obj['Body'].read().decode() if hasattr(cache_obj.get('Body', {}), 'read') else '{}'
            cache_data = json.loads(body_content)
            
            # Check if cache is still valid
            cache_timestamp = datetime.fromisoformat(cache_data['timestamp'])
            if cache_timestamp.tzinfo is None:
                cache_timestamp = cache_timestamp.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - cache_timestamp).days < config.get('cache_ttl_days', 30):
                logger.info("Returning cached validation results")
                return {
                    'statusCode': 200,
                    'body': cache_data['results']
                }
        except Exception as e:
            if hasattr(e, 'response') and e.response.get('Error', {}).get('Code') == 'NoSuchKey':
                logger.info("No cache found, proceeding with validation")
            else:
                logger.warning(f"Cache error: {str(e)}")
                logger.info("Proceeding with validation")
        
        # Prepare validation batches
        validation_batches = []
        for row in rows:
            for target in validator.validation_targets:
                validation_batches.append({
                    'row': row,
                    'target': target
                })
        
        # Process validation in batches
        async def process_validations():
            async with aiohttp.ClientSession() as session:
                results = await process_validation_batch(
                    session,
                    validation_batches,
                    api_key,
                    bucket_name,
                    cache_key,
                    validator
                )
                
                # Calculate next check dates
                for row in rows:
                    row_key = "|".join(str(row[col]) for col in validator.primary_key)
                    next_check_date, reasons = validator.determine_next_check_date(
                        row,
                        results['results']
                    )
                    if next_check_date:
                        # Convert datetime to string
                        next_check_str = next_check_date.isoformat()
                        results['results'][f"{row_key}_next_check"] = (next_check_str, 1.0, reasons)
                
                return results
        
        # Run the async validation process
        results = asyncio.run(process_validations())
        
        # Cache the results with UTC timestamp
        current_time = datetime.now(timezone.utc)
        cache_data = {
            'results': results,
            'timestamp': current_time.isoformat()
        }
        
        # Convert cache_data to JSON-serializable format
        json_serializable_cache = json.dumps(cache_data, default=str)
        
        try:
            bucket.put_object(
                Key=cache_path,
                Body=json_serializable_cache,
                Metadata={'timestamp': current_time.isoformat()}
            )
        except Exception as e:
            logger.warning(f"Failed to cache results: {str(e)}")
        
        return {
            'statusCode': 200,
            'body': results
        }
        
    except Exception as e:
        logger.error(f"Error in validation process: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        } 