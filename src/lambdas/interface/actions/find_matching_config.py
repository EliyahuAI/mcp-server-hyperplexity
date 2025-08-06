"""
Find matching configuration files based on table column analysis.
Searches user's results folder for configs with validation targets that match uploaded table columns.
"""
import logging
import json
import boto3
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from src.lambdas.interface.core.unified_s3_manager import UnifiedS3Manager
from src.shared.shared_table_parser import s3_table_parser
from src.lambdas.interface.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def extract_validation_targets(config_data: Dict) -> List[str]:
    """Extract column names from config validation_targets"""
    try:
        validation_targets = config_data.get('validation_targets', [])
        
        # Handle both old format (dict) and new format (array of objects)
        if isinstance(validation_targets, dict):
            # Old format: {"column_name": {...}, ...}
            return list(validation_targets.keys())
        elif isinstance(validation_targets, list):
            # New format: [{"column": "column_name", ...}, ...] or [{"name": "column_name", ...}, ...]
            columns = []
            for target in validation_targets:
                if isinstance(target, dict):
                    # Check for 'column' field first, then 'name' field
                    column_name = target.get('column') or target.get('name')
                    if column_name:
                        columns.append(column_name)
            return columns
        else:
            logger.warning(f"validation_targets is neither dict nor list: {type(validation_targets)}")
            return []
    except Exception as e:
        logger.error(f"Error extracting validation targets: {e}")
        return []

def calculate_column_match_score(table_columns: List[str], config_columns: List[str]) -> float:
    """Calculate match score between table columns and config validation targets"""
    if not table_columns or not config_columns:
        return 0.0
    
    # Convert to lowercase for case-insensitive matching and clean up
    table_cols_lower = [col.lower().strip() for col in table_columns if col and col.strip()]
    config_cols_lower = [col.lower().strip() for col in config_columns if col and col.strip()]
    
    if not table_cols_lower or not config_cols_lower:
        return 0.0
    
    logger.info(f"Comparing table columns: {table_cols_lower}")
    logger.info(f"Against config columns: {config_cols_lower}")
    
    # Calculate exact matches
    exact_matches = len(set(table_cols_lower) & set(config_cols_lower))
    logger.info(f"Exact matches: {exact_matches}")
    
    # Calculate partial matches (substring matching)
    partial_matches = 0
    for table_col in table_cols_lower:
        for config_col in config_cols_lower:
            if table_col != config_col:  # Don't double-count exact matches
                if table_col in config_col or config_col in table_col:
                    partial_matches += 0.5
                    logger.debug(f"Partial match: '{table_col}' <-> '{config_col}'")
                    break
    
    logger.info(f"Partial matches: {partial_matches}")
    
    total_score = exact_matches + partial_matches
    max_possible = max(len(table_cols_lower), len(config_cols_lower))
    
    final_score = min(total_score / max_possible, 1.0) if max_possible > 0 else 0.0
    logger.info(f"Final match score: {final_score} (total: {total_score}, max_possible: {max_possible})")
    
    return final_score

def analyze_table_columns(email: str, session_id: str, storage_manager: UnifiedS3Manager) -> List[str]:
    """Extract column names from uploaded Excel file"""
    try:
        # Get Excel file from unified storage
        excel_content, excel_s3_key = storage_manager.get_excel_file(email, session_id)
        if not excel_content or not excel_s3_key:
            logger.warning(f"No Excel file found for session {session_id}")
            return []
        
        # Use shared table parser to analyze columns
        try:
            # Analyze table structure directly from S3
            table_analysis = s3_table_parser.analyze_table_structure(storage_manager.bucket_name, excel_s3_key)
            
            if not table_analysis:
                logger.warning("Table analysis failed")
                return []
            
            # Extract column names from analysis
            columns = []
            column_analysis = table_analysis.get('column_analysis', {})
            
            logger.info(f"Table analysis keys: {list(table_analysis.keys())}")
            logger.info(f"Column analysis keys: {list(column_analysis.keys())}")
            
            for col_name, col_info in column_analysis.items():
                if col_name and col_name.strip():
                    columns.append(col_name.strip())
            
            logger.info(f"Extracted {len(columns)} columns from table: {columns[:5]}{'...' if len(columns) > 5 else ''}")
            return columns
            
        except Exception as e:
            logger.error(f"Failed to analyze table structure: {e}")
            return []
            
    except Exception as e:
        logger.error(f"Failed to analyze table columns: {e}")
        return []

