
import json
import logging
import aiohttp
from datetime import datetime
from typing import Dict, Any
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from ..utils import extract_json_from_text, validate_and_normalize_soft_schema, repair_json_with_haiku

logger = logging.getLogger(__name__)

class GeminiProvider:
    def __init__(self, project_id: str, location: str, cache_handler, usage_handler, ai_client=None):
        self.project_id = project_id
        self.location = location or 'us-central1'  # Default to us-central1 for Gemini
        self.cache_handler = cache_handler
        self.usage_handler = usage_handler
        self.ai_client = ai_client

    async def _get_access_token(self) -> str:
        """Get OAuth2 access token for Vertex AI using service account credentials."""
        import os

        # Get credentials file path from environment
        creds_file = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if not creds_file:
            raise Exception("GOOGLE_APPLICATION_CREDENTIALS environment variable not set")

        # Strip quotes if present (common issue with env vars)
        creds_file = creds_file.strip('"').strip("'")

        # Load service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            creds_file,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )

        # Refresh token
        credentials.refresh(Request())
        return credentials.token

    async def _normalize_gemini_response(self, gemini_response: Dict, soft_schema: bool, schema: Dict, model: str) -> Dict:
        """
        Normalize Gemini response to unified format.

        Gemini response format:
        {
            "candidates": [{
                "content": {
                    "parts": [{"text": "..."}],
                    "role": "model"
                },
                "finishReason": "STOP",
                "safetyRatings": [...]
            }],
            "usageMetadata": {
                "promptTokenCount": 123,
                "candidatesTokenCount": 456,
                "totalTokenCount": 579
            }
        }
        """
        try:
            # Extract text content from response
            text_content = ""
            if 'candidates' in gemini_response and gemini_response['candidates']:
                candidate = gemini_response['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    for part in candidate['content']['parts']:
                        if 'text' in part:
                            text_content += part['text']

            # Build normalized response
            # Map Gemini's usageMetadata to standard usage format
            usage_metadata = gemini_response.get('usageMetadata', {})
            normalized = {
                'id': gemini_response.get('modelVersion', 'gemini'),
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'text', 'text': text_content}],
                'stop_reason': self._map_finish_reason(gemini_response.get('candidates', [{}])[0].get('finishReason', 'STOP')),
                'usage': usage_metadata,  # Preserve usageMetadata for token extraction
                'usageMetadata': usage_metadata  # Also keep camelCase for Gemini-specific extraction
            }

            # Handle soft schema cleanup
            if soft_schema and schema:
                try:
                    parsed = extract_json_from_text(text_content)
                    repair_attempted = False

                    # If extraction failed, try Haiku repair
                    if not parsed and self.ai_client:
                        logger.warning(f"[GEMINI] JSON extraction failed, attempting Haiku repair")
                        repair_attempted = True
                        parsed, repair_result, repair_explanation = await repair_json_with_haiku(text_content, schema, self.ai_client)

                        if repair_result:
                            repair_cost = repair_result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)

                            # Log the repair explanation
                            logger.info(f"[HAIKU_REPAIR] Provider: gemini, Model: {model}")
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
                                original_provider='gemini',
                                original_model=model,
                                malformed_input=text_content,
                                repaired_output=parsed,
                                repair_explanation=repair_explanation or 'No explanation provided',
                                repair_cost=repair_cost
                            )

                    if parsed:
                        norm, warnings = validate_and_normalize_soft_schema(parsed, schema, fuzzy_keys=True)
                        if warnings:
                            logger.warning(f"[GEMINI] Soft schema warnings: {warnings}")

                        # Check if required fields are present
                        required = schema.get('required', [])
                        missing = [f for f in required if f not in norm]
                        if missing:
                            # Try Haiku repair if we haven't already
                            if not repair_attempted and self.ai_client:
                                logger.warning(f"[GEMINI] Missing required fields {missing}, attempting Haiku repair")
                                repair_attempted = True
                                parsed, repair_result, repair_explanation = await repair_json_with_haiku(text_content, schema, self.ai_client)

                                if repair_result and parsed:
                                    repair_cost = repair_result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)

                                    # Log the repair explanation
                                    logger.info(f"[HAIKU_REPAIR] Provider: gemini, Model: {model}")
                                    logger.info(f"[HAIKU_REPAIR] Explanation: {repair_explanation}")
                                    logger.info(f"[HAIKU_REPAIR] Cost: ${repair_cost:.6f}")

                                    # Attach repair metrics to normalized response
                                    normalized['_repair_meta'] = {
                                        'repaired': True,
                                        'cost': repair_cost,
                                        'model': 'claude-haiku-4-5',
                                        'provider': 'anthropic',
                                        'explanation': repair_explanation
                                    }

                                    # Save repair data to S3
                                    await self.cache_handler.save_haiku_repair_data(
                                        original_provider='gemini',
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
                                logger.error(f"[GEMINI] Missing required fields: {missing}")
                                raise Exception(f"[SCHEMA_ERROR] Missing required fields: {missing}")

                        normalized['content'][0]['text'] = json.dumps(norm)
                    else:
                        logger.error(f"[GEMINI] Could not extract or repair JSON from response")
                        raise Exception("[REPAIR_FAILED] Haiku repair failed to extract valid JSON")

                except Exception as e:
                    # Re-raise critical errors to trigger backup model retry
                    if "[SCHEMA_ERROR]" in str(e) or "[REPAIR_FAILED]" in str(e):
                        logger.error(f"[GEMINI] Critical soft schema error: {e}")
                        raise
                    logger.warning(f"Gemini soft schema cleaning failed: {e}")

            return normalized

        except Exception as e:
            logger.error(f"Gemini normalization failed: {e}")
            return {'id': 'error', 'type': 'message', 'role': 'assistant', 'content': [{'type': 'text', 'text': str(gemini_response)}], 'stop_reason': 'error', 'usage': {}}

    def _map_finish_reason(self, finish_reason: str) -> str:
        """Map Gemini finish reasons to unified format."""
        mapping = {
            'STOP': 'end_turn',
            'MAX_TOKENS': 'max_tokens',
            'SAFETY': 'refusal',
            'RECITATION': 'refusal',
            'OTHER': 'unknown'
        }
        return mapping.get(finish_reason, 'unknown')

    async def make_single_call(self, prompt: str, schema: Dict, model: str, use_cache: bool, cache_key: str, start_time: datetime, max_tokens: int = 8000, soft_schema: bool = False) -> Dict:
        """Make a single call to Gemini via Vertex AI."""
        enforced_max_tokens = self.usage_handler.enforce_provider_token_limit(model, max_tokens)

        # Build request
        request_body = {
            "contents": [{
                "role": "user",
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": enforced_max_tokens
            }
        }

        # Add JSON mode if schema provided
        if schema:
            if soft_schema:
                # Soft schema: Add instructions to prompt, no API enforcement
                request_body["contents"][0]["parts"][0]["text"] = f"{prompt}\n\nReturn your answer as valid JSON matching this schema:\n{json.dumps(schema)}"
            else:
                # Hard schema: Use native Gemini JSON mode
                request_body["generationConfig"]["responseMimeType"] = "application/json"
                request_body["generationConfig"]["responseSchema"] = schema

        debug_request = {'model': model, 'prompt': prompt, 'max_tokens': enforced_max_tokens}

        try:
            access_token = await self._get_access_token()
            url = f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/{self.location}/publishers/google/models/{model}:generateContent"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=request_body) as response:
                    processing_time = (datetime.now() - start_time).total_seconds()
                    response_text = await response.text()

                    if response.status == 200:
                        response_json = json.loads(response_text)
                    else:
                        error = Exception(f"Gemini API status {response.status}: {response_text}")
                        await self.cache_handler.save_debug_data('gemini', model, debug_request, response_text, error=error, context=f"status_{response.status}", cache_key=cache_key)
                        raise error

            # Normalize response
            unified_response = await self._normalize_gemini_response(response_json, soft_schema, schema, model)

            # Check for max_tokens truncation
            if unified_response.get('stop_reason') in ['max_tokens', 'length']:
                await self.cache_handler.save_debug_data('gemini', model, debug_request, unified_response, context="max_tokens_truncated", cache_key=cache_key)
                raise Exception(f"[MAX_TOKENS] Model {model} hit limit")

            await self.cache_handler.save_debug_data('gemini', model, debug_request, unified_response, context="single_call_success", cache_key=cache_key)

            # Extract token usage from original response (has usageMetadata)
            token_usage = self.usage_handler.extract_token_usage(response_json, model)

            # Cache if enabled
            if use_cache and cache_key:
                await self.cache_handler.cache_response(cache_key, unified_response, 'gemini', token_usage, processing_time)

            # Return in unified format
            return {
                'response': unified_response,
                'token_usage': token_usage,
                'processing_time': processing_time,
                'is_cached': False,
                'citations': []  # Gemini doesn't provide citations in this endpoint
            }

        except Exception as e:
            await self.cache_handler.save_debug_data('gemini', model, debug_request, None, error=e, context="exception", cache_key=cache_key)
            raise
