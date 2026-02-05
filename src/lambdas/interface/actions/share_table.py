"""
Share Table Handler - Publishes validation results as a public demo table.

Copies table_metadata.json and enhanced Excel from a user's session to the
public demos folder: demos/interactive_tables/{slug}/

The shared table is then accessible via ?demo={slug} URL without authentication.
"""
import hashlib
import json
import logging
import os
import re
import time
from typing import Dict, Any

import boto3

from interface_lambda.utils.helpers import create_response
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

# Reuse session ID validation from viewer_data
from interface_lambda.actions.viewer_data import (
    SESSION_ID_PATTERN,
    _verify_session_ownership_cached,
    _find_latest_version_in_bucket,
    _find_results_folder,
    _load_json_from_s3,
    _find_excel_file,
)


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s_-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text[:50]  # Limit length


def _generate_demo_name(table_name: str, session_id: str) -> str:
    """Generate a URL-safe demo name from table name + session hash."""
    slug = _slugify(table_name) if table_name else 'shared-table'
    if not slug:
        slug = 'shared-table'
    hash_suffix = hashlib.md5(session_id.encode()).hexdigest()[:6]
    return f"{slug}-{hash_suffix}"


def handle(request_data: Dict[str, Any], context) -> Dict:
    """
    Handle shareTable requests.

    Required params (injected by http_handler):
        - _verified_email: User's verified email address
        - session_id: Session ID to share

    Optional params:
        - version: Config version number (default: latest)

    Returns:
        - success: bool
        - table_name: The demo slug name for the URL
        - share_url_path: The ?demo= query parameter value
        - already_shared: bool
    """
    try:
        email = request_data.get('_verified_email')
        if not email:
            return create_response(401, {
                'success': False,
                'error': 'Authentication required.'
            })

        session_id = request_data.get('session_id', '').strip()
        version = request_data.get('version')

        if not session_id:
            return create_response(400, {
                'success': False,
                'error': 'Session ID is required'
            })

        # Validate session ID format
        if not SESSION_ID_PATTERN.match(session_id):
            logger.warning(f"[SHARE] Invalid session ID format: {session_id}")
            return create_response(400, {
                'success': False,
                'error': 'Invalid session ID format'
            })

        # Verify session ownership
        if not _verify_session_ownership_cached(email, session_id):
            logger.warning(f"[SHARE] Ownership check failed: {email} -> {session_id}")
            return create_response(403, {
                'success': False,
                'error': 'Access denied: you do not own this session.'
            })

        # Initialize storage manager and find session data
        storage_manager = UnifiedS3Manager()
        primary_bucket = storage_manager.bucket_name
        dev_bucket = f"{primary_bucket}-dev" if not primary_bucket.endswith('-dev') else primary_bucket

        session_path = storage_manager.get_session_path(email, session_id)

        # Find config version
        config_version = None
        active_bucket = primary_bucket

        if version:
            config_version = int(version)
        else:
            config_version = _find_latest_version_in_bucket(primary_bucket, session_path)
            if not config_version:
                config_version = _find_latest_version_in_bucket(dev_bucket, session_path)
                if config_version:
                    active_bucket = dev_bucket

            if not config_version:
                return create_response(404, {
                    'success': False,
                    'error': 'No validation results found for this session'
                })

        # Find results folder
        results_prefix = f"{session_path}v{config_version}_results/"
        results_prefix_dev = f"{session_path}v{config_version}_results-dev/"

        actual_results_prefix = _find_results_folder(active_bucket, results_prefix, results_prefix_dev)
        if not actual_results_prefix and active_bucket == primary_bucket:
            actual_results_prefix = _find_results_folder(dev_bucket, results_prefix, results_prefix_dev)
            if actual_results_prefix:
                active_bucket = dev_bucket

        if not actual_results_prefix:
            return create_response(404, {
                'success': False,
                'error': 'No results folder found for this session'
            })

        # Load full validation metadata only (not preview)
        full_metadata_key = f"{actual_results_prefix}table_metadata.json"
        table_metadata = _load_json_from_s3(active_bucket, full_metadata_key)

        if not table_metadata:
            return create_response(400, {
                'success': False,
                'error': 'Only fully validated tables can be shared. Please run a full validation first.'
            })

        # Get table name from metadata - this is the primary source
        table_name = table_metadata.get('table_name', '')
        logger.info(f"[SHARE] table_name from metadata: '{table_name}'")

        # Try session_info for clean_table_name, original_filename, and analysis date
        session_info_key = f"{session_path}session_info.json"
        session_info = _load_json_from_s3(active_bucket, session_info_key)
        clean_table_name = None
        original_filename = None
        analysis_date = None

        logger.info(f"[SHARE] session_info loaded: {session_info is not None}")

        if session_info:
            clean_table_name = session_info.get('clean_table_name')
            original_filename = session_info.get('original_filename')

            logger.info(f"[SHARE] From session_info: clean_table_name='{clean_table_name}', original_filename='{original_filename}'")

            # Get analysis date from version info
            versions_info = session_info.get('versions', {})
            version_key = f"v{config_version}"
            if version_key in versions_info:
                version_info = versions_info[version_key]
                analysis_date = version_info.get('validation_completed_at') or version_info.get('created_at')

        # Fallback: use table_metadata timestamp if available
        if not analysis_date and table_metadata:
            analysis_date = table_metadata.get('generated_at') or table_metadata.get('created_at')

        # Get original_filename if not already set
        if not original_filename:
            original_filename = table_metadata.get('original_filename')

        # Helper function to check if a name is valid and meaningful
        def is_valid_name(name):
            if not name or not isinstance(name, str):
                return False
            name = name.strip()
            # Filter out empty, generic, or placeholder names
            if not name or name in ['Validation Results', 'Shared Table', 'Table', '']:
                return False
            # Filter out names that look like session IDs
            if name.startswith('Table ') and len(name) <= 15:
                return False
            return True

        # Determine display name with comprehensive fallback chain
        # Priority: clean_table_name > table_name > derived from filename > session ID
        display_name = None

        # 1. Try clean_table_name from session_info (best - human-readable)
        if is_valid_name(clean_table_name):
            display_name = clean_table_name.strip()
            logger.info(f"[SHARE] Using clean_table_name: '{display_name}'")

        # 2. Try table_name from metadata
        if not display_name and is_valid_name(table_name):
            display_name = table_name.strip()
            logger.info(f"[SHARE] Using table_name: '{display_name}'")

        # 3. Try deriving from original_filename
        if not display_name and original_filename:
            from interface_lambda.utils.helpers import clean_table_name as derive_clean_name
            derived_name = derive_clean_name(original_filename, for_display=True)
            if is_valid_name(derived_name):
                display_name = derived_name
                logger.info(f"[SHARE] Derived from filename: '{display_name}'")

        # 4. Last resort: extract from table_metadata structure or use session ID
        if not display_name:
            logger.warning(f"[SHARE] No valid display name found in standard locations")
            # Try to get a hint from first column name
            if table_metadata.get('columns') and len(table_metadata.get('columns', [])) > 0:
                first_col = table_metadata['columns'][0].get('name', '')
                if first_col and first_col not in ['Column', 'Row', 'ID', 'Index']:
                    display_name = f"Table - {first_col}"
                    logger.info(f"[SHARE] Using column hint: '{display_name}'")

            # Final fallback: session ID
            if not display_name:
                session_suffix = session_id.split('_')[-1][:8] if '_' in session_id else session_id[:8]
                display_name = f"Shared Table {session_suffix}"
                logger.warning(f"[SHARE] Using session ID fallback: '{display_name}'")

        logger.info(f"[SHARE] Final display_name: '{display_name}'")
        demo_name = _generate_demo_name(display_name, session_id)

        # Determine demo bucket (demos go to the same env bucket)
        env = os.environ.get('ENVIRONMENT', 'prod')
        base_bucket = os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')
        if env == 'dev' or base_bucket.endswith('-dev'):
            demo_bucket = base_bucket if base_bucket.endswith('-dev') else f"{base_bucket}-dev"
        else:
            demo_bucket = base_bucket.replace('-dev', '')

        demo_path = f"demos/interactive_tables/{demo_name}/"

        # Check if already shared (idempotent)
        existing_info = _load_json_from_s3(demo_bucket, f"{demo_path}info.json")
        if existing_info and existing_info.get('source_session_id') == session_id:
            logger.info(f"[SHARE] Already shared: {demo_name} (session {session_id})")
            return create_response(200, {
                'success': True,
                'table_name': demo_name,
                'share_url_path': demo_name,
                'already_shared': True
            })

        # Create a deep copy of metadata to avoid any potential reference issues
        # This ensures the original session metadata is never modified
        import copy
        demo_metadata = copy.deepcopy(table_metadata)

        # Update table_name in the COPY to use the clean display name
        demo_metadata['table_name'] = display_name

        # Copy table_metadata.json to demo folder using the modified copy
        logger.info(f"[SHARE] Copying metadata to s3://{demo_bucket}/{demo_path}table_metadata.json")
        s3_client.put_object(
            Bucket=demo_bucket,
            Key=f"{demo_path}table_metadata.json",
            Body=json.dumps(demo_metadata).encode('utf-8'),
            ContentType='application/json'
        )

        # Copy enhanced Excel file
        excel_key, excel_filename = _find_excel_file(active_bucket, actual_results_prefix, is_full_validation=True)
        if excel_key:
            try:
                excel_obj = s3_client.get_object(Bucket=active_bucket, Key=excel_key)
                excel_content = excel_obj['Body'].read()
                dest_excel_name = excel_filename or 'results.xlsx'
                s3_client.put_object(
                    Bucket=demo_bucket,
                    Key=f"{demo_path}{dest_excel_name}",
                    Body=excel_content,
                    ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                logger.info(f"[SHARE] Copied Excel: {dest_excel_name}")
            except Exception as e:
                logger.warning(f"[SHARE] Could not copy Excel file: {e}")

        # Create info.json with provenance
        email_hash = hashlib.sha256(email.lower().strip().encode()).hexdigest()[:16]
        info = {
            'display_name': display_name,
            'source_session_id': session_id,
            'source_email_hash': email_hash,
            'source_version': config_version,
            'shared_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'original_filename': original_filename,
            'analysis_date': analysis_date
        }

        s3_client.put_object(
            Bucket=demo_bucket,
            Key=f"{demo_path}info.json",
            Body=json.dumps(info).encode('utf-8'),
            ContentType='application/json'
        )

        logger.info(f"[SHARE] Successfully shared session {session_id} as demo '{demo_name}'")

        return create_response(200, {
            'success': True,
            'table_name': demo_name,
            'share_url_path': demo_name,
            'already_shared': False
        })

    except Exception as e:
        logger.error(f"[SHARE] Error: {e}")
        import traceback
        logger.error(f"[SHARE] Traceback: {traceback.format_exc()}")
        return create_response(500, {
            'success': False,
            'error': 'Failed to share table'
        })


def _get_demo_bucket() -> str:
    """Get the appropriate demo bucket based on environment."""
    env = os.environ.get('ENVIRONMENT', 'prod')
    base_bucket = os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')
    if env == 'dev' or base_bucket.endswith('-dev'):
        return base_bucket if base_bucket.endswith('-dev') else f"{base_bucket}-dev"
    return base_bucket.replace('-dev', '')


def _find_shared_demo_for_session(demo_bucket: str, session_id: str, demo_name_hint: str = None) -> dict:
    """
    Find if a session has been shared as a demo.

    If demo_name_hint is provided, check that specific demo first (fast path).
    Otherwise, we rely on the deterministic name generation.

    Returns:
        dict with 'found', 'demo_name', 'demo_path', 'info' keys, or {'found': False}
    """
    # Since demo names are deterministic (based on table name + session hash),
    # we need the table name to reconstruct. But we can also scan by listing
    # demos and checking info.json. For efficiency, we list demos with the
    # session hash suffix.
    hash_suffix = hashlib.md5(session_id.encode()).hexdigest()[:6]

    if demo_name_hint:
        # Fast path: check specific demo
        info = _load_json_from_s3(demo_bucket, f"demos/interactive_tables/{demo_name_hint}/info.json")
        if info and info.get('source_session_id') == session_id:
            return {
                'found': True,
                'demo_name': demo_name_hint,
                'demo_path': f"demos/interactive_tables/{demo_name_hint}/",
                'info': info
            }

    # Search for demos ending with the session hash suffix (paginated)
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(
            Bucket=demo_bucket,
            Prefix='demos/interactive_tables/',
            Delimiter='/'
        )

        for page in pages:
            for prefix_obj in page.get('CommonPrefixes', []):
                folder = prefix_obj.get('Prefix', '').rstrip('/')
                folder_name = folder.split('/')[-1]
                if folder_name.endswith(f"-{hash_suffix}"):
                    info = _load_json_from_s3(demo_bucket, f"{folder}/info.json")
                    if info and info.get('source_session_id') == session_id:
                        return {
                            'found': True,
                            'demo_name': folder_name,
                            'demo_path': f"{folder}/",
                            'info': info
                        }
    except Exception as e:
        logger.warning(f"[SHARE] Error searching for shared demos: {e}")

    return {'found': False}


def handle_unshare(request_data: Dict[str, Any], context) -> Dict:
    """
    Handle unshareTable requests - removes a shared demo.

    Required params:
        - _verified_email: User's verified email address
        - session_id: Session ID whose share to remove

    Optional params:
        - table_name: The demo slug (speeds up lookup)

    Returns:
        - success: bool
        - was_shared: bool (whether it was shared before)
    """
    try:
        email = request_data.get('_verified_email')
        if not email:
            return create_response(401, {
                'success': False,
                'error': 'Authentication required.'
            })

        session_id = request_data.get('session_id', '').strip()
        table_name_hint = request_data.get('table_name', '').strip() or None

        if not session_id:
            return create_response(400, {
                'success': False,
                'error': 'Session ID is required'
            })

        if not SESSION_ID_PATTERN.match(session_id):
            return create_response(400, {
                'success': False,
                'error': 'Invalid session ID format'
            })

        # Verify ownership
        if not _verify_session_ownership_cached(email, session_id):
            return create_response(403, {
                'success': False,
                'error': 'Access denied: you do not own this session.'
            })

        demo_bucket = _get_demo_bucket()
        shared = _find_shared_demo_for_session(demo_bucket, session_id, table_name_hint)

        if not shared['found']:
            return create_response(200, {
                'success': True,
                'was_shared': False
            })

        # Delete all objects in the demo folder
        demo_path = shared['demo_path']
        try:
            response = s3_client.list_objects_v2(
                Bucket=demo_bucket,
                Prefix=demo_path
            )
            objects_to_delete = [{'Key': obj['Key']} for obj in response.get('Contents', [])]
            if objects_to_delete:
                s3_client.delete_objects(
                    Bucket=demo_bucket,
                    Delete={'Objects': objects_to_delete}
                )
                logger.info(f"[SHARE] Deleted {len(objects_to_delete)} objects from {demo_path}")
        except Exception as e:
            logger.error(f"[SHARE] Error deleting demo objects: {e}")
            return create_response(500, {
                'success': False,
                'error': 'Failed to remove shared table'
            })

        logger.info(f"[SHARE] Unshared session {session_id} (demo '{shared['demo_name']}')")

        return create_response(200, {
            'success': True,
            'was_shared': True,
            'removed_demo_name': shared['demo_name']
        })

    except Exception as e:
        logger.error(f"[SHARE] Unshare error: {e}")
        import traceback
        logger.error(f"[SHARE] Traceback: {traceback.format_exc()}")
        return create_response(500, {
            'success': False,
            'error': 'Failed to unshare table'
        })


def handle_check_share_status(request_data: Dict[str, Any], context) -> Dict:
    """
    Handle checkShareStatus requests - checks if a session is currently shared.

    Required params:
        - _verified_email: User's verified email address
        - session_id: Session ID to check

    Returns:
        - success: bool
        - is_shared: bool
        - table_name: demo slug (if shared)
        - share_url_path: demo slug for URL (if shared)
    """
    try:
        email = request_data.get('_verified_email')
        if not email:
            return create_response(401, {
                'success': False,
                'error': 'Authentication required.'
            })

        session_id = request_data.get('session_id', '').strip()

        if not session_id:
            return create_response(400, {
                'success': False,
                'error': 'Session ID is required'
            })

        if not SESSION_ID_PATTERN.match(session_id):
            return create_response(400, {
                'success': False,
                'error': 'Invalid session ID format'
            })

        # Verify ownership
        if not _verify_session_ownership_cached(email, session_id):
            return create_response(403, {
                'success': False,
                'error': 'Access denied: you do not own this session.'
            })

        demo_bucket = _get_demo_bucket()
        shared = _find_shared_demo_for_session(demo_bucket, session_id)

        if shared['found']:
            return create_response(200, {
                'success': True,
                'is_shared': True,
                'table_name': shared['demo_name'],
                'share_url_path': shared['demo_name']
            })
        else:
            return create_response(200, {
                'success': True,
                'is_shared': False
            })

    except Exception as e:
        logger.error(f"[SHARE] Check status error: {e}")
        return create_response(500, {
            'success': False,
            'error': 'Failed to check share status'
        })
