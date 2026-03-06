"""
Find matching configuration files based on table column analysis.
Searches user's results folder for configs with validation targets that match uploaded table columns.
"""
import logging
import json
import boto3
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set

from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from shared_table_parser import s3_table_parser
from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def calculate_content_hash(config_data: Dict) -> str:
    """
    Calculate SHA256 hash of configuration content for deduplication.
    Only includes validation targets and rules, excluding metadata like names, descriptions, etc.
    """
    if not config_data:
        return ""
    
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
        return full_hash[:32]  # 32 chars instead of 16 for better collision resistance
        
    except Exception as e:
        logger.warning(f"Failed to calculate content hash: {e}")
        return ""

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
    
    logger.debug(f"Comparing table columns: {table_cols_lower}")
    logger.debug(f"Against config columns: {config_cols_lower}")
    
    # Calculate exact matches
    exact_matches = len(set(table_cols_lower) & set(config_cols_lower))
    logger.debug(f"Exact matches: {exact_matches}")
    
    # Calculate partial matches (substring matching)
    partial_matches = 0
    for table_col in table_cols_lower:
        for config_col in config_cols_lower:
            if table_col != config_col:  # Don't double-count exact matches
                if table_col in config_col or config_col in table_col:
                    partial_matches += 0.5
                    logger.debug(f"Partial match: '{table_col}' <-> '{config_col}'")
                    break
    
    logger.debug(f"Partial matches: {partial_matches}")
    
    total_score = exact_matches + partial_matches
    max_possible = max(len(table_cols_lower), len(config_cols_lower))
    
    final_score = min(total_score / max_possible, 1.0) if max_possible > 0 else 0.0
    
    # Only log match results for high scores or when debugging
    if final_score >= 1.0:
        logger.info(f"PERFECT MATCH: {final_score} ({exact_matches}/{max_possible} columns)")
    elif final_score >= 0.8:
        logger.info(f"Strong match: {final_score} ({exact_matches} exact + {partial_matches} partial)")
    else:
        logger.debug(f"Low match score: {final_score} (total: {total_score}, max_possible: {max_possible})")
    
    return final_score

def get_columns_from_dynamodb(email: str, session_id: str) -> List[str]:
    """
    Get column names from DynamoDB qc_by_column field (much faster than S3 analysis).
    Falls back to S3 analysis if not available.
    """
    try:
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
        import boto3
        from boto3.dynamodb.conditions import Key, Attr

        # Access runs table
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('perplexity-validator-runs')

        # Use session_id-based query (faster than scan)
        try:
            response = table.query(
                IndexName='session_id-start_time-index',
                KeyConditionExpression=Key('session_id').eq(session_id),
                FilterExpression=Attr('qc_metrics').exists() & Attr('qc_metrics.qc_by_column').exists(),
                ScanIndexForward=False,  # Most recent first
                Limit=1  # Only need the most recent
            )
        except Exception as query_error:
            # Do NOT fall back to a full table scan — it times out on large tables.
            logger.debug(f"[QC_COLUMNS] GSI query failed, skipping: {query_error}")
            return None

        # Get the most recent run with qc_by_column data
        runs_with_qc = response.get('Items', [])

        if runs_with_qc:
            # Sort by start_time to get most recent
            runs_with_qc.sort(key=lambda x: x.get('start_time', ''), reverse=True)
            most_recent = runs_with_qc[0]

            # Extract column names from qc_by_column keys
            qc_by_column = most_recent.get('qc_metrics', {}).get('qc_by_column', {})
            columns = list(qc_by_column.keys())

            if columns:
                logger.debug(f"[QC_COLUMNS] Extracted {len(columns)} columns from DynamoDB qc_by_column: {columns[:5]}{'...' if len(columns) > 5 else ''}")
                return columns

        logger.debug(f"[QC_COLUMNS] No qc_by_column data found in DynamoDB for session {session_id}")
        return None

    except Exception as e:
        logger.warning(f"[QC_COLUMNS] Could not get columns from DynamoDB: {e}, falling back to S3 analysis")
        return None

