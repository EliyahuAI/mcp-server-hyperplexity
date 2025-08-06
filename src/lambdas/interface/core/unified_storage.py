#!/usr/bin/env python3
"""
Unified Storage Manager for Perplexity Validator
Implements clean storage solution per specifications:
- S3 structure: email/email_domain/timestamp_id/
- Single storage per session, accessed throughout lifecycle
- Automatic file lifecycle management
"""

import os
import json
import boto3
import hashlib
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class UnifiedStorageManager:
    """Manages unified file storage for perplexity validator sessions"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
        
        # Use unified bucket if available, otherwise fallback to legacy
        if os.environ.get('S3_UNIFIED_BUCKET'):
            unified_bucket = os.environ.get('S3_UNIFIED_BUCKET')
            self.primary_bucket = unified_bucket
            self.results_bucket = unified_bucket
            self.use_unified_structure = True
            logger.info(f"UNIFIED_STORAGE: Using unified bucket: {unified_bucket}")
            
            # Download bucket needs special handling - check if separate download bucket is configured
            # The downloads folder in unified bucket has public permissions via bucket policy
            self.download_bucket = os.environ.get('S3_DOWNLOAD_BUCKET', unified_bucket)
            if self.download_bucket == unified_bucket:
                logger.info(f"UNIFIED_STORAGE: Downloads use unified bucket with public downloads/ folder")
            else:
                logger.info(f"UNIFIED_STORAGE: Downloads use separate public bucket: {self.download_bucket}")
        else:
            # Legacy multi-bucket approach
            self.primary_bucket = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
            self.download_bucket = os.environ.get('S3_CONFIG_BUCKET', 'perplexity-config-downloads')
            self.results_bucket = os.environ.get('S3_RESULTS_BUCKET', 'perplexity-results')
            self.use_unified_structure = False
            logger.info("UNIFIED_STORAGE: Using legacy multi-bucket structure")
        
    def create_session_id(self, email: str) -> str:
        """Create unique session ID for email validation"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Create short hash from email + timestamp for uniqueness
        hash_input = f"{email}_{timestamp}".encode()
        short_hash = hashlib.md5(hash_input).hexdigest()[:8]
        return f"{timestamp}_{short_hash}"
    
    def get_storage_path(self, email: str, session_id: str) -> str:
        """Get standardized storage path based on bucket structure."""
        if self.use_unified_structure:
            # New unified structure: results/{domain}/{email_prefix}/{session_id}/
            domain = email.split('@')[-1] if '@' in email else 'unknown'
            email_prefix = email.split('@')[0].replace('.', '_').replace('+', '_plus_')[:20]
            
            # Use session_id directly without extracting/regenerating timestamps
            # This avoids the duplicate timestamp issue
            return f"results/{domain}/{email_prefix}/{session_id}/"
        else:
            # Legacy structure: email/email_domain/timestamp_id/
            email_domain = email.split('@')[1] if '@' in email else 'unknown'
            safe_email = email.replace('@', '_at_').replace('.', '_')
            safe_domain = email_domain.replace('.', '_')
            return f"{safe_email}/{safe_domain}/{session_id}/"
    
    def store_excel_file(self, email: str, session_id: str, file_content: bytes, 
                        filename: str) -> Dict[str, str]:
        """Store Excel file in unified storage structure"""
        try:
            storage_path = self.get_storage_path(email, session_id)
            
            # Clean filename but preserve extension
            clean_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
            s3_key = f"{storage_path}excel_{clean_filename}"
            
            # Store file with metadata
            self.s3_client.put_object(
                Bucket=self.primary_bucket,
                Key=s3_key,
                Body=file_content,
                ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                Metadata={
                    'email': email,
                    'session_id': session_id,
                    'upload_type': 'excel',
                    'upload_timestamp': datetime.now().isoformat(),
                    'original_filename': filename
                }
            )
            
            logger.info(f"Stored Excel file: {s3_key}")
            
            return {
                'success': True,
                's3_key': s3_key,
                'storage_path': storage_path,
                'message': f'Excel file stored successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to store Excel file: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def store_config_file(self, email: str, session_id: str, config_data: Dict, 
                         source: str = 'upload', version: int = 1) -> Dict[str, str]:
        """Store config file (uploaded or AI-generated) in unified storage"""
        try:
            storage_path = self.get_storage_path(email, session_id)
            
            # Add version and source to config metadata
            if 'storage_metadata' not in config_data:
                config_data['storage_metadata'] = {}
            
            config_data['storage_metadata'].update({
                'version': version,
                'source': source,  # 'upload' or 'ai_generated'
                'email': email,
                'session_id': session_id,
                'timestamp': datetime.now().isoformat()
            })
            
            # Create filename with version
            config_filename = f"config_v{version:02d}.json"
            s3_key = f"{storage_path}{config_filename}"
            
            # Store config as JSON
            config_json = json.dumps(config_data, indent=2)
            
            self.s3_client.put_object(
                Bucket=self.primary_bucket,
                Key=s3_key,
                Body=config_json,
                ContentType='application/json',
                Metadata={
                    'email': email,
                    'session_id': session_id,
                    'upload_type': 'config',
                    'config_source': source,
                    'config_version': str(version),
                    'upload_timestamp': datetime.now().isoformat()
                }
            )
            
            logger.info(f"Stored config file: {s3_key} (version {version})")
            
            return {
                'success': True,
                's3_key': s3_key,
                'storage_path': storage_path,
                'version': version,
                'message': f'Config v{version} stored successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to store config file: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def store_preview_results(self, email: str, session_id: str, 
                            preview_data: Dict) -> Dict[str, str]:
        """Store preview results in unified storage"""
        try:
            storage_path = self.get_storage_path(email, session_id)
            
            # Add metadata to preview results
            preview_data['storage_metadata'] = {
                'email': email,
                'session_id': session_id,
                'result_type': 'preview',
                'timestamp': datetime.now().isoformat()
            }
            
            s3_key = f"{storage_path}preview_results.json"
            
            # Store preview results
            preview_json = json.dumps(preview_data, indent=2)
            
            self.s3_client.put_object(
                Bucket=self.primary_bucket,
                Key=s3_key,
                Body=preview_json,
                ContentType='application/json',
                Metadata={
                    'email': email,
                    'session_id': session_id,
                    'result_type': 'preview',
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            logger.info(f"Stored preview results: {s3_key}")
            
            return {
                'success': True,
                's3_key': s3_key,
                'storage_path': storage_path,
                'message': 'Preview results stored successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to store preview results: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def store_validation_results(self, email: str, session_id: str, 
                               results_zip: bytes) -> Dict[str, str]:
        """Store final validation results ZIP in unified storage"""
        try:
            storage_path = self.get_storage_path(email, session_id)
            s3_key = f"{storage_path}validation_results.zip"
            
            # Store validation results ZIP
            self.s3_client.put_object(
                Bucket=self.primary_bucket,
                Key=s3_key,
                Body=results_zip,
                ContentType='application/zip',
                Metadata={
                    'email': email,
                    'session_id': session_id,
                    'result_type': 'validation',
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            logger.info(f"Stored validation results: {s3_key}")
            
            return {
                'success': True,
                's3_key': s3_key,
                'storage_path': storage_path,
                'message': 'Validation results stored successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to store validation results: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_latest_config(self, email: str, session_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Get the latest config file for a session, checking both unified and legacy paths"""
        try:
            storage_path = self.get_storage_path(email, session_id)
            logger.info(f"UNIFIED_STORAGE: Looking for config file at: {storage_path}")
            
            # List all config files for this session
            response = self.s3_client.list_objects_v2(
                Bucket=self.primary_bucket,
                Prefix=storage_path,
                MaxKeys=100
            )
            
            config_files = []
            if 'Contents' in response:
                config_files = [obj for obj in response['Contents'] if obj['Key'].endswith('.json')]
            
            # If not found and using unified structure, try legacy path
            if not config_files and self.use_unified_structure:
                logger.info(f"UNIFIED_STORAGE: Config not found in unified path, trying legacy path...")
                
                # Generate legacy path
                email_domain = email.split('@')[1] if '@' in email else 'unknown'
                safe_email = email.replace('@', '_at_').replace('.', '_')
                safe_domain = email_domain.replace('.', '_')
                legacy_path = f"{safe_email}/{safe_domain}/{session_id}"
                
                logger.info(f"UNIFIED_STORAGE: Checking legacy path: {legacy_path}")
                
                legacy_response = self.s3_client.list_objects_v2(
                    Bucket=self.primary_bucket,
                    Prefix=legacy_path,
                    MaxKeys=100
                )
                
                if 'Contents' in legacy_response:
                    config_files = [obj for obj in legacy_response['Contents'] if obj['Key'].endswith('.json')]
            
            if not config_files:
                logger.warning(f"UNIFIED_STORAGE: No config file found for session {session_id}")
                return None, None
            
            # Sort by last modified (latest first)
            latest_file = sorted(config_files, key=lambda x: x['LastModified'], reverse=True)[0]
            
            # Download and parse the latest config
            obj = self.s3_client.get_object(Bucket=self.primary_bucket, Key=latest_file['Key'])
            config_data = json.loads(obj['Body'].read().decode('utf-8'))
            
            logger.info(f"UNIFIED_STORAGE: Found config file at: {latest_file['Key']}")
            return config_data, latest_file['Key']
            
        except Exception as e:
            logger.error(f"Failed to get latest config: {str(e)}")
            return None, None
    
    def get_excel_file(self, email: str, session_id: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Get the Excel file for a session, checking both unified and legacy paths"""
        try:
            # Try current unified structure first
            storage_path = self.get_storage_path(email, session_id)
            logger.info(f"UNIFIED_STORAGE: Looking for Excel file at: {storage_path}")
            
            # List Excel files for this session
            response = self.s3_client.list_objects_v2(
                Bucket=self.primary_bucket,
                Prefix=storage_path,
                MaxKeys=50
            )
            
            if 'Contents' in response:
                # Look for Excel files (including CSV)
                excel_files = [obj for obj in response['Contents'] 
                              if obj['Key'].endswith(('.xlsx', '.xls', '.csv'))]
                
                if excel_files:
                    # Get the latest Excel file
                    latest_excel = sorted(excel_files, key=lambda x: x['LastModified'], reverse=True)[0]
                    
                    # Download the file
                    obj = self.s3_client.get_object(Bucket=self.primary_bucket, Key=latest_excel['Key'])
                    logger.info(f"UNIFIED_STORAGE: Found Excel file at: {latest_excel['Key']}")
                    return obj['Body'].read(), latest_excel['Key']
            
            # If not found and using unified structure, try legacy path as fallback
            if self.use_unified_structure:
                logger.info(f"UNIFIED_STORAGE: Excel not found in unified path, trying legacy path...")
                
                # Generate legacy path
                email_domain = email.split('@')[1] if '@' in email else 'unknown'
                safe_email = email.replace('@', '_at_').replace('.', '_')
                safe_domain = email_domain.replace('.', '_')
                legacy_path = f"{safe_email}/{safe_domain}/{session_id}"
                
                logger.info(f"UNIFIED_STORAGE: Checking legacy path: {legacy_path}")
                
                legacy_response = self.s3_client.list_objects_v2(
                    Bucket=self.primary_bucket,
                    Prefix=legacy_path,
                    MaxKeys=50
                )
                
                if 'Contents' in legacy_response:
                    excel_files = [obj for obj in legacy_response['Contents'] 
                                  if obj['Key'].endswith(('.xlsx', '.xls', '.csv'))]
                    
                    if excel_files:
                        latest_excel = sorted(excel_files, key=lambda x: x['LastModified'], reverse=True)[0]
                        obj = self.s3_client.get_object(Bucket=self.primary_bucket, Key=latest_excel['Key'])
                        logger.info(f"UNIFIED_STORAGE: Found Excel file at legacy path: {latest_excel['Key']}")
                        return obj['Body'].read(), latest_excel['Key']
            
            logger.warning(f"UNIFIED_STORAGE: No Excel file found for session {session_id}")
            return None, None
            
            if 'Contents' not in response:
                return None, None
            
            # Get the latest Excel file
            excel_files = response['Contents']
            if not excel_files:
                return None, None
            
            latest_file = sorted(excel_files, key=lambda x: x['LastModified'], reverse=True)[0]
            
            # Download the file
            obj = self.s3_client.get_object(Bucket=self.primary_bucket, Key=latest_file['Key'])
            file_content = obj['Body'].read()
            
            return file_content, latest_file['Key']
            
        except Exception as e:
            logger.error(f"Failed to get Excel file: {str(e)}")
            return None, None
    
    def create_config_download_link(self, email: str, session_id: str, 
                                  config_data: Dict) -> str:
        """Create downloadable config in download bucket with proper folder structure"""
        try:
            import uuid
            
            # Create filename based on session info
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"config_{session_id}_{timestamp}.json"
            
            if self.use_unified_structure:
                # Use unified structure: downloads/{uuid}/filename
                download_uuid = str(uuid.uuid4())
                s3_key = f"downloads/{download_uuid}/{filename}"
            else:
                # Legacy structure: downloads/filename
                s3_key = f"downloads/{filename}"
            
            # Add download metadata
            if 'download_metadata' not in config_data:
                config_data['download_metadata'] = {}
            
            config_data['download_metadata'].update({
                'email': email,
                'session_id': session_id,
                'download_created': datetime.now().isoformat(),
                'expires': (datetime.now() + timedelta(hours=24)).isoformat()
            })
            
            # Store in download bucket
            config_json = json.dumps(config_data, indent=2)
            
            self.s3_client.put_object(
                Bucket=self.download_bucket,
                Key=s3_key,
                Body=config_json,
                ContentType='application/json',
                Metadata={
                    'email': email,
                    'session_id': session_id,
                    'expires': (datetime.now() + timedelta(hours=24)).isoformat()
                }
            )
            
            # Create public download URL
            download_url = f"https://{self.download_bucket}.s3.amazonaws.com/{s3_key}"
            
            logger.info(f"Created config download: {download_url}")
            return download_url
            
        except Exception as e:
            logger.error(f"Failed to create config download link: {str(e)}")
            return ""
    
    def cleanup_old_sessions(self, days_old: int = 7):
        """Clean up sessions older than specified days"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            
            # List all objects in the bucket
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.primary_bucket)
            
            deleted_count = 0
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                        logger.info(f"Deleting old file: {obj['Key']}")
                        self.s3_client.delete_object(
                            Bucket=self.primary_bucket,
                            Key=obj['Key']
                        )
                        deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old files")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old sessions: {str(e)}")
            return 0
    
    def get_session_summary(self, email: str, session_id: str) -> Dict[str, Any]:
        """Get summary of all files in a session"""
        try:
            storage_path = self.get_storage_path(email, session_id)
            
            # List all files for this session
            response = self.s3_client.list_objects_v2(
                Bucket=self.primary_bucket,
                Prefix=storage_path,
                MaxKeys=100
            )
            
            summary = {
                'email': email,
                'session_id': session_id,
                'storage_path': storage_path,
                'files': {}
            }
            
            if 'Contents' in response:
                for obj in response['Contents']:
                    filename = obj['Key'].split('/')[-1]
                    file_type = 'unknown'
                    
                    if filename.startswith('excel_'):
                        file_type = 'excel'
                    elif filename.startswith('config_'):
                        file_type = 'config'
                    elif filename == 'preview_results.json':
                        file_type = 'preview'
                    elif filename == 'validation_results.zip':
                        file_type = 'validation'
                    
                    summary['files'][filename] = {
                        'type': file_type,
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'].isoformat(),
                        's3_key': obj['Key']
                    }
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get session summary: {str(e)}")
            return {'error': str(e)}