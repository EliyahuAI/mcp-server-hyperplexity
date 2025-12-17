
import json
import logging
import random
import asyncio
import aiohttp
from datetime import datetime

from ..utils import (
    normalize_anthropic_model,
    extract_citations_from_response,
    validate_and_normalize_soft_schema,
    extract_content_description,
    extract_json_from_text
)

logger = logging.getLogger(__name__)

class AnthropicProvider:
    def __init__(self, api_key: str, cache_handler, usage_handler):
        self.api_key = api_key
        self.cache_handler = cache_handler
        self.usage_handler = usage_handler

    async def call_text_api(self, prompt: str, model: str, use_cache: bool, context: str, max_web_searches: int):
        normalized_model = normalize_anthropic_model(model)
        cache_key = self.cache_handler.get_cache_key(prompt, normalized_model, None, context, max_web_searches) if use_cache else None

        if use_cache and cache_key:
            cached_data = await self.cache_handler.check_cache(cache_key, 'anthropic')
            if cached_data:
                token_usage = cached_data.get('token_usage', {})
                # Generate enhanced metrics for cached response
                enhanced_data = self.usage_handler.get_enhanced_call_metrics(
                    cached_data['api_response'], normalized_model, 0.001,
                    pre_extracted_token_usage=token_usage, is_cached=True
                )
                
                return {
                    'response': cached_data['api_response'],
                    'token_usage': token_usage,
                    'processing_time': cached_data.get('processing_time', 0),
                    'is_cached': True,
                    'citations': extract_citations_from_response(cached_data['api_response']),
                    'enhanced_data': enhanced_data,
                    'cache_key': cache_key
                }

        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': self.api_key,
            'anthropic-version': '2023-06-01'
        }
        
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
        return await self._make_api_call_with_retry("https://api.anthropic.com/v1/messages", headers, data, normalized_model, use_cache, cache_key, start_time)

    async def make_single_call(self, url: str, headers: dict, data: dict, normalized_model: str, use_cache: bool, cache_key: str, start_time: datetime, max_web_searches: int, soft_schema: bool, schema: dict):
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

                        # Check for refusal
                        if response_json.get('stop_reason') == 'refusal':
                            await self.cache_handler.save_debug_data('anthropic', normalized_model, debug_request, response_json, context="refusal", cache_key=cache_key)
                            raise Exception(f"[REFUSAL] Model {normalized_model} refused request")

                        # Check for max_tokens
                        if response_json.get('stop_reason') == 'max_tokens':
                            await self.cache_handler.save_debug_data('anthropic', normalized_model, debug_request, response_json, context="max_tokens_truncated", cache_key=cache_key)
                            output_tokens = response_json.get('usage', {}).get('output_tokens', 0)
                            raise Exception(f"[MAX_TOKENS] limit={data.get('max_tokens')} output={output_tokens}")

                        if soft_schema:
                            # Clean soft schema response
                            response_json = self._clean_soft_schema_response(response_json, schema)

                        await self.cache_handler.save_debug_data('anthropic', normalized_model, debug_request, response_json, context="single_call_success", cache_key=cache_key)
                        
                        token_usage = self.usage_handler.extract_token_usage(response_json, normalized_model)
                        
                        if use_cache and cache_key:
                            await self.cache_handler.save_to_cache(cache_key, response_json, token_usage, processing_time, normalized_model, 'anthropic')
                        
                        enhanced_data = self.usage_handler.get_enhanced_call_metrics(
                            response_json, normalized_model, processing_time, is_cached=False, max_web_searches=max_web_searches
                        )
                        
                        return {
                            'response': response_json,
                            'token_usage': token_usage,
                            'processing_time': processing_time,
                            'is_cached': False,
                            'citations': extract_citations_from_response(response_json),
                            'enhanced_data': enhanced_data
                        }
                    else:
                        error = Exception(f"Anthropic API status {response.status}: {response_text}")
                        await self.cache_handler.save_debug_data('anthropic', normalized_model, debug_request, response_text, error=error, context=f"status_{response.status}", cache_key=cache_key)
                        raise error

        except Exception as e:
            await self.cache_handler.save_debug_data('anthropic', normalized_model, debug_request, None, error=e, context="exception", cache_key=cache_key)
            raise

    async def _make_api_call_with_retry(self, url: str, headers: dict, data: dict, normalized_model: str, use_cache: bool, cache_key: str, start_time: datetime) -> dict:
        max_retries = 3
        base_delay = 2.0
        debug_request = {'url': url, 'headers': {k: 'REDACTED' if k=='X-API-Key' else v for k,v in headers.items()}, 'data': data}

        for attempt in range(max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=data) as response:
                        processing_time = (datetime.now() - start_time).total_seconds()
                        response_text = await response.text()

                        if response.status == 200:
                            response_json = json.loads(response_text)
                            await self.cache_handler.save_debug_data('anthropic', normalized_model, debug_request, response_json, context=f"attempt_{attempt}")
                            token_usage = self.usage_handler.extract_token_usage(response_json, normalized_model)
                            
                            if use_cache and cache_key:
                                await self.cache_handler.save_to_cache(cache_key, response_json, token_usage, processing_time, normalized_model, 'anthropic')

                            return {
                                'response': response_json,
                                'token_usage': token_usage,
                                'processing_time': processing_time,
                                'is_cached': False,
                                'citations': extract_citations_from_response(response_json),
                                'cache_key': cache_key
                            }
                        elif response.status in [502, 503, 529]:
                            if attempt < max_retries:
                                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                                logger.warning(f"Anthropic retry {attempt+1}/{max_retries} due to {response.status}")
                                await asyncio.sleep(delay)
                                continue
                            else:
                                raise Exception(f"Anthropic API failed after retries: {response.status} {response_text}")
                        else:
                            raise Exception(f"Anthropic API error {response.status}: {response_text}")
            except Exception as e:
                if "retry" in str(e).lower(): raise
                logger.error(f"Error calling Anthropic: {e}")
                if attempt == max_retries: raise
                await asyncio.sleep(base_delay * (2 ** attempt))

    def _clean_soft_schema_response(self, response_json: dict, schema: dict) -> dict:
        try:
            if 'content' in response_json:
                text_content = ""
                for block in response_json['content']:
                    if block.get('type') == 'text': text_content += block.get('text', '')
                
                parsed = extract_json_from_text(text_content)
                
                if parsed:
                    if schema:
                        normalized, warnings = validate_and_normalize_soft_schema(parsed, schema, fuzzy_keys=True)
                        if warnings:
                            logger.warning(f"Soft schema warnings: {warnings}")
                        parsed = normalized
                    
                    return {
                        'choices': [{'message': {'role': 'assistant', 'content': json.dumps(parsed)}}],
                        'id': response_json.get('id'),
                        'model': response_json.get('model'),
                        'usage': response_json.get('usage'),
                        'stop_reason': response_json.get('stop_reason')
                    }
            return response_json
        except Exception as e:
            logger.error(f"Soft schema cleaning failed: {e}")
            return response_json
