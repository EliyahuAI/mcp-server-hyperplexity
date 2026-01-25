"""
Handles viewer data retrieval for the results viewer page.
Loads table_metadata JSON and generates download URLs for completed sessions.
"""
import json
import logging
import boto3
import os
from typing import Optional, Dict, Any

from interface_lambda.utils.helpers import create_response
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')


def handle(request_data: Dict[str, Any], context) -> Dict:
    """
    Handle getViewerData requests.

    Required params:
        - email: User's email address
        - session_id: Session ID to load results for

    Optional params:
        - version: Config version number (default: latest)
        - is_preview: If False, only return full validation data (default: auto-detect best)

    Returns:
        - success: bool
        - table_metadata: Interactive table metadata JSON
        - table_name: Name of the table
        - download_url: URL to download Excel file
        - enhanced_download_url: URL to download enhanced Excel
        - json_download_url: URL to download JSON metadata
    """
    logger.info(f"[VIEWER_DATA] Starting handle with request_data: {request_data}")

    try:
        # Extract and validate parameters
        email = request_data.get('email', '').lower().strip()
        session_id = request_data.get('session_id', '').strip()
        version = request_data.get('version')
        is_preview = request_data.get('is_preview')  # None = auto, False = full only, True = preview only

        if not email:
            return create_response(400, {
                'success': False,
                'error': 'Email address is required'
            })

        if not session_id:
            return create_response(400, {
                'success': False,
                'error': 'Session ID is required'
            })

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Determine which bucket to use - try primary, fallback to -dev
        primary_bucket = storage_manager.bucket_name
        dev_bucket = f"{primary_bucket}-dev" if not primary_bucket.endswith('-dev') else primary_bucket

        # Get session path
        session_path = storage_manager.get_session_path(email, session_id)
        logger.info(f"[VIEWER_DATA] Session path: {session_path}")

        # Determine version to use - try primary bucket first, then dev bucket
        config_version = None
        active_bucket = primary_bucket

        if version:
            config_version = int(version)
        else:
            # Find latest version by listing result folders - try primary bucket first
            config_version = _find_latest_version_in_bucket(primary_bucket, session_path)
            if not config_version:
                # Try dev bucket as fallback
                config_version = _find_latest_version_in_bucket(dev_bucket, session_path)
                if config_version:
                    active_bucket = dev_bucket
                    logger.info(f"[VIEWER_DATA] Found results in dev bucket: {dev_bucket}")

            if not config_version:
                return create_response(404, {
                    'success': False,
                    'error': 'No validation results found for this session'
                })

        logger.info(f"[VIEWER_DATA] Using config version: {config_version}, is_preview: {is_preview}")

        # Determine results folder - try standard first, then -dev fallback
        results_prefix = f"{session_path}v{config_version}_results/"
        results_prefix_dev = f"{session_path}v{config_version}_results-dev/"

        # Check which results folder exists in the active bucket
        actual_results_prefix = _find_results_folder(active_bucket, results_prefix, results_prefix_dev)

        # If not found in active bucket, try the other bucket
        if not actual_results_prefix and active_bucket == primary_bucket:
            actual_results_prefix = _find_results_folder(dev_bucket, results_prefix, results_prefix_dev)
            if actual_results_prefix:
                active_bucket = dev_bucket
                logger.info(f"[VIEWER_DATA] Found results folder in dev bucket: {dev_bucket}")
        if not actual_results_prefix:
            return create_response(404, {
                'success': False,
                'error': 'No results folder found for this session'
            })

        logger.info(f"[VIEWER_DATA] Using results folder: {actual_results_prefix}")

        # Load table_metadata JSON with priority:
        # 1. If is_preview=False (explicitly requesting full): only try full validation metadata
        # 2. Otherwise (auto or preview): try full first, then fallback to preview
        table_metadata = None
        metadata_key = None
        is_full_validation = False

        if is_preview is not True:  # is_preview is False or None (auto)
            # Try full validation metadata first (table_metadata.json)
            full_metadata_key = f"{actual_results_prefix}table_metadata.json"
            table_metadata = _load_json_from_s3(active_bucket, full_metadata_key)
            if table_metadata:
                metadata_key = full_metadata_key
                is_full_validation = True
                logger.info(f"[VIEWER_DATA] Loaded full validation metadata from {full_metadata_key}")

        if not table_metadata and is_preview is not False:
            # Try preview metadata (preview_table_metadata.json)
            preview_metadata_key = f"{actual_results_prefix}preview_table_metadata.json"
            table_metadata = _load_json_from_s3(active_bucket, preview_metadata_key)
            if table_metadata:
                metadata_key = preview_metadata_key
                logger.info(f"[VIEWER_DATA] Loaded preview metadata from {preview_metadata_key}")

        if not table_metadata:
            return create_response(404, {
                'success': False,
                'error': 'Table metadata not found for this session'
            })

        # Find Excel file and generate download URL
        excel_key, excel_filename = _find_excel_file(active_bucket, actual_results_prefix)

        enhanced_download_url = None
        if excel_key:
            enhanced_download_url = _generate_presigned_url(
                active_bucket,
                excel_key,
                excel_filename or 'results.xlsx'
            )

        # Generate JSON download URL
        json_download_url = _generate_presigned_url(
            active_bucket,
            metadata_key,
            f"table_metadata_v{config_version}.json"
        )

        # Extract table name from metadata or session
        table_name = table_metadata.get('table_name') or _extract_table_name(session_id)

        # Load session_info to get clean_table_name and analysis date
        clean_table_name = None
        original_filename = None
        analysis_date = None

        try:
            session_info = storage_manager.load_session_info(email, session_id)
            clean_table_name = session_info.get('clean_table_name')
            original_filename = session_info.get('original_filename')

            # Try to get analysis date from session_info versions
            versions_info = session_info.get('versions', {})
            version_key = f"v{config_version}"
            if version_key in versions_info:
                version_info = versions_info[version_key]
                # Look for validation completion time
                analysis_date = version_info.get('validation_completed_at') or version_info.get('created_at')

            # Fallback: use table_metadata timestamp if available
            if not analysis_date and table_metadata:
                analysis_date = table_metadata.get('generated_at') or table_metadata.get('created_at')

            logger.info(f"[VIEWER_DATA] Loaded session_info: clean_table_name='{clean_table_name}', analysis_date='{analysis_date}'")
        except Exception as e:
            logger.warning(f"[VIEWER_DATA] Could not load session_info: {e}")

        # If no original_filename, try to find it from S3 (input xlsx files in session folder)
        if not original_filename:
            try:
                response = s3_client.list_objects_v2(
                    Bucket=active_bucket,
                    Prefix=session_path,
                    MaxKeys=50
                )
                for obj in response.get('Contents', []):
                    key = obj['Key']
                    filename = key.split('/')[-1]
                    # Look for input xlsx files (not in results folders)
                    if filename.endswith('.xlsx') and '_results' not in key and 'v1_' not in key and 'v2_' not in key:
                        original_filename = filename
                        logger.info(f"[VIEWER_DATA] Found input file in S3: {original_filename}")
                        break
            except Exception as e:
                logger.debug(f"[VIEWER_DATA] Could not find input file in S3: {e}")

        # If still no analysis_date, try to get from results folder metadata file timestamp
        if not analysis_date:
            try:
                response = s3_client.head_object(
                    Bucket=active_bucket,
                    Key=metadata_key
                )
                if 'LastModified' in response:
                    analysis_date = response['LastModified'].isoformat()
                    logger.info(f"[VIEWER_DATA] Got analysis_date from S3 metadata: {analysis_date}")
            except Exception as e:
                logger.debug(f"[VIEWER_DATA] Could not get metadata timestamp: {e}")

        # If no clean_table_name from session_info, derive from original filename
        if not clean_table_name or clean_table_name == "Validation Results":
            from interface_lambda.utils.helpers import clean_table_name as derive_clean_name
            # Prefer original_filename, then try session_id for a meaningful name
            if original_filename:
                clean_table_name = derive_clean_name(original_filename, for_display=True)
            else:
                # Last resort: use session_id but make it readable
                clean_table_name = f"Table {session_id.split('_')[-1][:8]}"
            logger.info(f"[VIEWER_DATA] Derived clean_table_name: '{clean_table_name}'")

        return create_response(200, {
            'success': True,
            'table_metadata': table_metadata,
            'table_name': table_name,
            'clean_table_name': clean_table_name,
            'original_filename': original_filename,
            'analysis_date': analysis_date,
            'session_id': session_id,
            'version': config_version,
            'is_full_validation': is_full_validation,
            'enhanced_download_url': enhanced_download_url,
            'json_download_url': json_download_url
        })

    except Exception as e:
        logger.error(f"[VIEWER_DATA] Error processing request: {e}")
        import traceback
        logger.error(f"[VIEWER_DATA] Traceback: {traceback.format_exc()}")
        return create_response(500, {
            'success': False,
            'error': 'Failed to retrieve viewer data',
            'details': str(e)
        })


