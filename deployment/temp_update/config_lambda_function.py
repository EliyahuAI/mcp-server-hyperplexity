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
from ai_api_client import ai_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for configuration generation requests."""
    try:
        logger.info("=== CONFIG LAMBDA STARTED ===")
        logger.info(f"Event: {json.dumps(event, indent=2)}")
        
        # Extract request parameters
        table_analysis = event.get('table_analysis')
        generation_mode = event.get('generation_mode', 'automatic')
        conversation_id = event.get('conversation_id')
        user_message = event.get('user_message', '')
        session_id = event.get('session_id', 'unknown')
        excel_s3_key = event.get('excel_s3_key')
        
        if not table_analysis and not excel_s3_key:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'success': False,
                    'error': 'Missing table_analysis or excel_s3_key in request'
                })
            }
        
        # If we have excel_s3_key but no table_analysis, analyze the table
        if excel_s3_key and not table_analysis:
            logger.info(f"Analyzing table from S3: {excel_s3_key}")
            try:
                from shared_table_parser import s3_table_parser
                bucket = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
                table_analysis = s3_table_parser.analyze_table_structure(bucket, excel_s3_key)
            except Exception as e:
                logger.error(f"Failed to analyze table: {str(e)}")
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'success': False,
                        'error': f'Table analysis failed: {str(e)}'
                    })
                }
        
        logger.info(f"Config generation for session: {session_id}, mode: {generation_mode}")
        
        # Process the config generation request
        if generation_mode == 'automatic':
            result = asyncio.run(generate_config_automatic(
                table_analysis, session_id
            ))
        else:  # interview mode
            result = asyncio.run(generate_config_interview(
                table_analysis, session_id, 
                conversation_id, user_message
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

async def generate_config_automatic(table_analysis: Dict, session_id: str) -> Dict:
    """Generate configuration automatically using Claude."""
    try:
        # Build the config generation prompt
        prompt = build_config_generation_prompt(table_analysis, mode='automatic')
        
        # Call Claude using shared client
        result = await ai_client.call_structured_api(
            prompt=prompt,
            schema=get_config_generation_schema(),
            model="claude-3-5-sonnet-20241022",
            tool_name="generate_config",
            context=f"session_{session_id}"
        )
        
        # Extract generated config from response
        generated_config = ai_client.extract_structured_response(result['response'], "generate_config")
        ai_response = 'Configuration generated automatically using AI analysis'
        
        # Save config to S3 and return the key
        try:
            config_s3_key = save_config_to_s3(generated_config, session_id)
            
            return {
                'success': True,
                'generated_config': generated_config,
                'generated_config_s3_key': config_s3_key,
                'ai_response': ai_response,
                'session_id': session_id,
                'generation_mode': 'automatic'
            }
            
        except Exception as s3_error:
            logger.error(f"Failed to save config to S3: {str(s3_error)}")
            # Still return the config even if S3 save fails
            return {
                'success': True,
                'generated_config': generated_config,
                'ai_response': ai_response,
                'session_id': session_id,
                'generation_mode': 'automatic'
            }
        
    except Exception as e:
        logger.error(f"Automatic config generation failed: {str(e)}")
        return {
            'success': False,
            'error': f'Automatic generation failed: {str(e)}',
            'session_id': session_id
        }

async def generate_config_interview(table_analysis: Dict, session_id: str,
                                  conversation_id: str = None, user_message: str = '') -> Dict:
    """Generate configuration through interview mode."""
    try:
        if not conversation_id:
            # Start new conversation
            prompt = build_config_generation_prompt(table_analysis, mode='interview_start')
        else:
            # Continue conversation
            prompt = build_config_generation_prompt(
                table_analysis, mode='interview_continue', 
                conversation_id=conversation_id, user_message=user_message
            )
        
        # Call Claude using shared client
        result = await ai_client.call_text_api(
            prompt=prompt,
            model="claude-3-5-sonnet-20241022",
            context=f"session_{session_id}_interview"
        )
        
        ai_response = ai_client.extract_text_response(result['response'])
        current_conversation_id = conversation_id or f"conv_{session_id}"
        
        # Check if this response contains a complete config
        generated_config = None
        try:
            # Try to extract config from the response if it's complete
            if "final_config" in ai_response.lower() or "configuration:" in ai_response.lower():
                # Attempt to parse a complete config from the response
                generated_config = extract_config_from_text_response(ai_response)
        except:
            pass  # No complete config yet
        
        # Save config to S3 if complete
        config_s3_key = None
        if generated_config:
            try:
                config_s3_key = save_config_to_s3(generated_config, session_id)
            except Exception as s3_error:
                logger.error(f"Failed to save config to S3: {str(s3_error)}")
        
        # For interview mode, we might not have a complete config yet
        return {
            'success': True,
            'ai_response': ai_response,
            'conversation_id': current_conversation_id,
            'session_id': session_id,
            'generation_mode': 'interview',
            'generated_config': generated_config,  # May be None if not complete
            'generated_config_s3_key': config_s3_key  # May be None if not complete
        }
        
    except Exception as e:
        logger.error(f"Interview config generation failed: {str(e)}")
        return {
            'success': False,
            'error': f'Interview generation failed: {str(e)}',
            'session_id': session_id
        }

def build_config_generation_prompt(table_analysis: Dict, mode: str = 'automatic',
                                 conversation_id: str = None, user_message: str = '') -> str:
    """Build config generation prompt based on table analysis."""
    
    basic_info = table_analysis.get('basic_info', {})
    column_analysis = table_analysis.get('column_analysis', {})
    domain_info = table_analysis.get('domain_info', {})
    
    base_prompt = f"""
