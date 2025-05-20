import json
import boto3
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from botocore.exceptions import NoCredentialsError
import asyncio
import aiohttp
import logging
import os
from schema_validator import SchemaValidator
from botocore.config import Config
import traceback

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients with retry configuration
config = Config(
    retries = dict(
        max_attempts = 3
    )
)
s3 = boto3.client('s3', config=config)
ssm = boto3.client('ssm', config=config)

def get_perplexity_api_key() -> str:
    """Get Perplexity API key from environment or SSM."""
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        try:
            response = ssm.get_parameter(
                Name='/Perplexity_API_Key',
                WithDecryption=True
            )
            api_key = response['Parameter']['Value']
        except Exception as e:
            logger.error(f"Failed to get API key from SSM: {str(e)}")
            raise
    return api_key

async def validate_with_perplexity(
    session: aiohttp.ClientSession,
    prompt: str,
    api_key: str,
    model: str = "sonar-pro"
) -> Dict[str, Any]:
    """Validate a prompt using Perplexity API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a data validation expert. Return your answer in valid JSON format."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 1000,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                        "quote": {"type": "string"},
                        "sources": {"type": "array", "items": {"type": "string"}},
                        "update_required": {"type": "boolean"},
                        "explanation": {"type": "string"}
                    },
                    "required": ["answer", "confidence", "sources", "update_required"]
                }
            }
        }
    }
    
    try:
        logger.info(f"Sending request to Perplexity API with model: {model}")
        logger.info(f"Request data: {json.dumps(data, indent=2)}")
        
        async with session.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        ) as response:
            response_text = await response.text()
            logger.info(f"API Response status: {response.status}")
            logger.info(f"API Response body: {response_text}")
            
            if response.status != 200:
                raise Exception(f"API returned status {response.status}: {response_text}")
            
            return json.loads(response_text)
    except Exception as e:
        logger.error(f"Error calling Perplexity API: {str(e)}")
        raise

def get_cache_key(row: Dict[str, Any], target: str) -> str:
    """Generate a unique cache key for validation request."""
    # Sort keys to ensure consistent hashing
    sorted_row = dict(sorted(row.items()))
    row_str = json.dumps(sorted_row, sort_keys=True)
    return hashlib.md5(f"{row_str}:{target}".encode()).hexdigest()

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for validation requests."""
    try:
        # Initialize validator with config
        config = event.get('config', {})
        validator = SchemaValidator(config)
        
        # Get API key and S3 bucket
        api_key = get_perplexity_api_key()
        s3_bucket = os.environ['S3_CACHE_BUCKET']
        
        # Process rows
        rows = event.get('validation_data', {}).get('rows', [])
        validation_results = {}
        total_cache_hits = 0
        total_cache_misses = 0
        
        async def process_all_rows():
            nonlocal total_cache_hits, total_cache_misses
            
            # Process rows in batches
            batch_size = 5  # Adjust based on API limits
            async with aiohttp.ClientSession() as session:
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    batch_tasks = []
                    
                    for row in batch:
                        row_results = {}
                        for target in validator.validation_targets:
                            # Check cache
                            cache_key = get_cache_key(row, target.column)
                            try:
                                cache_response = s3.get_object(
                                    Bucket=s3_bucket,
                                    Key=f"validation_cache/{cache_key}.json"
                                )
                                cached_result = json.loads(cache_response['Body'].read())
                                row_results[target.column] = cached_result
                                total_cache_hits += 1
                                logger.info(f"Cache hit for {target.column}")
                                continue
                            except:
                                total_cache_misses += 1
                                logger.info(f"Cache miss for {target.column}")
                            
                            # Process validation
                            prompt = validator.generate_validation_prompt(row, target)
                            result = await validate_with_perplexity(session, prompt, api_key)
                            
                            # Parse and store result
                            parsed_result = validator.parse_validation_result(result, target)
                            row_results[target.column] = {
                                'value': parsed_result[0],
                                'confidence': parsed_result[1],
                                'sources': parsed_result[2],
                                'confidence_level': parsed_result[3],
                                'quote': parsed_result[4],
                                'main_source': parsed_result[5]
                            }
                            
                            # Cache result
                            try:
                                s3.put_object(
                                    Bucket=s3_bucket,
                                    Key=f"validation_cache/{cache_key}.json",
                                    Body=json.dumps(row_results[target.column]),
                                    ContentType='application/json'
                                )
                                logger.info(f"Cached result for {target.column}")
                            except Exception as e:
                                logger.error(f"Failed to cache result: {str(e)}")
                        
                        # Determine next check date
                        next_check, reasons = validator.determine_next_check_date(row, row_results)
                        row_results['next_check'] = next_check.isoformat() if next_check else None
                        row_results['reasons'] = reasons
                        
                        validation_results[i + len(batch_tasks)] = row_results
                    
                    # Wait for all tasks in the batch to complete
                    await asyncio.gather(*batch_tasks)
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process_all_rows())
        finally:
            loop.close()
        
        return {
            'statusCode': 200,
            'body': {
                'validation_results': validation_results,
                'cache_stats': {
                    'hits': total_cache_hits,
                    'misses': total_cache_misses
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'body': {
                'error': str(e)
            }
        } 