#!/usr/bin/env python3
"""
Shared AI API client with caching support.
Used by both validation and config lambdas to interact with Anthropic's Claude API and Perplexity API.
"""

import json
import logging
import os
import hashlib
import aiohttp
import boto3
import asyncio
import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
from perplexity_schema import get_response_format_schema
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test logging to verify module is loaded
logger.info("AI_API_CLIENT: Module loaded successfully")

class AIAPIClient:
    """Shared AI API client with caching and schema support."""
    
    # Model hierarchy from best to most basic
    MODEL_HIERARCHY = [
        "claude-opus-4-1",
        "claude-opus-4-0", 
        "claude-sonnet-4-0",
        "sonar-pro",
        "claude-3-7-sonnet-latest",
        "sonar",
        "claude-3-5-haiku-latest"
    ]
    
    def __init__(self, s3_bucket: str = None):
        # Check if using unified bucket structure
        self.unified_bucket = os.environ.get('S3_UNIFIED_BUCKET')
        if self.unified_bucket:
            self.s3_bucket = self.unified_bucket
            self.use_unified_structure = True
            logger.info(f"AI_API_CLIENT: Using unified S3 bucket: {self.unified_bucket}")
        else:
            # Legacy fallback
            self.s3_bucket = s3_bucket or os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
            self.use_unified_structure = False
            logger.info(f"AI_API_CLIENT: Using legacy S3 bucket: {self.s3_bucket}")
        
        self.s3_client = boto3.client('s3')
        self.anthropic_api_key = self._get_anthropic_api_key()
        self.perplexity_api_key = self._get_perplexity_api_key()
    
    def _get_anthropic_api_key(self) -> str:
        """Get Anthropic API key from environment or SSM."""
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if api_key:
            logger.info("Using Anthropic API key from environment variable")
            return api_key
        
        # Try AWS Systems Manager Parameter Store
        try:
            ssm_client = boto3.client('ssm')
            param_names = ['/Anthropic_API_Key', 'Anthropic_API_Key']
            
            for param_name in param_names:
                try:
                    logger.info(f"Attempting to retrieve Anthropic API key from SSM parameter: {param_name}")
                    response = ssm_client.get_parameter(
                        Name=param_name,
                        WithDecryption=True
                    )
                    logger.info(f"Successfully retrieved Anthropic API key from {param_name}")
                    return response['Parameter']['Value']
                except Exception as e:
                    logger.warning(f"Failed to get Anthropic API key from SSM parameter '{param_name}': {str(e)}")
                    continue
            
            logger.error("Failed to retrieve Anthropic API key from any SSM parameter variant")
            raise Exception(f"Anthropic API key not found in SSM. Tried parameters: {param_names}")
            
        except Exception as e:
            logger.error(f"Failed to retrieve Anthropic API key: {str(e)}")
            raise
    
    def _get_perplexity_api_key(self) -> str:
        """Get Perplexity API key from environment or SSM."""
        api_key = os.environ.get('PERPLEXITY_API_KEY')
        if api_key:
            logger.info("Using Perplexity API key from environment variable")
            return api_key
        
        # Try AWS Systems Manager Parameter Store
        try:
            ssm_client = boto3.client('ssm')
            param_names = ['/perplexity-validator/perplexity-api-key', 'Perplexity_API_Key']
            
            for param_name in param_names:
                try:
                    logger.info(f"Attempting to retrieve Perplexity API key from SSM parameter: {param_name}")
                    response = ssm_client.get_parameter(
                        Name=param_name,
                        WithDecryption=True
                    )
                    logger.info(f"Successfully retrieved Perplexity API key from {param_name}")
                    return response['Parameter']['Value']
                except Exception as e:
                    logger.warning(f"Failed to get Perplexity API key from SSM parameter '{param_name}': {str(e)}")
                    continue
            
            # If we get here, all parameter names failed
            raise Exception("Could not retrieve Perplexity API key from any SSM parameter")
        except Exception as e:
            logger.error(f"Failed to retrieve Perplexity API key: {str(e)}")
            raise
    
    def _determine_api_provider(self, model: str) -> str:
        """Determine API provider based on model name."""
        if (model.startswith('anthropic/') or 
            model.startswith('anthropic.') or 
            model.startswith('claude-')):
            return 'anthropic'
        return 'perplexity'
    
    def _normalize_anthropic_model(self, model: str) -> str:
        """Convert anthropic/ format to direct API format if needed."""
        if model.startswith('anthropic/'):
            return model.replace('anthropic/', '')
        elif model.startswith('anthropic.'):
            return model.replace('anthropic.', '').replace('-v1:0', '')
        return model
    
    def _get_backup_models(self, primary_model: str, count: int = 2) -> List[str]:
        """Get the next N backup models based on hierarchy position."""
        try:
            # Find the primary model in hierarchy
            primary_index = self.MODEL_HIERARCHY.index(primary_model)
            
            # Get the next models after the primary
            backup_models = []
            for i in range(1, count + 1):
                backup_index = primary_index + i
                if backup_index < len(self.MODEL_HIERARCHY):
                    backup_models.append(self.MODEL_HIERARCHY[backup_index])
            
            return backup_models
            
        except ValueError:
            # Primary model not in hierarchy, return default backups
            logger.warning(f"Model {primary_model} not in hierarchy, using default backups")
            return ["claude-opus-4-0", "claude-3-7-sonnet-latest"][:count]
    
    def _get_cache_key(self, prompt: str, model: str, schema: Dict = None, context: str = "") -> str:
        """Generate a unique cache key for the request."""
        schema_str = json.dumps(schema, sort_keys=True) if schema else ""
        cache_input = f"{prompt}:{model}:{schema_str}:{context}"
        return hashlib.md5(cache_input.encode()).hexdigest()
    
    def _get_validation_cache_key(self, row_data: Dict, targets: List, model: str, search_context_size: str = "low", config_hash: str = "") -> str:
        """
        Generate a cache key based on core validation data, ignoring validation history.
        This allows cache hits between preview and full validation of the same rows.
        """
        # Create a normalized representation of the validation request
        cache_components = {
            'row_data': {k: str(v) for k, v in row_data.items()},  # Normalize row data
            'targets': [{'column': t.column if hasattr(t, 'column') else str(t), 
                        'importance': t.importance if hasattr(t, 'importance') else '',
                        'format': t.format if hasattr(t, 'format') else ''} for t in targets],
            'model': model,
            'search_context_size': search_context_size,
            'config_hash': config_hash
        }
        
        # Create deterministic JSON string and hash it
        cache_input = json.dumps(cache_components, sort_keys=True)
        return hashlib.md5(cache_input.encode()).hexdigest()
    
    def _extract_token_usage(self, response: Dict, model: str, search_context_size: str = None) -> Dict:
        """Extract token usage information from API response, handling both Perplexity and Anthropic formats."""
        if 'usage' not in response:
            return {
                'api_provider': self._determine_api_provider(model),
                'input_tokens': 0,
                'output_tokens': 0,
                'cache_creation_tokens': 0,
                'cache_read_tokens': 0,
                'total_tokens': 0,
                'model': model
            }
        
        usage = response['usage']
        api_provider = self._determine_api_provider(model)
        
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
            # Perplexity format: prompt_tokens, completion_tokens, total_tokens
            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)
            
            return {
                'api_provider': 'perplexity',
                'input_tokens': prompt_tokens,
                'output_tokens': completion_tokens,
                'cache_creation_tokens': 0,
                'cache_read_tokens': 0,
                'total_tokens': total_tokens,
                'model': model,
                'search_context_size': search_context_size
            }
    
    def _get_cache_s3_key(self, cache_key: str, api_provider: str) -> str:
        """Generate S3 key for cache based on structure type."""
        if self.use_unified_structure:
            # New unified structure: cache/{service}/{hash}/response.json
            service = 'claude' if api_provider == 'anthropic' else 'perplexity'
            return f"cache/{service}/{cache_key}/response.json"
        else:
            # Legacy structure: {service}_cache/{hash}.json
            cache_prefix = 'claude_cache' if api_provider == 'anthropic' else 'validation_cache'
            return f"{cache_prefix}/{cache_key}.json"

    async def _check_cache(self, cache_key: str, api_provider: str = 'claude') -> Optional[Dict]:
        """Check if response is cached."""
        cache_check_start = datetime.now()
        try:
            s3_key = self._get_cache_s3_key(cache_key, api_provider)
            
            logger.info(f"CACHE_CHECK: Checking S3 cache for key: {cache_key[:8]}... in bucket: {self.s3_bucket}, path: {s3_key}")
            
            cache_response = self.s3_client.get_object(
                Bucket=self.s3_bucket,
                Key=s3_key
            )
            
            cached_data = json.loads(cache_response['Body'].read())
            cache_check_time = (datetime.now() - cache_check_start).total_seconds()
            
            # Fix legacy cached token usage format - ensure it has normalized fields
            if 'token_usage' in cached_data:
                token_usage = cached_data['token_usage']
                api_provider_name = token_usage.get('api_provider', api_provider)
                
                # For Perplexity cached data, ensure input_tokens and output_tokens are set
                if api_provider_name == 'perplexity':
                    if 'input_tokens' not in token_usage and 'prompt_tokens' in token_usage:
                        token_usage['input_tokens'] = token_usage['prompt_tokens']
                    if 'output_tokens' not in token_usage and 'completion_tokens' in token_usage:
                        token_usage['output_tokens'] = token_usage['completion_tokens']
                
                # For Anthropic cached data, the fields should already be correct but double-check
                elif api_provider_name == 'anthropic':
                    if 'input_tokens' not in token_usage:
                        token_usage['input_tokens'] = token_usage.get('input_tokens', 0)
                    if 'output_tokens' not in token_usage:
                        token_usage['output_tokens'] = token_usage.get('output_tokens', 0)
            
            # Log detailed cache hit information
            cached_at = cached_data.get('cached_at', 'Unknown')
            cached_model = cached_data.get('model', 'Unknown')
            cache_age_hours = "Unknown"
            
            try:
                if cached_at != 'Unknown':
                    cached_time = datetime.fromisoformat(cached_at.replace('Z', '+00:00'))
                    cache_age = datetime.now(timezone.utc) - cached_time
                    cache_age_hours = cache_age.total_seconds() / 3600
            except:
                pass
            
            logger.info(f"CACHE_HIT: Found cached response for key: {cache_key[:8]}... "
                       f"(cached {cache_age_hours:.1f}h ago, model: {cached_model}, "
                       f"check_time: {cache_check_time:.3f}s)")
            
            return cached_data
            
        except self.s3_client.exceptions.NoSuchKey:
            cache_check_time = (datetime.now() - cache_check_start).total_seconds()
            logger.info(f"CACHE_MISS: No cached response found for key: {cache_key[:8]}... "
                       f"(check_time: {cache_check_time:.3f}s)")
            return None
        except Exception as e:
            cache_check_time = (datetime.now() - cache_check_start).total_seconds()
            logger.error(f"CACHE_ERROR: Failed to check cache for key: {cache_key[:8]}... "
                        f"Error: {str(e)}, check_time: {cache_check_time:.3f}s")
            return None
    
    async def _save_to_cache(self, cache_key: str, response: Dict, token_usage: Dict, processing_time: float, model: str, api_provider: str = 'anthropic'):
        """Save response to cache."""
        try:
            cache_entry = {
                'api_response': response,
                'cached_at': datetime.now(timezone.utc).isoformat(),
                'model': model,
                'token_usage': token_usage,
                'processing_time': processing_time
            }
            
            s3_key = self._get_cache_s3_key(cache_key, api_provider)
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=json.dumps(cache_entry),
                ContentType='application/json'
            )
            logger.info(f"Cached API response, key: {cache_key[:8]}...")
        except Exception as e:
            logger.error(f"Failed to cache API response: {str(e)}")
    
    async def _save_debug_data(self, api_provider: str, model: str, request_data: Dict, 
                              response_data: Any, error: Exception = None, context: str = ""):
        """Save debug data for API calls to help diagnose issues."""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            status = "ERROR" if error else "SUCCESS"
            model_clean = model.replace('/', '_').replace(':', '_')
            
            # Create filename: YYYYMMDD_HHMMSS_provider_model_status.json
            debug_filename = f"{timestamp}_{api_provider}_{model_clean}_{status}.json"
            
            debug_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'api_provider': api_provider,
                'model': model,
                'status': status,
                'context': context,
                'request': request_data,
                'response': None,
                'error': None,
                'error_details': None,
                'stack_trace': None
            }
            
            if error:
                debug_entry['error'] = str(error)
                debug_entry['error_type'] = type(error).__name__
                debug_entry['stack_trace'] = traceback.format_exc()
                
                # Extract HTTP status if available
                error_str = str(error)
                if '(429)' in error_str:
                    debug_entry['error_details'] = {'http_status': 429, 'error_type': 'rate_limit'}
                elif '(499)' in error_str:
                    debug_entry['error_details'] = {'http_status': 499, 'error_type': 'client_disconnect'}
                elif '(529)' in error_str:
                    debug_entry['error_details'] = {'http_status': 529, 'error_type': 'overloaded'}
            else:
                debug_entry['response'] = response_data
            
            # Save to S3 debug folder with clearer structure
            if self.use_unified_structure:
                s3_key = f"debug/{api_provider}/{debug_filename}"
            else:
                s3_key = f"api_debug/{api_provider}/{debug_filename}"
            
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=json.dumps(debug_entry, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"[DEBUG] Saved debug data to s3://{self.s3_bucket}/{s3_key}")
            
            # Also log key information
            if error:
                logger.error(f"[DEBUG] API call failed - Provider: {api_provider}, Model: {model}, Error: {str(error)}")
                logger.error(f"[DEBUG] Request URL: {request_data.get('url', 'N/A')}")
                logger.error(f"[DEBUG] Request headers keys: {list(request_data.get('headers', {}).keys())}")
                logger.error(f"[DEBUG] Request data keys: {list(request_data.get('data', {}).keys())}")
            else:
                logger.info(f"[DEBUG] API call succeeded - Provider: {api_provider}, Model: {model}")
                
        except Exception as e:
            logger.error(f"[DEBUG] Failed to save debug data: {str(e)}")
    
    async def call_structured_api(self, prompt: str, schema: Dict, model: Union[str, List[str]] = "claude-3-5-sonnet-20241022", 
                                 tool_name: str = "structured_response", use_cache: bool = True, 
                                 context: str = "") -> Dict:
        """
        Call AI API with structured output using JSON response format.
        
        Args:
            prompt: The prompt to send to the AI
            schema: JSON schema for the expected response structure
            model: The model to use (string) or list of models to try in sequence
            tool_name: Name of the tool for structured output (legacy parameter, now ignored)
            use_cache: Whether to use caching
            context: Additional context for cache key generation
            
        Returns:
            Dict containing the structured response and metadata
        """
        call_start_time = datetime.now()
        
        # Convert single model to list and auto-add backup models
        if isinstance(model, str):
            models_to_try = [model]
            # Auto-add next 2 models from hierarchy as backup
            backup_models = self._get_backup_models(model, 2)
            models_to_try.extend(backup_models)
            logger.info(f"Auto-selected backup models for {model}: {backup_models}")
        else:
            models_to_try = model
        
        logger.info(f"STRUCTURED_API_CALL: Starting call with {len(models_to_try)} model(s): {models_to_try}, "
                   f"use_cache: {use_cache}, context: '{context[:50]}...', "
                   f"prompt_length: {len(prompt)}, schema_keys: {list(schema.keys()) if schema else 'None'}")
        
        last_error = None
        
        # Try each model once in sequence
        for model_index, current_model in enumerate(models_to_try):
            try:
                logger.info(f"[MODEL_TRY] Attempting model {model_index + 1}/{len(models_to_try)}: {current_model}")
                
                # Normalize model for current provider
                api_provider = self._determine_api_provider(current_model)
                current_model_normalized = self._normalize_anthropic_model(current_model)
                
                # Generate cache key for this specific model
                cache_key = self._get_cache_key(prompt, current_model_normalized, schema, context) if use_cache else None
                
                # Check cache for this specific model
                if use_cache and cache_key:
                    cached_data = await self._check_cache(cache_key, api_provider)
                    if cached_data:
                        logger.info(f"[CACHE_HIT] Using cached response for model {current_model}")
                        token_usage = cached_data.get('token_usage', {})
                        # Normalize legacy cached token usage for Perplexity
                        if token_usage.get('api_provider') == 'perplexity':
                            if 'input_tokens' not in token_usage and 'prompt_tokens' in token_usage:
                                token_usage['input_tokens'] = token_usage['prompt_tokens']
                            if 'output_tokens' not in token_usage and 'completion_tokens' in token_usage:
                                token_usage['output_tokens'] = token_usage['completion_tokens']
                        
                        return {
                            'response': cached_data['api_response'],
                            'token_usage': token_usage,
                            'processing_time': cached_data.get('processing_time', 0),
                            'is_cached': True,
                            'model_used': current_model
                        }
                
                # Make API call based on provider
                if api_provider == 'anthropic':
                    # Anthropic API call
                    headers = {
                        'Content-Type': 'application/json',
                        'X-API-Key': self.anthropic_api_key,
                        'anthropic-version': '2023-06-01'
                    }
                    
                    data = {
                        "model": current_model_normalized,
                        "max_tokens": 8000,
                        "temperature": 0.1,
                        "messages": [{"role": "user", "content": prompt}],
                        "tools": [{
                            "name": tool_name,
                            "description": f"Provide structured response using {tool_name}",
                            "input_schema": schema
                        }],
                        "tool_choice": {"type": "tool", "name": tool_name}
                    }
                    
                    result = await self._make_single_anthropic_call("https://api.anthropic.com/v1/messages", 
                                                                   headers, data, current_model_normalized, 
                                                                   use_cache, cache_key, call_start_time)
                    
                elif api_provider == 'perplexity':
                    # Perplexity API call for structured output
                    result = await self._make_single_perplexity_structured_call(prompt, schema, current_model,
                                                                               use_cache, cache_key, call_start_time)
                else:
                    logger.warning(f"[SKIP] Unknown provider for model {current_model}")
                    continue
                
                # If we got a result, add model info and return it
                if result:
                    result['model_used'] = current_model
                    result['used_backup_model'] = model_index > 0
                    logger.info(f"[SUCCESS] Model {current_model} succeeded")
                    return result
                    
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"[FAILED] Model {current_model} failed: {error_msg}")
                last_error = e
                
                # If this is a 529 overload, try next model. For other errors, continue trying too.
                if "overloaded" in error_msg and "529" in error_msg:
                    logger.info(f"[OVERLOAD] Model {current_model} overloaded, trying next model")
                    continue
                elif model_index == len(models_to_try) - 1:
                    # This was the last model, re-raise the error
                    raise
                else:
                    # Try next model for any error
                    continue
        
        # If we get here, all models failed
        if last_error:
            raise last_error
        else:
            raise Exception("All models failed - no specific error captured")
    
    async def call_text_api(self, prompt: str, model: Union[str, List[str]] = "claude-3-5-sonnet-20241022", 
                           use_cache: bool = True, context: str = "") -> Dict:
        """
        Call AI API for text response.
        
        Args:
            prompt: The prompt to send to the AI
            model: The model to use (string) or list of models to try in sequence
            use_cache: Whether to use caching
            context: Additional context for cache key generation
            
        Returns:
            Dict containing the text response and metadata
        """
        normalized_model = self._normalize_anthropic_model(model)
        cache_key = self._get_cache_key(prompt, normalized_model, None, context) if use_cache else None
        
        # Check cache first
        if use_cache and cache_key:
            cached_data = await self._check_cache(cache_key, 'anthropic')
            if cached_data:
                token_usage = cached_data.get('token_usage', {})
                # Debug log the cached token usage structure
                logger.info(f"DEBUG: Cached token usage keys: {list(token_usage.keys())}")
                logger.info(f"DEBUG: Cached token usage api_provider: {token_usage.get('api_provider')}")
                logger.info(f"DEBUG: Cached token usage input_tokens: {token_usage.get('input_tokens')}")
                logger.info(f"DEBUG: Cached token usage prompt_tokens: {token_usage.get('prompt_tokens')}")
                
                # Normalize legacy cached token usage for Perplexity
                if token_usage.get('api_provider') == 'perplexity':
                    if 'input_tokens' not in token_usage and 'prompt_tokens' in token_usage:
                        token_usage['input_tokens'] = token_usage['prompt_tokens']
                        logger.info(f"DEBUG: Fixed input_tokens: {token_usage['input_tokens']}")
                    if 'output_tokens' not in token_usage and 'completion_tokens' in token_usage:
                        token_usage['output_tokens'] = token_usage['completion_tokens']
                        logger.info(f"DEBUG: Fixed output_tokens: {token_usage['output_tokens']}")
                    
                    logger.info(f"DEBUG: Final token usage: input={token_usage.get('input_tokens')}, output={token_usage.get('output_tokens')}, total={token_usage.get('total_tokens')}")
                
                return {
                    'response': cached_data['api_response'],
                    'token_usage': token_usage,
                    'processing_time': cached_data.get('processing_time', 0),
                    'is_cached': True
                }
        
        # Make API call
        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': self.anthropic_api_key,
            'anthropic-version': '2023-06-01'
        }
        
        data = {
            "model": normalized_model,
            "max_tokens": 4000,
            "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        start_time = datetime.now()
        
        return await self._make_claude_api_call_with_retry("https://api.anthropic.com/v1/messages", headers, data, 
                                                         normalized_model, use_cache, cache_key, start_time)
    
    async def validate_with_perplexity_smart_cache(self, prompt: str, row_data: Dict, targets: List,
                                                 model: str = "sonar-pro", search_context_size: str = "low", 
                                                 use_cache: bool = True, config_hash: str = "") -> Dict:
        """
        Validate with Perplexity using smart caching that ignores validation history.
        This allows cache hits between preview and full validation runs.
        """
        cache_key = self._get_validation_cache_key(row_data, targets, model, search_context_size, config_hash) if use_cache else None
        
        # Check cache first
        if use_cache and cache_key:
            cached_data = await self._check_cache(cache_key, 'perplexity')
            if cached_data:
                logger.info(f"Smart cache hit for validation key: {cache_key[:8]}... (row: {list(row_data.keys())[:2]})")
                token_usage = cached_data.get('token_usage', {})
                # Debug log the cached token usage structure
                logger.info(f"DEBUG: Cached token usage keys: {list(token_usage.keys())}")
                logger.info(f"DEBUG: Cached token usage api_provider: {token_usage.get('api_provider')}")
                logger.info(f"DEBUG: Cached token usage input_tokens: {token_usage.get('input_tokens')}")
                logger.info(f"DEBUG: Cached token usage prompt_tokens: {token_usage.get('prompt_tokens')}")
                
                # Normalize legacy cached token usage for Perplexity
                if token_usage.get('api_provider') == 'perplexity':
                    if 'input_tokens' not in token_usage and 'prompt_tokens' in token_usage:
                        token_usage['input_tokens'] = token_usage['prompt_tokens']
                        logger.info(f"DEBUG: Fixed input_tokens: {token_usage['input_tokens']}")
                    if 'output_tokens' not in token_usage and 'completion_tokens' in token_usage:
                        token_usage['output_tokens'] = token_usage['completion_tokens']
                        logger.info(f"DEBUG: Fixed output_tokens: {token_usage['output_tokens']}")
                    
                    logger.info(f"DEBUG: Final token usage: input={token_usage.get('input_tokens')}, output={token_usage.get('output_tokens')}, total={token_usage.get('total_tokens')}")
                
                return {
                    'response': cached_data['api_response'],
                    'token_usage': token_usage,
                    'processing_time': cached_data.get('processing_time', 0),
                    'is_cached': True
                }
        
        # Make API call using the standard method
        result = await self.validate_with_perplexity(prompt, model, search_context_size, use_cache=False, context="")
        
        # Cache using the smart key instead of prompt-based key
        if use_cache and cache_key and not result.get('is_cached'):
            await self._save_to_cache(cache_key, result['response'], result['token_usage'], result['processing_time'], model, 'perplexity')
            logger.info(f"Smart cached validation key: {cache_key[:8]}... (row: {list(row_data.keys())[:2]})")
        
        return result
    
    async def validate_with_perplexity(self, prompt: str, model: str = "sonar-pro", 
                                     search_context_size: str = "low", use_cache: bool = True, 
                                     context: str = "") -> Dict:
        """
        Validate a prompt using Perplexity API.
        
        Args:
            prompt: The prompt to send to Perplexity
            model: The Perplexity model to use
            search_context_size: Search context size (low/high)
            use_cache: Whether to use caching
            context: Additional context for cache key generation
            
        Returns:
            Dict containing the validation response and metadata
        """
        cache_key = self._get_cache_key(prompt, model, None, f"{context}:{search_context_size}") if use_cache else None
        
        # Check cache first
        if use_cache and cache_key:
            cached_data = await self._check_cache(cache_key, 'perplexity')
            if cached_data:
                token_usage = cached_data.get('token_usage', {})
                # Debug log the cached token usage structure
                logger.info(f"DEBUG: Cached token usage keys: {list(token_usage.keys())}")
                logger.info(f"DEBUG: Cached token usage api_provider: {token_usage.get('api_provider')}")
                logger.info(f"DEBUG: Cached token usage input_tokens: {token_usage.get('input_tokens')}")
                logger.info(f"DEBUG: Cached token usage prompt_tokens: {token_usage.get('prompt_tokens')}")
                
                # Normalize legacy cached token usage for Perplexity
                if token_usage.get('api_provider') == 'perplexity':
                    if 'input_tokens' not in token_usage and 'prompt_tokens' in token_usage:
                        token_usage['input_tokens'] = token_usage['prompt_tokens']
                        logger.info(f"DEBUG: Fixed input_tokens: {token_usage['input_tokens']}")
                    if 'output_tokens' not in token_usage and 'completion_tokens' in token_usage:
                        token_usage['output_tokens'] = token_usage['completion_tokens']
                        logger.info(f"DEBUG: Fixed output_tokens: {token_usage['output_tokens']}")
                    
                    logger.info(f"DEBUG: Final token usage: input={token_usage.get('input_tokens')}, output={token_usage.get('output_tokens')}, total={token_usage.get('total_tokens')}")
                
                return {
                    'response': cached_data['api_response'],
                    'token_usage': token_usage,
                    'processing_time': cached_data.get('processing_time', 0),
                    'is_cached': True
                }
        
        # Make API call
        headers = {
            "Authorization": f"Bearer {self.perplexity_api_key}",
            "Content-Type": "application/json"
        }
        
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
        
        # Prepare debug request data
        debug_request = {
            'url': "https://api.perplexity.ai/chat/completions",
            'headers': {k: v if k != 'Authorization' else 'Bearer REDACTED' for k, v in headers.items()},
            'data': data
        }
        
        start_time = datetime.now()
        
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=60)
                async with session.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=timeout
                ) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    
                    if response.status == 200:
                        response_json = await response.json()
                        
                        # Save debug data for successful call
                        await self._save_debug_data('perplexity', model, debug_request, 
                                                  response_json, context=f"search_context_{search_context_size}")
                        
                        token_usage = self._extract_token_usage(response_json, model, search_context_size)
                        
                        # Log token usage
                        logger.info(f"Perplexity API Token Usage - Input: {token_usage['input_tokens']}, "
                                   f"Output: {token_usage['output_tokens']}, "
                                   f"Total: {token_usage['total_tokens']}")
                        
                        # Cache the response
                        if use_cache and cache_key:
                            await self._save_to_cache(cache_key, response_json, token_usage, processing_time, model, 'perplexity')
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False
                        }
                    else:
                        error_text = await response.text()
                        if response.status == 429:
                            error = Exception(f"Perplexity API rate limit exceeded (429): {error_text}")
                        elif response.status == 499:
                            error = Exception(f"Perplexity API client disconnected (499): {error_text}")
                        else:
                            error = Exception(f"Perplexity API returned status {response.status}: {error_text}")
                        
                        # Save debug data for error
                        await self._save_debug_data('perplexity', model, debug_request, 
                                                  error_text, error=error, context=f"search_context_{search_context_size}_status_{response.status}")
                        raise error
                        
        except asyncio.TimeoutError as e:
            logger.error(f"Perplexity API timeout error: {str(e)}")
            timeout_error = Exception(f"Perplexity API timeout: {str(e)}")
            await self._save_debug_data('perplexity', model, debug_request, 
                                      None, error=timeout_error, context=f"search_context_{search_context_size}_timeout")
            raise timeout_error
        except aiohttp.ClientError as e:
            logger.error(f"Perplexity API client error: {str(e)}")
            client_error = Exception(f"Perplexity API client error: {str(e)}")
            await self._save_debug_data('perplexity', model, debug_request, 
                                      None, error=client_error, context=f"search_context_{search_context_size}_client_error")
            raise client_error
        except Exception as e:
            logger.error(f"Error calling Perplexity API: {str(e)}")
            await self._save_debug_data('perplexity', model, debug_request, 
                                      None, error=e, context=f"search_context_{search_context_size}_exception")
            raise
    
    def extract_structured_response(self, response: Dict, tool_name: str = "structured_response") -> Dict:
        """Extract structured data from Claude's tool use response."""
        try:
            # For tool use, the structured data is in the tool_use content
            for content_item in response.get('content', []):
                if content_item.get('type') == 'tool_use' and content_item.get('name') == tool_name:
                    return content_item.get('input', {})
            
            # Fallback: extract from text
            for content_item in response.get('content', []):
                if content_item.get('type') == 'text':
                    text = content_item.get('text', '')
                    if '{' in text and '}' in text:
                        start = text.find('{')
                        end = text.rfind('}') + 1
                        return json.loads(text[start:end])
            
            raise ValueError("Could not extract structured response from Claude output")
            
        except Exception as e:
            logger.error(f"Failed to extract structured response: {str(e)}")
            raise
    
    def extract_text_response(self, response: Dict) -> str:
        """Extract text content from Claude's response."""
        try:
            content = ""
            for item in response.get('content', []):
                if item.get('type') == 'text':
                    content += item.get('text', '')
            return content
        except Exception as e:
            logger.error(f"Failed to extract text response: {str(e)}")
            raise

    async def _make_claude_api_call_with_retry(self, url: str, headers: Dict, data: Dict, 
                                             normalized_model: str, use_cache: bool, 
                                             cache_key: str, start_time: datetime) -> Dict:
        """Make Claude API call with retry logic for 529 overload errors."""
        max_retries = 3
        base_delay = 2.0
        
        # Prepare debug request data
        debug_request = {
            'url': url,
            'headers': {k: v if k != 'X-API-Key' else 'REDACTED' for k, v in headers.items()},
            'data': data
        }
        
        for attempt in range(max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=data) as response:
                        processing_time = (datetime.now() - start_time).total_seconds()
                        response_text = await response.text()
                        
                        if response.status == 200:
                            response_json = json.loads(response_text)
                            
                            # Save debug data for successful call
                            await self._save_debug_data('anthropic', normalized_model, debug_request, 
                                                      response_json, context=f"attempt_{attempt}")
                            
                            token_usage = self._extract_token_usage(response_json, normalized_model)
                            
                            # Log token usage
                            logger.info(f"Claude API Token Usage - Input: {token_usage['input_tokens']}, "
                                       f"Output: {token_usage['output_tokens']}, "
                                       f"Cache Creation: {token_usage['cache_creation_tokens']}, "
                                       f"Cache Read: {token_usage['cache_read_tokens']}, "
                                       f"Total: {token_usage['total_tokens']}")
                            
                            # Cache the response
                            if use_cache and cache_key:
                                await self._save_to_cache(cache_key, response_json, token_usage, processing_time, normalized_model, 'anthropic')
                            
                            if attempt > 0:
                                logger.info(f"[SUCCESS] Claude API call succeeded on attempt {attempt + 1}")
                            
                            return {
                                'response': response_json,
                                'token_usage': token_usage,
                                'processing_time': processing_time,
                                'is_cached': False
                            }
                        elif response.status == 529:
                            if attempt < max_retries:
                                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                                logger.warning(f"[ERROR] Claude API overloaded (529) on attempt {attempt + 1}/{max_retries + 1}. "
                                             f"Retrying in {delay:.1f}s. Error: {response_text}")
                                await asyncio.sleep(delay)
                                continue
                            else:
                                logger.error(f"[ERROR] Claude API overloaded (529) - max retries exceeded. Error: {response_text}")
                                error = Exception(f"Claude API overloaded after {max_retries} retries (529): {response_text}")
                                await self._save_debug_data('anthropic', normalized_model, debug_request, 
                                                          response_text, error=error, context=f"attempt_{attempt}_status_{response.status}")
                                raise error
                        else:
                            if response.status == 429:
                                error = Exception(f"Claude API rate limit exceeded (429): {response_text}")
                            elif response.status == 499:
                                error = Exception(f"Claude API client disconnected (499): {response_text}")
                            else:
                                error = Exception(f"Claude API returned status {response.status}: {response_text}")
                            
                            await self._save_debug_data('anthropic', normalized_model, debug_request, 
                                                      response_text, error=error, context=f"attempt_{attempt}_status_{response.status}")
                            raise error
                        
            except Exception as e:
                if "overloaded after" in str(e) or "rate limit" in str(e) or "client disconnected" in str(e):
                    raise
                logger.error(f"Error calling Claude API on attempt {attempt + 1}: {str(e)}")
                
                # Save debug data for unexpected errors
                await self._save_debug_data('anthropic', normalized_model, debug_request, 
                                          None, error=e, context=f"attempt_{attempt}_exception")
                
                if attempt == max_retries:
                    raise
                
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Retrying Claude API call in {delay:.1f}s...")
                await asyncio.sleep(delay)
    
    async def _make_single_anthropic_call(self, url: str, headers: Dict, data: Dict, 
                                         normalized_model: str, use_cache: bool, 
                                         cache_key: str, start_time: datetime) -> Dict:
        """Make a single Anthropic API call without retries."""
        debug_request = {
            'url': url,
            'headers': {k: v if k != 'X-API-Key' else 'REDACTED' for k, v in headers.items()},
            'data': data
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    response_text = await response.text()
                    
                    if response.status == 200:
                        response_json = json.loads(response_text)
                        
                        # Save debug data for successful call
                        await self._save_debug_data('anthropic', normalized_model, debug_request, 
                                                  response_json, context="single_call_success")
                        
                        token_usage = self._extract_token_usage(response_json, normalized_model)
                        
                        # Cache the response
                        if use_cache and cache_key:
                            await self._save_to_cache(cache_key, response_json, token_usage, processing_time, normalized_model, 'anthropic')
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False
                        }
                    else:
                        error = Exception(f"Anthropic API returned status {response.status}: {response_text}")
                        await self._save_debug_data('anthropic', normalized_model, debug_request, 
                                                  response_text, error=error, context=f"single_call_status_{response.status}")
                        raise error
                        
        except Exception as e:
            await self._save_debug_data('anthropic', normalized_model, debug_request, 
                                      None, error=e, context="single_call_exception")
            raise
    
    async def _make_single_perplexity_structured_call(self, prompt: str, schema: Dict, model: str,
                                                     use_cache: bool, cache_key: str, start_time: datetime) -> Dict:
        """Make a single Perplexity API call for structured output."""
        # Perplexity supports structured output via response_format
        headers = {
            "Authorization": f"Bearer {self.perplexity_api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Return your answer in valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 8000,
            "response_format": {
                "type": "json_object",
                "schema": schema
            },
            "web_search_options": {
                "search_context_size": "low"  # Default to low for structured calls
            }
        }
        
        debug_request = {
            'url': "https://api.perplexity.ai/chat/completions",
            'headers': {k: v if k != 'Authorization' else 'Bearer REDACTED' for k, v in headers.items()},
            'data': data
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=60)
                async with session.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=timeout
                ) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    
                    if response.status == 200:
                        response_json = await response.json()
                        
                        # Save debug data for successful call
                        await self._save_debug_data('perplexity', model, debug_request, 
                                                  response_json, context="structured_call_success")
                        
                        token_usage = self._extract_token_usage(response_json, model, "low")
                        
                        # Cache the response
                        if use_cache and cache_key:
                            await self._save_to_cache(cache_key, response_json, token_usage, processing_time, model, 'perplexity')
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False
                        }
                    else:
                        error_text = await response.text()
                        error = Exception(f"Perplexity API returned status {response.status}: {error_text}")
                        await self._save_debug_data('perplexity', model, debug_request, 
                                                  error_text, error=error, context=f"structured_call_status_{response.status}")
                        raise error
                        
        except asyncio.TimeoutError as e:
            timeout_error = Exception(f"Perplexity API timeout: {str(e)}")
            await self._save_debug_data('perplexity', model, debug_request, 
                                      None, error=timeout_error, context="structured_call_timeout")
            raise timeout_error
        except Exception as e:
            await self._save_debug_data('perplexity', model, debug_request, 
                                      None, error=e, context="structured_call_exception")
            raise

# Global instance for easy import
ai_client = AIAPIClient()