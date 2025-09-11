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
from botocore.config import Config
import traceback
import random
import time
import csv
from io import StringIO
from pathlib import Path

from schema_validator_simplified import SimplifiedSchemaValidator
from perplexity_schema import get_response_format_schema
from row_key_utils import generate_row_key
from ai_api_client import ai_client

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

# Import enhanced batch manager (after logger is configured)
try:
    from enhanced_batch_manager import EnhancedDynamicBatchSizeManager
    ENHANCED_BATCH_MANAGER_AVAILABLE = True
    logger.info("✅ Enhanced batch manager available")
except ImportError as e:
    logger.warning(f"Enhanced batch manager not available: {e}")
    ENHANCED_BATCH_MANAGER_AVAILABLE = False

# Import WebSocket client for progress updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger.warning("WebSocket client not available")

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

class DynamicBatchSizeManager:
    """
    Manages dynamic batch sizing based on rate limiting and success patterns.
    
    PER-MODEL STRATEGY:
    - Track separate batch sizes for each model (auto-registers new models)
    - When multiple models are used in a batch, use the minimum batch size
    - When multiple models are successful, only increase the model with lowest batch size
    - 10% increase after 5 consecutive successes
    - 25% decrease after 2 consecutive failures
    """
    
    def __init__(self, 
                 initial_batch_size: int = 50,
                 min_batch_size: int = 10,
                 max_batch_size: int = 100,
                 success_increase_factor: float = 1.1,  # 10% increase
                 failure_decrease_factor: float = 0.75,  # 25% decrease
                 consecutive_successes_for_increase: int = 5,  # 5 successes
                 consecutive_failures_for_decrease: int = 2):  # 2 failures
        
        # Per-model tracking dictionaries
        self.model_batch_sizes = {}  # Dict[str, int] - model_name -> batch_size
        self.model_consecutive_successes = {}  # Dict[str, int]
        self.model_consecutive_failures = {}  # Dict[str, int]
        self.model_rate_limit_events = {}  # Dict[str, int]
        
        self.initial_batch_size = initial_batch_size
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.success_increase_factor = success_increase_factor
        self.failure_decrease_factor = failure_decrease_factor
        self.consecutive_successes_for_increase = consecutive_successes_for_increase
        self.consecutive_failures_for_decrease = consecutive_failures_for_decrease
        self.total_batches = 0
        
        # Initialized per-model batch manager
    
    def register_model(self, model: str):
        """Register a new model if not already tracked."""
        if model not in self.model_batch_sizes:
            self.model_batch_sizes[model] = self.initial_batch_size
            self.model_consecutive_successes[model] = 0
            self.model_consecutive_failures[model] = 0
            self.model_rate_limit_events[model] = 0
            # Registered new model
    
    def get_batch_size_for_models(self, models: set) -> int:
        """
        Get the appropriate batch size based on which models will be used.
        
        Args:
            models: Set of model names (e.g., 'claude-3-5-sonnet-20241022', 'llama-3.1-sonar-small-128k-online')
            
        Returns:
            The batch size to use for this batch (minimum across all models)
        """
        if not models:
            # No models specified, use default
            return self.initial_batch_size
        
        # Register any new models
        for model in models:
            self.register_model(model)
        
        # Use minimum batch size across all models
        batch_sizes = [self.model_batch_sizes[model] for model in models]
        min_batch_size = min(batch_sizes)
        
        if len(models) > 1:
            model_sizes_str = ", ".join([f"{model}={self.model_batch_sizes[model]}" for model in sorted(models)])
            # Using minimum batch size
        
        return min_batch_size
    
    def on_rate_limit(self, model: str):
        """
        Called when a rate limit is encountered for a specific model.
        
        Args:
            model: The model that hit the rate limit
        """
        self.register_model(model)
        
        self.model_rate_limit_events[model] += 1
        self.model_consecutive_failures[model] += 1
        self.model_consecutive_successes[model] = 0
        
        new_batch_size = max(
            self.min_batch_size,
            int(self.model_batch_sizes[model] * self.failure_decrease_factor)
        )
        
        if new_batch_size != self.model_batch_sizes[model]:
            logger.warning(f"Rate limit hit for {model}")
            self.model_batch_sizes[model] = new_batch_size
        else:
            logger.warning(f"Rate limit hit for {model}, at minimum batch size")
    
    def on_success(self, models_used: set):
        """
        Called when a batch completes successfully.
        
        Args:
            models_used: Set of models actually used in this batch
        """
        self.total_batches += 1
        
        if not models_used:
            return
        
        # Register any new models and update success counters
        for model in models_used:
            self.register_model(model)
            self.model_consecutive_successes[model] += 1
            self.model_consecutive_failures[model] = 0
        
        # Only increase the model with the lowest batch size
        min_model = min(models_used, key=lambda m: self.model_batch_sizes[m])
        self._try_increase_batch_size(min_model)
    
    def on_failure(self, models_used: set, is_rate_limit: bool = False):
        """
        Called when a batch fails.
        
        Args:
            models_used: Set of models used in this batch
            is_rate_limit: Whether the failure was due to rate limiting
        """
        if is_rate_limit:
            # Rate limits are handled by on_rate_limit
            return
        
        if not models_used:
            return
        
        # Register models and update failure counters
        for model in models_used:
            self.register_model(model)
            self.model_consecutive_failures[model] += 1
            self.model_consecutive_successes[model] = 0
            self._try_decrease_batch_size(model)
    
    def _try_increase_batch_size(self, model: str):
        """Helper method to try increasing batch size for a specific model."""
        if (self.model_consecutive_successes[model] >= self.consecutive_successes_for_increase and 
            self.model_batch_sizes[model] < self.max_batch_size):
            
            new_batch_size = min(
                self.max_batch_size,
                int(self.model_batch_sizes[model] * self.success_increase_factor)
            )
            
            if new_batch_size != self.model_batch_sizes[model]:
                # Increasing batch size after success streak
                self.model_batch_sizes[model] = new_batch_size
                self.model_consecutive_successes[model] = 0
    
    def _try_decrease_batch_size(self, model: str):
        """Helper method to try decreasing batch size for a specific model."""
        if self.model_consecutive_failures[model] >= self.consecutive_failures_for_decrease:
            new_batch_size = max(
                self.min_batch_size,
                int(self.model_batch_sizes[model] * self.failure_decrease_factor)
            )
            
            if new_batch_size != self.model_batch_sizes[model]:
                logger.warning(f"Reducing batch size for {model} after consecutive failures")
                self.model_batch_sizes[model] = new_batch_size
                self.model_consecutive_failures[model] = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics for monitoring."""
        stats = {
            'total_batches': self.total_batches,
            'registered_models': list(self.model_batch_sizes.keys()),
            'model_batch_sizes': dict(self.model_batch_sizes),
            'model_consecutive_successes': dict(self.model_consecutive_successes),
            'model_consecutive_failures': dict(self.model_consecutive_failures),
            'model_rate_limit_events': dict(self.model_rate_limit_events)
        }
        
        # Add success rates per model
        model_success_rates = {}
        for model in self.model_batch_sizes.keys():
            # Approximate success rate based on recent performance
            failures = self.model_consecutive_failures[model]
            rate_limits = self.model_rate_limit_events[model]
            total_issues = failures + rate_limits
            # Use a simple heuristic: if total_batches > 10, estimate success rate
            if self.total_batches > 10:
                model_success_rates[model] = max(0.0, 1.0 - (total_issues / max(1, self.total_batches)))
            else:
                model_success_rates[model] = 1.0 if total_issues == 0 else 0.5
        
        stats['model_success_rates'] = model_success_rates
        return stats
    
    def log_status(self):
        """Log current status for monitoring."""
        if not self.model_batch_sizes:
            # No models registered
            return
        
        model_status = []
        for model in sorted(self.model_batch_sizes.keys()):
            status = (f"{model}={self.model_batch_sizes[model]} "
                     f"(succ={self.model_consecutive_successes[model]}, "
                     f"fail={self.model_consecutive_failures[model]}, "
                     f"rl={self.model_rate_limit_events[model]})")
            model_status.append(status)
        
        # Batch manager status updated

def discover_batch_models(rows, validator):
    """
    Discover all models that will be used for a batch of rows.
    
    Args:
        rows: List of row data dictionaries
        validator: Validator instance with validation targets and configuration
        
    Returns:
        Set[str]: Set of model names that will be used
    """
    models = set()
    
    # Get validation targets that aren't ID or IGNORED
    validation_targets = [t for t in validator.validation_targets 
                        if t.importance.upper() not in ["ID", "IGNORED"]]
    
    if not validation_targets:
        # No validation targets found
        return models
    
    # Group targets by search group
    grouped_targets = validator.group_columns_by_search_group(validation_targets)
    
    # Resolve model for each search group
    for group_id, group_targets in grouped_targets.items():
        if group_targets:
            model, _ = resolve_search_group_model(group_targets, validator)
            models.add(model)
            # Found model for search group
    
    logger.info(f"Found models for batch: {sorted(models)}")
    return models

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
        # Apply web search rate limiting before making the call
        try:
            # In lambda deployment, shared modules are copied to root level
            try:
                from web_search_rate_limiter import apply_web_search_rate_limiting
            except ImportError:
                # Fallback for local development
                from shared.web_search_rate_limiter import apply_web_search_rate_limiting
            session_id = "validation_session"  # You might want to pass this as a parameter
            max_searches = data.get("tools", [{}])[0].get("max_uses", 10)
            await apply_web_search_rate_limiting(session_id, anthropic_model, max_searches)
            # Web search rate limiting applied
        except ImportError:
            logger.warning("Web search rate limiter not available, proceeding without rate limiting")
        except Exception as e:
            logger.warning(f"Web search rate limiting failed: {e}, proceeding without rate limiting")
        
        # Sending request to Anthropic API
        
        # Log the formatted prompt for better diagnostics
        prompt_lines = prompt.split('\n')
        formatted_prompt = "\n".join([f"  {line}" for line in prompt_lines])
        # Formatted prompt for API request
        
        # Log simplified request data
        simplified_request = {
            "model": anthropic_model,
            "temperature": data["temperature"],
            "max_tokens": data["max_tokens"],
            "tools": [{"type": "web_search_20250305", "max_uses": 10}]
        }
        # Prepared API request
        
        # Make the direct Anthropic API call with increased timeout
        timeout = aiohttp.ClientTimeout(total=120)  # 2 minutes for web search operations
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=timeout
        ) as response:
            response_text = await response.text()
            # Received API response
            
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
                
                # Token usage recorded
            else:
                logger.warning("No usage information found in Anthropic API response")
            
            # Log the response for debugging
            # Full API response received
            
            # Convert Anthropic response format to match Perplexity format for compatibility
            # Processing response content
            
            if 'content' in response_json and response_json['content'] is not None and len(response_json['content']) > 0:
                # Look for tool_use content (our structured validation data)
                validation_data = None
                text_content = ""
                
                # Processing response content items
                
                for i, content_item in enumerate(response_json['content']):
                    if content_item is None:
                        logger.warning(f"Content item {i} is None, skipping")
                        continue
                    
                    # Processing content item
                    
                    if content_item.get('type') == 'text':
                        text_content += content_item.get('text', '')
                    elif content_item.get('type') == 'tool_use' and content_item.get('name') == 'validate_data':
                        # Extract the structured validation data from the tool call
                        tool_input = content_item.get('input', {})
                        # Processing tool input
                        
                        # Extract the validation_results array from the wrapper object
                        if 'validation_results' in tool_input:
                            validation_data = tool_input['validation_results']
                            # Found validation data
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
                logger.error(f"No content field or empty content in Anthropic response")
                logger.error(f"Response structure: {json.dumps(response_json, indent=2)}")
                raise Exception(f"Unexpected Anthropic response format: missing or empty 'content' field")
            
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
        # Sending request to Perplexity API
        
        # Log a readable version of the prompt for debugging
        prompt_lines = prompt.split('\n')
        formatted_prompt = "\n".join([f"  {line}" for line in prompt_lines])
        # Formatted prompt for API request
        
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

def setup_shared_module_path():
    """Ensure shared module is importable in lambda environment."""
    import sys
    import os
    
    # Add common paths where shared module might be located
    possible_paths = [
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # src/ directory
        os.path.dirname(os.path.dirname(__file__)),  # lambdas/ directory  
        os.path.dirname(__file__),  # current directory
        '/opt/python/lib/python3.9/site-packages',  # Lambda layer path
        '/var/task',  # Lambda runtime path
    ]
    
    for path in possible_paths:
        if path and os.path.exists(path) and path not in sys.path:
            sys.path.insert(0, path)

# REMOVED: load_pricing_data() function - moved to ai_api_client.py
def load_pricing_data_REMOVED() -> Dict[str, Dict[str, float]]:
    """Load pricing data from DynamoDB model config table, fallback to CSV."""
    pricing_data = {}
    
    # Default pricing for unknown models
    default_pricing = {
        'perplexity': {'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0},
        'anthropic': {'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0}
    }
    
    try:
        # Try DynamoDB model config table first (preferred)
        try:
            # In lambda deployment, shared modules are copied to root level
            from model_config_table import ModelConfigTable
        except ImportError:
            try:
                # Fallback to shared.module for local development
                from shared.model_config_table import ModelConfigTable
            except ImportError as ie:
                # Last resort: try path setup
                logger.warning(f"Both import methods failed: {ie}, attempting path setup")
                setup_shared_module_path()
                from shared.model_config_table import ModelConfigTable
        config_table = ModelConfigTable()
        configs = config_table.list_all_configs()
        
        if configs:
            # Loading pricing from DynamoDB
            for config in configs:
                if config.get('enabled', False):
                    model_pattern = config.get('model_pattern', '')
                    pricing_data[model_pattern] = {
                        'api_provider': config.get('api_provider', 'unknown'),
                        'input_cost_per_million_tokens': float(config.get('input_cost_per_million_tokens', 3.0)),
                        'output_cost_per_million_tokens': float(config.get('output_cost_per_million_tokens', 15.0)),
                        'notes': config.get('notes', ''),
                        'priority': config.get('priority', 999)
                    }
            # Loaded pricing configurations
            # Debug: List first few patterns
            patterns = list(pricing_data.keys())[:5]
            # Loaded pricing patterns
            return pricing_data
        else:
            logger.warning("No configurations found in DynamoDB model config table, falling back to CSV")
            
    except Exception as e:
        logger.warning(f"Failed to load pricing from DynamoDB: {str(e)}, falling back to CSV")
    
    # Fallback to CSV file (legacy)
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
                # Found pricing CSV
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
            # Loaded pricing configurations from CSV
        else:
            logger.warning(f"Pricing CSV file not found in any of the expected locations, using defaults")
            
    except Exception as e:
        logger.warning(f"Failed to load pricing data from CSV: {str(e)}, using defaults")
    
    return pricing_data

# REMOVED: calculate_token_costs() function - moved to ai_api_client.py  
def calculate_token_costs_REMOVED(token_usage: Dict[str, Any], pricing_data: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Calculate costs based on token usage and pricing data."""
    if not token_usage:
        return {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0}
    
    api_provider = token_usage.get('api_provider', 'unknown')
    model = token_usage.get('model', 'unknown')
    
    # Try to find exact model match first
    pricing = None
    # Looking for pricing data
    
    if model in pricing_data:
        pricing = pricing_data[model]
        # Using exact pricing match
    else:
        # Sort pricing patterns by priority (if available) and try pattern matching
        sorted_patterns = sorted(pricing_data.items(), key=lambda x: x[1].get('priority', 999))
        # Testing pricing patterns
        
        # Try pattern matching (for DynamoDB configs with wildcards)
        import re
        for pricing_pattern, pricing_config in sorted_patterns:
            # Convert glob pattern to regex
            regex_pattern = pricing_pattern.replace('*', '.*')
            regex_pattern = f"^{regex_pattern}$"
            
            try:
                match_result = re.match(regex_pattern, model, re.IGNORECASE)
                # Testing pricing pattern
                
                if match_result:
                    pricing = pricing_config
                    # Using pattern pricing match
                    break
            except re.error as e:
                logger.warning(f"Invalid pricing regex pattern: {e}")
                # If pattern is invalid regex, try simple string matching
                if pricing_pattern.lower() in model.lower() or model.lower() in pricing_pattern.lower():
                    pricing = pricing_config
                    # Using string pricing match
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
        input_tokens = token_usage.get('input_tokens', 0)  # ai_api_client normalizes to input_tokens
        output_tokens = token_usage.get('output_tokens', 0)  # ai_api_client normalizes to output_tokens
        
        # Handle legacy cached format where we might have prompt_tokens/completion_tokens instead
        if input_tokens == 0 and output_tokens == 0:
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
    
    # Debug logging for low cost investigation
    if input_tokens > 0 or output_tokens > 0:
        # Calculated costs for model usage
        pass
    
    return {
        'input_cost': round(input_cost, 6),
        'output_cost': round(output_cost, 6), 
        'total_cost': round(total_cost, 6),
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'pricing_model': pricing.get('model_name', model)
    }