def _find_latest_version_in_bucket(bucket: str, session_path: str) -> Optional[int]:
    """Find the latest config version by listing result folders in a specific bucket.

    Handles both standard (_results) and dev (_results-dev) folders.
    """
    try:
        response = s3_client.list_objects_v2(
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
                    # Extract version number: "v1_results" or "v1_results-dev" -> 1
                    version_part = folder_name.split('_')[0]  # "v1"
                    version_num = int(version_part[1:])  # 1
                    versions.append(version_num)
                except (ValueError, IndexError):
                    pass

        return max(versions) if versions else None

    except Exception as e:
        logger.error(f"[VIEWER_DATA] Error finding versions: {e}")
        return None


def _find_results_folder(bucket: str, standard_prefix: str, dev_prefix: str) -> Optional[str]:
    """Find which results folder exists, preferring standard over dev.

    Args:
        bucket: S3 bucket name
        standard_prefix: Standard results folder path (e.g., v1_results/)
        dev_prefix: Dev results folder path (e.g., v1_results-dev/)

    Returns:
        The prefix of the folder that exists, or None if neither exists.
    """
    try:
        # Check standard folder first
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=standard_prefix,
            MaxKeys=1
        )
        if response.get('Contents'):
            return standard_prefix

        # Fallback to dev folder
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=dev_prefix,
            MaxKeys=1
        )
        if response.get('Contents'):
            logger.info(f"[VIEWER_DATA] Using dev folder as fallback: {dev_prefix}")
            return dev_prefix

        return None

    except Exception as e:
        logger.error(f"[VIEWER_DATA] Error finding results folder: {e}")
        return None


