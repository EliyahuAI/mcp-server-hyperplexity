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

# Configure logging BEFORE importing ai_api_client
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True  # Force reconfiguration
)

# Import after logging setup
from ai_api_client import ai_client

# Get logger for this module
logger = logging.getLogger(__name__)

# Also ensure ai_api_client logger is set to INFO
logging.getLogger('ai_api_client').setLevel(logging.INFO)

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

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for configuration generation requests."""
    try:
        logger.info("=== CONFIG LAMBDA STARTED ===")
        logger.info(f"Event: {json.dumps(event, indent=2)}")
        
        # Extract request parameters
        table_analysis = event.get('table_analysis')
        existing_config = event.get('existing_config')  # Optional
        instructions = event.get('instructions', 'Generate an optimal configuration for this data validation scenario')
        session_id = event.get('session_id', 'unknown')
        
        # Conversation history preservation parameters
        preserve_conversation_history = event.get('preserve_conversation_history', False)
        conversation_history = event.get('conversation_history', [])
        
        logger.info(f"Config lambda parameters:")
        logger.info(f"- Session ID: {session_id}")
        logger.info(f"- Has existing_config: {existing_config is not None}")
        logger.info(f"- Preserve conversation: {preserve_conversation_history}")
        logger.info(f"- Conversation history entries: {len(conversation_history)}")
        
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
            try:
                from shared_table_parser import s3_table_parser
                # Use unified bucket if available
                bucket = os.environ.get('S3_UNIFIED_BUCKET', os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache'))
                
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
        
        # Process the config generation request (single unified mode)
        result = asyncio.run(generate_config_unified(
            table_analysis, existing_config, instructions, session_id, conversation_history
        ))
        
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
                                 conversation_history: list = None) -> Dict:
    """Unified config generation - always returns both updated config and clarifying questions."""
    try:
        # Build the unified generation prompt
        prompt = build_unified_generation_prompt(table_analysis, existing_config, instructions)
        
        # Call Claude using shared client with unified schema
        # Note: Empty context allows cache hits across sessions with same table analysis
        config_settings = load_config_settings()
        result = await ai_client.call_structured_api(
            prompt=prompt,
            schema=get_unified_generation_schema(),
            model=config_settings.get('model', 'claude-opus-4-1'),
            tool_name="generate_config_and_questions",
            context="",
            max_tokens=config_settings.get('max_tokens', 16000),
            max_web_searches=0
        )
        
        # Debug logging
        logger.info(f"AI API result type: {type(result)}")
        logger.info(f"AI API result keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}")
        
        # More detailed debugging
        if isinstance(result, str):
            logger.error(f"ERROR: AI API returned string instead of dict: {result[:200]}...")
            raise TypeError("AI API returned string instead of expected dictionary response")
        
        # Check if result is the response directly or wrapped
        if isinstance(result, dict) and 'response' in result:
            response = result['response']
            logger.info(f"Response type: {type(response)}")
            logger.info(f"Response keys: {response.keys() if isinstance(response, dict) else 'Not a dict'}")
        else:
            response = result
        
        # Additional check after unwrapping - response might be a string
        if isinstance(response, str):
            logger.error(f"ERROR: Response is a string instead of dict: {response[:200]}...")
            raise TypeError("AI API response is a string instead of expected dictionary")
            
        # Extract response data
        try:
            response_data = ai_client.extract_structured_response(response, "generate_config_and_questions")
        except Exception as e:
            logger.error(f"Failed to extract structured response: {str(e)}")
            logger.error(f"Response was: {json.dumps(response, indent=2) if isinstance(response, dict) else response}")
            raise
        
        # Get the updated config and add conversation tracking
        updated_config = response_data.get('updated_config')
        clarifying_questions = response_data.get('clarifying_questions', '')
        clarification_urgency = response_data.get('clarification_urgency', 0.0)
        ai_summary = response_data.get('ai_summary', '')
        technical_ai_summary = response_data.get('technical_ai_summary', '')
        
        # Add conversation entry to config change log
        if updated_config:
            updated_config = add_conversation_entry(
                updated_config, existing_config, instructions, 
                clarifying_questions, clarification_urgency, ai_summary, technical_ai_summary, session_id,
                conversation_history
            )
        
        # Save config to both S3 buckets
        config_s3_key = None
        download_url = None
        try:
            if updated_config:
                # Save to cache bucket for internal use
                config_s3_key = save_config_to_cache(updated_config, session_id)
                
                # Save to download bucket for public access
                download_s3_key = save_config_to_downloads(updated_config, session_id)
                
                if download_s3_key:
                    # Create download URL for the public bucket
                    download_url = create_config_download_url(download_s3_key)
        except Exception as s3_error:
            logger.error(f"Failed to save config to S3: {str(s3_error)}")
        
        return {
            'success': True,
            'updated_config': updated_config,
            'clarifying_questions': clarifying_questions,
            'clarification_urgency': clarification_urgency,
            'ai_summary': ai_summary,
            'technical_ai_summary': technical_ai_summary,
            'config_s3_key': config_s3_key,
            'download_url': download_url,
            'session_id': session_id
        }
        
    except TypeError as e:
        error_msg = str(e)
        logger.error(f"[ERROR] Type error in config generation: {error_msg}")
        
        # Provide user-friendly error message for string response issues
        if "string indices must be integers" in error_msg or "AI API response is a string" in error_msg:
            return {
                'success': False,
                'error': 'The AI returned an unexpected format. This can happen when the request is too complex. Please try simplifying your instructions or breaking them into smaller steps.',
                'error_type': 'format_error',
                'error_details': error_msg,
                'session_id': session_id,
                'retry_suggestion': 'Try providing more specific instructions or use simpler language.'
            }
        
        return {
            'success': False,
            'error': f'Configuration format error: {error_msg}',
            'error_type': 'type_error',
            'session_id': session_id
        }
        
    except Exception as e:
        error_msg = str(e)
        if "overloaded" in error_msg.lower() and "529" in error_msg:
            logger.error(f"[ERROR] Claude API overloaded - unified config generation failed: {error_msg}")
            return {
                'success': False,
                'error': 'Claude API is currently overloaded. Please try again in a few moments.',
                'error_type': 'api_overloaded',
                'session_id': session_id
            }
        else:
            logger.error(f"Unified config generation failed: {error_msg}")
            return {
                'success': False,
                'error': f'Config generation failed: {error_msg}',
                'error_type': 'general_error',
                'session_id': session_id
            }

def build_unified_generation_prompt(table_analysis: Dict, existing_config: Dict = None, 
                                  instructions: str = '') -> str:
    """Build unified prompt for config generation that always returns both config and questions."""
    
    basic_info = table_analysis.get('basic_info', {})
    column_analysis = table_analysis.get('column_analysis', {})
    domain_info = table_analysis.get('domain_info', {})
    
    # Safely extract shape information
    shape = basic_info.get('shape', [0, 0])
    if isinstance(shape, (list, tuple)) and len(shape) >= 2:
        rows, cols = shape[0], shape[1]
    else:
        rows, cols = 0, 0
        logger.warning(f"Invalid shape format: {shape} (type: {type(shape)})")
    
    base_prompt = f"""You are an expert in data validation and configuration generation for the pharmaceutical industry.

