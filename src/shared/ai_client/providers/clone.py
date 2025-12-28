
import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class CloneProvider:
    def __init__(self, ai_client, cache_handler, usage_handler):
        self.ai_client = ai_client
        self.cache_handler = cache_handler
        self.usage_handler = usage_handler
        self._clone_instance = None

    def _get_clone_instance(self):
        """Lazy load TheClone2Refined instance."""
        if self._clone_instance is None:
            # Import here to avoid circular dependency
            # We assume src/ is in python path or we use relative imports if possible
            # But the_clone is a top level package in src/
            try:
                # Add src/ to path if needed (though typically Lambda environment handles this)
                import sys
                import os
                # This path addition might be redundant if src/ is root, but safe
                src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
                if src_path not in sys.path:
                    sys.path.append(src_path)
                
                from the_clone.the_clone import TheClone2Refined
                self._clone_instance = TheClone2Refined(ai_client=self.ai_client)
            except ImportError as e:
                logger.error(f"Failed to import TheClone2Refined: {e}")
                raise

        return self._clone_instance

    async def make_structured_call(self, prompt: str, model: str, use_cache: bool, cache_key: str, start_time: datetime, schema: Dict = None, soft_schema: bool = False, debug_name: str = None, include_domains: List[str] = None, exclude_domains: List[str] = None, use_code_extraction: bool = False, findall: bool = False) -> Dict:
        """
        Execute a call to 'The Clone' agentic pipeline.
        
        Args:
            prompt: The user query
            model: 'the-clone', 'the-clone-claude', or 'the-clone-baseten'
            ...
        """
        try:
            clone = self._get_clone_instance()
            
            # Determine provider based on model name
            provider = 'deepseek' # Default
            
            if model == 'the-clone-claude':
                provider = 'claude'
            elif model == 'the-clone-baseten':
                provider = 'baseten'
            elif model == 'the-clone':
                provider = 'deepseek'
            
            # Execute query
            logger.info(f"[CLONE_PROVIDER] Executing agentic pipeline for model: {model} (provider={provider}, findall={findall})")
            result = await clone.query(
                prompt=prompt,
                provider=provider,
                schema=schema,  # Pass schema to Clone for structured output
                debug_dir=f"/tmp/clone_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}", # Temp debug dir
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                use_code_extraction=use_code_extraction,
                findall=findall  # Pass findall parameter
            )
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Extract result and metadata
            answer = result.get('answer', {})
            citations = result.get('citations', [])
            metadata = result.get('metadata', {})
            cost_breakdown = metadata.get('cost_breakdown', {})
            cost_by_provider = metadata.get('cost_by_provider', {})
            total_cost = metadata.get('total_cost', 0.0)

            # Construct synthetic token usage from cost
            # We don't have exact tokens, so we create a 'cost-only' usage object
            # Enhanced metrics will pick this up
            token_usage = {
                'api_provider': 'clone',
                'model': model,
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'api_provided_cost': {
                    'total_cost': total_cost,
                    'breakdown': cost_breakdown,
                    'source': 'agentic_pipeline'
                }
            }

            # Build provider_metrics from cost_by_provider for DynamoDB tracking
            provider_metrics = {}
            for provider, data in cost_by_provider.items():
                provider_metrics[provider] = {
                    'cost_actual': data.get('cost', 0.0),
                    'cost_estimated': data.get('cost', 0.0),  # No cache, so actual = estimated
                    'calls': data.get('calls', 0),
                    'tokens': 0,  # Token count not available from Clone
                    'cache_efficiency_percent': 0.0
                }
            
            # Normalize response structure
            # The Clone returns an 'answer' dict. 
            # We wrap it in the standard chat completion format
            response_json = {
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': json.dumps(answer) # Return as stringified JSON
                    }
                }],
                'usage': token_usage,
                'model': model,
                'stop_reason': 'stop'
            }
            
            # Save debug data
            if debug_name:
                await self.cache_handler.save_debug_data('clone', model, {'prompt': prompt}, response_json, context="agent_success", debug_name=debug_name)

                # Also save markdown log if available
                debug_log = metadata.get('debug_log', '')
                if debug_log:
                    await self.cache_handler.save_markdown_log('clone', model, debug_log, debug_name=debug_name)
            
            # Save to cache if enabled
            if use_cache and cache_key:
                await self.cache_handler.save_to_cache(cache_key, response_json, token_usage, processing_time, model, 'clone')
            
            # Generate enhanced metrics
            # We pass pre_extracted_token_usage because we constructed it manually
            enhanced_data = self.usage_handler.get_enhanced_call_metrics(
                response_json, model, processing_time, is_cached=False,
                pre_extracted_token_usage=token_usage
            )

            # Inject detailed cost breakdown into enhanced metrics
            enhanced_data['costs']['actual']['breakdown'] = cost_breakdown

            # Inject provider-level metrics for DynamoDB aggregation
            enhanced_data['provider_metrics'] = provider_metrics
            enhanced_data['api_provider'] = 'clone'  # Top-level provider is 'clone'
            
            return {
                'response': response_json,
                'token_usage': token_usage,
                'processing_time': processing_time,
                'is_cached': False,
                'citations': citations,
                'enhanced_data': enhanced_data
            }

        except Exception as e:
            logger.error(f"[CLONE_PROVIDER] Error executing clone: {e}")
            await self.cache_handler.save_debug_data('clone', model, {'prompt': prompt}, None, error=e, context="agent_exception")
            raise
