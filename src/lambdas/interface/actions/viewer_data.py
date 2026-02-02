"""
Handles viewer data retrieval for the results viewer page.
Loads table_metadata JSON and generates download URLs for completed sessions.
"""
import json
import logging
import boto3
import os
import re
import time
from typing import Optional, Dict, Any

from interface_lambda.utils.helpers import create_response
from interface_lambda.utils.session_manager import extract_email_from_request, revoke_token
from interface_lambda.utils.rate_limiter import check_rate_limit
from interface_lambda.utils.security_logger import (
    log_ownership_violation,
    log_rate_limit_exceeded,
    log_invalid_session_format,
    log_path_traversal_attempt,
    log_unvalidated_email_access
)
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

# Lambda instance-level cache (persists across warm invocations for performance)
_SESSION_OWNERSHIP_CACHE = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes

# Session ID validation pattern: session_YYYYMMDD_HHMMSS_xxxxxxxx OR session_demo_YYYYMMDD_HHMMSS_xxxxxxxx
SESSION_ID_PATTERN = re.compile(r'^session_(demo_)?\d{8}_\d{6}_[a-f0-9]{8}$')


def _verify_session_ownership(email: str, session_id: str) -> bool:
    """
    Verify that email owns the session_id in DynamoDB (no caching).

    Args:
        email: User's email address (normalized)
        session_id: Session ID to verify

    Returns:
        True if email owns the session, False otherwise
    """
    try:
        runs_table = boto3.resource('dynamodb', region_name='us-east-1').Table('perplexity-validator-runs')
        response = runs_table.get_item(Key={'session_id': session_id})

        if 'Item' not in response:
            logger.warning(f"[SECURITY] Session not found: {session_id}")
            return False

        session_email = response['Item'].get('email', '').lower().strip()
        request_email = email.lower().strip()

        if session_email != request_email:
            logger.error(f"[SECURITY] Ownership violation: {request_email} attempted to access session owned by {session_email}")
            return False

        return True
    except Exception as e:
        logger.error(f"[SECURITY] Error verifying ownership: {e}")
        return False


