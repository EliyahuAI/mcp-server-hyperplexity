#!/usr/bin/env python3
"""
Example usage of the enhanced provider-specific metrics system.
This shows how background handlers and other components should use the new
comprehensive tracking system implemented in ai_api_client.py.
"""

from src.shared.ai_api_client import AIAPIClient
from src.shared.dynamodb_schemas import update_run_status
import logging

logger = logging.getLogger(__name__)

def example_usage_in_validation_handler():
    """
    Example of how to use enhanced metrics in a validation handler.
    This replaces the old get_unified_cost_and_time_data() calls.
    """
    
    # Initialize the AI API client
    ai_client = AIAPIClient()
    
    # Track metrics for each API call
    call_metrics_list = []
    
    # Example: Process multiple API responses in a batch
    for i, (response, model, processing_time) in enumerate(api_responses_batch):
        # Get enhanced metrics for this specific call
        batch_info = {'batch_size': len(current_batch), 'rows_processed': len(current_batch)}
        
        enhanced_metrics = ai_client.get_enhanced_call_metrics(
            response=response,
            model=model,
            processing_time=processing_time,
            search_context_size='medium',  # For Perplexity calls
            batch_info=batch_info
        )
        
        call_metrics_list.append(enhanced_metrics)
        
        # Log individual call details
        call_info = enhanced_metrics['call_info']
        costs = enhanced_metrics['costs']
        timing = enhanced_metrics['timing']
        caching = enhanced_metrics['caching']
        per_row = enhanced_metrics['per_row']
        
        logger.info(f"[CALL_METRICS] Call {i+1}: {call_info['api_provider']} {call_info['model']}")
        logger.info(f"  Cost: ${costs['actual']['total_cost']:.6f} (actual) / ${costs['without_cache']['total_cost']:.6f} (no cache)")
        logger.info(f"  Cache savings: ${costs['cache_savings']['absolute_savings']:.6f} ({costs['cache_savings']['percentage_savings']:.1f}%)")
        logger.info(f"  Time: {timing['actual_time']:.3f}s (actual) / {timing['estimated_time_without_cache']:.3f}s (no cache)")
        logger.info(f"  Per row: ${per_row['cost_per_row_actual']:.6f}/row, {per_row['time_per_row_actual']:.3f}s/row")
        logger.info(f"  Cache efficiency: {caching['cache_hit_rate_percent']:.1f}% hit rate")
    
    # Aggregate all metrics by provider
    aggregated_metrics = AIAPIClient.aggregate_provider_metrics(call_metrics_list)
    
    logger.info("[AGGREGATED_METRICS] Provider breakdown:")
    for provider, metrics in aggregated_metrics['providers'].items():
        logger.info(f"  {provider}:")
        logger.info(f"    Calls: {metrics['calls']}, Tokens: {metrics['tokens']:,}")
        logger.info(f"    Cost: ${metrics['cost_actual']:.6f} (actual) / ${metrics['cost_without_cache']:.6f} (no cache)")
        logger.info(f"    Average: ${metrics['average_cost_per_call']:.6f}/call, {metrics['average_time_per_call']:.3f}s/call")
        logger.info(f"    Cache efficiency: {metrics['cache_efficiency_percent']:.1f}%")
    
    # Calculate full validation estimates
    total_rows_in_table = 10000
    preview_rows_processed = 100
    
    full_validation_estimates = AIAPIClient.calculate_full_validation_estimates(
        aggregated_metrics=aggregated_metrics,
        total_rows_in_table=total_rows_in_table,
        preview_rows_processed=preview_rows_processed
    )
    
    logger.info("[FULL_VALIDATION_ESTIMATES]")
    total_estimates = full_validation_estimates['total_estimates']
    logger.info(f"  Estimated cost: ${total_estimates['estimated_total_cost_actual']:.2f} (with cache) / ${total_estimates['estimated_total_cost_without_cache']:.2f} (no cache)")
    logger.info(f"  Estimated time: {total_estimates['estimated_total_processing_time']:.1f} seconds")
    logger.info(f"  Estimated calls: {total_estimates['estimated_total_calls']:,}")
    logger.info(f"  Cache efficiency: {total_estimates['estimated_cache_efficiency_percent']:.1f}%")
    
    # Log batch estimates for different batch sizes
    for batch_config, batch_estimates in full_validation_estimates['batch_estimates'].items():
        logger.info(f"  {batch_config}: {batch_estimates['estimated_batches']} batches, {batch_estimates['estimated_time_per_batch']:.1f}s/batch")
    
    # Update DynamoDB with comprehensive metrics
    try:
        # Extract aggregated provider metrics for DynamoDB storage
        provider_metrics_for_db = {}
        for provider, metrics in aggregated_metrics['providers'].items():
            provider_metrics_for_db[provider] = {
                'calls': metrics['calls'],
                'tokens': metrics['tokens'],
                'cost_actual': metrics['cost_actual'],
                'cost_without_cache': metrics['cost_without_cache'],
                'processing_time': metrics['processing_time'],
                'cache_hit_tokens': metrics['cache_hit_tokens'],
                'cost_per_row_actual': metrics['cost_actual'] / preview_rows_processed if preview_rows_processed > 0 else 0,
                'cost_per_row_without_cache': metrics['cost_without_cache'] / preview_rows_processed if preview_rows_processed > 0 else 0,
                'time_per_row_actual': metrics['processing_time'] / preview_rows_processed if preview_rows_processed > 0 else 0,
                'cache_efficiency_percent': metrics['cache_efficiency_percent']
            }
        
        # Update run status with enhanced metrics
        update_run_status(
            session_id=session_id,
            run_key=run_key,
            status='COMPLETED',
            run_type='Preview',  # or 'Validation'
            processed_rows=preview_rows_processed,
            total_rows=total_rows_in_table,
            eliyahu_cost=aggregated_metrics['totals']['total_cost_actual'],
            quoted_validation_cost=0.0 if is_preview else calculated_user_charge,
            estimated_validation_eliyahu_cost=total_estimates['estimated_total_cost_without_cache'],
            time_per_row_seconds=aggregated_metrics['totals']['total_processing_time'] / preview_rows_processed,
            provider_metrics=provider_metrics_for_db  # NEW: Enhanced provider-specific metrics
        )
        
        logger.info(f"[DATABASE_UPDATE] Successfully updated DynamoDB with enhanced provider metrics")
        
    except Exception as e:
        logger.error(f"[DATABASE_UPDATE] Failed to update DynamoDB with enhanced metrics: {e}")
        import traceback
        logger.error(f"[DATABASE_UPDATE] Traceback: {traceback.format_exc()}")

