
import json
import logging
import hashlib
import re
import os
import asyncio
import traceback
from datetime import datetime, timezone
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

    async def check_cache(self, cache_key: str, api_provider: str = 'claude') -> Optional[Dict]:
        """Check if response is cached."""
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
            
            return cached_data

        except Exception as e:
            logger.error(f"Cache check failed: {e}")
            return None

    async def save_to_cache(self, cache_key: str, response: Dict, token_usage: Dict, processing_time: float, model: str, api_provider: str = 'anthropic', enhanced_metrics: Dict = None):
        """Save response to cache."""
        try:
            cache_entry = {
                'api_response': response,
                'cached_at': datetime.now(timezone.utc).isoformat(),
                'model': model,
                'token_usage': token_usage,
                'processing_time': processing_time,
                'enhanced_data': enhanced_metrics
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
                              cache_key: str = None):
        """Save debug data for API calls."""
        if os.environ.get('DISABLE_AI_DEBUG_SAVES', '').lower() == 'true':
            return

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
            
        except Exception as e:
            logger.error(f"Failed to save debug data: {e}")

    async def save_markdown_log(self, api_provider: str, model: str, markdown_content: str, debug_name: str = None):
        """Save markdown log alongside standard debug data."""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            model_clean = model.replace('/', '_').replace(':', '_')

            if debug_name:
                filename = f"{timestamp}_{model_clean}_{debug_name}.md"
            else:
                filename = f"{timestamp}_{model_clean}.md"

            # Store in debug folder alongside JSON debug files
            path = f"debug/{api_provider}" if self.use_unified_structure else f"api_debug/{api_provider}"
            s3_key = f"{path}/{filename}"

            async with self.s3_session.client('s3') as s3_client:
                await s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=markdown_content.encode('utf-8'),
                    ContentType='text/markdown'
                )

            logger.info(f"Saved markdown log: {s3_key}")

        except Exception as e:
            logger.error(f"Failed to save markdown log: {e}")

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