async def call_claude_with_shared_client(prompt: str, model: str, tool_schema: Dict, max_web_searches: int = 3) -> Dict:
    """
    Call Claude using the shared AI client.
    Returns a response in the format expected by the validation lambda.
    """
    try:
        # Call the shared client
        result = await ai_client.call_structured_api(
            prompt=prompt,
            schema=tool_schema,
            model=model,
            tool_name="validate_data",
            use_cache=True,  # Enable caching
            max_web_searches=max_web_searches
        )
        
        # Extract the structured response
        structured_data = ai_client.extract_structured_response(result['response'], "validate_data")
        
        # Get validation_results from the structured data
        validation_results = structured_data.get('validation_results', structured_data)
        
        # Convert to the format expected by the validation lambda
        # The validation lambda expects a response with choices[0].message.content as a JSON string
        formatted_response = {
            'choices': [{
                'message': {
                    'role': 'assistant',
                    'content': json.dumps(validation_results)
                }
            }]
        }
        
        # Add usage information if available
        if 'token_usage' in result:
            formatted_response['usage'] = result['token_usage']
        
        # Include enhanced data from ai_client result for cost/time tracking
        formatted_response['enhanced_data'] = result
        
        return formatted_response
        
    except Exception as e:
        logger.error(f"Error calling Claude through shared client: {str(e)}")
        raise

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
    # Resolving model for targets
    warnings = []
    
    # Check if we have search group definitions and this group has a defined model
    if targets and hasattr(targets[0], 'search_group'):
        group_id = targets[0].search_group
        # Checking for model override
        
        # Check if validator has search_groups defined
        if hasattr(validator, 'search_groups') and validator.search_groups:
            # Checking search group definitions
            for group_def in validator.search_groups:
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

