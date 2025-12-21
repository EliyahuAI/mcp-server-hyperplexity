
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

class AIAPIClient:
    """Shared AI API client with caching and schema support."""
    
    MODEL_HIERARCHY = MODEL_HIERARCHY

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

        # Initialize Gemini provider (same project as Vertex, but us-central1 for better Gemini availability)
        gemini_location = os.environ.get('GEMINI_LOCATION', 'us-central1')
        self.gemini = GeminiProvider(project_id, gemini_location, self.cache_handler, self.usage_handler, ai_client=self)

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
            return ["claude-opus-4-0", "claude-3-7-sonnet-latest"][:count]

    async def call_structured_api(self, prompt: str, schema: Dict, model: Union[str, List[str]] = "claude-sonnet-4-5",
                                 tool_name: str = "structured_response", use_cache: bool = True,
                                 context: str = "", max_tokens: int = None, max_web_searches: int = 3,
                                 search_context_size: str = "low", debug_name: str = None, soft_schema: bool = False,
                                 include_domains: Optional[List[str]] = None, exclude_domains: Optional[List[str]] = None,
                                 use_code_extraction: bool = None) -> Dict:

        call_start_time = datetime.now()

        if isinstance(model, str):
            models_to_try = [model]
            backups = self._get_backup_models(model, 2)
            models_to_try.extend(backups)
            if backups:
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
                
                if use_cache and cache_key:
                    cached_data = await self.cache_handler.check_cache(cache_key, api_provider)
                    if cached_data:
                         # ... (metrics logic similar to original) ...
                         # Return cached response logic
                         # I'll rely on what check_cache returns and normalize it
                         token_usage = cached_data.get('token_usage', {})
                         enhanced_data = self.usage_handler.get_enhanced_call_metrics(cached_data['api_response'], current_model, 0.001, pre_extracted_token_usage=token_usage, is_cached=True)
                         
                         return {
                             'response': cached_data['api_response'],
                             'token_usage': token_usage,
                             'processing_time': cached_data.get('processing_time', 0),
                             'is_cached': True,
                             'model_used': current_model,
                             'citations': extract_citations_from_response(cached_data['api_response']) if api_provider=='anthropic' else extract_citations_from_perplexity_response(cached_data['api_response']),
                             'enhanced_data': enhanced_data
                         }

                # Make Call
                if api_provider == 'anthropic':
                    result = await self.anthropic.make_single_call("https://api.anthropic.com/v1/messages",
                         {'Content-Type': 'application/json', 'X-API-Key': self.anthropic.api_key, 'anthropic-version': '2023-06-01'},
                         self._build_anthropic_data(current_model_normalized, prompt, schema, tool_name, max_tokens, max_web_searches, soft_schema),
                         current_model_normalized, use_cache, cache_key, call_start_time, max_web_searches, soft_schema, schema)
                elif api_provider == 'perplexity':
                    result = await self.perplexity.make_single_structured_call(prompt, schema, current_model, use_cache, cache_key, call_start_time, search_context_size, debug_name, max_tokens or 8000, soft_schema, include_domains, exclude_domains)
                elif api_provider == 'gemini':
                    if not self.gemini.project_id: continue
                    # Gemini has native JSON mode support, use soft_schema parameter as-is
                    result = await self.gemini.make_single_call(prompt, schema, current_model, use_cache, cache_key, call_start_time, max_tokens or 8000, soft_schema)
                elif api_provider == 'vertex':
                    if not self.vertex.project_id: continue
                    # Force soft_schema for all Vertex models (DeepSeek) as hard schema support is experimental/flaky
                    use_soft_schema_for_vertex = True
                    result = await self.vertex.make_single_call(prompt, schema, current_model_normalized, use_cache, cache_key, call_start_time, max_tokens or 8000, use_soft_schema_for_vertex)
                elif api_provider == 'baseten':
                    if not self.baseten: continue
                    # Force soft_schema for Baseten DeepSeek V3.2 due to potential native JSON issues or consistency
                    use_soft_schema_for_baseten = True
                    result = await self.baseten.make_single_call(prompt, schema, current_model, use_cache, cache_key, call_start_time, max_tokens or 8000, use_soft_schema_for_baseten)
                elif api_provider == 'clone':
                    result = await self.clone.make_structured_call(prompt, current_model, use_cache, cache_key, call_start_time, schema, soft_schema, debug_name, include_domains, exclude_domains, use_code_extraction)
                else:
                    continue

                if result:
                    result['model_used'] = current_model
                    result['used_backup_model'] = model_index > 0
                    attempted_models.append({'model': current_model, 'success': True})
                    result['attempted_models'] = attempted_models

                    # Normalize response format for compatibility
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
                    
                    # URL validation
                    try:
                         if result.get('citations'):
                             content_str = result['response']['choices'][0]['message']['content']
                             parsed = json.loads(content_str)
                             validated = validate_urls_in_response(parsed, result['citations'])
                             result['response']['choices'][0]['message']['content'] = json.dumps(validated)
                    except Exception:
                         pass

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

    def _build_anthropic_data(self, model, prompt, schema, tool_name, max_tokens, max_web_searches, soft_schema):
        max_t = self.usage_handler.enforce_provider_token_limit(model, max_tokens or 8000)
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