def _load_json_from_s3(bucket: str, key: str) -> Optional[Dict]:
    """Load and parse JSON file from S3."""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')
        return json.loads(content)
    except s3_client.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'NoSuchKey':
            logger.warning(f"[VIEWER_DATA] Key not found: {key}")
        else:
            logger.error(f"[VIEWER_DATA] S3 error loading {key}: {e}")
        return None
    except Exception as e:
        logger.error(f"[VIEWER_DATA] Error loading JSON from {key}: {e}")
        return None


def _find_excel_file(bucket: str, prefix: str) -> tuple:
    """Find enhanced Excel file in the results folder."""
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix
        )

        for obj in response.get('Contents', []):
            key = obj['Key']
            # Look for enhanced Excel files
            if key.endswith('.xlsx') and 'enhanced' in key.lower():
                filename = key.split('/')[-1]
                return key, filename

        # Fallback: any xlsx file
        for obj in response.get('Contents', []):
            key = obj['Key']
            if key.endswith('.xlsx'):
                filename = key.split('/')[-1]
                return key, filename

        return None, None

    except Exception as e:
        logger.error(f"[VIEWER_DATA] Error finding Excel file: {e}")
        return None, None


def _generate_presigned_url(bucket: str, key: str, filename: str, expiration: int = 3600) -> Optional[str]:
    """Generate a presigned download URL."""
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket,
                'Key': key,
                'ResponseContentDisposition': f'attachment; filename="{filename}"'
            },
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        logger.error(f"[VIEWER_DATA] Error generating presigned URL: {e}")
        return None


def _extract_table_name(session_id: str) -> str:
    """Extract a readable table name from session ID."""
    # Session IDs look like: session_20240124_abc123
    try:
        parts = session_id.split('_')
        if len(parts) >= 2:
            date_part = parts[1] if len(parts) > 1 else ''
            if len(date_part) == 8:  # YYYYMMDD
                formatted_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
                return f"Validation Results ({formatted_date})"
    except Exception:
        pass
    return "Validation Results"
