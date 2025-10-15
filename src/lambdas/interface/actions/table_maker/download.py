"""
Handles table download requests - generates presigned URLs for table files
"""
import logging
from typing import Dict, Any
from interface_lambda.utils.helpers import create_response
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle_table_download_url(request_data: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Generate presigned download URL for the unvalidated table Excel file.

    Args:
        request_data: Request containing email and session_id
        context: Lambda context

    Returns:
        Response with presigned download URL
    """
    try:
        email = request_data.get('email')
        session_id = request_data.get('session_id')

        if not email or not session_id:
            logger.error("[TABLE_DOWNLOAD] Missing email or session_id")
            return create_response(400, {
                'success': False,
                'error': 'Missing required parameters: email and session_id'
            })

        logger.info(f"[TABLE_DOWNLOAD] Generating download URL for session {session_id}")

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Get the Excel file S3 key (the original input file with _input suffix)
        excel_content, excel_s3_key = storage_manager.get_excel_file(email, session_id)

        if not excel_s3_key:
            logger.error(f"[TABLE_DOWNLOAD] No Excel file found for session {session_id}")
            return create_response(404, {
                'success': False,
                'error': 'Table file not found for this session'
            })

        # Generate presigned URL (valid for 1 hour)
        presigned_url = storage_manager.generate_presigned_url(excel_s3_key, expiration=3600)

        if not presigned_url:
            logger.error(f"[TABLE_DOWNLOAD] Failed to generate presigned URL for {excel_s3_key}")
            return create_response(500, {
                'success': False,
                'error': 'Failed to generate download URL'
            })

        # Extract filename from S3 key
        filename = excel_s3_key.split('/')[-1]

        # If it's the _input suffix version, use a cleaner name for download
        if filename.endswith('_input.xlsx'):
            # Use session ID for the download filename
            filename = f"table_{session_id}.xlsx"

        logger.info(f"[TABLE_DOWNLOAD] Generated presigned URL for {filename}")

        return create_response(200, {
            'success': True,
            'download_url': presigned_url,
            'filename': filename,
            'expires_in': 3600  # 1 hour in seconds
        })

    except Exception as e:
        logger.error(f"[TABLE_DOWNLOAD] Error generating download URL: {e}")
        import traceback
        logger.error(f"[TABLE_DOWNLOAD] Traceback: {traceback.format_exc()}")
        return create_response(500, {
            'success': False,
            'error': f'Failed to generate download URL: {str(e)}'
        })