def _verify_session_ownership_cached(email: str, session_id: str) -> bool:
    """
    Verify session ownership with 5-minute Lambda cache.

    Performance:
    - Cache hit: ~2ms (dictionary lookup)
    - Cache miss: ~30ms (DynamoDB read)
    - Expected hit rate: >95% (users repeatedly access same sessions)

    Args:
        email: User's email address (normalized)
        session_id: Session ID to verify

    Returns:
        True if email owns the session, False otherwise
    """
    cache_key = f"{email}:{session_id}"
    now = time.time()

    # Check cache first
    cached = _SESSION_OWNERSHIP_CACHE.get(cache_key)
    if cached and (now - cached['timestamp']) < _CACHE_TTL_SECONDS:
        logger.debug(f"[CACHE_HIT] Session ownership for {cache_key}")
        return cached['is_owner']

    # Cache miss - query DynamoDB
    logger.debug(f"[CACHE_MISS] Querying DynamoDB for {cache_key}")
    is_owner = _verify_session_ownership(email, session_id)

    # Store in cache
    _SESSION_OWNERSHIP_CACHE[cache_key] = {
        'is_owner': is_owner,
        'timestamp': now
    }

    # Limit cache size (prevent memory bloat)
    if len(_SESSION_OWNERSHIP_CACHE) > 1000:
        # Remove oldest entries
        sorted_items = sorted(_SESSION_OWNERSHIP_CACHE.items(), key=lambda x: x[1]['timestamp'])
        for old_key, _ in sorted_items[:500]:  # Remove oldest 500
            del _SESSION_OWNERSHIP_CACHE[old_key]

    return is_owner


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
        # SECURITY: Extract headers and IP from request_data (added by http_handler)
        headers = request_data.get('_headers', {})
        request_context = request_data.get('_requestContext', {})
        ip_address = request_context.get('identity', {}).get('sourceIp')

        # SECURITY: Extract email from verified session token (preferred)
        # Falls back to email field in request body for backward compatibility
        email = extract_email_from_request(request_data, headers)

        # Backward compatibility: if no token, try email field (legacy support)
        if not email:
            email = request_data.get('email', '').lower().strip()
            if email:
                logger.warning(f"[SECURITY] Legacy email field used (no session token): {email}")

        # Extract and validate parameters
        session_id = request_data.get('session_id', '').strip()
        version = request_data.get('version')
        is_preview = request_data.get('is_preview')  # None = auto, False = full only, True = preview only

        if not email:
            return create_response(400, {
                'success': False,
                'error': 'Email address is required (please provide session token or email)'
            })

        if not session_id:
            return create_response(400, {
                'success': False,
                'error': 'Session ID is required'
            })

        # SECURITY: Validate session ID format to prevent path traversal
        if not SESSION_ID_PATTERN.match(session_id):
            log_invalid_session_format(session_id, email=email, ip_address=ip_address)
            logger.error(f"[SECURITY] Invalid session ID format: {session_id}")
            return create_response(400, {
                'success': False,
                'error': 'Invalid session ID format'
            })

        if '..' in session_id or '/' in session_id or '\\' in session_id:
            log_path_traversal_attempt(session_id, email=email, ip_address=ip_address)
            logger.error(f"[SECURITY] Path traversal attempt: {session_id}")

            # SECURITY FLAG: Revoke token on path traversal attempt (attack indicator)
            session_token = headers.get('X-Session-Token') or headers.get('x-session-token')
            if session_token:
                revoke_token(session_token, reason="path_traversal_attempt")
                logger.critical(f"[SECURITY] REVOKED token for {email} - path traversal attack attempt")

            return create_response(400, {
                'success': False,
                'error': 'Invalid session ID. Your session has been revoked for security.',
                'token_revoked': True
            })

        # SECURITY: Check rate limit (higher limit for dev environment)
        # Dev: 200 requests/min for testing, Prod: 20 requests/min (accounts for WebSocket checks)
        import os
        env = os.environ.get('ENVIRONMENT', 'prod')
        max_requests = 200 if env == 'dev' else 20
        is_allowed, remaining = check_rate_limit(email, 'getViewerData', max_requests=max_requests, window_minutes=1)
        if not is_allowed:
            log_rate_limit_exceeded(email, action='getViewerData', limit=max_requests, ip_address=ip_address)
            logger.warning(f"[SECURITY] Rate limit exceeded for {email}")

            # SECURITY: Only revoke token in prod (dev needs flexibility for testing)
            token_revoked = False
            if env == 'prod':
                session_token = headers.get('X-Session-Token') or headers.get('x-session-token')
                if session_token:
                    revoke_token(session_token, reason="excessive_rate_limit_violations")
                    logger.warning(f"[SECURITY] Revoked token for {email} due to rate limit abuse")
                    token_revoked = True

            error_msg = 'Rate limit exceeded. Your session has been revoked for security. Please re-validate your email.' if token_revoked else 'Rate limit exceeded. Please wait a moment before retrying.'

            return create_response(429, {
                'success': False,
                'error': error_msg,
                'retry_after': 60,
                'token_revoked': token_revoked
            })

        # SECURITY: Verify email is validated in DynamoDB
        from dynamodb_schemas import is_email_validated

        if not is_email_validated(email):
            log_unvalidated_email_access(email, ip_address=ip_address)
            logger.warning(f"[SECURITY] Unvalidated email attempted access: {email}")
            return create_response(401, {
                'success': False,
                'error': 'Email not validated. Please validate your email first.'
            })

        # SECURITY: Skip ownership check for demo sessions (no DynamoDB record needed)
        is_demo_session = 'demo' in session_id.lower() if session_id else False

        if is_demo_session:
            logger.info(f"[VIEWER_DATA] Demo session detected, skipping ownership check: {session_id}")
        else:
            # SECURITY: Verify session ownership (with Lambda caching for performance)
            ownership_result = _verify_session_ownership_cached(email, session_id)
            if not ownership_result:
                # Check if session exists first to distinguish between "not found" and "unauthorized"
                try:
                    runs_table = boto3.resource('dynamodb', region_name='us-east-1').Table('perplexity-validator-runs')
                    response = runs_table.get_item(Key={'session_id': session_id})
                    session_exists = 'Item' in response
                except:
                    session_exists = False

                if not session_exists:
                    # Session not found - likely race condition or invalid session_id
                    # Don't revoke token for this (user didn't do anything wrong)
                    logger.warning(f"[SECURITY] Session not found (may be processing): {session_id} for {email}")
                    return create_response(404, {
                        'success': False,
                        'error': 'Session not found. If preview just completed, please try again in a moment.',
                        'session_not_found': True
                    })
                else:
                    # Session exists but belongs to someone else - actual ownership violation
                    log_ownership_violation(email, session_id, ip_address=ip_address)
                    logger.error(f"[SECURITY] Ownership violation - {email} attempted to access {session_id}")

                    # SECURITY FLAG: Revoke token immediately on ownership violation (most severe)
                    session_token = headers.get('X-Session-Token') or headers.get('x-session-token')
                    if session_token:
                        revoke_token(session_token, reason="ownership_violation")
                        logger.critical(f"[SECURITY] REVOKED token for {email} - attempted unauthorized access to {session_id}")

                    return create_response(403, {
                        'success': False,
                        'error': 'Access denied: you do not own this session. Your session has been revoked for security.',
                        'token_revoked': True
                    })
                # End of ownership check block

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
        excel_key, excel_filename = _find_excel_file(active_bucket, actual_results_prefix, is_full_validation)

        enhanced_download_url = None
        if excel_key:
            enhanced_download_url = _generate_presigned_url(
                active_bucket,
                excel_key,
                excel_filename or 'results.xlsx',
                email=email,
                session_id=session_id
            )

        # Generate JSON download URL
        json_download_url = _generate_presigned_url(
            active_bucket,
            metadata_key,
            f"table_metadata_v{config_version}.json",
            email=email,
            session_id=session_id
        )

        # Extract table name from metadata or session
        table_name = table_metadata.get('table_name') or _extract_table_name(session_id)

        # Load session_info to get clean_table_name and analysis date
        # IMPORTANT: Load from active_bucket (not default bucket) since results may be in -dev bucket
        clean_table_name = None
        original_filename = None
        analysis_date = None

        try:
            # Load session_info directly from the active bucket where we found results
            session_info_key = f"{session_path}session_info.json"
            session_info = _load_json_from_s3(active_bucket, session_info_key)

            if session_info:
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

                logger.info(f"[VIEWER_DATA] Loaded session_info from {active_bucket}: clean_table_name='{clean_table_name}', analysis_date='{analysis_date}'")
            else:
                logger.warning(f"[VIEWER_DATA] No session_info.json found in {active_bucket}")
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


