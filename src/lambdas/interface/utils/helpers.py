"""
Shared helper functions for the interface lambda.
"""
import re
import secrets
import logging
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def clean_table_name(filename: str, for_display: bool = True) -> str:
    """
    Extract a clean table name from a filename.

    Removes:
    - File extensions (.xlsx, .xls, .csv)
    - Common suffixes: _input, _validated, _enhanced, _results, _output
    - Date patterns: _YYYYMMDD, _YYYY-MM-DD, _Update_YYYYMMDD
    - Upload prefixes: upload_xxxx_
    - UUID-like patterns at the end

    Examples (for_display=True):
        'upload_abc123_MyTable_input.xlsx' -> 'MyTable'
        'CompanyData_enhanced_20250115.xlsx' -> 'CompanyData'
        'Q4_Financial_Results_input.xlsx' -> 'Q4 Financial Results'

    Examples (for_display=False, keeps underscores for filenames):
        'Q4_Financial_Results_input.xlsx' -> 'Q4_Financial_Results'

    Args:
        filename: Original filename
        for_display: If True, replace underscores with spaces for UI display.
                    If False, keep underscores (suitable for filenames).

    Returns:
        Clean table name
    """
    if not filename:
        return "Untitled Table" if for_display else "Untitled_Table"

    # Remove file extension
    base_name = re.sub(r'\.(xlsx|xls|csv)$', '', filename, flags=re.IGNORECASE)

    # Remove upload_xxxx_ prefix (presigned upload IDs)
    base_name = re.sub(r'^upload_[a-f0-9]+_', '', base_name, flags=re.IGNORECASE)

    # Remove common suffixes (case insensitive)
    suffixes_to_remove = [
        r'_input$',
        r'_validated$',
        r'_enhanced$',
        r'_results$',
        r'_output$',
        r'enhanced_',
    ]
    for pattern in suffixes_to_remove:
        base_name = re.sub(pattern, '', base_name, flags=re.IGNORECASE)

    # Remove date patterns: _YYYYMMDD or _YYYY-MM-DD at end
    base_name = re.sub(r'_\d{8}$', '', base_name)
    base_name = re.sub(r'_\d{4}-\d{2}-\d{2}$', '', base_name)

    # Remove _Update_YYYYMMDD patterns
    base_name = re.sub(r'_Update_\d{8}$', '', base_name, flags=re.IGNORECASE)

    # Remove trailing UUID-like patterns (8+ hex chars at end after underscore)
    base_name = re.sub(r'_[a-f0-9]{8,}$', '', base_name, flags=re.IGNORECASE)

    # Clean up any trailing/leading underscores
    base_name = base_name.strip('_')

    if for_display:
        # Replace underscores with spaces for display
        display_name = base_name.replace('_', ' ')
        # Clean up multiple spaces
        display_name = re.sub(r'\s+', ' ', display_name).strip()
        return display_name if display_name else "Untitled Table"
    else:
        # Keep underscores for filename use
        # Clean up multiple underscores
        base_name = re.sub(r'_+', '_', base_name).strip('_')
        return base_name if base_name else "Untitled_Table"


def generate_reference_pin() -> str:
    """Generate a 6-digit reference pin for the run."""
    return f"{secrets.randbelow(900000) + 100000:06d}"

def create_email_folder_path(email_address: str) -> str:
    """
    Create S3 folder path based on email address.
    If @ is allowed in S3 keys, use email directly.
    Otherwise, use domain/user structure.
    """
    if not email_address:
        return "no-email"
    
    try:
        # Clean the email address for use in S3 paths
        cleaned_email = email_address.lower().strip()
        
        # S3 allows @ in object keys, so we can use it directly
        # But let's replace @ with underscore for better compatibility
        # and avoid potential issues with some tools
        if '@' in cleaned_email:
            user, domain = cleaned_email.split('@', 1)
            # Use domain/user structure for better organization
            folder_path = f"{domain}/{user}"
        else:
            # If no @ found, use as-is
            folder_path = cleaned_email
        
        # Sanitize for S3 compatibility
        # Replace any remaining special characters
        folder_path = folder_path.replace(' ', '_').replace('+', 'plus')
        
        return folder_path
    except Exception as e:
        logger.warning(f"Error creating email folder path for {email_address}: {e}")
        return "email-error"

def create_response(status_code, body, is_json=True):
    """
    Creates a standard API Gateway response dictionary, ensuring CORS headers are always included.
    
    Args:
        status_code (int): The HTTP status code for the response.
        body (dict or str): The response body.
        is_json (bool): If True, the body will be JSON-stringified.
        
    Returns:
        dict: A valid API Gateway response object.
    """
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    }
    if is_json:
        headers['Content-Type'] = 'application/json'
        response_body = json.dumps(body)
    else:
        response_body = body

    return {
        'statusCode': status_code,
        'headers': headers,
        'body': response_body
    } 