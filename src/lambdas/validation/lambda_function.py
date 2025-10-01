import json
import boto3
import hashlib
import unicodedata
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
import difflib
import queue
import threading

from schema_validator_simplified import SimplifiedSchemaValidator
from perplexity_schema import get_response_format_schema
from row_key_utils import generate_row_key
from ai_api_client import ai_client

def find_similar_columns(expected_columns: List[str], actual_columns: List[str], similarity_threshold: float = 0.8) -> Dict[str, str]:
    """
    Find column mappings between expected and actual columns using string similarity.
    
    Args:
        expected_columns: List of expected column names
        actual_columns: List of actual column names from API response
        similarity_threshold: Minimum similarity ratio (0.0 to 1.0) for a match
        
    Returns:
        Dictionary mapping actual column names to expected column names
        Only includes mappings above the similarity threshold
    """
    column_mappings = {}
    used_actual_columns = set()
    
    for expected_col in expected_columns:
        best_match = None
        best_ratio = 0.0
        
        for actual_col in actual_columns:
            if actual_col in used_actual_columns:
                continue
                
            # Calculate similarity ratio using difflib
            ratio = difflib.SequenceMatcher(None, expected_col.lower(), actual_col.lower()).ratio()
            
            if ratio > best_ratio and ratio >= similarity_threshold:
                best_match = actual_col
                best_ratio = ratio
        
        if best_match:
            column_mappings[best_match] = expected_col
            used_actual_columns.add(best_match)
    
    return column_mappings

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Add a handler to ensure logs appear in CloudWatch
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)
    logger.debug("Initialized logger with StreamHandler")
else:
    pass  # logger.info("Logger already has handlers, skipping handler setup")

# QC integration imports (after logger is configured)
try:
    from qc_integration import QCIntegrationManager
    QC_AVAILABLE = True
    logger.debug("QC module imported successfully")
except ImportError as e:
    QC_AVAILABLE = False
    logger.warning(f"QC module not available: {e}")

# Import enhanced batch manager (after logger is configured)
try:
    from enhanced_batch_manager import EnhancedDynamicBatchSizeManager
    ENHANCED_BATCH_MANAGER_AVAILABLE = True
    logger.debug("✅ Enhanced batch manager available")
except ImportError as e:
    logger.warning(f"Enhanced batch manager not available: {e}")
    ENHANCED_BATCH_MANAGER_AVAILABLE = False

# Import WebSocket client for progress updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
    logger.debug(f"WebSocket client initialized successfully")
except ImportError as e:
    websocket_client = None
    logger.debug(f"WebSocket client import failed: {e}")
except Exception as e:
    websocket_client = None
    logger.debug(f"WebSocket client initialization failed: {e}")

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
    
        logger.debug(f"Found models for batch: {sorted(models)}")
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
                logger.debug(f"Attempting to retrieve Anthropic API key from SSM parameter: {param_name}")
                
                response = ssm.get_parameter(
                    Name=param_name,
                    WithDecryption=True
                )
                api_key = response['Parameter']['Value']
                logger.debug(f"Successfully retrieved Anthropic API key from {param_name}")
                break
                
            except Exception as e:
                logger.warning(f"Failed to get Anthropic API key from SSM parameter '{param_name}': {str(e)}")
                continue
        
        if not api_key:
            logger.error("Failed to retrieve Anthropic API key from any SSM parameter variant")
            
            # Try to list parameters to help with debugging
            try:
                logger.debug("Attempting to list SSM parameters for debugging...")
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
                    logger.debug(f"Found parameters starting with 'Anthropic': {[p['Name'] for p in params_response['Parameters']]}")
                else:
                    pass  # logger.warning("No parameters found starting with 'Anthropic'")
                    
            except Exception as list_error:
                logger.error(f"Failed to list SSM parameters: {str(list_error)}")
            
            raise Exception(f"Anthropic API key not found in SSM. Tried parameters: {param_names}")
    else:
        logger.debug("Using Anthropic API key from environment variable")
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

