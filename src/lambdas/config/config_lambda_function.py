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
                bucket = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
                
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
        
        # Process the config generation request (single unified mode)
        result = asyncio.run(generate_config_unified(
            table_analysis, existing_config, instructions, session_id, latest_validation_results
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
                                 latest_validation_results: Dict = None) -> Dict:
    """Unified config generation - always returns both updated config and clarifying questions."""
    logger.info(f"Config generation started for session {session_id}")
    send_websocket_progress(session_id, "Processing table data...", 60)
    
    # Debug logging for existing config
    if existing_config:
        change_log = existing_config.get('config_change_log', [])
        generation_metadata = existing_config.get('generation_metadata', {})
        current_version = generation_metadata.get('version', 1)
        logger.info(f"Existing config found - Version: {current_version}, Change log entries: {len(change_log)}")
        
        if change_log:
            logger.info(f"Recent change log entries:")
            for i, entry in enumerate(change_log[-3:], 1):
                logger.info(f"  Entry {len(change_log)-3+i}: v{entry.get('version', 'unknown')} - {entry.get('instructions', 'No instructions')[:50]}...")
    else:
        logger.info("No existing config provided - creating new configuration")
    
    try:
        # For refinements, embed user message in conversation log first
        if existing_config and instructions:
            existing_config = embed_user_message_in_log(existing_config, instructions, session_id)
        
        # Build the unified generation prompt
        prompt = build_unified_generation_prompt(table_analysis, existing_config, instructions, latest_validation_results)
        
        # Call Claude using shared client with unified schema
        schema = get_unified_generation_schema()
        
        result = await ai_client.call_structured_api(
            prompt=prompt,
            schema=schema,
            model="claude-sonnet-4-0",
            tool_name="generate_config_and_questions"
            # Removed context parameter - it was incorrectly using session_id
            # Context should be for search_context_size in validation calls
        )
        
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
                config_filename=config_filename
            )
        
        # Save config to S3 after adding conversation entry (so saved config includes full history)
        config_s3_key = None
        config_download_url = None
        try:
            if updated_config:
                save_result = save_config_to_s3(updated_config, session_id, table_analysis, existing_config)
                if save_result:
                    config_s3_key = save_result['s3_key']
                    saved_filename = save_result['filename']
                    config_download_url = create_config_download_url(config_s3_key)
                    logger.info(f"Config saved to S3 with key: {config_s3_key}")
                    logger.info(f"Config filename: {saved_filename}")
                    logger.info(f"Download URL created: {config_download_url}")
                    
                    # Use the actual saved filename (should match what we calculated)
                    config_filename = saved_filename
                else:
                    logger.error("Failed to get S3 save result")
        except Exception as s3_error:
            logger.error(f"Failed to save config to S3: {str(s3_error)}")
            config_s3_key = None
            config_download_url = None
        
        # Extract version for easy access
        config_version = updated_config.get('generation_metadata', {}).get('version', 1) if updated_config else 1
        
        return {
            'success': True,
            'updated_config': updated_config,
            'clarifying_questions': clarifying_questions,
            'clarification_urgency': clarification_urgency,
            'reasoning': reasoning,
            'ai_summary': ai_summary,
            'technical_ai_summary': technical_ai_summary,
            'config_s3_key': config_s3_key,
            'config_download_url': config_download_url,
            'config_filename': config_filename,
            'config_version': config_version,  # Add explicit version field
            'session_id': session_id
        }
        
    except Exception as e:
        logger.error(f"Unified config generation failed: {str(e)}")
        return {
            'success': False,
            'error': f'Config generation failed: {str(e)}',
            'session_id': session_id
        }

