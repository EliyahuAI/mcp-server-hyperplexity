
import logging
import os
import aioboto3
from typing import Dict, List, Union, Optional
from datetime import datetime

from .config import (
    MODEL_HIERARCHY,
    get_anthropic_api_key,
    get_perplexity_api_key,
    get_baseten_api_key,
    get_google_ai_studio_api_key,
    setup_vertex_credentials
)
from .utils import (
    determine_api_provider,
    normalize_anthropic_model,
    normalize_vertex_model,
    extract_structured_response,
    extract_citations_from_response,
    extract_citations_from_perplexity_response,
    validate_urls_in_response,
    validate_against_schema
)
from .usage import UsageHandler
from .caching import CacheHandler
from .providers.anthropic import AnthropicProvider
from .providers.perplexity import PerplexityProvider
from .providers.vertex import VertexProvider
from .providers.baseten import BasetenProvider
from .providers.clone import CloneProvider
from .providers.gemini import GeminiProvider

logger = logging.getLogger(__name__)


def _schema_has_conditionals(schema: Dict) -> bool:
    """
    Recursively check if schema contains if/then/else conditionals.
    These are not supported by Gemini and other non-Claude models.
    """
    if not isinstance(schema, dict):
        return False

    # Check for conditional keywords at this level
    if any(key in schema for key in ['if', 'then', 'else']):
        return True

    # Recursively check nested structures
    for value in schema.values():
        if isinstance(value, dict):
            if _schema_has_conditionals(value):
                return True
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _schema_has_conditionals(item):
                    return True

    return False

