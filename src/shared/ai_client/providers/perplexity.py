
import json
import logging
import asyncio
import aiohttp
import re
from datetime import datetime
from typing import Dict, List, Optional
from shared.perplexity_schema import get_response_format_schema

from ..utils import (
    extract_citations_from_perplexity_response,
    validate_and_normalize_soft_schema,
    extract_json_from_text,
    repair_json_with_haiku
)

logger = logging.getLogger(__name__)

class PerplexityProvider:
    def __init__(self, api_key: str, cache_handler, usage_handler, ai_client=None):
        self.api_key = api_key
        self.cache_handler = cache_handler
        self.usage_handler = usage_handler
        self.ai_client = ai_client  # For Haiku JSON repair

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
            # Pass enhanced_data for timing preservation
            enhanced_data = result.get('enhanced_data')
            await self.cache_handler.save_to_cache(cache_key, result['response'], result['token_usage'], result['processing_time'], model, 'perplexity', enhanced_data)

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
                {"role": "system", "content": "You are a data validation expert. Return raw JSON only (first char {, last char }, parseable by json.loads() as-is)."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 3000,
            "response_format": get_response_format_schema(is_multiplex=True),
            "web_search_options": {
                "search_context_size": search_context_size
                # Note: sonar models don't support max_tokens_per_page
                # Only search_context_size: "low" | "medium" | "high"
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

                        # Generate enhanced metrics BEFORE caching (needed for time_estimated preservation)
                        enhanced_data = self.usage_handler.get_enhanced_call_metrics(
                            response_json, model, processing_time, search_context_size=search_context_size, is_cached=False
                        )

                        if use_cache and cache_key:
                            await self.cache_handler.save_to_cache(cache_key, response_json, token_usage, processing_time, model, 'perplexity', enhanced_data)
                        
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
                {"role": "system", "content": "You are a helpful assistant. Return raw JSON only (first char {, last char }, parseable by json.loads() as-is)."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": enforced_max_tokens,
            "web_search_options": {
                "search_context_size": search_context_size
                # Note: sonar models don't support max_tokens_per_page
                # Only search_context_size: "low" | "medium" | "high"
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
                            response_json = await self._clean_soft_schema_response(response_json, actual_schema)

                        await self.cache_handler.save_debug_data('perplexity', model, debug_request, response_json, context="structured_call_success", debug_name=debug_name)
                        token_usage = self.usage_handler.extract_token_usage(response_json, model, "low")

                        # Generate enhanced metrics BEFORE caching (needed for time_estimated preservation)
                        enhanced_data = self.usage_handler.get_enhanced_call_metrics(response_json, model, processing_time, is_cached=False)

                        # Merge repair costs if present
                        if '_repair_meta' in response_json:
                            repair_meta = response_json['_repair_meta']
                            repair_cost = repair_meta.get('cost', 0.0)

                            if 'costs' in enhanced_data and 'actual' in enhanced_data['costs']:
                                enhanced_data['costs']['actual']['total_cost'] += repair_cost
                                enhanced_data['repair_info'] = repair_meta
                                logger.info(f"[COST_UPDATE] Added repair cost ${repair_cost:.4f} to total. New total: ${enhanced_data['costs']['actual']['total_cost']:.4f}")

                        if use_cache and cache_key:
                            await self.cache_handler.save_to_cache(cache_key, response_json, token_usage, processing_time, model, 'perplexity', enhanced_data)
                        
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

    async def _clean_soft_schema_response(self, response_json: dict, schema: dict) -> dict:
        try:
            if 'choices' in response_json and response_json['choices']:
                content = response_json['choices'][0]['message']['content']
                parsed = extract_json_from_text(content)
                repair_attempted = False

                # If extraction failed, try Haiku repair
                if not parsed and self.ai_client:
                    logger.warning(f"[PERPLEXITY] JSON extraction failed, attempting Haiku repair")
                    repair_attempted = True
                    parsed, repair_result, repair_explanation = await repair_json_with_haiku(content, schema, self.ai_client)

                    if repair_result:
                        repair_cost = repair_result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)

                        # Log the repair explanation
                        logger.info(f"[HAIKU_REPAIR] Provider: perplexity, Model: {model}")
                        logger.info(f"[HAIKU_REPAIR] Explanation: {repair_explanation}")
                        logger.info(f"[HAIKU_REPAIR] Cost: ${repair_cost:.6f}")

                        response_json['_repair_meta'] = {
                            'repaired': True,
                            'cost': repair_cost,
                            'model': 'gemini-2.5-flash-lite',
                            'provider': 'gemini',
                            'explanation': repair_explanation
                        }

                        # Save repair data to S3
                        await self.cache_handler.save_haiku_repair_data(
                            original_provider='perplexity',
                            original_model=model,
                            malformed_input=content,
                            repaired_output=parsed,
                            repair_explanation=repair_explanation or 'No explanation provided',
                            repair_cost=repair_cost
                        )

                if parsed:
                    normalized, warnings = validate_and_normalize_soft_schema(parsed, schema, fuzzy_keys=True)
                    if warnings:
                        logger.warning(f"Perplexity soft schema warnings: {warnings}")

                    # Check if required fields are present (but allow empty values)
                    # In soft_schema mode, if field exists, it's OK even if empty
                    required = schema.get('required', [])
                    missing = [f for f in required if f not in normalized]
                    if missing:
                        # Log diagnostic info
                        logger.error(f"[PERPLEXITY] Found missing required fields: {missing}")
                        logger.error(f"[PERPLEXITY] repair_attempted={repair_attempted}, ai_client_available={self.ai_client is not None}")

                        # Try Haiku repair if we haven't already
                        if not repair_attempted and self.ai_client:
                            logger.warning(f"[PERPLEXITY] Missing required fields {missing}, attempting Haiku repair")
                            repair_attempted = True
                            parsed, repair_result, repair_explanation = await repair_json_with_haiku(content, schema, self.ai_client)

                            if repair_result and parsed:
                                repair_cost = repair_result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)

                                # Log the repair explanation
                                logger.info(f"[HAIKU_REPAIR] Provider: perplexity, Model: {model}")
                                logger.info(f"[HAIKU_REPAIR] Explanation: {repair_explanation}")
                                logger.info(f"[HAIKU_REPAIR] Cost: ${repair_cost:.6f}")

                                response_json['_repair_meta'] = {
                                    'repaired': True,
                                    'cost': repair_cost,
                                    'model': 'gemini-2.5-flash-lite',
                                    'provider': 'gemini',
                                    'explanation': repair_explanation
                                }

                                # Save repair data to S3
                                await self.cache_handler.save_haiku_repair_data(
                                    original_provider='perplexity',
                                    original_model=model,
                                    malformed_input=content,
                                    repaired_output=parsed,
                                    repair_explanation=repair_explanation or 'No explanation provided',
                                    repair_cost=repair_cost
                                )

                                # Re-validate after repair
                                normalized, warnings = validate_and_normalize_soft_schema(parsed, schema, fuzzy_keys=True)
                                missing = [f for f in required if f not in normalized]

                        # If still missing after repair attempt, raise error
                        if missing:
                            logger.error(f"[PERPLEXITY] Missing required fields: {missing}")
                            raise Exception(f"[SCHEMA_ERROR] Missing required fields: {missing}")

                    response_json['choices'][0]['message']['content'] = json.dumps(normalized)
                else:
                    logger.error(f"[PERPLEXITY] Could not extract or repair JSON from response")
                    raise Exception("[REPAIR_FAILED] Haiku repair failed to extract valid JSON")

            return response_json
        except Exception as e:
            # Re-raise critical errors to trigger backup model retry
            if "[SCHEMA_ERROR]" in str(e) or "[REPAIR_FAILED]" in str(e):
                logger.error(f"[PERPLEXITY] Critical soft schema error: {e}")
                raise
            logger.error(f"Perplexity soft schema cleaning error: {e}")
            return response_json
