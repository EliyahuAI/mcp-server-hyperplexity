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

        # Get session path
        session_path = storage_manager.get_session_path(email, session_id)
        logger.info(f"[VIEWER_DATA] Session path: {session_path}")

        # Determine version to use
        if version:
            config_version = int(version)
        else:
            # Find latest version by listing result folders
            config_version = _find_latest_version(storage_manager, session_path)
            if not config_version:
                return create_response(404, {
                    'success': False,
                    'error': 'No validation results found for this session'
                })

        logger.info(f"[VIEWER_DATA] Using config version: {config_version}, is_preview: {is_preview}")

        # Determine results folder - try standard first, then -dev fallback
        results_prefix = f"{session_path}v{config_version}_results/"
        results_prefix_dev = f"{session_path}v{config_version}_results-dev/"

        # Check which results folder exists
        actual_results_prefix = _find_results_folder(storage_manager.bucket_name, results_prefix, results_prefix_dev)
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
            table_metadata = _load_json_from_s3(storage_manager.bucket_name, full_metadata_key)
            if table_metadata:
                metadata_key = full_metadata_key
                is_full_validation = True
                logger.info(f"[VIEWER_DATA] Loaded full validation metadata from {full_metadata_key}")

        if not table_metadata and is_preview is not False:
            # Try preview metadata (preview_table_metadata.json)
            preview_metadata_key = f"{actual_results_prefix}preview_table_metadata.json"
            table_metadata = _load_json_from_s3(storage_manager.bucket_name, preview_metadata_key)
            if table_metadata:
                metadata_key = preview_metadata_key
                logger.info(f"[VIEWER_DATA] Loaded preview metadata from {preview_metadata_key}")

        if not table_metadata:
            return create_response(404, {
                'success': False,
                'error': 'Table metadata not found for this session'
            })

        # Find Excel file and generate download URL
        excel_key, excel_filename = _find_excel_file(storage_manager.bucket_name, actual_results_prefix)

        enhanced_download_url = None
        if excel_key:
            enhanced_download_url = _generate_presigned_url(
                storage_manager.bucket_name,
                excel_key,
                excel_filename or 'results.xlsx'
            )

        # Generate JSON download URL
        json_download_url = _generate_presigned_url(
            storage_manager.bucket_name,
            metadata_key,
            f"table_metadata_v{config_version}.json"
        )

        # Extract table name from metadata or session
        table_name = table_metadata.get('table_name') or _extract_table_name(session_id)

        return create_response(200, {
            'success': True,
            'table_metadata': table_metadata,
            'table_name': table_name,
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


def _find_latest_version(storage_manager: UnifiedS3Manager, session_path: str) -> Optional[int]:
    """Find the latest config version by listing result folders.

    Handles both standard (_results) and dev (_results-dev) folders.
    """
    try:
        response = s3_client.list_objects_v2(
            Bucket=storage_manager.bucket_name,
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
