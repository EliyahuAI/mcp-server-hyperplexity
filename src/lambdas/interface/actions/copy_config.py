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

def copy_config_to_session(email: str, session_id: str, config_data: Dict[str, Any], source_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Direct function to copy config data to a session (for auto-selection)
    
    Args:
        email: Target user email
        session_id: Target session ID  
        config_data: Config data to copy
        source_info: Source metadata
    
    Returns:
        {'success': bool, 'version': int, 'config_s3_key': str, 'config_id': str, ...}
    """
    try:
        storage_manager = UnifiedS3Manager()
        
        # Extract original metadata before cleaning
        source_metadata = config_data.get('storage_metadata', {})
        original_name = source_metadata.get('original_name') or source_metadata.get('config_id')
        source_session = source_info.get('source_session') or source_metadata.get('session_id')
        source_description = source_metadata.get('description', config_data.get('general_notes', ''))
        
        # Extract original filename for preservation - check multiple sources
        source_filename = source_info.get('source_filename') or source_info.get('config_filename')
        if not source_filename and source_info.get('source_config_key'):
            source_filename = Path(source_info['source_config_key']).name
        
        # If still no filename, try to get it from the original_name metadata
        if not source_filename and original_name:
            # If original_name looks like a filename, use it
            if '.' in original_name:
                source_filename = original_name
            else:
                # Generate filename from original_name
                source_filename = f"{original_name}.json"
        
        # Keep all config data including metadata
        clean_config_data = config_data.copy()
        
        # Get current config version for the target session
        existing_config, _ = storage_manager.get_latest_config(email, session_id)
        version = 1
        if existing_config and existing_config.get('storage_metadata', {}).get('version'):
            version = existing_config['storage_metadata']['version'] + 1
        
        # Store the copied config with preserved original_name chain and filename
        storage_result = storage_manager.store_config_file(
            email=email, 
            session_id=session_id, 
            config_data=clean_config_data, 
            version=version, 
            source=f"auto_copied_{source_session}",
            description=source_description,
            original_name=original_name,  # Preserve original name chain
            source_session=source_session,
            preserve_original_filename=source_filename  # Keep exact filename
        )
        
        if storage_result['success']:
            logger.info(f"Auto-copied config to {email}/{session_id} v{version}, preserving original_name: {original_name}")
            return {
                'success': True,
                'version': version,
                'config_s3_key': storage_result.get('s3_key'),
                'config_id': storage_result.get('config_id'),
                'source_info': source_info,
                'original_name': original_name
            }
        else:
            return {'success': False, 'error': storage_result.get('error', 'Storage failed')}
            
    except Exception as e:
        logger.error(f"Failed to copy config to session: {e}")
        return {'success': False, 'error': str(e)}

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
        
        # Extract original metadata before cleaning
        source_metadata = source_config_data.get('storage_metadata', {})
        original_name = source_metadata.get('original_name') or source_metadata.get('config_id')
        source_description = source_metadata.get('description', source_config_data.get('general_notes', ''))
        
        # Extract original filename from S3 key for preservation
        original_filename = Path(source_config_key).name if source_config_key else None
        
        # If no filename from S3 key, try to get it from the original_name metadata
        if not original_filename and original_name:
            # If original_name looks like a filename, use it
            if '.' in original_name:
                original_filename = original_name
            else:
                # Generate filename from original_name
                original_filename = f"{original_name}.json"
        
        # Keep all config data including metadata
        clean_config_data = source_config_data.copy()
        
        # Get current config version for the target session
        existing_config, _ = storage_manager.get_latest_config(email, session_id)
        version = 1
        if existing_config and existing_config.get('storage_metadata', {}).get('version'):
            version = existing_config['storage_metadata']['version'] + 1
        
        # Store the copied config with preserved original_name chain and filename
        storage_result = storage_manager.store_config_file(
            email=email, 
            session_id=session_id, 
            config_data=clean_config_data, 
            version=version, 
            source='copied_from_previous',
            description=source_description,
            original_name=original_name,  # Preserve original name chain
            source_session=source_session,
            preserve_original_filename=original_filename  # Keep exact filename
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
                source_session=source_session,
                config_id=storage_result.get('config_id'),
                config_description=source_description
            )
            if session_info_result['success']:
                logger.info(f"Session info updated with copied config tracking")
        except Exception as e:
            logger.warning(f"Failed to update session info: {e}")
        
        logger.info(f"Successfully copied config from {source_config_key} to session {session_id}")
        
        return create_response(200, {
            'success': True,
            'config_data': clean_config_data,
            'config_version': version,
            'config_s3_key': storage_result['s3_key'],
            'config_id': storage_result.get('config_id'),
            'source_info': {
                'source_session': source_session,
                'source_key': source_config_key,
                'copied_at': datetime.now().isoformat(),
                'original_name': original_name
            },
            'message': f'Configuration successfully copied from previous session'
        })
        
    except Exception as e:
        logger.error(f"Copy config error: {e}")
        return create_response(500, {
            'success': False,
            'error': str(e)
        })