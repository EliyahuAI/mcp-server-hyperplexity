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
from schema_validator_simplified import SimplifiedSchemaValidator
from botocore.config import Config
import traceback
from perplexity_schema import get_response_format_schema
from row_key_utils import generate_row_key  # Import centralized row key generation
import random
import time
import csv
from io import StringIO

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
# Bedrock not needed - using direct Anthropic API for web search support
# bedrock = boto3.client('bedrock-runtime', config=config)

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

def get_anthropic_api_key() -> str:
    """Get Anthropic API key from environment or SSM."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        # Try both parameter name variants (with and without leading slash)
        # ARN shows: arn:aws:ssm:us-east-1:400232868802:parameter/Anthropic_API_Key
        param_names = ['/Anthropic_API_Key', 'Anthropic_API_Key']
        
        for param_name in param_names:
            try:
                logger.info(f"Attempting to retrieve Anthropic API key from SSM parameter: {param_name}")
                
                response = ssm.get_parameter(
                    Name=param_name,
                    WithDecryption=True
                )
                api_key = response['Parameter']['Value']
                logger.info(f"Successfully retrieved Anthropic API key from {param_name}")
                break
                
            except Exception as e:
                logger.warning(f"Failed to get Anthropic API key from SSM parameter '{param_name}': {str(e)}")
                continue
        
        if not api_key:
            logger.error("Failed to retrieve Anthropic API key from any SSM parameter variant")
            
            # Try to list parameters to help with debugging
            try:
                logger.info("Attempting to list SSM parameters for debugging...")
                params_response = ssm.describe_parameters(
                    ParameterFilters=[
                        {
                            'Key': 'Name',
                            'Option': 'BeginsWith',
                            'Values': ['Anthropic']
                        }
                    ]
                )
                if params_response['Parameters']:
                    logger.info(f"Found parameters starting with 'Anthropic': {[p['Name'] for p in params_response['Parameters']]}")
                else:
                    logger.warning("No parameters found starting with 'Anthropic'")
                    
            except Exception as list_error:
                logger.error(f"Failed to list SSM parameters: {str(list_error)}")
            
            raise Exception(f"Anthropic API key not found in SSM. Tried parameters: {param_names}")
    else:
        logger.info("Using Anthropic API key from environment variable")
    return api_key

def determine_api_provider(model: str) -> str:
    """Determine which API provider to use based on model name."""
    if (model.startswith('anthropic/') or 
        model.startswith('anthropic.') or 
        model.startswith('claude-')):
        return 'anthropic'
    else:
        return 'perplexity'

def normalize_anthropic_model(model: str) -> str:
    """Convert anthropic/ format to direct API format if needed."""
    if model.startswith('anthropic/'):
        # Convert anthropic/claude-sonnet-4-20250514 to claude-sonnet-4-20250514
        return model.replace('anthropic/', '')
    elif model.startswith('anthropic.'):
        # Convert anthropic.claude-sonnet-4-20250514-v1:0 to claude-sonnet-4-20250514
        return model.replace('anthropic.', '').replace('-v1:0', '')
    return model

async def validate_with_anthropic(
    session: aiohttp.ClientSession,
    prompt: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514"
) -> Dict[str, Any]:
    """Validate a prompt using direct Anthropic API with web search."""
    # Normalize the model name for direct API
    anthropic_model = normalize_anthropic_model(model)
    
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    
    # Get the JSON schema for structured responses
    schema = get_response_format_schema(is_multiplex=True)
    array_schema = schema['json_schema']['schema']
    
    # Wrap the array schema in an object for tool calling (Anthropic requires type: object)
    tool_schema = {
        "type": "object",
        "properties": {
            "validation_results": array_schema
        },
        "required": ["validation_results"]
    }
    
    # Create system prompt for validation expert
    system_prompt = """You are a data validation expert with access to web search. Use web search to find current, accurate information for validation. Use the validate_data tool to provide your structured response."""

    # Create the request body with both web search and validation tools
    data = {
        "model": anthropic_model,
        "max_tokens": 3000,
        "temperature": 0.1,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "tools": [
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 10  # Allow multiple searches for thorough validation
            },
            {
                "name": "validate_data",
                "description": "Provide structured validation results for data fields",
                "input_schema": tool_schema
            }
        ],
        "tool_choice": {
            "type": "tool",
            "name": "validate_data"
        }
    }
    
    try:
        logger.info(f"Sending request to Anthropic API with model: {anthropic_model}")
        
        # Log the formatted prompt for better diagnostics
        prompt_lines = prompt.split('\n')
        formatted_prompt = "\n".join([f"  {line}" for line in prompt_lines])
        logger.info(f"Formatted prompt:\n{formatted_prompt}")
        
        # Log simplified request data
        simplified_request = {
            "model": anthropic_model,
            "temperature": data["temperature"],
            "max_tokens": data["max_tokens"],
            "tools": [{"type": "web_search_20250305", "max_uses": 10}]
        }
        logger.info(f"Request config: {json.dumps(simplified_request, indent=2)}")
        
        # Make the direct Anthropic API call with increased timeout
        timeout = aiohttp.ClientTimeout(total=120)  # 2 minutes for web search operations
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=timeout
        ) as response:
            response_text = await response.text()
            logger.info(f"Anthropic API Response status: {response.status}")
            
            if response.status == 429:
                # Rate limit error - include more details for retry logic
                raise Exception(f"Anthropic API rate limit exceeded (429): {response_text}")
            elif response.status == 499:
                # Client disconnect - treat as timeout
                raise Exception(f"Anthropic API client disconnected (499): {response_text}")
            elif response.status != 200:
                raise Exception(f"Anthropic API returned status {response.status}: {response_text}")
            
            response_json = json.loads(response_text)
            
            # Extract and log token usage information for Anthropic
            if 'usage' in response_json:
                usage = response_json['usage']
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                cache_creation_tokens = usage.get('cache_creation_tokens', 0)
                cache_read_tokens = usage.get('cache_read_tokens', 0)
                total_tokens = input_tokens + output_tokens + cache_creation_tokens + cache_read_tokens
                
                logger.info(f"Anthropic API Token Usage - Input: {input_tokens}, Output: {output_tokens}, Cache Creation: {cache_creation_tokens}, Cache Read: {cache_read_tokens}, Total: {total_tokens}")
            else:
                logger.warning("No usage information found in Anthropic API response")
            
            # Log the response for debugging
            logger.info(f"Anthropic API Response: {json.dumps(response_json, indent=2)}")
            
            # Convert Anthropic response format to match Perplexity format for compatibility
            if 'content' in response_json and len(response_json['content']) > 0:
                # Look for tool_use content (our structured validation data)
                validation_data = None
                text_content = ""
                
                for content_item in response_json['content']:
                    if content_item['type'] == 'text':
                        text_content += content_item['text']
                    elif content_item['type'] == 'tool_use' and content_item['name'] == 'validate_data':
                        # Extract the structured validation data from the tool call
                        tool_input = content_item['input']
                        # Extract the validation_results array from the wrapper object
                        if 'validation_results' in tool_input:
                            validation_data = tool_input['validation_results']
                            logger.info(f"Found structured validation data: {validation_data}")
                        else:
                            logger.warning("Tool input missing validation_results field")
                            validation_data = tool_input  # Fallback to raw input
                
                # If we got structured data from the tool, convert it to JSON string format
                if validation_data:
                    # Convert the structured data to a JSON string for compatibility with existing parser
                    content = json.dumps(validation_data)
                else:
                    # Fallback to text content if no tool call found
                    content = text_content
                    logger.warning("No structured validation data found in tool call, using text content")
                
                # Create a response format compatible with the existing parsing logic
                formatted_response = {
                    'choices': [{
                        'message': {
                            'role': 'assistant',
                            'content': content
                        }
                    }]
                }
                
                # Add any citations from web searches if available
                if 'usage' in response_json:
                    formatted_response['usage'] = response_json['usage']
                
                return formatted_response
            else:
                raise Exception(f"Unexpected Anthropic response format: {response_json}")
            
    except asyncio.TimeoutError as e:
        logger.error(f"Anthropic API timeout error: {str(e)}")
        raise Exception(f"Anthropic API timeout: {str(e)}")
    except aiohttp.ClientError as e:
        logger.error(f"Anthropic API client error: {str(e)}")
        raise Exception(f"Anthropic API client error: {str(e)}")
    except Exception as e:
        logger.error(f"Error calling Anthropic API: {str(e)}")
        raise

async def validate_with_perplexity(
    session: aiohttp.ClientSession,
    prompt: str,
    api_key: str,
    model: str = "sonar-pro",
    search_context_size: str = "low"
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
        "max_tokens": 3000,
        "response_format": get_response_format_schema(is_multiplex=True),
        "web_search_options": {
            "search_context_size": search_context_size
        }
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
        
        timeout = aiohttp.ClientTimeout(total=60)  # Increased timeout for Perplexity
        async with session.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=data,
            timeout=timeout
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
                        # Properly parse JSON content, handling escaped newlines
                        content_json = json.loads(content.replace("\\n", " "))
                        # Create a cleaner version for logging by removing all newlines
                        clean_content = json.dumps(content_json, indent=2)
                        
                        # Create a copy with formatted content for logging
                        log_response = response_json.copy()
                        if 'choices' in log_response and len(log_response['choices']) > 0:
                            if 'message' in log_response['choices'][0]:
                                log_response['choices'][0]['message'] = {
                                    'role': message.get('role', 'assistant'),
                                    'content': f"PARSED_JSON: {clean_content}"
                                }
                        
                        # Log the formatted response with consistent JSON formatting
                        logger.info(f"API Response body (formatted): {json.dumps(log_response, indent=2)}")
                    except Exception as json_err:
                        # If content isn't valid JSON or has formatting issues, log as is
                        logger.info(f"API Response body (raw content, parse error: {str(json_err)}): {json.dumps(response_json, indent=2)}")
                else:
                    logger.info(f"API Response body: {json.dumps(response_json, indent=2)}")
                    
            except json.JSONDecodeError:
                # If response isn't valid JSON, log as is
                logger.info(f"API Response body (raw): {response_text}")
            
            if response.status == 429:
                # Rate limit error
                raise Exception(f"Perplexity API rate limit exceeded (429): {response_text}")
            elif response.status == 499:
                # Client disconnect - treat as timeout
                raise Exception(f"Perplexity API client disconnected (499): {response_text}")
            elif response.status != 200:
                raise Exception(f"Perplexity API returned status {response.status}: {response_text}")
            
            parsed_response = json.loads(response_text)
            
            # Extract and log token usage information
            if 'usage' in parsed_response:
                usage = parsed_response['usage']
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0) 
                total_tokens = usage.get('total_tokens', 0)
                
                logger.info(f"Perplexity API Token Usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}")
                
                # Add search_context_size to usage tracking if available
                if 'search_context_size' in usage:
                    search_context_from_response = usage.get('search_context_size', 'unknown')
                    logger.info(f"API confirmed search_context_size: {search_context_from_response}")
            else:
                logger.warning("No usage information found in Perplexity API response")
            
            return parsed_response
    except asyncio.TimeoutError as e:
        logger.error(f"Perplexity API timeout error: {str(e)}")
        raise Exception(f"Perplexity API timeout: {str(e)}")
    except aiohttp.ClientError as e:
        logger.error(f"Perplexity API client error: {str(e)}")
        raise Exception(f"Perplexity API client error: {str(e)}")
    except Exception as e:
        logger.error(f"Error calling Perplexity API: {str(e)}")
        raise

def extract_token_usage(result: Dict[str, Any], model: str, search_context_size: str = None) -> Dict[str, Any]:
    """
    Extract token usage information from API response, handling both Perplexity and Anthropic formats.
    
    Args:
        result: The API response dictionary
        model: The model name to determine API provider
        search_context_size: Search context size (only applicable for Perplexity)
        
    Returns:
        Normalized token usage dictionary
    """
    if 'usage' not in result:
        return {}
    
    usage = result['usage']
    api_provider = determine_api_provider(model)
    
    if api_provider == 'anthropic':
        # Anthropic format: input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)
        cache_creation_tokens = usage.get('cache_creation_tokens', 0)
        cache_read_tokens = usage.get('cache_read_tokens', 0)
        total_tokens = input_tokens + output_tokens + cache_creation_tokens + cache_read_tokens
        
        return {
            'api_provider': 'anthropic',
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cache_creation_tokens': cache_creation_tokens,
            'cache_read_tokens': cache_read_tokens,
            'total_tokens': total_tokens,
            'model': model
        }
    else:
        # Perplexity format: prompt_tokens, completion_tokens, total_tokens, search_context_size
        prompt_tokens = usage.get('prompt_tokens', 0)
        completion_tokens = usage.get('completion_tokens', 0)
        total_tokens = usage.get('total_tokens', 0)
        
        return {
            'api_provider': 'perplexity',
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'search_context_size': usage.get('search_context_size', search_context_size),
            'model': model
        }

def load_pricing_data() -> Dict[str, Dict[str, float]]:
    """Load pricing data from CSV file."""
    pricing_data = {}
    
    # Default pricing for unknown models
    default_pricing = {
        'perplexity': {'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0},
        'anthropic': {'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0}
    }
    
    try:
        # Try multiple possible locations for the CSV file
        possible_paths = [
            os.path.join(os.path.dirname(__file__), 'pricing_data.csv'),  # Same directory as lambda_function.py
            os.path.join(os.path.dirname(__file__), '..', 'pricing_data.csv'),  # Parent directory
            'pricing_data.csv',  # Current working directory
            'src/pricing_data.csv'  # Relative path from project root
        ]
        
        csv_path = None
        for path in possible_paths:
            if os.path.exists(path):
                csv_path = path
                logger.info(f"Found pricing CSV at: {csv_path}")
                break
        
        if csv_path and os.path.exists(csv_path):
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    model_name = row['model_name']
                    pricing_data[model_name] = {
                        'api_provider': row['api_provider'],
                        'input_cost_per_million_tokens': float(row['input_cost_per_million_tokens']),
                        'output_cost_per_million_tokens': float(row['output_cost_per_million_tokens']),
                        'notes': row.get('notes', '')
                    }
        else:
            logger.warning(f"Pricing CSV file not found in any of the expected locations, using defaults")
            
    except Exception as e:
        logger.warning(f"Failed to load pricing data from CSV: {str(e)}, using defaults")
    
    return pricing_data

def calculate_token_costs(token_usage: Dict[str, Any], pricing_data: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Calculate costs based on token usage and pricing data."""
    if not token_usage:
        return {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0}
    
    api_provider = token_usage.get('api_provider', 'unknown')
    model = token_usage.get('model', 'unknown')
    
    # Try to find exact model match first
    pricing = None
    if model in pricing_data:
        pricing = pricing_data[model]
    else:
        # Try to find a partial match for the model
        for pricing_model in pricing_data:
            if pricing_model.lower() in model.lower() or model.lower() in pricing_model.lower():
                pricing = pricing_data[pricing_model]
                logger.info(f"Using pricing for {pricing_model} for model {model}")
                break
    
    # Fallback to default pricing by provider
    if not pricing:
        logger.warning(f"No pricing found for model {model}, using default {api_provider} pricing")
        if api_provider == 'perplexity':
            pricing = {'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0}  # sonar-pro rates
        elif api_provider == 'anthropic':
            pricing = {'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0}  # claude-4-sonnet rates
        else:
            pricing = {'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0}  # default
    
    # Calculate costs based on API provider
    input_cost = 0.0
    output_cost = 0.0
    
    if api_provider == 'perplexity':
        input_tokens = token_usage.get('prompt_tokens', 0)
        output_tokens = token_usage.get('completion_tokens', 0)
    elif api_provider == 'anthropic':
        input_tokens = token_usage.get('input_tokens', 0)
        output_tokens = token_usage.get('output_tokens', 0)
        # Note: cache tokens are typically free or heavily discounted, not including in cost calculation
    else:
        # Unknown provider, try to use total tokens
        input_tokens = token_usage.get('total_tokens', 0) // 2  # rough estimate
        output_tokens = token_usage.get('total_tokens', 0) // 2
    
    # Calculate costs (pricing is per million tokens)
    input_cost = (input_tokens / 1_000_000) * pricing['input_cost_per_million_tokens']
    output_cost = (output_tokens / 1_000_000) * pricing['output_cost_per_million_tokens']
    total_cost = input_cost + output_cost
    
    return {
        'input_cost': round(input_cost, 6),
        'output_cost': round(output_cost, 6), 
        'total_cost': round(total_cost, 6),
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'pricing_model': pricing.get('model_name', model)
    }

def get_cache_key(prompt: str, model: str = "sonar-pro", search_context_size: str = "low", search_groups: list = None) -> str:
    """
    Generate a unique cache key for validation request based on prompt, model, search context size, and search groups.
    
    Args:
        prompt: The prompt text sent to the API
        model: The model name used for the request
        search_context_size: The search context size for Perplexity API
        search_groups: Search group definitions that affect cache validity
        
    Returns:
        A hash string to use as the cache key
    """
    # Create a hash of prompt + model + search_context_size + search_groups for a deterministic cache key
    search_groups_str = json.dumps(search_groups, sort_keys=True) if search_groups else ""
    cache_input = f"{prompt}:{model}:{search_context_size}:{search_groups_str}"
    return hashlib.md5(cache_input.encode()).hexdigest()

def resolve_search_group_model(targets: List[Any], validator) -> Tuple[str, List[str]]:
    """
    Resolve model conflicts within a search group.
    
    Rules (in priority order):
    1. If search group definition exists, use its model setting (highest priority)
    2. If all targets use default model -> use default
    3. If any target has preferred_model -> prefer that over default
    4. If multiple different preferred_models -> pick first one and warn
    
    Returns:
        Tuple of (selected_model, list_of_warnings)
    """
    print(f"RESOLVE_MODEL: Called with {len(targets)} targets")
    logger.error(f"RESOLVE_MODEL: Called with {len(targets)} targets")
    warnings = []
    
    # Check if we have search group definitions and this group has a defined model
    if targets and hasattr(targets[0], 'search_group'):
        group_id = targets[0].search_group
        logger.info(f"Checking search group {group_id} for model override")
        
        # Check if validator has search_groups defined
        if hasattr(validator, 'search_groups') and validator.search_groups:
            logger.info(f"Validator has {len(validator.search_groups)} search group definitions")
            for group_def in validator.search_groups:
                logger.info(f"Checking group definition: {group_def}")
                if isinstance(group_def, dict) and group_def.get('group_id') == group_id:
                    if 'model' in group_def:
                        logger.info(f"Using search group {group_id} defined model: {group_def['model']}")
                        return group_def['model'], warnings
                    else:
                        logger.warning(f"Search group {group_id} found but no model defined")
        else:
            logger.info(f"Validator has no search_groups or empty search_groups")
    
    models_in_group = set()
    preferred_models = []
    
    # Collect all models used in this group
    for target in targets:
        if target.preferred_model:
            models_in_group.add(target.preferred_model)
            preferred_models.append((target.column, target.preferred_model))
        else:
            models_in_group.add(validator.default_model)
    
    # If only one model is used, that's our answer
    if len(models_in_group) == 1:
        selected_model = list(models_in_group)[0]
        logger.info(f"Search group uses consistent model: {selected_model}")
        return selected_model, warnings
    
    # If we have conflicts, prefer any specified model over default
    non_default_models = [m for m in models_in_group if m != validator.default_model]
    
    if len(non_default_models) == 1:
        # Only one non-default model, use that
        selected_model = non_default_models[0]
        logger.info(f"Search group has mixed models, preferring specified model: {selected_model} over default: {validator.default_model}")
        return selected_model, warnings
    
    elif len(non_default_models) > 1:
        # Multiple conflicting preferred models - pick the first one and warn
        selected_model = preferred_models[0][1]  # Use the first preferred model encountered
        
        # Build detailed warning message
        conflict_details = []
        for column, model in preferred_models:
            conflict_details.append(f"'{column}' -> {model}")
        
        warning_msg = f"Search group has conflicting preferred models: {', '.join(conflict_details)}. Selected '{selected_model}' (from '{preferred_models[0][0]}')"
        warnings.append(warning_msg)
        logger.warning(warning_msg)
        return selected_model, warnings
    
    else:
        # Fallback to default (shouldn't reach here given the logic above)
        selected_model = validator.default_model
        logger.info(f"Search group using default model: {selected_model}")
        return selected_model, warnings

def resolve_search_group_context_size(targets: List[Any], validator) -> str:
    """
    Resolve search context size within a search group.
    
    Rules (in priority order):
    1. If search group definition exists, use its search_context setting (highest priority)
    2. Otherwise, use the largest context size among all columns in the search group
    3. Priority order: high > medium > low
    4. If no column-specific context size is set, use default
    
    Returns:
        Selected search context size ("low", "medium", or "high")
    """
    print(f"RESOLVE_CONTEXT: Called with {len(targets)} targets")
    logger.error(f"RESOLVE_CONTEXT: Called with {len(targets)} targets")
    # Check if we have search group definitions and this group has a defined context
    if targets and hasattr(targets[0], 'search_group'):
        group_id = targets[0].search_group
        logger.info(f"Checking search group {group_id} for context override")
        
        # Check if validator has search_groups defined
        if hasattr(validator, 'search_groups') and validator.search_groups:
            logger.info(f"Validator has {len(validator.search_groups)} search group definitions")
            for group_def in validator.search_groups:
                logger.info(f"Checking group definition: {group_def}")
                if isinstance(group_def, dict) and group_def.get('group_id') == group_id:
                    if 'search_context' in group_def:
                        logger.info(f"Using search group {group_id} defined context: {group_def['search_context']}")
                        return group_def['search_context']
                    else:
                        logger.warning(f"Search group {group_id} found but no search_context defined")
        else:
            logger.info(f"Validator has no search_groups or empty search_groups")
    
    context_sizes = []
    
    # Define priority order (higher number = higher priority)
    priority_map = {"low": 1, "medium": 2, "high": 3}
    
    # Collect all context sizes used in this group
    for target in targets:
        if hasattr(target, 'search_context_size') and target.search_context_size:
            context_sizes.append(target.search_context_size)
        else:
            context_sizes.append(validator.default_search_context_size)
    
    # Find the highest priority context size
    if not context_sizes:
        selected_context_size = validator.default_search_context_size
    else:
        # Get the context size with the highest priority
        selected_context_size = max(context_sizes, key=lambda x: priority_map.get(x, 0))
    
    logger.info(f"Search group context sizes: {context_sizes}, selected: {selected_context_size}")
    return selected_context_size

async def retry_api_call_with_backoff(
    api_call_func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True,
    custom_delays: List[float] = None
):
    """
    Retry an API call with exponential backoff for rate limiting and timeout errors.
    
    Args:
        api_call_func: Async function to call
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        backoff_multiplier: Multiplier for exponential backoff
        jitter: Add random jitter to prevent thundering herd
        custom_delays: List of specific delays to use instead of exponential backoff
    
    Returns:
        Result of the API call
        
    Raises:
        Exception: If all retries are exhausted
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):  # +1 for initial attempt
        try:
            # Try the API call
            result = await api_call_func()
            if attempt > 0:
                logger.info(f"API call succeeded on attempt {attempt + 1}")
            return result
            
        except Exception as e:
            last_exception = e
            error_str = str(e).lower()
            
            # Check if this is a retryable error
            is_rate_limit = "rate_limit" in error_str or "429" in error_str
            is_timeout = "timeout" in error_str or "499" in error_str or "client disconnected" in error_str
            is_server_error = "500" in error_str or "502" in error_str or "503" in error_str or "504" in error_str
            
            if not (is_rate_limit or is_timeout or is_server_error):
                # Non-retryable error, raise immediately
                logger.error(f"Non-retryable error on attempt {attempt + 1}: {str(e)}")
                raise e
            
            if attempt >= max_retries:
                # Last attempt failed, raise the exception
                logger.error(f"All retry attempts exhausted. Final error: {str(e)}")
                raise e
            
            # Calculate delay - use custom delays if provided, otherwise exponential backoff
            if custom_delays:
                # Use specific delays from the list (attempt is 0-indexed for delays)
                if attempt < len(custom_delays):
                    delay = custom_delays[attempt]
                else:
                    # If we've exhausted custom delays, use the last one
                    delay = custom_delays[-1]
            else:
                # Use exponential backoff
                delay = min(base_delay * (backoff_multiplier ** attempt), max_delay)
                
                # Add jitter to prevent thundering herd
                if jitter:
                    delay = delay * (0.5 + random.random() * 0.5)  # Random between 50-100% of calculated delay
            
            # Special handling for rate limits - but respect custom delays if provided
            if is_rate_limit:
                try:
                    # Try to extract retry-after from error message or use longer delay
                    if "rate_limit" in error_str:
                        # Only apply minimum delay if not using custom delays
                        if not custom_delays:
                            delay = max(delay, 30)  # 30 seconds minimum for rate limits
                        logger.warning(f"Rate limit hit on attempt {attempt + 1}, waiting {delay:.2f}s before retry")
                    else:
                        logger.warning(f"Server error on attempt {attempt + 1}, waiting {delay:.2f}s before retry")
                except Exception:
                    pass
            else:
                logger.warning(f"Retryable error on attempt {attempt + 1}: {str(e)}, waiting {delay:.2f}s before retry")
            
            # Wait before retrying
            await asyncio.sleep(delay)
    
    # Should never reach here, but just in case
    raise last_exception

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
        
        # Debug validation history in event
        logger.error("==== VALIDATION HISTORY DEBUG ====")
        if 'validation_history' in event:
            vh = event['validation_history']
            logger.error(f"Validation history present in event with {len(vh)} row keys")
            if vh:
                # Show first key
                first_key = list(vh.keys())[0]
                logger.error(f"First validation history key: {first_key}")
                logger.error(f"Fields for first key: {list(vh[first_key].keys())}")
                # Show sample history entry
                if vh[first_key]:
                    sample_field = list(vh[first_key].keys())[0]
                    sample_history = vh[first_key][sample_field]
                    logger.error(f"Sample history for {sample_field}: {len(sample_history)} entries")
                    if sample_history:
                        logger.error(f"First entry: {json.dumps(sample_history[0], indent=2)}")
        else:
            logger.error("NO validation_history in event at all!")
        
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
            
        # Debug check for validation_targets examples
        if 'validation_targets' in config:
            targets_with_examples = 0
            for target in config.get('validation_targets', []):
                if 'examples' in target and target['examples']:
                    targets_with_examples += 1
                    logger.error(f"Found examples for {target.get('column')}: {target['examples']}")
            logger.error(f"Found {targets_with_examples} validation targets with examples")
            
        print(f"LAMBDA_HANDLER: Creating SimplifiedSchemaValidator with config keys: {list(config.keys())}")
        print(f"LAMBDA_HANDLER: Config has search_groups: {'search_groups' in config}")
        if 'search_groups' in config:
            print(f"LAMBDA_HANDLER: Number of search groups: {len(config['search_groups'])}")
        
        validator = SimplifiedSchemaValidator(config)
        
        print(f"LAMBDA_HANDLER: Validator created with {len(validator.search_groups)} search groups")
        logger.error(f"LAMBDA_HANDLER: Validator created with {len(validator.search_groups)} search groups")
        
        # Get API keys and S3 bucket - get both keys if we might need mixed models
        perplexity_api_key = None
        anthropic_api_key = None
        
        # Check if we need mixed API support by examining all column models
        needs_perplexity = False
        needs_anthropic = False
        
        # Check default model
        default_provider = determine_api_provider(validator.default_model)
        if default_provider == 'anthropic':
            needs_anthropic = True
        else:
            needs_perplexity = True
        
        # Check individual column preferred models
        for target in validator.validation_targets:
            if target.preferred_model:
                provider = determine_api_provider(target.preferred_model)
                if provider == 'anthropic':
                    needs_anthropic = True
                else:
                    needs_perplexity = True
        
        logger.info(f"API requirements - Perplexity: {needs_perplexity}, Anthropic: {needs_anthropic}")
        
        # Get required API keys
        if needs_anthropic:
            anthropic_api_key = get_anthropic_api_key()
            logger.info("Retrieved Anthropic API key")
        if needs_perplexity:
            perplexity_api_key = get_perplexity_api_key()
            logger.info("Retrieved Perplexity API key")
            
        s3_bucket = os.environ['S3_CACHE_BUCKET']
        
        # Process rows
        rows = event.get('validation_data', {}).get('rows', [])
        validation_results = {}
        total_cache_hits = 0
        total_cache_misses = 0
        total_multiplex_validations = 0
        total_single_validations = 0
        
        # Track batch-level timing
        batch_timing_data = []
        total_batches = 0
        
        async def process_all_rows():
            nonlocal total_cache_hits, total_cache_misses, total_multiplex_validations, total_single_validations, batch_timing_data, total_batches
            
            # Process rows in batches
            batch_size = 5  # Fixed batch size for parallel processing
            total_batches = (len(rows) + batch_size - 1) // batch_size  # Calculate total number of batches
            
            logger.info(f"🚀 BATCH PROCESSING: {len(rows)} rows in {total_batches} batches of {batch_size} rows each")
            
            async with aiohttp.ClientSession() as session:
                for batch_num in range(0, len(rows), batch_size):
                    batch_start_time = time.time()  # Start timing this batch
                    
                    batch = rows[batch_num:batch_num + batch_size]
                    actual_batch_size = len(batch)
                    batch_index = batch_num // batch_size + 1
                    
                    logger.info(f"🎯 Starting batch {batch_index}/{total_batches} with {actual_batch_size} rows")
                    
                    row_tasks = []
                    for row_idx, row in enumerate(batch):
                        task = asyncio.create_task(process_row(session, row, batch_num + row_idx))
                        row_tasks.append(task)
                    
                    # Wait for all rows in the batch to complete
                    batch_results = await asyncio.gather(*row_tasks)
                    
                    batch_end_time = time.time()
                    batch_processing_time = batch_end_time - batch_start_time
                    
                    # Store batch timing data
                    batch_timing_info = {
                        'batch_number': batch_index,
                        'batch_size': actual_batch_size,
                        'processing_time_seconds': batch_processing_time,
                        'time_per_row_in_batch': batch_processing_time / actual_batch_size if actual_batch_size > 0 else 0
                    }
                    batch_timing_data.append(batch_timing_info)
                    
                    logger.info(f"✅ Completed batch {batch_index}/{total_batches} in {batch_processing_time:.2f}s (avg {batch_processing_time/actual_batch_size:.2f}s per row in batch)")
                    
                    # Store results
                    for idx, result in batch_results:
                        validation_results[idx] = result
        
        async def process_row(session, row, row_idx):
            """Process a single row with progressive multiplexing."""
            nonlocal total_cache_hits, total_cache_misses, total_multiplex_validations, total_single_validations
            
            row_results = {}
            accumulated_results = {}  # Store results to pass as context to later groups
            
            # Use pre-computed row key if available, otherwise generate it
            if '_row_key' in row:
                row_key = row['_row_key']
                logger.info(f"Using pre-computed row key: {row_key}")
                # Remove _row_key from row data so it doesn't get processed as a column
                row_data = {k: v for k, v in row.items() if k != '_row_key'}
            else:
                # Fallback: generate row key if not provided (for backward compatibility)
                row_data = row
                row_key = generate_row_key(row_data, validator.primary_key)
                logger.warning(f"No pre-computed row key found, generated: {row_key}")
            
            # Get validation history if provided in the event
            validation_history = {}
            if 'validation_history' in event and row_key in event['validation_history']:
                validation_history = event['validation_history'][row_key]
                logger.info(f"Found validation history for row key: {row_key}")
                logger.info(f"History contains data for {len(validation_history)} fields")
                # Log sample history for debugging
                if validation_history:
                    sample_field = list(validation_history.keys())[0]
                    logger.info(f"Sample history field '{sample_field}': {validation_history[sample_field][:1]}")
            else:
                logger.warning(f"No validation history found for row key: {row_key}")
                if 'validation_history' in event:
                    logger.warning(f"Available history keys: {list(event['validation_history'].keys())[:5]}")
                else:
                    logger.warning("No validation_history in event at all")
            
            # Get ignored fields and ID fields - add them to results without processing
            ignored_fields = validator.get_ignored_fields()
            id_fields = validator.get_id_fields()
            
            # Process IGNORED fields
            if ignored_fields:
                logger.info(f"Adding {len(ignored_fields)} IGNORED fields without processing")
                for ignored_field in ignored_fields:
                    # Simply copy the original value to the result without validation
                    original_value = row_data.get(ignored_field.column, "")
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
            
            # Process ID fields - Include original values in results for preview table display
            if id_fields:
                logger.info(f"Including {len(id_fields)} ID fields with original values for preview display")
                for id_field in id_fields:
                    # Simply copy the original value to the result without validation
                    original_value = row_data.get(id_field.column, "")
                    row_results[id_field.column] = {
                        'value': original_value,
                        'confidence': 1.0,  # Max confidence since we're not checking
                        'confidence_level': "ID",  # Special confidence level for ID fields
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
            grouped_targets = validator.group_columns_by_search_group(validation_targets)
            
            # Sort search groups by number to ensure sequential processing
            sorted_groups = sorted(grouped_targets.keys())
            
            # Process each search group in order
            for group_id in sorted_groups:
                targets = grouped_targets[group_id]
                if not targets:
                    continue
                
                logger.info(f"Processing search group {group_id} with {len(targets)} columns")
                
                # Always use multiplex validation regardless of number of fields
                await process_multiplex_group(session, row_data, row_results, targets, accumulated_results, validation_history)
                total_multiplex_validations += 1
                
                # Add this group's results to accumulated results for next groups
                for target in targets:
                    if target.column in row_results:
                        accumulated_results[target.column] = row_results[target.column]
            
            # Still determine next check date, but without holistic validation
            next_check, reasons = validator.determine_next_check_date(row_data, row_results)
            row_results['next_check'] = next_check.isoformat() if next_check else None
            row_results['reasons'] = reasons
            
            return row_idx, row_results
        
        async def process_multiplex_group(session, row, row_results, targets, previous_results=None, validation_history=None, is_isolated_validation=False):
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
                if is_isolated_validation:
                    logger.info(f"This is an ISOLATED validation for field '{validation_targets[0].column}'")
            else:
                logger.info(f"Processing {len(validation_targets)} fields together using multiplex format")
            
            # Filter validation history to just the fields we're validating in this group
            filtered_validation_history = None
            if validation_history:
                filtered_validation_history = {}
                for target in validation_targets:
                    if target.column in validation_history:
                        filtered_validation_history[target.column] = validation_history[target.column]
                
                if filtered_validation_history:
                    logger.info(f"Including validation history for {len(filtered_validation_history)} fields")
                    # LOG DETAILED HISTORY INFO
                    for field, history_entries in filtered_validation_history.items():
                        logger.info(f"  Field '{field}' has {len(history_entries)} history entries")
                        if history_entries:
                            logger.info(f"    First entry: value='{history_entries[0].get('value', 'N/A')}', confidence={history_entries[0].get('confidence_level', 'N/A')}")
                else:
                    logger.info("No matching validation history for fields in this group")
            else:
                logger.info("No validation history provided to process_multiplex_group")
            
            # Resolve which model to use for this search group
            model, model_warnings = resolve_search_group_model(validation_targets, validator)
            
            # Log any model conflict warnings
            for warning in model_warnings:
                logger.warning(f"Search group model conflict: {warning}")
            
            # Resolve search context size for this search group
            search_context_size = resolve_search_group_context_size(validation_targets, validator)
            
            # Generate multiplex prompt first - we need this for the cache key
            logger.info(f"Generating multiplex prompt for {len(validation_targets)} field(s) with context from previous groups")
            logger.info(f"Using resolved model for search group: {model}")
            logger.info(f"Using resolved search context size for search group: {search_context_size}")
            logger.info(f"Passing validation_history to generate_multiplex_prompt: {filtered_validation_history is not None}")
            prompt = validator.generate_multiplex_prompt(row, validation_targets, previous_results, filtered_validation_history)
            
            # Generate cache key based on the prompt, model, search context size, and search groups
            cache_key = get_cache_key(prompt, model, search_context_size, validator.search_groups)
            logger.info(f"Using cache key based on prompt hash: {cache_key[:8]}...")
            
            # Check if this exact prompt has been cached before
            try:
                cache_response = s3.get_object(
                    Bucket=s3_bucket,
                    Key=f"validation_cache/{cache_key}.json"
                )
                cached_data = json.loads(cache_response['Body'].read())
                total_cache_hits += 1
                logger.info(f"Cache hit for prompt with key: {cache_key[:8]}...")
                
                # Handle both old and new cache formats
                if 'api_response' in cached_data:
                    # New format with metadata
                    cached_api_response = cached_data['api_response']
                    cached_token_usage = cached_data.get('token_usage', {})
                    cached_processing_time = cached_data.get('processing_time')
                    cached_at = cached_data.get('cached_at')
                else:
                    # Legacy format - just the API response
                    cached_api_response = cached_data
                    cached_token_usage = extract_token_usage(cached_api_response, model, search_context_size)
                    cached_processing_time = None
                    cached_at = None
                
                # Store the raw API response for this prompt in row_results
                response_id = f"response_{len(row_results.get('_raw_responses', {})) + 1}"
                if '_raw_responses' not in row_results:
                    row_results['_raw_responses'] = {}
                
                row_results['_raw_responses'][response_id] = {
                    'prompt': prompt,
                    'response': cached_api_response,
                    'is_cached': True,
                    'fields': [t.column for t in validation_targets],
                    'model': model,  # Add model information
                    'token_usage': cached_token_usage,  # Add token usage tracking
                    'processing_time': cached_processing_time,  # Add cached processing time
                    'cached_at': cached_at  # Add cache timestamp
                }
                
                # Parse the cached API response
                parsed_results = validator.parse_multiplex_result(cached_api_response, row)
                
                # ENHANCED LOGGING: Track expected vs actual cached results
                expected_columns = [t.column for t in validation_targets]
                actual_columns = list(parsed_results.keys())
                
                logger.info(f"🔍 CACHED SEARCH GROUP RESPONSE ANALYSIS:")
                logger.info(f"  Expected columns: {expected_columns}")
                logger.info(f"  Cached parsed columns: {actual_columns}")
                logger.info(f"  Expected count: {len(expected_columns)}, Actual count: {len(actual_columns)}")
                
                # Check for missing columns in cached results
                missing_columns = set(expected_columns) - set(actual_columns)
                if missing_columns:
                    logger.error(f"❌ MISSING COLUMNS IN CACHED RESULTS: {list(missing_columns)}")
                    logger.error(f"  These columns were expected but not found in cached response")
                    logger.error(f"🔄 CACHE REJECTED: Making fresh API call due to incomplete cached response")
                    
                    # CRITICAL FIX: Don't use incomplete cached response - make fresh API call instead
                    total_cache_misses += 1  # Count this as a cache miss
                    total_cache_hits -= 1    # Decrement the cache hit we counted earlier
                    
                    # Fall through to make fresh API call below
                    
                else:
                    # Check for unexpected columns in cached results
                    unexpected_columns = set(actual_columns) - set(expected_columns)
                    if unexpected_columns:
                        logger.warning(f"⚠️ UNEXPECTED COLUMNS IN CACHED RESULTS: {list(unexpected_columns)}")
                        logger.warning(f"  These columns were found but not expected")
                    
                    # Process results as if we had just called the API
                    cached_processed_count = 0
                    for target in validation_targets:
                        if target.column in parsed_results:
                            parsed_result = parsed_results[target.column]
                            row_results[target.column] = {
                                'value': parsed_result[0],
                                'confidence': parsed_result[1],
                                'sources': parsed_result[2],
                                'confidence_level': parsed_result[3],
                                'quote': parsed_result[4],
                                'main_source': parsed_result[5],
                                'update_required': parsed_result[6],
                                'substantially_different': parsed_result[7],
                                'response_id': response_id,  # Reference which API response this came from
                                'model': model  # Add model information from our context
                            }
                            
                            # Add consistent_with_model_knowledge if available
                            if len(parsed_result) > 8:
                                row_results[target.column]['consistent_with_model_knowledge'] = parsed_result[8]
                            
                            cached_processed_count += 1
                            logger.info(f"✅ Processed cached result for column: {target.column}")
                        else:
                            logger.error(f"❌ CACHED COLUMN RESULT MISSING: {target.column} was expected but not found in cached parsed results")
                    
                    logger.info(f"📊 CACHED PROCESSING SUMMARY: {cached_processed_count}/{len(validation_targets)} columns successfully processed from cache")
                    
                    # Cache was complete and used successfully
                    return
                
                # If we reach here, cache was incomplete - log the raw cached response for debugging
                logger.error(f"🔍 RAW CACHED API RESPONSE DEBUG (due to missing columns):")
                if 'choices' in cached_api_response and len(cached_api_response['choices']) > 0:
                    content = cached_api_response['choices'][0].get('message', {}).get('content', '')
                    logger.error(f"  Cached raw content length: {len(content)}")
                    logger.error(f"  Cached raw content preview: {content[:500]}...")
                else:
                    logger.error(f"  Unexpected cached API response structure: {json.dumps(cached_api_response, indent=2)[:1000]}...")
                
            except Exception as e:
                # Cache miss - need to call the API
                total_cache_misses += 1
                logger.info(f"Cache miss for prompt with key: {cache_key[:8]}..., will call API")
            
            # Route to appropriate API based on model
            api_provider = determine_api_provider(model)
            start_time = time.time()  # Track API call timing
            if api_provider == 'anthropic':
                logger.info(f"Routing to Anthropic API with model: {model}")
                result = await retry_api_call_with_backoff(
                    lambda: validate_with_anthropic(session, prompt, anthropic_api_key, model),
                    max_retries=5,  # 6 total attempts with specific delays
                    custom_delays=[1, 5, 10, 20, 30, 60]  # 1s, 5s, 10s, 20s, 30s, 60s
                )
            else:
                logger.info(f"Routing to Perplexity API with model: {model} and search_context_size: {search_context_size}")
                result = await retry_api_call_with_backoff(
                    lambda: validate_with_perplexity(session, prompt, perplexity_api_key, model, search_context_size),
                    max_retries=5,  # 6 total attempts with specific delays
                    custom_delays=[1, 5, 10, 20, 30, 60]  # 1s, 5s, 10s, 20s, 30s, 60s
                )
            processing_time = time.time() - start_time
            
            # Store the raw API response for this prompt in row_results
            response_id = f"response_{len(row_results.get('_raw_responses', {})) + 1}"
            if '_raw_responses' not in row_results:
                row_results['_raw_responses'] = {}
            
            # Extract token usage information from the API response
            token_usage = extract_token_usage(result, model, search_context_size)
            
            row_results['_raw_responses'][response_id] = {
                'prompt': prompt,
                'response': result,
                'is_cached': False,
                'fields': [t.column for t in validation_targets],
                'model': model,  # Add model information
                'token_usage': token_usage,  # Add token usage tracking
                'processing_time': processing_time  # Add actual processing time
            }
            
            # Cache the complete API response with metadata
            try:
                # Add timing and cost metadata to the cached entry
                cache_entry = {
                    'api_response': result,
                    'cached_at': datetime.now(timezone.utc).isoformat(),
                    'model': model,
                    'search_context_size': search_context_size,
                    'token_usage': token_usage,
                    'processing_time': processing_time
                }
                
                s3.put_object(
                    Bucket=s3_bucket,
                    Key=f"validation_cache/{cache_key}.json",
                    Body=json.dumps(cache_entry),
                    ContentType='application/json'
                )
                logger.info(f"Cached API response with metadata, key: {cache_key[:8]}...")
            except Exception as e:
                logger.error(f"Failed to cache API response: {str(e)}")
            
            # Parse multiplex results
            parsed_results = validator.parse_multiplex_result(result, row)
            
            # ENHANCED LOGGING: Track expected vs actual results
            expected_columns = [t.column for t in validation_targets]
            actual_columns = list(parsed_results.keys())
            
            logger.info(f"🔍 SEARCH GROUP RESPONSE ANALYSIS:")
            logger.info(f"  Expected columns: {expected_columns}")
            logger.info(f"  Parsed columns: {actual_columns}")
            logger.info(f"  Expected count: {len(expected_columns)}, Actual count: {len(actual_columns)}")
            
            # Check for missing columns
            missing_columns = set(expected_columns) - set(actual_columns)
            if missing_columns:
                logger.error(f"❌ MISSING COLUMNS DETECTED: {list(missing_columns)}")
                logger.error(f"  These columns were expected but not found in API response")
                
            # Check for unexpected columns
            unexpected_columns = set(actual_columns) - set(expected_columns)
            if unexpected_columns:
                logger.warning(f"⚠️ UNEXPECTED COLUMNS FOUND: {list(unexpected_columns)}")
                logger.warning(f"  These columns were found but not expected")
            
            # Log the parsed results for debugging
            logger.info(f"Parsed {len(parsed_results)} results from API response")
            for col, parsed_result in parsed_results.items():
                quote_text = parsed_result[4] if len(parsed_result) > 4 else "N/A"
                logger.info(f"  {col}: quote='{quote_text[:50]}{'...' if len(quote_text) > 50 else ''}'")
            
            # Process the API response results
            processed_count = 0
            for target in validation_targets:
                if target.column in parsed_results:
                    parsed_result = parsed_results[target.column]
                    row_results[target.column] = {
                        'value': parsed_result[0],
                        'confidence': parsed_result[1],
                        'sources': parsed_result[2],
                        'confidence_level': parsed_result[3],
                        'quote': parsed_result[4],
                        'main_source': parsed_result[5],
                        'update_required': parsed_result[6],
                        'substantially_different': parsed_result[7],
                        'response_id': response_id,  # Reference which API response this came from
                        'model': model  # Add model information from our context
                    }
                    
                    # Add consistent_with_model_knowledge if available
                    if len(parsed_result) > 8:
                        row_results[target.column]['consistent_with_model_knowledge'] = parsed_result[8]
                    
                    processed_count += 1
                    logger.info(f"✅ Processed result for column: {target.column}")
                else:
                    logger.error(f"❌ COLUMN RESULT MISSING: {target.column} was expected but not found in parsed results")
            
            logger.info(f"📊 PROCESSING SUMMARY: {processed_count}/{len(validation_targets)} columns successfully processed")
            
            # If we have missing results, log the raw API response for debugging
            if missing_columns:
                logger.error(f"🔍 RAW API RESPONSE DEBUG (due to missing columns):")
                if 'choices' in result and len(result['choices']) > 0:
                    content = result['choices'][0].get('message', {}).get('content', '')
                    logger.error(f"  Raw content length: {len(content)}")
                    logger.error(f"  Raw content preview: {content[:500]}...")
                else:
                    logger.error(f"  Unexpected API response structure: {json.dumps(result, indent=2)[:1000]}...")
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process_all_rows())
        finally:
            loop.close()
            
            # Ensure we're returning the complete validation results for each row
            logger.info(f"Returning full validation results for {len(validation_results)} rows")
            
            # Load pricing data for cost calculations
            pricing_data = load_pricing_data()
            
            # Collect all raw responses from all rows and aggregate token usage and processing time
            all_raw_responses = {}
            total_processing_time = 0.0  # This will be the sum of all batch times (parallel processing)
            total_token_usage = {
                'total_tokens': 0,
                'api_calls': 0,
                'cached_calls': 0,
                'total_cost': 0.0,
                'by_provider': {
                    'perplexity': {
                        'prompt_tokens': 0,
                        'completion_tokens': 0,
                        'total_tokens': 0,
                        'calls': 0,
                        'input_cost': 0.0,
                        'output_cost': 0.0,
                        'total_cost': 0.0
                    },
                    'anthropic': {
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'cache_creation_tokens': 0,
                        'cache_read_tokens': 0,
                        'total_tokens': 0,
                        'calls': 0,
                        'input_cost': 0.0,
                        'output_cost': 0.0,
                        'total_cost': 0.0
                    }
                },
                'by_model': {}
            }
            
            # First pass: collect all responses and calculate token usage
            # For timing, we need to calculate the maximum processing time per batch (parallel processing)
            batch_processing_times = {}  # batch_number -> max_processing_time_in_that_batch
            
            for row_idx, row_result in validation_results.items():
                if '_raw_responses' in row_result:
                    # Calculate which batch this row was in (batch_size = 5)
                    batch_number = row_idx // 5
                    if batch_number not in batch_processing_times:
                        batch_processing_times[batch_number] = 0.0
                    
                    # Track the total processing time for this row
                    row_processing_time = 0.0
                    
                    # Add a row prefix to each response ID to avoid collisions
                    for response_id, response_data in row_result['_raw_responses'].items():
                        new_response_id = f"row{row_idx}_{response_id}"
                        all_raw_responses[new_response_id] = response_data
                        
                        # Count API calls (move this OUTSIDE token usage check)
                        is_cached = response_data.get('is_cached', False)
                        if is_cached:
                            total_token_usage['cached_calls'] += 1
                            logger.info(f"DEBUG: Counting as cached call - response_id: {new_response_id}, is_cached: {is_cached}")
                        else:
                            total_token_usage['api_calls'] += 1
                            logger.info(f"DEBUG: Counting as API call - response_id: {new_response_id}, is_cached: {is_cached}")
                        
                        # Aggregate token usage
                        if 'token_usage' in response_data:
                            usage = response_data['token_usage']
                            if usage:  # Only process if token_usage is not empty
                                api_provider = usage.get('api_provider', 'unknown')
                                total_tokens = usage.get('total_tokens', 0)
                                total_token_usage['total_tokens'] += total_tokens
                                
                                # Calculate costs for this usage
                                costs = calculate_token_costs(usage, pricing_data)
                                total_token_usage['total_cost'] += costs['total_cost']
                        
                        # Aggregate processing time for this row
                        if 'processing_time' in response_data:
                            proc_time = response_data.get('processing_time', 0.0)
                            if proc_time and isinstance(proc_time, (int, float)):
                                row_processing_time += proc_time
                    
                    # For parallel processing, the batch time is the maximum time of any row in that batch
                    # (since all rows in a batch are processed in parallel)
                    batch_processing_times[batch_number] = max(batch_processing_times[batch_number], row_processing_time)
                    logger.info(f"Row {row_idx} (batch {batch_number}) total time: {row_processing_time:.3f}s, batch max now: {batch_processing_times[batch_number]:.3f}s")
            
            # Calculate total processing time as sum of all batch times (since batches are processed sequentially)
            total_processing_time = sum(batch_processing_times.values())
            logger.info(f"Calculated parallel processing time: {total_processing_time:.3f}s across {len(batch_processing_times)} batches")
            
            # Second pass: aggregate provider-specific token usage
            for row_idx, row_result in validation_results.items():
                if '_raw_responses' in row_result:
                    for response_id, response_data in row_result['_raw_responses'].items():
                        # Continue with provider-specific token usage aggregation
                        if 'token_usage' in response_data:
                            usage = response_data['token_usage']
                            if usage:  # Only process if token_usage is not empty
                                api_provider = usage.get('api_provider', 'unknown')
                                total_tokens = usage.get('total_tokens', 0)
                                costs = calculate_token_costs(usage, pricing_data)
                                # Aggregate by provider
                                if api_provider == 'perplexity':
                                    provider_usage = total_token_usage['by_provider']['perplexity']
                                    provider_usage['prompt_tokens'] += usage.get('prompt_tokens', 0)
                                    provider_usage['completion_tokens'] += usage.get('completion_tokens', 0)
                                    provider_usage['total_tokens'] += total_tokens
                                    provider_usage['calls'] += 1
                                    provider_usage['input_cost'] += costs['input_cost']
                                    provider_usage['output_cost'] += costs['output_cost']
                                    provider_usage['total_cost'] += costs['total_cost']
                                elif api_provider == 'anthropic':
                                    provider_usage = total_token_usage['by_provider']['anthropic']
                                    provider_usage['input_tokens'] += usage.get('input_tokens', 0)
                                    provider_usage['output_tokens'] += usage.get('output_tokens', 0)
                                    provider_usage['cache_creation_tokens'] += usage.get('cache_creation_tokens', 0)
                                    provider_usage['cache_read_tokens'] += usage.get('cache_read_tokens', 0)
                                    provider_usage['total_tokens'] += total_tokens
                                    provider_usage['calls'] += 1
                                    provider_usage['input_cost'] += costs['input_cost']
                                    provider_usage['output_cost'] += costs['output_cost']
                                    provider_usage['total_cost'] += costs['total_cost']
                                
                                # Track by model
                                model = response_data.get('model', 'unknown')
                                if model not in total_token_usage['by_model']:
                                    total_token_usage['by_model'][model] = {
                                        'api_provider': api_provider,
                                        'total_tokens': 0,
                                        'calls': 0,
                                        'input_cost': 0.0,
                                        'output_cost': 0.0,
                                        'total_cost': 0.0
                                    }
                                    # Add provider-specific fields
                                    if api_provider == 'perplexity':
                                        total_token_usage['by_model'][model].update({
                                            'prompt_tokens': 0,
                                            'completion_tokens': 0
                                        })
                                    elif api_provider == 'anthropic':
                                        total_token_usage['by_model'][model].update({
                                            'input_tokens': 0,
                                            'output_tokens': 0,
                                            'cache_creation_tokens': 0,
                                            'cache_read_tokens': 0
                                        })
                                
                                # Update model-specific usage
                                model_usage = total_token_usage['by_model'][model]
                                model_usage['total_tokens'] += total_tokens
                                model_usage['calls'] += 1
                                model_usage['input_cost'] += costs['input_cost']
                                model_usage['output_cost'] += costs['output_cost']
                                model_usage['total_cost'] += costs['total_cost']
                                
                                if api_provider == 'perplexity':
                                    model_usage['prompt_tokens'] += usage.get('prompt_tokens', 0)
                                    model_usage['completion_tokens'] += usage.get('completion_tokens', 0)
                                elif api_provider == 'anthropic':
                                    model_usage['input_tokens'] += usage.get('input_tokens', 0)
                                    model_usage['output_tokens'] += usage.get('output_tokens', 0)
                                    model_usage['cache_creation_tokens'] += usage.get('cache_creation_tokens', 0)
                                    model_usage['cache_read_tokens'] += usage.get('cache_read_tokens', 0)
                    
                    # Remove the raw responses from the row result to avoid duplication
                    del row_result['_raw_responses']
            
            # Log aggregation results BEFORE adding to metadata
            logger.info(f"DEBUG: About to add processing_time to metadata")
            logger.info(f"DEBUG: total_processing_time value = {total_processing_time}")
            logger.info(f"DEBUG: type of total_processing_time = {type(total_processing_time)}")
            
            # Log token usage and cost summary
            logger.info(f"Token Usage Summary: {total_token_usage['total_tokens']} total tokens")
            logger.info(f"Total Estimated Cost: ${total_token_usage['total_cost']:.6f}")
            logger.info(f"API Calls: {total_token_usage['api_calls']} new, {total_token_usage['cached_calls']} cached")
            logger.info(f"Total Processing Time: {total_processing_time:.3f}s")
            
            # Log by provider
            perplexity_usage = total_token_usage['by_provider']['perplexity']
            anthropic_usage = total_token_usage['by_provider']['anthropic']
            
            if perplexity_usage['calls'] > 0:
                logger.info(f"Perplexity API: {perplexity_usage['prompt_tokens']} prompt + {perplexity_usage['completion_tokens']} completion = {perplexity_usage['total_tokens']} total tokens across {perplexity_usage['calls']} calls")
                logger.info(f"Perplexity Cost: ${perplexity_usage['input_cost']:.6f} input + ${perplexity_usage['output_cost']:.6f} output = ${perplexity_usage['total_cost']:.6f} total")
            
            if anthropic_usage['calls'] > 0:
                logger.info(f"Anthropic API: {anthropic_usage['input_tokens']} input + {anthropic_usage['output_tokens']} output + {anthropic_usage['cache_creation_tokens']} cache_creation + {anthropic_usage['cache_read_tokens']} cache_read = {anthropic_usage['total_tokens']} total tokens across {anthropic_usage['calls']} calls")
                logger.info(f"Anthropic Cost: ${anthropic_usage['input_cost']:.6f} input + ${anthropic_usage['output_cost']:.6f} output = ${anthropic_usage['total_cost']:.6f} total")
            
            # Log by model
            for model, model_usage in total_token_usage['by_model'].items():
                api_provider = model_usage.get('api_provider', 'unknown')
                logger.info(f"Model {model} ({api_provider}): {model_usage['total_tokens']} tokens across {model_usage['calls']} calls, cost: ${model_usage['total_cost']:.6f}")
            
            # Log the size of the response data (approximately)
            response_json = json.dumps({
                'validation_results': validation_results,
                'cache_stats': {
                    'hits': total_cache_hits,
                    'misses': total_cache_misses,
                    'multiplex_validations': total_multiplex_validations,
                    'single_validations': total_single_validations
                }
            })
            response_size_kb = len(response_json) / 1024
            logger.info(f"Response size without raw responses: approximately {response_size_kb:.2f} KB")
            
            # Estimate size with raw responses
            raw_responses_json = json.dumps(all_raw_responses)
            raw_size_kb = len(raw_responses_json) / 1024
            logger.info(f"Raw responses size: approximately {raw_size_kb:.2f} KB")
            logger.info(f"Total estimated response size: {response_size_kb + raw_size_kb:.2f} KB")
            
            # Calculate batch timing statistics using parallel processing time calculation
            num_batches = len(batch_processing_times)
            if num_batches > 0:
                avg_batch_time = total_processing_time / num_batches  # Parallel time per batch
                avg_time_per_row_across_batches = total_processing_time / len(validation_results) if validation_results else 0
                total_batch_time = total_processing_time  # Use parallel processing time
            else:
                avg_batch_time = 0
                avg_time_per_row_across_batches = 0
                total_batch_time = 0
            
            # Log batch timing summary
            logger.info(f"📊 BATCH TIMING SUMMARY:")
            logger.info(f"  🚀 Total batches processed: {len(batch_processing_times)}")
            logger.info(f"  ⏱️ Average time per batch: {avg_batch_time:.2f}s")
            logger.info(f"  → Average time per row across all batches: {avg_time_per_row_across_batches:.2f}s")
            logger.info(f"  ✅ Total batch processing time: {total_batch_time:.2f}s")
            
            # Calculate validation structure metrics
            validation_targets = [t for t in validator.validation_targets if t.importance.upper() not in ["ID", "IGNORED"]]
            validated_columns_count = len(validation_targets)
            grouped_targets = validator.group_columns_by_search_group(validation_targets)
            search_groups_count = len(grouped_targets)
            
            # Count high context and Claude search groups
            high_context_groups_count = 0
            claude_groups_count = 0
            for group_id, targets in grouped_targets.items():
                if targets:
                    # Check if any target in this group has high context
                    group_has_high_context = any(
                        (getattr(target, 'search_context_size', '') or '').lower() == 'high'
                        for target in targets
                    )
                    if group_has_high_context:
                        high_context_groups_count += 1
                    
                    # Check if any target in this group uses Claude/Anthropic model
                    group_model, _ = resolve_search_group_model(targets, validator)
                    if determine_api_provider(group_model) == 'anthropic':
                        claude_groups_count += 1
            
            # Log validation metrics summary
            logger.info(f"🔍 VALIDATION STRUCTURE METRICS:")
            logger.info(f"  📊 Validated columns: {validated_columns_count}")
            logger.info(f"  🔗 Search groups: {search_groups_count}")
            logger.info(f"  🎯 High context search groups: {high_context_groups_count}")
            logger.info(f"  🤖 Claude search groups: {claude_groups_count}")
            
            # Create a single response
            response = {
                "statusCode": 200,
                "body": {
                    "success": True,
                    "message": "Validation completed",
                    "data": {
                        # Map row indices to results
                        "rows": validation_results
                    },
                    "metadata": {
                        "total_rows": len(rows),
                        "completed_rows": len(validation_results),
                        "cache_hits": total_cache_hits,
                        "cache_misses": total_cache_misses,
                        "multiplex_validations": total_multiplex_validations,
                        "single_validations": total_single_validations,
                        "token_usage": total_token_usage,
                        "processing_time": total_processing_time,  # Keep for backward compatibility
                        # NEW: Batch timing data
                        "batch_timing": {
                            "total_batches": len(batch_processing_times),
                            "batch_size": 5,  # Fixed batch size
                            "total_batch_time_seconds": total_batch_time,
                            "average_batch_time_seconds": avg_batch_time,
                            "average_time_per_row_seconds": avg_time_per_row_across_batches,
                            "batch_details": list(batch_processing_times.items())  # Convert dict to list of (batch_num, time) pairs
                        },
                        # NEW: Validation structure metrics
                        "validation_metrics": {
                            "validated_columns_count": validated_columns_count,
                            "search_groups_count": search_groups_count,
                            "high_context_search_groups_count": high_context_groups_count,
                            "claude_search_groups_count": claude_groups_count
                        }
                    }
                }
            }
            
            # DEBUG: Log what we're actually returning in metadata
            logger.info(f"DEBUG: Metadata being returned: {list(response['body']['metadata'].keys())}")
            logger.info(f"DEBUG: processing_time in metadata = {response['body']['metadata'].get('processing_time', 'NOT FOUND')}")
            
            # Add the raw responses for debugging if in test_mode
            test_mode = event.get('test_mode', False)
            if test_mode:
                # Return the raw responses as well in test mode
                if 'raw_responses' in event:
                    response['body']['raw_responses'] = event['raw_responses']
            
            # Remove any raw response content if not in test mode
            else:
                # Clean up any raw response content that might have been added (just to be safe)
                if 'raw_responses' in response['body']:
                    del response['body']['raw_responses']
                
            # Return the combined results
            return response
        
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'body': {
                'error': str(e)
            }
        } 