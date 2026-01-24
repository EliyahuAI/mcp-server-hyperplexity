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

        logger.info(f"[VIEWER_DATA] Using config version: {config_version}")

        # Load table_metadata JSON
        metadata_key = f"{session_path}v{config_version}_results/preview_table_metadata.json"
        table_metadata = _load_json_from_s3(storage_manager.bucket_name, metadata_key)

        if not table_metadata:
            # Try full validation metadata path
            metadata_key = f"{session_path}v{config_version}_results/table_metadata.json"
            table_metadata = _load_json_from_s3(storage_manager.bucket_name, metadata_key)

        if not table_metadata:
            return create_response(404, {
                'success': False,
                'error': 'Table metadata not found for this session'
            })

        # Find Excel file and generate download URL
        results_prefix = f"{session_path}v{config_version}_results/"
        excel_key, excel_filename = _find_excel_file(storage_manager.bucket_name, results_prefix)

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
    """Find the latest config version by listing result folders."""
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
            # Match pattern like "v1_results", "v2_results"
            if folder_name.startswith('v') and '_results' in folder_name:
                try:
                    version_num = int(folder_name.split('_')[0][1:])
                    versions.append(version_num)
                except (ValueError, IndexError):
                    pass

        return max(versions) if versions else None

    except Exception as e:
        logger.error(f"[VIEWER_DATA] Error finding versions: {e}")
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
