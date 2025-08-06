"""
Functions for interacting with Amazon S3.
"""
import logging
import boto3
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

# Use unified bucket if available, otherwise fallback to legacy
if os.environ.get('S3_UNIFIED_BUCKET'):
    S3_RESULTS_BUCKET = os.environ.get('S3_UNIFIED_BUCKET')
    logger.info(f"S3_MANAGER: Using unified bucket: {S3_RESULTS_BUCKET}")
else:
    S3_RESULTS_BUCKET = os.environ.get('S3_RESULTS_BUCKET', 'perplexity-results')
    logger.info(f"S3_MANAGER: Using legacy bucket: {S3_RESULTS_BUCKET}")

def upload_file_to_s3(file_content, bucket, key, content_type='application/octet-stream'):
    """Upload file content to S3."""
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=file_content,
            ContentType=content_type
        )
        logger.info(f"Uploaded file to s3://{bucket}/{key}")
        return True
    except Exception as e:
        logger.error(f"Error uploading to S3: {str(e)}")
        return False

def download_file_from_s3(bucket, key):
    """Download file content from S3."""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read()
        logger.info(f"Downloaded file from s3://{bucket}/{key}")
        return content
    except Exception as e:
        logger.error(f"Error downloading from S3: {str(e)}")
        return None

def generate_presigned_url(bucket, key, expiration=3600):
    """Generate a presigned URL for downloading a file from S3."""
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        logger.error(f"Error generating presigned URL: {str(e)}")
        return None 