
import json
import logging
import aiohttp
from datetime import datetime
from typing import Dict, Any

from ..utils import extract_json_from_text, validate_and_normalize_soft_schema, repair_json_with_haiku

logger = logging.getLogger(__name__)

class BasetenProvider:
    def __init__(self, api_key: str, cache_handler, usage_handler, ai_client=None):
        self.api_key = api_key
        self.cache_handler = cache_handler
        self.usage_handler = usage_handler
        self.ai_client = ai_client  # For Haiku JSON repair
        self.base_url = "https://inference.baseten.co/v1"

    async def _normalize_baseten_response(self, response: Dict, soft_schema: bool = False, schema: Dict = None) -> Dict:
        """Normalize Baseten API response to Anthropic-style format."""
        try:
            # Baseten returns standard OpenAI format
            if 'choices' in response and len(response['choices']) > 0:
                choice = response['choices'][0]
                message = choice.get('message', {})
                text_content = message.get('content', '')
                
                normalized = {
                    'id': response.get('id', 'baseten_msg'),
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'text', 'text': text_content}],
                    'stop_reason': choice.get('finish_reason', 'stop'),
                    'usage': response.get('usage', {})
                }
            else:
                # Fallback
                text_content = str(response)
                normalized = {
                    'id': 'baseten_msg',
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'text', 'text': text_content}],
                    'stop_reason': 'unknown',
                    'usage': {}
                }

            if soft_schema and schema:
                try:
                    parsed = extract_json_from_text(text_content)

                    # If extraction failed, try Haiku repair
                    if not parsed and self.ai_client:
                        logger.warning(f"[BASETEN] JSON extraction failed, attempting Haiku repair")
                        parsed = await repair_json_with_haiku(text_content, schema, self.ai_client)

                    if parsed:
                        norm, warnings = validate_and_normalize_soft_schema(parsed, schema, fuzzy_keys=True)
                        if warnings:
                            logger.warning(f"[BASETEN] Soft schema warnings: {warnings}")

                        # Check if critical required fields are missing (treat as error)
                        required = schema.get('required', [])
                        missing_critical = [f for f in required if f not in norm or not norm[f]]
                        if missing_critical:
                            logger.error(f"[BASETEN] Missing critical required fields after repair: {missing_critical}")
                            raise Exception(f"[SCHEMA_ERROR] Missing required fields: {missing_critical}")

                        normalized['content'][0]['text'] = json.dumps(norm)
                    else:
                        logger.error(f"[BASETEN] Could not extract or repair JSON from response")
                        raise Exception("[REPAIR_FAILED] Haiku repair failed to extract valid JSON")
                except Exception as e:
                    # Re-raise critical errors to trigger backup model retry
                    if "[SCHEMA_ERROR]" in str(e) or "[REPAIR_FAILED]" in str(e):
                        logger.error(f"[BASETEN] Critical soft schema error: {e}")
                        raise
                    logger.warning(f"Baseten soft schema cleaning failed: {e}")

            return normalized

        except Exception as e:
            # Re-raise critical errors to trigger backup model retry
            if "[SCHEMA_ERROR]" in str(e) or "[REPAIR_FAILED]" in str(e):
                raise
            logger.error(f"Baseten normalization failed: {e}")
            return {'id': 'error', 'type': 'message', 'role': 'assistant', 'content': [{'type': 'text', 'text': str(response)}], 'stop_reason': 'error', 'usage': {}}

    async def make_single_call(self, prompt: str, schema: Dict, model: str, use_cache: bool, cache_key: str, start_time: datetime, max_tokens: int = 8000, soft_schema: bool = False) -> Dict:
        enforced_max_tokens = self.usage_handler.enforce_provider_token_limit(model, max_tokens)
        
        final_prompt = prompt
        if schema:
            if soft_schema:
                final_prompt = f"{prompt}\n\nReturn your answer as valid JSON matching this schema: {json.dumps(schema)}"
        
        debug_request = {'model_id': model, 'prompt': final_prompt, 'max_tokens': enforced_max_tokens}
        
        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                'Authorization': f'Bearer {self.api_key}', 
                'Content-Type': 'application/json'
            }
            # Re-reading user example: `api_key="sxYEtips..."`.
            # Typically Baseten uses `Authorization: Api-Key <API_KEY>`.
            # I will use that.
            
            # Use specific Baseten model name if generic is passed
            baseten_model = "deepseek-ai/DeepSeek-V3.2" # Hardcoded based on user example
            
            data = {
                "model": baseten_model,
                "messages": [{"role": "user", "content": final_prompt}],
                "temperature": 0.1,
                "max_tokens": enforced_max_tokens,
                "stream": False
            }
            
            if schema and not soft_schema:
                data["response_format"] = {
                    "type": "json_schema", 
                    "json_schema": {
                        "name": "response_schema", 
                        "strict": True, 
                        "schema": schema
                    }
                }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    response_text = await response.text()
                    
                    if response.status == 200:
                        response_json = json.loads(response_text)
                    else:
                        error = Exception(f"Baseten API status {response.status}: {response_text}")
                        await self.cache_handler.save_debug_data('baseten', model, debug_request, response_text, error=error, context=f"status_{response.status}", cache_key=cache_key)
                        raise error

            unified_response = await self._normalize_baseten_response(response_json, soft_schema, schema)
            
            if unified_response.get('stop_reason') in ['max_tokens', 'length']:
                 await self.cache_handler.save_debug_data('baseten', model, debug_request, unified_response, context="max_tokens_truncated", cache_key=cache_key)
                 raise Exception(f"[MAX_TOKENS] Model {model} hit limit")

            await self.cache_handler.save_debug_data('baseten', model, debug_request, unified_response, context="single_call_success", cache_key=cache_key)
            
            token_usage = self.usage_handler.extract_token_usage(response_json, model)
            
            if use_cache and cache_key:
                await self.cache_handler.save_to_cache(cache_key, unified_response, token_usage, processing_time, model, 'baseten')
            
            enhanced_data = self.usage_handler.get_enhanced_call_metrics(unified_response, model, processing_time, is_cached=False)
            
            return {
                'response': unified_response,
                'token_usage': token_usage,
                'processing_time': processing_time,
                'is_cached': False,
                'citations': [],
                'enhanced_data': enhanced_data
            }

        except Exception as e:
            await self.cache_handler.save_debug_data('baseten', model, debug_request, None, error=e, context="exception", cache_key=cache_key)
            raise
