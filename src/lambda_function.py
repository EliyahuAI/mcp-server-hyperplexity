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
from perplexity_schema import get_response_format_schema

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Add a handler to ensure logs appear in CloudWatch
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)
    logger.info("Initialized logger with StreamHandler")
else:
    logger.info("Logger already has handlers, skipping handler setup")

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
    
    # Use multiplex schema since we're always using multiplex format now
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a data validation expert. Return your answer in valid JSON format."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 1000,
        "response_format": get_response_format_schema(is_multiplex=True)
    }
    
    try:
        # Log the formatted prompt for better diagnostics
        logger.info(f"Sending request to Perplexity API with model: {model}")
        
        # Log a readable version of the prompt for debugging
        prompt_lines = prompt.split('\n')
        formatted_prompt = "\n".join([f"  {line}" for line in prompt_lines])
        logger.info(f"Formatted prompt:\n{formatted_prompt}")
        
        # Simplified request data log (without the full prompt)
        simplified_data = {
            "model": data["model"],
            "temperature": data["temperature"],
            "max_tokens": data["max_tokens"],
            "response_format": data["response_format"]
        }
        logger.info(f"Request config: {json.dumps(simplified_data, indent=2)}")
        
        async with session.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        ) as response:
            response_text = await response.text()
            logger.info(f"API Response status: {response.status}")
            
            # Parse the JSON response and pretty print for CloudWatch logs
            try:
                response_json = json.loads(response_text)
                
                # Extract and format the content for better readability in logs
                if 'choices' in response_json and len(response_json['choices']) > 0:
                    message = response_json['choices'][0].get('message', {})
                    content = message.get('content', '')
                    
                    # Try to parse and format the content as JSON
                    try:
                        content_json = json.loads(content)
                        formatted_content = json.dumps(content_json, indent=2)
                        
                        # Create a copy with formatted content for logging
                        log_response = response_json.copy()
                        log_response['choices'][0]['message']['content'] = f"PARSED JSON:\n{formatted_content}"
                        
                        # Log the formatted response
                        logger.info(f"API Response body (with formatted content): {json.dumps(log_response, indent=2)}")
                    except:
                        # If content isn't valid JSON, log as is
                        logger.info(f"API Response body: {json.dumps(response_json, indent=2)}")
                else:
                    logger.info(f"API Response body: {json.dumps(response_json, indent=2)}")
                    
            except json.JSONDecodeError:
                # If response isn't valid JSON, log as is
                logger.info(f"API Response body (raw): {response_text}")
            
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
        # Test CloudWatch logging - with extreme verbosity for debugging
        print("==== LAMBDA FUNCTION STARTED - CONSOLE.LOG PRINT ====")
        logger.error("==== LAMBDA FUNCTION STARTED - ERROR LEVEL LOG ====")  # Use ERROR level for visibility
        logger.error(f"Request ID: {context.aws_request_id if context else 'unknown'}")
        logger.error(f"Function name: {context.function_name if context else 'unknown'}")
        logger.error(f"Log group: {'/aws/lambda/' + (context.function_name if context else 'perplexity-validator')}")
        logger.error(f"Log stream: {context.log_stream_name if context else 'unknown'}")
        
        # Check if logging handlers are working
        logger.error(f"Logger handlers: {logger.handlers}")
        
        # Flush any pending logs
        for handler in logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()
                logger.error("Flushed log handler")
        
        # Explicitly create log group (testing permissions)
        try:
            logs_client = boto3.client('logs')
            log_group_name = f"/aws/lambda/{context.function_name if context else 'perplexity-validator'}"
            
            # Check if log group exists
            try:
                logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
                logger.info(f"Log group exists: {log_group_name}")
            except Exception as e:
                # Create log group if it doesn't exist
                try:
                    logs_client.create_log_group(logGroupName=log_group_name)
                    logger.info(f"Created log group: {log_group_name}")
                except Exception as create_e:
                    logger.error(f"Failed to create log group: {str(create_e)}")
                    logger.error("This may indicate a permissions issue with the Lambda execution role")
        except Exception as logs_e:
            logger.error(f"Error working with CloudWatch logs: {str(logs_e)}")
        
        # Initialize validator with config
        config = event.get('config', {})
        
        # Log the config for debugging
        logger.error(f"Config received: {json.dumps({k: v for k, v in config.items() if k != 'validation_targets'})[:500]}...")
        
        # Check if general_notes is present
        if 'general_notes' in config:
            logger.error(f"General notes included: {config['general_notes'][:200]}...")
        else:
            logger.error("WARNING: general_notes NOT found in config!")
            
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
            
            # Get ignored fields and ID fields - add them to results without processing
            ignored_fields = validator._get_ignored_fields(validator.validation_targets)
            id_fields = validator._get_id_fields(validator.validation_targets)
            
            # Process IGNORED fields
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
            
            # Process ID fields - similar to IGNORED fields, we don't validate them
            if id_fields:
                logger.info(f"Adding {len(id_fields)} ID fields to results without validation")
                for id_field in id_fields:
                    # Simply copy the original value to the result without validation
                    original_value = row.get(id_field.column, "")
                    row_results[id_field.column] = {
                        'value': original_value,
                        'confidence': 1.0,  # Max confidence since we're not checking
                        'confidence_level': "HIGH",
                        'sources': [],
                        'quote': "",
                        'main_source': "",
                        'update_required': False,  # Never update ID fields
                        'substantially_different': False
                    }
                    
                    # Add ID field results to accumulated results
                    accumulated_results[id_field.column] = row_results[id_field.column]
            
            # Group validation targets by search group - exclude ID and IGNORED fields 
            validation_targets = [t for t in validator.validation_targets if t.importance.upper() not in ["ID", "IGNORED"]]
            grouped_targets = validator._group_columns_by_search_group(validation_targets)
            
            # Sort search groups by number to ensure sequential processing
            sorted_groups = sorted(grouped_targets.keys())
            
            # Process each search group in order
            for group_id in sorted_groups:
                targets = grouped_targets[group_id]
                if not targets:
                    continue
                
                logger.info(f"Processing search group {group_id} with {len(targets)} columns")
                
                # Always use multiplex validation regardless of number of fields
                await process_multiplex_group(session, row, row_results, targets, accumulated_results)
                total_multiplex_validations += 1
                
                # Add this group's results to accumulated results for next groups
                for target in targets:
                    if target.column in row_results:
                        accumulated_results[target.column] = row_results[target.column]
            
            # Revisit CRITICAL fields with less than HIGH confidence
            critical_fields = validator._get_critical_fields(validator.validation_targets)
            critical_revisits = []
            
            for critical_field in critical_fields:
                # Skip ID fields that are already processed
                if critical_field.importance.upper() == "ID":
                    continue
                    
                if critical_field.column in row_results:
                    result = row_results[critical_field.column]
                    confidence_level = result.get('confidence_level', 'LOW')
                    
                    if confidence_level != 'HIGH':
                        logger.info(f"Revisiting CRITICAL field {critical_field.column} with {confidence_level} confidence")
                        critical_revisits.append(critical_field)
            
            # Process revisit fields via multiplex as well
            if critical_revisits:
                logger.info(f"Re-validating {len(critical_revisits)} critical fields via multiplex")
                
                # Pass the current accumulated results (including all previous validations)
                # This ensures the critical field has all context from previous validations
                for field in critical_revisits:
                    logger.info(f"Providing previous validation context for {field.column} re-validation")
                
                await process_multiplex_group(session, row, row_results, critical_revisits, accumulated_results)
                total_multiplex_validations += 1
                
                # Log the final results after re-validation
                for field in critical_revisits:
                    if field.column in row_results:
                        new_result = row_results[field.column]
                        new_confidence = new_result.get('confidence_level', 'LOW')
                        logger.info(f"After re-validation: {field.column} confidence is now {new_confidence}")
                        
                        # For critical fields that still have LOW confidence, try one more time in isolation
                        if new_confidence == "LOW":
                            logger.info(f"Field {field.column} still has LOW confidence - trying isolated validation")
                            # Process this single field in isolation (but still using the multiplex format)
                            await process_multiplex_group(session, row, row_results, [field], accumulated_results)
                            
                            if field.column in row_results:
                                final_confidence = row_results[field.column].get('confidence_level', 'LOW')
                                logger.info(f"After isolated validation: {field.column} confidence is now {final_confidence}")
            
            # Determine next check date
            next_check, reasons = validator.determine_next_check_date(row, row_results)
            row_results['next_check'] = next_check.isoformat() if next_check else None
            row_results['reasons'] = reasons
            
            # Get holistic validation results (already done in determine_next_check_date)
            holistic_validation = row_results.get('holistic_validation', {})
            
            # Add a summary of the holistic validation
            if holistic_validation:
                row_results['holistic_summary'] = {
                    'is_consistent': holistic_validation.get('is_consistent', True),
                    'overall_confidence': holistic_validation.get('overall_confidence', 'HIGH'),
                    'concerns_count': len(holistic_validation.get('concerns', [])),
                    'needs_review': holistic_validation.get('needs_review', False),
                    'priority_fields': holistic_validation.get('priority_fields', [])
                }
                
                # Log holistic validation results
                logger.info(f"Holistic validation: {json.dumps(row_results['holistic_summary'], indent=2)}")
                if holistic_validation.get('concerns', []):
                    logger.info(f"Concerns: {holistic_validation['concerns']}")
                    
                # If holistic validation finds consistency issues, perform one final check
                if not holistic_validation.get('is_consistent', True) or holistic_validation.get('needs_review', False):
                    logger.info("Holistic validation found issues - performing final consistency check")
                    
                    # Update accumulated_results with all current values
                    for field, result in row_results.items():
                        if field not in ['next_check', 'reasons', 'holistic_validation', 'holistic_summary']:
                            accumulated_results[field] = result
                    
                    # Re-validate any fields marked as priority
                    priority_fields = holistic_validation.get('priority_fields', [])
                    if priority_fields:
                        # Find the validation targets for these fields
                        priority_targets = []
                        for field_name in priority_fields:
                            for target in validation_targets:
                                if target.column == field_name:
                                    priority_targets.append(target)
                                    break
                        
                        if priority_targets:
                            logger.info(f"Re-validating {len(priority_targets)} priority fields from holistic validation")
                            await process_multiplex_group(session, row, row_results, priority_targets, accumulated_results)
                            
                            # Update the holistic validation after re-validating priority fields
                            next_check, reasons = validator.determine_next_check_date(row, row_results)
                            row_results['next_check'] = next_check.isoformat() if next_check else None
                            row_results['reasons'] = reasons
                            
                            # Log updated holistic results
                            if 'holistic_validation' in row_results:
                                logger.info("Updated holistic validation after priority field re-validation:")
                                logger.info(json.dumps(row_results['holistic_validation'], indent=2))
            
            return row_idx, row_results
        
        async def process_multiplex_group(session, row, row_results, targets, previous_results=None):
            """Process a group of columns with a single multiplex API call, even if there's only one column."""
            nonlocal total_cache_hits, total_cache_misses
            
            # First, filter out any ID or IGNORED fields - we don't validate these
            validation_targets = [t for t in targets if t.importance.upper() not in ["ID", "IGNORED"]]
            
            # If there are no fields to validate after filtering, just return
            if not validation_targets:
                logger.info("No non-ID/IGNORED fields to validate in this group")
                return
                
            # Log clear info about what we're processing
            if len(validation_targets) == 1:
                logger.info(f"Processing field '{validation_targets[0].column}' using multiplex format")
            else:
                logger.info(f"Processing {len(validation_targets)} fields together using multiplex format")
            
            # Check if all targets in this group are in cache
            all_cached = True
            cached_results = {}
            
            for target in validation_targets:
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
                    total_cache_misses += 1
                    logger.info(f"Cache miss for {target.column}")
                    break
            
            if all_cached:
                # If everything was cached, use cached results
                if len(validation_targets) == 1:
                    logger.info(f"Using cached result for field {validation_targets[0].column}")
                else:
                    logger.info(f"Using cached results for all {len(validation_targets)} columns in search group")
                for column, result in cached_results.items():
                    row_results[column] = result
                return
            
            # Generate multiplex prompt and validate
            logger.info(f"Generating multiplex prompt for {len(validation_targets)} field(s) with context from previous groups")
            prompt = validator.generate_multiplex_prompt(row, validation_targets, previous_results)
            
            # Call Perplexity API
            result = await validate_with_perplexity(session, prompt, api_key)
            
            # Parse multiplex results
            parsed_results = validator.parse_multiplex_result(result, row)
            
            # Process and store results for each column
            for target in validation_targets:
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
                        
                        # If sources contains numeric references, convert them to URLs
                        if 'sources' in row_results[target.column] and isinstance(row_results[target.column]['sources'], list):
                            from url_extractor import ensure_url_sources
                            source_obj = {
                                "sources": row_results[target.column]['sources'],
                                "main_source": row_results[target.column].get('main_source', '')
                            }
                            processed = ensure_url_sources(source_obj, result['citations'])
                            row_results[target.column]['sources'] = processed['sources']
                            row_results[target.column]['main_source'] = processed['main_source']
                    
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
                    # If column wasn't found in multiplex result, log an error and set a placeholder
                    logger.error(f"Column {target.column} not found in multiplex result")
                    # Set a placeholder result with error information
                    row_results[target.column] = {
                        'value': row.get(target.column, ""),  # Keep original value
                        'confidence': 0.0,
                        'confidence_level': "LOW",
                        'sources': [],
                        'quote': "",
                        'main_source': "",
                        'update_required': False,
                        'substantially_different': False,
                        'error': "Field not found in multiplex validation result"
                    }
        
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