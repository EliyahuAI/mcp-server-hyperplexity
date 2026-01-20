
import json
import logging
import asyncio
import aiohttp
import os
from datetime import datetime
from threading import Lock
from typing import Dict, Any, Optional, Tuple
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from ..utils import extract_json_from_text, validate_and_normalize_soft_schema, repair_json_with_haiku
from ..config import get_model_timeout, get_timeout_tier

logger = logging.getLogger(__name__)

# Per-model, per-loop semaphores (each Gemini model variant has its own rate limit quota)
# IMPORTANT: asyncio.Semaphore is bound to the event loop when first used.
# In Lambda, asyncio.new_event_loop() creates a new loop each invocation,
# so we must create the semaphore lazily for the current loop.
_gemini_semaphore_lock = Lock()
_gemini_semaphores: Dict[Tuple[int, str], asyncio.Semaphore] = {}  # (loop_id, model) -> Semaphore
_gemini_default_max_concurrent: int = 5  # Default max concurrent calls per model

# Rationale for default of 5 per model:
# - Vertex AI Gemini standard tier: ~60 RPM per model (1 req/sec sustained)
# - Each model variant (2.0-flash, 2.5-flash-lite, 2.5-flash) has separate quota
# - With batch extraction enabled, typical usage is 1-2 calls per iteration
# - Findall mode runs up to 5 parallel batch calls (one per search term)
# - Setting to 5 allows findall to run without queuing while preventing bursts
# - Can be configured per-model via env vars: GEMINI_MAX_CONCURRENT_2_0_FLASH=10


def get_gemini_semaphore(model: str) -> asyncio.Semaphore:
    """
    Get or create a semaphore for a specific Gemini model and current event loop.

    Each model has its own semaphore because Vertex AI rate limits are per-model.
    Semaphores are also keyed by event loop to handle Lambda's new loop per invocation.
    This allows us to maximize throughput when using multiple model variants.
    """
    global _gemini_semaphores, _gemini_default_max_concurrent

    # Get current event loop ID
    # This is always called from async context (make_single_call), so loop should exist
    loop = asyncio.get_running_loop()
    loop_id = id(loop)

    # Normalize model name for env var lookup (e.g., "gemini-2.0-flash" -> "2_0_FLASH")
    model_suffix = model.replace('gemini-', '').replace('.', '_').replace('-', '_').upper()
    env_var = f'GEMINI_MAX_CONCURRENT_{model_suffix}'

    key = (loop_id, model)

    with _gemini_semaphore_lock:
        if key not in _gemini_semaphores:
            # Check for model-specific env var, fall back to default
            max_concurrent = int(os.environ.get(env_var,
                                os.environ.get('GEMINI_MAX_CONCURRENT', _gemini_default_max_concurrent)))
            logger.debug(f"[GEMINI_SEMAPHORE] Creating new semaphore for loop {loop_id}, model {model}")
            _gemini_semaphores[key] = asyncio.Semaphore(max_concurrent)
            logger.info(f"[GEMINI_RATE_LIMIT] Initialized semaphore for {model} with max_concurrent={max_concurrent}")

            # Clean up old loop semaphores (keep only last 2 loops to prevent memory leak)
            loop_ids = set(k[0] for k in _gemini_semaphores.keys())
            if len(loop_ids) > 2:
                oldest_loop = min(loop_ids)
                keys_to_remove = [k for k in _gemini_semaphores.keys() if k[0] == oldest_loop]
                for old_key in keys_to_remove:
                    del _gemini_semaphores[old_key]
                logger.debug(f"[GEMINI_SEMAPHORE] Cleaned up {len(keys_to_remove)} semaphores from old loop {oldest_loop}")

        return _gemini_semaphores[key]


