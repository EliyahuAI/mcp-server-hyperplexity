"""
Unified S3 Storage Manager for Hyperplexity.
Replaces multiple bucket approach with single, well-organized bucket structure.
"""

import os
import json
import boto3
import uuid
from datetime import datetime, timedelta
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
    └── cache/{service}/{hash}/                                        (30 days)
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
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=file_content,
                ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                Metadata={
                    'session_id': session_id,
                    'email': email,
                    'upload_timestamp': datetime.now().isoformat()
                }
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
            else:
                config_filename = f"config_v{version}_{source}.json"
            
            file_key = f"{session_path}{config_filename}"
            
            # Generate clean config ID that matches the filename structure
            # New format: {session_id}_{filename_without_extension}
            # Example: session_20250918_150921_ea332116_config_v1_ai_generated
            # Maps to: session_20250918_150921_ea332116/config_v1_ai_generated.json
            filename_without_ext = config_filename.replace('.json', '')
            config_id = f"{session_id}_{filename_without_ext}"
            
            logger.info(f"Generated clean config ID: {config_id} for file: {config_filename}")
            
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
                           enhanced_excel_content: bytes = None, summary_text: str = None) -> Dict[str, Any]:
        """Store enhanced Excel and summary text in versioned results folder"""
        try:
            session_path = self.get_session_path(email, session_id)
            results_folder = f"{session_path}v{config_version}_results/"
            
            stored_files = []
            
            # Store enhanced Excel if provided
            if enhanced_excel_content:
                excel_key = f"{results_folder}enhanced_validation.xlsx"
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=excel_key,
                    Body=enhanced_excel_content,
                    ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                stored_files.append(excel_key)
                logger.info(f"Stored enhanced Excel: {excel_key}")
            
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
    
    def get_excel_file(self, email: str, session_id: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Get Excel file from session folder"""
        try:
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
        """Get latest config file from session folder"""
        try:
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
    
    def get_cached_response(self, service: str, request_hash: str) -> Optional[Dict]:
        """Get cached API response"""
        try:
            cache_key = f"cache/{service}/{request_hash}/response.json"
            
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=cache_key)
            cache_data = json.loads(response['Body'].read().decode('utf-8'))
            
            # Check if cache is still valid (within 30 days)
            cached_at = datetime.fromisoformat(cache_data['cached_at'])
            if datetime.now() - cached_at > timedelta(days=30):
                logger.info(f"Cache expired for {service}/{request_hash}")
                return None
            
            logger.info(f"Retrieved cached {service} response: {cache_key}")
            return cache_data['response']
            
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
        """Get the latest validation results for a session"""
        try:
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
            # STRATEGY 1: Try new clean format first (direct path construction)
            session_id = None
            filename = None
            
            # FIRST: Fixed-length session parsing (most common for copied configs)
            if len(config_id) > 32 and config_id.startswith('session_'):
                # Session format: session_YYYYMMDD_HHMMSS_XXXXXXXX (32 chars total)
                # Common when configs are copied: session_20250918_150921_ea332116_session_20250915_143022_abc_MarketResearch_Config
                session_id = config_id[:32]
                remaining = config_id[32:]
                if remaining.startswith('_'):
                    filename = remaining[1:] + '.json'  # Remove leading underscore
                    logger.debug(f"Parsed with fixed length (copied config): session={session_id}, filename={filename}")
            
            # SECOND: New format with _config_v marker
            elif '_config_v' in config_id:
                # Parse: {session_id}_config_v{version}_{source} -> {session_id}/config_v{version}_{source}.json
                config_v_pos = config_id.find('_config_v')
                if config_v_pos > 0:
                    session_id = config_id[:config_v_pos]
                    filename = config_id[config_v_pos + 1:] + '.json'  # Skip the leading underscore
                    logger.debug(f"Parsed with _config_v marker: session={session_id}, filename={filename}")
            
            # Try direct lookup if we successfully parsed
            if session_id and filename:
                session_path = self.get_session_path(email, session_id)
                config_key = f"{session_path}{filename}"
                
                logger.debug(f"Trying new format direct lookup: {config_id} -> {config_key}")
                
                try:
                    config_response = self.s3_client.get_object(Bucket=self.bucket_name, Key=config_key)
                    config_data = json.loads(config_response['Body'].read().decode('utf-8'))
                    logger.info(f"Found config by new format: {config_id} -> {filename}")
                    return config_data, config_key
                except self.s3_client.exceptions.NoSuchKey:
                    logger.debug(f"Config not found with new format, trying legacy lookup")
                except Exception as e:
                    logger.debug(f"Error with new format lookup: {e}")
            
            # STRATEGY 2: Legacy lookup (existing complex logic)
            return self._legacy_get_config_by_id(config_id, email)
            
        except Exception as e:
            logger.error(f"Failed to find config by ID: {e}")
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