def build_unified_generation_prompt(table_analysis: Dict, existing_config: Dict = None, 
                                  instructions: str = '', latest_validation_results: Dict = None) -> str:
    """Build unified prompt for config generation that always returns both config and questions."""
    
    basic_info = table_analysis.get('basic_info', {})
    column_analysis = table_analysis.get('column_analysis', {})
    domain_info = table_analysis.get('domain_info', {})
    
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
    
    base_prompt = f"""{prompt_template}

TABLE ANALYSIS:
- File: {basic_info.get('filename', 'Unknown')}
- Size: {basic_info.get('shape', [0, 0])[0]} rows × {basic_info.get('shape', [0, 0])[1]} columns
- Domain: {domain_info.get('likely_domain', 'general')} (confidence: {domain_info.get('confidence', 0)})

ALL COLUMN NAMES ({len(basic_info.get('column_names', []))} total):
{', '.join(basic_info.get('column_names', []))}

CRITICAL REQUIREMENT: Your configuration MUST include a validation_target entry for EVERY SINGLE one of these {len(basic_info.get('column_names', []))} columns. No column can be omitted.

COLUMN DETAILS:"""
    
    for col_name, col_info in column_analysis.items():
        sample_values = col_info.get('sample_values', [])[:3]
        base_prompt += f"""
{col_name}:
  - Type: {col_info.get('data_type', 'Unknown')}
  - Fill Rate: {col_info.get('fill_rate', 0):.1%}
  - Sample Values: {sample_values}"""
    
    if existing_config:
        # Extract conversation history for context
        change_log = existing_config.get('config_change_log', [])
        current_version = existing_config.get('generation_metadata', {}).get('version', 1)
        next_version = current_version + 1
        
        if change_log:
            base_prompt += f"""

EXISTING CONFIGURATION:
This configuration has been iteratively improved through {len(change_log)} previous interactions.

Recent conversation history:"""
            # Include last 3 interactions for context
            for entry in change_log[-3:]:
                base_prompt += f"""
- {entry.get('timestamp', 'Unknown')}: "{entry.get('instructions', 'No instructions')}"
  Response: {entry.get('clarifying_questions', 'No questions')[:100]}..."""
        
        base_prompt += f"""

CURRENT CONFIGURATION SUMMARY:
- Search Groups: {len(existing_config.get('search_groups', []))}
- Validation Targets: {len(existing_config.get('validation_targets', []))}
- General Notes: {existing_config.get('general_notes', 'None')[:200]}..."""
        
        # Add validation results context if available
        if latest_validation_results:
            try:
                # Extract key validation insights
                validation_summary = latest_validation_results.get('summary', {})
                overall_confidence = validation_summary.get('overall_confidence', 'Unknown')
                error_count = len(latest_validation_results.get('validation_errors', []))
                warning_count = len(latest_validation_results.get('validation_warnings', []))
                
                base_prompt += f"""

LATEST VALIDATION RESULTS CONTEXT:
This configuration was recently tested with validation. Use these results to inform your refinements:
- Overall Confidence: {overall_confidence}
- Validation Errors: {error_count}
- Validation Warnings: {warning_count}"""
                
                # Include specific error/warning patterns if present
                if error_count > 0:
                    errors = latest_validation_results.get('validation_errors', [])[:3]  # First 3 errors
                    base_prompt += f"""
- Recent Error Examples: {[err.get('message', 'Unknown error')[:100] for err in errors]}"""
                
                if warning_count > 0:
                    warnings = latest_validation_results.get('validation_warnings', [])[:3]  # First 3 warnings
                    base_prompt += f"""
- Recent Warning Examples: {[warn.get('message', 'Unknown warning')[:100] for warn in warnings]}"""
                    
            except Exception as e:
                logger.warning(f"Could not parse validation results for context: {e}")
                base_prompt += f"""

LATEST VALIDATION RESULTS: Available but could not be parsed for context"""
    
    base_prompt += f"""

USER INSTRUCTIONS: {instructions}

TASK: You must ALWAYS provide both:
1. An updated/optimized configuration (required search groups + validation targets)
2. Clarifying questions to gather more information for further improvements

Requirements:
- Update the configuration based on the instructions and table analysis
- MANDATORY: Include exactly {len(basic_info.get('column_names', []))} validation_targets (one for each column)
- Generate 2-4 specific clarifying questions that would help improve the configuration further
- Set clarification_urgency (0-1 scale): 
  * 0.0 = Configuration is solid, no clarification needed
  * 0.1-0.3 = Minor improvements possible with clarification
  * 0.4-0.6 = Moderate improvements likely with clarification  
  * 0.7-0.9 = Important columns may have suboptimal settings
  * 1.0 = Critical columns will likely be wrong without clarification
- Include your reasoning for the changes made

VALIDATION CHECKLIST - Verify your response includes:
✓ Exactly {len(basic_info.get('column_names', []))} validation_targets
✓ Each column name appears once: {', '.join(basic_info.get('column_names', []))}

Use the generate_config_and_questions tool to return both the configuration and questions."""
    
    return base_prompt