def calculate_full_validation_estimates_with_batch_timing(aggregated_metrics: Dict, all_enhanced_call_data: List[Dict],
                                                         total_rows_in_table: int, preview_rows_processed: int,
                                                         batch_processing_times: Dict,
                                                         qc_manager=None,  # Add QC manager for QC time calculations
                                                         target_full_validation_batch_size: int = 50) -> Dict[str, Any]:
    """
    Calculate full validation estimates based on aggregated preview metrics and actual batch timing.
    This function belongs in validation lambda because only it knows the batch architecture.
    Uses actual batch/row/search group information from enhanced_data.
    
    Args:
        aggregated_metrics: Output from aggregate_provider_metrics()
        all_enhanced_call_data: All individual enhanced_data from AI client calls with batch_number, row_idx, search_group
        total_rows_in_table: Total number of rows in the full table
        preview_rows_processed: Number of rows processed in the preview
        batch_processing_times: Actual batch timing measurements (batch_number -> actual_time)
        target_full_validation_batch_size: Target batch size to use for full validation (default: 50)
        
    Returns:
        Comprehensive full validation estimates with proper batch timing
    """
    try:
        if preview_rows_processed <= 0 or total_rows_in_table <= 0:
            logger.warning("calculate_full_validation_estimates: Invalid row counts")
            return {'error': 'invalid_row_counts'}
        
        if target_full_validation_batch_size <= 0:
            logger.warning(f"calculate_full_validation_estimates: Invalid target batch size: {target_full_validation_batch_size}, using default 50")
            target_full_validation_batch_size = 50
        
        pass  # logger.info(f"[ESTIMATE_CALCULATION] Starting with {total_rows_in_table} total rows, {preview_rows_processed} preview rows, target batch size {target_full_validation_batch_size}")
        
        scaling_factor = total_rows_in_table / preview_rows_processed
        
        # Group enhanced data by batch and row to calculate proper batch timing
        batches = {}  # batch_number -> {row_idx -> [enhanced_data_items]}
        
        if not all_enhanced_call_data:
            logger.error("calculate_full_validation_estimates: No enhanced call data available")
            return {'error': 'no_enhanced_call_data'}
        
        pass  # logger.info(f"[ESTIMATE_CALCULATION] Processing {len(all_enhanced_call_data)} enhanced call data items")
        
        for enhanced_data in all_enhanced_call_data:
            batch_number = enhanced_data.get('batch_number')
            row_idx = enhanced_data.get('row_idx')
            
            if batch_number is not None and row_idx is not None:
                if batch_number not in batches:
                    batches[batch_number] = {}
                if row_idx not in batches[batch_number]:
                    batches[batch_number][row_idx] = []
                batches[batch_number][row_idx].append(enhanced_data)
        
        # Calculate estimated batch timing using estimated times (not actual times with cache)
        estimated_batch_times = {}
        
        for batch_number, batch_rows in batches.items():
            batch_estimated_times = []  # List of total estimated time per row in this batch
            
            for row_idx, row_calls in batch_rows.items():
                # Sum estimated times for all calls in this row (calls per row are sequential)
                row_estimated_time = 0.0
                for enhanced_data in row_calls:
                    timing = enhanced_data.get('timing', {})
                    row_estimated_time += timing.get('time_estimated_seconds', 0.0)
                
                batch_estimated_times.append(row_estimated_time)
            
            # Batch time = max of all row times (rows in batch run in parallel)
            estimated_batch_times[batch_number] = max(batch_estimated_times) if batch_estimated_times else 0.0
        
        # Total estimated time = sum of all batch times (batches run sequentially)
        estimated_total_time_preview = sum(estimated_batch_times.values())
        avg_estimated_batch_time = estimated_total_time_preview / len(estimated_batch_times) if estimated_batch_times else 0.0
        
        # Get actual batch size statistics for full validation projection
        actual_batch_sizes = []
        for batch_num, batch_rows in batches.items():
            actual_batch_sizes.append(len(batch_rows))
        avg_actual_batch_size = sum(actual_batch_sizes) / len(actual_batch_sizes) if actual_batch_sizes else 10
        
        # Add QC time to batch estimates if QC is enabled
        qc_time_per_batch = 0.0
        if qc_manager and qc_manager.is_qc_enabled() and hasattr(qc_manager, 'get_qc_metrics'):
            qc_tracker_data = qc_manager.get_qc_metrics()
            total_qc_time_estimated = qc_tracker_data.get('total_qc_time_estimated', 0.0)
            # QC processes rows in sequence within a batch, so add total QC time to batch time
            # For preview, we processed actual_batches_processed batches
            qc_time_per_batch = total_qc_time_estimated / len(batches) if len(batches) > 0 else 0.0
            logger.debug(f"[BATCH_TIMING_QC] Adding QC time to batch estimates: {qc_time_per_batch:.2f}s per batch")

            # Add QC time to each batch estimate
            for batch_num in estimated_batch_times:
                estimated_batch_times[batch_num] += qc_time_per_batch

            # Recalculate totals with QC time included
            estimated_total_time_preview = sum(estimated_batch_times.values())
            avg_estimated_batch_time = estimated_total_time_preview / len(estimated_batch_times) if estimated_batch_times else 0.0

        # Calculate estimated batches and total time for full validation using target batch architecture
        # Use the target batch size for full validation, not the preview's smaller batch size
        # Use ceil because partial batches take as long as full batches (parallel processing within batch)
        import math
        estimated_batches_for_full_table = max(1, math.ceil(total_rows_in_table / target_full_validation_batch_size))
        # Batches run SEQUENTIALLY, rows within each batch run in PARALLEL
        estimated_total_time_for_full_validation = estimated_batches_for_full_table * avg_estimated_batch_time
        
        estimates = {
            'scaling_info': {
                'total_rows_in_table': total_rows_in_table,
                'preview_rows_processed': preview_rows_processed,
                'scaling_factor': scaling_factor
            },
            'batch_timing_analysis': {
                'preview_estimated_batch_times': estimated_batch_times,
                'preview_estimated_total_time': estimated_total_time_preview,
                'preview_avg_estimated_batch_time': avg_estimated_batch_time,
                'actual_batches_processed': len(batches),
                'preview_average_batch_size': avg_actual_batch_size,  # Actual batch size used in preview
                'target_full_validation_batch_size': target_full_validation_batch_size,  # Target size for full validation
                'estimated_batches_for_full_table': estimated_batches_for_full_table,
                'estimated_time_per_batch': avg_estimated_batch_time,
                'estimated_total_time_for_full_validation': estimated_total_time_for_full_validation
            },
            'provider_estimates': {},
            'total_estimates': {}
        }
        
        # Calculate estimates by provider from aggregated metrics
        providers = aggregated_metrics.get('providers', {})
        for provider, provider_data in providers.items():
            estimates['provider_estimates'][provider] = {
                'estimated_calls': int(provider_data.get('calls', 0) * scaling_factor),
                'estimated_tokens': int(provider_data.get('tokens', 0) * scaling_factor),
                'estimated_cost_actual': provider_data.get('cost_actual', 0.0) * scaling_factor,
                'estimated_cost_estimated': provider_data.get('cost_estimated', 0.0) * scaling_factor,
                'estimated_processing_time': provider_data.get('estimated_processing_time', 0.0) * scaling_factor
            }
        
        # Calculate direct average row estimated processing time over all rows
        # NOTE: This is different from existing fields:
        #   - time_per_row_seconds: actual time with cache benefits
        #   - avg_time_per_row_seconds: calculated from total/rows in DynamoDB
        # This field: avg_estimated_row_processing_time = direct average of estimated times (no cache) across all individual rows
        total_row_estimated_times = []
        for enhanced_data in all_enhanced_call_data:
            row_idx = enhanced_data.get('row_idx')
            if row_idx is not None:
                # Calculate total estimated time per row by summing all calls for that row
                row_calls = [ed for ed in all_enhanced_call_data if ed.get('row_idx') == row_idx]
                row_estimated_time = sum(
                    ed.get('timing', {}).get('time_estimated_seconds', 0.0)
                    for ed in row_calls
                )
                if row_idx not in [r[0] for r in total_row_estimated_times]:  # Avoid duplicates
                    total_row_estimated_times.append((row_idx, row_estimated_time))
        
        # Calculate the direct average over all rows
        avg_row_estimated_time = sum(time for _, time in total_row_estimated_times) / len(total_row_estimated_times) if total_row_estimated_times else 0.0
        
        # Calculate total estimates using proper timing
        totals = aggregated_metrics.get('totals', {})
        estimates['total_estimates'] = {
            'estimated_total_calls': int(totals.get('total_calls', 0) * scaling_factor),
            'estimated_total_tokens': int(totals.get('total_tokens', 0) * scaling_factor),
            'estimated_total_cost_actual': totals.get('total_cost_actual', 0.0) * scaling_factor,
            'estimated_total_cost_estimated': totals.get('total_cost_estimated', 0.0) * scaling_factor,
            'estimated_total_processing_time': estimated_total_time_for_full_validation,  # Use proper batch-based scaling
            'estimated_actual_processing_time': sum(batch_processing_times.values()) * scaling_factor,  # Actual timing with cache benefits
            'estimated_total_cache_savings_cost': totals.get('total_cache_savings_cost', 0.0) * scaling_factor,
            'estimated_cache_efficiency_percent': totals.get('overall_cache_efficiency', 0.0),
            'avg_estimated_row_processing_time': avg_row_estimated_time  # Direct average over all rows using estimated times (no scaling needed - already per-row)
        }
        
        # Add per-provider cost calculations
        providers = aggregated_metrics.get('providers', {})
        estimates['per_provider_estimates'] = {}
        
        for provider_name, provider_data in providers.items():
            provider_cost_estimated = provider_data.get('cost_estimated', 0.0)
            provider_cost_actual = provider_data.get('cost_actual', 0.0)
            
            # Calculate per-row costs using estimated costs (no cache benefits)
            per_row_estimated_cost = provider_cost_estimated / preview_rows_processed if preview_rows_processed > 0 else 0.0
            per_row_actual_cost = provider_cost_actual / preview_rows_processed if preview_rows_processed > 0 else 0.0
            
            estimates['per_provider_estimates'][provider_name] = {
                'total_cost_estimated': provider_cost_estimated * scaling_factor,
                'total_cost_actual': provider_cost_actual * scaling_factor,
                'per_row_estimated_cost': per_row_estimated_cost,
                'per_row_actual_cost': per_row_actual_cost,
                'calls': provider_data.get('calls', 0),
                'tokens': provider_data.get('tokens', 0)
            }
        
        # Add timing calculations
        estimates['timing_estimates'] = {
            'time_per_row_seconds': avg_row_estimated_time,  # Use estimated time without cache
            'total_estimated_time_seconds': estimated_total_time_for_full_validation,
            'actual_processing_time_seconds': sum(batch_processing_times.values()),
            'actual_time_per_batch_seconds': avg_estimated_batch_time
        }
        
        # Debug logging
        pass  # logger.info(f"[BATCH_TIMING] Processed {len(batches)} batches with {len(all_enhanced_call_data)} total calls")
        pass  # logger.info(f"[BATCH_TIMING] Preview: {estimated_total_time_preview:.2f}s, Actual total time: {sum(batch_processing_times.values()):.2f}s")
        pass  # logger.info(f"[BATCH_TIMING] Preview average batch size: {avg_actual_batch_size:.1f} rows, Average estimated batch time: {avg_estimated_batch_time:.2f}s")
        logger.debug(f"[BATCH_TIMING] Full validation: {total_rows_in_table} rows ÷ {target_full_validation_batch_size} target batch size = {estimated_batches_for_full_table} batches")
        logger.debug(f"[BATCH_TIMING] Full validation estimate: {estimated_batches_for_full_table} batches × {avg_estimated_batch_time:.2f}s = {estimated_total_time_for_full_validation:.2f}s total")
        pass  # logger.info(f"[BATCH_TIMING] Average estimated row processing time: {avg_row_estimated_time:.2f}s (direct calculation over {len(total_row_estimated_times)} rows)")
        
        # Log per-provider cost estimates
        for provider_name, provider_estimates in estimates['per_provider_estimates'].items():
            pass  # logger.info(f"[PROVIDER_COSTS] {provider_name}: ${provider_estimates['per_row_estimated_cost']:.6f} per row (estimated), "
                  # f"${provider_estimates['total_cost_estimated']:.6f} total estimated")
        
        return estimates
        
    except Exception as e:
        logger.error(f"calculate_full_validation_estimates_with_batch_timing: Error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {'error': str(e)}

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
        enhanced_data = result.get('enhanced_data', {})
        formatted_response['enhanced_data'] = enhanced_data
        
        # Debug logging for enhanced data
        if enhanced_data:
            costs = enhanced_data.get('costs', {})
            pass  # logger.info(f"[ENHANCED_DEBUG] Enhanced data found - actual: ${costs.get('total_cost', 0):.6f}, "
                       # f"estimated: ${costs.get('total_cost_without_cache', 0):.6f}")
        else:
            pass  # logger.warning(f"[ENHANCED_DEBUG] No enhanced_data found in result: {list(result.keys())}")
        
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
                        logger.debug(f"Using search group {group_id} defined model: {group_def['model']}")
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
        logger.debug(f"Search group uses consistent model: {selected_model}")
        return selected_model, warnings
    
    # If we have conflicts, prefer any specified model over default
    non_default_models = [m for m in models_in_group if m != validator.default_model]
    
    if len(non_default_models) == 1:
        # Only one non-default model, use that
        selected_model = non_default_models[0]
        logger.debug(f"Search group has mixed models, preferring specified model: {selected_model} over default: {validator.default_model}")
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
        logger.debug(f"Search group using default model: {selected_model}")
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
    pass  # logger.debug(f"RESOLVE_MAX_WEB_SEARCHES: Called with {len(targets)} targets")
    
    # Check if we have search group definitions and this group has a defined max_web_searches
    if targets and hasattr(targets[0], 'search_group'):
        group_id = targets[0].search_group
        logger.debug(f"Checking search group {group_id} for anthropic_max_web_searches override")
        
        # Check if validator has search_groups defined
        if hasattr(validator, 'search_groups') and validator.search_groups:
            for group_def in validator.search_groups:
                if isinstance(group_def, dict) and group_def.get('group_id') == group_id:
                    if 'anthropic_max_web_searches' in group_def:
                        max_searches = group_def['anthropic_max_web_searches']
                        logger.debug(f"Using search group {group_id} defined anthropic_max_web_searches: {max_searches}")
                        return max_searches
    
    # Check for validator default
    if hasattr(validator, 'config') and isinstance(validator.config, dict):
        default_max_searches = validator.config.get('anthropic_max_web_searches_default')
        if default_max_searches is not None:
            logger.debug(f"Using validator default anthropic_max_web_searches: {default_max_searches}")
            return default_max_searches
    
    # Global default
    logger.debug("Using global default anthropic_max_web_searches: 3")
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
    pass  # logger.debug(f"RESOLVE_CONTEXT: Called with {len(targets)} targets")
    # Check if we have search group definitions and this group has a defined context
    if targets and hasattr(targets[0], 'search_group'):
        group_id = targets[0].search_group
        logger.debug(f"Checking search group {group_id} for context override")
        
        # Check if validator has search_groups defined
        if hasattr(validator, 'search_groups') and validator.search_groups:
            # Checking search group definitions
            for group_def in validator.search_groups:
                if isinstance(group_def, dict) and group_def.get('group_id') == group_id:
                    if 'search_context' in group_def:
                        logger.debug(f"Using search group {group_id} defined context: {group_def['search_context']}")
                        return group_def['search_context']
                    else:
                        logger.warning(f"Search group {group_id} found but no search_context defined")
        else:
            logger.debug(f"Validator has no search_groups or empty search_groups")
    
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
    
    logger.debug(f"Search group context sizes: {context_sizes}, selected: {selected_context_size}")
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
                logger.debug(f"API call succeeded on attempt {attempt + 1}")
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
        logger.debug("=== CONFIG GENERATION REQUEST ===")
        
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
        
        logger.debug(f"Config generation for session: {session_id}, mode: {generation_mode}")
        
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
                        "search_context_size": {"type": "string", "enum": ["low", "medium", "high"]}
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
        
        logger.debug(f"Config uploaded to S3: {key}")
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
        
        logger.debug(f"Created download URL for S3 key: {s3_key}")
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

def construct_enhanced_models_parameter(validator, all_enhanced_call_data: List[Dict], aggregated_metrics: Dict, qc_fail_rates_by_column: Dict[str, Dict] = None) -> Dict:
    """
    Construct enhanced models parameter JSON structure with detailed information per search group.
    
    Args:
        validator: SimplifiedSchemaValidator instance with configuration
        all_enhanced_call_data: List of enhanced call data from ai_api_client
        aggregated_metrics: Aggregated metrics from ai_api_client
    
    Returns:
        Dict: Enhanced models parameter with search group details
    """
    try:
        enhanced_models = {}

        logger.debug(f"[ENHANCED_MODELS_DEBUG] construct_enhanced_models_parameter called")
        logger.debug(f"[ENHANCED_MODELS_DEBUG] all_enhanced_call_data type: {type(all_enhanced_call_data)}, length: {len(all_enhanced_call_data) if all_enhanced_call_data else 0}")
        logger.debug(f"[ENHANCED_MODELS_DEBUG] aggregated_metrics type: {type(aggregated_metrics)}, is_none: {aggregated_metrics is None}")

        # Get validation targets and group by search group - exclude ID and IGNORED for models array
        all_targets = getattr(validator, 'validation_targets', [])
        validation_targets = [t for t in all_targets if t.importance.upper() not in ["ID", "IGNORED"]]
        logger.debug(f"Enhanced models debug: all_targets count: {len(all_targets)}, validation_targets count: {len(validation_targets)}")
        if not validation_targets:
            logger.warning("No non-ID/IGNORED validation targets found in validator")
            return {}
        
        # Group targets by search group
        grouped_targets = validator.group_columns_by_search_group(validation_targets)
        logger.debug(f"Enhanced models debug: grouped_targets count: {len(grouped_targets)}")
        logger.debug(f"Enhanced models debug: all_enhanced_call_data length: {len(all_enhanced_call_data) if all_enhanced_call_data else 0}")
        logger.debug(f"Enhanced models debug: aggregated_metrics: {aggregated_metrics is not None}")
        
        # Get overall aggregated metrics for cost/time calculations
        providers_data = aggregated_metrics.get('providers', {}) if aggregated_metrics else {}
        totals_data = aggregated_metrics.get('totals', {}) if aggregated_metrics else {}
        
        # Calculate total ESTIMATED costs and times (without caching benefits)
        total_cost_estimated = totals_data.get('total_cost_estimated', 0.0)
        total_estimated_time = totals_data.get('total_estimated_processing_time', 0.0)
        
        # If not found in totals, try providers for estimated values
        if total_cost_estimated == 0.0 or total_estimated_time == 0.0:
            for provider, provider_data in providers_data.items():
                if total_cost_estimated == 0.0:
                    total_cost_estimated += provider_data.get('cost_estimated', 0.0)
                if total_estimated_time == 0.0:
                    total_estimated_time += provider_data.get('total_estimated_processing_time', 0.0)
        
        # Map search groups from call data to actual search group IDs
        # The search_group in call data is a counter (0, 1, 2...), need to map to actual IDs
        sorted_group_ids = sorted(grouped_targets.keys())
        
        # Extract model usage stats per search group from enhanced call data (estimated values)
        search_group_stats = {}
        model_usage_stats = {}
        
        # Debug: Log structure of enhanced call data
        if all_enhanced_call_data:
            sample_call = all_enhanced_call_data[0]
            pass  # logger.info(f"[ENHANCED_MODELS_DEBUG] Sample enhanced call data keys: {list(sample_call.keys())}")
            pass  # logger.info(f"[ENHANCED_MODELS_DEBUG] Sample values - cost_estimated: {sample_call.get('cost_estimated')}, estimated_processing_time: {sample_call.get('estimated_processing_time')}, search_group: {sample_call.get('search_group')}")
        
        for call_data in all_enhanced_call_data:
            # Extract model from call_info structure
            call_info = call_data.get('call_info', {})
            model_used = call_info.get('model', 'unknown')
            
            # Extract cost and timing from nested structures
            costs = call_data.get('costs', {})
            estimated_costs = costs.get('estimated', {})
            cost_estimated = estimated_costs.get('total_cost', 0.0)
            
            timing = call_data.get('timing', {})
            time_estimated = timing.get('time_estimated_seconds', 0.0)
            
            search_group_counter = call_data.get('search_group', 0)  # This is the counter (0, 1, 2...)
            
            # Map counter to actual search group ID
            if search_group_counter < len(sorted_group_ids):
                actual_search_group_id = sorted_group_ids[search_group_counter]
            else:
                actual_search_group_id = 'unknown'
            
            # Track per search group
            if actual_search_group_id not in search_group_stats:
                search_group_stats[actual_search_group_id] = {
                    'models_used': set(),
                    'cost_estimated': 0.0,
                    'estimated_processing_time': 0.0,
                    'call_count': 0
                }
            
            search_group_stats[actual_search_group_id]['models_used'].add(model_used)
            search_group_stats[actual_search_group_id]['cost_estimated'] += cost_estimated
            search_group_stats[actual_search_group_id]['estimated_processing_time'] += time_estimated
            search_group_stats[actual_search_group_id]['call_count'] += 1
            
            # Also track per model (for fallback)
            if model_used not in model_usage_stats:
                model_usage_stats[model_used] = {
                    'cost_estimated': 0.0,
                    'estimated_processing_time': 0.0,
                    'call_count': 0
                }
            
            model_usage_stats[model_used]['cost_estimated'] += cost_estimated
            model_usage_stats[model_used]['estimated_processing_time'] += time_estimated
            model_usage_stats[model_used]['call_count'] += 1
        
        # Build enhanced models structure for each search group
        for search_group_id, targets in grouped_targets.items():
            group_key = f"search_group_{search_group_id}"

            # Filter to only non-ignored targets
            active_targets = [t for t in targets if t.importance.upper() not in ('ID', 'IGNORED')]
            column_count = len(active_targets)

            logger.debug(f"Enhanced models debug: search_group_{search_group_id} has {len(targets)} total targets, {column_count} active targets")
            if targets:
                logger.debug(f"Enhanced models debug: sample target importance values: {[t.importance for t in targets[:3]]}")

            if column_count == 0:
                logger.warning(f"Enhanced models debug: Skipping search_group_{search_group_id} - no active columns after filtering")
                continue  # Skip groups with no active columns
            
            # Get column names for this search group
            column_names = [target.column for target in active_targets if hasattr(target, 'column')]
            
            # Resolve model and settings for this search group
            configured_model, _ = resolve_search_group_model(targets, validator)
            search_context_level = resolve_search_group_context_size(targets, validator)
            max_web_searches_value = resolve_search_group_max_web_searches(targets, validator)
            
            # Get full search group configuration information
            search_group_config = {}
            search_groups_config = getattr(validator, 'search_groups', [])
            for group_config in search_groups_config:
                if group_config.get('group_id') == search_group_id:
                    search_group_config = group_config.copy()
                    break
            
            # Determine models requested vs actually used
            models_requested = [configured_model]
            
            # Get actual usage statistics for this search group
            group_stats = search_group_stats.get(search_group_id, {
                'models_used': set(),
                'cost_estimated': 0.0,
                'estimated_processing_time': 0.0,
                'call_count': 0
            })
            
            # Determine actual models used vs configured
            models_actually_used = list(group_stats['models_used'])
            if models_actually_used:
                # Use most frequently used model as mode (for now, just use first)
                mode_model_used = models_actually_used[0] if configured_model in models_actually_used else configured_model
                other_models_used = [m for m in models_actually_used if m != mode_model_used]
            else:
                # No actual data, use configured model
                mode_model_used = configured_model
                other_models_used = []
            
            # Calculate per-group cost and time estimates
            if group_stats['call_count'] > 0:
                # Use actual search group data
                average_estimated_cost = group_stats['cost_estimated'] / group_stats['call_count']
                average_estimated_time = group_stats['estimated_processing_time'] / group_stats['call_count']
            else:
                # Fallback: use model-specific data if available
                model_stats = model_usage_stats.get(configured_model, {
                    'cost_estimated': 0.0,
                    'estimated_processing_time': 0.0,
                    'call_count': 0
                })
                
                if model_stats['call_count'] > 0:
                    average_estimated_cost = model_stats['cost_estimated'] / model_stats['call_count']
                    average_estimated_time = model_stats['estimated_processing_time'] / model_stats['call_count']
                else:
                    # Final fallback: distribute total across active groups
                    total_active_groups = len([sg for sg, tgts in grouped_targets.items()
                                             if len([t for t in tgts if t.importance.upper() not in ('ID', 'IGNORED')]) > 0])
                    
                    if total_active_groups > 0:
                        average_estimated_cost = total_cost_estimated / total_active_groups
                        average_estimated_time = total_estimated_time / total_active_groups
                    else:
                        average_estimated_cost = 0.0
                        average_estimated_time = 0.0
            
            # Determine max_web_searches value for display
            max_web_searches = None
            if 'claude' in configured_model.lower() or 'anthropic' in configured_model.lower():
                max_web_searches = max_web_searches_value
            
            # NOTE: QC metrics are now tracked separately at the validation level,
            # not per search group, since QC is done after validation is complete

            # Build the enhanced structure
            enhanced_models[group_key] = {
                "models_requested": models_requested,
                "mode_model_used": mode_model_used,
                "other_models_used": other_models_used,
                "column_count": column_count,
                "column_names": column_names,
                "average_estimated_cost": round(average_estimated_cost, 6),
                "average_estimated_time": round(average_estimated_time, 2),
                "search_context_level": search_context_level,
                "max_web_searches": max_web_searches,
                "search_group_config": search_group_config
            }
        
        # Debug: Log what we constructed
        logger.debug(f"[ENHANCED_MODELS_DEBUG] Constructed enhanced models parameter with {len(enhanced_models)} search groups")
        logger.debug(f"[ENHANCED_MODELS_DEBUG] Enhanced models keys: {list(enhanced_models.keys())}")
        logger.debug(f"[ENHANCED_MODELS_DEBUG] Search group stats found: {list(search_group_stats.keys())}")
        for group_id, stats in search_group_stats.items():
            logger.debug(f"[ENHANCED_MODELS_DEBUG] Group {group_id}: calls={stats['call_count']}, cost=${stats['cost_estimated']:.6f}, time={stats['estimated_processing_time']:.2f}")
        logger.debug(f"Constructed enhanced models parameter with {len(enhanced_models)} search groups")
        return enhanced_models
        
    except Exception as e:
        logger.error(f"Error constructing enhanced models parameter: {str(e)}")
        logger.error(traceback.format_exc())
        return {}

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

def progress_sender(progress_queue, session_id):
    """
    Worker thread function to send progress updates from a queue.

    This function runs in a separate thread and processes messages from the
    progress_queue. It ensures that only the latest progress is sent and
    discards any stale (out-of-order) messages.
    """
    last_sent_count = -1
    while True:
        try:
            item = progress_queue.get()
            if item is None:
                # Sentinel value received, terminate the thread
                logger.debug("[PROGRESS_SENDER] Received sentinel, terminating.")
                break

            count, message, progress_percent = item
            
            # The final message has a count of float('inf')
            is_final_message = count == float('inf')

            if is_final_message or count > last_sent_count:
                if not is_final_message:
                    last_sent_count = count
                
                logger.debug(f"[PROGRESS_SENDER] Sending progress: count={count}, last_sent={last_sent_count}")
                send_websocket_progress(session_id, message, progress_percent)
            else:
                logger.debug(f"[PROGRESS_SENDER] Skipping stale progress: count={count}, last_sent={last_sent_count}")
            
            progress_queue.task_done()
        except Exception as e:
            logger.error(f"[PROGRESS_SENDER] Error in progress sender thread: {e}")


def send_websocket_progress(session_id: str, message: str, progress: int = None):
    """Send progress update via WebSocket"""
    logger.debug(f"send_websocket_progress called: websocket_client={websocket_client is not None}, session_id={session_id}, message={message}, progress={progress}")

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

            logger.debug(f"Sending data: {update_data}")
            result = websocket_client.send_to_session(session_id, update_data)
            logger.debug(f"Send result: {result}")
            logger.debug(f"Sent WebSocket progress: {message} to session {session_id}")
        except Exception as e:
            logger.debug(f"Failed to send WebSocket progress: {e}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
    else:
        logger.debug(f"Cannot send - websocket_client={websocket_client is not None}, session_id={session_id}")

def report_ai_call_progress(session_id: str, total_expected: int, counter_lock, completed_counter, progress_queue):
    """Puts an AI call progress update on the queue."""
    logger.debug(f"report_ai_call_progress called: session_id={session_id}, total_expected={total_expected}")

    if not session_id or total_expected <= 0 or progress_queue is None:
        return
    
    with counter_lock:
        completed_counter[0] += 1
        current_count = completed_counter[0]
    
    # Calculate progress percentage
    ai_progress = 5 + (current_count / total_expected) * 85
    progress_percent = min(90, int(ai_progress))
    
    message = f"AI call {current_count}/{total_expected} completed"
    
    try:
        # Put the progress update on the queue
        progress_queue.put((current_count, message, progress_percent))
        logger.debug(f"[AI_PROGRESS] Queued progress update: {current_count}/{total_expected}")
    except Exception as e:
        logger.error(f"[AI_PROGRESS] Failed to queue progress update: {e}")

class ContinuationTriggered(Exception):
    """Exception raised when continuation is triggered to exit Lambda immediately."""
    def __init__(self, response_data):
        self.response_data = response_data
        super().__init__("Continuation triggered")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for validation requests and config generation."""
    progress_thread = None
    progress_queue = None
    try:
        # ========== SQS EVENT HANDLING FOR SMART DELEGATION SYSTEM ==========
        # Check if this is an SQS event (from Smart Delegation System)
        if 'Records' in event and event['Records']:
            logger.debug(f"[SQS_HANDLER] Processing {len(event['Records'])} SQS message(s)")

            # Process each SQS record
            responses = []
            for record in event['Records']:
                if record.get('eventSource') == 'aws:sqs':
                    try:
                        # Extract the actual validation request from SQS message body
                        message_body = json.loads(record['body'])
                        logger.debug(f"[SQS_HANDLER] Processing SQS message: {message_body.get('message_type', 'unknown')}")

                        # Call the same lambda_handler recursively with the extracted event
                        response = lambda_handler(message_body, context)
                        responses.append(response)

                    except Exception as sqs_error:
                        logger.error(f"[SQS_HANDLER] Error processing SQS record: {sqs_error}")
                        responses.append({
                            'statusCode': 500,
                            'body': json.dumps({'error': f'SQS processing error: {str(sqs_error)}'})
                        })

            # Return the last response (or aggregate if needed)
            return responses[-1] if responses else {'statusCode': 200, 'body': json.dumps({'message': 'No valid SQS records processed'})}

        # Check for config generation request first
        if event.get('config_generation_request'):
            logger.info("Processing config generation request")
            return handle_config_generation_request(event, context)

        # ========== SMART DELEGATION SYSTEM - TIME MONITORING ==========
        # Check if this is an async delegation request from the smart delegation system
        is_async_request = event.get('async_delegation_request', False)
        session_id = event.get('session_id', 'unknown')
        logger.info(f"[ASYNC_CHECK] Lambda invoked with async_delegation_request={is_async_request}, session_id={session_id}")

        # Time monitoring configuration
        # FOR TESTING: Set safety buffer to 14.8 minutes to force continuation after first batch
        # This ensures that after processing just one batch, remaining time < buffer, triggering continuation
        SAFETY_BUFFER_MS = int(os.environ.get('VALIDATOR_SAFETY_BUFFER_MS', '888000'))  # TEST: 14.8 minutes (888000ms)
        MAX_PROCESSING_TIME_MS = int(os.environ.get('VALIDATOR_MAX_PROCESSING_TIME_MS', '900000'))  # 15 minutes default

        # Track execution start time
        execution_start_time = time.time() * 1000  # milliseconds

        def get_remaining_time_ms():
            """Get remaining execution time in milliseconds."""
            if context:
                return context.get_remaining_time_in_millis()
            else:
                # Fallback calculation for testing
                elapsed_ms = (time.time() * 1000) - execution_start_time
                return MAX_PROCESSING_TIME_MS - elapsed_ms

        def should_continue_processing(next_batch_estimated_time_ms=None):
            """Check if we have enough time to continue processing.

            Args:
                next_batch_estimated_time_ms: Estimated time for next batch in milliseconds.
                                             If None, just checks safety buffer.
            """
            remaining_ms = get_remaining_time_ms()

            if next_batch_estimated_time_ms:
                # Smart check: Will the next batch finish within safety limits?
                required_time = next_batch_estimated_time_ms + SAFETY_BUFFER_MS
                can_continue = remaining_ms > required_time

                if not can_continue:
                    logger.info(f"[TIME_CHECK] Cannot continue: {remaining_ms}ms left, need {required_time}ms ({next_batch_estimated_time_ms}ms batch + {SAFETY_BUFFER_MS}ms buffer)")

                return can_continue
            else:
                # Simple check: Just ensure we have safety buffer
                return remaining_ms > SAFETY_BUFFER_MS

        def save_async_progress(chunks_completed=0, chunks_total=0, rows_processed=0, current_cost=0.0):
            """Save progress to DynamoDB for async processing."""
            if is_async_request and session_id != 'unknown':
                try:
                    # Import here to avoid circular imports
                    import sys
                    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
                    from dynamodb_schemas import update_async_progress

                    # Get run_key from event or derive it
                    run_key = event.get('run_key', f"AsyncValidation_{int(time.time())}")

                    update_async_progress(
                        session_id=session_id,
                        run_key=run_key,
                        chunks_completed=chunks_completed,
                        chunks_total=chunks_total,
                        rows_processed=rows_processed,
                        current_cost=current_cost
                    )
                    logger.debug(f"[ASYNC_PROGRESS] Updated progress: {chunks_completed}/{chunks_total} chunks, {rows_processed} rows, ${current_cost:.2f}")
                except Exception as e:
                    logger.error(f"[ASYNC_PROGRESS] Failed to save progress: {e}")

        def trigger_self_continuation():
            """Trigger self-continuation via direct Lambda invocation for more processing time."""
            # VALIDATION: Only async-delegated validations can use continuations
            if not is_async_request:
                logger.warning(f"[CONTINUATION] Sync mode cannot use continuations - validation will timeout")
                logger.warning(f"[CONTINUATION] Interface should have delegated to async based on preview estimates")
                return False

            try:
                import boto3

                # Use updated event if available (set during batch processing)
                current_event = globals().get('_continuation_event', event)

                # Get deployment environment
                deployment_environment = os.environ.get('DEPLOYMENT_ENVIRONMENT', 'prod')

                # Save complete payload to S3 for continuation
                s3_client = boto3.client('s3')
                s3_bucket = current_event.get('S3_UNIFIED_BUCKET', os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage-dev'))

                # Generate unique payload key
                continuation_count = current_event.get('continuation_count', 0) + 1
                payload_timestamp = int(time.time() * 1000)

                # Get results path from event (should be passed by interface lambda)
                results_path = current_event.get('results_path')
                if not results_path:
                    # Fallback to constructing path from email and config_version
                    domain, email_prefix = get_s3_path_components(current_event)
                    config_version = current_event.get('config_version', 1)
                    results_path = f"results/{domain}/{email_prefix}/{session_id}/v{config_version}_results"
                    logger.warning(f"[S3_PATH] results_path not in event, constructed: {results_path}")

                # Get original payload S3 key - REQUIRED for async continuations
                original_payload_s3_key = current_event.get('complete_payload_s3_key')

                if not original_payload_s3_key:
                    # Async mode MUST have S3 payload key from interface delegation
                    logger.error(f"[CONTINUATION] Cannot trigger async continuation without complete_payload_s3_key")
                    logger.error(f"[CONTINUATION] This indicates the validator was not properly delegated from interface")
                    return False

                logger.info(f"[CONTINUATION] Reusing original payload: {original_payload_s3_key}")

                # IMPORTANT: Track progress by ROWS (not batches) to prevent infinite loops
                # Get current row count from the updated event (set before triggering continuation)
                current_completed_rows = current_event.get('current_completed_rows', 0)

                # Create continuation invocation event - reuse original payload
                continuation_payload = {
                    'message_type': 'ASYNC_VALIDATION_CONTINUATION',
                    'session_id': session_id,
                    'run_key': current_event.get('run_key', f"AsyncValidation_{int(time.time())}"),
                    'async_delegation_request': True,
                    'is_continuation': True,
                    'continuation_count': continuation_count,
                    'deployment_environment': deployment_environment,
                    # Reuse ORIGINAL payload - no need for new S3 file
                    'complete_payload_s3_key': original_payload_s3_key,
                    'S3_UNIFIED_BUCKET': s3_bucket,
                    'VALIDATOR_LAMBDA_NAME': current_event.get('VALIDATOR_LAMBDA_NAME'),
                    # Pass results path and config version
                    'results_path': results_path,
                    'config_version': current_event.get('config_version', 1),
                    'email': current_event.get('email'),
                    # Pass minimal tracking data
                    'last_completed_rows': current_completed_rows,
                    'continuation_chain': current_event.get('continuation_chain', [])
                }

                # Direct Lambda invocation (async)
                lambda_client = boto3.client('lambda')
                validator_lambda_name = current_event.get('VALIDATOR_LAMBDA_NAME') or os.environ.get('VALIDATOR_LAMBDA_NAME', 'perplexity-validator-function')

                response = lambda_client.invoke(
                    FunctionName=validator_lambda_name,
                    InvocationType='Event',  # Async invocation
                    Payload=json.dumps(continuation_payload, default=str)
                )

                logger.info(f"[DIRECT_INVOKE] Triggered continuation #{continuation_count} for session {session_id}, status: {response['StatusCode']}")
                return True

            except Exception as e:
                logger.error(f"[SELF_TRIGGER] Failed to trigger continuation: {e}")
                return False

        def trigger_interface_completion(results_s3_key, delete_payload=True):
            """Trigger interface lambda for job completion via direct invocation and cleanup S3 payload.

            Args:
                results_s3_key: S3 key where final results are stored
                delete_payload: If True, delete the complete_payload_s3_key from S3. Set False for error completions
                               to avoid race conditions with concurrent continuations.
            """
            try:
                import boto3

                # ========== S3 PAYLOAD CLEANUP ==========
                # Clean up the complete payload file after successful validation
                # IMPORTANT: Only delete on FINAL completion (all rows done), not on error/fallback completions
                # This prevents race conditions where one failing continuation deletes the payload while
                # other continuations are still running and need it.
                complete_payload_s3_key = event.get('complete_payload_s3_key')
                if complete_payload_s3_key and delete_payload:
                    try:
                        s3_client = boto3.client('s3')
                        s3_bucket = event.get('S3_UNIFIED_BUCKET', os.environ.get('S3_UNIFIED_BUCKET', 'perplexity-validator-unified'))

                        # Delete the complete payload file
                        s3_client.delete_object(Bucket=s3_bucket, Key=complete_payload_s3_key)
                        logger.info(f"[CLEANUP] Successfully deleted complete payload from S3: {complete_payload_s3_key}")

                    except Exception as cleanup_error:
                        # Don't fail completion if cleanup fails - just log the error
                        logger.warning(f"[CLEANUP] Failed to delete complete payload from S3: {cleanup_error}")
                        logger.warning(f"[CLEANUP] Payload will remain at: {complete_payload_s3_key}")
                elif complete_payload_s3_key and not delete_payload:
                    logger.info(f"[CLEANUP] Skipping payload deletion (error completion): {complete_payload_s3_key}")
                    logger.info(f"[CLEANUP] Payload will remain for potential concurrent continuations to use")
                else:
                    logger.debug(f"[CLEANUP] No complete_payload_s3_key found - no cleanup needed")

                # Get deployment environment from Lambda environment variable
                deployment_environment = os.environ.get('DEPLOYMENT_ENVIRONMENT', 'prod')

                # Get S3 bucket from event or environment
                s3_bucket_for_message = event.get('S3_UNIFIED_BUCKET', os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage'))

                # Create completion payload for direct invocation
                completion_payload = {
                    'async_completion': True,  # Flag for background handler
                    'message_type': 'ASYNC_VALIDATION_COMPLETE',
                    'session_id': session_id,
                    'run_key': event.get('run_key', f"AsyncValidation_{int(time.time())}"),
                    'results_s3_key': results_s3_key,
                    'S3_UNIFIED_BUCKET': s3_bucket_for_message,
                    'completion_timestamp': datetime.now(timezone.utc).isoformat(),
                    'total_duration_seconds': (time.time() * 1000 - execution_start_time) / 1000,
                    'background_processing': True,  # Route to background handler
                    'deployment_environment': deployment_environment
                }

                # Direct Lambda invocation (async)
                lambda_client = boto3.client('lambda')
                interface_lambda_name = os.environ.get('INTERFACE_LAMBDA_NAME', 'perplexity-interface-function')

                logger.info(f"[COMPLETION_TRIGGER] Sending completion via direct invocation to {interface_lambda_name}")
                logger.debug(f"[COMPLETION_TRIGGER] Payload: {json.dumps(completion_payload, indent=2, default=str)}")

                response = lambda_client.invoke(
                    FunctionName=interface_lambda_name,
                    InvocationType='Event',  # Async invocation
                    Payload=json.dumps(completion_payload, default=str)
                )

                logger.info(f"[COMPLETION_TRIGGER] Successfully triggered interface completion for session {session_id}, status: {response['StatusCode']}")
                return True

            except Exception as e:
                logger.error(f"[COMPLETION_TRIGGER] Failed to trigger interface: {e}")
                return False

        logger.debug(f"[TIME_MONITORING] Lambda execution started, safety buffer: {SAFETY_BUFFER_MS}ms, remaining: {get_remaining_time_ms()}ms")

        # Continue with normal validation logic
        # Test CloudWatch logging - with extreme verbosity for debugging
        print("==== LAMBDA FUNCTION STARTED - CONSOLE.LOG PRINT ====")
        pass  # logger.error("==== LAMBDA FUNCTION STARTED - ERROR LEVEL LOG ====")  # Use ERROR level for visibility
        pass  # logger.error(f"Request ID: {context.aws_request_id if context else 'unknown'}")
        pass  # logger.error(f"Function name: {context.function_name if context else 'unknown'}")
        pass  # logger.error(f"Log group: {'/aws/lambda/' + (context.function_name if context else 'perplexity-validator')}")
        pass  # logger.error(f"Log stream: {context.log_stream_name if context else 'unknown'}")
        
        # Debug validation history in event
        pass  # logger.error("==== VALIDATION HISTORY DEBUG ====")
        if 'validation_history' in event:
            vh = event['validation_history']
            pass  # logger.error(f"Validation history present in event with {len(vh)} row keys")
            if vh:
                # Show first key
                first_key = list(vh.keys())[0]
                pass  # logger.error(f"First validation history key: {first_key}")
                pass  # logger.error(f"Fields for first key: {list(vh[first_key].keys())}")
                # Show sample history entry
                if vh[first_key]:
                    sample_field = list(vh[first_key].keys())[0]
                    sample_history = vh[first_key][sample_field]
                    pass  # logger.error(f"Sample history for {sample_field}: {len(sample_history)} entries")
                    if sample_history:
                        pass  # logger.error(f"First entry: {json.dumps(sample_history[0], indent=2)}")
        else:
            pass  # logger.error("NO validation_history in event at all!")
        
        # Check if logging handlers are working
        pass  # logger.error(f"Logger handlers: {logger.handlers}")
        
        # Flush any pending logs
        for handler in logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()
                pass  # logger.error("Flushed log handler")
        
        # Explicitly create log group (testing permissions)
        try:
            import boto3
            logs_client = boto3.client('logs')
            log_group_name = f"/aws/lambda/{context.function_name if context else 'perplexity-validator'}"
            
            # Check if log group exists
            try:
                response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
                log_groups = response.get('logGroups', [])
                log_group_exists = any(lg['logGroupName'] == log_group_name for lg in log_groups)
                
                if log_group_exists:
                    logger.debug(f"Log group exists: {log_group_name}")
                else:
                    # Create log group if it doesn't exist
                    try:
                        logs_client.create_log_group(logGroupName=log_group_name)
                        logger.debug(f"Created log group: {log_group_name}")
                    except Exception as create_e:
                        pass  # logger.error(f"Failed to create log group: {str(create_e)}")
                        logger.warning("This may indicate a permissions issue with the Lambda execution role")
            except Exception as e:
                logger.error(f"Failed to check log group existence: {str(e)}")
        except Exception as logs_e:
            logger.error(f"Error working with CloudWatch logs: {str(logs_e)}")
        
        # ========== SMART DELEGATION SYSTEM - COMPLETE PAYLOAD LOADING ==========
        # Check if this is an async delegation request that needs complete payload loaded from S3
        complete_payload_s3_key = event.get('complete_payload_s3_key')

        # VALIDATION: Async mode MUST have S3 payload key
        if is_async_request and not complete_payload_s3_key:
            logger.error(f"[ASYNC_PAYLOAD] Async delegation request without complete_payload_s3_key")
            logger.error(f"[ASYNC_PAYLOAD] This indicates improper delegation from interface")
            logger.error(f"[ASYNC_PAYLOAD] Event keys: {list(event.keys())}")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid async request: missing complete_payload_s3_key',
                    'session_id': session_id,
                    'message': 'Async validations must be properly delegated from interface with S3 payload'
                })
            }

        if is_async_request and complete_payload_s3_key:
            logger.debug(f"[ASYNC_PAYLOAD] Loading complete sync-compatible payload from S3: {complete_payload_s3_key}")
            try:
                import boto3
                s3_client = boto3.client('s3')
                s3_bucket = event.get('S3_UNIFIED_BUCKET', os.environ.get('S3_UNIFIED_BUCKET', 'perplexity-validator-unified'))

                # Download complete payload from S3
                response = s3_client.get_object(Bucket=s3_bucket, Key=complete_payload_s3_key)
                payload_content = response['Body'].read().decode('utf-8')
                complete_payload = json.loads(payload_content)

                logger.debug(f"[ASYNC_PAYLOAD] Successfully loaded complete payload from S3")
                logger.debug(f"[ASYNC_PAYLOAD] Payload contains {len(complete_payload.get('validation_data', {}).get('rows', []))} rows")
                logger.debug(f"[ASYNC_PAYLOAD] Config has {len(complete_payload.get('config', {}).get('validation_targets', []))} targets")

                # Preserve critical fields from Lambda invocation event before replacing
                preserved_fields = {
                    'results_path': event.get('results_path'),
                    'config_version': event.get('config_version'),
                    'email': event.get('email'),
                    'run_key': event.get('run_key'),
                    'session_id': event.get('session_id'),
                    'VALIDATOR_LAMBDA_NAME': event.get('VALIDATOR_LAMBDA_NAME'),
                    'S3_UNIFIED_BUCKET': event.get('S3_UNIFIED_BUCKET'),
                    'deployment_environment': event.get('deployment_environment'),
                    'is_continuation': event.get('is_continuation'),
                    'continuation_count': event.get('continuation_count'),
                    'last_completed_rows': event.get('last_completed_rows'),
                    'complete_payload_s3_key': event.get('complete_payload_s3_key')  # CRITICAL for continuations
                }

                # Replace the current event with the complete payload for processing
                # This makes the async validator behave exactly like the sync validator
                event = complete_payload

                # Restore preserved fields (only if not None and not already in payload)
                for field, value in preserved_fields.items():
                    if value is not None and field not in event:
                        event[field] = value
                        logger.debug(f"[ASYNC_PAYLOAD] Restored {field} from invocation event")

                # IMPORTANT: Re-set the async flag after replacing event
                # The complete_payload has async_delegation_request set, but we need to update our variable
                is_async_request = event.get('async_delegation_request', False)
                logger.info(f"[ASYNC_PAYLOAD] After loading payload, is_async_request = {is_async_request}")

            except Exception as payload_error:
                logger.error(f"[ASYNC_PAYLOAD] Failed to load complete payload from S3 key {complete_payload_s3_key}: {payload_error}")
                logger.error(f"[ASYNC_PAYLOAD] S3 bucket: {s3_bucket}")
                # Clean up the problematic payload file
                try:
                    import boto3
                    s3_client = boto3.client('s3')
                    s3_client.delete_object(Bucket=s3_bucket, Key=complete_payload_s3_key)
                    logger.warning(f"[CLEANUP] Deleted corrupted payload from S3: {complete_payload_s3_key}")
                except Exception as cleanup_error:
                    logger.warning(f"[CLEANUP] Failed to delete corrupted payload: {cleanup_error}")

                # Return error - cannot proceed without complete payload
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': f'Failed to load validation payload from S3: {str(payload_error)}',
                        'complete_payload_s3_key': complete_payload_s3_key,
                        'bucket': s3_bucket
                    })
                }
        elif is_async_request and not complete_payload_s3_key:
            # Fallback: try legacy config loading for backward compatibility
            logger.warning(f"[ASYNC_PAYLOAD] Async delegation request missing complete_payload_s3_key, trying legacy config loading")
            config_s3_key = event.get('config_s3_key')
            if config_s3_key:
                try:
                    import boto3
                    s3_client = boto3.client('s3')
                    s3_bucket = event.get('S3_UNIFIED_BUCKET', os.environ.get('S3_UNIFIED_BUCKET', 'perplexity-validator-unified'))
                    response = s3_client.get_object(Bucket=s3_bucket, Key=config_s3_key)
                    config_content = response['Body'].read().decode('utf-8')
                    config = json.loads(config_content)
                    # Update event config
                    event['config'] = config
                    logger.debug(f"[ASYNC_PAYLOAD] Legacy config loaded successfully")
                except Exception as e:
                    logger.error(f"[ASYNC_PAYLOAD] Legacy config loading also failed: {e}")
                    return {
                        'statusCode': 500,
                        'body': json.dumps({'error': 'Failed to load validation configuration via legacy method'})
                    }
            else:
                logger.error(f"[ASYNC_PAYLOAD] No complete_payload_s3_key or config_s3_key found")
                return {
                    'statusCode': 500,
                    'body': json.dumps({'error': 'Async delegation request missing both complete_payload_s3_key and config_s3_key'})
                }

        # ========== S3 PAYLOAD CLEANUP HELPER FUNCTION ==========
        def cleanup_s3_payload_if_needed():
            """Clean up S3 payload if this is an async request with a complete payload."""
            complete_payload_s3_key = event.get('complete_payload_s3_key')
            if complete_payload_s3_key and is_async_request:
                try:
                    import boto3
                    s3_client = boto3.client('s3')
                    s3_bucket = event.get('S3_UNIFIED_BUCKET', os.environ.get('S3_UNIFIED_BUCKET', 'perplexity-validator-unified'))
                    s3_client.delete_object(Bucket=s3_bucket, Key=complete_payload_s3_key)
                    logger.debug(f"[CLEANUP] Deleted complete payload from S3: {complete_payload_s3_key}")
                except Exception as cleanup_error:
                    logger.warning(f"[CLEANUP] Failed to delete payload {complete_payload_s3_key}: {cleanup_error}")

        # Initialize validator with config (now loaded from S3 if async, or embedded if sync)
        config = event.get('config', {})
        
        # Log the config for debugging
        pass  # logger.error(f"Config received: {json.dumps({k: v for k, v in config.items() if k != 'validation_targets'})[:500]}...")
        
        # Check if general_notes is present
        if 'general_notes' in config:
            logger.debug(f"General notes included: {config['general_notes'][:200]}...")
        else:
            pass  # logger.error("WARNING: general_notes NOT found in config!")
            
        # Debug check for validation_targets examples
        if 'validation_targets' in config:
            targets_with_examples = 0
            for target in config.get('validation_targets', []):
                if 'examples' in target and target['examples']:
                    targets_with_examples += 1
                    pass  # logger.error(f"Found examples for {target.get('column')}: {target['examples']}")
            pass  # logger.error(f"Found {targets_with_examples} validation targets with examples")
            
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

        # Initialize QC manager if available
        qc_manager = None
        if QC_AVAILABLE:
            try:
                qc_manager = QCIntegrationManager(config, "prompts.yml")
                logger.debug(f"QC Manager initialized: enabled={qc_manager.is_qc_enabled()}")
            except Exception as e:
                logger.error(f"Failed to initialize QC manager: {e}")
                qc_manager = None

        print(f"LAMBDA_HANDLER: Validator created with {len(validator.search_groups)} search groups")
        pass  # logger.error(f"LAMBDA_HANDLER: Validator created with {len(validator.search_groups)} search groups")
        
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
        
        logger.debug(f"API requirements - Perplexity: {needs_perplexity}, Anthropic: {needs_anthropic}")
        
        # Get required API keys
        if needs_anthropic:
            anthropic_api_key = get_anthropic_api_key()
            logger.debug("Retrieved Anthropic API key")
        if needs_perplexity:
            perplexity_api_key = get_perplexity_api_key()
            logger.debug("Retrieved Perplexity API key")
            
        s3_bucket = os.environ['S3_CACHE_BUCKET']
        
        # Extract session_id for progress updates
        session_id = event.get('session_id')

        # Create a queue and a worker thread for progress updates
        progress_queue = queue.Queue()
        progress_thread = None
        if session_id and websocket_client:
            logger.debug(f"Session ID for progress updates: {session_id}")
            progress_thread = threading.Thread(target=progress_sender, args=(progress_queue, session_id))
            progress_thread.start()
            progress_queue.put((0, "Starting validation process...", 5))

        # ========== ASYNC COORDINATION SYSTEM ==========
        # DynamoDB-based locking to ensure only ONE lambda processes this session at a time
        current_lambda_id = context.aws_request_id if context else f"local_{int(time.time() * 1000)}"
        # Note: lock_acquired initialized at function level for finally block scope

        def get_s3_path_components(event_data):
            """Extract domain and email_prefix from event for S3 paths."""
            email = event_data.get('email') or event_data.get('email_address', '')
            if email and '@' in email:
                domain = email.split('@')[-1].lower().strip()
                email_prefix = email.split('@')[0].replace('.', '_').replace('+', '_plus_')[:20]
            else:
                logger.warning(f"[S3_PATH] No valid email in event, using defaults")
                domain = "unknown"
                email_prefix = "unknown"
            return domain, email_prefix

        # SAFETY: Check for excessive continuation count to prevent infinite chains
        if is_async_request:
            MAX_CONTINUATIONS = int(os.environ.get('MAX_CONTINUATIONS', '20'))
            continuation_count = event.get('continuation_count', 0)

            if continuation_count >= MAX_CONTINUATIONS:
                logger.error(f"[SAFETY] Excessive continuation count ({continuation_count}) >= max ({MAX_CONTINUATIONS}) - aborting")
                return {
                    'statusCode': 429,  # Too Many Requests
                    'body': json.dumps({
                        'error': f'Maximum continuation limit reached ({MAX_CONTINUATIONS})',
                        'session_id': session_id,
                        'continuation_count': continuation_count,
                        'message': 'Possible infinite loop detected - validation aborted for safety'
                    })
                }
            elif continuation_count > 0:
                logger.info(f"[CHAIN-{continuation_count:02d}] Continuation #{continuation_count} starting for session {session_id}")
            else:
                logger.info(f"[CHAIN-00] Initial async validation starting for session {session_id}")

        # Update DynamoDB run status to indicate async validation has started
        if is_async_request and session_id != 'unknown':
            try:
                import sys
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
                from dynamodb_schemas import update_run_status

                run_key = event.get('run_key')
                if run_key:
                    # Determine if this is initial start or continuation
                    is_continuation = event.get('is_continuation', False)
                    continuation_count = event.get('continuation_count', 0)

                    if is_continuation:
                        status = f'ASYNC_CONTINUATION_{continuation_count}'
                        verbose_status = f'Async validation continuation #{continuation_count} started'
                    else:
                        status = 'ASYNC_PROCESSING_STARTED'
                        verbose_status = 'Async validation lambda has started processing'

                    # Include continuation tracking in the update
                    additional_data = {
                        'continuation_chain': event.get('continuation_chain', []) + [{
                            'continuation_number': continuation_count,
                            'started_at': datetime.now(timezone.utc).isoformat(),
                            'is_continuation': is_continuation,
                            'last_completed_batch': event.get('last_completed_batch', -1)
                        }]
                    }

                    update_run_status(
                        session_id=session_id,
                        run_key=run_key,
                        status=status,
                        verbose_status=verbose_status,
                        **additional_data
                    )
                    logger.info(f"[ASYNC_START] Updated DynamoDB run status to {status} for session {session_id}")
                else:
                    logger.warning(f"[ASYNC_START] No run_key provided in event for session {session_id}")
            except Exception as e:
                logger.error(f"[ASYNC_START] Failed to update DynamoDB run status: {e}")

        # Process rows
        all_rows = event.get('validation_data', {}).get('rows', [])

        # CRITICAL SAFETY CHECK: Detect if preview data was sent to full validation
        is_continuation = event.get('is_continuation', False)
        if not is_continuation and is_async_request:
            # First validation (not continuation) - check if row count matches preview
            row_count = len(all_rows)
            logger.info(f"[SAFETY_CHECK] First async validation: {row_count} rows in payload, is_async={is_async_request}")

            # If this looks like preview data (3 rows or less) but is being processed as full validation
            if row_count <= 3:
                logger.error(f"[SAFETY_CHECK] ❌ ALERT: Only {row_count} rows in payload for async validation")
                logger.error(f"[SAFETY_CHECK] This may be preview data incorrectly sent to full validation")
                logger.error(f"[SAFETY_CHECK] run_key: {event.get('run_key')}, session: {session_id}")

        # CRITICAL: For continuations, load existing results from S3 to append to them
        validation_results = {}
        existing_token_usage = {}
        existing_enhanced_metrics = {}
        skip_count = 0

        if is_async_request and event.get('is_continuation', False):
            # This is a continuation - need to load existing results from S3
            try:
                import boto3
                s3_client = boto3.client('s3')
                s3_bucket = event.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')

                # Get results path from event or construct it with config_version
                results_path = event.get('results_path')
                if results_path:
                    results_s3_key = f"{results_path}/complete_validation_results.json"
                else:
                    domain, email_prefix = get_s3_path_components(event)
                    config_version = event.get('config_version', 1)
                    results_s3_key = f"results/{domain}/{email_prefix}/{session_id}/v{config_version}_results/complete_validation_results.json"
                    logger.warning(f"[CONTINUATION_LOAD] results_path not in event, constructed path with config_version={config_version}")

                logger.info(f"[CONTINUATION_LOAD] Loading existing results from s3://{s3_bucket}/{results_s3_key}")

                response_s3 = s3_client.get_object(Bucket=s3_bucket, Key=results_s3_key)
                existing_results = json.loads(response_s3['Body'].read().decode('utf-8'))

                # Load existing validation results
                validation_results = existing_results.get('validation_results', {})
                existing_token_usage = existing_results.get('token_usage', {})
                existing_enhanced_metrics = existing_results.get('enhanced_metrics', {})

                # CRITICAL: Skip already-processed rows to avoid duplicate work
                skip_count = len(validation_results)
                logger.info(f"[CONTINUATION_LOAD] Loaded {skip_count} existing row results")
                logger.info(f"[CONTINUATION_LOAD] Will skip first {skip_count} rows and process remaining rows")

            except s3_client.exceptions.NoSuchKey:
                logger.info(f"[CONTINUATION_LOAD] No existing results found - starting fresh")
            except Exception as e:
                logger.warning(f"[CONTINUATION_LOAD] Failed to load existing results: {e}")
                logger.warning(f"[CONTINUATION_LOAD] Starting fresh - this may cause data loss!")

        # Skip already-processed rows in continuations
        rows = all_rows[skip_count:]
        logger.info(f"[ROW_PROCESSING] Total rows in payload: {len(all_rows)}, Skipping: {skip_count}, Processing: {len(rows)}")

        total_cache_hits = 0
        total_cache_misses = 0
        total_multiplex_validations = 0
        total_single_validations = 0
        
        # Thread-safe counter for AI call progress tracking

        ai_call_counter_lock = threading.Lock()
        completed_ai_calls = [0]  # Use list for mutable reference

        
        # Calculate total expected AI calls for progress tracking
        # Interface lambda now sends ALL rows at once, so len(rows) = total dataset size
        validation_targets = [t for t in validator.validation_targets if t.importance.upper() not in ["ID", "IGNORED"]]
        grouped_targets = validator.group_columns_by_search_group(validation_targets)
        search_groups_count = len(grouped_targets)
        total_expected_ai_calls = search_groups_count * len(rows)

        # Add QC calls to progress tracking if QC is enabled
        if qc_manager and qc_manager.is_qc_enabled():
            qc_expected_calls = len(rows)  # One QC call per row
            total_expected_ai_calls += qc_expected_calls
            logger.debug(f"[AI_PROGRESS] Total expected calls: {search_groups_count * len(rows)} validation + {qc_expected_calls} QC = {total_expected_ai_calls}")
        
        # Processing progress setup completed
        # Expected AI calls calculated
        
        # Track batch-level timing and API provider usage
        batch_timing_data = []
        total_batches = 0
        batches_with_claude = 0
        batches_without_claude = 0
        batch_manager = None  # Will be set in process_all_rows

        # Track QC data across all rows
        all_qc_results = {}  # row_key -> field_name -> qc_data
        qc_metrics_summary = {
            'total_rows_processed': 0,
            'total_fields_reviewed': 0,
            'total_fields_modified': 0,
            'total_qc_cost': 0.0,
            'total_qc_cost_actual': 0.0,
            'total_qc_cost_estimated': 0.0,
            'total_qc_time_actual': 0.0,
            'total_qc_time_estimated': 0.0,
            'total_qc_time_savings': 0.0,
            'total_qc_calls': 0,  # Track total QC API calls
            'confidence_lowered_count': 0,  # Track confidence lowered events
            'values_replaced_count': 0,  # Track value replacements
            'qc_models_used': set()
        }
        
        async def process_all_rows(progress_queue):
            nonlocal validation_results, total_cache_hits, total_cache_misses, total_multiplex_validations, total_single_validations, batch_timing_data, total_batches, total_expected_ai_calls, batches_with_claude, batches_without_claude, batch_manager, search_groups_count, all_qc_results, qc_metrics_summary
            
            # Initialize dynamic batch size manager
            # TESTING: Disable enhanced manager as it overrides batch size 3 setting with CSV config
            if False and ENHANCED_BATCH_MANAGER_AVAILABLE:
                try:
                    batch_manager = EnhancedDynamicBatchSizeManager(
                        session_id=session_id,
                        enable_audit_logging=True
                    )
                    logger.debug("🚀 Using EnhancedDynamicBatchSizeManager with CSV configuration")
                except Exception as e:
                    logger.error(f"Failed to initialize enhanced batch manager: {e}")
                    logger.debug("🔄 Falling back to basic DynamicBatchSizeManager")
                    batch_manager = DynamicBatchSizeManager(
                        initial_batch_size=3,   # TEST: Force 3 rows per batch for continuation testing
                        min_batch_size=3,       # TEST: Minimum 3 rows
                        max_batch_size=3,       # TEST: Maximum 3 rows (fixed size)
                        success_increase_factor=1.0,      # TEST: No increase
                        failure_decrease_factor=1.0,      # TEST: No decrease
                        consecutive_successes_for_increase=999,  # TEST: Never increase
                        consecutive_failures_for_decrease=999    # TEST: Never decrease
                    )
            else:
                # Fallback to basic batch manager if enhanced version not available
                logger.debug("🔄 Using basic DynamicBatchSizeManager (enhanced version not available)")
                batch_manager = DynamicBatchSizeManager(
                    initial_batch_size=3,   # TEST: Force 3 rows per batch for continuation testing
                    min_batch_size=3,       # TEST: Minimum 3 rows
                    max_batch_size=3,       # TEST: Maximum 3 rows (fixed size)
                    success_increase_factor=1.0,      # TEST: No increase
                    failure_decrease_factor=1.0,      # TEST: No decrease
                    consecutive_successes_for_increase=999,  # TEST: Never increase
                    consecutive_failures_for_decrease=999    # TEST: Never decrease
                )
            
            # Discover which models will be used across all rows
            all_models = discover_batch_models(rows, validator)

            # Get initial batch size based on discovered models
            current_batch_size = batch_manager.get_batch_size_for_models(all_models)
            total_batches = (len(rows) + current_batch_size - 1) // current_batch_size  # Calculate total number of batches

            logger.info(f"[BATCH_SIZE] Initial batch size: {current_batch_size} rows (models: {sorted(all_models) if all_models else 'none'})")
            logger.info(f"[BATCH_SIZE] Total batches planned: {total_batches} for {len(rows)} rows")
            logger.debug(f"🚀 PER-MODEL BATCH PROCESSING: {len(rows)} rows in {total_batches} batches starting with {current_batch_size} rows each")
            pass  # logger.info(f"🔍 Models that will be used: {sorted(all_models) if all_models else ['default']}")
            
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

                    logger.info(f"[BATCH_SIZE] Batch {batch_index}/{total_batches}: processing {actual_batch_size} rows (size from manager: {current_batch_size})")
                    logger.debug(f"Starting batch {batch_index} with {actual_batch_size} rows")
                    
                    # Log batch manager status every 10 batches
                    if batch_index % 10 == 0:
                        batch_manager.log_status()
                    
                    batch_start_time = time.time()
                    
                    # REMOVED: Batch progress messages (interface lambda handles batch-level progress)
                    # Validation lambda will send row-level detail updates instead
                    
                    row_tasks = []
                    for row_idx, row in enumerate(batch):
                        global_row_idx = start_idx + row_idx
                        task = asyncio.create_task(process_row(session, row, global_row_idx, batch_manager, batch_index, progress_queue))
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
                        for row_idx, row_results, row_models, batch_num in batch_results:
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

                        logger.debug(f"Completed batch {batch_index} in {batch_processing_time:.2f}s")

                        # Store results BEFORE checking for continuation
                        logger.debug(f"Storing results for batch {batch_index}: {len(batch_results)} results")
                        for idx, result, _, batch_num in batch_results:
                            validation_results[idx] = result

                        # ========== ASYNC MODE: Smart Continuation Check ==========
                        # Check after EVERY batch if we should continue (including last batch)
                        # This handles cases where validator receives incomplete data (e.g., preview)
                        if is_async_request:
                            # Calculate average batch time from history
                            all_batch_times = batch_timing_data + event.get('batch_timing_history', [])

                            if all_batch_times:
                                avg_batch_time_seconds = sum(bt['processing_time_seconds'] for bt in all_batch_times) / len(all_batch_times)
                                next_batch_estimated_ms = int(avg_batch_time_seconds * 1000)

                                # Check if we have time for the next batch (or if this is the last batch but work remains)
                                has_more_batches = batch_index < total_batches - 1
                                processed_so_far = len(validation_results)
                                total_rows_in_dataset = len(all_rows)
                                has_unprocessed_rows = processed_so_far < total_rows_in_dataset

                                should_trigger = False
                                if has_more_batches and not should_continue_processing(next_batch_estimated_ms):
                                    # More batches planned, but time is running out
                                    should_trigger = True
                                    logger.info(f"[ASYNC_CONTINUATION] Triggering: more batches planned but time low")
                                elif not has_more_batches and has_unprocessed_rows:
                                    # Last batch done but rows remain (incomplete data received)
                                    should_trigger = True
                                    logger.error(f"[ASYNC_CONTINUATION] Triggering: last batch done but {total_rows_in_dataset - processed_so_far} rows remain!")
                                    logger.error(f"[ASYNC_CONTINUATION] This indicates validator received incomplete data (likely preview)")

                                if should_trigger:
                                    logger.info(f"[ASYNC_CONTINUATION] Need to trigger continuation after batch {batch_index}")
                                    logger.info(f"[ASYNC_CONTINUATION] Avg batch time: {avg_batch_time_seconds:.2f}s, Remaining time insufficient")

                                    # Save progress to DynamoDB
                                    save_async_progress(
                                        chunks_completed=batch_index + 1,
                                        chunks_total=total_batches,
                                        rows_processed=sum(1 for _ in validation_results),
                                        current_cost=0.0  # TODO: Calculate actual cost
                                    )

                                    # Save cumulative results to S3
                                    cumulative_results = {
                                        'validation_results': validation_results,
                                        'batch_timing_data': all_batch_times,
                                        'continuation_metadata': {
                                            'batches_completed': batch_index + 1,
                                            'total_batches': total_batches,
                                            'is_continuation': event.get('is_continuation', False),
                                            'continuation_count': event.get('continuation_count', 0)
                                        }
                                    }

                                    # Save to S3 - use same file for append logic
                                    import boto3
                                    s3_client = boto3.client('s3')
                                    s3_bucket = event.get('S3_UNIFIED_BUCKET', os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage'))

                                    # Get results path from event or construct it with config_version
                                    results_path = event.get('results_path')
                                    if results_path:
                                        results_s3_key = f"{results_path}/complete_validation_results.json"
                                    else:
                                        domain, email_prefix = get_s3_path_components(event)
                                        config_version = event.get('config_version', 1)
                                        results_s3_key = f"results/{domain}/{email_prefix}/{session_id}/v{config_version}_results/complete_validation_results.json"
                                        logger.warning(f"[CONTINUATION_SAVE] results_path not in event, constructed path with config_version={config_version}")

                                    s3_client.put_object(
                                        Bucket=s3_bucket,
                                        Key=results_s3_key,
                                        Body=json.dumps(cumulative_results, default=str),
                                        ContentType='application/json'
                                    )

                                    logger.info(f"[ASYNC_CONTINUATION] Saved results to S3 (for continuation): {results_s3_key}")

                                    # Store batch timing history
                                    continuation_event = event.copy()
                                    continuation_event['batch_timing_history'] = all_batch_times
                                    continuation_event['last_completed_batch'] = batch_index
                                    # IMPORTANT: Track rows (not batches) for progress validation
                                    continuation_event['current_completed_rows'] = len(validation_results)

                                    # Store event for trigger_self_continuation
                                    globals()['_continuation_event'] = continuation_event

                                    # Trigger continuation NOW (time running low)
                                    if trigger_self_continuation():
                                        logger.info(f"[ASYNC_CONTINUATION] Successfully triggered continuation - Lambda will exit now")
                                        # CRITICAL: Raise exception to exit entire Lambda handler immediately
                                        # Return statement only exits async function, not lambda_handler
                                        raise ContinuationTriggered({
                                            'statusCode': 202,
                                            'body': {
                                                'message': 'Continuation triggered - partial results saved to S3',
                                                'session_id': session_id,
                                                'rows_processed': len(validation_results),
                                                'continuation_count': event.get('continuation_count', 0) + 1
                                            }
                                        })
                                    else:
                                        logger.error(f"[ASYNC_CONTINUATION] Failed to trigger continuation, continuing current execution")

                        # Notify batch manager of success with models used
                        batch_manager.on_success(batch_models_used)
                            
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
                                    _, _, row_models, _ = task.result()
                                    failed_batch_models.update(row_models)
                                except Exception as e:
                                    pass  # logger.debug(f"Could not extract models from completed task: {e}")
                        
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
                        
                        logger.debug(f"Storing {len(completed_results)} partial results from failed batch {batch_index}")
                        for idx, result, _, _ in completed_results:
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
                
        
        async def process_row(session, row, row_idx, batch_manager=None, batch_number=None, progress_queue=None):
            """Process a single row with progressive multiplexing."""
            nonlocal total_cache_hits, total_cache_misses, total_multiplex_validations, total_single_validations, total_expected_ai_calls, qc_manager, all_qc_results, qc_metrics_summary, validator, config
            
            # Track which models and API providers were used for this row
            row_models_used = set()
            row_api_providers = set()
            
            row_results = {}
            accumulated_results = {}  # Store results to pass as context to later groups
            
            # Use pre-computed row key if available, otherwise generate it
            if '_row_key' in row:
                row_key = row['_row_key']
                logger.debug(f"Using pre-computed row key: {row_key}")
                # Remove _row_key from row data so it doesn't get processed as a column
                row_data = {k: v for k, v in row.items() if k != '_row_key'}
            else:
                # Fallback: generate row key if not provided (for backward compatibility)
                row_data = row
                row_key = generate_row_key(row_data, validator.primary_key)
                logger.warning(f"No pre-computed row key found, generated: {row_key}")
            
            # Get validation history if provided in the event
            validation_history = {}
            if 'validation_history' in event and event['validation_history'] is not None and row_key in event['validation_history']:
                validation_history = event['validation_history'][row_key]
                pass  # logger.info(f"Found validation history for row key: {row_key}")
                logger.debug(f"History contains data for {len(validation_history)} fields")
                # Log sample history for debugging
                if validation_history:
                    sample_field = list(validation_history.keys())[0]
                    pass  # logger.info(f"Sample history field '{sample_field}': {validation_history[sample_field][:1]}")
            else:
                logger.warning(f"No validation history found for row key: {row_key}")
                if 'validation_history' in event and event['validation_history'] is not None:
                    pass  # logger.warning(f"Available history keys: {list(event['validation_history'].keys())[:5]}")
                else:
                    logger.warning("No validation_history in event at all")
            
            # Get ignored fields and ID fields - add them to results without processing
            ignored_fields = validator.get_ignored_fields()
            id_fields = validator.get_id_fields()
            
            # Process IGNORED fields
            if ignored_fields:
                logger.debug(f"Adding {len(ignored_fields)} IGNORED fields without processing")
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
                pass  # logger.info(f"Including {len(id_fields)} ID fields with original values for preview display")
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
            
            # Group validation targets by search group - exclude ID and IGNORED fields for processing
            validation_targets = [t for t in validator.validation_targets if t.importance.upper() not in ["ID", "IGNORED"]]
            grouped_targets = validator.group_columns_by_search_group(validation_targets)

            # Keep ALL validation targets (including ID fields) for QC context
            all_validation_targets_for_qc = validator.validation_targets
            
            # Sort search groups by number to ensure sequential processing
            sorted_groups = sorted(grouped_targets.keys())
            
            # Process each search group in order
            for group_id in sorted_groups:
                targets = grouped_targets[group_id]
                if not targets:
                    continue
                
                # Processing search group
                
                # Always use multiplex validation regardless of number of fields
                await process_multiplex_group(session, row_data, row_results, targets, accumulated_results, validation_history, False, row_models_used, group_id, row_api_providers)
                total_multiplex_validations += 1
                
                report_ai_call_progress(session_id, total_expected_ai_calls, ai_call_counter_lock, completed_ai_calls, progress_queue)
                
                # Add this group's results to accumulated results for next groups
                # Exclude ID fields from accumulated results since they are context only
                for target in targets:
                    if target.column in row_results and target.importance.upper() != "ID":
                        accumulated_results[target.column] = row_results[target.column]

            # === QC PROCESSING (after all groups complete) ===
            qc_data = {}
            if qc_manager and qc_manager.is_qc_enabled():
                try:
                    logger.debug(f"Starting QC processing for row {row_idx}")

                    # Prepare all group results for QC
                    all_group_results = {}
                    for group_id in sorted_groups:
                        group_targets = grouped_targets[group_id]
                        group_results = []
                        for target in group_targets:
                            if target.column in row_results:
                                # Format validation result for QC processing
                                validation_result = row_results[target.column]
                                formatted_result = {
                                    'column': target.column,
                                    'answer': validation_result.get('value', ''),
                                    'confidence': validation_result.get('confidence_level', ''),
                                    'original_confidence': validation_result.get('original_confidence', ''),
                                    'reasoning': validation_result.get('quote', ''),
                                    'sources': validation_result.get('sources', []),
                                    'explanation': validation_result.get('explanation', ''),
                                    'consistent_with_model_knowledge': validation_result.get('consistent_with_model', '')
                                }
                                group_results.append(formatted_result)
                        if group_results:
                            all_group_results[f"group_{group_id}"] = group_results

                    # Collect group metadata for QC context
                    group_metadata = {}
                    for group_id in sorted_groups:
                        group_targets = grouped_targets[group_id]
                        group_key = f"group_{group_id}"

                        # Get group description, name, and model from validator configuration
                        group_description = ""
                        group_name = ""
                        group_model = ""
                        search_context_level = ""
                        max_web_searches = None

                        # Look up group configuration in search_groups if available
                        if hasattr(validator, 'search_groups') and validator.search_groups:
                            for group_config in validator.search_groups:
                                if group_config.get('group_id') == group_id:
                                    group_description = group_config.get('description', '')
                                    group_name = group_config.get('group_name', '')
                                    break

                        # Resolve model and settings for this group
                        if group_targets:
                            group_model, _ = resolve_search_group_model(group_targets, validator)
                            search_context_level = resolve_search_group_context_size(group_targets, validator)
                            max_web_searches = resolve_search_group_max_web_searches(group_targets, validator)

                        group_metadata[group_key] = {
                            'description': group_description,
                            'group_name': group_name,
                            'model': group_model,
                            'search_context_level': search_context_level,
                            'max_web_searches': max_web_searches,
                            'group_id': group_id
                        }

                    # Process QC for complete row
                    qc_results_by_field, qc_metrics = await qc_manager.process_complete_row_qc(
                        session=session,
                        row=row_data,
                        all_group_results=all_group_results,
                        validation_targets=all_validation_targets_for_qc,  # Use ALL targets including ID fields
                        context=config.get('table_context', ''),
                        general_notes=config.get('general_notes', ''),
                        group_metadata=group_metadata
                    )

                    # Report QC call progress
                    report_ai_call_progress(session_id, total_expected_ai_calls, ai_call_counter_lock, completed_ai_calls, progress_queue)

                    # Merge QC results into row_results
                    if qc_results_by_field:
                        for field_name, qc_field_data in qc_results_by_field.items():
                            if field_name in row_results and qc_field_data.get('qc_applied', False):
                                # PRESERVE the original validation values before QC changes them
                                row_results[field_name]['pre_qc_value'] = row_results[field_name]['value']
                                row_results[field_name]['pre_qc_confidence'] = row_results[field_name].get('confidence_level', row_results[field_name].get('confidence', ''))

                                # Update the field with QC values
                                row_results[field_name]['qc_applied'] = True
                                row_results[field_name]['qc_entry'] = qc_field_data.get('qc_entry', '')
                                row_results[field_name]['qc_confidence'] = qc_field_data.get('qc_confidence', '')  # Fixed: use qc_confidence instead of updated_confidence
                                row_results[field_name]['qc_reasoning'] = qc_field_data.get('qc_reasoning', '')
                                row_results[field_name]['qc_action_taken'] = qc_field_data.get('qc_action_taken', '')
                                row_results[field_name]['qc_citations'] = qc_field_data.get('qc_citations', '')
                                row_results[field_name]['qc_sources'] = qc_field_data.get('qc_sources', [])
                                row_results[field_name]['qc_original_confidence'] = qc_field_data.get('qc_original_confidence', '')
                                row_results[field_name]['qc_updated_confidence'] = qc_field_data.get('qc_updated_confidence', '')

                                # QC results are stored as metadata only - interface lambda will prioritize QC values for display

                    # Store QC results for final response
                    logger.debug(f"[QC_RESULTS_DEBUG] Row {row_idx}: qc_results_by_field = {qc_results_by_field}")
                    if qc_results_by_field:
                        # Store QC results using hash key (for Excel compatibility)
                        all_qc_results[row_key] = qc_results_by_field
                        logger.debug(f"[QC_RESULTS_DEBUG] Stored QC results for row_idx {row_idx} with hash_key {row_key}: {len(qc_results_by_field)} fields")

                        # Debug: Show the actual values being stored
                        for field_name, qc_data in qc_results_by_field.items():
                            if isinstance(qc_data, dict) and qc_data.get('qc_applied', False):
                                original_val = row_data.get(field_name, '')
                                validated_val = row_results.get(field_name, {}).get('value', '')
                                qc_val = qc_data.get('qc_entry', '')
                                logger.debug(f"[QC_VALUES_DEBUG] {field_name}: Original='{original_val}' -> Validated='{validated_val}' -> QC='{qc_val}'")
                    else:
                        logger.debug(f"[QC_RESULTS_DEBUG] No QC results to store for row {row_idx}")

                    # Update QC metrics summary
                    qc_metrics_summary['total_rows_processed'] += 1
                    if qc_metrics:
                        qc_metrics_summary['total_fields_reviewed'] += qc_metrics.get('qc_fields_reviewed', 0)
                        qc_metrics_summary['total_fields_modified'] += qc_metrics.get('qc_fields_modified', 0)
                        qc_metrics_summary['total_qc_cost'] += qc_metrics.get('qc_cost', 0.0)
                        # Add timing and cost aggregation
                        qc_metrics_summary['total_qc_cost_actual'] += qc_metrics.get('qc_cost_actual', 0.0)
                        qc_metrics_summary['total_qc_cost_estimated'] += qc_metrics.get('qc_cost_estimated', 0.0)
                        qc_metrics_summary['total_qc_time_actual'] += qc_metrics.get('qc_time_actual_seconds', 0.0)
                        qc_metrics_summary['total_qc_time_estimated'] += qc_metrics.get('qc_time_estimated_seconds', 0.0)
                        qc_metrics_summary['total_qc_time_savings'] += qc_metrics.get('qc_time_savings_seconds', 0.0)
                        qc_metrics_summary['total_qc_calls'] += qc_metrics.get('qc_calls', 0)  # Add QC API calls
                        qc_metrics_summary['confidence_lowered_count'] += qc_metrics.get('confidence_lowered_count', 0)
                        qc_metrics_summary['values_replaced_count'] += qc_metrics.get('values_replaced_count', 0)
                        if qc_metrics.get('qc_model_used'):
                            qc_metrics_summary['qc_models_used'].add(qc_metrics['qc_model_used'])

                    logger.debug(f"QC processing completed for row {row_idx}: {len(qc_results_by_field)} fields processed")

                except Exception as e:
                    logger.error(f"QC processing failed for row {row_idx}: {str(e)}")
                    # Continue without QC data on error

            # Still determine next check date, but without holistic validation
            next_check, reasons = validator.determine_next_check_date(row_data, row_results)
            row_results['next_check'] = next_check.isoformat() if next_check else None
            row_results['reasons'] = reasons
            
            return row_idx, row_results, row_models_used, batch_number
        
        async def process_multiplex_group(session, row, row_results, targets, previous_results=None, validation_history=None, is_isolated_validation=False, row_models_used=None, group_id=None, row_api_providers=None):
            """Process a group of columns with a single multiplex AI API call using ai_api_client."""
            nonlocal total_cache_hits, total_cache_misses
            
            # Initialize row_models_used if not provided
            if row_models_used is None:
                row_models_used = set()
            
            # Initialize row_api_providers if not provided
            if row_api_providers is None:
                row_api_providers = set()
            
            # First, filter out any ID or IGNORED fields - we don't validate these
            validation_targets = [t for t in targets if t.importance.upper() not in ["ID", "IGNORED"]]
            
            # If there are no fields to validate after filtering, just return
            if not validation_targets:
                logger.debug("No non-ID/IGNORED fields to validate in this group")
                return
            
            # Log clear info about what we're processing
            if len(validation_targets) == 1:
                pass  # logger.info(f"Processing field '{validation_targets[0].column}' using multiplex format")
                if is_isolated_validation:
                    pass  # logger.info(f"This is an ISOLATED validation for field '{validation_targets[0].column}'")
            else:
                logger.debug(f"Processing {len(validation_targets)} fields together using multiplex format")
            
            # Get model configuration
            model, warnings = resolve_search_group_model(validation_targets, validator)
            search_context_size = resolve_search_group_context_size(validation_targets, validator)
            max_web_searches = resolve_search_group_max_web_searches(validation_targets, validator)
            api_provider = determine_api_provider(model)
            
            # Track which model is being used for this row
            row_models_used.add(model)
            row_api_providers.add(api_provider)
            
            # Filter validation history to just the fields we're validating in this group
            filtered_validation_history = None
            if validation_history and not is_isolated_validation:
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
                            pass  # logger.info(f"    First entry: value='{history_entries[0].get('value', 'N/A')}', confidence={history_entries[0].get('confidence_level', 'N/A')}")
                else:
                    logger.info("No relevant validation history found for this group")
            
            # Generate multiplex prompt
            logger.debug(f"Generating multiplex prompt for {len(validation_targets)} field(s) with context from previous groups")
            logger.debug(f"Using resolved model: {model}")
            logger.debug(f"Using resolved search context size: {search_context_size}")
            logger.debug(f"Using resolved max web searches: {max_web_searches}")
            
            prompt = validator.generate_multiplex_prompt(row, validation_targets, previous_results, filtered_validation_history)
            
            # Set up shared result variable for wrapper functions
            shared_client_result = None
            
            # Call ai_api_client with retry logic and provider-specific handling
            start_time = time.time()
            
            logger.debug(f"Using ai_client for {api_provider} API with model: {model}")
            
            try:
                # For ALL models, use unified structured API call
                logger.debug(f"Using unified structured API for {api_provider} with search_context_size: {search_context_size}")
                
                # Create schema for structured output
                schema = get_response_format_schema(is_multiplex=True)
                
                # Wrap the array schema in an object for tool calling (needed for Anthropic)
                tool_schema = {
                    "type": "object",
                    "properties": {
                        "validation_results": schema['json_schema']['schema']
                    },
                    "required": ["validation_results"]
                }
                
                # Prepare field names and debug info for reuse
                field_names = [t.column for t in validation_targets]
                group_str = str(group_id) if group_id is not None else "unknown"
                
                # Get the search group name for better debug identification
                group_name = None
                if group_id is not None and hasattr(validator, 'search_groups') and validator.search_groups:
                    for group_def in validator.search_groups:
                        if isinstance(group_def, dict) and group_def.get('group_id') == group_id:
                            group_name = group_def.get('group_name')
                            break
                
                # Call ai_client with unified approach - format conversion handled internally
                async def call_unified_wrapper():
                    nonlocal shared_client_result
                    # Create descriptive debug name including group name and field info
                    if group_name:
                        # Use group name if available (e.g. "validation_Product_Identification_fields_3")
                        safe_group_name = group_name.replace(' ', '_').replace('-', '_')[:20]
                        debug_name = f"validation_{safe_group_name}_fields_{len(field_names)}"
                        if len(field_names) <= 3:
                            # Include field names if not too many
                            safe_fields = [field.replace(' ', '_')[:15] for field in field_names]
                            debug_name = f"validation_{safe_group_name}_{'-'.join(safe_fields)}"
                    else:
                        # Fallback to group ID if no name available
                        debug_name = f"validation_group_{group_str}_fields_{len(field_names)}"
                        if len(field_names) <= 3:
                            safe_fields = [field.replace(' ', '_')[:15] for field in field_names]
                            debug_name = f"validation_group_{group_str}_{'-'.join(safe_fields)}"
                    
                    shared_client_result = await ai_client.call_structured_api(
                        prompt=prompt,
                        model=model, 
                        schema=tool_schema,
                        tool_name="validate_data",
                        use_cache=True,
                        max_web_searches=max_web_searches,
                        search_context_size=search_context_size,
                        debug_name=debug_name
                    )
                    # Response is now unified Perplexity format from ai_client
                    return shared_client_result['response']
                
                api_response = await retry_api_call_with_backoff(
                    call_unified_wrapper,
                    max_retries=5,  # 6 total attempts with specific delays
                    custom_delays=[1, 5, 10, 20, 30, 60],  # 1s, 5s, 10s, 20s, 30s, 60s
                    batch_manager=batch_manager,
                    model=model
                )
                
                # Enhanced data is consistent across all providers now
                token_usage = shared_client_result.get('token_usage', {})
                enhanced_data = shared_client_result.get('enhanced_data', {})
                is_cached = shared_client_result.get('is_cached', False)
                citations = shared_client_result.get('citations', [])
                
                processing_time = time.time() - start_time
                
                # Update cache counters based on ai_client result
                if is_cached:
                    total_cache_hits += 1
                    logger.debug(f"AI client cache hit for model: {model}")
                else:
                    total_cache_misses += 1
                    logger.info(f"AI client cache miss, made fresh API call for model: {model}")
                
            except Exception as e:
                logger.error(f"AI client call failed: {str(e)}")
                raise  # Re-raise the exception to be handled by caller
            
            # Store the raw API response for this prompt in row_results
            response_id = f"response_{len(row_results.get('_raw_responses', {})) + 1}"
            if '_raw_responses' not in row_results:
                row_results['_raw_responses'] = {}
            
            row_results['_raw_responses'][response_id] = {
                'prompt': prompt,
                'response': api_response,
                'is_cached': is_cached,
                'fields': [t.column for t in validation_targets],  # Use validation_targets, not targets
                'model': model,
                'token_usage': token_usage,
                'processing_time': processing_time,
                'citations': citations,
                'enhanced_data': enhanced_data  # Always available from ai_client
            }
            
            # Parse the API response (now normalized to Perplexity format)
            parsed_results = validator.parse_multiplex_result(api_response, row)
            
            # CRITICAL CACHE VALIDATION LOGIC: Check that response contains all required columns
            # [FIX] Normalize expected columns to match normalized parsing in schema_validator_simplified.py
            expected_columns = [unicodedata.normalize('NFC', t.column).strip() for t in validation_targets]  # Use validation_targets, not targets
            actual_columns = list(parsed_results.keys())

            logger.debug(f"🔍 RESPONSE ANALYSIS:")
            logger.info(f"Expected columns: {expected_columns}")
            logger.info(f"Parsed columns: {actual_columns}")
            logger.debug(f"Expected count: {len(expected_columns)}, Actual count: {len(actual_columns)}")

            # [DEBUG] Log detailed column comparison for debugging cache mismatches
            for i, (exp, act) in enumerate(zip(expected_columns, actual_columns)):
                logger.debug(f"[COLUMN_COMPARE] {i}: expected='{exp}' (repr: {repr(exp)}) vs actual='{act}' (repr: {repr(act)}) match={exp == act}")

            # Check for exact missing columns first
            exact_missing_columns = set(expected_columns) - set(actual_columns)
            
            # If we have missing columns, try flexible column matching
            column_corrections = {}
            flexible_missing_columns = set()
            
            if exact_missing_columns:
                # Attempt flexible column matching for missing columns
                if len(actual_columns) == len(expected_columns):
                    logger.debug(f"🔄 COLUMN COUNT MATCHES: Attempting flexible column matching for similar names")
                    column_mappings = find_similar_columns(expected_columns, actual_columns, similarity_threshold=0.8)
                    
                    for actual_col, expected_col in column_mappings.items():
                        if expected_col in exact_missing_columns and actual_col != expected_col:
                            column_corrections[actual_col] = expected_col
                            logger.warning(f"⚠️ COLUMN NAME CORRECTION: '{actual_col}' -> '{expected_col}' (similarity matching)")
                    
                    # Update parsed_results with corrected column names
                    for actual_col, expected_col in column_corrections.items():
                        parsed_results[expected_col] = parsed_results.pop(actual_col)
                    
                    # Recalculate missing columns after corrections
                    updated_actual_columns = list(parsed_results.keys())
                    flexible_missing_columns = set(expected_columns) - set(updated_actual_columns)
                    
                    if not flexible_missing_columns:
                        logger.debug(f"✅ COLUMN MATCHING SUCCESS: All columns matched after similarity corrections")
                else:
                    flexible_missing_columns = exact_missing_columns
            
            # Check for missing columns after flexible matching attempt
            missing_columns = flexible_missing_columns
            if missing_columns:
                if is_cached:
                    logger.error(f"❌ MISSING COLUMNS IN CACHED RESPONSE: {list(missing_columns)}")
                    logger.error(f"🔄 CACHE REJECTED: Making fresh API call due to incomplete cached response")
                    
                    # Adjust cache counters - this is actually a cache miss
                    total_cache_misses += 1
                    total_cache_hits -= 1
                    
                    # Make fresh API call with cache disabled using unified approach
                    logger.info(f"Making fresh unified API call for {api_provider} with cache disabled")
                    
                    # Use the same unified approach for fresh calls with group name
                    if group_name:
                        safe_group_name = group_name.replace(' ', '_').replace('-', '_')[:20]
                        fresh_debug_name = f"validation_fresh_{safe_group_name}_fields_{len(field_names)}"
                        if len(field_names) <= 3:
                            safe_fields = [field.replace(' ', '_')[:15] for field in field_names]
                            fresh_debug_name = f"validation_fresh_{safe_group_name}_{'-'.join(safe_fields)}"
                    else:
                        fresh_debug_name = f"validation_fresh_group_{group_str}_fields_{len(field_names)}"
                        if len(field_names) <= 3:
                            safe_fields = [field.replace(' ', '_')[:15] for field in field_names]
                            fresh_debug_name = f"validation_fresh_group_{group_str}_{'-'.join(safe_fields)}"
                    
                    shared_client_result = await ai_client.call_structured_api(
                        prompt=prompt,
                        model=model, 
                        schema=tool_schema,
                        tool_name="validate_data",
                        use_cache=False,  # Disable cache for fresh call
                        max_web_searches=max_web_searches,
                        search_context_size=search_context_size,
                        debug_name=fresh_debug_name
                    )
                    
                    # Response is already in unified Perplexity format from ai_client
                    api_response = shared_client_result['response']
                    token_usage = shared_client_result.get('token_usage', {})
                    enhanced_data = shared_client_result.get('enhanced_data', {})
                    is_cached = False  # This is now a fresh call
                    citations = shared_client_result.get('citations', [])
                    
                    # Recalculate processing time for fresh call
                    processing_time = time.time() - start_time
                    
                    # Re-parse the fresh API response (now normalized to Perplexity format)
                    parsed_results = validator.parse_multiplex_result(api_response, row)
                    fresh_actual_columns = list(parsed_results.keys())
                    
                    # Check again for missing columns in fresh response with flexible matching
                    exact_missing_fresh = set(expected_columns) - set(fresh_actual_columns)
                    
                    if exact_missing_fresh:
                        # Try flexible column matching for fresh response as well
                        if len(fresh_actual_columns) == len(expected_columns):
                            logger.info(f"🔄 FRESH RESPONSE: Attempting flexible column matching")
                            fresh_column_mappings = find_similar_columns(expected_columns, fresh_actual_columns, similarity_threshold=0.8)
                            
                            fresh_column_corrections = {}
                            for actual_col, expected_col in fresh_column_mappings.items():
                                if expected_col in exact_missing_fresh and actual_col != expected_col:
                                    fresh_column_corrections[actual_col] = expected_col
                                    logger.warning(f"⚠️ FRESH RESPONSE COLUMN CORRECTION: '{actual_col}' -> '{expected_col}' (similarity matching)")
                            
                            # Update parsed_results with corrected column names
                            for actual_col, expected_col in fresh_column_corrections.items():
                                parsed_results[expected_col] = parsed_results.pop(actual_col)
                            
                            # Recalculate missing columns after corrections
                            updated_fresh_columns = list(parsed_results.keys())
                            missing_columns = set(expected_columns) - set(updated_fresh_columns)
                        else:
                            missing_columns = exact_missing_fresh
                    else:
                        missing_columns = set()
                    
                    if missing_columns:
                        logger.error(f"❌ MISSING COLUMNS EVEN IN FRESH API RESPONSE AFTER FLEXIBLE MATCHING: {list(missing_columns)}")
                        logger.error(f"This indicates a serious issue with the AI model or prompt generation")
                        raise ValueError(f"Fresh API response still missing required columns: {missing_columns}")
                    
                    logger.info(f"✅ FRESH API CALL SUCCESS: All {len(expected_columns)} columns now present")
                    
                    # Update the raw response storage with the fresh response
                    row_results['_raw_responses'][response_id].update({
                        'response': api_response,
                        'is_cached': is_cached,
                        'token_usage': token_usage,
                        'processing_time': processing_time,  # Updated timing
                        'enhanced_data': enhanced_data,
                        'citations': citations
                    })
                    
                else:
                    # This was already a fresh API call - try flexible matching one more time
                    if len(actual_columns) == len(expected_columns):
                        logger.info(f"🔄 FRESH API CALL: Attempting flexible column matching for remaining missing columns")
                        column_mappings = find_similar_columns(expected_columns, actual_columns, similarity_threshold=0.8)
                        
                        final_column_corrections = {}
                        for actual_col, expected_col in column_mappings.items():
                            if expected_col in missing_columns and actual_col != expected_col:
                                final_column_corrections[actual_col] = expected_col
                                logger.warning(f"⚠️ FINAL COLUMN CORRECTION: '{actual_col}' -> '{expected_col}' (similarity matching)")
                        
                        # Update parsed_results with corrected column names
                        for actual_col, expected_col in final_column_corrections.items():
                            parsed_results[expected_col] = parsed_results.pop(actual_col)
                        
                        # Recalculate missing columns after final corrections
                        final_actual_columns = list(parsed_results.keys())
                        remaining_missing_columns = set(expected_columns) - set(final_actual_columns)
                        
                        if remaining_missing_columns:
                            logger.error(f"❌ MISSING COLUMNS IN FRESH API RESPONSE AFTER FLEXIBLE MATCHING: {list(remaining_missing_columns)}")
                            logger.error(f"This indicates a serious issue with the AI model or prompt generation")
                            raise ValueError(f"Fresh API response missing required columns: {remaining_missing_columns}")
                        else:
                            logger.info(f"✅ FINAL FLEXIBLE MATCHING SUCCESS: All columns matched after similarity corrections")
                    else:
                        logger.error(f"❌ MISSING COLUMNS IN FRESH API RESPONSE: {list(missing_columns)}")
                        logger.error(f"Column count mismatch: expected {len(expected_columns)}, got {len(actual_columns)}")
                        logger.error(f"This indicates a serious issue with the AI model or prompt generation")
                        raise ValueError(f"Fresh API response missing required columns: {missing_columns}")
            
            # Check for unexpected columns (warning only) - use current parsed_results keys
            current_actual_columns = list(parsed_results.keys())
            unexpected_columns = set(current_actual_columns) - set(expected_columns)
            if unexpected_columns:
                logger.warning(f"⚠️ UNEXPECTED COLUMNS IN API RESPONSE: {list(unexpected_columns)}")
                logger.warning(f"These columns were found but not expected")
            
            # Log column corrections summary if any were made
            if column_corrections:
                logger.debug(f"📋 COLUMN CORRECTIONS SUMMARY:")
                for actual_col, expected_col in column_corrections.items():
                    logger.info(f"  • '{actual_col}' -> '{expected_col}'")
            
            # Process results - create proper result structure for each validation target column
            processed_count = 0
            for target in validation_targets:  # Use validation_targets, not targets
                if target.column in parsed_results:
                    parsed_result = parsed_results[target.column]
                    
                    # Create result structure matching expected format
                    # Tuple structure: (value, confidence, sources, confidence_level, reasoning, main_source, original_confidence, explanation, consistent_with_model_knowledge)
                    row_results[target.column] = {
                        'value': parsed_result[0],
                        'confidence': parsed_result[1],  # String confidence
                        'sources': parsed_result[2],
                        'confidence_level': parsed_result[3],
                        'reasoning': parsed_result[4],
                        'main_source': parsed_result[5],
                        'original_confidence': parsed_result[6] if len(parsed_result) > 6 else None,
                        'explanation': parsed_result[7] if len(parsed_result) > 7 else '',
                        'response_id': response_id,
                        'model': model
                    }
                    
                    # Add optional fields
                    if len(parsed_result) > 8:
                        row_results[target.column]['consistent_with_model_knowledge'] = parsed_result[8]
                    
                    # Add citations from API response
                    row_results[target.column]['citations'] = citations
                    
                    # Keep quote for backward compatibility
                    row_results[target.column]['quote'] = parsed_result[4]
                    
                    processed_count += 1
                    
                else:
                    logger.error(f"❌ COLUMN RESULT MISSING: {target.column} was expected but not found in parsed results")
            
            logger.info(f"✅ Processed {processed_count}/{len(validation_targets)} columns successfully")
            
            # Function modifies row_results and row_models_used in place - no return needed  
         # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process_all_rows(progress_queue))
            
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
        
        # Create row to batch mapping from batch_timing_data collected during processing
        # Due to dynamic batch sizing, we need to reconstruct which rows were in each batch
        row_to_batch_mapping = {}
        current_row = 0
        for timing_info in batch_timing_data:
            batch_number = timing_info['batch_number']
            batch_size = timing_info['batch_size']
            # Map the next batch_size rows to this batch
            for i in range(batch_size):
                if current_row < len(validation_results):
                    row_to_batch_mapping[current_row] = batch_number
                    current_row += 1
                else:
                    break
        
        # Extract enhanced data from all responses
        pass  # logger.info(f"[AGG_DEBUG] Starting enhanced data extraction from {len(validation_results)} rows")
        pass  # logger.info(f"[AGG_DEBUG] Row to batch mapping: {dict(list(row_to_batch_mapping.items())[:5])}...")  # Show first 5 for debug
        
        for row_idx, row_result in validation_results.items():
            if '_raw_responses' in row_result:
                pass  # logger.info(f"[AGG_DEBUG] Row {row_idx}: Found {len(row_result['_raw_responses'])} raw responses")
                batch_number = row_to_batch_mapping.get(row_idx, row_idx // 10)  # Fallback to rough estimate
                
                search_group_counter = 0  # Track which search group (AI call sequence) in this row
                for response_id, response_data in row_result['_raw_responses'].items():
                    enhanced_data = response_data.get('enhanced_data')
                    
                    # Debug enhanced data structure
                    pass  # logger.info(f"[AGG_DEBUG] Row {row_idx}, Response {response_id}: enhanced_data type: {type(enhanced_data)}")
                    if enhanced_data:
                        if isinstance(enhanced_data, dict):
                            costs = enhanced_data.get('costs', {})
                            pass  # logger.info(f"[AGG_DEBUG] Enhanced data costs: actual=${costs.get('actual', {}).get('total_cost', 0):.6f}, estimated=${costs.get('estimated', {}).get('total_cost', 0):.6f}")
                        else:
                            logger.warning(f"[AGG_DEBUG] Enhanced data is not a dict: {enhanced_data}")
                    else:
                        logger.warning(f"[AGG_DEBUG] No enhanced_data found for response {response_id}")
                    
                    if enhanced_data:
                        # Debug: Check what enhanced data contains
                        costs = enhanced_data.get('costs', {})
                        actual_cost = costs.get('actual', {}).get('total_cost', 0.0)
                        estimated_cost = costs.get('estimated', {}).get('total_cost', 0.0)
                        provider_metrics = enhanced_data.get('provider_metrics', {})
                        
                        pass  # logger.info(f"[AGG_DEBUG] Row {row_idx}, Response {response_id}: "
                              # f"Actual cost: ${actual_cost:.6f}, Estimated cost: ${estimated_cost:.6f}, "
                              # f"Provider metrics: {list(provider_metrics.keys())}")
                        
                        # Add row, batch, and search group context for tracking
                        enhanced_data_with_context = enhanced_data.copy()
                        enhanced_data_with_context['row_idx'] = row_idx
                        enhanced_data_with_context['batch_number'] = batch_number
                        enhanced_data_with_context['search_group'] = search_group_counter  # nth AI call in this row
                        enhanced_data_with_context['response_id'] = response_id
                        all_enhanced_call_data.append(enhanced_data_with_context)
                        
                        search_group_counter += 1
                    else:
                        logger.warning(f"[AGG_DEBUG] Row {row_idx}, Response {response_id}: No enhanced_data found")
            else:
                logger.warning(f"[AGG_DEBUG] Row {row_idx}: No _raw_responses found")
        
        # Initialize batch processing times before any potential exceptions
        batch_processing_times_calculated = {}  # batch_number -> max_processing_time_in_that_batch

        # Use ai_client aggregation methods instead of manual calculations
        if all_enhanced_call_data:
            pass  # logger.info(f"[AGG_DEBUG] Collected {len(all_enhanced_call_data)} enhanced call data items for aggregation")

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

            pass  # logger.info(f"[AGG_DEBUG] About to aggregate: {total_calls_to_aggregate} calls, "
                  # f"Providers: {list(providers_found)}, "
                  # f"Sample costs: {costs_preview[:5]}...")

            try:
                # Use ai_client.aggregate_provider_metrics() to get comprehensive aggregated data
                aggregated_metrics = ai_client.aggregate_provider_metrics(all_enhanced_call_data)

                # ========== COST_DEBUG: Raw AI Client Aggregated Metrics ==========
                logger.debug(f"[COST_DEBUG] RAW aggregated_metrics from ai_client: {aggregated_metrics}")
                if aggregated_metrics and 'totals' in aggregated_metrics:
                    totals = aggregated_metrics['totals']
                    logger.debug(f"[COST_DEBUG] RAW totals: actual=${totals.get('total_cost_actual', 0):.6f}, estimated=${totals.get('total_cost_estimated', 0):.6f}")
                    providers = aggregated_metrics.get('providers', {})
                    for provider, data in providers.items():
                        logger.debug(f"[COST_DEBUG] RAW provider {provider}: calls={data.get('calls', 0)}, tokens={data.get('tokens', 0)}, actual=${data.get('cost_actual', 0):.6f}, estimated=${data.get('cost_estimated', 0):.6f}")

                # Log the results of the final aggregation for debugging
                if aggregated_metrics and 'totals' in aggregated_metrics:
                    totals = aggregated_metrics['totals']
                    pass  # logger.info(f"[AGGREGATION_DEBUG] Final Aggregated Times - Estimated (no cache): {totals.get('total_estimated_processing_time', 'N/A'):.3f}s, Actual (with cache): {totals.get('total_actual_processing_time', 'N/A'):.3f}s")
                    pass  # logger.info(f"[AGGREGATION_DEBUG] Final Aggregated Costs - Estimated (no cache): ${totals.get('total_cost_estimated', 'N/A'):.6f}, Actual (with cache): ${totals.get('total_cost_actual', 'N/A'):.6f}")
                
                # Debug: Check what came out of aggregation
                providers = aggregated_metrics.get('providers', {})
                totals = aggregated_metrics.get('totals', {})
                pass  # logger.info(f"[AGG_DEBUG] Aggregation complete - Providers: {list(providers.keys())}, "
                      # f"Total calls: {totals.get('total_calls', 0)}, "
                      # f"Total actual cost: ${totals.get('total_cost_actual', 0.0):.6f}, "
                      # f"Total estimated cost: ${totals.get('total_cost_estimated', 0.0):.6f}")
                
                # Calculate cost and timing estimates for both preview and validation modes
                is_preview = event.get('is_preview', False)
                
                # For preview: calculate estimates for full table
                # For validation: calculate estimates for actual processed rows 
                if is_preview:
                    total_rows_in_table = event.get('total_rows', len(validation_results))
                    preview_rows_processed = len(validation_results)
                else:
                    # For validation mode, we're processing the actual rows
                    total_rows_in_table = len(validation_results)
                    preview_rows_processed = len(validation_results)

                # Get target batch size from batch manager
                if batch_manager:
                    # For enhanced batch manager, get a representative batch size
                    if hasattr(batch_manager, 'model_batch_sizes') and batch_manager.model_batch_sizes:
                        # Use average of current model batch sizes
                        target_batch_size = int(sum(batch_manager.model_batch_sizes.values()) / len(batch_manager.model_batch_sizes))
                        pass  # logger.info(f"[BATCH_SIZE_DEBUG] Using average batch size from registered models: {target_batch_size}")
                    else:
                        # No models registered yet, use default approach
                        target_batch_size = batch_manager.get_batch_size_for_models(set())
                        pass  # logger.info(f"[BATCH_SIZE_DEBUG] Using default batch size from enhanced manager: {target_batch_size}")
                else:
                    target_batch_size = 50
                    pass  # logger.info(f"[BATCH_SIZE_DEBUG] No batch manager available, using fallback: {target_batch_size}")
                
                pass  # logger.info(f"[BATCH_SIZE_DEBUG] target_batch_size: {target_batch_size}, mode: {'preview' if is_preview else 'validation'}")
                
                # ========== COST_DEBUG: Full Validation Estimates Calculation ==========
                logger.debug(f"[COST_DEBUG] Calculating full validation estimates with:")
                logger.debug(f"[COST_DEBUG] - total_rows_in_table: {total_rows_in_table}")
                logger.debug(f"[COST_DEBUG] - preview_rows_processed: {preview_rows_processed}")
                logger.debug(f"[COST_DEBUG] - target_batch_size: {target_batch_size}")

                full_validation_estimates = calculate_full_validation_estimates_with_batch_timing(
                    aggregated_metrics=aggregated_metrics,
                    all_enhanced_call_data=all_enhanced_call_data,
                    total_rows_in_table=total_rows_in_table,
                    preview_rows_processed=preview_rows_processed,
                    batch_processing_times=batch_processing_times_calculated,
                    qc_manager=qc_manager,  # Pass QC manager for QC time inclusion
                    target_full_validation_batch_size=target_batch_size
                )

                # ========== COST_DEBUG: Full Validation Estimates Result ==========
                logger.debug(f"[COST_DEBUG] full_validation_estimates result: {full_validation_estimates}")

                if 'error' in full_validation_estimates:
                    logger.error(f"[VALIDATOR_SIDE_ERROR] Estimates calculation failed: {full_validation_estimates['error']}")
                    full_validation_estimates = None
                else:
                    mode_desc = "full validation estimates" if is_preview else "actual validation metrics"
                    logger.debug(f"Generated {mode_desc}: {full_validation_estimates.get('total_estimates', 'N/A')}")
                    pass  # logger.info(f"[VALIDATOR_SIDE_DEBUG] Calculated estimates object: {json.dumps(full_validation_estimates, indent=2)}")
                    
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
            # Cost tracking now handled by enhanced_data aggregation
            'by_provider': {
                'perplexity': {
                    'prompt_tokens': 0,
                    'completion_tokens': 0,
                    'total_tokens': 0,
                    'calls': 0
                },
                'anthropic': {
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'cache_creation_tokens': 0,
                    'cache_read_tokens': 0,
                    'total_tokens': 0,
                    'calls': 0
                }
            },
            'by_model': {}
        }
        
        # First pass: collect all responses and calculate token usage
        # For timing, we need to calculate the maximum processing time per batch (parallel processing)
        # Use the actual row-to-batch mapping we created above
        # Note: batch_processing_times_calculated is already initialized above
        
        for row_idx, row_result in validation_results.items():
            if '_raw_responses' in row_result:
                # Use actual batch mapping instead of hardcoded calculation
                batch_number = row_to_batch_mapping.get(row_idx, row_idx // 10)  # Fallback to rough estimate
                if batch_number not in batch_processing_times_calculated:
                    batch_processing_times_calculated[batch_number] = 0.0
                
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
                batch_processing_times_calculated[batch_number] = max(batch_processing_times_calculated[batch_number], row_processing_time)
                pass  # logger.info(f"Row {row_idx} (batch {batch_number}) total time: {row_processing_time:.3f}s, batch max now: {batch_processing_times_calculated[batch_number]:.3f}s")
        
        # Calculate total processing time as sum of all batch times (since batches are processed sequentially)
        total_processing_time = sum(batch_processing_times_calculated.values())
        logger.debug(f"Calculated parallel processing time: {total_processing_time:.3f}s across {len(batch_processing_times_calculated)} batches")
        
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
                                    'calls': 0
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
                            # REMOVED: Manual cost aggregation - handled by enhanced_data aggregation
                            
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
        
        # Add total_cost back to token_usage for backward compatibility with background handler
        if aggregated_metrics and aggregated_metrics.get('totals'):
            total_cost_actual = aggregated_metrics['totals'].get('total_cost_actual', 0.0)
            total_token_usage['total_cost'] = total_cost_actual
            
            # Add provider-specific costs for compatibility
            providers = aggregated_metrics.get('providers', {})
            for provider_name, provider_data in providers.items():
                if provider_name in total_token_usage['by_provider']:
                    total_token_usage['by_provider'][provider_name]['total_cost'] = provider_data.get('cost_actual', 0.0)
            
            pass  # logger.info(f"[COST_COMPATIBILITY] Added total_cost=${total_cost_actual:.6f} to token_usage for background handler compatibility")
        else:
            total_token_usage['total_cost'] = 0.0
            # Add zero costs to providers for safety
            for provider_name in total_token_usage['by_provider']:
                total_token_usage['by_provider'][provider_name]['total_cost'] = 0.0
            logger.warning(f"[COST_COMPATIBILITY] No aggregated_metrics available - setting total_cost=0.0 in token_usage")
        
        # Log token usage summary (cost logging now handled by enhanced_data aggregation)
        logger.debug(f"Token Usage Summary: {total_token_usage['total_tokens']} total tokens, ${total_token_usage['total_cost']:.6f} total cost")
        logger.debug(f"API Calls: {total_token_usage['api_calls']} new, {total_token_usage['cached_calls']} cached")
        logger.info(f"Total Processing Time: {total_processing_time:.3f}s")
        
        # Log by provider
        perplexity_usage = total_token_usage['by_provider']['perplexity']
        anthropic_usage = total_token_usage['by_provider']['anthropic']
        
        if perplexity_usage['calls'] > 0:
            logger.debug(f"Perplexity API: {perplexity_usage['prompt_tokens']} prompt + {perplexity_usage['completion_tokens']} completion = {perplexity_usage['total_tokens']} total tokens across {perplexity_usage['calls']} calls, ${perplexity_usage.get('total_cost', 0.0):.6f} cost")
        
        if anthropic_usage['calls'] > 0:
            logger.debug(f"Anthropic API: {anthropic_usage['input_tokens']} input + {anthropic_usage['output_tokens']} output + {anthropic_usage['cache_creation_tokens']} cache_creation + {anthropic_usage['cache_read_tokens']} cache_read = {anthropic_usage['total_tokens']} total tokens across {anthropic_usage['calls']} calls, ${anthropic_usage.get('total_cost', 0.0):.6f} cost")
        
        # Log by model
        for model, model_usage in total_token_usage['by_model'].items():
            api_provider = model_usage.get('api_provider', 'unknown')
            logger.debug(f"Model {model} ({api_provider}): {model_usage['total_tokens']} tokens across {model_usage['calls']} calls")
        
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
        logger.debug(f"Response size without raw responses: approximately {response_size_kb:.2f} KB")
        
        # Estimate size with raw responses
        raw_responses_json = json.dumps(all_raw_responses)
        raw_size_kb = len(raw_responses_json) / 1024
        logger.debug(f"Raw responses size: approximately {raw_size_kb:.2f} KB")
        logger.debug(f"Total estimated response size: {response_size_kb + raw_size_kb:.2f} KB")
        
        # Calculate batch timing statistics using parallel processing time calculation
        num_batches = len(batch_processing_times_calculated)
        if num_batches > 0:
            avg_batch_time = total_processing_time / num_batches  # Parallel time per batch
            avg_time_per_row_across_batches = total_processing_time / len(validation_results) if validation_results else 0
            total_batch_time = total_processing_time  # Use parallel processing time
        else:
            avg_batch_time = 0
            avg_time_per_row_across_batches = 0
            total_batch_time = 0
        
        # Log batch timing summary
        logger.debug(f"📊 BATCH TIMING SUMMARY:")
        logger.debug(f"  🚀 Total batches processed: {len(batch_processing_times_calculated)}")
        logger.debug(f"  ⏱️ Average time per batch: {avg_batch_time:.2f}s")
        logger.debug(f"  → Average time per row across all batches: {avg_time_per_row_across_batches:.2f}s")
        logger.debug(f"  ✅ Total batch processing time: {total_batch_time:.2f}s")
        
        # Calculate validation structure metrics
        logger.debug(f"[VALIDATION_METRICS_DEBUG] Total validation_targets: {len(validator.validation_targets)}")
        logger.debug(f"[VALIDATION_METRICS_DEBUG] Validation targets importance values: {[f'{t.column}:{t.importance}' for t in validator.validation_targets]}")
        validation_targets = [t for t in validator.validation_targets if t.importance.upper() not in ["ID", "IGNORED"]]
        validated_columns_count = len(validation_targets)
        logger.debug(f"[VALIDATION_METRICS] Calculated validated_columns_count: {validated_columns_count} from {len(validator.validation_targets)} total targets (after filtering ID/IGNORED)")
        grouped_targets = validator.group_columns_by_search_group(validation_targets)
        search_groups_count = len(grouped_targets)
        
        # Count enhanced context (medium + high) and Claude search groups
        enhanced_context_groups_count = 0
        claude_groups_count = 0
        for group_id, targets in grouped_targets.items():
            if targets:
                # Check if any target in this group has enhanced context (medium or high)
                group_has_enhanced_context = any(
                    (getattr(target, 'search_context_size', '') or '').lower() in ['medium', 'high']
                    for target in targets
                )
                
                # If no explicit context found on targets, check the resolved context for this group
                if not group_has_enhanced_context:
                    try:
                        resolved_context = resolve_search_group_context_size(targets, validator)
                        group_has_enhanced_context = resolved_context and resolved_context.lower() in ['medium', 'high']
                        pass  # logger.debug(f"Group {group_id} resolved context: {resolved_context}")
                    except Exception as e:
                        logger.warning(f"Failed to resolve context size for group {group_id}: {e}")
                
                if group_has_enhanced_context:
                    enhanced_context_groups_count += 1
                
                # Check if any target in this group uses Claude/Anthropic model
                group_model, _ = resolve_search_group_model(targets, validator)
                if determine_api_provider(group_model) == 'anthropic':
                    claude_groups_count += 1
        
        # Log validation metrics summary
        # Validation structure metrics:
        # Logged validation metrics
        
        # Get QC fail rates for models parameter if QC was used
        qc_fail_rates_by_column = {}
        if all_qc_results and qc_manager:
            qc_fail_rates_by_column = qc_manager.cost_tracker.get_qc_fail_rates_by_column()

        # ========== COST_DEBUG: Pre-QC Cost Analysis ==========
        logger.debug(f"[COST_DEBUG] all_enhanced_call_data length: {len(all_enhanced_call_data) if all_enhanced_call_data else 0}")
        # Log individual enhanced call data items to see what costs are being passed
        if all_enhanced_call_data:
            for i, call_data in enumerate(all_enhanced_call_data):
                logger.debug(f"[COST_DEBUG] enhanced_call_data[{i}] structure: {call_data}")
                # Check if it has provider_metrics structure
                if 'provider_metrics' in call_data:
                    for provider, metrics in call_data.get('provider_metrics', {}).items():
                        logger.debug(f"[COST_DEBUG] enhanced_call_data[{i}] provider_metrics[{provider}]: {metrics}")
                else:
                    logger.debug(f"[COST_DEBUG] enhanced_call_data[{i}] missing provider_metrics structure")
        logger.debug(f"[COST_DEBUG] aggregated_metrics keys: {list(aggregated_metrics.keys()) if aggregated_metrics else 'None'}")

        if aggregated_metrics:
            totals = aggregated_metrics.get('totals', {})
            providers = aggregated_metrics.get('providers', {})
            logger.debug(f"[COST_DEBUG] PRE-QC totals: actual=${totals.get('total_cost_actual', 0):.6f}, estimated=${totals.get('total_cost_estimated', 0):.6f}")
            for provider, data in providers.items():
                logger.debug(f"[COST_DEBUG] PRE-QC provider {provider}: calls={data.get('calls', 0)}, tokens={data.get('tokens', 0)}, actual=${data.get('cost_actual', 0):.6f}, estimated=${data.get('cost_estimated', 0):.6f}")

        logger.debug(f"[COST_DEBUG] qc_fail_rates_by_column keys: {list(qc_fail_rates_by_column.keys()) if qc_fail_rates_by_column else 'None'}")

        enhanced_models_parameter = construct_enhanced_models_parameter(
            validator, all_enhanced_call_data, aggregated_metrics, qc_fail_rates_by_column
        )

        # ========== COST_DEBUG: Enhanced Models Parameter Structure ==========
        logger.debug(f"[COST_DEBUG] enhanced_models_parameter keys: {list(enhanced_models_parameter.keys()) if enhanced_models_parameter else 'None'}")
        if enhanced_models_parameter:
            logger.debug(f"[COST_DEBUG] enhanced_models_parameter structure: {enhanced_models_parameter}")
            # Log model details if models array exists
            models_array = enhanced_models_parameter.get('models', [])
            logger.debug(f"[COST_DEBUG] models array length: {len(models_array)}")
            for i, model in enumerate(models_array):
                logger.debug(f"[COST_DEBUG] model[{i}]: {model}")
                if 'qc_fail_rates' in model:
                    logger.debug(f"[COST_DEBUG] model[{i}] qc_fail_rates: {model['qc_fail_rates']}")
        logger.debug(f"[COST_DEBUG] qc_fail_rates_by_column passed to enhanced_models: {qc_fail_rates_by_column}")
        
        # Prepare QC data for response
        qc_response_data = {}
        logger.debug(f"[QC_RESPONSE_DEBUG] Preparing QC response - qc_manager: {qc_manager is not None}, "
                   f"is_enabled: {qc_manager.is_qc_enabled() if qc_manager else 'N/A'}, "
                   f"rows_processed: {qc_metrics_summary.get('total_rows_processed', 0)}, "
                   f"fields_reviewed: {qc_metrics_summary.get('total_fields_reviewed', 0)}")

        # Include QC metrics if QC was enabled and ran (even if no modifications)
        if qc_manager and qc_manager.is_qc_enabled() and qc_metrics_summary.get('total_rows_processed', 0) > 0:
            # Get properly formatted QC tracker metrics to fill in any missing data
            if hasattr(qc_manager, 'get_aggregated_qc_metrics'):
                qc_tracker_aggregated = qc_manager.get_aggregated_qc_metrics()
                qc_tracker_data = qc_tracker_aggregated.get('qc_totals', {})
                # Use tracker data if our summary is missing values
                if qc_metrics_summary.get('total_qc_calls', 0) == 0 and qc_tracker_data.get('total_qc_calls', 0) > 0:
                    qc_metrics_summary['total_qc_calls'] = qc_tracker_data['total_qc_calls']
                if qc_metrics_summary.get('confidence_lowered_count', 0) == 0 and qc_tracker_data.get('confidence_lowered_count', 0) > 0:
                    qc_metrics_summary['confidence_lowered_count'] = qc_tracker_data['confidence_lowered_count']
                if qc_metrics_summary.get('values_replaced_count', 0) == 0 and qc_tracker_data.get('values_replaced_count', 0) > 0:
                    qc_metrics_summary['values_replaced_count'] = qc_tracker_data['values_replaced_count']
                # Also update other metrics that might be missing
                if qc_metrics_summary.get('total_fields_modified', 0) == 0 and qc_tracker_data.get('total_fields_modified', 0) > 0:
                    qc_metrics_summary['total_fields_modified'] = qc_tracker_data['total_fields_modified']

            # Add column-level QC analysis
            logger.debug(f"[QC_METRICS_DEBUG] Checking for cost_tracker: hasattr={hasattr(qc_manager, 'cost_tracker')}, qc_manager={qc_manager.__class__.__name__ if qc_manager else None}")
            if hasattr(qc_manager, 'cost_tracker'):
                qc_by_column = qc_manager.cost_tracker.get_qc_fail_rates_by_column()
                qc_metrics_summary['qc_by_column'] = qc_by_column
                logger.debug(f"[QC_METRICS] Added qc_by_column analysis: {len(qc_by_column)} columns - columns: {list(qc_by_column.keys())}")
            else:
                # Fallback: try to get qc_by_column from tracker data
                if qc_tracker_data and 'qc_by_column' in qc_tracker_data:
                    logger.debug(f"[QC_METRICS_DEBUG] Using qc_by_column from tracker_data directly")
                    qc_metrics_summary['qc_by_column'] = qc_tracker_data['qc_by_column']

            # Convert set to list for JSON serialization
            qc_metrics_summary['qc_models_used'] = list(qc_metrics_summary.get('qc_models_used', set()))
            qc_response_data = {
                'qc_results': all_qc_results,  # May be empty if no modifications
                'qc_metrics': qc_metrics_summary
            }
            logger.debug(f"QC Summary: {qc_metrics_summary['total_rows_processed']} rows processed, "
                       f"{qc_metrics_summary['total_fields_reviewed']} fields reviewed, "
                       f"{qc_metrics_summary['total_fields_modified']} fields modified, "
                       f"${qc_metrics_summary.get('total_qc_cost', 0):.4f} cost")
            logger.debug(f"[QC_RESPONSE_DEBUG] Including QC data in response - qc_results count: {len(all_qc_results)}, metrics: {qc_metrics_summary}")
            logger.debug(f"[QC_RESPONSE_DEBUG] all_qc_results keys: {list(all_qc_results.keys())}")
            if all_qc_results:
                sample_key = list(all_qc_results.keys())[0]
                sample_value = all_qc_results[sample_key]
                logger.debug(f"[QC_RESPONSE_DEBUG] Sample QC result - key: {sample_key}, fields: {list(sample_value.keys()) if isinstance(sample_value, dict) else 'Not a dict'}")

            # Log QC fail rate summary if available
            if qc_manager:
                qc_manager.cost_tracker.log_qc_fail_rate_summary()
        else:
            # Even if no rows were processed, check if QC manager has metrics to report
            if qc_manager and hasattr(qc_manager, 'get_aggregated_qc_metrics'):
                qc_tracker_aggregated = qc_manager.get_aggregated_qc_metrics()
                qc_tracker_totals = qc_tracker_aggregated.get('qc_totals', {})
                if qc_tracker_totals and any(qc_tracker_totals.get(k, 0) for k in ['total_qc_calls', 'total_fields_reviewed']):
                    logger.debug(f"[QC_RESPONSE_DEBUG] Found QC tracker metrics despite no rows processed: {qc_tracker_totals}")
                    # Add qc_by_column if available
                    if hasattr(qc_manager, 'cost_tracker'):
                        qc_by_column = qc_manager.cost_tracker.get_qc_fail_rates_by_column()
                        qc_tracker_totals['qc_by_column'] = qc_by_column
                        logger.debug(f"[QC_METRICS] Added qc_by_column to tracker data: {len(qc_by_column)} columns")
                    # Include the properly formatted tracker metrics in response
                    qc_response_data = {
                        'qc_results': {},  # Empty results
                        'qc_metrics': qc_tracker_totals
                    }

        # ========== QC PROVIDER METRICS INTEGRATION ==========
        # Add QC metrics to aggregated_metrics for provider tracking
        qc_enhanced_aggregated_metrics = aggregated_metrics.copy() if aggregated_metrics else {'providers': {}, 'totals': {}}

        # Add QC-specific provider tracking if QC was used
        if all_qc_results and qc_manager:
            qc_tracker_metrics = qc_manager.get_qc_metrics()

            # Add QC costs to the specific provider (anthropic for QC)
            if 'providers' not in qc_enhanced_aggregated_metrics:
                qc_enhanced_aggregated_metrics['providers'] = {}

            # Update anthropic provider with QC costs
            if 'anthropic' not in qc_enhanced_aggregated_metrics['providers']:
                qc_enhanced_aggregated_metrics['providers']['anthropic'] = {
                    'calls': 0, 'tokens': 0, 'cost_actual': 0.0, 'cost_estimated': 0.0,
                    'time_actual': 0.0, 'time_estimated': 0.0
                }

            anthropic_provider = qc_enhanced_aggregated_metrics['providers']['anthropic']
            # Add QC costs/tokens/time/calls to anthropic provider for consistent aggregation
            anthropic_provider['calls'] += qc_tracker_metrics.get('total_qc_calls', 0)  # Include QC calls in Anthropic provider
            anthropic_provider['tokens'] += qc_tracker_metrics.get('total_qc_tokens', 0)
            anthropic_provider['cost_actual'] += qc_tracker_metrics.get('total_qc_cost', 0.0)
            anthropic_provider['cost_estimated'] += qc_tracker_metrics.get('total_qc_estimated_cost', 0.0)
            anthropic_provider['time_actual'] += qc_tracker_metrics.get('total_qc_time_actual', 0.0)
            anthropic_provider['time_estimated'] += qc_tracker_metrics.get('total_qc_time_estimated', 0.0)

            # Calculate QC fail rates by column
            qc_fail_rates = qc_manager.cost_tracker.get_qc_fail_rates_by_column()

            # Add separate QC_Costs provider entry for QC-specific analysis
            # NOTE: This is for tracking/display only - actual costs are already added to anthropic provider
            # to avoid double counting in totals
            qc_enhanced_aggregated_metrics['providers']['QC_Costs'] = {
                'calls': qc_tracker_metrics.get('total_qc_calls', 0),
                'tokens': qc_tracker_metrics.get('total_qc_tokens', 0),
                'cost_actual': qc_tracker_metrics.get('total_qc_cost', 0.0),
                'cost_estimated': qc_tracker_metrics.get('total_qc_estimated_cost', 0.0),
                'time_actual': qc_tracker_metrics.get('total_qc_time_actual', 0.0),
                'time_estimated': qc_tracker_metrics.get('total_qc_time_estimated', 0.0),
                'is_metadata_only': True,  # Flag to indicate this shouldn't be summed in totals
                'qc_specific_metrics': {
                    'fields_reviewed': qc_tracker_metrics.get('total_fields_reviewed', 0),
                    'fields_modified': qc_tracker_metrics.get('total_fields_modified', 0),
                    'confidence_lowered_count': qc_tracker_metrics.get('confidence_lowered_count', 0),
                    'values_replaced_count': qc_tracker_metrics.get('values_replaced_count', 0),
                    'models_used': list(qc_tracker_metrics.get('qc_models_used', set())),
                    'qc_fail_rates_by_column': qc_fail_rates
                }
            }

            # Update totals to include QC costs
            if 'totals' not in qc_enhanced_aggregated_metrics:
                qc_enhanced_aggregated_metrics['totals'] = {}

            totals = qc_enhanced_aggregated_metrics['totals']
            # Add QC costs/tokens/time/calls to totals for consistent aggregation
            totals['total_calls'] = totals.get('total_calls', 0) + qc_tracker_metrics.get('total_qc_calls', 0)  # Include QC calls in totals
            totals['total_tokens'] = totals.get('total_tokens', 0) + qc_tracker_metrics.get('total_qc_tokens', 0)
            totals['total_cost_actual'] = totals.get('total_cost_actual', 0.0) + qc_tracker_metrics.get('total_qc_cost', 0.0)
            totals['total_cost_estimated'] = totals.get('total_cost_estimated', 0.0) + qc_tracker_metrics.get('total_qc_estimated_cost', 0.0)
            totals['total_actual_processing_time'] = totals.get('total_actual_processing_time', 0.0) + qc_tracker_metrics.get('total_qc_time_actual', 0.0)
            totals['total_estimated_processing_time'] = totals.get('total_estimated_processing_time', 0.0) + qc_tracker_metrics.get('total_qc_time_estimated', 0.0)

            # ========== COST_DEBUG: Post-QC Cost Analysis ==========
            logger.debug(f"[COST_DEBUG] QC tracker metrics: {qc_tracker_metrics}")
            logger.debug(f"[COST_DEBUG] POST-QC totals: actual=${totals.get('total_cost_actual', 0):.6f}, estimated=${totals.get('total_cost_estimated', 0):.6f}")
            for provider, data in qc_enhanced_aggregated_metrics.get('providers', {}).items():
                logger.debug(f"[COST_DEBUG] POST-QC provider {provider}: calls={data.get('calls', 0)}, tokens={data.get('tokens', 0)}, actual=${data.get('cost_actual', 0):.6f}, estimated=${data.get('cost_estimated', 0):.6f}")

            # Update full_validation_estimates to include QC costs (QC TIME already included in batch estimates)
            if full_validation_estimates and qc_tracker_metrics:
                qc_scaling_factor = total_rows_in_table / max(1, preview_rows_processed) if is_preview else 1.0
                qc_estimated_full_cost = qc_tracker_metrics.get('total_qc_estimated_cost', 0.0) * qc_scaling_factor
                # Note: QC time is already included in batch estimates, don't add again

                # Update the total estimates to include QC costs only
                if 'total_estimates' in full_validation_estimates:
                    full_validation_estimates['total_estimates']['estimated_total_cost_estimated'] += qc_estimated_full_cost
                    # DON'T add QC time here - already included in batch timing
                    logger.debug(f"[COST_DEBUG] Updated full validation estimates with QC cost: added ${qc_estimated_full_cost:.6f} (${qc_tracker_metrics.get('total_qc_estimated_cost', 0.0):.6f} * {qc_scaling_factor:.1f})")
                    logger.debug(f"[COST_DEBUG] Final estimated_total_cost_estimated: ${full_validation_estimates['total_estimates']['estimated_total_cost_estimated']:.6f}")
                    logger.debug(f"[TIME_DEBUG] QC time already included in batch estimates, not adding separately")
                    logger.debug(f"[TIME_DEBUG] Final estimated_total_processing_time: {full_validation_estimates['total_estimates']['estimated_total_processing_time']:.2f}s")

                # Note: Not updating timing_estimates or batch_timing_analysis as QC time is already included

        # Log the enhanced_models_parameter before including in response
        logger.debug(f"[MODELS_PASSTHROUGH_DEBUG] enhanced_models_parameter being sent in response: {list(enhanced_models_parameter.keys()) if enhanced_models_parameter else 'EMPTY'}")
        if enhanced_models_parameter:
            logger.debug(f"[MODELS_PASSTHROUGH_DEBUG] Sample search group data: {list(enhanced_models_parameter.get('search_group_1', {}).keys()) if 'search_group_1' in enhanced_models_parameter else 'No search_group_1'}")

        # Create a single response
        response = {
            "statusCode": 200,
            "body": {
                "success": True,
                "message": "Validation completed",
                "data": {
                    # Map row indices to results
                    "rows": validation_results,
                    # Add QC data if available
                    **qc_response_data
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
                        "aggregated_metrics": qc_enhanced_aggregated_metrics,  # Complete provider breakdown with costs/tokens/timing including QC
                        "full_validation_estimates": full_validation_estimates,  # Full validation projections for preview operations
                        "preview_operation": event.get('is_preview', False),
                        "ai_client_calls_count": len(all_enhanced_call_data),
                        "all_enhanced_call_data": all_enhanced_call_data,  # Individual enhanced data from all AI calls for other calculations
                        # NEW: Batch timing data
                        "batch_timing": {
                            "total_batches": len(batch_processing_times_calculated),
                            "dynamic_batch_sizing": True,  # Indicate that batch sizes were dynamic
                            "total_batch_time_seconds": total_batch_time,
                            "average_batch_time_seconds": avg_batch_time,
                            "average_time_per_row_seconds": avg_time_per_row_across_batches,
                            "batch_details": list(batch_processing_times_calculated.items())  # Convert dict to list of (batch_num, time) pairs
                        },
                        # NEW: Validation structure metrics
                        "validation_metrics": {
                            "validated_columns_count": validated_columns_count,
                            "search_groups_count": search_groups_count,
                            "enhanced_context_search_groups_count": enhanced_context_groups_count,
                            "claude_search_groups_count": claude_groups_count
                        },
                        # NEW: Enhanced models parameter with detailed search group information
                        "enhanced_models_parameter": enhanced_models_parameter,
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
        }
        
        # DEBUG: Log what we're actually returning in metadata
        logger.debug(f"[METADATA_RETURN_DEBUG] Metadata keys being returned: {list(response['body']['metadata'].keys())}")
        logger.debug(f"[METADATA_RETURN_DEBUG] validation_metrics in metadata: {response['body']['metadata'].get('validation_metrics', 'NOT FOUND')}")

        # Log what validation lambda is sending back (CALL COUNTS DEBUGGING) - FINAL VERSION
        validation_calls_by_provider = {}
        qc_calls_total = 0
        if qc_enhanced_aggregated_metrics and qc_enhanced_aggregated_metrics.get('providers'):
            providers = qc_enhanced_aggregated_metrics.get('providers', {})
            for provider, data in providers.items():
                if not data.get('is_metadata_only', False):  # Exclude metadata-only providers
                    validation_calls_by_provider[provider] = data.get('calls', 0)

        if qc_metrics_summary.get('total_rows_processed', 0) > 0:
            qc_calls_total = qc_metrics_summary.get('total_qc_calls', 0)

        logger.debug(f"[VALIDATION_LAMBDA_RESPONSE] FINAL - Sending call counts to interface:")
        logger.debug(f"[VALIDATION_LAMBDA_RESPONSE]   Validation calls by provider: {validation_calls_by_provider}")
        logger.debug(f"[VALIDATION_LAMBDA_RESPONSE]   QC calls total: {qc_calls_total}")
        logger.debug(f"[VALIDATION_LAMBDA_RESPONSE]   Grand total calls: {sum(validation_calls_by_provider.values()) + qc_calls_total}")
        logger.debug(f"[METADATA_RETURN_DEBUG] validated_columns_count: {response['body']['metadata'].get('validation_metrics', {}).get('validated_columns_count', 'NOT FOUND')}")
        
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
        if progress_thread:
            final_count = completed_ai_calls[0]
            progress_queue.put((float('inf'), f"Validation completed! {final_count} AI calls processed", 100))

        # ========== SAVE CUMULATIVE RESULTS TO S3 ==========
        # Always save complete cumulative results for async processing
        logger.info(f"[S3_SAVE] Checking if should save to S3: is_async_request={is_async_request}, session_id={session_id}")
        if is_async_request and session_id:
            try:
                # Helper function to merge token usage dicts
                def merge_token_usage(existing, current):
                    """Merge token usage from existing and current runs."""
                    merged = existing.copy() if existing else {}
                    for key, value in (current or {}).items():
                        if isinstance(value, dict):
                            merged[key] = merge_token_usage(merged.get(key, {}), value)
                        elif isinstance(value, (int, float)):
                            merged[key] = merged.get(key, 0) + value
                        else:
                            merged[key] = value
                    return merged

                # Merge token usage and metrics with existing data (from continuation)
                current_token_usage = response['body']['metadata']['token_usage']
                current_enhanced_metrics = response['body']['metadata']['enhanced_metrics']

                merged_token_usage = merge_token_usage(existing_token_usage, current_token_usage)
                merged_enhanced_metrics = merge_token_usage(existing_enhanced_metrics, current_enhanced_metrics)

                logger.debug(f"[S3_SAVE] Merged token usage: existing keys={list(existing_token_usage.keys())}, current keys={list(current_token_usage.keys())}, merged keys={list(merged_token_usage.keys())}")

                # Create cumulative results structure
                cumulative_results = {
                    'validation_results': response['body']['data']['rows'],  # Already includes existing + new rows
                    'token_usage': merged_token_usage,
                    'enhanced_metrics': merged_enhanced_metrics,
                    'metadata': {
                        'total_rows_processed': response['body']['metadata']['completed_rows'],
                        'total_rows': response['body']['metadata']['total_rows'],
                        'processing_complete': True,  # Will be updated for continuation
                        'cache_hits': response['body']['metadata']['cache_hits'],
                        'cache_misses': response['body']['metadata']['cache_misses'],
                        'processing_time': response['body']['metadata']['processing_time'],
                        'completion_timestamp': datetime.now(timezone.utc).isoformat(),
                        'continuation_count': event.get('continuation_count', 0)
                    }
                }

                # Include QC data if available
                if 'qc_results' in response['body']['data']:
                    cumulative_results['qc_results'] = response['body']['data']['qc_results']
                if 'qc_metrics' in response['body']['data']:
                    cumulative_results['qc_metrics'] = response['body']['data']['qc_metrics']

                # Save to S3
                s3_client = boto3.client('s3')
                s3_bucket = event.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')

                # Get results path from event or construct it with config_version
                results_path = event.get('results_path')
                if results_path:
                    results_s3_key = f"{results_path}/complete_validation_results.json"
                else:
                    domain, email_prefix = get_s3_path_components(event)
                    config_version = event.get('config_version', 1)
                    results_s3_key = f"results/{domain}/{email_prefix}/{session_id}/v{config_version}_results/complete_validation_results.json"
                    logger.warning(f"[S3_SAVE] results_path not in event, constructed path with config_version={config_version}")

                logger.info(f"[S3_SAVE] About to save to S3: bucket={s3_bucket}, key={results_s3_key}")

                s3_client.put_object(
                    Bucket=s3_bucket,
                    Key=results_s3_key,
                    Body=json.dumps(cumulative_results, default=str),
                    ContentType='application/json',
                    Metadata={
                        'session_id': session_id,
                        'completion_timestamp': datetime.now(timezone.utc).isoformat()
                    }
                )

                logger.info(f"[S3_SAVE] Successfully saved cumulative results to s3://{s3_bucket}/{results_s3_key}")

                # Check if we should trigger completion or continue
                remaining_ms = get_remaining_time_ms()
                should_continue = should_continue_processing()
                logger.info(f"[S3_SAVE] Decision point: remaining_ms={remaining_ms}, should_continue={should_continue}")

                # Check if there's more work to do (incomplete validation)
                total_rows = len(event.get('validation_data', {}).get('rows', []))
                validation_results_data = cumulative_results.get('validation_results', {})

                # Debug: Check the structure of validation_results
                logger.info(f"[S3_SAVE] validation_results type: {type(validation_results_data)}, is dict: {isinstance(validation_results_data, dict)}, is list: {isinstance(validation_results_data, list)}")

                # Count processed rows correctly based on structure
                if isinstance(validation_results_data, dict):
                    processed_rows = len(validation_results_data)
                elif isinstance(validation_results_data, list):
                    processed_rows = len(validation_results_data)
                else:
                    logger.error(f"[S3_SAVE] Unexpected validation_results type: {type(validation_results_data)}")
                    processed_rows = 0

                has_more_work = processed_rows < total_rows
                logger.info(f"[S3_SAVE] Work status: processed_rows={processed_rows}, total_rows={total_rows}, has_more_work={has_more_work}")

                # IMPORTANT: Check if work is complete FIRST, before considering time
                if not has_more_work:
                    # All work is done - trigger completion regardless of time remaining
                    # DELETE payload since this is successful final completion
                    logger.info(f"[S3_SAVE] All rows processed ({processed_rows}/{total_rows}), triggering interface completion")
                    logger.info(f"[S3_SAVE] About to call trigger_interface_completion with results_s3_key={results_s3_key}")
                    trigger_interface_completion(results_s3_key, delete_payload=True)
                    logger.info(f"[S3_SAVE] trigger_interface_completion call completed")
                elif has_more_work:
                    # More work to do - validate progress was made to prevent infinite loops
                    # IMPORTANT: Compare ROWS with ROWS (not batches with rows!)
                    last_completed_rows = event.get('last_completed_rows', 0)  # Row count from previous continuation
                    current_completed_rows = processed_rows  # Current row count

                    # Check if progress was made (at least 1 more row processed)
                    progress_made = current_completed_rows > last_completed_rows
                    logger.info(f"[PROGRESS_CHECK] Last completed rows: {last_completed_rows}, Current rows: {current_completed_rows}, Progress made: {progress_made}")

                    if not progress_made:
                        logger.error(f"[PROGRESS_CHECK] No progress made since last continuation! Preventing infinite loop.")
                        logger.error(f"[PROGRESS_CHECK] Last: {last_completed_rows} rows, Current: {current_completed_rows} rows")
                        logger.error(f"[PROGRESS_CHECK] Marking validation as failed and triggering completion")

                        # Add error to results
                        cumulative_results['validation_error'] = 'No progress made - preventing infinite continuation loop'
                        cumulative_results['status'] = 'FAILED_NO_PROGRESS'

                        # Save updated results
                        s3_client.put_object(
                            Bucket=s3_bucket,
                            Key=results_s3_key,
                            Body=json.dumps(cumulative_results, default=str),
                            ContentType='application/json'
                        )

                        # Trigger completion (not continuation)
                        # DON'T delete payload - may have concurrent continuations that need it
                        trigger_interface_completion(results_s3_key, delete_payload=False)
                    else:
                        # More work remains but batch loop completed
                        # This should NOT happen - if batch loop completed normally without triggering continuation,
                        # all batches should be done (which means all work should be done)
                        logger.error(f"[S3_SAVE] ERROR: Batch loop completed but work remains!")
                        logger.error(f"[S3_SAVE] Processed: {processed_rows}/{total_rows} rows, Time remaining: {remaining_ms}ms")
                        logger.error(f"[S3_SAVE] This indicates a logic error in batch planning")

                        # Mark as failed and trigger completion
                        cumulative_results['validation_error'] = 'Batch loop completed but work incomplete - logic error'
                        cumulative_results['status'] = 'FAILED_INCOMPLETE'

                        s3_client.put_object(
                            Bucket=s3_bucket,
                            Key=results_s3_key,
                            Body=json.dumps(cumulative_results, default=str),
                            ContentType='application/json'
                        )

                        trigger_interface_completion(results_s3_key, delete_payload=False)
                else:
                    # This should never happen - all cases are covered above
                    logger.error(f"[S3_SAVE] Unexpected state: should_continue={should_continue}, has_more_work={has_more_work}, remaining_ms={remaining_ms}")
                    logger.error(f"[S3_SAVE] Falling back to trigger completion")
                    # DON'T delete payload - this is an unexpected error state
                    trigger_interface_completion(results_s3_key, delete_payload=False)

            except Exception as e:
                logger.error(f"[S3_SAVE] Failed to save cumulative results to S3: {e}")
                logger.error(f"[S3_SAVE] Exception details: {type(e).__name__}: {str(e)}")
                logger.error(f"[S3_SAVE] Traceback: {traceback.format_exc()}")
                # Don't fail the entire function - just log the error

        # Return the combined results
        return response
    except ContinuationTriggered as ct:
        # Continuation was triggered - exit Lambda immediately with success response
        logger.info(f"[LAMBDA_EXIT] Exiting due to continuation trigger")
        return ct.response_data
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        logger.error(traceback.format_exc())

        # Clean up S3 payload on error if this is an async request
        try:
            cleanup_s3_payload_if_needed()
        except Exception as cleanup_error:
            logger.warning(f"[CLEANUP] Error during S3 cleanup in exception handler: {cleanup_error}")

        return {
        'statusCode': 500,
        'body': {
            'error': str(e)
        }
        }
    finally:
        if progress_thread:
            if progress_queue:
                progress_queue.put(None)
            progress_thread.join()