You are an expert in data validation and configuration generation for the pharmaceutical industry.

TABLE ANALYSIS:
- File: {basic_info.get('filename', 'Unknown')}
- Size: {basic_info.get('shape', [0, 0])[0]} rows × {basic_info.get('shape', [0, 0])[1]} columns
- Domain: {domain_info.get('likely_domain', 'general')} (confidence: {domain_info.get('confidence', 0)})

COLUMN DETAILS:
"""
    
    for col_name, col_info in column_analysis.items():
        sample_values = col_info.get('sample_values', [])[:3]
        base_prompt += f"""
{col_name}:
  - Type: {col_info.get('data_type', 'Unknown')}
  - Fill Rate: {col_info.get('fill_rate', 0):.1%}
  - Sample Values: {sample_values}
"""
    
    if mode == 'automatic':
        base_prompt += """

TASK: Generate a complete validation configuration for this table. Focus on:
1. Appropriate validation rules for each column based on its data type and samples
2. Proper importance levels (ID, CRITICAL, HIGH, MEDIUM, LOW) 
3. Logical search groupings for related columns
4. Domain-specific validation patterns

Use the generate_config tool to return a properly structured configuration.
"""
    
    elif mode == 'interview_start':
        base_prompt += """

TASK: Start an interactive interview to help create a custom validation configuration.
Ask 2-3 specific questions about:
1. The most critical columns for validation
2. Business rules or constraints for key fields
3. Any specific validation requirements

Keep questions focused and practical. Don't ask about every column - focus on the most important ones.
"""
    
    elif mode == 'interview_continue':
        base_prompt += f"""

PREVIOUS CONVERSATION ID: {conversation_id}

USER RESPONSE: {user_message}

TASK: Continue the interview based on the user's response. Either:
1. Ask follow-up questions to clarify requirements, OR
2. Generate the final configuration if you have enough information

If generating final config, use the generate_config tool.
"""
    
    return base_prompt

def get_config_generation_schema() -> Dict:
    """Get the JSON schema for config generation."""
    return {
        "type": "object",
        "properties": {
            "general_notes": {
                "type": "string",
                "description": "General notes about the validation configuration"
            },
            "validation_targets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string"},
                        "description": {"type": "string"},
                        "importance": {"type": "string", "enum": ["ID", "CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                        "format": {"type": "string"},
                        "notes": {"type": "string"},
                        "examples": {"type": "array", "items": {"type": "string"}},
                        "search_group": {"type": "integer"},
                        "preferred_model": {"type": "string"},
                        "search_context_size": {"type": "string", "enum": ["low", "high"]}
                    },
                    "required": ["column", "description", "importance", "format", "examples", "search_group"]
                }
            }
        },
        "required": ["general_notes", "validation_targets"]
    }

def save_config_to_s3(generated_config: Dict, session_id: str) -> str:
    """Save generated configuration to S3 and return the key."""
    try:
        import boto3
        
        # Upload config to S3
        s3_client = boto3.client('s3')
        bucket_name = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
        
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
        
        logger.info(f"Config uploaded to S3: {key}")
        return key
        
    except Exception as e:
        logger.error(f"Failed to save config to S3: {str(e)}")
        raise

def create_config_download_url(s3_key: str) -> str:
    """Create S3 download URL for the generated configuration."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
        
        # Generate presigned URL (valid for 1 hour)
        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': s3_key},
            ExpiresIn=3600
        )
        
        logger.info(f"Created download URL for S3 key: {s3_key}")
        return download_url
        
    except Exception as e:
        logger.error(f"Failed to create config download URL: {str(e)}")
        return ""

def extract_config_from_text_response(text_response: str) -> Dict:
    """Extract configuration from text response (for interview mode)."""
    try:
        # Look for JSON-like structures in the text
        import re
        
        # Try to find JSON blocks
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text_response, re.DOTALL)
        
        for match in matches:
            try:
                config = json.loads(match)
                # Validate that it looks like a config
                if 'columns' in config or 'validation_targets' in config:
                    return config
            except json.JSONDecodeError:
                continue
        
        # If no valid JSON found, return None
        return None
        
    except Exception as e:
        logger.error(f"Failed to extract config from text: {str(e)}")
        return None