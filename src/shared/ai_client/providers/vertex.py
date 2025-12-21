
import json
import logging
import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, Any

from ..utils import normalize_vertex_model, extract_json_from_text, validate_and_normalize_soft_schema, repair_json_with_haiku

logger = logging.getLogger(__name__)

class VertexProvider:
    def __init__(self, project_id: str, cache_handler, usage_handler, ai_client=None):
        self.project_id = project_id
        self.cache_handler = cache_handler
        self.usage_handler = usage_handler
        self.ai_client = ai_client  # For Haiku JSON repair

    async def _get_vertex_access_token(self) -> str:
        """Get Google Cloud OAuth access token."""
        try:
            from google.auth.transport.requests import Request
            from google.auth import default
            credentials, _ = default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            if not credentials.valid:
                await asyncio.to_thread(credentials.refresh, Request())
            return credentials.token
        except Exception as e:
            logger.error(f"Failed to get Vertex access token: {e}")
            raise Exception(f"Vertex authentication failed: {e}")

    async def _normalize_vertex_response(self, vertex_response: Dict, soft_schema: bool = False, schema: Dict = None) -> Dict:
        """Normalize Vertex AI API response to Anthropic-style format."""
        try:
            # DeepSeek/OpenAI format
            if 'content' in vertex_response and isinstance(vertex_response['content'], list):
                text_content = vertex_response['content'][0].get('text', '')
                normalized = {
                    'id': vertex_response.get('id', 'vertex_msg'),
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'text', 'text': text_content}],
                    'stop_reason': vertex_response.get('stop_reason', 'stop'),
                    'usage': vertex_response.get('usage', {})
                }
            # Gemini format
            elif 'candidates' in vertex_response:
                candidate = vertex_response['candidates'][0]
                text_content = ''
                for part in candidate.get('content', {}).get('parts', []):
                    if 'text' in part: text_content += part['text']
                
                normalized = {
                    'id': vertex_response.get('id', 'vertex_msg'),
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'text', 'text': text_content}],
                    'stop_reason': candidate.get('finishReason', 'end_turn').lower(),
                    'usage': vertex_response.get('usage_metadata', vertex_response.get('usage', {}))
                }
            else:
                text_content = vertex_response.get('text', '') or str(vertex_response)
                normalized = {
                    'id': 'vertex_msg',
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'text', 'text': text_content}],
                    'stop_reason': 'end_turn',
                    'usage': vertex_response.get('usage_metadata', {})
                }

            if soft_schema and schema:
                try:
                    parsed = extract_json_from_text(text_content)
                    repair_attempted = False

                    # If extraction failed, try Haiku repair
                    if not parsed and self.ai_client:
                        logger.warning(f"[VERTEX] JSON extraction failed, attempting Haiku repair")
                        repair_attempted = True
                        parsed, repair_result, repair_explanation = await repair_json_with_haiku(text_content, schema, self.ai_client)

                        if repair_result:
                            repair_cost = repair_result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)

                            # Log the repair explanation
                            logger.info(f"[HAIKU_REPAIR] Provider: vertex, Model: {model}")
                            logger.info(f"[HAIKU_REPAIR] Explanation: {repair_explanation}")
                            logger.info(f"[HAIKU_REPAIR] Cost: ${repair_cost:.6f}")

                            # Attach repair metrics to normalized response
                            normalized['_repair_meta'] = {
                                'repaired': True,
                                'cost': repair_cost,
                                'model': 'gemini-2.0-flash',
                                'provider': 'gemini',
                                'explanation': repair_explanation
                            }

                            # Save repair data to S3
                            await self.cache_handler.save_haiku_repair_data(
                                original_provider='vertex',
                                original_model=model,
                                malformed_input=text_content,
                                repaired_output=parsed,
                                repair_explanation=repair_explanation or 'No explanation provided',
                                repair_cost=repair_cost
                            )

                    if parsed:
                        norm, warnings = validate_and_normalize_soft_schema(parsed, schema, fuzzy_keys=True)
                        if warnings:
                            logger.warning(f"[VERTEX] Soft schema warnings: {warnings}")

                        # Check if required fields are present (but allow empty values)
                        # In soft_schema mode, if field exists, it's OK even if empty
                        required = schema.get('required', [])
                        missing = [f for f in required if f not in norm]
                        if missing:
                            # Log diagnostic info
                            logger.error(f"[VERTEX] Found missing required fields: {missing}")
                            logger.error(f"[VERTEX] repair_attempted={repair_attempted}, ai_client_available={self.ai_client is not None}")

                            # Try Haiku repair if we haven't already
                            if not repair_attempted and self.ai_client:
                                logger.warning(f"[VERTEX] Missing required fields {missing}, attempting Haiku repair")
                                repair_attempted = True
                                parsed, repair_result, repair_explanation = await repair_json_with_haiku(text_content, schema, self.ai_client)

                                if repair_result and parsed:
                                    repair_cost = repair_result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)

                                    # Log the repair explanation
                                    logger.info(f"[HAIKU_REPAIR] Provider: vertex, Model: {model}")
                                    logger.info(f"[HAIKU_REPAIR] Explanation: {repair_explanation}")
                                    logger.info(f"[HAIKU_REPAIR] Cost: ${repair_cost:.6f}")

                                    # Attach repair metrics to normalized response
                                    normalized['_repair_meta'] = {
                                        'repaired': True,
                                        'cost': repair_cost,
                                        'model': 'gemini-2.0-flash',
                                        'provider': 'gemini',
                                        'explanation': repair_explanation
                                    }

                                    # Save repair data to S3
                                    await self.cache_handler.save_haiku_repair_data(
                                        original_provider='vertex',
                                        original_model=model,
                                        malformed_input=text_content,
                                        repaired_output=parsed,
                                        repair_explanation=repair_explanation or 'No explanation provided',
                                        repair_cost=repair_cost
                                    )

                                    # Re-validate after repair
                                    norm, warnings = validate_and_normalize_soft_schema(parsed, schema, fuzzy_keys=True)
                                    missing = [f for f in required if f not in norm]

                            # If still missing after repair attempt, raise error
                            if missing:
                                logger.error(f"[VERTEX] Missing required fields: {missing}")
                                raise Exception(f"[SCHEMA_ERROR] Missing required fields: {missing}")

                        normalized['content'][0]['text'] = json.dumps(norm)
                    else:
                        logger.error(f"[VERTEX] Could not extract or repair JSON from response")
                        raise Exception("[REPAIR_FAILED] Haiku repair failed to extract valid JSON")
                except Exception as e:
                    # Re-raise critical errors to trigger backup model retry
                    if "[SCHEMA_ERROR]" in str(e) or "[REPAIR_FAILED]" in str(e):
                        logger.error(f"[VERTEX] Critical soft schema error: {e}")
                        raise
                    logger.warning(f"Vertex soft schema cleaning failed: {e}")
            
            return normalized

        except Exception as e:
            logger.error(f"Vertex normalization failed: {e}")
            return {'id': 'error', 'type': 'message', 'role': 'assistant', 'content': [{'type': 'text', 'text': str(vertex_response)}], 'stop_reason': 'error', 'usage': {}}

    async def make_single_call(self, prompt: str, schema: Dict, model: str, use_cache: bool, cache_key: str, start_time: datetime, max_tokens: int = 8000, soft_schema: bool = False) -> Dict:
        enforced_max_tokens = self.usage_handler.enforce_provider_token_limit(model, max_tokens)
        
        final_prompt = prompt
        if schema:
            if soft_schema:
                final_prompt = f"""{prompt}

Return raw JSON (first char {{, last char }}}}, parseable by json.loads() as-is):
{json.dumps(schema)}"""
        
        debug_request = {'model_id': model, 'prompt': final_prompt, 'max_tokens': enforced_max_tokens}
        
        try:
            access_token = await self._get_vertex_access_token()
            url = f"https://aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/global/endpoints/openapi/chat/completions"
            headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
            
            data = {
                "model": f"deepseek-ai/{model}",
                "messages": [{"role": "user", "content": final_prompt}],
                "temperature": 0.1,
                "max_tokens": enforced_max_tokens,
                "stream": False
            }
            
            if schema and not soft_schema:
                data["response_format"] = {"type": "json_schema", "json_schema": {"name": "response_schema", "strict": True, "schema": schema}}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    response_text = await response.text()
                    
                    if response.status == 200:
                        response_json = json.loads(response_text)
                        
                        # Convert OpenAI format to Gemini/Vertex format for internal consistency if needed, 
                        # OR just use the OpenAI format structure. 
                        # The extract_vertex_token_usage handles both.
                        # I'll construct a dict that matches what _normalize_vertex_response expects
                        # The response_json here IS OpenAI format (choices/message/content)
                        # So let's pass it as is to normalization if it supports it.
                        # _normalize_vertex_response checks for 'content' list (DeepSeek) or 'candidates'.
                        # OpenAI format has 'choices'. I should adapt it.
                        
                        response_dict = {
                            'content': [{'type': 'text', 'text': response_json['choices'][0]['message']['content']}],
                            'usage': response_json.get('usage', {}),
                            'stop_reason': response_json['choices'][0].get('finish_reason', 'stop')
                        }
                    else:
                        error = Exception(f"Vertex API status {response.status}: {response_text}")
                        await self.cache_handler.save_debug_data('vertex', model, debug_request, response_text, error=error, context=f"status_{response.status}", cache_key=cache_key)
                        raise error

            unified_response = await self._normalize_vertex_response(response_dict, soft_schema, schema)
            
            if unified_response.get('stop_reason') in ['max_tokens', 'length']:
                 await self.cache_handler.save_debug_data('vertex', model, debug_request, unified_response, context="max_tokens_truncated", cache_key=cache_key)
                 raise Exception(f"[MAX_TOKENS] Model {model} hit limit")

            await self.cache_handler.save_debug_data('vertex', model, debug_request, unified_response, context="single_call_success", cache_key=cache_key)
            
            token_usage = self.usage_handler.extract_token_usage(response_dict, model)
            
            if use_cache and cache_key:
                await self.cache_handler.save_to_cache(cache_key, unified_response, token_usage, processing_time, model, 'vertex')
            
            enhanced_data = self.usage_handler.get_enhanced_call_metrics(unified_response, model, processing_time, is_cached=False)
            
            # Merge repair costs if present
            if '_repair_meta' in unified_response:
                repair_meta = unified_response['_repair_meta']
                repair_cost = repair_meta.get('cost', 0.0)
                
                if 'costs' in enhanced_data and 'actual' in enhanced_data['costs']:
                    enhanced_data['costs']['actual']['total_cost'] += repair_cost
                    enhanced_data['repair_info'] = repair_meta
                    logger.info(f"[COST_UPDATE] Added repair cost ${repair_cost:.4f} to total. New total: ${enhanced_data['costs']['actual']['total_cost']:.4f}")

            return {
                'response': unified_response,
                'token_usage': token_usage,
                'processing_time': processing_time,
                'is_cached': False,
                'citations': [],
                'enhanced_data': enhanced_data
            }

        except Exception as e:
            await self.cache_handler.save_debug_data('vertex', model, debug_request, None, error=e, context="exception", cache_key=cache_key)
            raise