def search_user_configs(email: str, storage_manager: UnifiedS3Manager) -> List[Dict[str, Any]]:
    """Search for all config files in user's results folders"""
    try:
        # Validate email format to prevent path traversal
        if not email or '@' not in email or '..' in email or '/' in email:
            logger.error(f"Invalid email format for config search: {email}")
            return []
            
        # Extract domain and email prefix for path construction
        domain = email.split('@')[-1] if '@' in email else 'unknown'
        email_prefix = email.split('@')[0].replace('.', '_').replace('+', '_plus_')[:20]
        
        # Additional sanitization
        domain = domain.replace('..', '').replace('/', '')
        email_prefix = email_prefix.replace('..', '').replace('/', '')
        
        # Search prefix for all user sessions
        user_results_prefix = f"results/{domain}/{email_prefix}/"
        
        logger.info(f"Searching for configs in: {user_results_prefix}")
        
        # List all objects in user's results folders with limits for performance
        s3_client = storage_manager.s3_client
        paginator = s3_client.get_paginator('list_objects_v2')
        
        # Track highest version config per session
        session_configs = {}  # session_path -> {version: int, config_info: dict}
        processed_objects = 0
        max_objects = 1000  # Limit total S3 objects to process
        
        for page in paginator.paginate(
            Bucket=storage_manager.bucket_name, 
            Prefix=user_results_prefix,
            PaginationConfig={'MaxItems': max_objects}
        ):
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                processed_objects += 1
                if processed_objects > max_objects:
                    logger.info(f"Reached max object limit ({max_objects}), stopping search")
                    break
                    
                key = obj['Key']
                filename = key.split('/')[-1]
                
                # Look for config files (both versioned and legacy patterns)
                if (filename.startswith('config_v') and filename.endswith('.json')) or \
                   (filename.startswith('config_') and filename.endswith('.json')):
                    
                    # Skip files in results subfolders (only get main session configs)
                    path_parts = key.split('/')
                    if len(path_parts) >= 4 and not any('_results' in part for part in path_parts):
                        session_path = '/'.join(path_parts[:-1]) + '/'
                        
                        # Extract version number from filename
                        version = 1
                        if filename.startswith('config_v'):
                            try:
                                # Handle formats like config_v1.json, config_v01.json, config_v1_source.json
                                version_part = filename[8:].split('.')[0].split('_')[0]  # Extract just the version number
                                # Handle both v1 and v01 formats
                                version = int(version_part.lstrip('0') or '1')  # Remove leading zeros, default to 1 if all zeros
                                logger.info(f"Parsed version {version} from filename {filename}")
                            except (ValueError, IndexError):
                                logger.warning(f"Could not parse version from {filename}, using version 1")
                                version = 1
                        
                        # Only keep the highest version config per session
                        if session_path not in session_configs or version > session_configs[session_path]['version']:
                            session_configs[session_path] = {
                                'version': version,
                                'config_info': {
                                    'key': key,
                                    'filename': filename,
                                    'last_modified': obj['LastModified'],
                                    'size': obj['Size'],
                                    'session_path': session_path
                                }
                            }
            
            # Break out of page loop if we hit limits
            if processed_objects > max_objects:
                break
        
        # Extract config files (only highest version per session)
        config_files = [info['config_info'] for info in session_configs.values()]
        
        logger.info(f"Found {len(config_files)} latest config files from {len(session_configs)} sessions")
        return config_files
        
    except Exception as e:
        logger.error(f"Failed to search user configs: {e}")
        return []

