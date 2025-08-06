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
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from perplexity_schema import get_response_format_schema

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIAPIClient:
    """Shared AI API client with caching and schema support."""
    
    def __init__(self, s3_bucket: str = None):
        self.s3_bucket = s3_bucket or os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
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
    
    def _get_cache_key(self, prompt: str, model: str, schema: Dict = None, context: str = "") -> str:
        """Generate a unique cache key for the request."""
        schema_str = json.dumps(schema, sort_keys=True) if schema else ""
        cache_input = f"{prompt}:{model}:{schema_str}:{context}"
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
    
    async def _check_cache(self, cache_key: str, api_provider: str = 'claude') -> Optional[Dict]:
        """Check if response is cached."""
        try:
            cache_prefix = 'claude_cache' if api_provider == 'anthropic' else 'validation_cache'
            cache_response = self.s3_client.get_object(
                Bucket=self.s3_bucket,
                Key=f"{cache_prefix}/{cache_key}.json"
            )
            cached_data = json.loads(cache_response['Body'].read())
            logger.info(f"Cache hit for key: {cache_key[:8]}...")
            return cached_data
        except Exception as e:
            logger.info(f"Cache miss for key: {cache_key[:8]}...")
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
            
            cache_prefix = 'claude_cache' if api_provider == 'anthropic' else 'validation_cache'
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=f"{cache_prefix}/{cache_key}.json",
                Body=json.dumps(cache_entry),
                ContentType='application/json'
            )
            logger.info(f"Cached API response, key: {cache_key[:8]}...")
        except Exception as e:
            logger.error(f"Failed to cache API response: {str(e)}")
    
    async def call_structured_api(self, prompt: str, schema: Dict, model: str = "claude-3-5-sonnet-20241022", 
                                 tool_name: str = "structured_response", use_cache: bool = True, 
                                 context: str = "") -> Dict:
        """
        Call Claude API with structured output using JSON response format.
        
        Args:
            prompt: The prompt to send to Claude
            schema: JSON schema for the expected response structure
            model: The Claude model to use
            tool_name: Name of the tool for structured output (legacy parameter, now ignored)
            use_cache: Whether to use caching
            context: Additional context for cache key generation
            
        Returns:
            Dict containing the structured response and metadata
        """
        normalized_model = self._normalize_anthropic_model(model)
        cache_key = self._get_cache_key(prompt, normalized_model, schema, context) if use_cache else None
        
        # Check cache first
        if use_cache and cache_key:
            cached_data = await self._check_cache(cache_key, 'anthropic')
            if cached_data:
                return {
                    'response': cached_data['api_response'],
                    'token_usage': cached_data.get('token_usage', {}),
                    'processing_time': cached_data.get('processing_time', 0),
                    'is_cached': True
                }
        
        # Make API call with fallback strategy
        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': self.anthropic_api_key,
            'anthropic-version': '2023-06-01'
        }
        
        # Use tool use approach (response_format not supported by Claude API)
        data = {
            "model": normalized_model,
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
        
        # EXTENSIVE DEBUG LOGGING - LOG THE COMPLETE REQUEST
        logger.info("=== CLAUDE API REQUEST DEBUG ===")
        logger.info(f"Model: {normalized_model}")
        logger.info(f"Tool name: {tool_name}")
        logger.info(f"Prompt length: {len(prompt)} characters")
        logger.info(f"Schema keys: {list(schema.keys()) if schema else 'None'}")
        
        # Log the complete schema being sent
        schema_json = json.dumps(schema, indent=2)
        logger.info(f"Complete input_schema being sent to Claude:")
        logger.info(f"Schema length: {len(schema_json)} characters")
        logger.info(schema_json)
        
        # Check for problematic patterns in the actual schema being sent
        problematic_patterns = ['minItems', 'minLength', 'minimum', 'maximum', '$schema']
        found_patterns = [pattern for pattern in problematic_patterns if pattern in schema_json]
        if found_patterns:
            logger.error(f"PROBLEMATIC SCHEMA PATTERNS FOUND: {found_patterns}")
        else:
            logger.info("Schema appears clean (no problematic patterns)")
        
        # Log the complete request structure (without API key)
        debug_data = data.copy()
        debug_headers = headers.copy()
        debug_headers['X-API-Key'] = '***REDACTED***'
        logger.info(f"Complete request headers: {json.dumps(debug_headers, indent=2)}")
        logger.info(f"Complete request data: {json.dumps(debug_data, indent=2)}")
        logger.info("=== END CLAUDE API REQUEST DEBUG ===")
        
        start_time = datetime.now()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.anthropic.com/v1/messages", 
                                       headers=headers, json=data) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    
                    if response.status == 200:
                        response_json = await response.json()
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
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False
                        }
                    else:
                        error_text = await response.text()
                        if response.status == 429:
                            raise Exception(f"Claude API rate limit exceeded (429): {error_text}")
                        elif response.status == 499:
                            raise Exception(f"Claude API client disconnected (499): {error_text}")
                        else:
                            raise Exception(f"Claude API returned status {response.status}: {error_text}")
                        
        except Exception as e:
            logger.error(f"Error calling Claude API: {str(e)}")
            raise
    
    async def call_text_api(self, prompt: str, model: str = "claude-3-5-sonnet-20241022", 
                           use_cache: bool = True, context: str = "") -> Dict:
        """
        Call Claude API for text response.
        
        Args:
            prompt: The prompt to send to Claude
            model: The Claude model to use
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
                return {
                    'response': cached_data['api_response'],
                    'token_usage': cached_data.get('token_usage', {}),
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
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.anthropic.com/v1/messages", 
                                       headers=headers, json=data) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    
                    if response.status == 200:
                        response_json = await response.json()
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
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False
                        }
                    else:
                        error_text = await response.text()
                        if response.status == 429:
                            raise Exception(f"Claude API rate limit exceeded (429): {error_text}")
                        elif response.status == 499:
                            raise Exception(f"Claude API client disconnected (499): {error_text}")
                        else:
                            raise Exception(f"Claude API returned status {response.status}: {error_text}")
                        
        except Exception as e:
            logger.error(f"Error calling Claude API: {str(e)}")
            raise
    
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
                return {
                    'response': cached_data['api_response'],
                    'token_usage': cached_data.get('token_usage', {}),
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
                            raise Exception(f"Perplexity API rate limit exceeded (429): {error_text}")
                        elif response.status == 499:
                            raise Exception(f"Perplexity API client disconnected (499): {error_text}")
                        else:
                            raise Exception(f"Perplexity API returned status {response.status}: {error_text}")
                        
        except asyncio.TimeoutError as e:
            logger.error(f"Perplexity API timeout error: {str(e)}")
            raise Exception(f"Perplexity API timeout: {str(e)}")
        except aiohttp.ClientError as e:
            logger.error(f"Perplexity API client error: {str(e)}")
            raise Exception(f"Perplexity API client error: {str(e)}")
        except Exception as e:
            logger.error(f"Error calling Perplexity API: {str(e)}")
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

# Global instance for easy import
ai_client = AIAPIClient()