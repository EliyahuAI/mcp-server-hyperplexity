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
        
        # Append source session to filename if not already present AND filename doesn't start with session_
        if source_filename and source_session:
            base_name = source_filename.replace('.json', '')
            # Check if filename already starts with session_ pattern
            if not base_name.startswith('session_') and source_session not in base_name:
                source_filename = f"{source_session}_{base_name}.json"
        
        # Keep all config data including metadata
        clean_config_data = config_data.copy()
        
        # Use source config version to preserve evolutionary history
        source_version = source_metadata.get('version', 1)
        version = source_version  # Preserve source config version to track evolution
        
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
            'source_config_key': 's3_key_of_source_config',  # LEGACY: Direct S3 path
            'source_config_id': 'session_20250918_170524_c4b7eba7_config_v1_ai_generated',  # NEW: Config ID lookup
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
        source_config_id = event_data.get('source_config_id')  # New parameter for config ID
        source_session = event_data.get('source_session')
        
        # Check for alternative parameter names that frontend might be using
        if not source_config_id:
            source_config_id = event_data.get('config_id')  # Check if using 'config_id' instead
        if not source_config_key:
            source_config_key = event_data.get('config_key')  # Check if using 'config_key' instead
            
        # Handle frontend sending string "undefined" instead of actual values
        if source_config_key == "undefined":
            source_config_key = None
        if source_config_id == "undefined":
            source_config_id = None
        if source_session == "undefined":
            source_session = None
            
        # DEBUG: Log received parameters to understand what frontend is sending
        logger.info(f"Copy config parameters - email: {email}, session_id: {session_id}")
        logger.info(f"Source parameters - config_key: {source_config_key}, config_id: {source_config_id}, session: {source_session}")
        logger.info(f"Full event_data keys: {list(event_data.keys())}")
        logger.info(f"Full event_data: {event_data}")
        
        # If no valid source provided, try to find the most recent matching config
        if not (source_config_key or source_config_id):
            logger.info("No source config specified - finding most recent matching config")
            # Use the find_matching_configs to get the latest perfect match
            from interface_lambda.actions.find_matching_config import find_matching_configs_optimized
            
            try:
                matching_result = find_matching_configs_optimized(email, session_id, limit=1)
                if matching_result.get('success') and matching_result.get('matches'):
                    latest_match = matching_result['matches'][0]
                    source_config_id = latest_match.get('config_id')
                    source_config_key = latest_match.get('config_key')
                    logger.info(f"Auto-found latest matching config: {source_config_id}")
                else:
                    return create_response(400, {
                        'success': False,
                        'error': 'No source config specified and no matching configs found for current session'
                    })
            except Exception as e:
                logger.error(f"Failed to auto-find matching config: {e}")
                return create_response(400, {
                    'success': False,
                    'error': 'No source config specified and failed to find matching configs'
                })
        
        if not all([email, session_id]) or not (source_config_key or source_config_id):
            return create_response(400, {
                'success': False,
                'error': 'Missing required parameters: email, session_id, and either source_config_key or source_config_id'
            })
        
        storage_manager = UnifiedS3Manager()
        
        # Handle both config ID and direct S3 key approaches
        if source_config_id:
            # NEW: Lookup config by ID using optimized system
            logger.info(f"Looking up config by ID: {source_config_id}")
            source_config_data, source_config_key = storage_manager.find_config_by_id(source_config_id, email)
            if not source_config_data or not source_config_key:
                logger.error(f"Config ID not found: {source_config_id}")
                return create_response(404, {
                    'success': False,
                    'error': f'Source configuration not found for ID: {source_config_id}'
                })
            logger.info(f"Successfully found config by ID: {source_config_id} -> {source_config_key}")
        else:
            # LEGACY: Direct S3 key approach
            try:
                response = storage_manager.s3_client.get_object(
                    Bucket=storage_manager.bucket_name, 
                    Key=source_config_key
                )
                source_config_data = json.loads(response['Body'].read().decode('utf-8'))
                logger.info(f"Successfully retrieved source config by key: {source_config_key}")
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
        
        # Preserve original session prefix if it exists (don't add source_session if filename already has one)
        # Only add source_session prefix if filename doesn't already have a session_ prefix
        if original_filename and source_session:
            import re
            session_prefix_pattern = r'^session_(?:demo_)?\d{8}_\d{6}_[a-f0-9]{8}_'
            base_name = original_filename.replace('.json', '')

            if not re.match(session_prefix_pattern, base_name):
                # No session prefix exists - add the source session
                original_filename = f"{source_session}_{base_name}.json"
                logger.info(f"Added source session to filename: {original_filename}")
            else:
                # Session prefix already exists - preserve it
                logger.info(f"Preserving existing session in filename: {original_filename}")
        
        # Keep all config data including metadata
        clean_config_data = source_config_data.copy()
        
        # Use source config version to preserve evolutionary history
        source_version = source_metadata.get('version', 1)
        version = source_version  # Preserve source config version to track evolution
        
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
        
        # Skip old session info creation - use clean structure only
        table_name = f"table_{session_id.split('_')[-1]}"
        
        # Update session_info.json with comprehensive tracking
        try:
            # Update session config tracking
            # Ensure session has table_name set by adding it to session_info first
            existing_session_info = storage_manager.load_session_info(email, session_id)
            if "table_name" not in existing_session_info:
                existing_session_info["table_name"] = table_name
                existing_session_info["session_id"] = session_id
                existing_session_info["email"] = email
                storage_manager.save_session_info(email, session_id, existing_session_info)
            
            update_success = storage_manager.update_session_config(
                email=email,
                session_id=session_id,
                config_data=clean_config_data,
                config_key=storage_result['s3_key'],
                config_id=storage_result.get('config_id'),
                version=version,
                source='copied_from_previous',
                description=source_description,
                source_session=source_session,
                source_config_path=source_config_key  # Include source config path
            )
            
            if update_success:
                logger.info(f"Updated session_info.json with copied config tracking")
            else:
                logger.warning(f"Failed to update session_info.json (will fall back to messy logic)")
                
        except Exception as e:
            logger.warning(f"Failed to update session_info.json (will fall back to messy logic): {e}")
        
        logger.info(f"Successfully copied config from {source_config_key} to session {session_id}")
        
        return create_response(200, {
            'success': True,
            'config_data': clean_config_data,
            'config_version': version,
            'config_s3_key': storage_result['s3_key'],
            'config_id': storage_result.get('config_id'),
            'session_tracking_updated': update_success,
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