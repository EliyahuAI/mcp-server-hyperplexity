
import json
import logging
import aiohttp
from datetime import datetime
from typing import Dict, Optional

from ..utils import extract_json_from_text, validate_and_normalize_soft_schema, repair_json_with_haiku
from ..config import get_model_timeout, get_timeout_tier

logger = logging.getLogger(__name__)

# Models that respond well to json_object format but need schema described in prompt.
# MiniMax M2.5 ignores json_schema mode (returns empty); Kimi K2.5 supports it but
# soft schema also works reliably. We use soft_schema=True for all OpenRouter models
# and add response_format=json_object to prevent markdown output.
_DEFAULT_TIMEOUT = 120  # OpenRouter adds its own routing latency


class OpenRouterProvider:
    def __init__(self, api_key: str, cache_handler, usage_handler, ai_client=None):
        self.api_key = api_key
        self.cache_handler = cache_handler
        self.usage_handler = usage_handler
        self.ai_client = ai_client
        self.base_url = "https://openrouter.ai/api/v1"

    async def _normalize_response(self, response: Dict, soft_schema: bool = False,
                                   schema: Dict = None, model: str = None) -> Dict:
        """Normalize OpenRouter response to Anthropic-style format."""
        try:
            if 'choices' in response and len(response['choices']) > 0:
                choice = response['choices'][0]
                message = choice.get('message', {})
                text_content = message.get('content', '') or ''

                normalized = {
                    'id': response.get('id', 'openrouter_msg'),
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'text', 'text': text_content}],
                    'stop_reason': choice.get('finish_reason', 'stop'),
                    'usage': response.get('usage', {}),
                }
            else:
                text_content = str(response)
                normalized = {
                    'id': 'openrouter_msg',
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'text', 'text': text_content}],
                    'stop_reason': 'unknown',
                    'usage': {},
                }

            if soft_schema and schema:
                try:
                    parsed = extract_json_from_text(text_content)
                    repair_attempted = False

                    if not parsed and self.ai_client:
                        logger.warning(f"[OPENROUTER] JSON extraction failed for {model}, attempting repair")
                        repair_attempted = True
                        parsed, repair_result, repair_explanation = await repair_json_with_haiku(
                            text_content, schema, self.ai_client
                        )

                        if repair_result:
                            repair_cost = repair_result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                            logger.info(f"[HAIKU_REPAIR] Provider: openrouter, Model: {model}")
                            logger.info(f"[HAIKU_REPAIR] Explanation: {repair_explanation}")
                            logger.info(f"[HAIKU_REPAIR] Cost: ${repair_cost:.6f}")
                            normalized['_repair_meta'] = {
                                'repaired': True,
                                'cost': repair_cost,
                                'model': 'gemini-2.5-flash-lite',
                                'provider': 'gemini',
                                'explanation': repair_explanation,
                            }
                            await self.cache_handler.save_haiku_repair_data(
                                original_provider='openrouter',
                                original_model=model,
                                malformed_input=text_content,
                                repaired_output=parsed,
                                repair_explanation=repair_explanation or 'No explanation provided',
                                repair_cost=repair_cost,
                            )

                    if parsed:
                        norm, warnings = validate_and_normalize_soft_schema(parsed, schema, fuzzy_keys=True)
                        if warnings:
                            logger.warning(f"[OPENROUTER] Soft schema warnings: {warnings}")

                        required = schema.get('required', [])
                        missing = [f for f in required if f not in norm]
                        enum_errors = [w for w in warnings if 'Invalid enum value' in w]

                        if missing or enum_errors:
                            if missing:
                                logger.error(f"[OPENROUTER] Missing required fields: {missing}")
                            if enum_errors:
                                logger.error(f"[OPENROUTER] Enum errors: {enum_errors}")

                            if not repair_attempted and self.ai_client:
                                issues = []
                                if missing:
                                    issues.append(f"missing fields {missing}")
                                if enum_errors:
                                    issues.append(f"enum errors {enum_errors}")
                                logger.warning(f"[OPENROUTER] Schema issues: {', '.join(issues)}, attempting repair")
                                repair_attempted = True
                                parsed, repair_result, repair_explanation = await repair_json_with_haiku(
                                    text_content, schema, self.ai_client
                                )

                                if repair_result and parsed:
                                    repair_cost = repair_result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                                    logger.info(f"[HAIKU_REPAIR] Provider: openrouter, Model: {model}")
                                    logger.info(f"[HAIKU_REPAIR] Cost: ${repair_cost:.6f}")
                                    normalized['_repair_meta'] = {
                                        'repaired': True,
                                        'cost': repair_cost,
                                        'model': 'gemini-2.5-flash-lite',
                                        'provider': 'gemini',
                                        'explanation': repair_explanation,
                                    }
                                    await self.cache_handler.save_haiku_repair_data(
                                        original_provider='openrouter',
                                        original_model=model,
                                        malformed_input=text_content,
                                        repaired_output=parsed,
                                        repair_explanation=repair_explanation or 'No explanation provided',
                                        repair_cost=repair_cost,
                                    )
                                    norm, warnings = validate_and_normalize_soft_schema(parsed, schema, fuzzy_keys=True)
                                    missing = [f for f in required if f not in norm]
                                    enum_errors = [w for w in warnings if 'Invalid enum value' in w]

                            if missing or enum_errors:
                                error_parts = []
                                if missing:
                                    error_parts.append(f"Missing required fields: {missing}")
                                if enum_errors:
                                    error_parts.append(f"Invalid enum values: {enum_errors}")
                                raise Exception(f"[SCHEMA_ERROR] {'; '.join(error_parts)}")

                        normalized['content'][0]['text'] = json.dumps(norm)
                    else:
                        logger.error(f"[OPENROUTER] Could not extract or repair JSON")
                        raise Exception("[REPAIR_FAILED] Could not extract valid JSON from OpenRouter response")

                except Exception as e:
                    if "[SCHEMA_ERROR]" in str(e) or "[REPAIR_FAILED]" in str(e):
                        raise
                    logger.warning(f"[OPENROUTER] Soft schema cleaning failed: {e}")

            return normalized

        except Exception as e:
            if "[SCHEMA_ERROR]" in str(e) or "[REPAIR_FAILED]" in str(e):
                raise
            logger.error(f"[OPENROUTER] Normalization failed: {e}")
            return {
                'id': 'error', 'type': 'message', 'role': 'assistant',
                'content': [{'type': 'text', 'text': str(response)}],
                'stop_reason': 'error', 'usage': {},
            }

    async def make_single_call(self, prompt: str, schema: Dict, model: str,
                               use_cache: bool, cache_key: str, start_time: datetime,
                               max_tokens: int = 64000, soft_schema: bool = True,
                               timeout_override: Optional[int] = None) -> Dict:
        """
        Make a single structured call via OpenRouter.

        OpenRouter test findings (2026-02-25):
          - MiniMax M2.5: only works with soft_schema + response_format=json_object.
            json_schema mode returns empty content.
          - Kimi K2.5: json_schema strict works, but soft_schema + json_object also
            works reliably. We standardise on soft_schema for both.

        Always sets response_format=json_object so models don't fall back to markdown.
        ZDR (zero data retention) enforced via provider.zdr=true in request body.
        """
        enforced_max_tokens = self.usage_handler.enforce_provider_token_limit(model, max_tokens)

        # Build prompt: always embed schema for reliable extraction
        final_prompt = prompt
        if schema and soft_schema:
            final_prompt = f"""{prompt}

CRITICAL: You MUST respond with ONLY valid JSON matching this schema. Do NOT include any explanatory text, analysis, or preamble. Start your response with {{ and end with }}.

Schema:
{json.dumps(schema, indent=2)}

Response format: Return ONLY the JSON object, nothing else."""

        debug_request = {'model_id': model, 'prompt': final_prompt, 'max_tokens': enforced_max_tokens}

        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'HTTP-Referer': 'https://hyperplexity.ai',
                'X-OpenRouter-Title': 'HyperplexityValidator',
            }

            data = {
                'model': model,
                'messages': [{'role': 'user', 'content': final_prompt}],
                'temperature': 0.1,
                'max_tokens': enforced_max_tokens,
                'stream': False,
                # Always use json_object to prevent markdown output (MiniMax needs this).
                # Even for hard-schema scenarios, this is the reliable mode.
                'response_format': {'type': 'json_object'},
                # Zero Data Retention — only route to ZDR endpoints
                'provider': {'zdr': True},
            }

            timeout_seconds = get_model_timeout(model, timeout_override) or _DEFAULT_TIMEOUT
            logger.debug(f"[OPENROUTER] Calling {model}, timeout={timeout_seconds}s, soft_schema={soft_schema}")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=data,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds)
                ) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    response_text = await response.text()

                    if response.status == 200:
                        response_json = json.loads(response_text)
                    else:
                        error = Exception(f"OpenRouter API status {response.status}: {response_text[:500]}")
                        await self.cache_handler.save_debug_data(
                            'openrouter', model, debug_request, response_text,
                            error=error, context=f"status_{response.status}", cache_key=cache_key
                        )
                        raise error

            unified_response = await self._normalize_response(response_json, soft_schema, schema, model)

            if unified_response.get('stop_reason') in ('max_tokens', 'length'):
                await self.cache_handler.save_debug_data(
                    'openrouter', model, debug_request, unified_response,
                    context="max_tokens_truncated", cache_key=cache_key
                )
                raise Exception(f"[MAX_TOKENS] OpenRouter model {model} hit token limit")

            await self.cache_handler.save_debug_data(
                'openrouter', model, debug_request, unified_response,
                context="single_call_success", cache_key=cache_key
            )

            token_usage = self.usage_handler.extract_token_usage(response_json, model)
            enhanced_data = self.usage_handler.get_enhanced_call_metrics(
                unified_response, model, processing_time, is_cached=False
            )

            if '_repair_meta' in unified_response:
                repair_cost = unified_response['_repair_meta'].get('cost', 0.0)
                if 'costs' in enhanced_data and 'actual' in enhanced_data['costs']:
                    enhanced_data['costs']['actual']['total_cost'] += repair_cost
                    enhanced_data['repair_info'] = unified_response['_repair_meta']

            return {
                'response': unified_response,
                'token_usage': token_usage,
                'processing_time': processing_time,
                'is_cached': False,
                'citations': [],
                'enhanced_data': enhanced_data,
            }

        except Exception as e:
            await self.cache_handler.save_debug_data(
                'openrouter', model, debug_request, None,
                error=e, context="exception", cache_key=cache_key
            )
            raise