def resolve_search_group_max_web_searches(targets: List[Any], validator) -> int:
    """
    Resolve max web searches for Anthropic within a search group.
    
    Rules (in priority order):
    1. If search group definition exists and has anthropic_max_web_searches, use it (highest priority)
    2. Otherwise, use validator's anthropic_max_web_searches_default if set
    3. Finally, use global default of 3
    
    Returns:
        Max web searches (0-10)
    """
    logger.debug(f"RESOLVE_MAX_WEB_SEARCHES: Called with {len(targets)} targets")
    
    # Check if we have search group definitions and this group has a defined max_web_searches
    if targets and hasattr(targets[0], 'search_group'):
        group_id = targets[0].search_group
        logger.info(f"Checking search group {group_id} for anthropic_max_web_searches override")
        
        # Check if validator has search_groups defined
        if hasattr(validator, 'search_groups') and validator.search_groups:
            for group_def in validator.search_groups:
                if isinstance(group_def, dict) and group_def.get('group_id') == group_id:
                    if 'anthropic_max_web_searches' in group_def:
                        max_searches = group_def['anthropic_max_web_searches']
                        logger.info(f"Using search group {group_id} defined anthropic_max_web_searches: {max_searches}")
                        return max_searches
    
    # Check for validator default
    if hasattr(validator, 'config') and isinstance(validator.config, dict):
        default_max_searches = validator.config.get('anthropic_max_web_searches_default')
        if default_max_searches is not None:
            logger.info(f"Using validator default anthropic_max_web_searches: {default_max_searches}")
            return default_max_searches
    
    # Global default
    logger.info("Using global default anthropic_max_web_searches: 3")
    return 3

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
    logger.debug(f"RESOLVE_CONTEXT: Called with {len(targets)} targets")
    # Check if we have search group definitions and this group has a defined context
    if targets and hasattr(targets[0], 'search_group'):
        group_id = targets[0].search_group
        logger.info(f"Checking search group {group_id} for context override")
        
        # Check if validator has search_groups defined
        if hasattr(validator, 'search_groups') and validator.search_groups:
            # Checking search group definitions
            for group_def in validator.search_groups:
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
    custom_delays: List[float] = None,
    batch_manager: Optional[DynamicBatchSizeManager] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None
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
            
            # Notify batch manager of rate limits
            if is_rate_limit and batch_manager and model:
                batch_manager.on_rate_limit(model)
            
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

def handle_config_generation_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle AI configuration generation requests using existing Claude integration."""
    try:
        logger.info("=== CONFIG GENERATION REQUEST ===")
        
        # Extract request parameters
        table_analysis = event.get('table_analysis')
        generation_mode = event.get('generation_mode', 'automatic')
        conversation_id = event.get('conversation_id')
        user_message = event.get('user_message', '')
        session_id = event.get('session_id', 'unknown')
        
        if not table_analysis:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'success': False,
                    'error': 'Missing table_analysis in request'
                })
            }
        
        logger.info(f"Config generation for session: {session_id}, mode: {generation_mode}")
        
        # Get Anthropic API key (reuse existing logic)
        anthropic_api_key = get_anthropic_api_key()
        if not anthropic_api_key:
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'success': False,
                    'error': 'Anthropic API key not available'
                })
            }
        
        # Process the config generation request
        if generation_mode == 'automatic':
            result = asyncio.run(generate_config_automatic(
                table_analysis, anthropic_api_key, session_id
            ))
        else:  # interview mode
            result = asyncio.run(generate_config_interview(
                table_analysis, anthropic_api_key, session_id, 
                conversation_id, user_message
            ))
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"Config generation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }

async def generate_config_automatic(table_analysis: Dict, api_key: str, session_id: str) -> Dict:
    """Generate configuration automatically using Claude."""
    try:
        # Build the config generation prompt
        prompt = build_config_generation_prompt(table_analysis, mode='automatic')
        
        # Call Claude using existing infrastructure
        async with aiohttp.ClientSession() as session:
            config_response = await call_anthropic_api_structured(
                session, prompt, api_key, 
                schema=get_config_generation_schema(),
                model="claude-sonnet-4-0"
            )
        
        # Extract generated config from response
        generated_config = extract_config_from_claude_response(config_response)
        ai_response = 'Configuration generated automatically using AI analysis'
        
        # Save config to S3 and return the key
        try:
            config_s3_key = save_config_to_s3(generated_config, session_id)
            
            return {
                'success': True,
                'generated_config': generated_config,
                'generated_config_s3_key': config_s3_key,
                'ai_response': ai_response,
                'session_id': session_id,
                'generation_mode': 'automatic'
            }
            
        except Exception as s3_error:
            logger.error(f"Failed to save config to S3: {str(s3_error)}")
            # Still return the config even if S3 save fails
            return {
                'success': True,
                'generated_config': generated_config,
                'ai_response': ai_response,
                'session_id': session_id,
                'generation_mode': 'automatic'
            }
        
    except Exception as e:
        logger.error(f"Automatic config generation failed: {str(e)}")
        
        return {
            'success': False,
            'error': f'Automatic generation failed: {str(e)}',
            'session_id': session_id
        }

async def generate_config_interview(table_analysis: Dict, api_key: str, session_id: str,
                                  conversation_id: str = None, user_message: str = '') -> Dict:
    """Generate configuration through interview mode."""
    try:
        if not conversation_id:
            # Start new conversation
            prompt = build_config_generation_prompt(table_analysis, mode='interview_start')
        else:
            # Continue conversation
            prompt = build_config_generation_prompt(
                table_analysis, mode='interview_continue', 
                conversation_id=conversation_id, user_message=user_message
            )
        
        # Call Claude using existing infrastructure
        async with aiohttp.ClientSession() as session:
            response = await call_anthropic_api_text(
                session, prompt, api_key, model="claude-sonnet-4-0"
            )
        
        ai_response = response.get('content', 'Interview response generated')
        current_conversation_id = conversation_id or f"conv_{session_id}"
        
        # Check if this response contains a complete config
        generated_config = None
        try:
            # Try to extract config from the response if it's complete
            if "final_config" in ai_response.lower() or "configuration:" in ai_response.lower():
                # Attempt to parse a complete config from the response
                generated_config = extract_config_from_text_response(ai_response)
        except:
            pass  # No complete config yet
        
        # Save config to S3 if complete
        config_s3_key = None
        if generated_config:
            try:
                config_s3_key = save_config_to_s3(generated_config, session_id)
            except Exception as s3_error:
                logger.error(f"Failed to save config to S3: {str(s3_error)}")
        
        # For interview mode, we might not have a complete config yet
        return {
            'success': True,
            'ai_response': ai_response,
            'conversation_id': current_conversation_id,
            'session_id': session_id,
            'generation_mode': 'interview',
            'generated_config': generated_config,  # May be None if not complete
            'generated_config_s3_key': config_s3_key  # May be None if not complete
        }
        
    except Exception as e:
        logger.error(f"Interview config generation failed: {str(e)}")
        
        return {
            'success': False,
            'error': f'Interview generation failed: {str(e)}',
            'session_id': session_id
        }

def build_config_generation_prompt(table_analysis: Dict, mode: str = 'automatic',
                                 conversation_id: str = None, user_message: str = '') -> str:
    """Build config generation prompt based on table analysis."""
    
    basic_info = table_analysis.get('basic_info', {})
    column_analysis = table_analysis.get('column_analysis', {})
    domain_info = table_analysis.get('domain_info', {})
    
    base_prompt = f"""
