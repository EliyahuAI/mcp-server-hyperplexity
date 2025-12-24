#!/usr/bin/env python3
"""
Configuration Generation Module
Unified config generation logic extracted from config Lambda
"""

import json
import logging
import os
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
    logging.warning("WebSocket client not available")

# Configure logging
logger = logging.getLogger(__name__)

def load_config_settings():
    """Load configuration settings from JSON file"""
    settings_path = os.path.join(os.path.dirname(__file__), 'config_settings.json')
    try:
        with open(settings_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback to defaults
        return {
            'max_tokens': 16000,
            'model': ['claude-opus-4-1', 'claude-opus-4-20240229', 'claude-sonnet-4-5']
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


async def generate_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate validation config from table analysis.
    Replaces Lambda invoke with direct function call.

    Args:
        payload: Same payload structure as Lambda invoke:
            - table_analysis
            - existing_config (optional)
            - instructions (optional)
            - session_id
            - email
            - conversation_history
            - latest_validation_results

    Returns:
        Same structure as Lambda response:
            - success: bool
            - updated_config: Dict
            - clarifying_questions: str
            - clarification_urgency: float
            - reasoning: str
            - ai_summary: str
            - session_id: str
            - eliyahu_cost: float
            - enhanced_data: Dict
            - token_usage: Dict
            - ...
    """
    try:
        # Debug: Log what we received in the payload
        logger.debug(f"CONFIG_RECEIVED: Payload keys: {list(payload.keys())}")
        logger.debug(f"CONFIG_RECEIVED: Has existing_config: {bool(payload.get('existing_config'))}")
        logger.debug(f"CONFIG_RECEIVED: Has latest_validation_results: {bool(payload.get('latest_validation_results'))}")

        # Extract request parameters
        table_analysis = payload.get('table_analysis')
        existing_config = payload.get('existing_config')  # Optional
        instructions = payload.get('instructions', 'Generate an optimal configuration for this data validation scenario')
        session_id = payload.get('session_id', 'unknown')
        latest_validation_results = payload.get('latest_validation_results')  # Optional - for refinement context

        # Send initial progress update
        if session_id:
            send_websocket_progress(session_id, "Starting AI configuration generation...", 10)

        # Table can be provided in multiple formats
        excel_s3_key = payload.get('excel_s3_key')
        csv_s3_key = payload.get('csv_s3_key')
        table_data = payload.get('table_data')  # Direct table data
        email = payload.get('email', '')

        # Need either table_analysis or a way to generate it
        if not table_analysis and not any([excel_s3_key, csv_s3_key, table_data, (email and session_id)]):
            return {
                'success': False,
                'error': 'Missing table_analysis or table data (excel_s3_key, csv_s3_key, table_data, or email+session_id for lookup)'
            }

        # Generate table analysis if not provided
        if not table_analysis:
            logger.info("Generating table analysis from provided data")
            if session_id:
                send_websocket_progress(session_id, "Analyzing table structure...", 25)
            try:
                bucket = os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')

                # If no explicit excel_s3_key provided, use unified method to find latest table in session folder
                if not excel_s3_key and not csv_s3_key and not table_data:
                    if email and session_id:
                        logger.info(f"No excel_s3_key provided, using UnifiedS3Manager to find table for session {session_id}")
                        from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
                        s3_manager = UnifiedS3Manager()
                        excel_content, excel_s3_key = s3_manager.get_excel_file(email, session_id)

                        if not excel_content or not excel_s3_key:
                            return {
                                'success': False,
                                'error': f'No Excel file found in session folder for session {session_id}'
                            }
                        logger.info(f"Found Excel file in session folder: {excel_s3_key}")
                    else:
                        return {
                            'success': False,
                            'error': 'Need email and session_id to locate table file'
                        }

                if excel_s3_key:
                    logger.info(f"Analyzing Excel from S3: {excel_s3_key}")
                    table_analysis = s3_table_parser.analyze_table_structure(bucket, excel_s3_key, extract_formulas=True)
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
                    'success': False,
                    'error': f'Table analysis failed: {str(e)}'
                }

        logger.info(f"Config generation for session: {session_id}")

        # Send progress update before AI generation
        if session_id:
            send_websocket_progress(session_id, "Requesting AI configuration...", 50)

        # Get conversation history from payload if provided
        conversation_history = payload.get('conversation_history', [])

        # Process the config generation request (single unified mode)
        result = await generate_config_unified(
            table_analysis, existing_config, instructions, session_id, latest_validation_results, conversation_history
        )

        # Send completion progress update
        if session_id:
            send_websocket_progress(session_id, "Configuration generated successfully!", 100)

        return result

    except Exception as e:
        logger.error(f"Config generation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


async def generate_config_unified(table_analysis: Dict, existing_config: Dict = None,
                                 instructions: str = '', session_id: str = 'unknown',
                                 latest_validation_results: Dict = None, conversation_history: list = None, retry_count: int = 0) -> Dict:
    """Unified config generation - always returns both updated config and clarifying questions."""
    MAX_RETRIES = 3

    logger.info(f"CONFIG GENERATION ENTRY - Session: {session_id}, Instructions: {instructions[:50]}..., Retry: {retry_count}")
    logger.debug(f"GENERATE_CONFIG_UNIFIED_PARAMS: existing_config={bool(existing_config)}, latest_validation_results={bool(latest_validation_results)}")

    if existing_config:
        if isinstance(existing_config, dict):
            logger.debug(f"GENERATE_CONFIG_UNIFIED_PARAMS: existing_config keys: {list(existing_config.keys())}")
            logger.debug(f"GENERATE_CONFIG_UNIFIED_PARAMS: config_change_log present: {bool(existing_config.get('config_change_log'))}")
        else:
            logger.warning(f"GENERATE_CONFIG_UNIFIED_PARAMS: existing_config is not a dict - type: {type(existing_config)}")
            # Convert to None since we can't use a non-dict config
            existing_config = None

    logger.info(f"Config generation started for session {session_id} (retry {retry_count}/{MAX_RETRIES})")
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
                logger.debug(f"  Entry {len(conversation_history)-3+i}: USER - {entry.get('user_instructions', 'No instructions')[:50]}...")
            else:
                logger.debug(f"  Entry {len(conversation_history)-3+i}: {entry_type} - {entry.get('instructions', 'No instructions')[:50]}...")
    else:
        logger.info("No conversation history provided")

    try:
        # Build the unified generation prompt
        prompt = build_unified_generation_prompt(table_analysis, existing_config, instructions, latest_validation_results, conversation_history, session_id)

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

        # Parse updated_config if it's a JSON string (double-encoded)
        if updated_config and isinstance(updated_config, str):
            try:
                updated_config = json.loads(updated_config)
                logger.info("[CONFIG_PARSING] Successfully parsed updated_config from JSON string")
            except json.JSONDecodeError as e:
                logger.error(f"[CONFIG_PARSING] Failed to parse updated_config JSON: {e}")
                raise ValueError(f"Invalid JSON in updated_config: {str(e)}")

        clarifying_questions = response_data.get('clarifying_questions', '')
        clarification_urgency = response_data.get('clarification_urgency', 0.0)
        reasoning = response_data.get('reasoning', '')
        ai_summary = response_data.get('ai_summary', '')

        # Debug: Log clarifying questions details
        logger.debug(f"CONFIG_DEBUG: Clarifying questions generated: {bool(clarifying_questions)}")
        if clarifying_questions:
            logger.debug(f"CONFIG_DEBUG: Questions length: {len(clarifying_questions)}")
            logger.debug(f"CONFIG_DEBUG: Questions preview: {clarifying_questions[:200]}...")

        # Validate the AI-generated config before proceeding
        if updated_config:
            is_valid, errors, warnings = validate_config_complete(updated_config, table_analysis)

            if not is_valid:
                if retry_count >= MAX_RETRIES:
                    logger.error(f"Max retries ({MAX_RETRIES}) reached, returning invalid config with errors")
                else:
                    logger.warning(f"AI generated invalid config, attempting retry {retry_count + 1}/{MAX_RETRIES} with validation errors")
                    # Retry with validation errors as refinement instructions
                    error_instructions = f"The previous configuration had validation errors. Please fix these issues:\n\nErrors:\n" + "\n".join(f"- {error}" for error in errors)
                    if warnings:
                        error_instructions += f"\n\nWarnings:\n" + "\n".join(f"- {warning}" for warning in warnings)

                    # Recursive call to fix the config
                    retry_result = await generate_config_unified(
                        table_analysis=table_analysis,
                        existing_config=updated_config,  # Use the invalid config as base
                        instructions=error_instructions,
                        session_id=session_id,
                        latest_validation_results=latest_validation_results,
                        retry_count=retry_count + 1
                    )

                    if retry_result.get('success') and retry_result.get('updated_config'):
                        logger.info(f"Successfully fixed config validation errors on retry {retry_count + 1}")
                        updated_config = retry_result['updated_config']
                        # Merge retry information
                        reasoning += f"\n\nRetry: {retry_result.get('reasoning', '')}"
                        ai_summary += f"\n\nRetry Summary: {retry_result.get('ai_summary', '')}"
                    else:
                        logger.error(f"Failed to fix config validation errors on retry {retry_count + 1}")

        # Config generation returns clean structured response - interface lambda handles metadata and conversation tracking
        logger.info("Config generation complete - returning clean config to interface lambda")

        return {
            'success': True,
            'updated_config': updated_config,
            'clarifying_questions': clarifying_questions,
            'clarification_urgency': clarification_urgency,
            'reasoning': reasoning,
            'ai_summary': ai_summary,
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
        # Safely get session_id, with fallback if parameter is undefined
        try:
            safe_session_id = session_id
        except NameError:
            safe_session_id = 'unknown'
        return {
            'success': False,
            'error': f'Config generation failed: {str(e)}',
            'session_id': safe_session_id
        }


def build_unified_generation_prompt(table_analysis: Dict, existing_config: Dict = None,
                                  instructions: str = '', latest_validation_results: Dict = None,
                                  conversation_history: list = None, session_id: str = 'unknown') -> str:
    """Build unified prompt for config generation that always returns both config and questions."""

    basic_info = table_analysis.get('basic_info', {})
    column_analysis = table_analysis.get('column_analysis', {})
    domain_info = table_analysis.get('domain_info', {})
    formula_data = table_analysis.get('formula_data', [])
    has_formulas = table_analysis.get('metadata', {}).get('has_formulas', False)

    # Get detailed performance data from DynamoDB first to inform refinement decision
    detailed_runs_data = get_latest_runs_data_from_dynamodb(session_id) if session_id != 'unknown' else None
    logger.debug(f"RUNS DATA FROM DYNAMODB: {bool(detailed_runs_data)}")

    # Determine if this is a new config or refinement
    has_existing_config = (existing_config is not None and
                          isinstance(existing_config, dict) and
                          existing_config.get('config_change_log', []))
    has_validation_data = detailed_runs_data is not None or latest_validation_results is not None

    is_new_config = not (has_existing_config or has_validation_data)

    # Check if this is from Table Maker (special prompt with NO IGNORED COLUMNS rule)
    metadata = table_analysis.get('metadata', {})
    is_table_maker = metadata.get('generated_by') == 'table_maker'

    logger.debug(f"REFINEMENT DETECTION: existing_config={bool(has_existing_config)}, validation_data={bool(has_validation_data)}, is_new_config={is_new_config}, is_table_maker={is_table_maker}")

    # Load the appropriate prompt template
    current_dir = os.path.dirname(__file__)

    if is_table_maker:
        # Table Maker mode: Use specialized prompt with NO IGNORED COLUMNS requirement
        prompt_file = os.path.join(current_dir, 'prompts', 'table_maker_config_prompt.md')
        logger.info("Using Table Maker config prompt (NO IGNORED COLUMNS)")
    elif is_new_config:
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

    # Extract conversation_context for Table Maker
    conversation_context = table_analysis.get('conversation_context', None)
    if conversation_context:
        logger.info(f"[CONFIG GENERATION] Found conversation_context with keys: {list(conversation_context.keys())}")
        logger.debug(f"[CONFIG GENERATION] Conversation context details: research_purpose={bool(conversation_context.get('research_purpose'))}, tablewide_research={bool(conversation_context.get('tablewide_research'))}, column_details={len(conversation_context.get('column_details', []))} columns")
    else:
        logger.info("[CONFIG GENERATION] No conversation_context found (not a Table Maker table)")

    # Build base prompt with field replacements
    table_analysis_content = build_table_analysis_section(
        basic_info, column_analysis, domain_info, calculated_columns, referenced_columns, has_formulas, conversation_context
    )

    # Build validation context and user feedback sections
    logger.debug(f"VALIDATION CONTEXT CHECK - latest_validation_results is None: {latest_validation_results is None}")

    # Use the already-retrieved DynamoDB data
    if detailed_runs_data:
        logger.debug(f"DYNAMODB RUNS KEYS: {list(detailed_runs_data.keys())}")
        # Use the detailed DynamoDB data for validation context
        validation_context_content = build_validation_context_section(detailed_runs_data)
    else:
        # Fallback to interface response data
        if latest_validation_results:
            logger.debug(f"FALLBACK - VALIDATION RESULTS KEYS: {list(latest_validation_results.keys())}")
        validation_context_content = build_validation_context_section(latest_validation_results) if latest_validation_results else ""

    user_feedback_content = build_user_feedback_section(instructions, conversation_history) if (instructions or conversation_history) else ""

    # Ensure we have fallback content for empty sections
    if not table_analysis_content:
        table_analysis_content = "# TABLE ANALYSIS\n\nTable analysis data not available."
    if not formula_analysis_content:
        formula_analysis_content = "# FORMULA ANALYSIS\n\nNo Excel formulas detected in this dataset."
    if not validation_context_content:
        validation_context_content = "# VALIDATION CONTEXT\n\nNo previous validation results available for context."
    if not user_feedback_content:
        user_feedback_content = "# USER FEEDBACK\n\nNo specific user feedback provided for this refinement."

    base_prompt = (prompt_template
                   .replace('{{TABLE_ANALYSIS}}', table_analysis_content)
                   .replace('{{FORMULA_ANALYSIS}}', formula_analysis_content)
                   .replace('{{VALIDATION_CONTEXT}}', validation_context_content)
                   .replace('{{USER_FEEDBACK_SECTION}}', user_feedback_content))

    if existing_config:
        # Add existing configuration context
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
        if latest_validation_results and isinstance(latest_validation_results, dict):
            validation_summary = latest_validation_results.get('validation_summary', {})
            model_data = latest_validation_results.get('model_data', {})
            qc_metrics = latest_validation_results.get('qc_metrics', {})

            # Convert DynamoDB format to plain values if needed
            if model_data:
                model_data = convert_dynamodb_to_plain(model_data)

            if qc_metrics:
                qc_metrics = convert_dynamodb_to_plain(qc_metrics)

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

**PROBLEM COLUMNS - REQUIRE ATTENTION:**
These columns have high QC fail rates and should be improved:
"""
                        for col in problem_columns:
                            base_prompt += f"""
- **{col['name']}**: Overall fail: {col['overall_fail_rate']:.1%}, Value fail: {col['value_fail_rate']:.1%}, Confidence fail: {col['confidence_fail_rate']:.1%} ({col['modified']}/{col['reviewed']} modified)
  -> Consider: Different model, better search context, improved examples, or format clarification"""

                    # Show well-performing columns
                    if good_columns:
                        base_prompt += f"""

**WELL-PERFORMING COLUMNS:**"""
                        for col in good_columns:
                            base_prompt += f"""
- **{col['name']}**: {col['overall_fail_rate']:.1%} fail rate ({col['reviewed']} reviewed) - Good performance"""

                base_prompt += f"""

**REFINEMENT GUIDANCE:**
- Focus improvements on problem columns with high fail rates
- Consider upgrading to more advanced models for failing columns
- Review examples and format specifications for failing columns
- Consider moving problem columns to different search groups with related information"""

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
        # Show only first 2 formula examples to avoid clutter
        for formula in formulas[:2]:
            formula_dependencies_detail += f"""
  - Row {formula['row']}: {formula['formula']} ({formula['type']})
  - Description: {formula['description']}"""

        # Add note if there are more formulas
        if len(formulas) > 2:
            formula_dependencies_detail += f"""
  - ... and {len(formulas) - 2} more rows with similar formulas"""

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
- **{col_name}**: CALCULATED COLUMN - Mark as IGNORED importance, these should not be validated by AI as they are dependent columns containing formulas, NOT suitable as ID field"""
        elif col_name in referenced_columns:
            column_formula_context += f"""
- **{col_name}**: SOURCE COLUMN - Mark as RESEARCH importance, strict format validation required, can be ID field if unique"""

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


def build_user_feedback_section(instructions: str, conversation_history: list) -> str:
    """Build the user feedback section for the refinement prompt."""
    if not instructions and not conversation_history:
        return ""

    content = """# USER FEEDBACK AND REFINEMENT REQUEST

"""

    # Extract and present all user messages from conversation history
    user_messages = []
    if conversation_history:
        for entry in conversation_history:
            if entry.get('entry_type') == 'user_input' or entry.get('action') == 'user_message':
                timestamp = entry.get('timestamp', 'Unknown time')
                user_instruction = entry.get('user_instructions', entry.get('instructions', ''))
                if user_instruction:
                    user_messages.append({
                        'timestamp': timestamp,
                        'instruction': user_instruction
                    })

    if user_messages:
        content += "**User Feedback History** (chronological order):\n\n"
        for i, msg in enumerate(user_messages, 1):
            # Parse timestamp to make it readable
            try:
                dt = datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00'))
                readable_time = dt.strftime('%Y-%m-%d %H:%M')
            except:
                readable_time = msg['timestamp'][:16]  # Fallback

            content += f"{i}. **{readable_time}**: {msg['instruction']}\n\n"

    # Highlight the current/latest instruction
    if instructions:
        content += f"""**CURRENT REQUEST** (focus on this):
"{instructions}"

"""

    content += """**Your Task**:
1. **Review all user feedback** to understand the evolution of their requirements
2. **Focus primarily on the CURRENT REQUEST** while considering previous context
3. **Make ONLY the specific changes** needed to address the current request
4. **Preserve everything else** that is working well and hasn't been criticized
5. **Avoid going in circles** - don't undo previous changes unless specifically requested

"""

    return content


def get_latest_runs_data_from_dynamodb(session_id: str) -> Optional[Dict]:
    """Get the latest runs data directly from DynamoDB table."""
    try:
        import boto3
        from botocore.exceptions import ClientError

        logger.debug(f"Querying DynamoDB runs table for session: {session_id}")

        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('perplexity-validator-runs')

        # Query for the most recent validation or preview run for this session
        preview_response = table.query(
            KeyConditionExpression='session_id = :session_id AND begins_with(run_key, :preview)',
            ExpressionAttributeValues={
                ':session_id': session_id,
                ':preview': 'Preview#'
            },
            ScanIndexForward=False,  # Get most recent first
            Limit=1
        )

        validation_response = table.query(
            KeyConditionExpression='session_id = :session_id AND begins_with(run_key, :validation)',
            ExpressionAttributeValues={
                ':session_id': session_id,
                ':validation': 'Validation#'
            },
            ScanIndexForward=False,  # Get most recent first
            Limit=1
        )

        # Combine results and get the most recent
        all_items = preview_response.get('Items', []) + validation_response.get('Items', [])
        if all_items:
            # Sort by run_key to get most recent (since run_key contains timestamp)
            response = {'Items': sorted(all_items, key=lambda x: x['run_key'], reverse=True)}
        else:
            response = {'Items': []}

        if response.get('Items'):
            run_item = response['Items'][0]
            logger.debug(f"Found DynamoDB run item with keys: {list(run_item.keys())}")
            return run_item
        else:
            logger.debug(f"No runs found in DynamoDB for session: {session_id}")
            return None

    except Exception as e:
        logger.warning(f"Error querying DynamoDB runs table: {e}")
        return None


def build_validation_context_from_interface_data(interface_response: Dict) -> str:
    """Build validation context from interface response data format."""
    logger.debug("Building validation context from interface data")

    cost_estimates = interface_response.get('cost_estimates', {})
    validation_metrics = interface_response.get('validation_metrics', {})
    markdown_table = interface_response.get('markdown_table', '')

    content = """
# VALIDATION RESULTS CONTEXT

The following validation results are available from the most recent preview run:
"""

    # Add actual preview results first
    if markdown_table:
        content += """
## Actual Preview Results

Here are the actual validation results from the preview run:

"""
        content += f"```\n{markdown_table}\n```\n\n"

    content += """
## Cost Analysis
"""

    if cost_estimates:
        estimated_cost = cost_estimates.get('estimated_validation_eliyahu_cost', 0)
        estimated_time = cost_estimates.get('estimated_validation_time', 0)
        content += f"""
- **Estimated Total Cost**: ${estimated_cost:.2f}
- **Estimated Processing Time**: {estimated_time:.1f} minutes
"""

    if validation_metrics:
        content += f"""
## Validation Metrics
- **Search Groups**: {validation_metrics.get('search_groups_count', 'Unknown')}
- **Validated Columns**: {validation_metrics.get('validated_columns_count', 'Unknown')}
- **Claude Search Groups**: {validation_metrics.get('claude_search_groups_count', 0)} (expensive)
"""

    content += """

## Cost Optimization Recommendations
Based on the preview results, consider:
1. **High-cost areas**: Claude models with web searches are significantly more expensive
2. **Processing time**: Complex models take much longer to process
3. **Search group efficiency**: Multiple search groups increase total cost

"""

    return content


def build_validation_context_from_runs_data(runs_data: Dict, models: Dict, qc_metrics: Dict, provider_metrics: Dict) -> str:
    """Build detailed validation context from DynamoDB runs data."""
    logger.debug("Building validation context from detailed runs data")

    content = """
# VALIDATION RESULTS CONTEXT

The following detailed validation results are from the most recent run:
"""

    # Add actual preview results if available in runs data
    preview_data = runs_data.get('preview_data')
    if preview_data:
        # Handle JSON string format from DynamoDB
        if isinstance(preview_data, str):
            try:
                preview_data = json.loads(preview_data)
            except:
                logger.warning("Could not parse preview_data JSON")
                preview_data = None

        if preview_data and isinstance(preview_data, dict):
            markdown_table = preview_data.get('markdown_table', '')
            if markdown_table:
                content += """
## Actual Preview Results

Here are the actual validation results from the preview run:

"""
                content += f"```\n{markdown_table}\n```\n\n"

    content += """
## Cost Analysis by Search Group
"""

    # Parse models data (JSON string in DynamoDB)
    if isinstance(models, str):
        try:
            models = json.loads(models)
        except:
            models = {}

    if models:
        for group_name, group_data in models.items():
            if isinstance(group_data, dict):
                avg_cost = group_data.get('average_estimated_cost', 0)
                avg_time = group_data.get('average_estimated_time', 0)
                model_used = group_data.get('mode_model_used', 'unknown')
                column_count = group_data.get('column_count', 0)

                content += f"""
**{group_name}** ({model_used}):
- Cost per row: ${avg_cost:.4f}
- Time per row: {avg_time:.1f}s
- Columns: {column_count}
"""

    # Add QC metrics
    if qc_metrics and isinstance(qc_metrics, dict):
        qc_by_column = qc_metrics.get('qc_by_column', {})
        if qc_by_column:
            content += """
## Quality Control Issues
High-priority columns needing attention:
"""
            for col_name, col_qc in qc_by_column.items():
                if isinstance(col_qc, dict):
                    fail_rate = col_qc.get('overall_fail_rate', 0)
                    if fail_rate > 20:  # High fail rate
                        content += f"""
- **{col_name}**: {fail_rate:.1f}% QC fail rate (needs improvement)
"""

    # Add provider cost summary
    if provider_metrics:
        content += """
## Provider Cost Breakdown
"""
        for provider, metrics in provider_metrics.items():
            if isinstance(metrics, dict):
                cost_per_row = metrics.get('cost_per_row_actual', 0)
                calls = metrics.get('calls', 0)
                content += f"""
- **{provider}**: ${cost_per_row:.4f}/row ({calls} calls)
"""

    content += """
## Cost Optimization Opportunities
Based on actual performance data:
1. **Most expensive search groups** should be optimized first
2. **High QC fail rates** indicate models that aren't working well
3. **Claude with web searches** typically costs 10-20x more than Perplexity models
"""

    return content


def build_validation_context_section(latest_validation_results: Dict) -> str:
    """Build the validation context section with performance data."""
    if not latest_validation_results:
        return ""

    # Safety check: ensure we have a dict, not a list
    if not isinstance(latest_validation_results, dict):
        logger.error(f"build_validation_context_section - ERROR: Expected dict but got {type(latest_validation_results)}")
        return "# VALIDATION CONTEXT\n\nValidation results format error - expected dictionary but received different type."

    logger.debug(f"build_validation_context_section - Available keys: {list(latest_validation_results.keys())}")

    # Check for DynamoDB runs table structure (the detailed performance data)
    models = latest_validation_results.get('models', {})
    qc_metrics = latest_validation_results.get('qc_metrics', {})
    provider_metrics = latest_validation_results.get('provider_metrics', {})

    # Convert DynamoDB format if it's raw DynamoDB data
    if isinstance(models, dict) and models:
        # Check if it's DynamoDB format (has type descriptors)
        if any(isinstance(v, dict) and len(v) == 1 and list(v.keys())[0] in ['S', 'N', 'M', 'L'] for v in models.values() if isinstance(v, dict)):
            models = convert_dynamodb_to_plain(models)
        if isinstance(qc_metrics, dict) and qc_metrics:
            qc_metrics = convert_dynamodb_to_plain(qc_metrics)
        if isinstance(provider_metrics, dict) and provider_metrics:
            provider_metrics = convert_dynamodb_to_plain(provider_metrics)

    logger.debug(f"DynamoDB runs data - models: {bool(models)}, qc_metrics: {bool(qc_metrics)}, provider_metrics: {bool(provider_metrics)}")

    # If we have detailed performance data, use it
    if models or qc_metrics or provider_metrics:
        return build_validation_context_from_runs_data(latest_validation_results, models, qc_metrics, provider_metrics)

    # Fallback to interface response structure
    logger.debug("No detailed performance data found, trying interface response structure")
    cost_estimates = latest_validation_results.get('cost_estimates', {})
    validation_metrics = latest_validation_results.get('validation_metrics', {})

    if cost_estimates or validation_metrics:
        return build_validation_context_from_interface_data(latest_validation_results)

    return ""


def build_table_analysis_section(basic_info, column_analysis, domain_info, calculated_columns, referenced_columns, has_formulas, conversation_context=None):
    """Build the table analysis section

    Args:
        basic_info: Basic file information
        column_analysis: Column-level analysis
        domain_info: Domain information
        calculated_columns: Set of columns with formulas
        referenced_columns: Set of columns referenced in formulas
        has_formulas: Whether spreadsheet has formulas
        conversation_context: Optional Table Maker context with research purpose, column definitions, etc.
    """
    column_count = len(basic_info.get('column_names', []))

    # Start with basic table information
    table_section = f"""
# TABLE ANALYSIS

**File Information:**
- Size: {basic_info.get('shape', [0, 0])[0]} rows x {basic_info.get('shape', [0, 0])[1]} columns
- Domain: {domain_info.get('likely_domain', 'general')} (confidence: {domain_info.get('confidence', 0)})

**All Column Names ({column_count} total):**
{', '.join(basic_info.get('column_names', []))}

**CRITICAL REQUIREMENT:** Your configuration MUST include a validation_target entry for EVERY SINGLE one of these {column_count} columns. No column can be omitted."""

    # Add Table Maker context if available
    if conversation_context:
        table_section += "\n\n"
        table_section += "═══════════════════════════════════════════════════════════════\n"
        table_section += "## 📚 TABLE MAKER CONTEXT - Rich Information from AI-Assisted Table Creation\n"
        table_section += "═══════════════════════════════════════════════════════════════\n\n"
        table_section += "This table was generated through an AI-assisted Table Maker process. Use this context to inform your configuration:\n\n"

        # Add research purpose
        research_purpose = conversation_context.get('research_purpose', '')
        if research_purpose:
            table_section += f"### Research Purpose\n\n{research_purpose}\n\n"

        # Add user requirements
        user_requirements = conversation_context.get('user_requirements', '')
        if user_requirements:
            table_section += f"### User Requirements\n\n{user_requirements}\n\n"

        # Add tablewide research
        tablewide_research = conversation_context.get('tablewide_research', '')
        if tablewide_research:
            table_section += f"### Tablewide Research Summary\n\n{tablewide_research}\n\n"

        # Add column definitions with rich detail
        column_details = conversation_context.get('column_details', [])
        if column_details:
            table_section += "### Column Definitions from Table Maker\n\n"
            table_section += "**CRITICAL**: Use the `description` and `validation_strategy` from these column definitions EXACTLY in your validation target `notes`. Do not paraphrase.\n\n"

            for col in column_details:
                col_name = col.get('name', 'Unknown')
                description = col.get('description', '')
                validation_strategy = col.get('validation_strategy', '')
                format_type = col.get('format', '')
                importance = col.get('importance', '')

                table_section += f"**{col_name}:**\n"
                if importance.upper() == 'ID':
                    table_section += f"- **Type**: IDENTIFICATION COLUMN\n"
                table_section += f"- **Description**: {description}\n"
                if validation_strategy:
                    table_section += f"- **Validation Strategy**: {validation_strategy}\n"
                if format_type:
                    table_section += f"- **Format**: {format_type}\n"
                table_section += "\n"

        # Add identification columns list
        identification_columns = conversation_context.get('identification_columns', [])
        if identification_columns:
            table_section += f"### Identification Columns\n\n"
            table_section += f"These columns define what each row represents: {', '.join(identification_columns)}\n\n"
            table_section += "**NOTE**: Researchable ID columns (names, companies, URLs, institutions) should be placed in validation groups with importance: \"CRITICAL\". Simple ID columns (dates, indices) should be in Group 0 with importance: \"ID\".\n\n"

    table_section += "\n## Column Details"

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
- **CALCULATED COLUMN**: Contains Excel formulas - validate using AI logic (Claude, no web search), NOT suitable as ID field"""

            # Check if this column is referenced by formulas (is a source column)
            elif col_name in referenced_columns:
                table_section += f"""
- **SOURCE COLUMN**: Used in Excel formulas - requires strict format validation, can be ID field if unique"""

    return table_section


def get_unified_generation_schema() -> Dict:
    """Get the unified JSON schema for AI config generation by combining the response wrapper with the config schema."""

    # Load the column config schema (source of truth)
    config_schema_file = os.path.join(os.path.dirname(__file__), 'schemas', 'column_config_schema.json')
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
            "required": ["updated_config", "clarifying_questions", "clarification_urgency", "ai_summary"],
            "properties": {
                "updated_config": config_schema,  # Use the loaded config schema directly
                "clarifying_questions": {
                    "type": "string",
                    "description": "CRITICAL: Questions shown AFTER user sees preview - NEVER reference preview data. Keep to 2-3 questions max, only when needed. Use short, clear lay-person language. General terms only ('more thorough searching' NOT 'high search context'). NEVER mention specific models, costs, or technical parameters. Limit to 2 options maximum. Example: 'Should I prioritize recent information or include historical data?'"
                },
                "clarification_urgency": {
                    "type": "number",
                    "description": "Urgency score from 0-1 with anchored levels:\n0.0-0.1 = MINIMAL (configuration is solid, minor tweaks only)\n0.2-0.3 = LOW (refinements should typically use this range - good foundation, some improvements possible)\n0.4-0.6 = MODERATE (several important clarifications needed)\n0.7-0.8 = HIGH (significant assumptions made, clarification strongly recommended)\n0.9-1.0 = CRITICAL (core columns will likely be wrong without clarification)\n\nREFINEMENT RULE: Refinements must use LOWER urgency than new configurations (typically 0.1-0.3) since they build on existing validated foundations."
                },
                "ai_summary": {
                    "type": "string",
                    "description": "Light, 1-3 sentence description of validation settings or changes in plain language. Use general terms ONLY ('thorough validation', 'quick checks', etc.). NEVER mention specific models, technical parameters, or implementation details. Focus on what's being validated. Keep it very brief."
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
                          ai_summary: str = '',
                          session_id: str = 'unknown', conversation_history: list = None,
                          config_filename: str = '') -> Dict:
    """Add conversation entry to config change log and update metadata."""

    # Initialize or preserve existing change log with multiple fallbacks
    if 'config_change_log' not in updated_config:
        # Priority 1: Use conversation_history passed from interface lambda
        if conversation_history and len(conversation_history) > 0:
            updated_config['config_change_log'] = conversation_history.copy()
            logger.info(f"Preserved {len(updated_config['config_change_log'])} conversation entries from interface lambda")
        # Priority 2: Use existing_config if available
        elif existing_config and 'config_change_log' in existing_config:
            updated_config['config_change_log'] = existing_config['config_change_log'].copy()
            logger.info(f"Preserved {len(updated_config['config_change_log'])} conversation entries from existing_config")
        # Priority 3: Initialize empty log
        else:
            updated_config['config_change_log'] = []
            logger.info("Initialized new conversation log")
    else:
        logger.info(f"Using existing config_change_log with {len(updated_config.get('config_change_log', []))} entries")

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
