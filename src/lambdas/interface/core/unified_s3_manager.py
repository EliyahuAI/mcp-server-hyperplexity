"""
Unified S3 Storage Manager for Hyperplexity.
Replaces multiple bucket approach with single, well-organized bucket structure.
"""

import os
import json
import boto3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Optional, Any
import logging
from urllib.parse import quote
import hashlib

logger = logging.getLogger(__name__)

class UnifiedS3Manager:
    """
    Unified S3 storage manager with clean folder structure:
    
    bucket/
    ├── results/{domain}/{email_prefix}/{yyyymmdd_hhmmss_sessionId}/  (1 year retention)
    ├── downloads/{uuid}/                                              (7 days, public)
    └── cache/{service}/{hash}/                                        (configurable TTL, default 1 day)
    """
    
    def __init__(self):
        self.bucket_name = os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')
        self.s3_client = boto3.client('s3')
        
    def get_session_path(self, email: str, session_id: str) -> str:
        """
        Generate consistent session storage path.
        Format: results/{domain}/{email_prefix}/{yyyymmdd_hhmmss_sessionId}/
        """
        # Extract domain and create safe email prefix
        domain = email.split('@')[-1] if '@' in email else 'unknown'
        email_prefix = email.split('@')[0].replace('.', '_').replace('+', '_plus_')[:20]

        # Use session_id directly as folder name - no duplicate timestamps
        session_folder = session_id

        return f"results/{domain}/{email_prefix}/{session_folder}/"

    def get_table_maker_path(self, email: str, session_id: str, conversation_id: str, file_name: str) -> str:
        """
        Generate Table Maker storage path for conversation files.
        Format: results/{domain}/{email_prefix}/{session_id}/table_maker/{conversation_id}/{file_name}
        """
        session_path = self.get_session_path(email, session_id)
        return f"{session_path}table_maker/{conversation_id}/{file_name}"

    def _calculate_config_content_hash(self, config_data: Dict) -> str:
        """
        Calculate SHA256 hash of configuration content for deduplication.
        Only includes validation targets and rules, excluding metadata like names, descriptions, etc.
        """
        try:
            # Extract only the validation content, not metadata
            validation_targets = config_data.get('validation_targets', [])
            
            # Normalize validation targets for consistent hashing
            normalized_targets = []
            for target in validation_targets:
                if isinstance(target, dict):
                    # Extract key validation fields, ignore metadata like names/descriptions
                    normalized_target = {}
                    
                    # Core validation fields that affect behavior
                    for field in ['column', 'name', 'column_name', 'validation_rules', 'required', 'data_type']:
                        if field in target:
                            value = target[field]
                            # Normalize string values (case insensitive, strip whitespace)
                            if isinstance(value, str):
                                normalized_target[field] = value.lower().strip()
                            else:
                                normalized_target[field] = value
                    
                    if normalized_target:
                        normalized_targets.append(normalized_target)
                elif isinstance(target, str):
                    # Simple string target
                    normalized_targets.append(target.lower().strip())
            
            # Sort targets for consistent ordering
            normalized_targets.sort(key=lambda x: json.dumps(x, sort_keys=True) if isinstance(x, dict) else str(x))
            
            # Include other validation settings that affect behavior
            validation_content = {
                'targets': normalized_targets
            }
            
            # Include ALL fields that affect validation behavior (not just validation_targets)
            validation_affecting_fields = [
                'validation_mode', 'strictness', 'custom_rules', 'validation_settings',
                'column_mappings', 'search_instructions', 'general_notes', 
                'table_structure', 'processing_rules', 'output_format'
            ]
            
            for field in validation_affecting_fields:
                if field in config_data and config_data[field]:
                    # Normalize string values for consistent hashing
                    value = config_data[field]
                    if isinstance(value, str):
                        validation_content[field] = value.lower().strip()
                    elif isinstance(value, dict):
                        # Recursively normalize dict values
                        normalized_dict = {}
                        for k, v in value.items():
                            if isinstance(v, str):
                                normalized_dict[k.lower().strip()] = v.lower().strip()
                            else:
                                normalized_dict[k.lower().strip()] = v
                        validation_content[field] = normalized_dict
                    else:
                        validation_content[field] = value
            
            # Create consistent hash - use 32 chars to reduce collision risk
            content_str = json.dumps(validation_content, sort_keys=True)
            full_hash = hashlib.sha256(content_str.encode('utf-8')).hexdigest()
            return full_hash[:32]  # 32 chars for better collision resistance
            
        except Exception as e:
            logger.warning(f"Failed to calculate content hash: {e}")
            return f"error_{hash(str(config_data))}"[:32]
    
    def store_excel_file(self, email: str, session_id: str, file_content: bytes, 
                        filename: str = None) -> Dict[str, Any]:
        """Store Excel file in session folder with _input suffix"""
        try:
            session_path = self.get_session_path(email, session_id)
            
            # Preserve original filename but add _input suffix
            if filename:
                name_parts = filename.rsplit('.', 1)
                if len(name_parts) == 2:
                    base_name, extension = name_parts
                    input_filename = f"{base_name}_input.{extension}"
                else:
                    input_filename = f"{filename}_input"
            else:
                input_filename = 'excel_file_input.xlsx'
            
            file_key = f"{session_path}{input_filename}"
            
            # Store original filename in metadata if provided
            metadata = {
                'session_id': session_id,
                'email': email,
                'upload_timestamp': datetime.now().isoformat()
            }
            if filename:
                metadata['original_filename'] = filename

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=file_content,
                ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                Metadata=metadata
            )
            
            logger.info(f"Stored Excel file: {file_key}")
            return {
                'success': True,
                's3_key': file_key,
                'session_path': session_path
            }
            
        except Exception as e:
            logger.error(f"Failed to store Excel file: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def store_config_file(self, email: str, session_id: str, config_data: Dict, 
                         version: int = 1, source: str = 'user', description: str = None,
                         original_name: str = None, source_session: str = None, 
                         usage_timestamp: str = None, preserve_original_filename: str = None) -> Dict[str, Any]:
        """Store config file in session folder with versioning"""
        try:
            session_path = self.get_session_path(email, session_id)
            
            # Use preserved filename if provided (for copying), otherwise generate new one
            if preserve_original_filename:
                config_filename = preserve_original_filename
                logger.info(f"Using preserved filename: {config_filename}")
            else:
                config_filename = f"config_v{version}_{source}.json"

            file_key = f"{session_path}{config_filename}"

            # Generate clean config ID that matches the filename structure
            # New format: {session_id}_{filename_without_extension}
            # Example: session_20250918_150921_ea332116_config_v1_ai_generated
            # Maps to: session_20250918_150921_ea332116/config_v1_ai_generated.json

            import re
            filename_without_ext = config_filename.replace('.json', '')

            # BUGFIX: If filename already has a session prefix, use it for config_id (preserve original source)
            # Otherwise, prepend current session_id
            # Also handle legacy duplicated suffixes (e.g., config_v1_ai_generated_config_v1_ai_generated)
            session_prefix_pattern = r'^(session_(?:demo_)?\d{8}_\d{6}_[a-f0-9]{8})_'
            match = re.match(session_prefix_pattern, filename_without_ext)

            if match:
                # Filename already has session prefix - use it as-is to preserve original source
                config_id = filename_without_ext

                # LEGACY FIX: Strip duplicate suffixes if they exist
                # Pattern: _something_something (where both parts are identical)
                parts = config_id.split('_')
                if len(parts) >= 4:
                    # Check if last parts repeat (e.g., config_v1_ai_generated_config_v1_ai_generated)
                    midpoint = len(parts) // 2
                    first_half = '_'.join(parts[midpoint:])
                    second_half = '_'.join(parts[midpoint:])

                    # If we have duplicated suffixes after the session ID
                    remaining = config_id[len(match.group(1)) + 1:]  # Everything after session_XXX_
                    if '_' in remaining:
                        suffix_parts = remaining.split('_')
                        midpoint = len(suffix_parts) // 2
                        if midpoint > 0:
                            first_half = '_'.join(suffix_parts[:midpoint])
                            second_half = '_'.join(suffix_parts[midpoint:])
                            if first_half == second_half:
                                # Duplicated suffix found - use first half only
                                config_id = f"{match.group(1)}_{first_half}"
                                logger.info(f"Stripped duplicate suffix from config ID: {config_id}")

                logger.info(f"Preserved original session in config ID: {config_id}")
            else:
                # No session prefix - prepend current session
                config_id = f"{session_id}_{filename_without_ext}"
                logger.info(f"Generated new config ID with current session: {config_id}")
            
            # Calculate and store content hash directly in the config for easy access
            content_hash = self._calculate_config_content_hash(config_data)
            
            # Add comprehensive metadata including content tracking
            now = datetime.now().isoformat()
            
            # Preserve first_created from existing metadata or set new
            existing_metadata = config_data.get('storage_metadata', {})
            first_created = existing_metadata.get('first_created', now)
            
            storage_metadata = {
                'version': version,
                'source': source,
                'session_id': session_id,
                'email': email,
                'stored_at': now,
                'created_at': now,
                'config_id': config_id,
                'description': description or config_data.get('general_notes', ''),
                'original_name': original_name,
                'source_session': source_session,
                # Enhanced tracking fields
                'content_hash': content_hash,
                'creation_method': source,
                'usage_count': 1 if source in ['used_by_id', 'copied', 'applied'] else 0,
                'first_created': first_created,  # CRITICAL: Preserve original creation time
                'metadata_version': '2.0'  # For future schema evolution
            }
            
            # Add usage timestamp if this config is being used/applied
            if usage_timestamp:
                storage_metadata['last_used'] = usage_timestamp
            elif source in ['used_by_id', 'copied', 'applied']:
                # If it's being used but no explicit timestamp, use current time
                storage_metadata['last_used'] = now
                
            config_with_meta = {
                **config_data,
                'storage_metadata': storage_metadata
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=json.dumps(config_with_meta, indent=2),
                ContentType='application/json',
                Metadata={
                    'session_id': session_id,
                    'email': email,
                    'version': str(version),
                    'source': source
                }
            )
            
            logger.info(f"Stored config file: {file_key}")
            return {
                'success': True,
                's3_key': file_key,
                'session_path': session_path,
                'version': version,
                'config_id': config_id
            }
            
        except Exception as e:
            logger.error(f"Failed to store config file: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_session_info(self, email: str, session_id: str, table_name: str, 
                           current_config_version: int = 1, config_source: str = None, 
                           source_session: str = None, config_id: str = None, 
                           config_description: str = None) -> Dict[str, Any]:
        """Create or update session_info.json file"""
        try:
            session_path = self.get_session_path(email, session_id)
            session_info_key = f"{session_path}session_info.json"
            
            # Try to get existing session info
            try:
                existing_response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=session_info_key
                )
                existing_info = json.loads(existing_response['Body'].read())
                total_configs = max(existing_info.get('total_configs', 1), current_config_version)
                config_history = existing_info.get('config_history', [])
            except:
                total_configs = current_config_version
                config_history = []
            
            # Track config history
            if config_source:
                config_entry = {
                    'version': current_config_version,
                    'source': config_source,
                    'created_at': datetime.now().isoformat(),
                    'config_id': config_id,
                    'description': config_description
                }
                if source_session:
                    config_entry['source_session'] = source_session
                
                # Update or add to history
                config_history = [entry for entry in config_history if entry['version'] != current_config_version]
                config_history.append(config_entry)
            
            session_info = {
                'session_id': session_id,
                'created': datetime.now().isoformat(),
                'email': email,
                'table_name': table_name,
                'current_config_version': current_config_version,
                'total_configs': total_configs,
                'last_updated': datetime.now().isoformat(),
                'config_history': config_history
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=session_info_key,
                Body=json.dumps(session_info, indent=2),
                ContentType='application/json'
            )
            
            return {
                'success': True,
                's3_key': session_info_key,
                'session_info': session_info
            }
            
        except Exception as e:
            logger.error(f"Failed to create session info: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def store_results(self, email: str, session_id: str, config_version: int,
                     results_data: Dict, result_type: str = 'validation') -> Dict[str, Any]:
        """Store processing results in versioned results folder"""
        try:
            session_path = self.get_session_path(email, session_id)
            results_folder = f"{session_path}v{config_version}_results/"
            results_key = f"{results_folder}{result_type}_results.json"
            
            # Add metadata to results
            results_with_meta = {
                **results_data,
                'processing_metadata': {
                    'config_version': config_version,
                    'session_id': session_id,
                    'email': email,
                    'result_type': result_type,
                    'processed_at': datetime.now().isoformat()
                }
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=results_key,
                Body=json.dumps(results_with_meta, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"Stored {result_type} results: {results_key}")
            return {
                'success': True,
                's3_key': results_key,
                'results_folder': results_folder
            }
            
        except Exception as e:
            logger.error(f"Failed to store results: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def store_enhanced_files(self, email: str, session_id: str, config_version: int,
                           enhanced_excel_content: bytes = None, summary_text: str = None,
                           result_type: str = 'validation') -> Dict[str, Any]:
        """Store enhanced Excel and summary text in versioned results folder

        Args:
            email: User email
            session_id: Session ID
            config_version: Config version number
            enhanced_excel_content: Excel file content bytes
            summary_text: Summary text content
            result_type: 'preview' or 'validation' - determines filename
        """
        try:
            session_path = self.get_session_path(email, session_id)
            results_folder = f"{session_path}v{config_version}_results/"

            stored_files = []

            # Store enhanced Excel if provided
            if enhanced_excel_content:
                # Use different filenames for preview vs validation
                if result_type == 'preview':
                    excel_filename = "enhanced_preview.xlsx"
                else:
                    excel_filename = "enhanced_validation.xlsx"

                excel_key = f"{results_folder}{excel_filename}"
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=excel_key,
                    Body=enhanced_excel_content,
                    ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                stored_files.append(excel_key)
                logger.info(f"Stored enhanced {result_type} Excel: {excel_key}")

            # Store summary text if provided
            if summary_text:
                summary_key = f"{results_folder}validation_summary.txt"
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=summary_key,
                    Body=summary_text.encode('utf-8'),
                    ContentType='text/plain'
                )
                stored_files.append(summary_key)
                logger.info(f"Stored summary text: {summary_key}")

            return {
                'success': True,
                'stored_files': stored_files,
                'results_folder': results_folder
            }
            
        except Exception as e:
            logger.error(f"Failed to store enhanced files: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_excel_file(self, email: str, session_id: str, bypass_session_info: bool = False) -> Tuple[Optional[bytes], Optional[str]]:
        """Get Excel file from session folder, preferring session_info.json lookup"""
        try:
            # First try to get Excel path from session_info.json (unless bypassed)
            if not bypass_session_info:
                try:
                    session_info = self.load_session_info(email, session_id)
                    excel_path = session_info.get('table_path')
                    
                    if excel_path:
                        logger.info(f"Found Excel path in session_info.json: {excel_path}")
                        response = self.s3_client.get_object(
                            Bucket=self.bucket_name,
                            Key=excel_path
                        )
                        content = response['Body'].read()
                        logger.debug(f"Successfully retrieved Excel file from session_info path: {excel_path}")
                        return content, excel_path
                except Exception as e:
                    logger.info(f"Could not get Excel path from session_info.json, falling back to file scanning: {e}")
            
            # Fallback to file scanning if session_info.json doesn't have the path
            session_path = self.get_session_path(email, session_id)
            logger.debug(f"Looking for Excel file in session path: {session_path}")
            
            # Try common Excel file names (including new _input suffix pattern)
            potential_keys = [
                f"{session_path}excel_file_input.xlsx",  # New pattern
                f"{session_path}excel_file.xlsx",       # Legacy pattern
                f"{session_path}input.xlsx",
                f"{session_path}table.xlsx"
            ]
            
            # Also list files in the session folder to find any Excel file
            # BUT prioritize original input files over enhanced/results files
            try:
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=session_path
                )
                
                if 'Contents' in response:
                    logger.info(f"Found {len(response['Contents'])} objects in session folder")
                    input_files = []
                    other_files = []
                    
                    for obj in response['Contents']:
                        if obj['Key'].endswith(('.xlsx', '.xls', '.csv')):
                            # Only include files directly in the session folder, not in subfolders like v1_results/
                            # and prioritize original input files over enhanced/results files
                            key_parts = obj['Key'].replace(session_path, '').split('/')
                            filename = key_parts[-1]
                            
                            # Skip files in subfolders (like v1_results/enhanced_validation.xlsx)
                            if len(key_parts) > 1 and key_parts[0]:  # Has subfolder
                                logger.debug(f"Skipping file in subfolder: {obj['Key']}")
                                continue
                            
                            # Prioritize original input files over any processed/enhanced files
                            if ('_input.' in filename or 
                                filename in ['excel_file.xlsx', 'input.xlsx', 'table.xlsx'] or
                                ('enhanced' not in filename and 'validation' not in filename)):
                                input_files.append(obj['Key'])
                                logger.debug(f"Prioritizing input file: {obj['Key']}")
                            else:
                                other_files.append(obj['Key'])
                                logger.debug(f"Adding as fallback file: {obj['Key']}")
                    
                    # Add input files first (prioritized), then other files as fallback
                    for key in input_files:
                        potential_keys.insert(0, key)
                    for key in other_files:
                        potential_keys.append(key)
                else:
                    logger.warning(f"No contents found in session folder: {session_path}")
            except Exception as e:
                logger.error(f"Error listing session folder contents: {e}")
                pass
            
            # Try to download the first available Excel file
            logger.info(f"Attempting to retrieve Excel file from {len(potential_keys)} potential keys:")
            for i, key in enumerate(potential_keys):
                logger.info(f"  {i+1}. {key}")
            
            for key in potential_keys:
                try:
                    response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                    filename = key.split('/')[-1]
                    if 'enhanced_validation' in filename:
                        logger.warning(f"USING ENHANCED FILE (not original input): {key}")
                    else:
                        logger.info(f"Successfully retrieved original Excel file: {key}")
                    return response['Body'].read(), key
                except Exception as e:
                    logger.debug(f"Failed to retrieve {key}: {e}")
                    continue
            
            logger.warning(f"No Excel file found for session {session_id}")
            return None, None
            
        except Exception as e:
            logger.error(f"Failed to get Excel file: {e}")
            return None, None
    
    def get_latest_config(self, email: str, session_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Get latest config file from session folder, preferring session_info.json lookup"""
        try:
            # First try to get config path from session_info.json
            try:
                session_info = self.load_session_info(email, session_id)
                current_version = session_info.get('current_version')
                
                if current_version and str(current_version) in session_info.get('versions', {}):
                    version_data = session_info['versions'][str(current_version)]
                    config_path = version_data.get('config', {}).get('config_path')
                    
                    if config_path:
                        logger.info(f"Found config path in session_info.json: {config_path}")
                        response = self.s3_client.get_object(
                            Bucket=self.bucket_name,
                            Key=config_path
                        )
                        config_data = json.loads(response['Body'].read().decode('utf-8'))
                        logger.debug(f"Successfully retrieved config file from session_info path: {config_path}")
                        return config_data, config_path
            except Exception as e:
                logger.info(f"Could not get config path from session_info.json, falling back to file scanning: {e}")
            
            # Fallback to file scanning if session_info.json doesn't have the path
            session_path = self.get_session_path(email, session_id)
            
            # List all config files in session folder (both new v{N}_ pattern and legacy config_ pattern)
            logger.debug(f"Looking for config files in: {session_path}")
            
            # First try new versioned pattern - config_v{N}_{source}.json
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=f"{session_path}config_v",
                Delimiter='/'  # Don't recurse into subfolders
            )
            
            config_files = []
            if 'Contents' in response:
                # Filter for config_v{N}_{source}.json pattern (only in main session folder)
                for obj in response['Contents']:
                    logger.debug(f"Checking object: {obj['Key']}")
                    filename = obj['Key'].split('/')[-1]
                    if (filename.startswith('config_v') and 
                        filename.endswith('.json') and 
                        '_' in filename and 
                        obj['Key'].count('/') == session_path.count('/')):  # Ensure it's in main folder, not subfolder
                        config_files.append(obj)
            
            # If no versioned configs found, try legacy pattern
            if not config_files:
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=f"{session_path}config_",
                    Delimiter='/'  # Don't recurse into subfolders
                )
                if 'Contents' in response:
                    for obj in response['Contents']:
                        filename = obj['Key'].split('/')[-1]
                        if (filename.startswith('config_') and 
                            filename.endswith('.json') and
                            obj['Key'].count('/') == session_path.count('/')):  # Ensure it's in main folder
                            config_files.append(obj)
            
            # If still no configs found, search for ALL .json files in session (including copied configs with session prefix)
            if not config_files:
                logger.info("No standard config files found, searching for all JSON files in session")
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=session_path,
                    Delimiter='/'  # Don't recurse into subfolders
                )
                if 'Contents' in response:
                    for obj in response['Contents']:
                        filename = obj['Key'].split('/')[-1]
                        # Include any .json file that might be a config, but exclude results files
                        if (filename.endswith('.json') and 
                            obj['Key'].count('/') == session_path.count('/') and
                            not filename.startswith('session_info') and
                            'results' not in filename and
                            'receipt' not in filename):
                            # Validate it's actually a config by checking if it has storage_metadata
                            try:
                                config_response = self.s3_client.get_object(Bucket=self.bucket_name, Key=obj['Key'])
                                config_data = json.loads(config_response['Body'].read().decode('utf-8'))
                                if 'storage_metadata' in config_data:
                                    config_files.append(obj)
                                    logger.info(f"Found config file: {filename}")
                            except Exception as e:
                                logger.debug(f"Skipping non-config file {filename}: {e}")
                                continue
            
            if not config_files:
                logger.info(f"No config files found for session {session_id}")
                return None, None
            
            logger.info(f"Found {len(config_files)} config files")
            
            # Sort by last modified to get latest
            config_files = sorted(config_files, key=lambda x: x['LastModified'], reverse=True)
            latest_key = config_files[0]['Key']
            
            # Download latest config
            config_response = self.s3_client.get_object(Bucket=self.bucket_name, Key=latest_key)
            config_data = json.loads(config_response['Body'].read().decode('utf-8'))
            
            logger.info(f"Retrieved latest config: {latest_key}")
            return config_data, latest_key
            
        except Exception as e:
            logger.error(f"Failed to get latest config: {e}")
            return None, None
    
    def store_validation_results(self, email: str, session_id: str, results_data: Dict,
                               result_type: str = 'validation') -> Dict[str, Any]:
        """Store validation results in session folder"""
        try:
            session_path = self.get_session_path(email, session_id)
            timestamp = datetime.now().strftime('%H%M%S')
            results_filename = f"{result_type}_results_{timestamp}.json"
            file_key = f"{session_path}{results_filename}"
            
            # Add metadata
            results_with_meta = {
                **results_data,
                'metadata': {
                    'session_id': session_id,
                    'email': email,
                    'result_type': result_type,
                    'stored_at': datetime.now().isoformat()
                }
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=json.dumps(results_with_meta, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"Stored {result_type} results: {file_key}")
            return {
                'success': True,
                's3_key': file_key,
                'session_path': session_path
            }
            
        except Exception as e:
            logger.error(f"Failed to store {result_type} results: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_public_download_link(self, data: Any, filename: str = None, 
                                  content_type: str = 'application/json') -> str:
        """Create public download link in downloads folder"""
        logger.info(f"[DEBUG] create_public_download_link called with data type: {type(data)}")
        logger.info(f"[DEBUG] create_public_download_link filename: {filename}")
        logger.info(f"[DEBUG] create_public_download_link content_type: {content_type}")
        
        try:
            download_uuid = str(uuid.uuid4())
            download_key = f"downloads/{download_uuid}/{filename or 'download.json'}"
            logger.info(f"[DEBUG] Generated download_key: {download_key}")
            
            # Prepare content
            try:
                if isinstance(data, (dict, list)):
                    content = json.dumps(data, indent=2)
                    logger.info(f"[DEBUG] Data is dict/list, converted to JSON, size: {len(content)}")
                elif isinstance(data, bytes):
                    content = data
                    logger.info(f"[DEBUG] Data is bytes, size: {len(content)}")
                else:
                    content = str(data)
                    logger.info(f"[DEBUG] Data converted to string, size: {len(content)}")
                
                # Debug logging
                logger.info(f"[DEBUG] S3 Upload - Data type: {type(data)}, Content size: {len(content) if hasattr(content, '__len__') else 'unknown'}")
                logger.info(f"[DEBUG] S3 Upload - Key: {download_key}, ContentType: {content_type}")
                
            except Exception as e:
                logger.error(f"[DEBUG] Error during content preparation: {e}")
                import traceback
                logger.error(f"[DEBUG] Content preparation traceback: {traceback.format_exc()}")
                raise
            
            # Store in public downloads folder
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=download_key,
                Body=content,
                ContentType=content_type,
                Metadata={
                    'created_at': datetime.now().isoformat(),
                    'expires_after': '7_days'
                }
            )
            
            # Verify upload by checking object size
            try:
                response = self.s3_client.head_object(Bucket=self.bucket_name, Key=download_key)
                uploaded_size = response['ContentLength']
                logger.info(f"[DEBUG] S3 Upload verified - Object size: {uploaded_size} bytes")
            except Exception as e:
                logger.error(f"[DEBUG] Failed to verify S3 upload: {e}")
            
            # Generate public URL
            public_url = f"https://{self.bucket_name}.s3.amazonaws.com/{download_key}"
            
            logger.info(f"Created public download link: {download_key}")
            return public_url
            
        except Exception as e:
            logger.error(f"Failed to create download link: {e}")
            return ""
    
    def cache_api_response(self, service: str, request_hash: str, 
                          response_data: Dict) -> Dict[str, Any]:
        """Cache API response in cache folder"""
        try:
            cache_key = f"cache/{service}/{request_hash}/response.json"
            
            cache_data = {
                'response': response_data,
                'cached_at': datetime.now().isoformat(),
                'service': service,
                'request_hash': request_hash
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=cache_key,
                Body=json.dumps(cache_data, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"Cached {service} response: {cache_key}")
            return {
                'success': True,
                'cache_key': cache_key
            }
            
        except Exception as e:
            logger.error(f"Failed to cache {service} response: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_cached_response(self, service: str, request_hash: str, cache_ttl_days: int = 1) -> Optional[Dict]:
        """Get cached API response. Returns full cache_data dict with 'expired' flag."""
        try:
            cache_key = f"cache/{service}/{request_hash}/response.json"

            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=cache_key)
            cache_data = json.loads(response['Body'].read().decode('utf-8'))

            # Check if cache is still valid
            cached_at_str = cache_data['cached_at']
            # Handle timezone formats: 'Z' suffix or '+00:00'
            if cached_at_str.endswith('Z'):
                cached_at_str = cached_at_str.replace('Z', '+00:00')
            cached_at = datetime.fromisoformat(cached_at_str)
            # Ensure timezone-aware comparison
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - cached_at
            if age > timedelta(days=cache_ttl_days):
                logger.info(f"Cache expired for {service}/{request_hash} (age: {age.days}d, TTL: {cache_ttl_days} days)")
                cache_data['expired'] = True
            else:
                cache_data['expired'] = False

            logger.info(f"Retrieved cached {service} response: {cache_key}")
            return cache_data

        except Exception as e:
            logger.debug(f"Cache miss for {service}/{request_hash}: {e}")
            return None
    
    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """Generate presigned URL for private files"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return ""
    
    def list_session_files(self, email: str, session_id: str) -> Dict[str, Any]:
        """List all files in a session folder"""
        try:
            session_path = self.get_session_path(email, session_id)
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=session_path
            )
            
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    files.append({
                        'key': obj['Key'],
                        'filename': obj['Key'].split('/')[-1],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'].isoformat(),
                        'download_url': self.generate_presigned_url(obj['Key'])
                    })
            
            return {
                'success': True,
                'session_path': session_path,
                'files': files,
                'count': len(files)
            }
            
        except Exception as e:
            logger.error(f"Failed to list session files: {e}")
            return {
                'success': False,
                'error': str(e),
                'files': []
            }
    
    def get_latest_validation_results(self, email: str, session_id: str) -> Optional[Dict]:
        """Get the latest validation results for a session, preferring session_info.json lookup"""
        try:
            # First try to get latest results path from session_info.json
            try:
                session_info = self.load_session_info(email, session_id)
                
                # Find the latest version with validation results
                versions = session_info.get('versions', {})
                latest_version = 0
                latest_results_path = None
                
                for version_str, version_data in versions.items():
                    try:
                        version_num = int(version_str)
                        validation = version_data.get('validation', {})
                        
                        if validation and version_num > latest_version:
                            # Get the validation results from this version
                            if validation.get('results_path'):
                                latest_version = version_num
                                latest_results_path = validation['results_path']
                    except (ValueError, TypeError):
                        continue
                
                if latest_results_path:
                    logger.info(f"Found latest validation results in session_info.json: {latest_results_path}")
                    response = self.s3_client.get_object(
                        Bucket=self.bucket_name,
                        Key=latest_results_path
                    )
                    results_data = json.loads(response['Body'].read().decode('utf-8'))
                    logger.info(f"Successfully retrieved validation results from session_info path")
                    return results_data
                else:
                    logger.info("No validation results paths found in session_info.json")
                    
            except Exception as e:
                logger.info(f"Could not get validation results from session_info.json, falling back to file scanning: {e}")
            
            # Fallback to file scanning if session_info.json doesn't have the path
            session_path = self.get_session_path(email, session_id)
            logger.info(f"DEBUG_VALIDATION_RESULTS: Searching for validation results in session_path: {session_path}")
            
            # List ALL objects in session folder first to debug what's actually there
            all_objects_response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=session_path
            )
            
            if 'Contents' in all_objects_response:
                logger.info(f"DEBUG_VALIDATION_RESULTS: Found {len(all_objects_response['Contents'])} total objects in session folder:")
                for obj in all_objects_response['Contents']:
                    logger.info(f"DEBUG_VALIDATION_RESULTS: - {obj['Key']}")
            else:
                logger.warning(f"DEBUG_VALIDATION_RESULTS: No objects found in session folder: {session_path}")
                
            # Method 1: Try using CommonPrefixes approach for versioned result folders
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=f"{session_path}v",
                Delimiter='/'
            )
            
            result_folders = []
            if 'CommonPrefixes' in response:
                logger.info(f"DEBUG_VALIDATION_RESULTS: Found {len(response['CommonPrefixes'])} CommonPrefixes with v prefix:")
                for prefix_info in response['CommonPrefixes']:
                    folder_path = prefix_info['Prefix']
                    folder_name = folder_path.rstrip('/').split('/')[-1]
                    logger.info(f"DEBUG_VALIDATION_RESULTS: Checking folder: {folder_path} -> {folder_name}")
                    if folder_name.endswith('_results'):
                        # Extract version number
                        try:
                            version_str = folder_name.replace('_results', '').replace('v', '')
                            version = int(version_str)
                            result_folders.append((version, folder_path))
                            logger.info(f"DEBUG_VALIDATION_RESULTS: Added result folder: version {version}, path {folder_path}")
                        except ValueError:
                            logger.warning(f"DEBUG_VALIDATION_RESULTS: Could not extract version from folder: {folder_name}")
                            continue
            else:
                logger.info(f"DEBUG_VALIDATION_RESULTS: No CommonPrefixes found with v prefix")
            
            # Method 2: If CommonPrefixes didn't work, scan all objects and identify result folders manually
            if not result_folders:
                logger.info(f"DEBUG_VALIDATION_RESULTS: CommonPrefixes approach failed, trying direct object scan...")
                all_response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=session_path
                )
                
                if 'Contents' in all_response:
                    folder_versions = set()
                    for obj in all_response['Contents']:
                        key = obj['Key']
                        # Look for pattern: session_path + v{number}_results/...
                        relative_path = key[len(session_path):]
                        if '/' in relative_path:
                            folder_part = relative_path.split('/')[0]
                            if folder_part.startswith('v') and folder_part.endswith('_results'):
                                try:
                                    version_str = folder_part.replace('_results', '').replace('v', '')
                                    version = int(version_str)
                                    folder_path = f"{session_path}{folder_part}/"
                                    folder_versions.add((version, folder_path))
                                    logger.info(f"DEBUG_VALIDATION_RESULTS: Found result folder via object scan: v{version} -> {folder_path}")
                                except ValueError:
                                    continue
                    
                    result_folders = list(folder_versions)
                    logger.info(f"DEBUG_VALIDATION_RESULTS: Object scan found {len(result_folders)} result folders")
                
            # Also check for validation results files directly in the session folder (alternative storage pattern)
            direct_results_patterns = [
                f"{session_path}validation_results.json",
                f"{session_path}preview_results.json"
            ]
            
            logger.info(f"DEBUG_VALIDATION_RESULTS: Checking for direct validation results files...")
            for pattern in direct_results_patterns:
                try:
                    response = self.s3_client.get_object(Bucket=self.bucket_name, Key=pattern)
                    results_data = json.loads(response['Body'].read().decode('utf-8'))
                    logger.info(f"DEBUG_VALIDATION_RESULTS: Found direct validation results at: {pattern}")
                    return results_data
                except Exception as e:
                    logger.info(f"DEBUG_VALIDATION_RESULTS: No direct results at {pattern}: {e}")
                    pass
            
            if not result_folders:
                logger.info(f"No validation results found for session {session_id}")
                return None
            
            # Get the latest version
            latest_version, latest_folder = max(result_folders, key=lambda x: x[0])
            logger.info(f"DEBUG_VALIDATION_RESULTS: Selected latest version {latest_version} with folder path: {latest_folder}")
            
            # Try to get validation results from the latest folder - check both full and preview results
            # First try full validation results
            results_key = f"{latest_folder}validation_results.json"
            logger.info(f"DEBUG_VALIDATION_RESULTS: Trying to access validation results at: {results_key}")
            
            try:
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=results_key)
                results_data = json.loads(response['Body'].read().decode('utf-8'))
                logger.info(f"Retrieved latest full validation results from version {latest_version}")
                return results_data
            except Exception as e:
                logger.info(f"Full validation results not found at {results_key}: {e}")
                
            # Fallback to preview results if full validation not available
            preview_results_key = f"{latest_folder}preview_results.json"
            
            try:
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=preview_results_key)
                results_data = json.loads(response['Body'].read().decode('utf-8'))
                logger.info(f"Retrieved latest preview results from version {latest_version}")
                return results_data
            except Exception as e:
                logger.warning(f"Could not retrieve preview results from {preview_results_key}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get latest validation results: {e}")
            return None
    
    def get_latest_preview_results(self, email: str, session_id: str) -> Optional[Dict]:
        """Get the latest preview results for a session, preferring session_info.json lookup"""
        try:
            # First try to get latest preview results path from session_info.json
            try:
                session_info = self.load_session_info(email, session_id)
                
                # Find the latest version with preview results
                versions = session_info.get('versions', {})
                latest_version = 0
                latest_results_path = None
                
                for version_str, version_data in versions.items():
                    try:
                        version_num = int(version_str)
                        preview = version_data.get('preview', {})
                        
                        if preview and version_num > latest_version:
                            # Get the preview results from this version
                            if preview.get('results_path'):
                                latest_version = version_num
                                latest_results_path = preview['results_path']
                    except (ValueError, TypeError):
                        continue
                
                if latest_results_path:
                    logger.info(f"Found latest preview results in session_info.json: {latest_results_path}")
                    response = self.s3_client.get_object(
                        Bucket=self.bucket_name,
                        Key=latest_results_path
                    )
                    results_data = json.loads(response['Body'].read().decode('utf-8'))
                    logger.info(f"Successfully retrieved preview results from session_info path")
                    return results_data
                else:
                    logger.info("No preview results paths found in session_info.json")
                    
            except Exception as e:
                logger.info(f"Could not get preview results from session_info.json, falling back to file scanning: {e}")
            
            # Fallback: try to find preview results using similar logic to validation results
            # (reuse the same file scanning approach but look for preview_results.json files)
            session_path = self.get_session_path(email, session_id)
            
            # Check for preview results files directly in versioned folders
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=f"{session_path}v",
                Delimiter='/'
            )
            
            result_folders = []
            if 'CommonPrefixes' in response:
                for prefix_info in response['CommonPrefixes']:
                    folder_path = prefix_info['Prefix']
                    folder_name = folder_path.rstrip('/').split('/')[-1]
                    if folder_name.endswith('_results'):
                        try:
                            version_str = folder_name.replace('_results', '').replace('v', '')
                            version = int(version_str)
                            result_folders.append((version, folder_path))
                        except ValueError:
                            continue
            
            # Sort by version descending and try to get preview results
            result_folders.sort(reverse=True)
            for version, folder_path in result_folders:
                try:
                    preview_key = f"{folder_path}preview_results.json"
                    response = self.s3_client.get_object(Bucket=self.bucket_name, Key=preview_key)
                    results_data = json.loads(response['Body'].read().decode('utf-8'))
                    logger.info(f"Found preview results in versioned folder: {preview_key}")
                    return results_data
                except Exception:
                    continue
            
            logger.info(f"No preview results found for session {session_id}")
            return None
                
        except Exception as e:
            logger.error(f"Failed to get latest preview results: {e}")
            return None
    
    def get_latest_results_for_context(self, email: str, session_id: str) -> Optional[Dict]:
        """Get latest results (validation or preview) for config refinement context.
        Uses file scanning to avoid circular dependencies during config generation."""
        try:
            session_path = self.get_session_path(email, session_id)
            logger.info(f"Getting latest results for config context from: {session_path}")
            
            # Use file scanning approach to avoid session_info.json dependency
            # Look for versioned result folders
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=f"{session_path}v",
                Delimiter='/'
            )
            
            result_folders = []
            if 'CommonPrefixes' in response:
                for prefix_info in response['CommonPrefixes']:
                    folder_path = prefix_info['Prefix']
                    folder_name = folder_path.rstrip('/').split('/')[-1]
                    if folder_name.endswith('_results'):
                        try:
                            version_str = folder_name.replace('_results', '').replace('v', '')
                            version = int(version_str)
                            result_folders.append((version, folder_path))
                        except ValueError:
                            continue
            
            # Sort by version descending (newest first)
            result_folders.sort(reverse=True)
            
            # Try validation results first, then preview results
            for version, folder_path in result_folders:
                # Try validation results
                try:
                    validation_key = f"{folder_path}validation_results.json"
                    response = self.s3_client.get_object(Bucket=self.bucket_name, Key=validation_key)
                    results_data = json.loads(response['Body'].read().decode('utf-8'))
                    logger.info(f"Found validation results for context: {validation_key}")
                    return results_data
                except Exception:
                    pass
                
                # Try preview results if validation not found
                try:
                    preview_key = f"{folder_path}preview_results.json"
                    response = self.s3_client.get_object(Bucket=self.bucket_name, Key=preview_key)
                    results_data = json.loads(response['Body'].read().decode('utf-8'))
                    logger.info(f"Found preview results for context: {preview_key}")
                    return results_data
                except Exception:
                    continue
            
            logger.info(f"No results found for config context in session {session_id}")
            return None
                
        except Exception as e:
            logger.error(f"Failed to get latest results for context: {e}")
            return None
    
    def load_session_info(self, email: str, session_id: str) -> Dict:
        """Load session_info.json or create empty structure if it doesn't exist"""
        try:
            session_path = self.get_session_path(email, session_id)
            session_info_key = f"{session_path}session_info.json"
            
            try:
                response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=session_info_key
                )
                session_info = json.loads(response['Body'].read().decode('utf-8'))
                logger.debug(f"Loaded existing session_info.json for {session_id}")
                
                # Clean up old structure fields to ensure clean format
                old_fields_to_remove = ['config_history', 'current_config_version', 'total_configs']
                for field in old_fields_to_remove:
                    if field in session_info:
                        logger.debug(f"Removing old session field: {field}")
                        del session_info[field]
                
                # Ensure versions structure exists
                if 'versions' not in session_info:
                    session_info['versions'] = {}
                
                return session_info
            except self.s3_client.exceptions.NoSuchKey:
                # Create new session_info structure with clean version-based organization
                logger.info(f"Creating new session_info.json for {session_id}")
                return {
                    "session_id": session_id,
                    "created": datetime.now().isoformat(),
                    "email": email,
                    "table_name": f"table_{session_id.split('_')[-1]}",
                    "current_version": 0,
                    "last_updated": datetime.now().isoformat(),
                    "versions": {}
                }
        except Exception as e:
            logger.error(f"Failed to load session_info.json: {e}")
            # Return minimal structure for fallback
            return {
                "session_id": session_id,
                "created": datetime.now().isoformat(),
                "email": email,
                "table_name": f"table_{session_id.split('_')[-1]}",
                "current_version": 0,
                "last_updated": datetime.now().isoformat(),
                "versions": {}
            }
    
    def save_session_info(self, email: str, session_id: str, session_info: Dict) -> bool:
        """Save updated session_info.json"""
        try:
            session_path = self.get_session_path(email, session_id)
            session_info_key = f"{session_path}session_info.json"
            
            # Update timestamp (use existing field name)
            session_info['last_updated'] = datetime.now().isoformat()
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=session_info_key,
                Body=json.dumps(session_info, indent=2),
                ContentType='application/json'
            )
            logger.info(f"Saved session_info.json for {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save session_info.json: {e}")
            return False
    
    def update_session_config(self, email: str, session_id: str, config_data: Dict, 
                            config_key: str, config_id: str, version: int, 
                            source: str, description: str = None, source_session: str = None,
                            excel_s3_key: str = None, source_config_path: str = None, run_key: str = None) -> bool:
        """Update session_info.json with new config information organized by version"""
        try:
            session_info = self.load_session_info(email, session_id)
            
            # Get Excel file path - prefer provided path, then from existing session_info, fallback to file scan
            if not excel_s3_key:
                # First try existing session_info (if we're updating an existing session)
                excel_s3_key = session_info.get('table_path')
                
                # If still not found, do file scan as last resort
                if not excel_s3_key:
                    excel_content, excel_s3_key = self.get_excel_file(email, session_id, bypass_session_info=True)
            
            # Create clean version-based tracking structure
            if "versions" not in session_info:
                session_info["versions"] = {}
            
            # Create clean version entry
            version_entry = {
                "config": {
                    "config_id": config_id,
                    "config_path": config_key,
                    "source": source,
                    "created_at": datetime.now().isoformat(),
                    "description": description or ""
                }
                # preview and validation will be added when operations complete
            }
            
            if source_session:
                version_entry["config"]["source_session"] = source_session
            
            if source_config_path:
                version_entry["config"]["source_config_path"] = source_config_path
            
            if run_key:
                version_entry["config"]["run_key"] = run_key
            
            # Store version entry
            session_info["versions"][str(version)] = version_entry
            
            # Update session-level tracking (clean structure)
            session_info["current_version"] = version
            session_info["last_updated"] = datetime.now().isoformat()
            
            # Ensure basic session info fields are set
            if "session_id" not in session_info:
                session_info["session_id"] = session_id
            if "email" not in session_info:
                session_info["email"] = email
            if "table_name" not in session_info:
                # Generate table name from session ID if not set
                session_info["table_name"] = f"table_{session_id.split('_')[-1]}"
            
            # Store table path at session level (doesn't change per version)
            if excel_s3_key:
                session_info["table_path"] = excel_s3_key
            
            return self.save_session_info(email, session_id, session_info)
        except Exception as e:
            logger.error(f"Failed to update session config: {e}")
            return False
    
    def update_session_results(self, email: str, session_id: str, operation_type: str,
                             config_id: str, version: int, run_key: str,
                             results_path: str = None, enhanced_excel_path: str = None,
                             status: str = "completed", completed_at: str = None,
                             frontend_payload: Dict = None) -> bool:
        """Update session_info.json with results information and complete frontend payload for UX analysis"""
        try:
            logger.info(f"[SESSION_TRACKING] Updating {operation_type} results for session {session_id}, version {version}")
            
            session_info = self.load_session_info(email, session_id)
            
            # Ensure versions structure exists
            if "versions" not in session_info:
                session_info["versions"] = {}
            
            # Ensure version entry exists
            version_key = str(version)
            if version_key not in session_info["versions"]:
                # Create minimal version entry if it doesn't exist
                session_info["versions"][version_key] = {
                    "version": version,
                    "config": {"config_id": config_id}
                }
            
            # Create results entry with essential file paths and run lookup
            result_entry = {
                "run_key": run_key,  # Key to lookup full details in runs database
                "status": status,
                "completed_at": completed_at or datetime.now().isoformat()
            }
            
            # Add file paths if provided
            if results_path:
                result_entry["results_path"] = results_path  # Path to validation_results.json or preview_results.json
            if enhanced_excel_path:
                result_entry["enhanced_excel_path"] = enhanced_excel_path  # Path to enhanced Excel file
            if frontend_payload:
                result_entry["frontend_payload"] = frontend_payload  # Complete payload sent to frontend for UX analysis
            
            # Set singular preview/validation object
            if operation_type == "preview":
                session_info["versions"][version_key]["preview"] = result_entry
                logger.info(f"[SESSION_TRACKING] Set preview for version {version}")
            elif operation_type == "validation":
                session_info["versions"][version_key]["validation"] = result_entry
                logger.info(f"[SESSION_TRACKING] Set validation for version {version}")
            
            return self.save_session_info(email, session_id, session_info)
        except Exception as e:
            logger.error(f"Failed to update session results: {e}")
            return False
    
    def update_session_costs(self, email: str, session_id: str, version: int, operation_type: str,
                           eliyahu_cost: float = None, quoted_cost: float = None, 
                           estimated_cost: float = None, cost_details: dict = None, 
                           run_id: str = None, run_key: str = None) -> bool:
        """Update cost information for a specific version and operation type"""
        try:
            session_info = self.load_session_info(email, session_id)
            
            # Ensure versions structure exists
            if "versions" not in session_info:
                session_info["versions"] = {}
            
            version_key = str(version)
            if version_key not in session_info["versions"]:
                logger.warning(f"Version {version} not found in session_info, cannot update costs")
                return False
            
            # Find the most recent operation of the specified type for this version
            operations = session_info["versions"][version_key].get(f"{operation_type}s", [])
            if not operations:
                logger.warning(f"No {operation_type} operations found for version {version}")
                return False
            
            # Update the most recent operation's cost info
            latest_operation = operations[-1]
            
            # Build comprehensive cost info
            cost_info = latest_operation.get("cost_info", {})
            
            if eliyahu_cost is not None:
                cost_info["eliyahu_cost"] = eliyahu_cost
            if quoted_cost is not None:
                cost_info["quoted_cost"] = quoted_cost
            if estimated_cost is not None:
                cost_info["estimated_cost"] = estimated_cost
            
            cost_info["processing_type"] = operation_type
            cost_info["cost_updated_at"] = datetime.now().isoformat()
            
            # Add run identifiers for runs table linkage
            if run_id:
                cost_info["run_id"] = run_id
            if run_key:
                cost_info["run_key"] = run_key
            
            # Add detailed cost breakdown if provided
            if cost_details:
                cost_info.update(cost_details)
            
            latest_operation["cost_info"] = cost_info
            
            # Update summary costs at session level
            if operation_type == "preview":
                if "latest_preview_cost" not in session_info:
                    session_info["latest_preview_cost"] = {}
                session_info["latest_preview_cost"] = cost_info.copy()
            elif operation_type == "validation":
                if "latest_validation_cost" not in session_info:
                    session_info["latest_validation_cost"] = {}
                session_info["latest_validation_cost"] = cost_info.copy()
            
            return self.save_session_info(email, session_id, session_info)
        except Exception as e:
            logger.error(f"Failed to update session costs: {e}")
            return False
    
    def add_session_refinement(self, email: str, session_id: str, from_version: int,
                             to_version: int, triggered_by: str, changes_made: list = None,
                             context_used: dict = None) -> bool:
        """Add refinement entry to session_info.json with full context paths"""
        try:
            session_info = self.load_session_info(email, session_id)

            refinement_entry = {
                "from_version": from_version,
                "to_version": to_version,
                "triggered_by": triggered_by,
                "refinement_timestamp": datetime.now().isoformat(),
                "from_config_path": "",  # Will be populated from session_info
                "to_config_path": ""     # Will be populated after new config is stored
            }

            # Find the config path for the from_version using clean structure
            versions = session_info.get("versions", {})
            from_version_data = versions.get(str(from_version))
            if from_version_data and from_version_data.get("config"):
                refinement_entry["from_config_path"] = from_version_data["config"].get("config_path", "")

            # Add context file paths used for refinement
            if context_used:
                refinement_entry["context_used"] = context_used
            else:
                # Auto-populate context from version-based structure
                context_used = {}
                if from_version_data:
                    # Get preview and validation results from the version being refined
                    if from_version_data.get("preview", {}).get("results_path"):
                        context_used["preview_results_path"] = from_version_data["preview"]["results_path"]
                    if from_version_data.get("validation", {}).get("results_path"):
                        context_used["validation_results_path"] = from_version_data["validation"]["results_path"]
                    if from_version_data.get("validation", {}).get("enhanced_excel_path"):
                        context_used["validation_enhanced_excel_path"] = from_version_data["validation"]["enhanced_excel_path"]

                refinement_entry["context_used"] = context_used

            if changes_made:
                refinement_entry["changes_made"] = changes_made

            # Skip refinements tracking - refinements generate new config versions instead
            # This function is deprecated and should not be used
            logger.warning("add_session_refinement is deprecated - refinements create new config versions")

            return self.save_session_info(email, session_id, session_info)
        except Exception as e:
            logger.error(f"Failed to add session refinement: {e}")
            return False

    def update_validation_runs(self, email: str, session_id: str, run_data: dict, is_preview: bool = False) -> bool:
        """
        Update the validation_runs array in session_info.json

        Args:
            email: User email
            session_id: Clean session ID
            run_data: Dict with keys: config_s3_key, total_rows, total_columns,
                     confidences_original, confidences_updated
            is_preview: Whether this is a preview run

        Returns:
            True if successful, False otherwise
        """
        try:
            import time

            session_info = self.load_session_info(email, session_id)

            # Ensure validation_runs array exists
            if 'validation_runs' not in session_info:
                session_info['validation_runs'] = []

            # Generate run_key: {session_id}_{unix_timestamp}
            run_key = f"{session_id}_{int(time.time())}"

            if is_preview:
                # Preview: overwrite run_number 1 if it exists
                session_info['validation_runs'] = [r for r in session_info['validation_runs'] if r.get('run_number') != 1]

                new_run = {
                    'run_number': 1,
                    'run_time': datetime.now(timezone.utc).isoformat(),
                    'session_id': session_id,
                    'configuration_id': run_data.get('config_s3_key', ''),
                    'run_key': run_key,
                    'rows': run_data.get('total_rows', 0),
                    'columns': run_data.get('total_columns', 0),
                    'confidences_original': run_data.get('confidences_original', ''),
                    'confidences_updated': run_data.get('confidences_updated', ''),
                    'is_preview': True
                }
                session_info['validation_runs'].insert(0, new_run)
                logger.info(f"[VALIDATION_RUNS] Created preview run (run_number=1) for session {session_id}")
            else:
                # Full validation
                existing_runs = session_info.get('validation_runs', [])

                # Check if run_number 1 is a preview
                if existing_runs and existing_runs[0].get('is_preview') and existing_runs[0].get('run_number') == 1:
                    # Overwrite preview with full validation
                    session_info['validation_runs'][0] = {
                        'run_number': 1,
                        'run_time': datetime.now(timezone.utc).isoformat(),
                        'session_id': session_id,
                        'configuration_id': run_data.get('config_s3_key', ''),
                        'run_key': run_key,
                        'rows': run_data.get('total_rows', 0),
                        'columns': run_data.get('total_columns', 0),
                        'confidences_original': run_data.get('confidences_original', ''),
                        'confidences_updated': run_data.get('confidences_updated', ''),
                        'is_preview': False
                    }
                    logger.info(f"[VALIDATION_RUNS] Overwrote preview with full validation (run_number=1) for session {session_id}")
                else:
                    # Append as new run
                    next_run_number = max([r.get('run_number', 0) for r in existing_runs], default=0) + 1
                    new_run = {
                        'run_number': next_run_number,
                        'run_time': datetime.now(timezone.utc).isoformat(),
                        'session_id': session_id,
                        'configuration_id': run_data.get('config_s3_key', ''),
                        'run_key': run_key,
                        'rows': run_data.get('total_rows', 0),
                        'columns': run_data.get('total_columns', 0),
                        'confidences_original': run_data.get('confidences_original', ''),
                        'confidences_updated': run_data.get('confidences_updated', ''),
                        'is_preview': False
                    }
                    session_info['validation_runs'].append(new_run)
                    logger.info(f"[VALIDATION_RUNS] Appended full validation (run_number={next_run_number}) for session {session_id}")

            # Save updated session_info
            return self.save_session_info(email, session_id, session_info)

        except Exception as e:
            logger.error(f"Failed to update validation_runs: {e}")
            return False

    def find_config_by_id(self, config_id: str, email: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Clean config lookup function that handles both new and legacy config ID formats.

        New format: {session_id}_{filename_without_extension}
        Example: session_20250918_150921_ea332116_config_v1_ai_generated
        Maps to: session_20250918_150921_ea332116/config_v1_ai_generated.json

        Legacy format: {session_id}_v{version}_{description}
        Example: session_20250918_150921_ea332116_v1_Configuration_for_AIML_co
        Requires fallback search
        """
        try:
            logger.info(f"[FIND_CONFIG_BY_ID] Looking up config_id: {config_id}")

            # STRATEGY 1: Try new clean format first (direct path construction)
            session_id = None
            filename = None

            # FIRST: Pattern-based session parsing using regex (more robust than fixed-length)
            import re

            # Match session pattern: session_YYYYMMDD_HHMMSS_XXXXXXXX or session_demo_YYYYMMDD_HHMMSS_XXXXXXXX
            session_pattern = r'^(session_(?:demo_)?\d{8}_\d{6}_[a-f0-9]{8})'
            match = re.match(session_pattern, config_id)

            if match:
                session_id = match.group(1)
                remaining = config_id[len(session_id):]
                if remaining.startswith('_'):
                    filename = remaining[1:] + '.json'  # Remove leading underscore
                    logger.info(f"[FIND_CONFIG_BY_ID] Parsed with regex: session={session_id}, filename={filename}")

            # FALLBACK: New format with _config_v marker
            elif '_config_v' in config_id:
                # Parse: {session_id}_config_v{version}_{source} -> {session_id}/config_v{version}_{source}.json
                config_v_pos = config_id.find('_config_v')
                if config_v_pos > 0:
                    session_id = config_id[:config_v_pos]
                    filename = config_id[config_v_pos + 1:] + '.json'  # Skip the leading underscore
                    logger.info(f"[FIND_CONFIG_BY_ID] Parsed with _config_v marker: session={session_id}, filename={filename}")

            # Try direct lookup if we successfully parsed
            if session_id and filename:
                session_path = self.get_session_path(email, session_id)
                config_key = f"{session_path}{filename}"

                logger.info(f"[FIND_CONFIG_BY_ID] Trying direct lookup: {config_key}")

                try:
                    config_response = self.s3_client.get_object(Bucket=self.bucket_name, Key=config_key)
                    config_data = json.loads(config_response['Body'].read().decode('utf-8'))
                    logger.info(f"[FIND_CONFIG_BY_ID] SUCCESS - Found config: {config_id} -> {filename}")
                    return config_data, config_key
                except self.s3_client.exceptions.NoSuchKey:
                    logger.warning(f"[FIND_CONFIG_BY_ID] Config not found at {config_key}, trying legacy lookup")
                except Exception as e:
                    logger.warning(f"[FIND_CONFIG_BY_ID] Error with direct lookup: {e}, trying legacy lookup")
            else:
                logger.warning(f"[FIND_CONFIG_BY_ID] Could not parse config_id with regex or _config_v marker")

            # STRATEGY 2: Legacy lookup (existing complex logic)
            result = self._legacy_get_config_by_id(config_id, email)
            if result[0]:
                logger.info(f"[FIND_CONFIG_BY_ID] SUCCESS via legacy lookup: {config_id}")
                return result

            # STRATEGY 3: FALLBACK for legacy duplicated config IDs
            # Try stripping duplicate session prefixes and suffixes
            # Pattern: session_A_session_B_config_v1_ai_generated_config_v1_ai_generated
            # Should be: session_B_config_v1_ai_generated
            import re
            session_pattern = r'^(session_(?:demo_)?\d{8}_\d{6}_[a-f0-9]{8})_(session_(?:demo_)?\d{8}_\d{6}_[a-f0-9]{8})_(.+)'
            match = re.match(session_pattern, config_id)

            if match:
                # Has double session prefix - use the second (source) session
                source_session = match.group(2)
                remainder = match.group(3)

                # Check for duplicated suffix
                suffix_parts = remainder.split('_')
                if len(suffix_parts) >= 2:
                    midpoint = len(suffix_parts) // 2
                    first_half = '_'.join(suffix_parts[:midpoint])
                    second_half = '_'.join(suffix_parts[midpoint:])

                    if first_half == second_half:
                        # Duplicated suffix - use first half
                        clean_config_id = f"{source_session}_{first_half}"
                        logger.warning(f"[FIND_CONFIG_BY_ID] Trying fallback for legacy duplicate: {config_id} -> {clean_config_id}")

                        result = self.find_config_by_id(clean_config_id, email)
                        if result[0]:
                            logger.info(f"[FIND_CONFIG_BY_ID] SUCCESS via legacy duplicate fallback")
                            return result

            logger.error(f"[FIND_CONFIG_BY_ID] FAILED - Could not find config: {config_id}")
            return None, None

        except Exception as e:
            logger.error(f"[FIND_CONFIG_BY_ID] Exception for {config_id}: {e}")
            return None, None

    def get_config_by_id(self, config_id: str, email: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Get config by config ID - delegates to find_config_by_id for clean implementation"""
        return self.find_config_by_id(config_id, email)

    def _legacy_get_config_by_id(self, config_id: str, email: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Legacy config lookup with fallback search strategies"""
        try:
            # Parse config_id to extract session_id and version
            # Format: {session_id}_v{version}_{description}
            parts = config_id.split('_v')
            if len(parts) < 2:
                logger.warning(f"Invalid config_id format: {config_id}")
                return None, None
            
            session_id = parts[0]
            version_part = parts[1].split('_')[0]
            
            try:
                version = int(version_part)
            except ValueError:
                logger.warning(f"Invalid version in config_id: {config_id}")
                return None, None
            
            # Get session path and construct config key
            session_path = self.get_session_path(email, session_id)
            
            # STRATEGY 1: Try standard config filename patterns first
            potential_keys = [
                f"{session_path}config_v{version}_user.json",
                f"{session_path}config_v{version}_upload.json", 
                f"{session_path}config_v{version}_ai_generated.json",
                f"{session_path}config_v{version}_copied_from_previous.json",
                f"{session_path}config_v{version}_used_by_id.json"
            ]
            
            # STRATEGY 2: Search for session+name pattern (preserved filenames with session prefix)
            all_files_response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=session_path
            )
            
            if 'Contents' in all_files_response:
                for obj in all_files_response['Contents']:
                    filename = obj['Key'].split('/')[-1]
                    # Look for files starting with session_id (session_filename.json pattern)
                    if filename.startswith(session_id) and filename.endswith('.json'):
                        potential_keys.insert(0, obj['Key'])  # Prioritize session+name files
                    # Also add any .json files that might contain version info
                    elif filename.endswith('.json') and obj['Key'] not in potential_keys:
                        potential_keys.append(obj['Key'])
            
            # STRATEGY 3: Search by version prefix for any remaining matches
            version_search_response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=f"{session_path}config_v{version}_"
            )
            
            if 'Contents' in version_search_response:
                for obj in version_search_response['Contents']:
                    if obj['Key'] not in potential_keys:
                        potential_keys.insert(0, obj['Key'])
            
            # Try to find and validate the config
            for key in potential_keys:
                try:
                    config_response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                    config_data = json.loads(config_response['Body'].read().decode('utf-8'))
                    
                    # Verify this config matches the requested ID
                    stored_config_id = config_data.get('storage_metadata', {}).get('config_id')
                    if stored_config_id == config_id:
                        filename = key.split('/')[-1]
                        logger.info(f"Found config by ID: {config_id} in file: {filename}")
                        return config_data, key
                        
                except Exception as e:
                    logger.debug(f"Failed to retrieve config from {key}: {e}")
                    continue
            
            logger.warning(f"Config not found for ID: {config_id}")
            return None, None
            
        except Exception as e:
            logger.error(f"Failed to get config by ID: {e}")
            return None, None