TABLE ANALYSIS:
- File: {basic_info.get('filename', 'Unknown')}
- Size: {rows} rows × {cols} columns
- Domain: {domain_info.get('likely_domain', 'general')} (confidence: {domain_info.get('confidence', 0)})

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
        if change_log:
            base_prompt += f"""

EXISTING CONFIGURATION:
This configuration has been iteratively improved through {len(change_log)} previous interactions.

Current version: {existing_config.get('generation_metadata', {}).get('version', 1)}

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
    
    base_prompt += f"""

USER INSTRUCTIONS: {instructions}

TASK: You must ALWAYS provide both:
1. An updated/optimized configuration (required search groups + validation targets)
2. Clarifying questions to gather more information for further improvements

Requirements:
- Update the configuration based on the instructions and table analysis
- Generate 2-4 specific clarifying questions that would help improve the configuration further
- Set clarification_urgency (0-1 scale): 
  * 0.0 = Configuration is solid, no clarification needed
  * 0.1-0.3 = Minor improvements possible with clarification
  * 0.4-0.6 = Moderate improvements likely with clarification  
  * 0.7-0.9 = Important columns may have suboptimal settings
  * 1.0 = Critical columns will likely be wrong without clarification
- Include clear explanations in your ai_summary

Use the generate_config_and_questions tool to return both the configuration and questions."""
    
    return base_prompt

def get_unified_generation_schema() -> Dict:
    """Get the unified JSON schema for AI config generation."""
    import os
    
    # Load the AI generation schema which already includes the full structure
    ai_schema_file = os.path.join(os.path.dirname(__file__), 'ai_generation_schema.json')
    logger.info(f"Looking for schema at: {ai_schema_file}")
    logger.info(f"File exists: {os.path.exists(ai_schema_file)}")
    
    if not os.path.exists(ai_schema_file):
        raise FileNotFoundError(f"AI generation schema file not found: {ai_schema_file}")
    
    try:
        with open(ai_schema_file, 'r') as f:
            schema = json.load(f)
        
        logger.info(f"Successfully loaded AI generation schema with {len(schema.get('properties', {}))} root properties")
        # Log the schema being used for debugging
        schema_str = json.dumps(schema)
        logger.info(f"Schema contains minItems: {'minItems' in schema_str}")
        logger.info(f"Schema contains minimum: {'minimum' in schema_str}")
        logger.info(f"Schema contains maximum: {'maximum' in schema_str}")
        return schema
        
    except Exception as e:
        logger.error(f"Error loading schema file: {str(e)}")
        raise Exception(f"Failed to load AI generation schema: {str(e)}")

def add_conversation_entry(updated_config: Dict, existing_config: Dict = None, 
                          instructions: str = '', clarifying_questions: str = '',
                          clarification_urgency: float = 0.0, ai_summary: str = '', 
                          technical_ai_summary: str = '', session_id: str = 'unknown', 
                          conversation_history: list = None) -> Dict:
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
        'ai_summary': ai_summary,
        'technical_ai_summary': technical_ai_summary,
        'version': current_version,
        'model_used': 'claude-opus-4-1'
    }
    
    updated_config['config_change_log'].append(conversation_entry)
    
    # Update generation metadata
    if 'generation_metadata' not in updated_config:
        updated_config['generation_metadata'] = {}
    
    updated_config['generation_metadata'].update({
        'version': current_version,
        'last_updated': datetime.now().isoformat(),
        'total_interactions': len(updated_config['config_change_log']),
        'model_used': 'claude-opus-4-1'
    })
    
    return updated_config

def save_config_to_downloads(generated_config: Dict, session_id: str) -> str:
    """Save generated configuration to S3 and return the key."""
    try:
        import boto3
        
        # Upload config to S3 download bucket (public access)
        s3_client = boto3.client('s3')
        
        # Use unified download bucket structure if available
        if os.environ.get('S3_UNIFIED_BUCKET'):
            bucket_name = os.environ.get('S3_DOWNLOAD_BUCKET', os.environ.get('S3_UNIFIED_BUCKET'))
            # Create unique filename with unified structure
            import uuid
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            download_uuid = str(uuid.uuid4())
            key = f"downloads/{download_uuid}/config_{session_id}_{timestamp}.json"
        else:
            # Legacy structure
            bucket_name = os.environ.get('S3_CONFIG_BUCKET', 'perplexity-config-downloads')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            key = f"generated_configs/{session_id}_{timestamp}.json"
        
        # Upload config as JSON
        config_json = json.dumps(generated_config, indent=2)
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=config_json,
            ContentType='application/json',
            Metadata={'session_id': session_id}
        )
        
        logger.info(f"Config uploaded to downloads bucket: {key}")
        return key
        
    except Exception as e:
        logger.error(f"Failed to save config to downloads bucket: {str(e)}")
        raise

def save_config_to_cache(generated_config: Dict, session_id: str) -> str:
    """Save generated configuration to cache bucket for internal use."""
    try:
        import boto3
        
        # Upload config to S3 cache bucket (internal use)
        s3_client = boto3.client('s3')
        # Use unified bucket if available
        bucket_name = os.environ.get('S3_UNIFIED_BUCKET', os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache'))
        
        # Create unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        key = f"generated_configs/{session_id}_{timestamp}.json"
        
        # Upload config as JSON
        config_json = json.dumps(generated_config, indent=2)
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=config_json,
            ContentType='application/json',
            Metadata={'session_id': session_id}
        )
        
        logger.info(f"Config uploaded to cache bucket: {key}")
        return key
        
    except Exception as e:
        logger.error(f"Failed to save config to cache bucket: {str(e)}")
        raise

def create_config_download_url(s3_key: str) -> str:
    """Create S3 download URL for the generated configuration."""
    try:
        import boto3
        
        # Use unified download bucket if available
        bucket_name = os.environ.get('S3_DOWNLOAD_BUCKET', os.environ.get('S3_CONFIG_BUCKET', 'perplexity-config-downloads'))
        
        # Since the bucket has public access, create direct public URL
        download_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
        
        logger.info(f"=== DOWNLOAD URL DEBUG ===")
        logger.info(f"Input S3 key: {s3_key}")
        logger.info(f"S3 cache bucket: {bucket_name}")
        logger.info(f"Generated presigned URL: {download_url}")
        
        return download_url
        
    except Exception as e:
        logger.error(f"Failed to create config download URL: {str(e)}")
        return ""

