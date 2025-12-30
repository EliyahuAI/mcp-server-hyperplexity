
import json
import logging
import aiohttp
from datetime import datetime
from typing import Dict, Any, Optional
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
                            # Log diagnostic info
                            logger.error(f"[GEMINI] Found missing required fields: {missing}")
                            logger.error(f"[GEMINI] repair_attempted={repair_attempted}, ai_client_available={self.ai_client is not None}")

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

    def _convert_schema_for_gemini(self, schema: Dict) -> tuple[Dict, Dict]:
        """
        Convert JSON Schema to Gemini-compatible format and track conversions.

        Gemini schema quirks:
        1. Does not support array syntax for type: "type": ["string", "null"]
        2. Does not support "items": False for tuple validation
        3. Protobuf-based schema has stricter requirements
        4. Does not support: $schema, if/then/else conditionals

        Returns:
            (converted_schema, conversion_map) where conversion_map tracks what was changed
        """
        import copy

        conversion_map = {
            'null_conversions': [],  # Track fields where null was converted to "NULL"
            'type_array_fixes': [],  # Track fields where type arrays were flattened
            'stripped_fields': [],  # Track unsupported fields that were removed
            'has_complex_conditionals': False,  # Flag if schema has if/then/else (can't be fully converted)
        }

        def process_schema_node(node, path=""):
            """Recursively process schema nodes to fix Gemini incompatibilities."""
            if not isinstance(node, dict):
                return node

            node = copy.deepcopy(node)

            # Fix 0: Strip unsupported JSON Schema meta fields and conditionals
            unsupported_fields = ['$schema', '$id', '$ref', 'if', 'then', 'else', 'not', 'allOf', 'oneOf']
            for field in unsupported_fields:
                if field in node:
                    conversion_map['stripped_fields'].append(f"{path}.{field}" if path else field)

                    # Flag complex conditionals that can't be properly converted
                    if field in ['if', 'then', 'else']:
                        conversion_map['has_complex_conditionals'] = True
                        logger.warning(f"[GEMINI_SCHEMA] Found conditional '{field}' at {path} - schema may be too complex for Gemini")

                    del node[field]

            # Fix 1: Handle "type": ["string", "null"] -> "type": "string" + convert nulls in enum
            if 'type' in node and isinstance(node['type'], list):
                # Record the fix
                conversion_map['type_array_fixes'].append({
                    'path': path,
                    'original_types': node['type'],
                    'has_null': None in node['type'] or 'null' in node['type']
                })

                # If array contains null and another type, use the non-null type
                types = [t for t in node['type'] if t is not None and t != 'null']
                if types:
                    node['type'] = types[0]  # Use first non-null type
                else:
                    # Fallback: just use string
                    node['type'] = 'string'

            # Fix 2: Convert null in enums to "NULL" (Gemini doesn't handle null well in enums)
            if 'enum' in node and (None in node['enum'] or 'null' in node['enum']):
                conversion_map['null_conversions'].append(path)
                new_enum = []
                for val in node['enum']:
                    if val is None or val == 'null':
                        new_enum.append("NULL")
                    else:
                        new_enum.append(val)
                node['enum'] = new_enum

            # Fix 3: Remove "items": False (not supported in Gemini)
            if 'items' in node and node['items'] is False:
                logger.debug(f"[GEMINI_SCHEMA] Removing 'items': False at {path} (tuple validation not supported)")
                del node['items']

            # Recursively process nested structures
            if 'properties' in node:
                for prop_name, prop_schema in node['properties'].items():
                    node['properties'][prop_name] = process_schema_node(
                        prop_schema,
                        f"{path}.{prop_name}" if path else prop_name
                    )

            if 'items' in node and isinstance(node['items'], dict):
                node['items'] = process_schema_node(node['items'], f"{path}[]")

            if 'additionalProperties' in node and isinstance(node['additionalProperties'], dict):
                node['additionalProperties'] = process_schema_node(
                    node['additionalProperties'],
                    f"{path}.*"
                )

            # Handle prefixItems (used in tuple schemas)
            if 'prefixItems' in node and isinstance(node['prefixItems'], list):
                # First recursively process each prefixItem schema
                node['prefixItems'] = [
                    process_schema_node(item, f"{path}[{i}]")
                    for i, item in enumerate(node['prefixItems'])
                ]

                # Then convert to items (Gemini doesn't support tuple validation)
                logger.debug(f"[GEMINI_SCHEMA] Converting prefixItems to items at {path} (tuple validation not supported)")
                if len(node['prefixItems']) == 1:
                    # Single item: just use it directly
                    node['items'] = node['prefixItems'][0]
                else:
                    # Multiple items: use anyOf to accept any of the position schemas
                    node['items'] = {
                        'anyOf': node['prefixItems']
                    }
                conversion_map['prefixItems_conversions'] = conversion_map.get('prefixItems_conversions', [])
                conversion_map['prefixItems_conversions'].append(path)
                del node['prefixItems']

            return node

        converted = process_schema_node(schema)

        # Log conversions if any were made
        if conversion_map['null_conversions'] or conversion_map['type_array_fixes'] or conversion_map.get('prefixItems_conversions') or conversion_map['stripped_fields']:
            logger.info(f"[GEMINI_SCHEMA] Applied compatibility fixes:")
            if conversion_map['stripped_fields']:
                logger.info(f"  - Stripped {len(conversion_map['stripped_fields'])} unsupported field(s): {conversion_map['stripped_fields'][:5]}")
                if conversion_map['has_complex_conditionals']:
                    logger.warning(f"  - WARNING: Schema contains if/then/else conditionals - may need Haiku fallback")
            if conversion_map['type_array_fixes']:
                logger.info(f"  - Fixed {len(conversion_map['type_array_fixes'])} type array(s)")
            if conversion_map['null_conversions']:
                logger.info(f"  - Converted null to 'NULL' in {len(conversion_map['null_conversions'])} field(s): {conversion_map['null_conversions']}")
            if conversion_map.get('prefixItems_conversions'):
                logger.info(f"  - Converted prefixItems to items in {len(conversion_map['prefixItems_conversions'])} field(s): {conversion_map['prefixItems_conversions']}")

        return converted, conversion_map

    def _restore_gemini_response_values(self, response_data: Any, conversion_map: Dict) -> Any:
        """
        Restore converted values in Gemini response back to original intent.

        Converts "NULL" strings back to None/null based on conversion_map.
        """
        if not conversion_map.get('null_conversions'):
            return response_data  # No conversions to restore

        def restore_node(data, path=""):
            """Recursively restore NULL strings to null."""
            if isinstance(data, dict):
                restored = {}
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key

                    # Check if this field had null conversions
                    if current_path in conversion_map['null_conversions']:
                        # Convert "NULL" string back to None
                        if value == "NULL":
                            restored[key] = None
                        elif isinstance(value, list):
                            # Handle arrays with NULL strings
                            restored[key] = [None if v == "NULL" else restore_node(v, f"{current_path}[]") for v in value]
                        else:
                            restored[key] = restore_node(value, current_path)
                    else:
                        restored[key] = restore_node(value, current_path)
                return restored

            elif isinstance(data, list):
                # For arrays, check if parent path had conversions
                return [restore_node(item, f"{path}[]") for item in data]

            else:
                return data

        restored = restore_node(response_data)

        if restored != response_data:
            logger.info(f"[GEMINI_SCHEMA] Restored {len(conversion_map['null_conversions'])} NULL string(s) to null")

        return restored

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

        # Track schema conversions for later restoration
        conversion_map = None

        # Add JSON mode if schema provided
        if schema:
            if soft_schema:
                # Soft schema: Add instructions to prompt, no API enforcement
                request_body["contents"][0]["parts"][0]["text"] = f"""{prompt}

Return raw JSON (first char {{, last char }}, parseable by json.loads() as-is):
{json.dumps(schema)}"""
            else:
                # Hard schema: Use native Gemini JSON mode with compatibility fixes
                request_body["generationConfig"]["responseMimeType"] = "application/json"

                # Convert schema to Gemini-compatible format
                converted_schema, conversion_map = self._convert_schema_for_gemini(schema)

                # Check if schema is too complex for Gemini (has conditionals)
                if conversion_map.get('has_complex_conditionals'):
                    error_msg = "Schema contains if/then/else conditionals not supported by Gemini - use Haiku/Claude instead"
                    logger.warning(f"[GEMINI_SCHEMA] {error_msg}")
                    raise Exception(error_msg)

                request_body["generationConfig"]["responseSchema"] = converted_schema

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

            # Restore converted values if we made schema conversions (hard schema only)
            if conversion_map and not soft_schema:
                try:
                    # Extract JSON from response text
                    text_content = ""
                    if 'content' in unified_response and unified_response['content']:
                        for content_block in unified_response['content']:
                            if content_block.get('type') == 'text':
                                text_content += content_block.get('text', '')

                    logger.info(f"[GEMINI_SCHEMA] Attempting to restore NULL values in response")
                    logger.info(f"[GEMINI_SCHEMA] Text content length: {len(text_content)} chars")

                    if text_content:
                        response_data = json.loads(text_content)
                        logger.info(f"[GEMINI_SCHEMA] Parsed response data successfully")
                        restored_data = self._restore_gemini_response_values(response_data, conversion_map)
                        logger.info(f"[GEMINI_SCHEMA] Restored values successfully")
                        # Update response with restored values
                        unified_response['content'][0]['text'] = json.dumps(restored_data)
                        logger.info(f"[GEMINI_SCHEMA] Updated response with restored JSON")
                except Exception as e:
                    logger.error(f"[GEMINI_SCHEMA] Failed to restore converted values: {e}")
                    logger.error(f"[GEMINI_SCHEMA] Text content preview: {text_content[:500]}")
                    import traceback
                    logger.error(f"[GEMINI_SCHEMA] Stack trace: {traceback.format_exc()}")

            # Check for max_tokens truncation
            if unified_response.get('stop_reason') in ['max_tokens', 'length']:
                await self.cache_handler.save_debug_data('gemini', model, debug_request, unified_response, context="max_tokens_truncated", cache_key=cache_key)
                raise Exception(f"[MAX_TOKENS] Model {model} hit limit")

            await self.cache_handler.save_debug_data('gemini', model, debug_request, unified_response, context="single_call_success", cache_key=cache_key)

            # Extract token usage from original response (has usageMetadata)
            token_usage = self.usage_handler.extract_token_usage(response_json, model)

            # Generate enhanced metrics BEFORE caching (needed for time_estimated preservation)
            enhanced_data = self.usage_handler.get_enhanced_call_metrics(
                unified_response, model, processing_time,
                pre_extracted_token_usage=token_usage,
                is_cached=False
            )

            # Cache if enabled (with enhanced_data for timing preservation)
            if use_cache and cache_key:
                await self.cache_handler.save_to_cache(cache_key, unified_response, token_usage, processing_time, model, 'gemini', enhanced_data)

            # Return in unified format
            return {
                'response': unified_response,
                'token_usage': token_usage,
                'processing_time': processing_time,
                'is_cached': False,
                'citations': [],  # Gemini doesn't provide citations in this endpoint
                'enhanced_data': enhanced_data
            }

        except Exception as e:
            await self.cache_handler.save_debug_data('gemini', model, debug_request, None, error=e, context="exception", cache_key=cache_key)
            raise