def batch_get_columns_from_dynamodb(email: str, session_ids: List[str]) -> Dict[str, List[str]]:
    """
    Batch fetch column names from DynamoDB for multiple sessions at once.
    Much more efficient than calling get_columns_from_dynamodb in a loop.

    Returns:
        Dict mapping session_id -> list of column names (or None if not found)
    """
    if not session_ids:
        return {}

    try:
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
        import boto3
        from boto3.dynamodb.conditions import Key, Attr

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('perplexity-validator-runs')

        results = {}

        # Query in batches using the email-based GSI for efficiency
        try:
            # Get all runs for this user with qc_by_column data
            response = table.query(
                IndexName='EmailStartTimeIndex',
                KeyConditionExpression=Key('email').eq(email),
                FilterExpression=Attr('qc_metrics').exists() & Attr('qc_metrics.qc_by_column').exists(),
                ScanIndexForward=False  # Most recent first
            )

            all_runs = response.get('Items', [])

            # Handle pagination if needed
            while 'LastEvaluatedKey' in response:
                response = table.query(
                    IndexName='EmailStartTimeIndex',
                    KeyConditionExpression=Key('email').eq(email),
                    FilterExpression=Attr('qc_metrics').exists() & Attr('qc_metrics.qc_by_column').exists(),
                    ScanIndexForward=False,
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                all_runs.extend(response.get('Items', []))

                # Stop if we have enough data
                if len(all_runs) > 500:
                    logger.info(f"[BATCH_QC] Collected {len(all_runs)} runs, stopping pagination")
                    break

            logger.info(f"[BATCH_QC] Fetched {len(all_runs)} runs with qc_by_column data for {email}")

            # Group by session_id and keep most recent per session
            session_runs = {}
            for run in all_runs:
                run_session_id = run.get('session_id')
                if run_session_id in session_ids:
                    if run_session_id not in session_runs:
                        session_runs[run_session_id] = run
                    else:
                        # Keep most recent
                        if run.get('start_time', '') > session_runs[run_session_id].get('start_time', ''):
                            session_runs[run_session_id] = run

            # Extract columns for each session
            for session_id, run in session_runs.items():
                qc_by_column = run.get('qc_metrics', {}).get('qc_by_column', {})
                columns = list(qc_by_column.keys())
                if columns:
                    results[session_id] = columns
                    logger.debug(f"[BATCH_QC] Session {session_id}: {len(columns)} columns")

            logger.info(f"[BATCH_QC] Successfully extracted columns for {len(results)}/{len(session_ids)} sessions")
            return results

        except Exception as query_error:
            # Do NOT fall back to per-session individual queries — each could trigger a scan.
            logger.warning(f"[BATCH_QC] Batch query failed, skipping (no fallback): {query_error}")
            return {}

    except Exception as e:
        logger.error(f"[BATCH_QC] Batch get columns failed: {e}")
        return {}


def analyze_table_columns(email: str, session_id: str, storage_manager: UnifiedS3Manager) -> List[str]:
    """Extract column names from uploaded Excel file (with DynamoDB optimization)"""
    try:
        # OPTIMIZATION: Try to get columns from DynamoDB first (much faster)
        columns = get_columns_from_dynamodb(email, session_id)
        if columns:
            return columns

        # FALLBACK: Analyze Excel file from S3 if DynamoDB doesn't have the data
        logger.info("[QC_COLUMNS] Using S3 Excel analysis fallback")

        # Get Excel file from unified storage
        excel_content, excel_s3_key = storage_manager.get_excel_file(email, session_id)
        if not excel_content or not excel_s3_key:
            logger.warning(f"No Excel file found for session {session_id}")
            return []

        # Use shared table parser to analyze columns
        try:
            # Analyze table structure directly from S3
            table_analysis = s3_table_parser.analyze_table_structure(storage_manager.bucket_name, excel_s3_key, extract_formulas=False)

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

            logger.info(f"Extracted {len(columns)} columns from S3 table: {columns[:5]}{'...' if len(columns) > 5 else ''}")
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
                
                # Look for config files (multiple patterns)
                # Patterns: config_v1.json, config_something.json, something_config_V01.json, something_config.json
                is_config = False
                if filename.endswith('.json'):
                    if filename.startswith('config_') or filename.startswith('config_v'):
                        is_config = True
                    elif '_config_' in filename or '_config.' in filename:
                        is_config = True
                    elif filename.endswith('_config.json'):
                        is_config = True
                
                if is_config:
                    
                    # Skip files in results subfolders (only get main session configs)
                    path_parts = key.split('/')
                    if len(path_parts) >= 4 and not any('_results' in part for part in path_parts):
                        session_path = '/'.join(path_parts[:-1]) + '/'
                        
                        # Extract version number from filename
                        version = 1
                        import re
                        
                        # Try multiple patterns for version extraction
                        # Patterns: config_v1.json, config_V01.json, something_config_V04.json
                        version_patterns = [
                            r'config_[vV](\d+)',  # config_v1 or config_V1
                            r'_config_[vV](\d+)',  # something_config_V04
                            r'_[vV](\d+)\.json$',  # anything_V04.json
                            r'_v(\d+)_',  # _v1_ in middle
                        ]
                        
                        for pattern in version_patterns:
                            match = re.search(pattern, filename)
                            if match:
                                try:
                                    version = int(match.group(1).lstrip('0') or '1')
                                    logger.debug(f"Parsed version {version} from filename {filename}")
                                    break
                                except (ValueError, IndexError):
                                    continue
                        
                        if version == 1 and any(pattern in filename.lower() for pattern in ['_v', '_config']):
                            logger.debug(f"Could not parse version from {filename}, using default version 1")
                        
                        # Only keep the highest version config per session
                        if session_path not in session_configs or version > session_configs[session_path]['version']:
                            logger.debug(f"Keeping config: {filename} (v{version}) in {session_path}, modified: {obj['LastModified']}")
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
                        else:
                            logger.debug(f"Skipping older version: {filename} (v{version}) in {session_path}")
            
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

def get_successfully_used_config_ids(email: str) -> List[str]:
    """
    Get all configuration IDs that have been successfully used in Preview or Validation runs.
    This provides a whitelist of configs that are proven to work.
    Excludes demo session configs as they are temporary.
    """
    try:
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
        import boto3
        from boto3.dynamodb.conditions import Key, Attr

        # Access runs table directly
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('perplexity-validator-runs')

        config_with_times = []

        # Use EmailStartTimeIndex GSI for fast lookup (ordered by start_time)
        try:
            logger.debug(f"[GET_CONFIGS] Querying EmailStartTimeIndex GSI for {email}")
            response = table.query(
                IndexName='EmailStartTimeIndex',
                KeyConditionExpression=Key('email').eq(email),
                FilterExpression=Attr('status').eq('COMPLETED') & Attr('configuration_id').exists(),
                ScanIndexForward=False  # Most recent first
            )
        except Exception as e:
            # Do NOT fall back to a full table scan — it times out on large tables.
            logger.debug(f"[GET_CONFIGS] EmailStartTimeIndex GSI not available, skipping: {e}")
            return []

        # Collect configs with their start_time for sorting
        for item in response.get('Items', []):
            config_id = item.get('configuration_id')
            start_time = item.get('start_time', '')

            # Skip demo configs (temporary sessions that get cleaned up)
            if config_id and config_id != 'unknown' and 'session_demo_' not in config_id:
                config_with_times.append((config_id, start_time))
                logger.debug(f"Found successfully used config: {config_id} at {start_time}")
            elif config_id and 'session_demo_' in config_id:
                logger.debug(f"Skipping demo config: {config_id}")

        # Handle pagination for GSI query
        while 'LastEvaluatedKey' in response:
            try:
                response = table.query(
                    IndexName='EmailStartTimeIndex',
                    KeyConditionExpression=Key('email').eq(email),
                    FilterExpression=Attr('status').eq('COMPLETED') & Attr('configuration_id').exists(),
                    ScanIndexForward=False,
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
            except:
                break  # Stop pagination on error

            for item in response.get('Items', []):
                config_id = item.get('configuration_id')
                start_time = item.get('start_time', '')

                # Skip demo configs
                if config_id and config_id != 'unknown' and 'session_demo_' not in config_id:
                    config_with_times.append((config_id, start_time))
                    logger.debug(f"Found successfully used config: {config_id} at {start_time}")
                elif config_id and 'session_demo_' in config_id:
                    logger.debug(f"Skipping demo config: {config_id}")

        # Sort by start_time (most recent first) and extract unique config_ids
        config_with_times.sort(key=lambda x: x[1], reverse=True)

        # DEDUPLICATION: Only keep the latest version per session
        # Group configs by session_id and keep only the highest version per session
        session_configs = {}  # session_id -> (config_id, version, start_time)

        for config_id, start_time in config_with_times:
            # Extract session ID and version from config_id
            session_id, version = extract_session_and_version_from_config_id(config_id)

            # Only keep the highest version per session
            if session_id not in session_configs or version > session_configs[session_id][1]:
                session_configs[session_id] = (config_id, version, start_time)
                logger.debug(f"Keeping {config_id} (v{version}) for session {session_id}")
            else:
                logger.debug(f"Skipping {config_id} (v{version}), already have v{session_configs[session_id][1]} for session {session_id}")

        # Extract config_ids and sort by start_time (most recent first)
        deduplicated_configs = [(config_id, start_time) for config_id, version, start_time in session_configs.values()]
        deduplicated_configs.sort(key=lambda x: x[1], reverse=True)
        successfully_used_configs = [config_id for config_id, _ in deduplicated_configs]

        logger.info(f"Found {len(successfully_used_configs)} successfully used configs (excluding demos, deduplicated by session) for {email}, ordered by recency")
        logger.info(f"Original count before deduplication: {len(config_with_times)}")
        return successfully_used_configs

    except Exception as e:
        logger.warning(f"Could not get successfully used config IDs for {email}: {e}")
        # Return empty list to allow all configs (fallback behavior)
        return []

def get_session_usage_info(email: str, source_session: str, storage_manager: UnifiedS3Manager) -> Dict[str, Any]:
    """
    Determine if a session was used for preview or full validation
    """
    try:
        # Try DynamoDB first - more reliable
        try:
            import sys
            import os
            sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
            from dynamodb_schemas import get_run_by_session_id
            
            run_data = get_run_by_session_id(source_session)
            if run_data:
                total_rows = float(run_data.get('total_rows', 0))
                processed_rows = float(run_data.get('processed_rows', 0))
                status = run_data.get('status', '')
                verbose_status = run_data.get('verbose_status', '')
                
                # PRIMARY: Use verbose_status to determine usage type (most reliable)
                usage_type = 'unknown'
                is_error = False
                
                if verbose_status:
                    verbose_lower = verbose_status.lower().strip()
                    if verbose_lower.startswith('preview'):
                        usage_type = 'preview'
                    elif verbose_lower.startswith('validation'):
                        usage_type = 'full_validation'
                    else:
                        # Other verbose_status values indicate errors/incomplete runs
                        usage_type = 'error'
                        is_error = True
                        logger.debug(f"Session {source_session} has error status: {verbose_status}")
                
                # FALLBACK: If no verbose_status, use completion ratio (less reliable)
                if usage_type == 'unknown':
                    if total_rows > 0 and processed_rows > 0:
                        completion_ratio = processed_rows / total_rows
                        if completion_ratio >= 0.8 and status == 'COMPLETED':
                            usage_type = 'full_validation'
                        else:
                            usage_type = 'preview'
                    else:
                        usage_type = 'unknown'
                
                return {
                    'type': usage_type,
                    'is_error': is_error,
                    'total_rows': int(total_rows),
                    'processed_rows': int(processed_rows),
                    'completion_ratio': processed_rows / total_rows if total_rows > 0 else 0,
                    'status': status,
                    'verbose_status': verbose_status,
                    'source': 'dynamodb'
                }
        except ImportError:
            logger.debug("DynamoDB schemas not available for usage detection")
        except Exception as e:
            logger.debug(f"DynamoDB usage detection failed: {e}")
        
        # Fallback: Check S3 for .zip files in results folder
        try:
            domain = email.split('@')[-1] if '@' in email else 'unknown'
            email_prefix = email.split('@')[0].replace('.', '_').replace('+', '_plus_')[:20]
            
            # Sanitization
            domain = domain.replace('..', '').replace('/', '')
            email_prefix = email_prefix.replace('..', '').replace('/', '')
            
            results_prefix = f"results/{domain}/{email_prefix}/{source_session}/"
            
            s3_client = storage_manager.s3_client
            response = s3_client.list_objects_v2(
                Bucket=storage_manager.bucket_name,
                Prefix=results_prefix,
                MaxKeys=50
            )
            
            # Check for .zip files (indicates full validation)
            has_zip = False
            if 'Contents' in response:
                for obj in response['Contents']:
                    if obj['Key'].endswith('.zip'):
                        has_zip = True
                        break
            
            usage_type = 'full_validation' if has_zip else 'preview'
            return {
                'type': usage_type,
                'source': 's3_detection',
                'has_results_zip': has_zip
            }
            
        except Exception as e:
            logger.debug(f"S3 usage detection failed: {e}")
            
        # Default fallback
        return {
            'type': 'unknown',
            'source': 'fallback'
        }
        
    except Exception as e:
        logger.error(f"Usage info detection failed: {e}")
        return {
            'type': 'unknown',
            'source': 'error',
            'error': str(e)
        }

def get_config_usage_info(storage_manager, config_key: str) -> Optional[Dict]:
    """Get usage information for a configuration from session tracking files."""
    try:
        # Extract session info from config key path
        # Format: results/{domain}/{email_prefix}/{session_id}/config_v1.json
        path_parts = config_key.split('/')
        if len(path_parts) >= 4:
            domain = path_parts[1]
            email_prefix = path_parts[2]
            session_id = path_parts[3]

            # Look for session_info.json in the same directory
            session_info_key = f"results/{domain}/{email_prefix}/{session_id}/session_info.json"

            try:
                response = storage_manager.s3_client.get_object(
                    Bucket=storage_manager.bucket_name,
                    Key=session_info_key
                )
                session_info = json.loads(response['Body'].read().decode('utf-8'))

                # Look for validation usage in session_info
                validations = session_info.get('validations', [])
                if validations:
                    # Get most recent validation timestamp
                    latest_validation = max(validations, key=lambda x: x.get('timestamp', ''))
                    return {
                        'last_used': latest_validation.get('timestamp'),
                        'usage_type': 'validation'
                    }

                # Check for preview usage
                previews = session_info.get('previews', [])
                if previews:
                    latest_preview = max(previews, key=lambda x: x.get('timestamp', ''))
                    return {
                        'last_used': latest_preview.get('timestamp'),
                        'usage_type': 'preview'
                    }

            except Exception as e:
                logger.debug(f"Could not load session info for usage tracking: {e}")

    except Exception as e:
        logger.debug(f"Could not extract session info from config key: {e}")

    return None

def find_original_creation_date(content_hash: str, current_config_data: Dict, current_file_date: datetime, 
                              all_config_files: List[Dict], storage_manager: UnifiedS3Manager) -> Dict[str, Any]:
    """
    Find the original creation date for a configuration by tracing back through identical content.
    
    Rules:
    1. Check original_version field to trace back to source
    2. Find all configs with same content hash and use earliest stored_at
    3. Fall back to earliest file modification date
    4. Use current config date as final fallback
    """
    try:
        current_metadata = current_config_data.get('storage_metadata', {})
        
        # Rule 1: Follow original_version chain if available
        original_version = current_metadata.get('original_version') or current_metadata.get('original_name')
        if original_version:
            # Try to find the referenced original config
            for config_file in all_config_files:
                try:
                    # Check if this could be the original config
                    if (original_version in config_file['key'] or 
                        original_version in config_file.get('filename', '') or
                        original_version in str(config_file.get('session_path', ''))):
                        
                        # Load and verify it has the same content
                        response = storage_manager.s3_client.get_object(
                            Bucket=storage_manager.bucket_name, 
                            Key=config_file['key']
                        )
                        orig_config_data = json.loads(response['Body'].read().decode('utf-8'))
                        orig_hash = calculate_content_hash(orig_config_data)
                        
                        if orig_hash == content_hash:
                            # Found the original! Get its date
                            orig_metadata = orig_config_data.get('storage_metadata', {})
                            if orig_metadata.get('stored_at'):
                                orig_date = datetime.fromisoformat(orig_metadata['stored_at'].replace('Z', '+00:00'))
                                return {
                                    'original_date': orig_date,
                                    'source': 'original_version_chain',
                                    'original_config_id': orig_metadata.get('config_id', original_version),
                                    'chain_length': 1
                                }
                            else:
                                # Use file modification date as fallback
                                return {
                                    'original_date': config_file['last_modified'],
                                    'source': 'original_version_file_date',
                                    'original_config_id': orig_metadata.get('config_id', original_version),
                                    'chain_length': 1
                                }
                except Exception as e:
                    logger.debug(f"Error checking original version {original_version}: {e}")
                    continue
        
        # Rule 2: Find all configs with same content hash and use earliest stored_at
        earliest_stored_date = None
        earliest_config_id = None
        configs_checked = 0
        
        for config_file in all_config_files:
            try:
                # Load config and get stored hash
                response = storage_manager.s3_client.get_object(
                    Bucket=storage_manager.bucket_name, 
                    Key=config_file['key']
                )
                other_config_data = json.loads(response['Body'].read().decode('utf-8'))
                other_metadata = other_config_data.get('storage_metadata', {})
                other_hash = other_metadata.get('content_hash', '')
                
                # Fallback to calculation if hash not stored
                if not other_hash:
                    other_hash = calculate_content_hash(other_config_data)
                
                if other_hash == content_hash:
                    configs_checked += 1
                    # other_metadata already defined above
                    
                    if other_metadata.get('stored_at'):
                        stored_date = datetime.fromisoformat(other_metadata['stored_at'].replace('Z', '+00:00'))
                        if earliest_stored_date is None or stored_date < earliest_stored_date:
                            earliest_stored_date = stored_date
                            earliest_config_id = other_metadata.get('config_id', 'unknown')
                
                # Limit search to avoid performance issues
                if configs_checked >= 10:
                    break
                    
            except Exception as e:
                logger.debug(f"Error checking config {config_file['key']} for hash matching: {e}")
                continue
        
        if earliest_stored_date:
            return {
                'original_date': earliest_stored_date,
                'source': 'content_hash_search',
                'original_config_id': earliest_config_id,
                'configs_with_same_content': configs_checked
            }
        
        # Rule 3: Fall back to earliest file modification date among matching configs
        earliest_file_date = current_file_date
        earliest_file_config = None
        
        for config_file in all_config_files:
            try:
                response = storage_manager.s3_client.get_object(
                    Bucket=storage_manager.bucket_name, 
                    Key=config_file['key']
                )
                other_config_data = json.loads(response['Body'].read().decode('utf-8'))
                other_hash = calculate_content_hash(other_config_data)
                
                if other_hash == content_hash:
                    if config_file['last_modified'] < earliest_file_date:
                        earliest_file_date = config_file['last_modified']
                        earliest_file_config = config_file
                        
            except Exception as e:
                continue
        
        if earliest_file_config:
            return {
                'original_date': earliest_file_date,
                'source': 'file_modification_date',
                'original_config_id': earliest_file_config.get('filename', 'unknown')
            }
        
        # Rule 4: Final fallback - use current config date
        current_stored_date = current_file_date
        if current_metadata.get('stored_at'):
            try:
                current_stored_date = datetime.fromisoformat(current_metadata['stored_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
                
        return {
            'original_date': current_stored_date,
            'source': 'current_config_fallback',
            'original_config_id': current_metadata.get('config_id', 'current')
        }
        
    except Exception as e:
        logger.error(f"Error finding original creation date: {e}")
        return {
            'original_date': current_file_date,
            'source': 'error_fallback',
            'error': str(e)
        }

def find_last_used_date(content_hash: str, current_config_data: Dict, all_config_files: List[Dict], 
                       storage_manager: UnifiedS3Manager) -> datetime:
    """
    Find the most recent usage date for a configuration by looking at all instances with same content.
    
    Logic:
    1. Check all configs with same content hash
    2. Look for usage indicators in storage_metadata (last_used, applied_at, etc.)
    3. Fall back to file modification dates of configs with same content
    4. Use creation date as final fallback
    """
    try:
        latest_usage_date = None
        current_metadata = current_config_data.get('storage_metadata', {})
        
        # Check current config's usage metadata first
        for usage_field in ['last_used', 'applied_at', 'used_at', 'copied_at']:
            if current_metadata.get(usage_field):
                try:
                    usage_date = datetime.fromisoformat(current_metadata[usage_field].replace('Z', '+00:00'))
                    if latest_usage_date is None or usage_date > latest_usage_date:
                        latest_usage_date = usage_date
                except (ValueError, AttributeError):
                    continue
        
        # Search through all configs with same content for usage dates
        configs_checked = 0
        for config_file in all_config_files:
            try:
                # Don't check too many files for performance
                if configs_checked >= 10:
                    break
                    
                # Load config and verify same content
                response = storage_manager.s3_client.get_object(
                    Bucket=storage_manager.bucket_name, 
                    Key=config_file['key']
                )
                other_config_data = json.loads(response['Body'].read().decode('utf-8'))
                other_hash = calculate_content_hash(other_config_data)
                
                if other_hash == content_hash:
                    configs_checked += 1
                    other_metadata = other_config_data.get('storage_metadata', {})
                    
                    # Check for usage timestamps in metadata
                    for usage_field in ['last_used', 'applied_at', 'used_at', 'copied_at']:
                        if other_metadata.get(usage_field):
                            try:
                                usage_date = datetime.fromisoformat(other_metadata[usage_field].replace('Z', '+00:00'))
                                if latest_usage_date is None or usage_date > latest_usage_date:
                                    latest_usage_date = usage_date
                                    logger.debug(f"Found usage date {usage_date} in {config_file['filename']}")
                            except (ValueError, AttributeError):
                                continue
                    
                    # For previews: If no explicit usage timestamp exists, use stored_at as proxy for when config was used
                    # But only if this config shows evidence of being used for validation (has usage_info data)
                    if latest_usage_date is None and other_metadata.get('stored_at'):
                        # Only treat stored_at as usage if this config was used for validation
                        config_path_parts = config_file['key'].split('/')
                        config_session = config_path_parts[-2] if len(config_path_parts) >= 2 else None
                        
                        if config_session:
                            try:
                                session_usage = get_session_usage_info("", config_session, storage_manager)
                                # If session shows validation usage, use stored_at as approximate usage time
                                if session_usage.get('type') in ['preview', 'full_validation'] and not session_usage.get('is_error', False):
                                    stored_date = datetime.fromisoformat(other_metadata['stored_at'].replace('Z', '+00:00'))
                                    latest_usage_date = stored_date
                                    logger.debug(f"Using stored_at as usage date for validated config: {stored_date}")
                            except Exception as e:
                                logger.debug(f"Could not check session usage for stored_at logic: {e}")
                    
            except Exception as e:
                logger.debug(f"Error checking usage date for {config_file['key']}: {e}")
                continue
        
        # If we found explicit usage dates, return the latest one
        if latest_usage_date:
            return latest_usage_date
        
        # If no explicit usage found, return None to indicate "never used"
        # Don't use stored_at or file modification dates as they don't represent actual usage
        return None
        
    except Exception as e:
        logger.error(f"Error finding last used date: {e}")
        # Return None as error fallback to indicate "never used"
        return None

def extract_session_and_version_from_config_id(config_id: str) -> Tuple[str, int]:
    """Extract session ID and version from config_id"""
    try:
        # Handle different config_id formats
        if '_config_v' in config_id:
            # New format: session_20250918_150921_ea332116_config_v1_ai_generated
            session_part = config_id[:config_id.find('_config_v')]
            version_part = config_id[config_id.find('_config_v') + 9:]  # Skip '_config_v'
            # Extract just the numeric version (handles both 'v1' and '1')
            version_str = ''
            for char in version_part:
                if char.isdigit():
                    version_str += char
                elif version_str:  # Stop after finding digits
                    break
            version = int(version_str) if version_str else 1
            return session_part, version
        elif '_v' in config_id:
            # Legacy format: session_20250918_150921_ea332116_v1_Configuration_for_AIML_co
            parts = config_id.split('_v')
            if len(parts) >= 2:
                session_part = parts[0]
                # Extract just the numeric version
                version_str = ''
                for char in parts[1]:
                    if char.isdigit():
                        version_str += char
                    elif version_str:  # Stop after finding digits
                        break
                version = int(version_str) if version_str else 1
                return session_part, version

        # Fallback: assume version 1
        return config_id, 1
    except (ValueError, IndexError) as e:
        logger.debug(f"Could not parse config_id: {config_id}, using fallback (v1). Error: {e}")
        return config_id, 1

def find_matching_configs_optimized(email: str, session_id: str, limit: int = 2) -> Dict[str, Any]:
    """
    Optimized config matching that starts with successfully used configs and only loads the latest
    version from each session. Much more efficient than loading all configs then filtering.

    Strategy:
    1. Try DynamoDB qc_by_column first (FAST) - can search 100+ configs
    2. If no qc data, fall back to S3 Excel analysis (SLOW) - limit to 10 attempts
    """
    try:
        storage_manager = UnifiedS3Manager()

        # OPTIMIZATION: Try DynamoDB first (fast path)
        table_columns = get_columns_from_dynamodb(email, session_id)
        used_fast_path = table_columns is not None

        if not table_columns:
            # FALLBACK: S3 Excel analysis (slow path)
            logger.info("[FIND_CONFIG] No DynamoDB qc_by_column data - using S3 Excel analysis (slow)")
            # Get Excel file from unified storage
            excel_content, excel_s3_key = storage_manager.get_excel_file(email, session_id)
            if not excel_content or not excel_s3_key:
                logger.warning(f"No Excel file found for session {session_id}")
                return {
                    'success': True,
                    'matches': [],
                    'table_columns': [],
                    'total_configs_searched': 0,
                    'message': 'Could not analyze columns from uploaded table. Please ensure you have uploaded a valid Excel file.'
                }

            # Analyze table structure directly from S3
            table_analysis = s3_table_parser.analyze_table_structure(storage_manager.bucket_name, excel_s3_key, extract_formulas=False)
            if table_analysis:
                column_analysis = table_analysis.get('column_analysis', {})
                table_columns = [col.strip() for col in column_analysis.keys() if col and col.strip()]
                logger.info(f"[FIND_CONFIG] Extracted {len(table_columns)} columns from S3: {table_columns[:5]}...")
        else:
            logger.info(f"[FIND_CONFIG] Using DynamoDB qc_by_column (fast path): {len(table_columns)} columns")

        if not table_columns:
            return {
                'success': True,
                'matches': [],
                'table_columns': [],
                'total_configs_searched': 0,
                'message': 'Could not analyze columns from uploaded table.'
            }
        
        # Get whitelist of successfully used configuration IDs (ordered by recency)
        successfully_used_configs = get_successfully_used_config_ids(email)
        logger.info(f"[FIND_CONFIG] Found {len(successfully_used_configs)} successfully used configs for filtering")
        logger.debug(f"[FIND_CONFIG] Whitelist first 5: {successfully_used_configs[:5]}")

        if not successfully_used_configs:
            # DynamoDB whitelist is empty — likely a timing issue (GSI eventual consistency
            # means a just-completed run's configuration_id may not be queryable yet).
            # Fall back to the legacy direct S3 scan so freshly generated configs are found.
            logger.info(
                "[FIND_CONFIG] No successfully used configs in DynamoDB whitelist — "
                "falling back to direct S3 scan (find_matching_configs_legacy)"
            )
            return find_matching_configs_legacy(email, session_id, limit)

        logger.info(f"[FIND_CONFIG] Starting interleaved qc_by_column filtering + S3 analysis")

        matches = []
        perfect_matches = []
        configs_processed = 0
        configs_excluded_by_qc = 0
        failed_loads = 0
        max_s3_analyses = 10
        max_configs_to_check = 50  # Limit total configs checked to avoid timeout

        # BATCH OPTIMIZATION: Pre-fetch qc_by_column data for all candidate configs
        import re
        session_pattern = r'^(session_(?:demo_)?\d{8}_\d{6}_[a-f0-9]{8})'
        candidate_session_ids = []
        for config_id in successfully_used_configs[:max_configs_to_check]:
            match = re.match(session_pattern, config_id)
            if match:
                candidate_session_ids.append(match.group(1))

        logger.info(f"[FIND_CONFIG] Batch fetching qc_by_column for {len(candidate_session_ids)} sessions")
        qc_columns_cache = batch_get_columns_from_dynamodb(email, candidate_session_ids)
        logger.info(f"[FIND_CONFIG] Cached qc_by_column data for {len(qc_columns_cache)} sessions")

        # Process configs in order of recency with interleaved qc filter + S3 check
        for idx, config_id in enumerate(successfully_used_configs):
            # TIMEOUT PROTECTION: Stop after checking too many configs
            if idx >= max_configs_to_check:
                logger.warning(f"[FIND_CONFIG] Reached max configs to check limit ({max_configs_to_check}), stopping")
                break
            # Stop early if we've analyzed enough
            if configs_processed >= max_s3_analyses:
                logger.warning(f"[FIND_CONFIG] Reached max S3 analyses limit ({max_s3_analyses}), stopping")
                break

            if failed_loads >= 30:
                logger.warning(f"[FIND_CONFIG] Reached max failed loads limit (30), stopping")
                break

            # Extract session from config_id
            match = re.match(session_pattern, config_id)
            config_session_id = match.group(1) if match else None

            # Try qc_by_column exclusionary filter first (fast) - use cached data
            if config_session_id:
                config_qc_columns = qc_columns_cache.get(config_session_id)

                if config_qc_columns:
                    # EXCLUSIONARY CHECK: If config has qc columns NOT in our table, skip
                    config_qc_set = set(config_qc_columns)
                    table_set = set(table_columns)
                    extra_columns = config_qc_set - table_set

                    if extra_columns:
                        logger.debug(f"[FIND_CONFIG] EXCLUDED {config_id}: has {len(extra_columns)} qc columns not in table")
                        configs_excluded_by_qc += 1
                        continue

                    logger.debug(f"[FIND_CONFIG] SHORTLISTED {config_id}: all {len(config_qc_columns)} qc columns present - checking S3 now")

            # Passed qc filter (or no qc data) - check S3 immediately
            try:
                logger.debug(f"[FIND_CONFIG] S3 check {configs_processed + 1}: Loading config {config_id}")

                # Load S3 config file (shortlisted, so likely to match)
                config_data, config_key = storage_manager.find_config_by_id(config_id, email)
                if not config_data:
                    logger.warning(f"[FIND_CONFIG] Failed load #{failed_loads + 1}: Config not in S3: {config_id}")
                    failed_loads += 1
                    continue

                # Extract validation targets from config file
                config_columns = extract_validation_targets(config_data)
                if not config_columns:
                    logger.debug(f"[FIND_CONFIG] No validation targets in config: {config_id}")
                    failed_loads += 1
                    continue

                logger.debug(f"[FIND_CONFIG] Successfully loaded {config_id}: {len(config_columns)} validation columns")
                failed_loads = 0
                configs_processed += 1

                # Calculate match score
                match_score = calculate_column_match_score(table_columns, config_columns)
                logger.debug(f"Config {config_id}: match_score={match_score:.3f}, table_cols={len(table_columns)}, config_cols={len(config_columns)}")

                if match_score >= 0.8:
                    logger.debug(f"High score config {config_id}: table={table_columns[:3]}..., config={config_columns[:3]}...")
                
                # Skip low matches
                if match_score < 0.8:
                    continue
                
                # Get metadata for match entry
                storage_metadata = config_data.get('storage_metadata', {})
                description = storage_metadata.get('description') or config_data.get('general_notes', 'No description available')
                
                # Create match data
                match_data = {
                    'config_id': config_id,
                    'config_key': config_key,
                    'config_s3_key': config_key,  # Add this for frontend compatibility
                    'match_score': match_score,
                    'description': description,
                    'created_date': storage_metadata.get('first_created') or storage_metadata.get('created_at', ''),
                    'last_modified': storage_metadata.get('stored_at', ''),
                    'column_count': len(config_columns),
                    'matching_columns': len(set(table_columns) & set(config_columns)),
                    'source_session': extract_session_and_version_from_config_id(config_id)[0]  # Extract session for frontend
                }
                
                # Categorize matches
                if match_score >= 1.0:
                    perfect_matches.append(match_data)
                    logger.info(f"PERFECT MATCH: {config_id} with score {match_score:.3f}")
                    # EARLY TERMINATION: Stop immediately when we find the first perfect match
                    logger.info(f"Stopping search after finding perfect match - processed {configs_processed} configs")
                    break
                else:
                    matches.append(match_data)
                
            except Exception as e:
                logger.error(f"Error processing config {config_id}: {e}")
                failed_loads += 1
                continue
        
        # Sort and return results
        logger.info(f"[FIND_CONFIG] Search complete: {configs_processed} S3 checks, {configs_excluded_by_qc} excluded by qc_by_column")

        if perfect_matches:
            # Sort by created_date and return only the most recent
            perfect_matches.sort(key=lambda x: x.get('created_date', ''), reverse=True)
            final_matches = [perfect_matches[0]]
            logger.info(f"Returning most recent perfect match: {perfect_matches[0]['config_id']}")
        else:
            final_matches = []
            logger.info("No perfect matches found - returning empty list")

        result = {
            'success': True,
            'matches': final_matches,
            'table_columns': table_columns,
            'total_configs_searched': configs_processed,
            'perfect_matches_found': len(perfect_matches),
            'regular_matches_found': len(matches),
            'total_available_configs': len(successfully_used_configs)
        }

        # Add perfect_match flag for frontend/backend to detect
        if final_matches:
            result['perfect_match'] = True
            result['auto_select_config'] = final_matches[0]
            logger.info(f"[FIND_CONFIG] Setting perfect_match=True, auto_select_config={final_matches[0].get('config_id')}")
        else:
            result['perfect_match'] = False

        return result
        
    except Exception as e:
        logger.error(f"Error in optimized config matching: {e}")
        return {
            'success': False,
            'error': str(e),
            'matches': [],
            'table_columns': [],
            'total_configs_searched': 0
        }

def find_matching_configs(email: str, session_id: str, limit: int = 2) -> Dict[str, Any]:
    """
    Find config files that match the uploaded table's column structure.
    Uses optimized approach that starts with whitelist of successful configs.
    """
    return find_matching_configs_optimized(email, session_id, limit)

def find_matching_configs_legacy(email: str, session_id: str, limit: int = 2) -> Dict[str, Any]:
    """
    LEGACY: Find config files that match the uploaded table's column structure
    
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
        
        # Get whitelist of successfully used configuration IDs
        successfully_used_configs = get_successfully_used_config_ids(email)
        logger.info(f"Found {len(successfully_used_configs)} successfully used configs for filtering")
        if successfully_used_configs:
            logger.info(f"Whitelist sample: {list(successfully_used_configs)[:3]}...")
        
        # Sort config files by modification time (most recent first) for better performance
        config_files.sort(key=lambda x: x['last_modified'], reverse=True)
        
        logger.info(f"Analyzing {len(config_files)} config files, first 3 by date:")
        for i, cf in enumerate(config_files[:3]):
            logger.debug(f"  {i+1}. {cf['filename']} - {cf['last_modified']} - {cf['key']}")
        
        # Check configs and collect up to 5 perfect matches or best matches
        matches = []
        perfect_matches = []
        s3_client = storage_manager.s3_client
        seen_content_hashes: Set[str] = set()  # For deduplication
        
        for i, config_file in enumerate(config_files):
            config_id = "unknown"  # Initialize config_id for error handling
            try:
                # Download and parse config
                response = s3_client.get_object(Bucket=storage_manager.bucket_name, Key=config_file['key'])
                config_data = json.loads(response['Body'].read().decode('utf-8'))
                
                # Extract source session and config ID FIRST for proper logging
                path_parts = config_file['key'].split('/')
                source_session = path_parts[-2] if len(path_parts) >= 2 else 'unknown'
                
                storage_metadata = config_data.get('storage_metadata', {})
                config_id = storage_metadata.get('config_id')
                logger.debug(f"Config file {config_file['key']}: storage_metadata.config_id = {config_id}")
                
                # Generate clean config_id from filename if not present (new format)
                if not config_id:
                    filename = config_file['key'].split('/')[-1]
                    logger.debug(f"Extracting from filename: {filename}, source_session: {source_session}")
                    if filename.endswith('.json'):
                        filename_without_ext = filename[:-5]  # Remove .json
                        config_id = f"{source_session}_{filename_without_ext}"
                        logger.info(f"Generated config_id from filename: {config_id} (session: {source_session}, file: {filename})")
                    else:
                        # Fallback for legacy - ensure config_id is always set
                        version = storage_metadata.get('version', 1)
                        config_id = f"{source_session}_v{version}_legacy"
                        logger.info(f"Generated legacy config_id: {config_id}")
                
                # Ensure config_id is never None
                if not config_id:
                    config_id = f"{source_session}_unknown_config"
                    logger.warning(f"Final fallback config_id: {config_id}")
                
                # Extract validation targets
                config_columns = extract_validation_targets(config_data)
                if not config_columns:
                    logger.debug(f"No validation targets found in {config_file['key']}")
                    continue
                
                logger.debug(f"Checking config {config_file['filename']}: {len(config_columns)} columns")
                
                # Get content hash from stored metadata (calculated when config was stored)
                content_hash = storage_metadata.get('content_hash', '')
                
                # Fallback: calculate hash if not stored (for older configs)
                if not content_hash:
                    content_hash = calculate_content_hash(config_data)
                
                # Skip if we've already seen this exact configuration content
                if content_hash and content_hash in seen_content_hashes:
                    logger.debug(f"Skipping duplicate config content with hash {content_hash}: {config_file['filename']}")
                    continue
                    
                if content_hash:
                    seen_content_hashes.add(content_hash)
                
                # Calculate match score
                match_score = calculate_column_match_score(table_columns, config_columns)
                logger.info(f"Config {config_id}: match_score={match_score:.3f}, table_cols={len(table_columns)}, config_cols={len(config_columns)}")
                if match_score >= 0.8:
                    logger.info(f"High score config {config_id}: table={table_columns[:3]}..., config={config_columns[:3]}...")
                
                # Skip matches that are too poor (below 80% threshold)
                if match_score < 0.8:
                    logger.debug(f"Skipping config with low match score: {match_score:.2f} < 0.8")
                    continue
                
                # Log only perfect and strong matches
                if match_score >= 0.9:
                    logger.info(f"Config match: {config_file['filename']} - Score: {match_score:.2f} ({len(config_columns)} columns)")
                
                # Find matching columns
                table_cols_lower = [col.lower().strip() for col in table_columns]
                config_cols_lower = [col.lower().strip() for col in config_columns]
                matching_columns = list(set(table_cols_lower) & set(config_cols_lower))
                
                description = storage_metadata.get('description') or config_data.get('general_notes', 'No description available')
                
                # FILTER TO ONLY SUCCESSFULLY USED CONFIGURATIONS
                # Only include configs that have been successfully used in Preview or Validation runs
                if successfully_used_configs:
                    # Check exact match first
                    config_allowed = config_id in successfully_used_configs
                    
                    # If no exact match, check for partial matches (in case of truncation)
                    if not config_allowed:
                        for used_config in successfully_used_configs:
                            if config_id.startswith(used_config) or used_config.startswith(config_id):
                                config_allowed = True
                                logger.info(f"Config {config_id} matched truncated whitelist entry: {used_config}")
                                break
                    
                    if not config_allowed:
                        logger.info(f"Skipping config {config_id}: not in successfully used configs whitelist")
                        logger.debug(f"Successfully used configs: {list(successfully_used_configs)[:5]}...")
                        continue
                    else:
                        logger.info(f"Config {config_id} passed whitelist filter")
                
                # Use original creation date from metadata with proper timezone handling
                storage_metadata = config_data.get('storage_metadata', {})
                
                # Get creation date - preserve original creation even for copied configs
                created_date = None
                if 'first_created' in storage_metadata and storage_metadata['first_created']:
                    created_date = storage_metadata['first_created']
                elif 'created_at' in storage_metadata and storage_metadata['created_at']:
                    created_date = storage_metadata['created_at']
                else:
                    # Fallback to S3 object creation date
                    s3_response = storage_manager.s3_client.head_object(
                        Bucket=storage_manager.bucket_name, 
                        Key=config_file['key']
                    )
                    created_date = s3_response['LastModified'].isoformat()

                # Get last used date from session usage tracking
                last_used_date = None
                try:
                    # Check session_info.json files for usage tracking
                    usage_info = get_config_usage_info(storage_manager, config_file['key'])
                    if usage_info and 'last_used' in usage_info:
                        last_used_date = usage_info['last_used']
                    else:
                        # Fallback: use file modification date only if no usage tracking
                        last_used_date = config_file['last_modified']
                except Exception as e:
                    logger.warning(f"Could not determine last used date: {e}")
                    last_used_date = created_date  # Safe fallback
                
                match_data = {
                    'config_s3_key': config_file['key'],
                    'config_data': config_data,
                    'created_date': created_date.isoformat() if hasattr(created_date, 'isoformat') else str(created_date),
                    'last_used_date': last_used_date.isoformat() if last_used_date and hasattr(last_used_date, 'isoformat') else None,
                    'source_session': storage_metadata.get('session_id', source_session),
                    'match_percentage': int(match_score * 100),
                    'content_hash_match': True,
                    'original_filename': storage_metadata.get('original_name', Path(config_file['key']).name),
                    'match_score': match_score,
                    'matching_columns': matching_columns,
                    'total_columns': len(config_columns),
                    'session_path': config_file['session_path'],
                    'last_modified': config_file['last_modified'].isoformat(),
                    'config_filename': config_file['filename'],
                    'config_id': config_id,
                    'description': description,
                    'usage_info': usage_info,
                    'content_hash': content_hash,
                    'version': storage_metadata.get('version', 1),
                    'original_name': storage_metadata.get('original_name'),
                    'source': storage_metadata.get('source', 'unknown')
                }
                
                # Separate perfect matches from regular matches
                if match_score >= 1.0:
                    logger.info(f"PERFECT MATCH FOUND with score {match_score} in config {config_file['key']}")
                    perfect_matches.append(match_data)
                    
                    # Continue searching for up to 2 perfect matches for performance
                    if len(perfect_matches) >= 2:
                        logger.info(f"Found 2 perfect matches, stopping search at config {i+1}")
                        break
                else:
                    matches.append(match_data)
                    
                # Early termination for regular matches if no perfect matches and we have enough regular matches
                if len(perfect_matches) == 0 and len(matches) >= 4 and i >= 10:
                    logger.info(f"Stopping search after checking {i+1} configs - found sufficient regular matches")
                    break
                
            except Exception as e:
                logger.error(f"Error processing config {config_file['key']} (config_id: {config_id}): {e}")
                continue
        
        # Combine and sort matches: perfect matches first, then by score and recency
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(hours=24)
        
        def sort_key(match):
            base_score = match['match_score']
            try:
                last_modified_str = match['last_modified'].replace('Z', '+00:00')
                last_modified = datetime.fromisoformat(last_modified_str)
            except (ValueError, AttributeError):
                # Fallback to epoch if date parsing fails
                last_modified = datetime.fromtimestamp(0, tz=timezone.utc)
            
            # Give slight bonus to very recent configs (within 24 hours)
            if last_modified > yesterday:
                recency_bonus = 0.05
            else:
                recency_bonus = 0.0
                
            # Sort primarily by score+bonus, then by date for final tiebreaker
            return (base_score + recency_bonus, last_modified)
        
        # Sort perfect matches by recency (since they all have score 1.0)
        perfect_matches.sort(key=lambda x: datetime.fromisoformat(x['last_modified'].replace('Z', '+00:00')), reverse=True)
        
        # Sort regular matches by score and recency
        matches.sort(key=sort_key, reverse=True)
        
        # NEW LOGIC: Only return the most recent 100% match, or no matches if none exist
        final_matches = []
        if perfect_matches:
            # Sort by created_date and return only the most recent
            perfect_matches.sort(key=lambda x: x.get('created_date', ''), reverse=True)
            final_matches = [perfect_matches[0]]  # Only most recent
            logger.info(f"Returning only most recent perfect match: {perfect_matches[0]['config_id']} created {perfect_matches[0].get('created_date')}")
        else:
            # FALLBACK: If whitelist filtering is too aggressive and we have no perfect matches,
            # but we searched configs, consider relaxing the filter for very high scores
            if successfully_used_configs and matches:
                high_score_matches = [m for m in matches if m.get('match_score', 0) >= 0.95]
                if high_score_matches:
                    logger.info(f"No perfect matches with whitelist, but found {len(high_score_matches)} high-score matches - considering fallback")
                    # For now, still return empty list but log for investigation
            
            # No perfect matches - return empty list (frontend will show only "Create with AI")
            final_matches = []
            logger.info("No perfect matches found - returning empty list")
        
        result = {
            'success': True,
            'matches': final_matches,
            'table_columns': table_columns,
            'total_configs_searched': len(config_files),
            'perfect_matches_found': len(perfect_matches),
            'regular_matches_found': len(matches)
        }
        
        # If we found perfect matches, mark the first one for auto-selection
        if final_matches:
            result['perfect_match'] = True
            result['auto_select_config'] = final_matches[0]
            logger.info(f"Perfect match found - suggesting auto-selection of config: {final_matches[0]['config_id']}")
        else:
            result['perfect_match'] = False
            
        return result
        
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