"""
Use a configuration by its config ID instead of downloading the file.
This provides secure access to configs without exposing the actual files.
Also copies agent_memory.json if it exists in the source session.
"""
import logging
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path

from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def copy_agent_memory(
    storage_manager: UnifiedS3Manager,
    source_email: str,
    source_session: str,
    target_email: str,
    target_session: str
) -> Optional[Dict[str, Any]]:
    """
    Copy agent_memory.json from source session to target session if it exists.
    Adds a system note about being careful with dynamic content.
    """
    try:
        # Construct source and target memory paths
        source_path = storage_manager.get_session_path(source_email, source_session)
        target_path = storage_manager.get_session_path(target_email, target_session)

        source_memory_key = f"{source_path}agent_memory.json"
        target_memory_key = f"{target_path}agent_memory.json"

        # Try to load source memory
        try:
            response = storage_manager.s3_client.get_object(
                Bucket=storage_manager.bucket_name,
                Key=source_memory_key
            )
            memory_data = json.loads(response['Body'].read().decode('utf-8'))
            logger.info(f"Found source agent_memory.json with {len(memory_data.get('queries', {}))} queries")
        except storage_manager.s3_client.exceptions.NoSuchKey:
            logger.info(f"No agent_memory.json found in source session {source_session}")
            return None
        except Exception as e:
            logger.warning(f"Failed to read source agent_memory.json: {e}")
            return None

        # Add system caution note about dynamic content
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        caution_note = {
            "type": "system_caution",
            "message": (
                f"Memory copied from session {source_session} on {today}. "
                f"Contains data from both original and current session. "
                f"For dynamic content, check query_time for freshness."
            ),
            "copied_from_session": source_session,
            "copied_on": today
        }

        # Add caution note to memory metadata
        if 'system_notes' not in memory_data:
            memory_data['system_notes'] = []
        memory_data['system_notes'].append(caution_note)

        # Update memory metadata for new session
        memory_data['session_id'] = target_session
        memory_data['email'] = target_email
        memory_data['copied_from'] = {
            'session_id': source_session,
            'email': source_email,
            'copied_at': datetime.now(timezone.utc).isoformat()
        }
        memory_data['last_updated'] = datetime.now(timezone.utc).isoformat()

        # Save to target session
        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=target_memory_key,
            Body=json.dumps(memory_data, indent=2),
            ContentType='application/json'
        )

        query_count = len(memory_data.get('queries', {}))
        logger.info(f"Copied agent_memory.json to {target_session} ({query_count} queries, caution note added)")

        # CRITICAL: Load copied memory into RAM cache immediately
        # This ensures parallel agents can access the copied memory without S3 reads
        try:
            from the_clone.search_memory_cache import MemoryCache
            memory = MemoryCache.load_from_copy(
                target_session_id=target_session,
                source_session_id=source_session,
                email=target_email,
                s3_manager=storage_manager,
                ai_client=None  # Will be set when clone uses it
            )
            logger.info(f"[MEMORY_CACHE] Loaded copied memory into RAM cache for {target_session}")
        except Exception as e:
            # Non-critical: Memory will still work, just slower (will load on-demand)
            logger.warning(f"[MEMORY_CACHE] Failed to pre-load copied memory into cache: {e}")

        return {
            'success': True,
            'queries_copied': query_count,
            'source_session': source_session,
            'target_session': target_session,
            'caution_note_added': True
        }

    except Exception as e:
        logger.error(f"Failed to copy agent_memory.json: {e}")
        return {'success': False, 'error': str(e)}

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
        
        # Handle special identifier 'last' to get previous configuration
        if config_id.lower() == 'last':
            # Get session info to find previous configuration
            session_info = storage_manager.load_session_info(email, session_id)

            if not session_info:
                return create_response(404, {
                    'success': False,
                    'error': 'No session information found. Cannot determine previous configuration.'
                })

            # Look through config history to find the most recent config before current
            versions = session_info.get('versions', {})
            version_numbers = [int(v) for v in versions.keys() if v.isdigit()]

            if len(version_numbers) < 2:
                return create_response(404, {
                    'success': False,
                    'error': 'No previous configuration available. This is the first or only configuration.'
                })

            # Get the second-to-latest version
            version_numbers.sort(reverse=True)
            previous_version = version_numbers[1]  # Second highest version

            previous_version_data = versions.get(str(previous_version), {})
            config_info = previous_version_data.get('config', {})
            config_path = config_info.get('config_path')

            if not config_path:
                return create_response(404, {
                    'success': False,
                    'error': f'Previous configuration path not found for version {previous_version}'
                })

            # Load the previous configuration directly
            try:
                config_response = storage_manager.s3_client.get_object(
                    Bucket=storage_manager.bucket_name,
                    Key=config_path
                )
                config_data = json.loads(config_response['Body'].read().decode('utf-8'))
                config_key = config_path
                logger.info(f"Found previous config version {previous_version} for session {session_id}")
            except Exception as e:
                return create_response(404, {
                    'success': False,
                    'error': f'Failed to load previous configuration: {str(e)}'
                })
        else:
            # Look up the config by ID (normal path)
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

        # Determine the source based on whether this is a revert operation
        if config_id.lower() == 'last':
            source = f'restoringV{previous_version}'
        else:
            source = 'used_by_id'

        # Store the config in the current session with usage timestamp
        usage_timestamp = datetime.now().isoformat()
        storage_result = storage_manager.store_config_file(
            email=email,
            session_id=session_id,
            config_data=clean_config_data,
            version=version,
            source=source,
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
                config_source=source,
                source_session=source_session,
                config_id=storage_result.get('config_id'),
                config_description=source_description
            )
            if session_info_result['success']:
                logger.info(f"Session info updated with config ID usage tracking")
        except Exception as e:
            logger.warning(f"Failed to update session info: {e}")
        
        logger.info(f"Successfully applied config ID {config_id} to session {session_id}")

        # Also copy agent_memory.json if it exists in the source session
        memory_copy_result = None
        if source_session:
            logger.info(f"Attempting to copy agent_memory from {source_session} to {session_id}")
            # Extract source email from config metadata or use current email
            source_email = source_metadata.get('email', email)
            memory_copy_result = copy_agent_memory(
                storage_manager=storage_manager,
                source_email=source_email,
                source_session=source_session,
                target_email=email,
                target_session=session_id
            )

            # Record memory copy in session_info.json
            if memory_copy_result and memory_copy_result.get('success'):
                try:
                    session_info = storage_manager.load_session_info(email, session_id)
                    session_info['agent_memory_copied'] = {
                        'copied_from_session': source_session,
                        'copied_from_email': source_email,
                        'copied_at': datetime.now(timezone.utc).isoformat(),
                        'queries_copied': memory_copy_result.get('queries_copied', 0),
                        'caution_note_added': True
                    }
                    storage_manager.save_session_info(email, session_id, session_info)
                    logger.info(f"Recorded agent_memory copy in session_info.json")
                except Exception as e:
                    logger.warning(f"Failed to record memory copy in session_info.json: {e}")
        else:
            # Try to extract source_session from config_key or config_id
            session_match = re.search(r'(session_(?:demo_)?\d{8}_\d{6}_[a-f0-9]{8})', config_key or config_id)
            if session_match:
                extracted_session = session_match.group(1)
                logger.info(f"Extracted source_session from key: {extracted_session}")
                source_email = source_metadata.get('email', email)
                memory_copy_result = copy_agent_memory(
                    storage_manager=storage_manager,
                    source_email=source_email,
                    source_session=extracted_session,
                    target_email=email,
                    target_session=session_id
                )
            else:
                logger.warning(f"Cannot copy agent_memory - source_session not available")

        return create_response(200, {
            'success': True,
            'config_data': clean_config_data,
            'config_version': version,
            'config_s3_key': storage_result['s3_key'],
            'config_id': storage_result.get('config_id'),
            'memory_copied': memory_copy_result,
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