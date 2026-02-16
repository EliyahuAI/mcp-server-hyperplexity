"""
Create a new validation session from existing session's enhanced results.

This enables the "Update Table" feature in the Interactive Results Viewer,
allowing users to re-validate their enhanced data with modifications.
"""
import logging
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import re

from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response, clean_table_name
from interface_lambda.actions.copy_config import copy_agent_memory, copy_config_to_session

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def generate_session_id(email: str) -> str:
    """
    Generate a new session ID in the standard format.
    Format: session_YYYYMMDD_HHMMSS_XXXXXXXX
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime('%Y%m%d_%H%M%S')
    hash_input = f"{email}_{timestamp}_{now.microsecond}".encode()
    short_hash = hashlib.md5(hash_input).hexdigest()[:8]
    return f"session_{timestamp}_{short_hash}"


def handle_create_update_session(event_data: Dict[str, Any], context=None) -> Dict:
    """
    Create a new session from an existing session's enhanced results.

    This action:
    1. Generates a new session_id
    2. Locates the enhanced Excel file in the source session's results folder
    3. Copies the enhanced Excel to the new session as the input file
    4. Copies config using the existing pattern
    5. Copies agent_memory.json if it exists
    6. Initializes session_info.json with source tracking

    Args:
        event_data: {
            'email': 'user@example.com',
            'source_session_id': 'session_20250115_123456_abc12345',
            'source_version': 1  # Optional, defaults to latest
        }

    Returns:
        {
            'success': True,
            'new_session_id': 'session_20250124_...',
            'table_name': 'table_xyz',
            'config_copied': True,
            'memory_copied': True
        }
    """
    logger.info(f"[CREATE_UPDATE_SESSION] Starting with event_data: {event_data}")

    try:
        # Extract and validate parameters
        email = event_data.get('email', '').lower().strip()
        source_session_id = event_data.get('source_session_id', '').strip()
        source_version = event_data.get('source_version')

        if not email:
            return create_response(400, {
                'success': False,
                'error': 'Email address is required'
            })

        if not source_session_id:
            return create_response(400, {
                'success': False,
                'error': 'Source session ID is required'
            })

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Get source session path
        source_session_path = storage_manager.get_session_path(email, source_session_id)
        logger.info(f"[CREATE_UPDATE_SESSION] Source session path: {source_session_path}")

        # Determine which bucket to use (try primary, then dev)
        primary_bucket = storage_manager.bucket_name
        dev_bucket = f"{primary_bucket}-dev" if not primary_bucket.endswith('-dev') else primary_bucket
        active_bucket = primary_bucket

        # Find the version to use if not specified
        if source_version:
            config_version = int(source_version)
        else:
            config_version = _find_latest_version(storage_manager, primary_bucket, source_session_path)
            if not config_version:
                config_version = _find_latest_version(storage_manager, dev_bucket, source_session_path)
                if config_version:
                    active_bucket = dev_bucket

            if not config_version:
                return create_response(404, {
                    'success': False,
                    'error': 'No validation results found for source session'
                })

        logger.info(f"[CREATE_UPDATE_SESSION] Using version {config_version} from bucket {active_bucket}")

        # Find results folder (standard or dev)
        results_prefix = f"{source_session_path}v{config_version}_results/"
        results_prefix_dev = f"{source_session_path}v{config_version}_results-dev/"
        actual_results_prefix = _find_results_folder(storage_manager, active_bucket, results_prefix, results_prefix_dev)

        if not actual_results_prefix and active_bucket == primary_bucket:
            actual_results_prefix = _find_results_folder(storage_manager, dev_bucket, results_prefix, results_prefix_dev)
            if actual_results_prefix:
                active_bucket = dev_bucket

        if not actual_results_prefix:
            return create_response(404, {
                'success': False,
                'error': 'No results folder found for source session'
            })

        logger.info(f"[CREATE_UPDATE_SESSION] Results folder: {actual_results_prefix}")

        # Find the enhanced Excel file in the results folder
        enhanced_excel_key, enhanced_filename, is_preview_data = _find_enhanced_excel(storage_manager, active_bucket, actual_results_prefix)

        if not enhanced_excel_key:
            return create_response(404, {
                'success': False,
                'error': 'No enhanced Excel file found in source session results. Please run a full validation first.'
            })

        if is_preview_data:
            logger.warning(f"[CREATE_UPDATE_SESSION] Using PREVIEW data - full validation not found")

        logger.info(f"[CREATE_UPDATE_SESSION] Found enhanced Excel: {enhanced_excel_key} (preview={is_preview_data})")

        # Generate new session ID
        new_session_id = generate_session_id(email)
        new_session_path = storage_manager.get_session_path(email, new_session_id)
        logger.info(f"[CREATE_UPDATE_SESSION] New session ID: {new_session_id}")

        # Copy enhanced Excel as the input file for the new session
        # Clean the original filename and add _Update_YYYYMMDD suffix
        clean_base = clean_table_name(enhanced_filename, for_display=False)
        update_date = datetime.now(timezone.utc).strftime('%Y%m%d')
        input_filename = f"{clean_base}_Update_{update_date}_input.xlsx"

        logger.info(f"[CREATE_UPDATE_SESSION] Filename: '{enhanced_filename}' -> '{input_filename}'")

        input_key = f"{new_session_path}{input_filename}"

        # Use S3 copy_object for server-side copy (much faster for large files)
        try:
            storage_manager.s3_client.copy_object(
                Bucket=storage_manager.bucket_name,  # Always store in primary bucket
                Key=input_key,
                CopySource={'Bucket': active_bucket, 'Key': enhanced_excel_key},
                ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                Metadata={
                    'session_id': new_session_id,
                    'email': email,
                    'upload_timestamp': datetime.now(timezone.utc).isoformat(),
                    'source_session': source_session_id,
                    'source_version': str(config_version),
                    'copied_from': enhanced_excel_key
                },
                MetadataDirective='REPLACE'  # Required when setting new metadata
            )
            logger.info(f"[CREATE_UPDATE_SESSION] Copied input Excel using S3 copy_object: {input_key}")
        except Exception as e:
            logger.error(f"[CREATE_UPDATE_SESSION] Failed to copy input Excel: {e}")
            return create_response(500, {
                'success': False,
                'error': f'Failed to copy input Excel: {str(e)}'
            })

        # Copy config from source session (this also copies agent_memory internally)
        config_copied = False
        memory_copied = False
        config_key = None
        try:
            config_key, config_data = _find_and_copy_config(
                storage_manager, email, source_session_id, new_session_id,
                active_bucket, source_session_path
            )
            if config_key:
                config_copied = True
                # copy_config_to_session also copies agent_memory, so mark it as copied
                memory_copied = True
                logger.info(f"[CREATE_UPDATE_SESSION] Config copied: {config_key}")
        except Exception as e:
            logger.warning(f"[CREATE_UPDATE_SESSION] Config copy failed (non-fatal): {e}")

        # Only copy agent_memory separately if config copy failed (since config copy includes memory)
        if not config_copied:
            try:
                memory_result = copy_agent_memory(
                    storage_manager=storage_manager,
                    source_email=email,
                    source_session=source_session_id,
                    target_email=email,
                    target_session=new_session_id
                )
                if memory_result and memory_result.get('success'):
                    memory_copied = True
                    logger.info(f"[CREATE_UPDATE_SESSION] Agent memory copied separately ({memory_result.get('queries_copied', 0)} queries)")
            except Exception as e:
                logger.warning(f"[CREATE_UPDATE_SESSION] Memory copy failed (non-fatal): {e}")

        # Initialize session_info.json with source tracking
        table_name = f"table_{new_session_id.split('_')[-1]}"
        session_info = {
            'session_id': new_session_id,
            'email': email,
            'table_name': table_name,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'created_from_update': {
                'source_session_id': source_session_id,
                'source_version': config_version,
                'source_results_path': actual_results_prefix,
                'source_excel_path': enhanced_excel_key,
                'updated_at': datetime.now(timezone.utc).isoformat()
            },
            'input_file': {
                's3_key': input_key,
                'filename': input_filename,
                'bucket': storage_manager.bucket_name
            },
            'config_copied': config_copied,
            'memory_copied': memory_copied
        }

        # Add config info if copied
        if config_copied and config_key:
            session_info['config'] = {
                's3_key': config_key,
                'copied_from_session': source_session_id
            }

        # Save session_info.json
        try:
            storage_manager.save_session_info(email, new_session_id, session_info)
            logger.info(f"[CREATE_UPDATE_SESSION] Session info saved")
        except Exception as e:
            logger.warning(f"[CREATE_UPDATE_SESSION] Failed to save session_info (non-fatal): {e}")

        response_data = {
            'success': True,
            'new_session_id': new_session_id,
            'table_name': table_name,
            'input_file_key': input_key,
            'config_copied': config_copied,
            'memory_copied': memory_copied,
            'used_preview_data': is_preview_data,
            'source_info': {
                'session_id': source_session_id,
                'version': config_version,
                'results_path': actual_results_prefix,
                'source_file': enhanced_excel_key
            }
        }

        if is_preview_data:
            response_data['warning'] = 'Only preview data was available. Run a full validation for complete results.'

        return create_response(200, response_data)

    except Exception as e:
        logger.error(f"[CREATE_UPDATE_SESSION] Error: {e}")
        import traceback
        logger.error(f"[CREATE_UPDATE_SESSION] Traceback: {traceback.format_exc()}")
        return create_response(500, {
            'success': False,
            'error': f'Failed to create update session: {str(e)}'
        })


def _find_latest_version(storage_manager: UnifiedS3Manager, bucket: str, session_path: str) -> Optional[int]:
    """Find the latest config version by listing result folders."""
    try:
        response = storage_manager.s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=session_path,
            Delimiter='/'
        )

        versions = []
        for prefix in response.get('CommonPrefixes', []):
            folder = prefix.get('Prefix', '').rstrip('/')
            folder_name = folder.split('/')[-1]
            # Match pattern like "v1_results", "v2_results", "v1_results-dev"
            if folder_name.startswith('v') and '_results' in folder_name:
                try:
                    version_part = folder_name.split('_')[0]  # "v1"
                    version_num = int(version_part[1:])  # 1
                    versions.append(version_num)
                except (ValueError, IndexError):
                    pass

        return max(versions) if versions else None

    except Exception as e:
        logger.error(f"[CREATE_UPDATE_SESSION] Error finding versions: {e}")
        return None


def _find_results_folder(storage_manager: UnifiedS3Manager, bucket: str,
                         standard_prefix: str, dev_prefix: str) -> Optional[str]:
    """Find which results folder exists, preferring standard over dev."""
    try:
        # Check standard folder first
        response = storage_manager.s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=standard_prefix,
            MaxKeys=1
        )
        if response.get('Contents'):
            return standard_prefix

        # Fallback to dev folder
        response = storage_manager.s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=dev_prefix,
            MaxKeys=1
        )
        if response.get('Contents'):
            return dev_prefix

        return None

    except Exception as e:
        logger.error(f"[CREATE_UPDATE_SESSION] Error finding results folder: {e}")
        return None


def _find_enhanced_excel(storage_manager: UnifiedS3Manager, bucket: str,
                         results_prefix: str) -> tuple:
    """Find the full validation enhanced Excel file in the results folder.

    Prioritizes full validation files over preview files to ensure we get
    the complete validated data.

    Returns:
        tuple: (key, filename, is_preview) - is_preview is True if only preview data found
    """
    try:
        response = storage_manager.s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=results_prefix
        )

        contents = response.get('Contents', [])

        # First pass: look for full validation enhanced files (enhanced but NOT preview)
        for obj in contents:
            key = obj['Key']
            filename = key.split('/')[-1].lower()
            if filename.endswith('.xlsx') and 'enhanced' in filename and 'preview' not in filename:
                logger.info(f"[CREATE_UPDATE_SESSION] Found full validation Excel: {key}")
                return key, key.split('/')[-1], False

        # Second pass: look for any xlsx that's not a preview
        for obj in contents:
            key = obj['Key']
            filename = key.split('/')[-1].lower()
            if filename.endswith('.xlsx') and 'preview' not in filename:
                logger.info(f"[CREATE_UPDATE_SESSION] Found non-preview Excel: {key}")
                return key, key.split('/')[-1], False

        # Third pass: any enhanced file (including preview as last resort)
        for obj in contents:
            key = obj['Key']
            filename = key.split('/')[-1].lower()
            if filename.endswith('.xlsx') and 'enhanced' in filename:
                logger.warning(f"[CREATE_UPDATE_SESSION] Only preview enhanced Excel found: {key}")
                return key, key.split('/')[-1], True

        # Final fallback: any xlsx file
        for obj in contents:
            key = obj['Key']
            filename = key.split('/')[-1].lower()
            is_preview = 'preview' in filename
            logger.warning(f"[CREATE_UPDATE_SESSION] Fallback to any Excel: {key} (preview={is_preview})")
            return key, key.split('/')[-1], is_preview

        return None, None, False

    except Exception as e:
        logger.error(f"[CREATE_UPDATE_SESSION] Error finding enhanced Excel: {e}")
        return None, None, False


def _find_and_copy_config(storage_manager: UnifiedS3Manager, email: str,
                          source_session: str, target_session: str,
                          source_bucket: str, source_session_path: str) -> tuple:
    """Find and copy config from source session to target session using proper copy mechanism."""
    try:
        # List config files in source session
        response = storage_manager.s3_client.list_objects_v2(
            Bucket=source_bucket,
            Prefix=source_session_path
        )

        config_key = None

        # Find the most recent config file
        # Sort by LastModified datetime, using epoch as fallback for missing values
        contents = response.get('Contents', [])
        sorted_contents = sorted(
            contents,
            key=lambda x: x.get('LastModified', datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True
        )
        for obj in sorted_contents:
            key = obj['Key']
            filename = key.split('/')[-1].lower()
            # Check filename (not full path) for config files, excluding session_info.json
            if filename.endswith('.json') and 'config' in filename and filename != 'session_info.json':
                config_key = key
                break

        if not config_key:
            logger.warning(f"[CREATE_UPDATE_SESSION] No config file found in source session")
            return None, None

        # Read the config data
        response = storage_manager.s3_client.get_object(
            Bucket=source_bucket,
            Key=config_key
        )
        config_data = json.loads(response['Body'].read().decode('utf-8'))

        # Use the existing copy_config_to_session function for proper versioning,
        # naming, and tracking
        source_info = {
            'source_session': source_session,
            'source_email': email,
            'source_config_key': config_key,
            'source_filename': config_key.split('/')[-1],
            'copied_for': 'update_table'
        }

        copy_result = copy_config_to_session(
            email=email,
            session_id=target_session,
            config_data=config_data,
            source_info=source_info
        )

        if copy_result.get('success'):
            target_config_key = copy_result.get('config_s3_key')
            logger.info(f"[CREATE_UPDATE_SESSION] Copied config using proper mechanism: {target_config_key}")
            return target_config_key, config_data
        else:
            logger.warning(f"[CREATE_UPDATE_SESSION] Config copy failed: {copy_result.get('error')}")
            return None, None

    except Exception as e:
        logger.error(f"[CREATE_UPDATE_SESSION] Error copying config: {e}")
        return None, None
