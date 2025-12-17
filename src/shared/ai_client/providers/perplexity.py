
import json
import logging
import asyncio
import aiohttp
import re
from datetime import datetime
from typing import Dict, List, Optional
from perplexity_schema import get_response_format_schema

from ..utils import (
    extract_citations_from_perplexity_response,
    validate_and_normalize_soft_schema
)

logger = logging.getLogger(__name__)

class PerplexityProvider:
    def __init__(self, api_key: str, cache_handler, usage_handler):
        self.api_key = api_key
        self.cache_handler = cache_handler
        self.usage_handler = usage_handler

    async def validate_with_smart_cache(self, prompt: str, row_data: Dict, targets: List,
                                        model: str, search_context_size: str,
                                        use_cache: bool, config_hash: str) -> Dict:
        """Validate with Perplexity using smart caching."""
        cache_key = self.cache_handler.get_validation_cache_key(row_data, targets, model, search_context_size, config_hash) if use_cache else None
        
        if use_cache and cache_key:
            cached_data = await self.cache_handler.check_cache(cache_key, 'perplexity')
            if cached_data:
                token_usage = cached_data.get('token_usage', {})
                enhanced_data = self.usage_handler.get_enhanced_call_metrics(
                    cached_data['api_response'], model, 0.001,
                    pre_extracted_token_usage=token_usage, is_cached=True
                )
                return {
                    'response': cached_data['api_response'],
                    'token_usage': token_usage,
                    'processing_time': cached_data.get('processing_time', 0),
                    'is_cached': True,
                    'citations': extract_citations_from_perplexity_response(cached_data['api_response']),
                    'enhanced_data': enhanced_data
                }

        result = await self.validate(prompt, model, search_context_size, use_cache=False, context="")
        
        if use_cache and cache_key and not result.get('is_cached'):
            await self.cache_handler.save_to_cache(cache_key, result['response'], result['token_usage'], result['processing_time'], model, 'perplexity')
        
        return result

    async def validate(self, prompt: str, model: str, search_context_size: str, use_cache: bool,
                       context: str, include_domains: Optional[List[str]] = None,
                       exclude_domains: Optional[List[str]] = None) -> Dict:
        """Validate a prompt using Perplexity API."""
        cache_key = self.cache_handler.get_cache_key(prompt, model, None, f"{context}:{search_context_size}", 
                                                     0, False, include_domains, exclude_domains) if use_cache else None

        if use_cache and cache_key:
            cached_data = await self.cache_handler.check_cache(cache_key, 'perplexity')
            if cached_data:
                token_usage = cached_data.get('token_usage', {})
                enhanced_data = self.usage_handler.get_enhanced_call_metrics(
                    cached_data['api_response'], model, 0.001,
                    pre_extracted_token_usage=token_usage, is_cached=True
                )
                return {
                    'response': cached_data['api_response'],
                    'token_usage': token_usage,
                    'processing_time': cached_data.get('processing_time', 0),
                    'is_cached': True,
                    'citations': extract_citations_from_perplexity_response(cached_data['api_response']),
                    'enhanced_data': enhanced_data
                }

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
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
                "search_context_size": search_context_size,
                "max_tokens_per_page": {"low": 2048, "medium": 3072, "high": 4096}.get(search_context_size, 2048)
            }
        }

        if include_domains or exclude_domains:
            search_domain_filter = []
            if include_domains: search_domain_filter.extend(include_domains)
            if exclude_domains: search_domain_filter.extend([f"-{d}" for d in exclude_domains])
            data["web_search_options"]["search_domain_filter"] = search_domain_filter

        start_time = datetime.now()
        debug_request = {'url': "https://api.perplexity.ai/chat/completions", 'headers': {k: 'REDACTED' if k=='Authorization' else v for k,v in headers.items()}, 'data': data}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.perplexity.ai/chat/completions", headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    
                    if response.status == 200:
                        response_json = await response.json()
                        await self.cache_handler.save_debug_data('perplexity', model, debug_request, response_json, context=f"search_context_{search_context_size}")
                        
                        token_usage = self.usage_handler.extract_token_usage(response_json, model, search_context_size)
                        
                        if use_cache and cache_key:
                            await self.cache_handler.save_to_cache(cache_key, response_json, token_usage, processing_time, model, 'perplexity')
                        
                        enhanced_data = self.usage_handler.get_enhanced_call_metrics(
                            response_json, model, processing_time, search_context_size=search_context_size, is_cached=False
                        )
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False,
                            'citations': extract_citations_from_perplexity_response(response_json),
                            'enhanced_data': enhanced_data
                        }
                    else:
                        error_text = await response.text()
                        error = Exception(f"Perplexity API status {response.status}: {error_text}")
                        await self.cache_handler.save_debug_data('perplexity', model, debug_request, error_text, error=error, context=f"status_{response.status}")
                        raise error
        except Exception as e:
            await self.cache_handler.save_debug_data('perplexity', model, debug_request, None, error=e, context="exception")
            raise

    async def make_single_structured_call(self, prompt: str, schema: Dict, model: str, use_cache: bool,
                                          cache_key: str, start_time: datetime, search_context_size: str,
                                          debug_name: str, max_tokens: int, soft_schema: bool,
                                          include_domains: List[str], exclude_domains: List[str]) -> Dict:
        
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        
        # Extract validation_results schema if present (legacy tool format)
        actual_schema = schema
        if (isinstance(schema, dict) and schema.get('type') == 'object' and 
            'properties' in schema and 'validation_results' in schema['properties']):
            actual_schema = schema['properties']['validation_results']

        enforced_max_tokens = self.usage_handler.enforce_provider_token_limit(model, max_tokens)
        
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Return your answer in valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": enforced_max_tokens,
            "web_search_options": {
                "search_context_size": search_context_size,
                "max_tokens_per_page": {"low": 2048, "medium": 3072, "high": 4096}.get(search_context_size, 2048)
            }
        }

        if include_domains or exclude_domains:
            search_domain_filter = []
            if include_domains: search_domain_filter.extend(include_domains)
            if exclude_domains: search_domain_filter.extend([f"-{d}" for d in exclude_domains])
            data["web_search_options"]["search_domain_filter"] = search_domain_filter

        if not soft_schema:
            data["response_format"] = {"type": "json_schema", "json_schema": {"schema": actual_schema}}

        debug_request = {'url': "https://api.perplexity.ai/chat/completions", 'headers': {k: 'REDACTED' if k=='Authorization' else v for k,v in headers.items()}, 'data': data}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.perplexity.ai/chat/completions", headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    
                    if response.status == 200:
                        response_json = await response.json()
                        
                        if soft_schema:
                            response_json = self._clean_soft_schema_response(response_json, actual_schema)

                        await self.cache_handler.save_debug_data('perplexity', model, debug_request, response_json, context="structured_call_success", debug_name=debug_name)
                        token_usage = self.usage_handler.extract_token_usage(response_json, model, "low")
                        
                        if use_cache and cache_key:
                            await self.cache_handler.save_to_cache(cache_key, response_json, token_usage, processing_time, model, 'perplexity')
                        
                        enhanced_data = self.usage_handler.get_enhanced_call_metrics(response_json, model, processing_time, is_cached=False)
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False,
                            'citations': extract_citations_from_perplexity_response(response_json),
                            'enhanced_data': enhanced_data
                        }
                    else:
                        error_text = await response.text()
                        error = Exception(f"Perplexity API status {response.status}: {error_text}")
                        await self.cache_handler.save_debug_data('perplexity', model, debug_request, error_text, error=error, context=f"status_{response.status}", debug_name=debug_name)
                        raise error
        except Exception as e:
            await self.cache_handler.save_debug_data('perplexity', model, debug_request, None, error=e, context="structured_call_exception", debug_name=debug_name)
            raise

    def _clean_soft_schema_response(self, response_json: dict, schema: dict) -> dict:
        try:
            if 'choices' in response_json and response_json['choices']:
                content = response_json['choices'][0]['message']['content']
                cleaned = re.sub(r'^```json\s*|\s*```$', '', content.strip(), flags=re.MULTILINE)
                match = re.search(r'(\{.*\})', cleaned, re.DOTALL)
                if match: cleaned = match.group(1)
                
                parsed = json.loads(cleaned)
                normalized, warnings = validate_and_normalize_soft_schema(parsed, schema, fuzzy_keys=True)
                if warnings:
                    logger.warning(f"Perplexity soft schema warnings: {warnings}")
                
                response_json['choices'][0]['message']['content'] = json.dumps(normalized)
            return response_json
        except Exception as e:
            logger.error(f"Perplexity soft schema cleaning error: {e}")
            return response_json
