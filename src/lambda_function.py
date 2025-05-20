import json
import boto3
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from botocore.exceptions import NoCredentialsError
import asyncio
import aiohttp
import logging
import os
from schema_validator import SchemaValidator
from botocore.config import Config

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
    
    logger.info(f"Calling Perplexity API with prompt length: {len(prompt)} chars")
    
    try:
        async with session.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=data,
            timeout=30  # Add timeout
        ) as response:
            if response.status == 200:
                result = await response.json()
                logger.info(f"API call successful, response length: {len(str(result))} chars")
                return result
            else:
                error_text = await response.text()
                logger.error(f"API call failed with status {response.status}: {error_text}")
                # Return a structured error response that can be safely handled
                return {
                    "error": True,
                    "status": response.status,
                    "message": error_text
                }
    except aiohttp.ClientError as e:
        logger.error(f"HTTP client error: {str(e)}")
        return {"error": True, "message": f"HTTP client error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error calling API: {str(e)}")
        return {"error": True, "message": f"Unexpected error: {str(e)}"}

def get_cache_key(data: Dict) -> str:
    """Generate a unique cache key for the validation request."""
    # Check if debug mode is enabled
    debug_options = data.get('debug_options', {})
    print_cache_details = debug_options.get('print_cache_key_details', False)
    
    # Include model name in the cache key
    cache_data = {
        **data,
        "model": "sonar-pro"  # Add model to ensure different models don't share cache
    }
    
    # Remove debug_options from the data being hashed
    if 'debug_options' in cache_data:
        del cache_data['debug_options']
    
    # Sort the keys to ensure consistent hash
    json_str = json.dumps(cache_data, sort_keys=True)
    
    if print_cache_details:
        logger.info(f"CACHE KEY DEBUG: Hash input JSON (truncated): {json_str[:200]}...")
        logger.info(f"CACHE KEY DEBUG: Hash input data structure: {list(cache_data.keys())}")
        if 'validation_data' in cache_data and 'rows' in cache_data['validation_data']:
            for i, row in enumerate(cache_data['validation_data']['rows']):
                logger.info(f"CACHE KEY DEBUG: Row {i} keys: {list(row.keys())}")
                for key, value in row.items():
                    logger.info(f"CACHE KEY DEBUG: Row {i} - {key}: {value}")
    
    data_bytes = json_str.encode()
    hash_result = hashlib.sha256(data_bytes).hexdigest()
    
    if print_cache_details:
        logger.info(f"CACHE KEY DEBUG: Generated hash: {hash_result}")
    
    return hash_result

async def process_validation_batch(
    session: aiohttp.ClientSession,
    batch: List[Dict],
    api_key: str,
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
            logger.error(f"Exception for {target.column}: {str(result)}")
            processed_results[target.column] = (None, 0.0, f"Error: {str(result)}")
        elif isinstance(result, dict) and result.get('error'):
            # Handle structured error responses from the API call
            logger.error(f"API error for {target.column}: {result.get('message')}")
            processed_results[target.column] = (None, 0.0, f"API Error: {result.get('message')}")
        else:
            validated_value, confidence, message = validator.parse_validation_result(result, target)
            processed_results[target.column] = (validated_value, confidence, message)
    
    return {
        "results": processed_results
    }

def lambda_handler(event, context):
    """Main Lambda handler function."""
    try:
        # Check for debug options
        debug_options = event.get('debug_options', {})
        if debug_options and debug_options.get('print_cache_key_details'):
            logger.info(f"DEBUG MODE ENABLED: Will print cache key generation details")
        
        # Initialize S3 client with standard configuration
        s3_bucket = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
        s3_client = boto3.client('s3')
        
        # Get API key from SSM
        api_key = get_perplexity_api_key()
        
        # Parse input data and initialize validator
        config = event.get('config', {})
        validator = SchemaValidator(config)
        
        # Prepare validation data
        validation_data = event.get('validation_data', {})
        rows = validation_data.get('rows', [])
        
        # Generate cache key - make sure we include any debug options
        cache_key_data = {'validation_data': validation_data}
        if debug_options:
            cache_key_data['debug_options'] = debug_options
        cache_key = get_cache_key(cache_key_data)
        cache_path = f"validation_results/{cache_key}.json"
        
        # Try S3 cache first
        try:
            logger.info(f"Checking S3 cache at {s3_bucket}/{cache_path}")
            
            try:
                # Get object from S3
                response = s3_client.get_object(
                    Bucket=s3_bucket,
                    Key=cache_path
                )
                cache_data = json.loads(response['Body'].read().decode())
                
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
            except s3_client.exceptions.NoSuchKey:
                logger.info("No cache found, proceeding with validation")
            except Exception as e:
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
                    
                    # Cache the results in S3
                    try:
                        # Prepare cache data with UTC timestamp
                        current_time = datetime.now(timezone.utc)
                        cache_data = {
                            'results': results,
                            'timestamp': current_time.isoformat()
                        }
                        
                        # Convert cache_data to JSON-serializable format
                        json_serializable_cache = json.dumps(cache_data, default=str)
                        
                        # Store in S3
                        s3_client.put_object(
                            Bucket=s3_bucket,
                            Key=cache_path,
                            Body=json_serializable_cache,
                            ContentType='application/json',
                            Metadata={'timestamp': current_time.isoformat()}
                        )
                        logger.info(f"Successfully cached results to {cache_path}")
                    except Exception as e:
                        logger.warning(f"Failed to cache results to S3: {str(e)}")
                    
                    return results
            
            # Run the async validation process
            results = asyncio.run(process_validations())
            
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
    except Exception as e:
        logger.error(f"Error in validation process: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        } 