class AIAPIClient:
    """Shared AI API client with caching and schema support."""

    MODEL_HIERARCHY = MODEL_HIERARCHY

    # Class-level session context (shared across ALL instances)
    # This ensures memory system works even if multiple AIAPIClient instances exist
    _session_id = None
    _email = None
    _s3_manager = None

    def __init__(self, s3_bucket: str = None):
        # Cache bucket logic
        cache_bucket = os.environ.get('S3_CACHE_BUCKET')
        if cache_bucket:
            self.s3_bucket = cache_bucket
            self.use_unified_structure = True
        elif os.environ.get('S3_UNIFIED_BUCKET'):
            self.unified_bucket = os.environ.get('S3_UNIFIED_BUCKET')
            self.s3_bucket = self.unified_bucket
            self.use_unified_structure = True
        else:
            self.s3_bucket = s3_bucket or 'perplexity-cache'
            self.use_unified_structure = False

        self.s3_session = aioboto3.Session()
        
        # Initialize handlers
        self.cache_handler = CacheHandler(self.s3_bucket, self.s3_session, self.use_unified_structure)
        self.usage_handler = UsageHandler()

        # Initialize providers
        self.anthropic = AnthropicProvider(get_anthropic_api_key(), self.cache_handler, self.usage_handler, ai_client=self)
        self.perplexity = PerplexityProvider(get_perplexity_api_key(), self.cache_handler, self.usage_handler, ai_client=self)

        project_id, location = setup_vertex_credentials()
        self.vertex = VertexProvider(project_id, self.cache_handler, self.usage_handler, ai_client=self)
        self.vertex_project = project_id # exposed for compatibility

        # Initialize Gemini provider
        # Prefer Google AI Studio (much higher rate limits: 1000+ RPM vs ~10 RPM on Vertex AI)
        gemini_location = os.environ.get('GEMINI_LOCATION', 'us-central1')
        ai_studio_api_key = get_google_ai_studio_api_key()
        self.gemini = GeminiProvider(
            project_id, gemini_location, self.cache_handler, self.usage_handler,
            ai_client=self, ai_studio_api_key=ai_studio_api_key
        )

        # Initialize Baseten provider (pass self for Haiku repair capability)
        try:
             self.baseten = BasetenProvider(get_baseten_api_key(), self.cache_handler, self.usage_handler, ai_client=self)
        except Exception as e:
             logger.warning(f"Failed to initialize Baseten provider: {e}")
             self.baseten = None

        # Initialize Clone provider
        self.clone = CloneProvider(self, self.cache_handler, self.usage_handler)

        # Expose usage handler methods directly for compatibility
        self.calculate_token_costs = self.usage_handler.calculate_token_costs
        self.calculate_processing_time_estimate = self.usage_handler.calculate_processing_time_estimate
        self.get_enhanced_call_metrics = self.usage_handler.get_enhanced_call_metrics
        self.extract_token_usage = self.usage_handler.extract_token_usage

        # NOTE: Session context now uses CLASS VARIABLES (see _session_id, _email, _s3_manager above)
        # This ensures all instances share the same context, fixing multi-instance bugs

    @property
    def session_id(self):
        """Get session_id from class variable (shared across all instances)."""
        return AIAPIClient._session_id

    @property
    def email(self):
        """Get email from class variable (shared across all instances)."""
        return AIAPIClient._email

    @property
    def s3_manager(self):
        """Get s3_manager from class variable (shared across all instances)."""
        return AIAPIClient._s3_manager

    def set_session_context(self, session_id: str, email: str, s3_manager=None):
        """Set session context for memory system (call once per lambda invocation).

        Uses CLASS variables so all AIAPIClient instances share the same context.
        This fixes bugs where multiple instances exist due to import path differences.
        """
        AIAPIClient._session_id = session_id
        AIAPIClient._email = email
        AIAPIClient._s3_manager = s3_manager
        logger.info(f"[AI_CLIENT_MEMORY] Session context set on CLASS (instance {id(self)}): session_id={session_id}, email={email}, s3_manager={type(s3_manager).__name__ if s3_manager else 'None'}")

    def _get_backup_models(self, primary_model: str, count: int = 2) -> List[str]:
        try:
            primary_index = self.MODEL_HIERARCHY.index(primary_model)
            primary_is_baseten = 'baseten' in primary_model.lower()
            
            backup_models = []
            curr_index = primary_index + 1
            
            while len(backup_models) < count and curr_index < len(self.MODEL_HIERARCHY):
                candidate = self.MODEL_HIERARCHY[curr_index]
                candidate_is_baseten = 'baseten' in candidate.lower()
                
                # Rule: Baseten models only chosen if primary was Baseten
                if candidate_is_baseten and not primary_is_baseten:
                    curr_index += 1
                    continue
                
                backup_models.append(candidate)
                curr_index += 1
                
            return backup_models
        except ValueError:
            # Model not in hierarchy - use fast/cheap models as fallback
            return ["claude-haiku-4-5", "gemini-2.5-flash-lite"][:count]

    async def call_structured_api(self, prompt: str, schema: Dict, model: Union[str, List[str]] = "claude-sonnet-4-5",
                                 tool_name: str = "structured_response", use_cache: bool = True,
                                 context: str = "", max_tokens: int = None, max_web_searches: int = 3,
                                 search_context_size: str = "low", debug_name: str = None, soft_schema: bool = False,
                                 include_domains: Optional[List[str]] = None, exclude_domains: Optional[List[str]] = None,
                                 use_code_extraction: bool = None, findall: bool = False, extraction: bool = False,
                                 findall_iterations: int = 1, timeout: Optional[int] = None,
                                 cache_ttl_days: int = 1,

                                 # NEW: 3-Tier Refinement Mode parameters
                                 original_data: Optional[Dict] = None,  # If provided, enables refinement mode
                                 validator_fn: Optional[callable] = None,  # Validates refined data (data) -> (is_valid, errors, warnings)
                                 try_patches_first: bool = True,  # Tier 1: try patches before full output
                                 refinement_context: Optional[Dict[str, str]] = None  # Additional context sections for refinement prompts
                                 ) -> Dict:

        call_start_time = datetime.now()

        # ═══════════════════════════════════════════════════════════
        # 3-TIER REFINEMENT MODE
        # ═══════════════════════════════════════════════════════════
        # If original_data is provided, use 3-tier cost-optimized refinement:
        # Tier 1: Primary model generates patches
        # Tier 2: Cheap model (model[1]) implements changes directly
        # Tier 3: Primary model generates full output (fallback)
        # ═══════════════════════════════════════════════════════════

        if original_data is not None:
            logger.info(f"🎯 3-TIER REFINEMENT MODE activated for {debug_name or 'refinement'}")

            # Normalize model list
            if isinstance(model, str):
                models_list = [model]
                backups = self._get_backup_models(model, 2)
                models_list.extend(backups)
            else:
                models_list = model

            primary_model = models_list[0]
            cheap_model = models_list[1] if len(models_list) > 1 else primary_model

            logger.info(f"   Tier 1: {primary_model} (patches)")
            logger.info(f"   Tier 2: {cheap_model} (direct implementation)")
            logger.info(f"   Tier 3: {primary_model} (full generation)")

            tier_costs = []

            # TIER 1: Primary model generates patches
            if try_patches_first:
                logger.info("📍 TIER 1: Attempting patches...")

                tier1_result = await self._refinement_tier1_patches(
                    prompt=prompt,
                    original_data=original_data,
                    schema=schema,
                    model=primary_model,
                    tool_name=tool_name,
                    validator_fn=validator_fn,
                    refinement_context=refinement_context,
                    max_tokens=max_tokens,
                    use_cache=use_cache,
                    debug_name=debug_name,
                    cache_ttl_days=cache_ttl_days
                )

                tier_costs.append(tier1_result.get('eliyahu_cost', 0.0))

                if tier1_result.get('success'):
                    logger.info(f"✅ TIER 1 SUCCESS: Patches applied (${tier1_result.get('eliyahu_cost', 0):.6f})")
                    tier1_result['refinement_tier'] = 1
                    tier1_result['tier_costs'] = tier_costs
                    tier1_result['total_refinement_cost'] = sum(tier_costs)
                    return tier1_result

                logger.warning(f"⚠️ TIER 1 FAILED: {tier1_result.get('error', 'Unknown error')}")

            # TIER 2: Cheap model direct implementation
            if cheap_model != primary_model or not try_patches_first:
                logger.info("📍 TIER 2: Trying cheap model direct implementation...")

                tier2_result = await self._refinement_tier2_cheap(
                    prompt=prompt,
                    original_data=original_data,
                    schema=schema,
                    model=cheap_model,
                    tool_name=tool_name,
                    validator_fn=validator_fn,
                    failed_patches=tier1_result.get('patches') if 'tier1_result' in locals() else None,
                    refinement_context=refinement_context,
                    max_tokens=max_tokens,
                    use_cache=use_cache,
                    debug_name=debug_name,
                    cache_ttl_days=cache_ttl_days
                )

                tier_costs.append(tier2_result.get('eliyahu_cost', 0.0))

                if tier2_result.get('success'):
                    logger.info(f"✅ TIER 2 SUCCESS: Cheap model implemented (${tier2_result.get('eliyahu_cost', 0):.6f})")
                    tier2_result['refinement_tier'] = 2
                    tier2_result['tier_costs'] = tier_costs
                    tier2_result['total_refinement_cost'] = sum(tier_costs)
                    return tier2_result

                logger.warning(f"⚠️ TIER 2 FAILED: {tier2_result.get('error', 'Unknown error')}")

            # TIER 3: Primary model full generation (fallback to normal execution)
            logger.info("📍 TIER 3: Falling back to primary model full generation...")

            # Build full generation prompt
            prompt = self._build_refinement_prompt_tier3(prompt, original_data, refinement_context)

            # Store tier info to add to result later
            refinement_tier3_info = {
                'tier': 3,
                'tier_costs': tier_costs,
                'method': 'full_generation'
            }

            # Continue to normal execution with modified prompt...
            # Result will be augmented with tier info at the end

        # Check if schema has conditionals (if/then/else) that Gemini/non-Claude models can't handle
        schema_has_conditionals = _schema_has_conditionals(schema) if schema else False

        if isinstance(model, str):
            models_to_try = [model]
            backups = self._get_backup_models(model, 2)
            models_to_try.extend(backups)

            # If schema has conditionals, prioritize Haiku for backup
            if schema_has_conditionals:
                # Remove Gemini from backups if present
                models_to_try = [m for m in models_to_try if 'gemini' not in m.lower()]

                # Ensure Haiku is in the backup chain (add if not already)
                if 'claude-haiku-4-5' not in models_to_try:
                    # Insert Haiku as first backup (after primary)
                    models_to_try.insert(1, 'claude-haiku-4-5')

                logger.warning(f"[SCHEMA_CONDITIONALS] Schema contains if/then/else - prioritizing Haiku")
                logger.info(f"[BACKUP_MODELS] Primary: {model}, Backups (adjusted for conditionals): {models_to_try[1:]}")
            elif backups:
                logger.info(f"[BACKUP_MODELS] Primary: {model}, Backups: {backups}")
        else:
            models_to_try = model

        # Default use_code_extraction to True for clone models, False otherwise
        if use_code_extraction is None:
            primary_model = models_to_try[0] if models_to_try else model
            use_code_extraction = primary_model.startswith('the-clone') if isinstance(primary_model, str) else False

        last_error = None
        attempted_models = []  # Track all attempts for logging

        for model_index, current_model in enumerate(models_to_try):
            try:
                api_provider = determine_api_provider(current_model)
                current_model_normalized = normalize_anthropic_model(current_model)
                
                if api_provider == 'vertex': 
                     current_model_normalized = normalize_vertex_model(current_model)

                cache_key = self.cache_handler.get_cache_key(prompt, current_model_normalized, schema, context, max_web_searches,
                                               soft_schema, include_domains, exclude_domains) if use_cache else None

                # Check cache via provider logic or manually?
                # Providers have check_cache inside them usually? No, I put it in AnthropicProvider.call_text_api but make_single_call doesn't check.
                # The original call_structured_api checked cache itself.

                cached_data = None  # Initialize to prevent UnboundLocalError
                expired_cache_context = ""  # Context from expired cache to inject into prompt
                if use_cache and cache_key:
                    cached_data = await self.cache_handler.check_cache(cache_key, api_provider, cache_ttl_days)
                    if cached_data:
                        # Check if cache is expired - if so, inject context into prompt
                        if cached_data.get('expired'):
                            logger.info(f"[CACHE_EXPIRED] Using expired cache as context for fresh call")
                            expired_cache_context = self.cache_handler.format_expired_cache_context(cached_data)
                            cached_data = None  # Treat as cache miss, will make fresh call
                        else:
                            # ... (metrics logic similar to original) ...
                            # Return cached response logic
                            # I'll rely on what check_cache returns and normalize it
                            token_usage = cached_data.get('token_usage', {})
                            cached_response = cached_data['api_response']

                            # [FIX] Validate cached response format - must have 'choices' key for compatibility
                            # If it's in old/raw Anthropic format, invalidate and rebuild cache
                            if not isinstance(cached_response, dict) or 'choices' not in cached_response:
                                logger.warning(f"[CACHE_FORMAT] Cached response missing 'choices' key for {api_provider}. Keys: {list(cached_response.keys()) if isinstance(cached_response, dict) else 'N/A'}")
                                logger.warning(f"[CACHE_FORMAT] Invalidating bad cache entry and making fresh call")

                                # Move bad cache to debug
                                await self.cache_handler.move_bad_cache_to_debug(
                                    cache_key,
                                    api_provider,
                                    "Missing 'choices' key in cached response (likely old format)",
                                    cached_response=cached_data
                                )

                                # Don't return cached data - fall through to make fresh API call
                                cached_data = None
                            else:
                                # Cached response is valid - return it with preserved time_estimated
                                cached_time_estimated = cached_data.get('time_estimated')  # Get original estimated time
                                enhanced_data = self.usage_handler.get_enhanced_call_metrics(
                                    cached_response, current_model, 0.001,
                                    pre_extracted_token_usage=token_usage, is_cached=True,
                                    cached_time_estimated=cached_time_estimated  # Pass original time for aggregation
                                )

                                # Use stored citations if available (clone provider), otherwise extract from response
                                cached_citations = cached_data.get('citations', [])
                                if not cached_citations:
                                    cached_citations = extract_citations_from_response(cached_response) if api_provider=='anthropic' else extract_citations_from_perplexity_response(cached_response)

                                return {
                                    'response': cached_response,
                                    'token_usage': token_usage,
                                    'processing_time': cached_data.get('processing_time', 0),
                                    'is_cached': True,
                                    'model_used': current_model,
                                    'citations': cached_citations,
                                    'enhanced_data': enhanced_data
                                }

                # If we have expired cache context, augment the prompt
                effective_prompt = prompt + expired_cache_context if expired_cache_context else prompt

                if not cached_data and use_cache and cache_key:
                    logger.debug(f"No valid cache found for {api_provider}, making fresh API call")

                # Make Call (use effective_prompt which includes expired cache context if any)
                if api_provider == 'anthropic':
                    result = await self.anthropic.make_single_call("https://api.anthropic.com/v1/messages",
                         {'Content-Type': 'application/json', 'X-API-Key': self.anthropic.api_key, 'anthropic-version': '2023-06-01'},
                         self._build_anthropic_data(current_model_normalized, effective_prompt, schema, tool_name, max_tokens, max_web_searches, soft_schema),
                         current_model_normalized, use_cache, cache_key, call_start_time, max_web_searches, soft_schema, schema, timeout)
                elif api_provider == 'perplexity':
                    result = await self.perplexity.make_single_structured_call(effective_prompt, schema, current_model, use_cache, cache_key, call_start_time, search_context_size, debug_name, max_tokens or 64000, soft_schema, include_domains, exclude_domains)
                elif api_provider == 'gemini':
                    if not self.gemini.project_id: continue
                    # Gemini has native JSON mode support, use soft_schema parameter as-is
                    result = await self.gemini.make_single_call(effective_prompt, schema, current_model, use_cache, cache_key, call_start_time, max_tokens or 64000, soft_schema, timeout)
                elif api_provider == 'vertex':
                    if not self.vertex.project_id: continue
                    # Force soft_schema for all Vertex models (DeepSeek) as hard schema support is experimental/flaky
                    use_soft_schema_for_vertex = True
                    result = await self.vertex.make_single_call(effective_prompt, schema, current_model_normalized, use_cache, cache_key, call_start_time, max_tokens or 64000, use_soft_schema_for_vertex, timeout)
                elif api_provider == 'baseten':
                    if not self.baseten: continue
                    # Force soft_schema for Baseten DeepSeek V3.2 due to potential native JSON issues or consistency
                    use_soft_schema_for_baseten = True
                    result = await self.baseten.make_single_call(effective_prompt, schema, current_model, use_cache, cache_key, call_start_time, max_tokens or 64000, use_soft_schema_for_baseten, timeout)
                elif api_provider == 'clone':
                    result = await self.clone.make_structured_call(effective_prompt, current_model, use_cache, cache_key, call_start_time, schema, soft_schema, debug_name, include_domains, exclude_domains, use_code_extraction, findall, extraction, findall_iterations)
                else:
                    continue

                if result:
                    result['model_used'] = current_model
                    result['used_backup_model'] = model_index > 0
                    attempted_models.append({'model': current_model, 'success': True})
                    result['attempted_models'] = attempted_models

                    # Normalize response format for compatibility FIRST
                    if api_provider in ['anthropic', 'gemini', 'baseten', 'vertex']:
                        # Convert to unified format
                        import json
                        api_response = result['response']
                        structured = extract_structured_response(api_response, tool_name)

                        # Put the extracted structure directly in the unified format
                        # Don't try to extract validation_results - that's application-specific
                        result['response'] = {'choices': [{'message': {'role': 'assistant', 'content': json.dumps(structured)}}]}
                        if api_provider == 'anthropic':
                            result['citations'] = extract_citations_from_response(api_response)

                    # UNIVERSAL SCHEMA VALIDATION & REPAIR
                    # Run AFTER normalization so all providers have unified format
                    # Run BEFORE caching so we cache validated/repaired responses
                    result = await self._validate_and_repair_structured_response(
                        result, schema, current_model, api_provider, soft_schema
                    )

                    # Cache the VALIDATED response (after normalization and validation)
                    # This ensures cache hits don't need re-validation/repair
                    if api_provider in ['anthropic', 'gemini', 'baseten', 'vertex']:
                        if use_cache and cache_key and not result.get('is_cached', False):
                            processing_time = result.get('processing_time', 0)
                            token_usage = result.get('token_usage', {})
                            await self.cache_handler.save_to_cache(
                                cache_key,
                                result['response'],  # Save validated response
                                token_usage,
                                processing_time,
                                current_model,
                                api_provider
                            )
                            logger.debug(f"[CACHE_SAVE] Saved validated response for {api_provider}/{current_model}")

                    # URL validation
                    try:
                         if result.get('citations'):
                             content_str = result['response']['choices'][0]['message']['content']
                             parsed = json.loads(content_str)
                             validated = validate_urls_in_response(parsed, result['citations'])
                             result['response']['choices'][0]['message']['content'] = json.dumps(validated)
                    except Exception:
                         pass

                    # Augment with Tier 3 refinement info if applicable
                    if 'refinement_tier3_info' in locals():
                        # Extract refined data
                        try:
                            import json
                            content = result['response']['choices'][0]['message']['content']
                            refined_data = json.loads(content)

                            # Validate if validator provided
                            if validator_fn:
                                is_valid, errors, warnings = validator_fn(refined_data)
                                if not is_valid:
                                    logger.error(f"Tier 3 validation failed: {errors}")
                                    # Even if validation fails, return result with error info
                                    result['validation_errors'] = errors
                                    result['validation_warnings'] = warnings
                                else:
                                    result['refined_data'] = refined_data

                            else:
                                result['refined_data'] = refined_data

                            # Add tier 3 info
                            tier_costs.append(result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0))
                            result['refinement_tier'] = 3
                            result['tier_costs'] = tier_costs
                            result['total_refinement_cost'] = sum(tier_costs)
                            result['method'] = 'full_generation'

                            logger.info(f"✅ TIER 3 SUCCESS: Full generation (${result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0):.6f})")
                            logger.info(f"💰 Total refinement cost: ${sum(tier_costs):.6f} across {len(tier_costs)} tiers")

                        except Exception as e:
                            logger.warning(f"Could not augment Tier 3 result: {e}")

                    return result
            
            except Exception as e:
                attempted_models.append({'model': current_model, 'success': False, 'error': str(e)[:100]})
                logger.warning(f"[BACKUP_RETRY] Model {current_model} failed: {e}")
                logger.info(f"[BACKUP_RETRY] Trying next model in queue (remaining: {len(models_to_try) - model_index - 1})")
                last_error = e
                if "[REFUSAL]" in str(e):
                    # Add fallbacks
                    try:
                        idx = self.MODEL_HIERARCHY.index(current_model)
                        for m in self.MODEL_HIERARCHY[idx+1:]:
                            if m not in models_to_try: models_to_try.append(m)
                    except:
                        pass
                continue
        
        raise last_error or Exception("All models failed")

    async def _validate_and_repair_structured_response(self, result: Dict, schema: Dict,
                                                        model: str, provider: str,
                                                        soft_schema: bool) -> Dict:
        """
        Universal schema validation and repair for ALL providers and schema modes.

        Args:
            result: Provider response dict with 'response' key
            schema: Expected JSON schema
            model: Model name
            provider: Provider name (perplexity, anthropic, etc.)
            soft_schema: Whether soft schema mode was used

        Returns:
            result dict, potentially with repaired response and _repair_meta

        Raises:
            Exception with [SCHEMA_ERROR] or [REPAIR_FAILED] prefix to trigger backup models
        """
        from .utils import extract_json_from_text, repair_json_with_haiku
        import json

        try:
            # Skip validation if no schema provided
            if not schema or not isinstance(schema, dict):
                return result

            # Skip repair if already inside a repair call (prevent recursive repair loop)
            # repair_json_with_haiku adds _repair_explanation to the schema before calling call_structured_api
            if '_repair_explanation' in schema.get('properties', {}):
                return result

            # Extract response content
            response = result.get('response', {})
            if not response:
                return result

            # Get content from unified format
            if 'choices' in response and len(response['choices']) > 0:
                message = response['choices'][0].get('message', {})
                content = message.get('content', '')

                if not isinstance(content, str) or not content.strip():
                    return result

                # Try to parse JSON
                parsed = None
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    # Not valid JSON, try extraction
                    parsed = extract_json_from_text(content)

                # If parsed is a list (e.g. Perplexity returns raw array), wrap in expected object
                # Perplexity unwraps validation_results schema, so response is the inner array
                if isinstance(parsed, list) and schema.get('type') == 'object' and 'properties' in schema:
                    # Find the single array property to wrap the list into
                    array_props = [k for k, v in schema['properties'].items()
                                   if isinstance(v, dict) and v.get('type') == 'array']
                    if len(array_props) == 1:
                        parsed = {array_props[0]: parsed}
                        result['response']['choices'][0]['message']['content'] = json.dumps(parsed)
                        logger.debug(f"[UNIVERSAL_VALIDATION] Wrapped array response into '{array_props[0]}' property")

                # Check if we have valid parsed JSON
                if not parsed or not isinstance(parsed, dict):
                    logger.warning(f"[UNIVERSAL_VALIDATION] {provider}/{model}: JSON extraction failed")

                    # Attempt repair
                    parsed, repair_result, repair_explanation = await repair_json_with_haiku(
                        content, schema, self
                    )

                    if repair_result and parsed:
                        repair_cost = repair_result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                        logger.info(f"[HAIKU_REPAIR] Provider: {provider}, Model: {model}, Schema: {'soft' if soft_schema else 'hard'}")
                        logger.info(f"[HAIKU_REPAIR] Explanation: {repair_explanation}")
                        logger.info(f"[HAIKU_REPAIR] Cost: ${repair_cost:.6f}")

                        result['_repair_meta'] = {
                            'repaired': True,
                            'cost': repair_cost,
                            'model': 'gemini-2.5-flash-lite',
                            'provider': 'gemini',
                            'explanation': repair_explanation,
                            'original_provider': provider,
                            'original_model': model,
                            'schema_mode': 'soft' if soft_schema else 'hard'
                        }

                        # Merge repair cost into enhanced_data
                        if 'enhanced_data' in result and repair_cost > 0:
                            enhanced_data = result['enhanced_data']
                            if 'costs' in enhanced_data and 'actual' in enhanced_data['costs']:
                                enhanced_data['costs']['actual']['total_cost'] = enhanced_data['costs']['actual'].get('total_cost', 0.0) + repair_cost
                                enhanced_data['repair_info'] = result['_repair_meta']
                                logger.info(f"[COST_UPDATE] Added repair cost ${repair_cost:.4f}. New total: ${enhanced_data['costs']['actual']['total_cost']:.4f}")

                        # Save repair data
                        await self.cache_handler.save_haiku_repair_data(
                            original_provider=provider,
                            original_model=model,
                            malformed_input=content,
                            repaired_output=parsed,
                            repair_explanation=repair_explanation or 'No explanation provided',
                            repair_cost=repair_cost
                        )

                        # Update response content
                        result['response']['choices'][0]['message']['content'] = json.dumps(parsed)
                    else:
                        logger.error(f"[UNIVERSAL_VALIDATION] {provider}/{model}: Repair failed")
                        raise Exception("[REPAIR_FAILED] Could not extract or repair JSON")

                # Validate required fields
                if parsed and schema:
                    required = schema.get('required', [])
                    missing = [f for f in required if f not in parsed]

                    if missing:
                        logger.warning(f"[UNIVERSAL_VALIDATION] {provider}/{model}: Missing required fields {missing}")

                        # Attempt repair
                        parsed_repaired, repair_result, repair_explanation = await repair_json_with_haiku(
                            content, schema, self
                        )

                        if repair_result and parsed_repaired:
                            repair_cost = repair_result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                            logger.info(f"[HAIKU_REPAIR] Provider: {provider}, Model: {model}, Schema: {'soft' if soft_schema else 'hard'}")
                            logger.info(f"[HAIKU_REPAIR] Explanation: {repair_explanation}")
                            logger.info(f"[HAIKU_REPAIR] Cost: ${repair_cost:.6f}")

                            result['_repair_meta'] = {
                                'repaired': True,
                                'cost': repair_cost,
                                'model': 'gemini-2.5-flash-lite',
                                'provider': 'gemini',
                                'explanation': repair_explanation,
                                'original_provider': provider,
                                'original_model': model,
                                'schema_mode': 'soft' if soft_schema else 'hard',
                                'reason': 'missing_required_fields'
                            }

                            # Merge repair cost into enhanced_data
                            if 'enhanced_data' in result and repair_cost > 0:
                                enhanced_data = result['enhanced_data']
                                if 'costs' in enhanced_data and 'actual' in enhanced_data['costs']:
                                    enhanced_data['costs']['actual']['total_cost'] = enhanced_data['costs']['actual'].get('total_cost', 0.0) + repair_cost
                                    enhanced_data['repair_info'] = result['_repair_meta']
                                    logger.info(f"[COST_UPDATE] Added repair cost ${repair_cost:.4f}. New total: ${enhanced_data['costs']['actual']['total_cost']:.4f}")

                            await self.cache_handler.save_haiku_repair_data(
                                original_provider=provider,
                                original_model=model,
                                malformed_input=content,
                                repaired_output=parsed_repaired,
                                repair_explanation=repair_explanation or 'No explanation provided',
                                repair_cost=repair_cost
                            )

                            # Re-validate
                            missing_after = [f for f in required if f not in parsed_repaired]
                            if not missing_after:
                                parsed = parsed_repaired
                                result['response']['choices'][0]['message']['content'] = json.dumps(parsed)
                            else:
                                logger.error(f"[UNIVERSAL_VALIDATION] {provider}/{model}: Still missing {missing_after} after repair")
                                raise Exception(f"[SCHEMA_ERROR] Missing required fields after repair: {missing_after}")
                        else:
                            logger.error(f"[UNIVERSAL_VALIDATION] {provider}/{model}: Repair failed for missing fields")
                            raise Exception(f"[SCHEMA_ERROR] Missing required fields: {missing}")

            return result

        except Exception as e:
            # Re-raise critical errors to trigger backup model retry
            if "[SCHEMA_ERROR]" in str(e) or "[REPAIR_FAILED]" in str(e):
                logger.error(f"[UNIVERSAL_VALIDATION] Critical error for {provider}/{model}: {e}")
                raise
            # Log but don't fail for other errors
            logger.warning(f"[UNIVERSAL_VALIDATION] Validation error (non-critical): {e}")
            return result

    def _build_anthropic_data(self, model, prompt, schema, tool_name, max_tokens, max_web_searches, soft_schema):
        max_t = self.usage_handler.enforce_provider_token_limit(model, max_tokens or 64000)
        if soft_schema:
            return {
                "model": model, "max_tokens": max_t, "temperature": 0.1,
                "messages": [{"role": "user", "content": f"{prompt}\n\nIMPORTANT: Return your response as valid JSON only."}]
            }
        
        tools = []
        if max_web_searches > 0:
            tools.append({"type": "web_search_20250305", "name": "web_search", "max_uses": max_web_searches})
        tools.append({"name": tool_name, "description": f"Provide structured response using {tool_name}.", "input_schema": schema})
        
        tool_choice = {"type": "auto"} if max_web_searches > 0 else {"type": "tool", "name": tool_name}
        return {
            "model": model, "max_tokens": max_t, "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}],
            "tools": tools, "tool_choice": tool_choice
        }

    async def call_text_api(self, prompt: str, model: Union[str, List[str]] = "claude-sonnet-4-5",
                           use_cache: bool = True, context: str = "", max_web_searches: int = 3) -> Dict:
        if isinstance(model, list): model = model[0]
        return await self.anthropic.call_text_api(prompt, model, use_cache, context, max_web_searches)

    async def validate_with_perplexity_smart_cache(self, prompt: str, row_data: Dict, targets: List,
                                                 model: str = "sonar-pro", search_context_size: str = "low", 
                                                 use_cache: bool = True, config_hash: str = "") -> Dict:
        return await self.perplexity.validate_with_smart_cache(prompt, row_data, targets, model, search_context_size, use_cache, config_hash)

    async def validate_with_perplexity(self, prompt: str, model: str = "sonar-pro",
                                     search_context_size: str = "low", use_cache: bool = True,
                                     context: str = "", include_domains: Optional[List[str]] = None,
                                     exclude_domains: Optional[List[str]] = None) -> Dict:
        return await self.perplexity.validate(prompt, model, search_context_size, use_cache, context, include_domains, exclude_domains)

    # Re-expose methods for compatibility
    def _extract_token_usage(self, response, model, search_context_size=None):
        return self.usage_handler.extract_token_usage(response, model, search_context_size)

    def extract_structured_response(self, response, tool_name="structured_response"):
        """Extract structured response from API response."""
        return extract_structured_response(response, tool_name)

    def load_pricing_data(self):
        return self.usage_handler.load_pricing_data()

    def aggregate_provider_metrics(self, metrics_list):
        return self.usage_handler.aggregate_provider_metrics(metrics_list)

    async def _save_debug_data(self, *args, **kwargs):
        return await self.cache_handler.save_debug_data(*args, **kwargs)

    async def _move_bad_cache_to_debug(self, *args, **kwargs):
        return await self.cache_handler.move_bad_cache_to_debug(*args, **kwargs)

    # ═══════════════════════════════════════════════════════════
    # 3-TIER REFINEMENT MODE HELPER METHODS
    # ═══════════════════════════════════════════════════════════

    def _build_refinement_prompt_tier1(self, instruction: str, original_data: Dict, refinement_context: Dict = None) -> str:
        """Build prompt for Tier 1 (patches with primary model)"""
        prompt = f"""# USER REQUEST
{instruction}

# CURRENT DATA
```json
{self._format_json_compact(original_data)}
```

# TASK
Generate JSON Patch operations (RFC 6902) to implement the requested changes.

**Requirements:**
- Use minimal patches - only change what's requested
- Use exact JSON Pointer paths (e.g., "/field/subfield" or "/array/0/field")
- Include 'test' operations before critical changes for safety
- Preserve all unchanged data

**Available operations:**
- replace: Change existing field value
- add: Add new field or array element
- remove: Delete field or array element
- test: Verify expected value (safety check)

**Example:**
```json
{{
  "patch_operations": [
    {{"op": "test", "path": "/field_name", "value": "expected_current_value"}},
    {{"op": "replace", "path": "/field_name", "value": "new_value"}}
  ],
  "reasoning": "Changed field_name because..."
}}
```
"""

        # Add context if provided
        if refinement_context:
            prompt += "\n# ADDITIONAL CONTEXT\n"
            for section_name, section_content in refinement_context.items():
                prompt += f"\n## {section_name}\n{section_content}\n"

        return prompt

    def _build_refinement_prompt_tier2(self, instruction: str, original_data: Dict, failed_patches: List = None, refinement_context: Dict = None) -> str:
        """Build prompt for Tier 2 (direct implementation with cheap model)"""

        context_info = ""
        if failed_patches:
            context_info = f"""
# FAILED PATCHES (for reference)
These patches didn't work - you don't need to use patches, just implement directly:
```json
{self._format_json_compact(failed_patches)}
```
"""

        prompt = f"""# USER REQUEST
{instruction}

# CURRENT DATA
```json
{self._format_json_compact(original_data)}
```

{context_info}

# TASK
Implement the requested changes directly and return the complete updated data.

**Requirements:**
- Make ONLY the changes requested in the user request
- Keep everything else exactly as it is
- Return the complete updated data structure
- Ensure all required fields are present
- Maintain the same structure and data types
"""

        # Add context if provided
        if refinement_context:
            prompt += "\n# ADDITIONAL CONTEXT\n"
            for section_name, section_content in refinement_context.items():
                prompt += f"\n## {section_name}\n{section_content}\n"

        return prompt

    def _build_refinement_prompt_tier3(self, instruction: str, original_data: Dict, refinement_context: Dict = None) -> str:
        """Build prompt for Tier 3 (full generation with primary model)"""
        prompt = f"""# USER REQUEST
{instruction}

# CURRENT DATA (for context)
```json
{self._format_json_compact(original_data)}
```

# TASK
Generate the complete updated data with the requested changes.

**Requirements:**
- Implement the requested changes
- Ensure all required fields are present and valid
- Maintain consistent structure and data types
- Include all necessary data for the complete object
"""

        # Add context if provided
        if refinement_context:
            prompt += "\n# ADDITIONAL CONTEXT\n"
            for section_name, section_content in refinement_context.items():
                prompt += f"\n## {section_name}\n{section_content}\n"

        return prompt

    def _format_json_compact(self, data) -> str:
        """Format JSON in a compact but readable way for prompts"""
        import json
        # For large data, use compact format
        if isinstance(data, (dict, list)) and len(str(data)) > 5000:
            return json.dumps(data, separators=(',', ':'))
        return json.dumps(data, indent=2)

    def _create_patch_schema(self) -> Dict:
        """Create JSON schema for patch responses (Tier 1)"""
        return {
            "type": "object",
            "required": ["patch_operations", "reasoning"],
            "properties": {
                "patch_operations": {
                    "type": "array",
                    "description": "Array of RFC 6902 JSON Patch operations",
                    "items": {
                        "type": "object",
                        "required": ["op", "path"],
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["add", "remove", "replace", "test", "move", "copy"],
                                "description": "Operation type"
                            },
                            "path": {
                                "type": "string",
                                "description": "JSON Pointer path (e.g., '/field' or '/array/0/subfield')"
                            },
                            "value": {
                                "description": "Value for add/replace operations"
                            },
                            "from": {
                                "type": "string",
                                "description": "Source path for move/copy operations"
                            }
                        }
                    },
                    "minItems": 1
                },
                "reasoning": {
                    "type": "string",
                    "description": "Clear explanation of why these changes address the request"
                }
            }
        }

    async def _refinement_tier1_patches(self, prompt: str, original_data: Dict, schema: Dict, model: str,
                                       tool_name: str, validator_fn: callable = None,
                                       refinement_context: Dict = None, **kwargs) -> Dict:
        """Tier 1: Generate and apply patches with primary model"""
        try:
            # Build patch-specific prompt
            tier1_prompt = self._build_refinement_prompt_tier1(prompt, original_data, refinement_context)

            # Use patch schema
            patch_schema = self._create_patch_schema()

            # Call API for patches
            result = await self.call_structured_api(
                prompt=tier1_prompt,
                schema=patch_schema,
                model=model,
                tool_name=f"{tool_name}_patches",
                original_data=None,  # Prevent recursive refinement mode
                **kwargs
            )

            # Extract patches
            structured_data = self.extract_structured_response(result['response'], f"{tool_name}_patches")
            patches = structured_data.get('patch_operations', [])
            reasoning = structured_data.get('reasoning', '')

            if not patches:
                return {
                    'success': False,
                    'error': 'No patches generated',
                    'eliyahu_cost': result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                }

            # Apply patches
            try:
                import jsonpatch
                patch = jsonpatch.JsonPatch(patches)
                refined_data = patch.apply(original_data)
            except Exception as e:
                logger.error(f"Patch application failed: {e}")
                return {
                    'success': False,
                    'error': f'Patch application failed: {str(e)}',
                    'patches': patches,
                    'eliyahu_cost': result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                }

            # Validate if validator provided
            if validator_fn:
                is_valid, errors, warnings = validator_fn(refined_data)
                if not is_valid:
                    return {
                        'success': False,
                        'error': f'Validation failed: {errors[0] if errors else "Unknown"}',
                        'validation_errors': errors,
                        'patches': patches,
                        'eliyahu_cost': result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                    }

            # Success!
            return {
                'success': True,
                'response': result['response'],
                'refined_data': refined_data,
                'patches': patches,
                'reasoning': reasoning,
                'method': 'patches',
                'model_used': model,
                'eliyahu_cost': result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0),
                'token_usage': result.get('token_usage', {}),
                'enhanced_data': result.get('enhanced_data', {}),
                'processing_time': result.get('processing_time', 0.0),
                'is_cached': result.get('is_cached', False)
            }

        except Exception as e:
            logger.error(f"Tier 1 patches exception: {e}")
            return {'success': False, 'error': str(e), 'eliyahu_cost': 0.0}

    async def _refinement_tier2_cheap(self, prompt: str, original_data: Dict, schema: Dict, model: str,
                                     tool_name: str, validator_fn: callable = None, failed_patches: List = None,
                                     refinement_context: Dict = None, **kwargs) -> Dict:
        """Tier 2: Direct implementation with cheap model"""
        try:
            # Build tier 2 prompt
            tier2_prompt = self._build_refinement_prompt_tier2(prompt, original_data, failed_patches, refinement_context)

            # Call API with full schema
            result = await self.call_structured_api(
                prompt=tier2_prompt,
                schema=schema,
                model=model,
                tool_name=f"{tool_name}_implementation",
                original_data=None,  # Prevent recursive refinement mode
                **kwargs
            )

            # Extract refined data
            refined_data = self.extract_structured_response(result['response'], f"{tool_name}_implementation")

            # Validate if validator provided
            if validator_fn:
                is_valid, errors, warnings = validator_fn(refined_data)
                if not is_valid:
                    return {
                        'success': False,
                        'error': f'Validation failed: {errors[0] if errors else "Unknown"}',
                        'validation_errors': errors,
                        'eliyahu_cost': result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                    }

            # Success!
            return {
                'success': True,
                'response': result['response'],
                'refined_data': refined_data,
                'method': 'cheap_implementation',
                'model_used': model,
                'eliyahu_cost': result.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0.0),
                'token_usage': result.get('token_usage', {}),
                'enhanced_data': result.get('enhanced_data', {}),
                'processing_time': result.get('processing_time', 0.0),
                'is_cached': result.get('is_cached', False)
            }

        except Exception as e:
            logger.error(f"Tier 2 cheap implementation exception: {e}")
            return {'success': False, 'error': str(e), 'eliyahu_cost': 0.0}