You are an expert in data validation and configuration generation for the pharmaceutical industry.

TABLE ANALYSIS:
- File: {basic_info.get('filename', 'Unknown')}
- Size: {basic_info.get('total_rows', 0)} rows × {basic_info.get('total_columns', 0)} columns
- Domain: {domain_info.get('inferred_domain', 'general')} (confidence: {domain_info.get('domain_confidence', 0)})
- Purpose: {domain_info.get('inferred_purpose', 'data analysis')}

COLUMN DETAILS:
"""
    
    for col_name, col_info in column_analysis.items():
        sample_values = col_info.get('sample_values', [])[:3]
        base_prompt += f"""
{col_name}:
  - Type: {col_info.get('data_type', 'Unknown')}
  - Importance: {col_info.get('inferred_importance', 'MEDIUM')}
  - Completeness: {100 - col_info.get('null_percentage', 0):.1f}%
  - Sample Values: {sample_values}
"""
    
    if mode == 'automatic':
        base_prompt += """
TASK: Generate a complete validation configuration for this table that optimizes for pharmaceutical competitive intelligence workflows.

Focus on:
1. Appropriate importance levels (ID, CRITICAL, HIGH, MEDIUM, LOW)
2. Logical search groups for batch processing
3. Model selection (Claude 4 for complex analysis, Perplexity for factual updates)
4. Validation criteria and examples

Generate a complete configuration following the established schema.
"""
    
    elif mode == 'interview_start':
        base_prompt += """
TASK: Start an interactive interview to generate a customized validation configuration.

Begin by asking 3-5 strategic questions about:
1. Specific validation priorities for this dataset
2. Business use cases and critical fields
3. Performance vs accuracy trade-offs
4. Domain-specific requirements

Keep questions focused and practical. Tailor questions to the pharmaceutical domain based on the table analysis.
"""
    
    elif mode == 'interview_continue':
        base_prompt += f"""
CONVERSATION CONTEXT:
Conversation ID: {conversation_id}
User Message: "{user_message}"

TASK: Continue the configuration interview based on the user's response.

Analyze their input and either:
1. Ask follow-up questions to clarify requirements
2. Generate the final configuration if you have enough information

Maintain context from the previous conversation and build toward a complete configuration.
"""
    
    return base_prompt

def get_config_generation_schema() -> Dict:
    """Get JSON schema for config generation tool."""
    return {
        "type": "object",
        "properties": {
            "general_notes": {
                "type": "string",
                "description": "Comprehensive notes about the configuration and validation guidelines"
            },
            "default_model": {
                "type": "string",
                "description": "Default model to use for validation",
                "default": "sonar-pro"
            },
            "search_groups": {
                "type": "array",
                "description": "Logical search group definitions",
                "items": {
                    "type": "object",
                    "properties": {
                        "group_id": {"type": "integer"},
                        "group_name": {"type": "string"},
                        "description": {"type": "string"},
                        "model": {"type": "string"},
                        "search_context": {"type": "string", "enum": ["low", "high"]}
                    },
                    "required": ["group_id", "group_name", "description", "model", "search_context"]
                }
            },
            "validation_targets": {
                "type": "array",
                "description": "Validation target configurations",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string"},
                        "description": {"type": "string"},
                        "importance": {"type": "string", "enum": ["ID", "CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                        "format": {"type": "string"},
                        "notes": {"type": "string"},
                        "examples": {"type": "array", "items": {"type": "string"}},
                        "search_group": {"type": "integer"},
                        "preferred_model": {"type": "string"},
                        "search_context_size": {"type": "string", "enum": ["low", "high"]}
                    },
                    "required": ["column", "description", "importance", "format", "examples", "search_group"]
                }
            }
        },
        "required": ["general_notes", "validation_targets"]
    }

def save_config_to_s3(generated_config: Dict, session_id: str) -> str:
    """Save generated configuration to S3 and return the key."""
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        # Upload config to S3
        s3_client = boto3.client('s3')
        bucket_name = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
        
        # Create unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        key = f"generated_configs/{session_id}_{timestamp}.json"
        
        # Upload config as JSON
        config_json = json.dumps(generated_config, indent=2)
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=config_json,
            ContentType='application/json',
            Metadata={'session_id': session_id}
        )
        
        logger.info(f"Config uploaded to S3: {key}")
        return key
        
    except Exception as e:
        logger.error(f"Failed to save config to S3: {str(e)}")
        raise

def create_config_download_url(s3_key: str) -> str:
    """Create S3 download URL for the generated configuration."""
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        s3_client = boto3.client('s3')
        bucket_name = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
        
        # Generate presigned URL (valid for 1 hour)
        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': s3_key},
            ExpiresIn=3600
        )
        
        logger.info(f"Created download URL for S3 key: {s3_key}")
        return download_url
        
    except Exception as e:
        logger.error(f"Failed to create config download URL: {str(e)}")
        return ""

def extract_config_from_text_response(text_response: str) -> Dict:
    """Extract configuration from text response (for interview mode)."""
    try:
        # Look for JSON-like structures in the text
        import re
        
        # Try to find JSON blocks
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text_response, re.DOTALL)
        
        for match in matches:
            try:
                config = json.loads(match)
                # Validate that it looks like a config
                if 'columns' in config or 'validation_rules' in config:
                    return config
            except json.JSONDecodeError:
                continue
        
        # If no valid JSON found, return None
        return None
        
    except Exception as e:
        logger.error(f"Failed to extract config from text: {str(e)}")
        return None

def extract_config_from_claude_response(response: Dict) -> Dict:
    """Extract configuration from Claude's structured response."""
    try:
        # Similar to existing extraction logic in the validation code
        for content_item in response.get('content', []):
            if content_item.get('type') == 'tool_use':
                return content_item.get('input', {})
        
        # Fallback: extract from text
        for content_item in response.get('content', []):
            if content_item.get('type') == 'text':
                text = content_item.get('text', '')
                if '{' in text and '}' in text:
                    start = text.find('{')
                    end = text.rfind('}') + 1
                    return json.loads(text[start:end])
        
        raise ValueError("Could not extract config from Claude response")
        
    except Exception as e:
        logger.error(f"Config extraction failed: {str(e)}")
        raise

async def call_anthropic_api_structured(session: aiohttp.ClientSession, prompt: str, 
                                       api_key: str, schema: Dict, model: str = "claude-sonnet-4-0") -> Dict:
    """Call Anthropic API with structured output (tool use)."""
    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': api_key,
        'anthropic-version': '2023-06-01'
    }
    
    data = {
        "model": model,
        "max_tokens": 8000,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [{
            "name": "generate_config",
            "description": "Generate a validation configuration",
            "input_schema": schema
        }],
        "tool_choice": {"type": "tool", "name": "generate_config"}
    }
    
    async with session.post("https://api.anthropic.com/v1/messages", 
                           headers=headers, json=data) as response:
        if response.status == 200:
            return await response.json()
        else:
            error_text = await response.text()
            raise Exception(f"Anthropic API error: {response.status} - {error_text}")

