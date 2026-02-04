"""
Demo Data Handler - Public Demo Tables (No Email Required)

Handles getDemoData requests to load demo tables from the public demos folder.
No authentication required - these are public demo tables.

Demo tables are stored at:
  - Dev: s3://hyperplexity-storage-dev/demos/interactive_tables/{table_name}/
  - Prod: s3://hyperplexity-storage/demos/interactive_tables/{table_name}/
"""
import json
import logging
import boto3
import os
import re
from typing import Dict, Any

from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')


def handle(request_data: Dict[str, Any], context) -> Dict:
    """
    Handle getDemoData requests - no authentication required.

    Required params:
        - table_name: Name of the demo table to load

    Returns:
        - success: bool
        - table_metadata: Interactive table metadata JSON
        - clean_table_name: Display name for the table
        - is_demo: True (always)
    """
    try:
        table_name = request_data.get('table_name', '').strip()

        if not table_name:
            return create_response(400, {
                'success': False,
                'error': 'Table name is required'
            })

        # Sanitize table name to prevent path traversal attacks
        # Allow only alphanumeric, hyphens, and underscores
        safe_table_name = re.sub(r'[^a-zA-Z0-9_-]', '', table_name)
        if safe_table_name != table_name:
            logger.warning(f"[DEMO_DATA] Table name sanitized: '{table_name}' -> '{safe_table_name}'")
            if not safe_table_name:
                return create_response(400, {
                    'success': False,
                    'error': 'Invalid table name format. Use only letters, numbers, hyphens, and underscores.'
                })

        # Determine bucket based on environment
        # For demos, we use the appropriate bucket based on environment
        base_bucket = os.environ.get('S3_UNIFIED_BUCKET', 'hyperplexity-storage')
        env = os.environ.get('ENVIRONMENT', 'prod')

        # Use dev bucket for dev environment
        if env == 'dev' or base_bucket.endswith('-dev'):
            bucket = base_bucket if base_bucket.endswith('-dev') else f"{base_bucket}-dev"
        else:
            bucket = base_bucket.replace('-dev', '')

        # Demo path
        demo_path = f"demos/interactive_tables/{safe_table_name}/"
        metadata_key = f"{demo_path}table_metadata.json"

        logger.info(f"[DEMO_DATA] Loading demo from s3://{bucket}/{metadata_key}")

        # Load table metadata
        try:
            response = s3_client.get_object(Bucket=bucket, Key=metadata_key)
            table_metadata = json.loads(response['Body'].read().decode('utf-8'))
        except s3_client.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'NoSuchKey':
                logger.warning(f"[DEMO_DATA] Demo table not found: {safe_table_name}")
                return create_response(404, {
                    'success': False,
                    'error': 'Whoops - this table might never have existed, or it was deleted! Either way, it\'s not here.'
                })
            raise

        # Generate clean display name from table_name
        clean_name = safe_table_name.replace('-', ' ').replace('_', ' ').title()

        # Check for optional info.json with additional metadata
        try:
            info_key = f"{demo_path}info.json"
            info_response = s3_client.get_object(Bucket=bucket, Key=info_key)
            info = json.loads(info_response['Body'].read().decode('utf-8'))
            # Override clean_name if provided in info
            if info.get('display_name'):
                clean_name = info.get('display_name')
            logger.info(f"[DEMO_DATA] Loaded info.json for {safe_table_name}")
        except Exception:
            # Info file is optional - ignore errors
            pass

        # Find Excel file in demo folder and generate presigned download URL
        excel_download_url = None
        try:
            list_resp = s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=demo_path
            )
            for obj in list_resp.get('Contents', []):
                if obj['Key'].endswith('.xlsx'):
                    excel_filename = obj['Key'].split('/')[-1]
                    excel_download_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={
                            'Bucket': bucket,
                            'Key': obj['Key'],
                            'ResponseContentDisposition': f'attachment; filename="{excel_filename}"'
                        },
                        ExpiresIn=3600
                    )
                    logger.info(f"[DEMO_DATA] Found Excel file: {excel_filename}")
                    break
        except Exception as e:
            logger.debug(f"[DEMO_DATA] No Excel file found: {e}")

        logger.info(f"[DEMO_DATA] Successfully loaded demo: {safe_table_name} ({clean_name})")

        return create_response(200, {
            'success': True,
            'table_metadata': table_metadata,
            'table_name': safe_table_name,
            'clean_table_name': clean_name,
            'is_demo': True,
            'enhanced_download_url': excel_download_url
        })

    except Exception as e:
        logger.error(f"[DEMO_DATA] Error: {e}")
        import traceback
        logger.error(f"[DEMO_DATA] Traceback: {traceback.format_exc()}")
        return create_response(500, {
            'success': False,
            'error': 'Failed to load demo data'
        })