class GeminiProvider:
    # Rate limit retry configuration
    # Only retry twice before letting ai_client try backup models in the chain
    RATE_LIMIT_MAX_RETRIES = 2
    RATE_LIMIT_BASE_DELAY = 1.0  # seconds
    RATE_LIMIT_MAX_DELAY = 8.0  # seconds (reduced since we retry less)

    def __init__(self, project_id: str, location: str, cache_handler, usage_handler, ai_client=None):
        self.project_id = project_id
        self.location = location or 'us-central1'  # Default to us-central1 for Gemini
        self.cache_handler = cache_handler
        self.usage_handler = usage_handler
        self.ai_client = ai_client

    async def _get_access_token(self) -> str:
        """Get OAuth2 access token for Vertex AI using service account credentials."""
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
            # NOTE: Section symbols (§) are now the standard for location codes
            # Do NOT convert back to backticks - keep § as-is in the response

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

                        # Check for enum validation errors (e.g., "Invalid enum value for 'importance': 'HARD' not in [...]")
                        enum_errors = [w for w in warnings if 'Invalid enum value' in w]

                        if missing or enum_errors:
                            # Log diagnostic info
                            if missing:
                                logger.error(f"[GEMINI] Found missing required fields: {missing}")
                            if enum_errors:
                                logger.error(f"[GEMINI] Found enum validation errors: {enum_errors}")
                            logger.error(f"[GEMINI] repair_attempted={repair_attempted}, ai_client_available={self.ai_client is not None}")

                            # Try Haiku repair if we haven't already
                            if not repair_attempted and self.ai_client:
                                issues = []
                                if missing:
                                    issues.append(f"missing fields {missing}")
                                if enum_errors:
                                    issues.append(f"enum errors {enum_errors}")
                                logger.warning(f"[GEMINI] Schema issues: {', '.join(issues)}, attempting Haiku repair")
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
                                    enum_errors = [w for w in warnings if 'Invalid enum value' in w]

                            # If still have schema issues after repair attempt, raise error
                            if missing or enum_errors:
                                error_parts = []
                                if missing:
                                    error_parts.append(f"Missing required fields: {missing}")
                                if enum_errors:
                                    error_parts.append(f"Invalid enum values: {enum_errors}")
                                error_msg = "; ".join(error_parts)
                                logger.error(f"[GEMINI] {error_msg}")
                                raise Exception(f"[SCHEMA_ERROR] {error_msg}")

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

            # Fix -1: Escape backticks in all string fields (Gemini treats them as markdown)
            # This includes description, title, examples, default, const, and enum values
            for key in ['description', 'title', 'default', 'const']:
                if key in node and isinstance(node[key], str) and '`' in node[key]:
                    node[key] = node[key].replace('`', '§')
                    logger.debug(f"[GEMINI_SCHEMA] Escaped backticks in {key} at {path}")

            # Also escape backticks in enum arrays
            if 'enum' in node and isinstance(node['enum'], list):
                escaped_enum = []
                for val in node['enum']:
                    if isinstance(val, str) and '`' in val:
                        escaped_enum.append(val.replace('`', '§'))
                        logger.debug(f"[GEMINI_SCHEMA] Escaped backticks in enum value at {path}")
                    else:
                        escaped_enum.append(val)
                if escaped_enum != node['enum']:
                    node['enum'] = escaped_enum

            # Fix 0: Strip unsupported JSON Schema meta fields, validation constraints, and conditionals
            # Gemini's protobuf-based schema only supports basic structure, not validation keywords
            unsupported_fields = [
                '$schema', '$id', '$ref', 'if', 'then', 'else', 'not', 'allOf', 'oneOf',
                'uniqueItems', 'minItems', 'maxItems', 'minLength', 'maxLength',
                'pattern', 'format', 'minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum',
                'const', 'dependencies', 'patternProperties', 'minProperties', 'maxProperties'
            ]
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

            # Fix 2b: Convert integer enums to string enums (Gemini requires string enums AND type: string)
            if 'enum' in node and any(isinstance(val, int) for val in node['enum']):
                conversion_map['integer_enum_conversions'] = conversion_map.get('integer_enum_conversions', [])
                conversion_map['integer_enum_conversions'].append(path)
                node['enum'] = [str(val) if isinstance(val, int) else val for val in node['enum']]
                # Gemini also requires type to be "string" when using enums
                if node.get('type') == 'integer':
                    node['type'] = 'string'
                logger.debug(f"[GEMINI_SCHEMA] Converted integer enum to strings at {path}")

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
        if conversion_map['null_conversions'] or conversion_map['type_array_fixes'] or conversion_map.get('prefixItems_conversions') or conversion_map['stripped_fields'] or conversion_map.get('integer_enum_conversions'):
            logger.info(f"[GEMINI_SCHEMA] Applied compatibility fixes:")
            if conversion_map['stripped_fields']:
                logger.info(f"  - Stripped {len(conversion_map['stripped_fields'])} unsupported field(s): {conversion_map['stripped_fields'][:5]}")
                if conversion_map['has_complex_conditionals']:
                    logger.warning(f"  - WARNING: Schema contains if/then/else conditionals - may need Haiku fallback")
            if conversion_map['type_array_fixes']:
                logger.info(f"  - Fixed {len(conversion_map['type_array_fixes'])} type array(s)")
            if conversion_map['null_conversions']:
                logger.info(f"  - Converted null to 'NULL' in {len(conversion_map['null_conversions'])} field(s): {conversion_map['null_conversions']}")
            if conversion_map.get('integer_enum_conversions'):
                logger.info(f"  - Converted integer enums to strings in {len(conversion_map['integer_enum_conversions'])} field(s): {conversion_map['integer_enum_conversions']}")
            if conversion_map.get('prefixItems_conversions'):
                logger.info(f"  - Converted prefixItems to items in {len(conversion_map['prefixItems_conversions'])} field(s): {conversion_map['prefixItems_conversions']}")

        return converted, conversion_map

    def _restore_gemini_response_values(self, response_data: Any, conversion_map: Dict) -> Any:
        """
        Restore converted values in Gemini response back to original intent.

        Converts "NULL" strings back to None/null based on conversion_map.
        Converts string integer enum values back to integers.
        """
        if not conversion_map.get('null_conversions') and not conversion_map.get('integer_enum_conversions'):
            return response_data  # No conversions to restore

        integer_enum_paths = conversion_map.get('integer_enum_conversions', [])
        null_paths = conversion_map.get('null_conversions', [])

        def restore_node(data, path=""):
            """Recursively restore NULL strings to null and string integers to integers."""
            if isinstance(data, dict):
                restored = {}
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key

                    # Check if this field had integer enum conversions
                    if current_path in integer_enum_paths:
                        # Convert string integer back to int
                        if isinstance(value, str) and value.isdigit():
                            restored[key] = int(value)
                        else:
                            restored[key] = restore_node(value, current_path)
                    # Check if this field had null conversions
                    elif current_path in null_paths:
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

        restorations = []
        if null_paths and restored != response_data:
            restorations.append(f"{len(null_paths)} NULL string(s) to null")
        if integer_enum_paths:
            restorations.append(f"{len(integer_enum_paths)} string integer(s) to int")
        if restorations:
            logger.info(f"[GEMINI_SCHEMA] Restored: {', '.join(restorations)}")

        return restored

    async def make_single_call(self, prompt: str, schema: Dict, model: str, use_cache: bool, cache_key: str, start_time: datetime, max_tokens: int = 8000, soft_schema: bool = False, timeout_override: int = None) -> Dict:
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

        # Explicitly disable thinking for Gemini 2.5 models to prevent thinking tokens
        # from counting against maxOutputTokens (thinkingBudget: 0 = disabled)
        if '2.5' in model or '2-5' in model:
            request_body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}

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
                request_body["contents"][0]["parts"][0]["text"] = prompt

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

        # Get model-specific timeout (with optional override)
        timeout_seconds = get_model_timeout(model, timeout_override)
        logger.debug(f"[GEMINI] Using timeout {get_timeout_tier(model)} for {model}{' (override)' if timeout_override else ''}")

        # Get per-model semaphore for concurrency control
        semaphore = get_gemini_semaphore(model)

        try:
            access_token = await self._get_access_token()
            url = f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/{self.location}/publishers/google/models/{model}:generateContent"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            # Retry loop with exponential backoff for rate limits
            last_error = None
            for attempt in range(self.RATE_LIMIT_MAX_RETRIES + 1):
                async with semaphore:  # Limit concurrent Gemini calls
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, headers=headers, json=request_body, timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as response:
                            processing_time = (datetime.now() - start_time).total_seconds()
                            response_text = await response.text()

                            if response.status == 200:
                                response_json = json.loads(response_text)
                                break  # Success - exit retry loop
                            elif response.status == 429 or 'RESOURCE_EXHAUSTED' in response_text or 'quota' in response_text.lower():
                                # Rate limited - apply exponential backoff
                                delay = min(self.RATE_LIMIT_BASE_DELAY * (2 ** attempt), self.RATE_LIMIT_MAX_DELAY)
                                logger.warning(f"[GEMINI_RATE_LIMIT] 429 on attempt {attempt + 1}/{self.RATE_LIMIT_MAX_RETRIES + 1}, backing off {delay:.1f}s")
                                last_error = Exception(f"Gemini API rate limited (429): {response_text[:200]}")

                                if attempt < self.RATE_LIMIT_MAX_RETRIES:
                                    await asyncio.sleep(delay)
                                    continue  # Retry
                                else:
                                    # Max retries exhausted - raise to trigger backup model
                                    await self.cache_handler.save_debug_data('gemini', model, debug_request, response_text, error=last_error, context="rate_limit_exhausted", cache_key=cache_key)
                                    raise last_error
                            else:
                                # Other error - don't retry
                                error = Exception(f"Gemini API status {response.status}: {response_text}")
                                await self.cache_handler.save_debug_data('gemini', model, debug_request, response_text, error=error, context=f"status_{response.status}", cache_key=cache_key)
                                raise error

            # Normalize response
            unified_response = await self._normalize_gemini_response(response_json, soft_schema, schema, model)

            # Restore converted values if we made schema conversions (hard schema only)
            if conversion_map and not soft_schema and (conversion_map.get('null_conversions') or conversion_map.get('integer_enum_conversions')):
                try:
                    # Extract JSON from response text
                    text_content = ""
                    if 'content' in unified_response and unified_response['content']:
                        for content_block in unified_response['content']:
                            if content_block.get('type') == 'text':
                                text_content += content_block.get('text', '')

                    logger.debug(f"[GEMINI_SCHEMA] Attempting to restore NULL values in response")

                    if text_content:
                        response_data = json.loads(text_content)
                        restored_data = self._restore_gemini_response_values(response_data, conversion_map)
                        # Update response with restored values
                        unified_response['content'][0]['text'] = json.dumps(restored_data)
                        # Log what was restored
                        restorations = []
                        if conversion_map.get('null_conversions'):
                            restorations.append(f"{len(conversion_map['null_conversions'])} NULL value(s)")
                        if conversion_map.get('integer_enum_conversions'):
                            restorations.append(f"{len(conversion_map['integer_enum_conversions'])} integer enum(s)")
                        if restorations:
                            logger.info(f"[GEMINI_SCHEMA] Restored: {', '.join(restorations)}")
                except json.JSONDecodeError as e:
                    # If JSON is malformed, skip NULL restoration and let downstream repair handle it
                    logger.debug(f"[GEMINI_SCHEMA] Skipping NULL restoration - JSON is malformed (will be repaired downstream)")
                except Exception as e:
                    logger.warning(f"[GEMINI_SCHEMA] Failed to restore NULL values: {e} - continuing without restoration")

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
