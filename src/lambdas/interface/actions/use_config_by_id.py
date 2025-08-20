"""
Use a configuration by its config ID instead of downloading the file.
This provides secure access to configs without exposing the actual files.
"""
import logging
import json
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle_use_config_by_id(event_data, context=None):
    """
    Use a configuration by its config ID
    
    Args:
        event_data: {
            'email': 'user@example.com',
            'session_id': 'current_session_id',
            'config_id': 'session_20250819_201314_d8363961_v1_financial_portfolio'
        }
    
    Returns:
        {
            'success': True,
            'config_data': {...},
            'config_version': 1,
            'config_s3_key': 'path/to/copied_config.json',
            'config_id': 'new_config_id',
            'source_info': {
                'original_config_id': 'source_config_id',
                'original_name': 'original_name_chain'
            }
        }
    """
    try:
        email = event_data.get('email')
        session_id = event_data.get('session_id')
        config_id = event_data.get('config_id')
        
        if not all([email, session_id, config_id]):
            return create_response(400, {
                'success': False,
                'error': 'Missing required parameters: email, session_id, or config_id'
            })
        
        # Validate config_id format and sanitize
        config_id = config_id.strip()
        if not config_id or len(config_id) > 200:
            return create_response(400, {
                'success': False,
                'error': 'Invalid config_id: must be non-empty and under 200 characters'
            })
        
        # Basic email validation
        if '@' not in email or len(email) > 100:
            return create_response(400, {
                'success': False,
                'error': 'Invalid email format'
            })
        
        storage_manager = UnifiedS3Manager()
        
        # Look up the config by ID
        config_data, config_key = storage_manager.get_config_by_id(config_id, email)
        
        if not config_data:
            return create_response(404, {
                'success': False,
                'error': f'Configuration not found for ID: {config_id}'
            })
        
        logger.info(f"Found config by ID {config_id}: {config_key}")
        
        # Extract source metadata
        source_metadata = config_data.get('storage_metadata', {})
        original_name = source_metadata.get('original_name') or config_id
        source_session = source_metadata.get('session_id')
        source_description = source_metadata.get('description', config_data.get('general_notes', ''))
        
        # Clean the config data for copying
        clean_config_data = config_data.copy()
        if 'storage_metadata' in clean_config_data:
            del clean_config_data['storage_metadata']
        
        # Get current config version for the target session
        existing_config, _ = storage_manager.get_latest_config(email, session_id)
        version = 1
        if existing_config and existing_config.get('storage_metadata', {}).get('version'):
            version = existing_config['storage_metadata']['version'] + 1
        
        # Store the config in the current session with usage timestamp
        usage_timestamp = datetime.now().isoformat()
        storage_result = storage_manager.store_config_file(
            email=email, 
            session_id=session_id, 
            config_data=clean_config_data, 
            version=version, 
            source='used_by_id',
            description=source_description,
            original_name=original_name,  # Preserve original name chain
            source_session=source_session,
            usage_timestamp=usage_timestamp  # Record when this config was applied
        )
        
        if not storage_result['success']:
            return create_response(500, {
                'success': False,
                'error': f'Failed to store config: {storage_result["error"]}'
            })
        
        # Update session info
        try:
            table_name = f"table_{session_id.split('_')[-1]}"
            session_info_result = storage_manager.create_session_info(
                email=email,
                session_id=session_id,
                table_name=table_name,
                current_config_version=version,
                config_source='used_by_id',
                source_session=source_session,
                config_id=storage_result.get('config_id'),
                config_description=source_description
            )
            if session_info_result['success']:
                logger.info(f"Session info updated with config ID usage tracking")
        except Exception as e:
            logger.warning(f"Failed to update session info: {e}")
        
        logger.info(f"Successfully applied config ID {config_id} to session {session_id}")
        
        return create_response(200, {
            'success': True,
            'config_data': clean_config_data,
            'config_version': version,
            'config_s3_key': storage_result['s3_key'],
            'config_id': storage_result.get('config_id'),
            'source_info': {
                'original_config_id': config_id,
                'original_name': original_name,
                'source_session': source_session,
                'applied_at': datetime.now().isoformat()
            },
            'message': f'Configuration {config_id} successfully applied'
        })
        
    except Exception as e:
        logger.error(f"Use config by ID error: {e}")
        return create_response(500, {
            'success': False,
            'error': str(e)
        })