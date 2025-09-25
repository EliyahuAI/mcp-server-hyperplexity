"""
Get AI summary information from stored configuration files.
This is useful when configurations are loaded from S3 and the AI summary questions
were not passed back after generation or refinement.
"""
import logging
import json
from typing import Dict, Any, List, Optional

from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle_get_ai_summary(event_data, context=None):
    """
    Get AI summary information from stored configurations
    
    Args:
        event_data: {
            'email': 'user@example.com',
            'session_id': 'current_session_id',
            'config_id': 'optional_specific_config_id'  # If not provided, gets latest config
        }
    
    Returns:
        {
            'success': True,
            'ai_summary': 'Latest AI summary text',
            'technical_ai_summary': 'Technical details (when available)',
            'config_version': 1,
            'conversation_history': [
                {
                    'timestamp': '2025-01-01T12:00:00',
                    'ai_summary': 'summary text',
                    'instructions': 'user instructions',
                    'version': 1
                }
            ]
        }
    """
    try:
        email = event_data.get('email')
        session_id = event_data.get('session_id')
        config_id = event_data.get('config_id')  # Optional
        
        if not all([email, session_id]):
            return create_response(400, {
                'success': False,
                'error': 'Missing required parameters: email and session_id'
            })
        
        # Basic email validation
        if '@' not in email or len(email) > 100:
            return create_response(400, {
                'success': False,
                'error': 'Invalid email format'
            })
        
        storage_manager = UnifiedS3Manager()
        
        # Get configuration data
        if config_id:
            # Get specific config by ID
            config_data, config_key = storage_manager.get_config_by_id(config_id, email)
            if not config_data:
                return create_response(404, {
                    'success': False,
                    'error': f'Configuration not found for ID: {config_id}'
                })
            logger.info(f"Found config by ID {config_id}: {config_key}")
        else:
            # Get latest config for this session
            config_data, config_key = storage_manager.get_latest_config(email, session_id)
            if not config_data:
                return create_response(404, {
                    'success': False,
                    'error': f'No configuration found for session: {session_id}'
                })
            logger.info(f"Found latest config for session {session_id}: {config_key}")
        
        # Extract AI summary information
        current_ai_summary = ""
        technical_ai_summary = ""
        config_version = config_data.get('storage_metadata', {}).get('version', 1)
        
        # Check for current AI summary fields
        if 'ai_summary' in config_data:
            current_ai_summary = config_data['ai_summary']
        
        if 'technical_ai_summary' in config_data:
            technical_ai_summary = config_data['technical_ai_summary']
        
        # Extract conversation history with AI summaries
        conversation_history = []
        config_change_log = config_data.get('config_change_log', [])
        
        for entry in config_change_log:
            if 'ai_summary' in entry:
                history_entry = {
                    'timestamp': entry.get('timestamp', ''),
                    'ai_summary': entry.get('ai_summary', ''),
                    'instructions': entry.get('instructions', ''),
                    'version': entry.get('version', 0),
                    'action': entry.get('action', 'unknown')
                }
                
                # Include technical summary if available
                if 'technical_ai_summary' in entry:
                    history_entry['technical_ai_summary'] = entry['technical_ai_summary']
                
                conversation_history.append(history_entry)
        
        # If no current AI summary, try to get the most recent one from conversation history
        if not current_ai_summary and conversation_history:
            # Sort by timestamp descending to get latest
            conversation_history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            current_ai_summary = conversation_history[0].get('ai_summary', '')
            technical_ai_summary = conversation_history[0].get('technical_ai_summary', '')
        
        # Get clarifying questions if available
        clarifying_questions = config_data.get('clarifying_questions', '')
        clarification_urgency = config_data.get('clarification_urgency', 0)

        # DEBUG: Log clarifying questions search
        logger.info(f"🔍 GET_AI_SUMMARY_DEBUG: Config data keys: {list(config_data.keys())}")
        logger.info(f"🔍 GET_AI_SUMMARY_DEBUG: Clarifying questions found: {bool(clarifying_questions)}")
        if clarifying_questions:
            logger.info(f"🔍 GET_AI_SUMMARY_DEBUG: Questions length: {len(clarifying_questions)}")
            logger.info(f"🔍 GET_AI_SUMMARY_DEBUG: Questions preview: {clarifying_questions[:200]}...")

        # Also check in change log entries
        if not clarifying_questions and config_change_log:
            logger.info(f"🔍 GET_AI_SUMMARY_DEBUG: No direct questions, checking {len(config_change_log)} change log entries")
            for i, entry in enumerate(config_change_log):
                if 'clarifying_questions' in entry and entry['clarifying_questions']:
                    logger.info(f"🔍 GET_AI_SUMMARY_DEBUG: Found questions in change log entry {i}: {len(entry['clarifying_questions'])} chars")
                    clarifying_questions = entry['clarifying_questions']
                    clarification_urgency = entry.get('clarification_urgency', 0)
                    break

        logger.info(f"Successfully retrieved AI summary for session {session_id}, version {config_version}")
        
        response_data = {
            'success': True,
            'ai_summary': current_ai_summary,
            'config_version': config_version,
            'conversation_history': conversation_history,
            'session_id': session_id
        }
        
        # Add optional fields if they exist
        if technical_ai_summary:
            response_data['technical_ai_summary'] = technical_ai_summary
        
        if clarifying_questions:
            response_data['clarifying_questions'] = clarifying_questions
            response_data['clarification_urgency'] = clarification_urgency
        
        if config_id:
            response_data['config_id'] = config_id
        
        return create_response(200, response_data)
        
    except Exception as e:
        logger.error(f"Get AI summary error: {e}")
        return create_response(500, {
            'success': False,
            'error': str(e)
        })


def handle_get_ai_summary_by_config_id(event_data, context=None):
    """
    Convenience wrapper to get AI summary by config ID only
    """
    config_id = event_data.get('config_id')
    email = event_data.get('email')
    
    if not config_id or not email:
        return create_response(400, {
            'success': False,
            'error': 'Missing required parameters: config_id and email'
        })
    
    # Use a dummy session_id since we're looking up by config_id
    event_data['session_id'] = 'lookup_by_id'
    return handle_get_ai_summary(event_data, context)