"""
Handles the downloadConfig action - serves config files from S3
"""
import logging
import json
import boto3
import os
import base64
from pathlib import Path

from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(request_data, context):
    """
    Handles the downloadConfig action - downloads config from S3 and returns it
    """
    config_s3_key = request_data.get('config_s3_key', '')
    
    if not config_s3_key:
        return create_response(400, {'error': 'Missing config_s3_key parameter'})
    
    try:
        # Download config from S3
        s3_client = boto3.client('s3')
        
        # Use unified bucket for downloads if available
        if os.environ.get('S3_UNIFIED_BUCKET'):
            bucket_name = os.environ.get('S3_DOWNLOAD_BUCKET', os.environ.get('S3_UNIFIED_BUCKET'))
            logger.info(f"DOWNLOAD_CONFIG: Using download bucket: {bucket_name}")
        else:
            bucket_name = os.environ.get('S3_CONFIG_BUCKET', 'perplexity-config-downloads')
            logger.info(f"DOWNLOAD_CONFIG: Using legacy config bucket: {bucket_name}")
        
        # Get the object
        response = s3_client.get_object(Bucket=bucket_name, Key=config_s3_key)
        config_content = response['Body'].read().decode('utf-8')
        
        # Validate it's valid JSON
        config_data = json.loads(config_content)
        
        # Extract filename from key
        filename = config_s3_key.split('/')[-1]
        
        # Return as downloadable file
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
            },
            'body': config_content,
            'isBase64Encoded': False
        }
        
    except s3_client.exceptions.NoSuchKey:
        return create_response(404, {'error': 'Config file not found'})
    except json.JSONDecodeError:
        return create_response(500, {'error': 'Invalid config file format'})
    except Exception as e:
        logger.error(f"Error downloading config: {str(e)}")
        return create_response(500, {'error': f'Failed to download config: {str(e)}'})