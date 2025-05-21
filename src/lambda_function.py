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
                        "explanation": {"type": "string"},
                        "substantially_different": {"type": "boolean"},
                        "consistent_with_model_knowledge": {"type": "string", "description": "Indicate if the answer is consistent with the model's general knowledge beyond the specific sources cited. Should be 'Yes' or 'No' followed by explanation."}
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
        total_multiplex_validations = 0
        total_single_validations = 0
        
        async def process_all_rows():
            nonlocal total_cache_hits, total_cache_misses, total_multiplex_validations, total_single_validations
            
            # Process rows in batches
            batch_size = 5  # Adjust based on API limits
            async with aiohttp.ClientSession() as session:
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    row_tasks = []
                    
                    for row_idx, row in enumerate(batch):
                        task = asyncio.create_task(process_row(session, row, i + row_idx))
                        row_tasks.append(task)
                    
                    # Wait for all rows in the batch to complete
                    batch_results = await asyncio.gather(*row_tasks)
                    
                    # Store results
                    for idx, result in batch_results:
                        validation_results[idx] = result
        
        async def process_row(session, row, row_idx):
            """Process a single row with progressive multiplexing."""
            nonlocal total_cache_hits, total_cache_misses, total_multiplex_validations, total_single_validations
            
            row_results = {}
            accumulated_results = {}  # Store results to pass as context to later groups
            
            # Get ignored fields - add them to results without processing
            ignored_fields = validator._get_ignored_fields(validator.validation_targets)
            if ignored_fields:
                logger.info(f"Adding {len(ignored_fields)} IGNORED fields without processing")
                for ignored_field in ignored_fields:
                    # Simply copy the original value to the result without validation
                    original_value = row.get(ignored_field.column, "")
                    row_results[ignored_field.column] = {
                        'value': original_value,
                        'confidence': 1.0,  # Max confidence since we're not checking
                        'confidence_level': "HIGH",
                        'sources': [],
                        'quote': "",
                        'main_source': "",
                        'update_required': False,  # Never update ignored fields
                        'substantially_different': False
                    }
            
            # Process ID fields first
            id_fields = validator._get_id_fields(validator.validation_targets)
            if id_fields:
                logger.info(f"Processing {len(id_fields)} ID fields")
                for id_field in id_fields:
                    await process_single_column(session, row, row_results, id_field)
                    
                    # Add ID field results to accumulated results
                    if id_field.column in row_results:
                        accumulated_results[id_field.column] = row_results[id_field.column]
            
            # Group validation targets by search group
            grouped_targets = validator._group_columns_by_search_group(validator.validation_targets)
            
            # Sort search groups by number to ensure sequential processing
            sorted_groups = sorted(grouped_targets.keys())
            
            # Process each search group in order
            for group_id in sorted_groups:
                targets = grouped_targets[group_id]
                
                # Skip ID fields that were already processed and IGNORED fields
                targets = [t for t in targets if t.importance.upper() != "ID" and t.importance.upper() != "IGNORED"]
                if not targets:
                    continue
                
                logger.info(f"Processing search group {group_id} with {len(targets)} columns")
                
                if len(targets) > 1:
                    # Multiplex validation for this group
                    await process_multiplex_group(session, row, row_results, targets, accumulated_results)
                    total_multiplex_validations += 1
                else:
                    # Single column validation
                    for target in targets:
                        await process_single_column(session, row, row_results, target)
                        total_single_validations += 1
                
                # Add this group's results to accumulated results for next groups
                for target in targets:
                    if target.column in row_results:
                        accumulated_results[target.column] = row_results[target.column]
            
            # Revisit CRITICAL fields with less than HIGH confidence
            critical_fields = validator._get_critical_fields(validator.validation_targets)
            critical_revisits = []
            
            for critical_field in critical_fields:
                if critical_field.column in row_results:
                    result = row_results[critical_field.column]
                    confidence_level = result.get('confidence_level', 'LOW')
                    
                    if confidence_level != 'HIGH':
                        logger.info(f"Revisiting CRITICAL field {critical_field.column} with {confidence_level} confidence")
                        critical_revisits.append(critical_field)
            
            # Process revisit fields individually with all accumulated context
            for revisit_target in critical_revisits:
                logger.info(f"Re-validating critical field: {revisit_target.column}")
                # Process individually to get better confidence
                await process_single_column(session, row, row_results, revisit_target, accumulated_results)
                total_single_validations += 1
            
            # Determine next check date
            next_check, reasons = validator.determine_next_check_date(row, row_results)
            row_results['next_check'] = next_check.isoformat() if next_check else None
            row_results['reasons'] = reasons
            
            return row_idx, row_results
        
        async def process_multiplex_group(session, row, row_results, targets, previous_results=None):
            """Process a group of columns with a single multiplex API call."""
            nonlocal total_cache_hits, total_cache_misses, total_single_validations
            
            # Check if all targets in this group are in cache
            all_cached = True
            cached_results = {}
            
            for target in targets:
                cache_key = get_cache_key(row, target.column)
                try:
                    cache_response = s3.get_object(
                        Bucket=s3_bucket,
                        Key=f"validation_cache/{cache_key}.json"
                    )
                    cached_result = json.loads(cache_response['Body'].read())
                    cached_results[target.column] = cached_result
                    total_cache_hits += 1
                    logger.info(f"Cache hit for {target.column}")
                except:
                    all_cached = False
                    break
            
            if all_cached:
                # If everything was cached, use cached results
                logger.info(f"Using cached results for all {len(targets)} columns in search group")
                for column, result in cached_results.items():
                    row_results[column] = result
                return
            
            # Generate multiplex prompt and validate
            logger.info(f"Generating multiplex prompt for {len(targets)} columns with context from previous groups")
            prompt = validator.generate_multiplex_prompt(row, targets, previous_results)
            
            # Call Perplexity API
            result = await validate_with_perplexity(session, prompt, api_key)
            
            # Parse multiplex results
            parsed_results = validator.parse_multiplex_result(result, row)
            
            # Process and store results for each column
            for target in targets:
                if target.column in parsed_results:
                    parsed_result = parsed_results[target.column]
                    value = parsed_result[0]
                    numeric_confidence = parsed_result[1]
                    sources = parsed_result[2]
                    confidence_level = parsed_result[3]
                    quote = parsed_result[4]
                    main_source = parsed_result[5]
                    update_required = parsed_result[6]
                    substantially_different = parsed_result[7]
                    consistent_with_model_knowledge = parsed_result[8] if len(parsed_result) > 8 else None
                    
                    # If update_required wasn't set by the API, set it based on substantially_different
                    if update_required is None:
                        update_required = substantially_different
                    
                    row_results[target.column] = {
                        'value': value,
                        'confidence': numeric_confidence,
                        'sources': sources,
                        'confidence_level': confidence_level,
                        'quote': quote,
                        'main_source': main_source,
                        'update_required': update_required,
                        'substantially_different': substantially_different
                    }
                    
                    # Add consistent_with_model_knowledge if available
                    if consistent_with_model_knowledge:
                        row_results[target.column]['consistent_with_model_knowledge'] = consistent_with_model_knowledge
                    
                    # Include any citations from the API response
                    if 'citations' in result:
                        row_results[target.column]['api_citations'] = result['citations']
                    
                    # Cache result
                    try:
                        cache_key = get_cache_key(row, target.column)
                        s3.put_object(
                            Bucket=s3_bucket,
                            Key=f"validation_cache/{cache_key}.json",
                            Body=json.dumps(row_results[target.column]),
                            ContentType='application/json'
                        )
                        logger.info(f"Cached multiplex result for {target.column}")
                    except Exception as e:
                        logger.error(f"Failed to cache multiplex result for {target.column}: {str(e)}")
                else:
                    # If column wasn't found in multiplex result, do single validation
                    logger.warning(f"Column {target.column} not found in multiplex result, falling back to single validation")
                    await process_single_column(session, row, row_results, target, previous_results)
                    total_single_validations += 1
        
        async def process_single_column(session, row, row_results, target, previous_results=None):
            """Process a single column validation."""
            nonlocal total_cache_hits, total_cache_misses
            
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
                return
            except:
                total_cache_misses += 1
                logger.info(f"Cache miss for {target.column}")
            
            # Get original value for comparison
            original_value = row.get(target.column, "")
            
            # Process validation
            prompt = validator.generate_validation_prompt(row, target, previous_results)
            result = await validate_with_perplexity(session, prompt, api_key)
            
            # Parse and store result
            parsed_result = validator.parse_validation_result(result, target, original_value)
            
            # Check if result is substantially different from original
            value = parsed_result[0]
            numeric_confidence = parsed_result[1]
            sources = parsed_result[2]
            confidence_level = parsed_result[3]
            quote = parsed_result[4]
            main_source = parsed_result[5]
            update_required = parsed_result[6]  # From the API response
            substantially_different = parsed_result[7]  # From the API response or calculated
            consistent_with_model_knowledge = parsed_result[8] if len(parsed_result) > 8 else None
            
            # If update_required wasn't set by the API, set it based on substantially_different
            if update_required is None:
                update_required = substantially_different
            
            row_results[target.column] = {
                'value': value,
                'confidence': numeric_confidence,
                'sources': sources,
                'confidence_level': confidence_level, 
                'quote': quote,
                'main_source': main_source,
                'update_required': update_required,
                'substantially_different': substantially_different
            }
            
            # Add consistent_with_model_knowledge if available
            if consistent_with_model_knowledge:
                row_results[target.column]['consistent_with_model_knowledge'] = consistent_with_model_knowledge
            
            # Also include any other fields from the API response
            if isinstance(result, dict) and 'choices' in result and len(result['choices']) > 0:
                message = result['choices'][0]['message']
                if 'content' in message:
                    try:
                        content_json = json.loads(message.get('content', '{}'))
                        # Copy over any fields we don't already have
                        for key, value in content_json.items():
                            if key not in row_results[target.column]:
                                row_results[target.column][key] = value
                    except:
                        pass  # If we can't parse the content as JSON, just continue
            
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
                    'misses': total_cache_misses,
                    'multiplex_validations': total_multiplex_validations,
                    'single_validations': total_single_validations
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