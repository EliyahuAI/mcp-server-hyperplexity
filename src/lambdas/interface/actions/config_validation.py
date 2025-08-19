"""
Handles the validateConfig action.
"""
import logging
import json
import sys
import os
from pathlib import Path

from interface_lambda.utils.helpers import create_response
from config_validator import load_and_validate_config
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(request_data, context):
    """
    Handles the validateConfig action using shared validation with optional table matching.
    Also stores valid configs in unified storage for later use.
    """
    config_content = request_data.get('config', '')
    table_analysis = request_data.get('table_analysis')  # Optional table analysis for column matching
    email = request_data.get('email', '')
    session_id = request_data.get('session_id', '')
    
    if not config_content:
        return create_response(400, {'error': 'Missing config content', 'valid': False})
    
    # Use shared validation function with optional table matching
    result = load_and_validate_config(config_content, table_analysis)
    
    # Only store config if this is an upload validation (not AI generation or refinement validation)
    is_upload_validation = request_data.get('is_upload', False)  # Frontend sets this for user uploads
    
    # If this is an upload validation and we have email/session_id, store it (even if invalid, for refinement)
    if is_upload_validation and email and session_id:
        try:
            # Clean session ID (remove _preview suffix if present)
            base_session_id = session_id
            if base_session_id.endswith('_preview'):
                base_session_id = base_session_id[:-8]
            if not base_session_id.startswith('session_'):
                base_session_id = f"session_{base_session_id}"
            
            storage_manager = UnifiedS3Manager()
            
            # Get config data from validation result
            config_data = result.get('config_data', {})
            
            if config_data:
                # Get current version number (increment from existing configs)
                existing_config, _ = storage_manager.get_latest_config(email, base_session_id)
                version = 1
                if existing_config and existing_config.get('storage_metadata', {}).get('version'):
                    version = existing_config['storage_metadata']['version'] + 1
                
                # Store config in unified storage
                storage_result = storage_manager.store_config_file(
                    email, base_session_id, config_data, version=version, source='upload'
                )
                
                if storage_result['success']:
                    logger.info(f"Valid config stored in unified storage: {storage_result['s3_key']}")
                    # Add storage info to response
                    result['stored'] = True
                    result['storage_path'] = storage_result['s3_key']
                else:
                    logger.error(f"Failed to store valid config: {storage_result['error']}")
                    result['stored'] = False
                    result['storage_error'] = storage_result['error']
            
        except Exception as e:
            logger.error(f"Error storing config in unified storage: {str(e)}")
            result['stored'] = False
            result['storage_error'] = str(e)
    
    # Remove config_data from response for API response (but keep storage info)
    api_response = {k: v for k, v in result.items() if k != 'config_data'}
    
    return create_response(200, api_response) 