def example_metrics_analysis():
    """
    Example of how to analyze stored provider metrics for optimization.
    """
    
    # This would be called from a separate analysis script or dashboard
    logger.info("[METRICS_ANALYSIS] Starting provider efficiency analysis...")
    
    # Query DynamoDB for recent runs with provider metrics
    # (Implementation would depend on your specific querying needs)
    
    sample_provider_metrics = {
        'anthropic': {
            'calls': 45,
            'tokens': 125000,
            'cost_actual': 0.75,
            'cost_without_cache': 1.20,
            'cache_efficiency_percent': 37.5
        },
        'perplexity': {
            'calls': 15,
            'tokens': 45000,
            'cost_actual': 0.15,
            'cost_without_cache': 0.18,
            'cache_efficiency_percent': 16.7
        }
    }
    
    # Analyze cache efficiency by provider
    logger.info("[ANALYSIS] Cache efficiency comparison:")
    for provider, metrics in sample_provider_metrics.items():
        efficiency = metrics['cache_efficiency_percent']
        cost_per_token = metrics['cost_actual'] / metrics['tokens'] * 1000000  # Per million tokens
        
        logger.info(f"  {provider}:")
        logger.info(f"    Cache efficiency: {efficiency:.1f}%")
        logger.info(f"    Cost per million tokens: ${cost_per_token:.2f}")
        logger.info(f"    Savings from cache: ${metrics['cost_without_cache'] - metrics['cost_actual']:.6f}")
    
    # Identify optimization opportunities
    total_savings = sum(m['cost_without_cache'] - m['cost_actual'] for m in sample_provider_metrics.values())
    total_cost = sum(m['cost_actual'] for m in sample_provider_metrics.values())
    
    logger.info(f"[OPTIMIZATION] Total cost savings from caching: ${total_savings:.6f}")
    logger.info(f"[OPTIMIZATION] Overall efficiency: {(total_savings / (total_cost + total_savings)) * 100:.1f}%")

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    # Simulate some API responses for demonstration
    api_responses_batch = [
        # (response_dict, model_name, processing_time_seconds)
        ({'usage': {'input_tokens': 1000, 'output_tokens': 500, 'cache_read_tokens': 200}}, 'claude-sonnet-4-0', 2.5),
        ({'usage': {'prompt_tokens': 800, 'completion_tokens': 300}}, 'sonar-pro', 1.8),
    ]
    
    session_id = "test_session_123"
    run_key = "run_456"
    is_preview = True
    current_batch = ['row1', 'row2', 'row3']  # Sample batch
    
    example_usage_in_validation_handler()
    example_metrics_analysis()