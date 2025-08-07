"""
Copy a matching configuration to the current session with proper source tracking.
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

def handle_copy_config(event_data, context=None):
    """
    Copy a config from another session to the current session
    
    Args:
        event_data: {
            'email': 'user@example.com',
            'session_id': 'current_session_id',
            'source_config_key': 's3_key_of_source_config',
            'source_session': 'source_session_id'
        }
    
    Returns:
        {
            'success': True,
            'config_data': {...},
            'config_version': 1,
            'config_s3_key': 'path/to/copied_config.json',
            'download_url': 'https://...',
            'source_info': {
                'source_session': 'session_id',
                'source_key': 's3_key'
            }
        }
    """
    try:
        email = event_data.get('email')
        session_id = event_data.get('session_id')
        source_config_key = event_data.get('source_config_key')
        source_session = event_data.get('source_session')
        
        if not all([email, session_id, source_config_key]):
            return create_response(400, {
                'success': False,
                'error': 'Missing required parameters: email, session_id, or source_config_key'
            })
        
        storage_manager = UnifiedS3Manager()
        
        # Download the source config
        try:
            response = storage_manager.s3_client.get_object(
                Bucket=storage_manager.bucket_name, 
                Key=source_config_key
            )
            source_config_data = json.loads(response['Body'].read().decode('utf-8'))
            logger.info(f"Successfully retrieved source config: {source_config_key}")
        except Exception as e:
            logger.error(f"Failed to retrieve source config {source_config_key}: {e}")
            return create_response(404, {
                'success': False,
                'error': f'Source configuration not found: {str(e)}'
            })
        
        # Remove storage metadata from source config to avoid conflicts
        if 'storage_metadata' in source_config_data:
            del source_config_data['storage_metadata']
        
        # Get current config version for the target session
        existing_config, _ = storage_manager.get_latest_config(email, session_id)
        version = 1
        if existing_config and existing_config.get('storage_metadata', {}).get('version'):
            version = existing_config['storage_metadata']['version'] + 1
        
        # Store the copied config in the current session
        storage_result = storage_manager.store_config_file(
            email=email, 
            session_id=session_id, 
            config_data=source_config_data, 
            version=version, 
            source='copied_from_previous'
        )
        
        if not storage_result['success']:
            return create_response(500, {
                'success': False,
                'error': f'Failed to store copied config: {storage_result["error"]}'
            })
        
        # Update session info with source tracking
        try:
            table_name = f"table_{session_id.split('_')[-1]}"
            session_info_result = storage_manager.create_session_info(
                email=email,
                session_id=session_id,
                table_name=table_name,
                current_config_version=version,
                config_source='copied_from_previous',
                source_session=source_session
            )
            if session_info_result['success']:
                logger.info(f"Session info updated with copied config tracking")
        except Exception as e:
            logger.warning(f"Failed to update session info: {e}")
        
        # Create download link for the copied config
        download_url = storage_manager.create_public_download_link(
            source_config_data, 
            f"config_copied_from_{source_session or 'unknown'}_{datetime.now().strftime('%Y%m%d')}.json"
        )
        
        logger.info(f"Successfully copied config from {source_config_key} to session {session_id}")
        
        return create_response(200, {
            'success': True,
            'config_data': source_config_data,
            'config_version': version,
            'config_s3_key': storage_result['s3_key'],
            'download_url': download_url,
            'source_info': {
                'source_session': source_session,
                'source_key': source_config_key,
                'copied_at': datetime.now().isoformat()
            },
            'message': f'Configuration successfully copied from previous session'
        })
        
    except Exception as e:
        logger.error(f"Copy config error: {e}")
        return create_response(500, {
            'success': False,
            'error': str(e)
        })