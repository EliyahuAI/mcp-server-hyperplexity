
import json
import logging
import hashlib
import re
import os
import asyncio
import traceback
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from .utils import extract_content_description

logger = logging.getLogger(__name__)

class CacheHandler:
    """
    Handles S3 caching and debug data storage.
    """
    def __init__(self, s3_bucket: str, s3_session, use_unified_structure: bool = False):
        self.s3_bucket = s3_bucket
        self.s3_session = s3_session
        self.use_unified_structure = use_unified_structure

    def get_cache_key(self, prompt: str, model, schema: Dict = None, context: str = "", max_web_searches: int = 3,
                       soft_schema: bool = False, include_domains: Optional[List[str]] = None,
                       exclude_domains: Optional[List[str]] = None) -> str:
        """Generate a unique cache key for the request. Model can be str or List[str]."""
        # Normalize prompt whitespace
        normalized_prompt = re.sub(r'\s+', ' ', prompt).strip()
        schema_str = json.dumps(schema, sort_keys=True) if schema else ""
        sorted_include = sorted(include_domains) if include_domains else []
        sorted_exclude = sorted(exclude_domains) if exclude_domains else []

        # Handle model as string or list
        model_str = json.dumps(model) if isinstance(model, list) else model

        cache_input = f"{normalized_prompt}:{model_str}:{schema_str}:{context}:{max_web_searches}:{sorted_include}:{sorted_exclude}"
        return hashlib.md5(cache_input.encode()).hexdigest()

    def get_validation_cache_key(self, row_data: Dict, targets: List, model, search_context_size: str = "low", config_hash: str = "") -> str:
        """Generate a cache key based on core validation data. Model can be str or List[str]."""
        cache_components = {
            'row_data': {k: str(v) for k, v in row_data.items()},
            'targets': [{'column': t.column if hasattr(t, 'column') else str(t),
                        'importance': t.importance if hasattr(t, 'importance') else '',
                        'format': t.format if hasattr(t, 'format') else ''} for t in targets],
            'model': model if isinstance(model, str) else json.dumps(model),
            'search_context_size': search_context_size,
            'config_hash': config_hash
        }
        cache_input = json.dumps(cache_components, sort_keys=True)
        return hashlib.md5(cache_input.encode()).hexdigest()

    def _get_cache_s3_key(self, cache_key: str, api_provider: str) -> str:
        """Generate S3 key for cache based on structure type."""
        if self.use_unified_structure:
            service = 'claude' if api_provider == 'anthropic' else 'perplexity'
            return f"cache/{service}/{cache_key}/response.json"
        else:
            cache_prefix = 'claude_cache' if api_provider == 'anthropic' else 'validation_cache'
            return f"{cache_prefix}/{cache_key}.json"

    async def check_cache(self, cache_key: str, api_provider: str = 'claude', cache_ttl_days: int = 1) -> Optional[Dict]:
        """Check if response is cached. Returns cached data with 'expired' flag if found."""
        try:
            s3_key = self._get_cache_s3_key(cache_key, api_provider)
            logger.debug(f"Checking S3 cache: {s3_key}")

            async with self.s3_session.client('s3') as s3_client:
                try:
                    cache_response = await s3_client.get_object(Bucket=self.s3_bucket, Key=s3_key)
                    async with cache_response['Body'] as stream:
                        cache_body = await stream.read()
                except Exception as e:
                    if 'NoSuchKey' in str(e) or '404' in str(e):
                        return None
                    raise

            if not cache_body:
                return None

            cached_data = json.loads(cache_body)
            if not isinstance(cached_data, dict) or 'api_response' not in cached_data:
                return None

            # Fix legacy token usage
            if 'token_usage' in cached_data:
                usage = cached_data['token_usage']
                provider = usage.get('api_provider', api_provider)
                if provider == 'perplexity':
                    if 'input_tokens' not in usage and 'prompt_tokens' in usage:
                        usage['input_tokens'] = usage['prompt_tokens']
                    if 'output_tokens' not in usage and 'completion_tokens' in usage:
                        usage['output_tokens'] = usage['completion_tokens']

            # Check cache TTL expiration
            cached_at_str = cached_data.get('cached_at')
            if cached_at_str:
                try:
                    # Handle both formats: with and without timezone
                    if cached_at_str.endswith('Z'):
                        cached_at_str = cached_at_str.replace('Z', '+00:00')
                    cached_at = datetime.fromisoformat(cached_at_str)
                    # Ensure timezone-aware comparison
                    if cached_at.tzinfo is None:
                        cached_at = cached_at.replace(tzinfo=timezone.utc)
                    age = datetime.now(timezone.utc) - cached_at
                    if age > timedelta(days=cache_ttl_days):
                        logger.info(f"Cache expired: {cache_key[:16]}... (age: {age.days}d {age.seconds//3600}h, TTL: {cache_ttl_days} days)")
                        cached_data['expired'] = True
                        # Store age info for format_expired_cache_context
                        cached_data['_cache_age_seconds'] = age.total_seconds()
                        cached_data['_cached_at_parsed'] = cached_at.isoformat()
                    else:
                        cached_data['expired'] = False
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse cached_at timestamp: {cached_at_str}, treating as valid: {e}")
                    cached_data['expired'] = False
            else:
                # No timestamp - treat as valid (legacy cache entries)
                cached_data['expired'] = False

            return cached_data

        except Exception as e:
            logger.error(f"Cache check failed: {e}")
            return None

    def format_expired_cache_context(self, cached_data: Dict) -> str:
        """Format expired cache result and citations for prompt injection."""
        result = cached_data.get('api_response', {})
        citations = cached_data.get('citations', [])

        # Format cache age (absolute and relative time)
        age_str = ""
        cached_at_str = cached_data.get('_cached_at_parsed') or cached_data.get('cached_at', '')
        age_seconds = cached_data.get('_cache_age_seconds')

        if age_seconds is not None:
            # Calculate relative time
            age_days = age_seconds / 86400  # seconds per day
            if age_days >= 1:
                age_str = f"{age_days:.1f} days ago"
            else:
                age_hours = age_seconds / 3600
                age_str = f"{age_hours:.1f} hours ago"

        # Build the timestamp line
        if cached_at_str and age_str:
            timestamp_line = f"Cached at: {cached_at_str} ({age_str})\n"
        elif cached_at_str:
            timestamp_line = f"Cached at: {cached_at_str}\n"
        elif age_str:
            timestamp_line = f"Cache age: {age_str}\n"
        else:
            timestamp_line = ""

        context = "\n\n--- Expired cache result (check for newer information): ---\n"
        context += timestamp_line

        # Format the result - handle different response structures
        if isinstance(result, dict):
            # Try to extract the actual content
            if 'choices' in result and result['choices']:
                choice = result['choices'][0]
                if 'message' in choice and 'content' in choice['message']:
                    content = choice['message'].get('content', '')
                    context += f"Previous result: {content}\n"
                else:
                    context += f"Previous result: {json.dumps(result, indent=2)}\n"
            else:
                context += f"Previous result: {json.dumps(result, indent=2)}\n"
        else:
            context += f"Previous result: {result}\n"

        if citations:
            context += f"Previous citations: {', '.join(str(c) for c in citations)}\n"

        context += "--- End expired cache ---\n"
        return context

    async def save_to_cache(self, cache_key: str, response: Dict, token_usage: Dict, processing_time: float, model: str, api_provider: str = 'anthropic', enhanced_metrics: Dict = None, citations: List = None):
        """Save response to cache."""
        try:
            # Extract time_estimated from enhanced_metrics if available (critical for proper timing aggregation)
            time_estimated = processing_time
            if enhanced_metrics and 'timing' in enhanced_metrics:
                time_estimated = enhanced_metrics['timing'].get('time_estimated_seconds', processing_time)

            cache_entry = {
                'api_response': response,
                'cached_at': datetime.now(timezone.utc).isoformat(),
                'model': model,
                'token_usage': token_usage,
                'processing_time': processing_time,
                'time_estimated': time_estimated,  # Preserve original estimated time for aggregation
                'enhanced_data': enhanced_metrics,
                'citations': citations or []  # Store citations directly for clone/other providers
            }

            s3_key = self._get_cache_s3_key(cache_key, api_provider)
            async with self.s3_session.client('s3') as s3_client:
                await s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=json.dumps(cache_entry),
                    ContentType='application/json'
                )
            logger.debug(f"Cached response: {s3_key}")
        except Exception as e:
            logger.error(f"Failed to cache response: {e}")

    async def save_debug_data(self, api_provider: str, model: str, request_data: Dict,
                              response_data: Any, error: Exception = None, context: str = "", debug_name: str = None,
                              cache_key: str = None) -> Optional[str]:
        """Save debug data for API calls. Returns S3 URI if saved, None otherwise."""
        if os.environ.get('DISABLE_AI_DEBUG_SAVES', '').lower() == 'true':
            return None

        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            status = "ERROR" if error else "SUCCESS"
            model_clean = model.replace('/', '_').replace(':', '_')

            if debug_name:
                name_clean = ''.join(c for c in debug_name if c.isalnum() or c in '_-').strip()[:30]
                content_description = name_clean if name_clean else 'custom'
            else:
                content_description = extract_content_description(request_data)

            debug_filename = f"{timestamp}_{api_provider}_{model_clean}_{status}_{content_description}.json"

            debug_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'api_provider': api_provider,
                'model': model,
                'status': status,
                'context': context,
                'request': request_data,
                'response': None if error else response_data,
                'error': str(error) if error else None,
                'stack_trace': traceback.format_exc() if error else None
            }

            if cache_key:
                debug_entry['cache_key'] = cache_key

            # Determine S3 key
            is_refusal = error and ('[REFUSAL]' in str(error) or 'stop_reason=refusal' in str(error))
            if is_refusal:
                path = "debug/refusals" if self.use_unified_structure else "api_debug/refusals"
            elif api_provider == 'openrouter' and '/' in model:
                # Subfolder per vendor: debug/openrouter/minimax/, debug/openrouter/moonshotai/
                vendor = model.split('/')[0]
                path = f"debug/{api_provider}/{vendor}" if self.use_unified_structure else f"api_debug/{api_provider}/{vendor}"
            else:
                path = f"debug/{api_provider}" if self.use_unified_structure else f"api_debug/{api_provider}"

            s3_key = f"{path}/{debug_filename}"

            async with self.s3_session.client('s3') as s3_client:
                await s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=json.dumps(debug_entry, indent=2, ensure_ascii=False),
                    ContentType='application/json'
                )

            if error:
                logger.error(f"Saved error debug: {s3_key}")

            return f"s3://{self.s3_bucket}/{s3_key}"

        except Exception as e:
            logger.error(f"Failed to save debug data: {e}")
            return None

    async def save_markdown_log(self, api_provider: str, model: str, markdown_content: str, debug_name: str = None) -> Optional[str]:
        """Save markdown log alongside standard debug data. Returns S3 URI if saved, None otherwise."""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            model_clean = model.replace('/', '_').replace(':', '_')

            if debug_name:
                filename = f"{timestamp}_{model_clean}_{debug_name}.md"
            else:
                filename = f"{timestamp}_{model_clean}.md"

            # Store in debug folder alongside JSON debug files
            if api_provider == 'openrouter' and '/' in model:
                vendor = model.split('/')[0]
                path = f"debug/{api_provider}/{vendor}" if self.use_unified_structure else f"api_debug/{api_provider}/{vendor}"
            else:
                path = f"debug/{api_provider}" if self.use_unified_structure else f"api_debug/{api_provider}"
            s3_key = f"{path}/{filename}"

            async with self.s3_session.client('s3') as s3_client:
                await s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=markdown_content.encode('utf-8'),
                    ContentType='text/markdown'
                )

            return f"s3://{self.s3_bucket}/{s3_key}"

        except Exception as e:
            logger.error(f"Failed to save markdown log: {e}")
            return None

    async def save_haiku_repair_data(self, original_provider: str, original_model: str,
                                      malformed_input: str, repaired_output: Dict,
                                      repair_explanation: str, repair_cost: float = 0.0):
        """Save Haiku repair data to S3 debug folder under haiku_repairs."""
        if os.environ.get('DISABLE_AI_DEBUG_SAVES', '').lower() == 'true':
            return

        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            original_model_clean = original_model.replace('/', '_').replace(':', '_')

            repair_filename = f"{timestamp}_{original_provider}_{original_model_clean}_haiku_repair.json"

            repair_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'original_provider': original_provider,
                'original_model': original_model,
                'repair_model': 'claude-haiku-4-5',
                'repair_explanation': repair_explanation,
                'repair_cost': repair_cost,
                'malformed_input': malformed_input,
                'repaired_output': repaired_output
            }

            # Save to haiku_repairs subfolder
            path = "debug/haiku_repairs" if self.use_unified_structure else "api_debug/haiku_repairs"
            s3_key = f"{path}/{repair_filename}"

            async with self.s3_session.client('s3') as s3_client:
                await s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=json.dumps(repair_entry, indent=2, ensure_ascii=False),
                    ContentType='application/json'
                )

            logger.info(f"[HAIKU_REPAIR] Saved repair data: {s3_key}")

        except Exception as e:
            logger.error(f"Failed to save Haiku repair data: {e}")

    async def move_bad_cache_to_debug(self, cache_key: str, api_provider: str, failure_reason: str,
                                       prompt: str = None, expected_columns: List[str] = None,
                                       actual_columns: List[str] = None, cached_response: Dict = None) -> bool:
        """Move bad cache entry to debug."""
        try:
            s3_key = self._get_cache_s3_key(cache_key, api_provider)
            
            # Try to fetch existing
            try:
                async with self.s3_session.client('s3') as s3_client:
                    resp = await s3_client.get_object(Bucket=self.s3_bucket, Key=s3_key)
                    cache_data = json.loads(await resp['Body'].read())
            except Exception:
                cache_data = cached_response or {}

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            service = 'claude' if api_provider == 'anthropic' else 'perplexity'
            
            debug_entry = {
                'failure_reason': failure_reason,
                'cache_key': cache_key,
                'rejected_at': datetime.now(timezone.utc).isoformat(),
                'cached_data': cache_data,
                'prompt_preview': prompt if prompt else None
            }
            
            debug_key = f"debug/bad_cache/{service}/{timestamp}_{cache_key[:8]}_rejected.json"
            
            async with self.s3_session.client('s3') as s3_client:
                await s3_client.put_object(Bucket=self.s3_bucket, Key=debug_key, Body=json.dumps(debug_entry))
                await s3_client.delete_object(Bucket=self.s3_bucket, Key=s3_key)
            
            logger.debug(f"Moved bad cache {s3_key} to {debug_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to move bad cache: {e}")
            return False