def get_unified_generation_schema() -> Dict:
    """Get the unified JSON schema that combines column config validation with AI feedback requirements."""
    # Load the base column config schema
    column_config_schema = load_column_config_schema()
    
    # Load the AI generation feedback schema
    ai_feedback_schema = load_ai_generation_schema()
    
    # Combine them - the updated_config must follow column_config_schema
    # Create a deep copy to avoid modifying the original
    updated_config_schema = json.loads(json.dumps(column_config_schema))
    updated_config_schema["description"] = "The complete updated configuration following the column_config_schema.json structure"
    
    combined_schema = {
        "type": "object",
        "properties": {
            "updated_config": updated_config_schema
        },
        "required": ["updated_config"]
    }
    
    # Add AI feedback properties
    for prop_name, prop_schema in ai_feedback_schema.get("properties", {}).items():
        combined_schema["properties"][prop_name] = prop_schema
    
    # Add AI feedback required fields (deduplicate to avoid duplicate entries)
    ai_required = ai_feedback_schema.get("required", [])
    for field in ai_required:
        if field not in combined_schema["required"]:
            combined_schema["required"].append(field)
    
    
    return combined_schema

def load_column_config_schema() -> Dict:
    """Load the base column config schema from the shared JSON file."""
    import os
    current_dir = os.path.dirname(__file__)
    
    # Try multiple possible locations for the schema file
    possible_paths = [
        # 1. Same directory as this file (deployed Lambda)
        os.path.join(current_dir, 'column_config_schema.json'),
        # 2. Lambda task root directory 
        '/var/task/column_config_schema.json',
        # 3. Relative to current working directory
        'column_config_schema.json',
        # 4. Local testing - src/ location
        os.path.join(current_dir, '..', 'src', 'column_config_schema.json'),
        # 5. Shared directory for local testing
        os.path.join(current_dir, '..', '..', 'src', 'column_config_schema.json')
    ]
    
    schema_file = None
    for path in possible_paths:
        if os.path.exists(path):
            schema_file = path
            break
    
    if not schema_file:
        # Enhanced error message with debugging info
        tried_paths = '\n'.join([f"  - {path}" for path in possible_paths])
        current_files = [f for f in os.listdir(current_dir) if f.endswith('.json')] if os.path.exists(current_dir) else []
        raise FileNotFoundError(
            f"Column config schema file not found in any of these locations:\n{tried_paths}\n"
            f"Current directory: {current_dir}\n"
            f"Files in current directory: {current_files}\n"
            f"Current working directory: {os.getcwd()}"
        )
    
    try:
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        return schema
    except Exception as e:
        logger.error(f"Failed to load column config schema {schema_file}: {e}")
        raise Exception(f"Could not load column config schema: {str(e)}")

def load_ai_generation_schema() -> Dict:
    """Load the AI generation feedback schema from the JSON file."""
    import os
    current_dir = os.path.dirname(__file__)
    schema_file = os.path.join(current_dir, 'ai_generation_schema.json')
    
    if not os.path.exists(schema_file):
        raise FileNotFoundError(f"AI generation schema file not found: {schema_file}")
    
    try:
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        return schema
    except Exception as e:
        logger.error(f"Failed to load AI generation schema {schema_file}: {e}")
        raise Exception(f"Could not load AI generation schema: {str(e)}")

