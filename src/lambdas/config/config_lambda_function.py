#!/usr/bin/env python3
"""
Independent Configuration Lambda
Handles AI-powered configuration generation separately from validation
"""

import json
import logging
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from ai_api_client import ai_client
from shared_table_parser import s3_table_parser  
from config_validator import validate_config_complete

# Import WebSocket client for progress updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger.warning("WebSocket client not available")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_config_settings():
    """Load configuration settings from JSON file"""
    import os
    settings_path = os.path.join(os.path.dirname(__file__), 'config_settings.json')
    try:
        with open(settings_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback to defaults
        return {
            'max_tokens': 16000,
            'model': ['claude-opus-4-1', 'claude-4-opus-20240229', 'claude-sonnet-4-0']
        }

def send_websocket_progress(session_id: str, message: str, progress: int = None):
    """Send progress update via WebSocket"""
    if websocket_client and session_id:
        try:
            update_data = {
                'type': 'config_progress_update',
                'message': message,
                'session_id': session_id,
                'timestamp': datetime.now().isoformat()
            }
            if progress is not None:
                update_data['progress'] = progress
            
            websocket_client.send_to_session(session_id, update_data)
            logger.info(f"Sent WebSocket config progress: {message} to session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to send WebSocket config progress: {e}")

# NOTE: Cost calculation functions moved to centralized ai_api_client.py
# Use ai_client.calculate_token_costs() for cost calculations
# Use ai_client.load_pricing_data() for pricing data loading

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for configuration generation requests."""
    try:
        # Extract request parameters
        table_analysis = event.get('table_analysis')
        existing_config = event.get('existing_config')  # Optional
        instructions = event.get('instructions', 'Generate an optimal configuration for this data validation scenario')
        session_id = event.get('session_id', 'unknown')
        latest_validation_results = event.get('latest_validation_results')  # Optional - for refinement context
        
        # Send initial progress update
        if session_id:
            send_websocket_progress(session_id, "Starting AI configuration generation...", 10)
        
        # Table can be provided in multiple formats
        excel_s3_key = event.get('excel_s3_key')
        csv_s3_key = event.get('csv_s3_key')
        table_data = event.get('table_data')  # Direct table data
        
        # Need either table_analysis or a way to generate it
        if not table_analysis and not any([excel_s3_key, csv_s3_key, table_data]):
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'success': False,
                    'error': 'Missing table_analysis or table data (excel_s3_key, csv_s3_key, or table_data)'
                })
            }
        
        # Generate table analysis if not provided
        if not table_analysis:
            logger.info("Generating table analysis from provided data")
            if session_id:
                send_websocket_progress(session_id, "Analyzing table structure...", 25)
            try:
                bucket = os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')
                
                if excel_s3_key:
                    logger.info(f"Analyzing Excel from S3: {excel_s3_key}")
                    table_analysis = s3_table_parser.analyze_table_structure(bucket, excel_s3_key)
                elif csv_s3_key:
                    logger.info(f"Analyzing CSV from S3: {csv_s3_key}")
                    table_analysis = s3_table_parser.analyze_table_structure(bucket, csv_s3_key)
                elif table_data:
                    logger.info("Analyzing direct table data")
                    # Process direct table data (would need implementation in table parser)
                    raise NotImplementedError("Direct table data parsing not yet implemented")
                    
            except Exception as e:
                logger.error(f"Failed to analyze table: {str(e)}")
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'success': False,
                        'error': f'Table analysis failed: {str(e)}'
                    })
                }
        
        logger.info(f"Config generation for session: {session_id}")
        
        # Send progress update before AI generation
        if session_id:
            send_websocket_progress(session_id, "Requesting AI configuration...", 50)
        
        # Get conversation history from payload if provided
        conversation_history = event.get('conversation_history', [])

        # Process the config generation request (single unified mode)
        result = asyncio.run(generate_config_unified(
            table_analysis, existing_config, instructions, session_id, latest_validation_results, conversation_history
        ))
        
        # Send completion progress update
        if session_id:
            send_websocket_progress(session_id, "Configuration generated successfully!", 100)
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"Config lambda error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }

async def generate_config_unified(table_analysis: Dict, existing_config: Dict = None,
                                 instructions: str = '', session_id: str = 'unknown',
                                 latest_validation_results: Dict = None, conversation_history: list = None) -> Dict:
    """Unified config generation - always returns both updated config and clarifying questions."""
    logger.info(f"Config generation started for session {session_id}")
    send_websocket_progress(session_id, "Generating new configuration... (~70s)", 55)
    
    # Debug logging for existing config and conversation history
    if existing_config:
        generation_metadata = existing_config.get('generation_metadata', {})
        current_version = generation_metadata.get('version', 1)
        logger.info(f"Existing config found - Version: {current_version}")
    else:
        logger.info("No existing config provided - creating new configuration")

    # Use conversation history from interface lambda (includes user message if refinement)
    if conversation_history:
        logger.info(f"Conversation history provided - {len(conversation_history)} entries")
        for i, entry in enumerate(conversation_history[-3:], 1):
            entry_type = entry.get('entry_type', entry.get('action', 'unknown'))
            if entry_type == 'user_input':
                logger.info(f"  Entry {len(conversation_history)-3+i}: USER - {entry.get('user_instructions', 'No instructions')[:50]}...")
            else:
                logger.info(f"  Entry {len(conversation_history)-3+i}: {entry_type} - {entry.get('instructions', 'No instructions')[:50]}...")
    else:
        logger.info("No conversation history provided")
    
    try:
        # Note: User message logging is handled by the interface lambda before calling us
        
        # Build the unified generation prompt
        prompt = build_unified_generation_prompt(table_analysis, existing_config, instructions, latest_validation_results, conversation_history)
        
        # Call Claude using shared client with unified schema
        schema = get_unified_generation_schema()
        
        config_settings = load_config_settings()
        
        # Determine debug name based on whether this is generation or refinement
        is_refinement = existing_config is not None and existing_config.get('config_change_log', [])
        debug_name = "config_refinement" if is_refinement else "config_generation"
        
        result = await ai_client.call_structured_api(
            prompt=prompt,
            schema=schema,
            model=config_settings.get('model', 'claude-opus-4-1'),
            tool_name="generate_config_and_questions",
            max_tokens=config_settings.get('max_tokens', 16000),
            max_web_searches=0,
            debug_name=debug_name
            # Removed context parameter - it was incorrectly using session_id
            # Context should be for search_context_size in validation calls
        )
        
        # Extract enhanced data from AI client response (individual call enhanced metrics)
        enhanced_data = result.get('enhanced_data', {})
        token_usage = result.get('token_usage', {})
        
        # Extract timing data from enhanced metrics (individual call structure)
        timing_data = enhanced_data.get('timing', {})
        estimated_processing_time = timing_data.get('time_estimated_seconds', result.get('processing_time', 0))
        actual_processing_time = timing_data.get('time_actual_seconds', result.get('processing_time', 0))
        
        model_used = result.get('model_used', config_settings.get('model', 'claude-opus-4-1'))
        is_cached = result.get('is_cached', False)
        
        # Extract cost from enhanced data (individual call structure)
        costs_data = enhanced_data.get('costs', {})
        eliyahu_cost = costs_data.get('actual', {}).get('total_cost', 0.0)
        estimated_cost = costs_data.get('estimated', {}).get('total_cost', 0.0)
        
        if eliyahu_cost == 0.0 and not enhanced_data:
            # Fallback to legacy cost calculation if enhanced data not available
            cost_data = ai_client.calculate_token_costs(token_usage)
            eliyahu_cost = cost_data.get('total_cost', 0.0)
            estimated_cost = eliyahu_cost
            logger.warning("[CONFIG_PRICING] Enhanced data not available, using legacy cost calculation")
        else:
            logger.info(f"[CONFIG_PRICING] Using enhanced cost data: actual=${eliyahu_cost:.6f}, estimated=${estimated_cost:.6f}")
        
        # Add total_cost to token_usage for backward compatibility with background handler
        if not token_usage.get('total_cost'):
            token_usage['total_cost'] = eliyahu_cost
            logger.info(f"[CONFIG_COST_COMPATIBILITY] Added total_cost=${eliyahu_cost:.6f} to token_usage for background handler compatibility")
        
        # Extract response data
        response_data = ai_client.extract_structured_response(result['response'], "generate_config_and_questions")
        
        # Get the updated config and add conversation tracking
        updated_config = response_data.get('updated_config')
        clarifying_questions = response_data.get('clarifying_questions', '')
        clarification_urgency = response_data.get('clarification_urgency', 0.0)
        reasoning = response_data.get('reasoning', '')
        ai_summary = response_data.get('ai_summary', '')
        technical_ai_summary = response_data.get('technical_ai_summary', '')
        
        # Validate the AI-generated config before proceeding
        if updated_config:
            is_valid, errors, warnings = validate_config_complete(updated_config, table_analysis)
            
            if not is_valid:
                logger.warning(f"AI generated invalid config, attempting retry with validation errors")
                # Retry with validation errors as refinement instructions
                error_instructions = f"The previous configuration had validation errors. Please fix these issues:\n\nErrors:\n" + "\n".join(f"- {error}" for error in errors)
                if warnings:
                    error_instructions += f"\n\nWarnings:\n" + "\n".join(f"- {warning}" for warning in warnings)
                
                # Recursive call to fix the config
                retry_result = await generate_config_unified(
                    table_analysis=table_analysis,
                    existing_config=updated_config,  # Use the invalid config as base
                    instructions=error_instructions,
                    session_id=f"{session_id}_retry",
                    latest_validation_results=latest_validation_results
                )
                
                if retry_result.get('success') and retry_result.get('updated_config'):
                    logger.info("Successfully fixed config validation errors on retry")
                    updated_config = retry_result['updated_config']
                    # Merge retry information
                    reasoning += f"\n\nRetry: {retry_result.get('reasoning', '')}"
                    ai_summary += f"\n\nRetry Summary: {retry_result.get('ai_summary', '')}"
                    technical_ai_summary += f"\n\nRetry Technical Summary: {retry_result.get('technical_ai_summary', '')}"
                else:
                    logger.error("Failed to fix config validation errors on retry")
        
        # Add conversation entry to config change log first
        if updated_config:
            # Get the version info for the filename (before saving)
            current_version = 1
            if existing_config and 'generation_metadata' in existing_config:
                current_version = existing_config['generation_metadata'].get('version', 1) + 1
            
            # Create preliminary filename for conversation entry
            base_filename = "unknown_table"
            if table_analysis and 'basic_info' in table_analysis:
                import re
                original_filename = table_analysis['basic_info'].get('filename', 'unknown_table')
                base_filename = re.sub(r'\.(xlsx?|csv)$', '', original_filename, flags=re.IGNORECASE)
                base_filename = re.sub(r'_config(_V\d+)?$', '', base_filename, flags=re.IGNORECASE)
            config_filename = f"{base_filename}_config_V{current_version:02d}.json"
            
            # Add conversation entry with metadata
            updated_config = add_conversation_entry(
                updated_config, existing_config, instructions,
                clarifying_questions, clarification_urgency, reasoning, ai_summary, technical_ai_summary, session_id,
                conversation_history, config_filename
            )
        
        # Note: S3 saving is handled by the interface lambda after receiving the config
        # Config lambda focuses on generation, interface lambda handles storage
        config_s3_key = None
        config_download_url = None
        logger.info("Config generation complete - S3 storage handled by interface lambda")
        
        # Extract version for easy access
        config_version = updated_config.get('generation_metadata', {}).get('version', 1) if updated_config else 1

        # Create clean config without metadata for interface lambda (interface lambda adds its own metadata)
        clean_config = updated_config.copy() if updated_config else {}
        # Remove metadata that should be handled by interface lambda
        metadata_keys = ['generation_metadata', 'storage_metadata']
        for key in metadata_keys:
            if key in clean_config:
                del clean_config[key]

        return {
            'success': True,
            'updated_config': clean_config,
            'clarifying_questions': clarifying_questions,
            'clarification_urgency': clarification_urgency,
            'reasoning': reasoning,
            'ai_summary': ai_summary,
            'technical_ai_summary': technical_ai_summary,
            'config_s3_key': config_s3_key,
            'config_download_url': config_download_url,
            'config_filename': config_filename,
            'config_version': config_version,  # Add explicit version field
            'session_id': session_id,
            # Add cost and usage tracking data (enhanced metrics)
            'eliyahu_cost': eliyahu_cost,
            'estimated_cost': estimated_cost,
            'enhanced_data': enhanced_data,
            'token_usage': token_usage,
            'estimated_processing_time': estimated_processing_time,
            'actual_processing_time': actual_processing_time,
            'processing_time': actual_processing_time,  # Legacy field for compatibility
            'model_used': model_used,
            'is_cached': is_cached,
            # Add cost_info structure for background handler compatibility
            'cost_info': {
                'total_cost': eliyahu_cost,
                'estimated_cost': estimated_cost,
                'total_tokens': token_usage.get('total_tokens', 0),
                'anthropic_tokens': token_usage.get('total_tokens', 0) if token_usage.get('api_provider') == 'anthropic' else 0,
                'anthropic_cost': eliyahu_cost if token_usage.get('api_provider') == 'anthropic' else 0.0,
                'anthropic_calls': 1 if token_usage.get('api_provider') == 'anthropic' else 0,
                'perplexity_tokens': token_usage.get('total_tokens', 0) if token_usage.get('api_provider') == 'perplexity' else 0,
                'perplexity_cost': eliyahu_cost if token_usage.get('api_provider') == 'perplexity' else 0.0,
                'perplexity_calls': 1 if token_usage.get('api_provider') == 'perplexity' else 0
            }
        }
        
    except Exception as e:
        logger.error(f"Unified config generation failed: {str(e)}")
        return {
            'success': False,
            'error': f'Config generation failed: {str(e)}',
            'session_id': session_id
        }

def build_unified_generation_prompt(table_analysis: Dict, existing_config: Dict = None,
                                  instructions: str = '', latest_validation_results: Dict = None,
                                  conversation_history: list = None) -> str:
    """Build unified prompt for config generation that always returns both config and questions."""
    
    basic_info = table_analysis.get('basic_info', {})
    column_analysis = table_analysis.get('column_analysis', {})
    domain_info = table_analysis.get('domain_info', {})
    formula_data = table_analysis.get('formula_data', [])
    has_formulas = table_analysis.get('metadata', {}).get('has_formulas', False)
    
    # Determine if this is a new config or refinement
    is_new_config = existing_config is None or not existing_config.get('config_change_log', [])
    
    # Load the appropriate prompt template
    import os
    current_dir = os.path.dirname(__file__)
    
    if is_new_config:
        prompt_file = os.path.join(current_dir, 'prompts', 'create_new_config_prompt.md')
    else:
        prompt_file = os.path.join(current_dir, 'prompts', 'refine_existing_config_prompt.md')
    
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
        
        # Process includes for common guidance
        if '{{INCLUDE:common_config_guidance.md}}' in prompt_template:
            common_guidance_file = os.path.join(current_dir, 'prompts', 'common_config_guidance.md')
            try:
                with open(common_guidance_file, 'r', encoding='utf-8') as f:
                    common_guidance = f.read()
                prompt_template = prompt_template.replace('{{INCLUDE:common_config_guidance.md}}', common_guidance)
            except Exception as e:
                logger.warning(f"Could not load common guidance {common_guidance_file}: {e}")
                prompt_template = prompt_template.replace('{{INCLUDE:common_config_guidance.md}}', "")
        
    except Exception as e:
        logger.warning(f"Could not load prompt template {prompt_file}: {e}")
        # Fallback to basic prompt
        prompt_template = "You are an expert in data validation and configuration generation."
    
    # Process formula analysis template if formulas are present
    formula_analysis_content = ""
    calculated_columns = set()
    referenced_columns = set()

    if has_formulas and formula_data:
        formula_analysis_content = process_formula_analysis_template(
            formula_data, table_analysis, current_dir
        )

        # Still need these sets for column-specific context
        for row_idx, row_formulas in enumerate(formula_data):
            for col_name, formula_info in row_formulas.items():
                calculated_columns.add(col_name)
                for ref in formula_info['referenced_columns']:
                    referenced_columns.add(ref['column_name'])

    # Build base prompt with field replacements
    table_analysis_content = build_table_analysis_section(
        basic_info, column_analysis, domain_info, calculated_columns, referenced_columns, has_formulas
    )

    base_prompt = (prompt_template
                   .replace('{{TABLE_ANALYSIS}}', table_analysis_content)
                   .replace('{{FORMULA_ANALYSIS}}', formula_analysis_content))

    if existing_config:
        # Use conversation history from interface lambda
        current_version = existing_config.get('generation_metadata', {}).get('version', 1)
        next_version = current_version + 1

        # Always add the existing configuration section header
        base_prompt += f"""

# EXISTING CONFIGURATION
"""

        if conversation_history:
            base_prompt += f"""
This configuration has been iteratively improved through {len(conversation_history)} previous interactions.

## Recent Conversation History
"""
            # Include last 3 interactions for context
            for entry in conversation_history[-3:]:
                entry_type = entry.get('entry_type', entry.get('action', 'unknown'))
                if entry_type == 'user_input':
                    base_prompt += f"""
- **{entry.get('timestamp', 'Unknown')}**: USER MESSAGE: "{entry.get('user_instructions', 'No instructions')}"
"""
                else:
                    base_prompt += f"""
- **{entry.get('timestamp', 'Unknown')}**: "{entry.get('instructions', 'No instructions')}"
  - Response: {entry.get('clarifying_questions', 'No questions')[:100]}...
"""
        else:
            base_prompt += f"""
This is the current configuration that needs to be refined.
"""

        base_prompt += f"""

## Current Configuration Summary
- **Search Groups**: {len(existing_config.get('search_groups', []))}
- **Validation Targets**: {len(existing_config.get('validation_targets', []))}
- **General Notes**: {existing_config.get('general_notes', 'None')[:200]}...

## Complete Current Configuration

Here is the full current configuration that you need to refine:

```json
{json.dumps(existing_config, indent=2)}
```

**IMPORTANT**: You MUST work with this existing configuration structure. Make only the specific changes requested by the user while preserving the overall structure and any settings that are working well."""

        # Add validation results context if available
        logger.info(f"VALIDATION_CONTEXT_DEBUG: latest_validation_results type: {type(latest_validation_results)}, is_none: {latest_validation_results is None}")

        if latest_validation_results and isinstance(latest_validation_results, dict):
            logger.info(f"VALIDATION_CONTEXT_DEBUG: latest_validation_results keys: {list(latest_validation_results.keys())}")

            validation_summary = latest_validation_results.get('validation_summary', {})
            model_data = latest_validation_results.get('model_data', {})
            qc_metrics = latest_validation_results.get('qc_metrics', {})

            logger.info(f"VALIDATION_CONTEXT_DEBUG: Raw model_data type: {type(model_data)}, empty: {not bool(model_data)}")
            logger.info(f"VALIDATION_CONTEXT_DEBUG: Raw qc_metrics type: {type(qc_metrics)}, empty: {not bool(qc_metrics)}")

            # Convert DynamoDB format to plain values if needed
            if model_data:
                logger.info(f"VALIDATION_CONTEXT_DEBUG: Sample model_data keys: {list(model_data.keys())[:3] if isinstance(model_data, dict) else 'Not a dict'}")
                model_data = convert_dynamodb_to_plain(model_data)
                logger.info(f"VALIDATION_CONTEXT_DEBUG: Converted model_data keys: {list(model_data.keys())[:3] if isinstance(model_data, dict) else 'Not a dict'}")

            if qc_metrics:
                logger.info(f"VALIDATION_CONTEXT_DEBUG: Sample qc_metrics keys: {list(qc_metrics.keys())[:3] if isinstance(qc_metrics, dict) else 'Not a dict'}")
                qc_metrics = convert_dynamodb_to_plain(qc_metrics)
                logger.info(f"VALIDATION_CONTEXT_DEBUG: Converted qc_metrics keys: {list(qc_metrics.keys())[:3] if isinstance(qc_metrics, dict) else 'Not a dict'}")

            if validation_summary or model_data or qc_metrics:
                base_prompt += f"""

# VALIDATION RESULTS CONTEXT

The following validation results are available from the most recent run using this configuration:

## Validation Summary
- **Total Columns Validated**: {validation_summary.get('total_columns', 'Unknown')}
- **Overall Status**: {validation_summary.get('overall_status', 'Unknown')}
- **Issues Found**: {validation_summary.get('total_issues', 'Unknown')}"""

                # Add model performance data
                if model_data:
                    base_prompt += f"""

## Search Group Performance Analysis

**Model Usage and Performance by Search Group:**
"""
                    for group_key, group_data in model_data.items():
                        if isinstance(group_data, dict) and 'search_group_config' in group_data:
                            group_config = group_data['search_group_config']
                            group_id = group_config.get('group_id', 'Unknown')
                            group_name = group_config.get('group_name', 'Unknown')
                            model_used = group_data.get('mode_model_used', 'Unknown')
                            column_count = group_data.get('column_count', 0)
                            avg_cost = group_data.get('average_estimated_cost', 0)
                            avg_time = group_data.get('average_estimated_time', 0)
                            search_context = group_data.get('search_context_level', 'Unknown')
                            max_web_searches = group_data.get('max_web_searches')
                            columns = group_data.get('column_names', [])

                            base_prompt += f"""
**Search Group {group_id}: {group_name}**
- Model Used: {model_used}
- Columns ({column_count}): {', '.join(columns)}
- Avg Cost: ${avg_cost:.4f} per row
- Avg Time: {avg_time:.1f}s per row
- Search Context: {search_context}
- Web Searches: {max_web_searches if max_web_searches is not None else 'N/A (Perplexity)'}"""

                # Add QC metrics and column-specific fail rates
                if qc_metrics and isinstance(qc_metrics, dict):
                    qc_enabled = qc_metrics.get('enabled', False)
                    qc_cost = qc_metrics.get('cost_per_row_actual', 0)
                    confidence_lowered = qc_metrics.get('confidence_lowered_count', 0)

                    base_prompt += f"""

## Quality Control (QC) Performance Analysis

**QC Overview:**
- QC Enabled: {qc_enabled}
- QC Cost per Row: ${qc_cost:.4f}
- Confidence Adjustments: {confidence_lowered}

**Column-Specific QC Analysis:**"""

                    qc_by_column = qc_metrics.get('qc_by_column', {})
                    problem_columns = []
                    good_columns = []

                    for col_name, col_metrics in qc_by_column.items():
                        if isinstance(col_metrics, dict):
                            total_reviewed = col_metrics.get('total_reviewed', 0)
                            total_modified = col_metrics.get('total_modified', 0)
                            value_fail_rate = float(col_metrics.get('value_fail_rate', 0))
                            confidence_fail_rate = float(col_metrics.get('confidence_fail_rate', 0))
                            overall_fail_rate = float(col_metrics.get('overall_fail_rate', 0))

                            # Identify problem columns (high fail rates)
                            if overall_fail_rate > 0.2 or value_fail_rate > 0.3:  # 20% overall or 30% value fail rate
                                problem_columns.append({
                                    'name': col_name,
                                    'overall_fail_rate': overall_fail_rate,
                                    'value_fail_rate': value_fail_rate,
                                    'confidence_fail_rate': confidence_fail_rate,
                                    'reviewed': total_reviewed,
                                    'modified': total_modified
                                })
                            elif total_reviewed > 0:
                                good_columns.append({
                                    'name': col_name,
                                    'overall_fail_rate': overall_fail_rate,
                                    'reviewed': total_reviewed
                                })

                    # Show problem columns first
                    if problem_columns:
                        base_prompt += f"""

**❌ PROBLEM COLUMNS - REQUIRE ATTENTION:**
These columns have high QC fail rates and should be improved:
"""
                        for col in problem_columns:
                            base_prompt += f"""
- **{col['name']}**: Overall fail: {col['overall_fail_rate']:.1%}, Value fail: {col['value_fail_rate']:.1%}, Confidence fail: {col['confidence_fail_rate']:.1%} ({col['modified']}/{col['reviewed']} modified)
  → Consider: Different model, better search context, improved examples, or format clarification"""

                    # Show well-performing columns
                    if good_columns:
                        base_prompt += f"""

**✅ WELL-PERFORMING COLUMNS:**"""
                        for col in good_columns:
                            base_prompt += f"""
- **{col['name']}**: {col['overall_fail_rate']:.1%} fail rate ({col['reviewed']} reviewed) - Good performance"""

                base_prompt += f"""

**REFINEMENT GUIDANCE:**
- Focus improvements on problem columns with high fail rates
- Consider upgrading models for failing columns (sonar → sonar-pro → claude-sonnet-4)
- Increase web searches for claude models if accuracy is critical
- Review examples and format specifications for failing columns
- Consider moving problem columns to different search groups with related information"""

    # Add user instructions if provided
    if instructions:
        base_prompt += f"""

# USER REFINEMENT REQUEST

**User Instructions**: {instructions}

**Your Task**: Analyze the user's request and make ONLY the specific changes needed to address their concerns. Preserve everything else that is working well."""

    return base_prompt

def process_formula_analysis_template(formula_data, table_analysis, current_dir):
    """Process the formula analysis template with field replacements"""
    try:
        formula_template_path = os.path.join(current_dir, 'prompts', 'formula_analysis.md')
        with open(formula_template_path, 'r', encoding='utf-8') as f:
            formula_template = f.read()
    except Exception as e:
        logger.warning(f"Could not load formula template {formula_template_path}: {e}")
        return ""

    formula_count = table_analysis.get('metadata', {}).get('formula_count', 0)

    # Create a mapping of columns to their formulas for better organization
    formula_by_column = {}
    referenced_columns = set()
    calculated_columns = set()

    for row_idx, row_formulas in enumerate(formula_data):
        for col_name, formula_info in row_formulas.items():
            if col_name not in formula_by_column:
                formula_by_column[col_name] = []
            formula_by_column[col_name].append({
                'row': row_idx + 1,
                'formula': formula_info['formula'],
                'type': formula_info['formula_type'],
                'description': formula_info['description'],
                'referenced_columns': formula_info['referenced_columns']
            })
            calculated_columns.add(col_name)
            for ref in formula_info['referenced_columns']:
                referenced_columns.add(ref['column_name'])

    # Build formula dependencies detail
    formula_dependencies_detail = ""
    for col_name, formulas in formula_by_column.items():
        formula_dependencies_detail += f"""

**{col_name} (CALCULATED COLUMN):**
- Contains {len(formulas)} formula(s)
- Formulas:"""
        for formula in formulas:
            formula_dependencies_detail += f"""
  - Row {formula['row']}: {formula['formula']} ({formula['type']})
  - Description: {formula['description']}"""

    # Source columns section
    source_cols = referenced_columns - calculated_columns
    if source_cols:
        formula_dependencies_detail += f"""

**SOURCE COLUMNS (Referenced by Formulas):**
These columns are used in calculations and require strict format validation:"""
        for col in source_cols:
            formula_dependencies_detail += f"""
- **{col}**: Used in formulas - MUST maintain consistent data format to prevent Excel formula errors"""

    # Build column-specific formula context
    column_formula_context = ""
    for col_name in calculated_columns | referenced_columns:
        if col_name in calculated_columns:
            column_formula_context += f"""
- **{col_name}**: CALCULATED COLUMN - Contains Excel formulas, use Claude validation (no web search)"""
        elif col_name in referenced_columns:
            column_formula_context += f"""
- **{col_name}**: SOURCE COLUMN - Used in Excel formulas, requires strict format validation"""

    # Replace template fields
    return (formula_template
            .replace('{{FORMULA_COUNT}}', str(formula_count))
            .replace('{{FORMULA_DEPENDENCIES_DETAIL}}', formula_dependencies_detail)
            .replace('{{CALCULATED_COLUMNS_LIST}}', ', '.join(calculated_columns) if calculated_columns else 'None')
            .replace('{{SOURCE_COLUMNS_LIST}}', ', '.join(source_cols) if source_cols else 'None')
            .replace('{{COLUMN_FORMULA_CONTEXT}}', column_formula_context))


def convert_dynamodb_to_plain(data):
    """Convert DynamoDB formatted data (with type descriptors) to plain Python objects"""
    if not data:
        return data

    if isinstance(data, dict):
        # Check if this looks like a DynamoDB item with type descriptors
        if len(data) == 1 and list(data.keys())[0] in ['S', 'N', 'BOOL', 'M', 'L', 'SS', 'NS', 'BS', 'NULL']:
            # This is a DynamoDB attribute value
            key = list(data.keys())[0]
            value = data[key]

            if key == 'S':
                return str(value)
            elif key == 'N':
                try:
                    # Try to convert to int first, then float
                    if '.' in str(value):
                        return float(value)
                    else:
                        return int(value)
                except ValueError:
                    return float(value)
            elif key == 'BOOL':
                return bool(value)
            elif key == 'M':
                # Map type - recursively convert
                return {k: convert_dynamodb_to_plain(v) for k, v in value.items()}
            elif key == 'L':
                # List type - recursively convert
                return [convert_dynamodb_to_plain(item) for item in value]
            elif key == 'NULL':
                return None
            else:
                return value
        else:
            # Regular dict - recursively convert values
            return {k: convert_dynamodb_to_plain(v) for k, v in data.items()}

    elif isinstance(data, list):
        return [convert_dynamodb_to_plain(item) for item in data]

    else:
        return data

def build_table_analysis_section(basic_info, column_analysis, domain_info, calculated_columns, referenced_columns, has_formulas):
    """Build the table analysis section"""
    column_count = len(basic_info.get('column_names', []))

    table_section = f"""
# TABLE ANALYSIS

**File Information:**
- File: {basic_info.get('filename', 'Unknown')}
- Size: {basic_info.get('shape', [0, 0])[0]} rows x {basic_info.get('shape', [0, 0])[1]} columns
- Domain: {domain_info.get('likely_domain', 'general')} (confidence: {domain_info.get('confidence', 0)})

**All Column Names ({column_count} total):**
{', '.join(basic_info.get('column_names', []))}

**CRITICAL REQUIREMENT:** Your configuration MUST include a validation_target entry for EVERY SINGLE one of these {column_count} columns. No column can be omitted.

## Column Details"""

    for col_name, col_info in column_analysis.items():
        sample_values = col_info.get('sample_values', [])[:3]
        table_section += f"""
**{col_name}:**
- Type: {col_info.get('data_type', 'Unknown')}
- Fill Rate: {col_info.get('fill_rate', 0):.1%}
- Sample Values: {sample_values}"""

        # Add formula context if this column has formulas or is referenced by formulas
        if has_formulas:
            # Check if this column is calculated (has formulas)
            if col_name in calculated_columns:
                table_section += f"""
- **CALCULATED COLUMN**: Contains Excel formulas - use Claude validation (no web search)"""

            # Check if this column is referenced by formulas (is a source column)
            elif col_name in referenced_columns:
                table_section += f"""
- **SOURCE COLUMN**: Used in Excel formulas - requires strict format validation"""

    return table_section

def get_unified_generation_schema() -> Dict:
    """Get the unified JSON schema for AI config generation by combining the response wrapper with the config schema."""
    import os

    # Load the column config schema (source of truth)
    config_schema_file = os.path.join(os.path.dirname(__file__), 'column_config_schema.json')
    logger.info(f"Looking for config schema at: {config_schema_file}")

    if not os.path.exists(config_schema_file):
        raise FileNotFoundError(f"Column config schema file not found: {config_schema_file}")

    try:
        with open(config_schema_file, 'r') as f:
            config_schema = json.load(f)
            logger.info(f"Successfully loaded column config schema")

        # Build the AI response wrapper schema
        ai_response_schema = {
            "title": "AI Config Generation Response Schema",
            "description": "Schema for AI responses when generating or refining column configurations",
            "type": "object",
            "required": ["updated_config", "clarifying_questions", "clarification_urgency", "technical_ai_summary", "ai_summary"],
            "properties": {
                "updated_config": config_schema,  # Use the loaded config schema directly
                "clarifying_questions": {
                    "type": "string",
                    "description": "Specific questions about the table or columns to help improve the configuration further."
                },
                "clarification_urgency": {
                    "type": "number",
                    "description": "Urgency score from 0-1 with anchored levels:\n0.0-0.1 = MINIMAL (configuration is solid, minor tweaks only)\n0.2-0.3 = LOW (refinements should typically use this range - good foundation, some improvements possible)\n0.4-0.6 = MODERATE (several important clarifications needed)\n0.7-0.8 = HIGH (significant assumptions made, clarification strongly recommended)\n0.9-1.0 = CRITICAL (core columns will likely be wrong without clarification)\n\nREFINEMENT RULE: Refinements must use LOWER urgency than new configurations (typically 0.1-0.3) since they build on existing validated foundations."
                },
                "technical_ai_summary": {
                    "type": "string",
                    "description": "Technical summary explaining what you did, highlighting assumptions that you needed to make. Include details about search groups, context, criticality, and specific configuration decisions. The focus changes depending on whether the configuration is new or a refinement (you are updating an existing configuration):\n\nFOR NEW CONFIGURATIONS: What is your understanding of the context of this table? What were your assumptions? Does this need refinement? \n\n FOR REFINEMENTS: Focus on changes made and the reasons why they were made. Does this need futher refinement?"
                },
                "ai_summary": {
                    "type": "string",
                    "description": "Simple lay person description of what is happening without explicitly mentioning search groups, context, or criticality. This should be shorter and clearer than the technical summary. Examples: 'Increased search context to high' becomes 'Instructed Perplexity to look at more sources', 'Created dedicated search group' becomes 'Looking for that value by itself'. Focus on the 'why' in simple terms."
                }
            },
            "additionalProperties": False
        }

        logger.info(f"Successfully built AI response schema")
        return ai_response_schema

    except Exception as e:
        logger.error(f"Failed to load column config schema: {e}")
        raise

def add_conversation_entry(updated_config: Dict, existing_config: Dict = None,
                          instructions: str = '', clarifying_questions: str = '',
                          clarification_urgency: float = 0.0, reasoning: str = '',
                          ai_summary: str = '', technical_ai_summary: str = '',
                          session_id: str = 'unknown', conversation_history: list = None,
                          config_filename: str = '') -> Dict:
    """Add conversation entry to config change log and update metadata."""
    from datetime import datetime

    # Initialize or preserve existing change log with multiple fallbacks
    if 'config_change_log' not in updated_config:
        # Priority 1: Use conversation_history passed from interface lambda
        if conversation_history and len(conversation_history) > 0:
            updated_config['config_change_log'] = conversation_history.copy()
            logger.info(f"✅ Preserved {len(updated_config['config_change_log'])} conversation entries from interface lambda")
        # Priority 2: Use existing_config if available
        elif existing_config and 'config_change_log' in existing_config:
            updated_config['config_change_log'] = existing_config['config_change_log'].copy()
            logger.info(f"✅ Preserved {len(updated_config['config_change_log'])} conversation entries from existing_config")
        # Priority 3: Initialize empty log
        else:
            updated_config['config_change_log'] = []
            logger.info("🆕 Initialized new conversation log")
    else:
        logger.info(f"ℹ️ Using existing config_change_log with {len(updated_config.get('config_change_log', []))} entries")

    # Get version number
    current_version = 1
    if existing_config and 'generation_metadata' in existing_config:
        current_version = existing_config['generation_metadata'].get('version', 1) + 1

    # Add conversation entry
    conversation_entry = {
        'timestamp': datetime.now().isoformat(),
        'action': 'unified_generation',
        'session_id': session_id,
        'instructions': instructions,
        'clarifying_questions': clarifying_questions,
        'clarification_urgency': clarification_urgency,
        'reasoning': reasoning,
        'ai_summary': ai_summary,
        'technical_ai_summary': technical_ai_summary,
        'version': current_version,
        'model_used': 'claude-opus-4-1',
        'config_filename': config_filename
    }

    updated_config['config_change_log'].append(conversation_entry)

    # Update generation metadata
    updated_config['generation_metadata'] = {
        'version': current_version,
        'last_updated': datetime.now().isoformat(),
        'total_interactions': len(updated_config['config_change_log']),
        'model_used': conversation_entry['model_used']
    }

    return updated_config
