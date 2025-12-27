
import logging
import time
import re
from typing import Dict, Any, Optional, List
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

from .utils import determine_api_provider

logger = logging.getLogger(__name__)

class UsageHandler:
    """
    Handles token usage extraction, pricing, cost calculation, and limits.
    """
    def __init__(self):
        self._token_limits_cache = {}
        self._pricing_data_cache = None
        self.model_config_table = self._load_model_config_table()

    def _load_model_config_table(self):
        """ robustly load ModelConfigTable """
        try:
            # Try multiple import strategies
            for import_strategy in ['direct', 'shared', 'path_setup']:
                try:
                    if import_strategy == 'direct':
                        from model_config_table import ModelConfigTable
                    elif import_strategy == 'shared':
                        from shared.model_config_table import ModelConfigTable
                    else:  # path_setup
                        import sys
                        # This assumes we are in src/shared/ai_client/
                        # We might need to look up to src/
                        sys.path.append('/var/task/shared')
                        from shared.model_config_table import ModelConfigTable
                    
                    return ModelConfigTable()
                except ImportError:
                    continue
            
            logger.warning("Failed to import ModelConfigTable")
            return None
        except Exception as e:
            logger.warning(f"Error loading ModelConfigTable: {e}")
            return None

    def enforce_provider_token_limit(self, model: str, requested_tokens: int) -> int:
        """Enforce model-specific maximum token limits."""
        if not requested_tokens or requested_tokens <= 0:
            return requested_tokens

        model_limit = self.get_model_token_limit(model)

        if model_limit and requested_tokens > model_limit:
            logger.warning(f"[TOKEN_LIMIT_ENFORCED] Model {model} requested {requested_tokens} tokens, "
                         f"but model limit is {model_limit}. Capping at {model_limit} tokens.")
            return model_limit

        return requested_tokens

    def get_model_token_limit(self, model: str) -> Optional[int]:
        """Get the maximum token limit for a model."""
        if model in self._token_limits_cache:
            return self._token_limits_cache[model]

        if not self.model_config_table:
            return None

        try:
            config = self.model_config_table.get_config_for_model(model)
            if config and config.get('max_tokens', 0) > 0:
                token_limit = int(config['max_tokens'])
                self._token_limits_cache[model] = token_limit
                return token_limit
            else:
                self._token_limits_cache[model] = None
                return None
        except Exception as e:
            logger.error(f"Failed to get token limit for model {model}: {e}")
            return None

    def extract_token_usage(self, response: Dict, model: str, search_context_size: str = None) -> Dict:
        """Extract token usage information from API response."""
        # Validate inputs
        if not isinstance(response, dict):
            return self.get_empty_token_usage(model)
        
        if not isinstance(model, str) or not model.strip():
            return self.get_empty_token_usage('unknown')
        
        # Check for usage data in response
        if 'usage' not in response and 'usage_metadata' not in response and 'usageMetadata' not in response:
            logger.warning(f"No usage data in API response for model {model}")
            return self.get_empty_token_usage(model)
        
        usage = response.get('usage', {})
        if not isinstance(usage, dict):
             # Try usage_metadata for Vertex if usage is not a dict or missing
             usage = response.get('usage_metadata', {})
             if not isinstance(usage, dict):
                 return self.get_empty_token_usage(model)
        
        try:
            api_provider = determine_api_provider(model)
            
            if api_provider == 'anthropic':
                input_tokens = max(0, int(usage.get('input_tokens', 0)))
                output_tokens = max(0, int(usage.get('output_tokens', 0)))
                cache_creation_tokens = max(0, int(usage.get('cache_creation_tokens', 0)))
                cache_read_tokens = max(0, int(usage.get('cache_read_tokens', 0)))
                total_tokens = input_tokens + output_tokens + cache_creation_tokens + cache_read_tokens

                server_tool_use = usage.get('server_tool_use', {})
                web_search_requests = 0
                web_fetch_requests = 0
                if isinstance(server_tool_use, dict):
                    web_search_requests = max(0, int(server_tool_use.get('web_search_requests', 0)))
                    web_fetch_requests = max(0, int(server_tool_use.get('web_fetch_requests', 0)))

                return {
                    'api_provider': 'anthropic',
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'cache_creation_tokens': cache_creation_tokens,
                    'cache_read_tokens': cache_read_tokens,
                    'total_tokens': total_tokens,
                    'model': model,
                    'web_search_requests': web_search_requests,
                    'web_fetch_requests': web_fetch_requests
                }

            elif api_provider == 'gemini':
                # Gemini uses usageMetadata (camelCase)
                usage_data = response.get('usageMetadata', response.get('usage', {}))
                prompt_tokens = max(0, int(usage_data.get('promptTokenCount', 0)))
                candidates_tokens = max(0, int(usage_data.get('candidatesTokenCount', 0)))
                total_tokens = max(0, int(usage_data.get('totalTokenCount', prompt_tokens + candidates_tokens)))

                return {
                    'api_provider': 'gemini',
                    'model': model,
                    'input_tokens': prompt_tokens,
                    'output_tokens': candidates_tokens,
                    'total_tokens': total_tokens
                }

            elif api_provider == 'vertex':
                return self._extract_vertex_token_usage(response, model)

            elif api_provider == 'baseten':
                # Baseten uses OpenAI-compatible format (same as Vertex for DeepSeek)
                return self._extract_vertex_token_usage(response, model)

            else:
                # Perplexity
                prompt_tokens = max(0, int(usage.get('prompt_tokens', 0)))
                completion_tokens = max(0, int(usage.get('completion_tokens', 0)))
                reported_total = max(0, int(usage.get('total_tokens', 0)))

                if reported_total > 0:
                    total_tokens = reported_total
                else:
                    total_tokens = prompt_tokens + completion_tokens

                cost_data = usage.get('cost', {})
                api_provided_cost = None
                if isinstance(cost_data, dict) and cost_data:
                    try:
                        api_provided_cost = {
                            'input_cost': float(cost_data.get('input_tokens_cost', 0)),
                            'output_cost': float(cost_data.get('output_tokens_cost', 0)),
                            'request_cost': float(cost_data.get('request_cost', 0)),
                            'total_cost': float(cost_data.get('total_cost', 0)),
                            'source': 'perplexity_api'
                        }
                    except (ValueError, TypeError):
                        pass

                return {
                    'api_provider': 'perplexity',
                    'input_tokens': prompt_tokens,
                    'output_tokens': completion_tokens,
                    'cache_creation_tokens': 0,
                    'cache_read_tokens': 0,
                    'total_tokens': total_tokens,
                    'model': model,
                    'search_context_size': usage.get('search_context_size', search_context_size),
                    'api_provided_cost': api_provided_cost
                }
                
        except Exception as e:
            logger.error(f"Error parsing token data for model {model}: {e}")
            return self.get_empty_token_usage(model)

    def _extract_vertex_token_usage(self, vertex_response: Dict, model: str) -> Dict:
        """Extract token usage from Vertex AI or Baseten API response (both use OpenAI-compatible format)."""
        try:
            # Determine actual provider from model name
            api_provider = determine_api_provider(model)

            usage = vertex_response.get('usage_metadata', {}) or vertex_response.get('usage', {})

            # Support Vertex native (prompt_token_count), standard (input_tokens), and OpenAI (prompt_tokens)
            input_tokens = max(0, int(
                usage.get('prompt_token_count') or
                usage.get('input_tokens') or
                usage.get('prompt_tokens') or
                0
            ))

            # Support Vertex native (candidates_token_count), standard (output_tokens), and OpenAI (completion_tokens)
            output_tokens = max(0, int(
                usage.get('candidates_token_count') or
                usage.get('output_tokens') or
                usage.get('completion_tokens') or
                0
            ))

            total_tokens = max(0, int(
                usage.get('total_token_count') or
                usage.get('total_tokens') or
                (input_tokens + output_tokens)
            ))

            return {
                'api_provider': api_provider,  # Use detected provider (vertex or baseten)
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cache_creation_tokens': 0,
                'cache_read_tokens': 0,
                'total_tokens': total_tokens,
                'model': model
            }
        except Exception:
            api_provider = determine_api_provider(model)
            return {
                'api_provider': api_provider,  # Use detected provider
                'input_tokens': 0, 'output_tokens': 0, 'cache_creation_tokens': 0, 'cache_read_tokens': 0,
                'total_tokens': 0, 'model': model
            }

    def get_empty_token_usage(self, model: str) -> Dict:
        try:
            api_provider = determine_api_provider(model)
        except:
            api_provider = 'unknown'
        return {
            'api_provider': api_provider, 'input_tokens': 0, 'output_tokens': 0,
            'cache_creation_tokens': 0, 'cache_read_tokens': 0, 'total_tokens': 0,
            'model': model, 'error': 'failed_token_extraction'
        }

    def load_pricing_data(self) -> Dict[str, Dict[str, float]]:
        """Load pricing data from DynamoDB."""
        if self._pricing_data_cache is not None:
            return self._pricing_data_cache

        pricing_data = {}
        default_pricing = {
            'input_cost_per_million_tokens': 3.0,
            'output_cost_per_million_tokens': 15.0,
            'api_provider': 'unknown',
            'priority': 999
        }

        if self.model_config_table:
            try:
                configs = self.model_config_table.list_all_configs()
                if configs:
                    for config in configs:
                        if not config.get('enabled', False): continue
                        model_pattern = config.get('model_pattern', '').strip()
                        if not model_pattern: continue
                        
                        try:
                            input_cost = float(config.get('input_cost_per_million_tokens', 3.0))
                            output_cost = float(config.get('output_cost_per_million_tokens', 15.0))
                            priority = int(config.get('priority', 999))
                            
                            pricing_data[model_pattern] = {
                                'api_provider': config.get('api_provider', 'unknown'),
                                'input_cost_per_million_tokens': input_cost,
                                'output_cost_per_million_tokens': output_cost,
                                'notes': config.get('notes', ''),
                                'priority': priority
                            }
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"Failed to load pricing configs: {e}")

        if not pricing_data:
            pricing_data = {
                'sonar*': {'api_provider': 'perplexity', 'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0, 'priority': 100},
                'claude*': {'api_provider': 'anthropic', 'input_cost_per_million_tokens': 3.0, 'output_cost_per_million_tokens': 15.0, 'priority': 100},
                '*': default_pricing
            }
        
        if '*' not in pricing_data:
            pricing_data['*'] = default_pricing

        self._pricing_data_cache = pricing_data
        return pricing_data

    def calculate_token_costs(self, token_usage: Dict[str, Any], pricing_data: Dict[str, Dict[str, float]] = None) -> Dict[str, float]:
        """Calculate costs based on token usage and pricing data."""
        if not pricing_data:
            pricing_data = self.load_pricing_data()

        api_provider = token_usage.get('api_provider', 'unknown')
        model = token_usage.get('model', 'unknown')

        # API provided cost (Perplexity)
        api_provided_cost = token_usage.get('api_provided_cost')
        if api_provided_cost:
             return {
                'input_cost': api_provided_cost.get('input_cost', 0.0),
                'output_cost': api_provided_cost.get('output_cost', 0.0),
                'request_cost': api_provided_cost.get('request_cost', 0.0),
                'total_cost': api_provided_cost.get('total_cost', 0.0),
                'input_tokens': token_usage.get('input_tokens', 0),
                'output_tokens': token_usage.get('output_tokens', 0),
                'pricing_model': model,
                'pricing_source': 'api_provided',
                'api_provider': api_provider
            }
        
        # Web search cost (Claude)
        web_search_requests = token_usage.get('web_search_requests', 0)
        web_search_cost = web_search_requests * 0.01

        # Find pricing
        pricing = None
        pricing_source = 'none'

        # Exact match
        if model in pricing_data:
            pricing = pricing_data[model]
            pricing_source = f'exact_match_{model}'
        else:
            # Pattern match
            sorted_patterns = sorted(pricing_data.items(), key=lambda x: x[1].get('priority', 999))
            for pattern, config in sorted_patterns:
                regex_pattern = f"^{pattern.replace('*', '.*')}$"
                try:
                    if re.match(regex_pattern, model, re.IGNORECASE):
                        pricing = config
                        pricing_source = f'pattern_match_{pattern}'
                        break
                except re.error:
                    if pattern.lower() in model.lower():
                        pricing = config
                        pricing_source = f'string_match_{pattern}'
                        break
        
        if not pricing:
            pricing = pricing_data.get('*', {})
            pricing_source = 'fallback'

        input_rate = float(pricing.get('input_cost_per_million_tokens', 3.0))
        output_rate = float(pricing.get('output_cost_per_million_tokens', 15.0))
        
        input_tokens = token_usage.get('input_tokens', 0)
        output_tokens = token_usage.get('output_tokens', 0)
        
        # Use decimal for precision
        try:
            input_cost_dec = (Decimal(str(input_tokens)) / Decimal('1000000')) * Decimal(str(input_rate))
            output_cost_dec = (Decimal(str(output_tokens)) / Decimal('1000000')) * Decimal(str(output_rate))
            total_cost_dec = input_cost_dec + output_cost_dec
            
            input_cost = float(input_cost_dec.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))
            output_cost = float(output_cost_dec.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))
            total_cost = float(total_cost_dec.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))
        except:
            input_cost = (input_tokens / 1_000_000) * input_rate
            output_cost = (output_tokens / 1_000_000) * output_rate
            total_cost = input_cost + output_cost

        total_cost += web_search_cost

        return {
            'input_cost': input_cost,
            'output_cost': output_cost,
            'web_search_cost': web_search_cost,
            'total_cost': total_cost,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'pricing_model': pricing.get('model_name', model),
            'pricing_source': pricing_source,
            'api_provider': api_provider
        }

    def calculate_processing_time_estimate(self, token_usage: Dict[str, Any], processing_time: float) -> Dict[str, float]:
        """Calculate time estimates based on token usage."""
        try:
            total_tokens = token_usage.get('total_tokens', 0)
            input_tokens = token_usage.get('input_tokens', 0)
            output_tokens = token_usage.get('output_tokens', 0)
            
            if total_tokens == 0:
                return {
                    'time_per_token': 0.0,
                    'time_per_input_token': 0.0,
                    'time_per_output_token': 0.0,
                    'estimated_time_per_1k_tokens': 0.0,
                    'processing_time': processing_time,
                    'error': 'no_tokens'
                }
            
            time_per_token = processing_time / total_tokens if total_tokens > 0 else 0.0
            time_per_input_token = processing_time / input_tokens if input_tokens > 0 else 0.0
            time_per_output_token = processing_time / output_tokens if output_tokens > 0 else 0.0
            
            return {
                'time_per_token': round(time_per_token, 6),
                'time_per_input_token': round(time_per_input_token, 6),
                'time_per_output_token': round(time_per_output_token, 6),
                'estimated_time_per_1k_tokens': round(time_per_token * 1000, 3),
                'processing_time': round(processing_time, 3),
                'total_tokens': total_tokens
            }
        except Exception as e:
            logger.error(f"Error calculating time estimates: {e}")
            return {
                'time_per_token': 0.0,
                'time_per_input_token': 0.0,
                'time_per_output_token': 0.0,
                'estimated_time_per_1k_tokens': 0.0,
                'processing_time': processing_time,
                'error': str(e)
            }

    def get_enhanced_call_metrics(self, response: Dict, model: str, processing_time: float,
                                  search_context_size: str = None, batch_info: Dict = None,
                                  pre_extracted_token_usage: Dict = None, is_cached: bool = None,
                                  max_web_searches: int = None) -> Dict[str, Any]:
        """Enhanced metrics calculation."""
        if pre_extracted_token_usage:
            token_usage = pre_extracted_token_usage
        else:
            token_usage = self.extract_token_usage(response, model, search_context_size)
            
        api_provider = token_usage.get('api_provider', 'unknown')
        cache_detected = is_cached if is_cached is not None else (pre_extracted_token_usage is not None)
        
        if cache_detected:
            cost_estimated = self.calculate_token_costs(token_usage)
            cost_data = {
                'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0, 'pricing_source': 'cached_response'
            }
        else:
            cost_data = self.calculate_token_costs(token_usage)
            cost_estimated = self._calculate_cost_without_caching_benefits(token_usage, cost_data)
            
        caching_metrics = self._extract_caching_metrics(token_usage)
        timing_metrics = self._calculate_comprehensive_timing_metrics(token_usage, processing_time, caching_metrics, cache_detected)
        per_row_metrics = self._calculate_per_row_metrics(cost_data, cost_estimated, timing_metrics, batch_info)
        
        return {
            'call_info': {
                'model': model,
                'api_provider': api_provider,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'search_context_size': search_context_size,
                'max_web_searches': max_web_searches or 0
            },
            'tokens': {
                'input_tokens': token_usage.get('input_tokens', 0),
                'output_tokens': token_usage.get('output_tokens', 0),
                'total_tokens': token_usage.get('total_tokens', 0),
                'cache_creation_tokens': token_usage.get('cache_creation_tokens', 0),
                'cache_read_tokens': token_usage.get('cache_read_tokens', 0)
            },
            'costs': {
                'actual': cost_data,
                'estimated': cost_estimated,
                'cache_savings': {
                    'absolute_savings': cost_estimated.get('total_cost', 0.0) - cost_data.get('total_cost', 0.0),
                    'percentage_savings': self._calculate_percentage_savings(cost_data.get('total_cost', 0.0), cost_estimated.get('total_cost', 0.0))
                }
            },
            'timing': timing_metrics,
            'caching': caching_metrics,
            'per_row': per_row_metrics,
            'is_top_level_call': True,  # This is always a top-level call (user-facing validation/QC call)
            'provider_metrics': {
                api_provider: {
                    'calls': 1,
                    'tokens': token_usage.get('total_tokens', 0),
                    'cost_actual': cost_data.get('total_cost', 0.0),
                    'cost_estimated': cost_estimated.get('total_cost', 0.0),
                    'time_estimated': timing_metrics.get('time_estimated_seconds', processing_time),
                    'time_actual': timing_metrics.get('time_actual_seconds', processing_time),
                    'cache_hit_tokens': token_usage.get('cache_read_tokens', 0)
                }
            }
        }

    def _calculate_cost_without_caching_benefits(self, token_usage: Dict, actual_cost_data: Dict) -> Dict:
        cache_read_tokens = token_usage.get('cache_read_tokens', 0)
        if cache_read_tokens == 0:
            return actual_cost_data
        
        try:
            pricing_data = self.load_pricing_data()
            temp_usage = token_usage.copy()
            temp_usage['cache_read_tokens'] = 0
            temp_usage['input_tokens'] = token_usage.get('input_tokens', 0) + cache_read_tokens
            return self.calculate_token_costs(temp_usage, pricing_data)
        except Exception:
            return actual_cost_data

    def _extract_caching_metrics(self, token_usage: Dict) -> Dict:
        cache_read = token_usage.get('cache_read_tokens', 0)
        cache_creation = token_usage.get('cache_creation_tokens', 0)
        input_tokens = token_usage.get('input_tokens', 0)
        total_tokens = token_usage.get('total_tokens', 0)
        
        hit_rate = (cache_read / max(1, input_tokens)) * 100
        coverage = (cache_read / max(1, total_tokens)) * 100
        
        return {
            'cache_read_tokens': cache_read,
            'cache_creation_tokens': cache_creation,
            'cache_hit_rate_percent': hit_rate,
            'cache_coverage_percent': coverage,
            'has_cache_benefit': cache_read > 0
        }

    def _calculate_comprehensive_timing_metrics(self, token_usage: Dict, time_actual: float, caching_metrics: Dict, is_internal_cache: bool) -> Dict:
        total_tokens = token_usage.get('total_tokens', 0)
        tokens_per_sec = total_tokens / max(0.1, time_actual)
        
        if is_internal_cache:
            time_estimated = time_actual
            time_actual = 0.001
        elif caching_metrics['cache_read_tokens'] > 0:
            estimated_cache_time = (caching_metrics['cache_read_tokens'] / tokens_per_sec) * 8.0
            time_estimated = time_actual + estimated_cache_time
        else:
            time_estimated = time_actual
            
        return {
            'time_actual_seconds': time_actual,
            'time_estimated_seconds': time_estimated,
            'time_savings_seconds': time_estimated - time_actual,
            'tokens_per_second_actual': tokens_per_sec
        }

    def _calculate_per_row_metrics(self, cost_actual, cost_estimated, timing, batch_info) -> Dict:
        batch_size = max(1, batch_info.get('batch_size', 1) if batch_info else 1)
        return {
            'batch_size': batch_size,
            'cost_per_row_actual': cost_actual.get('total_cost', 0) / batch_size,
            'cost_per_row_estimated': cost_estimated.get('total_cost', 0) / batch_size,
            'time_per_row_actual': timing.get('time_actual_seconds', 0) / batch_size,
        }

    def _calculate_percentage_savings(self, actual: float, estimated: float) -> float:
        if estimated <= 0: return 0.0
        return ((estimated - actual) / estimated) * 100

    def aggregate_provider_metrics(self, metrics_list: List[Dict]) -> Dict:
        """Aggregate metrics from multiple API calls, including nested provider_metrics from Clone."""
        if not metrics_list:
            return {'totals': {'total_cost': 0.0}, 'providers': {}, 'by_model': {}}

        total_cost_actual = 0.0
        total_cost_estimated = 0.0
        total_top_level_calls = 0  # Track user-facing validation/QC calls (not Clone internals)
        providers = {}
        by_model = {}

        for metric in metrics_list:
            if not isinstance(metric, dict):
                continue

            # Count top-level calls (user-facing validation/QC calls)
            # Each validation call or QC call counts as 1, regardless of internal Clone calls
            if metric.get('is_top_level_call', True):  # Default to True for backward compatibility
                total_top_level_calls += 1

            # Check if this has nested provider_metrics (from Clone)
            if 'provider_metrics' in metric:
                # Aggregate nested provider metrics (for cost tracking only)
                for provider, provider_data in metric.get('provider_metrics', {}).items():
                    if provider not in providers:
                        providers[provider] = {
                            'cost_actual': 0.0,
                            'cost_estimated': 0.0,
                            'calls': 0,  # Internal call count (for cost breakdown)
                            'tokens': 0,
                            'cache_efficiency_percent': 0.0
                        }
                    providers[provider]['cost_actual'] += float(provider_data.get('cost_actual', 0.0))
                    providers[provider]['cost_estimated'] += float(provider_data.get('cost_estimated', 0.0))
                    providers[provider]['calls'] += int(provider_data.get('calls', 0))
                    providers[provider]['tokens'] += int(provider_data.get('tokens', 0))
                total_cost_actual += sum(float(p.get('cost_actual', 0.0)) for p in metric.get('provider_metrics', {}).values())
                total_cost_estimated += sum(float(p.get('cost_estimated', 0.0)) for p in metric.get('provider_metrics', {}).values())
            else:
                # Single provider call - extract from costs
                costs = metric.get('costs', {})
                actual = costs.get('actual', {})
                estimated = costs.get('estimated', {})
                cost_actual = float(actual.get('total_cost', 0.0))
                cost_estimated = float(estimated.get('total_cost', 0.0))
                total_cost_actual += cost_actual
                total_cost_estimated += cost_estimated

                # Aggregate by single provider
                provider = metric.get('api_provider', 'unknown')
                if provider not in providers:
                    providers[provider] = {
                        'cost_actual': 0.0,
                        'cost_estimated': 0.0,
                        'calls': 0,
                        'tokens': 0,
                        'cache_efficiency_percent': 0.0
                    }
                providers[provider]['cost_actual'] += cost_actual
                providers[provider]['cost_estimated'] += cost_estimated
                providers[provider]['calls'] += 1
                providers[provider]['tokens'] += int(metric.get('token_usage', {}).get('total_tokens', 0))

            # Aggregate by model (top-level model name)
            model = metric.get('model', 'unknown')
            if model not in by_model:
                by_model[model] = {'cost': 0.0, 'calls': 0}
            metric_cost = float(metric.get('costs', {}).get('actual', {}).get('total_cost', 0.0))
            if 'provider_metrics' in metric:
                metric_cost = sum(float(p.get('cost_actual', 0.0)) for p in metric.get('provider_metrics', {}).values())
            by_model[model]['cost'] += metric_cost
            by_model[model]['calls'] += 1

        # Calculate cache efficiency for each provider
        for provider, data in providers.items():
            if data['cost_estimated'] > 0:
                savings = data['cost_estimated'] - data['cost_actual']
                data['cache_efficiency_percent'] = (savings / data['cost_estimated']) * 100

        return {
            'totals': {
                'total_cost_actual': total_cost_actual,
                'total_cost_estimated': total_cost_estimated,
                'total_calls': len(metrics_list),  # Legacy: total enhanced_data items processed
                'total_top_level_calls': total_top_level_calls  # NEW: User-facing validation/QC calls only
            },
            'providers': providers,
            'by_model': by_model
        }