def embed_user_message_in_log(existing_config: Dict, instructions: str, session_id: str) -> Dict:
    """Embed user message in conversation log before processing for refinements."""
    
    # Initialize conversation log if it doesn't exist
    if 'config_change_log' not in existing_config:
        existing_config['config_change_log'] = []
    
    # Add user message entry
    user_message_entry = {
        'timestamp': datetime.now().isoformat(),
        'action': 'user_message',
        'session_id': session_id,
        'user_instructions': instructions,
        'entry_type': 'user_input'
    }
    
    existing_config['config_change_log'].append(user_message_entry)
    return existing_config

def add_conversation_entry(updated_config: Dict, existing_config: Dict = None, 
                          instructions: str = '', clarifying_questions: str = '',
                          clarification_urgency: float = 0.0, reasoning: str = '', 
                          ai_summary: str = '', technical_ai_summary: str = '', session_id: str = 'unknown',
                          config_filename: str = None) -> Dict:
    """Add conversation entry to config change log and update metadata."""
    
    # Preserve existing change log from existing_config
    if existing_config and 'config_change_log' in existing_config:
        # Copy existing conversation history to updated config
        updated_config['config_change_log'] = existing_config['config_change_log'].copy()
        logger.info(f"Preserved {len(updated_config['config_change_log'])} existing conversation entries")
    elif 'config_change_log' not in updated_config:
        # Initialize if not present
        updated_config['config_change_log'] = []
    
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
        'model_used': 'claude-sonnet-4-0'
    }
    
    # Add config filename if provided
    if config_filename:
        conversation_entry['config_filename'] = config_filename
    
    updated_config['config_change_log'].append(conversation_entry)
    
    # Update generation metadata
    if 'generation_metadata' not in updated_config:
        updated_config['generation_metadata'] = {}
    
    updated_config['generation_metadata'].update({
        'version': current_version,
        'last_updated': datetime.now().isoformat(),
        'total_interactions': len(updated_config['config_change_log']),
        'model_used': 'claude-sonnet-4-0'
    })
    
    # Add saved filename to metadata if provided
    if config_filename:
        updated_config['generation_metadata']['saved_filename'] = config_filename
    
    return updated_config

def save_config_to_s3(generated_config: Dict, session_id: str, table_analysis: Dict = None, existing_config: Dict = None) -> Dict:
    """Save generated configuration to S3 with proper naming based on input file.
    
    Returns:
        Dict containing 's3_key' and 'filename' on success
    """
    try:
        import boto3
        import re
        
        # Upload config to S3
        s3_client = boto3.client('s3')
        bucket_name = os.environ.get('S3_CONFIG_BUCKET', 'perplexity-config-downloads')
        
        # Get the current version number
        current_version = 1
        if existing_config and 'generation_metadata' in existing_config:
            current_version = existing_config['generation_metadata'].get('version', 1) + 1
        
        # Extract base filename from table analysis
        base_filename = "unknown_table"
        if table_analysis and 'basic_info' in table_analysis:
            original_filename = table_analysis['basic_info'].get('filename', 'unknown_table')
            # Remove file extension
            base_filename = re.sub(r'\.(xlsx?|csv)$', '', original_filename, flags=re.IGNORECASE)
            # Remove any existing _config or _config_VXX suffixes
            base_filename = re.sub(r'_config(_V\d+)?$', '', base_filename, flags=re.IGNORECASE)
        
        # Create config filename with version
        config_filename = f"{base_filename}_config_V{current_version:02d}.json"
        key = f"generated_configs/{config_filename}"
        
        # Upload config as JSON
        config_json = json.dumps(generated_config, indent=2)
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=config_json,
            ContentType='application/json',
            Metadata={'session_id': session_id}
        )
        
        logger.info(f"Config uploaded to S3: {key}")
        return {
            's3_key': key,
            'filename': config_filename
        }
        
    except Exception as e:
        logger.error(f"Failed to save config to S3: {str(e)}")
        raise

def create_config_download_url(s3_key: str) -> str:
    """Create S3 download URL for the generated configuration."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = os.environ.get('S3_CONFIG_BUCKET', 'perplexity-config-downloads')
        
        # Since the bucket has public access, create direct public URL
        public_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
        
        logger.info(f"Created public download URL for S3 key: {s3_key}")
        return public_url
        
    except Exception as e:
        logger.error(f"Failed to create config download URL: {str(e)}")
        return ""