async def call_anthropic_api_text(session: aiohttp.ClientSession, prompt: str, 
                                 api_key: str, model: str = "claude-sonnet-4-0") -> Dict:
    """Call Anthropic API for text response (interview mode)."""
    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': api_key,
        'anthropic-version': '2023-06-01'
    }
    
    data = {
        "model": model,
        "max_tokens": 4000,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    async with session.post("https://api.anthropic.com/v1/messages", 
                           headers=headers, json=data) as response:
        if response.status == 200:
            result = await response.json()
            # Extract text content
            for content_item in result.get('content', []):
                if content_item.get('type') == 'text':
                    return {'content': content_item.get('text', '')}
            return {'content': 'No text response received'}
        else:
            error_text = await response.text()
            raise Exception(f"Anthropic API error: {response.status} - {error_text}")

def send_websocket_progress(session_id: str, message: str, progress: int = None):
    """Send progress update via WebSocket"""
    if websocket_client and session_id:
        try:
            update_data = {
                'type': 'progress_update',
                'message': message,
                'session_id': session_id,
                'timestamp': datetime.now().isoformat()
            }
            if progress is not None:
                update_data['progress'] = progress
            
            websocket_client.send_to_session(session_id, update_data)
            logger.info(f"Sent WebSocket progress: {message} to session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to send WebSocket progress: {e}")

def report_ai_call_progress(session_id: str, total_expected: int, counter_lock, completed_counter, last_reported_counter):
    """Thread-safe AI call progress reporting that prevents out-of-order updates"""
    if not session_id or total_expected <= 0:
        return completed_counter[0], last_reported_counter[0]
    
    with counter_lock:
        completed_counter[0] += 1
        current_count = completed_counter[0]
        
        # Only report if count actually increased from last reported value
        if current_count > last_reported_counter[0]:
            last_reported_counter[0] = current_count
            
            # Calculate progress percentage
            ai_progress = 5 + (current_count / total_expected) * 85
            progress_percent = min(90, int(ai_progress))  # Cap at 90%
            
            send_websocket_progress(session_id, f"AI call {current_count}/{total_expected} completed", progress_percent)
            logger.info(f"[AI PROGRESS] Reported {current_count}/{total_expected} (was {completed_counter[0]-1})")
        else:
            logger.debug(f"[AI PROGRESS] Skipped reporting {current_count}/{total_expected} (already reported)")
    
    return completed_counter[0], last_reported_counter[0]

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for validation requests and config generation."""
    try:
        # Check for config generation request first
        if event.get('config_generation_request'):
            logger.info("Processing config generation request")
            return handle_config_generation_request(event, context)
        
        # Continue with normal validation logic
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
                response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
                log_groups = response.get('logGroups', [])
                log_group_exists = any(lg['logGroupName'] == log_group_name for lg in log_groups)
                
                if log_group_exists:
                    logger.info(f"Log group exists: {log_group_name}")
                else:
                    # Create log group if it doesn't exist
                    try:
                        logs_client.create_log_group(logGroupName=log_group_name)
                        logger.info(f"Created log group: {log_group_name}")
                    except Exception as create_e:
                        logger.error(f"Failed to create log group: {str(create_e)}")
                        logger.error("This may indicate a permissions issue with the Lambda execution role")
            except Exception as e:
                logger.error(f"Failed to check log group existence: {str(e)}")
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
        
        print(f"LAMBDA_HANDLER: Config has validation_targets: {'validation_targets' in config}")
        if 'validation_targets' in config:
            print(f"LAMBDA_HANDLER: Number of validation_targets: {len(config['validation_targets'])}")
            # Print first validation target for debugging
            if config['validation_targets']:
                first_target = config['validation_targets'][0]
                print(f"LAMBDA_HANDLER: First validation target: {first_target}")
        
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
        
        # Extract session_id for progress updates
        session_id = event.get('session_id')
        if session_id:
            logger.info(f"Session ID for progress updates: {session_id}")
            send_websocket_progress(session_id, "Starting validation process...", 5)
        
        # Process rows
        rows = event.get('validation_data', {}).get('rows', [])
        validation_results = {}
        total_cache_hits = 0
        total_cache_misses = 0
        total_multiplex_validations = 0
        total_single_validations = 0
        
        # Thread-safe counter for AI call progress tracking
        import threading
        ai_call_counter_lock = threading.Lock()
        completed_ai_calls = [0]  # Use list for mutable reference
        last_reported_count = [0]  # Use list for mutable reference
        
        # Calculate total expected AI calls for progress tracking
        # Interface lambda now sends ALL rows at once, so len(rows) = total dataset size
        validation_targets = [t for t in validator.validation_targets if t.importance.upper() not in ["ID", "IGNORED"]]
        grouped_targets = validator.group_columns_by_search_group(validation_targets)
        search_groups_count = len(grouped_targets)
        total_expected_ai_calls = search_groups_count * len(rows)
        
        # Processing progress setup completed
        # Expected AI calls calculated
        
        # Track batch-level timing and API provider usage
        batch_timing_data = []
        total_batches = 0
        batches_with_claude = 0
        batches_without_claude = 0
        batch_manager = None  # Will be set in process_all_rows
        
        async def process_all_rows():
            nonlocal total_cache_hits, total_cache_misses, total_multiplex_validations, total_single_validations, batch_timing_data, total_batches, total_expected_ai_calls, batches_with_claude, batches_without_claude, batch_manager, search_groups_count
            
            # Initialize dynamic batch size manager (enhanced version with CSV config if available)
            if ENHANCED_BATCH_MANAGER_AVAILABLE:
                try:
                    batch_manager = EnhancedDynamicBatchSizeManager(
                        session_id=session_id,
                        enable_audit_logging=True
                    )
                    logger.info("🚀 Using EnhancedDynamicBatchSizeManager with CSV configuration")
                except Exception as e:
                    logger.error(f"Failed to initialize enhanced batch manager: {e}")
                    logger.info("🔄 Falling back to basic DynamicBatchSizeManager")
                    batch_manager = DynamicBatchSizeManager(
                        initial_batch_size=50,  # Start with 50 rows per batch
                        min_batch_size=10,      # Minimum 10 rows per batch
                        max_batch_size=100,     # Maximum 100 rows per batch
                        success_increase_factor=1.1,      # 10% increase on success streak
                        failure_decrease_factor=0.75,     # 25% decrease on failure
                        consecutive_successes_for_increase=5,  # Need 5 consecutive successes
                        consecutive_failures_for_decrease=2    # Reduce after 2 failures
                    )
            else:
                # Fallback to basic batch manager if enhanced version not available
                logger.info("🔄 Using basic DynamicBatchSizeManager (enhanced version not available)")
                batch_manager = DynamicBatchSizeManager(
                    initial_batch_size=50,  # Start with 50 rows per batch
                    min_batch_size=10,      # Minimum 10 rows per batch
                    max_batch_size=100,     # Maximum 100 rows per batch
                    success_increase_factor=1.1,      # 10% increase on success streak
                    failure_decrease_factor=0.75,     # 25% decrease on failure
                    consecutive_successes_for_increase=5,  # Need 5 consecutive successes
                    consecutive_failures_for_decrease=2    # Reduce after 2 failures
                )
            
            # Discover which models will be used across all rows
            all_models = discover_batch_models(rows, validator)
            
            # Get initial batch size based on discovered models
            current_batch_size = batch_manager.get_batch_size_for_models(all_models)
            total_batches = (len(rows) + current_batch_size - 1) // current_batch_size  # Calculate total number of batches
            
            logger.info(f"🚀 PER-MODEL BATCH PROCESSING: {len(rows)} rows in {total_batches} batches starting with {current_batch_size} rows each")
            logger.info(f"🔍 Models that will be used: {sorted(all_models) if all_models else ['default']}")
            
            async with aiohttp.ClientSession() as session:
                processed_rows = 0
                batch_num = 0
                
                while processed_rows < len(rows):
                    # Discover models for this specific batch
                    batch_start_idx = processed_rows
                    batch_end_idx = min(batch_start_idx + batch_manager.get_batch_size_for_models(all_models), len(rows))
                    potential_batch = rows[batch_start_idx:batch_end_idx]
                    
                    # Get current batch size based on models for this batch
                    batch_models = discover_batch_models(potential_batch, validator) if potential_batch else all_models
                    current_batch_size = batch_manager.get_batch_size_for_models(batch_models)
                    
                    # Calculate batch boundaries with updated batch size
                    start_idx = processed_rows
                    end_idx = min(start_idx + current_batch_size, len(rows))
                    batch = rows[start_idx:end_idx]
                    actual_batch_size = len(batch)
                    batch_index = batch_num + 1
                    
                    logger.info(f"Starting batch {batch_index} with {actual_batch_size} rows")
                    
                    # Log batch manager status every 10 batches
                    if batch_index % 10 == 0:
                        batch_manager.log_status()
                    
                    batch_start_time = time.time()
                    
                    # REMOVED: Batch progress messages (interface lambda handles batch-level progress)
                    # Validation lambda will send row-level detail updates instead
                    
                    row_tasks = []
                    for row_idx, row in enumerate(batch):
                        task = asyncio.create_task(process_row(session, row, start_idx + row_idx, batch_manager))
                        row_tasks.append(task)
                    
                    # Wait for all rows in the batch to complete
                    batch_success = True
                    try:
                        batch_results = await asyncio.gather(*row_tasks)
                        
                        batch_end_time = time.time()
                        batch_processing_time = batch_end_time - batch_start_time
                        
                        # Track models used in this batch
                        batch_models_used = set()
                        batch_api_providers = set()
                        for row_idx, row_results, row_models in batch_results:
                            batch_models_used.update(row_models)
                            # Also track providers for backward compatibility
                            for model in row_models:
                                batch_api_providers.add(determine_api_provider(model))
                        
                        # Count batches with Claude vs without Claude (for backward compatibility)
                        if 'anthropic' in batch_api_providers:
                            batches_with_claude += 1
                            # Batch used Claude models
                        else:
                            batches_without_claude += 1
                            # Batch used Perplexity models
                        
                        # Store batch timing data
                        batch_timing_info = {
                            'batch_number': batch_index,
                            'batch_size': actual_batch_size,
                            'processing_time_seconds': batch_processing_time,
                            'time_per_row_in_batch': batch_processing_time / actual_batch_size if actual_batch_size > 0 else 0,
                            'dynamic_batch_size': current_batch_size,
                            'api_providers': list(batch_api_providers)
                        }
                        batch_timing_data.append(batch_timing_info)
                        
                        logger.info(f"Completed batch {batch_index} in {batch_processing_time:.2f}s")
                        
                        # Notify batch manager of success with models used
                        batch_manager.on_success(batch_models_used)
                        
                        # Store results
                        logger.info(f"Storing results for batch {batch_index}: {len(batch_results)} results")
                        for idx, result, _ in batch_results:
                            validation_results[idx] = result
                            
                    except Exception as batch_error:
                        batch_success = False
                        batch_end_time = time.time()
                        batch_processing_time = batch_end_time - batch_start_time
                        logger.error(f"❌ Batch {batch_index} failed after {batch_processing_time:.2f}s: {str(batch_error)}")
                        
                        # Check if this was a rate limit error
                        error_str = str(batch_error).lower()
                        is_rate_limit = "rate_limit" in error_str or "429" in error_str
                        
                        # Extract models from completed results in failed batch
                        failed_batch_models = set()
                        for task in row_tasks:
                            if task.done() and not task.exception():
                                try:
                                    _, _, row_models = task.result()
                                    failed_batch_models.update(row_models)
                                except Exception as e:
                                    logger.debug(f"Could not extract models from completed task: {e}")
                        
                        # If no completed results, use the expected models for this batch
                        if not failed_batch_models:
                            failed_batch_models = batch_models
                        
                        # Notify batch manager of failure with models used
                        batch_manager.on_failure(failed_batch_models, is_rate_limit=is_rate_limit)
                        
                        # Store partial results if any tasks completed successfully
                        completed_results = []
                        for task in row_tasks:
                            if task.done() and not task.exception():
                                try:
                                    completed_results.append(task.result())
                                except Exception as e:
                                    logger.warning(f"Failed to get result from completed task: {e}")
                        
                        logger.info(f"Storing {len(completed_results)} partial results from failed batch {batch_index}")
                        for idx, result, _ in completed_results:
                            validation_results[idx] = result
                    
                    # Update progress
                    processed_rows = end_idx
                    batch_num += 1
                    
                    # Add small delay between batches to prevent overwhelming the system
                    if batch_num < total_batches:
                        await asyncio.sleep(0.1)
                
                # Log final batch manager statistics
                final_stats = batch_manager.get_stats()
                # Final batch statistics logged
                
                # Log detailed model statistics
                for model in final_stats['registered_models']:
                    batch_size = final_stats['model_batch_sizes'][model]
                    rate_limits = final_stats['model_rate_limit_events'][model]
                    success_rate = final_stats['model_success_rates'][model]
                    # Model statistics logged
                
                # Log batch API provider statistics
                # API provider statistics logged
                
        
        async def process_row(session, row, row_idx, batch_manager=None):
            """Process a single row with progressive multiplexing."""
            nonlocal total_cache_hits, total_cache_misses, total_multiplex_validations, total_single_validations, total_expected_ai_calls
            
            # Track which models were used for this row
            row_models_used = set()
            
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
                
                # Processing search group
                
                # Always use multiplex validation regardless of number of fields
                await process_multiplex_group(session, row_data, row_results, targets, accumulated_results, validation_history, False, row_models_used)
                total_multiplex_validations += 1
                
                # Send AI call progress update via WebSocket using thread-safe counter
                report_ai_call_progress(session_id, total_expected_ai_calls, ai_call_counter_lock, completed_ai_calls, last_reported_count)
                
                # Add this group's results to accumulated results for next groups
                for target in targets:
                    if target.column in row_results:
                        accumulated_results[target.column] = row_results[target.column]
            
            # Still determine next check date, but without holistic validation
            next_check, reasons = validator.determine_next_check_date(row_data, row_results)
            row_results['next_check'] = next_check.isoformat() if next_check else None
            row_results['reasons'] = reasons
            
            return row_idx, row_results, row_models_used
        
        async def process_multiplex_group(session, row, row_results, targets, previous_results=None, validation_history=None, is_isolated_validation=False, row_models_used=None):
            """Process a group of columns with a single multiplex API call, even if there's only one column."""
            nonlocal total_cache_hits, total_cache_misses
            
            # Initialize row_models_used if not provided
            if row_models_used is None:
                row_models_used = set()
            
            # Get access to row_api_providers from the calling function
            import inspect
            frame = inspect.currentframe()
            while frame:
                if 'row_api_providers' in frame.f_locals:
                    row_api_providers = frame.f_locals['row_api_providers']
                    break
                frame = frame.f_back
            else:
                # Fallback if we can't find row_api_providers
                row_api_providers = set()
            
            # First, filter out any ID or IGNORED fields - we don't validate these
            validation_targets = [t for t in targets if t.importance.upper() not in ["ID", "IGNORED"]]
            
            # If there are no fields to validate after filtering, just return
            if not validation_targets:
                logger.info("No non-ID/IGNORED fields to validate in this group")
                return row_idx, row_results, row_models_used
                
            # Log clear info about what we're processing
            if len(validation_targets) == 1:
                logger.info(f"Processing field '{validation_targets[0].column}' using multiplex format")
                if is_isolated_validation:
                    logger.info(f"This is an ISOLATED validation for field '{validation_targets[0].column}'")
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
            
            # Resolve max web searches for Anthropic models in this search group
            max_web_searches = resolve_search_group_max_web_searches(validation_targets, validator)
            
            # Generate multiplex prompt first - we need this for the cache key
            logger.info(f"Generating multiplex prompt for {len(validation_targets)} field(s) with context from previous groups")
            logger.info(f"Using resolved model for search group: {model}")
            logger.info(f"Using resolved search context size for search group: {search_context_size}")
            logger.info(f"Using resolved max web searches for search group: {max_web_searches}")
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
                    'cached_at': cached_at,  # Add cache timestamp
                    'citations': []  # Cached responses won't have new citations, but maintain structure
                }
                
                # Parse the cached API response
                parsed_results = validator.parse_multiplex_result(cached_api_response, row)
                
                # ENHANCED LOGGING: Track expected vs actual cached results
                expected_columns = [t.column for t in validation_targets]
                actual_columns = list(parsed_results.keys())
                
                # Analyzing cached response
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
                            # New tuple structure: (value, confidence_level, sources, confidence_level, reasoning, main_source, original_confidence, explanation, consistent_with_model_knowledge)
                            row_results[target.column] = {
                                'value': parsed_result[0],
                                'confidence': parsed_result[1],  # String confidence now
                                'sources': parsed_result[2],
                                'confidence_level': parsed_result[3],
                                'reasoning': parsed_result[4],  # Changed from quote
                                'main_source': parsed_result[5],
                                'original_confidence': parsed_result[6] if len(parsed_result) > 6 else None,  # New field
                                'explanation': parsed_result[7] if len(parsed_result) > 7 else '',  # New field
                                'response_id': response_id,  # Reference which API response this came from
                                'model': model  # Add model information from our context
                            }
                            
                            # Add consistent_with_model_knowledge if available
                            if len(parsed_result) > 8:
                                row_results[target.column]['consistent_with_model_knowledge'] = parsed_result[8]
                            
                            # Add citations from raw API response
                            if response_id in row_results.get('_raw_responses', {}):
                                citations = row_results['_raw_responses'][response_id].get('citations', [])
                                row_results[target.column]['citations'] = citations
                            
                            # Keep quote for backward compatibility (map reasoning to quote)
                            row_results[target.column]['quote'] = parsed_result[4]
                            
                            cached_processed_count += 1
                            # Processed cached result
                        else:
                            logger.error(f"❌ CACHED COLUMN RESULT MISSING: {target.column} was expected but not found in cached parsed results")
                    
                    # Cached processing completed
                    
                    # Cache was complete and used successfully
                    return row_idx, row_results, row_models_used
                
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
            
            # Track which model is being used for this row
            row_models_used.add(model)
            
            # Use shared AI client for all API calls
            logger.info(f"Using shared AI client for {api_provider} API with model: {model}")
            
            # Variables to track the full result from shared client
            shared_client_result = None
            
            if api_provider == 'anthropic':
                # For Claude models, we need to structure the call differently
                schema = get_response_format_schema(is_multiplex=True)
                
                # Wrap the array schema in an object for tool calling
                tool_schema = {
                    "type": "object",
                    "properties": {
                        "validation_results": schema['json_schema']['schema']
                    },
                    "required": ["validation_results"]
                }
                
                # For Claude, we'll handle caching ourselves since we need specific cache key format
                result = await retry_api_call_with_backoff(
                    lambda: call_claude_with_shared_client(prompt, model, tool_schema, max_web_searches),
                    max_retries=5,  # 6 total attempts with specific delays
                    custom_delays=[1, 5, 10, 20, 30, 60],  # 1s, 5s, 10s, 20s, 30s, 60s
                    batch_manager=batch_manager,
                    model=model
                )
            else:
                # For Perplexity, use the validate_with_perplexity method
                logger.info(f"Using Perplexity with search_context_size: {search_context_size}")
                
                # The shared client returns a wrapper with response, token_usage, etc.
                async def call_perplexity_wrapper():
                    nonlocal shared_client_result
                    shared_client_result = await ai_client.validate_with_perplexity(prompt, model, search_context_size, use_cache=True)
                    # Return just the API response part for compatibility with existing parsing
                    return shared_client_result['response']
                
                result = await retry_api_call_with_backoff(
                    call_perplexity_wrapper,
                    max_retries=5,  # 6 total attempts with specific delays
                    custom_delays=[1, 5, 10, 20, 30, 60],  # 1s, 5s, 10s, 20s, 30s, 60s
                    batch_manager=batch_manager,
                    model=model
                )
            processing_time = time.time() - start_time
            
            # Store the raw API response for this prompt in row_results
            response_id = f"response_{len(row_results.get('_raw_responses', {})) + 1}"
            if '_raw_responses' not in row_results:
                row_results['_raw_responses'] = {}
            
            # Extract token usage information and cached status
            if shared_client_result and 'token_usage' in shared_client_result:
                # For Perplexity, use the token usage from shared client
                token_usage = shared_client_result['token_usage']
                is_cached = shared_client_result.get('is_cached', False)
                enhanced_data = shared_client_result  # Perplexity enhanced data
            else:
                # For Anthropic/Claude, extract from the result
                token_usage = extract_token_usage(result, model, search_context_size)
                is_cached = False
                enhanced_data = result.get('enhanced_data', None) if isinstance(result, dict) else None  # Claude enhanced data
            
            row_results['_raw_responses'][response_id] = {
                'prompt': prompt,
                'response': result,
                'is_cached': is_cached,
                'fields': [t.column for t in validation_targets],
                'model': model,  # Add model information
                'token_usage': token_usage,  # Add token usage tracking
                'processing_time': processing_time,  # Add actual processing time
                'citations': shared_client_result.get('citations', []) if shared_client_result else [],  # Add web search citations
                'enhanced_data': enhanced_data  # Store complete enhanced ai_client data for both Perplexity and Claude
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
                    # New tuple structure: (value, confidence_level, sources, confidence_level, reasoning, main_source, original_confidence, explanation, consistent_with_model_knowledge)
                    row_results[target.column] = {
                        'value': parsed_result[0],
                        'confidence': parsed_result[1],  # String confidence now
                        'sources': parsed_result[2],
                        'confidence_level': parsed_result[3],
                        'reasoning': parsed_result[4],  # Changed from quote
                        'main_source': parsed_result[5],
                        'original_confidence': parsed_result[6] if len(parsed_result) > 6 else None,  # New field
                        'explanation': parsed_result[7] if len(parsed_result) > 7 else '',  # New field
                        'response_id': response_id,  # Reference which API response this came from
                        'model': model  # Add model information from our context
                    }
                    
                    # Add consistent_with_model_knowledge if available
                    if len(parsed_result) > 8:
                        row_results[target.column]['consistent_with_model_knowledge'] = parsed_result[8]
                    
                    # Add citations from raw API response
                    if response_id in row_results.get('_raw_responses', {}):
                        citations = row_results['_raw_responses'][response_id].get('citations', [])
                        row_results[target.column]['citations'] = citations
                    
                    # Keep quote for backward compatibility (map reasoning to quote)
                    row_results[target.column]['quote'] = parsed_result[4]
                    
                    processed_count += 1
                    # Processed result
                else:
                    logger.error(f"❌ COLUMN RESULT MISSING: {target.column} was expected but not found in parsed results")
            
            # Processing summary completed
            
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
            
            # Wait for any remaining tasks to complete (don't cancel them)
            pending = asyncio.all_tasks(loop)
            if pending:
                logger.info(f"Waiting for {len(pending)} remaining tasks to complete...")
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
        finally:
            loop.close()
        
        # Extract final batch manager statistics
        final_stats = batch_manager.get_stats() if batch_manager else {}
        
        # Ensure we're returning the complete validation results for each row
        logger.info(f"Returning full validation results for {len(validation_results)} rows")
        
        # Enhanced cost/time data will be extracted from ai_client responses
        # No separate pricing lookup needed - data comes from ai_client.get_enhanced_call_metrics()
        
        # ========== ENHANCED AI_API_CLIENT INTEGRATION ==========
        # Collect all enhanced data from ai_client responses and use aggregation methods
        all_enhanced_call_data = []
        
        # Extract enhanced data from all responses
        logger.info(f"[AGG_DEBUG] Starting enhanced data extraction from {len(validation_results)} rows")
        for row_idx, row_result in validation_results.items():
            if '_raw_responses' in row_result:
                logger.info(f"[AGG_DEBUG] Row {row_idx}: Found {len(row_result['_raw_responses'])} raw responses")
                for response_id, response_data in row_result['_raw_responses'].items():
                    enhanced_data = response_data.get('enhanced_data')
                    if enhanced_data:
                        # Debug: Check what enhanced data contains
                        costs = enhanced_data.get('costs', {})
                        actual_cost = costs.get('actual', {}).get('total_cost', 0.0)
                        estimated_cost = costs.get('without_cache', {}).get('total_cost', 0.0)
                        provider_metrics = enhanced_data.get('provider_metrics', {})
                        
                        logger.info(f"[AGG_DEBUG] Row {row_idx}, Response {response_id}: "
                                  f"Actual cost: ${actual_cost:.6f}, Estimated cost: ${estimated_cost:.6f}, "
                                  f"Provider metrics: {list(provider_metrics.keys())}")
                        
                        # Add row context for tracking
                        enhanced_data_with_context = enhanced_data.copy()
                        enhanced_data_with_context['row_idx'] = row_idx
                        enhanced_data_with_context['response_id'] = response_id
                        all_enhanced_call_data.append(enhanced_data_with_context)
                    else:
                        logger.warning(f"[AGG_DEBUG] Row {row_idx}, Response {response_id}: No enhanced_data found")
            else:
                logger.warning(f"[AGG_DEBUG] Row {row_idx}: No _raw_responses found")
        
        # Use ai_client aggregation methods instead of manual calculations
        if all_enhanced_call_data:
            logger.info(f"[AGG_DEBUG] Collected {len(all_enhanced_call_data)} enhanced call data items for aggregation")
            
            # Debug: Summary of what we're about to aggregate
            total_calls_to_aggregate = len(all_enhanced_call_data)
            providers_found = set()
            costs_preview = []
            for item in all_enhanced_call_data:
                provider_metrics = item.get('provider_metrics', {})
                providers_found.update(provider_metrics.keys())
                costs = item.get('costs', {})
                actual_cost = costs.get('actual', {}).get('total_cost', 0.0)
                costs_preview.append(f"${actual_cost:.6f}")
            
            logger.info(f"[AGG_DEBUG] About to aggregate: {total_calls_to_aggregate} calls, "
                      f"Providers: {list(providers_found)}, "
                      f"Sample costs: {costs_preview[:5]}...")
            
            try:
                # Use ai_client.aggregate_provider_metrics() to get comprehensive aggregated data
                aggregated_metrics = ai_client.aggregate_provider_metrics(all_enhanced_call_data)
                
                # Debug: Check what came out of aggregation
                providers = aggregated_metrics.get('providers', {})
                totals = aggregated_metrics.get('totals', {})
                logger.info(f"[AGG_DEBUG] Aggregation complete - Providers: {list(providers.keys())}, "
                          f"Total calls: {totals.get('total_calls', 0)}, "
                          f"Total actual cost: ${totals.get('total_cost_actual', 0.0):.6f}, "
                          f"Total estimated cost: ${totals.get('total_cost_without_cache', 0.0):.6f}")
                
                # For preview operations, also calculate full validation estimates
                if event.get('is_preview', False):
                    total_rows_in_table = event.get('total_rows', len(validation_results))
                    preview_rows_processed = len(validation_results) 
                    
                    full_validation_estimates = ai_client.calculate_full_validation_estimates(
                        aggregated_metrics=aggregated_metrics,
                        total_rows_in_table=total_rows_in_table,
                        preview_rows_processed=preview_rows_processed
                    )
                    logger.info(f"Generated full validation estimates: {full_validation_estimates['total_estimates']}")
                else:
                    full_validation_estimates = None
                    
            except Exception as e:
                logger.error(f"Failed to use enhanced aggregation methods: {e}")
                # Fall back to manual aggregation
                aggregated_metrics = None
                full_validation_estimates = None
        else:
            logger.warning("No enhanced data found in responses - falling back to manual aggregation")
            aggregated_metrics = None
            full_validation_estimates = None

        # Collect all raw responses from all rows and aggregate token usage and processing time
        all_raw_responses = {}
        total_processing_time = 0.0  # This will be the sum of all batch times (parallel processing)
        total_token_usage = {
            'total_tokens': 0,
            'api_calls': 0,
            'cached_calls': 0,
            'total_cost': 0.0,  # Actual cost (only non-cached)
            'estimated_total_cost': 0.0,  # Estimated cost (all calls as if not cached)
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
                        # Counted cached call
                    else:
                        total_token_usage['api_calls'] += 1
                        # Counted API call
                    
                    # Aggregate token usage
                    if 'token_usage' in response_data:
                        usage = response_data['token_usage']
                        if usage:  # Only process if token_usage is not empty
                            api_provider = usage.get('api_provider', 'unknown')
                            total_tokens = usage.get('total_tokens', 0)
                            total_token_usage['total_tokens'] += total_tokens
                            
                            # REMOVED: Manual cost extraction - all costs now handled by enhanced_data aggregation
                            # No individual cost calculations should happen here
                    
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
                            # REMOVED: Manual cost extraction - handled by enhanced_data aggregation
                            is_cached = response_data.get('is_cached', False)
                            # Aggregate by provider
                            if api_provider == 'perplexity':
                                provider_usage = total_token_usage['by_provider']['perplexity']
                                input_tokens = usage.get('input_tokens', 0)
                                output_tokens = usage.get('output_tokens', 0)
                                
                                # Handle legacy cached format where we might have prompt_tokens/completion_tokens instead
                                if input_tokens == 0 and output_tokens == 0:
                                    input_tokens = usage.get('prompt_tokens', 0)
                                    output_tokens = usage.get('completion_tokens', 0)
                                
                                provider_usage['prompt_tokens'] += input_tokens  # ai_api_client normalizes to input_tokens
                                provider_usage['completion_tokens'] += output_tokens  # ai_api_client normalizes to output_tokens
                                provider_usage['total_tokens'] += total_tokens
                                provider_usage['calls'] += 1
                                # REMOVED: Manual cost aggregation - handled by enhanced_data aggregation
                            elif api_provider == 'anthropic':
                                provider_usage = total_token_usage['by_provider']['anthropic']
                                provider_usage['input_tokens'] += usage.get('input_tokens', 0)
                                provider_usage['output_tokens'] += usage.get('output_tokens', 0)
                                provider_usage['cache_creation_tokens'] += usage.get('cache_creation_tokens', 0)
                                provider_usage['cache_read_tokens'] += usage.get('cache_read_tokens', 0)
                                provider_usage['total_tokens'] += total_tokens
                                provider_usage['calls'] += 1
                                # REMOVED: Manual cost aggregation - handled by enhanced_data aggregation
                            
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
                            # Add to actual cost only if not cached
                            if not is_cached:
                                model_usage['input_cost'] += costs['input_cost']
                                model_usage['output_cost'] += costs['output_cost']
                                model_usage['total_cost'] += costs['total_cost']
                            
                            if api_provider == 'perplexity':
                                model_usage['prompt_tokens'] += usage.get('input_tokens', 0)  # ai_api_client normalizes to input_tokens
                                model_usage['completion_tokens'] += usage.get('output_tokens', 0)  # ai_api_client normalizes to output_tokens
                            elif api_provider == 'anthropic':
                                model_usage['input_tokens'] += usage.get('input_tokens', 0)
                                model_usage['output_tokens'] += usage.get('output_tokens', 0)
                                model_usage['cache_creation_tokens'] += usage.get('cache_creation_tokens', 0)
                                model_usage['cache_read_tokens'] += usage.get('cache_read_tokens', 0)
                
                # Remove the raw responses from the row result to avoid duplication
                del row_result['_raw_responses']
        
        # Calculate total actual cost from providers
        perplexity_actual_cost = total_token_usage['by_provider']['perplexity']['total_cost']
        anthropic_actual_cost = total_token_usage['by_provider']['anthropic']['total_cost']
        total_token_usage['total_cost'] = perplexity_actual_cost + anthropic_actual_cost
        
        # Log token usage and cost summary
        logger.info(f"Token Usage Summary: {total_token_usage['total_tokens']} total tokens")
        logger.info(f"Actual Cost: ${total_token_usage['total_cost']:.6f} (non-cached only)")
        logger.info(f"Estimated Cost: ${total_token_usage['estimated_total_cost']:.6f} (if nothing cached)")
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
        # Validation structure metrics:
        # Logged validation metrics
        
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
                    "token_usage": total_token_usage,  # Keep for backward compatibility
                    "processing_time": total_processing_time,  # Keep for backward compatibility
                    
                    # ========== ENHANCED AI_API_CLIENT MEASURES ==========
                    "enhanced_metrics": {
                        "aggregated_metrics": aggregated_metrics,  # Complete provider breakdown with costs/tokens/timing
                        "full_validation_estimates": full_validation_estimates,  # Full validation projections for preview operations
                        "preview_operation": event.get('is_preview', False),
                        "ai_client_calls_count": len(all_enhanced_call_data)
                    } if aggregated_metrics else None,
                    # NEW: Batch timing data
                    "batch_timing": {
                        "total_batches": len(batch_processing_times),
                        "dynamic_batch_sizing": True,  # Indicate that batch sizes were dynamic
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
                    },
                    # NEW: Batch API provider statistics (backward compatibility)
                    "batch_provider_stats": {
                        "batches_with_claude": batches_with_claude,
                        "batches_without_claude": batches_without_claude,
                        "total_batches": batches_with_claude + batches_without_claude
                    },
                    # NEW: Per-model batch statistics
                    "per_model_batch_stats": final_stats
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
            
        # Send final progress update
        if session_id:
            final_count = completed_ai_calls[0]
            send_websocket_progress(session_id, f"Validation completed! {final_count} AI calls processed", 100)
        
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