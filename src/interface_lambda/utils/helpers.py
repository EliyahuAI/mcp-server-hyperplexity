"""
Shared helper functions for the interface lambda.
"""
import secrets
import logging
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)


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