def find_matching_configs(email: str, session_id: str, limit: int = 5) -> Dict[str, Any]:
    """
    Find config files that match the uploaded table's column structure
    
    Args:
        email: User email
        session_id: Current session ID
        limit: Maximum number of matches to return
    
    Returns:
        {
            'success': True,
            'matches': [
                {
                    'config_key': 's3_key',
                    'config_data': {...},
                    'match_score': 0.0-1.0,
                    'matching_columns': ['col1', 'col2'],
                    'session_path': 'path/to/session/',
                    'last_modified': 'iso_timestamp',
                    'download_url': 'https://...',
                    'source_session': 'session_id'
                }
            ],
            'table_columns': ['col1', 'col2', ...],
            'total_configs_searched': 10
        }
    """
    try:
        storage_manager = UnifiedS3Manager()
        
        # Get columns from current table
        table_columns = analyze_table_columns(email, session_id, storage_manager)
        logger.info(f"Analyzed table columns for {email}/{session_id}: {table_columns}")
        
        if not table_columns:
            return {
                'success': True,  # Still success, just no matches possible
                'matches': [],
                'table_columns': [],
                'total_configs_searched': 0,
                'message': 'Could not analyze columns from uploaded table. Please ensure you have uploaded a valid Excel file.'
            }
        
        # Search for user's config files
        config_files = search_user_configs(email, storage_manager)
        if not config_files:
            return {
                'success': True,
                'matches': [],
                'table_columns': table_columns,
                'total_configs_searched': 0,
                'message': 'No previous configurations found for this user'
            }
        
        # Sort config files by modification time (most recent first) for better performance
        config_files.sort(key=lambda x: x['last_modified'], reverse=True)
        
        # Analyze each config for column matches
        matches = []
        s3_client = storage_manager.s3_client
        
        for config_file in config_files:
            try:
                # Download and parse config
                response = s3_client.get_object(Bucket=storage_manager.bucket_name, Key=config_file['key'])
                config_data = json.loads(response['Body'].read().decode('utf-8'))
                
                # Extract validation targets
                config_columns = extract_validation_targets(config_data)
                if not config_columns:
                    logger.debug(f"No validation targets found in {config_file['key']}")
                    continue
                
                logger.info(f"Config {config_file['key']}: found {len(config_columns)} columns: {config_columns[:3]}{'...' if len(config_columns) > 3 else ''}")
                logger.info(f"Table columns ({len(table_columns)}): {table_columns[:3]}{'...' if len(table_columns) > 3 else ''}")
                
                # Calculate match score
                match_score = calculate_column_match_score(table_columns, config_columns)
                logger.info(f"Match score for {config_file['key']}: {match_score}")
                
                if match_score == 0:
                    continue
                
                # Find matching columns
                table_cols_lower = [col.lower().strip() for col in table_columns]
                config_cols_lower = [col.lower().strip() for col in config_columns]
                matching_columns = list(set(table_cols_lower) & set(config_cols_lower))
                
                # Extract source session from path
                path_parts = config_file['key'].split('/')
                source_session = path_parts[-2] if len(path_parts) >= 2 else 'unknown'
                
                # Create download link
                download_url = storage_manager.create_public_download_link(
                    config_data, 
                    f"config_{source_session}_{datetime.now().strftime('%Y%m%d')}.json"
                )
                
                matches.append({
                    'config_key': config_file['key'],
                    'config_data': config_data,
                    'match_score': match_score,
                    'matching_columns': matching_columns,
                    'total_columns': len(config_columns),
                    'session_path': config_file['session_path'],
                    'last_modified': config_file['last_modified'].isoformat(),
                    'download_url': download_url,
                    'source_session': source_session,
                    'config_filename': config_file['filename']
                })
                
                # Break early on perfect match (100% score) since files are sorted by recency
                if match_score >= 1.0:
                    logger.info(f"Found perfect match with score {match_score}, breaking early")
                    break
                
                # Also break if we have enough good matches
                if len(matches) >= limit:
                    logger.info(f"Found {limit} matches, stopping search")
                    break
                
            except Exception as e:
                logger.error(f"Error processing config {config_file['key']}: {e}")
                continue
        
        # Since we're processing most recent files first and breaking on perfect matches,
        # we only need to sort by match score (files are already in recency order)
        matches.sort(key=lambda x: x['match_score'], reverse=True)
        
        logger.info(f"Found {len(matches)} matching configs out of {len(config_files)} total configs")
        
        return {
            'success': True,
            'matches': matches,
            'table_columns': table_columns,
            'total_configs_searched': len(config_files)
        }
        
    except Exception as e:
        logger.error(f"Failed to find matching configs: {e}")
        return {
            'success': False,
            'error': str(e),
            'matches': [],
            'table_columns': []
        }

def handle_find_matching_config(event_data, context=None):
    """Handler for finding matching configs"""
    
    try:
        email = event_data.get('email')
        session_id = event_data.get('session_id')
        limit = event_data.get('limit', 5)
        
        if not email or not session_id:
            return create_response(400, {
                'success': False,
                'error': 'Missing email or session_id'
            })
        
        result = find_matching_configs(email, session_id, limit)
        
        if result['success']:
            return create_response(200, result)
        else:
            return create_response(500, result)
            
    except Exception as e:
        logger.error(f"Find matching config handler error: {e}")
        return create_response(500, {
            'success': False,
            'error': str(e),
            'matches': []
        })