def _find_excel_file(bucket: str, prefix: str, is_full_validation: bool = False) -> tuple:
    """Find enhanced Excel file in the results folder.

    Args:
        bucket: S3 bucket name
        prefix: Results folder prefix
        is_full_validation: If True, exclude preview Excel files

    Returns:
        Tuple of (s3_key, filename) or (None, None) if not found
    """
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix
        )

        # Collect all Excel files
        excel_files = []
        for obj in response.get('Contents', []):
            key = obj['Key']
            if key.endswith('.xlsx'):
                filename = key.split('/')[-1]
                excel_files.append((key, filename))

        if not excel_files:
            return None, None

        # Filter based on validation type
        if is_full_validation:
            # For full validation, EXCLUDE preview files and prefer enhanced files
            non_preview_files = [
                (key, filename) for key, filename in excel_files
                if 'preview' not in filename.lower()
            ]

            if non_preview_files:
                # Prefer enhanced files
                enhanced_files = [
                    (key, filename) for key, filename in non_preview_files
                    if 'enhanced' in filename.lower()
                ]
                if enhanced_files:
                    logger.info(f"[VIEWER_DATA] Found full validation enhanced Excel: {enhanced_files[0][1]}")
                    return enhanced_files[0]

                # Fallback to any non-preview xlsx
                logger.info(f"[VIEWER_DATA] Found full validation Excel: {non_preview_files[0][1]}")
                return non_preview_files[0]
        else:
            # For preview, prefer preview files
            preview_files = [
                (key, filename) for key, filename in excel_files
                if 'preview' in filename.lower()
            ]

            if preview_files:
                # Prefer enhanced preview files
                enhanced_preview = [
                    (key, filename) for key, filename in preview_files
                    if 'enhanced' in filename.lower()
                ]
                if enhanced_preview:
                    logger.info(f"[VIEWER_DATA] Found preview enhanced Excel: {enhanced_preview[0][1]}")
                    return enhanced_preview[0]

                logger.info(f"[VIEWER_DATA] Found preview Excel: {preview_files[0][1]}")
                return preview_files[0]

        # Last resort fallback: any enhanced file, then any xlsx file
        enhanced_files = [(key, filename) for key, filename in excel_files if 'enhanced' in filename.lower()]
        if enhanced_files:
            logger.warning(f"[VIEWER_DATA] Using fallback enhanced Excel: {enhanced_files[0][1]}")
            return enhanced_files[0]

        logger.warning(f"[VIEWER_DATA] Using fallback Excel: {excel_files[0][1]}")
        return excel_files[0]

    except Exception as e:
        logger.error(f"[VIEWER_DATA] Error finding Excel file: {e}")
        return None, None


def _generate_presigned_url(
    bucket: str,
    key: str,
    filename: str,
    email: str,
    session_id: str,
    expiration: int = 300  # REDUCED from 3600 to 5 minutes for security
) -> Optional[str]:
    """
    Generate a presigned download URL with ownership verification.

    SECURITY: Verifies that the requesting email owns the session before
    generating download URLs. Prevents unauthorized file access.

    Args:
        bucket: S3 bucket name
        key: S3 object key
        filename: Filename for Content-Disposition header
        email: User's email (must own the session)
        session_id: Session ID (for ownership verification)
        expiration: URL expiration in seconds (default: 300 = 5 minutes)

    Returns:
        Presigned URL if ownership verified, None otherwise
    """
    # SECURITY: Verify ownership before generating URL
    if not _verify_session_ownership_cached(email, session_id):
        logger.error(f"[SECURITY] Ownership check failed for presigned URL: {email} -> {session_id}")
        return None

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
