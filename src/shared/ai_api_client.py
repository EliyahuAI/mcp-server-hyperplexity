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
import aioboto3
import asyncio
import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
from decimal import Decimal
from perplexity_schema import get_response_format_schema
from model_config_table import ModelConfigTable
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
        "claude-sonnet-4-5",
        "claude-sonnet-4-0",
        "sonar-pro",
        "claude-3-7-sonnet-latest",
        "sonar",
        "claude-3-5-haiku-latest"
    ]

    # Token limits now retrieved from model configuration database
    
    def __init__(self, s3_bucket: str = None):
        # Check for dedicated cache bucket first (shared across all environments)
        cache_bucket = os.environ.get('S3_CACHE_BUCKET')
        if cache_bucket:
            self.s3_bucket = cache_bucket
            self.use_unified_structure = True
            logger.info(f"AI_API_CLIENT: Using shared cache bucket: {cache_bucket}")
        elif os.environ.get('S3_UNIFIED_BUCKET'):
            # Fallback to unified bucket structure
            self.unified_bucket = os.environ.get('S3_UNIFIED_BUCKET')
            self.s3_bucket = self.unified_bucket
            self.use_unified_structure = True
            logger.info(f"AI_API_CLIENT: Using unified S3 bucket: {self.unified_bucket}")
        else:
            # Legacy fallback
            self.s3_bucket = s3_bucket or 'perplexity-cache'
            self.use_unified_structure = False
            logger.info(f"AI_API_CLIENT: Using legacy S3 bucket: {self.s3_bucket}")

        # Use aioboto3 for async S3 operations (non-blocking event loop)
        self.s3_session = aioboto3.Session()
        # Keep boto3 client for non-async operations (SSM parameter retrieval)
        self.anthropic_api_key = self._get_anthropic_api_key()
        self.perplexity_api_key = self._get_perplexity_api_key()

        # Initialize model configuration table for dynamic token limits
        self.model_config_table = ModelConfigTable()
        self._token_limits_cache = {}  # Cache for token limits to avoid repeated DB calls
        self._pricing_data_cache = None # Cache for pricing data to avoid repeated DB calls
    
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

    def _enforce_provider_token_limit(self, model: str, requested_tokens: int) -> int:
        """
        Enforce model-specific maximum token limits from database configuration to prevent API errors.

        Args:
            model: The model name to check limits for
            requested_tokens: The originally requested max_tokens value

        Returns:
            int: The enforced token limit that won't exceed model maximums
        """
        if not requested_tokens or requested_tokens <= 0:
            return requested_tokens

        # Get model-specific token limit from database
        model_limit = self._get_model_token_limit(model)

        if model_limit and requested_tokens > model_limit:
            logger.warning(f"[TOKEN_LIMIT_ENFORCED] Model {model} requested {requested_tokens} tokens, "
                         f"but model limit is {model_limit}. Capping at {model_limit} tokens.")
            return model_limit

        return requested_tokens

    def _get_model_token_limit(self, model: str) -> Optional[int]:
        """
        Get the maximum token limit for a model from the configuration database.

        Args:
            model: The model name

        Returns:
            int: The max token limit for the model, or None if no limit is configured
        """
        # Check cache first
        if model in self._token_limits_cache:
            return self._token_limits_cache[model]

        try:
            # Get model configuration from database
            config = self.model_config_table.get_config_for_model(model)

            if config and config.get('max_tokens', 0) > 0:
                token_limit = int(config['max_tokens'])
                # Cache the result
                self._token_limits_cache[model] = token_limit
                logger.debug(f"Retrieved token limit for {model}: {token_limit}")
                return token_limit
            else:
                logger.warning(f"No token limit configured for model: {model}")
                # Cache the None result to avoid repeated DB calls
                self._token_limits_cache[model] = None
                return None

        except Exception as e:
            logger.error(f"Failed to get token limit for model {model}: {e}")
            return None

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
    
    def _get_cache_key(self, prompt: str, model: str, schema: Dict = None, context: str = "", max_web_searches: int = 3) -> str:
        """Generate a unique cache key for the request."""
        schema_str = json.dumps(schema, sort_keys=True) if schema else ""
        cache_input = f"{prompt}:{model}:{schema_str}:{context}:{max_web_searches}"
        cache_key = hashlib.md5(cache_input.encode()).hexdigest()
        
        # Log cache key components for debugging
        logger.info(f"Using cache key based on prompt hash: {hashlib.md5(prompt.encode()).hexdigest()[:8]}...")
        
        return cache_key
    
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
        """
        Extract token usage information from API response with robust validation and error handling.
        Centralized implementation used by both validation and config lambdas.
        """
        # Validate inputs
        if not isinstance(response, dict):
            logger.error(f"ai_api_client._extract_token_usage: Invalid response type {type(response)}, expected dict")
            return self._get_empty_token_usage(model)
        
        if not isinstance(model, str) or not model.strip():
            logger.error(f"ai_api_client._extract_token_usage: Invalid model '{model}', expected non-empty string")
            return self._get_empty_token_usage('unknown')
        
        # Check for usage data in response
        if 'usage' not in response:
            logger.warning(f"ai_api_client._extract_token_usage: No usage data in API response for model {model}")
            return self._get_empty_token_usage(model)
        
        usage = response['usage']
        if not isinstance(usage, dict):
            logger.error(f"ai_api_client._extract_token_usage: Invalid usage type {type(usage)}, expected dict")
            return self._get_empty_token_usage(model)
        
        try:
            api_provider = self._determine_api_provider(model)
            logger.debug(f"ai_api_client._extract_token_usage: Processing {api_provider} response for model {model}")
            
            if api_provider == 'anthropic':
                # Anthropic format: input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens
                input_tokens = max(0, int(usage.get('input_tokens', 0)))
                output_tokens = max(0, int(usage.get('output_tokens', 0)))
                cache_creation_tokens = max(0, int(usage.get('cache_creation_tokens', 0)))
                cache_read_tokens = max(0, int(usage.get('cache_read_tokens', 0)))
                total_tokens = input_tokens + output_tokens + cache_creation_tokens + cache_read_tokens
                
                # Validate token counts are reasonable
                if total_tokens > 10_000_000:  # 10M token sanity check
                    logger.warning(f"ai_api_client._extract_token_usage: Unusually high token count {total_tokens} for model {model}")
                
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
                prompt_tokens = max(0, int(usage.get('prompt_tokens', 0)))
                completion_tokens = max(0, int(usage.get('completion_tokens', 0)))
                reported_total = max(0, int(usage.get('total_tokens', 0)))
                
                # Calculate total tokens - use reported total if available, otherwise sum components
                if reported_total > 0:
                    total_tokens = reported_total
                    # Validate components match total (within reasonable tolerance)
                    calculated_total = prompt_tokens + completion_tokens
                    if calculated_total > 0 and abs(calculated_total - reported_total) > (calculated_total * 0.1):
                        logger.warning(f"ai_api_client._extract_token_usage: Token mismatch for {model}: reported={reported_total}, calculated={calculated_total}")
                else:
                    total_tokens = prompt_tokens + completion_tokens
                
                # Validate token counts are reasonable
                if total_tokens > 10_000_000:  # 10M token sanity check
                    logger.warning(f"ai_api_client._extract_token_usage: Unusually high token count {total_tokens} for model {model}")
                
                return {
                    'api_provider': 'perplexity',
                    'input_tokens': prompt_tokens,
                    'output_tokens': completion_tokens,
                    'cache_creation_tokens': 0,
                    'cache_read_tokens': 0,
                    'total_tokens': total_tokens,
                    'model': model,
                    'search_context_size': usage.get('search_context_size', search_context_size)
                }
                
        except (ValueError, TypeError) as e:
            logger.error(f"ai_api_client._extract_token_usage: Error parsing token data for model {model}: {e}")
            return self._get_empty_token_usage(model)
        except Exception as e:
            logger.error(f"ai_api_client._extract_token_usage: Unexpected error for model {model}: {e}")
            return self._get_empty_token_usage(model)
    
    def _get_empty_token_usage(self, model: str) -> Dict:
        """Return empty token usage structure with safe defaults."""
        try:
            api_provider = self._determine_api_provider(model)
        except:
            api_provider = 'unknown'
        
        return {
            'api_provider': api_provider,
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_creation_tokens': 0,
            'cache_read_tokens': 0,
            'total_tokens': 0,
            'model': model,
            'error': 'failed_token_extraction'
        }
    
    # ========== CENTRALIZED COST AND TIME CALCULATION SYSTEM ==========
    
    def load_pricing_data(self) -> Dict[str, Dict[str, float]]:
        """
        Centralized pricing data loader used by both validation and config lambdas.
        Load pricing data from DynamoDB model config table with robust fallbacks and validation.
        This method caches the pricing data in an instance variable to avoid repeated database calls.
        
        Returns:
            Dict mapping model patterns to pricing configurations with validated data
        """
        # Check instance cache first
        if self._pricing_data_cache is not None:
            logger.debug("ai_api_client.load_pricing_data: Returning cached pricing data")
            return self._pricing_data_cache

        import time
        import csv
        
        pricing_data = {}
        load_source = "none"
        
        # Robust default pricing for unknown models - production rates
        default_pricing = {
            'input_cost_per_million_tokens': 3.0,
            'output_cost_per_million_tokens': 15.0,
            'api_provider': 'unknown',
            'priority': 999
        }
        
        # Attempt to load from DynamoDB with multiple retry strategies
        for attempt in range(3):  # Up to 3 attempts
            try:
                # Try multiple import strategies
                config_table = None
                import_error = None
                
                for import_strategy in ['direct', 'shared', 'path_setup']:
                    try:
                        if import_strategy == 'direct':
                            from model_config_table import ModelConfigTable
                        elif import_strategy == 'shared':
                            from shared.model_config_table import ModelConfigTable
                        else:  # path_setup
                            import sys
                            sys.path.append('/var/task/shared')
                            from shared.model_config_table import ModelConfigTable
                        
                        config_table = ModelConfigTable()
                        break
                        
                    except ImportError as ie:
                        import_error = ie
                        continue
                
                if not config_table:
                    logger.warning(f"ai_api_client.load_pricing_data: Failed to import ModelConfigTable after all strategies: {import_error}")
                    break
                
                # Retrieve configurations with validation
                configs = config_table.list_all_configs()
                
                if configs and isinstance(configs, list):
                    loaded_count = 0
                    for config in configs:
                        try:
                            # Validate configuration data
                            if not isinstance(config, dict):
                                logger.warning(f"ai_api_client.load_pricing_data: Invalid config type {type(config)}, skipping")
                                continue
                                
                            if not config.get('enabled', False):
                                continue  # Skip disabled configurations
                            
                            model_pattern = config.get('model_pattern', '').strip()
                            if not model_pattern:
                                logger.warning(f"ai_api_client.load_pricing_data: Empty model_pattern in config, skipping")
                                continue
                            
                            # Validate and sanitize pricing data
                            try:
                                input_cost = float(config.get('input_cost_per_million_tokens', 3.0))
                                output_cost = float(config.get('output_cost_per_million_tokens', 15.0))
                                
                                # Sanity check pricing (reasonable bounds)
                                if input_cost < 0 or input_cost > 1000:
                                    logger.warning(f"ai_api_client.load_pricing_data: Suspicious input cost {input_cost} for {model_pattern}, using default")
                                    input_cost = 3.0
                                if output_cost < 0 or output_cost > 1000:
                                    logger.warning(f"ai_api_client.load_pricing_data: Suspicious output cost {output_cost} for {model_pattern}, using default")
                                    output_cost = 15.0
                                    
                            except (ValueError, TypeError) as e:
                                logger.warning(f"ai_api_client.load_pricing_data: Invalid pricing data for {model_pattern}: {e}, using defaults")
                                input_cost = 3.0
                                output_cost = 15.0
                            
                            # Validate priority
                            try:
                                priority = int(config.get('priority', 999))
                            except (ValueError, TypeError):
                                priority = 999
                            
                            pricing_data[model_pattern] = {
                                'api_provider': config.get('api_provider', 'unknown'),
                                'input_cost_per_million_tokens': input_cost,
                                'output_cost_per_million_tokens': output_cost,
                                'notes': config.get('notes', ''),
                                'priority': priority
                            }
                            loaded_count += 1
                            
                        except Exception as config_error:
                            logger.warning(f"ai_api_client.load_pricing_data: Error processing config: {config_error}")
                            continue
                    
                    if loaded_count > 0:
                        load_source = f"dynamodb_{loaded_count}_configs"
                        logger.debug(f"ai_api_client.load_pricing_data: Successfully loaded {loaded_count} pricing configurations from DynamoDB")
                        break
                    else:
                        logger.warning("ai_api_client.load_pricing_data: No valid configurations loaded from DynamoDB")
                        
                else:
                    logger.warning("ai_api_client.load_pricing_data: DynamoDB returned no configurations or invalid format")
                    
            except Exception as db_error:
                logger.warning(f"ai_api_client.load_pricing_data: DynamoDB attempt {attempt + 1} failed: {db_error}")
                if attempt < 2:  # Don't sleep on last attempt
                    time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                continue
            
            break  # Success - exit retry loop
        
        # Final fallback: ensure we have at least default pricing patterns
        if not pricing_data:
            logger.warning("ai_api_client.load_pricing_data: All sources failed, using hardcoded defaults")
            pricing_data = {
                'sonar*': {'api_provider': 'perplexity', 'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0, 'priority': 100},
                'claude*': {'api_provider': 'anthropic', 'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0, 'priority': 100},
                '*': {'api_provider': 'unknown', 'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0, 'priority': 999}
            }
            load_source = "hardcoded_defaults"
        
        # Always ensure fallback exists
        if '*' not in pricing_data:
            pricing_data['*'] = default_pricing

        # Log final status
        logger.debug(f"ai_api_client.load_pricing_data: Final result - {len(pricing_data)} patterns loaded from {load_source}")

        # Cache the result
        self._pricing_data_cache = pricing_data
        return self._pricing_data_cache
    
    def calculate_token_costs(self, token_usage: Dict[str, Any], pricing_data: Dict[str, Dict[str, float]] = None) -> Dict[str, float]:
        """
        Centralized cost calculation used by both validation and config lambdas.
        Calculate costs based on token usage and pricing data with robust validation and error handling.
        
        Args:
            token_usage: Dictionary containing token usage data from API response
            pricing_data: Optional pricing data dict (will load if not provided)
            
        Returns:
            Dictionary with input_cost, output_cost, total_cost, and validation metadata
        """
        # Input validation
        if not isinstance(token_usage, dict) or not token_usage:
            logger.warning("ai_api_client.calculate_token_costs: Empty or invalid token_usage")
            return {
                'input_cost': 0.0, 
                'output_cost': 0.0, 
                'total_cost': 0.0,
                'input_tokens': 0,
                'output_tokens': 0,
                'pricing_model': 'none',
                'error': 'invalid_token_usage'
            }
        
        
        # Load pricing data if not provided
        if not pricing_data:
            try:
                pricing_data = self.load_pricing_data()
            except Exception as e:
                logger.error(f"ai_api_client.calculate_token_costs: Failed to load pricing data: {e}")
                pricing_data = {}
        
        if not isinstance(pricing_data, dict) or not pricing_data:
            logger.error("ai_api_client.calculate_token_costs: Empty or invalid pricing_data")
            return {
                'input_cost': 0.0, 
                'output_cost': 0.0, 
                'total_cost': 0.0,
                'input_tokens': 0,
                'output_tokens': 0,
                'pricing_model': 'none',
                'error': 'invalid_pricing_data'
            }
        
        api_provider = token_usage.get('api_provider', 'unknown')
        model = token_usage.get('model', 'unknown')
        
        if not model or model == 'unknown':
            logger.warning("ai_api_client.calculate_token_costs: Missing or unknown model in token_usage")
        
        # Find pricing configuration with robust pattern matching
        pricing = None
        pricing_source = 'none'
        
        try:
            # Attempt 1: Try exact model match first
            if model in pricing_data:
                pricing = pricing_data[model]
                pricing_source = f'exact_match_{model}'
                logger.debug(f"ai_api_client.calculate_token_costs: Using exact pricing match for {model}")
            else:
                # Attempt 2: Pattern matching with priority sorting
                sorted_patterns = sorted(pricing_data.items(), key=lambda x: x[1].get('priority', 999))
                logger.debug(f"ai_api_client.calculate_token_costs: Testing {len(sorted_patterns)} pricing patterns for {model}")
                
                # Try pattern matching (for DynamoDB configs with wildcards)
                import re
                for pricing_pattern, pricing_config in sorted_patterns:
                    try:
                        # Convert glob pattern to regex
                        regex_pattern = pricing_pattern.replace('*', '.*')
                        regex_pattern = f"^{regex_pattern}$"
                        
                        match_result = re.match(regex_pattern, model, re.IGNORECASE)
                        
                        if match_result:
                            pricing = pricing_config
                            pricing_source = f'pattern_match_{pricing_pattern}'
                            logger.debug(f"ai_api_client.calculate_token_costs: Using pattern match '{pricing_pattern}' for {model}")
                            break
                            
                    except re.error as regex_error:
                        logger.warning(f"ai_api_client.calculate_token_costs: Invalid regex pattern '{pricing_pattern}': {regex_error}")
                        # Fallback to simple string matching for invalid regex
                        try:
                            if (pricing_pattern.lower() in model.lower() or 
                                model.lower() in pricing_pattern.lower()):
                                pricing = pricing_config
                                pricing_source = f'string_match_{pricing_pattern}'
                                logger.debug(f"ai_api_client.calculate_token_costs: Using string match '{pricing_pattern}' for {model}")
                                break
                        except Exception as string_error:
                            logger.warning(f"ai_api_client.calculate_token_costs: String matching failed for '{pricing_pattern}': {string_error}")
                            continue
                            
                    except Exception as pattern_error:
                        logger.warning(f"ai_api_client.calculate_token_costs: Pattern matching error for '{pricing_pattern}': {pattern_error}")
                        continue
                        
        except Exception as matching_error:
            logger.error(f"ai_api_client.calculate_token_costs: Critical error in pricing lookup: {matching_error}")
            pricing = None
        
        # Fallback to robust default pricing by provider
        if not pricing:
            logger.warning(f"ai_api_client.calculate_token_costs: No pricing found for model {model}, using default {api_provider} pricing")
            if api_provider == 'perplexity':
                pricing = {'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0}  # sonar-pro rates
                pricing_source = 'default_perplexity'
            elif api_provider == 'anthropic':
                pricing = {'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0}  # claude-4-sonnet rates
                pricing_source = 'default_anthropic'
            else:
                pricing = {'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0}  # universal fallback
                pricing_source = 'default_unknown'
        
        
        # Extract and validate token counts with robust error handling
        input_tokens = 0
        output_tokens = 0
        
        try:
            if api_provider == 'perplexity':
                # Primary: Use normalized tokens from ai_api_client
                input_tokens = max(0, int(token_usage.get('input_tokens', 0)))
                output_tokens = max(0, int(token_usage.get('output_tokens', 0)))
                
                # Fallback: Handle legacy format with prompt_tokens/completion_tokens
                if input_tokens == 0 and output_tokens == 0:
                    input_tokens = max(0, int(token_usage.get('prompt_tokens', 0)))
                    output_tokens = max(0, int(token_usage.get('completion_tokens', 0)))
                    
            elif api_provider == 'anthropic':
                input_tokens = max(0, int(token_usage.get('input_tokens', 0)))
                output_tokens = max(0, int(token_usage.get('output_tokens', 0)))
                # Note: cache tokens are typically free/discounted, not included in cost calculation
                
            else:
                # Unknown provider: try multiple strategies
                input_tokens = max(0, int(token_usage.get('input_tokens', 0)))
                output_tokens = max(0, int(token_usage.get('output_tokens', 0)))
                
                if input_tokens == 0 and output_tokens == 0:
                    # Fallback to legacy format
                    input_tokens = max(0, int(token_usage.get('prompt_tokens', 0)))
                    output_tokens = max(0, int(token_usage.get('completion_tokens', 0)))
                    
                if input_tokens == 0 and output_tokens == 0:
                    # Last resort: split total tokens evenly
                    total_tokens = max(0, int(token_usage.get('total_tokens', 0)))
                    input_tokens = total_tokens // 2
                    output_tokens = total_tokens - input_tokens  # Handle odd numbers
                    logger.warning(f"ai_api_client.calculate_token_costs: Using total_tokens split for unknown provider {api_provider}")
                    
        except (ValueError, TypeError) as token_error:
            logger.error(f"ai_api_client.calculate_token_costs: Error parsing token counts: {token_error}")
            input_tokens = 0
            output_tokens = 0
        
        
        # Validate extracted pricing configuration
        try:
            input_rate = float(pricing.get('input_cost_per_million_tokens', 3.0))
            output_rate = float(pricing.get('output_cost_per_million_tokens', 15.0))
            
            # Sanity check pricing rates
            if input_rate < 0 or input_rate > 1000:
                logger.warning(f"ai_api_client.calculate_token_costs: Suspicious input rate {input_rate}, using default 3.0")
                input_rate = 3.0
            if output_rate < 0 or output_rate > 1000:
                logger.warning(f"ai_api_client.calculate_token_costs: Suspicious output rate {output_rate}, using default 15.0")
                output_rate = 15.0
                
        except (ValueError, TypeError) as pricing_error:
            logger.error(f"ai_api_client.calculate_token_costs: Error parsing pricing rates: {pricing_error}")
            input_rate = 3.0
            output_rate = 15.0
        
        
        # Calculate costs with precision handling (pricing is per million tokens)
        try:
            # Use decimal arithmetic to avoid floating point precision issues
            from decimal import Decimal, ROUND_HALF_UP
            
            input_cost_decimal = (Decimal(str(input_tokens)) / Decimal('1000000')) * Decimal(str(input_rate))
            output_cost_decimal = (Decimal(str(output_tokens)) / Decimal('1000000')) * Decimal(str(output_rate))
            total_cost_decimal = input_cost_decimal + output_cost_decimal
            
            # Convert back to float with controlled precision
            input_cost = float(input_cost_decimal.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))
            output_cost = float(output_cost_decimal.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))
            total_cost = float(total_cost_decimal.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))
            
        except Exception as calc_error:
            logger.error(f"ai_api_client.calculate_token_costs: Error in cost calculation: {calc_error}")
            # Fallback to basic calculation
            input_cost = (input_tokens / 1_000_000) * input_rate
            output_cost = (output_tokens / 1_000_000) * output_rate
            total_cost = input_cost + output_cost
            
            # Round to 6 decimal places
            input_cost = round(input_cost, 6)
            output_cost = round(output_cost, 6)
            total_cost = round(total_cost, 6)

        # Log calculation details for debugging high-cost scenarios
        if total_cost > 1.0:  # Log expensive calls
            logger.debug(f"ai_api_client.calculate_token_costs: High cost calculation - Model: {model}, "
                       f"Input: {input_tokens} tokens (${input_cost:.6f}), "
                       f"Output: {output_tokens} tokens (${output_cost:.6f}), "
                       f"Total: ${total_cost:.6f}, Source: {pricing_source}")


        return {
            'input_cost': input_cost,
            'output_cost': output_cost, 
            'total_cost': total_cost,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'pricing_model': pricing.get('model_name', model),
            'pricing_source': pricing_source,
            'api_provider': api_provider
        }
    
    def calculate_processing_time_estimate(self, token_usage: Dict[str, Any], processing_time: float) -> Dict[str, float]:
        """
        Calculate time estimates for validation processing based on token usage and actual processing time.
        
        Args:
            token_usage: Dictionary containing token usage data
            processing_time: Actual processing time for this request in seconds
            
        Returns:
            Dictionary with time estimates and per-token timing data
        """
        try:
            # Extract token counts
            total_tokens = token_usage.get('total_tokens', 0)
            input_tokens = token_usage.get('input_tokens', 0)
            output_tokens = token_usage.get('output_tokens', 0)
            
            if total_tokens == 0:
                logger.warning("ai_api_client.calculate_processing_time_estimate: No tokens found in usage data")
                return {
                    'time_per_token': 0.0,
                    'time_per_input_token': 0.0,
                    'time_per_output_token': 0.0,
                    'estimated_time_per_1k_tokens': 0.0,
                    'processing_time': processing_time,
                    'error': 'no_tokens'
                }
            
            # Calculate per-token timing
            time_per_token = processing_time / total_tokens if total_tokens > 0 else 0.0
            time_per_input_token = processing_time / input_tokens if input_tokens > 0 else 0.0
            time_per_output_token = processing_time / output_tokens if output_tokens > 0 else 0.0
            
            # Useful metric: time per 1K tokens for scaling estimates
            estimated_time_per_1k_tokens = time_per_token * 1000
            
            return {
                'time_per_token': round(time_per_token, 6),
                'time_per_input_token': round(time_per_input_token, 6),
                'time_per_output_token': round(time_per_output_token, 6),
                'estimated_time_per_1k_tokens': round(estimated_time_per_1k_tokens, 3),
                'processing_time': round(processing_time, 3),
                'total_tokens': total_tokens
            }
            
        except Exception as e:
            logger.error(f"ai_api_client.calculate_processing_time_estimate: Error calculating time estimates: {e}")
            return {
                'time_per_token': 0.0,
                'time_per_input_token': 0.0,
                'time_per_output_token': 0.0,
                'estimated_time_per_1k_tokens': 0.0,
                'processing_time': processing_time,
                'error': str(e)
            }
    
    def get_enhanced_call_metrics(self, response: Dict, model: str, processing_time: float,
                                  search_context_size: str = None, batch_info: Dict = None,
                                  pre_extracted_token_usage: Dict = None, is_cached: bool = None,
                                  max_web_searches: int = None) -> Dict[str, Any]:
        """
        Enhanced elemental call tracking with comprehensive provider-specific metrics,
        caching analysis, and per-row cost calculations.

        Args:
            response: API response dictionary
            model: Model name used for the request
            processing_time: Actual processing time in seconds
            search_context_size: Context size for Perplexity API (optional)
            batch_info: Information about batch size and rows processed (optional)
            pre_extracted_token_usage: Pre-extracted token usage (for cached responses)
            is_cached: Whether this is a cached response
            max_web_searches: Maximum web searches used (for Anthropic extended thinking)

        Returns:
            Comprehensive call metrics including provider breakdown, caching efficiency, and per-row costs
        """
        try:
            # Extract basic token usage - use pre-extracted if available (for cached responses)
            if pre_extracted_token_usage:
                token_usage = pre_extracted_token_usage
                logger.debug(f"Using pre-extracted token usage for cached response: {token_usage.get('total_tokens', 0)} tokens")
            else:
                token_usage = self._extract_token_usage(response, model, search_context_size)
                
            api_provider = token_usage.get('api_provider', 'unknown')
            
            # Determine cache status using bulletproof single source of truth
            # Priority: 1) Explicit is_cached flag, 2) pre_extracted_token_usage presence
            cache_detected = is_cached if is_cached is not None else (pre_extracted_token_usage is not None)
            logger.debug(f"[CACHE_DETECTION_DEBUG] is_cached={is_cached}, pre_extracted_present={pre_extracted_token_usage is not None}, cache_detected={cache_detected}")
            
            # Calculate costs with and without caching
            if cache_detected:
                # For cached responses: actual cost is 0, estimated is what it would have cost
                logger.debug(f"[CACHE_COST_DEBUG] Cache detected - token_usage keys: {list(token_usage.keys())}, provider: {token_usage.get('api_provider')}")
                logger.debug(f"[CACHE_COST_DEBUG] Cache detected - input_tokens: {token_usage.get('input_tokens')}, output_tokens: {token_usage.get('output_tokens')}")
                cost_estimated = self.calculate_token_costs(token_usage)  # Original cost
                logger.debug(f"[CACHE_COST_DEBUG] calculate_token_costs returned: {cost_estimated}")
                cost_data = {  # Actual cost is 0 for cache hits
                    'input_cost': 0.0,
                    'output_cost': 0.0,
                    'total_cost': 0.0,
                    'pricing_source': 'cached_response'
                }
                logger.debug(f"[CACHE_COST_DEBUG] Cached response detected (is_cached={is_cached}, pre_extracted={pre_extracted_token_usage is not None}) - Actual: ${cost_data.get('total_cost', 0.0):.6f}, Estimated: ${cost_estimated.get('total_cost', 0.0):.6f}")
            else:
                # For fresh API calls: calculate normally
                cost_data = self.calculate_token_costs(token_usage)
                cost_estimated = self._calculate_cost_without_caching_benefits(token_usage, cost_data)
                logger.debug(f"[CACHE_COST_DEBUG] Fresh API call - Actual: ${cost_data.get('total_cost', 0.0):.6f}, Estimated: ${cost_estimated.get('total_cost', 0.0):.6f}")
            
            # Extract caching metrics
            caching_metrics = self._extract_caching_metrics(token_usage, response)
            
            # Calculate timing metrics (actual vs estimated without cache)
            # Pass bulletproof cache detection flag to ensure proper timing calculation
            timing_metrics = self._calculate_comprehensive_timing_metrics(
                token_usage, processing_time, caching_metrics, is_internal_cache=cache_detected
            )
            
            # Calculate per-row metrics
            per_row_metrics = self._calculate_per_row_metrics(
                cost_data, cost_estimated, timing_metrics, batch_info
            )
            
            # Build comprehensive metrics structure
            enhanced_metrics = {
                # Basic call information
                'call_info': {
                    'model': model,
                    'api_provider': api_provider,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'search_context_size': search_context_size,
                    'max_web_searches': max_web_searches if max_web_searches is not None else 0
                },
                
                # Token usage breakdown
                'tokens': {
                    'input_tokens': token_usage.get('input_tokens', 0),
                    'output_tokens': token_usage.get('output_tokens', 0),
                    'total_tokens': token_usage.get('total_tokens', 0),
                    'cache_creation_tokens': token_usage.get('cache_creation_tokens', 0),
                    'cache_read_tokens': token_usage.get('cache_read_tokens', 0)
                },
                
                # Cost breakdown with caching analysis
                'costs': {
                    # Actual costs (with caching benefits)
                    'actual': {
                        'input_cost': cost_data.get('input_cost', 0.0),
                        'output_cost': cost_data.get('output_cost', 0.0),
                        'total_cost': cost_data.get('total_cost', 0.0),
                        'pricing_source': cost_data.get('pricing_source', 'unknown')
                    },
                    # Estimated costs without caching benefits
                    'estimated': {
                        'input_cost': cost_estimated.get('input_cost', 0.0),
                        'output_cost': cost_estimated.get('output_cost', 0.0),
                        'total_cost': cost_estimated.get('total_cost', 0.0)
                    },
                    # Cost efficiency from caching
                    'cache_savings': {
                        'absolute_savings': cost_estimated.get('total_cost', 0.0) - cost_data.get('total_cost', 0.0),
                        'percentage_savings': self._calculate_percentage_savings(cost_data.get('total_cost', 0.0), 
                                                                               cost_estimated.get('total_cost', 0.0))
                    }
                },
                
                # Timing breakdown
                'timing': timing_metrics,
                
                # Caching efficiency metrics
                'caching': caching_metrics,
                
                # Per-row calculations
                'per_row': per_row_metrics,
                
                # Provider-specific metrics for aggregation
                'provider_metrics': {
                    api_provider: {
                        'calls': 1,
                        'tokens': token_usage.get('total_tokens', 0),
                        'cost_actual': cost_data.get('total_cost', 0.0),  # What was actually paid (with caching benefits)
                        'cost_estimated': cost_estimated.get('total_cost', 0.0),  # What it would cost without caching benefits
                        'time_estimated': timing_metrics.get('time_estimated_seconds', processing_time),  # Estimated time without cache for scaling
                        'time_actual': timing_metrics.get('time_actual_seconds', processing_time),  # Actual time with cache benefits
                        'cache_hit_tokens': token_usage.get('cache_read_tokens', 0)
                    }
                }
            }
            
            logger.debug(f"[ENHANCED_METRICS] {api_provider} call - Model: {model}, "
                        f"Cost: ${cost_data.get('total_cost', 0):.6f} (actual) / "
                        f"${cost_estimated.get('total_cost', 0):.6f} (no cache), "
                        f"Tokens: {token_usage.get('total_tokens', 0)}, "
                        f"Time: {processing_time:.3f}s, "
                        f"Cache savings: {enhanced_metrics['costs']['cache_savings']['percentage_savings']:.1f}%")
            
            return enhanced_metrics
            
        except Exception as e:
            logger.error(f"get_enhanced_call_metrics: Error processing response data: {e}")
            import traceback
            logger.error(f"get_enhanced_call_metrics: Traceback: {traceback.format_exc()}")
            return self._get_empty_enhanced_metrics(model, api_provider)
    
    # ========== HELPER METHODS FOR ENHANCED METRICS ==========
    
    def _calculate_cost_without_caching_benefits(self, token_usage: Dict, actual_cost_data: Dict) -> Dict[str, float]:
        """
        Calculate what the cost would be without any caching benefits.
        This involves estimating what cache hits would have cost if they were fresh API calls.
        """
        try:
            cache_read_tokens = token_usage.get('cache_read_tokens', 0)
            if cache_read_tokens == 0:
                # No caching benefits, return actual costs
                return actual_cost_data
            
            # Estimate the cost of cache hits as if they were fresh API calls
            # Cache reads are typically input tokens that were served from cache
            api_provider = token_usage.get('api_provider', 'unknown')
            
            # Get pricing data to calculate cache cost
            try:
                pricing_data = self.load_pricing_data()
                temp_token_usage = token_usage.copy()
                temp_token_usage['cache_read_tokens'] = 0  # Remove cache benefit
                temp_token_usage['input_tokens'] = token_usage.get('input_tokens', 0) + cache_read_tokens
                
                # Calculate cost without cache benefits
                cost_estimated = self.calculate_token_costs(temp_token_usage, pricing_data)
                return cost_estimated
                
            except Exception as e:
                logger.warning(f"_calculate_cost_without_caching_benefits: Error calculating cache cost: {e}")
                # Estimate cache cost as average input cost per token
                input_cost_per_token = actual_cost_data.get('input_cost', 0.0) / max(1, token_usage.get('input_tokens', 1))
                estimated_cache_cost = cache_read_tokens * input_cost_per_token
                
                return {
                    'input_cost': actual_cost_data.get('input_cost', 0.0) + estimated_cache_cost,
                    'output_cost': actual_cost_data.get('output_cost', 0.0),
                    'total_cost': actual_cost_data.get('total_cost', 0.0) + estimated_cache_cost
                }
                
        except Exception as e:
            logger.error(f"_calculate_cost_without_caching_benefits: Critical error: {e}")
            return actual_cost_data
    
    def _extract_caching_metrics(self, token_usage: Dict, response: Dict) -> Dict[str, Any]:
        """Extract comprehensive caching efficiency metrics."""
        try:
            cache_read_tokens = token_usage.get('cache_read_tokens', 0)
            cache_creation_tokens = token_usage.get('cache_creation_tokens', 0)
            input_tokens = token_usage.get('input_tokens', 0)
            total_tokens = token_usage.get('total_tokens', 0)
            
            cache_hit_rate = (cache_read_tokens / max(1, input_tokens)) * 100
            cache_coverage = (cache_read_tokens / max(1, total_tokens)) * 100
            
            return {
                'cache_read_tokens': cache_read_tokens,
                'cache_creation_tokens': cache_creation_tokens,
                'cache_hit_rate_percent': cache_hit_rate,
                'cache_coverage_percent': cache_coverage,
                'has_cache_benefit': cache_read_tokens > 0,
                'cache_efficiency_score': min(100, (cache_hit_rate * 1.2))  # Weighted score
            }
            
        except Exception as e:
            logger.error(f"_extract_caching_metrics: Error: {e}")
            return {
                'cache_read_tokens': 0, 'cache_creation_tokens': 0,
                'cache_hit_rate_percent': 0.0, 'cache_coverage_percent': 0.0,
                'has_cache_benefit': False, 'cache_efficiency_score': 0.0
            }
    
    def _calculate_comprehensive_timing_metrics(self, token_usage: Dict, time_actual_seconds: float, caching_metrics: Dict, is_internal_cache: bool = False) -> Dict[str, Any]:
        """
        Calculate comprehensive timing metrics including estimated time without cache benefits.
        """
        try:
            # Base efficiency: tokens per second
            total_tokens = token_usage.get('total_tokens', 0)
            tokens_per_second = total_tokens / max(0.1, time_actual_seconds)
            
            # Estimate time without caching benefits
            # Handle both Anthropic cache (cache_read_tokens) and our internal cache (is_internal_cache)
            cache_read_tokens = caching_metrics.get('cache_read_tokens', 0)
            
            if is_internal_cache:
                # For our internal cache: time_actual_seconds is the original processing time from cache
                # We need to set actual time to near-zero and estimated time to the original time
                time_estimated_seconds = time_actual_seconds  # Original processing time (~90s)
                time_actual_seconds = 0.001  # Cache retrieval time (overwrite the passed value)
                logger.debug(f"[TIMING_INTERNAL_CACHE] Internal cache detected - Actual: {time_actual_seconds:.3f}s, Estimated: {time_estimated_seconds:.3f}s")
            elif cache_read_tokens > 0:
                # Anthropic cache: estimate cache processing time vs fresh call time
                cache_speedup_factor = 8.0  # Conservative estimate
                estimated_cache_time = (cache_read_tokens / tokens_per_second) * cache_speedup_factor
                time_estimated_seconds = time_actual_seconds + estimated_cache_time
            else:
                # Fresh API call: actual time = estimated time
                time_estimated_seconds = time_actual_seconds
            
            # Time efficiency metrics
            time_savings_seconds = time_estimated_seconds - time_actual_seconds
            time_savings_percent = (time_savings_seconds / max(0.1, time_estimated_seconds)) * 100
            
            return {
                'time_actual_seconds': time_actual_seconds,
                'time_estimated_seconds': time_estimated_seconds,
                'time_savings_seconds': time_savings_seconds,
                'time_savings_percent': time_savings_percent,
                'tokens_per_second_actual': tokens_per_second,
                'tokens_per_second_estimated': total_tokens / max(0.1, time_estimated_seconds)
            }
            
        except Exception as e:
            logger.error(f"_calculate_comprehensive_timing_metrics: Error: {e}")
            return {
                'time_actual_seconds': time_actual_seconds, 'time_estimated_seconds': time_actual_seconds,
                'time_savings_seconds': 0.0, 'time_savings_percent': 0.0,
                'tokens_per_second_actual': 0.0, 'tokens_per_second_estimated': 0.0
            }
    
    def _calculate_per_row_metrics(self, cost_actual: Dict, cost_estimated: Dict, 
                                  timing_metrics: Dict, batch_info: Dict = None) -> Dict[str, Any]:
        """Calculate per-row cost and timing metrics."""
        try:
            batch_size = 1
            if batch_info and isinstance(batch_info, dict):
                batch_size = max(1, batch_info.get('batch_size', 1))
            
            per_row_cost_actual = cost_actual.get('total_cost', 0.0) / batch_size
            per_row_cost_estimated = cost_estimated.get('total_cost', 0.0) / batch_size
            per_row_time_actual = timing_metrics.get('time_actual_seconds', 0.0) / batch_size
            per_row_time_estimated = timing_metrics.get('time_estimated_seconds', 0.0) / batch_size
            
            return {
                'batch_size': batch_size,
                'cost_per_row_actual': per_row_cost_actual,
                'cost_per_row_estimated': per_row_cost_estimated,
                'time_per_row_actual': per_row_time_actual,
                'time_per_row_estimated': per_row_time_estimated,
                'cost_savings_per_row': per_row_cost_estimated - per_row_cost_actual,
                'time_savings_per_row': per_row_time_estimated - per_row_time_actual
            }
            
        except Exception as e:
            logger.error(f"_calculate_per_row_metrics: Error: {e}")
            return {
                'batch_size': 1, 'cost_per_row_actual': 0.0, 'cost_per_row_estimated': 0.0,
                'time_per_row_actual': 0.0, 'time_per_row_estimated': 0.0,
                'cost_savings_per_row': 0.0, 'time_savings_per_row': 0.0
            }
    
    def _calculate_percentage_savings(self, actual_cost: float, cost_estimated: float) -> float:
        """Calculate percentage savings from caching."""
        if cost_estimated <= 0:
            return 0.0
        return ((cost_estimated - actual_cost) / cost_estimated) * 100
    
    def _get_empty_enhanced_metrics(self, model: str, api_provider: str) -> Dict[str, Any]:
        """Return empty enhanced metrics structure for error cases."""
        return {
            'call_info': {'model': model, 'api_provider': api_provider, 'timestamp': datetime.now(timezone.utc).isoformat()},
            'tokens': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cache_creation_tokens': 0, 'cache_read_tokens': 0},
            'costs': {
                'actual': {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0, 'pricing_source': 'error'},
                'estimated': {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0},
                'cache_savings': {'absolute_savings': 0.0, 'percentage_savings': 0.0}
            },
            'timing': {'time_actual_seconds': 0.0, 'time_estimated_seconds': 0.0, 'time_savings_seconds': 0.0, 'time_savings_percent': 0.0, 'tokens_per_second_actual': 0.0, 'tokens_per_second_estimated': 0.0},
            'caching': {'cache_read_tokens': 0, 'cache_creation_tokens': 0, 'cache_hit_rate_percent': 0.0, 'cache_coverage_percent': 0.0, 'has_cache_benefit': False, 'cache_efficiency_score': 0.0},
            'per_row': {'batch_size': 1, 'cost_per_row_actual': 0.0, 'cost_per_row_estimated': 0.0, 'time_per_row_actual': 0.0, 'time_per_row_estimated': 0.0, 'cost_savings_per_row': 0.0, 'time_savings_per_row': 0.0},
            'provider_metrics': {api_provider: {'calls': 0, 'tokens': 0, 'cost_actual': 0.0, 'cost_estimated': 0.0, 'processing_time': 0.0, 'cache_hit_tokens': 0}},
            'error': True
        }
    
    # ========== PROVIDER-SPECIFIC AGGREGATION METHODS ==========
    
    @staticmethod
    def aggregate_provider_metrics(call_metrics_list: List[Dict]) -> Dict[str, Any]:
        """
        Aggregate enhanced call metrics by provider for comprehensive analysis.

        Args:
            call_metrics_list: List of enhanced call metrics from get_enhanced_call_metrics()

        Returns:
            Aggregated metrics by provider with comprehensive statistics
        """
        try:
            logger.debug(f"[AGGREGATE_DEBUG] Starting aggregation of {len(call_metrics_list)} call metrics")

            if not call_metrics_list:
                logger.warning("[AGGREGATE_DEBUG] No call metrics provided for aggregation")
                return {'providers': {}, 'totals': {}, 'error': 'no_metrics_provided'}

            # NOTE: Don't convert Decimals to float - DynamoDB will reject floats when writing back
            # Python's arithmetic works fine with Decimals, and convert_floats_to_decimal() will
            # ensure consistency when writing. Removing decimal_to_float() conversion.
            
            providers = {}
            # Initialize totals - use int for counts, float for costs/times
            # These will be converted to Decimal when writing to DynamoDB
            totals = {
                'total_calls': 0,  # Keep as int
                'total_tokens': 0,  # Keep as int
                'total_cost_actual': 0.0,
                'total_cost_estimated': 0.0,
                'total_estimated_processing_time': 0.0,
                'total_actual_processing_time': 0.0,
                'total_cache_savings_cost': 0.0,
                'total_cache_savings_time': 0.0,
                'overall_cache_efficiency': 0.0
            }
            
            for i, call_metrics in enumerate(call_metrics_list):
                if 'provider_metrics' not in call_metrics:
                    logger.warning(f"[AGGREGATE_DEBUG] Call {i}: No provider_metrics found")
                    continue
                
                provider_metrics_dict = call_metrics['provider_metrics']
                logger.debug(f"[AGGREGATE_DEBUG] Call {i}: Processing {len(provider_metrics_dict)} providers: {list(provider_metrics_dict.keys())}")
                    
                for provider, metrics in provider_metrics_dict.items():
                    calls_count = metrics.get('calls', 0)
                    cost_actual = metrics.get('cost_actual', 0.0)
                    cost_estimated = metrics.get('cost_estimated', 0.0)
                    logger.debug(f"[AGGREGATE_DEBUG] Call {i}, Provider {provider}: "
                               f"calls={calls_count}, cost_actual=${cost_actual:.6f}, cost_estimated=${cost_estimated:.6f}")
                    if provider not in providers:
                        providers[provider] = {
                            'calls': 0,
                            'tokens': 0,
                            'cost_actual': 0.0,
                            'cost_estimated': 0.0,
                            'time_estimated': 0.0,  # Estimated processing time
                            'time_actual': 0.0,     # Actual processing time
                            'cache_hit_tokens': 0,
                            'cache_savings_cost': 0.0,
                            'cache_savings_time': 0.0,
                            'average_cost_per_call': 0.0,
                            'average_tokens_per_call': 0.0,
                            'average_time_per_call': 0.0,
                            'cost_per_row_actual': 0.0,
                            'cost_per_row_estimated': 0.0,
                            'time_per_row_actual': 0.0,
                            'time_per_row_estimated': 0.0,
                            'cache_efficiency_percent': 0.0
                        }
                    
                    # Aggregate raw metrics
                    providers[provider]['calls'] += metrics.get('calls', 0)
                    providers[provider]['tokens'] += metrics.get('tokens', 0)
                    providers[provider]['cost_actual'] += metrics.get('cost_actual', 0.0)
                    providers[provider]['cost_estimated'] += metrics.get('cost_estimated', 0.0)
                    providers[provider]['time_estimated'] += metrics.get('time_estimated', 0.0)
                    providers[provider]['time_actual'] += metrics.get('time_actual', 0.0)
                    providers[provider]['cache_hit_tokens'] += metrics.get('cache_hit_tokens', 0)
                    
                    # Calculate savings from the call
                    call_cost_savings = call_metrics.get('costs', {}).get('cache_savings', {}).get('absolute_savings', 0.0)
                    call_time_savings = call_metrics.get('timing', {}).get('time_savings_seconds', 0.0)
                    
                    providers[provider]['cache_savings_cost'] += call_cost_savings
                    providers[provider]['cache_savings_time'] += call_time_savings
            
            # Calculate derived metrics for each provider
            for provider, metrics in providers.items():
                if metrics['calls'] > 0:
                    metrics['average_cost_per_call'] = metrics['cost_actual'] / metrics['calls']
                    metrics['average_tokens_per_call'] = metrics['tokens'] / metrics['calls']
                    metrics['average_time_per_call'] = metrics['time_actual'] / metrics['calls']
                
                # Cache efficiency
                if metrics['cost_estimated'] > 0:
                    metrics['cache_efficiency_percent'] = (metrics['cache_savings_cost'] / metrics['cost_estimated']) * 100
                
                # Update totals (ensure integers stay as ints for DynamoDB)
                totals['total_calls'] += int(metrics['calls'])
                totals['total_tokens'] += int(metrics['tokens'])
                totals['total_cost_actual'] += metrics['cost_actual']
                totals['total_cost_estimated'] += metrics['cost_estimated']
                totals['total_estimated_processing_time'] += metrics['time_estimated']
                totals['total_actual_processing_time'] += metrics['time_actual']
                totals['total_cache_savings_cost'] += metrics['cache_savings_cost']
                totals['total_cache_savings_time'] += metrics['cache_savings_time']
            
            # Calculate overall efficiency
            if totals['total_cost_estimated'] > 0:
                totals['overall_cache_efficiency'] = (totals['total_cache_savings_cost'] / totals['total_cost_estimated']) * 100
            
            # Debug: Final aggregation summary
            logger.debug(f"[AGGREGATE_DEBUG] Final aggregation results: "
                      f"Providers: {list(providers.keys())}, "
                      f"Total calls: {totals.get('total_calls', 0)}, "
                      f"Total actual cost: ${totals.get('total_cost_actual', 0.0):.6f}, "
                      f"Total estimated cost: ${totals.get('total_cost_estimated', 0.0):.6f}")
            
            for provider, provider_data in providers.items():
                logger.debug(f"[AGGREGATE_DEBUG] Provider {provider}: "
                          f"calls={provider_data.get('calls', 0)}, "
                          f"tokens={provider_data.get('tokens', 0)}, "
                          f"cost_actual=${provider_data.get('cost_actual', 0.0):.6f}, "
                          f"cost_estimated=${provider_data.get('cost_estimated', 0.0):.6f}")
            
            return {
                'providers': providers,
                'totals': totals,
                'summary': {
                    'provider_count': len(providers),
                    'dominant_provider': max(providers.keys(), key=lambda p: providers[p]['cost_actual']) if providers else None,
                    'most_efficient_provider': max(providers.keys(), key=lambda p: providers[p]['cache_efficiency_percent']) if providers else None
                }
            }
            
        except Exception as e:
            logger.error(f"aggregate_provider_metrics: Error: {e}")
            import traceback
            logger.error(f"aggregate_provider_metrics: Traceback: {traceback.format_exc()}")
            return {'providers': {}, 'totals': {}, 'error': str(e)}
    
    @staticmethod
    # NOTE: calculate_full_validation_estimates() function moved to validation lambda
    # The validation lambda now handles batch timing calculations since it knows the batch architecture
    # Use calculate_full_validation_estimates_with_batch_timing() in validation/lambda_function.py

    def get_unified_cost_and_time_data(self, response: Dict, model: str, processing_time: float, search_context_size: str = None) -> Dict[str, Any]:
        """
        DEPRECATED: Use get_enhanced_call_metrics() for comprehensive tracking.
        Maintained for backward compatibility.
        """
        try:
            # Extract token usage with validation
            token_usage = self._extract_token_usage(response, model, search_context_size)
            
            # Calculate costs
            cost_data = self.calculate_token_costs(token_usage)
            
            # Calculate time estimates
            time_data = self.calculate_processing_time_estimate(token_usage, processing_time)
            
            # Combine all data
            unified_data = {
                'token_usage': token_usage,
                'cost_data': cost_data,
                'time_data': time_data,
                'summary': {
                    'total_cost': cost_data.get('total_cost', 0.0),
                    'total_tokens': token_usage.get('total_tokens', 0),
                    'processing_time': processing_time,
                    'cost_per_token': cost_data.get('total_cost', 0.0) / max(1, token_usage.get('total_tokens', 1)),
                    'api_provider': token_usage.get('api_provider', 'unknown'),
                    'model': model
                }
            }
            
            logger.debug(f"ai_api_client.get_unified_cost_and_time_data: "
                        f"Model: {model}, Cost: ${cost_data.get('total_cost', 0):.6f}, "
                        f"Tokens: {token_usage.get('total_tokens', 0)}, "
                        f"Time: {processing_time:.3f}s")
            
            return unified_data
            
        except Exception as e:
            logger.error(f"ai_api_client.get_unified_cost_and_time_data: Error processing response data: {e}")
            return {
                'token_usage': self._get_empty_token_usage(model),
                'cost_data': {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0, 'error': str(e)},
                'time_data': {'processing_time': processing_time, 'error': str(e)},
                'summary': {
                    'total_cost': 0.0,
                    'total_tokens': 0,
                    'processing_time': processing_time,
                    'cost_per_token': 0.0,
                    'api_provider': 'unknown',
                    'model': model,
                    'error': str(e)
                }
            }
    
    # ========== END CENTRALIZED COST AND TIME CALCULATION SYSTEM ==========
    
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

            logger.debug(f"CACHE_CHECK: Checking S3 cache for key: {cache_key[:8]}... in bucket: {self.s3_bucket}, path: {s3_key}")

            # Use async S3 client to avoid blocking event loop
            async with self.s3_session.client('s3') as s3_client:
                cache_response = await s3_client.get_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key
                )

                # Validate JSON before parsing
                async with cache_response['Body'] as stream:
                    cache_body = await stream.read()
            if not cache_body:
                logger.warning(f"CACHE_REJECT: Empty cache file for key: {cache_key[:8]}... - will make API call")
                return None
            
            try:
                cached_data = json.loads(cache_body)
            except json.JSONDecodeError as e:
                logger.warning(f"CACHE_REJECT: Invalid JSON in cache for key: {cache_key[:8]}... - Error: {str(e)} - will make API call")
                return None
            
            # Validate cache structure
            if not isinstance(cached_data, dict):
                logger.warning(f"CACHE_REJECT: Cache data not a dict for key: {cache_key[:8]}... - Type: {type(cached_data)} - will make API call")
                return None
            
            if 'api_response' not in cached_data:
                logger.warning(f"CACHE_REJECT: Missing api_response in cache for key: {cache_key[:8]}... - Keys: {list(cached_data.keys())} - will make API call")
                return None
            
            # Validate API response structure
            api_response = cached_data['api_response']
            if not isinstance(api_response, dict):
                logger.warning(f"CACHE_REJECT: api_response not a dict for key: {cache_key[:8]}... - Type: {type(api_response)} - will make API call")
                return None
            
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
            else:
                logger.warning(f"CACHE_WARNING: Missing token_usage in cache for key: {cache_key[:8]}... - continuing anyway")
            
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
            
            logger.debug(f"CACHE_HIT: Found cached response for key: {cache_key[:8]}... "
                       f"(cached {cache_age_hours:.1f}h ago, model: {cached_model}, "
                       f"check_time: {cache_check_time:.3f}s)")
            
            # ENHANCED LOGGING: Check for suspiciously fast cache processing times
            cached_processing_time = cached_data.get('processing_time', 0)
            if cached_processing_time < 1.0 and cached_processing_time > 0:
                logger.debug(f"[FAST_CACHED_RESPONSE] Original API call was unusually fast ({cached_processing_time:.3f}s) "
                           f"for key: {cache_key[:8]}... This might indicate Anthropic cache was hit during original call.")
                
            # Log cache token information if available
            cached_token_usage = cached_data.get('token_usage', {})
            cache_read_tokens = cached_token_usage.get('cache_read_tokens', 0)
            cache_creation_tokens = cached_token_usage.get('cache_creation_tokens', 0)
            if cache_read_tokens > 0 or cache_creation_tokens > 0:
                logger.debug(f"[ANTHROPIC_CACHE_TOKENS] Cache tokens in original call: "
                           f"read={cache_read_tokens}, creation={cache_creation_tokens} for key: {cache_key[:8]}...")
            
            return cached_data

        except Exception as e:
            cache_check_time = (datetime.now() - cache_check_start).total_seconds()
            # Check if it's a NoSuchKey error (cache miss)
            if 'NoSuchKey' in str(e) or '404' in str(e):
                logger.debug(f"CACHE_MISS: No cached response found for key: {cache_key[:8]}... "
                           f"(check_time: {cache_check_time:.3f}s)")
                return None
            # Other errors
            logger.error(f"CACHE_ERROR: Failed to check cache for key: {cache_key[:8]}... "
                        f"Error: {str(e)}, check_time: {cache_check_time:.3f}s)")
            return None
    
    async def _save_to_cache(self, cache_key: str, response: Dict, token_usage: Dict, processing_time: float, model: str, api_provider: str = 'anthropic'):
        """Save response to cache including enhanced metrics."""
        try:
            # Generate enhanced metrics for caching
            try:
                enhanced_metrics = self.get_enhanced_call_metrics(response, model, processing_time, is_cached=False)
            except Exception as e:
                logger.warning(f"Failed to generate enhanced metrics for cache: {e}")
                enhanced_metrics = {}
            
            cache_entry = {
                'api_response': response,
                'cached_at': datetime.now(timezone.utc).isoformat(),
                'model': model,
                'token_usage': token_usage,
                'processing_time': processing_time,
                'enhanced_data': enhanced_metrics  # Add enhanced metrics to cache
                # NOTE: Deliberately NOT storing 'is_cached' - it's determined at retrieval time
            }

            s3_key = self._get_cache_s3_key(cache_key, api_provider)

            # Use async S3 client to avoid blocking event loop
            async with self.s3_session.client('s3') as s3_client:
                await s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=json.dumps(cache_entry),
                    ContentType='application/json'
                )

            logger.debug(f"Cached API response, key: {cache_key[:8]}...")
        except Exception as e:
            logger.error(f"Failed to cache API response: {str(e)}")
    
    async def _save_debug_data(self, api_provider: str, model: str, request_data: Dict,
                              response_data: Any, error: Exception = None, context: str = "", debug_name: str = None):
        """Save debug data for API calls to help diagnose issues."""
        # Check if debug saves are disabled (e.g., for standalone mode)
        if os.environ.get('DISABLE_AI_DEBUG_SAVES', '').lower() == 'true':
            return  # Skip debug saves

        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            status = "ERROR" if error else "SUCCESS"
            model_clean = model.replace('/', '_').replace(':', '_')
            
            # Use debug_name if provided, otherwise extract content description
            if debug_name:
                # Clean debug_name for filename safety
                name_clean = ''.join(c for c in debug_name if c.isalnum() or c in '_-').strip()[:30]
                content_description = name_clean if name_clean else 'custom'
            else:
                content_description = self._extract_content_description(request_data)
            
            # Create descriptive filename: YYYYMMDD_HHMMSS_provider_model_status_description.json
            debug_filename = f"{timestamp}_{api_provider}_{model_clean}_{status}_{content_description}.json"
            
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

            # Use async S3 client to avoid blocking event loop
            async with self.s3_session.client('s3') as s3_client:
                await s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=json.dumps(debug_entry, indent=2, ensure_ascii=False),
                    ContentType='application/json'
                )

            logger.debug(f"[DEBUG] Saved debug data to s3://{self.s3_bucket}/{s3_key}")
            
            # Also log key information
            if error:
                logger.error(f"[DEBUG] API call failed - Provider: {api_provider}, Model: {model}, Error: {str(error)}")
                logger.error(f"[DEBUG] Request URL: {request_data.get('url', 'N/A')}")
                logger.error(f"[DEBUG] Request headers keys: {list(request_data.get('headers', {}).keys())}")
                logger.error(f"[DEBUG] Request data keys: {list(request_data.get('data', {}).keys())}")
            else:
                logger.debug(f"[DEBUG] API call succeeded - Provider: {api_provider}, Model: {model}")
                
        except Exception as e:
            logger.error(f"[DEBUG] Failed to save debug data: {str(e)}")
    
    def _extract_content_description(self, request_data: Dict) -> str:
        """Extract a short description from the content for use in filename."""
        try:
            if 'data' in request_data and 'messages' in request_data['data']:
                for message in request_data['data']['messages']:
                    if isinstance(message, dict) and 'content' in message and message.get('role') == 'user':
                        content = message['content']
                        if isinstance(content, str) and content.strip():
                            # Extract first meaningful words, clean for filename
                            words = []
                            for word in content.split():
                                clean_word = ''.join(c for c in word if c.isalnum())
                                if clean_word and len(clean_word) > 2:
                                    words.append(clean_word)
                                if len(words) >= 4:  # Use first 4 meaningful words
                                    break
                            if words:
                                return '_'.join(words)[:50]  # Max 50 chars
            return 'request'
        except Exception:
            return 'request'
    
    
    async def call_structured_api(self, prompt: str, schema: Dict, model: Union[str, List[str]] = "claude-sonnet-4-5",
                                 tool_name: str = "structured_response", use_cache: bool = True,
                                 context: str = "", max_tokens: int = None, max_web_searches: int = 3,
                                 search_context_size: str = "low", debug_name: str = None) -> Dict:
        """
        Call AI API with structured output using JSON response format.
        
        Args:
            prompt: The prompt to send to the AI
            schema: JSON schema for the expected response structure
            model: The model to use (string) or list of models to try in sequence
            tool_name: Name of the tool for structured output (legacy parameter, now ignored)
            use_cache: Whether to use caching
            context: Additional context for cache key generation
            max_web_searches: Maximum web searches for Anthropic models
            search_context_size: Search context size for Perplexity models ("low", "medium", or "high")
            debug_name: Optional name to include in debug filenames for easier identification
            
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
            logger.debug(f"Auto-selected backup models for {model}: {backup_models}")
        else:
            models_to_try = model
        
        logger.debug(f"STRUCTURED_API_CALL: Starting call with {len(models_to_try)} model(s): {models_to_try}, "
                    f"use_cache: {use_cache}, context: '{context[:50]}...', "
                    f"prompt_length: {len(prompt)}, schema_keys: {list(schema.keys()) if schema else 'None'}")
        
        last_error = None
        
        # Try each model once in sequence
        for model_index, current_model in enumerate(models_to_try):
            try:
                logger.debug(f"[MODEL_TRY] Attempting model {model_index + 1}/{len(models_to_try)}: {current_model}")

                # Monitor for legacy Sonnet 3.5 usage
                if 'sonnet-3' in current_model.lower() or '3-5-sonnet' in current_model.lower() or '3.5-sonnet' in current_model.lower():
                    logger.warning(f"[LEGACY_MODEL_WARNING] Using legacy Sonnet 3.5 model: {current_model}. Expected claude-sonnet-4-5 or newer.")

                # Normalize model for current provider
                api_provider = self._determine_api_provider(current_model)
                current_model_normalized = self._normalize_anthropic_model(current_model)
                
                # Generate cache key for this specific model
                cache_key = self._get_cache_key(prompt, current_model_normalized, schema, context, max_web_searches) if use_cache else None
                
                # Check cache for this specific model
                if use_cache and cache_key:
                    cached_data = await self._check_cache(cache_key, api_provider)
                    if cached_data:
                        logger.debug(f"[CACHE_HIT] Using cached response for model {current_model}")
                        token_usage = cached_data.get('token_usage', {})
                        # Normalize legacy cached token usage for Perplexity
                        if token_usage.get('api_provider') == 'perplexity':
                            if 'input_tokens' not in token_usage and 'prompt_tokens' in token_usage:
                                token_usage['input_tokens'] = token_usage['prompt_tokens']
                            if 'output_tokens' not in token_usage and 'completion_tokens' in token_usage:
                                token_usage['output_tokens'] = token_usage['completion_tokens']
                        
                        # Extract citations based on API provider
                        if api_provider == 'perplexity':
                            citations = self.extract_citations_from_perplexity_response(cached_data['api_response'])
                        else:
                            citations = self.extract_citations_from_response(cached_data['api_response'])
                        
                        # Generate enhanced metrics for cached response
                        try:
                            enhanced_data = cached_data.get('enhanced_data')
                            logger.debug(f"[CACHE_ENHANCED_DEBUG] Cached data has enhanced_data: {enhanced_data is not None}")
                            if enhanced_data:
                                # Check if the cached enhanced_data has correct cost structure
                                cached_costs = enhanced_data.get('costs', {})
                                cached_actual = cached_costs.get('actual', {}).get('total_cost', 0.0)
                                cached_estimated = cached_costs.get('estimated', {}).get('total_cost', 0.0)
                                logger.debug(f"[CACHE_ENHANCED_DEBUG] Cached enhanced_data costs: actual=${cached_actual:.6f}, estimated=${cached_estimated:.6f}")
                                
                                # If cached enhanced_data has incorrect cost structure (actual == estimated), regenerate it
                                if cached_actual == cached_estimated and cached_actual > 0:
                                    logger.debug(f"[CACHE_ENHANCED_DEBUG] Cached enhanced_data has incorrect costs (actual==estimated), regenerating...")
                                    enhanced_data = None  # Force regeneration
                            
                            if not enhanced_data:
                                # For cached responses, generate enhanced metrics with special timing handling
                                original_processing_time = cached_data.get('processing_time', 0)
                                cached_token_usage = cached_data.get('token_usage', {})
                                enhanced_data = self.get_enhanced_call_metrics(
                                    cached_data['api_response'],
                                    current_model,
                                    0.001,  # Use minimal cache retrieval time instead of original processing time
                                    pre_extracted_token_usage=cached_token_usage,
                                    is_cached=True,
                                    max_web_searches=max_web_searches
                                )
                                
                                # Override timing metrics for cached response
                                if 'timing' in enhanced_data:
                                    enhanced_data['timing'].update({
                                        'time_actual_seconds': 0.001,  # Near zero for cache hit
                                        'time_estimated_seconds': original_processing_time,  # Original processing time
                                        'time_savings_seconds': original_processing_time - 0.001,
                                        'time_savings_percent': ((original_processing_time - 0.001) / max(0.001, original_processing_time)) * 100
                                    })
                                    # ALSO UPDATE THE PROVIDER METRICS TO MATCH
                                    if 'provider_metrics' in enhanced_data and enhanced_data['provider_metrics']:
                                        provider_name = list(enhanced_data['provider_metrics'].keys())[0]
                                        enhanced_data['provider_metrics'][provider_name]['time_actual'] = 0.001
                                        enhanced_data['provider_metrics'][provider_name]['time_estimated'] = original_processing_time
                                
                                actual_cost = enhanced_data.get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                                estimated_cost = enhanced_data.get('costs', {}).get('estimated', {}).get('total_cost', 0.0)
                                logger.debug(f"Generated enhanced metrics for cached response: actual=${actual_cost:.6f}, estimated=${estimated_cost:.6f}, original_time={original_processing_time:.3f}s")
                        except Exception as e:
                            logger.warning(f"Failed to generate enhanced metrics for cached response: {e}")
                            enhanced_data = {}
                        
                        # [FIX] Convert cached Claude responses to unified Perplexity format for consistent parsing
                        cached_response = cached_data['api_response']
                        if api_provider == 'anthropic':
                            # Convert cached Claude tool response to Perplexity format
                            logger.debug(f"Converting cached Claude response to unified Perplexity format")
                            structured_data = self.extract_structured_response(cached_response, tool_name)
                            validation_results = structured_data.get('validation_results', structured_data)

                            # Convert to Perplexity format that parser expects
                            cached_response = {
                                'choices': [{
                                    'message': {
                                        'role': 'assistant',
                                        'content': json.dumps(validation_results)
                                    }
                                }]
                            }

                        return {
                            'response': cached_response,
                            'token_usage': token_usage,
                            'processing_time': cached_data.get('processing_time', 0),
                            'is_cached': True,  # BULLETPROOF: Always True for cache hits - never take from cached_data  # BULLETPROOF: Always True for cache hits - never take from cached_data
                            'model_used': current_model,
                            'citations': citations,
                            'enhanced_data': enhanced_data
                        }
                
                # Log that we're making an API call (no cache hit)
                logger.debug(f"API_CALL_PROCEEDING: Making {api_provider} API call for model {current_model} - cache_key: {cache_key[:8] if cache_key else 'N/A'}...")
                
                # Make API call based on provider
                if api_provider == 'anthropic':
                    # Anthropic API call
                    headers = {
                        'Content-Type': 'application/json',
                        'X-API-Key': self.anthropic_api_key,
                        'anthropic-version': '2023-06-01'
                    }
                    
                    # Build tools list - only include web search if max_web_searches > 0
                    tools = []
                    if max_web_searches > 0:
                        tools.append({
                            "type": "web_search_20250305",
                            "name": "web_search",
                            "max_uses": max_web_searches
                        })
                    
                    tools.append({
                        "name": tool_name,
                        "description": f"Provide structured response using {tool_name}",
                        "input_schema": schema
                    })
                    
                    # Enforce provider token limits to prevent API errors
                    enforced_max_tokens = self._enforce_provider_token_limit(current_model, max_tokens or 8000)

                    data = {
                        "model": current_model_normalized,
                        "max_tokens": enforced_max_tokens,
                        "temperature": 0.1,
                        "messages": [{"role": "user", "content": prompt}],
                        "tools": tools,
                        "tool_choice": {"type": "auto"}
                    }
                    
                    result = await self._make_single_anthropic_call("https://api.anthropic.com/v1/messages",
                                                                   headers, data, current_model_normalized,
                                                                   use_cache, cache_key, call_start_time, max_web_searches)
                    
                elif api_provider == 'perplexity':
                    # Perplexity API call for structured output
                    result = await self._make_single_perplexity_structured_call(prompt, schema, current_model,
                                                                               use_cache, cache_key, call_start_time, search_context_size, debug_name, max_tokens or 8000)
                else:
                    logger.warning(f"[SKIP] Unknown provider for model {current_model}")
                    continue
                
                # If we got a result, add model info and normalize response format
                if result:
                    result['model_used'] = current_model
                    result['used_backup_model'] = model_index > 0
                    
                    # Normalize response format: Convert all responses to Perplexity format for unified parsing
                    if api_provider == 'anthropic':
                        # Convert Claude tool response to Perplexity format
                        logger.debug(f"Converting Claude response to unified Perplexity format")
                        claude_response = result['response']
                        structured_data = self.extract_structured_response(claude_response, tool_name)
                        validation_results = structured_data.get('validation_results', structured_data)
                        
                        # Convert to Perplexity format that parser expects
                        result['response'] = {
                            'choices': [{
                                'message': {
                                    'role': 'assistant',
                                    'content': json.dumps(validation_results)
                                }
                            }]
                        }
                        result['citations'] = self.extract_citations_from_response(claude_response)
                    else:
                        # Perplexity response is already in the correct format
                        result['citations'] = self.extract_citations_from_perplexity_response(result.get('response', {}))

                    # Monitor for legacy model references in response content
                    response_str = json.dumps(result.get('response', {})).lower()
                    if 'sonnet-3' in response_str or '3-5-sonnet' in response_str or '3.5-sonnet' in response_str or 'claude-3' in response_str:
                        logger.warning(f"[LEGACY_MODEL_REFERENCE] Response from {current_model} contains references to legacy Sonnet 3.x models. This may indicate model confusion.")

                    logger.debug(f"[SUCCESS] Model {current_model} succeeded with unified response format")
                    return result
                    
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"[FAILED] Model {current_model} failed: {error_msg}")
                last_error = e
                
                # If this is a 529 overload, try next model. For other errors, continue trying too.
                if "overloaded" in error_msg and "529" in error_msg:
                    logger.debug(f"[OVERLOAD] Model {current_model} overloaded, trying next model")
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
    
    async def call_text_api(self, prompt: str, model: Union[str, List[str]] = "claude-sonnet-4-5",
                           use_cache: bool = True, context: str = "", max_web_searches: int = 3) -> Dict:
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
        # Monitor for legacy Sonnet 3.5 usage
        if isinstance(model, str) and ('sonnet-3' in model.lower() or '3-5-sonnet' in model.lower() or '3.5-sonnet' in model.lower()):
            logger.warning(f"[LEGACY_MODEL_WARNING] Using legacy Sonnet 3.5 model: {model}. Expected claude-sonnet-4-5 or newer.")

        normalized_model = self._normalize_anthropic_model(model)
        cache_key = self._get_cache_key(prompt, normalized_model, None, context, max_web_searches) if use_cache else None
        
        # Check cache first
        if use_cache and cache_key:
            cached_data = await self._check_cache(cache_key, 'anthropic')
            if cached_data:
                token_usage = cached_data.get('token_usage', {})
                # Debug log the cached token usage structure
                logger.debug(f"DEBUG: Cached token usage keys: {list(token_usage.keys())}")
                logger.debug(f"DEBUG: Cached token usage api_provider: {token_usage.get('api_provider')}")
                logger.debug(f"DEBUG: Cached token usage input_tokens: {token_usage.get('input_tokens')}")
                logger.debug(f"DEBUG: Cached token usage prompt_tokens: {token_usage.get('prompt_tokens')}")
                
                # Normalize legacy cached token usage for Perplexity
                if token_usage.get('api_provider') == 'perplexity':
                    if 'input_tokens' not in token_usage and 'prompt_tokens' in token_usage:
                        token_usage['input_tokens'] = token_usage['prompt_tokens']
                        logger.debug(f"DEBUG: Fixed input_tokens: {token_usage['input_tokens']}")
                    if 'output_tokens' not in token_usage and 'completion_tokens' in token_usage:
                        token_usage['output_tokens'] = token_usage['completion_tokens']
                        logger.debug(f"DEBUG: Fixed output_tokens: {token_usage['output_tokens']}")
                    
                    logger.debug(f"DEBUG: Final token usage: input={token_usage.get('input_tokens')}, output={token_usage.get('output_tokens')}, total={token_usage.get('total_tokens')}")
                
                # Generate enhanced metrics for cached response
                try:
                    enhanced_data = cached_data.get('enhanced_data')
                    if not enhanced_data:
                        # For cached responses, generate enhanced metrics with special timing handling
                        original_processing_time = cached_data.get('processing_time', 0)
                        cached_token_usage = cached_data.get('token_usage', {})
                        enhanced_data = self.get_enhanced_call_metrics(
                            cached_data['api_response'], 
                            normalized_model, 
                            0.001,  # Use minimal cache retrieval time instead of original processing time
                            pre_extracted_token_usage=cached_token_usage,
                            is_cached=True
                        )
                        
                        # Override timing metrics for cached response
                        if 'timing' in enhanced_data:
                            enhanced_data['timing'].update({
                                'time_actual_seconds': 0.001,  # Near zero for cache hit
                                'time_estimated_seconds': original_processing_time,  # Original processing time
                                'time_savings_seconds': original_processing_time - 0.001,
                                'time_savings_percent': ((original_processing_time - 0.001) / max(0.001, original_processing_time)) * 100
                            })
                            # ALSO UPDATE THE PROVIDER METRICS TO MATCH
                            if 'provider_metrics' in enhanced_data and enhanced_data['provider_metrics']:
                                provider_name = list(enhanced_data['provider_metrics'].keys())[0]
                                enhanced_data['provider_metrics'][provider_name]['time_actual'] = 0.001
                                enhanced_data['provider_metrics'][provider_name]['time_estimated'] = original_processing_time
                        
                        actual_cost = enhanced_data.get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                        estimated_cost = enhanced_data.get('costs', {}).get('estimated', {}).get('total_cost', 0.0)
                        logger.debug(f"Generated enhanced metrics for cached anthropic response: actual=${actual_cost:.6f}, estimated=${estimated_cost:.6f}, original_time={original_processing_time:.3f}s")
                except Exception as e:
                    logger.warning(f"Failed to generate enhanced metrics for cached anthropic response: {e}")
                    enhanced_data = {}
                
                return {
                    'response': cached_data['api_response'],
                    'token_usage': token_usage,
                    'processing_time': cached_data.get('processing_time', 0),
                    'is_cached': True,  # BULLETPROOF: Always True for cache hits - never take from cached_data  # BULLETPROOF: Always True for cache hits - never take from cached_data
                    'citations': self.extract_citations_from_response(cached_data['api_response']),
                    'enhanced_data': enhanced_data
                }
        
        # Log that we're making an API call (no cache hit)
        logger.debug(f"API_CALL_PROCEEDING: Making anthropic text API call for model {normalized_model} - cache_key: {cache_key[:8] if cache_key else 'N/A'}...")
        
        # Make API call
        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': self.anthropic_api_key,
            'anthropic-version': '2023-06-01'
        }
        
        # Build tools list - only include web search if max_web_searches > 0
        tools = []
        if max_web_searches > 0:
            tools.append({
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_web_searches
            })
        
        data = {
            "model": normalized_model,
            "max_tokens": 4000,
            "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}],
            "tools": tools
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
                logger.debug(f"Smart cache hit for validation key: {cache_key[:8]}... (row: {list(row_data.keys())[:2]})")
                token_usage = cached_data.get('token_usage', {})
                # Debug log the cached token usage structure
                logger.debug(f"DEBUG: Cached token usage keys: {list(token_usage.keys())}")
                logger.debug(f"DEBUG: Cached token usage api_provider: {token_usage.get('api_provider')}")
                logger.debug(f"DEBUG: Cached token usage input_tokens: {token_usage.get('input_tokens')}")
                logger.debug(f"DEBUG: Cached token usage prompt_tokens: {token_usage.get('prompt_tokens')}")
                
                # Normalize legacy cached token usage for Perplexity
                if token_usage.get('api_provider') == 'perplexity':
                    if 'input_tokens' not in token_usage and 'prompt_tokens' in token_usage:
                        token_usage['input_tokens'] = token_usage['prompt_tokens']
                        logger.debug(f"DEBUG: Fixed input_tokens: {token_usage['input_tokens']}")
                    if 'output_tokens' not in token_usage and 'completion_tokens' in token_usage:
                        token_usage['output_tokens'] = token_usage['completion_tokens']
                        logger.debug(f"DEBUG: Fixed output_tokens: {token_usage['output_tokens']}")
                    
                    logger.debug(f"DEBUG: Final token usage: input={token_usage.get('input_tokens')}, output={token_usage.get('output_tokens')}, total={token_usage.get('total_tokens')}")
                
                # Generate enhanced metrics for cached response
                try:
                    enhanced_data = cached_data.get('enhanced_data')
                    if not enhanced_data:
                        # For cached responses, generate enhanced metrics with special timing handling
                        original_processing_time = cached_data.get('processing_time', 0)
                        cached_token_usage = cached_data.get('token_usage', {})
                        enhanced_data = self.get_enhanced_call_metrics(
                            cached_data['api_response'], 
                            model, 
                            0.001,  # Use minimal cache retrieval time instead of original processing time
                            pre_extracted_token_usage=cached_token_usage,
                            is_cached=True
                        )
                        
                        # Override timing metrics for cached response
                        if 'timing' in enhanced_data:
                            enhanced_data['timing'].update({
                                'time_actual_seconds': 0.001,  # Near zero for cache hit
                                'time_estimated_seconds': original_processing_time,  # Original processing time
                                'time_savings_seconds': original_processing_time - 0.001,
                                'time_savings_percent': ((original_processing_time - 0.001) / max(0.001, original_processing_time)) * 100
                            })
                            # ALSO UPDATE THE PROVIDER METRICS TO MATCH
                            if 'provider_metrics' in enhanced_data and enhanced_data['provider_metrics']:
                                provider_name = list(enhanced_data['provider_metrics'].keys())[0]
                                enhanced_data['provider_metrics'][provider_name]['time_actual'] = 0.001
                                enhanced_data['provider_metrics'][provider_name]['time_estimated'] = original_processing_time
                        
                        actual_cost = enhanced_data.get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                        estimated_cost = enhanced_data.get('costs', {}).get('estimated', {}).get('total_cost', 0.0)
                        logger.debug(f"Generated enhanced metrics for cached perplexity smart cache response: actual=${actual_cost:.6f}, estimated=${estimated_cost:.6f}, original_time={original_processing_time:.3f}s")
                except Exception as e:
                    logger.warning(f"Failed to generate enhanced metrics for cached perplexity smart cache response: {e}")
                    enhanced_data = {}
                
                return {
                    'response': cached_data['api_response'],
                    'token_usage': token_usage,
                    'processing_time': cached_data.get('processing_time', 0),
                    'is_cached': True,  # BULLETPROOF: Always True for cache hits - never take from cached_data
                    'citations': self.extract_citations_from_perplexity_response(cached_data['api_response']),
                    'enhanced_data': enhanced_data
                }
        
        # Log that we're making an API call (no cache hit)
        logger.debug(f"API_CALL_PROCEEDING: Making perplexity smart cache API call for model {model} - cache_key: {cache_key[:8] if cache_key else 'N/A'}...")
        
        # Make API call using the standard method
        result = await self.validate_with_perplexity(prompt, model, search_context_size, use_cache=False, context="")
        
        # Cache using the smart key instead of prompt-based key
        if use_cache and cache_key and not result.get('is_cached'):
            await self._save_to_cache(cache_key, result['response'], result['token_usage'], result['processing_time'], model, 'perplexity')
            logger.debug(f"Smart cached validation key: {cache_key[:8]}... (row: {list(row_data.keys())[:2]})")
        
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
        cache_key = self._get_cache_key(prompt, model, None, f"{context}:{search_context_size}", max_web_searches=0) if use_cache else None
        
        # Check cache first
        if use_cache and cache_key:
            cached_data = await self._check_cache(cache_key, 'perplexity')
            if cached_data:
                token_usage = cached_data.get('token_usage', {})
                # Debug log the cached token usage structure
                logger.debug(f"DEBUG: Cached token usage keys: {list(token_usage.keys())}")
                logger.debug(f"DEBUG: Cached token usage api_provider: {token_usage.get('api_provider')}")
                logger.debug(f"DEBUG: Cached token usage input_tokens: {token_usage.get('input_tokens')}")
                logger.debug(f"DEBUG: Cached token usage prompt_tokens: {token_usage.get('prompt_tokens')}")
                
                # Normalize legacy cached token usage for Perplexity
                if token_usage.get('api_provider') == 'perplexity':
                    if 'input_tokens' not in token_usage and 'prompt_tokens' in token_usage:
                        token_usage['input_tokens'] = token_usage['prompt_tokens']
                        logger.debug(f"DEBUG: Fixed input_tokens: {token_usage['input_tokens']}")
                    if 'output_tokens' not in token_usage and 'completion_tokens' in token_usage:
                        token_usage['output_tokens'] = token_usage['completion_tokens']
                        logger.debug(f"DEBUG: Fixed output_tokens: {token_usage['output_tokens']}")
                    
                    logger.debug(f"DEBUG: Final token usage: input={token_usage.get('input_tokens')}, output={token_usage.get('output_tokens')}, total={token_usage.get('total_tokens')}")
                
                # Generate enhanced metrics for cached response
                try:
                    enhanced_data = cached_data.get('enhanced_data')
                    if not enhanced_data:
                        # For cached responses, generate enhanced metrics with special timing handling
                        original_processing_time = cached_data.get('processing_time', 0)
                        cached_token_usage = cached_data.get('token_usage', {})
                        enhanced_data = self.get_enhanced_call_metrics(
                            cached_data['api_response'], 
                            model, 
                            0.001,  # Use minimal cache retrieval time instead of original processing time
                            pre_extracted_token_usage=cached_token_usage,
                            is_cached=True
                        )
                        
                        # Override timing metrics for cached response
                        if 'timing' in enhanced_data:
                            enhanced_data['timing'].update({
                                'time_actual_seconds': 0.001,  # Near zero for cache hit
                                'time_estimated_seconds': original_processing_time,  # Original processing time
                                'time_savings_seconds': original_processing_time - 0.001,
                                'time_savings_percent': ((original_processing_time - 0.001) / max(0.001, original_processing_time)) * 100
                            })
                            # ALSO UPDATE THE PROVIDER METRICS TO MATCH
                            if 'provider_metrics' in enhanced_data and enhanced_data['provider_metrics']:
                                provider_name = list(enhanced_data['provider_metrics'].keys())[0]
                                enhanced_data['provider_metrics'][provider_name]['time_actual'] = 0.001
                                enhanced_data['provider_metrics'][provider_name]['time_estimated'] = original_processing_time
                        
                        actual_cost = enhanced_data.get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                        estimated_cost = enhanced_data.get('costs', {}).get('estimated', {}).get('total_cost', 0.0)
                        logger.debug(f"Generated enhanced metrics for cached perplexity response: actual=${actual_cost:.6f}, estimated=${estimated_cost:.6f}, original_time={original_processing_time:.3f}s")
                except Exception as e:
                    logger.warning(f"Failed to generate enhanced metrics for cached perplexity response: {e}")
                    enhanced_data = {}
                
                return {
                    'response': cached_data['api_response'],
                    'token_usage': token_usage,
                    'processing_time': cached_data.get('processing_time', 0),
                    'is_cached': True,  # BULLETPROOF: Always True for cache hits - never take from cached_data
                    'citations': self.extract_citations_from_perplexity_response(cached_data['api_response']),
                    'enhanced_data': enhanced_data
                }
        
        # Log that we're making an API call (no cache hit)
        logger.debug(f"API_CALL_PROCEEDING: Making perplexity API call for model {model} - cache_key: {cache_key[:8] if cache_key else 'N/A'}...")
        
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
                        logger.debug(f"Perplexity API Token Usage - Input: {token_usage['input_tokens']}, "
                                   f"Output: {token_usage['output_tokens']}, "
                                   f"Total: {token_usage['total_tokens']}")
                        
                        # Cache the response
                        if use_cache and cache_key:
                            await self._save_to_cache(cache_key, response_json, token_usage, processing_time, model, 'perplexity')
                        
                        # Generate enhanced metrics for non-cached response
                        try:
                            enhanced_data = self.get_enhanced_call_metrics(
                                response_json, 
                                model, 
                                processing_time,
                                search_context_size=search_context_size,
                                is_cached=False
                            )
                            logger.debug(f"Generated enhanced metrics for non-cached perplexity response: cost=${enhanced_data.get('costs', {}).get('estimated', {}).get('total_cost', 0.0):.6f}, time={processing_time:.3f}s")
                        except Exception as e:
                            logger.warning(f"Failed to generate enhanced metrics for non-cached perplexity response: {e}")
                            enhanced_data = {}
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False,  # BULLETPROOF: Always False for fresh API calls
                            'citations': self.extract_citations_from_perplexity_response(response_json),
                            'enhanced_data': enhanced_data
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
        """Extract structured data from both Claude tool use format and unified Perplexity format."""
        try:
            # Check if this is unified Perplexity format (from call_structured_api)
            if 'choices' in response and isinstance(response['choices'], list) and len(response['choices']) > 0:
                message = response['choices'][0].get('message', {})
                content = message.get('content', '')
                if isinstance(content, str) and content.strip().startswith('{'):
                    try:
                        # Parse JSON content from unified format
                        return json.loads(content)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON from unified response: {e}")
                        # Fall through to try other formats
            
            # Original Claude tool use format
            for content_item in response.get('content', []):
                if content_item.get('type') == 'tool_use' and content_item.get('name') == tool_name:
                    return content_item.get('input', {})
            
            # Fallback: extract from text content (original Claude format)
            for content_item in response.get('content', []):
                if content_item.get('type') == 'text':
                    text = content_item.get('text', '')
                    if '{' in text and '}' in text:
                        start = text.find('{')
                        end = text.rfind('}') + 1
                        return json.loads(text[start:end])
            
            raise ValueError("Could not extract structured response from response format")
            
        except Exception as e:
            logger.error(f"Failed to extract structured response: {str(e)}")
            logger.error(f"Response format: {type(response)}, keys: {list(response.keys()) if isinstance(response, dict) else 'N/A'}")
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
    
    def extract_citations_from_response(self, response: Dict) -> List[Dict]:
        """Extract citations from Claude's web search response."""
        citations = []
        try:
            # Look for web_search_tool_result blocks (new format)
            for content_item in response.get('content', []):
                if content_item.get('type') == 'web_search_tool_result':
                    tool_content = content_item.get('content', [])
                    for result_item in tool_content:
                        if result_item.get('type') == 'web_search_result':
                            citation = {
                                'url': result_item.get('url', ''),
                                'title': result_item.get('title', ''),
                                'cited_text': '',  # Removed encrypted content to reduce costs
                                'encrypted_index': ''  # Removed encrypted index to reduce costs
                            }
                            citations.append(citation)
                
                # Legacy format support - tool_use blocks with web_search
                elif content_item.get('type') == 'tool_use' and content_item.get('name') == 'web_search':
                    tool_result = content_item.get('input', {})
                    if 'citations' in tool_result:
                        for citation in tool_result['citations']:
                            # Handle both dict and string citations
                            if isinstance(citation, dict):
                                citations.append({
                                    'url': citation.get('url', ''),
                                    'title': citation.get('title', ''),
                                    'cited_text': citation.get('cited_text', ''),
                                    'encrypted_index': citation.get('encrypted_index', '')
                                })
                            elif isinstance(citation, str):
                                # If citation is a string, use it as the title
                                citations.append({
                                    'url': '',
                                    'title': citation,
                                    'cited_text': '',
                                    'encrypted_index': ''
                                })
                
                # Legacy format support - tool_result blocks
                elif content_item.get('type') == 'tool_result':
                    tool_content = content_item.get('content', [])
                    for tool_item in tool_content:
                        if isinstance(tool_item, dict) and 'citations' in tool_item:
                            for citation in tool_item['citations']:
                                # Handle both dict and string citations
                                if isinstance(citation, dict):
                                    citations.append({
                                        'url': citation.get('url', ''),
                                        'title': citation.get('title', ''),
                                        'cited_text': citation.get('cited_text', ''),
                                        'encrypted_index': citation.get('encrypted_index', '')
                                    })
                                elif isinstance(citation, str):
                                    # If citation is a string, use it as the title
                                    citations.append({
                                        'url': '',
                                        'title': citation,
                                        'cited_text': '',
                                        'encrypted_index': ''
                                    })
            
            logger.debug(f"Extracted &citations from Claude response")
            return citations
            
        except Exception as e:
            logger.error(f"Failed to extract citations from response: {str(e)}")
            return []
    
    def extract_citations_from_perplexity_response(self, response: Dict) -> List[Dict]:
        """Extract citations from Perplexity's search_results response."""
        citations = []
        try:
            # Extract from search_results array (contains snippets/quotes)
            search_results = response.get('search_results', [])
            for result in search_results:
                citation = {
                    'url': result.get('url', ''),
                    'title': result.get('title', ''),
                    'cited_text': result.get('snippet', ''),  # This is the quote/snippet
                    'date': result.get('date', ''),
                    'last_updated': result.get('last_updated', '')
                }
                citations.append(citation)
            
            # Also extract from citations array (just URLs)
            citation_urls = response.get('citations', [])
            existing_urls = {c['url'] for c in citations}
            for url in citation_urls:
                if url not in existing_urls:
                    citations.append({
                        'url': url,
                        'title': '',
                        'cited_text': '',
                        'date': '',
                        'last_updated': ''
                    })
            
            logger.debug(f"Extracted &citations from Perplexity response ({len(search_results)} with snippets)")
            return citations
            
        except Exception as e:
            logger.error(f"Failed to extract citations from Perplexity response: {str(e)}")
            return []

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
                            logger.debug(f"Claude API Token Usage - Input: {token_usage['input_tokens']}, "
                                       f"Output: {token_usage['output_tokens']}, "
                                       f"Cache Creation: {token_usage['cache_creation_tokens']}, "
                                       f"Cache Read: {token_usage['cache_read_tokens']}, "
                                       f"Total: {token_usage['total_tokens']}")
                            
                            # Cache the response
                            if use_cache and cache_key:
                                await self._save_to_cache(cache_key, response_json, token_usage, processing_time, normalized_model, 'anthropic')
                            
                            if attempt > 0:
                                logger.debug(f"[SUCCESS] Claude API call succeeded on attempt {attempt + 1}")

                            # Monitor for legacy model references in response content
                            response_str = json.dumps(response_json).lower()
                            if 'sonnet-3' in response_str or '3-5-sonnet' in response_str or '3.5-sonnet' in response_str or 'claude-3' in response_str:
                                logger.warning(f"[LEGACY_MODEL_REFERENCE] Response from {normalized_model} contains references to legacy Sonnet 3.x models. This may indicate model confusion.")

                            return {
                                'response': response_json,
                                'token_usage': token_usage,
                                'processing_time': processing_time,
                                'is_cached': False,  # BULLETPROOF: Always False for fresh API calls  # BULLETPROOF: Always False for fresh API calls
                                'citations': self.extract_citations_from_response(response_json)
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
                                         cache_key: str, start_time: datetime, max_web_searches: int = 0) -> Dict:
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
                        
                        # Generate enhanced metrics for this call
                        try:
                            enhanced_data = self.get_enhanced_call_metrics(
                                response_json, normalized_model, processing_time, is_cached=False,
                                max_web_searches=max_web_searches
                            )
                        except Exception as e:
                            logger.warning(f"Failed to generate enhanced metrics for call_structured_api: {e}")
                            enhanced_data = {}
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False,  # BULLETPROOF: Always False for fresh API calls
                            'citations': self.extract_citations_from_response(response_json),
                            'enhanced_data': enhanced_data
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
                                                     use_cache: bool, cache_key: str, start_time: datetime,
                                                     search_context_size: str = "low", debug_name: str = None, max_tokens: int = 8000) -> Dict:
        """Make a single Perplexity API call for structured output."""
        # Perplexity supports structured output via response_format
        headers = {
            "Authorization": f"Bearer {self.perplexity_api_key}",
            "Content-Type": "application/json"
        }
        
        # Extract the actual validation schema from the tool schema format
        # The schema comes in as {"type": "object", "properties": {"validation_results": {...}}, "required": [...]}
        # We need to extract the validation_results schema and use the proper Perplexity format
        actual_schema = schema
        if (isinstance(schema, dict) and 
            schema.get('type') == 'object' and 
            'properties' in schema and 
            'validation_results' in schema['properties']):
            # Extract the actual validation results schema
            actual_schema = schema['properties']['validation_results']
            logger.debug(f"Extracted validation_results schema from tool format for Perplexity API")
        
        # Enforce provider token limits to prevent API errors
        enforced_max_tokens = self._enforce_provider_token_limit(model, max_tokens)

        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Return your answer in valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": enforced_max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "schema": actual_schema
                }
            },
            "web_search_options": {
                "search_context_size": search_context_size
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
                                                  response_json, context="structured_call_success", debug_name=debug_name)
                        
                        token_usage = self._extract_token_usage(response_json, model, "low")
                        
                        # Generate enhanced metrics for this call
                        try:
                            enhanced_data = self.get_enhanced_call_metrics(
                                response_json, model, processing_time, is_cached=False
                            )
                        except Exception as e:
                            logger.warning(f"Failed to generate enhanced metrics for Perplexity call: {e}")
                            enhanced_data = {}
                        
                        # Cache the response
                        if use_cache and cache_key:
                            await self._save_to_cache(cache_key, response_json, token_usage, processing_time, model, 'perplexity')
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False,  # BULLETPROOF: Always False for fresh API calls
                            'citations': self.extract_citations_from_perplexity_response(response_json),
                            'enhanced_data': enhanced_data
                        }
                    else:
                        error_text = await response.text()
                        error = Exception(f"Perplexity API returned status {response.status}: {error_text}")
                        await self._save_debug_data('perplexity', model, debug_request, 
                                                  error_text, error=error, context=f"structured_call_status_{response.status}", debug_name=debug_name)
                        raise error
                        
        except asyncio.TimeoutError as e:
            timeout_error = Exception(f"Perplexity API timeout: {str(e)}")
            await self._save_debug_data('perplexity', model, debug_request, 
                                      None, error=timeout_error, context="structured_call_timeout", debug_name=debug_name)
            raise timeout_error
        except Exception as e:
            await self._save_debug_data('perplexity', model, debug_request, 
                                      None, error=e, context="structured_call_exception", debug_name=debug_name)
            raise

# Global instance for easy import
ai_client = AIAPIClient()